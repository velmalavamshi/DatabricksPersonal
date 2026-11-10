# Databricks notebook source
# DBTITLE 1,Agent 89: QVD Extraction Agent
﻿# Databricks notebook source
%md
# Agent 89: QVD Extraction Agent

**Purpose:** Analyzes QVD (QlikView Data) files — extracts schemas, profiles data, maps QVD layered architecture (Extract→Transform→Mart) to Delta tables in Bronze/Silver layers.

**Pipeline Position:** Specialist Layer → called by Agent 88 (orchestrator)

**Inputs:**
- QVD file paths or metadata exports
- QVD XML headers (schema, row count, field types)
- QVD layer classification (Raw/Transform/Mart)

**Outputs:**
- Delta table DDL (CREATE TABLE statements with proper types)
- Schema mapping report (QVD field → Delta column)
- Data profiling summary (nulls, cardinality, min/max)
- Ingestion notebook (Auto Loader or COPY INTO)

**QVD Internals:**
- Binary columnar format (proprietary, highly compressed)
- XML header contains: table name, fields[], no. of records, creator info
- Field types: ASCII, FIX, REAL, DATE, TIMESTAMP, INTERVAL
- QVD Generator: which LOAD statement created this file
- Typical layering: Raw QVDs (source extract) → Transform QVDs (cleaned) → App QVDs (shaped for UI)

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "QVD Analysis Request")
dbutils.widgets.text("qvd_path", "", "QVD File/Folder Path")
dbutils.widgets.dropdown("target_layer", "bronze", ["bronze", "silver"], "Target Layer")
dbutils.widgets.text("target_schema", "mde_dev.bronze", "Target Schema")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
qvd_path = dbutils.widgets.get("qvd_path")
target_layer = dbutils.widgets.get("target_layer")
target_schema = dbutils.widgets.get("target_schema")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context Gathering — QVD Format Knowledge
# ══════════════════════════════════════════════════════════════════════

# QVD field type mapping to Delta/Spark types
QVD_TO_DELTA_TYPE_MAP = {
    "ASCII": "STRING",
    "FIX": "BIGINT",           # Fixed-point integer
    "REAL": "DOUBLE",           # Floating point
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
    "INTERVAL": "STRING",       # No direct Delta equivalent
    "TEXT": "STRING",
    "INTEGER": "BIGINT",
    "DUAL": "STRING",           # Qlik dual values (text + numeric)
}

# QVD layer detection patterns
QVD_LAYER_PATTERNS = {
    "extract": ["_raw", "_extract", "_src", "Extract_", "RAW_"],
    "transform": ["_clean", "_transform", "_trn", "Transform_", "TRN_"],
    "mart": ["_mart", "_app", "_dim", "_fact", "DIM_", "FACT_"],
}

# Common QVD metadata fields (from XML header)
QVD_HEADER_FIELDS = [
    "QvBuildNo", "CreatorDoc", "CreateUtcTime", "SourceCreateUtcTime",
    "StaleUtcTime", "TableName", "NoOfRecords", "NoOfFields",
    "FieldName", "BitOffset", "BitWidth", "Bias", "NumberFormat",
]

print(f"✅ QVD context loaded: {len(QVD_TO_DELTA_TYPE_MAP)} type mappings")
print(f"📋 Target: {target_schema} ({target_layer} layer)")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting
# ══════════════════════════════════════════════════════════════════════

system_prompt = """You are the QVD Extraction Agent (Agent 89) for Hologic's Qlik→Databricks migration.

You specialize in analyzing QVD (QlikView Data) files and converting them to Delta tables.

QVD Format Knowledge:
- Binary columnar format with XML header containing full schema metadata
- Field types: ASCII (STRING), FIX (BIGINT), REAL (DOUBLE), DATE, TIMESTAMP, DUAL (STRING)
- XML header includes: TableName, NoOfRecords, NoOfFields, field definitions, creator info
- QVD files are typically organized in layers: Extract → Transform → Mart

Your responsibilities:
1. SCHEMA EXTRACTION: Parse QVD XML headers to extract table/field definitions
2. TYPE MAPPING: Convert QVD field types to appropriate Delta Lake types
3. DATA PROFILING: Analyze row counts, null rates, cardinality, value distributions
4. DDL GENERATION: Create Delta table DDL with proper types, clustering, audit columns
5. INGESTION CODE: Generate Auto Loader or COPY INTO notebooks for QVD→Delta

Conversion Rules:
- QVD DUAL fields → STRING (preserve both text and numeric representations)
- QVD dates with format "YYYY-MM-DD" → DATE; with time → TIMESTAMP
- QVD FIX with NumberFormat containing decimals → DECIMAL(18,N)
- Always add: etl_load_datetime, etl_source_system='QLIKVIEW', etl_batch_id
- Always use xxhash64(CONCAT_WS('|', business_keys)) for surrogate keys
- Always apply Liquid Clustering on high-cardinality filter columns

QVD Layered Architecture Mapping:
- Extract QVDs (raw source copies) → Bronze Delta tables (1:1)
- Transform QVDs (cleaned/joined) → Silver Delta tables (may consolidate)
- Mart/App QVDs (shaped for UI) → Gold Delta tables (star schema)

Target: {target_schema} ({target_layer} layer)
"""

user_prompt = f"""Request: {request}
QVD Path: {qvd_path or 'Not specified'}
Target Layer: {target_layer}
Target Schema: {target_schema}

Please analyze the QVD artifact(s) and provide the Delta table conversion plan."""

print(f"✅ Prompts formatted")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call
# ══════════════════════════════════════════════════════════════════════

response = call_agent(
    agent_name="89_qvd_extraction",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=4096
)

print(response)

# COMMAND ----------

# DBTITLE 1,STEP 5 - Validate and Persist
# ══════════════════════════════════════════════════════════════════════
# STEP 5: Validate & Persist
# ══════════════════════════════════════════════════════════════════════

assert len(response) > 100, "Response too short"
assert any(kw in response.lower() for kw in ["delta", "table", "qvd", "column", "schema"]), \
    "Response missing expected QVD extraction content"

save_agent_output(
    agent_name="89_qvd_extraction",
    run_id=run_id,
    output_type="qvd_extraction_plan",
    content=response,
    metadata={"qvd_path": qvd_path, "target_layer": target_layer, "target_schema": target_schema}
)

print(f"\n✅ Agent 89 complete — QVD extraction plan saved")
print(f"📋 Run ID: {run_id}")

# COMMAND ----------

