# Databricks notebook source
# DBTITLE 1,Agent 40 — Morning Triage Orchestrator
# MAGIC %md
# MAGIC # Agent 40 — Morning Triage Orchestrator
# MAGIC
# MAGIC **Purpose:** Consumes BRIEFING_COMPLETE events from Agent 39. When status is CRITICAL or WARNING, automatically creates ADO work items and optionally ServiceNow incidents for each failed job or threshold breach.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Agent Number | 40 |
# MAGIC | Layer | EXECUTION |
# MAGIC | Parent | 00_supervisor_agent |
# MAGIC | Workspace | W1 (Production Agents) |
# MAGIC | Triggered By | Agent 39 (event: BRIEFING_COMPLETE, priority P1/P2) |
# MAGIC | Inputs | nexus_agent_events, system.lakeflow.job_run_timeline |
# MAGIC | Outputs | ADO work items, ServiceNow incidents, nexus_agent_events publish |
# MAGIC | Version | 1.0.0 |

# COMMAND ----------

# DBTITLE 1,Load shared config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Load briefing config (shared thresholds)
# MAGIC %run ./39a_briefing_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Imports and Setup
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — IMPORTS AND SETUP
# ══════════════════════════════════════════════════════════════════════════════

import json
import uuid
import requests
import base64
from datetime import datetime, timedelta, timezone
from pyspark.sql import functions as F

AGENT_NAME = "40_morning_triage_orchestrator"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)

print(f"🚨 Triage Orchestrator starting — {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
print(f"   Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Consume Briefing Event
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — CONSUME BRIEFING EVENT
# Read the most recent BRIEFING_COMPLETE event targeting this agent
# ══════════════════════════════════════════════════════════════════════════════

# Find unconsumed BRIEFING_COMPLETE events targeting this agent
briefing_events_df = spark.sql(f"""
    SELECT event_id, payload, priority, created_at, run_id AS source_run_id
    FROM {NEXUS_EVENTS_TABLE}
    WHERE event_type = 'BRIEFING_COMPLETE'
      AND target_agent = '{AGENT_NAME}'
      AND status = 'PUBLISHED'
    ORDER BY created_at DESC
    LIMIT 1
""")

if briefing_events_df.count() == 0:
    print("✅ No pending triage events — nothing to do")
    briefing_payload = None
    source_event_id = None
else:
    event_row = briefing_events_df.collect()[0]
    source_event_id = event_row['event_id']
    briefing_payload = json.loads(event_row['payload'])
    print(f"📥 Consuming event: {source_event_id}")
    print(f"   Status: {briefing_payload['overall_status']} | Priority: {event_row['priority']}")
    print(f"   Failed jobs: {briefing_payload['failed_count']} | Over budget: {briefing_payload['dbu_over_budget']}")

# COMMAND ----------

# DBTITLE 1,STEP 3: Identify Failed Jobs for Triage
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — IDENTIFY FAILED JOBS FOR TRIAGE
# Re-query system tables for detailed failure info (needed for ticket creation)
# ══════════════════════════════════════════════════════════════════════════════

triage_items = []  # List of items that need tickets

if briefing_payload and briefing_payload.get('failed_count', 0) > 0:
    lookback_ts = start_time - timedelta(hours=LOOKBACK_HOURS)
    
    failed_jobs_df = spark.sql(f"""
        SELECT
            job_id,
            run_id AS job_run_id,
            run_name AS job_name,
            result_state,
            termination_code,
            COALESCE(run_duration_seconds / 60.0, 0) AS duration_minutes,
            period_start_time AS start_time
        FROM {JOB_RUN_TABLE}
        WHERE period_start_time >= '{lookback_ts.strftime('%Y-%m-%d %H:%M:%S')}'
          AND result_state IN ('FAILED', 'TIMEDOUT', 'ERROR', 'TERMINATED')
          AND workspace_id = '{DEV_WORKSPACE_ID}'
        ORDER BY period_start_time DESC
        LIMIT 20
    """)
    
    for row in failed_jobs_df.collect():
        severity = "P1" if row['result_state'] in ('ERROR', 'TIMEDOUT') else "P2"
        triage_items.append({
            "type": "JOB_FAILURE",
            "severity": severity,
            "job_id": row['job_id'],
            "job_run_id": row['job_run_id'],
            "job_name": row['job_name'] or f"Job {row['job_id']}",
            "result_state": row['result_state'],
            "termination_code": row['termination_code'],
            "duration_minutes": float(row['duration_minutes']),
            "start_time": str(row['start_time']),
        })

# Add cost over-budget as a triage item
if briefing_payload and briefing_payload.get('dbu_over_budget', False):
    triage_items.append({
        "type": "COST_OVER_BUDGET",
        "severity": "P2",
        "job_id": None,
        "job_name": "DBU Budget Exceeded",
        "result_state": f"${briefing_payload.get('cost_usd_24h', 0):.2f} / {briefing_payload.get('dbu_24h', 0):.0f} DBU",
        "termination_code": None,
        "duration_minutes": 0,
        "start_time": start_time.strftime('%Y-%m-%d %H:%M:%S'),
    })

print(f"📝 Triage items identified: {len(triage_items)}")
for item in triage_items[:5]:
    print(f"   {item['severity']} | {item['type']} | {item['job_name']} | {item['result_state']}")
if len(triage_items) > 5:
    print(f"   ...and {len(triage_items) - 5} more")

# COMMAND ----------

# DBTITLE 1,STEP 4: Create ADO Work Items
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — CREATE ADO WORK ITEMS
# Creates Bug/Task work items in Azure DevOps for each triage item
# ══════════════════════════════════════════════════════════════════════════════

ado_created = []
ado_errors = []

if ADO_CONFIGURED and triage_items:
    ado_pat_b64 = base64.b64encode(f":{ADO_TOKEN}".encode()).decode()
    ado_headers = {
        "Authorization": f"Basic {ado_pat_b64}",
        "Content-Type": "application/json-patch+json"
    }

    for item in triage_items[:10]:  # Cap at 10 to avoid flooding
        work_item_type = "Bug" if item['type'] == 'JOB_FAILURE' else "Task"
        title = f"[NEXUS Auto-Triage] {item['job_name']} — {item['result_state']}"
        description = (
            f"<b>Auto-created by NEXUS Agent 40 (Triage Orchestrator)</b><br>"
            f"<b>Type:</b> {item['type']}<br>"
            f"<b>Severity:</b> {item['severity']}<br>"
            f"<b>Job:</b> {item['job_name']} (ID: {item['job_id']})<br>"
            f"<b>State:</b> {item['result_state']}<br>"
            f"<b>Termination Code:</b> {item.get('termination_code', 'N/A')}<br>"
            f"<b>Duration:</b> {item['duration_minutes']:.1f} min<br>"
            f"<b>Start Time:</b> {item['start_time']}<br>"
            f"<b>Run ID:</b> {item.get('job_run_id', 'N/A')}<br>"
            f"<hr><i>Briefing Run: {run_id}</i>"
        )
        priority_map = {"P1": 1, "P2": 2, "P3": 3}
        
        patch_doc = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": description},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": priority_map.get(item['severity'], 2)},
            {"op": "add", "path": "/fields/System.Tags", "value": "NEXUS;Auto-Triage;Agent-40"},
        ]

        try:
            url = f"{ADO_ORG_URL}/{ADO_PROJECT}/_apis/wit/workitems/${work_item_type}?api-version=7.1"
            resp = requests.post(url, headers=ado_headers, json=patch_doc, timeout=10)
            if resp.status_code in (200, 201):
                wi_id = resp.json().get('id')
                ado_created.append({"id": wi_id, "title": title, "type": work_item_type})
            else:
                ado_errors.append(f"{item['job_name']}: {resp.status_code}")
        except Exception as e:
            ado_errors.append(f"{item['job_name']}: {str(e)[:100]}")

    print(f"✅ ADO: Created {len(ado_created)} work items")
    for wi in ado_created[:5]:
        print(f"   #{wi['id']} [{wi['type']}] {wi['title'][:60]}")
    if ado_errors:
        print(f"⚠️  ADO errors: {len(ado_errors)}")
        for err in ado_errors[:3]:
            print(f"   ❌ {err}")

elif not ADO_CONFIGURED:
    print("⚠️  ADO not configured — skipping work item creation")
    print(f"   Would have created {len(triage_items)} work items")
else:
    print("✅ No triage items — no ADO work items needed")

# COMMAND ----------

# DBTITLE 1,STEP 5: Mark Event as Consumed
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — MARK EVENT AS CONSUMED & PUBLISH TRIAGE_COMPLETE
# ══════════════════════════════════════════════════════════════════════════════

# Mark the consumed event
if source_event_id:
    spark.sql(f"""
        UPDATE {NEXUS_EVENTS_TABLE}
        SET status = 'CONSUMED',
            consumed_at = CURRENT_TIMESTAMP(),
            consumed_by = '{AGENT_NAME}'
        WHERE event_id = '{source_event_id}'
    """)
    print(f"✅ Marked event {source_event_id[:8]}... as CONSUMED")

# Publish TRIAGE_COMPLETE event
triage_payload = {
    "triage_items_count": len(triage_items),
    "ado_created_count": len(ado_created),
    "ado_errors_count": len(ado_errors),
    "items_summary": [{"job_name": i['job_name'], "severity": i['severity'], "type": i['type']} for i in triage_items[:10]],
}

try:
    from pyspark.sql.types import StructType, StructField, StringType, TimestampType
    event_data = [(
        str(uuid.uuid4()),
        "TRIAGE_COMPLETE",
        AGENT_NAME,
        None,  # broadcast
        "W1",
        json.dumps(triage_payload),
        "P3",  # informational
        "PUBLISHED",
        start_time,
        None, None, run_id,
        datetime.now(timezone.utc),
        "NEXUS",
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
    event_df = spark.createDataFrame(event_data, schema=event_schema)
    event_df.write.format("delta").mode("append").saveAsTable(NEXUS_EVENTS_TABLE)
    print(f"✅ Published TRIAGE_COMPLETE event")
except Exception as e:
    print(f"❌ Event publish failed: {e}")

# COMMAND ----------

# DBTITLE 1,STEP 6: Validation and Summary
# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — VALIDATION AND SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

end_time = datetime.now(timezone.utc)
duration_sec = (end_time - start_time).total_seconds()

print("\n" + "─" * 60)
print(f"🚨 NEXUS TRIAGE ORCHESTRATOR — COMPLETE")
print("─" * 60)
print(f"  📝 Triage items    : {len(triage_items)}")
print(f"  📌 ADO created     : {len(ado_created)}")
print(f"  ⚠️  ADO errors      : {len(ado_errors)}")
print(f"  📡 Event consumed  : {source_event_id[:8] + '...' if source_event_id else 'None'}")
print(f"  📡 Event published : TRIAGE_COMPLETE")
print(f"  ⏱️  Duration       : {duration_sec:.1f}s")
print(f"  🆔 Run ID         : {run_id}")
print("─" * 60)

if briefing_payload is None:
    print("\n✅ No events to triage — healthy state")
elif len(ado_errors) == 0:
    print("\n✅ Agent 40 completed successfully")
else:
    print(f"\n⚠️  Agent 40 completed with {len(ado_errors)} ADO errors")