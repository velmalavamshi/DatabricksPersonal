# Databricks notebook source
# DBTITLE 1,Agent 92: Qlik Expression Agent
﻿# Databricks notebook source
%md
# Agent 92: Qlik Expression Agent

**Purpose:** Converts Qlik expressions (set analysis, AGGR(), variables, conditional logic) to Databricks SQL / Lakeview expressions.

**Pipeline Position:** Specialist Layer → called by Agent 88 (orchestrator)

**Inputs:**
- Qlik expression text (from charts, KPIs, calculated dimensions)
- Variable definitions (SET/LET)
- Set analysis expressions with modifiers

**Outputs:**
- Databricks SQL equivalents (for views, Lakeview datasets)
- Window function translations (for AGGR, Above, Below)
- Variable → parameter/CTE mapping

**Qlik Expression Constructs:**
- Set Analysis: `Sum({<Year={2024}, Region-={'APAC'}>} Sales)`
- AGGR(): `Aggr(Sum(Sales), Customer, Region)` (nested aggregation)
- Variables: `=$(vCurrentYear)` (expression variables with $ expansion)
- Conditional: `If(Flag=1, Sum(A), Sum(B))`
- Total qualifier: `Sum(TOTAL <Region> Sales)` (dimension bypass)
- Set operators: `*` (AND), `+` (OR), `-` (NOT), `/` (XOR)
- P() / E(): Possible/Excluded values in set context
- Element functions: `=Sum({1} Sales)` (ignore selections)

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "Expression Conversion Request")
dbutils.widgets.multiline("qlik_expression", "", "Qlik Expression (paste here)")
dbutils.widgets.multiline("variables", "", "Qlik Variables (SET/LET definitions)")
dbutils.widgets.dropdown("target", "sql", ["sql", "lakeview", "pyspark"], "Target Format")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
qlik_expression = dbutils.widgets.get("qlik_expression")
variables = dbutils.widgets.get("variables")
target = dbutils.widgets.get("target")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context — Set Analysis & Expression Translation Rules
# ══════════════════════════════════════════════════════════════════════

# Set Analysis → SQL WHERE clause patterns
SET_ANALYSIS_TO_SQL = {
    "Sum({<Year={2024}>} Sales)": "SUM(CASE WHEN Year = 2024 THEN Sales END)",
    "Sum({<Region-={'APAC'}>} Sales)": "SUM(CASE WHEN Region != 'APAC' THEN Sales END)",
    "Sum({<Year={2024}, Region={'US','EU'}>} Sales)": "SUM(CASE WHEN Year=2024 AND Region IN ('US','EU') THEN Sales END)",
    "Sum({1} Sales)": "SUM(Sales) -- ignores all selections (full dataset)",
    "Sum({$<Year={2024}>} Sales)": "SUM(CASE WHEN Year=2024 THEN Sales END) -- $ = current selections + modifier",
    "Count({<Status={'Active'}>} DISTINCT CustomerID)": "COUNT(DISTINCT CASE WHEN Status='Active' THEN CustomerID END)",
    "Sum({<Year=P(Year)>} Sales)": "-- P() = possible values; translate to subquery or parameter",
    "Sum({<Year=E(Year)>} Sales)": "-- E() = excluded values; translate to NOT IN subquery",
}

# AGGR() → Window functions / subqueries
AGGR_TO_SQL = {
    "Aggr(Sum(Sales), Customer)": "SELECT Customer, SUM(Sales) FROM ... GROUP BY Customer -- then JOIN back",
    "Aggr(NODISTINCT Sum(Sales), Customer, Year)": "SUM(Sales) OVER (PARTITION BY Customer, Year)",
    "Max(Aggr(Sum(Sales), Customer))": "SELECT MAX(customer_total) FROM (SELECT Customer, SUM(Sales) as customer_total ...)",
    "Only(Aggr(Count(OrderID), Customer))": "Scalar subquery: (SELECT COUNT(OrderID) FROM ... WHERE Customer = outer.Customer)",
}

# TOTAL qualifier → Window functions
TOTAL_TO_SQL = {
    "Sum(TOTAL Sales)": "SUM(Sales) OVER ()",
    "Sum(TOTAL <Region> Sales)": "SUM(Sales) OVER (PARTITION BY Region)",
    "Sum(Sales) / Sum(TOTAL Sales)": "SUM(Sales) / SUM(Sales) OVER () -- % of total",
    "Rank(TOTAL Sum(Sales))": "RANK() OVER (ORDER BY SUM(Sales) DESC)",
}

# Common Qlik functions → SQL
EXPRESSION_FUNCTIONS = {
    "Above(Sum(Sales))": "LAG(SUM(Sales)) OVER (ORDER BY ...)",
    "Below(Sum(Sales))": "LEAD(SUM(Sales)) OVER (ORDER BY ...)",
    "Above(Sum(Sales), 0, RowNo())": "SUM(SUM(Sales)) OVER (ORDER BY ... ROWS UNBOUNDED PRECEDING) -- running total",
    "RangeSum(Above(Sales, 0, RowNo()))": "SUM(Sales) OVER (ORDER BY ... ROWS UNBOUNDED PRECEDING)",
    "Rank(Sum(Sales))": "RANK() OVER (ORDER BY SUM(Sales) DESC)",
    "If(Sum(Sales)>0, Sum(Sales)/Sum(Cost), 0)": "CASE WHEN SUM(Sales)>0 THEN SUM(Sales)/SUM(Cost) ELSE 0 END",
    "Dual('Active', 1)": "-- Use a CASE WHEN or lookup table for dual-coded values",
    "Class(Amount, 1000)": "FLOOR(Amount / 1000) * 1000 -- binning",
    "Frac(Amount)": "Amount - FLOOR(Amount)",
    "Ceil(Amount, 100)": "CEIL(Amount / 100) * 100",
}

print(f"✅ Expression translation context loaded")
print(f"   {len(SET_ANALYSIS_TO_SQL)} set analysis patterns")
print(f"   {len(AGGR_TO_SQL)} AGGR patterns")
print(f"   {len(TOTAL_TO_SQL)} TOTAL qualifier patterns")
print(f"   {len(EXPRESSION_FUNCTIONS)} function mappings")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting
# ══════════════════════════════════════════════════════════════════════

import json

system_prompt = f"""You are the Qlik Expression Agent (Agent 92) for Hologic's NEXUS platform.

You convert Qlik expressions to {target.upper()} equivalents for Databricks.

Set Analysis Translation:
{json.dumps(SET_ANALYSIS_TO_SQL, indent=2)}

AGGR() Translation:
{json.dumps(AGGR_TO_SQL, indent=2)}

TOTAL Qualifier Translation:
{json.dumps(TOTAL_TO_SQL, indent=2)}

Function Mappings:
{json.dumps(EXPRESSION_FUNCTIONS, indent=2)}

Key Translation Principles:
1. Set Analysis modifiers → CASE WHEN inside aggregate (or WHERE clause if applied to entire measure)
2. Set {1} (full set, ignore selections) → no WHERE clause / separate CTE without filters
3. Set $ (current selections) → the dashboard filter context (Lakeview parameters)
4. AGGR() → either window function (if result used inline) or subquery/CTE (if nested)
5. TOTAL qualifier → window function with OVER (PARTITION BY ...)
6. Variables ($=expression) → CTEs, view definitions, or Lakeview dataset parameters
7. Above/Below/Previous → LAG/LEAD window functions
8. Rank/RangeSum → RANK/SUM OVER with appropriate frame

Output Format: {target}
- sql: Standard Databricks SQL (for views, Lakeview datasets)
- lakeview: SQL optimized for Lakeview widget expressions
- pyspark: PySpark DataFrame operations with window functions
"""

user_prompt = f"""Request: {request}
Target Format: {target}

Qlik Expression(s) to Convert:
```
{qlik_expression or '[No expression provided]'}
```

Variables in Scope:
```
{variables or '[No variables]'}
```

Please convert these Qlik expressions to {target} with explanation of the translation logic."""

print(f"✅ Prompts formatted — Target: {target}")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call
# ══════════════════════════════════════════════════════════════════════

response = call_agent(
    agent_name="92_qlik_expression",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=4096
)

print(response)

# COMMAND ----------

# DBTITLE 1,STEP 5 - Validate and Persist
# ══════════════════════════════════════════════════════════════════════
# STEP 5: Validate & Persist
# ══════════════════════════════════════════════════════════════════════

assert len(response) > 100, "Response too short"

save_agent_output(
    agent_name="92_qlik_expression",
    run_id=run_id,
    output_type=f"expression_conversion_{target}",
    content=response,
    metadata={"target": target, "expression_count": qlik_expression.count('\n') + 1 if qlik_expression else 0}
)

print(f"\n✅ Agent 92 complete — expressions converted to {target}")
print(f"📋 Run ID: {run_id}")

# COMMAND ----------

