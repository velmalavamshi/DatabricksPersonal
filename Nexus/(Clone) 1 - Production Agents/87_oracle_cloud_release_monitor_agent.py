# Databricks notebook source
# DBTITLE 1,Oracle Cloud Release Monitor
# MAGIC %md
# MAGIC # ☁️ Agent 87 — Oracle Cloud Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors Oracle Cloud (PBCS + HCM Cloud) quarterly updates, separate from EBS R12 on-prem. Covers Oracle Cloud Infrastructure changes, EPM Cloud, and HCM Cloud seasonal releases.
# MAGIC
# MAGIC **Tier:** STANDARD | **Called by:** Agent 77 | **Schedule:** Quarterly (aligned to Oracle Cloud update windows)

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2+3 — Oracle Cloud Context + LLM Analysis
# ══════════════════════════════════════════════════════════════════════
import json
from datetime import datetime, timedelta

dbutils.widgets.text("days_lookback", "90", "Days to Look Back (quarterly)")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")
days_lookback = int(dbutils.widgets.get("days_lookback"))
run_id = generate_run_id()

OCI_ENV = {
    "oracle_cloud_products": {
        "PBCS": {"name": "Planning & Budgeting Cloud Service (EPM Cloud)", "tables": 42, "schema": "stg_pbcs", "update_cadence": "Monthly (auto-applied)"},
        "HCM_Cloud": {"name": "Oracle HCM Cloud", "tables": 147, "schema": "stg_oracle_hcm", "update_cadence": "Quarterly + monthly patches"},
    },
    "integration_method": "REST APIs + SFTP flat file extracts",
    "critical_concerns": [
        "REST API version retirements (PBCS uses v3 Planning API)",
        "HCM Cloud data model changes (new fields, removed fields)",
        "EPM Cloud Smart View deprecation / replacement",
        "Authentication changes (OAuth2 for OCI APIs)",
        "Export format changes (CSV structure, encoding)",
    ],
}

OCI_SYSTEM_PROMPT = """You are the Oracle Cloud Release Monitor for Hologic's PBCS and HCM Cloud integrations.

Monitor: Oracle EPM Cloud (PBCS) monthly updates, Oracle HCM Cloud quarterly releases, OCI API changes.

Hologic uses:
- PBCS (42 tables in stg_pbcs) — financial planning data extracted via REST API + SFTP
- Oracle HCM Cloud (147 tables in stg_oracle_hcm) — workforce/payroll data
- Integration: REST APIs → MuleSoft → Databricks Auto Loader

Key differences from EBS (Agent 78): These are CLOUD products with auto-applied updates. Hologic cannot defer patches — must adapt.

Impact Rules:
- CRITICAL: API removal, data model breaking change (field removed we extract)
- HIGH: Authentication method change, export format change, new mandatory field
- MEDIUM: New API version with better features, new data endpoints available
- LOW: UI changes, features we don't use, documentation updates

Return JSON: {vendor, items: [{title, impact_level, description, hologic_impact, affected_modules, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Oracle Cloud (PBCS + HCM Cloud) changes from the last {days_lookback} days.

Products: {json.dumps({k: {'name': v['name'], 'tables': v['tables'], 'cadence': v['update_cadence']} for k, v in OCI_ENV['oracle_cloud_products'].items()}, indent=2)}
Integration: {OCI_ENV['integration_method']}
Concerns: {chr(10).join('- ' + c for c in OCI_ENV['critical_concerns'])}

Key questions:
1. PBCS REST API version changes (v3 Planning API status)?
2. HCM Cloud data model changes this quarter?
3. EPM Cloud Smart View replacement timeline?
4. OCI authentication changes (OAuth2 token endpoint)?
5. Export format changes affecting our flat file extracts?

Return JSON.
"""

response = call_agent("87_oracle_cloud_release_monitor", OCI_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=4096)
try:
    json_str = response.split("```json")[1].split("```")[0] if "```json" in response else response
    oci_result = json.loads(json_str.strip())
    print(f"\n✅ Oracle Cloud Analysis Complete: {len(oci_result.get('items', []))} items")
except Exception as e:
    oci_result = {"vendor": "oracle_cloud", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")
try:
    save_agent_output("87_oracle_cloud_release_monitor", run_id, "oci_release_analysis", json.dumps(oci_result, indent=2), {"products": list(OCI_ENV['oracle_cloud_products'].keys())})
except: pass