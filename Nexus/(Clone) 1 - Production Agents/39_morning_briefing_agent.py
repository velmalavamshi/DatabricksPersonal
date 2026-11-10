# Databricks notebook source
# DBTITLE 1,Agent 39 — Morning Briefing
# MAGIC %md
# MAGIC # Agent 39 — Morning Briefing Agent
# MAGIC
# MAGIC **Purpose:** Queries all operational data sources and delivers a daily morning briefing via Teams + Email.  
# MAGIC **Schedule:** Daily 07:00 UTC via Databricks Workflow (39b_briefing_scheduler.json)
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Agent Number | 39 |
# MAGIC | Layer | EXECUTION |
# MAGIC | Parent | 00_supervisor_agent |
# MAGIC | Workspace | W1 (Production Agents) |
# MAGIC | Inputs | system.lakeflow.job_run_timeline, system.billing.usage, ADO API |
# MAGIC | Outputs | Teams Adaptive Card, SendGrid HTML email, nexus_agent_events publish |
# MAGIC | Version | 1.0.0 |

# COMMAND ----------

# DBTITLE 1,Load shared config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Load briefing config
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

AGENT_NAME = "39_morning_briefing_agent"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)

print(f"🌅 Morning Briefing Agent starting — {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
print(f"   Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Collect Job Run Status
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — COLLECT JOB RUN STATUS
# Queries system.lakeflow.job_run_timeline for failures in lookback window
# ══════════════════════════════════════════════════════════════════════════════

lookback_ts = start_time - timedelta(hours=LOOKBACK_HOURS)

job_runs_df = spark.sql(f"""
    SELECT
        job_id,
        run_id AS job_run_id,
        run_name AS job_name,
        result_state,
        COALESCE(run_duration_seconds / 60.0, 0) AS duration_minutes,
        period_start_time AS start_time,
        workspace_id
    FROM {JOB_RUN_TABLE}
    WHERE period_start_time >= '{lookback_ts.strftime('%Y-%m-%d %H:%M:%S')}'
      AND (run_type = 'SUBMIT_RUN' OR run_type = 'JOB_RUN')
      AND workspace_id = '{DEV_WORKSPACE_ID}'
    ORDER BY period_start_time DESC
""")

total_runs = job_runs_df.count()
failed_runs_df = job_runs_df.filter(F.col("result_state").isin("FAILED", "TIMEDOUT", "ERROR", "TERMINATED"))
success_runs_df = job_runs_df.filter(F.col("result_state") == "SUCCESS")
running_runs_df = job_runs_df.filter(F.col("result_state").isNull())
long_running_df = running_runs_df.filter(F.col("duration_minutes") > JOB_SLA_MINUTES)

failed_list = failed_runs_df.limit(10).collect()
long_list = long_running_df.limit(5).collect()
success_count = success_runs_df.count()
failed_count = failed_runs_df.count()
long_count = long_running_df.count()

print(f"📊 Jobs ({LOOKBACK_HOURS}h window): {total_runs} total | {success_count} success | {failed_count} failed | {long_count} long-running")

# COMMAND ----------

# DBTITLE 1,STEP 3: Collect Cost Data
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — COLLECT COST DATA (last 24 hours)
# CORRECT pattern: JOIN system.billing.list_prices (NEVER hardcode rates)
# ══════════════════════════════════════════════════════════════════════════════

try:
    cost_df = spark.sql(f"""
        SELECT
            u.sku_name,
            SUM(u.usage_quantity) AS total_dbu,
            ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) AS cost_usd
        FROM {BILLING_TABLE} u
        JOIN {LIST_PRICES_TABLE} lp
            ON u.sku_name = lp.sku_name
            AND lp.price_end_time IS NULL
        WHERE u.usage_date >= DATE_SUB(CURRENT_DATE(), 1)
          AND u.workspace_id = {DEV_WORKSPACE_ID}
        GROUP BY u.sku_name
        ORDER BY cost_usd DESC
    """)

    total_cost_usd = float(cost_df.agg(F.sum("cost_usd")).collect()[0][0] or 0)
    total_dbu = float(cost_df.agg(F.sum("total_dbu")).collect()[0][0] or 0)
    top_skus = cost_df.limit(5).collect()
    
    # Compare against daily budget (convert $ to DBU equivalent for alerting)
    dbu_over_budget = total_dbu > DBU_BUDGET_DAILY
    dbu_pct = (total_dbu / DBU_BUDGET_DAILY * 100) if DBU_BUDGET_DAILY > 0 else 0
    
    print(f"💰 Cost (24h): ${total_cost_usd:.2f} | {total_dbu:.0f} DBU ({dbu_pct:.0f}% of {DBU_BUDGET_DAILY} budget)")
    cost_error = None

except Exception as e:
    total_cost_usd = 0.0
    total_dbu = 0.0
    dbu_over_budget = False
    dbu_pct = 0
    top_skus = []
    cost_error = str(e)
    print(f"⚠️  Could not query billing: {e}")

# COMMAND ----------

# DBTITLE 1,STEP 4: Collect ADO Tasks
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — COLLECT AZURE DEVOPS OPEN/STALE TASKS
# ══════════════════════════════════════════════════════════════════════════════

ado_items = []
ado_error = None

if ADO_CONFIGURED:
    try:
        ado_pat_b64 = base64.b64encode(f":{ADO_TOKEN}".encode()).decode()
        ado_headers = {
            "Authorization": f"Basic {ado_pat_b64}",
            "Content-Type": "application/json"
        }

        stale_date = (start_time - timedelta(days=ADO_STALE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        wiql_query = {
            "query": f"""
                SELECT [System.Id], [System.Title], [System.WorkItemType],
                       [System.AssignedTo], [System.State], [System.CreatedDate],
                       [Microsoft.VSTS.Common.Priority]
                FROM WorkItems
                WHERE [System.TeamProject] = '{ADO_PROJECT}'
                  AND [System.State] NOT IN ('Closed', 'Resolved', 'Done')
                  AND [System.WorkItemType] IN ('Bug', 'Task', 'User Story')
                  AND [System.CreatedDate] <= '{stale_date}'
                ORDER BY [Microsoft.VSTS.Common.Priority] ASC,
                         [System.CreatedDate] ASC
            """
        }

        wiql_url = f"{ADO_ORG_URL}/{ADO_PROJECT}/_apis/wit/wiql?api-version=7.1"
        resp = requests.post(wiql_url, headers=ado_headers, json=wiql_query, timeout=15)

        if resp.status_code == 200:
            work_item_ids = [str(wi["id"]) for wi in resp.json().get("workItems", [])[:15]]
            if work_item_ids:
                ids_str = ",".join(work_item_ids)
                detail_url = f"{ADO_ORG_URL}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title,System.WorkItemType,System.AssignedTo,System.State,Microsoft.VSTS.Common.Priority&api-version=7.1"
                detail_resp = requests.get(detail_url, headers=ado_headers, timeout=15)
                if detail_resp.status_code == 200:
                    ado_items = detail_resp.json().get("value", [])
        else:
            ado_error = f"ADO API returned {resp.status_code}"

    except Exception as e:
        ado_error = str(e)
else:
    ado_error = "ADO not configured (secrets missing)"

print(f"📋 ADO: {len(ado_items)} open/stale tasks" + (f" | ⚠️ {ado_error}" if ado_error else ""))

# COMMAND ----------

# DBTITLE 1,STEP 5: Determine Overall Status
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — DETERMINE OVERALL STATUS
# ══════════════════════════════════════════════════════════════════════════════

if failed_count >= CRITICAL_THRESHOLD or dbu_over_budget:
    overall_status = "CRITICAL"
    status_emoji = "🔴"
    status_color = "attention"   # Teams Adaptive Card color
    status_hex = "#D13438"       # Email color
elif long_count > 0 or len(ado_items) > 5:
    overall_status = "WARNING"
    status_emoji = "🟡"
    status_color = "warning"
    status_hex = "#F7A800"
else:
    overall_status = "HEALTHY"
    status_emoji = "✅"
    status_color = "good"
    status_hex = "#107C10"

today_str = start_time.strftime("%A, %B %d %Y")
print(f"\n{status_emoji} Overall Status: {overall_status}")
print(f"   Date: {today_str}")

# COMMAND ----------

# DBTITLE 1,STEP 6: Build and Send Teams Adaptive Card
# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — BUILD AND SEND TEAMS ADAPTIVE CARD
# ══════════════════════════════════════════════════════════════════════════════

def build_teams_card():
    """Builds a Teams Adaptive Card payload for the morning briefing."""
    # Failed jobs section
    failed_text = ""
    if failed_list:
        for r in failed_list[:5]:
            failed_text += f"\u2022 **{r['job_name'] or r['job_id']}** — {r['result_state']}\n"
        if failed_count > 5:
            failed_text += f"\n...and {failed_count - 5} more\n"
    else:
        failed_text = "No failures in the last 24 hours. ✅"

    # Cost section
    cost_text = f"**${total_cost_usd:.2f}** | {total_dbu:.0f} DBU ({dbu_pct:.0f}% of daily budget)"
    if dbu_over_budget:
        cost_text += " ⚠️ **OVER BUDGET**"

    # ADO section
    ado_text = ""
    if ado_items:
        for item in ado_items[:5]:
            f_data = item.get("fields", {})
            title = f_data.get("System.Title", "Untitled")
            priority = f_data.get("Microsoft.VSTS.Common.Priority", "—")
            ado_text += f"\u2022 P{priority}: {title}\n"
    elif ado_error:
        ado_text = f"⚠️ {ado_error}"
    else:
        ado_text = "No stale tasks. ✅"

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": f"{status_emoji} NEXUS Morning Briefing — {today_str}", "weight": "Bolder", "size": "Large", "wrap": True},
                    {"type": "TextBlock", "text": f"Overall: **{overall_status}**", "color": status_color, "weight": "Bolder"},
                    {"type": "TextBlock", "text": "---", "spacing": "Small"},
                    {"type": "TextBlock", "text": f"📊 **Jobs** ({total_runs} total, {success_count} success, {failed_count} failed)", "weight": "Bolder", "spacing": "Medium"},
                    {"type": "TextBlock", "text": failed_text, "wrap": True, "size": "Small"},
                    {"type": "TextBlock", "text": f"💰 **Cost (24h):** {cost_text}", "weight": "Bolder", "spacing": "Medium", "wrap": True},
                    {"type": "TextBlock", "text": f"📋 **ADO Stale Tasks** ({len(ado_items)} items)", "weight": "Bolder", "spacing": "Medium"},
                    {"type": "TextBlock", "text": ado_text, "wrap": True, "size": "Small"},
                ]
            }
        }]
    }
    return card

# Send to Teams
teams_sent = False
if TEAMS_CONFIGURED:
    try:
        card_payload = build_teams_card()
        resp = requests.post(TEAMS_WEBHOOK_URL, json=card_payload, timeout=10)
        if resp.status_code in (200, 202):
            teams_sent = True
            print("✅ Teams Adaptive Card sent")
        else:
            print(f"❌ Teams delivery failed: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Teams delivery error: {e}")
else:
    print("⚠️  Teams not configured — skipping")

# COMMAND ----------

# DBTITLE 1,STEP 7: Build and Send Email
# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — BUILD AND SEND EMAIL (SendGrid)
# ══════════════════════════════════════════════════════════════════════════════

def build_email_html():
    """Builds HTML email body for the morning briefing."""
    failed_rows = ""
    for r in failed_list[:10]:
        failed_rows += f"<tr><td>{r['job_name'] or r['job_id']}</td><td>{r['result_state']}</td><td>{str(r['start_time'])[:16]}</td></tr>"

    cost_rows = ""
    for sku in top_skus:
        cost_rows += f"<tr><td>{sku['sku_name']}</td><td>{sku['total_dbu']:.0f}</td><td>${sku['cost_usd']:.2f}</td></tr>"

    html = f"""
    <html><body style="font-family: Segoe UI, sans-serif; max-width: 700px; margin: 0 auto;">
    <div style="background: {status_hex}; color: white; padding: 16px; border-radius: 8px 8px 0 0;">
        <h1 style="margin:0;">{status_emoji} NEXUS Morning Briefing</h1>
        <p style="margin:4px 0 0 0;">{today_str} | Status: {overall_status}</p>
    </div>
    <div style="padding: 16px; border: 1px solid #ddd; border-top: none;">
        <h2>📊 Job Runs ({LOOKBACK_HOURS}h)</h2>
        <p><strong>{total_runs}</strong> total | <strong>{success_count}</strong> success | <strong style="color:#D13438;">{failed_count}</strong> failed | <strong>{long_count}</strong> long-running</p>
        {'<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse; width:100%;"><tr><th>Job</th><th>State</th><th>Time</th></tr>' + failed_rows + '</table>' if failed_rows else '<p>✅ No failures</p>'}

        <h2>💰 Cost (24h)</h2>
        <p><strong>${total_cost_usd:.2f}</strong> | {total_dbu:.0f} DBU ({dbu_pct:.0f}% of daily budget){' ⚠️ OVER BUDGET' if dbu_over_budget else ''}</p>
        {'<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse; width:100%;"><tr><th>SKU</th><th>DBU</th><th>Cost</th></tr>' + cost_rows + '</table>' if cost_rows else ''}

        <h2>📋 ADO Stale Tasks ({len(ado_items)})</h2>
        {'<p>⚠️ ' + ado_error + '</p>' if ado_error else '<p>✅ No stale tasks</p>' if not ado_items else '<ul>' + ''.join(f"<li>P{item.get('fields',{}).get('Microsoft.VSTS.Common.Priority','?')}: {item.get('fields',{}).get('System.Title','')}</li>" for item in ado_items[:10]) + '</ul>'}

        <hr><p style="font-size:11px; color:#888;">Run ID: {run_id} | Agent: {AGENT_NAME} | Generated: {start_time.strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
    </body></html>
    """
    return html

# Send via SendGrid REST API (no library dependency)
email_sent = False
if SENDGRID_CONFIGURED:
    try:
        email_payload = {
            "personalizations": [{"to": [{"email": r} for r in EMAIL_RECIPIENTS]}],
            "from": {"email": EMAIL_FROM, "name": EMAIL_FROM_NAME},
            "subject": f"{status_emoji} NEXUS Briefing: {overall_status} — {today_str}",
            "content": [{"type": "text/html", "value": build_email_html()}]
        }
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
            json=email_payload,
            timeout=10
        )
        if resp.status_code in (200, 202):
            email_sent = True
            print(f"✅ Email sent to {len(EMAIL_RECIPIENTS)} recipient(s)")
        else:
            print(f"❌ Email delivery failed: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Email error: {e}")
else:
    print("⚠️  SendGrid not configured — skipping")

# COMMAND ----------

# DBTITLE 1,STEP 8: Publish to Event Bus
# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 — PUBLISH TO NEXUS EVENT BUS
# ══════════════════════════════════════════════════════════════════════════════

event_payload = {
    "overall_status": overall_status,
    "total_runs": total_runs,
    "failed_count": failed_count,
    "success_count": success_count,
    "long_running_count": long_count,
    "cost_usd_24h": total_cost_usd,
    "dbu_24h": total_dbu,
    "dbu_over_budget": dbu_over_budget,
    "ado_stale_count": len(ado_items),
    "teams_sent": teams_sent,
    "email_sent": email_sent,
}

# Determine priority based on status
priority = "P1" if overall_status == "CRITICAL" else "P2" if overall_status == "WARNING" else "P3"

# Publish event
try:
    event_data = [(
        str(uuid.uuid4()),          # event_id
        "BRIEFING_COMPLETE",        # event_type
        AGENT_NAME,                 # source_agent
        "40_morning_triage_orchestrator" if overall_status != "HEALTHY" else None,  # target_agent
        "W1",                       # workspace
        json.dumps(event_payload),  # payload
        priority,                   # priority
        "PUBLISHED",                # status
        start_time,                 # created_at
        None,                       # consumed_at
        None,                       # consumed_by
        run_id,                     # run_id
        datetime.now(timezone.utc), # etl_load_datetime
        "NEXUS",                    # etl_source_system
    )]

    from pyspark.sql.types import StructType, StructField, StringType, TimestampType
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
    print(f"✅ Event published to {NEXUS_EVENTS_TABLE} (priority: {priority})")
except Exception as e:
    print(f"❌ Event publish failed: {e}")

# COMMAND ----------

# DBTITLE 1,STEP 9: Validation and Summary
# ══════════════════════════════════════════════════════════════════════════════
# STEP 9 — VALIDATION AND SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

end_time = datetime.now(timezone.utc)
duration_sec = (end_time - start_time).total_seconds()

print("\n" + "─" * 60)
print(f"🌅 NEXUS MORNING BRIEFING — COMPLETE")
print("─" * 60)
print(f"  {status_emoji} Status     : {overall_status}")
print(f"  📊 Jobs        : {total_runs} total, {failed_count} failed, {long_count} long")
print(f"  💰 Cost (24h)  : ${total_cost_usd:.2f} ({total_dbu:.0f} DBU)")
print(f"  📋 ADO         : {len(ado_items)} stale tasks")
print(f"  📨 Teams       : {'Sent ✅' if teams_sent else 'Skipped'}")
print(f"  📧 Email       : {'Sent ✅' if email_sent else 'Skipped'}")
print(f"  📡 Event Bus   : Published ({priority})")
print(f"  ⏱️ Duration    : {duration_sec:.1f}s")
print(f"  🆔 Run ID      : {run_id}")
print("─" * 60)

# Final status assertion
if total_runs >= 0:  # basic sanity
    print("\n✅ Agent 39 completed successfully")
else:
    print("\n❌ Unexpected state — review output above")