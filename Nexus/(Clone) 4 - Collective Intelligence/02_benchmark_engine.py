# Databricks notebook source
# DBTITLE 1,Benchmark Engine
# MAGIC %md
# MAGIC # Agent 02 — Benchmark Engine (W4)
# MAGIC
# MAGIC **Purpose:** Compares current workspace metrics against defined benchmarks. Produces a scorecard showing where the workspace sits relative to "excellent/good/acceptable/poor" thresholds.

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_ci_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Collect Current Metrics
# ======================================================================
# STEP 1 — COLLECT CURRENT METRICS
# ======================================================================

AGENT_NAME = "02_benchmark_engine"
run_id = str(uuid.uuid4())

# Job success rate (30d)
job_metrics = spark.sql(f"""
    SELECT
        COUNT(*) as total,
        COUNT_IF(result_state = 'SUCCESS') as success,
        ROUND(COUNT_IF(result_state = 'SUCCESS') * 100.0 / COUNT(*), 2) as success_rate,
        ROUND(AVG(CASE WHEN result_state = 'SUCCESS' THEN run_duration_seconds END) / 60.0, 1) as avg_duration_min
    FROM system.lakeflow.job_run_timeline
    WHERE workspace_id = '{DEV_WORKSPACE_ID}'
      AND period_start_time >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
      AND (run_type = 'JOB_RUN' OR run_type = 'SUBMIT_RUN')
""").collect()[0]

# Cost per table (30d)
cost_30d = spark.sql(f"""
    SELECT ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) as total_cost
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.workspace_id = '{DEV_WORKSPACE_ID}'
      AND u.usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
""").collect()[0]['total_cost']

table_count = spark.sql("SELECT COUNT(*) as cnt FROM mde_dev.information_schema.tables").collect()[0]['cnt']
cost_per_table = float(cost_30d or 0) / max(table_count, 1)

current_metrics = {
    "job_success_rate": float(job_metrics['success_rate'] or 0),
    "cost_per_table_monthly": round(cost_per_table, 2),
}

print(f"\U0001f4ca Current Metrics:")
print(f"   Job success rate: {current_metrics['job_success_rate']}%")
print(f"   Cost per table (monthly): ${current_metrics['cost_per_table_monthly']:.2f}")
print(f"   Total cost (30d): ${float(cost_30d or 0):,.2f}")
print(f"   Total tables: {table_count:,}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Score Against Benchmarks
# ======================================================================
# STEP 2 — SCORE AGAINST BENCHMARKS
# ======================================================================

def score_metric(value, benchmark, higher_is_better=True):
    """Score a metric against benchmark thresholds."""
    if higher_is_better:
        if value >= benchmark['excellent']: return 'EXCELLENT', 5
        if value >= benchmark['good']: return 'GOOD', 4
        if value >= benchmark['acceptable']: return 'ACCEPTABLE', 3
        if value >= benchmark['poor']: return 'POOR', 2
        return 'CRITICAL', 1
    else:  # lower is better (e.g., cost, MTTR)
        if value <= benchmark['excellent']: return 'EXCELLENT', 5
        if value <= benchmark['good']: return 'GOOD', 4
        if value <= benchmark['acceptable']: return 'ACCEPTABLE', 3
        if value <= benchmark['poor']: return 'POOR', 2
        return 'CRITICAL', 1

scorecard = []
for metric_id, value in current_metrics.items():
    if metric_id in BENCHMARKS:
        bm = BENCHMARKS[metric_id]
        higher_better = metric_id in ['job_success_rate', 'dq_pass_rate']
        rating, score = score_metric(value, bm, higher_better)
        scorecard.append({
            "metric": metric_id,
            "value": value,
            "unit": bm['unit'],
            "rating": rating,
            "score": score,
            "benchmark_good": bm['good'],
        })

print(f"\n\U0001f3c6 BENCHMARK SCORECARD")
print("=" * 65)
print(f"{'Metric':<28} {'Value':<12} {'Rating':<12} {'Score':<8} {'Benchmark'}")
print("-" * 65)
for s in scorecard:
    icon = {'EXCELLENT': '\u2b50', 'GOOD': '\u2705', 'ACCEPTABLE': '\U0001f7e1', 'POOR': '\U0001f7e0', 'CRITICAL': '\u274c'}[s['rating']]
    print(f"  {icon} {s['metric']:<25} {s['value']:<10}{s['unit']:<4} {s['rating']:<12} {s['score']}/5   (good={s['benchmark_good']})")
print("=" * 65)

avg_score = sum(s['score'] for s in scorecard) / max(len(scorecard), 1)
print(f"\n  Overall Score: {avg_score:.1f}/5")

BENCHMARK_SCORECARD = scorecard