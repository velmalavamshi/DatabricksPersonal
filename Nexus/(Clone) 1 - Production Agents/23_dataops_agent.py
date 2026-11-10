# Databricks notebook source
# DBTITLE 1,DataOps Agent
# MAGIC %md
# MAGIC # Agent 23 — DataOps
# MAGIC
# MAGIC **Purpose:** Design CI/CD frameworks, Git branching strategies, release management processes, and DevOps patterns for Databricks.
# MAGIC
# MAGIC **Output:** DataOpsFramework.md, GitStrategy.md, BranchingModel.md.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,DataOps execution
DATAOPS_PROMPT = """You are a DataOps Engineer designing CI/CD and release processes for Databricks.

1. GIT STRATEGY
   - Branching model: GitFlow vs trunk-based (recommend for data engineering)
   - Branch naming: feature/, bugfix/, release/, hotfix/
   - PR requirements: approvals, CI checks, test pass

2. CI/CD DESIGN
   - Pipeline stages: lint → test → build → deploy → validate
   - Databricks Asset Bundles (DABs) for deployment
   - Environment promotion: DEV → UAT → PRD
   - Secrets management across environments

3. RELEASE MANAGEMENT
   - Semantic versioning for notebooks/pipelines
   - Change log automation
   - Rollback strategy (Delta Time Travel for data, Git revert for code)

4. ENVIRONMENT MANAGEMENT
   - Workspace isolation strategy (16 workspaces)
   - Config-as-code (catalog/schema per environment)
   - Feature flags for gradual rollout

5. QUALITY GATES
   - Pre-merge: unit tests pass, lint clean, peer review
   - Pre-deploy: integration tests, security scan
   - Post-deploy: smoke test, data validation

Produce a complete DataOps framework document.
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = "Design the DataOps framework for Hologic's 16-workspace Databricks environment."

run_id = generate_run_id()
result = call_agent("data_engineer", DATAOPS_PROMPT, f"Design DataOps framework for:\n\n{INPUT}", max_tokens=3500)
save_agent_output("dataops", run_id, "dataops_framework", result, {})
print(result)
print(f"\n✅ Agent 23 (DataOps) completed | Run ID: {run_id}")