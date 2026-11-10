# Databricks notebook source
# DBTITLE 1,Data Quality Agent — DLT Expectations + DQX
# MAGIC %md
# MAGIC # Agent 16 — Data Quality (DLT Expectations + DQX)
# MAGIC
# MAGIC **Purpose:** Generate data validation rules using two complementary frameworks:
# MAGIC - **DLT Expectations** — inline `CONSTRAINT` blocks for Spark Declarative Pipelines (Bronze → Silver → Gold)
# MAGIC - **DQX Rules** — row-level profiling via `databricks-labs-dqx` — works on **any layer** including standalone Gold/Platinum views
# MAGIC
# MAGIC **Output:** DataQualityFramework.md, DLT expectations code, DQX rules JSON, reconciliation queries, SQL assertions
# MAGIC
# MAGIC **Pipeline position:** `02_data_engineer` → **`16_data_quality`** → `76_layer_validation` → `07_peer_review` → `31_release_approval`

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
    parts = ["## CANONICAL HOLOGIC DDL (production) — GENERATE DQ RULES BASED ON THESE ACTUAL COLUMN NAMES"]
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

# DBTITLE 1,STEP 1 — Widgets
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Widgets
# ══════════════════════════════════════════════════════════════════════════════
for w in ["target_table", "layer", "include_dqx", "code"]:
    try: dbutils.widgets.remove(w)
    except: pass

dbutils.widgets.text("target_table", "",        "Target Table (catalog.schema.table — optional)")
dbutils.widgets.dropdown("layer", "Silver",     ["Bronze", "Silver", "Gold", "Platinum"], "Medallion Layer")
dbutils.widgets.dropdown("include_dqx", "Yes",  ["Yes", "No"], "Include DQX Rules")
dbutils.widgets.text("code", "",                "Code to validate (blank = use latest engineer output)")

print("✅ STEP 1 complete — widgets configured")

# COMMAND ----------

# DBTITLE 1,STEP 2 — Context Gathering (schema + engineer output)
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Context Gathering (target table schema + engineer code output)
# ══════════════════════════════════════════════════════════════════════════════

TARGET_TABLE = dbutils.widgets.get("target_table").strip()
LAYER        = dbutils.widgets.get("layer")
INCLUDE_DQX  = dbutils.widgets.get("include_dqx") == "Yes"
CODE_INPUT   = dbutils.widgets.get("code").strip()

# Fall back to latest Data Engineer output
if not CODE_INPUT:
    CODE_INPUT = get_latest_agent_output("data_engineer", "generated_code") or \
                 "Generate data quality rules for a Silver dim_supplier table with xxHash64 SKs."

# Pull live table schema from Information Schema if target_table provided
schema_context = ""
if TARGET_TABLE:
    parts = TARGET_TABLE.split(".")
    if len(parts) == 3:
        catalog, schema, table = parts
        try:
            schema_df = spark.sql(f"""
                SELECT column_name, data_type, is_nullable
                FROM {catalog}.information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = '{table}'
                ORDER BY ordinal_position
            """)
            rows = schema_df.collect()
            if rows:
                schema_context = f"\n\nTarget table schema ({TARGET_TABLE}):\n"
                for r in rows:
                    nullable = "NULLABLE" if r.is_nullable == "YES" else "NOT NULL"
                    schema_context += f"  - {r.column_name}: {r.data_type} ({nullable})\n"
                print(f"✅ Schema fetched: {TARGET_TABLE} — {len(rows)} columns")
            else:
                print(f"⚠️  No columns found for {TARGET_TABLE} — proceeding with code context only")
        except Exception as e:
            print(f"⚠️  Schema fetch failed: {e} — proceeding with code context only")
    else:
        print(f"⚠️  target_table '{TARGET_TABLE}' not fully qualified — skipping schema fetch")

run_id = generate_run_id()
print(f"\n📋 Layer: {LAYER} | DQX: {INCLUDE_DQX} | Table: '{TARGET_TABLE or '(none)'}' | Run ID: {run_id}")
print(f"📄 Code input: {len(CODE_INPUT)} chars")

# COMMAND ----------

# DBTITLE 1,STEP 3 — Enhanced DQ System Prompt (DLT + DQX)
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Enhanced DQ System Prompt (DLT Expectations + DQX Rules)
# ══════════════════════════════════════════════════════════════════════════════

DQ_PROMPT = """You are a Data Quality Engineer specialising in Hologic Medallion architecture.

Generate ALL FOUR frameworks for the given code/table:

## FRAMEWORK 1: DLT EXPECTATIONS (Spark Declarative Pipelines)
For each critical column produce:
  CONSTRAINT <name> EXPECT (<sql_condition>) ON VIOLATION {DROP ROW | FAIL UPDATE | WARN}
Heuristics:
  - SK columns        → ON VIOLATION FAIL UPDATE (zero tolerance)
  - Audit columns     → ON VIOLATION FAIL UPDATE (zero tolerance)
  - Monetary DECIMAL  → ON VIOLATION WARN
  - Date columns      → ON VIOLATION WARN
  - Status/enum codes → ON VIOLATION DROP ROW

## FRAMEWORK 2: DQX RULES (databricks-labs-dqx)
Output a Python variable `dqx_rules` as a list of rule dicts for DQEngine.apply_checks_by_metadata_and_target().
Supported checks: is_not_null, is_not_null_and_not_empty, is_not_empty, is_in_range,
is_not_in_range, is_valid_date, is_valid_timestamp, regex_match, is_unique, sql_expression.

Example format:
dqx_rules = [
    {"check": "is_not_null",               "col_name": "Supplier_SK"},   # PascalCase SK
    {"check": "is_unique",                 "col_name": "Supplier_SK"},
    {"check": "is_not_null_and_not_empty", "col_name": "supplier_name"},
    {"check": "is_in_range",               "col_name": "amount", "min_limit": 0, "max_limit": 9999999},
    {"check": "is_valid_date",             "col_name": "transaction_date"},
    {"check": "is_not_null",               "col_name": "dl_rowhash"},
    {"check": "sql_expression",            "col_name": "dl_creation_date_time", "expression": "dl_creation_date_time IS NOT NULL"},
]

## FRAMEWORK 3: RECONCILIATION QUERIES
SQL comparing row counts + checksums between: stg_* → silver.* → gold.* → platinum.*

## FRAMEWORK 4: SQL ASSERTIONS (non-SDP notebook validation)
Standalone Databricks SQL using SELECT + CASE for assertion-style checks.

Return output in four clearly labelled sections.

Hologic Standards (enforce always):
- Surrogate keys: xxhash64(CONCAT_WS('|', keys)) — NEVER MD5
- Audit cols FACTS: dl_rowhash STRING, dl_creation_date_time TIMESTAMP, dl_last_updated_date_time TIMESTAMP (NOT etl_load_datetime)
- Audit cols DIMS: dl_iscurrent BOOLEAN, dl_recordstartdateutc TIMESTAMP, dl_recordenddateutc TIMESTAMP, dl_transform_id INT, dl_rowhash STRING
- Column naming: PascalCase (Supplier_SK, Invoice_ID, AccountingDate) — NEVER snake_case
- Clustering: CLUSTER BY AUTO (not PARTITION BY, not explicit CLUSTER BY cols)
- Liquid Clustering (NOT PARTITION BY)
- Catalogs: mde_dev (DEV), mde_uat (UAT), mde_prd (PRD)
"""

print("✅ STEP 3 complete — DQ system prompt loaded (DLT + DQX + Reconciliation + Assertions)")

# COMMAND ----------

# DBTITLE 1,STEP 4 — LLM Call → Generate DQ Framework
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — LLM Call → Generate DQ Framework (DLT + DQX + Recon + Assertions)
# ══════════════════════════════════════════════════════════════════════════════

dqx_instruction = (
    "Include Framework 2: DQX Rules as a `dqx_rules` Python list."
    if INCLUDE_DQX else
    "Skip Framework 2 (DQX rules not requested for this run)."
)

user_prompt = f"""## Canonical Hologic DDL — GENERATE DQ RULES USING ACTUAL COLUMN NAMES FROM THIS
{HOLOGIC_CANONICAL_STANDARDS}

Generate a complete data quality framework for the following {LAYER} layer code/table.
{dqx_instruction}

Code / context:
```python
{CODE_INPUT}
```
{schema_context}
Ensure all four sections are present and clearly labelled:
  1. DLT Expectations
  2. DQX Rules (dqx_rules list)
  3. Reconciliation Queries
  4. SQL Assertions
"""

result = call_agent("data_quality", DQ_PROMPT, user_prompt, max_tokens=4096)
print(result)

# COMMAND ----------

# DBTITLE 1,STEP 5 — Validate, Persist & DQX Usage Pattern
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Validate, Persist & DQX Usage Pattern
# ══════════════════════════════════════════════════════════════════════════════

# Persist output
save_agent_output(
    "data_quality", run_id, "quality_framework", result,
    {"layer": LAYER, "target_table": TARGET_TABLE, "include_dqx": INCLUDE_DQX, "code_chars": len(CODE_INPUT)}
)

# Presence checks
has_dlt  = "CONSTRAINT" in result or "EXPECT" in result
has_dqx  = any(k in result for k in ["dqx_rules", "is_not_null", "is_unique", "is_in_range"]) if INCLUDE_DQX else True
has_recon = "RECONCIL" in result.upper() or ("stg" in result.lower() and "COUNT" in result)
has_sql  = "SELECT" in result

print("\n" + "═" * 62)
print("  ✅ Agent 16 (Data Quality) — Validation Report")
print("═" * 62)
print(f"  DLT Expectations:   {'\u2705' if has_dlt  else '\u274c  MISSING'}")
print(f"  DQX Rules:          {'\u2705' if has_dqx  else '\u274c  MISSING' if INCLUDE_DQX else '\u23ed  Skipped'}")
print(f"  Reconciliation SQL: {'\u2705' if has_recon else '\u26a0\ufe0f  Not detected'}")
print(f"  SQL Assertions:     {'\u2705' if has_sql  else '\u26a0\ufe0f  Not detected'}")
print(f"  Layer:              {LAYER}")
print(f"  Run ID:             {run_id}")
print("═" * 62)

# DQX usage snippet
if INCLUDE_DQX:
    print("""
💡 To apply the generated DQX rules in any notebook (Silver/Gold/Platinum):

  %pip install databricks-labs-dqx -q

  from databricks.labs.dqx.engine import DQEngine

  dqx = DQEngine(spark)
  # Paste the generated `dqx_rules` list from above, then:
  good_df, bad_df = dqx.apply_checks_by_metadata_and_target(df, dqx_rules)
  print(f"✅ Good rows:  {good_df.count()}, ❌ Bad rows: {bad_df.count()}")
  bad_df.display()  # Inspect row-level violations
""")

if not has_dlt or (INCLUDE_DQX and not has_dqx):
    raise Exception(
        f"❌ Agent 16 GATE FAILED — DLT present: {has_dlt} | DQX present: {has_dqx}. "
        "Check LLM output above for missing sections."
    )

print(f"✅ Agent 16 complete — output saved | Run ID: {run_id}")
print("➡️  Next: 76_layer_validation_agent OR 07_peer_review_agent")