# Databricks notebook source
# DBTITLE 1,Integration Test Agent
# MAGIC %md
# MAGIC # Agent 20 — Integration Test
# MAGIC
# MAGIC **Purpose:** Generate cross-system integration test suites validating end-to-end data flows across Bronze→Silver→Gold layers.
# MAGIC
# MAGIC **Output:** IntegrationTests.md — E2E test scenarios, cross-layer validation, dependency tests.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Integration test execution
INTEGRATION_PROMPT = """You are a Senior QA Engineer specializing in data pipeline integration testing.

Generate integration test suites covering:

1. END-TO-END DATA FLOW
   - Source → Bronze (raw ingestion validation)
   - Bronze → Silver (cleansing, dedup, type casting)
   - Silver → Gold (joins, aggregations, SK generation)
   - Gold → Platinum (business aggregates)

2. CROSS-SYSTEM JOINS
   - Oracle EBS + Salesforce record matching
   - FK integrity across schemas
   - Conformed dimension consistency

3. PIPELINE DEPENDENCY TESTS
   - Upstream table freshness validation
   - Missing dependency handling (graceful failure)
   - Circular dependency detection

4. DATA VOLUME TESTS
   - Empty input handling
   - Large volume performance (>1M rows)
   - Schema evolution handling (new columns)

5. ENVIRONMENT PARITY
   - DEV vs UAT row count comparison
   - Config differences between environments

Output as executable PyTest code with fixtures and parametrized tests.
Use xxHash64 for any SK validation. Check audit columns on every table.
"""

try:
    INPUT = dbutils.widgets.get("code")
except:
    INPUT = get_latest_agent_output("unit_test", "test_suite") or get_latest_agent_output("data_engineer", "generated_code") or "Generate integration tests for the full Medallion pipeline."

run_id = generate_run_id()
result = call_agent("data_engineer", INTEGRATION_PROMPT, f"Generate integration tests for:\n\n{INPUT}", max_tokens=4000)
save_agent_output("integration_test", run_id, "integration_tests", result, {})
print(result)
print(f"\n✅ Agent 20 (Integration Test) completed | Run ID: {run_id}")