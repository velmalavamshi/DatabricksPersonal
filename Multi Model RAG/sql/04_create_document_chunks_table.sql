-- First ensure the target catalog and schema exist
CREATE SCHEMA IF NOT EXISTS mde_dev.rag_data;

CREATE TABLE IF NOT EXISTS mde_dev.rag_data.document_chunks (
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
  'delta.feature.allowColumnDefaults' = 'supported',
  'delta.enableChangeDataFeed' = 'true',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.columnMapping.mode' = 'name'
);