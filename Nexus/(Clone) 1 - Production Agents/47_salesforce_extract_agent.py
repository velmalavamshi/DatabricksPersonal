# Databricks notebook source
# DBTITLE 1,Salesforce Extract Agent
# MAGIC %md
# MAGIC # Agent 47 — Salesforce Extract Specialist (W1)
# MAGIC **Source:** Salesforce (stg_salesforce, 488 tables) | **Domains:** CDC, Bulk API, incremental, dedup

# COMMAND ----------

# DBTITLE 1,Load specialist base
# MAGIC %run ./61_specialist_base

# COMMAND ----------

# DBTITLE 1,Salesforce Extract Specialist
class SalesforceExtractSpecialist(SpecialistBase):
    def __init__(self):
        super().__init__("47_salesforce_extract_agent", "salesforce",
                         ["mde_dev.stg_salesforce"], ["extract", "CDC", "bulk_api", "incremental"])
    
    def get_known_issues(self):
        base = super().get_known_issues()
        base['known_quirks'] = [
            "Bulk API 2.0: 100M record/batch limit; large objects (Opportunity, Task) need date-range splits",
            "SystemModstamp vs LastModifiedDate: Use SystemModstamp for CDC (includes system-level changes)",
            "Soft deletes: IsDeleted=TRUE records only available via queryAll() in Bulk API",
            "Compound fields: Address/Geolocation return as nested objects; flatten in landing layer",
            "Formula fields: Cannot filter on formula fields in SOQL WHERE clause",
            "API limits: 100K API calls/24h (Enterprise); monitor via /services/data/vXX.0/limits",
            "RecordType: Always include RecordTypeId in extracts — business logic depends on it",
            "PersonAccount: Merges Account + Contact into single object; special handling required",
        ]
        return base
    
    def recommend_extract_strategy(self, table_name=None, context=None):
        prompt = f"""You are the Salesforce extract specialist for Hologic.
Recommend extraction for: {table_name or 'standard SFDC objects'}
Context: {context or 'CDC incremental via Bulk API 2.0'}

Consider: SystemModstamp for CDC, Bulk API 2.0 batching, soft deletes (queryAll), API limits.
Respond: Strategy | CDC column | Batch size | Frequency | Known gotchas."""
        return {"recommendation": call_llm(prompt, max_tokens=400)}

sf_extract_specialist = SalesforceExtractSpecialist()
try:
    consultation_payload = json.loads(dbutils.widgets.get("consultation_payload"))
    print(json.dumps(sf_extract_specialist.handle_consultation(consultation_payload), indent=2, default=str))
except:
    print("\u2705 47_salesforce_extract_agent ready")
    health = sf_extract_specialist.get_pipeline_health()
    print(f"   Pipeline health (7d): {health['status']} | Success: {health['success_rate']}% | Runs: {health['total_runs']}")