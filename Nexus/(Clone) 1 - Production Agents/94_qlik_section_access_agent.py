# Databricks notebook source
# DBTITLE 1,Agent 94: Qlik Section Access Agent
# MAGIC %md
# MAGIC # Agent 94: Qlik Section Access Agent
# MAGIC
# MAGIC **Purpose:** Converts Qlik Section Access (row-level security model) to Unity Catalog row filters, column masks, and ABAC policies.
# MAGIC
# MAGIC **Pipeline Position:** Specialist Layer → called by Agent 88 (orchestrator)
# MAGIC
# MAGIC **Inputs:**
# MAGIC - Section Access script blocks from QVW/QVF apps
# MAGIC - ACCESS, USERID, NTNAME, GROUP fields
# MAGIC - Reduction fields (data scope per user/group)
# MAGIC
# MAGIC **Outputs:**
# MAGIC - Unity Catalog row filter functions (SQL UDFs)
# MAGIC - Column mask definitions
# MAGIC - ABAC policy YAML/SQL
# MAGIC - User/group mapping table (Section Access → Entra ID groups)
# MAGIC - Migration validation queries
# MAGIC
# MAGIC **Qlik Section Access Concepts:**
# MAGIC - ADMIN vs USER access levels
# MAGIC - USERID / NTNAME / NTDOMAINSID / GROUP (identity fields)
# MAGIC - Reduction fields: any data field used to restrict rows per user
# MAGIC - OMIT: fields hidden entirely from certain users (column-level)
# MAGIC - Initial Data Reduction: server-side filter before data reaches client
# MAGIC - Section Application: the main data section (resumes after Section Access)

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "Section Access Conversion Request")
dbutils.widgets.multiline("section_access_script", "", "Section Access Script (paste here)")
dbutils.widgets.text("app_name", "", "Source Qlik App Name")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
section_access_script = dbutils.widgets.get("section_access_script")
app_name = dbutils.widgets.get("app_name")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context — Section Access → Unity Catalog Security
# ══════════════════════════════════════════════════════════════════════

# Section Access field → UC security mechanism
SECURITY_MAPPING = {
    "ACCESS (ADMIN/USER)": "UC GRANT/REVOKE (table-level permissions)",
    "USERID / NTNAME": "current_user() function in row filter",
    "NTDOMAINSID": "Entra ID group membership via is_account_group_member()",
    "GROUP": "UC group → is_account_group_member('group_name')",
    "Reduction fields (e.g., Region, Country)": "Row filter function with WHERE clause",
    "OMIT (hide columns)": "Column mask function (return NULL or '***')",
    "* (wildcard in field values)": "No filter applied (full access) → no row filter for that user",
}

# Pattern: Section Access → Row Filter UDF
ROW_FILTER_TEMPLATE = """
-- Row filter function for table: {table_name}
CREATE OR REPLACE FUNCTION mde_dev.gold.row_filter_{table_name}()
RETURNS STRING
RETURN
  CASE
    WHEN is_account_group_member('admin_group') THEN 'TRUE'
    WHEN is_account_group_member('region_us') THEN 'Region = "US"'
    WHEN is_account_group_member('region_eu') THEN 'Region = "EU"'
    ELSE 'FALSE'  -- deny all by default
  END;

-- Apply row filter
ALTER TABLE mde_dev.gold.{table_name}
  SET ROW FILTER mde_dev.gold.row_filter_{table_name} ON ();
"""

# Pattern: OMIT → Column Mask
COLUMN_MASK_TEMPLATE = """
-- Column mask for sensitive field: {column_name}
CREATE OR REPLACE FUNCTION mde_dev.gold.mask_{column_name}({column_name} STRING)
RETURNS STRING
RETURN
  CASE
    WHEN is_account_group_member('admin_group') THEN {column_name}
    ELSE '***REDACTED***'
  END;

-- Apply column mask
ALTER TABLE mde_dev.gold.{table_name}
  ALTER COLUMN {column_name} SET MASK mde_dev.gold.mask_{column_name};
"""

print(f"✅ Section Access context loaded")
print(f"   {len(SECURITY_MAPPING)} field-to-UC mappings")
print(f"   Row filter + column mask templates ready")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting
# ══════════════════════════════════════════════════════════════════════

import json

system_prompt = f"""You are the Qlik Section Access Agent (Agent 94) for Hologic's NEXUS platform.

You convert Qlik Section Access row-level security to Unity Catalog equivalents.

Section Access → UC Mapping:
{json.dumps(SECURITY_MAPPING, indent=2)}

Row Filter Template:
{ROW_FILTER_TEMPLATE}

Column Mask Template:
{COLUMN_MASK_TEMPLATE}

Conversion Process:
1. PARSE Section Access script — identify ACCESS levels, identity fields, reduction fields, OMIT
2. MAP Qlik users/groups to Entra ID / UC groups
3. GENERATE row filter UDFs (one per table + security dimension)
4. GENERATE column masks (for OMIT fields)
5. CREATE user/group mapping table (Section Access values → UC groups)
6. VALIDATE — provide test queries showing security applied correctly

Key Differences:
- Qlik: security is per-APP (embedded in QVW/QVF). UC: security is per-TABLE (shared across all consumers)
- Qlik: wildcard * = full access. UC: no row filter = full access
- Qlik: NTNAME is Windows domain login. UC: current_user() returns UPN (email)
- Qlik: Section Access loads from inline table or external file. UC: defined as SQL functions
- Qlik: reduction happens at data-model level. UC: row filters execute at query time

Hologic Standards:
- All security functions in mde_dev.gold schema
- Use is_account_group_member() for group-based security
- Default deny: ELSE 'FALSE' in row filters
- Document the mapping in a migration_security_map table
"""

user_prompt = f"""Request: {request}
Source App: {app_name or 'Not specified'}

Section Access Script:
```qlik
{section_access_script or '[No script provided - provide general guidance]'}
```

Please convert this Section Access definition to Unity Catalog security (row filters + column masks)."""

print(f"✅ Prompts formatted")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call
# ══════════════════════════════════════════════════════════════════════

response = call_agent(
    agent_name="94_qlik_section_access",
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
assert any(kw in response.lower() for kw in ["row filter", "column mask", "grant", "security", "access"]), \
    "Response missing security content"

save_agent_output(
    agent_name="94_qlik_section_access",
    run_id=run_id,
    output_type="section_access_conversion",
    content=response,
    metadata={"app_name": app_name}
)

print(f"\n✅ Agent 94 complete — Section Access converted to UC security")
print(f"📋 Run ID: {run_id}")

# COMMAND ----------

