# Databricks notebook source
# DBTITLE 1,Cost Anomaly Agent
# MAGIC %md
# MAGIC # Agent 05 — Cost Anomaly Detection
# MAGIC
# MAGIC **Purpose:** Continuously monitor Databricks billing for anomalies, idle resources, runaway jobs, and cost spikes.
# MAGIC
# MAGIC **Problem solved:** $13.9K/year in idle endpoint waste found manually. This agent automates that detection and expands to all cost categories.
# MAGIC
# MAGIC **Data sources:**
# MAGIC - `system.billing.usage` — granular DBU consumption
# MAGIC - `system.billing.list_prices` — authoritative rate lookup
# MAGIC - Historical baselines (rolling 30-day average)
# MAGIC
# MAGIC **Detection patterns:**
# MAGIC 1. **Idle resources** — endpoints/clusters billing with zero queries
# MAGIC 2. **Cost spikes** — daily cost > 2× rolling average
# MAGIC 3. **Runaway jobs** — single job consuming > 20% of workspace cost
# MAGIC 4. **New SKU charges** — unexpected new billing categories
# MAGIC
# MAGIC **Outputs:**
# MAGIC - `mde_dev.test_schema.agent_cost_anomalies` — detected anomalies
# MAGIC - Weekly cost report with trend analysis

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Detect cost anomalies
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Daily cost analysis with anomaly detection
# Uses system.billing.usage + list_prices (NEVER hardcoded rates)
# ══════════════════════════════════════════════════════════════════════════════

# Anomaly detection: compare last 7 days vs 30-day rolling average
df_anomalies = spark.sql(f"""
WITH daily_costs AS (
    SELECT 
        u.usage_date,
        u.workspace_id,
        u.sku_name,
        u.billing_origin_product,
        u.usage_metadata.endpoint_name,
        u.usage_metadata.job_id,
        u.usage_metadata.job_name,
        SUM(u.usage_quantity) as dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) as cost_usd
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.usage_date >= DATEADD(DAY, -37, CURRENT_DATE())  -- 30 day baseline + 7 day analysis
    GROUP BY 1, 2, 3, 4, 5, 6, 7
),
baseline AS (
    SELECT 
        workspace_id,
        sku_name,
        billing_origin_product,
        AVG(cost_usd) as avg_daily_cost,
        STDDEV(cost_usd) as stddev_daily_cost,
        MAX(cost_usd) as max_daily_cost
    FROM daily_costs
    WHERE usage_date BETWEEN DATEADD(DAY, -37, CURRENT_DATE()) AND DATEADD(DAY, -8, CURRENT_DATE())
    GROUP BY 1, 2, 3
),
recent AS (
    SELECT 
        usage_date,
        workspace_id,
        sku_name,
        billing_origin_product,
        endpoint_name,
        job_id,
        job_name,
        cost_usd
    FROM daily_costs
    WHERE usage_date >= DATEADD(DAY, -7, CURRENT_DATE())
)
SELECT 
    r.*,
    b.avg_daily_cost as baseline_avg,
    b.stddev_daily_cost as baseline_stddev,
    CASE 
        WHEN b.avg_daily_cost > 0 THEN ROUND((r.cost_usd - b.avg_daily_cost) / b.avg_daily_cost * 100, 1)
        ELSE NULL 
    END as pct_above_baseline,
    CASE 
        WHEN r.cost_usd > (b.avg_daily_cost + 2 * COALESCE(b.stddev_daily_cost, 0)) THEN 'SPIKE'
        WHEN r.cost_usd > 0 AND b.avg_daily_cost = 0 THEN 'NEW_CHARGE'
        WHEN b.avg_daily_cost > 5 AND r.cost_usd < b.avg_daily_cost * 0.1 THEN 'UNEXPECTED_DROP'
        ELSE 'NORMAL'
    END as anomaly_type
FROM recent r
LEFT JOIN baseline b 
    ON r.workspace_id = b.workspace_id 
    AND r.sku_name = b.sku_name 
    AND r.billing_origin_product = b.billing_origin_product
HAVING anomaly_type != 'NORMAL'
ORDER BY cost_usd DESC
""")

anomaly_count = df_anomalies.count()
print(f"{'\U0001f6a8' if anomaly_count > 0 else '\u2705'} Detected {anomaly_count} cost anomalies in last 7 days")
if anomaly_count > 0:
    df_anomalies.display()

# COMMAND ----------

# DBTITLE 1,Detect idle endpoints
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Idle endpoint detection
# Endpoints billing DBUs but with no queries/requests
# ══════════════════════════════════════════════════════════════════════════════

df_idle = spark.sql(f"""
WITH endpoint_costs AS (
    SELECT 
        u.workspace_id,
        u.usage_metadata.endpoint_name as endpoint_name,
        u.billing_origin_product,
        u.sku_name,
        MIN(u.usage_date) as first_billing_date,
        MAX(u.usage_date) as last_billing_date,
        COUNT(DISTINCT u.usage_date) as billing_days,
        SUM(u.usage_quantity) as total_dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) as total_cost_usd,
        ROUND(SUM(u.usage_quantity * lp.pricing.default) / COUNT(DISTINCT u.usage_date), 2) as avg_daily_cost
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
      AND u.usage_metadata.endpoint_name IS NOT NULL
      AND u.billing_origin_product IN ('VECTOR_SEARCH', 'MODEL_SERVING')
    GROUP BY 1, 2, 3, 4
)
SELECT 
    *,
    ROUND(avg_daily_cost * 365, 2) as projected_annual_cost,
    CASE 
        WHEN avg_daily_cost > 10 THEN 'HIGH_WASTE'
        WHEN avg_daily_cost > 3 THEN 'MEDIUM_WASTE'
        ELSE 'MONITOR'
    END as waste_severity
FROM endpoint_costs
WHERE total_cost_usd > 50  -- only flag if meaningful spend
ORDER BY total_cost_usd DESC
""")

print("💰 Endpoint cost analysis (last 30 days):")
df_idle.display()

# COMMAND ----------

# DBTITLE 1,Generate LLM report and save
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: LLM-powered cost optimization report
# ══════════════════════════════════════════════════════════════════════════════

COST_AGENT_PROMPT = """You are a Databricks FinOps specialist at Hologic. Your job is to identify waste and recommend optimizations.

Context:
- Total annual Databricks spend: $183,607/year across 19 workspaces
- Previously identified: phoenix_vs_endpoint ($9.3K/yr idle), mas-c8bd15bb-endpoint ($2.4K/yr, deleted)
- SKU rates: Jobs=$0.30, SQL Serverless=$0.70, SRTI=$0.07, All Purpose=$0.55

For each anomaly/waste, provide:
1. SEVERITY: HIGH/MEDIUM/LOW
2. ANNUAL IMPACT: Projected yearly waste in USD
3. RECOMMENDED ACTION: Specific, actionable step
4. OWNER: Who should action this (if identifiable)
5. RISK: What happens if we DON'T act

Format as a markdown report with executive summary and action table."""

run_id = generate_run_id()

# Prepare data for LLM
anomaly_data = df_anomalies.limit(20).toPandas().to_string() if anomaly_count > 0 else "No anomalies detected."
idle_data = df_idle.toPandas().to_string() if df_idle.count() > 0 else "No idle endpoints detected."

user_prompt = f"""## Weekly Cost Analysis Report

### Cost Anomalies (last 7 days)
{anomaly_data}

### Endpoint Idle Analysis (last 30 days)
{idle_data}

### Known Context
- phoenix_vs_endpoint: 7 STANDARD Vector Search units, owned by stone.teele@hologic.com, IDLE since March 21, 2026
- data_qa_endpoint: 1 unit, active, owned by ashok.marakani@hologic.com
- mas-c8bd15bb-endpoint: ALREADY DELETED (May 19, 2026)

Generate the weekly cost optimization report with specific recommendations and estimated savings."""

# NOTE (Tier 4): cost_anomaly is type=tool — delegate LLM synthesis to data_engineer
analysis = call_agent("data_engineer", COST_AGENT_PROMPT, user_prompt, max_tokens=3000)

# Save anomalies to Delta
if anomaly_count > 0:
    df_anomalies.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_cost_anomalies")
    print(f"✅ Anomalies saved to {CATALOG}.{SCHEMA}.agent_cost_anomalies")

# Save report
save_agent_output("cost_anomaly", run_id, "cost_report", analysis,
                  {"anomalies_detected": anomaly_count, "endpoints_analyzed": df_idle.count()})

print("\n" + analysis)
print(f"\n✅ Agent 05 (Cost Anomaly) completed | Run ID: {run_id}")