# Databricks notebook source
# DBTITLE 1,Layer Validation Agent — DQX + Nutter Gate
# MAGIC %md
# MAGIC # Agent 76 — Layer Validation Gate (DQX + Nutter)
# MAGIC
# MAGIC **Purpose:** Silver / Gold / Platinum promotion gate. Combines DQX profiling output (Agent 16)
# MAGIC with Nutter test execution status (Agent 08) to produce a **PASS / WARN / FAIL** decision
# MAGIC before the Release Approval Board (Agent 31) fires.
# MAGIC
# MAGIC **Validation pillars:**
# MAGIC - **DQX** — row-level data quality profiling (null rates, range violations, uniqueness)
# MAGIC - **Nutter** — notebook-based test execution (schema, SK, audit columns, business logic)
# MAGIC - **Live metrics** — actual row count, SK null check, audit column presence from `information_schema`
# MAGIC - **Standards compliance** — xxHash64, audit columns, Liquid Clustering present
# MAGIC
# MAGIC **Hard-fail conditions (non-negotiable):**
# MAGIC - Any SK column contains NULLs
# MAGIC - Missing dl_* audit columns: FACTS require `dl_rowhash` + `dl_creation_date_time` + `dl_last_updated_date_time`; DIMS also require `dl_iscurrent` + `dl_recordstartdateutc` + `dl_recordenddateutc`. Presence of `etl_load_datetime` is itself a violation.
# MAGIC - `MD5` or `SHA` surrogate key detected instead of `xxhash64`
# MAGIC
# MAGIC **Pipeline position:** `02_data_engineer` → `16_data_quality` → `08_unit_test` → **`76_layer_validation`** → `07_peer_review` → `31_release_approval`
# MAGIC
# MAGIC **Output:** LayerValidationReport (persisted to `mde_dev.test_schema.agent_outputs`), gate status

# COMMAND ----------

# DBTITLE 1,Load Shared Config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Load Hologic canonical DDL standards
def get_hologic_canonical_standards() -> str:
    canonical_tables = [
        f"{CATALOG}.gold.dim_customeraccount",
        f"{CATALOG}.gold.fact_ap_invoice",
    ]
    parts = ["## CANONICAL HOLOGIC DDL (production) — VALIDATE ALL TABLES AGAINST THESE PATTERNS"]
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
for w in ["target_table", "layer", "row_count_tolerance_pct"]:
    try: dbutils.widgets.remove(w)
    except: pass

dbutils.widgets.text("target_table",           "mde_dev.silver.dim_supplier", "Target Table (catalog.schema.table)")
dbutils.widgets.dropdown("layer", "Silver",    ["Bronze", "Silver", "Gold", "Platinum"],  "Medallion Layer")
dbutils.widgets.text("row_count_tolerance_pct", "1.0",                                     "Row Count Tolerance %")

print("✅ STEP 1 complete — widgets configured")

# COMMAND ----------

# DBTITLE 1,STEP 2 — Context Gathering (live metrics + upstream agent outputs)
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Context Gathering (DQX output, Nutter output, live table metrics)
# ══════════════════════════════════════════════════════════════════════════════

TARGET_TABLE  = dbutils.widgets.get("target_table").strip()
LAYER         = dbutils.widgets.get("layer")
ROW_TOLERANCE = float(dbutils.widgets.get("row_count_tolerance_pct") or "1.0")

run_id = generate_run_id()

# ── Pull upstream agent outputs ──
dqx_output    = get_latest_agent_output("data_quality", "quality_framework") or "(No Agent 16 DQX output found)"
nutter_output = get_latest_agent_output("unit_test",   "nutter_test_notebook") or "(No Agent 08 Nutter output found)"
pytest_output = get_latest_agent_output("unit_test",   "test_suite") or "(No Agent 08 PyTest output found)"

# ── Live table metrics ──
table_metrics  = {}
hard_fail_list = []

if TARGET_TABLE:
    parts = TARGET_TABLE.split(".")
    if len(parts) == 3:
        catalog, schema, table = parts
        try:
            # Row count
            table_metrics["row_count"] = spark.sql(f"SELECT COUNT(*) AS n FROM {TARGET_TABLE}").collect()[0]["n"]

            # Schema
            cols_df = spark.sql(f"""
                SELECT column_name, data_type, is_nullable
                FROM {catalog}.information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = '{table}'
                ORDER BY ordinal_position
            """)
            cols = cols_df.collect()
            table_metrics["column_count"] = len(cols)

            # SK columns + null check
            # Hologic PascalCase: CustomerAccount_SK, Invoice_SK — must use case-insensitive endswith
            sk_cols = [c.column_name for c in cols if c.column_name.upper().endswith("_SK")]
            table_metrics["sk_columns"] = sk_cols
            if sk_cols:
                null_expr = " OR ".join([f"{c} IS NULL" for c in sk_cols])
                sk_nulls  = spark.sql(f"SELECT COUNT(*) AS n FROM {TARGET_TABLE} WHERE {null_expr}").collect()[0]["n"]
                table_metrics["sk_null_count"] = sk_nulls
                if sk_nulls > 0:
                    hard_fail_list.append(f"SK NULL violation: {sk_nulls} null SK rows in {sk_cols}")

            # Audit columns
            # Hologic dl_* audit pattern (NOT etl_*). Facts need dl_rowhash + dl_creation_date_time minimum.
            DL_AUDIT_REQUIRED = {"dl_rowhash", "dl_creation_date_time"}
            DL_AUDIT_ALL = {"dl_rowhash", "dl_creation_date_time", "dl_last_updated_date_time",
                            "dl_iscurrent", "dl_recordstartdateutc", "dl_recordenddateutc", "dl_transform_id"}
            ETL_WRONG_COLS = {"etl_load_datetime", "etl_source_system", "etl_batch_id"}
            col_names = {c.column_name for c in cols}
            present_audit = list(col_names & DL_AUDIT_ALL)
            wrong_audit   = list(col_names & ETL_WRONG_COLS)
            table_metrics["audit_columns_present"] = present_audit
            table_metrics["audit_columns_complete"] = DL_AUDIT_REQUIRED.issubset(col_names)
            if wrong_audit:
                hard_fail_list.append(f"Non-Hologic etl_* audit columns present: {wrong_audit} (must use dl_* pattern)")
            if not DL_AUDIT_REQUIRED.issubset(col_names):
                missing_audit = DL_AUDIT_REQUIRED - col_names
                hard_fail_list.append(f"Missing required dl_* audit columns: {missing_audit}")

            print(f"✅ Live metrics for {TARGET_TABLE}")
            print(f"   Rows: {table_metrics['row_count']:,} | Cols: {table_metrics['column_count']} | SK: {sk_cols}")
            print(f"   Audit cols: {present_audit} | SK nulls: {table_metrics.get('sk_null_count', 'N/A')}")
        except Exception as e:
            print(f"⚠️  Metric collection failed: {e}")
            table_metrics["error"] = str(e)
    else:
        print(f"⚠️  target_table not fully qualified — skipping live metrics")

print(f"\n📋 Upstream context: DQX {len(dqx_output):,} chars | Nutter {len(nutter_output):,} chars")
print(f"   Hard fails so far: {hard_fail_list or 'None'}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — Build Validation System Prompt
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Validation System Prompt + User Context
# ══════════════════════════════════════════════════════════════════════════════

VALIDATION_SYSTEM_PROMPT = """You are a Data Quality Gate Officer for the Hologic Medallion Lakehouse.

Review outputs from Agent 16 (DQX/DLT quality framework) and Agent 08 (Nutter + PyTest)
and issue a PASS / WARN / FAIL gate decision before Agent 31 (Release Approval Board).

## Hard-Fail Conditions (auto-FAIL regardless of anything else)
1. SK column contains NULL values
2. Missing dl_* audit columns: FACTS require dl_rowhash + dl_creation_date_time + dl_last_updated_date_time; DIMS also require dl_iscurrent + dl_recordstartdateutc + dl_recordenddateutc. Presence of etl_load_datetime / etl_source_system / etl_batch_id is itself a hard fail (wrong standard)
3. MD5() or SHA() used instead of xxhash64() for surrogate keys
4. PARTITION BY used instead of CLUSTER BY AUTO, or CLUSTER BY (explicit_cols) instead of CLUSTER BY AUTO

## DQX Gate Thresholds
- SK / PK columns:       0% nulls tolerated (zero tolerance)
- Audit columns:          0% nulls tolerated
- Business key columns:   < 0.01% nulls
- dqx_rules list:         must be present with ≥4 rules covering SK + audit + business key columns
- Overall pass rate:      > 99.5%

## Nutter Gate Thresholds
- Lifecycle completeness: before/run/assertion(/after) present for each test case
- Required test cases:    schema_is_correct, sk_is_not_null, audit_cols_populated, row_count_matches
- Minimum test count:     4 assertion_* methods
- Teardown present:       after_* DROP TABLE in every test case that writes data

## Output Format (use exactly these section headers)

### 🎯 GATE DECISION: [PASS ✅ | PASS WITH WARNINGS ⚠️ | FAIL ❌]

### 📊 DQX Assessment
(dqx_rules present ✅/❌, coverage: SK/audit/business keys, critical violations)

### 🧪 Nutter Assessment
(test case count, required cases present/missing, lifecycle completeness, teardown ✅/❌)

### 📋 Standards Compliance
| Standard | Status | Detail |
|---|---|---|
| xxHash64 (not MD5) | ✅/❌ | ... |
| dl_* audit cols present (dl_rowhash + dl_creation_date_time minimum; no etl_* cols) | ✅/❌ | ... |
| Liquid Clustering | ✅/❌ | ... |
| No direct prod writes in tests | ✅/❌ | ... |

### 🔧 Remediation Actions (FAIL only)
(Numbered list of EXACT fixes required before resubmission)

### 💡 Recommendations (PASS/WARN only)
(Non-blocking improvements)
"""

metrics_str = "\n".join([f"  {k}: {v}" for k, v in table_metrics.items()])

user_context = f"""## Canonical Hologic DDL — VALIDATE TABLE AGAINST THESE PATTERNS
{HOLOGIC_CANONICAL_STANDARDS}

## Layer Validation Request
- Target Table:         {TARGET_TABLE}
- Medallion Layer:      {LAYER}
- Row Tolerance:        {ROW_TOLERANCE}%
- Run ID:               {run_id}
- Hard Fails Pre-Check: {hard_fail_list or 'None'}

## Live Table Metrics
{metrics_str if table_metrics else '  (Not available — table does not exist yet; validate from code context)'}

## Agent 16 — DQX + Quality Framework Output
{dqx_output[:3000]}{'... [truncated]' if len(dqx_output) > 3000 else ''}

## Agent 08 — Nutter Test Notebook
{nutter_output[:2000]}{'... [truncated]' if len(nutter_output) > 2000 else ''}

## Agent 08 — PyTest Suite (summary)
{pytest_output[:800]}{'... [truncated]' if len(pytest_output) > 800 else ''}

Issue your structured gate decision now.
"""

print(f"✅ STEP 3 complete — validation context: {len(user_context):,} chars")

# COMMAND ----------

# DBTITLE 1,STEP 4 — LLM Call → Gate Decision
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — LLM Call → Gate Report
# ══════════════════════════════════════════════════════════════════════════════

# If hard fails already detected, prepend them for the LLM
hard_fail_prefix = ""
if hard_fail_list:
    hard_fail_prefix = (
        "\n⚠️  HARD FAILS DETECTED BY PRE-CHECK (must result in FAIL decision):\n"
        + "\n".join([f"  ❌ {f}" for f in hard_fail_list])
        + "\n"
    )

gate_report = call_agent(
    "layer_validation",
    VALIDATION_SYSTEM_PROMPT,
    hard_fail_prefix + user_context,
    temperature=0.05,
    max_tokens=4096
)

print(gate_report)

# COMMAND ----------

# DBTITLE 1,STEP 5 — HARD GATE: Parse Decision, Persist, Route
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — HARD GATE: Parse Decision, Persist, Route to Next Agent
# ══════════════════════════════════════════════════════════════════════════════

# ── Parse gate status from LLM output ──
if "GATE DECISION: PASS WITH WARNINGS" in gate_report or "PASS WITH WARNINGS" in gate_report:
    gate_status = "WARN"
elif ("GATE DECISION: PASS" in gate_report or "GATE DECISION: PASS ✅" in gate_report) \
     and "FAIL" not in gate_report.split("GATE DECISION:")[1][:60].upper():
    gate_status = "PASS"
else:
    gate_status = "FAIL"

# Hard-fail override from pre-check
if hard_fail_list:
    gate_status = "FAIL"

# ── Persist gate report ──
save_agent_output(
    agent_name="layer_validation",
    run_id=run_id,
    output_type="gate_report",
    content=gate_report,
    metadata={
        "layer":         LAYER,
        "target_table":  TARGET_TABLE,
        "gate_status":   gate_status,
        "hard_fails":    hard_fail_list,
        "row_count":     table_metrics.get("row_count", -1),
        "sk_null_count": table_metrics.get("sk_null_count", -1),
    }
)

# ── Status banner ──
icons   = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
borders = {"PASS": "═", "WARN": "─", "FAIL": "─"}
print("\n" + borders[gate_status] * 65)
print(f"  {icons[gate_status]}  AGENT 76 — LAYER VALIDATION GATE: {gate_status}")
print(borders[gate_status] * 65)
print(f"  Table:    {TARGET_TABLE}")
print(f"  Layer:    {LAYER}")
print(f"  Run ID:   {run_id}")
if hard_fail_list:
    print("  Hard Failures:")
    for f in hard_fail_list:
        print(f"    ❌ {f}")
print(borders[gate_status] * 65)

if gate_status == "PASS":
    print("\n✅ Cleared — proceed to: 07_peer_review_agent → 31_release_approval_board")
elif gate_status == "WARN":
    print("\n⚠️  Cleared with warnings — review recommendations before release")
    print("➡️  Continue to: 07_peer_review_agent")
else:
    raise Exception(
        f"❌ LAYER VALIDATION GATE FAILED — {TARGET_TABLE} ({LAYER})\n"
        f"Hard failures: {hard_fail_list}\n"
        f"Run ID: {run_id}\n"
        "Fix all Remediation Actions above and re-run Agent 16 + Agent 08 before retrying."
    )

# COMMAND ----------

