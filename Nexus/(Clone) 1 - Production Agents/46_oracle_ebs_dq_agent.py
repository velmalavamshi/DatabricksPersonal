# Databricks notebook source
# DBTITLE 1,Oracle EBS DQ Agent
# MAGIC %md
# MAGIC # Agent 46 — Oracle EBS Data Quality Specialist (W1)
# MAGIC **Source:** Oracle EBS | **Domains:** completeness, accuracy, timeliness, referential integrity

# COMMAND ----------

# DBTITLE 1,Load specialist base
# MAGIC %run ./61_specialist_base

# COMMAND ----------

# DBTITLE 1,Oracle EBS DQ Specialist
class OracleEBSDQSpecialist(SpecialistBase):
    def __init__(self):
        super().__init__("46_oracle_ebs_dq_agent", "oracle_ebs",
                         ["mde_dev.stg_oracle_ebs"], ["data_quality", "completeness", "accuracy", "timeliness"])
    
    def get_known_issues(self):
        base = super().get_known_issues()
        base['known_quirks'] = [
            "AP_INVOICES_ALL.INVOICE_AMOUNT vs distribution sum: Rounding discrepancy on multi-currency",
            "GL_BALANCES: Period-end balances sometimes lag 1 day after close",
            "AR_PAYMENT_SCHEDULES: DUE_DATE can be NULL on prepayments (not a DQ failure)",
            "PO_LINE_LOCATIONS: QUANTITY_RECEIVED > QUANTITY_ORDERED is valid (over-receipt tolerance)",
            "HR_ALL_ORGANIZATION_UNITS: Inactive orgs remain but EFFECTIVE_END_DATE is populated",
            "WHO columns: LAST_UPDATE_DATE must always >= CREATION_DATE (violators indicate data corruption)",
        ]
        return base
    
    def recommend_dq_rules(self, table_name=None, context=None):
        """EBS-specific DQ rules."""
        if table_name and 'ap_invoice' in table_name.lower():
            return {"rules": [
                "NOT_NULL | INVOICE_NUM | Completeness | 100% | CRITICAL",
                "NOT_NULL | VENDOR_ID | Completeness | 100% | CRITICAL",
                "RANGE_CHECK | INVOICE_AMOUNT | Accuracy | -10M to 10M | HIGH",
                "REFERENTIAL | VENDOR_ID -> AP_SUPPLIERS.VENDOR_ID | Integrity | 100% | HIGH",
                "TIMELINESS | LAST_UPDATE_DATE | Freshness | < 48h | MEDIUM",
                "UNIQUENESS | INVOICE_NUM + ORG_ID | Uniqueness | 100% | CRITICAL",
            ]}
        return super().recommend_dq_rules(table_name, context)

ebs_dq_specialist = OracleEBSDQSpecialist()
try:
    consultation_payload = json.loads(dbutils.widgets.get("consultation_payload"))
    print(json.dumps(ebs_dq_specialist.handle_consultation(consultation_payload), indent=2, default=str))
except:
    print("\u2705 46_oracle_ebs_dq_agent ready")