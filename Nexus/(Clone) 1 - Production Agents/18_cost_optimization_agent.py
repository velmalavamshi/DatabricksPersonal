# Databricks notebook source
# DBTITLE 1,Cost Optimization Agent
# MAGIC %md
# MAGIC # Agent 18 — Cost Optimization
# MAGIC
# MAGIC **Purpose:** Analyze cluster sizing, query patterns, and DBU consumption to produce actionable cost reduction recommendations.
# MAGIC
# MAGIC **Output:** CostOptimizationReport.md, DBUOptimizationPlan.md

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Cost optimization execution
COST_OPT_PROMPT = """You are a Databricks FinOps specialist at Hologic. Analyze and recommend cost optimizations:

1. CLUSTER SIZING
   - Right-size under-utilized clusters (< 40% avg CPU)
   - Recommend spot instances for non-SLA workloads
   - Auto-scaling min/max optimization
   - Convert all-purpose to jobs compute where possible ($0.55 → $0.30/DBU)

2. SQL WAREHOUSE OPTIMIZATION
   - Serverless vs Pro warehouse sizing
   - Auto-stop timeout tuning
   - Query routing (small queries to Small WH, large to Medium)

3. STORAGE OPTIMIZATION
   - OPTIMIZE + VACUUM schedules
   - Z-ORDER → Liquid Clustering migration
   - Remove redundant table copies
   - Materialized views vs re-computation

4. PIPELINE EFFICIENCY
   - Batch window consolidation
   - Incremental vs full refresh patterns
   - Photon enablement for eligible workloads

5. ENDPOINT / SERVING
   - Idle endpoint detection (Vector Search, Model Serving)
   - Scale-to-zero configuration
   - SRTI at $0.07/DBU — still expensive when idle 24/7

IMPORTANT: Always calculate costs using system.billing.list_prices join.
Rates: Jobs=$0.30, SQL Serverless=$0.70, All-Purpose=$0.55, SRTI=$0.07/DBU.

For each recommendation provide:
- Current state (what it costs now)
- Recommended state
- Annual savings estimate
- Implementation effort (hours)
- Risk level
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = get_latest_agent_output("data_engineer", "generated_code") or "Analyze cost optimization opportunities for the DEV workspace."

run_id = generate_run_id()
result = call_agent("data_engineer", COST_OPT_PROMPT, f"Produce cost optimization plan for:\n\n{INPUT}", max_tokens=3500)
save_agent_output("cost_optimization", run_id, "cost_report", result, {})
print(result)
print(f"\n✅ Agent 18 (Cost Optimization) completed | Run ID: {run_id}")