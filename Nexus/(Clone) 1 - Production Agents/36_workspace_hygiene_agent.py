# Databricks notebook source
# DBTITLE 1,Workspace Hygiene Agent
# MAGIC %md
# MAGIC # Agent 36 — Workspace Hygiene
# MAGIC
# MAGIC **Purpose:** Find orphaned resources, stale tables, unused clusters, abandoned notebooks, and zombie endpoints across all 16 workspaces.
# MAGIC
# MAGIC **Output:** HygieneReport.md — orphaned resources with cleanup recommendations.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Workspace hygiene execution
HYGIENE_PROMPT = """You are a Platform Hygiene Engineer finding waste across Hologic's 16 Databricks workspaces.

Scan for and recommend cleanup of:

1. ORPHANED TABLES
   - Tables with no reads in 90+ days (system.access.table_lineage)
   - Tables with no upstream writes (dead data)
   - Temp tables never cleaned up (_tmp_, _backup_, _old_)

2. STALE RESOURCES
   - Clusters not used in 30+ days
   - Jobs disabled/paused for 60+ days
   - Notebooks not edited in 180+ days
   - Secrets never accessed

3. ZOMBIE ENDPOINTS
   - Vector Search endpoints with zero queries
   - Model Serving endpoints at zero traffic
   - SQL Warehouses with no queries in 14+ days

4. STORAGE WASTE
   - Tables without VACUUM (growing transaction log)
   - Tables without OPTIMIZE (small file problem)
   - Duplicate tables across schemas
   - Tables > 1TB without Liquid Clustering

5. PERMISSION BLOAT
   - Users with admin who don't need it
   - Service principals never used
   - Overly permissive GRANTs

For each finding: Resource, Location, Last Used, Estimated Cost, Recommendation.
"""

# Query for stale tables
df_stale = spark.sql(f"""
SELECT 
    table_catalog, table_schema, table_name,
    DATEDIFF(CURRENT_DATE(), last_altered) as days_since_altered
FROM {CATALOG}.information_schema.tables
WHERE table_type = 'MANAGED'
  AND last_altered < DATEADD(DAY, -90, CURRENT_DATE())
ORDER BY days_since_altered DESC
LIMIT 50
""")

stale_count = df_stale.count()
print(f"🚨 Found {stale_count} tables not modified in 90+ days")

stale_list = "\n".join([f"- {r['table_catalog']}.{r['table_schema']}.{r['table_name']} ({r['days_since_altered']} days stale)" for r in df_stale.limit(20).collect()])

run_id = generate_run_id()
result = call_agent("data_engineer", HYGIENE_PROMPT, f"""Workspace hygiene scan results:

Stale tables (90+ days, top 20):
{stale_list}

Total stale tables: {stale_count}
Total objects in catalog: 6,100+
Workspaces: 16

Generate the full hygiene report with cleanup recommendations and estimated savings.""", max_tokens=3500)
save_agent_output("workspace_hygiene", run_id, "hygiene_report", result, {"stale_tables": stale_count})
print(result)
print(f"\n✅ Agent 36 (Workspace Hygiene) completed | Run ID: {run_id}")