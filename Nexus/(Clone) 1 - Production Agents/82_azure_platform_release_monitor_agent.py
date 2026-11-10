# Databricks notebook source
# DBTITLE 1,Azure Platform Release Monitor
# MAGIC %md
# MAGIC # ☁️ Agent 82 — Azure Platform Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors Azure service retirements, region changes, pricing updates, and security patches affecting Hologic's Azure EA subscription and Databricks workspaces.
# MAGIC
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Called by:** Agent 77 (Release Intelligence Orchestrator)  
# MAGIC **Schedule:** Monthly (aligned to Azure update cycle)
# MAGIC
# MAGIC **Azure Release Cadence:**
# MAGIC - **Service retirements:** 12+ month notice, quarterly review
# MAGIC - **Region availability:** Continuous
# MAGIC - **Pricing changes:** Annual (EA renewal) + ad-hoc
# MAGIC - **Security patches:** Weekly (Patch Tuesday)
# MAGIC - **SDK/CLI versions:** Monthly
# MAGIC
# MAGIC **Hologic Azure Footprint:**
# MAGIC - 19 Databricks workspaces on Azure
# MAGIC - Azure EA subscription ($28.3K/quarter DEV subscription)
# MAGIC - Services: ADF/IR, Storage Accounts, VMs, Private Link, Key Vault
# MAGIC - Region: US East 2 (primary)

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + Azure Context
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Azure Platform Configuration
# ══════════════════════════════════════════════════════════════════════
dbutils.widgets.text("days_lookback", "30", "Days to Look Back")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")

days_lookback = int(dbutils.widgets.get("days_lookback"))
triggered_by = dbutils.widgets.get("triggered_by")

AZURE_ENV = {
    "subscription_type": "Enterprise Agreement (EA)",
    "primary_region": "East US 2",
    "secondary_region": "West US",
    "databricks_workspaces": 19,
    "annual_azure_spend": "$113K (Databricks portion of broader EA)",
    "services_used": [
        "Azure Databricks (19 workspaces)",
        "Azure Data Factory / Integration Runtime",
        "Azure Storage Accounts (ADLS Gen2)",
        "Azure Key Vault (secrets management)",
        "Azure Private Link (networking)",
        "Azure Virtual Machines (gateway, on-prem IR)",
        "Azure Active Directory / Entra ID",
        "Azure DevOps (CI/CD pipelines)",
        "Azure Monitor / Log Analytics",
    ],
    "networking": {
        "private_endpoints": True,
        "ip_acl": True,
        "vnet_injection": "Databricks workspaces",
    },
    "critical_dependencies": [
        "ADLS Gen2 → Databricks Unity Catalog external locations",
        "Key Vault → Databricks secret scopes (nexus-app-secrets)",
        "Private Link → Databricks workspace connectivity",
        "ADF/IR → Oracle EBS on-prem data movement",
        "Entra ID → SSO + SCIM provisioning for Databricks",
    ],
}

print(f"\n☁️  Azure Platform Release Monitor")
print(f"   Region: {AZURE_ENV['primary_region']} | Subscription: {AZURE_ENV['subscription_type']}")
print(f"   Services tracked: {len(AZURE_ENV['services_used'])}")
print(f"   Critical dependencies: {len(AZURE_ENV['critical_dependencies'])}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — LLM Analysis (Azure-specific)
# ══════════════════════════════════════════════════════════════════════
# STEP 3: LLM Analysis — Azure Platform Impact
# ══════════════════════════════════════════════════════════════════════
import json
from datetime import datetime, timedelta

run_id = generate_run_id()

AZURE_SYSTEM_PROMPT = """You are the Azure Platform Release Monitor for Hologic's Data Engineering team.

Expert in: Azure service lifecycle, region availability, pricing changes, security advisories, SDK/CLI deprecations, and Entra ID/AAD changes.

## Hologic Azure Environment
- EA subscription, East US 2 primary region
- 19 Databricks workspaces (VNet-injected, Private Link)
- ADLS Gen2 for Unity Catalog external locations
- ADF + Integration Runtime for Oracle EBS on-prem extraction
- Key Vault for secret scopes (Databricks secret backends)
- Entra ID for SSO + SCIM user provisioning
- Azure Monitor / Log Analytics for observability

## What to Monitor
1. **Service retirements** — ADLS Gen1→Gen2, classic resources, deprecated APIs
2. **Region changes** — East US 2 capacity, zone availability
3. **Pricing** — Storage pricing changes, egress cost changes, EA terms
4. **Private Link/networking** — Changes affecting Databricks connectivity
5. **Entra ID** — Authentication protocol changes, conditional access updates
6. **ADF** — IR version changes, connector deprecations
7. **Key Vault** — API version changes, certificate requirements
8. **Security** — Critical CVEs affecting Azure services we use

## Impact Rules
- CRITICAL: Service retirement within 6 months, security vulnerability, forced migration
- HIGH: Pricing increase >15%, authentication method retirement, networking change
- MEDIUM: New feature opportunity, optional migration path, performance improvement
- LOW: UI changes, non-impactful region additions, documentation updates

Return JSON: {vendor, items: [{title, impact_level, description, hologic_impact, affected_services, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Azure platform changes from the last {days_lookback} days impacting Hologic.

Our services: {', '.join(AZURE_ENV['services_used'])}
Critical dependencies: {chr(10).join('- ' + d for d in AZURE_ENV['critical_dependencies'])}
Region: {AZURE_ENV['primary_region']} | Networking: Private Link + VNet injection + IP ACL

Key questions:
1. Any Azure services we use approaching retirement?
2. ADLS Gen2 API changes affecting Unity Catalog external locations?
3. Entra ID authentication changes (OAuth, SCIM) affecting Databricks SSO?
4. ADF Integration Runtime version requirements?
5. Private Link / networking policy changes?
6. Key Vault API deprecations affecting Databricks secret scopes?
7. Storage pricing or egress cost changes?

Return JSON.
"""

response = call_agent("82_azure_platform_release_monitor", AZURE_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=4096)

try:
    json_str = response.split("```json")[1].split("```")[0] if "```json" in response else response
    azure_result = json.loads(json_str.strip())
    print(f"\n✅ Azure Platform Analysis Complete: {len(azure_result.get('items', []))} items")
except Exception as e:
    azure_result = {"vendor": "azure", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")

try:
    save_agent_output("82_azure_platform_release_monitor", run_id, "azure_release_analysis", json.dumps(azure_result, indent=2), {"region": AZURE_ENV['primary_region']})
except: pass