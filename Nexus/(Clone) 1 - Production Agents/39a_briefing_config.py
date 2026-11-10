# Databricks notebook source
# DBTITLE 1,39a — Morning Briefing Configuration
# ══════════════════════════════════════════════════════════════════════════════
# 39a_briefing_config
# Purpose: Configuration for Morning Briefing Agent (Agent 39)
# Called by: 39_morning_briefing_agent via %run ./39a_briefing_config
# ══════════════════════════════════════════════════════════════════════════════

# ── Delivery Channels ──────────────────────────────────────────────────────
# Credentials loaded from 'nexus' secret scope (never hardcoded)
try:
    TEAMS_WEBHOOK_URL = dbutils.secrets.get("nexus", "TEAMS_WEBHOOK_URL")
    TEAMS_CONFIGURED = True
except Exception:
    TEAMS_WEBHOOK_URL = None
    TEAMS_CONFIGURED = False

try:
    SENDGRID_API_KEY = dbutils.secrets.get("nexus", "SENDGRID_API_KEY")
    SENDGRID_CONFIGURED = True
except Exception:
    SENDGRID_API_KEY = None
    SENDGRID_CONFIGURED = False

# Email settings
EMAIL_FROM = "databricks-briefing@hologic.com"
EMAIL_FROM_NAME = "NEXUS Morning Briefing"
EMAIL_RECIPIENTS = [
    "sameet.patel@hologic.com",
]

# ── Azure DevOps ───────────────────────────────────────────────────────────
try:
    ADO_TOKEN = dbutils.secrets.get("nexus", "AZURE_DEVOPS_TOKEN")
    ADO_ORG_URL = dbutils.secrets.get("nexus", "AZURE_DEVOPS_ORG_URL")
    ADO_PROJECT = dbutils.secrets.get("nexus", "AZURE_DEVOPS_PROJECT")
    ADO_CONFIGURED = True
except Exception:
    ADO_TOKEN = None
    ADO_ORG_URL = None
    ADO_PROJECT = None
    ADO_CONFIGURED = False

# ── Briefing Thresholds ────────────────────────────────────────────────────
LOOKBACK_HOURS = 24              # How far back to check for failures
DBU_BUDGET_DAILY = 200.0         # Daily DBU budget for DEV workspace — alert if exceeded
JOB_SLA_MINUTES = 120            # Flag jobs running longer than this
ADO_STALE_DAYS = 2               # Flag ADO tasks open longer than this
CRITICAL_THRESHOLD = 3           # Number of failures to trigger CRITICAL status

# ── System Table References ────────────────────────────────────────────────
SYSTEM_CATALOG = "system"
JOB_RUN_TABLE = f"{SYSTEM_CATALOG}.lakeflow.job_run_timeline"
BILLING_TABLE = f"{SYSTEM_CATALOG}.billing.usage"
LIST_PRICES_TABLE = f"{SYSTEM_CATALOG}.billing.list_prices"

# ── NEXUS Tables ───────────────────────────────────────────────────────────
NEXUS_EVENTS_TABLE = "mde_dev.test_schema.nexus_agent_events"
NEXUS_REGISTRY_TABLE = "mde_dev.test_schema.nexus_agent_registry"
NEXUS_TRACE_TABLE = "mde_dev.test_schema.nexus_agent_trace_log"

# ── Workspace Context ──────────────────────────────────────────────────────
DEV_WORKSPACE_ID = 6617965257274108

# ── Display Schedule (documentation only) ──────────────────────────────────
BRIEFING_TIME = "07:00 UTC"

# ── Validation ─────────────────────────────────────────────────────────────
print("✅ Briefing config loaded")
print(f"   Teams webhook  : {'configured' if TEAMS_CONFIGURED else '⚠️  NOT SET'}")
print(f"   SendGrid       : {'configured' if SENDGRID_CONFIGURED else '⚠️  NOT SET'}")
print(f"   ADO            : {'configured' if ADO_CONFIGURED else '⚠️  NOT SET'}")
print(f"   Lookback       : {LOOKBACK_HOURS} hours")
print(f"   DBU budget     : {DBU_BUDGET_DAILY} DBU/day")
print(f"   Job SLA        : {JOB_SLA_MINUTES} min")
print(f"   Critical @ ≥   : {CRITICAL_THRESHOLD} failures")