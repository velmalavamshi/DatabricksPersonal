# Databricks notebook source
# DBTITLE 1,Metadata and Lineage Agent
# MAGIC %md
# MAGIC # Agent 22 — Metadata & Lineage
# MAGIC
# MAGIC **Purpose:** Map data lineage (table and column level), maintain business glossary, and ensure Unity Catalog metadata is complete.
# MAGIC
# MAGIC **Output:** DataLineage.md, BusinessGlossary.md, column-level lineage maps.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Metadata lineage execution
LINEAGE_PROMPT = """You are a Data Governance Specialist focused on metadata and lineage at Hologic.

1. TABLE-LEVEL LINEAGE
   - Map source → Bronze → Silver → Gold → Platinum flow
   - Identify orphan tables (no upstream or downstream)
   - Query: system.information_schema.table_lineage (if available)

2. COLUMN-LEVEL LINEAGE
   - Track transformations per column
   - Identify SK generation lineage (xxhash64 source columns)
   - Map audit columns back to ETL process

3. BUSINESS GLOSSARY
   - Define business terms for key columns
   - Map technical names to business names
   - Recommend Unity Catalog COMMENT updates

4. METADATA COMPLETENESS
   - Tables missing comments
   - Columns missing descriptions
   - % coverage score
   - Generate ALTER TABLE/COLUMN COMMENT statements

5. IMPACT ANALYSIS
   - If table X changes, what downstream is affected?
   - Critical path identification
   - Blast radius scoring

Output as markdown with mermaid diagrams for lineage flows where helpful.
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = "Map full lineage for the Oracle EBS AP module tables from stg_oracle_ebs through Gold."

run_id = generate_run_id()
result = call_agent("data_engineer", LINEAGE_PROMPT, f"Perform lineage analysis for:\n\n{INPUT}", max_tokens=3500)
save_agent_output("metadata_lineage", run_id, "lineage_report", result, {})
print(result)
print(f"\n✅ Agent 22 (Metadata & Lineage) completed | Run ID: {run_id}")