# Databricks notebook source
# DBTITLE 1,Power BI Release Monitor
# MAGIC %md
# MAGIC # 🟡 Agent 80 — Power BI Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors Power BI Desktop/Service monthly updates, connector deprecations, DAX/M changes, and Fabric integration impacts.  
# MAGIC Cross-references against Hologic's Power BI consumption layer.
# MAGIC
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Called by:** Agent 77 (Release Intelligence Orchestrator)  
# MAGIC **Schedule:** Monthly (aligned to Power BI Desktop release cycle)
# MAGIC
# MAGIC **Power BI Release Cadence:**
# MAGIC - **Desktop:** Monthly (2nd-3rd week, downloadable update)
# MAGIC - **Service:** Continuous (feature flags, usually Tuesdays)
# MAGIC - **Connectors:** As needed (Databricks connector critical for us)
# MAGIC - **DAX/M:** Rare breaking changes, usually additive
# MAGIC
# MAGIC **Hologic Power BI Integration:**
# MAGIC - DirectQuery + Import Mode from Databricks Gold/Platinum
# MAGIC - xxHash64 surrogate keys (175.8 GB VertiPaq savings)
# MAGIC - On-premises Data Gateway for refresh scheduling
# MAGIC - Agent 54 (powerbi_agent) monitors refresh pipelines

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + Power BI Context
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Widgets + Power BI Configuration
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("release_month", "2026-06", "Release Month (YYYY-MM)")
dbutils.widgets.text("release_notes_text", "", "Paste PBI Release Notes (or blank)")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")

release_month = dbutils.widgets.get("release_month")
release_notes_input = dbutils.widgets.get("release_notes_text")
triggered_by = dbutils.widgets.get("triggered_by")

PBI_ENV = {
    "connection_mode": ["DirectQuery (Gold/Platinum)", "Import Mode (aggregates)"],
    "connector_version": "Databricks SQL Connector (latest)",
    "gateway": "On-premises Data Gateway (Standard)",
    "datasets": {
        "total": 45,  # Approximate
        "directquery": 12,
        "import": 33,
    },
    "key_impacts_from_hash_migration": {
        "vertipaq_savings": "175.8 GB (53% reduction)",
        "refresh_io_savings": "1.51 TB/refresh (75% reduction)",
        "sk_type": "xxHash64 (BIGINT) — replacing MD5 (STRING)",
    },
    "critical_features_used": [
        "Composite Models (DirectQuery + Import)",
        "Incremental Refresh",
        "Row-Level Security (RLS)",
        "Deployment Pipelines (DEV→UAT→PRD)",
        "Dataflows Gen2",
        "Paginated Reports",
        "Databricks SQL Connector",
    ],
    "dax_functions_critical": [
        "CALCULATE", "SUMX", "FILTER", "RELATED", "LOOKUPVALUE",
        "DATEADD", "TOTALYTD", "PREVIOUSYEAR",
    ],
}

print(f"\n🟡 Power BI Release Monitor")
print(f"   Month: {release_month}")
print(f"   Datasets: {PBI_ENV['datasets']['total']} ({PBI_ENV['datasets']['directquery']} DQ, {PBI_ENV['datasets']['import']} Import)")
print(f"   Connector: {PBI_ENV['connector_version']}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — LLM Analysis (Power BI-specific)
# ══════════════════════════════════════════════════════════════════════
# STEP 3: LLM Call — Power BI Release Impact Analysis
# ══════════════════════════════════════════════════════════════════════
import json

run_id = generate_run_id()

PBI_SYSTEM_PROMPT = """You are the Power BI Release Monitor for Hologic's Data Engineering team.

You are an expert in Power BI release management, including:
- Monthly Desktop updates and feature releases
- Service (cloud) continuous updates
- Connector lifecycle (especially Databricks SQL connector)
- DAX/M language changes and deprecations
- Fabric integration impacts on existing PBI workflows
- VertiPaq engine changes affecting storage/performance
- Gateway version requirements

## Hologic's Power BI Environment
- ~45 datasets (12 DirectQuery from Databricks Gold/Platinum, 33 Import)
- Databricks SQL Connector for all Databricks connections
- On-premises Data Gateway (Standard mode)
- xxHash64 surrogate keys (BIGINT) throughout — replaced MD5 (STRING)
- Incremental Refresh on all Import datasets
- Row-Level Security (RLS) on sensitive datasets
- Deployment Pipelines (DEV→UAT→PRD)

## What to Monitor
1. **Databricks Connector Changes** — Version requirements, new auth methods, behavioral changes
2. **DirectQuery Changes** — Query folding behavior, connection limits, timeout changes
3. **VertiPaq Engine Changes** — Compression changes (affects our xxHash64 savings projections)
4. **DAX Deprecations** — Functions we use being deprecated or semantics changing
5. **Gateway Requirements** — Minimum version bumps, new auth requirements
6. **Incremental Refresh Changes** — Policy changes, new limitations
7. **Fabric Migration Pressure** — Features being Fabric-only that we need
8. **Data Type Handling** — Changes to how BIGINT/INT64 is handled (affects xxHash64 SKs)

## Impact Rules
- CRITICAL: Connector breaking change, forced gateway upgrade, data type handling change
- HIGH: DAX deprecation we use, DirectQuery behavioral change, Fabric-only feature we need
- MEDIUM: New optimization opportunity, optional connector upgrade with benefits
- LOW: UI-only, new visual types, Fabric features not relevant to us

## Response Format (JSON)
Return: {vendor, items: [{title, impact_level, description, hologic_impact, affected_datasets, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Power BI {release_month} release impacts for Hologic.

## Our Configuration
- Connection modes: {', '.join(PBI_ENV['connection_mode'])}
- Connector: {PBI_ENV['connector_version']}
- Gateway: {PBI_ENV['gateway']}
- Critical features: {', '.join(PBI_ENV['critical_features_used'])}
- Hash migration impact: {json.dumps(PBI_ENV['key_impacts_from_hash_migration'])}
- Critical DAX functions: {', '.join(PBI_ENV['dax_functions_critical'])}

## Release Notes
{release_notes_input if release_notes_input else f'[No manual notes. Analyze {release_month} based on known Power BI monthly release patterns. Focus on Databricks connector, DirectQuery, data type handling, and gateway changes.]'}

## Key Questions
1. Any Databricks SQL connector version changes or deprecations?
2. Changes to how BIGINT/INT64 surrogate keys are handled in VertiPaq?
3. DirectQuery query folding behavioral changes?
4. Gateway minimum version bumps?
5. New Fabric-only features that pressure migration from PBI Pro/Premium?
6. DAX function deprecations affecting our critical functions?

Return analysis as JSON.
"""

response = call_agent(
    agent_name="80_powerbi_release_monitor",
    system_prompt=PBI_SYSTEM_PROMPT,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=4096,
)

try:
    json_str = response
    if "```json" in response:
        json_str = response.split("```json")[1].split("```")[0]
    pbi_result = json.loads(json_str.strip())
    print(f"\n✅ Power BI Analysis Complete")
    print(f"   Items: {len(pbi_result.get('items', []))}")
    print(f"   Summary: {pbi_result.get('summary', 'N/A')[:200]}")
except Exception as e:
    pbi_result = {"vendor": "powerbi", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")

try:
    save_agent_output(
        agent_name="80_powerbi_release_monitor",
        run_id=run_id,
        output_type="pbi_release_analysis",
        content=json.dumps(pbi_result, indent=2),
        metadata={"month": release_month},
    )
except:
    pass