# Databricks notebook source
# DBTITLE 1,Delta Lake + Spark OSS Release Monitor
# MAGIC %md
# MAGIC # ⚡ Agent 84 — Delta Lake + Apache Spark OSS Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors open-source Delta Lake protocol changes and Apache Spark behavioral changes that ship inside DBR but have independent release cadences.
# MAGIC
# MAGIC **Tier:** STANDARD (`databricks-claude-sonnet-4-6`)  
# MAGIC **Called by:** Agent 77 (Release Intelligence Orchestrator)  
# MAGIC **Schedule:** Monthly (aligned to Delta Lake releases + Spark quarterly)
# MAGIC
# MAGIC **OSS Release Cadence:**
# MAGIC - **Delta Lake:** ~Quarterly (protocol versions are rare but high-impact)
# MAGIC - **Apache Spark:** Quarterly minor, annual major (4.x transition)
# MAGIC - **Delta Kernel:** Continuous (standalone reader/writer)
# MAGIC
# MAGIC **Hologic OSS Dependencies:**
# MAGIC - Delta writer protocol v5 (Liquid Clustering)
# MAGIC - Spark SQL semantics in 5,000+ views
# MAGIC - PySpark DataFrame API across 112 agents
# MAGIC - Auto Loader (cloudFiles) for Bronze ingestion

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2 — Widgets + OSS Context
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Delta Lake + Spark OSS Configuration
# ══════════════════════════════════════════════════════════════════════
dbutils.widgets.text("days_lookback", "30", "Days to Look Back")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")

days_lookback = int(dbutils.widgets.get("days_lookback"))
triggered_by = dbutils.widgets.get("triggered_by")

OSS_ENV = {
    "delta_protocol": {"reader": 2, "writer": 5},
    "spark_version_in_dbr": "3.5.x (bundled in DBR 17.3)",
    "delta_lake_version": "3.x (bundled in DBR 17.3)",
    "critical_spark_features": [
        "JOIN semantics (null handling in equi-joins)",
        "Type coercion rules (implicit casting)",
        "ANSI mode behavior (strict vs permissive)",
        "Adaptive Query Execution (AQE) optimizations",
        "DataFrame API (groupBy, agg, window functions)",
        "SQL parser (reserved words, function overloading)",
    ],
    "critical_delta_features": [
        "Liquid Clustering (writer v5)",
        "MERGE behavior (match conditions, output)",
        "Time Travel (retention, vacuum semantics)",
        "Change Data Feed (CDF) schema",
        "Deletion Vectors",
        "Row Tracking",
        "Universal Format (UniForm)",
    ],
    "views_at_risk": "5,000+ SQL views in gold/platinum (any function semantic change impacts)",
    "agents_at_risk": "112 agents using PySpark DataFrame API",
}

print(f"\n⚡ Delta Lake + Spark OSS Release Monitor")
print(f"   Delta Protocol: reader v{OSS_ENV['delta_protocol']['reader']}, writer v{OSS_ENV['delta_protocol']['writer']}")
print(f"   Spark: {OSS_ENV['spark_version_in_dbr']}")
print(f"   Delta: {OSS_ENV['delta_lake_version']}")
print(f"   Views at risk: {OSS_ENV['views_at_risk']}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — LLM Analysis (Delta/Spark OSS)
# ══════════════════════════════════════════════════════════════════════
import json
run_id = generate_run_id()

OSS_SYSTEM_PROMPT = """You are the Delta Lake + Apache Spark OSS Release Monitor for Hologic.

Expert in: Delta Lake protocol evolution, Spark SQL semantics, PySpark API stability, MERGE behavior, type coercion, and ANSI mode.

## Hologic Environment
- Delta writer protocol v5 (Liquid Clustering enabled)
- 5,000+ SQL views in gold/platinum depending on Spark SQL semantics
- 112 agents using PySpark DataFrame API
- Key functions: xxhash64(), CONCAT_WS(), date functions, window functions
- MERGE used extensively for Silver→Gold promotion
- Auto Loader (cloudFiles) for all Bronze ingestion
- Change Data Feed (CDF) for incremental processing

## What to Monitor
1. **Delta Protocol versions** — New writer versions (v6, v7) and what they enable/require
2. **MERGE behavior changes** — Match condition handling, output schema changes
3. **Spark SQL function changes** — xxhash64(), date_format(), cast() behavior
4. **NULL handling changes** — Join semantics, aggregate behavior with nulls
5. **Type coercion** — Implicit casting rules between versions
6. **ANSI mode** — Strict mode becoming default, division by zero, overflow
7. **AQE changes** — Adaptive optimization behavior differences
8. **CDF schema changes** — Change Data Feed metadata column changes
9. **Vacuum/Time Travel** — Retention policy changes
10. **Spark 4.0 migration** — Breaking changes in the Spark 3.x→4.x transition

## Impact Rules
- CRITICAL: xxhash64() behavior change (breaks ALL surrogate keys), protocol forced upgrade
- HIGH: NULL/join semantic change, MERGE output change, Spark 4.0 incompatibility
- MEDIUM: New protocol features (optional), AQE improvement, new Delta features
- LOW: Documentation, minor API additions, non-breaking additive changes

Return JSON: {vendor, items: [{title, impact_level, description, hologic_impact, affected_components, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Delta Lake + Apache Spark OSS changes from the last {days_lookback} days.

Our protocol: writer v{OSS_ENV['delta_protocol']['writer']}, reader v{OSS_ENV['delta_protocol']['reader']}
Spark version: {OSS_ENV['spark_version_in_dbr']}
Delta version: {OSS_ENV['delta_lake_version']}

Critical Spark features we depend on: {', '.join(OSS_ENV['critical_spark_features'])}
Critical Delta features: {', '.join(OSS_ENV['critical_delta_features'])}

Key questions:
1. Any xxhash64() behavior changes in upcoming Spark versions?
2. Delta protocol v6/v7 — what do they require and should we upgrade?
3. Spark 4.0 timeline — what breaks for our 5,000+ views?
4. MERGE behavior changes in latest Delta releases?
5. NULL handling or type coercion changes?
6. ANSI mode becoming mandatory — timeline and impact?

Return JSON.
"""

response = call_agent("84_delta_spark_oss_release_monitor", OSS_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=4096)

try:
    json_str = response.split("```json")[1].split("```")[0] if "```json" in response else response
    oss_result = json.loads(json_str.strip())
    print(f"\n✅ Delta/Spark OSS Analysis Complete: {len(oss_result.get('items', []))} items")
except Exception as e:
    oss_result = {"vendor": "delta_spark_oss", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")

try:
    save_agent_output("84_delta_spark_oss_release_monitor", run_id, "oss_release_analysis", json.dumps(oss_result, indent=2), {"delta_writer": OSS_ENV['delta_protocol']['writer']})
except: pass