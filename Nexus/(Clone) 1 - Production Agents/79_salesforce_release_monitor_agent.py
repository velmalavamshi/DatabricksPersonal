# Databricks notebook source
# DBTITLE 1,Salesforce Release Monitor
# MAGIC %md
# MAGIC # 🔵 Agent 79 — Salesforce Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors Salesforce seasonal releases (Spring/Summer/Winter), API version deprecations, and feature retirements.  
# MAGIC Cross-references against Hologic's 768 SFDC tables and CDC streams.
# MAGIC
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Called by:** Agent 77 (Release Intelligence Orchestrator)  
# MAGIC **Schedule:** 3x/year (aligned to Salesforce release windows) + monthly API check
# MAGIC
# MAGIC **Salesforce Release Cadence:**
# MAGIC - **Seasonal Releases:** 3x/year (Spring=Jan preview, Summer=Jun, Winter=Oct)
# MAGIC - **API Version Retirement:** Annual (minimum 3-year support window)
# MAGIC - **Security Patches:** Weekly maintenance windows (no downtime)
# MAGIC - **Feature Retirements:** Announced 12+ months in advance
# MAGIC
# MAGIC **Hologic SFDC Integration:**
# MAGIC - 768 tables extracted via CDC + Bulk API
# MAGIC - Agent 33 (salesforce_sync_agent) manages CDC dedup
# MAGIC - Agent 47 (salesforce_extract_agent) handles bulk extracts
# MAGIC - 280 additional custom objects tracked

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + Salesforce Context
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Widgets + Salesforce Configuration
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("release_season", "Summer_2026", "Release Season")
dbutils.widgets.text("release_notes_text", "", "Paste SFDC Release Notes (or blank for LLM)")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")

release_season = dbutils.widgets.get("release_season")
release_notes_input = dbutils.widgets.get("release_notes_text")
triggered_by = dbutils.widgets.get("triggered_by")

SFDC_ENV = {
    "total_tables": 768,
    "custom_objects": 280,
    "current_api_version": "v61.0",
    "minimum_supported_api": "v39.0",  # Typical 3-year minimum
    "integration_methods": ["CDC (Change Data Capture)", "Bulk API 2.0", "REST API", "Streaming API"],
    "critical_objects": [
        "Account", "Contact", "Opportunity", "Lead", "Case",
        "Contract", "Product2", "PricebookEntry", "Order",
        "Task", "Event", "Campaign", "CampaignMember",
    ],
    "custom_objects_critical": [
        "Instrument__c", "Service_Contract__c", "Install_Base__c",
        "Territory__c", "Quota__c",
    ],
    "extract_patterns": {
        "cdc": "Real-time via Salesforce CDC → Databricks Auto Loader",
        "bulk": "Nightly full/incremental via Bulk API 2.0 → Bronze layer",
        "api_version_used": "v58.0",  # Version in production connectors
    },
    "agents": {
        "sync": "33_salesforce_sync_agent (CDC dedup, conflict resolution)",
        "extract": "47_salesforce_extract_agent (bulk extract monitoring)",
    },
}

print(f"\n🔵 Salesforce Release Monitor")
print(f"   Season: {release_season} | API: {SFDC_ENV['current_api_version']}")
print(f"   Tables: {SFDC_ENV['total_tables']} + {SFDC_ENV['custom_objects']} custom objects")
print(f"   Production API in use: {SFDC_ENV['extract_patterns']['api_version_used']}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — LLM Analysis (Salesforce-specific)
# ══════════════════════════════════════════════════════════════════════
# STEP 3: LLM Call — Salesforce Release Impact Analysis
# ══════════════════════════════════════════════════════════════════════
import json

run_id = generate_run_id()

SFDC_SYSTEM_PROMPT = """You are the Salesforce Release Monitor for Hologic's Data Engineering team.

You are an expert in Salesforce release management, including:
- Seasonal release cycles (Spring, Summer, Winter)
- API version lifecycle and retirement schedule
- Object model changes (new fields, removed fields, behavioral changes)
- CDC (Change Data Capture) event changes
- Bulk API and REST API breaking changes
- Governor limit changes
- Shield/encryption changes affecting data access

## Hologic's Salesforce Environment
- 768 standard objects + 280 custom objects extracted to Databricks
- CDC real-time streams for critical objects (Account, Opportunity, Case)
- Bulk API 2.0 nightly extracts for full sync
- Current production API version in connectors: v58.0
- Key custom objects: Instrument__c, Service_Contract__c, Install_Base__c

## What to Monitor
1. **API Version Retirement** — Is v58.0 (our production version) approaching EOL?
2. **Object Model Changes** — Fields removed/renamed on objects we extract
3. **CDC Event Schema Changes** — Event payload structure modifications
4. **Bulk API Changes** — New limits, authentication changes, format changes
5. **Permission/Security Changes** — New restrictions on data access patterns
6. **Custom Object Platform Changes** — Limits on custom objects/fields
7. **Governor Limit Changes** — API call limits, query limits that affect extracts
8. **Einstein/AI Changes** — New AI features that create new data surfaces

## Impact Rules
- CRITICAL: API version retirement within 6 months, breaking object changes
- HIGH: CDC behavior changes, authentication method retirement, required migration
- MEDIUM: New features enabling better integration, optional improvements
- LOW: UI-only changes, new objects not in our scope

## Response Format (JSON)
Return: {vendor, items: [{title, impact_level, description, hologic_impact, affected_objects, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Salesforce {release_season} release impacts for Hologic.

## Our Configuration
- Production API version: {SFDC_ENV['extract_patterns']['api_version_used']}
- Integration methods: {', '.join(SFDC_ENV['integration_methods'])}
- Critical standard objects: {', '.join(SFDC_ENV['critical_objects'])}
- Critical custom objects: {', '.join(SFDC_ENV['custom_objects_critical'])}

## Release Notes
{release_notes_input if release_notes_input else f'[No manual notes. Analyze {release_season} based on known Salesforce release patterns. Focus on API retirement schedule, object model changes, and CDC/Bulk API impacts.]'}

## Key Questions
1. Is API v58.0 approaching minimum supported version?
2. Are any objects we extract (Account, Opportunity, Case, Contract) changing?
3. Are CDC event schemas being modified this release?
4. Any Bulk API 2.0 breaking changes?
5. New governor limits that could throttle our nightly extracts?
6. Any changes to composite/batch request handling?

Return analysis as JSON.
"""

response = call_agent(
    agent_name="79_salesforce_release_monitor",
    system_prompt=SFDC_SYSTEM_PROMPT,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=4096,
)

try:
    json_str = response
    if "```json" in response:
        json_str = response.split("```json")[1].split("```")[0]
    sfdc_result = json.loads(json_str.strip())
    print(f"\n✅ Salesforce Analysis Complete")
    print(f"   Items: {len(sfdc_result.get('items', []))}")
    print(f"   Summary: {sfdc_result.get('summary', 'N/A')[:200]}")
except Exception as e:
    sfdc_result = {"vendor": "salesforce", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")

try:
    save_agent_output(
        agent_name="79_salesforce_release_monitor",
        run_id=run_id,
        output_type="sfdc_release_analysis",
        content=json.dumps(sfdc_result, indent=2),
        metadata={"season": release_season, "api_version": SFDC_ENV['extract_patterns']['api_version_used']},
    )
except:
    pass