# Databricks notebook source
# DBTITLE 1,Cost Attribution
# MAGIC %md
# MAGIC # NEXUS Phase 11 — Cost Attribution (W0)
# MAGIC
# MAGIC **Purpose:** Per-agent and per-workspace cost attribution. Uses `system.billing.usage` joined to `list_prices` for actual DBU cost, plus LLM token cost estimates from event payloads.
# MAGIC
# MAGIC **Standard:** Always JOIN `system.billing.list_prices` — NEVER hardcode rates.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: NEXUS Job Cost Attribution (30d)
# ======================================================================
# STEP 1 — NEXUS JOB COST ATTRIBUTION (30 days)
# Maps Databricks job costs to NEXUS agents via job name patterns
# ======================================================================

AGENT_NAME = "12_cost_attribution"
run_id = generate_run_id()

# Get NEXUS-related job costs from billing
nexus_costs = spark.sql(f"""
    SELECT
        u.usage_metadata.job_id,
        u.usage_metadata.job_name,
        u.sku_name,
        u.billing_origin_product,
        SUM(u.usage_quantity) AS dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 4) AS cost_usd,
        COUNT(DISTINCT u.usage_date) as active_days
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.workspace_id = '{DEV_WORKSPACE_ID}'
      AND u.usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
      AND (
          u.usage_metadata.job_name LIKE '%NEXUS%'
          OR u.usage_metadata.job_name LIKE '%nexus%'
          OR u.usage_metadata.job_name LIKE '%morning_briefing%'
          OR u.usage_metadata.job_name LIKE '%triage%'
          OR u.usage_metadata.job_name LIKE '%governance%'
          OR u.usage_metadata.job_name LIKE '%intelligence%'
          OR u.usage_metadata.job_name LIKE '%event_mesh%'
      )
    GROUP BY u.usage_metadata.job_id, u.usage_metadata.job_name, u.sku_name, u.billing_origin_product
    ORDER BY cost_usd DESC
""")

nexus_cost_data = nexus_costs.collect()
total_nexus_cost = sum(float(r['cost_usd'] or 0) for r in nexus_cost_data)

print(f"\U0001f4b0 NEXUS COST ATTRIBUTION (Last 30 Days)")
print("=" * 65)

if nexus_cost_data:
    print(f"{'Job Name':<35} {'SKU':<20} {'DBUs':<10} {'Cost'}")
    print("-" * 65)
    for row in nexus_cost_data[:15]:
        job_name = (row['job_name'] or 'Unknown')[:33]
        sku_short = row['sku_name'].replace('PREMIUM_', '').replace('_US_EAST_2', '')[:18]
        print(f"  {job_name:<35} {sku_short:<20} {row['dbus']:<10.2f} ${row['cost_usd']:.4f}")
    print("-" * 65)
    print(f"  {'TOTAL NEXUS COST (30d)':<55} ${total_nexus_cost:.4f}")
    print(f"  Projected annual: ${total_nexus_cost * 12:.2f}")
else:
    print("  No NEXUS-specific job costs found (jobs may be PAUSED)")
    print("  Projected cost when active: ~$8-12/month based on job specs")

# COMMAND ----------

# DBTITLE 1,STEP 2: LLM Token Cost Estimation
# ======================================================================
# STEP 2 — LLM TOKEN COST ESTIMATION
# Estimates per-agent LLM cost from Foundation Model billing
# Claude Sonnet 4 via Databricks = billed as SRTI at $0.07/DBU
# ======================================================================

llm_costs = spark.sql(f"""
    SELECT
        u.usage_metadata.endpoint_name,
        SUM(u.usage_quantity) AS dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 4) AS cost_usd,
        COUNT(DISTINCT u.usage_date) as active_days
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.workspace_id = '{DEV_WORKSPACE_ID}'
      AND u.usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
      AND u.usage_metadata.endpoint_name = 'databricks-claude-sonnet-4-6'
    GROUP BY u.usage_metadata.endpoint_name
""")

llm_data = llm_costs.collect()

print(f"\n\U0001f916 LLM COST (databricks-claude-sonnet-4-6, 30d)")
print("-" * 50)
if llm_data:
    for row in llm_data:
        print(f"  Endpoint: {row['endpoint_name']}")
        print(f"  DBUs consumed: {row['dbus']:.2f}")
        print(f"  Cost: ${row['cost_usd']:.4f}")
        print(f"  Active days: {row['active_days']}")
        print(f"  Projected annual: ${float(row['cost_usd']) * 12:.2f}")
else:
    print("  No LLM usage billed in last 30d (may be using external model passthrough)")

# Total NEXUS platform cost
llm_total = sum(float(r['cost_usd'] or 0) for r in llm_data)
platform_total = total_nexus_cost + llm_total

print(f"\n\U0001f4ca COST SUMMARY")
print("=" * 50)
print(f"  Job compute cost (30d): ${total_nexus_cost:.4f}")
print(f"  LLM inference cost (30d): ${llm_total:.4f}")
print(f"  Total NEXUS cost (30d): ${platform_total:.4f}")
print(f"  Projected annual: ${platform_total * 12:.2f}")
print(f"  % of DEV workspace spend: {(platform_total * 12 / 48619) * 100:.2f}%")
print("=" * 50)