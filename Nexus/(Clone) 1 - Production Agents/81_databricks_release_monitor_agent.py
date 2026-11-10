# Databricks notebook source
# DBTITLE 1,Databricks Release Monitor
# MAGIC %md
# MAGIC # 🟠 Agent 81 — Databricks Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors Databricks Runtime versions, API deprecations, Unity Catalog changes, SQL function updates, and platform changes.  
# MAGIC Cross-references against Hologic's 19-workspace, 112-agent platform.
# MAGIC
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Called by:** Agent 77 (Release Intelligence Orchestrator)  
# MAGIC **Schedule:** Weekly (Databricks releases continuously)
# MAGIC
# MAGIC **Databricks Release Cadence:**
# MAGIC - **Runtime (LTS):** Every ~6 months (18-month support window)
# MAGIC - **Runtime (non-LTS):** Every ~2 weeks (6-month support)
# MAGIC - **SQL Functions:** Continuous (usually additive, rarely breaking)
# MAGIC - **REST API:** Versioned, 12+ month deprecation notice
# MAGIC - **Unity Catalog:** Continuous feature additions
# MAGIC - **Delta Lake Protocol:** Major version bumps require reader/writer upgrades
# MAGIC
# MAGIC **Hologic Databricks Footprint:**
# MAGIC - 19 workspaces ($183.6K/year)
# MAGIC - 112 NEXUS agents on Serverless Jobs Compute
# MAGIC - Unity Catalog with 3 environments (mde_dev/mde_uat/mde_prd)
# MAGIC - Liquid Clustering on fact tables
# MAGIC - Foundation Model API (Claude Sonnet 4-6, Claude Opus 4-8)

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + Databricks Context
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Widgets + Databricks Platform Configuration
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("days_lookback", "7", "Days to Look Back")
dbutils.widgets.text("release_notes_text", "", "Paste Databricks Release Notes (or blank)")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")

days_lookback = int(dbutils.widgets.get("days_lookback"))
release_notes_input = dbutils.widgets.get("release_notes_text")
triggered_by = dbutils.widgets.get("triggered_by")

# Auto-detect current runtime
try:
    current_runtime = spark.conf.get("spark.databricks.clusterUsageTags.sparkVersion", "unknown")
except:
    current_runtime = "unknown"

DBX_ENV = {
    "current_runtime": current_runtime,
    "workspaces": {
        "DEV": {"id": 6617965257274108, "spend": "$48,619/year"},
        "PRD": {"id": 685145432798888, "spend": "production"},
        "UAT": {"id": 7982886777824011, "spend": "staging"},
        "AI_BUILDER": {"id": 4337650355687191, "spend": "development"},
    },
    "total_workspaces": 19,
    "total_annual_spend": "$183,607",
    "compute_skus_used": [
        "PREMIUM_JOBS_COMPUTE_(PHOTON)",
        "PREMIUM_SERVERLESS_SQL_COMPUTE",
        "STANDARD_ALL_PURPOSE_COMPUTE",
        "PREMIUM_ALL_PURPOSE_COMPUTE",
        "PREMIUM_SERVERLESS_REAL_TIME_INFERENCE",
        "PREMIUM_JOBS_SERVERLESS_COMPUTE",
    ],
    "features_in_use": [
        "Unity Catalog (3 catalogs: mde_dev/mde_uat/mde_prd)",
        "Liquid Clustering (fact tables)",
        "Delta Lake (all tables)",
        "Serverless SQL Warehouses",
        "Serverless Jobs Compute (agents)",
        "Foundation Model API (Claude Sonnet/Opus)",
        "Vector Search (STANDARD, 7 units)",
        "Model Serving Endpoints",
        "Spark Declarative Pipelines (DLT)",
        "Auto Loader (CloudFiles)",
        "MLflow 3.x",
        "Databricks Apps",
        "AI Gateway",
    ],
    "api_integrations": [
        "REST API 2.0/2.1 (Jobs, Clusters, DBFS, Secrets)",
        "SQL Statement API (Genie, dashboards)",
        "Unity Catalog API (governance)",
        "Azure DevOps integration (CI/CD)",
        "MuleSoft connector",
    ],
    "delta_protocol": {
        "reader_version": 2,
        "writer_version": 5,  # Liquid Clustering requires writer v5
    },
}

print(f"\n🟠 Databricks Release Monitor")
print(f"   Current Runtime: {DBX_ENV['current_runtime']}")
print(f"   Workspaces: {DBX_ENV['total_workspaces']}")
print(f"   Spend: {DBX_ENV['total_annual_spend']}")
print(f"   Features tracked: {len(DBX_ENV['features_in_use'])}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — LLM Analysis (Databricks-specific)
# ══════════════════════════════════════════════════════════════════════
# STEP 3: LLM Call — Databricks Release Impact Analysis
# ══════════════════════════════════════════════════════════════════════
import json
from datetime import datetime, timedelta

run_id = generate_run_id()

DBX_SYSTEM_PROMPT = """You are the Databricks Release Monitor for Hologic's Data Engineering team.

You are an expert in Databricks platform releases, including:
- Databricks Runtime (LTS and non-LTS) version lifecycle
- REST API versioning and deprecation
- Unity Catalog feature evolution and breaking changes
- Delta Lake protocol version requirements
- SQL function additions, changes, and deprecations
- Serverless compute changes (pricing, capabilities)
- Foundation Model API changes (model availability, pricing)
- Spark behavioral changes between versions

## Hologic's Databricks Platform
- 19 workspaces, $183.6K/year total spend
- 112 NEXUS agents running on Serverless Jobs Compute
- Unity Catalog: 3 catalogs (mde_dev, mde_uat, mde_prd)
- Delta Lake: All tables, writer protocol v5 (Liquid Clustering)
- Serverless SQL Warehouses for BI/analytics
- Foundation Model API: Claude Sonnet 4-6 + Claude Opus 4-8
- Vector Search: 1 STANDARD endpoint (7 units)
- Model Serving: Multiple endpoints
- Auto Loader: Primary ingestion method from all source systems
- MLflow 3.x: Experiment tracking + UC model registry

## What to Monitor
1. **Runtime EOL** — When does our current LTS version lose support? When must we upgrade?
2. **REST API Deprecation** — APIs used by our CI/CD (Jobs API, Clusters API, Secrets API)
3. **Unity Catalog Changes** — New permissions model, breaking RBAC changes
4. **Delta Protocol Bumps** — New writer versions that enable features we want
5. **SQL Function Changes** — xxhash64() behavior, date functions in our views
6. **Serverless Changes** — Pricing updates, new SKUs, capability changes
7. **Foundation Model API** — Model retirement, new models, pricing changes
8. **Spark Behavioral Changes** — Null handling, join semantics, type coercion
9. **Auto Loader Changes** — New features or breaking changes in cloudFiles source
10. **Photon Changes** — Optimization changes that affect query behavior

## Impact Rules
- CRITICAL: Runtime EOL within 3 months, API removal, forced protocol upgrade
- HIGH: Model retirement (Claude versions), pricing increase >20%, security vulnerability
- MEDIUM: New feature (e.g., new AI function), performance improvement, optional upgrade
- LOW: Documentation changes, minor UI updates, features we don't use

## Response Format (JSON)
Return: {vendor, items: [{title, impact_level, description, hologic_impact, affected_components, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Databricks platform releases from the last {days_lookback} days and identify impacts to Hologic.

## Our Configuration
- Current Runtime: {DBX_ENV['current_runtime']}
- Delta Writer Protocol: v{DBX_ENV['delta_protocol']['writer_version']}
- SKUs in use: {', '.join(DBX_ENV['compute_skus_used'])}
- Features in use:
{chr(10).join('  - ' + f for f in DBX_ENV['features_in_use'])}
- API Integrations:
{chr(10).join('  - ' + a for a in DBX_ENV['api_integrations'])}

## Release Notes
{release_notes_input if release_notes_input else '[No manual notes. Analyze based on known Databricks release patterns. Focus on: Runtime LTS lifecycle, REST API 2.0/2.1 deprecation timeline, Unity Catalog changes, Foundation Model API model availability, and Serverless pricing.]'}

## Key Questions
1. Is our current runtime approaching EOL? What's the next LTS target?
2. Any REST API endpoints we use being deprecated?
3. Are Claude Sonnet 4-6 or Claude Opus 4-8 being retired/repriced?
4. Any new Delta protocol features that require writer version >5?
5. SQL function changes that could affect our gold/platinum views?
6. Serverless compute pricing changes?
7. Auto Loader behavioral changes that could affect our Bronze ingestion?
8. New AI/ML features worth adopting (e.g., new AI functions, Mosaic AI updates)?

Return analysis as JSON.
"""

response = call_agent(
    agent_name="81_databricks_release_monitor",
    system_prompt=DBX_SYSTEM_PROMPT,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=4096,
)

try:
    json_str = response
    if "```json" in response:
        json_str = response.split("```json")[1].split("```")[0]
    dbx_result = json.loads(json_str.strip())
    print(f"\n✅ Databricks Analysis Complete")
    print(f"   Items: {len(dbx_result.get('items', []))}")
    print(f"   Summary: {dbx_result.get('summary', 'N/A')[:200]}")
except Exception as e:
    dbx_result = {"vendor": "databricks", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")

try:
    save_agent_output(
        agent_name="81_databricks_release_monitor",
        run_id=run_id,
        output_type="dbx_release_analysis",
        content=json.dumps(dbx_result, indent=2),
        metadata={"runtime": DBX_ENV['current_runtime'], "days_lookback": days_lookback},
    )
except:
    pass