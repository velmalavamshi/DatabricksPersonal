# Databricks notebook source
# DBTITLE 1,Consultation Router
# MAGIC %md
# MAGIC # Agent 60 — Consultation Router (W1)
# MAGIC
# MAGIC **Purpose:** Receives CONSULTATION_REQUEST events, identifies the optimal specialist based on source system + capability needed, forwards the request, and tracks response SLA.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Schedule | Triggered by Event Mesh (02_event_mesh) |
# MAGIC | Inputs | CONSULTATION_REQUEST events |
# MAGIC | Outputs | Routed requests to specialists, SLA tracking |

# COMMAND ----------

# DBTITLE 1,Load configs
# MAGIC %run ./00_consultation_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Consume Pending Consultation Requests
# ======================================================================
# STEP 1 — CONSUME PENDING CONSULTATION REQUESTS
# ======================================================================

AGENT_NAME = "60_consultation_router"
run_id = generate_run_id()
start_time = datetime.now(timezone.utc)

# Find all pending CONSULTATION_REQUEST events
pending_requests = spark.sql(f"""
    SELECT event_id, source_agent, target_agent, payload, priority, created_at
    FROM {NEXUS_EVENTS}
    WHERE event_type = 'CONSULTATION_REQUEST'
      AND status = 'PUBLISHED'
      AND created_at >= DATEADD(HOUR, -4, CURRENT_TIMESTAMP())
    ORDER BY
        CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
        created_at ASC
    LIMIT 20
""").collect()

print(f"\U0001f4e8 Consultation Router starting — {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
print(f"   Pending requests: {len(pending_requests)}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Route to Specialists
# ======================================================================
# STEP 2 — ROUTE EACH REQUEST TO OPTIMAL SPECIALIST
# ======================================================================

from pyspark.sql.types import StructType, StructField, StringType, TimestampType

routed = []
skipped = []

for req in pending_requests:
    try:
        payload = json.loads(req['payload'])
    except:
        skipped.append({"event_id": req['event_id'], "reason": "invalid JSON"})
        continue
    
    caller = req['source_agent']
    source_system = payload.get('source_system', '')
    capability_needed = payload.get('capability_needed', None)
    question = payload.get('question', '')
    priority = req['priority'] or 'P3'
    
    # Find specialist
    specialist = None
    
    # Strategy 1: Explicit target in event
    if req['target_agent'] and req['target_agent'] in SPECIALIST_REGISTRY:
        specialist = req['target_agent']
    
    # Strategy 2: Source system lookup
    if not specialist and source_system:
        matches = find_specialist_for_source(source_system, capability_needed)
        if matches:
            specialist = matches[0]  # First match (most specific)
    
    # Strategy 3: Caller's consultation routes
    if not specialist and caller in CONSULTATION_ROUTES:
        route = CONSULTATION_ROUTES[caller]
        # Keyword match in question
        for spec in route['specialists']:
            if spec in SPECIALIST_REGISTRY:
                spec_domains = SPECIALIST_REGISTRY[spec]['domains']
                if any(d.lower() in question.lower() for d in spec_domains):
                    specialist = spec
                    break
        if not specialist and route['specialists']:
            specialist = route['specialists'][0]  # Default to first in list
    
    if not specialist:
        skipped.append({"event_id": req['event_id'], "reason": "no specialist found", "caller": caller})
        continue
    
    # Check circuit breaker for specialist
    cb_state = spark.sql(f"""
        SELECT state FROM {NEXUS_CIRCUIT} WHERE agent_name = '{specialist}'
    """).collect()
    
    if cb_state and cb_state[0]['state'] == 'OPEN':
        # Try alternate specialist
        alternates = find_specialist_for_source(source_system)
        alternate = next((a for a in alternates if a != specialist), None)
        if alternate:
            specialist = alternate
        else:
            skipped.append({"event_id": req['event_id'], "reason": f"specialist {specialist} circuit OPEN, no alternate"})
            continue
    
    # Mark original as DISPATCHED
    spark.sql(f"""
        UPDATE {NEXUS_EVENTS}
        SET status = 'DISPATCHED', consumed_by = '{AGENT_NAME}', consumed_at = CURRENT_TIMESTAMP()
        WHERE event_id = '{req['event_id']}'
    """)
    
    # Publish routed consultation to specialist
    routed_payload = {
        "consultation_id": payload.get('consultation_id', str(uuid.uuid4())),
        "caller_agent": caller,
        "specialist_agent": specialist,
        "question": question,
        "context": payload.get('context', {}),
        "source_system": source_system,
        "capability_needed": capability_needed,
        "priority": priority,
        "timeout_minutes": CONSULTATION_SLA[priority]['timeout_minutes'],
        "routed_at": datetime.now(timezone.utc).isoformat(),
    }
    
    event_data = [(
        str(uuid.uuid4()), "CONSULTATION_ROUTED", AGENT_NAME, specialist,
        "W1", json.dumps(routed_payload), priority, "PUBLISHED",
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
    
    routed.append({"caller": caller, "specialist": specialist, "priority": priority, "question": question[:50]})

print(f"\n\U0001f680 ROUTING COMPLETE")
print("=" * 60)
print(f"  Routed: {len(routed)}")
print(f"  Skipped: {len(skipped)}")
for r in routed:
    print(f"    {r['caller']} \u2192 {r['specialist']} [{r['priority']}] \"{r['question']}\"")
if skipped:
    print(f"\n  Skipped details:")
    for s in skipped:
        print(f"    {s['event_id'][:8]}... : {s['reason']}")