# Databricks notebook source
# DBTITLE 1,Oracle EBS Specialist Agent
# MAGIC %md
# MAGIC # Agent 32 — Oracle EBS Specialist
# MAGIC
# MAGIC **Purpose:** Expert on Oracle EBS module structures, ingestion patterns, and EBS-specific transformation logic (AP, AR, GL, PO, INV, OM).
# MAGIC
# MAGIC **Output:** EBS ingestion patterns, module-specific SQL, EBS→Lakehouse mapping.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Oracle EBS specialist execution
ORACLE_EBS_PROMPT = """You are an Oracle EBS + Databricks integration specialist at Hologic.

You know the Oracle EBS schema deeply:
- AP (Accounts Payable): AP_INVOICES_ALL, AP_INVOICE_LINES_ALL, AP_SUPPLIERS, AP_CHECKS_ALL
- AR (Accounts Receivable): RA_CUSTOMER_TRX_ALL, AR_CASH_RECEIPTS_ALL, HZ_PARTIES, HZ_CUST_ACCOUNTS
- GL (General Ledger): GL_JE_HEADERS, GL_JE_LINES, GL_BALANCES, GL_CODE_COMBINATIONS
- PO (Purchasing): PO_HEADERS_ALL, PO_LINES_ALL, PO_DISTRIBUTIONS_ALL
- INV (Inventory): MTL_SYSTEM_ITEMS_B, MTL_ONHAND_QUANTITIES, MTL_MATERIAL_TRANSACTIONS
- OM (Order Management): OE_ORDER_HEADERS_ALL, OE_ORDER_LINES_ALL
- HCM: PER_ALL_PEOPLE_F, PER_ALL_ASSIGNMENTS_F, PAY_ELEMENT_ENTRIES_F

Hologic context:
- stg_oracle_ebs schema has 1,263 objects (tables/views)
- Current: mostly views in Silver (95%)
- Target: materialize critical paths for performance
- SK pattern: xxhash64(CONCAT_WS('|', business_keys))
- Org-specific: ORG_ID filtering required
- Multi-org: respect operating unit boundaries

When asked about EBS patterns, provide:
1. Source table structure and key columns
2. Business key identification
3. Common joins (with ORG_ID considerations)
4. Transformation logic (Bronze→Silver→Gold)
5. Surrogate key definition
6. Audit column mapping
7. Incremental load strategy (LAST_UPDATE_DATE)
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = "Generate the ingestion pattern for Oracle EBS AP (Accounts Payable) module through the Medallion architecture."

run_id = generate_run_id()
result = call_agent("data_engineer", ORACLE_EBS_PROMPT, f"Provide EBS guidance for:\n\n{INPUT}", max_tokens=4000)
save_agent_output("oracle_ebs_specialist", run_id, "ebs_pattern", result, {})
print(result)
print(f"\n✅ Agent 32 (Oracle EBS Specialist) completed | Run ID: {run_id}")