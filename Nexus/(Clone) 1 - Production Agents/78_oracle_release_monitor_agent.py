# Databricks notebook source
# DBTITLE 1,Oracle EBS Release Monitor
# MAGIC %md
# MAGIC # 🔴 Agent 78 — Oracle EBS Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors Oracle E-Business Suite patches, Critical Patch Updates (CPUs), and desupport notices.  
# MAGIC Cross-references against Hologic's 1,263 EBS tables to flag breaking changes.
# MAGIC
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Called by:** Agent 77 (Release Intelligence Orchestrator)  
# MAGIC **Schedule:** Monthly + Quarterly (aligned to Oracle CPU dates: Jan/Apr/Jul/Oct)
# MAGIC
# MAGIC **Oracle Release Cadence:**
# MAGIC - **Critical Patch Updates (CPU):** Quarterly (3rd Tuesday of Jan, Apr, Jul, Oct)
# MAGIC - **Bundle Patches:** Monthly
# MAGIC - **E-Business Suite Patches:** As needed (EBS-specific)
# MAGIC - **Desupport Notices:** Annual (with 1-year+ warning)
# MAGIC
# MAGIC **Hologic EBS Modules Monitored:**
# MAGIC - AP (Accounts Payable), AR (Accounts Receivable), GL (General Ledger)
# MAGIC - PO (Purchasing), INV (Inventory), OM (Order Management)
# MAGIC - WIP (Work in Process), BOM (Bills of Material)
# MAGIC - FA (Fixed Assets), CM (Cost Management)

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + Oracle Context
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Widgets + Oracle EBS Configuration
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("release_notes_text", "", "Paste Oracle Release Notes (or leave blank for LLM knowledge)")
dbutils.widgets.text("cpu_quarter", "Q3_2026", "CPU Quarter (e.g., Q3_2026)")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")

release_notes_input = dbutils.widgets.get("release_notes_text")
cpu_quarter = dbutils.widgets.get("cpu_quarter")
triggered_by = dbutils.widgets.get("triggered_by")

# Oracle EBS Environment at Hologic
ORACLE_ENV = {
    "version": "R12.2.12",
    "total_tables": 1263,
    "modules": {
        "AP": {"tables": 89, "critical_tables": ["AP_INVOICES_ALL", "AP_INVOICE_LINES_ALL", "AP_CHECKS_ALL", "AP_PAYMENT_SCHEDULES_ALL"]},
        "AR": {"tables": 76, "critical_tables": ["RA_CUSTOMER_TRX_ALL", "AR_CASH_RECEIPTS_ALL", "AR_PAYMENT_SCHEDULES_ALL"]},
        "GL": {"tables": 54, "critical_tables": ["GL_JE_HEADERS", "GL_JE_LINES", "GL_BALANCES", "GL_CODE_COMBINATIONS"]},
        "PO": {"tables": 67, "critical_tables": ["PO_HEADERS_ALL", "PO_LINES_ALL", "PO_DISTRIBUTIONS_ALL", "RCV_TRANSACTIONS"]},
        "INV": {"tables": 112, "critical_tables": ["MTL_SYSTEM_ITEMS_B", "MTL_ONHAND_QUANTITIES", "MTL_MATERIAL_TRANSACTIONS"]},
        "OM": {"tables": 58, "critical_tables": ["OE_ORDER_HEADERS_ALL", "OE_ORDER_LINES_ALL", "WSH_DELIVERY_DETAILS"]},
        "WIP": {"tables": 34, "critical_tables": ["WIP_DISCRETE_JOBS", "WIP_OPERATIONS", "WIP_REQUIREMENT_OPERATIONS"]},
        "BOM": {"tables": 28, "critical_tables": ["BOM_BILL_OF_MATERIALS", "BOM_INVENTORY_COMPONENTS"]},
        "FA": {"tables": 31, "critical_tables": ["FA_ADDITIONS_B", "FA_BOOKS", "FA_DEPRN_DETAIL"]},
        "CM": {"tables": 22, "critical_tables": ["CST_ITEM_COSTS", "CST_COST_ELEMENTS"]},
    },
    "extract_agent": "44_oracle_ebs_extract_agent",
    "specialist_agent": "32_oracle_ebs_specialist_agent",
    "integration_method": "Databricks Auto Loader + MuleSoft APIs",
    "known_customizations": [
        "Custom flexfield structures on AP/AR/GL",
        "Custom WHO columns (CREATED_BY, LAST_UPDATE_DATE)",
        "Custom value sets for GL code combinations",
        "Custom concurrent programs for extract scheduling",
    ],
}

print(f"\n🔴 Oracle EBS Release Monitor")
print(f"   Version: {ORACLE_ENV['version']} | Tables: {ORACLE_ENV['total_tables']}")
print(f"   Modules: {', '.join(ORACLE_ENV['modules'].keys())}")
print(f"   Quarter: {cpu_quarter}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — LLM Analysis (Oracle-specific)
# ══════════════════════════════════════════════════════════════════════
# STEP 3: LLM Call — Oracle Release Impact Analysis
# ══════════════════════════════════════════════════════════════════════
import json

run_id = generate_run_id()

ORACLE_SYSTEM_PROMPT = """You are the Oracle EBS Release Monitor for Hologic's Data Engineering team.

You are an expert in Oracle E-Business Suite R12.2.x release management, including:
- Critical Patch Updates (CPUs) and their security implications
- Bundle patches and one-off patches
- Oracle Database underlying changes that affect EBS
- Desupport timelines and forced migration paths
- API changes that affect downstream integrations

## Hologic's Oracle EBS Environment
- Version: R12.2.12
- 1,263 tables extracted to Databricks Delta Lake
- Modules: AP, AR, GL, PO, INV, OM, WIP, BOM, FA, CM
- Integration: Auto Loader + MuleSoft APIs
- Downstream: Databricks Medallion (Bronze→Silver→Gold), Power BI

## What to Monitor
1. **Security patches** that require database changes (could break extracts)
2. **Table/column changes** in modules we extract from (schema drift)
3. **API deprecations** (REST/SOAP services used by MuleSoft)
4. **Concurrent program changes** (affect our extract scheduling)
5. **Database version requirements** (Oracle DB upgrades mandated by CPU)
6. **Desupport dates** for our current R12.2.x version
7. **WHO column changes** (CREATED_BY, LAST_UPDATE_DATE patterns)
8. **Flexfield structure changes** (affect our custom extract logic)

## Impact Assessment Rules
- CRITICAL: Security patch mandating DB schema change on tables we extract
- HIGH: API version retirement, module desupport, required upgrade path
- MEDIUM: New feature enabling better extract patterns, optional patches
- LOW: Informational (future roadmap, non-EBS Oracle Cloud changes)

## Response Format (JSON)
Return a JSON object with:
- vendor: "oracle_ebs"
- items: array of impact items (title, impact_level, description, hologic_impact, affected_modules, affected_tables, action_required, deadline)
- summary: executive summary
"""

module_summary = "\n".join([
    f"- {mod}: {info['tables']} tables, critical: {', '.join(info['critical_tables'][:3])}"
    for mod, info in ORACLE_ENV['modules'].items()
])

user_prompt = f"""Analyze Oracle EBS releases for {cpu_quarter} and identify impacts to Hologic.

## Our Environment
- Oracle EBS Version: {ORACLE_ENV['version']}
- Total Tables Extracted: {ORACLE_ENV['total_tables']}
- Module Details:
{module_summary}

## Integration Method
{ORACLE_ENV['integration_method']}

## Known Customizations
{chr(10).join('- ' + c for c in ORACLE_ENV['known_customizations'])}

## Release Notes Input
{release_notes_input if release_notes_input else '[No manual release notes provided. Analyze based on known Oracle release patterns for this quarter. Flag known upcoming CPU items, desupport timelines, and R12.2 lifecycle events.]'}

## Specific Questions
1. Are there any CPUs this quarter that mandate schema changes on our critical tables?
2. Are any APIs we depend on (Purchasing, AP, INV) being deprecated?
3. Is R12.2.12 approaching desupport? What's our migration timeline?
4. Any Oracle Database version requirements that affect our environment?
5. Are there patches that improve extract performance we should consider?

Return your analysis as JSON.
"""

response = call_agent(
    agent_name="78_oracle_release_monitor",
    system_prompt=ORACLE_SYSTEM_PROMPT,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=4096,
)

# Parse and display
try:
    json_str = response
    if "```json" in response:
        json_str = response.split("```json")[1].split("```")[0]
    oracle_result = json.loads(json_str.strip())
    print(f"\n✅ Oracle EBS Analysis Complete")
    print(f"   Items found: {len(oracle_result.get('items', []))}")
    print(f"   Summary: {oracle_result.get('summary', 'N/A')[:200]}")
except Exception as e:
    oracle_result = {"vendor": "oracle_ebs", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")

# Save output
try:
    save_agent_output(
        agent_name="78_oracle_release_monitor",
        run_id=run_id,
        output_type="oracle_release_analysis",
        content=json.dumps(oracle_result, indent=2),
        metadata={"quarter": cpu_quarter, "version": ORACLE_ENV['version']},
    )
except:
    pass  # Expected in AI Builder workspace