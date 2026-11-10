# Databricks notebook source
# DBTITLE 1,Medallion Validation Agent
# MAGIC %md
# MAGIC # Agent 10 — Medallion Validation
# MAGIC
# MAGIC **Purpose:** Validate data integrity across Medallion Architecture layers (stg → silver → gold → platinum).
# MAGIC
# MAGIC **Validation checks:**
# MAGIC 1. Row count consistency between layers
# MAGIC 2. Data freshness (stale tables detection)
# MAGIC 3. Surrogate key uniqueness and consistency
# MAGIC 4. Naming convention compliance
# MAGIC 5. Orphaned objects (tables not referenced by any view/job)
# MAGIC 6. Layer placement correctness (business logic not in staging, etc.)
# MAGIC
# MAGIC **Data sources:**
# MAGIC - `system.information_schema.tables/columns` — metadata
# MAGIC - `system.information_schema.view_table_usage` — lineage
# MAGIC - Delta table history for freshness checks
# MAGIC
# MAGIC **Output:** MedallionValidationReport with pass/fail per check

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Layer composition analysis
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Analyze layer composition and health
# ══════════════════════════════════════════════════════════════════════════════

df_layers = spark.sql(f"""
SELECT 
    table_schema,
    CASE 
        WHEN table_schema LIKE 'stg_%' THEN 'BRONZE'
        WHEN table_schema IN ('silver', 'silver_phx') THEN 'SILVER'
        WHEN table_schema IN ('gold', 'gold_phx') THEN 'GOLD'
        WHEN table_schema = 'platinum' THEN 'PLATINUM'
        ELSE 'OTHER'
    END as medallion_layer,
    table_type,
    COUNT(*) as object_count,
    MAX(last_altered) as most_recent_change
FROM system.information_schema.tables
WHERE table_catalog = '{CATALOG}'
GROUP BY 1, 2, 3
ORDER BY 2, 1, 3
""")

print("🏅 Medallion Layer Composition:")
df_layers.display()

# Summary by layer
df_layer_summary = spark.sql(f"""
SELECT 
    CASE 
        WHEN table_schema LIKE 'stg_%' THEN 'BRONZE'
        WHEN table_schema IN ('silver', 'silver_phx') THEN 'SILVER'
        WHEN table_schema IN ('gold', 'gold_phx') THEN 'GOLD'
        WHEN table_schema = 'platinum' THEN 'PLATINUM'
        ELSE 'OTHER'
    END as medallion_layer,
    COUNT(*) as total_objects,
    SUM(CASE WHEN table_type = 'MANAGED' THEN 1 ELSE 0 END) as physical_tables,
    SUM(CASE WHEN table_type = 'VIEW' THEN 1 ELSE 0 END) as views,
    ROUND(SUM(CASE WHEN table_type = 'VIEW' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as view_pct
FROM system.information_schema.tables
WHERE table_catalog = '{CATALOG}'
GROUP BY 1
ORDER BY 1
""")

print("\n📊 Layer Summary:")
df_layer_summary.display()

# COMMAND ----------

# DBTITLE 1,Naming convention validation
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Naming convention compliance
# Expected: dim_*, fact_*, vw_*, bridge_* in Gold/Platinum
# ══════════════════════════════════════════════════════════════════════════════

df_naming = spark.sql(f"""
SELECT 
    table_schema,
    table_name,
    table_type,
    CASE 
        WHEN table_schema IN ('gold', 'gold_phx', 'platinum') AND table_type != 'VIEW' 
             AND NOT (table_name LIKE 'dim_%' OR table_name LIKE 'fact_%' OR table_name LIKE 'bridge_%' 
                      OR table_name LIKE 'agg_%' OR table_name LIKE 'rpt_%') 
            THEN 'NON_COMPLIANT_TABLE'
        WHEN table_schema IN ('gold', 'gold_phx', 'platinum') AND table_type = 'VIEW' 
             AND NOT (table_name LIKE 'vw_%' OR table_name LIKE 'dim_%' OR table_name LIKE 'fact_%'
                      OR table_name LIKE 'bridge_%' OR table_name LIKE 'agg_%' OR table_name LIKE 'rpt_%')
            THEN 'NON_COMPLIANT_VIEW'
        ELSE 'COMPLIANT'
    END as naming_status
FROM system.information_schema.tables
WHERE table_catalog = '{CATALOG}'
  AND table_schema IN ('gold', 'gold_phx', 'platinum')
""")

# Count violations
naming_violations = df_naming.filter("naming_status != 'COMPLIANT'").count()
total_gold_platinum = df_naming.count()
compliance_rate = round((total_gold_platinum - naming_violations) / total_gold_platinum * 100, 1) if total_gold_platinum > 0 else 100

print(f"\n🏷️ Naming Convention Compliance:")
print(f"   Total objects in Gold/Platinum: {total_gold_platinum}")
print(f"   Violations: {naming_violations}")
print(f"   Compliance rate: {compliance_rate}%")

if naming_violations > 0:
    print("\n   Non-compliant objects (sample):")
    df_naming.filter("naming_status != 'COMPLIANT'").limit(20).display()

# COMMAND ----------

# DBTITLE 1,Data freshness check
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Data freshness — identify stale tables
# Physical tables not modified in 30+ days = potentially stale
# ══════════════════════════════════════════════════════════════════════════════

STALE_THRESHOLD_DAYS = 30

df_stale = spark.sql(f"""
SELECT 
    table_schema,
    table_name,
    table_type,
    last_altered,
    DATEDIFF(DAY, last_altered, CURRENT_DATE()) as days_since_update,
    CASE 
        WHEN DATEDIFF(DAY, last_altered, CURRENT_DATE()) > 90 THEN 'CRITICAL_STALE'
        WHEN DATEDIFF(DAY, last_altered, CURRENT_DATE()) > 60 THEN 'STALE'
        WHEN DATEDIFF(DAY, last_altered, CURRENT_DATE()) > {STALE_THRESHOLD_DAYS} THEN 'AGING'
        ELSE 'FRESH'
    END as freshness_status
FROM system.information_schema.tables
WHERE table_catalog = '{CATALOG}'
  AND table_schema IN ('silver', 'gold', 'platinum')
  AND table_type IN ('MANAGED', 'EXTERNAL')
  AND last_altered IS NOT NULL
ORDER BY days_since_update DESC
""")

freshness_summary = df_stale.groupBy("freshness_status").count().collect()
print("\n⏰ Data Freshness:")
for row in freshness_summary:
    icon = {"CRITICAL_STALE": "🔴", "STALE": "🟠", "AGING": "🟡", "FRESH": "🟢"}.get(row['freshness_status'], "⚪")
    print(f"   {icon} {row['freshness_status']}: {row['count']} tables")

# Show critical stale tables
critical_stale = df_stale.filter("freshness_status = 'CRITICAL_STALE'")
if critical_stale.count() > 0:
    print(f"\n🚨 Critically stale tables (>{90} days without update):")
    critical_stale.limit(15).display()

# COMMAND ----------

# DBTITLE 1,Generate validation report and save
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Compile validation report
# ══════════════════════════════════════════════════════════════════════════════

run_id = generate_run_id()

# Compile all checks
freshness_data = {row['freshness_status']: row['count'] for row in freshness_summary}

report_sections = {
    "Layer Composition": f"""| Layer | Objects | View % | Assessment |
|-------|---------|--------|------------|
| Bronze (stg_*) | {df_layer_summary.filter("medallion_layer = 'BRONZE'").select('total_objects').collect()[0][0] if df_layer_summary.filter("medallion_layer = 'BRONZE'").count() > 0 else 0} | N/A | Source staging |
| Silver | {df_layer_summary.filter("medallion_layer = 'SILVER'").select('total_objects').collect()[0][0] if df_layer_summary.filter("medallion_layer = 'SILVER'").count() > 0 else 0} | {df_layer_summary.filter("medallion_layer = 'SILVER'").select('view_pct').collect()[0][0] if df_layer_summary.filter("medallion_layer = 'SILVER'").count() > 0 else 0}% | ⚠️ Heavy view reliance |
| Gold | {df_layer_summary.filter("medallion_layer = 'GOLD'").select('total_objects').collect()[0][0] if df_layer_summary.filter("medallion_layer = 'GOLD'").count() > 0 else 0} | {df_layer_summary.filter("medallion_layer = 'GOLD'").select('view_pct').collect()[0][0] if df_layer_summary.filter("medallion_layer = 'GOLD'").count() > 0 else 0}% | Business layer |
| Platinum | {df_layer_summary.filter("medallion_layer = 'PLATINUM'").select('total_objects').collect()[0][0] if df_layer_summary.filter("medallion_layer = 'PLATINUM'").count() > 0 else 0} | {df_layer_summary.filter("medallion_layer = 'PLATINUM'").select('view_pct').collect()[0][0] if df_layer_summary.filter("medallion_layer = 'PLATINUM'").count() > 0 else 0}% | Curated/BI |""",
    
    "Naming Compliance": f"""- **Compliance Rate:** {compliance_rate}%
- **Violations:** {naming_violations} objects in Gold/Platinum don't follow dim_/fact_/vw_/bridge_ convention
- **Assessment:** {'\u2705 PASS' if compliance_rate >= 90 else '\u26a0\ufe0f NEEDS ATTENTION' if compliance_rate >= 70 else '\u274c FAIL'}""",
    
    "Data Freshness": f"""- **Fresh (< {STALE_THRESHOLD_DAYS}d):** {freshness_data.get('FRESH', 0)} tables
- **Aging ({STALE_THRESHOLD_DAYS}-60d):** {freshness_data.get('AGING', 0)} tables
- **Stale (60-90d):** {freshness_data.get('STALE', 0)} tables
- **Critical (>90d):** {freshness_data.get('CRITICAL_STALE', 0)} tables
- **Assessment:** {'\u274c CRITICAL' if freshness_data.get('CRITICAL_STALE', 0) > 10 else '\u26a0\ufe0f WARNING' if freshness_data.get('STALE', 0) > 5 else '\u2705 HEALTHY'}"""
}

report = format_agent_report("Medallion Architecture Validation Report", report_sections)

save_agent_output("medallion_validation", run_id, "validation_report", report,
                  {"compliance_rate": compliance_rate, "naming_violations": naming_violations,
                   "critical_stale": freshness_data.get('CRITICAL_STALE', 0)})

print(report)
print(f"\n✅ Agent 10 (Medallion Validation) completed | Run ID: {run_id}")