# Databricks notebook source
# DBTITLE 1,Data Modeler Agent
# MAGIC %md
# MAGIC # Agent 37 — Data Modeler
# MAGIC
# MAGIC **Purpose:** Reads the Scope document, analyzes existing facts/dimensions in the catalog, and produces logical + physical data model designs using existing or new tables.
# MAGIC
# MAGIC **Position in Pipeline:** Scope (12) → **Data Modeler (37)** → Lakehouse Architect (15) → Solution Architect (06)
# MAGIC
# MAGIC **Inputs:**
# MAGIC - Scope document (from Agent 12 or direct input)
# MAGIC - Existing catalog metadata (`mde_dev` schemas: gold, platinum, silver, stg_*)
# MAGIC
# MAGIC **Outputs:**
# MAGIC - Logical Data Model (entities, relationships, cardinality, grain)
# MAGIC - Physical Data Model (DDL, SK strategy, clustering, constraints)
# MAGIC - Reuse recommendations (which existing facts/dims to leverage vs. build new)
# MAGIC - Conforming dimension mapping
# MAGIC
# MAGIC **Key Design Principles:**
# MAGIC - Surrogate keys: `xxhash64(CONCAT_WS('|', business_keys))` — NEVER MD5
# MAGIC - Audit columns DIMS: `dl_iscurrent`, `dl_recordstartdateutc`, `dl_recordenddateutc`, `dl_transform_id`, `dl_rowhash`
# MAGIC - Audit columns FACTS: `dl_rowhash`, `dl_creation_date_time`, `dl_last_updated_date_time`
# MAGIC - ⚠️ NEVER use `etl_load_datetime`, `etl_source_system`, `etl_batch_id` — those are BANNED (old incorrect standard)
# MAGIC - Liquid Clustering (not partitioning) for new tables
# MAGIC - Kimball star schema in Gold/Platinum
# MAGIC - Bus matrix compliance
# MAGIC - Conformed dimensions where possible

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Agent parameters and inputs
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Parameters & Input
# Accept requirement from Scope Agent or direct user input
# ══════════════════════════════════════════════════════════════════════════════

dbutils.widgets.text("requirement", "", "Requirement / Scope Document")
dbutils.widgets.text("source_tables", "", "Source tables (comma-separated, optional)")
dbutils.widgets.text("target_layer", "gold", "Target layer (gold/platinum)")

# Get input: either from widget, or chain from Scope Agent
requirement = dbutils.widgets.get("requirement")
source_tables = dbutils.widgets.get("source_tables")
target_layer = dbutils.widgets.get("target_layer")

if not requirement:
    # Try to read from Scope Agent's latest output
    requirement = get_latest_agent_output("scope", "scope_document") or ""
    if requirement:
        print(f"📥 Loaded scope document from Agent 12 ({len(requirement)} chars)")
    else:
        print("⚠️ No requirement provided. Use widget or run Scope Agent (12) first.")

run_id = generate_run_id()
print(f"🏗️ Data Modeler Agent | Run ID: {run_id}")
print(f"   Target layer: {target_layer}")
print(f"   Requirement length: {len(requirement)} chars")

# COMMAND ----------

# DBTITLE 1,Load Hologic canonical DDL standards
# ══════════════════════════════════════════════════════════════════════════════
# CANONICAL HOLOGIC DDL STANDARDS
# Fetched live from production tables — injected into the LLM context so
# every generated model follows the ACTUAL Hologic pattern, not generic conventions.
# ══════════════════════════════════════════════════════════════════════════════

def get_hologic_canonical_standards() -> str:
    """
    Fetch DDL from canonical production Hologic gold tables.
    These are the MANDATORY templates the LLM must follow when designing
    new dim/fact tables.
    """
    canonical_tables = [
        f"{CATALOG}.gold.dim_customeraccount",   # Canonical SCD dimension
        f"{CATALOG}.gold.fact_ap_invoice",       # Canonical transactional fact
    ]
    parts = ["## CANONICAL HOLOGIC DDL (production) — FOLLOW THESE PATTERNS EXACTLY"]
    for tbl in canonical_tables:
        try:
            ddl = spark.sql(f"SHOW CREATE TABLE {tbl}").collect()[0][0]
            tbl_props_idx = ddl.find("TBLPROPERTIES")
            if tbl_props_idx > 0:
                ddl_short = ddl[:tbl_props_idx] + "TBLPROPERTIES (\n  'delta.autoOptimize.autoCompact' = 'true',\n  'delta.autoOptimize.optimizeWrite' = 'true',\n  'delta.parquet.compression.codec' = 'zstd',\n  'delta.enableDeletionVectors' = 'true',\n  'delta.enableRowTracking' = 'true',\n  'delta.checkpointPolicy' = 'v2')"
            else:
                ddl_short = ddl
            parts.append(f"\n### {tbl}\n```sql\n{ddl_short}\n```")
        except Exception as e:
            parts.append(f"\n### {tbl}\n  [Schema read failed: {e}]")
    return "\n".join(parts)

HOLOGIC_CANONICAL_STANDARDS = get_hologic_canonical_standards()
print(f"✅ Canonical Hologic DDL loaded ({len(HOLOGIC_CANONICAL_STANDARDS)} chars)")
print("   Key patterns: PascalCase columns | dl_* audit | CLUSTER BY AUTO | FLOAT amounts | zstd+deletionVectors")

# COMMAND ----------

# DBTITLE 1,Discover existing facts and dimensions from catalog
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Catalog Discovery
# Scan existing Gold/Platinum for facts and dimensions the model can reuse
# ══════════════════════════════════════════════════════════════════════════════

def discover_existing_models() -> dict:
    """Scan catalog for existing fact and dimension tables with metadata."""
    
    # Get all tables in Gold and Platinum layers
    df_tables = spark.sql(f"""
    SELECT 
        table_catalog,
        table_schema,
        table_name,
        CONCAT(table_catalog, '.', table_schema, '.', table_name) AS full_name,
        CASE 
            WHEN table_name LIKE 'fact_%' OR table_name LIKE 'fct_%' THEN 'FACT'
            WHEN table_name LIKE 'dim_%' THEN 'DIMENSION'
            WHEN table_name LIKE 'bridge_%' OR table_name LIKE 'br_%' THEN 'BRIDGE'
            WHEN table_name LIKE 'agg_%' THEN 'AGGREGATE'
            ELSE 'OTHER'
        END AS table_type,
        comment as table_comment
    FROM {CATALOG}.information_schema.tables
    WHERE table_schema IN ('gold', 'platinum', 'silver')
      AND table_type = 'MANAGED'
      -- Exclude dev artifacts: backups, temp tables, test copies
      AND NOT REGEXP_LIKE(table_name, '_(bkp|bk|tmp|temp|test)[0-9]*
    """)
    
    tables = df_tables.collect()
    
    # Get column details for fact/dim tables
    df_columns = spark.sql(f"""
    SELECT 
        CONCAT(table_catalog, '.', table_schema, '.', table_name) AS full_name,
        column_name,
        data_type,
        is_nullable,
        comment as column_comment
    FROM {CATALOG}.information_schema.columns
    WHERE table_schema IN ('gold', 'platinum')
      AND (table_name LIKE 'fact_%' OR table_name LIKE 'fct_%' OR table_name LIKE 'dim_%')
    ORDER BY full_name, ordinal_position
    """)
    
    columns = df_columns.collect()
    
    # Structure the catalog context
    catalog_context = {
        "facts": [t.asDict() for t in tables if t['table_type'] == 'FACT'],
        "dimensions": [t.asDict() for t in tables if t['table_type'] == 'DIMENSION'],
        "bridges": [t.asDict() for t in tables if t['table_type'] == 'BRIDGE'],
        "other": [t.asDict() for t in tables if t['table_type'] == 'OTHER'],
        "column_details": {},
        "total_tables": len(tables)
    }
    
    # Group columns by table
    for col in columns:
        table = col['full_name']
        if table not in catalog_context['column_details']:
            catalog_context['column_details'][table] = []
        catalog_context['column_details'][table].append({
            "name": col['column_name'],
            "type": col['data_type'],
            "nullable": col['is_nullable'],
            "comment": col['column_comment']
        })
    
    return catalog_context


# Also discover source system schemas for lineage
def discover_source_schemas(source_tables_str: str) -> str:
    """Get schema context for the specified source tables."""
    if not source_tables_str:
        return "No source tables specified."
    
    tables = [t.strip() for t in source_tables_str.split(',') if t.strip()]
    context_parts = []
    
    for table in tables[:10]:  # Limit to 10 to stay within token budget
        try:
            parts = table.split('.')
            if len(parts) == 3:
                cat, sch, tbl = parts
            elif len(parts) == 1:
                cat, sch, tbl = CATALOG, 'stg_oracle_ebs', parts[0]  # default
            else:
                continue
            
            cols = spark.sql(f"""
                SELECT column_name, data_type, comment
                FROM {cat}.information_schema.columns
                WHERE table_schema = '{sch}' AND table_name = '{tbl}'
                ORDER BY ordinal_position
            """).collect()
            
            if cols:
                col_list = "\n".join([f"  - {c['column_name']} ({c['data_type']})" + 
                                       (f" -- {c['comment']}" if c['comment'] else "") 
                                       for c in cols])
                context_parts.append(f"### {cat}.{sch}.{tbl}\n{col_list}")
        except:
            context_parts.append(f"### {table}\n  (schema not accessible)")
    
    return "\n\n".join(context_parts) if context_parts else "Source schemas not found."


print("📊 Discovering existing data model...")
catalog_context = discover_existing_models()
print(f"   Found: {len(catalog_context['facts'])} facts, {len(catalog_context['dimensions'])} dimensions, {len(catalog_context['bridges'])} bridges")
print(f"   Total tables scanned: {catalog_context['total_tables']}")

if source_tables:
    print(f"\n📋 Fetching source schemas...")
    source_context = discover_source_schemas(source_tables)
    print(f"   Source context: {len(source_context)} chars")
else:
    source_context = "No specific source tables provided. Model from requirement only.")
      AND NOT REGEXP_LIKE(table_name, '_[0-9]{8}
    """)
    
    tables = df_tables.collect()
    
    # Get column details for fact/dim tables
    df_columns = spark.sql(f"""
    SELECT 
        CONCAT(table_catalog, '.', table_schema, '.', table_name) AS full_name,
        column_name,
        data_type,
        is_nullable,
        comment as column_comment
    FROM {CATALOG}.information_schema.columns
    WHERE table_schema IN ('gold', 'platinum')
      AND (table_name LIKE 'fact_%' OR table_name LIKE 'fct_%' OR table_name LIKE 'dim_%')
    ORDER BY full_name, ordinal_position
    """)
    
    columns = df_columns.collect()
    
    # Structure the catalog context
    catalog_context = {
        "facts": [t.asDict() for t in tables if t['table_type'] == 'FACT'],
        "dimensions": [t.asDict() for t in tables if t['table_type'] == 'DIMENSION'],
        "bridges": [t.asDict() for t in tables if t['table_type'] == 'BRIDGE'],
        "other": [t.asDict() for t in tables if t['table_type'] == 'OTHER'],
        "column_details": {},
        "total_tables": len(tables)
    }
    
    # Group columns by table
    for col in columns:
        table = col['full_name']
        if table not in catalog_context['column_details']:
            catalog_context['column_details'][table] = []
        catalog_context['column_details'][table].append({
            "name": col['column_name'],
            "type": col['data_type'],
            "nullable": col['is_nullable'],
            "comment": col['column_comment']
        })
    
    return catalog_context


# Also discover source system schemas for lineage
def discover_source_schemas(source_tables_str: str) -> str:
    """Get schema context for the specified source tables."""
    if not source_tables_str:
        return "No source tables specified."
    
    tables = [t.strip() for t in source_tables_str.split(',') if t.strip()]
    context_parts = []
    
    for table in tables[:10]:  # Limit to 10 to stay within token budget
        try:
            parts = table.split('.')
            if len(parts) == 3:
                cat, sch, tbl = parts
            elif len(parts) == 1:
                cat, sch, tbl = CATALOG, 'stg_oracle_ebs', parts[0]  # default
            else:
                continue
            
            cols = spark.sql(f"""
                SELECT column_name, data_type, comment
                FROM {cat}.information_schema.columns
                WHERE table_schema = '{sch}' AND table_name = '{tbl}'
                ORDER BY ordinal_position
            """).collect()
            
            if cols:
                col_list = "\n".join([f"  - {c['column_name']} ({c['data_type']})" + 
                                       (f" -- {c['comment']}" if c['comment'] else "") 
                                       for c in cols])
                context_parts.append(f"### {cat}.{sch}.{tbl}\n{col_list}")
        except:
            context_parts.append(f"### {table}\n  (schema not accessible)")
    
    return "\n\n".join(context_parts) if context_parts else "Source schemas not found."


print("📊 Discovering existing data model...")
catalog_context = discover_existing_models()
print(f"   Found: {len(catalog_context['facts'])} facts, {len(catalog_context['dimensions'])} dimensions, {len(catalog_context['bridges'])} bridges")
print(f"   Total tables scanned: {catalog_context['total_tables']}")

if source_tables:
    print(f"\n📋 Fetching source schemas...")
    source_context = discover_source_schemas(source_tables)
    print(f"   Source context: {len(source_context)} chars")
else:
    source_context = "No specific source tables provided. Model from requirement only.")
      AND table_name NOT LIKE '%_tmp%'
      AND table_name NOT LIKE '%_temp%'
    ORDER BY table_schema, table_type, table_name
    """)
    
    tables = df_tables.collect()
    
    # Get column details for fact/dim tables
    df_columns = spark.sql(f"""
    SELECT 
        CONCAT(table_catalog, '.', table_schema, '.', table_name) AS full_name,
        column_name,
        data_type,
        is_nullable,
        comment as column_comment
    FROM {CATALOG}.information_schema.columns
    WHERE table_schema IN ('gold', 'platinum')
      AND (table_name LIKE 'fact_%' OR table_name LIKE 'fct_%' OR table_name LIKE 'dim_%')
    ORDER BY full_name, ordinal_position
    """)
    
    columns = df_columns.collect()
    
    # Structure the catalog context
    catalog_context = {
        "facts": [t.asDict() for t in tables if t['table_type'] == 'FACT'],
        "dimensions": [t.asDict() for t in tables if t['table_type'] == 'DIMENSION'],
        "bridges": [t.asDict() for t in tables if t['table_type'] == 'BRIDGE'],
        "other": [t.asDict() for t in tables if t['table_type'] == 'OTHER'],
        "column_details": {},
        "total_tables": len(tables)
    }
    
    # Group columns by table
    for col in columns:
        table = col['full_name']
        if table not in catalog_context['column_details']:
            catalog_context['column_details'][table] = []
        catalog_context['column_details'][table].append({
            "name": col['column_name'],
            "type": col['data_type'],
            "nullable": col['is_nullable'],
            "comment": col['column_comment']
        })
    
    return catalog_context


# Also discover source system schemas for lineage
def discover_source_schemas(source_tables_str: str) -> str:
    """Get schema context for the specified source tables."""
    if not source_tables_str:
        return "No source tables specified."
    
    tables = [t.strip() for t in source_tables_str.split(',') if t.strip()]
    context_parts = []
    
    for table in tables[:10]:  # Limit to 10 to stay within token budget
        try:
            parts = table.split('.')
            if len(parts) == 3:
                cat, sch, tbl = parts
            elif len(parts) == 1:
                cat, sch, tbl = CATALOG, 'stg_oracle_ebs', parts[0]  # default
            else:
                continue
            
            cols = spark.sql(f"""
                SELECT column_name, data_type, comment
                FROM {cat}.information_schema.columns
                WHERE table_schema = '{sch}' AND table_name = '{tbl}'
                ORDER BY ordinal_position
            """).collect()
            
            if cols:
                col_list = "\n".join([f"  - {c['column_name']} ({c['data_type']})" + 
                                       (f" -- {c['comment']}" if c['comment'] else "") 
                                       for c in cols])
                context_parts.append(f"### {cat}.{sch}.{tbl}\n{col_list}")
        except:
            context_parts.append(f"### {table}\n  (schema not accessible)")
    
    return "\n\n".join(context_parts) if context_parts else "Source schemas not found."


print("📊 Discovering existing data model...")
catalog_context = discover_existing_models()
print(f"   Found: {len(catalog_context['facts'])} facts, {len(catalog_context['dimensions'])} dimensions, {len(catalog_context['bridges'])} bridges")
print(f"   Total tables scanned: {catalog_context['total_tables']}")

if source_tables:
    print(f"\n📋 Fetching source schemas...")
    source_context = discover_source_schemas(source_tables)
    print(f"   Source context: {len(source_context)} chars")
else:
    source_context = "No specific source tables provided. Model from requirement only."

# COMMAND ----------

# DBTITLE 1,Build existing model summary for LLM context
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Build Existing Model Summary
# Format catalog discovery into LLM-digestible context
# ══════════════════════════════════════════════════════════════════════════════

def build_model_context(catalog_ctx: dict) -> str:
    """Format existing model into context string for LLM."""
    parts = []
    
    # Existing Facts
    if catalog_ctx['facts']:
        parts.append("## Existing Fact Tables")
        for f in catalog_ctx['facts']:
            cols = catalog_ctx['column_details'].get(f['full_name'], [])
            col_summary = ", ".join([c['name'] for c in cols[:15]])  # First 15 cols
            comment = f" — {f['table_comment']}" if f.get('table_comment') else ""
            parts.append(f"- **{f['full_name']}**{comment}")
            if cols:
                # Identify keys vs measures
                keys = [c['name'] for c in cols if c['name'].endswith('_sk') or c['name'].endswith('_key') or c['name'].endswith('_id')]
                measures = [c['name'] for c in cols if c['type'] in ('decimal', 'double', 'float', 'int', 'bigint') 
                           and not c['name'].endswith(('_sk', '_key', '_id'))]
                parts.append(f"  Keys: {', '.join(keys[:10])}")
                if measures:
                    parts.append(f"  Measures: {', '.join(measures[:10])}")
    
    # Existing Dimensions
    if catalog_ctx['dimensions']:
        parts.append("\n## Existing Dimension Tables")
        for d in catalog_ctx['dimensions']:
            cols = catalog_ctx['column_details'].get(d['full_name'], [])
            comment = f" — {d['table_comment']}" if d.get('table_comment') else ""
            parts.append(f"- **{d['full_name']}**{comment}")
            if cols:
                attrs = [c['name'] for c in cols if not c['name'].endswith(('_sk', '_key', 'etl_'))]
                parts.append(f"  Attributes: {', '.join(attrs[:12])}")
    
    # Existing Bridges
    if catalog_ctx['bridges']:
        parts.append("\n## Existing Bridge Tables")
        for b in catalog_ctx['bridges']:
            parts.append(f"- **{b['full_name']}**")
    
    return "\n".join(parts) if parts else "No existing fact/dimension tables found in Gold/Platinum."


existing_model_context = build_model_context(catalog_context)
print(f"📐 Model context prepared: {len(existing_model_context)} chars")
print(existing_model_context[:500] + "..." if len(existing_model_context) > 500 else existing_model_context)

# COMMAND ----------

# DBTITLE 1,LLM call: Generate logical and physical data model
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: LLM-Powered Data Modeling
# Generate logical + physical model with reuse recommendations
# ══════════════════════════════════════════════════════════════════════════════

DATA_MODELER_PROMPT = """You are a Senior Data Modeler for Hologic's Databricks Lakehouse.

You design Kimball star schema models (facts + dimensions) for the Gold and Platinum layers.

## Your Task
Given a requirement/scope document and the existing catalog context, produce:

### 1. REUSE ANALYSIS
- Which existing dimensions can be reused as-is (conformed dimensions)?
- Which existing facts/dims need extension (add columns)?
- What is genuinely NEW and must be built from scratch?

### 2. LOGICAL DATA MODEL
For each entity:
- Entity name (fact_xxx or dim_xxx)
- Grain (one row per...)
- Business keys
- Relationships (which dims hang off which facts, cardinality)
- Slowly Changing Dimension type (if applicable: SCD Type 1 or 2)

### 3. PHYSICAL DATA MODEL (DDL)
For each table:
- Full CREATE TABLE DDL in Databricks SQL
- All column definitions with data types and comments
- Surrogate key: `xxhash64(CONCAT_WS('|', business_key_cols)) AS table_sk`
- Audit columns — FACTS: dl_rowhash STRING, dl_creation_date_time TIMESTAMP, dl_last_updated_date_time TIMESTAMP
- Audit columns — DIMS: dl_iscurrent BOOLEAN, dl_recordstartdateutc TIMESTAMP, dl_recordenddateutc TIMESTAMP, dl_transform_id INT, dl_rowhash STRING
- ⚠️ NEVER use etl_load_datetime, etl_source_system, etl_batch_id — those are BANNED (old incorrect standard)
- TBLPROPERTIES for Liquid Clustering: CLUSTER BY AUTO (NEVER explicit columns)
- Table and column COMMENTs

### 4. BUS MATRIX
A cross-reference showing which dimensions apply to which facts.

### 5. DATA LINEAGE NOTES
Which source tables feed each target (Bronze → Silver → Gold/Platinum flow).

## Hologic Standards (MANDATORY — derived from production DDL, not invented conventions)
- Catalog: mde_dev (DEV) | mde_uat (UAT) | mde_prd (PRD)
- Gold: `gold` (Kimball star schema, analytics-ready) | Platinum: `platinum` (curated BI aggregates)
- Table names: snake_case with fact_/dim_/bridge_/agg_ prefix
- Column names: **PascalCase — NEVER snake_case**. Examples from production: CustomerAccount_SK, Invoice_ID, AccountingDate, PaymentStatusFlag, InvoiceCurrencyCode, GLDate, POHeader_ID
- Surrogate keys: `xxhash64(CONCAT_WS('|', business_key_cols)) AS EntityName_SK STRING COLLATE UTF8_BINARY` — NEVER MD5
- Audit columns — FACTS: `dl_rowhash STRING COLLATE UTF8_BINARY`, `dl_creation_date_time TIMESTAMP`, `dl_last_updated_date_time TIMESTAMP`
- Audit columns — DIMS: `dl_iscurrent BOOLEAN`, `dl_recordstartdateutc TIMESTAMP`, `dl_recordenddateutc TIMESTAMP`, `dl_transform_id INT`, `dl_rowhash STRING COLLATE UTF8_BINARY`
- Clustering: `CLUSTER BY AUTO` only — NEVER `CLUSTER BY (col1, col2)` with explicit columns
- PRIMARY KEY: `CONSTRAINT <table>_pk PRIMARY KEY (<GrainSK>)` on every table
- Data types: FLOAT for amounts/quantities, BIGINT for IDs, STRING for codes/flags, BOOLEAN for is*/has* flags, TIMESTAMP for dates
- Delta format (managed). TBLPROPERTIES: delta.autoOptimize.autoCompact=true, delta.autoOptimize.optimizeWrite=true, delta.parquet.compression.codec=zstd, delta.enableDeletionVectors=true, delta.enableRowTracking=true, delta.checkpointPolicy=v2

## NOTEBOOK IMPLEMENTATION GUIDANCE
When specifying how the physical model should be implemented as notebooks, reference these patterns:

### Dimension Notebooks (Gold):
- Notebook name = target table name (e.g. `dim_customer`)
- Silver staging view: `v_dim_<name>` with TBLPROPERTIES (config.sk_column_name, config.nk_column_names, config.cluster_by, config.dim_type)
- SK is NOT in the staging view SELECT — DimensionProcessor auto-generates it from nk_column_names
- Uses DimensionProcessor class + LakeOrchestrator.exit_with_status()
- Widgets: deltaSchemaName, deltaTableName, storageAccountEndpoint, catalogName, transformId

### Fact Notebooks (Gold):
- Notebook name = target table name (e.g. `fact_salesorder`)
- Silver staging view: `v_fact_<name>` with TBLPROPERTIES (config.sk_column_name, config.nk_column_names, config.cluster_by, config.fact_type)
- SK IS explicitly calculated in the staging view: `md5(concat_ws('|', NKs)) AS <Name>_SK`
- Uses FactProcessor class + LakeOrchestrator.exit_with_status()
- MUST have loadType widget (I=Incremental, F=Full)
- Incremental: date filtering based on MAX(dl_recordstartdateutc) from target

### Silver Views:
- Naming: v_mst_<source>_<table> (master) or v_trn_<source>_<table> (transaction)
- 1:1 with Bronze (stg_*), always include `AND dl_iscurrent = 'Y'`
- No multi-table joins, no application-specific logic

### Platinum Views (ONLY for custom aggregations):
- ⚠️ v_pbi_* views are AUTO-GENERATED by DimensionProcessor/FactProcessor during .process()
- Developers do NOT create Platinum notebooks for standard dims/facts — the processor handles it
- ViewProcessor + Platinum notebooks are ONLY for custom aggregations, cross-domain joins, or dashboard-specific logic beyond what the auto-generated v_pbi_ provides
- Uses ViewProcessor class, named v_pbi_*

## Output Format
Respond in structured markdown with clear sections for each of the 5 deliverables above.
Include complete DDL statements that are ready to run in Databricks SQL.
Also include a "Notebook Implementation" section specifying the correct notebook structure for each entity.
"""

# Build the user prompt with all context
user_prompt = f"""## Canonical Hologic DDL — FOLLOW EXACTLY (from production)
{HOLOGIC_CANONICAL_STANDARDS}

## Requirement / Scope Document
{requirement}

## Source Tables
{source_context}

## Existing Data Model in Catalog
{existing_model_context}

## Target Layer
{target_layer}

---

Design the data model. Follow ALL Hologic standards from the canonical DDL above.
Maximize reuse of existing dimensions. Produce the full Logical Model, Physical DDL, Bus Matrix, and Lineage Notes.
Every column must be PascalCase. Every table must use CLUSTER BY AUTO and the standard TBLPROPERTIES block."""

print(f"🧠 Calling LLM for data model design...")
print(f"   Prompt size: {len(user_prompt)} chars")

model_output = call_agent(
    "data_engineer",  # Uses LLM_CRITICAL for complex design work
    DATA_MODELER_PROMPT,
    user_prompt,
    temperature=0.2,
    max_tokens=8000
)

print(f"\n✅ Data model generated: {len(model_output)} chars")
print("=" * 60)
print(model_output[:2000])
if len(model_output) > 2000:
    print(f"\n... [{len(model_output) - 2000} more chars]")

# COMMAND ----------

# DBTITLE 1,Validate model output and save
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Validate & Persist
# Check model meets standards, then save to Delta
# ══════════════════════════════════════════════════════════════════════════════

# --- Validation checks ---
validation_results = []

# Check 1: xxHash64 (not MD5)
if 'md5(' in model_output.lower():
    validation_results.append("❌ FAIL: Model uses MD5 instead of xxHash64")
else:
    validation_results.append("✅ PASS: No MD5 detected (xxHash64 expected)")

# Check 2: Correct dl_* audit columns present (NEVER etl_*)
if 'dl_rowhash' in model_output or 'dl_iscurrent' in model_output or 'dl_creation_date_time' in model_output:
    validation_results.append("✅ PASS: Correct dl_* audit columns found")
else:
    validation_results.append("⚠️ WARN: dl_* audit columns not found in DDL (expected: dl_rowhash, dl_iscurrent, dl_creation_date_time)")

# Check 2b: REJECT if banned etl_* columns present
if 'etl_load_datetime' in model_output or 'etl_source_system' in model_output or 'etl_batch_id' in model_output:
    validation_results.append("❌ FAIL: BANNED etl_* columns detected (etl_load_datetime/etl_source_system/etl_batch_id) — must use dl_* instead")
else:
    validation_results.append("✅ PASS: No banned etl_* columns")

# Check 3: Liquid Clustering
if 'CLUSTER BY' in model_output.upper():
    validation_results.append("✅ PASS: Liquid Clustering specified")
else:
    validation_results.append("⚠️ WARN: No CLUSTER BY found — add Liquid Clustering")

# Check 4: PARTITION BY should NOT be present
if 'PARTITION BY' in model_output.upper():
    validation_results.append("❌ FAIL: Uses PARTITION BY instead of Liquid Clustering")
else:
    validation_results.append("✅ PASS: No legacy PARTITION BY")

# Check 5: Naming convention
if 'fact_' in model_output.lower() or 'dim_' in model_output.lower():
    validation_results.append("✅ PASS: Uses fact_/dim_ naming convention")
else:
    validation_results.append("⚠️ WARN: No fact_/dim_ prefix detected")

# Check 6: Comments present
if 'COMMENT' in model_output.upper():
    validation_results.append("✅ PASS: Table/column COMMENTs included")
else:
    validation_results.append("⚠️ WARN: No COMMENTs found — add business descriptions")

print("\n📋 Model Validation Results")
print("=" * 60)
for v in validation_results:
    print(f"  {v}")

fails = sum(1 for v in validation_results if '❌' in v)
warns = sum(1 for v in validation_results if '⚠️' in v)
print(f"\n  Summary: {len(validation_results) - fails - warns} passed, {warns} warnings, {fails} failures")

# --- Save outputs ---
metadata = {
    "target_layer": target_layer,
    "source_tables": source_tables,
    "existing_facts_reused": len([f for f in catalog_context['facts'] if f['full_name'].split('.')[-1] in model_output.lower()]),
    "existing_dims_reused": len([d for d in catalog_context['dimensions'] if d['full_name'].split('.')[-1] in model_output.lower()]),
    "validation_fails": fails,
    "validation_warns": warns
}

save_agent_output("data_modeler", run_id, "data_model", model_output, metadata)

# Also save just the DDL portion separately for the Data Engineer agent to consume
import re
ddl_blocks = re.findall(r'```sql(.*?)```', model_output, re.DOTALL)
if ddl_blocks:
    combined_ddl = "\n\n".join(ddl_blocks)
    save_agent_output("data_modeler", run_id, "physical_ddl", combined_ddl, 
                     {"ddl_statements": len(ddl_blocks)})
    print(f"\n💾 Saved {len(ddl_blocks)} DDL statements as separate output")

print(f"\n✅ Data Modeler Agent Complete | Run ID: {run_id}")
print(f"   Model saved to: {CATALOG}.{SCHEMA}.agent_outputs")
print(f"   Next step: Agent 15 (Lakehouse Architect) or Agent 06 (Solution Architect)")