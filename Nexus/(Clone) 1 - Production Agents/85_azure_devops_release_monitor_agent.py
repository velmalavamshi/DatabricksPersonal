# Databricks notebook source
# DBTITLE 1,Azure DevOps Release Monitor
# MAGIC %md
# MAGIC # 🛠️ Agent 85 — Azure DevOps Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors Azure DevOps pipeline agent changes, REST API deprecations, YAML schema updates, and new features affecting Hologic's CI/CD.
# MAGIC
# MAGIC **Tier:** STANDARD | **Called by:** Agent 77 | **Schedule:** Monthly

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2+3 — ADO Context + LLM Analysis
# ══════════════════════════════════════════════════════════════════════
import json
from datetime import datetime, timedelta

dbutils.widgets.text("days_lookback", "30", "Days to Look Back")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")
days_lookback = int(dbutils.widgets.get("days_lookback"))
run_id = generate_run_id()

ADO_ENV = {
    "features_used": ["Pipelines (YAML)", "Repos (Git)", "Boards (Work Items)", "Artifacts", "REST API 7.x"],
    "pipeline_agents": "Microsoft-hosted (Ubuntu latest)",
    "integrations": ["Databricks CLI tasks", "Azure Key Vault tasks", "REST API calls to Databricks", "Git push triggers"],
    "api_version": "7.1",
}

ADO_SYSTEM_PROMPT = """You are the Azure DevOps Release Monitor for Hologic's CI/CD platform.

Monitor: Pipeline agent image changes, REST API version deprecations, YAML schema updates, task version bumps, Git policy changes.

Hologic uses: YAML pipelines, Microsoft-hosted Ubuntu agents, Databricks CLI tasks, REST API 7.x for work items, Git repos with branch policies.

Impact Rules:
- CRITICAL: Agent image breaking change, API version removal, auth method retirement
- HIGH: Task major version bump, pipeline syntax deprecation, agent image OS change
- MEDIUM: New pipeline features, optional task upgrades, performance improvements
- LOW: UI changes, Boards features, non-pipeline updates

Return JSON: {vendor, items: [{title, impact_level, description, hologic_impact, affected_pipelines, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Azure DevOps changes (last {days_lookback} days) impacting Hologic.
Features: {', '.join(ADO_ENV['features_used'])}
Integrations: {', '.join(ADO_ENV['integrations'])}
API: {ADO_ENV['api_version']} | Agents: {ADO_ENV['pipeline_agents']}

Key questions: Pipeline agent Ubuntu image changes? REST API 7.x deprecations? YAML schema changes? Databricks CLI task updates?
Return JSON.
"""

response = call_agent("85_azure_devops_release_monitor", ADO_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=4096)
try:
    json_str = response.split("```json")[1].split("```")[0] if "```json" in response else response
    ado_result = json.loads(json_str.strip())
    print(f"\n✅ Azure DevOps Analysis Complete: {len(ado_result.get('items', []))} items")
except Exception as e:
    ado_result = {"vendor": "azure_devops", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")
try:
    save_agent_output("85_azure_devops_release_monitor", run_id, "ado_release_analysis", json.dumps(ado_result, indent=2), {})
except: pass