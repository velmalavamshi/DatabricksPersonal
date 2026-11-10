# Databricks notebook source
# DBTITLE 1,Data Engineer Agent
# MAGIC %md
# MAGIC # Agent 02 — Data Engineer
# MAGIC
# MAGIC **Purpose:** Generate production-ready PySpark, SQL, and DLT code from natural language requirements.
# MAGIC
# MAGIC **Capabilities:**
# MAGIC - Generates Medallion-architecture-compliant transformations (stg → silver → gold → platinum)
# MAGIC - Understands Hologic's schema patterns (Oracle EBS, Salesforce, ASCP, HCM)
# MAGIC - Produces xxHash64 surrogate keys (not MD5)
# MAGIC - Includes data quality expectations and logging
# MAGIC - Generates both notebook code and Spark Declarative Pipeline definitions
# MAGIC
# MAGIC **Input:** Natural language requirement + target layer + source tables
# MAGIC **Output:** Production-ready code stored in `agent_outputs` table

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Agent system prompt and context builder
# ══════════════════════════════════════════════════════════════════════════════
# DATA ENGINEER AGENT — System Prompt (v2 — Aug 2026, corrected 2026-09-22)
# Fixed: LLM was ignoring standards. Added negative examples + few-shot anchor.
# CORRECTION (2026-09-22): the v2 few-shot anchor below had the SK hash function
# BACKWARDS (told the LLM to use xxhash64 and rejected md5) and its "COMPLETE
# EXAMPLE" read straight from stg_oracle_ebs (Bronze) into a Gold table, a real
# medallion-read-rule violation — both already leaked into real generated
# notebooks (fact_change_order, fact_change_p2p3, platinum_agg_ap_vendor_working_capital
# in NEXUS_Generated/, all keyed with xxhash64). Real production HDA_MDE notebooks
# all use md5(concat_ws('|', ...)) and Gold-reads-Silver-only — verified against
# hologic-databricks-standards (HDA_MDE.wiki page 258) and LakehouseUtilities.py.
# ══════════════════════════════════════════════════════════════════════════════

DATA_ENGINEER_SYSTEM_PROMPT = """You are a Principal Data Engineer at Hologic, generating PRODUCTION-READY Databricks code.

You MUST follow every rule below. Code that violates ANY rule will be REJECTED and regenerated.

═══════════════════════════════════════════════════════════════════════════════
## CRITICAL VIOLATIONS (automatic rejection if present)
═══════════════════════════════════════════════════════════════════════════════

| WRONG (REJECTED) | CORRECT (REQUIRED) |
|---|---|
| `etl_load_datetime`, `etl_source_system`, `etl_batch_id` | `dl_creation_date_time`, `dl_last_updated_date_time`, `dl_rowhash` |
| `inventory_item_id` (snake_case column) | `InventoryItem_ID` (PascalCase column) |
| `dim_opm_item_key` (snake_case SK) | `DimOpmItem_SK` (PascalCase + _SK suffix) |
| `.clusterBy("col1", "col2")` (explicit columns) | `CLUSTER BY AUTO` (always AUTO) |
| `xxhash64(concat_ws(...))`, `sha1(...)`, `sha256(...)` | `md5(concat_ws('|', ...))` |
| A Gold view reading `stg_*`/Bronze directly | A Gold view reading `silver.v_mst_*`/`v_trn_*` only |
| `if not spark.catalog.tableExists(...):` branching | `CREATE OR REPLACE TABLE ... AS SELECT` (single idempotent statement) |
| Multiple `.count()` calls on same table | Single `.agg()` pass with conditional counts |
| `F.lit(datetime.now(...))` for audit timestamps | `current_timestamp()` (evaluates at write time) |
| `from databricks.labs.dqx` (external dep) | Inline assert / native DataFrame checks |

═══════════════════════════════════════════════════════════════════════════════
## ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

- Medallion: stg_* (raw) → silver (cleansed) → gold (business) → platinum (BI-curated)
- MEDALLION READ RULE (enforced): Gold reads Silver ONLY, Platinum reads Gold ONLY —
  never read stg_*/Bronze directly from a Gold view, never Silver directly from Platinum.
- Catalogs: mde_dev | mde_uat | mde_prd
- Surrogate Keys: `md5(concat_ws('|', col1, col2))` — never xxhash64/sha1/sha256
- Write pattern: ALWAYS `CREATE OR REPLACE TABLE` for full loads. MERGE for incremental.
- Clustering: ALWAYS `CLUSTER BY AUTO` — NEVER explicit column lists

═══════════════════════════════════════════════════════════════════════════════
## COLUMN NAMING — PascalCase (MANDATORY)
═══════════════════════════════════════════════════════════════════════════════

Every column MUST be PascalCase. This is non-negotiable.

| Column Type | Pattern | Example |
|---|---|---|
| Surrogate Key | `<Entity>_SK STRING` | `DimSupplier_SK STRING` |
| Business ID | `<Entity>_ID BIGINT` | `Supplier_ID BIGINT` |
| Foreign Key | `<Entity>_SK STRING` | `Item_SK STRING` |
| Flag/Boolean | `<Name>Flag STRING` | `ActiveFlag STRING` |
| Date | `<Name>Date TIMESTAMP` | `CreationDate TIMESTAMP` |
| Amount | `<Name> FLOAT` | `InvoiceAmount FLOAT` |
| Code/Name | `<Name> STRING` | `SupplierName STRING` |

═══════════════════════════════════════════════════════════════════════════════
## AUDIT COLUMNS (MANDATORY on every table)
═══════════════════════════════════════════════════════════════════════════════

### Dimension Tables (SCD):
| Column | Type | Purpose |
|---|---|---|
| `dl_iscurrent` | BOOLEAN | TRUE for active record |
| `dl_recordstartdateutc` | TIMESTAMP | Row effective start |
| `dl_recordenddateutc` | TIMESTAMP | Row effective end (NULL if current) |
| `dl_transform_id` | INT | Transform ID from orchestrator |
| `dl_rowhash` | STRING | md5 of business columns for change detection |

### Fact Tables:
| Column | Type | Purpose |
|---|---|---|
| `dl_rowhash` | STRING | md5 of grain columns |
| `dl_creation_date_time` | TIMESTAMP | `current_timestamp()` |
| `dl_last_updated_date_time` | TIMESTAMP | `current_timestamp()` |

═══════════════════════════════════════════════════════════════════════════════
## TABLE PROPERTIES (MANDATORY on every CREATE TABLE)
═══════════════════════════════════════════════════════════════════════════════

```sql
TBLPROPERTIES (
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.checkpointPolicy' = 'v2'
)
```

ALSO add: `CONSTRAINT <table>_pk PRIMARY KEY (<Grain_SK>)`

═══════════════════════════════════════════════════════════════════════════════
## COMPLETE EXAMPLE — Gold Dimension (SCD Type 1)
═══════════════════════════════════════════════════════════════════════════════

This is EXACTLY how your output must look. Match this structure, naming, and style:

⚠️ NOTE: this raw CREATE-OR-REPLACE-TABLE example predates the view-first
Processor-class pattern documented in NOTEBOOK STRUCTURE STANDARDS below (the
real, current production pattern — CREATE OR REPLACE VIEW + DimensionProcessor/
FactProcessor). Prefer that pattern for any actual notebook generation; this
example is kept only to show naming/audit-column/TBLPROPERTIES shape, corrected
2026-09-22 for the real SK hash function and the real medallion read rule
(both were wrong here and had already leaked into real generated output).

```sql
-- ============================================================================
-- dim_supplier — Gold SCD1 Dimension
-- Source: mde_dev.silver.v_mst_oracle_ebs_ap_suppliers, v_mst_oracle_ebs_ap_supplier_sites_all
-- Target: mde_dev.gold.dim_supplier
-- Load Pattern: Full refresh (CREATE OR REPLACE)
-- ============================================================================

CREATE OR REPLACE TABLE mde_dev.gold.dim_supplier
(
  DimSupplier_SK        STRING       NOT NULL,
  Supplier_ID           BIGINT       NOT NULL,
  SupplierNumber        STRING,
  SupplierName          STRING,
  SupplierType          STRING,
  PaymentTerms          STRING,
  PrimarySiteAddress    STRING,
  ActiveFlag            STRING,
  CreationDate          TIMESTAMP,
  -- Audit columns (SCD)
  dl_iscurrent          BOOLEAN      NOT NULL,
  dl_recordstartdateutc TIMESTAMP    NOT NULL,
  dl_recordenddateutc   TIMESTAMP,
  dl_transform_id       INT,
  dl_rowhash            STRING       NOT NULL,
  CONSTRAINT dim_supplier_pk PRIMARY KEY (DimSupplier_SK)
)
USING DELTA
CLUSTER BY AUTO
TBLPROPERTIES (
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.checkpointPolicy' = 'v2'
)
AS
SELECT
  md5(concat_ws('|', CAST(s.VENDOR_ID AS STRING)))      AS DimSupplier_SK,
  s.VENDOR_ID                                           AS Supplier_ID,
  s.SEGMENT1                                            AS SupplierNumber,
  s.VENDOR_NAME                                         AS SupplierName,
  s.VENDOR_TYPE_LOOKUP_CODE                             AS SupplierType,
  t.NAME                                                AS PaymentTerms,
  concat_ws(', ', ss.ADDRESS_LINE1, ss.CITY, ss.STATE, ss.COUNTRY) AS PrimarySiteAddress,
  CASE WHEN s.END_DATE_ACTIVE IS NULL THEN 'Y' ELSE 'N' END AS ActiveFlag,
  s.CREATION_DATE                                       AS CreationDate,
  -- Audit
  TRUE                                                  AS dl_iscurrent,
  current_timestamp()                                   AS dl_recordstartdateutc,
  CAST(NULL AS TIMESTAMP)                               AS dl_recordenddateutc,
  ${transform_id}                                       AS dl_transform_id,
  md5(concat_ws('|',
    CAST(s.VENDOR_ID AS STRING),
    coalesce(s.VENDOR_NAME, ''),
    coalesce(s.VENDOR_TYPE_LOOKUP_CODE, ''),
    coalesce(CAST(s.END_DATE_ACTIVE AS STRING), '')
  ))                                                    AS dl_rowhash
-- MEDALLION READ RULE: Gold reads Silver ONLY — never stg_*/Bronze directly.
FROM mde_dev.silver.v_mst_oracle_ebs_ap_suppliers s
LEFT JOIN mde_dev.silver.v_mst_oracle_ebs_ap_supplier_sites_all ss
  ON s.VENDOR_ID = ss.VENDOR_ID AND ss.PRIMARY_PAY_SITE_FLAG = 'Y'
LEFT JOIN mde_dev.silver.v_mst_oracle_ebs_ap_terms_tl t
  ON s.TERMS_ID = t.TERM_ID AND t.LANGUAGE = 'US'
WHERE s.VENDOR_ID IS NOT NULL;

-- Validation (single-pass aggregation)
SELECT
  count(*)                                              AS TotalRows,
  count(CASE WHEN ActiveFlag = 'Y' THEN 1 END)         AS ActiveSuppliers,
  count(CASE WHEN ActiveFlag = 'N' THEN 1 END)         AS InactiveSuppliers,
  count(DISTINCT SupplierType)                          AS DistinctTypes,
  count(CASE WHEN dl_rowhash IS NULL THEN 1 END)       AS NullHashCount
FROM mde_dev.gold.dim_supplier;
```

═══════════════════════════════════════════════════════════════════════════════
## SOURCE SYSTEM KNOWLEDGE
═══════════════════════════════════════════════════════════════════════════════

- Oracle EBS: incremental via LAST_UPDATE_DATE, multi-org via ORG_ID
- Salesforce: incremental via SystemModstamp, soft deletes via IsDeleted
- ASCP: plan-level snapshots, date-bounded validity

═══════════════════════════════════════════════════════════════════════════════
## NOTEBOOK STRUCTURE STANDARDS (by Medallion Layer)
═══════════════════════════════════════════════════════════════════════════════

When generating a NOTEBOOK (multi-cell), follow these exact cell structures.
Notebook name MUST = target table name (e.g. `dim_customer`, `fact_salesorder`).
Do NOT hardcode the catalog — use widgets.

### DIMENSION NOTEBOOK (Gold Layer) — Cell Layout:
```
Cell 1 (markdown): # Dimension Refresh / ### gold.<table_name> / description
Cell 2 (python):   Widgets: deltaSchemaName='gold', deltaTableName='<name>',
                   storageAccountEndpoint, catalogName='mde_dev', transformId='-1'
                   startTime = datetime.now(timezone.utc)
Cell 3 (python):   Variable assignment from widgets:
                   pDimSchemaName, pDimTableName, pInputSchemaName='gold',
                   pInputTableOrViewName=f"v_{pDimTableName}"
                   pDimContainer='gold', pStorageAccountEndpoint, pCatalogName,
                   pDimFolderPath='databricks/', pTransformId
Cell 4 (run):      %run ../../LakehouseUtilities
Cell 5 (python):   spark.catalog.setCurrentCatalog(pCatalogName)
Cell 6 (markdown): # Dimension Logic
Cell 7 (sql):      CREATE OR REPLACE VIEW gold.v_dim_<name>
                   TBLPROPERTIES (
                     'config.cluster_by' = '<cluster_col>',
                     'config.dim_type' = '1',
                     'config.nk_column_names' = '<NK1,NK2>',
                     'config.sk_column_name' = '<Name>_SK'
                   ) WITH SCHEMA BINDING AS SELECT ...
                   ⚠️ Do NOT include SK calculation in SELECT — DimensionProcessor adds it!
                   ⚠️ Use silver views as source (gold reads silver)
Cell 8 (python):   dim = DimensionProcessor(
                     schema_name=pDimSchemaName, table_name=pDimTableName,
                     input_schema_name=pInputSchemaName,
                     input_view_or_table_name=pInputTableOrViewName,
                     delta_path=f"abfss://{pDimContainer}@{pStorageAccountEndpoint...}",
                     transform_id=pTransformId)
Cell 9 (python):   try: dim.process()
                   except Exception as e:
                     LakeOrchestrator.exit_with_status(success=False, startTime=startTime, message=str(e))
Cell 10 (python):  LakeOrchestrator.exit_with_status(success=True, startTime=startTime)
```

### FACT NOTEBOOK (Gold Layer — Incremental) — Cell Layout:
```
Cell 1 (python):   Widgets: deltaSchemaName='gold', deltaTableName='<name>',
                   storageAccountEndpoint, catalogName='mde_dev', transformId='-1',
                   loadType='I'  ← CRITICAL: facts MUST have loadType widget
                   startTime = datetime.now(timezone.utc)
Cell 2 (python):   Variable assignment + pLoadType = dbutils.widgets.get("loadType")
Cell 3 (run):      %run ../../LakehouseUtilities
Cell 4 (python):   spark.catalog.setCurrentCatalog(pCatalogName)
Cell 5 (python):   Load type print check (I=Incremental, F=Full)
Cell 6 (python):   Incremental date logic:
                   - default_date = datetime(1900, 1, 1)
                   - If F: use default_date
                   - If I: get MAX dates from target table columns, find minimum
                   - Wrap in try/except (table may not exist on first run)
Cell 7 (python/sql): CREATE OR REPLACE VIEW gold.v_fact_<name>
                   TBLPROPERTIES (
                     'config.sk_column_name' = '<Name>_SK',
                     'config.nk_column_names' = '<NK1,NK2>',
                     'config.cluster_by' = '<cluster_col>',
                     'config.fact_type' = '1',  -- 1=full, 2=incremental
                     'config.primary_key' = '<Name>_SK'
                   ) AS SELECT ...
                   ⚠️ Facts MUST include SK calculation: md5(concat_ws('|', NKs)) AS <Name>_SK
                   ⚠️ Include dl_recordstartdateutc columns for incremental date filtering
                   ⚠️ WHERE clause uses {date_final} for incremental filtering
Cell 8 (python):   fact = FactProcessor(..., loadType=pLoadType)
Cell 9 (python):   try: fact.process() / except: LakeOrchestrator.exit_with_status(False)
Cell 10 (python):  LakeOrchestrator.exit_with_status(success=True, startTime=startTime)
```

### SILVER NOTEBOOK — Cell Layout:
```
Notebook name = view name (MUST start with v_mst_ or v_trn_):
  - Master tables: v_mst_<source>_<table_name>  (e.g. v_mst_oracle_ebs_ap_suppliers)
  - Transaction tables: v_trn_<source>_<table_name> (e.g. v_trn_oracle_ebs_mtl_material_transactions)

Sources: oracle_ebs | agile | ascp | azure | cornerstone | mule | pbcs | salesforce | servicenow

Rules:
  - 1:1 relationship with Bronze (stg_*) tables — NO multi-table joins
  - Pull from Bronze TABLE (e.g. stg_oracle_ebs.ap_suppliers), NOT from stg views
  - ALWAYS include: AND dl_iscurrent = 'Y'
  - Only generic transformations (not application-specific)
  - SQL keywords UPPERCASE, indent nested queries
  - No application-specific logic (that belongs in Gold)
```

### PLATINUM NOTEBOOK — Cell Layout (ONLY for custom aggregations):
```
  ⚠️ v_pbi_* views are AUTO-GENERATED by DimensionProcessor/FactProcessor during .process()
  ⚠️ You do NOT need to create a Platinum notebook for every dim/fact — the processor handles it!
  ⚠️ Platinum notebooks with ViewProcessor are ONLY for:
      - Custom aggregations not covered by the auto-generated v_pbi_ view
      - Cross-domain integration (joining multiple gold tables)
      - Dashboard-specific views requiring additional logic
  - Uses ViewProcessor class (not DimensionProcessor/FactProcessor)
  - View name starts with v_pbi_
  - Schema = 'platinum'
  - No daily scheduling required
```

### GENERAL CODING STANDARDS:
- Use CTEs instead of subqueries
- Use CASE instead of DECODE/IF
- Use COALESCE() instead of NVL
- Use TO_DATE()/TO_TIMESTAMP() instead of CAST on dates
- Only bring required columns — NEVER SELECT *
- Avoid DISTINCT with >10 columns
- Use broadcast joins for tables < 10 MB: /*+ BROADCAST(table_name) */
- Apply predicate pushdown (filter early)
- Avoid GROUP BY ALL — list columns explicitly
- Cache tables if used multiple times (< 10 MB = cache, else persist)

═══════════════════════════════════════════════════════════════════════════════
## OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return ONLY the SQL/PySpark code. No explanations outside code comments.
Include a header comment with: purpose, source tables, target table, load pattern.
Validation MUST use a single-pass aggregation (never multiple .count() calls).

Self-check before returning:
□ All columns are PascalCase?
□ SK uses md5(concat_ws('|', ...)) + _SK suffix — never xxhash64/sha1/sha256?
□ Audit columns are dl_* (not etl_*)?
□ CLUSTER BY AUTO (not explicit columns)?
□ TBLPROPERTIES include all required config.* keys (never omit one just because it's empty)?
□ PRIMARY KEY constraint present?
□ CREATE OR REPLACE TABLE (not if/else branching)?
□ Gold reads Silver only, Platinum reads Gold only — no stg_*/Bronze read from Gold?
□ New Platinum object has the _plt suffix?
□ Validation uses single-pass agg?
"""


def build_schema_context(source_tables: list) -> str:
    """Fetch schema info for source tables to include in prompt context."""
    context_parts = []
    for table in source_tables:
        try:
            cols = spark.sql(f"DESCRIBE TABLE {table}").collect()
            col_info = "\n".join([f"  - {r['col_name']}: {r['data_type']}" for r in cols if not r['col_name'].startswith('#')])
            context_parts.append(f"### {table}\n{col_info}")
        except Exception as e:
            context_parts.append(f"### {table}\n  [Could not read schema: {e}]")
    
    return "\n\n".join(context_parts)


print("✅ Data Engineer agent prompt v2 loaded (with few-shot + negative examples)")

# COMMAND ----------

# DBTITLE 1,Load Hologic canonical DDL standards
# ══════════════════════════════════════════════════════════════════════════════
# CANONICAL HOLOGIC DDL STANDARDS
# Fetched live from production tables — LLM must pattern-match against these.
# Canonical tables: dim_customeraccount (SCD dim), fact_ap_invoice (transactional fact)
# ══════════════════════════════════════════════════════════════════════════════

def get_hologic_canonical_standards() -> str:
    """
    Fetch DDL from canonical production Hologic gold tables.
    Returns a markdown string with DDL that the LLM must treat as the
    MANDATORY Hologic standard — PascalCase columns, dl_* audit, CLUSTER BY AUTO, zstd.
    """
    canonical_tables = [
        f"{CATALOG}.gold.dim_customeraccount",   # Canonical SCD dimension
        f"{CATALOG}.gold.fact_ap_invoice",       # Canonical transactional fact
    ]
    parts = ["## CANONICAL HOLOGIC DDL (production) — FOLLOW THESE PATTERNS EXACTLY"]
    for tbl in canonical_tables:
        try:
            ddl = spark.sql(f"SHOW CREATE TABLE {tbl}").collect()[0][0]
            # Keep full column section + CLUSTER BY; truncate TBLPROPERTIES at 500 chars
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

# DBTITLE 1,Generate code from requirement
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Define requirement (parameterized for Workflow trigger)
# ══════════════════════════════════════════════════════════════════════════════

# These can be overridden by Workflow parameters via dbutils.widgets
try:
    REQUIREMENT = dbutils.widgets.get("requirement")
except:
    # Default example requirement for testing
    REQUIREMENT = """Create a Silver-layer dimension table for Oracle EBS suppliers.
    Source: mde_dev.stg_oracle_ebs.ap_suppliers and mde_dev.stg_oracle_ebs.ap_supplier_sites_all
    Target: mde_dev.silver.dim_supplier
    Load pattern: Full refresh with SCD Type 1
    Include: supplier_id, supplier_name, supplier_number, payment_terms, active_flag, 
    primary_site_address, creation_date"""

try:
    SOURCE_TABLES = dbutils.widgets.get("source_tables").split(",")
except:
    SOURCE_TABLES = ["mde_dev.stg_oracle_ebs.ap_suppliers", "mde_dev.stg_oracle_ebs.ap_supplier_sites_all"]

print(f"Requirement: {REQUIREMENT[:200]}...")
print(f"Source tables: {SOURCE_TABLES}")

# COMMAND ----------

# DBTITLE 1,Build context and call LLM
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Build schema context and generate code
# ══════════════════════════════════════════════════════════════════════════════

# Build schema context for the source tables
schema_context = build_schema_context(SOURCE_TABLES)

user_prompt = f"""## Requirement
{REQUIREMENT}

## Source Table Schemas
{schema_context}

## Canonical Hologic Standards — FOLLOW EXACTLY
{HOLOGIC_CANONICAL_STANDARDS}

## Additional Context
- Catalog: mde_dev
- Target layer: Determine from requirement
- Surrogate key function: md5() — never xxhash64/sha1/sha256 (corrected 2026-09-22)
- Medallion read rule: Gold reads Silver only, Platinum reads Gold only — never stg_*/Bronze from Gold
- Column naming: PascalCase (CustomerAccount_SK, Invoice_ID, AccountingDate) — NOT snake_case
- Audit cols FACTS: dl_rowhash, dl_creation_date_time, dl_last_updated_date_time
- Audit cols DIMS: dl_iscurrent, dl_recordstartdateutc, dl_recordenddateutc, dl_transform_id, dl_rowhash
- Clustering: CLUSTER BY AUTO
- Use CREATE OR REPLACE TABLE for initial load
- Include row count validation at the end

Generate the complete, production-ready code.
"""

run_id = generate_run_id()

# Call the LLM
generated_code = call_agent(
    "data_engineer", 
    DATA_ENGINEER_SYSTEM_PROMPT, 
    user_prompt, 
    temperature=0.05,  # Lower temp = more deterministic adherence to standards
    max_tokens=8192   # Increased: full production notebook exceeds 4K tokens
)

print("✅ Code generated successfully")
print("\n" + "=" * 60)
print(generated_code)
print("=" * 60)

# COMMAND ----------

# DBTITLE 1,Save generated code as artifact
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Save and catalog the generated code
# ══════════════════════════════════════════════════════════════════════════════

# Save as agent output
save_agent_output(
    agent_name="data_engineer",
    run_id=run_id,
    output_type="generated_code",
    content=generated_code,
    metadata={
        "requirement": REQUIREMENT[:500],
        "source_tables": SOURCE_TABLES,
        "language": "python/sql"
    }
)

print(f"✅ Code saved to agent_outputs | Run ID: {run_id}")
print(f"\nTo retrieve later:")
print(f"  SELECT content FROM {CATALOG}.{SCHEMA}.agent_outputs")
print(f"  WHERE agent_name = 'data_engineer' AND run_id = '{run_id}'")

# COMMAND ----------

# DBTITLE 1,Validation + retry loop (reject bad code, regenerate up to 2x)
# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION + RETRY LOOP
# Rejects code that violates Hologic standards and regenerates (max 2 retries)
# ══════════════════════════════════════════════════════════════════════════════

import re

MAX_RETRIES = 2

def validate_generated_code(code: str) -> dict:
    """Run all Hologic standard checks. Returns dict of {check_name: (passed, severity)}."""
    code_lower = code.lower()
    
    # Critical checks (auto-reject if ANY fails)
    # Corrected 2026-09-22: this check previously REJECTED correct md5-based code and
    # demanded xxhash64 — backwards from the real, live-verified Hologic standard
    # (every real production HDA_MDE notebook uses md5). See DATA_ENGINEER_SYSTEM_PROMPT's
    # header correction note for the real generated notebooks this bug already produced.
    critical = {
        "Uses md5 (not xxhash64/sha1/sha256)": (
            "md5(" in code_lower and "xxhash64" not in code_lower
            and "sha1(" not in code_lower and "sha256(" not in code_lower,
            "CRITICAL"
        ),
        # Silver notebooks correctly read stg_*/Bronze (that's the real Silver contract) —
        # only flag a Bronze read when the code is NOT itself building a Silver view
        # (target schema 'silver' or a v_mst_/v_trn_ view name).
        "Gold/Platinum reads Silver/Gold only (no stg_*/Bronze read)": (
            ("schema_name='silver'" in code_lower.replace(" ", "")
             or "schemaname'silver'" in code_lower.replace(" ", "").replace('"', "'")
             or re.search(r'view\s+silver\.v_(mst|trn)_', code_lower)
             or re.search(r"'v_(mst|trn)_", code_lower))
            or (
                not re.search(r'from\s+(mde_dev\.)?stg_\w+\.', code_lower)
                and not re.search(r'join\s+(mde_dev\.)?stg_\w+\.', code_lower)
            ),
            "CRITICAL"
        ),
        "dl_* audit columns present": (
            ("dl_rowhash" in code or "dl_creation_date_time" in code or "dl_iscurrent" in code),
            "CRITICAL"
        ),
        "No banned etl_* columns": (
            "etl_load_datetime" not in code and "etl_source_system" not in code and "etl_batch_id" not in code,
            "CRITICAL"
        ),
        "CLUSTER BY AUTO (not explicit cols)": (
            "cluster by auto" in code_lower or ".clusterby" not in code_lower.replace(" ", ""),
            "CRITICAL"
        ),
        "PascalCase columns (no snake_case SK)": (
            # Check: has _SK (PascalCase) and no lowercase _sk pattern like 'dim_xxx_key'
            "_SK" in code and not re.search(r'\b[a-z_]+_key\b', code),
            "CRITICAL"
        ),
        "CREATE OR REPLACE (not if/else branching)": (
            "create or replace" in code_lower or "merge into" in code_lower,
            "CRITICAL"
        ),
    }
    
    # Warning checks (logged but don't trigger retry)
    warnings = {
        "TBLPROPERTIES includes zstd": (
            "zstd" in code_lower,
            "WARNING"
        ),
        "PRIMARY KEY constraint present": (
            "primary key" in code_lower,
            "WARNING"
        ),
        "References source tables": (
            any(t.split(".")[-1].lower() in code_lower for t in SOURCE_TABLES),
            "WARNING"
        ),
        "Single-pass validation (no multiple .count())": (
            code.count(".count()") <= 1,
            "WARNING"
        ),
        "No datetime.now() for audit": (
            "datetime.now" not in code,
            "WARNING"
        ),
    }
    
    return {**critical, **warnings}


def print_validation_results(checks: dict) -> tuple:
    """Print results. Returns (critical_failures, warning_failures)."""
    critical_fails = []
    warning_fails = []
    
    print("Code Quality Validation:")
    print("─" * 60)
    for check_name, (passed, severity) in checks.items():
        icon = "✅" if passed else ("❌" if severity == "CRITICAL" else "⚠️")
        print(f"  {icon} [{severity}] {check_name}")
        if not passed:
            if severity == "CRITICAL":
                critical_fails.append(check_name)
            else:
                warning_fails.append(check_name)
    print("─" * 60)
    return critical_fails, warning_fails


# --- Main retry loop ---
attempt = 0
final_code = generated_code

while attempt <= MAX_RETRIES:
    checks = validate_generated_code(final_code)
    critical_fails, warning_fails = print_validation_results(checks)
    
    if not critical_fails:
        # All critical checks passed
        if warning_fails:
            print(f"\n⚠️ Passed with {len(warning_fails)} warning(s): {warning_fails}")
        print(f"\n✅ ACCEPTED on attempt {attempt + 1} of {MAX_RETRIES + 1}")
        break
    else:
        attempt += 1
        if attempt > MAX_RETRIES:
            print(f"\n❌ REJECTED after {MAX_RETRIES + 1} attempts. Critical failures: {critical_fails}")
            print("Manual review required. Code saved but flagged.")
            break
        
        # Build correction prompt with specific failures
        correction_prompt = f"""Your previous output was REJECTED because it violated these Hologic standards:

{chr(10).join(f'- VIOLATION: {f}' for f in critical_fails)}

Review the CRITICAL VIOLATIONS table in your system instructions and regenerate.
Remember: PascalCase columns, dl_* audit, md5(concat_ws('|', ...)) for SKs (never xxhash64),
Gold/Platinum reads Silver/Gold only (never stg_*/Bronze), CLUSTER BY AUTO, CREATE OR REPLACE TABLE.

Here is the rejected code (fix it):
```
{final_code[:3000]}
```

Regenerate the COMPLETE code following ALL standards. Return ONLY the corrected code."""
        
        print(f"\n🔄 Attempt {attempt + 1}/{MAX_RETRIES + 1} — Regenerating (failures: {critical_fails})...")
        
        final_code = call_agent(
            "data_engineer",
            DATA_ENGINEER_SYSTEM_PROMPT,
            correction_prompt,
            temperature=0.02,  # Even lower temp on retry
            max_tokens=8192
        )
        print(f"   Regeneration complete. Re-validating...\n")

# Update generated_code to the final accepted/rejected version
generated_code = final_code