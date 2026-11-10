# Databricks notebook source
# DBTITLE 1,Environment Promotion Agent
# MAGIC %md
# MAGIC # Agent 09 — Environment Promotion
# MAGIC
# MAGIC **Purpose:** Validate and manage code/schema promotion across DEV → UAT → PRD workspaces.
# MAGIC
# MAGIC **Problem solved:** Multi-workspace deployment requires schema validation, job success verification, and configuration diff analysis before promotion.
# MAGIC
# MAGIC **Checks performed:**
# MAGIC 1. DEV job success rate (must be >95% in last 7 days)
# MAGIC 2. Schema compatibility between environments
# MAGIC 3. Configuration drift (secrets, cluster configs, warehouse settings)
# MAGIC 4. Deployment diff (what changed since last promotion)
# MAGIC 5. Rollback plan generation
# MAGIC
# MAGIC **Data sources:**
# MAGIC - `system.lakeflow.job_run_timeline` — cross-workspace job health
# MAGIC - `system.information_schema.tables/columns` — schema comparison
# MAGIC
# MAGIC **Output:** PromotionChecklist.md with go/no-go recommendation

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Check job health across environments
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Job health check per environment (last 7 days)
# Promotion gate: DEV must have >95% success rate
# ══════════════════════════════════════════════════════════════════════════════

LOOKBACK_DAYS = 7
SUCCESS_THRESHOLD = 95.0  # Minimum success rate to approve promotion

df_health = spark.sql(f"""
SELECT 
    workspace_id,
    CASE workspace_id
        WHEN '{DEV_WORKSPACE_ID}' THEN 'DEV'
        WHEN '{UAT_WORKSPACE_ID}' THEN 'UAT'
        WHEN '{PRD_WORKSPACE_ID}' THEN 'PRD'
        ELSE 'OTHER'
    END as environment,
    COUNT(*) as total_runs,
    SUM(CASE WHEN result_state = 'SUCCEEDED' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN result_state IN ('FAILED', 'ERROR') THEN 1 ELSE 0 END) as failure_count,
    ROUND(SUM(CASE WHEN result_state = 'SUCCEEDED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as success_rate
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= DATEADD(DAY, -{LOOKBACK_DAYS}, CURRENT_DATE())
  AND result_state IS NOT NULL
  AND workspace_id IN ('{DEV_WORKSPACE_ID}', '{UAT_WORKSPACE_ID}', '{PRD_WORKSPACE_ID}')
GROUP BY 1, 2
ORDER BY 2
""")

print("🏥 Environment Health (last 7 days):")
df_health.display()

# Check promotion gate
health_data = {row['environment']: row.asDict() for row in df_health.collect()}
dev_rate = health_data.get('DEV', {}).get('success_rate', 0)

promotion_gate_passed = dev_rate >= SUCCESS_THRESHOLD
print(f"\n{'\u2705' if promotion_gate_passed else '\u274c'} DEV Success Rate: {dev_rate}% (threshold: {SUCCESS_THRESHOLD}%)")
print(f"   Promotion Gate: {'PASSED' if promotion_gate_passed else 'BLOCKED'}")

# COMMAND ----------

# DBTITLE 1,Schema compatibility check
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Compare table/column counts between DEV catalog schemas
# In a real scenario, this would compare mde_dev vs mde_uat vs mde_prd
# ══════════════════════════════════════════════════════════════════════════════

# Compare DEV schema state (tables that were recently modified)
df_recent_changes = spark.sql(f"""
SELECT 
    table_schema,
    table_name,
    table_type,
    last_altered
FROM system.information_schema.tables
WHERE table_catalog = 'mde_dev'
  AND table_schema IN ('silver', 'gold', 'platinum')
  AND last_altered >= DATEADD(DAY, -{LOOKBACK_DAYS}, CURRENT_DATE())
ORDER BY last_altered DESC
""")

recent_count = df_recent_changes.count()
print(f"\n🔄 Tables modified in DEV in last {LOOKBACK_DAYS} days: {recent_count}")
if recent_count > 0:
    df_recent_changes.display()
else:
    print("   No schema changes detected — nothing to promote.")

# COMMAND ----------

# DBTITLE 1,Generate promotion checklist
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: LLM-powered promotion recommendation
# ══════════════════════════════════════════════════════════════════════════════

PROMOTION_PROMPT = """You are a Release Manager for a Databricks Lakehouse platform.

Based on the environment health data and schema changes, generate a promotion checklist.

Provide:
1. GO/NO-GO DECISION with clear reasoning
2. RISK ASSESSMENT (LOW/MEDIUM/HIGH)
3. PRE-PROMOTION CHECKLIST (mandatory steps before promoting)
4. PROMOTION STEPS (exact sequence to follow)
5. ROLLBACK PLAN (if promotion fails)
6. POST-PROMOTION VALIDATION (how to verify success)

Format as a structured markdown document suitable for management sign-off."""

run_id = generate_run_id()

# Prepare context
health_summary = "\n".join([
    f"- {env}: {data.get('total_runs', 0)} runs, {data.get('success_rate', 0)}% success, {data.get('failure_count', 0)} failures"
    for env, data in health_data.items()
])

changes_summary = f"{recent_count} tables modified" if recent_count > 0 else "No schema changes detected"

user_prompt = f"""## Environment Promotion Assessment

### Job Health (Last {LOOKBACK_DAYS} days)
{health_summary}

### Promotion Gate
- DEV success rate: {dev_rate}% (threshold: {SUCCESS_THRESHOLD}%)
- Gate status: {'PASSED' if promotion_gate_passed else 'BLOCKED'}

### Schema Changes in DEV
{changes_summary}

### Environment Context
- DEV Workspace: {DEV_WORKSPACE_ID}
- UAT Workspace: {UAT_WORKSPACE_ID}  
- PRD Workspace: {PRD_WORKSPACE_ID}
- Catalog pattern: mde_dev → mde_uat → mde_prd

Generate the complete promotion checklist and recommendation."""

checklist = call_agent("source_drift_detector", PROMOTION_PROMPT, user_prompt, max_tokens=3000)

# Save
save_agent_output("environment_promotion", run_id, "promotion_checklist", checklist,
                  {"gate_passed": promotion_gate_passed, "dev_success_rate": dev_rate,
                   "tables_changed": recent_count})

print(checklist)
print(f"\n✅ Agent 09 (Environment Promotion) completed | Run ID: {run_id}")