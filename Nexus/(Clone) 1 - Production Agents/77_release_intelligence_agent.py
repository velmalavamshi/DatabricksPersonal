# Databricks notebook source
# DBTITLE 1,Release Intelligence Agent — Orchestrator
# MAGIC %md
# MAGIC # 🔔 Agent 77 — Release Intelligence Agent (Orchestrator)
# MAGIC
# MAGIC **Purpose:** Monitors vendor releases across Oracle EBS, Salesforce, Power BI, and Databricks.  
# MAGIC Cross-references against Hologic's actual environment to flag breaking changes before they hit production.
# MAGIC
# MAGIC **Position in NEXUS:** W1 Production Agents → Proactive Monitoring Layer  
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Schedule:** Weekly (Monday 7:00 AM ET) + on-demand via Supervisor
# MAGIC
# MAGIC **Input:** Release notes context (injected or fetched)  
# MAGIC **Output:** Consolidated impact report → `mde_dev.test_schema.release_intelligence_log`
# MAGIC
# MAGIC **Downstream Integration:**
# MAGIC - Agent 39 (Morning Briefing) — CRITICAL/HIGH items surface in daily brief
# MAGIC - Agent 01 (Job Failure Triage) — correlates failures with known vendor changes
# MAGIC - Agent 04 (Source Drift) — release-driven schema changes
# MAGIC
# MAGIC **Impact Scoring:**
# MAGIC | Level | Meaning | Action Required |
# MAGIC |-------|---------|----------------|
# MAGIC | 🔴 CRITICAL | Breaking change, immediate action | Within 48 hours |
# MAGIC | 🟠 HIGH | Deprecation with timeline | Plan within 30 days |
# MAGIC | 🟡 MEDIUM | New capability / optional change | Evaluate opportunity |
# MAGIC | 🟢 LOW | Informational only | Awareness, no action |

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + Configuration
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Input Widgets + Release Intelligence Configuration
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("run_mode", "scheduled", "Run Mode (scheduled/on_demand)")
dbutils.widgets.text("vendor_filter", "all", "Vendor Filter (all/oracle/salesforce/powerbi/databricks)")
dbutils.widgets.text("days_lookback", "7", "Days to Look Back")
dbutils.widgets.text("triggered_by", "scheduler", "Triggered By")

run_mode = dbutils.widgets.get("run_mode")
vendor_filter = dbutils.widgets.get("vendor_filter")
days_lookback = int(dbutils.widgets.get("days_lookback"))
triggered_by = dbutils.widgets.get("triggered_by")

# ── Vendor Configuration ──
VENDOR_CONFIG = {
    "oracle": {
        "agent_id": 78,
        "name": "Oracle EBS",
        "tables_affected": 1263,
        "release_cadence": "Monthly patches + Quarterly CPUs (Jan/Apr/Jul/Oct)",
        "current_version": "R12.2.12",  # Update as versions change
        "sources": [
            "Oracle Critical Patch Updates (CPU)",
            "Oracle E-Business Suite Release Notes",
            "My Oracle Support (MOS) Alerts",
            "Oracle Desupport Notices",
        ],
        "hologic_impact_areas": [
            "AP (Accounts Payable)", "AR (Accounts Receivable)",
            "GL (General Ledger)", "PO (Purchasing)",
            "INV (Inventory)", "OM (Order Management)",
            "WIP (Work in Process)", "BOM (Bills of Material)",
        ],
    },
    "salesforce": {
        "agent_id": 79,
        "name": "Salesforce",
        "tables_affected": 768,
        "release_cadence": "3x/year (Spring=Jan, Summer=Jun, Winter=Oct) + weekly maintenance",
        "current_api_version": "v61.0",  # Summer '24
        "sources": [
            "Salesforce Release Notes (seasonal)",
            "Salesforce API Version Retirement Schedule",
            "Salesforce Trust Status",
            "Salesforce Developer Blog",
        ],
        "hologic_impact_areas": [
            "CDC (Change Data Capture) Streams",
            "Bulk API Extracts (47_salesforce_extract)",
            "Object Model Changes",
            "API Version Deprecation (affects 33_salesforce_sync)",
            "Lightning Web Component Changes",
        ],
    },
    "powerbi": {
        "agent_id": 80,
        "name": "Power BI",
        "tables_affected": None,  # Indirect — affects consumption layer
        "release_cadence": "Monthly (Desktop) + Continuous (Service)",
        "sources": [
            "Power BI Desktop Monthly Updates",
            "Power BI Service Updates",
            "Power BI Blog (Microsoft)",
            "Fabric/Power BI Connector Deprecations",
            "DAX Function Changes",
        ],
        "hologic_impact_areas": [
            "VertiPaq Storage (xxHash64 migration impact)",
            "DirectQuery/Import Mode Changes",
            "Gateway Refresh Pipelines",
            "Connector Versions (Databricks connector)",
            "DAX/M Function Deprecations",
            "Semantic Model (Dataset) Limits",
        ],
    },
    "databricks": {
        "agent_id": 81,
        "name": "Databricks",
        "tables_affected": None,  # Platform-wide
        "release_cadence": "Continuous (Runtime quarterly LTS, features weekly)",
        "sources": [
            "Databricks Runtime Release Notes (LTS/non-LTS)",
            "Databricks SQL Release Notes",
            "Unity Catalog Changelog",
            "Databricks REST API Changelog",
            "Delta Lake Release Notes",
            "MLflow Changelog",
        ],
        "hologic_impact_areas": [
            "Runtime Version EOL (affects all 112 agents)",
            "SQL Function Deprecations (affects gold/platinum views)",
            "Unity Catalog Breaking Changes (RBAC, lineage)",
            "REST API Version Retirement (affects CI/CD, ADO integration)",
            "Spark Behavioral Changes (join semantics, null handling)",
            "Delta Protocol Version Requirements",
            "Model Serving API Changes (affects 67_mlflow agent)",
            "Serverless Compute Changes (pricing, limits)",
        ],
    },
}

print(f"\n{'═' * 60}")
print(f"  🔔 RELEASE INTELLIGENCE AGENT — Configuration")
print(f"{'═' * 60}")
print(f"  Mode: {run_mode} | Vendor: {vendor_filter} | Lookback: {days_lookback} days")
print(f"  Triggered by: {triggered_by}")
print(f"  Monitoring {len(VENDOR_CONFIG)} vendors:")
for v, cfg in VENDOR_CONFIG.items():
    tables = f" ({cfg['tables_affected']} tables)" if cfg['tables_affected'] else ""
    print(f"    • {cfg['name']}{tables} — {cfg['release_cadence']}")
print(f"{'═' * 60}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — Context Gathering (Release Notes + Environment State)
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Gather Context — Current Environment + Recent Releases
# ══════════════════════════════════════════════════════════════════════
from datetime import datetime, timedelta

def gather_environment_context():
    """Query Hologic's current environment state for cross-referencing."""
    context = {}
    
    # Current Databricks Runtime version
    try:
        runtime_version = spark.conf.get("spark.databricks.clusterUsageTags.sparkVersion", "unknown")
        context["databricks_runtime"] = runtime_version
    except:
        context["databricks_runtime"] = "unknown"
    
    # Current workspace info
    context["workspace_id"] = spark.conf.get("spark.databricks.workspaceUrl", "unknown")
    context["environment"] = "AI_BUILDER"  # This notebook runs in AI Builder workspace
    
    # Table counts per source system (from catalog)
    try:
        table_counts = spark.sql("""
            SELECT 
                CASE 
                    WHEN table_name LIKE '%ebs%' OR table_schema LIKE '%ebs%' THEN 'oracle_ebs'
                    WHEN table_name LIKE '%sf%' OR table_name LIKE '%sfdc%' OR table_schema LIKE '%salesforce%' THEN 'salesforce'
                    WHEN table_name LIKE '%hcm%' OR table_schema LIKE '%hcm%' THEN 'hcm'
                    WHEN table_name LIKE '%ascp%' OR table_schema LIKE '%ascp%' THEN 'ascp'
                    ELSE 'other'
                END AS source_system,
                COUNT(*) AS table_count
            FROM mde_dev.information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'test_schema')
            GROUP BY 1
        """).collect()
        context["table_counts"] = {row["source_system"]: row["table_count"] for row in table_counts}
    except Exception as e:
        context["table_counts"] = {"error": str(e)}
    
    return context

def gather_release_notes_context(vendor: str, days: int) -> str:
    """
    Build release notes context for LLM analysis.
    
    In production, this would:
    1. Fetch from vendor RSS feeds / APIs
    2. Parse release note PDFs from a Unity Catalog Volume
    3. Query a Delta table populated by a scheduled scraper
    
    For now, we use the LLM's training knowledge + any manually uploaded notes.
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Check if release notes have been uploaded to our volume
    release_notes_path = f"/Volumes/mde_dev/test_schema/release_notes/{vendor}/"
    uploaded_notes = ""
    try:
        files = dbutils.fs.ls(release_notes_path)
        for f in files:
            if f.name.endswith(".md") or f.name.endswith(".txt"):
                content = spark.read.text(f.path).collect()
                uploaded_notes += "\n".join([row.value for row in content]) + "\n"
    except:
        uploaded_notes = "[No uploaded release notes found — using LLM knowledge]"
    
    return f"""
## Release Notes Context for {vendor.upper()}
Analysis window: {cutoff_date} to {datetime.now().strftime('%Y-%m-%d')}
Uploaded notes: {uploaded_notes[:2000] if uploaded_notes else 'None'}
"""

# Gather environment state
env_context = gather_environment_context()
print(f"\n✅ Environment context gathered:")
print(f"   Runtime: {env_context.get('databricks_runtime', 'N/A')}")
print(f"   Table counts: {env_context.get('table_counts', {})}")

# Gather release notes for active vendors
vendors_to_scan = [vendor_filter] if vendor_filter != "all" else list(VENDOR_CONFIG.keys())
release_contexts = {}
for vendor in vendors_to_scan:
    release_contexts[vendor] = gather_release_notes_context(vendor, days_lookback)
    print(f"   📄 {VENDOR_CONFIG[vendor]['name']}: context loaded")

# COMMAND ----------

# DBTITLE 1,STEP 4 — LLM Analysis (Impact Assessment per Vendor)
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call — Analyze Releases & Score Impact
# ══════════════════════════════════════════════════════════════════════
import json
from datetime import datetime

run_id = generate_run_id()
results = []

RELEASE_MONITOR_SYSTEM_PROMPT = """You are the Release Intelligence Agent for Hologic's Data Engineering team.

Your job: Analyze vendor release notes and identify changes that SPECIFICALLY impact Hologic's Databricks environment.

## Hologic Environment Context
- Platform: Databricks on Azure (19 workspaces, $183.6K/year)
- Source Systems: Oracle EBS (1,263 tables), Salesforce (768 tables), ASCP (238), HCM (147), Agile (82)
- Consumption: Power BI (DirectQuery + Import), Genie Spaces, AI/BI Dashboards
- Architecture: Medallion (Bronze → Silver → Gold → Platinum), Unity Catalog, Liquid Clustering
- Key Standards: xxHash64 surrogate keys, audit columns, Delta Lake
- Agents: 112 NEXUS agents running on Serverless Jobs Compute
- Runtime: Current LTS (check version provided)

## Impact Scoring Rules
- 🔴 CRITICAL: Breaking change that WILL cause failures if not addressed (API removed, security vulnerability, forced migration)
- 🟠 HIGH: Deprecation with defined end-of-life (must plan migration within 30-90 days)
- 🟡 MEDIUM: New feature that could benefit Hologic, or optional change worth evaluating
- 🟢 LOW: Informational only, no action needed

## Response Format (JSON)
```json
{
  "vendor": "<vendor_name>",
  "analysis_date": "<YYYY-MM-DD>",
  "items": [
    {
      "title": "<concise title>",
      "impact_level": "CRITICAL|HIGH|MEDIUM|LOW",
      "description": "<what changed>",
      "hologic_impact": "<specific impact to our environment>",
      "affected_components": ["<agent/table/pipeline affected>"],
      "action_required": "<specific action to take>",
      "deadline": "<date or 'N/A'>",
      "source_url": "<link if available>"
    }
  ],
  "summary": "<2-3 sentence executive summary>"
}
```

Be SPECIFIC to Hologic. Don't list generic changes — only items that affect OUR tables, OUR pipelines, OUR agents.
If no impactful changes found, return an empty items array with summary explaining why.
"""

for vendor in vendors_to_scan:
    config = VENDOR_CONFIG[vendor]
    release_context = release_contexts.get(vendor, "")
    
    user_prompt = f"""Analyze recent releases for {config['name']} and identify impacts to Hologic.

## Vendor Details
- Name: {config['name']}
- Hologic Tables Affected: {config['tables_affected'] or 'Platform-wide'}
- Current Version: {config.get('current_version', config.get('current_api_version', 'N/A'))}
- Release Cadence: {config['release_cadence']}

## Sources to Consider
{chr(10).join('- ' + s for s in config['sources'])}

## Hologic Impact Areas
{chr(10).join('- ' + a for a in config['hologic_impact_areas'])}

## Environment State
- Databricks Runtime: {env_context.get('databricks_runtime', 'unknown')}
- Table Counts: {json.dumps(env_context.get('table_counts', {}))}

## Release Notes (if available)
{release_context}

## Analysis Window
Last {days_lookback} days (since {(datetime.now() - timedelta(days=days_lookback)).strftime('%Y-%m-%d')})

Provide your analysis as JSON following the specified format.
"""
    
    print(f"\n🔍 Analyzing {config['name']} releases...")
    
    response = call_agent(
        agent_name="77_release_intelligence",
        system_prompt=RELEASE_MONITOR_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=4096,
    )
    
    # Parse JSON response
    try:
        # Extract JSON from response (handle markdown code blocks)
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        
        result = json.loads(json_str.strip())
        result["vendor"] = vendor
        results.append(result)
        
        critical_count = sum(1 for i in result.get("items", []) if i["impact_level"] == "CRITICAL")
        high_count = sum(1 for i in result.get("items", []) if i["impact_level"] == "HIGH")
        print(f"   ✅ {config['name']}: {len(result.get('items', []))} items found ")
        print(f"      ({critical_count} CRITICAL, {high_count} HIGH)")
    except (json.JSONDecodeError, IndexError) as e:
        print(f"   ⚠️  {config['name']}: Could not parse JSON response — storing raw")
        results.append({"vendor": vendor, "raw_response": response, "parse_error": str(e)})

print(f"\n{'═' * 60}")
print(f"  📊 Analysis complete: {len(results)} vendors scanned")
print(f"{'═' * 60}")

# COMMAND ----------

# DBTITLE 1,STEP 5 — Consolidate & Persist (Impact Report)
# ══════════════════════════════════════════════════════════════════════
# STEP 5: Consolidate Results & Persist to Delta
# ══════════════════════════════════════════════════════════════════════
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, ArrayType
from pyspark.sql.functions import current_timestamp, lit
import json

# ── Build consolidated report ──
consolidated_items = []
for result in results:
    vendor = result.get("vendor", "unknown")
    for item in result.get("items", []):
        consolidated_items.append({
            "run_id": run_id,
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
            "vendor": vendor,
            "title": item.get("title", ""),
            "impact_level": item.get("impact_level", "LOW"),
            "description": item.get("description", ""),
            "hologic_impact": item.get("hologic_impact", ""),
            "affected_components": json.dumps(item.get("affected_components", [])),
            "action_required": item.get("action_required", ""),
            "deadline": item.get("deadline", "N/A"),
            "source_url": item.get("source_url", ""),
            "triggered_by": triggered_by,
        })

# ── Persist to Delta (if running in DEV workspace with write access) ──
try:
    if consolidated_items:
        df = spark.createDataFrame(consolidated_items)
        df = df.withColumn("etl_load_datetime", current_timestamp()) \
               .withColumn("etl_source_system", lit("nexus_release_intelligence")) \
               .withColumn("etl_batch_id", lit(run_id))
        
        df.write.mode("append").saveAsTable("mde_dev.test_schema.release_intelligence_log")
        print(f"\n✅ {len(consolidated_items)} items persisted to mde_dev.test_schema.release_intelligence_log")
    else:
        print("\n✅ No impactful items found — nothing to persist.")
except Exception as e:
    print(f"\n⚠️  Delta write skipped (expected from AI Builder workspace): {str(e)[:100]}")
    print("   Items stored in memory for report generation below.")

# ── Generate Executive Summary ──
print(f"\n{'═' * 70}")
print(f"  🔔 RELEASE INTELLIGENCE WEEKLY DIGEST — {datetime.now().strftime('%Y-%m-%d')}")
print(f"{'═' * 70}")
print(f"  Run ID: {run_id}")
print(f"  Vendors Scanned: {', '.join(vendors_to_scan)}")
print(f"  Analysis Window: Last {days_lookback} days")
print(f"{'─' * 70}")

# Sort by severity
severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
sorted_items = sorted(consolidated_items, key=lambda x: severity_order.get(x["impact_level"], 4))

if sorted_items:
    for item in sorted_items:
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(item["impact_level"], "⚪")
        print(f"\n  {icon} [{item['impact_level']}] {item['vendor'].upper()} — {item['title']}")
        print(f"     Impact: {item['hologic_impact']}")
        print(f"     Action: {item['action_required']}")
        if item['deadline'] != 'N/A':
            print(f"     Deadline: {item['deadline']}")
else:
    print("\n  ✅ No impactful vendor changes detected this period.")
    print("     All systems operating on current/supported versions.")

print(f"\n{'═' * 70}")

# ── Save output for downstream agents (Morning Briefing integration) ──
release_digest = {
    "run_id": run_id,
    "date": datetime.now().strftime("%Y-%m-%d"),
    "vendors_scanned": vendors_to_scan,
    "total_items": len(consolidated_items),
    "critical_count": sum(1 for i in consolidated_items if i["impact_level"] == "CRITICAL"),
    "high_count": sum(1 for i in consolidated_items if i["impact_level"] == "HIGH"),
    "items": consolidated_items,
}

try:
    save_agent_output(
        agent_name="77_release_intelligence",
        run_id=run_id,
        output_type="weekly_digest",
        content=json.dumps(release_digest, indent=2),
        metadata={"vendors": vendors_to_scan, "item_count": len(consolidated_items)},
    )
    print(f"\n✅ Digest saved to agent_outputs (available to Morning Briefing agent)")
except Exception as e:
    print(f"\n⚠️  Output save skipped: {str(e)[:80]}")
    print("   Digest available in memory as 'release_digest' variable.")

# COMMAND ----------

# DBTITLE 1,STEP 6 — Validate & Quality Gate
# ══════════════════════════════════════════════════════════════════════
# STEP 6: Validation + Quality Gate
# ══════════════════════════════════════════════════════════════════════

def validate_release_intelligence_run(results, consolidated_items, run_id):
    """Quality gate for release intelligence output."""
    issues = []
    
    # Check all vendors were scanned
    scanned_vendors = [r.get("vendor") for r in results]
    for vendor in vendors_to_scan:
        if vendor not in scanned_vendors:
            issues.append(f"FAIL: Vendor '{vendor}' was not scanned")
    
    # Check for parse errors
    parse_errors = [r for r in results if "parse_error" in r]
    if parse_errors:
        issues.append(f"WARN: {len(parse_errors)} vendor(s) had JSON parse errors")
    
    # Check items have required fields
    required_fields = ["title", "impact_level", "hologic_impact", "action_required"]
    for item in consolidated_items:
        for field in required_fields:
            if not item.get(field):
                issues.append(f"WARN: Item '{item.get('title', 'unknown')}' missing field '{field}'")
    
    # Check impact levels are valid
    valid_levels = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    for item in consolidated_items:
        if item.get("impact_level") not in valid_levels:
            issues.append(f"FAIL: Invalid impact level '{item.get('impact_level')}' in '{item.get('title')}'")
    
    # Validation result
    failures = [i for i in issues if i.startswith("FAIL")]
    warnings = [i for i in issues if i.startswith("WARN")]
    
    if failures:
        status = "FAIL"
    elif warnings:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"
    
    return status, issues

# Run validation
status, issues = validate_release_intelligence_run(results, consolidated_items, run_id)

print(f"\n{'═' * 60}")
print(f"  🏁 QUALITY GATE: {status}")
print(f"{'═' * 60}")

if issues:
    for issue in issues:
        icon = "❌" if issue.startswith("FAIL") else "⚠️"
        print(f"  {icon} {issue}")
else:
    print(f"  ✅ All checks passed")
    print(f"  ✅ {len(consolidated_items)} items scored and validated")
    print(f"  ✅ Run ID: {run_id}")

print(f"\n  📋 Next Steps:")
if any(i["impact_level"] == "CRITICAL" for i in consolidated_items):
    print(f"  🚨 CRITICAL items detected — escalating to Morning Briefing")
    print(f"     → Agent 39 will include these in next daily brief")
    print(f"     → Consider running on-demand triage (Agent 01)")
else:
    print(f"  ✅ No critical items — standard weekly reporting")
    print(f"     → Available in next Monday morning briefing")