# Databricks notebook source
# DBTITLE 1,Event Mesh
# MAGIC %md
# MAGIC # NEXUS Event Mesh (W0)
# MAGIC
# MAGIC **Purpose:** Polls the `nexus_agent_events` table for pending PUBLISHED events, dispatches them to target agents, and manages event lifecycle (PUBLISHED → CONSUMED → EXPIRED).
# MAGIC
# MAGIC **Schedule:** Every 5 minutes via Workflow, or on-demand after agent chains.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Agent | 02_event_mesh |
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W0 (Meta Orchestrator) |
# MAGIC | Inputs | nexus_agent_events (status=PUBLISHED) |
# MAGIC | Outputs | Agent dispatches, event status updates |

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Poll Pending Events
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — POLL PENDING EVENTS
# Reads all PUBLISHED events that have a target_agent and haven't been consumed
# ══════════════════════════════════════════════════════════════════════════════

from datetime import timedelta

AGENT_NAME = "02_event_mesh"
run_id = generate_run_id()
start_time = datetime.now(timezone.utc)

# Expire events older than 24 hours that were never consumed
expiry_threshold = (start_time - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
spark.sql(f"""
    UPDATE {NEXUS_EVENTS}
    SET status = 'EXPIRED', consumed_at = CURRENT_TIMESTAMP(), consumed_by = '{AGENT_NAME}'
    WHERE status = 'PUBLISHED'
      AND created_at < '{expiry_threshold}'
""")

# Poll pending events (targeted, not broadcasts)
pending_events = spark.sql(f"""
    SELECT event_id, event_type, source_agent, target_agent, workspace, payload, priority, created_at
    FROM {NEXUS_EVENTS}
    WHERE status = 'PUBLISHED'
      AND target_agent IS NOT NULL
    ORDER BY
        CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
        created_at ASC
    LIMIT 20
""").collect()

print(f"📡 Event Mesh scanning... {len(pending_events)} pending events")
for evt in pending_events[:5]:
    print(f"   {evt['priority']} | {evt['event_type']} | {evt['source_agent']} → {evt['target_agent']}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Dispatch Events
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — DISPATCH EVENTS TO TARGET AGENTS
# Looks up target agent's notebook path and triggers execution
# ══════════════════════════════════════════════════════════════════════════════

dispatched = []
failed_dispatches = []

for evt in pending_events:
    target_agent = evt['target_agent']
    event_id = evt['event_id']
    
    # Look up agent in registry
    agent_info = spark.sql(f"""
        SELECT notebook_path, status, workspace
        FROM {NEXUS_REGISTRY}
        WHERE agent_name = '{target_agent}'
        LIMIT 1
    """).collect()
    
    if not agent_info:
        failed_dispatches.append({"event_id": event_id, "target": target_agent, "reason": "Agent not in registry"})
        continue
    
    agent = agent_info[0]
    if agent['status'] not in ('ACTIVE', 'DEVELOPMENT'):
        failed_dispatches.append({"event_id": event_id, "target": target_agent, "reason": f"Agent status: {agent['status']}"})
        continue
    
    # Check circuit breaker
    cb = spark.sql(f"""
        SELECT state FROM {NEXUS_CIRCUIT}
        WHERE agent_name = '{target_agent}'
    """).collect()
    
    if cb and cb[0]['state'] == 'OPEN':
        failed_dispatches.append({"event_id": event_id, "target": target_agent, "reason": "Circuit breaker OPEN"})
        continue
    
    # Dispatch strategy:
    # - For Workflow-scheduled agents: just mark as CONSUMED (they'll pick up on next run)
    # - For immediate dispatch: use dbutils.notebook.run (if in same workspace folder)
    #
    # For now, we mark targeted events as DISPATCHED and let agents poll on their own schedule.
    # This is the safest pattern for a single-workspace setup.
    
    spark.sql(f"""
        UPDATE {NEXUS_EVENTS}
        SET status = 'DISPATCHED',
            consumed_at = CURRENT_TIMESTAMP(),
            consumed_by = '{AGENT_NAME}'
        WHERE event_id = '{event_id}'
    """)
    dispatched.append({"event_id": event_id, "target": target_agent, "type": evt['event_type']})

print(f"\n✅ Dispatched: {len(dispatched)} events")
for d in dispatched[:5]:
    print(f"   → {d['target']} ({d['type']})")

if failed_dispatches:
    print(f"\n⚠️  Failed: {len(failed_dispatches)} events")
    for f in failed_dispatches[:5]:
        print(f"   ❌ {f['target']}: {f['reason']}")

# COMMAND ----------

# DBTITLE 1,STEP 3: Summary
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

end_time = datetime.now(timezone.utc)
duration_sec = (end_time - start_time).total_seconds()

# Get event stats
event_stats = spark.sql(f"""
    SELECT status, COUNT(*) as cnt
    FROM {NEXUS_EVENTS}
    GROUP BY status
    ORDER BY status
""").collect()

print("\n" + "─" * 60)
print(f"📡 NEXUS EVENT MESH — COMPLETE")
print("─" * 60)
print(f"  Dispatched     : {len(dispatched)}")
print(f"  Failed         : {len(failed_dispatches)}")
print(f"  Duration       : {duration_sec:.1f}s")
print(f"  Run ID         : {run_id}")
print(f"\n  Event Bus Stats:")
for row in event_stats:
    print(f"    {row['status']:12s} : {row['cnt']}")
print("─" * 60)