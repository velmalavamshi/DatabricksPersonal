# Databricks notebook source
# DBTITLE 1,Agent 90: Qlik Script Conversion Agent
﻿# Databricks notebook source
%md
# Agent 90: Qlik Script Conversion Agent

**Purpose:** Parses QlikView/Qlik Sense load scripts (from QVW, QVF, and QVS include files) and converts them to PySpark or Databricks SQL equivalents.

**Pipeline Position:** Specialist Layer → called by Agent 88 (orchestrator)

**Inputs:**
- QVW/QVF load script text (extracted from app metadata)
- QVS include file contents
- Source connection details (OLEDB, ODBC, REST, file paths)

**Outputs:**
- PySpark notebook cells (equivalent ETL logic)
- Databricks SQL statements
- Spark Declarative Pipeline (SDP) definitions where appropriate
- Mapping report: Qlik statement → Spark equivalent

**Qlik Script Constructs Handled:**
- LOAD ... FROM (file), LOAD ... SQL SELECT (database)
- Preceding LOAD (stacked transformations)
- Resident LOAD (in-memory re-reads)
- JOIN / CONCATENATE / OUTER JOIN
- MAPPING LOAD + ApplyMap()
- IntervalMatch, Generic LOAD
- FOR EACH / NEXT loops (parameterized loads)
- SET / LET variables
- STORE INTO QVD
- QUALIFY / UNQUALIFY
- Binary Load (load from another QVW)

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "Script Conversion Request")
dbutils.widgets.multiline("qlik_script", "", "Qlik Load Script (paste here)")
dbutils.widgets.dropdown("output_format", "pyspark", ["pyspark", "sql", "sdp"], "Output Format")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
qlik_script = dbutils.widgets.get("qlik_script")
output_format = dbutils.widgets.get("output_format")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context — Qlik Script → Spark Translation Rules
# ══════════════════════════════════════════════════════════════════════

# Qlik-to-Spark statement mapping
SCRIPT_TRANSLATION_MAP = {
    "LOAD ... FROM [file.qvd]": "spark.read.format('delta').load() or read_files()",
    "LOAD ... SQL SELECT": "spark.read.jdbc() or Lakehouse Federation",
    "Preceding LOAD": "Chained .withColumn() or CTE in SQL",
    "Resident LOAD": "Reference existing DataFrame (no reload)",
    "JOIN (LOAD)": ".join() with explicit keys",
    "CONCATENATE": ".union() / .unionByName()",
    "MAPPING LOAD + ApplyMap()": "broadcast join or map_from_arrays()",
    "IntervalMatch": "Range join (inequality join condition)",
    "Generic LOAD": "pivot() / unpivot()",
    "FOR EACH / NEXT": "List comprehension + reduce() or loop over partitions",
    "SET / LET variables": "Python variables or Spark conf",
    "STORE INTO QVD": ".write.format('delta').saveAsTable()",
    "QUALIFY *": "Prefix all columns with table name (alias strategy)",
    "UNQUALIFY": "Remove prefix (standard column names)",
    "Binary Load": "Read from source Delta table directly",
    "WHERE EXISTS()": ".join(other_df, 'key').select(original_cols) (semi-join)",
    "GROUP BY": ".groupBy().agg()",
    "ORDER BY": ".orderBy() (avoid unless needed for output)",
    "DISTINCT": ".distinct() or .dropDuplicates()",
    "NoConcatenate": "Separate DataFrame (new variable)",
    "AutoNumber": "monotonically_increasing_id() or row_number()",
    "Dual()": "Named struct or lookup table",
}

# Qlik functions to Spark SQL equivalents
FUNCTION_MAP = {
    "Date()": "date_format() / to_date()",
    "Num()": "cast() to numeric",
    "Text()": "cast() to string",
    "Left()": "left() / substring()",
    "Right()": "right() / substring()",
    "Mid()": "substring()",
    "Len()": "length()",
    "SubField()": "split() + element_at()",
    "If()": "CASE WHEN ... THEN ... ELSE ... END / when().otherwise()",
    "Match()": "CASE WHEN col IN (...)",
    "MixMatch()": "lower(col) IN (lower(...))",
    "WildMatch()": "col LIKE pattern (multiple)",
    "Aggr()": "Window function or subquery aggregate",
    "RangeSum()": "SUM() OVER (running total)",
    "Above()/Below()": "LAG() / LEAD()",
    "Peek()": "LAG() window function",
    "Previous()": "LAG(col, 1)",
    "RowNo()": "row_number() OVER (...)",
    "AutoNumber()": "dense_rank() or xxhash64()",
    "ApplyMap()": "LEFT JOIN to mapping table",
    "MapSubstring()": "regexp_replace() with map",
    "Exists()": "Semi-join / WHERE col IN (SELECT ...)",
}

print(f"✅ Translation rules loaded: {len(SCRIPT_TRANSLATION_MAP)} statement patterns, {len(FUNCTION_MAP)} function mappings")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting
# ══════════════════════════════════════════════════════════════════════

import json

system_prompt = f"""You are the Qlik Script Conversion Agent (Agent 90) for Hologic's NEXUS platform.

You convert QlikView/Qlik Sense load scripts to {output_format.upper()} equivalents on Databricks.

Translation Rules:
{json.dumps(SCRIPT_TRANSLATION_MAP, indent=2)}

Function Mappings:
{json.dumps(FUNCTION_MAP, indent=2)}

Output Requirements:
- Generate production-ready {output_format} code
- Preserve all business logic faithfully
- Add comments showing original Qlik line for traceability
- Apply Hologic standards: xxhash64 SKs, audit columns, Liquid Clustering
- Handle Qlik's implicit AUTOGENERATE and concatenation behavior
- Convert SET/LET variables to Python variables or widget parameters
- Flag any constructs that have no direct Spark equivalent (manual review needed)

Common Pitfalls:
- Qlik JOIN is LEFT JOIN by default (not INNER)
- Qlik CONCATENATE auto-matches by column name (like UNION BY NAME)
- Preceding LOAD applies AFTER the inner LOAD completes
- Resident LOAD re-reads the ENTIRE table (watch for filter pushdown loss)
- ApplyMap default value behavior (3rd param) must be explicitly handled
"""

user_prompt = f"""Request: {request}
Output Format: {output_format}

Qlik Script to Convert:
```qlik
{qlik_script or '[No script provided - provide general conversion guidance]'}
```

Please convert this Qlik script to {output_format} with full traceability comments."""

print(f"✅ Prompts formatted — Output format: {output_format}")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call
# ══════════════════════════════════════════════════════════════════════

response = call_agent(
    agent_name="90_qlik_script_conversion",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=6144  # Scripts can generate long outputs
)

print(response)

# COMMAND ----------

# DBTITLE 1,STEP 5 - Validate and Persist
# ══════════════════════════════════════════════════════════════════════
# STEP 5: Validate & Persist
# ══════════════════════════════════════════════════════════════════════

assert len(response) > 100, "Response too short"

save_agent_output(
    agent_name="90_qlik_script_conversion",
    run_id=run_id,
    output_type=f"script_conversion_{output_format}",
    content=response,
    metadata={"output_format": output_format, "script_length": len(qlik_script)}
)

print(f"\n✅ Agent 90 complete — script converted to {output_format}")
print(f"📋 Run ID: {run_id}")

# COMMAND ----------

