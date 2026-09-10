# Multi-Modal RAG Pipeline Configuration Guide

**Author**: Principal Databricks Architect  
**Date**: 2026-09-04  
**Version**: 1.0

---

## Table of Contents

1. [Secret Management Configuration](#1-secret-management-configuration)
2. [Cluster Sizing Recommendations](#2-cluster-sizing-recommendations)
3. [Unity Catalog Volumes Setup](#3-unity-catalog-volumes-setup)
4. [Complete Table Setup & Sample Data](#4-complete-table-setup--sample-data)
5. [Python Dependencies](#5-python-dependencies)
6. [Operational Guidelines](#6-operational-guidelines)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Secret Management Configuration

### 1.1 Create Secret Scope

Create a Databricks secret scope to store external system credentials:

```bash
databricks secrets create-scope --scope rag_pipeline_secrets
```

### 1.2 SFTP Credentials

For each SFTP source, store the following secrets:

```bash
# Replace <source_id> with your actual source_id from ingestion_control table
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_host
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_port
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_username
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_password
```

**Example** (for source_id: `sftp_financial_reports`):
```bash
databricks secrets put --scope rag_pipeline_secrets --key sftp_financial_reports_host
# Enter value: finance.company.com

databricks secrets put --scope rag_pipeline_secrets --key sftp_financial_reports_port
# Enter value: 22

databricks secrets put --scope rag_pipeline_secrets --key sftp_financial_reports_username
# Enter value: sftp_user

databricks secrets put --scope rag_pipeline_secrets --key sftp_financial_reports_password
# Enter value: <secure_password>
```

### 1.3 SharePoint Credentials

For SharePoint sources (OAuth App Registration):

```bash
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_site_url
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_client_id
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_client_secret
```

**Example** (for source_id: `sharepoint_hr_docs`):
```bash
databricks secrets put --scope rag_pipeline_secrets --key sharepoint_hr_docs_site_url
# Enter value: https://company.sharepoint.com/sites/HR

databricks secrets put --scope rag_pipeline_secrets --key sharepoint_hr_docs_client_id
# Enter value: <azure_app_client_id>

databricks secrets put --scope rag_pipeline_secrets --key sharepoint_hr_docs_client_secret
# Enter value: <azure_app_client_secret>
```

**SharePoint OAuth Setup**:
1. Register an Azure AD App in Azure Portal
2. Grant API Permissions: `Sites.Read.All`, `Files.Read.All`
3. Create a client secret
4. Use the Application (client) ID and client secret above

### 1.4 OneDrive Credentials

For OneDrive sources (Microsoft Graph API):

```bash
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_tenant_id
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_client_id
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_client_secret
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_user_email
```

**Example** (for source_id: `onedrive_engineering`):
```bash
databricks secrets put --scope rag_pipeline_secrets --key onedrive_engineering_tenant_id
# Enter value: <azure_tenant_id>

databricks secrets put --scope rag_pipeline_secrets --key onedrive_engineering_client_id
# Enter value: <azure_app_client_id>

databricks secrets put --scope rag_pipeline_secrets --key onedrive_engineering_client_secret
# Enter value: <azure_app_client_secret>

databricks secrets put --scope rag_pipeline_secrets --key onedrive_engineering_user_email
# Enter value: engineering@company.com
```

**OneDrive OAuth Setup**:
1. Same Azure AD App registration as SharePoint
2. Additional API Permissions: `Files.Read.All`, `User.Read.All`
3. Use delegated permissions for user-specific OneDrive access

### 1.5 AWS S3 Credentials

For AWS S3 bucket sources:

```bash
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_access_key_id
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_secret_access_key
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_region
```

**Example** (for source_id: `s3_legal_documents`):
```bash
databricks secrets put --scope rag_pipeline_secrets --key s3_legal_documents_access_key_id
# Enter value: AKIAIOSFODNN7EXAMPLE

databricks secrets put --scope rag_pipeline_secrets --key s3_legal_documents_secret_access_key
# Enter value: <aws_secret_access_key>

databricks secrets put --scope rag_pipeline_secrets --key s3_legal_documents_region
# Enter value: us-east-1
```

**AWS IAM Setup**:
1. Create IAM User or use IAM Role with programmatic access
2. Attach policy with S3 read permissions:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:GetObject",
           "s3:ListBucket"
         ],
         "Resource": [
           "arn:aws:s3:::your-bucket-name",
           "arn:aws:s3:::your-bucket-name/*"
         ]
       }
     ]
   }
   ```
3. Generate access key credentials from IAM console

**Note**: For enhanced security, use IAM roles with instance profiles instead of static credentials when running on AWS.

### 1.6 Azure Data Lake Storage Gen2 Credentials

For ADLS Gen2 sources:

```bash
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_storage_account_name
databricks secrets put --scope rag_pipeline_secrets --key <source_id>_storage_account_key
```

**Example** (for source_id: `adls_research_data`):
```bash
databricks secrets put --scope rag_pipeline_secrets --key adls_research_data_storage_account_name
# Enter value: companystorageaccount

databricks secrets put --scope rag_pipeline_secrets --key adls_research_data_storage_account_key
# Enter value: <storage_account_access_key>
```

**ADLS Gen2 Setup**:
1. Navigate to Azure Portal → Storage Accounts
2. Select your storage account
3. Go to **Access Keys** under Security + Networking
4. Copy **Storage account name** and **Key1** or **Key2**
5. Ensure the storage account has **Hierarchical namespace** enabled (ADLS Gen2 requirement)

**Alternative Authentication Methods**:
* **Service Principal (OAuth)**: Use Azure AD App registration with `Storage Blob Data Reader` role
* **Managed Identity**: For Databricks running on Azure, use workspace managed identity

### 1.7 Unity Catalog Volumes (No Credentials Required)

For UC Volumes as sources, no separate credentials are needed. Access is governed by Unity Catalog permissions.

**Prerequisites**:
1. Source UC Volume must exist: `/Volumes/catalog/schema/volume`
2. User/Service Principal must have `READ VOLUME` permission on the source
3. User/Service Principal must have `WRITE VOLUME` permission on the target

**Permission Check**:
```sql
-- Grant read access on source volume
GRANT READ VOLUME ON VOLUME source_catalog.source_schema.source_volume TO `user@company.com`;

-- Grant write access on target volume
GRANT WRITE VOLUME ON VOLUME main.rag_data.raw_documents_uc TO `user@company.com`;
```

---

## 2. Cluster Sizing Recommendations

### 2.1 Development/Testing Cluster

**Purpose**: Initial testing, small-scale ingestion (<1000 documents)

```yaml
Cluster Configuration:
  Type: Standard (Serverless not recommended for file I/O)
  Runtime: 14.3 LTS ML or later
  Node Type:
    Driver: Standard_DS3_v2 (14GB Memory, 4 Cores)
    Workers: Standard_DS3_v2
  Workers: 2-4 (Autoscaling)
  
Estimated Cost: ~$1-2/hour
Ingestion Throughput: ~50-100 documents/hour
```

### 2.2 Production Cluster

**Purpose**: Large-scale production ingestion (>10,000 documents)

```yaml
Cluster Configuration:
  Type: Standard
  Runtime: 14.3 LTS ML or later
  Node Type:
    Driver: Standard_DS4_v2 (28GB Memory, 8 Cores)
    Workers: Standard_DS4_v2 or Standard_E8s_v3 (memory-optimized)
  Workers: 8-16 (Autoscaling)
  
Optimizations:
  - Enable Photon: Yes
  - Delta Cache: Enabled
  - Auto-Termination: 30 minutes
  
Estimated Cost: ~$8-12/hour
Ingestion Throughput: ~500-1000 documents/hour
```

### 2.3 High-Performance Parsing Cluster

**Purpose**: Heavy document parsing (large PDFs, complex tables, OCR)

```yaml
Cluster Configuration:
  Type: Standard
  Runtime: 14.3 LTS ML or later
  Node Type:
    Driver: Standard_E8s_v3 (64GB Memory, 8 Cores)
    Workers: Standard_E8s_v3 (Memory-Optimized)
  Workers: 16-32 (Autoscaling)
  
Special Configuration:
  - spark.executor.memory: 48g
  - spark.executor.cores: 4
  - spark.sql.shuffle.partitions: 200
  
Estimated Cost: ~$15-25/hour
Parsing Throughput: ~2000-3000 documents/hour
```

### 2.4 Cluster Policies (Enterprise Governance)

**Recommended Cluster Policy** for Production:

```json
{
  "spark_version": {
    "type": "fixed",
    "value": "14.3.x-scala2.12"
  },
  "node_type_id": {
    "type": "allowlist",
    "values": ["Standard_DS4_v2", "Standard_E8s_v3"]
  },
  "autoscale": {
    "type": "fixed",
    "value": {
      "min_workers": 8,
      "max_workers": 32
    }
  },
  "runtime_engine": {
    "type": "fixed",
    "value": "PHOTON"
  },
  "autotermination_minutes": {
    "type": "range",
    "minValue": 10,
    "maxValue": 120,
    "defaultValue": 30
  }
}
```

---

## 3. Unity Catalog Volumes Setup

### 3.1 Create Volumes for Landing Files

```sql
-- Create catalog if not exists
CREATE CATALOG IF NOT EXISTS main;

-- Create schema for RAG data
CREATE SCHEMA IF NOT EXISTS main.rag_data
COMMENT 'RAG pipeline data storage';

-- Create volumes for each source type
CREATE VOLUME IF NOT EXISTS main.rag_data.raw_documents_financial
COMMENT 'Landing zone for financial reports from SFTP';

CREATE VOLUME IF NOT EXISTS main.rag_data.raw_documents_hr
COMMENT 'Landing zone for HR documents from SharePoint';

CREATE VOLUME IF NOT EXISTS main.rag_data.raw_documents_engineering
COMMENT 'Landing zone for engineering docs from OneDrive';
```

### 3.2 Volume Paths in Control Table

When populating the `ingestion_control` table, use these volume paths and source URI patterns:

**SFTP Sources**:
```sql
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id, source_system, connection_secret_scope, source_root_uri,
  target_volume_path, is_active
) VALUES (
  'sftp_financial_reports',
  'SFTP',
  'rag_pipeline_secrets',
  'sftp://finance.company.com/reports/',
  '/Volumes/main/rag_data/raw_documents_financial',
  TRUE
);
```

**SharePoint Sources**:
```sql
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id, source_system, connection_secret_scope, source_root_uri,
  target_volume_path, is_active
) VALUES (
  'sharepoint_hr_docs',
  'SharePoint',
  'rag_pipeline_secrets',
  'https://company.sharepoint.com/sites/HR/Shared Documents',
  '/Volumes/main/rag_data/raw_documents_hr',
  TRUE
);
```

**OneDrive Sources**:
```sql
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id, source_system, connection_secret_scope, source_root_uri,
  target_volume_path, is_active
) VALUES (
  'onedrive_engineering',
  'OneDrive',
  'rag_pipeline_secrets',
  '/drive/root:/Engineering/Documentation',
  '/Volumes/main/rag_data/raw_documents_engineering',
  TRUE
);
```

**AWS S3 Sources**:
```sql
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id, source_system, connection_secret_scope, source_root_uri,
  target_volume_path, file_types, is_active
) VALUES (
  's3_legal_documents',
  'S3',
  'rag_pipeline_secrets',
  's3://company-legal-bucket/contracts/',
  '/Volumes/main/rag_data/raw_documents_legal',
  ARRAY('pdf', 'docx'),
  TRUE
);
```

**ADLS Gen2 Sources**:
```sql
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id, source_system, connection_secret_scope, source_root_uri,
  target_volume_path, path_glob_pattern, is_active
) VALUES (
  'adls_research_data',
  'ADLS_Gen2',
  'rag_pipeline_secrets',
  'abfss://research@companystorage.dfs.core.windows.net/papers/',
  '/Volumes/main/rag_data/raw_documents_research',
  '**/*.pdf',
  TRUE
);
```

**Unity Catalog Volumes Sources**:
```sql
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id, source_system, connection_secret_scope, source_root_uri,
  target_volume_path, is_active
) VALUES (
  'uc_archive_documents',
  'UC_Volumes',
  NULL,  -- No secret scope needed for UC Volumes
  '/Volumes/archive/historical/documents/',
  '/Volumes/main/rag_data/raw_documents_archive',
  TRUE
);
```

---

## 4. Complete Table Setup & Sample Data

### 4.1 Create AI Metadata Schema

```sql
-- Step 1: Create the metadata catalog and schema
CREATE CATALOG IF NOT EXISTS ai_unstructured_metadata
COMMENT 'AI/ML metadata catalog for unstructured data pipelines';

CREATE SCHEMA IF NOT EXISTS ai_unstructured_metadata.default
LOCATION 'dbfs:/user/hive/warehouse/ai_unstructured_metadata.db'
COMMENT 'Default schema for RAG pipeline metadata and control tables';

-- Grant permissions to users/groups
GRANT USE CATALOG ON CATALOG ai_unstructured_metadata TO `data-engineers`;
GRANT USE SCHEMA ON SCHEMA ai_unstructured_metadata.default TO `data-engineers`;
GRANT SELECT, MODIFY ON SCHEMA ai_unstructured_metadata.default TO `data-engineers`;
```

### 4.2 Create Ingestion Control Table

The control table governs all ingestion sources and their configuration.

```sql
CREATE TABLE IF NOT EXISTS ai_unstructured_metadata.ingestion_control (
  source_id STRING NOT NULL COMMENT 'Unique identifier for the source system',
  source_system STRING NOT NULL COMMENT 'Type: SFTP, SharePoint, OneDrive, S3, ADLS_Gen2, UC_Volumes',
  connection_secret_scope STRING COMMENT 'Databricks secret scope for credentials',
  source_root_uri STRING NOT NULL COMMENT 'Root URI of the source (sftp://, https://, s3://, abfss://, /Volumes/)',
  path_glob_pattern STRING COMMENT 'Glob pattern for file filtering (e.g., **/*.pdf)',
  file_types ARRAY<STRING> COMMENT 'Allowed file extensions (e.g., ["pdf", "docx"])',
  target_volume_path STRING NOT NULL COMMENT 'UC Volume landing path (/Volumes/catalog/schema/volume)',
  target_delta_table STRING COMMENT 'Target Delta table for parsed chunks',
  parsing_engine STRING COMMENT 'Parsing engine: layout_aware, ocr_multimodal, or structured',
  metadata_extraction_rules MAP<STRING, STRING> COMMENT 'Custom extraction rules as key-value pairs',
  is_active BOOLEAN DEFAULT TRUE COMMENT 'Enable/disable this source',
  last_sync_timestamp TIMESTAMP COMMENT 'Last successful sync time',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  CONSTRAINT pk_ingestion_control PRIMARY KEY (source_id)
) 
USING DELTA
COMMENT 'Control plane for RAG ingestion sources'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
);

-- Create index for efficient source lookup
CREATE INDEX IF NOT EXISTS idx_source_system 
ON ai_unstructured_metadata.ingestion_control (source_system, is_active);
```

### 4.3 Create Document State Registry Table

The state registry tracks every document through the pipeline lifecycle.

```sql
CREATE TABLE IF NOT EXISTS ai_unstructured_metadata.document_state_registry (
  file_id STRING NOT NULL COMMENT 'UUID for the document',
  source_id STRING NOT NULL COMMENT 'Foreign key to ingestion_control.source_id',
  file_uri STRING NOT NULL COMMENT 'Original source URI',
  file_name STRING NOT NULL COMMENT 'Original file name',
  file_extension STRING COMMENT 'File extension (pdf, docx, etc.)',
  file_size_bytes BIGINT COMMENT 'File size in bytes',
  content_sha256_hash STRING NOT NULL COMMENT 'SHA-256 hash for change detection',
  volume_landing_path STRING COMMENT 'UC Volume landing path',
  source_access_control_groups ARRAY<STRING> COMMENT 'Source-level ACL groups for ABAC',
  status STRING NOT NULL COMMENT 'PENDING, PROCESSING, PROCESSED, FAILED, DELETED',
  chunk_count INT COMMENT 'Number of chunks generated',
  processing_duration_seconds DOUBLE COMMENT 'Parse duration in seconds',
  error_message STRING COMMENT 'Error message for failed documents',
  detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() COMMENT 'When file was first detected',
  processed_at TIMESTAMP COMMENT 'When processing completed',
  last_modified_at TIMESTAMP COMMENT 'Source file last modified time',
  CONSTRAINT pk_document_state PRIMARY KEY (file_id),
  CONSTRAINT fk_source FOREIGN KEY (source_id) REFERENCES ai_unstructured_metadata.ingestion_control(source_id)
)
USING DELTA
PARTITIONED BY (source_id)
COMMENT 'Document lifecycle tracking and audit trail'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 30 days',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_status_source 
ON ai_unstructured_metadata.document_state_registry (status, source_id);

CREATE INDEX IF NOT EXISTS idx_content_hash 
ON ai_unstructured_metadata.document_state_registry (content_sha256_hash);

CREATE INDEX IF NOT EXISTS idx_file_uri 
ON ai_unstructured_metadata.document_state_registry (file_uri);
```

### 4.4 Create Document Chunks Table

The final output table for parsed and chunked documents, ready for Vector Search.

```sql
-- First ensure the target catalog and schema exist
CREATE CATALOG IF NOT EXISTS main;
CREATE SCHEMA IF NOT EXISTS main.rag_data;

CREATE TABLE IF NOT EXISTS main.rag_data.document_chunks (
  chunk_id STRING NOT NULL COMMENT 'UUID for the chunk',
  file_id STRING NOT NULL COMMENT 'Foreign key to document_state_registry.file_id',
  source_id STRING NOT NULL COMMENT 'Source system identifier',
  chunk_index INT NOT NULL COMMENT 'Sequential chunk number within document',
  chunk_text STRING NOT NULL COMMENT 'Chunk content (text, tables as Markdown, or metadata)',
  chunk_type STRING NOT NULL COMMENT 'text, table, metadata',
  token_count INT COMMENT 'Token count (tiktoken cl100k_base)',
  file_name STRING COMMENT 'Original file name for display',
  file_extension STRING COMMENT 'File type',
  section_title STRING COMMENT 'Section heading if detected',
  page_number INT COMMENT 'Page number in source document',
  source_uri STRING COMMENT 'Original source URI for citation',
  volume_path STRING COMMENT 'UC Volume path for direct access',
  last_modified_at TIMESTAMP COMMENT 'Source file modification time',
  processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() COMMENT 'Chunk creation time',
  CONSTRAINT pk_chunk PRIMARY KEY (chunk_id)
)
USING DELTA
PARTITIONED BY (source_id)
COMMENT 'Parsed document chunks for Vector Search RAG'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.columnMapping.mode' = 'name'
);

-- Create indexes for efficient retrieval
CREATE INDEX IF NOT EXISTS idx_file_chunk 
ON main.rag_data.document_chunks (file_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_chunk_type 
ON main.rag_data.document_chunks (chunk_type, source_id);
```

### 4.5 Sample Data - Ingestion Control Table

Populate the control table with sample source configurations:

```sql
-- Example 1: SFTP Financial Reports
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id,
  source_system,
  connection_secret_scope,
  source_root_uri,
  path_glob_pattern,
  file_types,
  target_volume_path,
  target_delta_table,
  parsing_engine,
  is_active
) VALUES (
  'sftp_financial_reports',
  'SFTP',
  'rag_pipeline_secrets',
  'sftp://finance.company.com/reports/',
  '**/*.pdf',
  ARRAY('pdf'),
  '/Volumes/main/rag_data/raw_documents_financial',
  'main.rag_data.document_chunks',
  'layout_aware',
  TRUE
);

-- Example 2: SharePoint HR Documents
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id,
  source_system,
  connection_secret_scope,
  source_root_uri,
  path_glob_pattern,
  file_types,
  target_volume_path,
  target_delta_table,
  parsing_engine,
  is_active
) VALUES (
  'sharepoint_hr_docs',
  'SharePoint',
  'rag_pipeline_secrets',
  'https://company.sharepoint.com/sites/HR/Shared Documents',
  '**/*',
  ARRAY('pdf', 'docx', 'pptx'),
  '/Volumes/main/rag_data/raw_documents_hr',
  'main.rag_data.document_chunks',
  'layout_aware',
  TRUE
);

-- Example 3: OneDrive Engineering Documentation
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id,
  source_system,
  connection_secret_scope,
  source_root_uri,
  path_glob_pattern,
  file_types,
  target_volume_path,
  target_delta_table,
  parsing_engine,
  is_active
) VALUES (
  'onedrive_engineering',
  'OneDrive',
  'rag_pipeline_secrets',
  '/drive/root:/Engineering/Documentation',
  '**/*.{pdf,md,txt}',
  ARRAY('pdf', 'md', 'txt'),
  '/Volumes/main/rag_data/raw_documents_engineering',
  'main.rag_data.document_chunks',
  'structured',
  TRUE
);

-- Example 4: AWS S3 Legal Contracts
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id,
  source_system,
  connection_secret_scope,
  source_root_uri,
  file_types,
  target_volume_path,
  target_delta_table,
  parsing_engine,
  metadata_extraction_rules,
  is_active
) VALUES (
  's3_legal_documents',
  'S3',
  'rag_pipeline_secrets',
  's3://company-legal-bucket/contracts/',
  ARRAY('pdf', 'docx'),
  '/Volumes/main/rag_data/raw_documents_legal',
  'main.rag_data.document_chunks',
  'layout_aware',
  MAP('extract_signatures', 'true', 'detect_clauses', 'true'),
  TRUE
);

-- Example 5: ADLS Gen2 Research Papers
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id,
  source_system,
  connection_secret_scope,
  source_root_uri,
  path_glob_pattern,
  file_types,
  target_volume_path,
  target_delta_table,
  parsing_engine,
  is_active
) VALUES (
  'adls_research_data',
  'ADLS_Gen2',
  'rag_pipeline_secrets',
  'abfss://research@companystorage.dfs.core.windows.net/papers/',
  '**/*.pdf',
  ARRAY('pdf'),
  '/Volumes/main/rag_data/raw_documents_research',
  'main.rag_data.document_chunks',
  'ocr_multimodal',
  TRUE
);

-- Example 6: Unity Catalog Volumes Archive
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id,
  source_system,
  connection_secret_scope,
  source_root_uri,
  path_glob_pattern,
  file_types,
  target_volume_path,
  target_delta_table,
  parsing_engine,
  is_active
) VALUES (
  'uc_archive_documents',
  'UC_Volumes',
  NULL,  -- No credentials needed for UC Volumes
  '/Volumes/archive/historical/documents/',
  '**/*',
  ARRAY('pdf', 'docx', 'txt', 'json', 'xml'),
  '/Volumes/main/rag_data/raw_documents_archive',
  'main.rag_data.document_chunks',
  'layout_aware',
  TRUE
);

-- Example 7: Multi-format Marketing Materials (All sources)
INSERT INTO ai_unstructured_metadata.ingestion_control (
  source_id,
  source_system,
  connection_secret_scope,
  source_root_uri,
  file_types,
  target_volume_path,
  target_delta_table,
  parsing_engine,
  is_active
) VALUES (
  's3_marketing_materials',
  'S3',
  'rag_pipeline_secrets',
  's3://company-marketing/campaigns/',
  ARRAY('pdf', 'pptx', 'docx', 'jpg', 'png'),
  '/Volumes/main/rag_data/raw_documents_marketing',
  'main.rag_data.document_chunks',
  'ocr_multimodal',  -- OCR for image-based content
  TRUE
);
```

### 4.6 Verify Table Setup

Run these queries to verify your tables were created correctly:

```sql
-- Check ingestion control table
SELECT 
  source_id,
  source_system,
  source_root_uri,
  is_active,
  created_at
FROM ai_unstructured_metadata.ingestion_control
ORDER BY created_at DESC;

-- Verify table properties (CDF enabled)
SHOW TBLPROPERTIES ai_unstructured_metadata.ingestion_control;
SHOW TBLPROPERTIES ai_unstructured_metadata.document_state_registry;
SHOW TBLPROPERTIES main.rag_data.document_chunks;

-- Check indexes
SHOW INDEXES ON ai_unstructured_metadata.ingestion_control;
SHOW INDEXES ON ai_unstructured_metadata.document_state_registry;
SHOW INDEXES ON main.rag_data.document_chunks;

-- Count records per table
SELECT 'ingestion_control' as table_name, COUNT(*) as row_count 
FROM ai_unstructured_metadata.ingestion_control
UNION ALL
SELECT 'document_state_registry', COUNT(*) 
FROM ai_unstructured_metadata.document_state_registry
UNION ALL
SELECT 'document_chunks', COUNT(*) 
FROM main.rag_data.document_chunks;
```

### 4.7 Sample Queries for Monitoring

```sql
-- View all active sources with their last sync time
SELECT 
  source_id,
  source_system,
  SUBSTRING(source_root_uri, 1, 50) as source_uri,
  is_active,
  last_sync_timestamp,
  DATEDIFF(HOUR, last_sync_timestamp, CURRENT_TIMESTAMP()) as hours_since_sync
FROM ai_unstructured_metadata.ingestion_control
WHERE is_active = TRUE
ORDER BY last_sync_timestamp DESC NULLS LAST;

-- Document processing status summary
SELECT 
  dsr.source_id,
  ic.source_system,
  dsr.status,
  COUNT(*) as document_count,
  ROUND(AVG(dsr.file_size_bytes) / 1024 / 1024, 2) as avg_size_mb,
  ROUND(AVG(dsr.processing_duration_seconds), 2) as avg_duration_sec,
  ROUND(AVG(dsr.chunk_count), 1) as avg_chunks
FROM ai_unstructured_metadata.document_state_registry dsr
JOIN ai_unstructured_metadata.ingestion_control ic ON dsr.source_id = ic.source_id
GROUP BY dsr.source_id, ic.source_system, dsr.status
ORDER BY dsr.source_id, dsr.status;

-- Failed documents requiring attention
SELECT 
  source_id,
  file_name,
  file_extension,
  error_message,
  detected_at,
  DATEDIFF(DAY, detected_at, CURRENT_TIMESTAMP()) as days_pending
FROM ai_unstructured_metadata.document_state_registry
WHERE status = 'FAILED'
ORDER BY detected_at DESC
LIMIT 50;

-- Chunk statistics by source
SELECT 
  source_id,
  chunk_type,
  COUNT(*) as chunk_count,
  ROUND(AVG(token_count), 0) as avg_tokens,
  ROUND(AVG(LENGTH(chunk_text)), 0) as avg_chars,
  COUNT(DISTINCT file_id) as unique_documents
FROM main.rag_data.document_chunks
GROUP BY source_id, chunk_type
ORDER BY source_id, chunk_count DESC;

-- Recent ingestion activity (last 24 hours)
SELECT 
  DATE_TRUNC('hour', detected_at) as hour,
  source_id,
  status,
  COUNT(*) as file_count
FROM ai_unstructured_metadata.document_state_registry
WHERE detected_at >= CURRENT_TIMESTAMP() - INTERVAL 1 DAY
GROUP BY DATE_TRUNC('hour', detected_at), source_id, status
ORDER BY hour DESC, source_id;
```

---

## 5. Python Dependencies

### 5.1 Required Libraries

Install these libraries on your cluster:

```bash
# Core dependencies
pip install databricks-sdk databricks-vectorsearch

# Document parsing
pip install unstructured[all-docs]
pip install pytesseract
pip install opencv-python
pip install pillow

# Token counting
pip install tiktoken

# External source connectors
pip install paramiko  # SFTP
pip install Office365-REST-Python-Client  # SharePoint/OneDrive
pip install boto3  # AWS S3
pip install azure-storage-file-datalake  # Azure ADLS Gen2
pip install azure-identity  # Azure authentication (optional)

# Optional: Advanced table extraction
pip install tabula-py
pip install camelot-py[cv]
```

### 5.2 Cluster Init Script (Recommended)

Create an init script for consistent environment setup:

**Path**: `/Workspace/Shared/init_scripts/rag_pipeline_init.sh`

```bash
#!/bin/bash

# Install system dependencies for OCR
apt-get update
apt-get install -y tesseract-ocr libtesseract-dev poppler-utils

# Install Python dependencies
/databricks/python/bin/pip install --upgrade pip
/databricks/python/bin/pip install \
  unstructured[all-docs] \
  tiktoken \
  paramiko \
  Office365-REST-Python-Client \
  boto3 \
  azure-storage-file-datalake \
  azure-identity \
  databricks-sdk \
  databricks-vectorsearch

echo "RAG Pipeline init script completed successfully"
```

**Add to cluster configuration**:
```yaml
init_scripts:
  - dbfs:/Workspace/Shared/init_scripts/rag_pipeline_init.sh
```

---

## 6. Operational Guidelines

### 6.1 Pipeline Execution Schedule

**Recommended Workflow Schedule**:

```yaml
Phase 1 - Ingestion:
  Frequency: Hourly or Daily (depends on source update frequency)
  Databricks Job: rag_ingestion_job
  Schedule: 0 */6 * * * (Every 6 hours)
  
Phase 2 - Parsing:
  Frequency: Triggered after ingestion
  Databricks Job: rag_parsing_job
  Trigger: On completion of ingestion job
  
Phase 3 - Vector Sync:
  Frequency: Continuous or Triggered
  Type: Vector Search Delta Sync (CONTINUOUS mode)
  Auto-sync: Enabled via Change Data Feed
```

### 6.2 Databricks Workflow Definition

**Sample Workflow JSON** for Databricks Jobs:

```json
{
  "name": "Multi-Modal RAG Pipeline",
  "tasks": [
    {
      "task_key": "ingestion",
      "description": "Phase 1: File Ingestion",
      "notebook_task": {
        "notebook_path": "/Users/vamshialwayskush@gmail.com/Multi Model RAG/01_MultiModal_RAG_Orchestrator",
        "base_parameters": {
          "phase": "ingestion"
        }
      },
      "existing_cluster_id": "<cluster_id>"
    },
    {
      "task_key": "parsing",
      "description": "Phase 2: Document Parsing",
      "depends_on": [{"task_key": "ingestion"}],
      "notebook_task": {
        "notebook_path": "/Users/vamshialwayskush@gmail.com/Multi Model RAG/01_MultiModal_RAG_Orchestrator",
        "base_parameters": {
          "phase": "parsing"
        }
      },
      "existing_cluster_id": "<cluster_id>"
    },
    {
      "task_key": "vectorization",
      "description": "Phase 3: Vector Search Sync",
      "depends_on": [{"task_key": "parsing"}],
      "notebook_task": {
        "notebook_path": "/Users/vamshialwayskush@gmail.com/Multi Model RAG/01_MultiModal_RAG_Orchestrator",
        "base_parameters": {
          "phase": "vectorization"
        }
      },
      "existing_cluster_id": "<cluster_id>"
    }
  ],
  "schedule": {
    "quartz_cron_expression": "0 0 */6 * * ?",
    "timezone_id": "UTC"
  }
}
```

### 6.3 Monitoring & Alerting

**Key Metrics to Monitor**:

1. **Ingestion Metrics**:
   - Files synced per run (new, modified, deleted)
   - Sync errors per source
   - Average file size
   - SHA-256 computation time

2. **Parsing Metrics**:
   - Documents processed vs. failed
   - Average chunks per document
   - Parsing duration per file type
   - Worker memory utilization

3. **Vector Search Metrics**:
   - Index sync lag
   - Embedding generation time
   - Query latency (p50, p95, p99)
   - Index size growth rate

**SQL Queries for Monitoring**:

```sql
-- Ingestion success rate
SELECT 
  source_id,
  COUNT(*) as total_files,
  SUM(CASE WHEN status = 'PROCESSED' THEN 1 ELSE 0 END) as successful,
  ROUND(100.0 * SUM(CASE WHEN status = 'PROCESSED' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate_pct
FROM ai_unstructured_metadata.document_state_registry
GROUP BY source_id;

-- Processing duration by file type
SELECT 
  file_extension,
  COUNT(*) as file_count,
  ROUND(AVG(processing_duration_seconds), 2) as avg_duration_sec,
  ROUND(AVG(chunk_count), 1) as avg_chunks
FROM ai_unstructured_metadata.document_state_registry
WHERE status = 'PROCESSED'
GROUP BY file_extension
ORDER BY avg_duration_sec DESC;
```

---

## 7. Troubleshooting

### 7.1 Common Issues & Resolutions

#### Issue: Worker OOM During Ingestion

**Symptoms**: `OutOfMemoryError` during file download

**Root Cause**: Large files being loaded into worker memory

**Resolution**:
- Ensure files are downloaded to `/tmp` and streamed to volumes (already implemented)
- Increase worker memory: Use `Standard_E8s_v3` or higher
- Reduce batch size in `mapInPandas` operations

#### Issue: Table Detection Failures

**Symptoms**: Tables extracted as plain text instead of Markdown

**Root Cause**: Complex table layouts or scanned PDFs

**Resolution**:
- Switch `parsing_engine` to `ocr_multimodal` in control table
- Install advanced table extraction: `pip install camelot-py[cv]`
- Manually adjust `_table_to_markdown()` function for specific document formats

#### Issue: Vector Search Index Not Syncing

**Symptoms**: Index status stuck in `SYNCING` or `PROVISIONING`

**Root Cause**: Change Data Feed not enabled or table has no changes

**Resolution**:
```sql
-- Verify CDF is enabled
SHOW TBLPROPERTIES main.rag_data.document_chunks;

-- Enable if missing
ALTER TABLE main.rag_data.document_chunks
SET TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- Manually trigger sync
SELECT * FROM main.rag_data.document_chunks LIMIT 1;  -- Force table read
```

#### Issue: SharePoint/OneDrive Authentication Failures

**Symptoms**: `401 Unauthorized` or `403 Forbidden` errors

**Root Cause**: Expired tokens or insufficient permissions

**Resolution**:
1. Verify Azure AD app permissions:
   - SharePoint: `Sites.Read.All`, `Files.Read.All`
   - OneDrive: `Files.Read.All`, `User.Read.All`
2. Regenerate client secret in Azure Portal
3. Update Databricks secrets with new credentials
4. Grant admin consent for permissions in Azure AD

#### Issue: Chunking Splits Tables Mid-Row

**Symptoms**: Table rows split across multiple chunks

**Root Cause**: Token limit reached within a table

**Resolution**:
- Increase `MAX_CHUNK_TOKENS` to accommodate larger tables
- Implement table-aware chunking (already in code - tables are never split)
- For extremely large tables, consider summarization or separate table indexing

#### Issue: S3 Access Denied or NoCredentialsError

**Symptoms**: `403 Forbidden`, `NoCredentialsError`, or `InvalidAccessKeyId`

**Root Cause**: Invalid AWS credentials or insufficient IAM permissions

**Resolution**:
1. Verify credentials are correct in Databricks secrets:
   ```bash
   # Test credential retrieval (run in notebook)
   dbutils.secrets.get(scope="rag_pipeline_secrets", key="<source_id>_access_key_id")
   ```
2. Check IAM policy has `s3:GetObject` and `s3:ListBucket` permissions
3. Verify bucket name and region are correct in source_root_uri
4. For cross-account access, ensure bucket policy allows your IAM user/role
5. Check if MFA or IP restrictions are blocking access

#### Issue: ADLS Gen2 AuthenticationError

**Symptoms**: `401 Unauthorized` or `AuthenticationFailed`

**Root Cause**: Invalid storage account key or incorrect account name

**Resolution**:
1. Regenerate storage account key in Azure Portal
2. Update Databricks secret with new key
3. Verify storage account name matches exactly (case-sensitive)
4. Ensure container exists and is accessible
5. Check firewall rules: Add Databricks workspace IP ranges to allowed list
6. For service principal auth, verify RBAC role assignment (`Storage Blob Data Reader`)

#### Issue: UC Volumes Permission Denied

**Symptoms**: `PermissionDenied` when accessing source or target volume

**Root Cause**: Missing READ_VOLUME or WRITE_VOLUME grants

**Resolution**:
```sql
-- Check current permissions
SHOW GRANTS ON VOLUME source_catalog.source_schema.source_volume;

-- Grant read access (for source)
GRANT READ VOLUME ON VOLUME source_catalog.source_schema.source_volume 
TO `user@company.com`;

-- Grant write access (for target)
GRANT WRITE VOLUME ON VOLUME main.rag_data.raw_documents_uc 
TO `user@company.com`;

-- For service principals
GRANT READ VOLUME ON VOLUME source_catalog.source_schema.source_volume 
TO SERVICE_PRINCIPAL `<application-id>`;
```

---

## Appendix: Performance Tuning Parameters

### Spark Configuration for Large-Scale Processing

```python
spark.conf.set("spark.sql.shuffle.partitions", "200")
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")
spark.conf.set("spark.databricks.delta.autoCompact.enabled", "true")
spark.conf.set("spark.sql.files.maxPartitionBytes", "134217728")  # 128MB

# For memory-intensive parsing
spark.conf.set("spark.executor.memory", "48g")
spark.conf.set("spark.driver.memory", "32g")
spark.conf.set("spark.executor.memoryOverhead", "8g")
```

### Vector Search Performance Tuning

```python
# For high-throughput indexing
vector_search_manager.create_index_for_source(
    source_id="your_source",
    embedding_model="databricks-bge-large-en",
    pipeline_type="CONTINUOUS",  # Real-time sync
)

# For batch indexing with lower cost
vector_search_manager.create_index_for_source(
    source_id="your_source",
    embedding_model="databricks-bge-large-en",
    pipeline_type="TRIGGERED",  # Manual sync control
)
```

---

**End of Configuration Guide**