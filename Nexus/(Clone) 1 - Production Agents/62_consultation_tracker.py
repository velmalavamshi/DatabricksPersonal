# Databricks notebook source
# DBTITLE 1,Consultation Tracker
# MAGIC %md
# MAGIC # Agent 62 — Consultation Tracker (W1)
# MAGIC
# MAGIC **Purpose:** Monitors all open consultations. Tracks response times, detects SLA breaches, triggers CONSULTATION_TIMEOUT events, and produces consultation analytics.

# COMMAND ----------

# DBTITLE 1,Load consultation config
# MAGIC %run ./00_consultation_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Track Open Consultations
# ======================================================================
# STEP 1 — TRACK OPEN CONSULTATIONS & DETECT TIMEOUTS
# ======================================================================

AGENT_NAME = "62_consultation_tracker"
run_id = generate_run_id()
start_time = datetime.now(timezone.utc)

# Find all routed consultations that haven't been responded to
open_consultations = spark.sql(f"""
    SELECT event_id, source_agent, target_agent, payload, priority, created_at
    FROM {NEXUS_EVENTS}
    WHERE event_type = 'CONSULTATION_ROUTED'
      AND status = 'PUBLISHED'
      AND created_at >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
    ORDER BY created_at ASC
""").collect()

# Find responses
responses = spark.sql(f"""
    SELECT payload
    FROM {NEXUS_EVENTS}
    WHERE event_type = 'CONSULTATION_RESPONSE'
      AND created_at >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
""").collect()

# Extract consultation IDs that have been answered
answered_ids = set()
for resp in responses:
    try:
        p = json.loads(resp['payload'])
        answered_ids.add(p.get('consultation_id', ''))
    except:
        pass

# Check each open consultation for timeout
timeouts = []
still_open = []

for req in open_consultations:
    try:
        payload = json.loads(req['payload'])
    except:
        continue
    
    consultation_id = payload.get('consultation_id', '')
    
    if consultation_id in answered_ids:
        continue  # Already responded
    
    # Check if timed out
    timeout_min = payload.get('timeout_minutes', 60)
    elapsed_min = (start_time - req['created_at'].replace(tzinfo=timezone.utc)).total_seconds() / 60
    
    if elapsed_min > timeout_min:
        timeouts.append({
            "consultation_id": consultation_id,
            "caller": payload.get('caller_agent', 'unknown'),
            "specialist": payload.get('specialist_agent', req['target_agent']),
            "question": payload.get('question', '')[:60],
            "priority": req['priority'],
            "elapsed_minutes": round(elapsed_min, 1),
            "timeout_minutes": timeout_min,
        })
    else:
        still_open.append({
            "consultation_id": consultation_id,
            "specialist": payload.get('specialist_agent', req['target_agent']),
            "remaining_min": round(timeout_min - elapsed_min, 1),
            "priority": req['priority'],
        })

print(f"\u23f1\ufe0f CONSULTATION TRACKER")
print("=" * 60)
print(f"  Open consultations: {len(still_open)}")
print(f"  Timed out (SLA breach): {len(timeouts)}")
print(f"  Answered (24h): {len(answered_ids)}")
print("=" * 60)

# COMMAND ----------

# DBTITLE 1,STEP 2: Publish Timeout Events
# ======================================================================
# STEP 2 — PUBLISH TIMEOUT EVENTS & ESCALATE
# ======================================================================

from pyspark.sql.types import StructType, StructField, StringType, TimestampType

timeout_events_published = 0

for t in timeouts:
    timeout_payload = {
        "consultation_id": t['consultation_id'],
        "caller_agent": t['caller'],
        "specialist_agent": t['specialist'],
        "question": t['question'],
        "elapsed_minutes": t['elapsed_minutes'],
        "sla_minutes": t['timeout_minutes'],
        "breach_severity": "CRITICAL" if t['priority'] == 'P1' else "HIGH" if t['priority'] == 'P2' else "MEDIUM",
        "escalation_action": CONSULTATION_SLA[t['priority']]['escalation'],
    }
    
    try:
        event_data = [(
            str(uuid.uuid4()), "CONSULTATION_TIMEOUT", AGENT_NAME, t['caller'],
            "W1", json.dumps(timeout_payload), t['priority'], "PUBLISHED",
            datetime.now(timezone.utc), None, None, run_id, datetime.now(timezone.utc), "NEXUS"
        )]
        schema = StructType([
            StructField("event_id", StringType()), StructField("event_type", StringType()),
            StructField("source_agent", StringType()), StructField("target_agent", StringType()),
            StructField("workspace", StringType()), StructField("payload", StringType()),
            StructField("priority", StringType()), StructField("status", StringType()),
            StructField("created_at", TimestampType()), StructField("consumed_at", TimestampType()),
            StructField("consumed_by", StringType()), StructField("run_id", StringType()),
            StructField("etl_load_datetime", TimestampType()), StructField("etl_source_system", StringType()),
        ])
        spark.createDataFrame(event_data, schema=schema).write.format("delta").mode("append").saveAsTable(NEXUS_EVENTS)
        timeout_events_published += 1
    except Exception as e:
        print(f"  \u26a0\ufe0f Failed to publish timeout for {t['consultation_id'][:8]}: {e}")

if timeouts:
    print(f"\n\u26a0\ufe0f SLA BREACHES:")
    for t in timeouts:
        print(f"  \U0001f534 {t['specialist']} failed to respond to {t['caller']} | {t['elapsed_minutes']:.0f}m (SLA: {t['timeout_minutes']}m) | [{t['priority']}]")
    print(f"\n  Timeout events published: {timeout_events_published}")
else:
    print("\n  \u2705 No SLA breaches — all specialists responding within SLA")

# COMMAND ----------

# DBTITLE 1,STEP 3: Consultation Analytics
# ======================================================================
# STEP 3 — CONSULTATION ANALYTICS (7-day window)
# ======================================================================

consult_analytics = spark.sql(f"""
    SELECT
        target_agent as specialist,
        COUNT(*) as consultations_received,
        COUNT_IF(status = 'CONSUMED') as responded,
        ROUND(AVG(CASE WHEN consumed_at IS NOT NULL
            THEN TIMESTAMPDIFF(SECOND, created_at, consumed_at) END) / 60.0, 1) as avg_response_min
    FROM {NEXUS_EVENTS}
    WHERE event_type IN ('CONSULTATION_ROUTED', 'CONSULTATION_REQUEST')
      AND created_at >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      AND target_agent IS NOT NULL
    GROUP BY target_agent
    ORDER BY consultations_received DESC
""").collect()

print(f"\n\U0001f4ca CONSULTATION ANALYTICS (7d)")
print("=" * 65)
if consult_analytics:
    print(f"{'Specialist':<35} {'Received':<10} {'Responded':<10} {'Avg Response'}")
    print("-" * 65)
    for row in consult_analytics[:10]:
        resp_time = f"{row['avg_response_min']}m" if row['avg_response_min'] else '-'
        print(f"  {row['specialist'][:33]:<35} {row['consultations_received']:<10} {row['responded']:<10} {resp_time}")
else:
    print("  No consultation events in last 7 days (network not yet active)")

print(f"\n\u2705 Consultation tracker complete | Duration: {(datetime.now(timezone.utc) - start_time).total_seconds():.1f}s")