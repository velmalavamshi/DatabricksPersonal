# Databricks notebook source
# DBTITLE 1,Workspace Scanner
# MAGIC %md
# MAGIC # Agent 01 — Workspace Scanner (W2)
# MAGIC
# MAGIC **Purpose:** Scans a target workspace via system tables to produce a comprehensive data profile: table inventory, job health, cost breakdown, user activity, and ML/AI footprint.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W2 (Value Discovery) |
# MAGIC | Inputs | workspace_id (parameter), system tables |
# MAGIC | Outputs | Scan results dict (passed to scorer/assessor) |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_vd_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Parameters and Setup
# ======================================================================
# STEP 1 — PARAMETERS
# ======================================================================

AGENT_NAME = "01_workspace_scanner"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)

# Target workspace to scan (default: DEV)
dbutils.widgets.text("target_workspace_id", "6617965257274108", "Target Workspace ID")
dbutils.widgets.text("target_catalog", "mde_dev", "Target Catalog")

TARGET_WS_ID = dbutils.widgets.get("target_workspace_id")
TARGET_CATALOG = dbutils.widgets.get("target_catalog")

print(f"\U0001f50d Workspace Scanner starting")
print(f"   Target workspace: {TARGET_WS_ID}")
print(f"   Target catalog: {TARGET_CATALOG}")
print(f"   Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Table Inventory Scan
# ======================================================================
# STEP 2 — TABLE INVENTORY
# ======================================================================

table_scan_df = spark.sql(SCAN_QUERIES['table_summary'].format(catalog=TARGET_CATALOG))
table_scan = table_scan_df.collect()

total_tables = sum(r['table_count'] for r in table_scan)
total_schemas = len(table_scan)
total_managed = sum(r['managed'] for r in table_scan)
total_views = sum(r['views'] for r in table_scan)

# Identify layers (Bronze/Silver/Gold)
bronze_schemas = [r for r in table_scan if r['table_schema'].startswith('stg_') or 'bronze' in r['table_schema'].lower()]
silver_schemas = [r for r in table_scan if 'silver' in r['table_schema'].lower() or r['table_schema'].startswith('vw_')]
gold_schemas = [r for r in table_scan if 'gold' in r['table_schema'].lower() or 'platinum' in r['table_schema'].lower()]

scan_results = {
    "workspace_id": TARGET_WS_ID,
    "catalog": TARGET_CATALOG,
    "scan_time": start_time.isoformat(),
    "tables": {
        "total": total_tables,
        "schemas": total_schemas,
        "managed": total_managed,
        "views": total_views,
        "external": total_tables - total_managed - total_views,
        "bronze_tables": sum(r['table_count'] for r in bronze_schemas),
        "silver_tables": sum(r['table_count'] for r in silver_schemas),
        "gold_tables": sum(r['table_count'] for r in gold_schemas),
    },
    "top_schemas": [{"schema": r['table_schema'], "count": r['table_count']} for r in table_scan[:10]],
}

print(f"\n\U0001f4ca Table Inventory:")
print(f"   Total tables: {total_tables:,} across {total_schemas} schemas")
print(f"   Managed: {total_managed:,} | Views: {total_views:,} | External: {total_tables - total_managed - total_views:,}")
print(f"   Bronze: {scan_results['tables']['bronze_tables']:,} | Silver: {scan_results['tables']['silver_tables']:,} | Gold: {scan_results['tables']['gold_tables']:,}")

# COMMAND ----------

# DBTITLE 1,STEP 3: Job Health Scan
# ======================================================================
# STEP 3 — JOB HEALTH (30 days)
# ======================================================================

try:
    job_health_df = spark.sql(SCAN_QUERIES['job_health_30d'].format(workspace_id=TARGET_WS_ID))
    job_row = job_health_df.collect()[0]
    
    scan_results["jobs"] = {
        "total_runs_30d": int(job_row['total_runs']),
        "success_30d": int(job_row['success']),
        "failed_30d": int(job_row['failed']),
        "success_rate_pct": float(job_row['success_rate_pct'] or 0),
        "avg_duration_min": float(job_row['avg_duration_min'] or 0),
    }
    print(f"\n\U0001f4c8 Job Health (30d):")
    print(f"   Total runs: {scan_results['jobs']['total_runs_30d']:,}")
    print(f"   Success rate: {scan_results['jobs']['success_rate_pct']}%")
    print(f"   Failed: {scan_results['jobs']['failed_30d']:,}")
    print(f"   Avg duration: {scan_results['jobs']['avg_duration_min']:.1f} min")
except Exception as e:
    scan_results["jobs"] = {"error": str(e)[:100]}
    print(f"\u26a0\ufe0f Job health scan failed: {e}")

# COMMAND ----------

# DBTITLE 1,STEP 4: Cost Scan
# ======================================================================
# STEP 4 — COST BREAKDOWN (30 days)
# ======================================================================

try:
    cost_df = spark.sql(SCAN_QUERIES['cost_30d'].format(workspace_id=TARGET_WS_ID))
    cost_rows = cost_df.collect()
    
    total_cost_30d = sum(float(r['cost_usd']) for r in cost_rows)
    total_dbus_30d = sum(float(r['dbus']) for r in cost_rows)
    
    scan_results["cost"] = {
        "total_cost_30d_usd": round(total_cost_30d, 2),
        "total_dbus_30d": round(total_dbus_30d, 0),
        "annual_run_rate_usd": round(total_cost_30d * 12, 2),
        "top_skus": [{"sku": r['sku_name'], "cost": float(r['cost_usd']), "dbus": float(r['dbus'])} for r in cost_rows[:5]],
        "product_breakdown": {},
    }
    
    # Group by product
    for r in cost_rows:
        product = r['billing_origin_product'] or 'OTHER'
        scan_results["cost"]["product_breakdown"][product] = \
            scan_results["cost"]["product_breakdown"].get(product, 0) + float(r['cost_usd'])
    
    print(f"\n\U0001f4b0 Cost (30d):")
    print(f"   Total: ${total_cost_30d:,.2f} ({total_dbus_30d:,.0f} DBUs)")
    print(f"   Annual run rate: ${total_cost_30d * 12:,.0f}")
    print(f"   Top SKUs:")
    for r in cost_rows[:3]:
        print(f"     ${float(r['cost_usd']):>8,.2f} | {r['sku_name']}")
except Exception as e:
    scan_results["cost"] = {"error": str(e)[:100]}
    print(f"\u26a0\ufe0f Cost scan failed: {e}")

# COMMAND ----------

# DBTITLE 1,STEP 5: ML/AI Footprint
# ======================================================================
# STEP 5 — ML/AI FOOTPRINT
# ======================================================================

ml_footprint = {}

# Check for MLflow experiments
try:
    exp_count = spark.sql(f"""
        SELECT COUNT(DISTINCT experiment_id) as cnt
        FROM system.mlflow.experiments
    """).collect()[0]['cnt']
    ml_footprint['mlflow_experiments'] = int(exp_count)
except:
    ml_footprint['mlflow_experiments'] = 0

# Check for model serving endpoints
try:
    endpoints = spark.sql("""
        SELECT COUNT(*) as cnt FROM system.serving.served_entities
    """).collect()[0]['cnt']
    ml_footprint['serving_endpoints'] = int(endpoints)
except:
    ml_footprint['serving_endpoints'] = 0

# Check for Vector Search usage (via billing)
try:
    vs_cost = spark.sql(f"""
        SELECT COALESCE(SUM(u.usage_quantity), 0) as dbus
        FROM system.billing.usage u
        WHERE u.workspace_id = '{TARGET_WS_ID}'
          AND u.usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
          AND u.sku_name LIKE '%REAL_TIME_INFERENCE%'
    """).collect()[0]['dbus']
    ml_footprint['vector_search_dbus_30d'] = float(vs_cost)
except:
    ml_footprint['vector_search_dbus_30d'] = 0

# Check for GenAI model usage
try:
    genai_cost = spark.sql(f"""
        SELECT COALESCE(SUM(u.usage_quantity), 0) as dbus
        FROM system.billing.usage u
        WHERE u.workspace_id = '{TARGET_WS_ID}'
          AND u.usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
          AND (u.sku_name LIKE '%MODEL_SERVING%' OR u.sku_name LIKE '%ANTHROPIC%' OR u.sku_name LIKE '%OPENAI%')
    """).collect()[0]['dbus']
    ml_footprint['genai_dbus_30d'] = float(genai_cost)
except:
    ml_footprint['genai_dbus_30d'] = 0

scan_results["ml_ai"] = ml_footprint

print(f"\n\U0001f916 ML/AI Footprint:")
print(f"   MLflow experiments: {ml_footprint.get('mlflow_experiments', 0)}")
print(f"   Serving endpoints: {ml_footprint.get('serving_endpoints', 0)}")
print(f"   Vector Search DBUs (30d): {ml_footprint.get('vector_search_dbus_30d', 0):,.0f}")
print(f"   GenAI model DBUs (30d): {ml_footprint.get('genai_dbus_30d', 0):,.0f}")

# COMMAND ----------

# DBTITLE 1,STEP 6: Summary and Output
# ======================================================================
# STEP 6 — SUMMARY & PUBLISH RESULTS
# ======================================================================

end_time = datetime.now(timezone.utc)
scan_results["duration_sec"] = round((end_time - start_time).total_seconds(), 1)
scan_results["run_id"] = run_id

print("\n" + "=" * 60)
print(f"\U0001f50d WORKSPACE SCAN COMPLETE")
print("=" * 60)
print(f"  Workspace: {TARGET_WS_ID}")
print(f"  Catalog: {TARGET_CATALOG}")
print(f"  Tables: {scan_results['tables']['total']:,}")
print(f"  Schemas: {scan_results['tables']['schemas']}")
print(f"  Cost (30d): ${scan_results.get('cost', {}).get('total_cost_30d_usd', 0):,.2f}")
print(f"  Job success rate: {scan_results.get('jobs', {}).get('success_rate_pct', 'N/A')}%")
print(f"  Duration: {scan_results['duration_sec']}s")
print("=" * 60)

# Store results for downstream agents (scorer, assessor)
# In production, this would write to nexus_agent_memory
WORKSPACE_SCAN_RESULTS = scan_results
print(f"\n\u2705 Results stored in WORKSPACE_SCAN_RESULTS variable")