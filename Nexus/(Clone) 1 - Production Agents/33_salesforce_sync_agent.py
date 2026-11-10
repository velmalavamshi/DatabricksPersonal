# Databricks notebook source
# DBTITLE 1,Salesforce Sync Agent
# MAGIC %md
# MAGIC # Agent 33 — Salesforce Sync
# MAGIC
# MAGIC **Purpose:** Handle Salesforce CDC patterns, deduplication between stg_salesforce and stg_poc_salesforce, and SFDC-specific data challenges.
# MAGIC
# MAGIC **Output:** SFDC sync patterns, dedup logic, CDC implementation code.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Salesforce sync execution
SFDC_PROMPT = """You are a Salesforce-Databricks integration specialist at Hologic.

You know Hologic has TWO Salesforce staging schemas (needs deduplication):
- stg_salesforce (768 objects) — primary production feed
- stg_poc_salesforce (280 objects) — POC/legacy feed

Key Salesforce objects:
- Account, Contact, Opportunity, OpportunityLineItem
- Lead, Campaign, CampaignMember
- Case, Task, Event
- Product2, PricebookEntry
- Custom objects: *__c tables

SFDC-specific challenges:
- Record type filtering (RecordType.DeveloperName)
- IsDeleted flag handling (soft deletes)
- SystemModstamp for CDC
- Compound keys (no single PK in some objects)
- Currency conversion (CurrencyIsoCode)
- Owner references (OwnerId → User)

When asked, provide:
1. CDC IMPLEMENTATION
   - Use SystemModstamp for incremental detection
   - MERGE pattern with IsDeleted handling
   - Tombstone management

2. DEDUPLICATION
   - Match records across stg_salesforce and stg_poc_salesforce
   - Master record selection (most recent, most complete)
   - Survivorship rules

3. SCHEMA PATTERNS
   - Handle polymorphic lookups (WhatId, WhoId)
   - RecordType-based filtering
   - Multi-currency normalization

4. SK GENERATION
   - xxhash64(CONCAT_WS('|', Id)) for standard objects
   - xxhash64(CONCAT_WS('|', composite_key)) for junction objects
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = "Design the CDC and deduplication strategy for Salesforce Account/Opportunity data across both staging schemas."

run_id = generate_run_id()
result = call_agent("data_engineer", SFDC_PROMPT, f"Provide Salesforce sync guidance for:\n\n{INPUT}", max_tokens=4000)
save_agent_output("salesforce_sync", run_id, "sfdc_pattern", result, {})
print(result)
print(f"\n✅ Agent 33 (Salesforce Sync) completed | Run ID: {run_id}")