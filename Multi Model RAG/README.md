# Enterprise Multi-Modal RAG Data Ingestion Pipeline

**Author**: Principal Databricks Architect  
**Date**: 2026-09-04  
**Version**: 1.0

---

## Overview

A production-ready, enterprise-grade multi-modal RAG (Retrieval-Augmented Generation) data ingestion and parsing pipeline built on Databricks. This solution processes unstructured and complex documents (PDFs with embedded tables/charts, Word, PPTX, JSON, XML, TXT) from multiple sources (SFTP, SharePoint, OneDrive) and prepares them for semantic search and AI-powered retrieval.

## Architecture Highlights

### ✅ Metadata Control Plane & Governance
* **Unity Catalog Integration**: All metadata stored in managed Delta tables
* **Control Table**: Metadata-driven configuration for multi-source ingestion
* **State Registry**: Complete audit trail with SHA-256 content hashing
* **Deletion Tracking**: Tombstone records for automatic vector pruning

### ✅ Scalable Ingestion Engine
* **OOM Prevention**: Single-stream downloaders landing files directly to UC Volumes
* **Incremental Sync**: SHA-256 hash-based change detection
* **Multi-Source Support**: SFTP, SharePoint (Office365), OneDrive (Graph API)
* **Retry Logic**: Exponential backoff for transient failures
* **Rate Limiting**: Configurable throttling for external API calls

### ✅ Distributed Layout-Aware Parsing
* **PySpark mapInPandas**: Distributed processing across Spark workers
* **Semantic Structure**: Preserves reading order and document hierarchy
* **Table Integrity**: Converts tables to Markdown format without mid-row splits
* **Multimodal Support**: Text, tables, charts, and images with bounding boxes
* **Token-Aware Chunking**: Safe boundaries respecting context windows

### ✅ Vector Search Integration
* **Managed Embeddings**: Automated embedding generation via Databricks Foundation Models
* **Delta Sync Index**: Real-time or triggered sync with Change Data Feed
* **Auto-Pruning**: Automatic vector deletion based on tombstone records
* **Semantic Search**: Production-ready query interface with metadata filters

---

## Project Structure

```
Multi Model RAG/
├── sql/                                    # Unity Catalog DDL scripts
│   ├── 01_create_metadata_schema.sql       # Schema creation
│   ├── 02_create_ingestion_control_table.sql # Control plane table
│   ├── 03_create_document_state_registry.sql # Audit & state tracking
│   └── 04_create_document_chunks_table.sql   # Vector search source table
│
├── modules/                               # Production Python modules
│   ├── ingestion_engine.py                # Multi-source file sync
│   ├── parsing_engine.py                  # Distributed parsing & chunking
│   └── vector_search_manager.py           # Vector Search automation
│
├── 01_MultiModal_RAG_Orchestrator.ipynb   # Main orchestration notebook
│
├── docs/
│   └── CONFIGURATION_GUIDE.md             # Deployment & operations guide
│
└── README.md                              # This file
```

---

## Quick Start

### Prerequisites

1. **Databricks Workspace**: Runtime 14.3 LTS ML or later
2. **Unity Catalog**: Enabled with appropriate permissions
3. **Secret Scope**: For storing external credentials
4. **Compute Cluster**: See [Cluster Sizing](#cluster-sizing)

### Step 1: Deploy Unity Catalog Schema

Execute the SQL DDL scripts in order:

```sql
-- Run in Databricks SQL Editor or notebook
%run ./sql/01_create_metadata_schema.sql
%run ./sql/02_create_ingestion_control_table.sql
%run ./sql/03_create_document_state_registry.sql
%run ./sql/04_create_document_chunks_table.sql
```

### Step 2: Configure Secret Management

Follow the [Secret Management Configuration](./docs/CONFIGURATION_GUIDE.md#1-secret-management-configuration) guide to set up credentials for SFTP, SharePoint, and OneDrive.

### Step 3: Populate Control Table

Add source configurations to the `ingestion_control` table:

```sql
INSERT INTO ai_unstructured_metadata.ingestion_control VALUES
  (
    'sftp_financial_reports',           -- source_id
    'SFTP',                              -- source_system
    'rag_pipeline_secrets',              -- connection_secret_scope
    'sftp://finance.company.com/reports/', -- source_root_uri
    '**/*.pdf',                          -- path_glob_pattern
    ARRAY('pdf', 'xlsx'),                -- file_types
    '/Volumes/main/rag_data/raw_documents/financial', -- target_volume_path
    'main.rag_data.financial_chunks',    -- target_delta_table
    'layout_parser',                     -- parsing_engine
    TRUE,                                -- is_active
    NULL,                                -- last_sync_timestamp
    CURRENT_TIMESTAMP(),                 -- created_at
    CURRENT_TIMESTAMP()                  -- updated_at
  );
```

### Step 4: Create Unity Catalog Volumes

```sql
CREATE VOLUME IF NOT EXISTS main.rag_data.raw_documents_financial
COMMENT 'Landing zone for financial reports from SFTP';
```

### Step 5: Install Python Dependencies

On your cluster, install required libraries:

```bash
pip install databricks-sdk databricks-vectorsearch
pip install unstructured[all-docs] tiktoken
pip install paramiko Office365-REST-Python-Client
```

### Step 6: Run the Pipeline

Open and execute the orchestration notebook:

[01_MultiModal_RAG_Orchestrator](#notebook-3733443076255493)

---

## Cluster Sizing

### Development (Testing)
* **Node Type**: Standard_DS3_v2 (14GB Memory, 4 Cores)
* **Workers**: 2-4 (Autoscaling)
* **Cost**: ~$1-2/hour
* **Throughput**: ~50-100 documents/hour

### Production (Large Scale)
* **Node Type**: Standard_DS4_v2 or Standard_E8s_v3 (Memory-Optimized)
* **Workers**: 8-16 (Autoscaling)
* **Cost**: ~$8-12/hour
* **Throughput**: ~500-1000 documents/hour

### High-Performance Parsing
* **Node Type**: Standard_E8s_v3 (64GB Memory, 8 Cores)
* **Workers**: 16-32 (Autoscaling)
* **Cost**: ~$15-25/hour
* **Throughput**: ~2000-3000 documents/hour

See the [Cluster Sizing Recommendations](./docs/CONFIGURATION_GUIDE.md#2-cluster-sizing-recommendations) for detailed configurations.

---

## Pipeline Phases

### Phase 1: File Ingestion

**Module**: `ingestion_engine.py`

**Process**:
1. Retrieve active sources from `ingestion_control` table
2. Connect to external systems (SFTP/SharePoint/OneDrive)
3. List files matching glob patterns and file type filters
4. Download files to temp location and compute SHA-256 hash
5. Compare against `document_state_registry` for incremental sync
6. Copy new/modified files to Unity Catalog Volumes
7. Create/update state records
8. Detect and mark deleted files (tombstones)

**Key Features**:
* Single-stream downloaders prevent Worker OOMs
* Exponential backoff retry logic
* SHA-256 content hashing for change detection
* Deletion tracking for vector pruning

---

### Phase 2: Document Parsing & Chunking

**Module**: `parsing_engine.py`

**Process**:
1. Load pending files from volumes using `binaryFile` format
2. Distribute parsing across Spark workers via `mapInPandas`
3. Extract semantic elements:
   * **Text**: Paragraphs, headings, captions
   * **Tables**: Converted to Markdown format
   * **Charts/Images**: Bounding boxes or vision model captions
4. Apply token-aware chunking with safe boundaries
5. Preserve metadata: page number, element type, ACL groups
6. Write chunks to target Delta table with CDF enabled
7. Update state registry with processing status

**Key Features**:
* Layout-aware extraction preserving reading order
* Tables converted to Markdown without mid-row splits
* Token counting with Tiktoken for boundary-safe chunks
* Distributed processing for scalability

---

### Phase 3: Vector Search Integration

**Module**: `vector_search_manager.py`

**Process**:
1. Create Vector Search endpoint (if not exists)
2. Enable Change Data Feed on target Delta tables
3. Create Delta Sync Index with managed embeddings:
   * **Embedding Model**: `databricks-bge-large-en` (or custom)
   * **Primary Key**: `chunk_id`
   * **Source Column**: `chunk_text`
   * **Pipeline Type**: `TRIGGERED` or `CONTINUOUS`
4. Sync index (for TRIGGERED mode)
5. Monitor index status and health

**Key Features**:
* Managed embeddings via Databricks Foundation Models
* Automatic sync with Change Data Feed
* Deletion handling via primary key sync
* Production-ready query interface

---

## Operational Guidelines

### Recommended Execution Schedule

```yaml
Ingestion: Every 6 hours (0 */6 * * *)
Parsing: Triggered after ingestion completion
Vector Sync: Continuous (via Delta Sync)
```

### Monitoring Queries

**Ingestion Success Rate**:
```sql
SELECT 
  source_id,
  COUNT(*) as total_files,
  SUM(CASE WHEN status = 'PROCESSED' THEN 1 ELSE 0 END) as successful,
  ROUND(100.0 * SUM(CASE WHEN status = 'PROCESSED' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate_pct
FROM ai_unstructured_metadata.document_state_registry
GROUP BY source_id;
```

**Processing Duration by File Type**:
```sql
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

### Vector Search Query Example

```python
from modules.vector_search_manager import VectorSearchManager

vector_manager = VectorSearchManager(spark)

results = vector_manager.query_index(
    index_name="main.rag_data.financial_chunks_vs_index",
    query_text="What are the quarterly revenue figures for Q4 2025?",
    num_results=5,
    filters={"source_id": "sftp_financial_reports"}  # Optional metadata filter
)

for i, result in enumerate(results, 1):
    print(f"Result {i}:")
    print(f"  File: {result['file_name']}")
    print(f"  Page: {result['page_number']}")
    print(f"  Text: {result['chunk_text'][:200]}...")
    print()
```

---

## Key Design Decisions

### Why Single-Stream Downloaders?

**Problem**: Distributing large file downloads across Spark workers causes OOMs.

**Solution**: Download files sequentially to a temp location, compute hash, then copy to volumes. This prevents workers from holding massive byte arrays in memory.

### Why Markdown for Tables?

**Problem**: Raw table text loses relational structure, degrading retrieval quality.

**Solution**: Convert tables to Markdown format with proper row/column delimiters. This preserves table semantics for LLM interpretation while remaining text-based for embedding.

### Why Token-Aware Chunking?

**Problem**: Fixed character-based chunking can split sentences mid-token or break tables.

**Solution**: Use Tiktoken to count tokens and chunk at safe boundaries (paragraphs, sentences). Tables are treated as atomic units and never split.

### Why Delta Sync Index?

**Problem**: Manual embedding generation and vector updates are error-prone.

**Solution**: Databricks Vector Search Delta Sync Index automatically:
* Generates embeddings using managed models
* Syncs changes from Delta table via CDF
* Handles upserts and deletions via primary key
* Scales to billions of vectors

---

## Troubleshooting

Refer to the [Troubleshooting Guide](./docs/CONFIGURATION_GUIDE.md#6-troubleshooting) for common issues:

* Worker OOM during ingestion
* Table detection failures
* Vector Search index not syncing
* SharePoint/OneDrive authentication failures
* Chunking splits tables mid-row

---

## Performance Tuning

### Spark Configuration

```python
spark.conf.set("spark.sql.shuffle.partitions", "200")
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")
spark.conf.set("spark.databricks.delta.autoCompact.enabled", "true")
```

### Vector Search Performance

* **High Throughput**: Use `CONTINUOUS` pipeline type for real-time sync
* **Cost Optimization**: Use `TRIGGERED` pipeline type for batch indexing
* **Query Performance**: Add metadata filters to reduce search scope

---

## Security & Compliance

### Data Governance

* **Unity Catalog Integration**: All data governed by UC permissions
* **ACL Inheritance**: Source system ACL groups preserved in chunks
* **Audit Trail**: Complete processing history in state registry
* **Deletion Handling**: Tombstone records ensure GDPR/CCPA compliance

### Secret Management

* **Databricks Secrets**: All credentials stored in secret scopes
* **No Hard-Coded Credentials**: All external system access via secrets
* **Least Privilege**: OAuth app registrations with minimal permissions

---

## Future Enhancements

* **OCR Multimodal Parsing**: Vision model integration for scanned documents
* **Advanced Table Extraction**: Camelot/Tabula integration for complex tables
* **Document Classification**: Auto-tagging by document type and domain
* **Active Learning**: User feedback loop for improving chunk quality
* **Multi-Tenant Support**: Isolated processing per business unit

---

## Support & Contributing

**Maintainer**: Principal Databricks Architect  
**Contact**: vamshialwayskush@gmail.com

For issues, enhancements, or questions, please contact the maintainer or your Databricks account team.

---

## License

This solution is provided as-is for internal enterprise use. Databricks proprietary components (Vector Search, Unity Catalog, Foundation Models) require appropriate workspace licensing.

---

**Built with ❤️ on Databricks**