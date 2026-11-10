# Databricks notebook source
# DBTITLE 1,Documentation Sync Agent
# MAGIC %md
# MAGIC # Agent 35 — Documentation Sync
# MAGIC
# MAGIC **Purpose:** Auto-generate and maintain Unity Catalog table/column comments for 6,100+ objects. Keep metadata in sync with actual schema.
# MAGIC
# MAGIC **Output:** ALTER TABLE/COLUMN COMMENT statements, coverage reports.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Documentation sync execution
DOC_SYNC_PROMPT = """You are a Metadata Documentation Engineer. Generate Unity Catalog COMMENT statements.

For each table/column, generate business-friendly descriptions based on:
- Table name patterns (fact_, dim_, stg_)
- Column name patterns (_sk, _id, _date, _amt, _qty, _flag, _code)
- Source system context (Oracle EBS, Salesforce, ASCP, HCM)
- Domain knowledge (AP = Accounts Payable, AR = Accounts Receivable)

Generate:
1. ALTER TABLE catalog.schema.table SET COMMENT = 'Business description';
2. ALTER TABLE catalog.schema.table ALTER COLUMN col COMMENT 'Description';

Rules:
- Be specific: "Invoice header from Oracle EBS AP module" not "A table"
- Include grain: "One row per invoice line per distribution"
- Note SK source: "Surrogate key generated from xxhash64(vendor_id|org_id)"
- Flag audit columns: "ETL metadata: load timestamp"
- Mention source: "Sourced from Oracle EBS AP_INVOICES_ALL"
"""

# Find tables missing comments
df_missing = spark.sql(f"""
SELECT 
    table_catalog, table_schema, table_name, comment,
    CASE WHEN comment IS NULL OR comment = '' THEN 'MISSING' ELSE 'HAS_COMMENT' END as status
FROM {CATALOG}.information_schema.tables
WHERE table_schema NOT IN ('information_schema')
ORDER BY status, table_schema, table_name
""")

missing_count = df_missing.filter("status = 'MISSING'").count()
total_count = df_missing.count()
print(f"📊 Comment coverage: {total_count - missing_count}/{total_count} tables ({round((total_count - missing_count)*100/max(total_count,1), 1)}%)")

# Get sample of tables needing comments for LLM
sample_tables = df_missing.filter("status = 'MISSING'").limit(20).collect()
table_list = "\n".join([f"- {r['table_catalog']}.{r['table_schema']}.{r['table_name']}" for r in sample_tables])

run_id = generate_run_id()
result = call_agent("data_engineer", DOC_SYNC_PROMPT, f"Generate COMMENT statements for these tables:\n\n{table_list}", max_tokens=4000)
save_agent_output("documentation_sync", run_id, "comment_statements", result, {"missing_comments": missing_count, "total_tables": total_count})
print(result)
print(f"\n✅ Agent 35 (Documentation Sync) completed | Run ID: {run_id}")