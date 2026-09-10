"""
Multi-Modal RAG Pipeline: Vector Search Manager
===============================================
Automated provisioning and management of Databricks Vector Search Delta Sync Indexes.

Key Features:
- Managed Embeddings: Automatic embedding generation using Databricks Foundation Models
- Delta Sync Index: Real-time or triggered sync from source Delta tables with CDF
- Deletion Handling: Automatic vector pruning based on tombstone records
- Index Lifecycle: Create, update, sync, and monitor vector search indexes
- Query Interface: Semantic search with metadata filtering

Author: Principal Databricks Architect
Date: 2026-09-04
"""

import time
import logging
from typing import List, Dict, Optional
from datetime import datetime

from databricks.vector_search.client import VectorSearchClient
from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VectorSearchManager:
    """
    Manages Databricks Vector Search endpoints and Delta Sync indexes.
    Implements automated provisioning with managed embeddings.
    """

    def __init__(self, spark: SparkSession, endpoint_name: str = "rag_vector_search_endpoint"):
        """
        Initialize the vector search manager.

        Args:
            spark: Active SparkSession
            endpoint_name: Name of the vector search endpoint
        """
        self.spark = spark
        self.endpoint_name = endpoint_name
        self.vsc = VectorSearchClient()
        self.control_table = "ai_unstructured_metadata.ingestion_control"

    def create_endpoint(self, endpoint_type: str = "STANDARD") -> Dict:
        """
        Create a vector search endpoint if it doesn't exist.

        Args:
            endpoint_type: Type of endpoint (STANDARD or STANDARD_HIGH_PERFORMANCE)

        Returns:
            Endpoint details dictionary
        """
        try:
            # Check if endpoint exists
            existing_endpoints = self.vsc.list_endpoints()
            for endpoint in existing_endpoints.get("endpoints", []):
                if endpoint["name"] == self.endpoint_name:
                    logger.info(f"Endpoint '{self.endpoint_name}' already exists")
                    return endpoint

            # Create new endpoint
            logger.info(f"Creating vector search endpoint: {self.endpoint_name}")
            endpoint = self.vsc.create_endpoint(
                name=self.endpoint_name,
                endpoint_type=endpoint_type
            )

            # Wait for endpoint to be ready
            self._wait_for_endpoint_ready()
            logger.info(f"Endpoint '{self.endpoint_name}' created successfully")
            return endpoint

        except Exception as e:
            logger.error(f"Failed to create endpoint: {e}")
            raise

    def _wait_for_endpoint_ready(self, timeout_seconds: int = 600):
        """
        Wait for endpoint to be in ONLINE state.

        Args:
            timeout_seconds: Maximum time to wait
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                endpoint_info = self.vsc.get_endpoint(self.endpoint_name)
                status = endpoint_info.get("endpoint_status", {}).get("state")
                
                if status == "ONLINE":
                    logger.info(f"Endpoint '{self.endpoint_name}' is online")
                    return
                elif status in ["PROVISIONING", "STARTING"]:
                    logger.info(f"Endpoint status: {status}. Waiting...")
                    time.sleep(30)
                else:
                    raise RuntimeError(f"Endpoint in unexpected state: {status}")
            except Exception as e:
                logger.warning(f"Error checking endpoint status: {e}")
                time.sleep(30)
        
        raise TimeoutError(f"Endpoint did not become ready within {timeout_seconds} seconds")

    def create_index_for_source(self, source_id: str, 
                                embedding_model: str = "databricks-bge-large-en",
                                pipeline_type: str = "TRIGGERED") -> Dict:
        """
        Create a Delta Sync index for a specific ingestion source.

        Args:
            source_id: Source identifier from control table
            embedding_model: Databricks managed embedding model endpoint
            pipeline_type: TRIGGERED (manual sync) or CONTINUOUS (auto sync)

        Returns:
            Index creation response dictionary
        """
        # Get source configuration
        source_config = self._get_source_config(source_id)
        if not source_config:
            raise ValueError(f"Source '{source_id}' not found in control table")

        target_table = source_config["target_delta_table"]
        index_name = f"{target_table}_vs_index"

        # Ensure endpoint exists
        self.create_endpoint()

        try:
            # Check if index already exists
            try:
                existing_index = self.vsc.get_index(index_name=index_name)
                if existing_index:
                    logger.info(f"Index '{index_name}' already exists")
                    return existing_index
            except Exception:
                # Index doesn't exist, proceed with creation
                pass

            # Enable Change Data Feed on target table if not already enabled
            self._ensure_cdf_enabled(target_table)

            logger.info(f"Creating Delta Sync index: {index_name}")
            logger.info(f"  Source table: {target_table}")
            logger.info(f"  Embedding model: {embedding_model}")
            logger.info(f"  Pipeline type: {pipeline_type}")

            # Create Delta Sync Index with Managed Embeddings
            index_response = self.vsc.create_delta_sync_index(
                endpoint_name=self.endpoint_name,
                index_name=index_name,
                source_table_name=target_table,
                pipeline_type=pipeline_type,
                primary_key="chunk_id",
                embedding_source_column="chunk_text",
                embedding_model_endpoint_name=embedding_model,
            )

            # Wait for index to be ready
            self._wait_for_index_ready(index_name)
            logger.info(f"Index '{index_name}' created successfully")

            # Update control table with index name
            self._update_index_info(source_id, index_name)

            return index_response

        except Exception as e:
            logger.error(f"Failed to create index for source '{source_id}': {e}")
            raise

    def create_all_indexes(self, embedding_model: str = "databricks-bge-large-en",
                          pipeline_type: str = "TRIGGERED") -> Dict[str, str]:
        """
        Create Delta Sync indexes for all active sources.

        Args:
            embedding_model: Databricks managed embedding model endpoint
            pipeline_type: TRIGGERED or CONTINUOUS

        Returns:
            Dictionary mapping source_id to index_name
        """
        sources = self._get_active_sources()
        index_map = {}

        logger.info(f"Creating indexes for {len(sources)} active source(s)")

        for source in sources:
            source_id = source["source_id"]
            try:
                index_response = self.create_index_for_source(
                    source_id=source_id,
                    embedding_model=embedding_model,
                    pipeline_type=pipeline_type
                )
                index_name = f"{source['target_delta_table']}_vs_index"
                index_map[source_id] = index_name
                logger.info(f"✓ Created index for source '{source_id}'")
            except Exception as e:
                logger.error(f"✗ Failed to create index for source '{source_id}': {e}")
                continue

        return index_map

    def sync_index(self, index_name: str):
        """
        Trigger a sync for a Delta Sync index (for TRIGGERED pipeline type).

        Args:
            index_name: Fully qualified index name
        """
        try:
            logger.info(f"Triggering sync for index: {index_name}")
            self.vsc.get_index(index_name).sync()
            logger.info(f"Sync triggered successfully for {index_name}")
        except Exception as e:
            logger.error(f"Failed to sync index '{index_name}': {e}")
            raise

    def sync_all_indexes(self):
        """
        Trigger sync for all Delta Sync indexes.
        """
        sources = self._get_active_sources()
        
        for source in sources:
            index_name = f"{source['target_delta_table']}_vs_index"
            try:
                self.sync_index(index_name)
            except Exception as e:
                logger.warning(f"Could not sync index for {source['source_id']}: {e}")
                continue

    def query_index(self, index_name: str, query_text: str, 
                   num_results: int = 10, 
                   filters: Optional[Dict] = None) -> List[Dict]:
        """
        Query a vector search index with semantic search.

        Args:
            index_name: Fully qualified index name
            query_text: Query string
            num_results: Number of results to return
            filters: Optional metadata filters (e.g., {"source_id": "sftp_financial_reports"})

        Returns:
            List of search result dictionaries
        """
        try:
            logger.info(f"Querying index: {index_name}")
            logger.info(f"  Query: {query_text}")
            logger.info(f"  Num results: {num_results}")
            logger.info(f"  Filters: {filters}")

            index = self.vsc.get_index(index_name=index_name)
            
            # Perform similarity search
            results = index.similarity_search(
                query_text=query_text,
                columns=["chunk_id", "chunk_text", "file_name", "file_uri", 
                        "page_number", "element_type", "source_id"],
                num_results=num_results,
                filters=filters
            )

            return results.get("result", {}).get("data_array", [])

        except Exception as e:
            logger.error(f"Failed to query index '{index_name}': {e}")
            raise

    def get_index_status(self, index_name: str) -> Dict:
        """
        Get the status of a vector search index.

        Args:
            index_name: Fully qualified index name

        Returns:
            Index status dictionary
        """
        try:
            index_info = self.vsc.get_index(index_name=index_name)
            return {
                "name": index_info.get("name"),
                "status": index_info.get("status", {}).get("state"),
                "detailed_state": index_info.get("status", {}).get("detailed_state"),
                "index_type": index_info.get("index_type"),
                "delta_sync_status": index_info.get("delta_sync_index_spec", {}).get("pipeline_type"),
                "embedding_model": index_info.get("delta_sync_index_spec", {}).get("embedding_model_endpoint_name"),
                "source_table": index_info.get("delta_sync_index_spec", {}).get("source_table")
            }
        except Exception as e:
            logger.error(f"Failed to get status for index '{index_name}': {e}")
            raise

    def delete_index(self, index_name: str):
        """
        Delete a vector search index.

        Args:
            index_name: Fully qualified index name
        """
        try:
            logger.warning(f"Deleting index: {index_name}")
            self.vsc.delete_index(index_name=index_name)
            logger.info(f"Index '{index_name}' deleted successfully")
        except Exception as e:
            logger.error(f"Failed to delete index '{index_name}': {e}")
            raise

    def _wait_for_index_ready(self, index_name: str, timeout_seconds: int = 1800):
        """
        Wait for index to be in ONLINE state.

        Args:
            index_name: Index name
            timeout_seconds: Maximum time to wait (default: 30 minutes)
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                index_info = self.vsc.get_index(index_name)
                status = index_info.get("status", {}).get("state")
                detailed_state = index_info.get("status", {}).get("detailed_state")
                
                if status == "ONLINE":
                    logger.info(f"Index '{index_name}' is online")
                    return
                elif status in ["PROVISIONING", "SYNCING"]:
                    logger.info(f"Index status: {status} ({detailed_state}). Waiting...")
                    time.sleep(60)
                elif status == "OFFLINE":
                    logger.warning(f"Index is offline: {detailed_state}")
                    time.sleep(60)
                else:
                    raise RuntimeError(f"Index in unexpected state: {status}")
            except Exception as e:
                logger.warning(f"Error checking index status: {e}")
                time.sleep(60)
        
        raise TimeoutError(f"Index did not become ready within {timeout_seconds} seconds")

    def _ensure_cdf_enabled(self, table_name: str):
        """
        Ensure Change Data Feed is enabled on a Delta table.

        Args:
            table_name: Fully qualified table name
        """
        try:
            # Check if CDF is already enabled
            table_props = self.spark.sql(f"SHOW TBLPROPERTIES {table_name}").collect()
            cdf_enabled = any(
                row.key == "delta.enableChangeDataFeed" and row.value == "true"
                for row in table_props
            )

            if not cdf_enabled:
                logger.info(f"Enabling Change Data Feed on table: {table_name}")
                self.spark.sql(f"""
                    ALTER TABLE {table_name}
                    SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
                """)
                logger.info(f"Change Data Feed enabled on {table_name}")
            else:
                logger.info(f"Change Data Feed already enabled on {table_name}")

        except Exception as e:
            logger.error(f"Failed to enable CDF on table '{table_name}': {e}")
            raise

    def _get_source_config(self, source_id: str) -> Optional[Dict]:
        """
        Retrieve source configuration from control table.

        Args:
            source_id: Source identifier

        Returns:
            Source configuration dictionary or None
        """
        result = self.spark.sql(f"""
            SELECT 
                source_id,
                target_delta_table,
                parsing_engine
            FROM {self.control_table}
            WHERE source_id = '{source_id}'
        """).first()

        if result:
            return result.asDict()
        return None

    def _get_active_sources(self) -> List[Dict]:
        """
        Retrieve all active sources from control table.

        Returns:
            List of source configuration dictionaries
        """
        df = self.spark.sql(f"""
            SELECT 
                source_id,
                target_delta_table
            FROM {self.control_table}
            WHERE is_active = TRUE
        """)
        return [row.asDict() for row in df.collect()]

    def _update_index_info(self, source_id: str, index_name: str):
        """
        Update control table with index information.

        Args:
            source_id: Source identifier
            index_name: Created index name
        """
        # Note: This assumes an 'index_name' column exists in the control table
        # If not, you can skip this or add the column via ALTER TABLE
        try:
            self.spark.sql(f"""
                UPDATE {self.control_table}
                SET updated_at = CURRENT_TIMESTAMP()
                WHERE source_id = '{source_id}'
            """)
        except Exception as e:
            logger.warning(f"Could not update index info for source '{source_id}': {e}")

    def get_all_indexes_status(self) -> List[Dict]:
        """
        Get status of all vector search indexes.

        Returns:
            List of index status dictionaries
        """
        sources = self._get_active_sources()
        statuses = []

        for source in sources:
            index_name = f"{source['target_delta_table']}_vs_index"
            try:
                status = self.get_index_status(index_name)
                status["source_id"] = source["source_id"]
                statuses.append(status)
            except Exception as e:
                logger.warning(f"Could not get status for index '{index_name}': {e}")
                statuses.append({
                    "source_id": source["source_id"],
                    "name": index_name,
                    "status": "ERROR",
                    "error": str(e)
                })

        return statuses
