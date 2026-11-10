# Databricks notebook source
# DBTITLE 1,Unit Test Agent — PyTest + Nutter
# MAGIC %md
# MAGIC # Agent 08 — Unit Test Generator (PyTest + Nutter)
# MAGIC
# MAGIC **Purpose:** Generate comprehensive test suites for PySpark transformations and SQL logic using TWO frameworks:
# MAGIC - **PyTest** — function-level unit tests using `spark.createDataFrame()` (offline, no production reads)
# MAGIC - **Nutter** — Databricks notebook-based integration tests using `NutterFixture` (runs in-platform, against actual Delta tables in `mde_dev.test_schema`)
# MAGIC
# MAGIC **Test categories generated:**
# MAGIC - Schema validation (column names, types, nullability)
# MAGIC - Data quality (null counts, uniqueness, valid ranges)
# MAGIC - Business logic (transformation correctness, aggregation accuracy)
# MAGIC - Edge cases (empty DataFrames, all-null columns, duplicate keys)
# MAGIC - Regression (row count stability, xxHash64 consistency)
# MAGIC - Notebook lifecycle (Nutter: before/run/assertion/after hooks)
# MAGIC
# MAGIC **Input:** Code from Data Engineer agent or manual submission
# MAGIC **Output:** Complete PyTest file + Nutter NutterFixture notebook stub

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Load Hologic canonical DDL standards
def get_hologic_canonical_standards() -> str:
    canonical_tables = [
        f"{CATALOG}.gold.dim_customeraccount",
        f"{CATALOG}.gold.fact_ap_invoice",
    ]
    parts = ["## CANONICAL HOLOGIC DDL (production) — GENERATE TESTS THAT VALIDATE AGAINST THESE PATTERNS"]
    for tbl in canonical_tables:
        try:
            ddl = spark.sql(f"SHOW CREATE TABLE {tbl}").collect()[0][0]
            tbl_props_idx = ddl.find("TBLPROPERTIES")
            ddl_short = ddl[:tbl_props_idx] + "TBLPROPERTIES (\n  'delta.autoOptimize.autoCompact' = 'true',\n  'delta.autoOptimize.optimizeWrite' = 'true',\n  'delta.parquet.compression.codec' = 'zstd',\n  'delta.enableDeletionVectors' = 'true',\n  'delta.enableRowTracking' = 'true',\n  'delta.checkpointPolicy' = 'v2')" if tbl_props_idx > 0 else ddl
            parts.append(f"\n### {tbl}\n```sql\n{ddl_short}\n```")
        except Exception as e:
            parts.append(f"\n### {tbl}\n  [Schema read failed: {e}]")
    return "\n".join(parts)

HOLOGIC_CANONICAL_STANDARDS = get_hologic_canonical_standards()
print(f"✅ Canonical DDL loaded ({len(HOLOGIC_CANONICAL_STANDARDS)} chars) — PascalCase | dl_* audit | CLUSTER BY AUTO")

# COMMAND ----------

# DBTITLE 1,STEP 2 — Unit Test System Prompt (PyTest)
# ══════════════════════════════════════════════════════════════════════════════
# UNIT TEST AGENT
# ══════════════════════════════════════════════════════════════════════════════

UNIT_TEST_PROMPT = """You are a Senior QA Engineer specializing in PySpark and Databricks testing.

Generate a COMPLETE PyTest test suite for the given code. Follow these patterns:

## Test Structure
```python
import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime

@pytest.fixture(scope="session")
def spark():
    return SparkSession.builder.master("local[*]").getOrCreate()

@pytest.fixture
def sample_data(spark):
    # Create realistic test data matching source schema
    ...
```

## Required Test Categories

1. **Schema Tests** - Verify output table has correct columns, types
2. **Row Count Tests** - Source rows = target rows (for 1:1 transforms)
3. **Null Handling Tests** - Critical columns are NOT NULL
4. **Key Uniqueness Tests** - Surrogate keys are unique
5. **Hash Consistency Tests** - Same input → same xxHash64 output
6. **Business Logic Tests** - Transformations produce expected output
7. **Edge Case Tests** - Empty input, all nulls, duplicates
8. **Audit Column Tests** — FACTS: dl_rowhash NOT NULL, dl_creation_date_time NOT NULL, dl_last_updated_date_time NOT NULL. DIMS: dl_iscurrent NOT NULL, dl_recordstartdateutc NOT NULL. NEVER assert etl_load_datetime / etl_source_system / etl_batch_id — those are the wrong standard

## Rules
- Use `spark.createDataFrame()` with explicit schemas for test data
- Never read from production tables in unit tests
- Each test must be independent (no ordering dependency)
- Use descriptive test names: `test_<what>_<condition>_<expected>`
- Include both positive and negative test cases
- Target 90%+ code path coverage

Output the COMPLETE test file as a single Python code block.
"""

print("✅ STEP 2 complete — PyTest system prompt loaded")

# COMMAND ----------

# DBTITLE 1,Generate tests from code
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Get code to generate tests for
# ══════════════════════════════════════════════════════════════════════════════

try:
    CODE_TO_TEST = dbutils.widgets.get("code")
except:
    # Get from Data Engineer agent output
    CODE_TO_TEST = get_latest_agent_output("data_engineer", "generated_code")
    
    if not CODE_TO_TEST:
        CODE_TO_TEST = '''# Example: Silver dim_supplier transformation
from pyspark.sql import functions as F

df_suppliers = spark.read.table("mde_dev.stg_oracle_ebs.ap_suppliers")
df_sites = spark.read.table("mde_dev.stg_oracle_ebs.ap_supplier_sites_all")

df_silver = (
    df_suppliers.alias("s")
    .join(df_sites.alias("st"), F.col("s.vendor_id") == F.col("st.vendor_id"), "left")
    .select(
        F.expr("xxhash64(CONCAT_WS('|', s.vendor_id))").alias("supplier_sk"),
        F.col("s.vendor_id").alias("supplier_id"),
        F.col("s.vendor_name").alias("supplier_name"),
        F.col("s.segment1").alias("supplier_number"),
        F.col("st.city"),
        F.col("st.country"),
        F.when(F.col("s.end_date_active").isNull(), F.lit(True)).otherwise(F.lit(False)).alias("is_active"),
        F.current_timestamp().alias("etl_load_datetime"),
        F.lit("ORACLE_EBS").alias("etl_source_system"),
        F.lit("manual").alias("etl_batch_id")
    )
)

df_silver.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("mde_dev.silver.dim_supplier")
'''

run_id = generate_run_id()
print(f"Generating tests for code ({len(CODE_TO_TEST)} chars)")

# COMMAND ----------

# DBTITLE 1,Generate and save test suite
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Generate test suite
# ══════════════════════════════════════════════════════════════════════════════

user_prompt = f"""## Canonical Hologic DDL — GENERATE TESTS THAT VALIDATE AGAINST THESE PATTERNS
{HOLOGIC_CANONICAL_STANDARDS}

Generate a complete PyTest test suite for the following PySpark code:

```python
{CODE_TO_TEST}
```

The code runs in a Databricks environment with:
- Catalog: mde_dev
- Surrogate key function: xxhash64()
- Audit cols FACTS: dl_rowhash, dl_creation_date_time, dl_last_updated_date_time (NOT etl_load_datetime)
- Audit cols DIMS: dl_iscurrent, dl_recordstartdateutc, dl_recordenddateutc, dl_transform_id, dl_rowhash
- Column naming: PascalCase (Supplier_SK, Invoice_ID, AccountingDate) — NEVER snake_case

Generate the complete test file with all test categories."""

test_code = call_agent("unit_test", UNIT_TEST_PROMPT, user_prompt, max_tokens=4096)

# Save test suite
save_agent_output(
    agent_name="unit_test",
    run_id=run_id,
    output_type="test_suite",
    content=test_code,
    metadata={"source_code_length": len(CODE_TO_TEST)}
)

print("✅ Test suite generated")
print("\n" + "=" * 60)
print(test_code)
print("=" * 60)

# Count test functions
test_count = test_code.count("def test_")
print(f"\n✅ Agent 08 (Unit Test) completed | {test_count} tests generated | Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,STEP 3 — Nutter Test Notebook Generator
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Nutter Test Notebook Generator
# Generates a companion NutterFixture notebook for in-platform notebook testing
# (runs on Databricks serverless against mde_dev.test_schema scratch tables)
# ══════════════════════════════════════════════════════════════════════════════

NUTTER_SYSTEM_PROMPT = """You are a Senior QA Engineer specialising in Databricks Nutter notebook testing.

Nutter (PyPI package: nutter — NOT "databricks-nutter", which does not exist on PyPI and will
always fail to install) uses NutterFixture classes with a before/run/assertion/after lifecycle:
  before_<testcase>()     → seed data into mde_dev.test_schema
  run_<testcase>()        → execute the transform logic under test
  assertion_<testcase>()  → assert expected state (use plain Python assert)
  after_<testcase>()      → DROP TABLE mde_dev.test_schema.<scratch_table> (always!)

## Nutter Notebook Structure (4 cells)

### Cell 1 — Setup
```python
%pip install nutter -q
from runtime.nutterfixture import NutterFixture, tag
from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime
```

### Cell 2 — NutterFixture class
```python
class <TransformName>Tests(NutterFixture):

    # ─── TEST: schema_is_correct ───
    def before_schema_is_correct(self):
        # Seed minimal data into test scratch table
        ...

    def run_schema_is_correct(self):
        # Execute transform or spark.read.table()
        self.result_df = spark.read.table("mde_dev.test_schema.<table>")

    def assertion_schema_is_correct(self):
        expected = ["col1", "col2", "Supplier_SK", "dl_rowhash", "dl_creation_date_time"]  # PascalCase SKs, dl_* audit
        missing = set(expected) - set(self.result_df.columns)
        assert not missing, f"Missing columns: {missing}"

    def after_schema_is_correct(self):
        spark.sql("DROP TABLE IF EXISTS mde_dev.test_schema.<table>")

    # ─── TEST: sk_is_not_null (required for all fact/dim tables) ───
    def assertion_sk_is_not_null(self):  # no before/run needed if reusing result_df
        nulls = self.result_df.filter(F.col("<sk_col>").isNull()).count()
        assert nulls == 0, f"{nulls} null surrogate keys found"

    # ─── TEST: audit_cols_populated ───
    def assertion_audit_cols_populated(self):
        # Hologic standard: dl_* audit (NOT etl_*). FACTS need dl_rowhash + dl_creation_date_time.
        for col in ["dl_rowhash", "dl_creation_date_time", "dl_last_updated_date_time"]:
            nulls = self.result_df.filter(F.col(col).isNull()).count()
            assert nulls == 0, f"{col} has {nulls} nulls"
```

### Cell 3 — Runner
```python
result = <TransformName>Tests().execute_tests()
print(result.to_string())
assert result.run_result, "One or more Nutter tests FAILED — see output above"
```

## Rules
- ALWAYS use mde_dev.test_schema as the test catalog schema — NEVER write to silver/gold/platinum
- ALWAYS include after_* teardown (DROP TABLE IF EXISTS) to prevent Delta table leaks
- Tag regression tests with @tag("regression") — but ONLY on a `run_<testcase>` method, never on
  `assertion_<testcase>`/`before_`/`after_` — Nutter raises "a tag may only decorate a run_ method"
  otherwise (real error, confirmed live 2026-09-23). If a test case has no natural run_ step of its
  own (e.g. it only reuses another test's result_df via an assertion-only method), leave it untagged
  rather than tagging the assertion.
- before/run/assertion/after suffixes must MATCH for each test case
- Required test cases: schema_is_correct, sk_is_not_null, audit_cols_populated, row_count_matches
- For xxHash64: assert xxhash64(CONCAT_WS('|', key_col)) output is stable (same input → same hash)
- Include 4–6 test cases minimum

Generate a COMPLETE Nutter test notebook in 3 cells (setup, fixture class, runner).
Produce only Python code, no prose outside code blocks.
"""

nutter_user_prompt = f"""Generate a complete Nutter test notebook for the following PySpark/SQL code:

```python
{CODE_TO_TEST}
```

Environment:
- Test scratch schema: mde_dev.test_schema (safe for writes, protected from pipeline refreshes)
- xxHash64 surrogate keys: xxhash64(CONCAT_WS('|', key_col))
- Audit cols FACTS: dl_rowhash, dl_creation_date_time, dl_last_updated_date_time (NOT etl_load_datetime)
- Audit cols DIMS: dl_iscurrent, dl_recordstartdateutc, dl_recordenddateutc, dl_transform_id, dl_rowhash
- Column naming: PascalCase (Supplier_SK not supplier_sk)

Include: schema_is_correct, sk_is_not_null, audit_cols_populated, row_count_matches,
and one business logic test specific to the code above.
"""

nutter_notebook = call_agent("unit_test", NUTTER_SYSTEM_PROMPT, nutter_user_prompt, max_tokens=3000)

save_agent_output(
    agent_name="unit_test",
    run_id=run_id,
    output_type="nutter_test_notebook",
    content=nutter_notebook,
    metadata={"source_code_length": len(CODE_TO_TEST), "framework": "nutter"}
)

nutter_test_count = nutter_notebook.count("def assertion_")
print("✅ Nutter test notebook generated")
print("\n" + "=" * 62)
print(nutter_notebook)
print("=" * 62)
print(f"\n✅ Agent 08 Summary")
print(f"   PyTest functions:  {test_count}  (from test_code above)")
print(f"   Nutter assertions: {nutter_test_count}")
print(f"   Run ID:            {run_id}")
print("➡️  Next: 76_layer_validation_agent (validates both test suites before peer review)")