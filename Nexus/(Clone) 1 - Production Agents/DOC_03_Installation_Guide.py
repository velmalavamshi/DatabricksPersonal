# Databricks notebook source
# DBTITLE 1,Installation Guide - Cover
# MAGIC %md
# MAGIC # Hologic Multi-Agent AI Platform — Installation & Implementation Guide
# MAGIC
# MAGIC **Version:** 1.0  
# MAGIC **Last Updated:** June 2026  
# MAGIC **Audience:** Platform administrators deploying the agent system  
# MAGIC **Platform:** Databricks (Azure)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Document Purpose
# MAGIC
# MAGIC This guide covers end-to-end deployment of the Multi-Agent Platform:
# MAGIC - Prerequisites and permissions
# MAGIC - Step-by-step installation
# MAGIC - Configuration and customization
# MAGIC - Workflow setup (scheduling)
# MAGIC - Validation and smoke testing
# MAGIC - Production hardening
# MAGIC - Maintenance procedures

# COMMAND ----------

# DBTITLE 1,Prerequisites
# MAGIC %md
# MAGIC ## 1. Prerequisites
# MAGIC
# MAGIC ### Required Access
# MAGIC
# MAGIC | Requirement | Details |
# MAGIC | --- | --- |
# MAGIC | Databricks Workspace | AI Builder (4337650355687191) or any workspace with Unity Catalog |
# MAGIC | Catalog Access | `mde_dev` catalog — CREATE TABLE privilege on `test_schema` |
# MAGIC | Foundation Model APIs | Access to serving endpoints (e.g., `databricks-claude-sonnet-4-6`) |
# MAGIC | System Tables | Read access to `system.billing.usage`, `system.lakeflow.*`, `system.information_schema.*` |
# MAGIC | Compute | Serverless or Jobs Compute cluster |
# MAGIC
# MAGIC ### Verify Permissions
# MAGIC
# MAGIC ```sql
# MAGIC -- Check catalog access
# MAGIC SELECT current_catalog(), current_schema();
# MAGIC
# MAGIC -- Check system table access
# MAGIC SELECT COUNT(*) FROM system.billing.usage WHERE usage_date >= CURRENT_DATE() - 1;
# MAGIC
# MAGIC -- Check Foundation Model API access
# MAGIC -- (Run in Python)
# MAGIC from openai import OpenAI
# MAGIC client = OpenAI(api_key=token, base_url=f"https://{workspace_url}/serving-endpoints")
# MAGIC response = client.chat.completions.create(
# MAGIC     model="databricks-claude-sonnet-4-6",
# MAGIC     messages=[{"role": "user", "content": "Say hello"}],
# MAGIC     max_tokens=10
# MAGIC )
# MAGIC print(response.choices[0].message.content)  # Should print greeting
# MAGIC ```
# MAGIC
# MAGIC ### Software Requirements
# MAGIC
# MAGIC | Package | Version | Purpose |
# MAGIC | --- | --- | --- |
# MAGIC | Python | 3.11+ | Runtime (provided by Databricks) |
# MAGIC | openai | Latest | OpenAI-compatible LLM client |
# MAGIC | pyspark | Included | Data processing |
# MAGIC | Delta Lake | Included | State management |

# COMMAND ----------

# DBTITLE 1,Installation Steps
# MAGIC %md
# MAGIC ## 2. Installation Steps
# MAGIC
# MAGIC ### Step 1: Deploy Notebooks
# MAGIC
# MAGIC All agent notebooks are located at:
# MAGIC ```
# MAGIC /Workspace/Users/sameet.patel@hologic.com/1 - AI Project/1 - AI Multi Agents/1 - Production Agents/
# MAGIC ```
# MAGIC
# MAGIC To deploy to another workspace or user:
# MAGIC 1. Export the folder as a DBC archive or use Repos
# MAGIC 2. Import into the target workspace
# MAGIC 3. Update `00_agent_config` with workspace-specific values
# MAGIC
# MAGIC ### Step 2: Run Configuration Notebook
# MAGIC
# MAGIC Execute `00_agent_config` first. This:
# MAGIC - Installs the `openai` package
# MAGIC - Creates Delta tables (`agent_call_log`, `agent_outputs`)
# MAGIC - Validates LLM connectivity
# MAGIC - Exports shared utility functions
# MAGIC
# MAGIC ```
# MAGIC Expected output:
# MAGIC ✅ Config loaded | Catalog: mde_dev.test_schema | LLM: databricks-claude-sonnet-4-6
# MAGIC ✅ LLM client configured | Using OpenAI-compatible Databricks endpoint
# MAGIC ✅ Agent state management configured | Tables: agent_call_log, agent_outputs
# MAGIC ✅ Delta tables initialized in mde_dev.test_schema
# MAGIC ✅ Utilities loaded | generate_run_id(), get_workspace_name(), format_agent_report()
# MAGIC ```
# MAGIC
# MAGIC ### Step 3: Validate with Agent 01
# MAGIC
# MAGIC Run `01_job_failure_triage_agent` as a smoke test:
# MAGIC 1. Open the notebook
# MAGIC 2. Run All Cells
# MAGIC 3. Verify:
# MAGIC    - Cell 3 shows failing jobs from system tables
# MAGIC    - Cell 5 classifies failures via LLM
# MAGIC    - Cell 6 saves results to `agent_job_triage_results`
# MAGIC    - Cell 7 validation passes
# MAGIC
# MAGIC ### Step 4: Configure Remaining Agents
# MAGIC
# MAGIC Each agent works independently. Run any agent to verify it:
# MAGIC - Agent 03 (View Dependency) — good test for recursive SQL
# MAGIC - Agent 05 (Cost Anomaly) — good test for billing system tables
# MAGIC - Agent 02 (Data Engineer) — good test for LLM code generation

# COMMAND ----------

# DBTITLE 1,Workflow Setup
# MAGIC %md
# MAGIC ## 3. Workflow Setup (Scheduling)
# MAGIC
# MAGIC ### Create the Daily Monitoring Workflow
# MAGIC
# MAGIC Create a multi-task Workflow with these tasks:
# MAGIC
# MAGIC ```
# MAGIC Job Name: Multi-Agent Platform - Daily Monitoring
# MAGIC Schedule: 0 0 7 * * ? * (Daily at 7 AM)
# MAGIC Cluster: Jobs Compute (auto-terminating)
# MAGIC
# MAGIC Tasks:
# MAGIC ┌─────────────────────────────────────────────────────────────┐
# MAGIC │ Task 1: 01_job_failure_triage_agent                         │
# MAGIC │ Task 2: 04_source_drift_detector_agent (depends on: none)   │
# MAGIC │ Task 3: 05_cost_anomaly_agent (depends on: none)            │
# MAGIC │ Task 4: 10_medallion_validation_agent (depends on: none)    │
# MAGIC └─────────────────────────────────────────────────────────────┘
# MAGIC
# MAGIC All tasks can run in PARALLEL (no dependencies between monitoring agents).
# MAGIC ```
# MAGIC
# MAGIC ### Create the Feature Delivery Workflow
# MAGIC
# MAGIC ```
# MAGIC Job Name: Multi-Agent Platform - Feature Delivery
# MAGIC Schedule: On-demand (triggered manually or via API)
# MAGIC Cluster: Jobs Compute (auto-terminating)
# MAGIC Parameters: requirement (STRING), source_tables (STRING)
# MAGIC
# MAGIC Tasks (SEQUENTIAL):
# MAGIC ┌─────────────────────────────────────────────────────────────┐
# MAGIC │ 1. 11_business_analyst_agent                                 │
# MAGIC │ 2. 12_scope_agent (depends on: 1)                           │
# MAGIC │ 3. 13_project_manager_agent (depends on: 2)                 │
# MAGIC │ 4. 06_solution_architect_agent (depends on: 2)              │
# MAGIC │ 5. 02_data_engineer_agent (depends on: 4)                   │
# MAGIC │ 6. 07_peer_review_agent (depends on: 5)                     │
# MAGIC │ 7. 08_unit_test_agent (depends on: 5)                       │
# MAGIC │ 8. 09_environment_promotion_agent (depends on: 6, 7)        │
# MAGIC └─────────────────────────────────────────────────────────────┘
# MAGIC ```
# MAGIC
# MAGIC ### Cluster Configuration
# MAGIC
# MAGIC | Setting | Value |
# MAGIC | --- | --- |
# MAGIC | Type | Jobs Compute (single-node) |
# MAGIC | Node | Standard_DS3_v2 (14 GB, 4 cores) |
# MAGIC | Runtime | 15.4 LTS or later |
# MAGIC | Auto-terminate | 10 minutes after completion |
# MAGIC | Libraries | `openai` (installed via `%pip` in config notebook) |
# MAGIC | Cost | ~$0.30/DBU × 0.5 DBU/hr × 0.5 hr = **$0.08/run** |

# COMMAND ----------

# DBTITLE 1,Configuration Reference
# MAGIC %md
# MAGIC ## 4. Configuration Reference
# MAGIC
# MAGIC ### Environment Variables (in `00_agent_config`)
# MAGIC
# MAGIC | Variable | Default | Description |
# MAGIC | --- | --- | --- |
# MAGIC | `CATALOG` | `mde_dev` | Unity Catalog catalog name |
# MAGIC | `SCHEMA` | `test_schema` | Schema for agent tables |
# MAGIC | `DEV_WORKSPACE_ID` | `6617965257274108` | DEV workspace identifier |
# MAGIC | `PRD_WORKSPACE_ID` | `685145432798888` | PRD workspace identifier |
# MAGIC | `UAT_WORKSPACE_ID` | `7982886777824011` | UAT workspace identifier |
# MAGIC | `AI_BUILDER_WORKSPACE_ID` | `4337650355687191` | AI Builder workspace |
# MAGIC | `LLM_CRITICAL` | `databricks-claude-sonnet-4-6` | Model for critical agents |
# MAGIC | `LLM_STANDARD` | `databricks-claude-sonnet-4-6` | Model for standard agents |
# MAGIC
# MAGIC ### Deploying to UAT/PRD
# MAGIC
# MAGIC To deploy to a different environment:
# MAGIC
# MAGIC 1. Copy the folder to the target workspace
# MAGIC 2. Update `00_agent_config`:
# MAGIC ```python
# MAGIC CATALOG = "mde_uat"  # or "mde_prd"
# MAGIC SCHEMA = "agent_schema"  # dedicated schema recommended for PRD
# MAGIC ```
# MAGIC 3. Verify Foundation Model API access in the target workspace
# MAGIC 4. Run `00_agent_config` to create tables
# MAGIC 5. Create the Workflows in the target workspace

# COMMAND ----------

# DBTITLE 1,Validation and Maintenance
# MAGIC %md
# MAGIC ## 5. Validation & Smoke Testing
# MAGIC
# MAGIC ### Post-Installation Checklist
# MAGIC
# MAGIC | # | Check | How to Verify | Expected |
# MAGIC | --- | --- | --- | --- |
# MAGIC | 1 | Config notebook runs | Run `00_agent_config` | All ✅ messages |
# MAGIC | 2 | Delta tables exist | `SHOW TABLES IN mde_dev.test_schema LIKE 'agent_*'` | 2+ tables |
# MAGIC | 3 | LLM responds | Run any agent | Non-empty output |
# MAGIC | 4 | System tables accessible | `SELECT COUNT(*) FROM system.billing.usage` | Non-zero |
# MAGIC | 5 | Logs written | `SELECT * FROM mde_dev.test_schema.agent_call_log LIMIT 5` | Has rows |
# MAGIC | 6 | Workflow runs | Trigger manually | All tasks succeed |
# MAGIC
# MAGIC ### Health Check Query
# MAGIC
# MAGIC ```sql
# MAGIC -- Run this daily to verify platform health
# MAGIC SELECT 
# MAGIC     agent_name,
# MAGIC     COUNT(*) as calls_24h,
# MAGIC     SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
# MAGIC     SUM(CASE WHEN status LIKE 'ERROR%' THEN 1 ELSE 0 END) as errors,
# MAGIC     ROUND(AVG(duration_sec), 1) as avg_duration_sec
# MAGIC FROM mde_dev.test_schema.agent_call_log
# MAGIC WHERE timestamp >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
# MAGIC GROUP BY 1
# MAGIC ORDER BY errors DESC;
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 6. Production Hardening
# MAGIC
# MAGIC ### Recommended for Production
# MAGIC
# MAGIC | Area | Recommendation |
# MAGIC | --- | --- |
# MAGIC | **Alerting** | Set up Databricks SQL Alert on `agent_call_log` where `status LIKE 'ERROR%'` |
# MAGIC | **Retention** | Add `OPTIMIZE` + `VACUUM` schedule for agent tables (retain 90 days) |
# MAGIC | **Access Control** | Grant SELECT on agent tables only to data engineering group |
# MAGIC | **Secrets** | If integrating Azure DevOps: use `dbutils.secrets.get(scope, key)` |
# MAGIC | **Monitoring** | Dashboard on `agent_call_log` for daily call volume, error rate, token spend |
# MAGIC | **Backup** | Agent tables are in Unity Catalog — covered by metastore backup |
# MAGIC
# MAGIC ### Table Maintenance
# MAGIC
# MAGIC ```sql
# MAGIC -- Run weekly
# MAGIC OPTIMIZE mde_dev.test_schema.agent_call_log;
# MAGIC OPTIMIZE mde_dev.test_schema.agent_outputs;
# MAGIC
# MAGIC -- Retain 90 days of history
# MAGIC DELETE FROM mde_dev.test_schema.agent_call_log WHERE timestamp < DATEADD(DAY, -90, CURRENT_DATE());
# MAGIC VACUUM mde_dev.test_schema.agent_call_log RETAIN 168 HOURS;
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 7. Folder Structure
# MAGIC
# MAGIC ```
# MAGIC 1 - Production Agents/
# MAGIC ├── 00_agent_config              ← Shared configuration (RUN FIRST)
# MAGIC ├── 01_job_failure_triage_agent   ← Proactive monitoring
# MAGIC ├── 02_data_engineer_agent        ← Code generation
# MAGIC ├── 03_view_dependency_agent      ← Performance analysis
# MAGIC ├── 04_source_drift_detector      ← Schema drift detection
# MAGIC ├── 05_cost_anomaly_agent         ← Cost monitoring
# MAGIC ├── 06_solution_architect_agent   ← Architecture generation
# MAGIC ├── 07_peer_review_agent          ← Code review
# MAGIC ├── 08_unit_test_agent            ← Test generation
# MAGIC ├── 09_environment_promotion      ← DEV→UAT→PRD validation
# MAGIC ├── 10_medallion_validation       ← Layer integrity
# MAGIC ├── 11–36_*                       ← Remaining agents
# MAGIC ├── DOC_01_User_Guide            ← This documentation
# MAGIC ├── DOC_02_Developer_Guide        ← Technical internals
# MAGIC └── DOC_03_Installation_Guide     ← Deployment steps
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 8. Support & Escalation
# MAGIC
# MAGIC | Issue | Contact | SLA |
# MAGIC | --- | --- | --- |
# MAGIC | Agent not producing output | Check `agent_call_log` for errors | Self-service |
# MAGIC | LLM endpoint down | Databricks Support ticket | 4 hours |
# MAGIC | Permission issues | Workspace admin | Same day |
# MAGIC | New agent request | Data Engineering team | Sprint planning |
# MAGIC | Cost spike from agents | Check `agent_call_log` token counts | Self-service |