# Databricks notebook source
# DBTITLE 1,Failure Predictor
# MAGIC %md
# MAGIC # Agent 03 — Failure Predictor (W4)
# MAGIC
# MAGIC **Purpose:** Uses historical patterns to predict which jobs are likely to fail in the next 7 days. Identifies seasonal risks (month-end, quarter-end) and resource exhaustion trends.

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_ci_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Build Failure Probability Model
# ======================================================================
# STEP 1 — BUILD FAILURE PROBABILITY MODEL
# Uses day-of-week + day-of-month frequency to predict next failures
# ======================================================================

AGENT_NAME = "03_failure_predictor"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)

# Get failure history grouped by job + temporal features
failure_profile_df = spark.sql(f"""
    SELECT
        job_id, run_name,
        COUNT(*) as total_failures,
        COUNT_IF(DAYOFWEEK(period_start_time) = 1) as sun_fails,
        COUNT_IF(DAYOFWEEK(period_start_time) = 2) as mon_fails,
        COUNT_IF(DAYOFWEEK(period_start_time) = 3) as tue_fails,
        COUNT_IF(DAYOFWEEK(period_start_time) = 4) as wed_fails,
        COUNT_IF(DAYOFWEEK(period_start_time) = 5) as thu_fails,
        COUNT_IF(DAYOFWEEK(period_start_time) = 6) as fri_fails,
        COUNT_IF(DAYOFWEEK(period_start_time) = 7) as sat_fails,
        COUNT_IF(DAY(period_start_time) >= 28) as month_end_fails,
        COUNT_IF(DAY(period_start_time) <= 3) as month_start_fails,
        MAX(period_start_time) as last_failure
    FROM system.lakeflow.job_run_timeline
    WHERE workspace_id = '{DEV_WORKSPACE_ID}'
      AND period_start_time >= DATEADD(DAY, -90, CURRENT_TIMESTAMP())
      AND result_state IN ('FAILED', 'TIMEDOUT', 'ERROR')
      AND (run_type = 'JOB_RUN' OR run_type = 'SUBMIT_RUN')
    GROUP BY job_id, run_name
    HAVING COUNT(*) >= 3
    ORDER BY total_failures DESC
    LIMIT 30
""")

profiles = failure_profile_df.collect()

# Determine what day it is and predict for next 7 days
today = start_time
predictions = []

for profile in profiles:
    # Day-of-week failure distribution
    dow_fails = [profile['sun_fails'], profile['mon_fails'], profile['tue_fails'],
                 profile['wed_fails'], profile['thu_fails'], profile['fri_fails'], profile['sat_fails']]
    total = profile['total_failures']
    
    # For each of the next 7 days, compute failure probability
    for offset in range(PREDICTION_CONFIG['forecast_horizon_days']):
        future_date = today + timedelta(days=offset)
        future_dow = future_date.isoweekday() % 7  # 0=Sun in our array
        future_dom = future_date.day
        
        # Base probability from day-of-week
        dow_prob = dow_fails[future_dow] / max(total, 1)
        
        # Month-end boost
        month_end_boost = 0
        if future_dom >= 28:
            month_end_boost = (profile['month_end_fails'] / max(total, 1)) * 0.3
        elif future_dom <= 3:
            month_end_boost = (profile['month_start_fails'] / max(total, 1)) * 0.2
        
        # Recency boost (failed recently = more likely to fail again)
        days_since_last = (today - profile['last_failure'].replace(tzinfo=timezone.utc)).days if profile['last_failure'] else 999
        recency_boost = max(0, 0.2 - (days_since_last * 0.02))
        
        probability = min(1.0, dow_prob + month_end_boost + recency_boost)
        
        if probability >= PREDICTION_CONFIG['confidence_threshold']:
            # Determine risk level
            risk_level = "LOW"
            for level, config in sorted(PREDICTION_CONFIG['risk_levels'].items(), key=lambda x: x[1]['threshold'], reverse=True):
                if probability >= config['threshold']:
                    risk_level = level
                    break
            
            predictions.append({
                "job_id": profile['job_id'],
                "job_name": profile['run_name'] or f"Job {profile['job_id']}",
                "predicted_date": future_date.strftime('%Y-%m-%d'),
                "day_of_week": future_date.strftime('%A'),
                "probability": round(probability, 3),
                "risk_level": risk_level,
                "historical_failures_90d": profile['total_failures'],
                "days_since_last_failure": days_since_last,
            })

# Sort by probability
predictions.sort(key=lambda x: x['probability'], reverse=True)

print(f"\U0001f52e FAILURE PREDICTIONS (Next 7 Days)")
print("=" * 70)
print(f"{'Date':<12} {'Day':<10} {'Job':<30} {'Prob':<8} {'Risk'}")
print("-" * 70)
for p in predictions[:15]:
    risk_icon = {'CRITICAL': '\U0001f534', 'HIGH': '\U0001f7e0', 'MEDIUM': '\U0001f7e1', 'LOW': '\U0001f7e2'}[p['risk_level']]
    print(f"  {p['predicted_date']:<12} {p['day_of_week']:<10} {p['job_name'][:28]:<30} {p['probability']:<8.1%} {risk_icon} {p['risk_level']}")
print("=" * 70)
print(f"  Total predictions above {PREDICTION_CONFIG['confidence_threshold']:.0%} confidence: {len(predictions)}")

FAILURE_PREDICTIONS = predictions