# Databricks notebook source
# DBTITLE 1,Project Manager Agent
# MAGIC %md
# MAGIC # Agent 13 — Project Manager
# MAGIC
# MAGIC **Purpose:** Generate sprint plans, roadmaps, and dependency maps from scope documents.
# MAGIC
# MAGIC **Output:** ProjectPlan.md with sprints, milestones, and resource allocation

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Project Manager agent execution
PM_PROMPT = """You are an Agile Project Manager for a Databricks data engineering team.

From the scope document, produce:
1. SPRINT PLAN - 2-week sprints with specific deliverables
2. MILESTONES - key checkpoints with dates (relative: Sprint 1, Sprint 2...)
3. DEPENDENCIES - what blocks what, critical path
4. RESOURCE ALLOCATION - roles needed per sprint
5. RISK REGISTER - risks with probability, impact, mitigation
6. DEFINITION OF DONE - per deliverable

Assume: Team of 2-3 data engineers, 2-week sprints, DEV→UAT→PRD promotion cycle.
Format as markdown with tables."""

try:
    SCOPE_INPUT = dbutils.widgets.get("scope")
except:
    SCOPE_INPUT = get_latest_agent_output("scope", "scope_document") or "No scope document available."

run_id = generate_run_id()
result = call_agent("data_engineer", PM_PROMPT, f"Create project plan from:\n\n{SCOPE_INPUT}", max_tokens=3000)
save_agent_output("project_manager", run_id, "project_plan", result, {})
print(result)
print(f"\n✅ Agent 13 (Project Manager) completed | Run ID: {run_id}")