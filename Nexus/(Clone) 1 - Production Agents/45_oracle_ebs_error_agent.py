# Databricks notebook source
# DBTITLE 1,Oracle EBS Error Agent
# MAGIC %md
# MAGIC # Agent 45 — Oracle EBS Error Specialist (W1)
# MAGIC **Source:** Oracle EBS | **Domains:** error_handling, retry, dead_letter, reconciliation

# COMMAND ----------

# DBTITLE 1,Load specialist base
# MAGIC %run ./61_specialist_base

# COMMAND ----------

# DBTITLE 1,Oracle EBS Error Specialist
class OracleEBSErrorSpecialist(SpecialistBase):
    def __init__(self):
        super().__init__("45_oracle_ebs_error_agent", "oracle_ebs",
                         ["mde_dev.stg_oracle_ebs"], ["error_handling", "retry", "dead_letter"])
    
    def get_known_issues(self):
        base = super().get_known_issues()
        base['known_quirks'] = [
            "ORA-01555 (snapshot too old): Common on large GL extracts during period close",
            "ORA-04031 (shared pool): EBS concurrent manager can exhaust SGA during batch jobs",
            "FND_CONCURRENT_REQUESTS timeout: Default 6h for large AP/AR sweeps",
            "DBLINK failures: Intermittent on cross-instance APPS_RO link during maintenance windows",
            "Character set issues: AL32UTF8 vs WE8MSWIN1252 causes mojibake in supplier names",
            "Retry strategy: Exponential backoff (30s, 60s, 120s, 300s) for transient ORA errors",
        ]
        return base
    
    def classify_error(self, error_message):
        """Classify an EBS error and recommend action."""
        prompt = f"""Classify this Oracle EBS error and recommend an action:

Error: {error_message}

Categories: TRANSIENT (retry), DATA_ISSUE (fix source), CONFIG (fix connection), CAPACITY (scale up), UNKNOWN
Respond: Category | Root cause (1 line) | Recommended action | Retry? (Y/N)"""
        return {"classification": call_llm(prompt, max_tokens=200)}

ebs_error_specialist = OracleEBSErrorSpecialist()
try:
    consultation_payload = json.loads(dbutils.widgets.get("consultation_payload"))
    print(json.dumps(ebs_error_specialist.handle_consultation(consultation_payload), indent=2, default=str))
except:
    print("\u2705 45_oracle_ebs_error_agent ready")