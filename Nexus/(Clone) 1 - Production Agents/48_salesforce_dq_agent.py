# Databricks notebook source
# DBTITLE 1,Salesforce DQ Agent
# MAGIC %md
# MAGIC # Agent 48 — Salesforce Data Quality Specialist (W1)
# MAGIC **Source:** Salesforce | **Domains:** deduplication, merge_rules, data_quality, completeness

# COMMAND ----------

# DBTITLE 1,Load specialist base
# MAGIC %run ./61_specialist_base

# COMMAND ----------

# DBTITLE 1,Salesforce DQ Specialist
class SalesforceDQSpecialist(SpecialistBase):
    def __init__(self):
        super().__init__("48_salesforce_dq_agent", "salesforce",
                         ["mde_dev.stg_salesforce"], ["data_quality", "deduplication", "merge_rules"])
    
    def get_known_issues(self):
        base = super().get_known_issues()
        base['known_quirks'] = [
            "Account duplicates: Fuzzy match on Name + BillingAddress + Phone (exact match misses subsidiaries)",
            "Contact duplicates: Email is best match key but ~15% of contacts have no email",
            "Opportunity.Amount: Can be NULL for early-stage opportunities (not a DQ issue)",
            "Lead.ConvertedDate: Non-null means converted; don't count in active lead metrics",
            "RecordType-specific required fields: Custom validations differ per RecordType",
            "Merge survivors: MasterRecordId populated on merged (dead) records; always filter IsDeleted=false",
        ]
        return base
    
    def recommend_dq_rules(self, table_name=None, context=None):
        if table_name and 'account' in table_name.lower():
            return {"rules": [
                "NOT_NULL | Name | Completeness | 100% | CRITICAL",
                "NOT_NULL | OwnerId | Completeness | 100% | CRITICAL",
                "VALID_EMAIL | PersonEmail (if PersonAccount) | Format | 99% | MEDIUM",
                "UNIQUENESS | Name + BillingCity + BillingState | Dedup candidate | flag | HIGH",
                "REFERENTIAL | OwnerId -> User.Id | Integrity | 100% | HIGH",
                "NOT_NULL | Industry | Completeness | 90% | MEDIUM",
                "FRESHNESS | SystemModstamp | Timeliness | < 24h | MEDIUM",
            ]}
        return super().recommend_dq_rules(table_name, context)

sf_dq_specialist = SalesforceDQSpecialist()
try:
    consultation_payload = json.loads(dbutils.widgets.get("consultation_payload"))
    print(json.dumps(sf_dq_specialist.handle_consultation(consultation_payload), indent=2, default=str))
except:
    print("\u2705 48_salesforce_dq_agent ready")