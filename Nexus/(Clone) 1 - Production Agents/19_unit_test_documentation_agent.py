# Databricks notebook source
# DBTITLE 1,Unit Test Documentation Agent
# MAGIC %md
# MAGIC # Agent 19 — Unit Test Documentation
# MAGIC
# MAGIC **Purpose:** Generate comprehensive test case documentation with scenarios, expected results, edge cases, and traceability to requirements.
# MAGIC
# MAGIC **Output:** UnitTestDocument.md — test matrix, scenarios, expected/actual, pass criteria.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Unit test documentation execution
TEST_DOC_PROMPT = """You are a QA Documentation Specialist. Generate a Unit Test Document with:

1. TEST MATRIX
   - Table mapping: requirement → test case → priority
   - Coverage percentage per requirement

2. TEST SCENARIOS (for each table/transformation):
   - Schema validation (column types, nullability, count)
   - Null/empty checks on required fields
   - Uniqueness validation on surrogate keys
   - Referential integrity (FK → PK exists)
   - Business rule validation (ranges, formats, enums)
   - Edge cases (empty datasets, duplicates, late-arriving data)
   - SCD Type handling (if applicable)

3. EXPECTED RESULTS
   - Input data sample (3-5 rows)
   - Expected output after transformation
   - Expected row counts and aggregates

4. PASS/FAIL CRITERIA
   - What constitutes a pass vs failure
   - Tolerance thresholds for numeric comparisons
   - Date boundary handling

5. TRACEABILITY
   - Map each test to the source requirement or user story

Format as structured markdown with tables.
"""

try:
    INPUT = dbutils.widgets.get("code")
except:
    INPUT = get_latest_agent_output("unit_test", "test_suite") or get_latest_agent_output("data_engineer", "generated_code") or "Generate test documentation for a standard dimension table."

run_id = generate_run_id()
result = call_agent("data_engineer", TEST_DOC_PROMPT, f"Generate test documentation for:\n\n{INPUT}", max_tokens=3500)
save_agent_output("unit_test_documentation", run_id, "test_document", result, {})
print(result)
print(f"\n✅ Agent 19 (Unit Test Documentation) completed | Run ID: {run_id}")