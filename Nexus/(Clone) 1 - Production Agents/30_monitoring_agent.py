# Databricks notebook source
# DBTITLE 1,Monitoring Agent
# MAGIC %md
# MAGIC # Agent 30 — Monitoring
# MAGIC
# MAGIC **Purpose:** Design monitoring dashboards, alerting rules, and SLA tracking for production pipelines.
# MAGIC
# MAGIC **Output:** MonitoringGuide.md, dashboard SQL, alert definitions.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Monitoring execution
MONITORING_PROMPT = """You are a Monitoring Engineer designing dashboards and alerts for Databricks.

1. EXECUTIVE DASHBOARD
   - KPI boxes: Jobs success rate %, Data freshness %, Cost trend
   - Pipeline status (Green/Yellow/Red)
   - Top 5 failing jobs this week

2. OPERATIONAL DASHBOARD
   - Job run timeline (Gantt-style)
   - Duration trends per job (P50/P90)
   - Queue time analysis
   - Cluster utilization heatmap

3. DATA QUALITY DASHBOARD
   - DQ score per table/layer
   - Null rate trends
   - Schema drift events
   - Reconciliation results

4. COST DASHBOARD
   - Daily DBU spend by SKU
   - Top 10 expensive jobs
   - Cost per pipeline/domain
   - Forecast vs actual

5. ALERTING RULES (Databricks SQL Alerts)
   - Job failure: immediate alert
   - Duration > 2x P90: warning
   - Data freshness > SLA: critical
   - Cost spike > 50% over baseline: warning
   - Cluster idle > 30 min: info

Generate complete Databricks SQL queries for each dashboard panel.
Include CREATE ALERT syntax where applicable.
"""

run_id = generate_run_id()
result = call_agent("data_engineer", MONITORING_PROMPT, "Design monitoring dashboards and alerts for Hologic's production pipelines.", max_tokens=4000)
save_agent_output("monitoring", run_id, "monitoring_guide", result, {})
print(result)
print(f"\n✅ Agent 30 (Monitoring) completed | Run ID: {run_id}")