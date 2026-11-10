# Databricks notebook source
# DBTITLE 1,Scope Agent
# MAGIC %md
# MAGIC # Agent 12 — Scope
# MAGIC
# MAGIC **Purpose:** Define project scope, assumptions, risks, constraints, and exclusions from BRD input.
# MAGIC
# MAGIC **Output:** ScopeDocument.md with clear boundaries

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Scope agent execution
SCOPE_PROMPT = """You are a Senior Technical Scope Manager. From the BRD provided, produce a Scope Document:

1. IN SCOPE - specific deliverables, tables, pipelines
2. OUT OF SCOPE - explicitly excluded items
3. ASSUMPTIONS - what we're taking as given
4. CONSTRAINTS - technical/business limitations
5. RISKS - identified risks with mitigation
6. DEPENDENCIES - external teams/systems needed
7. EFFORT ESTIMATE - T-shirt sizing (S/M/L/XL) with justification

Context: Hologic Databricks Lakehouse, Medallion architecture, 15+ source systems.
Format as structured markdown."""

try:
    BRD_INPUT = dbutils.widgets.get("brd")
except:
    BRD_INPUT = get_latest_agent_output("business_analyst", "brd") or "No BRD available - provide requirement input."

run_id = generate_run_id()
result = call_agent("data_engineer", SCOPE_PROMPT, f"Create scope document from this BRD:\n\n{BRD_INPUT}", max_tokens=3000)
save_agent_output("scope", run_id, "scope_document", result, {})
print(result)
print(f"\n✅ Agent 12 (Scope) completed | Run ID: {run_id}")