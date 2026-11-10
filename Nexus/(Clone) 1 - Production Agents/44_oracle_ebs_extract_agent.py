# Databricks notebook source
# DBTITLE 1,Oracle EBS Extract Agent
# MAGIC %md
# MAGIC # Agent 44 — Oracle EBS Extract Specialist (W1)
# MAGIC
# MAGIC **Purpose:** Monitors Oracle EBS extract pipelines. Responds to CONSULTATION_ROUTED requests for EBS domain expertise: extract strategies, known issues, pipeline health.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Source System | Oracle EBS (stg_oracle_ebs, 1,263 tables) |
# MAGIC | Domains | AP, AR, GL, PO, INV, OM, BOM, WIP, extract, ingestion |
# MAGIC | Capabilities | get_pipeline_health, get_known_issues, recommend_extract_strategy |

# COMMAND ----------

# DBTITLE 1,Load specialist base
# MAGIC %run ./61_specialist_base

# COMMAND ----------

# DBTITLE 1,Oracle EBS Extract Specialist Implementation
# ======================================================================
# ORACLE EBS EXTRACT SPECIALIST
# Inherits from SpecialistBase, overrides with EBS domain knowledge
# ======================================================================

class OracleEBSExtractSpecialist(SpecialistBase):
    """Specialist for Oracle EBS extract/ingestion patterns."""
    
    def __init__(self):
        super().__init__(
            agent_name="44_oracle_ebs_extract_agent",
            source_system="oracle_ebs",
            schemas=["mde_dev.stg_oracle_ebs"],
            domains=["AP", "AR", "GL", "PO", "INV", "OM", "BOM", "WIP", "extract", "ingestion"]
        )
    
    def get_known_issues(self):
        """EBS-specific known issues."""
        base = super().get_known_issues()
        base['known_quirks'] = [
            "GL_JE_HEADERS/LINES: JE_SOURCE and JE_CATEGORY have inconsistent casing across instances",
            "AP_INVOICES_ALL: AMOUNT_APPLICABLE_TO_DISCOUNT can be NULL for prepayments",
            "PO_HEADERS_ALL: CLOSED_DATE populated even when STATUS is APPROVED (not closed)",
            "MTL_SYSTEM_ITEMS_B: INVENTORY_ITEM_STATUS_CODE is org-specific, not global",
            "RA_CUSTOMER_TRX_ALL: TRX_NUMBER format varies by operating unit (numeric vs alphanumeric)",
            "FND_CONCURRENT_REQUESTS: Phase/Status codes are numeric internally but displayed as text in UI",
            "Multi-org: Always filter by ORG_ID — cross-org queries without filter return duplicates",
            "Date columns: WHO columns (CREATED_BY, LAST_UPDATE_DATE) use DB timezone, not business timezone",
        ]
        return base
    
    def recommend_extract_strategy(self, table_name=None, context=None):
        """Recommend extraction pattern for EBS tables."""
        prompt = f"""You are the Oracle EBS extract specialist for Hologic.
        
Recommend an extraction strategy for: {table_name or 'general EBS tables'}
Context: {context or 'Standard incremental extraction'}

Consider:
1. LAST_UPDATE_DATE for CDC (most EBS tables have WHO columns)
2. Full-load vs incremental (GL journals = incremental, setup tables = full)
3. Volume considerations (AP_INVOICES_ALL can be 50M+ rows)
4. Multi-org partitioning (filter by ORG_ID for parallel extraction)
5. Audit column pattern: CREATION_DATE, CREATED_BY, LAST_UPDATE_DATE, LAST_UPDATED_BY

Respond with: Strategy name, Column for CDC, Estimated volume, Frequency, Notes."""
        return {"recommendation": call_llm(prompt, max_tokens=500)}

# Instantiate
ebs_extract_specialist = OracleEBSExtractSpecialist()

# Handle inbound consultations (if triggered by event mesh)
try:
    consultation_payload = json.loads(dbutils.widgets.get("consultation_payload"))
    result = ebs_extract_specialist.handle_consultation(consultation_payload)
    print(json.dumps(result, indent=2, default=str))
except:
    print("\u2705 44_oracle_ebs_extract_agent ready (no inbound consultation)")
    health = ebs_extract_specialist.get_pipeline_health()
    print(f"   Pipeline health (7d): {health['status']} | Success: {health['success_rate']}% | Runs: {health['total_runs']}")