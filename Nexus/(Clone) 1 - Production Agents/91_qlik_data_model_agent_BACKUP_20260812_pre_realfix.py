# Databricks notebook source
# DBTITLE 1,Agent 91: Qlik Data Model Agent
﻿# Databricks notebook source
%md
# Agent 91: Qlik Data Model Agent

**Purpose:** Analyzes QlikView/Qlik Sense associative data models and converts them to Kimball star schemas in Databricks (Gold layer).

**Pipeline Position:** Specialist Layer → called by Agent 88 (orchestrator)

**Inputs:**
- QVW/QVF data model metadata (tables, fields, associations)
- Synthetic key reports
- Table viewer exports

**Outputs:**
- Kimball star schema design (facts, dims, bridges)
- Association → JOIN mapping
- Synthetic key resolution strategy
- Circular reference remediation plan
- ERD documentation

**Qlik Associative Model Concepts:**
- Tables auto-associate on matching field names (no explicit FK/PK)
- Synthetic keys: auto-generated when 2+ fields match between tables
- Circular references: blocked by Qlik (must be resolved with QUALIFY or link tables)
- Link tables: denormalized bridge tables to avoid synthetic keys
- Loosely coupled tables: islands connected only through shared fields

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "Data Model Request")
dbutils.widgets.multiline("model_metadata", "", "Qlik Data Model Metadata (paste table/field list)")
dbutils.widgets.text("app_name", "", "Qlik App Name")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
model_metadata = dbutils.widgets.get("model_metadata")
app_name = dbutils.widgets.get("app_name")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context — Qlik Associative → Kimball Mapping Rules
# ══════════════════════════════════════════════════════════════════════

# Qlik model patterns and their Kimball equivalents
MODEL_CONVERSION_RULES = {
    "Transaction table (high row count, date + amount fields)": "FACT table",
    "Lookup table (low cardinality, descriptive fields)": "DIM table (Type 1 SCD)",
    "Slowly changing lookup (effective dates)": "DIM table (Type 2 SCD)",
    "Link table (multi-key bridge)": "BRIDGE table or factless fact",
    "Calendar/MasterCalendar": "dim_date (standard date dimension)",
    "Mapping table (2-column lookup)": "Embedded in DIM or lookup view",
    "Concatenated tables": "UNION view or consolidated fact",
    "Islands (disconnected table groups)": "Separate subject areas / data marts",
}

# Synthetic key resolution strategies
SYNTHETIC_KEY_STRATEGIES = {
    "Composite key fields are all business keys": "Create xxhash64 surrogate key on the composite",
    "Extra unintended matching fields": "QUALIFY one table's field to break the association",
    "Legitimate multi-field relationship": "Create explicit link/bridge table with compound key",
    "Date + other field matching": "Rename generic 'Date' to specific 'OrderDate', 'ShipDate'",
}

# Circular reference resolution
CIRCULAR_REF_STRATEGIES = {
    "Self-referencing hierarchy (e.g., Manager-Employee)": "Bridge table with HierarchyBelongsTo()",
    "Multiple paths between tables": "QUALIFY one path, create separate relationship",
    "Date table linking to multiple date fields": "Role-playing dims (dim_order_date, dim_ship_date)",
}

print(f"✅ Data model context loaded")
print(f"   {len(MODEL_CONVERSION_RULES)} conversion rules")
print(f"   {len(SYNTHETIC_KEY_STRATEGIES)} synthetic key strategies")
print(f"   {len(CIRCULAR_REF_STRATEGIES)} circular ref remediation patterns")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting
# ══════════════════════════════════════════════════════════════════════

system_prompt = """You are the Qlik Data Model Agent (Agent 91) for Hologic's NEXUS platform.

You convert Qlik's associative data models to Kimball star schemas for Databricks Gold layer.

Qlik Associative Model:
- Tables auto-associate on identically named fields (implicit FK relationships)
- NO explicit primary/foreign keys — associations are inferred
- Synthetic keys appear when 2+ fields match between tables
- Circular references are blocked (must resolve with QUALIFY or link tables)

Your Analysis Process:
1. IDENTIFY table types: fact (transactions), dim (lookups), bridge (link tables)
2. MAP associations to explicit JOIN relationships with cardinality
3. RESOLVE synthetic keys using appropriate strategy
4. DETECT circular references and propose remediation
5. DESIGN Kimball star schema: facts, dims, bridges, role-playing dims
6. GENERATE DDL with xxhash64 surrogate keys, audit columns, Liquid Clustering

Naming Conventions (Hologic):
- Facts: fact_<business_process> (e.g., fact_sales_order)
- Dims: dim_<entity> (e.g., dim_customer, dim_product)
- Bridges: bridge_<relationship> (e.g., bridge_product_category)
- Date dims: dim_date (single, role-played via FK naming)
- Aggregates: agg_<grain>_<measure>

Key Design Decisions:
- Qlik 'islands' (disconnected groups) → separate data marts in Gold
- Calendar/MasterCalendar → dim_date with fiscal periods
- Link tables → bridge tables OR denormalized into fact
- Mapping tables → attributes on relevant dimension
"""

user_prompt = f"""Request: {request}
App Name: {app_name or 'Not specified'}

Data Model Metadata:
{model_metadata or '[No metadata provided - provide general guidance]'}

Please analyze the Qlik data model and propose the Kimball star schema design."""

print(f"✅ Prompts formatted")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call
# ══════════════════════════════════════════════════════════════════════

response = call_agent(
    agent_name="91_qlik_data_model",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=6144
)

print(response)

# COMMAND ----------

# DBTITLE 1,STEP 5 - Validate and Persist
# ══════════════════════════════════════════════════════════════════════
# STEP 5: Validate & Persist
# ══════════════════════════════════════════════════════════════════════

assert len(response) > 100, "Response too short"
assert any(kw in response.lower() for kw in ["fact", "dim", "star", "schema", "model", "association"]), \
    "Response missing data modeling content"

save_agent_output(
    agent_name="91_qlik_data_model",
    run_id=run_id,
    output_type="data_model_design",
    content=response,
    metadata={"app_name": app_name}
)

print(f"\n✅ Agent 91 complete — star schema design saved")
print(f"📋 Run ID: {run_id}")

# COMMAND ----------

