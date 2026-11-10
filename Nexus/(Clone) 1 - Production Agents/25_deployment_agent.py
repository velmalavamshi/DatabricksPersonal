# Databricks notebook source
# DBTITLE 1,Deployment Agent
# MAGIC %md
# MAGIC # Agent 25 — Deployment
# MAGIC
# MAGIC **Purpose:** Generate deployment plans, environment promotion scripts, and release checklists for DEV→UAT→PRD migration.
# MAGIC
# MAGIC **Output:** DeploymentGuide.md, promotion scripts, pre/post deployment checks.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Deployment execution
DEPLOYMENT_PROMPT = """You are a Release Engineer producing deployment plans for Databricks.

1. PRE-DEPLOYMENT CHECKLIST
   - All unit tests pass
   - Peer review approved
   - Security scan clean
   - UAT sign-off obtained
   - Rollback plan documented

2. DEPLOYMENT STEPS
   - Database objects (CREATE/ALTER DDL)
   - Notebooks/code (bundle deploy or workspace import)
   - Workflow definitions (Jobs API)
   - Permissions (GRANT statements)
   - Secrets (scope management)

3. POST-DEPLOYMENT VALIDATION
   - Smoke test queries (verify data flows)
   - Row count comparison (DEV vs PRD)
   - Schema validation (columns, types)
   - Permission verification

4. ROLLBACK PLAN
   - Delta Time Travel for data: RESTORE TABLE TO VERSION AS OF
   - Git revert for code
   - Workflow rollback (previous job definition)

5. COMMUNICATION
   - Stakeholder notification template
   - Change Advisory Board (CAB) submission format

Environments:
- DEV: mde_dev catalog, workspace 6617965257274108
- UAT: mde_uat catalog, workspace 7982886777824011
- PRD: mde_prd catalog, workspace 685145432798888
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = get_latest_agent_output("cicd", "cicd_config") or "Generate a deployment plan for promoting a new Gold layer table from DEV to PRD."

run_id = generate_run_id()
result = call_agent("data_engineer", DEPLOYMENT_PROMPT, f"Generate deployment plan for:\n\n{INPUT}", max_tokens=3500)
save_agent_output("deployment", run_id, "deployment_plan", result, {})
print(result)
print(f"\n✅ Agent 25 (Deployment) completed | Run ID: {run_id}")