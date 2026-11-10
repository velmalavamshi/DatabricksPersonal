# Databricks notebook source
# DBTITLE 1,Enterprise Standards Agent
# MAGIC %md
# MAGIC # Agent 28 — Enterprise Standards
# MAGIC
# MAGIC **Purpose:** Validate code, architecture, and documentation against Hologic's enterprise coding standards, naming conventions, and folder structures.
# MAGIC
# MAGIC **Output:** StandardsComplianceReport.md — pass/fail per standard with remediation.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Load Hologic canonical DDL standards
def get_hologic_canonical_standards() -> str:
    canonical_tables = [
        f"{CATALOG}.gold.dim_customeraccount",
        f"{CATALOG}.gold.fact_ap_invoice",
    ]
    parts = ["## CANONICAL HOLOGIC DDL (production) — AUDIT ALL CODE AGAINST THESE PATTERNS"]
    for tbl in canonical_tables:
        try:
            ddl = spark.sql(f"SHOW CREATE TABLE {tbl}").collect()[0][0]
            tbl_props_idx = ddl.find("TBLPROPERTIES")
            ddl_short = ddl[:tbl_props_idx] + "TBLPROPERTIES (\n  'delta.autoOptimize.autoCompact' = 'true',\n  'delta.autoOptimize.optimizeWrite' = 'true',\n  'delta.parquet.compression.codec' = 'zstd',\n  'delta.enableDeletionVectors' = 'true',\n  'delta.enableRowTracking' = 'true',\n  'delta.checkpointPolicy' = 'v2')" if tbl_props_idx > 0 else ddl
            parts.append(f"\n### {tbl}\n```sql\n{ddl_short}\n```")
        except Exception as e:
            parts.append(f"\n### {tbl}\n  [Schema read failed: {e}]")
    return "\n".join(parts)

HOLOGIC_CANONICAL_STANDARDS = get_hologic_canonical_standards()
print(f"✅ Canonical DDL loaded ({len(HOLOGIC_CANONICAL_STANDARDS)} chars) — PascalCase | dl_* audit | CLUSTER BY AUTO")

# COMMAND ----------

# DBTITLE 1,Enterprise standards execution
STANDARDS_PROMPT = """You are an Enterprise Standards Auditor for Hologic's Databricks platform.

Validate against these MANDATORY standards (corrected 2026-09-22 — this prompt previously had the
SK formula and view-naming rules backwards/wrong; real production HDA_MDE notebooks and
hologic-databricks-standards (HDA_MDE.wiki page 258) are the ground truth, verified live):

1. NAMING CONVENTIONS
   - Gold/Platinum tables: snake_case, prefixed (fact_, dim_, bridge_, agg_). New Platinum objects
     get a `_plt` suffix (fact_<name>_plt, dim_<name>_plt).
   - Silver views: `v_mst_<source>_<table>` (reference) or `v_trn_<source>_<table>` (transaction),
     never `vw_` — sources: oracle_ebs, agile, ascp, azure, cornerstone, mule, pbcs, salesforce,
     servicenow.
   - Columns: **PascalCase-mashed, `_` ONLY immediately before a final `_ID`/`_SK` suffix — never
     snake_case.** Examples: CustomerAccount_SK, Invoice_ID, AccountingDate, PaymentStatusFlag.
   - SK suffix: _SK (STRING type) | ID suffix: _ID (BIGINT type) | amounts: FLOAT, not DECIMAL
   - Jobs: <domain>_<action>_<frequency> (e.g., finance_load_daily)

2. SURROGATE KEY STANDARD
   - MUST use: md5(CONCAT_WS('|', business_key_cols))
   - NEVER: xxhash64, SHA1, SHA256 for SKs — this is the real, live-verified standard; do not
     flag md5 as a violation and do not accept xxhash64 as compliant, no matter what an older
     copy of this prompt or another agent's prompt said.
   - Column name: PascalCase with _SK suffix (e.g., CustomerAccount_SK, InvoiceLine_SK) — STRING type, not BIGINT

3. AUDIT COLUMNS (on EVERY table — Hologic dl_* pattern, NEVER etl_*)
   FACTS: dl_rowhash STRING, dl_creation_date_time TIMESTAMP, dl_last_updated_date_time TIMESTAMP
   DIMS: dl_iscurrent BOOLEAN, dl_recordstartdateutc TIMESTAMP, dl_recordenddateutc TIMESTAMP, dl_transform_id INT, dl_rowhash STRING
   FLAG AS VIOLATION if etl_load_datetime / etl_source_system / etl_batch_id are present — wrong standard
   Silver views: SELECT only `dl_recordstartdateutc` (as to_timestamp) for lineage — never
   `dl_rowhash`/`dl_recordenddateutc`/`dl_load_id`. `dl_iscurrent` is filter-only (WHERE), never selected.

4. PROCESSOR CLASS & MEDALLION READ RULE
   - Gold facts use `FactProcessor` (real MERGE on loadType='I', dl_rowhash change detection — no
     delete propagation). Gold dimensions (incl. bridge tables) use `DimensionProcessor` (no
     loadType — always re-reads the FULL view; dim_type=1 SCD1 / 2 SCD2). Platinum marts use
     `PlatinumProcessor` (full CTAS, no incremental) or `ViewProcessor` for a plain reporting view.
   - **Gold reads Silver ONLY. Platinum reads Gold ONLY.** FLAG AS CRITICAL VIOLATION any Gold
     view reading `stg_*`/Bronze directly, or any Platinum view reading Silver directly.
   - Every Gold fact needs real incremental logic (watermark + dirty-batch) — flag a full
     recompute with no loadType/watermark handling as a violation.

5. TABLE PROPERTIES
   - CLUSTER BY AUTO — NOT PARTITION BY, NOT CLUSTER BY (explicit_cols)
   - Standard TBLPROPERTIES required: delta.autoOptimize.autoCompact=true, delta.autoOptimize.optimizeWrite=true, delta.parquet.compression.codec=zstd, delta.enableDeletionVectors=true, delta.enableRowTracking=true
   - All config.* keys required on the transient view (sk_column_name, nk_column_names,
     cluster_by, fact_type/dim_type, primary_key, foreign_key, unique_constraints,
     not_null_constraints, check_constraints) — flag a missing key even if its value would be empty
   - PRIMARY KEY constraint on grain SK column: CONSTRAINT <table>_pk PRIMARY KEY (<GrainSK>)
   - Table COMMENT with business description
   - Column COMMENTs on all columns

6. CODE STANDARDS
   - No SELECT * in production code
   - Explicit column lists in INSERT/MERGE
   - Error handling (try/except with logging)
   - No hardcoded credentials or connection strings

7. FOLDER STRUCTURE
   - /Bronze/ /Silver/ /Gold/ /Platinum/ layer folders
   - README.md in each project folder
   - Consistent notebook naming

For each violation: Standard, Location, Current, Expected, Severity.
Score overall compliance 0-100%.
"""

try:
    INPUT = dbutils.widgets.get("code")
except:
    INPUT = get_latest_agent_output("data_engineer", "generated_code") or "Audit enterprise standards compliance for recent pipeline code."

run_id = generate_run_id()
result = call_agent(
    "data_engineer",
    STANDARDS_PROMPT,
    f"## Canonical Hologic DDL — AUDIT ALL CODE AGAINST THESE PATTERNS\n{HOLOGIC_CANONICAL_STANDARDS}\n\nAudit standards compliance for:\n\n{INPUT}",
    max_tokens=3000
)
save_agent_output("enterprise_standards", run_id, "standards_report", result, {})
print(result)
print(f"\n✅ Agent 28 (Enterprise Standards) completed | Run ID: {run_id}")