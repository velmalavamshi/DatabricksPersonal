# Databricks notebook source
# DBTITLE 1,W4 Collective Intelligence — Configuration
# ======================================================================
# 00_ci_config
# W4 Collective Intelligence — Shared Configuration
# Pattern detection, benchmarking, failure prediction, insight publishing
# ======================================================================

import json
import uuid
import requests
import numpy as np
from datetime import datetime, timezone, timedelta
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
DEV_WORKSPACE_ID = "6617965257274108"

def call_llm(prompt, max_tokens=2048, temperature=0.1):
    """Call Foundation Model API."""
    url = f"https://{WORKSPACE_URL}/serving-endpoints/{LLM_ENDPOINT}/invocations"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ── Pattern Detection Configuration ─────────────────────────────────
PATTERN_TYPES = {
    "recurring_failure": {
        "description": "Same job fails repeatedly on a predictable schedule",
        "min_occurrences": 3,
        "lookback_days": 30,
        "severity": "HIGH",
    },
    "cascade_failure": {
        "description": "One job failure triggers a chain of downstream failures",
        "min_chain_length": 3,
        "time_window_minutes": 60,
        "severity": "CRITICAL",
    },
    "time_correlation": {
        "description": "Failures cluster at specific times (e.g., month-end, maintenance windows)",
        "min_correlation": 0.7,
        "lookback_days": 90,
        "severity": "MEDIUM",
    },
    "cost_spike": {
        "description": "Cost anomalies that repeat on a cycle",
        "std_dev_threshold": 2.5,
        "lookback_days": 60,
        "severity": "HIGH",
    },
    "performance_degradation": {
        "description": "Gradual increase in job duration over time",
        "slope_threshold": 0.05,  # 5% increase per week
        "min_data_points": 10,
        "severity": "MEDIUM",
    },
}

# ── Benchmark Thresholds ────────────────────────────────────────────
BENCHMARKS = {
    "job_success_rate": {"excellent": 99.0, "good": 95.0, "acceptable": 90.0, "poor": 85.0, "unit": "%"},
    "mttr_minutes": {"excellent": 5, "good": 15, "acceptable": 30, "poor": 60, "unit": "min"},
    "cost_per_table_monthly": {"excellent": 0.5, "good": 2.0, "acceptable": 5.0, "poor": 10.0, "unit": "$"},
    "pipeline_freshness_hours": {"excellent": 1, "good": 4, "acceptable": 12, "poor": 24, "unit": "hrs"},
    "idle_compute_pct": {"excellent": 5, "good": 10, "acceptable": 20, "poor": 30, "unit": "%"},
    "dq_pass_rate": {"excellent": 99.5, "good": 98.0, "acceptable": 95.0, "poor": 90.0, "unit": "%"},
}

# ── Prediction Model Settings ───────────────────────────────────────
PREDICTION_CONFIG = {
    "forecast_horizon_days": 7,       # Predict 7 days ahead
    "training_window_days": 90,       # Use 90 days of history
    "confidence_threshold": 0.75,     # Min confidence to publish prediction
    "seasonal_periods": [7, 14, 30],  # Weekly, bi-weekly, monthly cycles
    "risk_levels": {
        "CRITICAL": {"threshold": 0.9, "color": "#E74C3C"},
        "HIGH": {"threshold": 0.75, "color": "#F39C12"},
        "MEDIUM": {"threshold": 0.5, "color": "#F1C40F"},
        "LOW": {"threshold": 0.0, "color": "#27AE60"},
    },
}

# ── Insight Categories ─────────────────────────────────────────────
INSIGHT_CATEGORIES = [
    {"id": "reliability", "name": "Reliability Insights", "icon": "shield"},
    {"id": "cost", "name": "Cost Intelligence", "icon": "dollar"},
    {"id": "performance", "name": "Performance Trends", "icon": "chart"},
    {"id": "risk", "name": "Risk Predictions", "icon": "warning"},
    {"id": "opportunity", "name": "Optimization Opportunities", "icon": "lightbulb"},
]

# ── System Table Queries for Intelligence ──────────────────────────
CI_QUERIES = {
    "failure_history_90d": f"""
        SELECT
            job_id, run_name, result_state, termination_code,
            period_start_time, run_duration_seconds,
            DAYOFWEEK(period_start_time) as dow,
            HOUR(period_start_time) as hour_of_day,
            DAY(period_start_time) as day_of_month
        FROM system.lakeflow.job_run_timeline
        WHERE workspace_id = '{DEV_WORKSPACE_ID}'
          AND period_start_time >= DATEADD(DAY, -90, CURRENT_TIMESTAMP())
          AND result_state IN ('FAILED', 'TIMEDOUT', 'ERROR')
          AND (run_type = 'JOB_RUN' OR run_type = 'SUBMIT_RUN')
        ORDER BY period_start_time
    """,
    "duration_trends_90d": f"""
        SELECT
            job_id, run_name,
            DATE(period_start_time) as run_date,
            AVG(run_duration_seconds) as avg_duration_sec,
            COUNT(*) as run_count
        FROM system.lakeflow.job_run_timeline
        WHERE workspace_id = '{DEV_WORKSPACE_ID}'
          AND period_start_time >= DATEADD(DAY, -90, CURRENT_TIMESTAMP())
          AND result_state = 'SUCCESS'
          AND (run_type = 'JOB_RUN' OR run_type = 'SUBMIT_RUN')
        GROUP BY job_id, run_name, DATE(period_start_time)
        ORDER BY run_date
    """,
    "cost_daily_60d": f"""
        SELECT
            u.usage_date,
            u.billing_origin_product,
            SUM(u.usage_quantity) AS dbus,
            ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) AS cost_usd
        FROM system.billing.usage u
        JOIN system.billing.list_prices lp
            ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
        WHERE u.workspace_id = '{DEV_WORKSPACE_ID}'
          AND u.usage_date >= DATEADD(DAY, -60, CURRENT_DATE())
        GROUP BY u.usage_date, u.billing_origin_product
        ORDER BY u.usage_date
    """,
}

print("\u2705 W4 Collective Intelligence config loaded")
print(f"   Pattern types: {len(PATTERN_TYPES)}")
print(f"   Benchmark metrics: {len(BENCHMARKS)}")
print(f"   Insight categories: {len(INSIGHT_CATEGORIES)}")
print(f"   Prediction horizon: {PREDICTION_CONFIG['forecast_horizon_days']} days")

# COMMAND ----------

# DBTITLE 1,Load shared token optimizer
# Shared memory + token budget utilities (single source of truth for all folders)
%run ../shared_token_optimizer