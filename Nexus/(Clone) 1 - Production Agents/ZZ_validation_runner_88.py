# Databricks notebook source
# DBTITLE 1,Validation runner for Agent 88 (Procurement Analytics pilot)
# MAGIC %md
# MAGIC Temporary validation notebook — confirms Agent 88 pulls real Procurement Analytics
# MAGIC assessment data from `mde_dev.test_schema.qlik_*` instead of confabulating.
# MAGIC Safe to delete after the pilot is reviewed.

# COMMAND ----------

# MAGIC %run "./00_agent_config"

# COMMAND ----------

# MAGIC %run "./88_qlik_migration_orchestrator_agent" $request="Procurement Analytics" $mode="inventory" $qlik_app_path="Procurement Analytics" $run_id=""