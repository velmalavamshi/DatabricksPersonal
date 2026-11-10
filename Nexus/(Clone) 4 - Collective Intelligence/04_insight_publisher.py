# Databricks notebook source
# DBTITLE 1,Insight Publisher
# MAGIC %md
# MAGIC # Agent 04 — Insight Publisher (W4)
# MAGIC
# MAGIC **Purpose:** Synthesizes patterns, benchmarks, and predictions into a weekly intelligence digest. Publishes insights to the event bus for W1 agents to consume proactively.

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_ci_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Synthesize Intelligence Digest
# ======================================================================
# STEP 1 — SYNTHESIZE WEEKLY INTELLIGENCE DIGEST
# Combines outputs from pattern detector, benchmarks, and predictor
# ======================================================================

AGENT_NAME = "04_insight_publisher"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)

# Gather inputs
try:
    patterns = DETECTED_PATTERNS
except NameError:
    patterns = []

try:
    scorecard = BENCHMARK_SCORECARD
except NameError:
    scorecard = []

try:
    predictions = FAILURE_PREDICTIONS
except NameError:
    predictions = []

# Build digest using LLM
DIGEST_PROMPT = f"""Generate a concise weekly intelligence digest from these findings.

Patterns Detected: {len(patterns)}
Top patterns: {json.dumps(patterns[:5], default=str)[:1500]}

Benchmark Scorecard: {json.dumps(scorecard, default=str)[:500]}

Failure Predictions (next 7 days): {len(predictions)} jobs at risk
Top risks: {json.dumps(predictions[:5], default=str)[:800]}

Generate a digest with these sections:
1. KEY FINDING (the single most important insight this week, 2 sentences)
2. PATTERNS (bullet points of recurring patterns, max 5)
3. PREDICTIONS (what's likely to break this week, max 5)
4. BENCHMARK STATUS (one-line summary of where we stand)
5. RECOMMENDED ACTIONS (3-5 specific actions for the data engineering team)

Keep it concise. Max 400 words total. Use bullet points. No fluff."""

print("Generating weekly intelligence digest...")
digest_text = call_llm(DIGEST_PROMPT, max_tokens=1000, temperature=0.2)

print(f"\n\U0001f4e1 WEEKLY INTELLIGENCE DIGEST")
print("=" * 60)
print(digest_text)
print("=" * 60)

# COMMAND ----------

# DBTITLE 1,STEP 2: Publish to Event Bus
# ======================================================================
# STEP 2 — PUBLISH TO EVENT BUS
# ======================================================================

from pyspark.sql.types import StructType, StructField, StringType, TimestampType

digest_payload = {
    "digest_text": digest_text,
    "patterns_count": len(patterns),
    "predictions_count": len(predictions),
    "benchmark_avg_score": round(sum(s.get('score', 0) for s in scorecard) / max(len(scorecard), 1), 1),
    "top_risk_jobs": [p['job_name'] for p in predictions[:5]],
    "generated_at": start_time.isoformat(),
}

try:
    event_data = [(
        str(uuid.uuid4()), "WEEKLY_INTELLIGENCE_DIGEST", AGENT_NAME, None,
        "W4", json.dumps(digest_payload), "P3", "PUBLISHED",
        start_time, None, None, run_id, datetime.now(timezone.utc), "NEXUS"
    )]
    event_schema = StructType([
        StructField("event_id", StringType(), False),
        StructField("event_type", StringType(), False),
        StructField("source_agent", StringType(), False),
        StructField("target_agent", StringType(), True),
        StructField("workspace", StringType(), False),
        StructField("payload", StringType(), False),
        StructField("priority", StringType(), False),
        StructField("status", StringType(), False),
        StructField("created_at", TimestampType(), False),
        StructField("consumed_at", TimestampType(), True),
        StructField("consumed_by", StringType(), True),
        StructField("run_id", StringType(), True),
        StructField("etl_load_datetime", TimestampType(), False),
        StructField("etl_source_system", StringType(), False),
    ])
    df = spark.createDataFrame(event_data, schema=event_schema)
    df.write.format("delta").mode("append").saveAsTable(NEXUS_EVENTS)
    print(f"\n\u2705 Digest published to event bus (WEEKLY_INTELLIGENCE_DIGEST)")
except Exception as e:
    print(f"\u26a0\ufe0f Event publish failed: {e}")

end_time = datetime.now(timezone.utc)
print(f"\n\u2705 Insight Publisher complete | Duration: {(end_time - start_time).total_seconds():.1f}s")