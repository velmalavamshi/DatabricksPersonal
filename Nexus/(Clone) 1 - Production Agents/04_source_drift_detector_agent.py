# Databricks notebook source
# DBTITLE 1,Source Drift Detector Agent
# MAGIC %md
# MAGIC # Agent 04 — Source System Drift Detector
# MAGIC
# MAGIC **Purpose:** Proactively detect schema changes across 15+ source systems before they break downstream pipelines.
# MAGIC
# MAGIC **Problem solved:** Chronic job failures (122+/month) often caused by undetected source schema drift. Currently reactive (fix after failure) instead of proactive (detect before failure).
# MAGIC
# MAGIC **Data sources:**
# MAGIC - `system.information_schema.columns` — current schema state
# MAGIC - `mde_dev.test_schema.agent_schema_snapshots` — historical schema state (maintained by this agent)
# MAGIC - `system.lakeflow.job_run_timeline` — correlate drift with failures
# MAGIC
# MAGIC **Outputs:**
# MAGIC - `mde_dev.test_schema.agent_schema_snapshots` — daily schema state capture
# MAGIC - `mde_dev.test_schema.agent_drift_alerts` — detected schema changes
# MAGIC - Markdown report with impact assessment

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Capture current schema snapshot
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Capture current schema state for all staging schemas
# ══════════════════════════════════════════════════════════════════════════════

from pyspark.sql import functions as F

# Focus on staging schemas (source system landing zones)
df_current = spark.sql(f"""
SELECT 
    table_catalog,
    table_schema,
    table_name,
    column_name,
    ordinal_position,
    data_type,
    is_nullable,
    CURRENT_DATE() as snapshot_date
FROM system.information_schema.columns
WHERE table_catalog = '{CATALOG}'
  AND table_schema LIKE 'stg_%'
ORDER BY table_schema, table_name, ordinal_position
""")

print(f"✅ Current snapshot: {df_current.count()} columns across staging schemas")
print(f"   Schemas: {[r[0] for r in df_current.select('table_schema').distinct().collect()]}")

# COMMAND ----------

# DBTITLE 1,Compare with previous snapshot to detect drift
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Compare current schema vs last snapshot
# Detect: new columns, dropped columns, type changes, nullability changes
# ══════════════════════════════════════════════════════════════════════════════

# Check if snapshot table exists
table_exists = spark.catalog.tableExists(f"{CATALOG}.{SCHEMA}.agent_schema_snapshots")

if table_exists:
    # Get the most recent snapshot date
    last_snapshot_date = spark.sql(f"""
        SELECT MAX(snapshot_date) as last_date 
        FROM {CATALOG}.{SCHEMA}.agent_schema_snapshots
    """).collect()[0]["last_date"]
    
    print(f"Previous snapshot found: {last_snapshot_date}")
    
    # Compare: find changes
    df_current.createOrReplaceTempView("current_schema")
    
    df_drift = spark.sql(f"""
    WITH previous AS (
        SELECT * FROM {CATALOG}.{SCHEMA}.agent_schema_snapshots
        WHERE snapshot_date = '{last_snapshot_date}'
    ),
    -- New columns (in current but not in previous)
    new_columns AS (
        SELECT 
            c.table_schema, c.table_name, c.column_name, c.data_type,
            'COLUMN_ADDED' as change_type,
            NULL as old_value,
            c.data_type as new_value
        FROM current_schema c
        LEFT JOIN previous p 
            ON c.table_schema = p.table_schema 
            AND c.table_name = p.table_name 
            AND c.column_name = p.column_name
        WHERE p.column_name IS NULL
    ),
    -- Dropped columns (in previous but not in current)
    dropped_columns AS (
        SELECT 
            p.table_schema, p.table_name, p.column_name, p.data_type,
            'COLUMN_DROPPED' as change_type,
            p.data_type as old_value,
            NULL as new_value
        FROM previous p
        LEFT JOIN current_schema c 
            ON p.table_schema = c.table_schema 
            AND p.table_name = c.table_name 
            AND p.column_name = c.column_name
        WHERE c.column_name IS NULL
    ),
    -- Type changes
    type_changes AS (
        SELECT 
            c.table_schema, c.table_name, c.column_name, c.data_type,
            'TYPE_CHANGED' as change_type,
            p.data_type as old_value,
            c.data_type as new_value
        FROM current_schema c
        JOIN previous p 
            ON c.table_schema = p.table_schema 
            AND c.table_name = p.table_name 
            AND c.column_name = p.column_name
        WHERE c.data_type != p.data_type
    )
    SELECT *, CURRENT_TIMESTAMP() as detected_at FROM new_columns
    UNION ALL
    SELECT *, CURRENT_TIMESTAMP() as detected_at FROM dropped_columns
    UNION ALL
    SELECT *, CURRENT_TIMESTAMP() as detected_at FROM type_changes
    """)
    
    drift_count = df_drift.count()
    print(f"\n{'\U0001f6a8' if drift_count > 0 else '\u2705'} Detected {drift_count} schema changes since {last_snapshot_date}")
    
    if drift_count > 0:
        df_drift.display()
else:
    print("\u2139\ufe0f No previous snapshot found. This is the first run — establishing baseline.")
    drift_count = 0
    df_drift = spark.createDataFrame([], "table_schema STRING, table_name STRING, column_name STRING, data_type STRING, change_type STRING, old_value STRING, new_value STRING, detected_at TIMESTAMP")

# COMMAND ----------

# DBTITLE 1,Assess downstream impact of drift
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: For each drift, find downstream views/tables that reference it
# ══════════════════════════════════════════════════════════════════════════════

run_id = generate_run_id()

if drift_count > 0:
    # Find which views reference the drifted tables
    drifted_tables = df_drift.select("table_schema", "table_name").distinct().collect()
    
    impact_results = []
    for row in drifted_tables:
        schema, table = row["table_schema"], row["table_name"]
        
        # Find downstream consumers
        downstream = spark.sql(f"""
        SELECT 
            view_schema, view_name,
            CONCAT(view_catalog, '.', view_schema, '.', view_name) as downstream_view
        FROM system.information_schema.view_table_usage
        WHERE table_catalog = '{CATALOG}'
          AND table_schema = '{schema}'
          AND table_name = '{table}'
        """).collect()
        
        impact_results.append({
            "source_table": f"{CATALOG}.{schema}.{table}",
            "downstream_count": len(downstream),
            "downstream_views": [r["downstream_view"] for r in downstream[:10]]
        })
    
    print("💥 Impact Assessment:")
    for impact in sorted(impact_results, key=lambda x: -x["downstream_count"]):
        print(f"  {impact['source_table']}: {impact['downstream_count']} downstream views")
        for dv in impact["downstream_views"][:3]:
            print(f"    → {dv}")
else:
    impact_results = []
    print("✅ No drift detected — no impact assessment needed")

# COMMAND ----------

# DBTITLE 1,LLM analysis and save results
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Generate LLM report + persist snapshot and drift alerts
# ══════════════════════════════════════════════════════════════════════════════

# Save current snapshot (append with date for history)
df_current.write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_schema_snapshots")
print(f"✅ Schema snapshot saved to {CATALOG}.{SCHEMA}.agent_schema_snapshots")

# Save drift alerts if any
if drift_count > 0:
    df_drift.write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_drift_alerts")
    print(f"✅ {drift_count} drift alerts saved to {CATALOG}.{SCHEMA}.agent_drift_alerts")
    
    # LLM-powered impact analysis
    DRIFT_PROMPT = """You are a data platform reliability engineer. A source system schema change has been detected.
    Analyze the drift and provide:
    1. SEVERITY: How critical is this change (BREAKING, WARNING, INFO)
    2. IMPACT: Which downstream pipelines/reports will be affected
    3. RECOMMENDED ACTION: What to do immediately
    4. PREVENTION: How to prevent this from causing failures
    Format as markdown."""
    
    drift_summary = df_drift.toPandas().to_string()
    impact_summary = json.dumps(impact_results, indent=2)
    
    user_prompt = f"""Schema drift detected in mde_dev staging schemas:

{drift_summary}

Downstream impact:
{impact_summary}

Provide severity assessment and recommended actions."""
    
    analysis = call_agent("source_drift_detector", DRIFT_PROMPT, user_prompt, max_tokens=2000)
    save_agent_output("source_drift_detector", run_id, "drift_report", analysis,
                      {"changes_detected": drift_count, "tables_affected": len(impact_results)})
    print("\n" + analysis)
else:
    save_agent_output("source_drift_detector", run_id, "drift_report", 
                      "No schema drift detected. All source schemas stable.",
                      {"changes_detected": 0})

print(f"\n✅ Agent 04 (Source Drift Detector) completed | Run ID: {run_id}")