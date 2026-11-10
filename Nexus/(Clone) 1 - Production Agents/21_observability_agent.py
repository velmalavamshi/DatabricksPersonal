# Databricks notebook source
# DBTITLE 1,Observability Agent
# MAGIC %md
# MAGIC # Agent 21 — Observability
# MAGIC
# MAGIC **Purpose:** Monitor job latency, SLA breaches, streaming lag, data freshness, and generate alerting frameworks.
# MAGIC
# MAGIC **Output:** ObservabilityFramework.md, AlertingFramework.md, SLA dashboard queries.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Observability execution
OBSERVABILITY_PROMPT = """You are a Platform Observability Engineer at Hologic. Design and generate:

1. JOB LATENCY MONITORING
   - Baseline duration per job (P50, P90, P99)
   - Alert when duration exceeds 2x P90
   - Query: system.lakeflow.job_run_timeline

2. SLA COMPLIANCE
   - Define SLA per pipeline (e.g., Gold tables refreshed by 7 AM)
   - Track % on-time delivery over 30 days
   - Alert on breach

3. DATA FRESHNESS
   - Check max(etl_load_datetime) per Gold/Platinum table
   - Flag tables stale > 24h (or custom threshold)
   - Query information_schema for table modification times

4. STREAMING LAG (if applicable)
   - Monitor streaming checkpoints
   - Alert on backlog > threshold

5. ALERTING FRAMEWORK
   - SQL Alert definitions (Databricks SQL Alerts)
   - Severity levels and escalation paths
   - PagerDuty/Teams webhook patterns

6. DASHBOARD DESIGN
   - Key metrics for executive dashboard
   - Operational dashboard for engineers
   - KPI boxes: uptime %, fresh tables %, failed jobs count

Generate executable Databricks SQL queries for each monitor.
"""

run_id = generate_run_id()
result = call_agent("data_engineer", OBSERVABILITY_PROMPT, "Design the full observability framework for Hologic's Databricks platform with 6,100+ objects across 16 workspaces.", max_tokens=4000)
save_agent_output("observability", run_id, "observability_framework", result, {})
print(result)
print(f"\n✅ Agent 21 (Observability) completed | Run ID: {run_id}")