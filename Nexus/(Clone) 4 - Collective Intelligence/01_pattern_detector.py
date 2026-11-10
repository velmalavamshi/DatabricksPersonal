# Databricks notebook source
# DBTITLE 1,Pattern Detector
# MAGIC %md
# MAGIC # Agent 01 — Pattern Detector (W4)
# MAGIC
# MAGIC **Purpose:** Mines 90 days of system table history to detect recurring patterns: chronic job failures, cascade chains, time-correlated clusters, cost spikes, and performance degradation.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W4 (Collective Intelligence) |
# MAGIC | Schedule | Weekly (Sunday 02:00 UTC) |
# MAGIC | Inputs | system.lakeflow.job_run_timeline, system.billing.usage |
# MAGIC | Outputs | Detected patterns (JSON), published to event bus |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_ci_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Recurring Failure Detection
# ======================================================================
# STEP 1 — RECURRING FAILURE DETECTION
# Jobs that fail 3+ times with a detectable pattern
# ======================================================================

AGENT_NAME = "01_pattern_detector"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)
detected_patterns = []

print(f"\U0001f50d Pattern Detector starting — {start_time.strftime('%Y-%m-%d %H:%M UTC')}")

# Query 90-day failure history
failures_df = spark.sql(CI_QUERIES['failure_history_90d'])
failure_count = failures_df.count()
print(f"   Analyzing {failure_count:,} failures over 90 days...")

# Find chronic failures (same job_id failing 3+ times)
chronic_df = failures_df.groupBy("job_id", "run_name").agg(
    F.count("*").alias("failure_count"),
    F.collect_list("period_start_time").alias("failure_times"),
    F.collect_list("dow").alias("failure_days"),
    F.collect_list("hour_of_day").alias("failure_hours"),
).filter(F.col("failure_count") >= PATTERN_TYPES['recurring_failure']['min_occurrences'])

chronic_jobs = chronic_df.collect()

for job in chronic_jobs[:15]:  # Cap analysis at top 15
    days = job['failure_days']
    hours = job['failure_hours']
    
    # Detect day-of-week pattern
    from collections import Counter
    dow_counts = Counter(days)
    most_common_dow = dow_counts.most_common(1)[0]
    dow_concentration = most_common_dow[1] / len(days)
    
    # Detect hour pattern
    hour_counts = Counter(hours)
    most_common_hour = hour_counts.most_common(1)[0]
    hour_concentration = most_common_hour[1] / len(hours)
    
    pattern = {
        "type": "recurring_failure",
        "job_id": job['job_id'],
        "job_name": job['run_name'] or f"Job {job['job_id']}",
        "failure_count_90d": job['failure_count'],
        "day_pattern": {"most_common_day": most_common_dow[0], "concentration": round(dow_concentration, 2)},
        "hour_pattern": {"most_common_hour": most_common_hour[0], "concentration": round(hour_concentration, 2)},
        "is_periodic": dow_concentration > 0.5 or hour_concentration > 0.5,
        "severity": "HIGH" if job['failure_count'] > 10 else "MEDIUM",
    }
    detected_patterns.append(pattern)

print(f"\n   Recurring failures: {len(chronic_jobs)} chronic jobs detected")
for p in detected_patterns[:5]:
    periodic_tag = " [PERIODIC]" if p['is_periodic'] else ""
    print(f"     {p['job_name'][:40]:<42} {p['failure_count_90d']}x{periodic_tag}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Performance Degradation Detection
# ======================================================================
# STEP 2 — PERFORMANCE DEGRADATION DETECTION
# Jobs getting slower over time (linear regression on duration)
# ======================================================================

duration_df = spark.sql(CI_QUERIES['duration_trends_90d'])

# Group by job and compute trend
job_trends = duration_df.groupBy("job_id", "run_name").agg(
    F.count("*").alias("data_points"),
    F.min("avg_duration_sec").alias("min_duration"),
    F.max("avg_duration_sec").alias("max_duration"),
    F.avg("avg_duration_sec").alias("avg_duration"),
    F.min("run_date").alias("first_date"),
    F.max("run_date").alias("last_date"),
).filter(F.col("data_points") >= PATTERN_TYPES['performance_degradation']['min_data_points'])

degrading_jobs = []
for row in job_trends.collect():
    if row['max_duration'] and row['min_duration'] and row['min_duration'] > 0:
        growth_ratio = row['max_duration'] / row['min_duration']
        if growth_ratio > 1.5:  # 50%+ slower
            degrading_jobs.append({
                "type": "performance_degradation",
                "job_id": row['job_id'],
                "job_name": row['run_name'] or f"Job {row['job_id']}",
                "data_points": row['data_points'],
                "min_duration_sec": round(float(row['min_duration']), 1),
                "max_duration_sec": round(float(row['max_duration']), 1),
                "growth_ratio": round(growth_ratio, 2),
                "severity": "HIGH" if growth_ratio > 3.0 else "MEDIUM",
            })

# Sort by growth ratio
degrading_jobs.sort(key=lambda x: x['growth_ratio'], reverse=True)
detected_patterns.extend(degrading_jobs[:10])

print(f"\n   Performance degradation: {len(degrading_jobs)} jobs getting slower")
for d in degrading_jobs[:5]:
    print(f"     {d['job_name'][:40]:<42} {d['growth_ratio']:.1f}x slower")

# COMMAND ----------

# DBTITLE 1,STEP 3: Cost Spike Detection
# ======================================================================
# STEP 3 — COST SPIKE DETECTION
# Days where cost exceeds 2.5 standard deviations from mean
# ======================================================================

cost_df = spark.sql(CI_QUERIES['cost_daily_60d'])

# Aggregate daily total cost
daily_cost = cost_df.groupBy("usage_date").agg(
    F.sum("cost_usd").alias("daily_cost")
).orderBy("usage_date").toPandas()

if len(daily_cost) > 7:
    mean_cost = daily_cost['daily_cost'].mean()
    std_cost = daily_cost['daily_cost'].std()
    threshold = mean_cost + (PATTERN_TYPES['cost_spike']['std_dev_threshold'] * std_cost)
    
    spikes = daily_cost[daily_cost['daily_cost'] > threshold]
    
    if len(spikes) > 0:
        # Check for periodicity in spikes
        spike_days = [d.day for d in spikes['usage_date']]
        spike_dows = [d.weekday() for d in spikes['usage_date']]
        
        cost_pattern = {
            "type": "cost_spike",
            "spike_count_60d": len(spikes),
            "mean_daily_cost": round(mean_cost, 2),
            "threshold": round(threshold, 2),
            "max_spike_cost": round(float(spikes['daily_cost'].max()), 2),
            "spike_dates": [str(d) for d in spikes['usage_date'].tolist()[:5]],
            "severity": "HIGH" if len(spikes) > 3 else "MEDIUM",
        }
        detected_patterns.append(cost_pattern)
        print(f"\n   Cost spikes: {len(spikes)} days above ${threshold:.2f} (mean: ${mean_cost:.2f})")
    else:
        print(f"\n   Cost spikes: None detected (threshold: ${threshold:.2f})")
else:
    print("\n   Cost analysis: Insufficient data (< 7 days)")

# COMMAND ----------

# DBTITLE 1,STEP 4: Summary and Publish
# ======================================================================
# STEP 4 — SUMMARY & PUBLISH
# ======================================================================

end_time = datetime.now(timezone.utc)
duration_sec = (end_time - start_time).total_seconds()

# Categorize patterns
pattern_summary = {}
for p in detected_patterns:
    ptype = p['type']
    pattern_summary[ptype] = pattern_summary.get(ptype, 0) + 1

print("\n" + "=" * 60)
print(f"\U0001f50d PATTERN DETECTION COMPLETE")
print("=" * 60)
print(f"  Total patterns detected: {len(detected_patterns)}")
for ptype, count in pattern_summary.items():
    print(f"    {ptype}: {count}")
print(f"  Duration: {duration_sec:.1f}s")
print(f"  Run ID: {run_id}")
print("=" * 60)

# Store for downstream agents
DETECTED_PATTERNS = detected_patterns
print(f"\n\u2705 {len(detected_patterns)} patterns stored in DETECTED_PATTERNS")