# Databricks notebook source
# DBTITLE 1,Hash Migration Agent
# MAGIC %md
# MAGIC # Agent 34 — Hash Migration
# MAGIC
# MAGIC **Purpose:** Generate xxHash64 migration scripts from the hash_migration_analysis table. Handles 1,538 tables, 7,978 SK columns, 8.73B rows.
# MAGIC
# MAGIC **Output:** Migration DDL, validation queries, rollback scripts, batch execution plans.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Hash migration execution
HASH_MIGRATION_PROMPT = """You are a Hash Migration Engineer executing the MD5 → xxHash64 surrogate key migration at Hologic.

Context (from mde_dev.test_schema.hash_migration_analysis):
- 1,538 tables with MD5-based surrogate keys
- 7,978 SK columns to migrate
- 8.73 billion total rows
- Savings: 175.8 GB VertiPaq (53%), 1.51 TB/refresh I/O (75%)

Migration pattern for each table:

1. ADD NEW COLUMN
   ALTER TABLE catalog.schema.table ADD COLUMN {column_name}_new STRING;  -- Hologic SK type is STRING (xxhash64 cast to STRING)

2. POPULATE WITH xxHash64
   UPDATE catalog.schema.table
   SET {column_name}_new = CAST(xxhash64(CONCAT_WS('|', {business_key_columns})) AS STRING);  -- STRING per Hologic DDL standard

3. VALIDATE
   - Uniqueness check on new column
   - NULL check (should be 0 nulls)
   - Cardinality comparison (old vs new should match)
   - Join validation (FK references still resolve)

4. SWAP COLUMNS
   ALTER TABLE catalog.schema.table DROP COLUMN {column_name};
   ALTER TABLE catalog.schema.table RENAME COLUMN {column_name}_new TO {column_name};

5. UPDATE DOWNSTREAM
   - Regenerate views referencing this SK
   - Update FK references in child tables
   - Rebuild indexes/clustering

Batch strategy:
- Phase 1: Dimension tables (smallest, fewest dependencies)
- Phase 2: Fact tables (largest, most FKs)
- Phase 3: Bridge tables
- Phase 4: Aggregate tables

Generate executable scripts with error handling and rollback.
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = "Generate the migration script for the next batch of tables from hash_migration_analysis."

run_id = generate_run_id()
result = call_agent("data_engineer", HASH_MIGRATION_PROMPT, f"Generate hash migration scripts for:\n\n{INPUT}", max_tokens=4000)
save_agent_output("hash_migration", run_id, "migration_script", result, {})
print(result)
print(f"\n✅ Agent 34 (Hash Migration) completed | Run ID: {run_id}")