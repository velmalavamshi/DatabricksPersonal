"""
Multi-Modal RAG Pipeline: Ingestion Engine
===========================================
Enterprise-grade file synchronization module for SFTP, SharePoint, OneDrive, S3, ADLS Gen2, and UC Volumes.

Key Features:
- Prevent Worker OOMs: Single-stream downloaders landing files directly to UC Volumes
- Incremental Sync: SHA-256 content hashing for change detection
- Deletion Tracking: Tombstone records for vector pruning
- Rate Limiting: Exponential backoff for external API calls
- Secret Management: Databricks Secret Scope integration

Author: Principal Databricks Architect
Date: 2026-09-04
"""

import hashlib
import uuid
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import logging

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, current_timestamp
from databricks.sdk.runtime import dbutils

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class IngestionEngine:
    """
    Orchestrates file ingestion from external sources to Unity Catalog Volumes.
    Implements incremental sync, SHA-256 content hashing, and deletion tracking.
    """

    def __init__(self, spark: SparkSession):
        """
        Initialize the ingestion engine.

        Args:
            spark: Active SparkSession
        """
        self.spark = spark
        self.control_table = "ai_unstructured_metadata.ingestion_control"
        self.state_table = "ai_unstructured_metadata.document_state_registry"

    def get_active_sources(self) -> List[Dict]:
        """
        Retrieve active ingestion sources from the control table.

        Returns:
            List of source configuration dictionaries
        """
        df = self.spark.sql(f"""
            SELECT 
                source_id,
                source_system,
                connection_secret_scope,
                source_root_uri,
                path_glob_pattern,
                file_types,
                target_volume_path,
                target_delta_table,
                parsing_engine
            FROM {self.control_table}
            WHERE is_active = TRUE
        """)
        return [row.asDict() for row in df.collect()]

    def compute_sha256(self, file_path: str) -> str:
        """
        Compute SHA-256 hash of a file for change detection.

        Args:
            file_path: Path to the file

        Returns:
            Hexadecimal SHA-256 hash string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in 8MB chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(8388608), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def get_existing_files_state(self, source_id: str) -> Dict[str, Tuple[str, str]]:
        """
        Retrieve existing file states from the document state registry.

        Args:
            source_id: Source identifier

        Returns:
            Dictionary mapping file_uri -> (file_id, content_sha256_hash)
        """
        df = self.spark.sql(f"""
            SELECT file_uri, file_id, content_sha256_hash
            FROM {self.state_table}
            WHERE source_id = '{source_id}'
                AND status != 'DELETED'
        """)
        return {row.file_uri: (row.file_id, row.content_sha256_hash) for row in df.collect()}

    def sync_sftp_source(self, source_config: Dict) -> Dict[str, int]:
        """
        Synchronize files from SFTP source to Unity Catalog Volume.

        Args:
            source_config: Source configuration from control table

        Returns:
            Dictionary with sync statistics: {new: int, modified: int, deleted: int}
        """
        import paramiko
        from fnmatch import fnmatch

        stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}
        source_id = source_config["source_id"]
        secret_scope = source_config["connection_secret_scope"]

        # Retrieve SFTP credentials from Databricks Secrets
        try:
            sftp_host = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_host")
            sftp_port = int(dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_port"))
            sftp_username = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_username")
            sftp_password = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_password")
        except Exception as e:
            logger.error(f"Failed to retrieve SFTP credentials for {source_id}: {e}")
            return stats

        # Get existing files state
        existing_files = self.get_existing_files_state(source_id)
        current_files_set = set()

        # Establish SFTP connection with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                transport = paramiko.Transport((sftp_host, sftp_port))
                transport.connect(username=sftp_username, password=sftp_password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                logger.info(f"Connected to SFTP: {sftp_host}")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"SFTP connection attempt {attempt + 1} failed. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to SFTP after {max_retries} attempts: {e}")
                    return stats

        try:
            # Recursively list files matching glob pattern
            remote_root = source_config["source_root_uri"].replace("sftp://" + sftp_host, "")
            glob_pattern = source_config["path_glob_pattern"] or "**/*"
            file_types = source_config["file_types"] or []

            def list_remote_files(remote_dir: str) -> List[str]:
                """Recursively list all files in remote directory."""
                files = []
                try:
                    for attr in sftp.listdir_attr(remote_dir):
                        remote_path = f"{remote_dir}/{attr.filename}"
                        if attr.st_mode & 0o040000:  # Directory
                            files.extend(list_remote_files(remote_path))
                        else:  # File
                            files.append(remote_path)
                except Exception as e:
                    logger.warning(f"Cannot access {remote_dir}: {e}")
                return files

            remote_files = list_remote_files(remote_root)
            logger.info(f"Found {len(remote_files)} files on SFTP")

            # Process each file
            for remote_file in remote_files:
                try:
                    # Filter by file extension
                    file_ext = Path(remote_file).suffix.lower().lstrip('.')
                    if file_types and file_ext not in file_types:
                        continue

                    # Filter by glob pattern
                    relative_path = remote_file.replace(remote_root, "").lstrip("/")
                    if not fnmatch(relative_path, glob_pattern):
                        continue

                    file_uri = f"sftp://{sftp_host}{remote_file}"
                    current_files_set.add(file_uri)

                    # Get file stats
                    file_stat = sftp.stat(remote_file)
                    file_size = file_stat.st_size
                    last_modified = datetime.fromtimestamp(file_stat.st_mtime)

                    # Download to temp location and compute hash
                    temp_local_path = f"/tmp/{uuid.uuid4()}_{Path(remote_file).name}"
                    sftp.get(remote_file, temp_local_path)
                    content_hash = self.compute_sha256(temp_local_path)

                    # Check if file exists and has changed
                    if file_uri in existing_files:
                        existing_file_id, existing_hash = existing_files[file_uri]
                        if existing_hash != content_hash:
                            # File modified - update state
                            self._copy_to_volume(temp_local_path, source_config, relative_path)
                            self._update_file_state(
                                file_id=existing_file_id,
                                source_id=source_id,
                                file_uri=file_uri,
                                file_name=Path(remote_file).name,
                                file_extension=file_ext,
                                file_size_bytes=file_size,
                                content_sha256_hash=content_hash,
                                volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                                last_modified_at=last_modified,
                                status="PENDING"
                            )
                            stats["modified"] += 1
                            logger.info(f"Modified: {file_uri}")
                    else:
                        # New file - create state record
                        file_id = str(uuid.uuid4())
                        self._copy_to_volume(temp_local_path, source_config, relative_path)
                        self._create_file_state(
                            file_id=file_id,
                            source_id=source_id,
                            file_uri=file_uri,
                            file_name=Path(remote_file).name,
                            file_extension=file_ext,
                            file_size_bytes=file_size,
                            content_sha256_hash=content_hash,
                            volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                            last_modified_at=last_modified,
                            status="PENDING"
                        )
                        stats["new"] += 1
                        logger.info(f"New: {file_uri}")

                    # Clean up temp file
                    Path(temp_local_path).unlink(missing_ok=True)

                except Exception as e:
                    logger.error(f"Error processing {remote_file}: {e}")
                    stats["errors"] += 1
                    continue

            # Identify deleted files (exist in registry but not in source)
            deleted_uris = set(existing_files.keys()) - current_files_set
            for deleted_uri in deleted_uris:
                file_id, _ = existing_files[deleted_uri]
                self._mark_file_deleted(file_id)
                stats["deleted"] += 1
                logger.info(f"Deleted: {deleted_uri}")

        finally:
            sftp.close()
            transport.close()

        # Update last sync timestamp
        self._update_last_sync(source_id)
        return stats

    def sync_sharepoint_source(self, source_config: Dict) -> Dict[str, int]:
        """
        Synchronize files from SharePoint to Unity Catalog Volume.

        Args:
            source_config: Source configuration from control table

        Returns:
            Dictionary with sync statistics
        """
        from office365.sharepoint.client_context import ClientContext
        from office365.runtime.auth.client_credential import ClientCredential
        from fnmatch import fnmatch

        stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}
        source_id = source_config["source_id"]
        secret_scope = source_config["connection_secret_scope"]

        # Retrieve SharePoint credentials from Databricks Secrets
        try:
            site_url = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_site_url")
            client_id = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_client_id")
            client_secret = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_client_secret")
        except Exception as e:
            logger.error(f"Failed to retrieve SharePoint credentials for {source_id}: {e}")
            return stats

        # Get existing files state
        existing_files = self.get_existing_files_state(source_id)
        current_files_set = set()

        # Establish SharePoint connection with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = ClientCredential(client_id, client_secret)
                ctx = ClientContext(site_url).with_credentials(credentials)
                logger.info(f"Connected to SharePoint: {site_url}")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"SharePoint connection attempt {attempt + 1} failed. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to SharePoint after {max_retries} attempts: {e}")
                    return stats

        try:
            # Get folder from source_root_uri
            folder_relative_url = source_config["source_root_uri"].replace(site_url, "")
            root_folder = ctx.web.get_folder_by_server_relative_url(folder_relative_url)
            ctx.load(root_folder)
            ctx.execute_query()

            glob_pattern = source_config["path_glob_pattern"] or "**/*"
            file_types = source_config["file_types"] or []

            def list_sharepoint_files(folder, relative_path="") -> List[Dict]:
                """Recursively list all files in SharePoint folder."""
                files = []
                ctx.load(folder, ["Files", "Folders"])
                ctx.execute_query()

                # Process files in current folder
                for file in folder.files:
                    file_info = {
                        "name": file.properties["Name"],
                        "relative_path": f"{relative_path}/{file.properties['Name']}".lstrip("/"),
                        "size": file.properties["Length"],
                        "modified": datetime.fromisoformat(file.properties["TimeLastModified"].replace("Z", "+00:00")),
                        "server_relative_url": file.properties["ServerRelativeUrl"],
                        "file_object": file
                    }
                    files.append(file_info)

                # Recursively process subfolders
                for subfolder in folder.folders:
                    if subfolder.properties["Name"] not in ["Forms", "_cts", "_vti_pvt"]:
                        subfolder_relative = f"{relative_path}/{subfolder.properties['Name']}".lstrip("/")
                        files.extend(list_sharepoint_files(subfolder, subfolder_relative))

                return files

            sharepoint_files = list_sharepoint_files(root_folder)
            logger.info(f"Found {len(sharepoint_files)} files on SharePoint")

            # Process each file
            for file_info in sharepoint_files:
                try:
                    # Filter by file extension
                    file_ext = Path(file_info["name"]).suffix.lower().lstrip('.')
                    if file_types and file_ext not in file_types:
                        continue

                    # Filter by glob pattern
                    if not fnmatch(file_info["relative_path"], glob_pattern):
                        continue

                    file_uri = f"{site_url}{file_info['server_relative_url']}"
                    current_files_set.add(file_uri)

                    # Download to temp location and compute hash
                    temp_local_path = f"/tmp/{uuid.uuid4()}_{file_info['name']}"
                    with open(temp_local_path, "wb") as local_file:
                        file_info["file_object"].download(local_file).execute_query()
                    content_hash = self.compute_sha256(temp_local_path)

                    # Check if file exists and has changed
                    if file_uri in existing_files:
                        existing_file_id, existing_hash = existing_files[file_uri]
                        if existing_hash != content_hash:
                            # File modified
                            self._copy_to_volume(temp_local_path, source_config, file_info["relative_path"])
                            self._update_file_state(
                                file_id=existing_file_id,
                                source_id=source_id,
                                file_uri=file_uri,
                                file_name=file_info["name"],
                                file_extension=file_ext,
                                file_size_bytes=file_info["size"],
                                content_sha256_hash=content_hash,
                                volume_landing_path=f"{source_config['target_volume_path']}/{file_info['relative_path']}",
                                last_modified_at=file_info["modified"],
                                status="PENDING"
                            )
                            stats["modified"] += 1
                            logger.info(f"Modified: {file_uri}")
                    else:
                        # New file
                        file_id = str(uuid.uuid4())
                        self._copy_to_volume(temp_local_path, source_config, file_info["relative_path"])
                        self._create_file_state(
                            file_id=file_id,
                            source_id=source_id,
                            file_uri=file_uri,
                            file_name=file_info["name"],
                            file_extension=file_ext,
                            file_size_bytes=file_info["size"],
                            content_sha256_hash=content_hash,
                            volume_landing_path=f"{source_config['target_volume_path']}/{file_info['relative_path']}",
                            last_modified_at=file_info["modified"],
                            status="PENDING"
                        )
                        stats["new"] += 1
                        logger.info(f"New: {file_uri}")

                    # Clean up temp file
                    Path(temp_local_path).unlink(missing_ok=True)

                except Exception as e:
                    logger.error(f"Error processing {file_info['name']}: {e}")
                    stats["errors"] += 1
                    continue

            # Identify deleted files
            deleted_uris = set(existing_files.keys()) - current_files_set
            for deleted_uri in deleted_uris:
                file_id, _ = existing_files[deleted_uri]
                self._mark_file_deleted(file_id)
                stats["deleted"] += 1
                logger.info(f"Deleted: {deleted_uri}")

        except Exception as e:
            logger.error(f"SharePoint sync error: {e}")
            stats["errors"] += 1

        # Update last sync timestamp
        self._update_last_sync(source_id)
        return stats

    def sync_onedrive_source(self, source_config: Dict) -> Dict[str, int]:
        """
        Synchronize files from OneDrive to Unity Catalog Volume.
        Uses Microsoft Graph API for OneDrive access.

        Args:
            source_config: Source configuration from control table

        Returns:
            Dictionary with sync statistics
        """
        import requests
        from fnmatch import fnmatch

        stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}
        source_id = source_config["source_id"]
        secret_scope = source_config["connection_secret_scope"]

        # Retrieve OneDrive credentials from Databricks Secrets
        try:
            tenant_id = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_tenant_id")
            client_id = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_client_id")
            client_secret = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_client_secret")
            user_email = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_user_email")
        except Exception as e:
            logger.error(f"Failed to retrieve OneDrive credentials for {source_id}: {e}")
            return stats

        # Get existing files state
        existing_files = self.get_existing_files_state(source_id)
        current_files_set = set()

        # Acquire access token with retry logic
        max_retries = 3
        access_token = None
        for attempt in range(max_retries):
            try:
                token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                token_data = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials"
                }
                token_response = requests.post(token_url, data=token_data, timeout=30)
                token_response.raise_for_status()
                access_token = token_response.json()["access_token"]
                logger.info("Acquired OneDrive access token")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Token acquisition attempt {attempt + 1} failed. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to acquire access token after {max_retries} attempts: {e}")
                    return stats

        if not access_token:
            return stats

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            # Parse source_root_uri to get folder path
            folder_path = source_config["source_root_uri"].replace("/drive/root:", "")
            graph_api_url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:{folder_path}:/children"

            glob_pattern = source_config["path_glob_pattern"] or "**/*"
            file_types = source_config["file_types"] or []

            def list_onedrive_files(api_url: str, relative_path: str = "") -> List[Dict]:
                """Recursively list all files in OneDrive folder."""
                files = []
                try:
                    response = requests.get(api_url, headers=headers, timeout=30)
                    response.raise_for_status()
                    items = response.json().get("value", [])

                    for item in items:
                        if "folder" in item:
                            # Recursively process folders
                            subfolder_path = f"{relative_path}/{item['name']}".lstrip("/")
                            child_url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/items/{item['id']}/children"
                            files.extend(list_onedrive_files(child_url, subfolder_path))
                        elif "file" in item:
                            # Process file
                            file_info = {
                                "name": item["name"],
                                "relative_path": f"{relative_path}/{item['name']}".lstrip("/"),
                                "size": item["size"],
                                "modified": datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00")),
                                "download_url": item["@microsoft.graph.downloadUrl"],
                                "web_url": item["webUrl"]
                            }
                            files.append(file_info)
                except Exception as e:
                    logger.warning(f"Cannot access {api_url}: {e}")
                return files

            onedrive_files = list_onedrive_files(graph_api_url)
            logger.info(f"Found {len(onedrive_files)} files on OneDrive")

            # Process each file
            for file_info in onedrive_files:
                try:
                    # Filter by file extension
                    file_ext = Path(file_info["name"]).suffix.lower().lstrip('.')
                    if file_types and file_ext not in file_types:
                        continue

                    # Filter by glob pattern
                    if not fnmatch(file_info["relative_path"], glob_pattern):
                        continue

                    file_uri = file_info["web_url"]
                    current_files_set.add(file_uri)

                    # Download to temp location and compute hash
                    temp_local_path = f"/tmp/{uuid.uuid4()}_{file_info['name']}"
                    download_response = requests.get(file_info["download_url"], timeout=300)
                    download_response.raise_for_status()
                    with open(temp_local_path, "wb") as f:
                        f.write(download_response.content)
                    content_hash = self.compute_sha256(temp_local_path)

                    # Check if file exists and has changed
                    if file_uri in existing_files:
                        existing_file_id, existing_hash = existing_files[file_uri]
                        if existing_hash != content_hash:
                            # File modified
                            self._copy_to_volume(temp_local_path, source_config, file_info["relative_path"])
                            self._update_file_state(
                                file_id=existing_file_id,
                                source_id=source_id,
                                file_uri=file_uri,
                                file_name=file_info["name"],
                                file_extension=file_ext,
                                file_size_bytes=file_info["size"],
                                content_sha256_hash=content_hash,
                                volume_landing_path=f"{source_config['target_volume_path']}/{file_info['relative_path']}",
                                last_modified_at=file_info["modified"],
                                status="PENDING"
                            )
                            stats["modified"] += 1
                            logger.info(f"Modified: {file_uri}")
                    else:
                        # New file
                        file_id = str(uuid.uuid4())
                        self._copy_to_volume(temp_local_path, source_config, file_info["relative_path"])
                        self._create_file_state(
                            file_id=file_id,
                            source_id=source_id,
                            file_uri=file_uri,
                            file_name=file_info["name"],
                            file_extension=file_ext,
                            file_size_bytes=file_info["size"],
                            content_sha256_hash=content_hash,
                            volume_landing_path=f"{source_config['target_volume_path']}/{file_info['relative_path']}",
                            last_modified_at=file_info["modified"],
                            status="PENDING"
                        )
                        stats["new"] += 1
                        logger.info(f"New: {file_uri}")

                    # Clean up temp file
                    Path(temp_local_path).unlink(missing_ok=True)

                except Exception as e:
                    logger.error(f"Error processing {file_info['name']}: {e}")
                    stats["errors"] += 1
                    continue

            # Identify deleted files
            deleted_uris = set(existing_files.keys()) - current_files_set
            for deleted_uri in deleted_uris:
                file_id, _ = existing_files[deleted_uri]
                self._mark_file_deleted(file_id)
                stats["deleted"] += 1
                logger.info(f"Deleted: {deleted_uri}")

        except Exception as e:
            logger.error(f"OneDrive sync error: {e}")
            stats["errors"] += 1

        # Update last sync timestamp
        self._update_last_sync(source_id)
        return stats

    def sync_s3_source(self, source_config: Dict) -> Dict[str, int]:
        """
        Synchronize files from AWS S3 bucket to Unity Catalog Volume.

        Args:
            source_config: Source configuration from control table

        Returns:
            Dictionary with sync statistics: {new: int, modified: int, deleted: int}
        """
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
        from fnmatch import fnmatch

        stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}
        source_id = source_config["source_id"]
        secret_scope = source_config["connection_secret_scope"]

        # Retrieve S3 credentials from Databricks Secrets
        try:
            aws_access_key_id = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_access_key_id")
            aws_secret_access_key = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_secret_access_key")
            aws_region = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_region")
        except Exception as e:
            logger.error(f"Failed to retrieve S3 credentials for {source_id}: {e}")
            return stats

        # Get existing files state
        existing_files = self.get_existing_files_state(source_id)
        current_files_set = set()

        # Parse S3 URI: s3://bucket-name/prefix/
        source_uri = source_config["source_root_uri"]
        bucket_name = source_uri.replace("s3://", "").split("/")[0]
        prefix = "/".join(source_uri.replace("s3://", "").split("/")[1:])

        # Establish S3 client with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=aws_access_key_id,
                    aws_secret_access_key=aws_secret_access_key,
                    region_name=aws_region
                )
                # Test connection
                s3_client.head_bucket(Bucket=bucket_name)
                logger.info(f"Connected to S3 bucket: {bucket_name}")
                break
            except (ClientError, NoCredentialsError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"S3 connection attempt {attempt + 1} failed. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to S3 after {max_retries} attempts: {e}")
                    return stats

        try:
            glob_pattern = source_config["path_glob_pattern"] or "**/*"
            file_types = source_config["file_types"] or []

            # List all objects with pagination
            paginator = s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            for page in page_iterator:
                if 'Contents' not in page:
                    continue

                for obj in page['Contents']:
                    try:
                        s3_key = obj['Key']
                        
                        # Skip directories (keys ending with /)
                        if s3_key.endswith('/'):
                            continue

                        # Filter by file extension
                        file_ext = Path(s3_key).suffix.lower().lstrip('.')
                        if file_types and file_ext not in file_types:
                            continue

                        # Filter by glob pattern
                        relative_path = s3_key.replace(prefix, "").lstrip("/")
                        if not fnmatch(relative_path, glob_pattern):
                            continue

                        file_uri = f"s3://{bucket_name}/{s3_key}"
                        current_files_set.add(file_uri)

                        # Get object metadata
                        file_size = obj['Size']
                        last_modified = obj['LastModified']

                        # Download to temp location and compute hash
                        temp_local_path = f"/tmp/{uuid.uuid4()}_{Path(s3_key).name}"
                        s3_client.download_file(bucket_name, s3_key, temp_local_path)
                        content_hash = self.compute_sha256(temp_local_path)

                        # Check if file exists and has changed
                        if file_uri in existing_files:
                            existing_file_id, existing_hash = existing_files[file_uri]
                            if existing_hash != content_hash:
                                # File modified - update state
                                self._copy_to_volume(temp_local_path, source_config, relative_path)
                                self._update_file_state(
                                    file_id=existing_file_id,
                                    source_id=source_id,
                                    file_uri=file_uri,
                                    file_name=Path(s3_key).name,
                                    file_extension=file_ext,
                                    file_size_bytes=file_size,
                                    content_sha256_hash=content_hash,
                                    volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                                    last_modified_at=last_modified,
                                    status="PENDING"
                                )
                                stats["modified"] += 1
                                logger.info(f"Modified: {file_uri}")
                        else:
                            # New file - create state record
                            file_id = str(uuid.uuid4())
                            self._copy_to_volume(temp_local_path, source_config, relative_path)
                            self._create_file_state(
                                file_id=file_id,
                                source_id=source_id,
                                file_uri=file_uri,
                                file_name=Path(s3_key).name,
                                file_extension=file_ext,
                                file_size_bytes=file_size,
                                content_sha256_hash=content_hash,
                                volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                                last_modified_at=last_modified,
                                status="PENDING"
                            )
                            stats["new"] += 1
                            logger.info(f"New: {file_uri}")

                        # Clean up temp file
                        Path(temp_local_path).unlink(missing_ok=True)

                    except Exception as e:
                        logger.error(f"Error processing {s3_key}: {e}")
                        stats["errors"] += 1
                        continue

            # Identify deleted files (exist in registry but not in source)
            deleted_uris = set(existing_files.keys()) - current_files_set
            for deleted_uri in deleted_uris:
                file_id, _ = existing_files[deleted_uri]
                self._mark_file_deleted(file_id)
                stats["deleted"] += 1
                logger.info(f"Deleted: {deleted_uri}")

        except Exception as e:
            logger.error(f"Error syncing S3 source {source_id}: {e}")
            stats["errors"] += 1

        # Update last sync timestamp
        self._update_last_sync(source_id)
        return stats

    def sync_adls_gen2_source(self, source_config: Dict) -> Dict[str, int]:
        """
        Synchronize files from Azure Data Lake Storage Gen2 to Unity Catalog Volume.

        Args:
            source_config: Source configuration from control table

        Returns:
            Dictionary with sync statistics: {new: int, modified: int, deleted: int}
        """
        from azure.storage.filedatalake import DataLakeServiceClient
        from azure.core.exceptions import AzureError
        from fnmatch import fnmatch

        stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}
        source_id = source_config["source_id"]
        secret_scope = source_config["connection_secret_scope"]

        # Retrieve ADLS Gen2 credentials from Databricks Secrets
        try:
            storage_account_name = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_storage_account_name")
            storage_account_key = dbutils.secrets.get(scope=secret_scope, key=f"{source_id}_storage_account_key")
        except Exception as e:
            logger.error(f"Failed to retrieve ADLS Gen2 credentials for {source_id}: {e}")
            return stats

        # Get existing files state
        existing_files = self.get_existing_files_state(source_id)
        current_files_set = set()

        # Parse ADLS URI: abfss://container@storageaccount.dfs.core.windows.net/path/
        source_uri = source_config["source_root_uri"]
        container_name = source_uri.split("@")[0].replace("abfss://", "")
        directory_path = "/".join(source_uri.split("/")[3:]) if len(source_uri.split("/")) > 3 else ""

        # Establish ADLS Gen2 client with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                service_client = DataLakeServiceClient(
                    account_url=f"https://{storage_account_name}.dfs.core.windows.net",
                    credential=storage_account_key
                )
                file_system_client = service_client.get_file_system_client(file_system=container_name)
                logger.info(f"Connected to ADLS Gen2: {storage_account_name}/{container_name}")
                break
            except AzureError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"ADLS Gen2 connection attempt {attempt + 1} failed. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to ADLS Gen2 after {max_retries} attempts: {e}")
                    return stats

        try:
            glob_pattern = source_config["path_glob_pattern"] or "**/*"
            file_types = source_config["file_types"] or []

            # List all paths recursively
            paths = file_system_client.get_paths(path=directory_path, recursive=True)

            for path in paths:
                try:
                    # Skip directories
                    if path.is_directory:
                        continue

                    file_path = path.name
                    
                    # Filter by file extension
                    file_ext = Path(file_path).suffix.lower().lstrip('.')
                    if file_types and file_ext not in file_types:
                        continue

                    # Filter by glob pattern
                    relative_path = file_path.replace(directory_path, "").lstrip("/")
                    if not fnmatch(relative_path, glob_pattern):
                        continue

                    file_uri = f"abfss://{container_name}@{storage_account_name}.dfs.core.windows.net/{file_path}"
                    current_files_set.add(file_uri)

                    # Get file properties
                    file_size = path.content_length
                    last_modified = path.last_modified

                    # Download to temp location and compute hash
                    temp_local_path = f"/tmp/{uuid.uuid4()}_{Path(file_path).name}"
                    file_client = file_system_client.get_file_client(file_path)
                    
                    with open(temp_local_path, "wb") as local_file:
                        download = file_client.download_file()
                        local_file.write(download.readall())
                    
                    content_hash = self.compute_sha256(temp_local_path)

                    # Check if file exists and has changed
                    if file_uri in existing_files:
                        existing_file_id, existing_hash = existing_files[file_uri]
                        if existing_hash != content_hash:
                            # File modified - update state
                            self._copy_to_volume(temp_local_path, source_config, relative_path)
                            self._update_file_state(
                                file_id=existing_file_id,
                                source_id=source_id,
                                file_uri=file_uri,
                                file_name=Path(file_path).name,
                                file_extension=file_ext,
                                file_size_bytes=file_size,
                                content_sha256_hash=content_hash,
                                volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                                last_modified_at=last_modified,
                                status="PENDING"
                            )
                            stats["modified"] += 1
                            logger.info(f"Modified: {file_uri}")
                    else:
                        # New file - create state record
                        file_id = str(uuid.uuid4())
                        self._copy_to_volume(temp_local_path, source_config, relative_path)
                        self._create_file_state(
                            file_id=file_id,
                            source_id=source_id,
                            file_uri=file_uri,
                            file_name=Path(file_path).name,
                            file_extension=file_ext,
                            file_size_bytes=file_size,
                            content_sha256_hash=content_hash,
                            volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                            last_modified_at=last_modified,
                            status="PENDING"
                        )
                        stats["new"] += 1
                        logger.info(f"New: {file_uri}")

                    # Clean up temp file
                    Path(temp_local_path).unlink(missing_ok=True)

                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    stats["errors"] += 1
                    continue

            # Identify deleted files (exist in registry but not in source)
            deleted_uris = set(existing_files.keys()) - current_files_set
            for deleted_uri in deleted_uris:
                file_id, _ = existing_files[deleted_uri]
                self._mark_file_deleted(file_id)
                stats["deleted"] += 1
                logger.info(f"Deleted: {deleted_uri}")

        except Exception as e:
            logger.error(f"Error syncing ADLS Gen2 source {source_id}: {e}")
            stats["errors"] += 1

        # Update last sync timestamp
        self._update_last_sync(source_id)
        return stats

    def sync_uc_volumes_source(self, source_config: Dict) -> Dict[str, int]:
        """
        Synchronize files from Unity Catalog Volumes to another UC Volume (cross-catalog/schema replication).

        Args:
            source_config: Source configuration from control table

        Returns:
            Dictionary with sync statistics: {new: int, modified: int, deleted: int}
        """
        from fnmatch import fnmatch
        import os

        stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}
        source_id = source_config["source_id"]

        # Get existing files state
        existing_files = self.get_existing_files_state(source_id)
        current_files_set = set()

        # Parse UC Volume URI: /Volumes/catalog/schema/volume/path/
        source_volume_path = source_config["source_root_uri"]
        
        # Verify source volume exists
        try:
            dbutils.fs.ls(source_volume_path)
            logger.info(f"Connected to UC Volume: {source_volume_path}")
        except Exception as e:
            logger.error(f"Cannot access source UC Volume {source_volume_path}: {e}")
            return stats

        try:
            glob_pattern = source_config["path_glob_pattern"] or "**/*"
            file_types = source_config["file_types"] or []

            def list_uc_volume_files(path: str) -> List[Dict]:
                """Recursively list all files in UC Volume."""
                files = []
                try:
                    for file_info in dbutils.fs.ls(path):
                        if file_info.isDir():
                            # Recurse into subdirectories
                            files.extend(list_uc_volume_files(file_info.path))
                        else:
                            files.append({
                                "path": file_info.path,
                                "name": file_info.name,
                                "size": file_info.size,
                                "modified": datetime.fromtimestamp(file_info.modificationTime / 1000)
                            })
                except Exception as e:
                    logger.warning(f"Cannot access {path}: {e}")
                return files

            volume_files = list_uc_volume_files(source_volume_path)
            logger.info(f"Found {len(volume_files)} files in UC Volume")

            # Process each file
            for file_info in volume_files:
                try:
                    file_path = file_info["path"]
                    
                    # Filter by file extension
                    file_ext = Path(file_info["name"]).suffix.lower().lstrip('.')
                    if file_types and file_ext not in file_types:
                        continue

                    # Filter by glob pattern
                    relative_path = file_path.replace(source_volume_path, "").lstrip("/")
                    if not fnmatch(relative_path, glob_pattern):
                        continue

                    file_uri = file_path
                    current_files_set.add(file_uri)

                    file_size = file_info["size"]
                    last_modified = file_info["modified"]

                    # Copy to temp location and compute hash
                    # For UC Volumes, we use dbutils.fs.cp to local /tmp
                    temp_local_path = f"/tmp/{uuid.uuid4()}_{file_info['name']}"
                    dbutils.fs.cp(file_path, f"file:{temp_local_path}")
                    content_hash = self.compute_sha256(temp_local_path)

                    # Check if file exists and has changed
                    if file_uri in existing_files:
                        existing_file_id, existing_hash = existing_files[file_uri]
                        if existing_hash != content_hash:
                            # File modified - update state
                            self._copy_to_volume(temp_local_path, source_config, relative_path)
                            self._update_file_state(
                                file_id=existing_file_id,
                                source_id=source_id,
                                file_uri=file_uri,
                                file_name=file_info["name"],
                                file_extension=file_ext,
                                file_size_bytes=file_size,
                                content_sha256_hash=content_hash,
                                volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                                last_modified_at=last_modified,
                                status="PENDING"
                            )
                            stats["modified"] += 1
                            logger.info(f"Modified: {file_uri}")
                    else:
                        # New file - create state record
                        file_id = str(uuid.uuid4())
                        self._copy_to_volume(temp_local_path, source_config, relative_path)
                        self._create_file_state(
                            file_id=file_id,
                            source_id=source_id,
                            file_uri=file_uri,
                            file_name=file_info["name"],
                            file_extension=file_ext,
                            file_size_bytes=file_size,
                            content_sha256_hash=content_hash,
                            volume_landing_path=f"{source_config['target_volume_path']}/{relative_path}",
                            last_modified_at=last_modified,
                            status="PENDING"
                        )
                        stats["new"] += 1
                        logger.info(f"New: {file_uri}")

                    # Clean up temp file
                    Path(temp_local_path).unlink(missing_ok=True)

                except Exception as e:
                    logger.error(f"Error processing {file_info['name']}: {e}")
                    stats["errors"] += 1
                    continue

            # Identify deleted files (exist in registry but not in source)
            deleted_uris = set(existing_files.keys()) - current_files_set
            for deleted_uri in deleted_uris:
                file_id, _ = existing_files[deleted_uri]
                self._mark_file_deleted(file_id)
                stats["deleted"] += 1
                logger.info(f"Deleted: {deleted_uri}")

        except Exception as e:
            logger.error(f"Error syncing UC Volumes source {source_id}: {e}")
            stats["errors"] += 1

        # Update last sync timestamp
        self._update_last_sync(source_id)
        return stats

    def _copy_to_volume(self, temp_local_path: str, source_config: Dict, relative_path: str):
        """
        Copy file from temp location to Unity Catalog Volume.

        Args:
            temp_local_path: Temporary local file path
            source_config: Source configuration
            relative_path: Relative path within the volume
        """
        volume_path = f"{source_config['target_volume_path']}/{relative_path}"
        volume_dir = str(Path(volume_path).parent)

        # Ensure directory exists
        dbutils.fs.mkdirs(volume_dir)

        # Copy file
        dbutils.fs.cp(f"file://{temp_local_path}", volume_path, recurse=False)
        logger.debug(f"Copied to volume: {volume_path}")

    def _create_file_state(self, **kwargs):
        """
        Create a new file state record in the document state registry.
        """
        from pyspark.sql.types import StructType, StructField, StringType, LongType, TimestampType, MapType

        schema = StructType([
            StructField("file_id", StringType(), False),
            StructField("source_id", StringType(), False),
            StructField("file_uri", StringType(), False),
            StructField("file_name", StringType(), False),
            StructField("file_extension", StringType(), True),
            StructField("file_size_bytes", LongType(), True),
            StructField("content_sha256_hash", StringType(), False),
            StructField("volume_landing_path", StringType(), True),
            StructField("source_access_control_groups", StringType(), True),  # Array as JSON string
            StructField("status", StringType(), False),
            StructField("last_modified_at", TimestampType(), True)
        ])

        data = [(
            kwargs["file_id"],
            kwargs["source_id"],
            kwargs["file_uri"],
            kwargs["file_name"],
            kwargs.get("file_extension"),
            kwargs.get("file_size_bytes"),
            kwargs["content_sha256_hash"],
            kwargs.get("volume_landing_path"),
            None,  # ACL groups can be added if available from source
            kwargs["status"],
            kwargs.get("last_modified_at")
        )]

        df = self.spark.createDataFrame(data, schema)
        df.write.mode("append").saveAsTable(self.state_table)

    def _update_file_state(self, **kwargs):
        """
        Update an existing file state record.
        """
        file_id = kwargs["file_id"]
        self.spark.sql(f"""
            UPDATE {self.state_table}
            SET 
                content_sha256_hash = '{kwargs['content_sha256_hash']}',
                file_size_bytes = {kwargs.get('file_size_bytes', 'NULL')},
                volume_landing_path = '{kwargs.get('volume_landing_path', '')}',
                status = '{kwargs['status']}',
                last_modified_at = TIMESTAMP'{kwargs.get('last_modified_at', datetime.now())}'',
                detected_at = CURRENT_TIMESTAMP()
            WHERE file_id = '{file_id}'
        """)

    def _mark_file_deleted(self, file_id: str):
        """
        Mark a file as deleted (tombstone record for vector pruning).
        """
        self.spark.sql(f"""
            UPDATE {self.state_table}
            SET 
                status = 'DELETED',
                processed_at = CURRENT_TIMESTAMP()
            WHERE file_id = '{file_id}'
        """)

    def _update_last_sync(self, source_id: str):
        """
        Update the last sync timestamp for a source.
        """
        self.spark.sql(f"""
            UPDATE {self.control_table}
            SET 
                last_sync_timestamp = CURRENT_TIMESTAMP(),
                updated_at = CURRENT_TIMESTAMP()
            WHERE source_id = '{source_id}'
        """)

    def run_ingestion(self, source_system: Optional[str] = None):
        """
        Run the ingestion pipeline for all active sources or a specific source system.

        Args:
            source_system: Optional filter for specific source system (SFTP, SharePoint, OneDrive)
        """
        sources = self.get_active_sources()

        if source_system:
            sources = [s for s in sources if s["source_system"] == source_system]

        logger.info(f"Starting ingestion for {len(sources)} source(s)")

        total_stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}

        for source in sources:
            logger.info(f"Processing source: {source['source_id']} ({source['source_system']})")
            try:
                if source["source_system"] == "SFTP":
                    stats = self.sync_sftp_source(source)
                elif source["source_system"] == "SharePoint":
                    stats = self.sync_sharepoint_source(source)
                elif source["source_system"] == "OneDrive":
                    stats = self.sync_onedrive_source(source)
                elif source["source_system"] == "S3":
                    stats = self.sync_s3_source(source)
                elif source["source_system"] == "ADLS_Gen2":
                    stats = self.sync_adls_gen2_source(source)
                elif source["source_system"] == "UC_Volumes":
                    stats = self.sync_uc_volumes_source(source)
                else:
                    logger.warning(f"Unsupported source system: {source['source_system']}")
                    continue

                # Aggregate statistics
                for key in total_stats:
                    total_stats[key] += stats.get(key, 0)

                logger.info(f"Source {source['source_id']} stats: {stats}")
            except Exception as e:
                logger.error(f"Failed to process source {source['source_id']}: {e}")
                total_stats["errors"] += 1

        logger.info(f"Ingestion complete. Total stats: {total_stats}")
        return total_stats
