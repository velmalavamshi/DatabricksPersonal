CREATE TABLE IF NOT EXISTS mde_dev.ai_unstructured_metadata.document_state_registry (
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
  CONSTRAINT fk_source FOREIGN KEY (source_id) REFERENCES mde_dev.ai_unstructured_metadata.ingestion_control(source_id)
)
USING DELTA
PARTITIONED BY (source_id)
COMMENT 'Document lifecycle tracking and audit trail'
TBLPROPERTIES (
  'delta.feature.allowColumnDefaults' = 'supported',
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 30 days',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
);

-- -- Create indexes for common query patterns
-- CREATE INDEX IF NOT EXISTS idx_status_source 
-- ON ai_unstructured_metadata.document_state_registry (status, source_id);

-- CREATE INDEX IF NOT EXISTS idx_content_hash 
-- ON ai_unstructured_metadata.document_state_registry (content_sha256_hash);

-- CREATE INDEX IF NOT EXISTS idx_file_uri 
-- ON ai_unstructured_metadata.document_state_registry (file_uri);