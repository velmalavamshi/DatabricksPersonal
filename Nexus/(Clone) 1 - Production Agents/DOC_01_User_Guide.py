# Databricks notebook source
# DBTITLE 1,User Guide - Cover
# MAGIC %md
# MAGIC # Hologic Multi-Agent AI Platform — User Guide
# MAGIC
# MAGIC **Version:** 1.0  
# MAGIC **Last Updated:** June 2026  
# MAGIC **Author:** Data Engineering Team  
# MAGIC **Platform:** Databricks (Azure)  
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Document Purpose
# MAGIC
# MAGIC This guide explains how to use the Multi-Agent AI Platform to automate Databricks data engineering tasks. It covers:
# MAGIC - What each agent does
# MAGIC - How to trigger agents (manual and scheduled)
# MAGIC - How to read agent outputs
# MAGIC - How to customize agent behavior
# MAGIC - Troubleshooting common issues

# COMMAND ----------

# DBTITLE 1,Overview
# MAGIC %md
# MAGIC ## 1. Platform Overview
# MAGIC
# MAGIC ### What Is This Platform?
# MAGIC
# MAGIC The Multi-Agent AI Platform is a collection of **36 specialized AI agents** running natively in Databricks. Each agent automates a specific data engineering function — from triaging job failures to generating production code to validating architecture compliance.
# MAGIC
# MAGIC ### Key Benefits
# MAGIC
# MAGIC | Benefit | Description |
# MAGIC | --- | --- |
# MAGIC | Zero external infrastructure | Runs entirely within Databricks — no Docker, K8s, or external databases |
# MAGIC | Pay-per-use | ~$0.63/feature processed (no idle costs) |
# MAGIC | Full audit trail | Every LLM call logged to `mde_dev.test_schema.agent_call_log` |
# MAGIC | Enterprise governance | All outputs stored in Unity Catalog Delta tables |
# MAGIC
# MAGIC ### Architecture at a Glance
# MAGIC
# MAGIC ```
# MAGIC ┌─────────────────────────────────────────────────────────────┐
# MAGIC │                    DATABRICKS WORKSPACE                       │
# MAGIC ├─────────────────────────────────────────────────────────────┤
# MAGIC │  ┌──────────┐    ┌──────────────┐    ┌─────────────────┐   │
# MAGIC │  │ Workflow  │───▶│ Agent        │───▶│ Delta Tables    │   │
# MAGIC │  │ Trigger   │    │ Notebooks    │    │ (agent_outputs) │   │
# MAGIC │  └──────────┘    └──────┬───────┘    └─────────────────┘   │
# MAGIC │                          │                                   │
# MAGIC │                   ┌──────▼───────┐                          │
# MAGIC │                   │ AI Gateway   │                          │
# MAGIC │                   │ (Claude/GPT) │                          │
# MAGIC │                   └──────────────┘                          │
# MAGIC └─────────────────────────────────────────────────────────────┘
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Agent Catalog
# MAGIC %md
# MAGIC ## 2. Agent Catalog
# MAGIC
# MAGIC ### Proactive Monitoring Agents (Run on Schedule)
# MAGIC
# MAGIC These agents run automatically and alert on issues:
# MAGIC
# MAGIC | # | Agent | What It Does | Schedule |
# MAGIC | --- | --- | --- | --- |
# MAGIC | 01 | Job Failure Triage | Classifies job failures, recommends fixes | Daily |
# MAGIC | 03 | View Dependency | Maps view chains, finds performance bottlenecks | Weekly |
# MAGIC | 04 | Source Drift Detector | Detects schema changes before they break pipelines | Daily |
# MAGIC | 05 | Cost Anomaly | Finds billing spikes and idle resources | Daily |
# MAGIC | 10 | Medallion Validation | Validates data integrity across layers | Weekly |
# MAGIC | 21 | Observability | Monitors job latency, SLA breaches, data freshness | Hourly |
# MAGIC | 30 | Monitoring | Dashboards, alerting rules, SLA tracking | Daily |
# MAGIC
# MAGIC ### Feature Delivery Agents (Triggered per Feature Request)
# MAGIC
# MAGIC These agents form a pipeline for delivering new features:
# MAGIC
# MAGIC | # | Agent | What It Does | Input From |
# MAGIC | --- | --- | --- | --- |
# MAGIC | 11 | Business Analyst | Produces BRD + user stories | Raw requirement |
# MAGIC | 12 | Scope | Defines boundaries, risks, assumptions | Agent 11 |
# MAGIC | 13 | Project Manager | Sprint plan, roadmap, dependencies | Agent 12 |
# MAGIC | 14 | Azure DevOps | Creates Epics/Features/Stories/Tasks | Agent 13 |
# MAGIC | **37** | **Data Modeler** | **Logical/physical model, reuse analysis, DDL** | **Agent 12** |
# MAGIC | 15 | Lakehouse Architect | Medallion design, domain model | Agent 37 |
# MAGIC | 06 | Solution Architect | HLD + LLD documents | Agent 15 |
# MAGIC | 02 | Data Engineer | Production PySpark/SQL code | Agent 06 |
# MAGIC | 16 | Data Quality | Validation rules, expectations | Agent 02 |
# MAGIC | 17 | Security | RBAC, PII, GDPR review | Agent 02 |
# MAGIC | 18 | Cost Optimization | Cluster/query cost recommendations | Agent 02 |
# MAGIC | 07 | Peer Review | Code quality scoring | Agent 02 |
# MAGIC | 08 | Unit Test | PyTest test suite generation | Agent 02 |
# MAGIC | 19 | Unit Test Documentation | Test cases + scenarios | Agent 08 |
# MAGIC | 20 | Integration Test | Cross-system test suites | Agent 08 |
# MAGIC | 09 | Environment Promotion | DEV→UAT→PRD validation | Agent 07 |
# MAGIC | 31 | Release Approval Board | Final production gate | All prior agents |
# MAGIC
# MAGIC ### Specialized Agents
# MAGIC
# MAGIC | # | Agent | What It Does |
# MAGIC | --- | --- | --- |
# MAGIC | 22 | Metadata & Lineage | Column lineage, business glossary |
# MAGIC | 23 | DataOps | Git strategy, CI/CD design |
# MAGIC | 24 | CI/CD | Azure Pipelines / GitHub Actions generation |
# MAGIC | 25 | Deployment | Deployment plans, promotion scripts |
# MAGIC | 26 | Platform Reliability | DR, failover, backup strategy |
# MAGIC | 27 | AI Governance | Validates AI outputs, prevents hallucinations |
# MAGIC | 28 | Enterprise Standards | Naming, coding, documentation compliance |
# MAGIC | 29 | Documentation | Technical docs, user guides, runbooks |
# MAGIC | 32 | Oracle EBS Specialist | EBS-specific ingestion patterns |
# MAGIC | 33 | Salesforce Sync | SFDC CDC patterns, deduplication |
# MAGIC | 34 | Hash Migration | xxHash64 migration scripts |
# MAGIC | 35 | Documentation Sync | Auto-generates Unity Catalog comments |
# MAGIC | 36 | Workspace Hygiene | Finds orphaned resources, stale tables |

# COMMAND ----------

# DBTITLE 1,Supervisor Agent
# MAGIC %md
# MAGIC ## 2.1 Supervisor Agent (Agent 00)
# MAGIC
# MAGIC The Supervisor is the **brain of the platform** — the single entry point for all user requests. It sits above all 36 agents and orchestrates them.
# MAGIC
# MAGIC ### Core Responsibilities
# MAGIC
# MAGIC | # | Responsibility | What It Does |
# MAGIC | --- | --- | --- |
# MAGIC | 1 | **Understand Request & Intent** | Parses your natural language input and determines what you need |
# MAGIC | 2 | **Identify Work Type** | Classifies into: Feature Delivery, Investigation, Optimization, Governance, Monitoring, Code Generation, Architecture, or Clarification Needed |
# MAGIC | 3 | **Task Decomposition** | Breaks complex requests into atomic sub-tasks when multiple agents are required |
# MAGIC | 4 | **Agent Assignment** | Selects the best-fit agent(s) for each sub-task based on a capability registry |
# MAGIC | 5 | **Multi-Agent Coordination** | Orchestrates agents sequentially or in parallel, passing outputs between them |
# MAGIC | 6 | **Output Validation** | Verifies each agent's output is complete, relevant, non-empty, and safe (no PII leakage) |
# MAGIC | 7 | **Conflict Resolution** | Reconciles contradictions between agents (e.g., Architect recommends streaming but Cost says batch) |
# MAGIC | 8 | **Consolidated Response** | Merges all agent outputs into a single, coherent final deliverable |
# MAGIC | 9 | **Clarification Requests** | Asks you targeted questions only when the request is genuinely ambiguous |
# MAGIC | 10 | **Agent Fleet Review** | Periodically reviews ALL agents for performance, quality, cost, and generates improvement recommendations |
# MAGIC
# MAGIC ### Additional Operational Duties
# MAGIC
# MAGIC | # | Duty | Description |
# MAGIC | --- | --- | --- |
# MAGIC | 11 | Health Monitoring | Tracks agent success/failure rates, detects stuck pipelines |
# MAGIC | 12 | Pipeline Tracking | Shows where each feature request is in the delivery chain |
# MAGIC | 13 | Smart Routing | If Peer Review rejects code (score < 6), re-triggers Data Engineer with feedback |
# MAGIC | 14 | Retry Logic | Auto-retries failed LLM calls with exponential backoff (5s → 15s → 45s) |
# MAGIC | 15 | Gate Enforcement | Blocks Release Approval unless all prerequisite agents have succeeded |
# MAGIC | 16 | Daily Summary | Generates executive digest of all agent activity |
# MAGIC
# MAGIC ### How to Use the Supervisor
# MAGIC
# MAGIC The Supervisor is invoked via a single function:
# MAGIC
# MAGIC ```python
# MAGIC result = process_request("Your natural language request here")
# MAGIC ```
# MAGIC
# MAGIC **Examples:**
# MAGIC
# MAGIC ```python
# MAGIC # Feature delivery
# MAGIC result = process_request("Create a Silver-layer supplier dimension from Oracle EBS AP_SUPPLIERS")
# MAGIC
# MAGIC # Investigation
# MAGIC result = process_request("Why is job 613621324309790 failing every hour in DEV?")
# MAGIC
# MAGIC # Optimization
# MAGIC result = process_request("Find our most expensive queries and recommend optimizations")
# MAGIC
# MAGIC # Architecture
# MAGIC result = process_request("Design the Medallion architecture for Salesforce Account data")
# MAGIC
# MAGIC # Code generation (quick)
# MAGIC result = process_request("Write a MERGE statement for incremental loading of AP invoices")
# MAGIC ```
# MAGIC
# MAGIC ### Agent Fleet Review
# MAGIC
# MAGIC The Supervisor can review all 36 agents and recommend changes:
# MAGIC
# MAGIC ```python
# MAGIC # Full 30-day fleet review
# MAGIC review = review_all_agents(lookback_days=30)
# MAGIC
# MAGIC # Quick weekly check
# MAGIC review = review_all_agents(lookback_days=7)
# MAGIC ```
# MAGIC
# MAGIC The review evaluates each agent across 7 dimensions:
# MAGIC
# MAGIC | Dimension | What It Checks | Example Finding |
# MAGIC | --- | --- | --- |
# MAGIC | **Performance** | Success rate, avg duration, token efficiency | "Agent X has 45% success rate — prompt needs refinement" |
# MAGIC | **Output Quality** | Completeness, empty outputs, relevance | "Agent Y produces empty responses 30% of the time" |
# MAGIC | **Utilization** | Usage frequency, never-called agents | "Agent Z has never been invoked — merge with Agent W?" |
# MAGIC | **Prompt Effectiveness** | Output quality patterns suggest prompt issues | "Outputs frequently miss audit columns — add to prompt" |
# MAGIC | **Cost Efficiency** | Model tier appropriateness | "Documentation agent uses Critical model — switch to Standard" |
# MAGIC | **Overlap** | Capability duplication between agents | "Cost Anomaly and Cost Optimization overlap — consolidate?" |
# MAGIC | **Gaps** | Missing capabilities | "No agent handles real-time streaming monitoring" |
# MAGIC
# MAGIC Findings are severity-graded: 🔴 CRITICAL | 🟠 HIGH | 🟡 MEDIUM | 🟢 LOW | 🔵 INFO
# MAGIC
# MAGIC Review results are saved to `mde_dev.test_schema.agent_outputs` (output_type = `fleet_review`).
# MAGIC
# MAGIC ### What Happens Inside
# MAGIC
# MAGIC When you call `process_request()`:
# MAGIC
# MAGIC ```
# MAGIC Your Request
# MAGIC     │
# MAGIC     ▼
# MAGIC ┌─────────────────────────────────────────┐
# MAGIC │ Step 1-2: Understand + Classify        │
# MAGIC │ (LLM classifies into 8 work types)     │
# MAGIC └─────────────────┬───────────────────────┘
# MAGIC                   │
# MAGIC         ┌─────────▼─────────┐
# MAGIC         │ Ambiguous?          │
# MAGIC         │ (confidence < 0.5)  │
# MAGIC         └───┬────────────┬────┘
# MAGIC          YES │            │ NO
# MAGIC              ▼            ▼
# MAGIC       Ask User    Step 3-4: Decompose + Assign
# MAGIC                        │
# MAGIC                        ▼
# MAGIC               Step 5: Coordinate Agents
# MAGIC               (run sequentially/parallel)
# MAGIC                        │
# MAGIC                        ▼
# MAGIC               Step 6: Validate Outputs
# MAGIC               (completeness, PII, relevance)
# MAGIC                        │
# MAGIC                        ▼
# MAGIC               Step 7: Resolve Conflicts
# MAGIC                        │
# MAGIC                        ▼
# MAGIC               Step 8: Consolidate Response
# MAGIC                        │
# MAGIC                        ▼
# MAGIC                Final Answer to You
# MAGIC ```
# MAGIC
# MAGIC ### Work Types the Supervisor Recognizes
# MAGIC
# MAGIC | Work Type | Typical Agents Dispatched | Example Request |
# MAGIC | --- | --- | --- |
# MAGIC | FEATURE_DELIVERY | BA → Scope → Architect → Engineer → Review → Test | "Build a new customer dimension" |
# MAGIC | INVESTIGATION | Job Triage, Drift Detector, View Dependency | "Why did the nightly load fail?" |
# MAGIC | OPTIMIZATION | Cost Anomaly, Cost Optimization, View Dependency | "Reduce our SQL Warehouse spend" |
# MAGIC | GOVERNANCE | Security, Enterprise Standards, Documentation | "Review PII handling in HCM tables" |
# MAGIC | MONITORING | Observability, Medallion Validation, Monitoring | "Check data freshness across Gold layer" |
# MAGIC | CODE_GENERATION | Data Engineer, Unit Test, Peer Review | "Write a MERGE for AP invoices" |
# MAGIC | ARCHITECTURE | Solution Architect, Lakehouse Architect | "Design CDC strategy for Salesforce" |
# MAGIC | CLARIFICATION_NEEDED | None (asks user) | "Do the thing" |

# COMMAND ----------

# DBTITLE 1,How to Run Agents
# MAGIC %md
# MAGIC ## 3. How to Run Agents
# MAGIC
# MAGIC ### Option A: Run Manually (Interactive)
# MAGIC
# MAGIC 1. Open the agent notebook (e.g., `01_job_failure_triage_agent`)
# MAGIC 2. Click **Run All** or run cells sequentially
# MAGIC 3. Results appear in the notebook output and are saved to Delta tables
# MAGIC
# MAGIC ### Option B: Run via Workflow (Scheduled/On-Demand)
# MAGIC
# MAGIC 1. Navigate to **Lakeflow Jobs** in the left sidebar
# MAGIC 2. Find the job: `Multi-Agent Platform - Daily` or `Multi-Agent Platform - Feature Delivery`
# MAGIC 3. Click **Run Now** to trigger immediately, or view the schedule
# MAGIC
# MAGIC ### Option C: Run via REST API (Programmatic)
# MAGIC
# MAGIC ```python
# MAGIC import requests
# MAGIC
# MAGIC # Trigger a single agent via Jobs API
# MAGIC response = requests.post(
# MAGIC     f"https://{workspace_url}/api/2.1/jobs/run-now",
# MAGIC     headers={"Authorization": f"Bearer {token}"},
# MAGIC     json={"job_id": JOB_ID, "notebook_params": {"requirement": "your requirement here"}}
# MAGIC )
# MAGIC ```
# MAGIC
# MAGIC ### Passing Parameters to Agents
# MAGIC
# MAGIC All agents accept parameters via `dbutils.widgets`:
# MAGIC
# MAGIC | Agent | Parameter | Description |
# MAGIC | --- | --- | --- |
# MAGIC | 01 (Triage) | `lookback_days` | How far back to scan (default: 7) |
# MAGIC | 02 (Data Engineer) | `requirement` | Natural language requirement |
# MAGIC | 02 (Data Engineer) | `source_tables` | Comma-separated table names |
# MAGIC | 06 (Architect) | `requirement` | Architecture requirement |
# MAGIC | 06 (Architect) | `source_system` | Target source (e.g., stg_oracle_ebs) |
# MAGIC | 07 (Peer Review) | `code` | Code to review |

# COMMAND ----------

# DBTITLE 1,Reading Agent Outputs
# MAGIC %md
# MAGIC ## 4. Reading Agent Outputs
# MAGIC
# MAGIC ### Delta Tables
# MAGIC
# MAGIC All agent outputs are persisted in `mde_dev.test_schema`:
# MAGIC
# MAGIC | Table | Contents |
# MAGIC | --- | --- |
# MAGIC | `agent_call_log` | Audit trail of every LLM call (tokens, cost, duration) |
# MAGIC | `agent_outputs` | All generated artifacts (reports, code, reviews) |
# MAGIC | `agent_job_triage_results` | Classified job failures with recommendations |
# MAGIC | `agent_view_dependencies` | View chain map with materialization scores |
# MAGIC | `agent_schema_snapshots` | Daily schema state (for drift detection) |
# MAGIC | `agent_drift_alerts` | Detected schema changes |
# MAGIC | `agent_cost_anomalies` | Billing anomalies and idle resources |
# MAGIC
# MAGIC ### Querying Outputs
# MAGIC
# MAGIC ```sql
# MAGIC -- Get the latest triage report
# MAGIC SELECT content 
# MAGIC FROM mde_dev.test_schema.agent_outputs
# MAGIC WHERE agent_name = 'job_failure_triage' 
# MAGIC   AND output_type = 'triage_report'
# MAGIC ORDER BY timestamp DESC LIMIT 1;
# MAGIC
# MAGIC -- Get all code generated by the Data Engineer agent
# MAGIC SELECT timestamp, metadata, LEFT(content, 200) as preview
# MAGIC FROM mde_dev.test_schema.agent_outputs
# MAGIC WHERE agent_name = 'data_engineer'
# MAGIC ORDER BY timestamp DESC;
# MAGIC
# MAGIC -- Cost tracking: how much did agents cost today?
# MAGIC SELECT agent_name, COUNT(*) as calls, SUM(tokens_in + tokens_out) as total_tokens
# MAGIC FROM mde_dev.test_schema.agent_call_log
# MAGIC WHERE timestamp >= CURRENT_DATE()
# MAGIC GROUP BY 1 ORDER BY total_tokens DESC;
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Customizing Agents
# MAGIC %md
# MAGIC ## 5. Customizing Agents
# MAGIC
# MAGIC ### Changing the LLM Model
# MAGIC
# MAGIC Edit `00_agent_config` notebook, update these variables:
# MAGIC
# MAGIC ```python
# MAGIC LLM_CRITICAL = "databricks-claude-sonnet-4-6"   # For Architect, Data Engineer, Peer Review
# MAGIC LLM_STANDARD = "databricks-claude-sonnet-4-6"   # For all other agents
# MAGIC ```
# MAGIC
# MAGIC Available models (via Foundation Model APIs):
# MAGIC - `databricks-claude-sonnet-4-6` — Best quality, higher cost
# MAGIC - `databricks-claude-opus-4-6` — Maximum quality, highest cost
# MAGIC - `databricks-llama-4-maverick` — Good quality, lowest cost
# MAGIC - `databricks-gpt-oss-20b` — Moderate quality, low cost
# MAGIC
# MAGIC ### Changing Output Location
# MAGIC
# MAGIC Edit `00_agent_config`:
# MAGIC ```python
# MAGIC CATALOG = "mde_dev"      # Change catalog
# MAGIC SCHEMA = "test_schema"   # Change schema
# MAGIC ```
# MAGIC
# MAGIC ### Adding a New Agent
# MAGIC
# MAGIC 1. Copy any existing agent notebook as a template
# MAGIC 2. Update the system prompt for your use case
# MAGIC 3. Register it in `00_agent_config` → `AGENT_REGISTRY`
# MAGIC 4. Add it to the Workflow if it should run on schedule

# COMMAND ----------

# DBTITLE 1,Troubleshooting
# MAGIC %md
# MAGIC ## 6. Troubleshooting
# MAGIC
# MAGIC ### Agent returns empty or error response
# MAGIC
# MAGIC **Cause:** LLM endpoint may be rate-limited or unavailable.
# MAGIC
# MAGIC **Fix:** Check `agent_call_log` for the error:
# MAGIC ```sql
# MAGIC SELECT * FROM mde_dev.test_schema.agent_call_log
# MAGIC WHERE status LIKE 'ERROR%' ORDER BY timestamp DESC LIMIT 5;
# MAGIC ```
# MAGIC
# MAGIC ### "Table not found" errors
# MAGIC
# MAGIC **Cause:** First run hasn't created the tables yet.
# MAGIC
# MAGIC **Fix:** Run `00_agent_config` notebook first — it creates all required tables.
# MAGIC
# MAGIC ### Agent produces hallucinated table names
# MAGIC
# MAGIC **Cause:** System prompt doesn't have enough schema context.
# MAGIC
# MAGIC **Fix:** The Data Engineer agent (02) auto-fetches schema context via `build_schema_context()`. Ensure source tables exist and are accessible.
# MAGIC
# MAGIC ### Cost concerns
# MAGIC
# MAGIC **Monitor costs with:**
# MAGIC ```sql
# MAGIC SELECT 
# MAGIC     DATE(timestamp) as day,
# MAGIC     agent_name,
# MAGIC     COUNT(*) as calls,
# MAGIC     SUM(tokens_in) as input_tokens,
# MAGIC     SUM(tokens_out) as output_tokens
# MAGIC FROM mde_dev.test_schema.agent_call_log
# MAGIC GROUP BY 1, 2 ORDER BY 1 DESC, calls DESC;
# MAGIC ```
# MAGIC
# MAGIC **Estimated cost:** ~$0.003–$0.05 per agent call (Claude Sonnet 4). Full 36-agent pipeline = ~$0.63/feature.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Questions?** Contact the Data Engineering team or check the Developer Guide for technical details.