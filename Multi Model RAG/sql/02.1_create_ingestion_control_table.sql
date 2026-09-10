CREATE TABLE IF NOT EXISTS mde_dev.ai_unstructured_metadata.ingestion_control (
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
  'delta.feature.allowColumnDefaults' = 'supported',
  'delta.enableChangeDataFeed' = 'true',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
);
