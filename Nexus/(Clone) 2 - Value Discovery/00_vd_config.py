# Databricks notebook source
# DBTITLE 1,W2 Value Discovery — Configuration
# ======================================================================
# 00_vd_config
# W2 Value Discovery — Shared Configuration
# Assessment frameworks, scoring rubrics, maturity model, LLM config
# ======================================================================

import json
import uuid
import requests
from datetime import datetime, timezone
from pyspark.sql import functions as F

# ── Environment ────────────────────────────────────────────────────────
USER_EMAIL = spark.sql("SELECT current_user()").collect()[0][0]
NEXUS_SCHEMA = "mde_dev.test_schema"
NEXUS_EVENTS = f"{NEXUS_SCHEMA}.nexus_agent_events"
NEXUS_REGISTRY = f"{NEXUS_SCHEMA}.nexus_agent_registry"
NEXUS_MEMORY = f"{NEXUS_SCHEMA}.agent_memory"  # Consolidated: shared_token_optimizer creates this

LLM_ENDPOINT = "databricks-claude-sonnet-4-6"
WORKSPACE_URL = spark.conf.get("spark.databricks.workspaceUrl")
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

def call_llm(prompt, max_tokens=2048, temperature=0.1):
    """Call Foundation Model API via OpenAI-compatible REST endpoint."""
    url = f"https://{WORKSPACE_URL}/serving-endpoints/{LLM_ENDPOINT}/invocations"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ── Maturity Model (5 Levels) ──────────────────────────────────────────
MATURITY_LEVELS = {
    1: {"name": "Ad-hoc", "description": "No governance, manual processes, siloed data, no automation"},
    2: {"name": "Defined", "description": "Some standards, basic scheduling, catalog exists but incomplete"},
    3: {"name": "Managed", "description": "Unity Catalog enforced, CI/CD, DQ rules, cost monitoring"},
    4: {"name": "Optimized", "description": "Predictive optimization, auto-scaling, ML in production, full lineage"},
    5: {"name": "Innovating", "description": "AI agents, self-healing pipelines, real-time, GenAI in production"},
}

# ── Assessment Dimensions (radar chart axes) ─────────────────────────
ASSESSMENT_DIMENSIONS = [
    {"id": "data_governance", "name": "Data Governance", "weight": 1.0,
     "indicators": ["Unity Catalog adoption", "PII tagging", "access policies", "data classification"]},
    {"id": "pipeline_maturity", "name": "Pipeline Maturity", "weight": 1.0,
     "indicators": ["CI/CD", "DQ expectations", "idempotency", "error handling", "SLA monitoring"]},
    {"id": "cost_efficiency", "name": "Cost Efficiency", "weight": 0.8,
     "indicators": ["idle compute", "right-sizing", "serverless adoption", "Photon usage"]},
    {"id": "analytics_adoption", "name": "Analytics & BI", "weight": 0.8,
     "indicators": ["dashboard count", "Genie rooms", "SQL warehouse utilization", "self-service"]},
    {"id": "ml_ai_readiness", "name": "ML/AI Readiness", "weight": 1.2,
     "indicators": ["feature store", "MLflow experiments", "model serving", "vector search", "GenAI usage"]},
    {"id": "operational_excellence", "name": "Operational Excellence", "weight": 1.0,
     "indicators": ["job success rate", "MTTR", "alerting", "observability", "documentation"]},
]

# ── Use Case Scoring Rubric ───────────────────────────────────────────
USE_CASE_CRITERIA = {
    "feasibility": {
        "data_readiness": {"weight": 0.3, "description": "Is the required data already in the lakehouse?"},
        "technical_complexity": {"weight": 0.25, "description": "How complex is the implementation? (1=trivial, 5=PhD-level)"},
        "team_capability": {"weight": 0.2, "description": "Does the team have skills to build and maintain?"},
        "infrastructure_fit": {"weight": 0.25, "description": "Does Databricks natively support this pattern?"},
    },
    "impact": {
        "time_savings_hrs": {"weight": 0.2, "description": "Hours saved per month"},
        "cost_reduction": {"weight": 0.25, "description": "Dollar savings or revenue impact per year"},
        "risk_reduction": {"weight": 0.2, "description": "Compliance, audit, or quality risk mitigated"},
        "strategic_alignment": {"weight": 0.2, "description": "Alignment with stated business priorities"},
        "user_reach": {"weight": 0.15, "description": "Number of users/teams who benefit"},
    }
}

# ── Workspace Scan Queries (system tables) ───────────────────────────
SCAN_QUERIES = {
    "table_summary": """
        SELECT table_catalog, table_schema, COUNT(*) as table_count,
               SUM(CASE WHEN table_type = 'MANAGED' THEN 1 ELSE 0 END) as managed,
               SUM(CASE WHEN table_type = 'EXTERNAL' THEN 1 ELSE 0 END) as external,
               SUM(CASE WHEN table_type = 'VIEW' THEN 1 ELSE 0 END) as views
        FROM {catalog}.information_schema.tables
        GROUP BY table_catalog, table_schema
        ORDER BY table_count DESC
    """,
    "job_health_30d": """
        SELECT
            COUNT(*) as total_runs,
            COUNT_IF(result_state = 'SUCCESS') as success,
            COUNT_IF(result_state IN ('FAILED', 'TIMEDOUT', 'ERROR')) as failed,
            ROUND(COUNT_IF(result_state = 'SUCCESS') * 100.0 / COUNT(*), 1) as success_rate_pct,
            ROUND(AVG(run_duration_seconds) / 60.0, 1) as avg_duration_min
        FROM system.lakeflow.job_run_timeline
        WHERE workspace_id = '{workspace_id}'
          AND period_start_time >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
          AND (run_type = 'JOB_RUN' OR run_type = 'SUBMIT_RUN')
    """,
    "cost_30d": """
        SELECT
            u.sku_name,
            u.billing_origin_product,
            SUM(u.usage_quantity) AS dbus,
            ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) AS cost_usd
        FROM system.billing.usage u
        JOIN system.billing.list_prices lp
            ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
        WHERE u.workspace_id = '{workspace_id}'
          AND u.usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
        GROUP BY 1, 2
        ORDER BY cost_usd DESC
    """,
    "user_activity_30d": """
        SELECT
            COUNT(DISTINCT user_identity.email) as active_users,
            COUNT(*) as total_actions
        FROM system.access.audit
        WHERE workspace_id = '{workspace_id}'
          AND event_date >= DATEADD(DAY, -30, CURRENT_DATE())
          AND action_name IN ('commandExecute', 'runCommand', 'submitRun')
    """,
}

# ── Report Templates ────────────────────────────────────────────────────
REPORT_SECTIONS = [
    "Executive Summary",
    "Workspace Scan Results",
    "Maturity Assessment (Radar)",
    "Top AI/ML Use Cases (Scored)",
    "Quick Wins (< 2 weeks)",
    "Strategic Initiatives (3-6 months)",
    "Cost Optimization Opportunities",
    "Risk & Compliance Gaps",
    "Recommended Roadmap",
    "Appendix: Raw Metrics",
]

print("\u2705 W2 Value Discovery config loaded")
print(f"   Maturity levels: {len(MATURITY_LEVELS)}")
print(f"   Assessment dimensions: {len(ASSESSMENT_DIMENSIONS)}")
print(f"   Use case criteria: {sum(len(v) for v in USE_CASE_CRITERIA.values())} factors")
print(f"   Report sections: {len(REPORT_SECTIONS)}")

# COMMAND ----------

# DBTITLE 1,Load shared token optimizer
# MAGIC %run ../shared_token_optimizer