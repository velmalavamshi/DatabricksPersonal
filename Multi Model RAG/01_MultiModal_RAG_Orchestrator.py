# Databricks notebook source
# DBTITLE 1,Multi-Modal RAG Pipeline - Main Orchestrator
# MAGIC %md
# MAGIC # Enterprise Multi-Modal RAG Data Ingestion Pipeline
# MAGIC
# MAGIC **Author**: Principal Databricks Architect  
# MAGIC **Date**: 2026-09-04  
# MAGIC **Version**: 1.0
# MAGIC
# MAGIC ## Pipeline Overview
# MAGIC
# MAGIC This notebook orchestrates an enterprise-grade multi-modal RAG data ingestion pipeline across three phases:
# MAGIC
# MAGIC 1. **Ingestion Phase**: Sync files from SFTP, SharePoint, OneDrive to Unity Catalog Volumes
# MAGIC 2. **Parsing Phase**: Distributed layout-aware extraction with table preservation and token-aware chunking
# MAGIC 3. **Vectorization Phase**: Automated Vector Search Delta Sync Index provisioning with managed embeddings
# MAGIC
# MAGIC ### Key Features
# MAGIC
# MAGIC * **Metadata Control Plane**: Unity Catalog-based governance and audit tracking
# MAGIC * **Incremental Sync**: SHA-256 content hashing for change detection
# MAGIC * **Worker OOM Prevention**: Single-stream downloaders landing directly to UC Volumes
# MAGIC * **Table Integrity**: Markdown table preservation without mid-row splits
# MAGIC * **Deletion Handling**: Tombstone records for vector pruning
# MAGIC * **Scalability**: Distributed processing via PySpark mapInPandas
# MAGIC
# MAGIC ---

# COMMAND ----------

# DBTITLE 1,Configuration & Setup
# ============================================================================
# Configuration Parameters
# ============================================================================

# Catalog and Schema
CATALOG_NAME = "main"
SCHEMA_NAME = "rag_data"
METADATA_SCHEMA = "ai_unstructured_metadata"

# Vector Search Configuration
VECTOR_SEARCH_ENDPOINT = "rag_vector_search_endpoint"
EMBEDDING_MODEL = "databricks-bge-large-en"  # Managed embedding model
PIPELINE_TYPE = "TRIGGERED"  # or "CONTINUOUS" for real-time sync

# Parsing Configuration
MAX_CHUNK_TOKENS = 512  # Token limit per chunk

# Processing Control
SOURCE_ID_FILTER = None  # Set to specific source_id or None for all sources

print("Configuration loaded successfully")

# COMMAND ----------

# DBTITLE 1,Import Modules
# ============================================================================
# Import Pipeline Modules
# ============================================================================

import sys
import importlib.util
from pathlib import Path

# Add modules directory to Python path
modules_path = "/Workspace/Users/vamshialwayskush@gmail.com/Multi Model RAG/modules"
sys.path.insert(0, modules_path)

# Import custom modules
from ingestion_engine import IngestionEngine
from parsing_engine import ParsingEngine
from vector_search_manager import VectorSearchManager

print("\u2713 Modules imported successfully")

# COMMAND ----------

# DBTITLE 1,Initialize Pipeline Components
# ============================================================================
# Initialize Pipeline Components
# ============================================================================

from pyspark.sql import SparkSession

# Get or create Spark session
spark = SparkSession.builder.getOrCreate()

# Initialize pipeline engines
ingestion_engine = IngestionEngine(spark)
parsing_engine = ParsingEngine(spark, max_chunk_tokens=MAX_CHUNK_TOKENS)
vector_search_manager = VectorSearchManager(spark, endpoint_name=VECTOR_SEARCH_ENDPOINT)

print("\u2713 Pipeline components initialized")
print(f"  - Ingestion Engine: Ready")
print(f"  - Parsing Engine: Max chunk tokens = {MAX_CHUNK_TOKENS}")
print(f"  - Vector Search Manager: Endpoint = {VECTOR_SEARCH_ENDPOINT}")

# COMMAND ----------

# DBTITLE 1,Phase 1: File Ingestion
# MAGIC %md
# MAGIC ## Phase 1: File Ingestion
# MAGIC
# MAGIC Synchronize files from external sources (SFTP, SharePoint, OneDrive) to Unity Catalog Volumes.
# MAGIC
# MAGIC **Features**:
# MAGIC * Incremental sync using SHA-256 content hashing
# MAGIC * Single-stream downloaders to prevent Worker OOMs
# MAGIC * Deletion detection with tombstone records
# MAGIC * Exponential backoff retry logic

# COMMAND ----------

# DBTITLE 1,Run Ingestion
# ============================================================================
# Execute File Ingestion
# ============================================================================

import time
start_time = time.time()

print("Starting file ingestion phase...\n")

# Run ingestion for all active sources or filtered source
ingestion_stats = ingestion_engine.run_ingestion(source_system=SOURCE_ID_FILTER)

ingestion_duration = time.time() - start_time

print("\n" + "="*80)
print("INGESTION PHASE COMPLETE")
print("="*80)
print(f"Duration: {ingestion_duration:.2f} seconds")
print(f"New files: {ingestion_stats['new']}")
print(f"Modified files: {ingestion_stats['modified']}")
print(f"Deleted files: {ingestion_stats['deleted']}")
print(f"Errors: {ingestion_stats['errors']}")
print("="*80)

# COMMAND ----------

# DBTITLE 1,Phase 2: Document Parsing & Chunking
# MAGIC %md
# MAGIC ## Phase 2: Document Parsing & Chunking
# MAGIC
# MAGIC Distributed layout-aware extraction with table preservation and token-aware chunking.
# MAGIC
# MAGIC **Features**:
# MAGIC * PySpark mapInPandas for distributed processing
# MAGIC * Layout-aware parsing preserving semantic structure
# MAGIC * Tables converted to Markdown format without mid-row splits
# MAGIC * Token-aware chunking with safe boundaries
# MAGIC * Metadata retention: page number, element type, ACL groups

# COMMAND ----------

# DBTITLE 1,Run Parsing
# ============================================================================
# Execute Document Parsing
# ============================================================================

start_time = time.time()

print("Starting document parsing phase...\n")

# Parse pending documents
parsing_stats = parsing_engine.parse_documents(source_id=SOURCE_ID_FILTER)

parsing_duration = time.time() - start_time

print("\n" + "="*80)
print("PARSING PHASE COMPLETE")
print("="*80)
print(f"Duration: {parsing_duration:.2f} seconds")
print(f"Chunks processed: {parsing_stats['processed']}")
print(f"Failed documents: {parsing_stats['failed']}")
print("="*80)

# COMMAND ----------

# DBTITLE 1,Phase 3: Vector Search Integration
# MAGIC %md
# MAGIC ## Phase 3: Vector Search Integration
# MAGIC
# MAGIC Automated provisioning of Databricks Vector Search Delta Sync Indexes with managed embeddings.
# MAGIC
# MAGIC **Features**:
# MAGIC * Managed embeddings via Databricks Foundation Models
# MAGIC * Delta Sync Index with Change Data Feed
# MAGIC * Automatic vector pruning for deleted documents
# MAGIC * TRIGGERED or CONTINUOUS sync modes

# COMMAND ----------

# DBTITLE 1,Create Vector Search Indexes
# ============================================================================
# Create Vector Search Indexes
# ============================================================================

start_time = time.time()

print("Starting vector search index creation phase...\n")

# Create vector search endpoint
vector_search_manager.create_endpoint()

# Create indexes for all active sources
index_map = vector_search_manager.create_all_indexes(
    embedding_model=EMBEDDING_MODEL,
    pipeline_type=PIPELINE_TYPE
)

vectorization_duration = time.time() - start_time

print("\n" + "="*80)
print("VECTORIZATION PHASE COMPLETE")
print("="*80)
print(f"Duration: {vectorization_duration:.2f} seconds")
print(f"Indexes created: {len(index_map)}")
for source_id, index_name in index_map.items():
    print(f"  - {source_id}: {index_name}")
print("="*80)

# COMMAND ----------

# DBTITLE 1,Sync Vector Search Indexes
# ============================================================================
# Sync Vector Search Indexes (for TRIGGERED pipeline type)
# ============================================================================

if PIPELINE_TYPE == "TRIGGERED":
    print("Triggering sync for all indexes...\n")
    vector_search_manager.sync_all_indexes()
    print("\u2713 All indexes synced successfully")
else:
    print("Pipeline type is CONTINUOUS - indexes sync automatically")

# COMMAND ----------

# DBTITLE 1,Pipeline Summary & Monitoring
# MAGIC %md
# MAGIC ## Pipeline Summary & Monitoring
# MAGIC
# MAGIC Check the status of all vector search indexes and pipeline health.

# COMMAND ----------

# DBTITLE 1,Get Index Status
# ============================================================================
# Get Vector Search Index Status
# ============================================================================

import pandas as pd

print("Fetching status of all vector search indexes...\n")

index_statuses = vector_search_manager.get_all_indexes_status()

# Display as DataFrame
status_df = pd.DataFrame(index_statuses)
print(status_df.to_string(index=False))

print("\n" + "="*80)
print("PIPELINE HEALTH CHECK COMPLETE")
print("="*80)

# COMMAND ----------

# DBTITLE 1,Query Documents State
# MAGIC %sql
# MAGIC -- ============================================================================
# MAGIC -- Query Document Processing State
# MAGIC -- ============================================================================
# MAGIC
# MAGIC SELECT 
# MAGIC   source_id,
# MAGIC   status,
# MAGIC   COUNT(*) as file_count,
# MAGIC   SUM(file_size_bytes) / 1024 / 1024 as total_size_mb,
# MAGIC   SUM(chunk_count) as total_chunks
# MAGIC FROM ai_unstructured_metadata.document_state_registry
# MAGIC GROUP BY source_id, status
# MAGIC ORDER BY source_id, status;

# COMMAND ----------

# DBTITLE 1,Example: Semantic Search Query
# ============================================================================
# Example: Query Vector Search Index
# ============================================================================

# Example query - uncomment and customize
"""
index_name = "main.rag_data.financial_chunks_vs_index"
query_text = "What are the quarterly revenue figures for Q4 2025?"

results = vector_search_manager.query_index(
    index_name=index_name,
    query_text=query_text,
    num_results=5,
    filters={"source_id": "sftp_financial_reports"}  # Optional metadata filter
)

print(f"Query: {query_text}\n")
print(f"Found {len(results)} results:\n")

for i, result in enumerate(results, 1):
    print(f"Result {i}:")
    print(f"  File: {result.get('file_name')}")
    print(f"  Page: {result.get('page_number')}")
    print(f"  Text: {result.get('chunk_text')[:200]}...")
    print(f"  Score: {result.get('score')}")
    print()
"""

print("Uncomment the code above to run a semantic search query")

# COMMAND ----------

