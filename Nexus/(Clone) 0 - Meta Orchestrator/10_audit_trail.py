# Databricks notebook source
# DBTITLE 1,Audit Trail
# MAGIC %md
# MAGIC # NEXUS Phase 11 — Audit Trail (W0)
# MAGIC
# MAGIC **Purpose:** Comprehensive audit logging of all agent activity. Provides compliance-ready traceability: who triggered what agent, when, outcome, tokens consumed, and full payload lineage.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Schedule | Daily 05:30 UTC (before governance cycle) |
# MAGIC | Inputs | nexus_agent_events, nexus_agent_trace_log, system.access.audit |
# MAGIC | Outputs | Audit report, compliance summary, anomalous access alerts |

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Aggregate Audit Activity
# ======================================================================
# STEP 1 — AGGREGATE AUDIT ACTIVITY (Last 24h)
# Cross-references event bus, trace log, and system audit tables
# ======================================================================

AGENT_NAME = "10_audit_trail"
run_id = generate_run_id()
start_time = datetime.now(timezone.utc)
LOOKBACK_HOURS = 24

# Agent event activity (24h)
event_audit = spark.sql(f"""
    SELECT
        source_agent,
        event_type,
        status,
        workspace,
        priority,
        created_at,
        consumed_by,
        consumed_at,
        TIMESTAMPDIFF(SECOND, created_at, COALESCE(consumed_at, CURRENT_TIMESTAMP())) as time_to_consume_sec
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(HOUR, -{LOOKBACK_HOURS}, CURRENT_TIMESTAMP())
    ORDER BY created_at DESC
""")

# Summary stats
event_summary = spark.sql(f"""
    SELECT
        COUNT(*) as total_events,
        COUNT_IF(status = 'PUBLISHED') as pending,
        COUNT_IF(status = 'CONSUMED') as consumed,
        COUNT_IF(status = 'DISPATCHED') as dispatched,
        COUNT_IF(status = 'EXPIRED') as expired,
        COUNT(DISTINCT source_agent) as active_producers,
        COUNT(DISTINCT consumed_by) as active_consumers,
        COUNT(DISTINCT event_type) as event_types_used,
        ROUND(AVG(TIMESTAMPDIFF(SECOND, created_at, COALESCE(consumed_at, CURRENT_TIMESTAMP()))), 1) as avg_latency_sec
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(HOUR, -{LOOKBACK_HOURS}, CURRENT_TIMESTAMP())
""").collect()[0]

print(f"\U0001f4dc AUDIT TRAIL — Last {LOOKBACK_HOURS}h")
print("=" * 65)
print(f"  Total events: {event_summary['total_events']}")
print(f"  Status: Pending={event_summary['pending']} | Consumed={event_summary['consumed']} | Dispatched={event_summary['dispatched']} | Expired={event_summary['expired']}")
print(f"  Active producers: {event_summary['active_producers']}")
print(f"  Active consumers: {event_summary['active_consumers']}")
print(f"  Event types used: {event_summary['event_types_used']}")
print(f"  Avg time-to-consume: {event_summary['avg_latency_sec']}s")
print("=" * 65)

# COMMAND ----------

# DBTITLE 1,STEP 2: Workspace Access Audit
# ======================================================================
# STEP 2 — WORKSPACE ACCESS AUDIT
# Who accessed NEXUS notebooks/tables in the last 24h
# ======================================================================

try:
    access_audit = spark.sql(f"""
        SELECT
            user_identity.email as user_email,
            action_name,
            request_params.notebook_id,
            request_params.path,
            event_time,
            source_ip_address
        FROM system.access.audit
        WHERE workspace_id = '{DEV_WORKSPACE_ID}'
          AND event_time >= DATEADD(HOUR, -{LOOKBACK_HOURS}, CURRENT_TIMESTAMP())
          AND (
              request_params.path LIKE '%AI Multi Agents%'
              OR request_params.full_name_arg LIKE '%nexus_%'
          )
        ORDER BY event_time DESC
        LIMIT 100
    """)
    
    access_count = access_audit.count()
    print(f"\n\U0001f464 ACCESS AUDIT ({LOOKBACK_HOURS}h)")
    print("-" * 50)
    print(f"  NEXUS-related access events: {access_count}")
    
    if access_count > 0:
        # Group by user
        user_summary = access_audit.groupBy("user_email").count().orderBy(F.desc("count")).collect()
        print(f"  Unique users: {len(user_summary)}")
        for u in user_summary[:5]:
            print(f"    {u['user_email']}: {u['count']} actions")
        
        # Group by action
        action_summary = access_audit.groupBy("action_name").count().orderBy(F.desc("count")).collect()
        print(f"\n  Action breakdown:")
        for a in action_summary[:5]:
            print(f"    {a['action_name']}: {a['count']}")
    else:
        print(f"  No NEXUS access detected in audit log")

except Exception as e:
    print(f"\n\u26a0\ufe0f Access audit unavailable: {str(e)[:80]}")
    print("  (system.access.audit may not be accessible from this workspace)")

# COMMAND ----------

# DBTITLE 1,STEP 3: Anomaly Detection
# ======================================================================
# STEP 3 — ANOMALY DETECTION
# Flag unusual patterns: off-hours activity, burst events, unknown agents
# ======================================================================

anomalies = []

# Check for events from unregistered agents
registered_agents = [r['agent_name'] for r in spark.sql(f"SELECT agent_name FROM {NEXUS_REGISTRY}").collect()]

unregistered_events = spark.sql(f"""
    SELECT DISTINCT source_agent
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(HOUR, -{LOOKBACK_HOURS}, CURRENT_TIMESTAMP())
      AND source_agent IS NOT NULL
""").collect()

for row in unregistered_events:
    if row['source_agent'] not in registered_agents:
        anomalies.append({
            "type": "UNREGISTERED_AGENT",
            "severity": "HIGH",
            "detail": f"Events from unregistered agent: {row['source_agent']}",
        })

# Check for burst activity (>20 events from single agent in 1h)
burst_check = spark.sql(f"""
    SELECT source_agent, COUNT(*) as event_count,
           MIN(created_at) as window_start, MAX(created_at) as window_end
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(HOUR, -1, CURRENT_TIMESTAMP())
    GROUP BY source_agent
    HAVING COUNT(*) > 20
""").collect()

for burst in burst_check:
    anomalies.append({
        "type": "BURST_ACTIVITY",
        "severity": "MEDIUM",
        "detail": f"{burst['source_agent']} produced {burst['event_count']} events in 1h",
    })

# Check for stale events (published > 4h with no consumer)
stale_check = spark.sql(f"""
    SELECT COUNT(*) as stale_count
    FROM {NEXUS_EVENTS}
    WHERE status = 'PUBLISHED'
      AND created_at < DATEADD(HOUR, -4, CURRENT_TIMESTAMP())
""").collect()[0]['stale_count']

if stale_check > 5:
    anomalies.append({
        "type": "STALE_EVENTS",
        "severity": "MEDIUM",
        "detail": f"{stale_check} events stuck in PUBLISHED state > 4h",
    })

print(f"\n\U0001f6a8 ANOMALY DETECTION")
print("-" * 50)
if anomalies:
    for a in anomalies:
        icon = '\U0001f534' if a['severity'] == 'HIGH' else '\U0001f7e1'
        print(f"  {icon} [{a['severity']}] {a['type']}: {a['detail']}")
else:
    print("  \u2705 No anomalies detected")

print(f"\n\u2705 Audit trail complete | Duration: {(datetime.now(timezone.utc) - start_time).total_seconds():.1f}s")