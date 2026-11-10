# Databricks notebook source
# DBTITLE 1,CI/CD Agent
# MAGIC %md
# MAGIC # Agent 24 — CI/CD
# MAGIC
# MAGIC **Purpose:** Generate Azure DevOps Pipelines, GitHub Actions workflows, and Declarative Automation Bundles (DABs) configurations.
# MAGIC
# MAGIC **Output:** azure-pipelines.yml, GitHub Actions YAML, databricks.yml bundle configs.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,CI/CD execution
CICD_PROMPT = """You are a CI/CD Engineer generating deployment pipelines for Databricks.

Generate production-ready pipeline configurations for:

1. AZURE DEVOPS PIPELINE (azure-pipelines.yml)
   - Stages: Build, Test, Deploy-DEV, Deploy-UAT, Deploy-PRD
   - Use Databricks CLI for deployments
   - Include approval gates between UAT and PRD
   - Run unit tests via pytest on Databricks

2. GITHUB ACTIONS (if requested)
   - Similar stages as above
   - Use databricks/setup-cli action
   - Secrets via GitHub Secrets

3. DECLARATIVE AUTOMATION BUNDLES (databricks.yml)
   - Bundle configuration for notebooks/jobs/pipelines
   - Target environments: dev, uat, prd
   - Variable substitution per environment
   - Workspace mapping

4. DEPLOYMENT SCRIPTS
   - databricks bundle deploy --target <env>
   - Pre/post deployment validation
   - Rollback commands

Hologic environment:
- DEV workspace: 6617965257274108
- UAT workspace: 7982886777824011
- PRD workspace: 685145432798888
- Catalog pattern: mde_dev / mde_uat / mde_prd

Generate complete, runnable YAML files.
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = get_latest_agent_output("dataops", "dataops_framework") or "Generate CI/CD pipelines for deploying notebooks and workflows across DEV/UAT/PRD."

run_id = generate_run_id()
result = call_agent("data_engineer", CICD_PROMPT, f"Generate CI/CD configurations for:\n\n{INPUT}", max_tokens=4000)
save_agent_output("cicd", run_id, "cicd_config", result, {})
print(result)
print(f"\n✅ Agent 24 (CI/CD) completed | Run ID: {run_id}")