# Databricks notebook source
# DBTITLE 1,MuleSoft Release Monitor
# MAGIC %md
# MAGIC # 🔗 Agent 83 — MuleSoft Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors MuleSoft Anypoint Platform runtime updates, connector deprecations, and API policy changes affecting Hologic's integration backbone.
# MAGIC
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Called by:** Agent 77 (Release Intelligence Orchestrator)  
# MAGIC **Schedule:** Monthly
# MAGIC
# MAGIC **MuleSoft Release Cadence:**
# MAGIC - **Mule Runtime:** Quarterly major, monthly patches
# MAGIC - **Connectors:** Continuous (200+ connectors)
# MAGIC - **Anypoint Platform:** Continuous SaaS updates
# MAGIC - **API Policies:** As needed
# MAGIC
# MAGIC **Hologic MuleSoft Integration:**
# MAGIC - Integration backbone: Oracle EBS → MuleSoft → Databricks
# MAGIC - Salesforce CDC routing through MuleSoft
# MAGIC - Agent 59 (mulesoft_specialist) monitors health
# MAGIC - 4 tables in stg_mule schema

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + MuleSoft Context
# ══════════════════════════════════════════════════════════════════════
# STEP 2: MuleSoft Configuration
# ══════════════════════════════════════════════════════════════════════
dbutils.widgets.text("days_lookback", "30", "Days to Look Back")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")

days_lookback = int(dbutils.widgets.get("days_lookback"))
triggered_by = dbutils.widgets.get("triggered_by")

MULE_ENV = {
    "platform": "Anypoint Platform (CloudHub)",
    "runtime_version": "Mule 4.x",
    "connectors_critical": [
        "Database Connector (Oracle EBS JDBC)",
        "Salesforce Connector (CDC + Bulk)",
        "HTTP/REST Connector (Databricks APIs)",
        "File Connector (SFTP for flat files)",
        "ServiceNow Connector",
    ],
    "integration_patterns": [
        "Oracle EBS → MuleSoft → ADLS → Databricks Auto Loader (Bronze)",
        "Salesforce CDC → MuleSoft → Databricks Streaming",
        "Databricks Gold → MuleSoft → ServiceNow (bidirectional)",
        "Koerber WMS → MuleSoft → Databricks",
    ],
    "api_policies": ["Rate Limiting", "Client ID Enforcement", "JWT Validation"],
    "hologic_impact_areas": [
        "Bronze layer ingestion (all sources flow through MuleSoft)",
        "CDC event delivery latency",
        "Connector authentication (OAuth, Basic, certificate)",
        "CloudHub worker sizing and availability",
        "API Manager policies affecting throughput",
    ],
}

print(f"\n🔗 MuleSoft Release Monitor")
print(f"   Platform: {MULE_ENV['platform']} | Runtime: {MULE_ENV['runtime_version']}")
print(f"   Critical connectors: {len(MULE_ENV['connectors_critical'])}")
print(f"   Integration flows: {len(MULE_ENV['integration_patterns'])}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — LLM Analysis (MuleSoft-specific)
# ══════════════════════════════════════════════════════════════════════
import json
from datetime import datetime, timedelta

run_id = generate_run_id()

MULE_SYSTEM_PROMPT = """You are the MuleSoft Release Monitor for Hologic's Data Engineering team.

Expert in: MuleSoft Anypoint Platform, Mule 4 Runtime, CloudHub, connector lifecycle, API policies, and integration patterns.

## Hologic MuleSoft Environment
- Mule 4.x runtime on CloudHub
- Key connectors: Database (Oracle JDBC), Salesforce, HTTP/REST, File (SFTP), ServiceNow
- Integration backbone: ALL source systems flow through MuleSoft to Databricks
- Patterns: EBS→MuleSoft→ADLS, SFDC CDC→MuleSoft→Streaming, Gold→MuleSoft→ServiceNow

## What to Monitor
1. **Mule Runtime EOL** — When does our 4.x minor version lose support?
2. **Connector deprecations** — Database connector, Salesforce connector version changes
3. **CloudHub changes** — Worker sizing, region changes, uptime SLA
4. **Authentication changes** — OAuth token handling, certificate requirements
5. **API Policy changes** — Rate limiting behavior, new security policies
6. **Java version requirements** — JDK version mandates for runtime
7. **DataWeave changes** — Language changes that affect existing transformations

## Impact Rules
- CRITICAL: Connector removal, runtime EOL within 6 months, auth method retirement
- HIGH: Connector major version bump (breaking), CloudHub infra change, Java mandate
- MEDIUM: New connector features, performance improvements, optional DataWeave updates
- LOW: UI changes, non-impactful policy additions

Return JSON: {vendor, items: [{title, impact_level, description, hologic_impact, affected_flows, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze MuleSoft releases from the last {days_lookback} days impacting Hologic.

Our connectors: {', '.join(MULE_ENV['connectors_critical'])}
Integration flows: {chr(10).join('- ' + p for p in MULE_ENV['integration_patterns'])}

Key questions:
1. Any Mule 4.x runtime versions approaching EOL?
2. Database Connector (Oracle JDBC) changes affecting our EBS extraction?
3. Salesforce Connector changes affecting CDC delivery?
4. CloudHub worker or region changes?
5. Java/JDK version requirements changing?
6. DataWeave breaking changes in transformations?

Return JSON.
"""

response = call_agent("83_mulesoft_release_monitor", MULE_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=4096)

try:
    json_str = response.split("```json")[1].split("```")[0] if "```json" in response else response
    mule_result = json.loads(json_str.strip())
    print(f"\n✅ MuleSoft Analysis Complete: {len(mule_result.get('items', []))} items")
except Exception as e:
    mule_result = {"vendor": "mulesoft", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")

try:
    save_agent_output("83_mulesoft_release_monitor", run_id, "mulesoft_release_analysis", json.dumps(mule_result, indent=2), {"runtime": MULE_ENV['runtime_version']})
except: pass