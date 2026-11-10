# Databricks notebook source
# DBTITLE 1,Peer Review Agent
# MAGIC %md
# MAGIC # Agent 07 — Peer Review
# MAGIC
# MAGIC **Purpose:** Automated code review for PySpark, SQL, and DLT code. Evaluates quality, performance, security, and standards compliance.
# MAGIC
# MAGIC **Review dimensions:**
# MAGIC - Code quality (SOLID, readability, maintainability)
# MAGIC - Performance (shuffle avoidance, predicate pushdown, join optimization)
# MAGIC - Security (PII handling, RBAC, credential management)
# MAGIC - Standards compliance (naming, xxHash64, audit columns, Liquid Clustering)
# MAGIC - Cost implications (DBU impact, storage efficiency)
# MAGIC
# MAGIC **Input:** Code to review (from Data Engineer agent output or manual submission)
# MAGIC **Output:** Structured review with severity-rated findings

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Peer review system prompt
# ══════════════════════════════════════════════════════════════════════════════
# PEER REVIEW AGENT
# ══════════════════════════════════════════════════════════════════════════════

PEER_REVIEW_PROMPT = """You are a Principal Data Engineer conducting a rigorous peer review.

Review the code against these Hologic engineering standards:

## CRITICAL (Must Fix)
- MD5 usage (must be xxHash64)
- Hardcoded credentials or tokens
- No error handling for production code
- Missing or wrong audit columns. CORRECT Hologic standard:
  FACTS: dl_rowhash STRING, dl_creation_date_time TIMESTAMP, dl_last_updated_date_time TIMESTAMP
  DIMS: dl_iscurrent BOOLEAN, dl_recordstartdateutc TIMESTAMP, dl_recordenddateutc TIMESTAMP, dl_transform_id INT, dl_rowhash STRING
  FLAG as CRITICAL if etl_load_datetime / etl_source_system / etl_batch_id are present — these are the WRONG standard
- Using PARTITION BY instead of CLUSTER BY AUTO (Hologic standard is CLUSTER BY AUTO — also flag CLUSTER BY (col1, col2) with explicit columns as non-compliant)
- Unbounded queries without LIMIT in interactive contexts
- Cross-joins or Cartesian products without explicit justification
- snake_case column names on Gold/Platinum/Silver tables — Hologic standard is PascalCase (CustomerAccount_SK, Invoice_ID, AccountingDate). Flag customer_account_sk, invoice_id, accounting_date as CRITICAL naming violations
- Missing TBLPROPERTIES block on CREATE TABLE statements — must include delta.autoOptimize.autoCompact=true, delta.autoOptimize.optimizeWrite=true, delta.parquet.compression.codec=zstd, delta.enableDeletionVectors=true, delta.enableRowTracking=true
- Missing PRIMARY KEY constraint on grain SK column (CONSTRAINT <table>_pk PRIMARY KEY (<GrainSK>))
- SK column declared as BIGINT or INT — Hologic SK type is STRING (xxhash64 returns STRING)

## HIGH (Should Fix)
- No data quality validation (row counts, null checks)
- Missing incremental logic (full overwrite where MERGE is appropriate)
- Inefficient join patterns (broadcast hints missing for small tables)
- No logging/observability
- Hardcoded catalog/schema (should be parameterized)

## MEDIUM (Consider)
- Code duplication
- Missing inline documentation
- Suboptimal column ordering (clustering columns should be first)
- Non-standard naming conventions — specifically: table names must be snake_case with fact_/dim_/bridge_/agg_ prefix; column names must be PascalCase with _SK STRING and _ID BIGINT suffixes; amount/qty columns should be FLOAT not DECIMAL

## LOW (Nice to Have)
- Style improvements
- Additional test cases
- Performance micro-optimizations

## NOTEBOOK STRUCTURE COMPLIANCE (ADO Wiki Page 258 Standards)
When reviewing a complete notebook (not just a code snippet), also check:

### Dimension Notebooks (Gold):
- CRITICAL: Notebook name must = target table name (dim_*)
- CRITICAL: Must use DimensionProcessor class (not raw SQL INSERT/OVERWRITE)
- CRITICAL: Staging view name must be v_dim_<name> with TBLPROPERTIES (config.sk_column_name, config.nk_column_names, config.cluster_by)
- CRITICAL: SK must NOT be in the staging view SELECT (DimensionProcessor auto-generates it)
- HIGH: Must have %run ../../LakehouseUtilities
- HIGH: Must end with LakeOrchestrator.exit_with_status()
- HIGH: Catalog must NOT be hardcoded (use widgets: catalogName)
- MEDIUM: Should have markdown header cell describing the dimension

### Fact Notebooks (Gold):
- CRITICAL: Must have loadType widget ('I' or 'F')
- CRITICAL: Must use FactProcessor class
- CRITICAL: Staging view v_fact_<name> MUST include SK calculation: md5(concat_ws('|', NKs)) AS <Name>_SK
- CRITICAL: Staging view TBLPROPERTIES must include config.fact_type (1=full, 2=incremental)
- HIGH: Incremental logic must get MAX dates from target and filter with date_final
- HIGH: Must end with LakeOrchestrator.exit_with_status()
- HIGH: Catalog must NOT be hardcoded

### Silver Notebooks:
- CRITICAL: Notebook name = view name, must start with v_mst_ or v_trn_
- CRITICAL: Must have 1:1 relationship with Bronze (stg_*) table
- CRITICAL: Must include `AND dl_iscurrent = 'Y'` filter
- HIGH: Must NOT join multiple Bronze tables (that's Gold layer logic)
- HIGH: Must pull from Bronze TABLE directly (not from stg views)
- MEDIUM: SQL keywords should be UPPERCASE

### Platinum Notebooks (ONLY for custom aggregations — NOT standard dims/facts):
- NOTE: v_pbi_* views are AUTO-GENERATED by DimensionProcessor/FactProcessor during .process()
  Developers do NOT need separate Platinum notebooks for standard dims/facts.
  Only flag as a violation if someone creates a Platinum notebook that duplicates what the processor already auto-generates.
- CRITICAL: When a Platinum notebook IS needed (custom agg/cross-domain), must use ViewProcessor class
- HIGH: View name must start with v_pbi_
- HIGH: Schema must be 'platinum'

### General Coding Standards:
- HIGH: Use CTEs instead of subqueries
- HIGH: Use CASE instead of DECODE/IF
- HIGH: Use COALESCE() instead of NVL
- HIGH: Use TO_DATE()/TO_TIMESTAMP() instead of CAST on dates
- MEDIUM: Only bring required columns (no SELECT *)
- MEDIUM: Avoid DISTINCT with >10 columns
- MEDIUM: Use broadcast joins for tables < 10 MB
- MEDIUM: Apply predicate pushdown (filter early)
- MEDIUM: Avoid GROUP BY ALL

For EACH finding, provide:
```json
{
    "severity": "CRITICAL|HIGH|MEDIUM|LOW",
    "category": "PERFORMANCE|SECURITY|QUALITY|STANDARDS|COST",
    "line_hint": "description of where in the code",
    "finding": "what's wrong",
    "recommendation": "how to fix it",
    "effort_hours": 0.5
}
```

Also provide:
- OVERALL SCORE: 1-10 (10 = production-ready, no changes needed)
- APPROVAL: APPROVED / APPROVED_WITH_COMMENTS / CHANGES_REQUIRED / REJECTED
- SUMMARY: 2-3 sentence overall assessment

Respond with valid JSON containing "findings" array, "score", "approval", and "summary".
"""

print("✅ Peer Review agent loaded")

# COMMAND ----------

# DBTITLE 1,Load Hologic canonical DDL standards
# ══════════════════════════════════════════════════════════════════════════════
# CANONICAL HOLOGIC DDL STANDARDS
# Fetched live from production tables — used as the review reference pattern.
# The LLM compares submitted code against these DDLs to detect deviations.
# ══════════════════════════════════════════════════════════════════════════════

def get_hologic_canonical_standards() -> str:
    """
    Fetch DDL from canonical production Hologic gold tables.
    Returns markdown with production DDL used as the review reference—
    the LLM compares submitted code against these patterns.
    """
    canonical_tables = [
        f"{CATALOG}.gold.dim_customeraccount",   # Canonical SCD dimension
        f"{CATALOG}.gold.fact_ap_invoice",       # Canonical transactional fact
    ]
    parts = ["## CANONICAL HOLOGIC DDL (production) — COMPARE SUBMITTED CODE AGAINST THIS"]
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
print(f"✅ Canonical Hologic DDL loaded ({len(HOLOGIC_CANONICAL_STANDARDS)} chars) — review reference ready")
print("   Standards: PascalCase columns | dl_* audit | CLUSTER BY AUTO | FLOAT amounts | zstd+deletionVectors")

# COMMAND ----------

# DBTITLE 1,Execute peer review
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Get code to review (from agent_outputs or manual input)
# ══════════════════════════════════════════════════════════════════════════════

try:
    CODE_TO_REVIEW = dbutils.widgets.get("code")
except:
    # Try to get the latest output from the Data Engineer agent
    CODE_TO_REVIEW = get_latest_agent_output("data_engineer", "generated_code")
    
    if not CODE_TO_REVIEW:
        # Fallback: example code for testing
        CODE_TO_REVIEW = '''
import pyspark.sql.functions as F
from pyspark.sql import SparkSession

df = spark.read.table("mde_dev.stg_oracle_ebs.ap_invoices_all")

# Create silver table
df_silver = df.select(
    F.md5(F.concat_ws("|", "invoice_id", "org_id")).alias("invoice_sk"),
    "invoice_id",
    "vendor_id", 
    "invoice_num",
    "invoice_amount",
    "invoice_date",
    F.current_timestamp().alias("load_date")
)

df_silver.write.mode("overwrite").saveAsTable("mde_dev.silver.fact_ap_invoice")
print(f"Done: {df_silver.count()} rows")
'''

run_id = generate_run_id()

print(f"Code to review ({len(CODE_TO_REVIEW)} chars):")
print(CODE_TO_REVIEW[:500])

# COMMAND ----------

# DBTITLE 1,Call LLM for review and generate report
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Execute review and format results
# ══════════════════════════════════════════════════════════════════════════════

user_prompt = f"""## Canonical Hologic Production DDL — USE AS THE REFERENCE STANDARD
{HOLOGIC_CANONICAL_STANDARDS}

## Code to Review
```python
{CODE_TO_REVIEW}
```

Perform a thorough peer review. Compare this code directly against the canonical DDL above.
Column naming, audit columns, clustering, TBLPROPERTIES, data types, and PRIMARY KEY
must all match the production pattern. Flag any deviation from the canonical DDL as a finding."""

review_response = call_agent("peer_review", PEER_REVIEW_PROMPT, user_prompt, max_tokens=3000)

# Parse the response
try:
    clean = review_response.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
    review_data = json.loads(clean)
except:
    # If not valid JSON, treat as freeform review
    review_data = {"raw_review": review_response, "score": "N/A", "approval": "MANUAL_CHECK", "findings": []}

# Format report
findings = review_data.get("findings", [])
score = review_data.get("score", "N/A")
approval = review_data.get("approval", "UNKNOWN")
summary = review_data.get("summary", "")

print(f"\n{'='*60}")
print(f"PEER REVIEW RESULTS")
print(f"{'='*60}")
print(f"\n🎯 Score: {score}/10")
print(f"📝 Approval: {approval}")
print(f"💬 Summary: {summary}")
print(f"\n{'='*60}")
print(f"FINDINGS ({len(findings)} total)")
print(f"{'='*60}")

for i, finding in enumerate(findings, 1):
    severity = finding.get('severity', 'UNKNOWN')
    icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")
    print(f"\n{icon} [{severity}] {finding.get('category', '')}")
    print(f"   Finding: {finding.get('finding', '')}")
    print(f"   Fix: {finding.get('recommendation', '')}")
    print(f"   Effort: {finding.get('effort_hours', '?')}h")

# COMMAND ----------

# DBTITLE 1,Save review results
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Persist review
# ══════════════════════════════════════════════════════════════════════════════

save_agent_output(
    agent_name="peer_review",
    run_id=run_id,
    output_type="review_report",
    content=json.dumps(review_data, indent=2),
    metadata={
        "score": score,
        "approval": approval,
        "critical_findings": sum(1 for f in findings if f.get('severity') == 'CRITICAL'),
        "total_findings": len(findings)
    }
)

print(f"\n✅ Agent 07 (Peer Review) completed | Run ID: {run_id}")
print(f"   Score: {score}/10 | Approval: {approval} | Findings: {len(findings)}")