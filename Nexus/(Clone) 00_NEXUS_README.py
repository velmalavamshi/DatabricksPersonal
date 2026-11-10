# Databricks notebook source
# DBTITLE 1,NEXUS Platform README
# MAGIC %md
# MAGIC # NEXUS — Multi-Agent AI Platform
# MAGIC
# MAGIC > **Hologic's autonomous AI operations platform built 100% on Databricks.**
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Architecture
# MAGIC
# MAGIC ```
# MAGIC                         ┌─────────────────────────────┐
# MAGIC                         │   INTERACTIVE LAYER       │
# MAGIC                         │  CHAT_Interactive_Supervisor│
# MAGIC                         └─────────────┬───────────────┘
# MAGIC                                     │
# MAGIC                         ┌─────────────┴───────────────┐
# MAGIC                         │   W0: META ORCHESTRATOR     │
# MAGIC                         │  Supervisor • Router • Mesh  │
# MAGIC                         │  Governance + Monitoring (10) │
# MAGIC                         └───┬───────┬───────┬───────┬───┘
# MAGIC                             │       │       │       │
# MAGIC                     ┌───────┴─┐ ┌───┴───┐ ┌───┴───┐ ┌───┴───┐
# MAGIC                     │   W1    │ │  W2   │ │  W3   │ │  W4   │
# MAGIC                     │Production│ │Value  │ │Business│ │Collect│
# MAGIC                     │ 60 agents│ │Discov.│ │Champs │ │Intel. │
# MAGIC                     └──────────┘ └───────┘ └───────┘ └───────┘
# MAGIC                             │
# MAGIC                     ┌───────┴─────────────────────────┐
# MAGIC                     │   DELTA EVENT BUS               │
# MAGIC                     │   nexus_agent_events (CDF)       │
# MAGIC                     └─────────────────────────────────┘
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Folder Structure
# MAGIC
# MAGIC ```
# MAGIC /5 - AI Multi Agents/
# MAGIC ├── 00_NEXUS_README                    ← You are here
# MAGIC ├── 0 - Meta Orchestrator/             ← W0: Hub + Governance + Monitoring (13 agents)
# MAGIC │   ├── 00_meta_config
# MAGIC │   ├── 00_meta_supervisor
# MAGIC │   ├── 02_event_mesh
# MAGIC │   ├── 03_version_manager
# MAGIC │   ├── 04_security_layer
# MAGIC │   ├── 05_feedback_system
# MAGIC │   ├── 06_circuit_breaker_manager
# MAGIC │   ├── 07_governance_dashboard
# MAGIC │   ├── 08_nexus_scheduler
# MAGIC │   ├── 09_nexus_e2e_test
# MAGIC │   ├── 10_audit_trail
# MAGIC │   ├── 11_monitoring_dashboard
# MAGIC │   ├── 12_cost_attribution
# MAGIC │   ├── 13_event_bus_monitor
# MAGIC │   └── 14_agent_leaderboard
# MAGIC ├── 1 - Production Agents/             ← W1: 60 agents
# MAGIC │   ├── 00_agent_config
# MAGIC │   ├── 00_consultation_config
# MAGIC │   ├── 00_supervisor_agent
# MAGIC │   ├── CHAT_Interactive_Supervisor     ← Primary interface
# MAGIC │   ├── 39_morning_briefing_agent
# MAGIC │   ├── 39a_briefing_config
# MAGIC │   ├── 40_morning_triage_orchestrator
# MAGIC │   ├── 44-48: Oracle/Salesforce specialists
# MAGIC │   ├── 53-54: ServiceNow/PowerBI
# MAGIC │   ├── 60_consultation_router
# MAGIC │   ├── 61_specialist_base
# MAGIC │   └── 62_consultation_tracker
# MAGIC ├── 2 - Value Discovery/               ← W2: 5 agents
# MAGIC │   ├── 00_vd_config
# MAGIC │   ├── 01_workspace_scanner
# MAGIC │   ├── 02_use_case_scorer
# MAGIC │   ├── 03_maturity_assessor
# MAGIC │   └── 04_report_generator
# MAGIC ├── 3 - Business Champions/            ← W3: 5 agents
# MAGIC │   ├── 00_bc_config
# MAGIC │   ├── 01_business_case_builder
# MAGIC │   ├── 02_pptx_generator
# MAGIC │   ├── 03_executive_summary
# MAGIC │   └── 04_champion_coach
# MAGIC └── 4 - Collective Intelligence/       ← W4: 5 agents
# MAGIC     ├── 00_ci_config
# MAGIC     ├── 01_pattern_detector
# MAGIC     ├── 02_benchmark_engine
# MAGIC     ├── 03_failure_predictor
# MAGIC     └── 04_insight_publisher
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Agent Inventory (88 Total)
# MAGIC
# MAGIC | Workspace | Agents | Layer Types | Purpose |
# MAGIC |---|---|---|---|
# MAGIC | W0 Meta Orchestrator | 13 | Strategy, Execution, Governance, Monitoring | Hub routing, event mesh, governance, observability |
# MAGIC | W1 Production Agents | 60 | Strategy, Execution, Specialist | Day-to-day Databricks operations, consultation network |
# MAGIC | W2 Value Discovery | 5 | Strategy, Execution | Client scanning, maturity, use cases |
# MAGIC | W3 Business Champions | 5 | Strategy, Execution | Board decks, business cases, ROI |
# MAGIC | W4 Collective Intelligence | 5 | Strategy, Execution | Patterns, benchmarks, predictions |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Communication Patterns
# MAGIC
# MAGIC | Pattern | When | Example |
# MAGIC |---|---|---|
# MAGIC | **Supervisor routing** | Interactive requests | User → Meta Supervisor → W1 Agent |
# MAGIC | **Workflow chains** | Scheduled pipelines | Briefing → Triage → ADO |
# MAGIC | **Event bus (pub/sub)** | Async decoupled | Agent publishes BRIEFING_COMPLETE → Triage consumes |
# MAGIC | **Specialist consultation** | Domain expertise | Triage → consults Oracle EBS specialist |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Delta Infrastructure
# MAGIC
# MAGIC | Table | Purpose | CDF |
# MAGIC |---|---|---|
# MAGIC | `mde_dev.test_schema.nexus_agent_events` | Event bus (publish/subscribe) | Yes |
# MAGIC | `mde_dev.test_schema.nexus_agent_memory` | Per-agent key-value memory | No |
# MAGIC | `mde_dev.test_schema.nexus_agent_registry` | Agent catalog (88 rows) | No |
# MAGIC | `mde_dev.test_schema.nexus_agent_trace_log` | Execution traces, latency, tokens | No |
# MAGIC | `mde_dev.test_schema.nexus_agent_circuit_breaker` | Failure tracking, auto-pause | No |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Scheduled Jobs
# MAGIC
# MAGIC | Job | Schedule | Tasks | Est. Cost/Run |
# MAGIC |---|---|---|---|
# MAGIC | NEXUS_Morning_Briefing | Daily 07:00 UTC | briefing → triage | ~$0.05 |
# MAGIC | NEXUS_Governance_Cycle | Daily 06:00 UTC | versions → security/feedback/breakers → dashboard | ~$0.08 |
# MAGIC | NEXUS_Monitoring_Cycle | Daily 05:30 UTC | audit → monitoring/cost/eventbus → leaderboard | ~$0.10 |
# MAGIC | NEXUS_W4_Intelligence | Sun 02:00 UTC | patterns → benchmarks/predictor → publisher | ~$0.12 |
# MAGIC | NEXUS_Event_Mesh | Every 15 min | dispatch | ~$0.01 |
# MAGIC | NEXUS_Consultation_Tracker | Every 30 min | SLA monitoring | ~$0.01 |
# MAGIC
# MAGIC **Estimated total: ~$12-16/month** at $0.45/DBU serverless jobs.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Standards
# MAGIC
# MAGIC - **LLM:** `databricks-claude-sonnet-4-6` via REST API (NOT SDK — typed message bug)
# MAGIC - **Surrogate keys:** `xxhash64(CONCAT_WS('|', ...))` — never MD5
# MAGIC - **Credentials:** `dbutils.secrets.get("nexus", key)` — never hardcoded
# MAGIC - **Tables:** MERGE/COPY INTO for idempotency
# MAGIC - **Clustering:** Liquid Clustering (not PARTITION BY)
# MAGIC - **Cost queries:** Always JOIN `system.billing.list_prices`
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Operations Runbook
# MAGIC
# MAGIC ### First-Time Setup
# MAGIC 1. Run `00_nexus_infrastructure_setup` (Phase 1 — creates tables + secrets)
# MAGIC 2. Run `09_nexus_e2e_test` to validate platform health
# MAGIC 3. Run `08_nexus_scheduler` to deploy jobs (PAUSED)
# MAGIC 4. Unpause jobs after e2e passes
# MAGIC
# MAGIC ### Daily Operations
# MAGIC - Monitoring cycle at 05:30 UTC → `11_monitoring_dashboard` + `14_agent_leaderboard`
# MAGIC - Governance cycle at 06:00 UTC → `07_governance_dashboard`
# MAGIC - Morning briefing fires at 07:00 UTC → check Teams/email for alerts
# MAGIC - Consultation tracker every 30 min → SLA enforcement
# MAGIC - Use `CHAT_Interactive_Supervisor` for ad-hoc requests
# MAGIC
# MAGIC ### Troubleshooting
# MAGIC - Agent stuck? Check `nexus_agent_circuit_breaker` for OPEN state
# MAGIC - Event not consumed? Run `02_event_mesh` manually
# MAGIC - LLM timeout? Check endpoint status in Serving UI
# MAGIC - Cost spike? Check `system.billing.usage` for the agent's job
# MAGIC
# MAGIC ### Adding a New Agent
# MAGIC 1. Create notebook in appropriate workspace folder
# MAGIC 2. Add `%run ./00_*_config` as first executable cell
# MAGIC 3. Register in `nexus_agent_registry` (INSERT)
# MAGIC 4. Initialize circuit breaker (INSERT into `nexus_agent_circuit_breaker`)
# MAGIC 5. Add to scheduler if needed (update `08_nexus_scheduler`)
# MAGIC 6. Run e2e test to validate