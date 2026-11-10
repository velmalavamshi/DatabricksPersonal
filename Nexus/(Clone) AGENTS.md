# NEXUS Multi-Agent AI Platform

> **For AI Assistants:** This file provides full context for the NEXUS project. Load this before making changes to any agent notebook.

## Quick Reference

| Attribute | Value |
|-----------|-------|
| Project Name | NEXUS |
| Root Path | `/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/` |
| Total Agents | 134 (125 built + 9 planned) |
| LLM (APEX) | `databricks-claude-opus-5` — Architects, Modeler, Peer Review |
| LLM (CRITICAL) | `databricks-claude-sonnet-5` — Engineers, Triage, Security |
| LLM (STANDARD) | `databricks-claude-sonnet-5` — All others |
| State | Delta tables in `mde_dev.test_schema` |
| Compute | Serverless Jobs Compute ($0.45/DBU) |
| Tracing | MLflow 3 (experiment: `/Users/sameet.patel@hologic.com/NEXUS_Agent_Traces`) |

---

## Architecture Overview

NEXUS uses a **hierarchical hub-and-spoke** architecture with an **event bus** for async messaging:

```
                    ┌─────────────────────┐
                    │   Meta Supervisor   │  ← Intent classification + routing
                    │      (W0)           │
                    └─────────┬───────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ W1 Production │   │ W2 Value      │   │ W3 Business   │
│ (102 agents)  │   │ Discovery     │   │ Champions     │
└───────┬───────┘   └───────────────┘   └───────────────┘
        │
        ├── Strategy Layer (Supervisor, Architects, BA)
        ├── Specialist Layer (EBS, SFDC, ASCP, HCM, etc.)
        └── Execution Layer (Engineers, Quality, DevOps)
```

### Communication Patterns

1. **Hub-and-Spoke (synchronous):** Supervisor → classifies → routes → specialist executes
2. **Pipeline Chain (scheduled):** Workflow task dependencies (e.g., Briefing → Triage → ServiceNow)
3. **Delta State (async):** Agent writes output to `agent_outputs`, another reads later
4. **Event Bus (pub/sub):** `agent_events` Delta table for decoupled messaging

---

## Workspace Structure

| Workspace | Path | Purpose | Agent Count |
|-----------|------|---------|-------------|
| W0 | `0 - Meta Orchestrator/` | Meta Supervisor, intent router, event mesh, governance | 16 |
| W1 | `1 - Production Agents/` | Core engineering, specialists, execution, release intelligence (11), Qlik migration (9) | 103 |
| W2 | `2 - Value Discovery/` | Client scanning, use case scoring, idea scanning, proposal generation | 6 |
| W3 | `3 - Business Champions/` | Board-ready business cases, PowerPoint | 4 |
| W4 | `4 - Collective Intelligence/` | Pattern learning, benchmarks, predictions | 4 |

---

## Agent Inventory (W1 Production — 103 agents)

### Strategy Layer (5)
| ID | Agent | Purpose | Priority |
|----|-------|---------|----------|
| 00 | supervisor_agent | Routes within W1, orchestrates pipelines | HIGH |
| 06 | solution_architect_agent | HLD/LLD, architecture design | HIGH |
| 11 | business_analyst_agent | BRDs, user stories, requirements | MEDIUM |
| 38 | solution_recommender_agent | Artifact type selection | MEDIUM |
| 63 | agent_factory_agent | Creates Hologic-standard agent notebooks (7-cell template), registers in AGENT_REGISTRY | HIGH |

### Specialist Layer (27)
| ID | Agent | Domain | Tables | Notebook ID |
|----|-------|--------|--------|-------------|
| 15 | lakehouse_architect_agent | Medallion, Unity Catalog, Data Mesh | — | — |
| 64 | sdp_agent | Author/monitor Spark Declarative Pipelines — Bronze/Silver/Gold patterns, expectations, Auto CDC, streaming vs batch | — | 350235908256380 |
| 65 | sql_warehouse_agent | SQL Warehouse right-sizing, auto-stop policies, T-shirt sizing, Photon toggle, result cache tuning | — | 350235908256385 |
| 66 | unity_catalog_agent | Full UC governance — RBAC grants, tags, column masks, row filters, ABAC policies, lineage browsing (supersedes 17_security partial) | — | 350235908256386 |
| 67 | mlflow_model_serving_agent | MLflow experiment tracking, UC model registry, endpoint deployment, A/B routing, monitoring via system.serving tables | — | 350235908256387 |
| 68 | ai_bi_dashboard_agent | Lakeview AI/BI dashboard creation, widget authoring, dataset binding (distinct from 74_genie_space_agent) | — | 350235908256388 |
| 69 | cluster_management_agent | Cluster policies, autoscaling config, compute right-sizing, idle termination, Spark UI analysis | — | 350235908256389 |
| 70 | vector_search_agent | VS endpoint/index creation, embedding ingestion, similarity query patterns, RAG pipeline design (extends 05 cost tool) | — | 350235908256390 |
| 71 | notebook_lifecycle_agent | Create Hologic-standard notebooks (any type), Git sync, version tagging, cleanup/archive | — | 350235908256391 |
| 73 | databricks_app_agent | Scaffold/deploy/diagnose Databricks Apps, SP permissions, IP ACL guidance (renumbered from 60; consultation_router occupies slot 60) | — | 350235908256392 |
| 74 | genie_space_agent | Create Genie spaces, register mde_dev.gold/platinum tables, curate question sets, monitor query logs (renumbered from 61) | — | 350235908256393 |
| 75 | ai_gateway_agent | AI Gateway endpoint config, route/rate limits, guardrails (PII, toxicity), inference table logging (renumbered from 62) | — | 350235908256394 |
| 32 | oracle_ebs_specialist_agent | EBS (AP, AR, GL, PO, INV) | 1,263 |
| 33 | salesforce_sync_agent | SFDC CDC, dedup | 768 |
| 37 | data_modeler_agent | Kimball star schema, facts/dims | — |
| 44 | oracle_ebs_extract_agent | EBS extract monitoring | — |
| 47 | salesforce_extract_agent | SFDC extract monitoring | — |
| 49 | ascp_specialist_agent | Supply chain planning | 238 |
| 50 | agile_plm_agent | Product lifecycle, BOM | 82 |
| 51 | koerber_specialist_agent | Warehouse management | 2 |
| 52 | oracle_hcm_specialist_agent | Workforce, payroll | 147 |
| 53 | servicenow_agent | ServiceNow integration | — |
| 54 | powerbi_agent | Power BI refresh monitoring | — |
| 55 | pbcs_specialist_agent | Financial planning | 42 |
| 56 | hcp_specialist_agent | Healthcare providers, PII | 81 |
| 57 | definitive_specialist_agent | Market intelligence | 34 |
| 58 | cornerstone_specialist_agent | LMS, compliance | 29 |
| 59 | mulesoft_specialist_agent | API/integration health | 4 |

### Release Intelligence Layer (11)
| ID | Agent | Purpose | Notebook ID |
|----|-------|---------|-------------|
| 77 | release_intelligence_agent | Orchestrator — weekly consolidated vendor impact report | 1025795174227706 |
| 78 | oracle_release_monitor_agent | Oracle EBS patches, CPUs, desupport (1,263 tables) | 1025795174227707 |
| 79 | salesforce_release_monitor_agent | SFDC seasonal releases, API deprecations (768 tables) | 1025795174227708 |
| 80 | powerbi_release_monitor_agent | Monthly PBI updates, connector/DAX changes, Fabric | 1025795174227709 |
| 81 | databricks_release_monitor_agent | Runtime EOL, API deprecation, UC changes, model retirement | 1025795174227710 |
| 82 | azure_platform_release_monitor_agent | Azure service retirements, pricing, Entra ID, Private Link | 1025795174227711 |
| 83 | mulesoft_release_monitor_agent | Connector deprecations, MuleSoft runtime EOL, CloudHub | 1025795174227712 |
| 84 | delta_spark_oss_release_monitor_agent | Delta protocol bumps, Spark 4.0 transition, MERGE/NULL | 1025795174227713 |
| 85 | azure_devops_release_monitor_agent | Pipeline agent changes, ADO API deprecations, YAML schema | 1025795174227714 |
| 86 | python_ecosystem_release_monitor_agent | pandas 3.x, numpy 2.x, pyarrow, openai, mlflow 3.x | 1025795174227715 |
| 87 | oracle_cloud_release_monitor_agent | PBCS + HCM Cloud quarterly updates, OCI API changes | 1025795174227716 |

### Qlik Migration Layer (9)
| ID | Agent | Purpose | Notebook ID |
|----|-------|---------|-------------|
| 88 | qlik_migration_orchestrator_agent | Top-level orchestrator — inventory, dependency mapping, wave planning, progress tracking | 3084094643406393 |
| 89 | qvd_extraction_agent | QVD file analysis — schema extraction, data profiling, QVD layered arch → Delta tables | 3084094643406394 |
| 90 | qlik_script_conversion_agent | Parses QVS/QVW load scripts — LOAD, JOIN, CONCATENATE, mapping loads → PySpark/SQL | 3084094643406395 |
| 91 | qlik_data_model_agent | Analyzes associative models — synthetic keys, circular refs → Kimball star schema | 3084094643406396 |
| 92 | qlik_expression_agent | Converts set analysis, AGGR(), variables → Databricks SQL / Lakeview expressions | 3084094643406397 |
| 93 | qlik_ui_migration_agent | Maps QlikView/Sense objects (charts, tables, KPIs) → Lakeview / Power BI | 3084094643406398 |
| 94 | qlik_section_access_agent | Converts Section Access (RLS) → UC row filters, column masks, ABAC policies | 3084094643406399 |
| 95 | qlik_nprinting_agent | NPrinting reports/schedules → Databricks Jobs + Lakeview subscriptions + email | 3084094643406400 |
| 96 | qlik_preassessment_agent | Deterministic -prj folder parser — batch inventory, expression corpus, variables, dependency DAG → Delta tables for Agent 88 | 2474517819316867 |

### Execution Layer (41)
| ID | Agent | Purpose |
|----|-------|---------|
| 01 | job_failure_triage_agent | Classify failures, auto-remediation |
| 02 | data_engineer_agent | Production PySpark/SQL code |
| 03 | view_dependency_agent | Performance bottleneck analysis |
| 04 | source_drift_detector_agent | Schema change detection |
| 07 | peer_review_agent | Code quality scoring (blocks on < 6) |
| 08 | unit_test_agent | PyTest + Nutter test notebook generation |
| 16 | data_quality_agent | DLT expectations + DQX rules (databricks-labs-dqx) |
| 17 | security_agent | RBAC, PII, GDPR review |
| 20 | integration_test_agent | End-to-end test suites |
| 76 | layer_validation_agent | Silver/Gold/Platinum DQX + Nutter gate (PASS/WARN/FAIL) before Agent 31 |
| 39 | morning_briefing_agent | Daily morning briefing (Teams + Email) |
| 40 | morning_triage_orchestrator | Auto-creates ADO work items |

### Tools (deterministic, no LLM — 14)
| ID | Tool | Function |
|----|------|----------|
| 05 | cost_anomaly | `system.billing.usage` anomaly detection |
| 10 | medallion_validation | `information_schema` layer integrity |
| 14 | azure_devops | ADO API work item creation |
| 18 | cost_optimization | Right-sizing via billing queries |
| 21 | observability | Logging/tracing queries |
| 22 | metadata_lineage | Unity Catalog lineage queries |
| 23 | dataops | Workflow status queries |
| 24 | cicd | Pipeline status queries |
| 25 | deployment | Deployment checklist execution |
| 26 | platform_reliability | System tables cluster/warehouse health |
| 30 | monitoring | `agent_call_log` health metrics |
| 36 | workspace_hygiene | Orphaned resources across workspaces |

### Skills (context injection — 6)
| ID | Skill | Injected Context |
|----|-------|------------------|
| 19 | unit_test_documentation | Test matrix template |
| 27 | ai_governance | Model risk, bias, fairness |
| 28 | enterprise_standards | xxHash64, audit cols, Liquid Clustering |
| 29 | documentation | Hologic wiki format |
| 31 | release_approval_board | HARD GATE checklist |
| 35 | documentation_sync | Stale docs, auto-changelog |

---

## W2 Value Discovery Inventory (6 agents)

| ID | Agent | Purpose | Notebook ID |
|----|-------|---------|-------------|
| 01 | workspace_scanner | Scans target workspace via system tables for inventory, cost, jobs, and AI footprint | 276762526488006 |
| 02 | use_case_scorer | Uses LLM scoring to rank AI/ML opportunities from workspace scan results | 276762526488007 |
| 03 | maturity_assessor | Assesses Databricks maturity across governance, pipelines, cost, BI, AI, and operations | 276762526488008 |
| 04 | report_generator | Produces assessment report and executive summary from W2 outputs | 276762526488009 |
| 05 | idea_scanner | Scans external idea libraries, cross-references NEXUS coverage, scores Hologic relevance, and seeds `idea_seed_library` | 1405118320738450 |
| 06 | agent_proposal_generator | Reads top-scored gap ideas from `idea_seed_library`, LLM-generates Databricks-native build proposals, and persists to `agent_build_backlog` for W1 Agent 63 | 1405118320738458 |

---

## Key Files

| File | Purpose |
|------|---------|
| `1 - Production Agents/00_agent_config.py` | Shared config, LLM client, `call_agent()`, state management |
| `1 - Production Agents/00_supervisor_agent.py` | W1 router, `coordinate_agents()`, pipeline orchestration |
| `2 - Value Discovery/00_vd_config` | Shared W2 config, scan queries, scoring frameworks, `call_llm()` |
| `shared_token_optimizer.py` | Memory, budget, catalog cache (loaded via `%run`) |
| `CHAT_Interactive_Supervisor.py` | Interactive chat interface (LLM-only, no Delta writes) |

---

## Project Documentation (Canonical Location)

> **⚠️ ALL phase, handoff, enhancement, and planning docs live in `0 - Project Docs/`. ALWAYS create new docs here. NEVER scatter across subfolders.**

**Path:** `/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/0 - Project Docs/`

| File | Purpose |
|------|---------|
| `PHASE_8_GOVERNANCE_OMNIGENT.md` | Phase 8 — Governance Engine design & implementation notes |
| `PHASE_9_AGENT_INTELLIGENCE_OMP.md` | Phase 9 — Agent Intelligence Engine (semantic memory, compaction, stream rules) |
| `PHASE_10_RELEASE.md` | Phase 10 — Release planning & deployment notes |
| `PHASE_11.md` | Phase 11 — Current/upcoming enhancements |
| `NEXUS_UI_ENHANCEMENTS_PHASE.md` | UI/UX improvements for the NEXUS chat app |
| `NEXUS_APP_PATCH_HANDOFF.md` | App patch handoff notes (deployment, fixes, config) |
| `CONVERSATION_HISTORY_PLAN.md` | Conversation history feature design |
| `Handoff_Setup_Notion.mht` | Original Notion export — handoff setup reference |
| `CHECKLIST.md` | **Master checklist — review BEFORE starting any new phase or enhancement** |
| `databricks-genie-token-optimizer-prompt.md` | Token optimizer prompt engineering reference |

### Rules for This Folder

1. **New phases** → Create `PHASE_<N>_<TOPIC>.md` here
2. **New handoffs** → Create `<FEATURE>_HANDOFF.md` here
3. **Before starting new work** → Review `CHECKLIST.md` first
4. **Never create enhancement docs** in `5 - Agent Chat App/`, `0 - All files/`, or any other subfolder

---

## Coding Standards

### Agent Creation Checklist

When adding new agents, complete ALL steps:

| # | Step | Location | Why |
|---|------|----------|-----|
| 1 | Create agent notebook(s) in W1 folder | `1 - Production Agents/` | 7-cell template (md, config, widgets, context, prompt, LLM, validate) |
| 2 | Add to AGENTS.md inventory table | `AGENTS.md` | ID, name, purpose, notebook ID |
| 3 | Update agent count in Quick Reference | `AGENTS.md` top table | Total Agents row + W1 row |
| 4 | Add domain keywords to `AGENT_REGISTRY` | `CHAT_Interactive_Supervisor` Cell 6 | Intent router keyword matching |
| 5 | Add agent section to `SUPERVISOR_PROMPT` | `CHAT_Interactive_Supervisor` Cell 6 | Full system prompt awareness |
| 6 | Add agent section to `SUPERVISOR_PROMPT_FOR_PLAYGROUND` | `CHAT_Interactive_Supervisor` Cell 3 | Playground copy-paste prompt |
| 7 | Update `app.py` system prompt | `2 - Agent Chat App/app.py` | Databricks App UI (hologic-ai-agents) |
| 8 | Update `.assistant_instructions.md` | User home `.assistant_instructions.md` | Agent count + notebook IDs for assistant memory |
| 9 | Re-run Cell 6 | `CHAT_Interactive_Supervisor` | Reload registry into running session |

**Skip list:** Steps 7 (app) can be batched — update after multiple agent groups are complete, not per-agent.

### Every Agent Notebook Follows This Structure:

```
Cell 1: %md header (purpose, I/O, pipeline position)
Cell 2: %run ./00_agent_config (inherit shared toolkit)
Cell 3: STEP 1 — Widgets (input from supervisor or human)
Cell 4: STEP 2 — Context gathering (catalog scan, Delta reads)
Cell 5: STEP 3 — Context formatting (build LLM prompt context)
Cell 6: STEP 4 — LLM call (call_agent() with system + user prompt)
Cell 7: STEP 5 — Validate & persist (quality gates, save_agent_output())
```

### Hologic Standards (ENFORCE ALWAYS — derived from production DDL)

- **Surrogate keys:** `xxhash64(CONCAT_WS('|', keys))` as **STRING** with `_SK` suffix — NEVER MD5/SHA
- **Column naming:** **PascalCase** (e.g. `CustomerAccount_SK`, `InvoiceLine_SK`, `AccountingDate`, `PaymentStatusFlag`)
- **Table naming:** snake_case with prefix: `fact_`/`dim_`/`bridge_`/`agg_`/`stg_`
- **Audit columns (FACTS):** `dl_rowhash STRING`, `dl_creation_date_time TIMESTAMP`, `dl_last_updated_date_time TIMESTAMP`
- **Audit columns (DIMS):** `dl_iscurrent BOOLEAN`, `dl_recordstartdateutc TIMESTAMP`, `dl_recordenddateutc TIMESTAMP`, `dl_transform_id INT`, `dl_rowhash STRING`
- **⚠️ NEVER:** `etl_load_datetime`, `etl_source_system`, `etl_batch_id` — these are violations of the Hologic standard
- **Clustering:** `CLUSTER BY AUTO` (NOT PARTITION BY, NOT explicit CLUSTER BY columns)
- **TBLPROPERTIES:** `autoCompact=true`, `optimizeWrite=true`, `compression=zstd`, `deletionVectors=true`, `rowTracking=true`
- **Constraints:** `PRIMARY KEY` on grain SK column + table/column `COMMENT`s required
- **Catalog:** `mde_dev` (DEV), `mde_uat` (UAT), `mde_prd` (PRD)
- **Data types:** STRING for codes/IDs, FLOAT for amounts, DATE/TIMESTAMP for temporal

### LLM Configuration (3-Tier Model Hierarchy)

```python
LLM_APEX     = "databricks-claude-opus-5"    # Architects (06, 15, 37), Peer Review (07)
LLM_CRITICAL = "databricks-claude-sonnet-5"  # Engineers, Triage, Security
LLM_STANDARD = "databricks-claude-sonnet-5"  # All others (swap to cheaper when available)
```

| Tier | Model | Agents | Rationale |
|------|-------|--------|----------|
| APEX | Claude Opus 4-8 | solution_architect (06), peer_review (07), lakehouse_architect (15), data_modeler (37) | Benchmark: 7/7 quality vs Sonnet 6/7 on architecture tasks. 8s faster, +0.14¢/call |
| CRITICAL | Claude Sonnet 4-6 | supervisor (00), data_engineer (02), job_failure_triage (01), security (17), + 5 others | Fast + capable. Strong on code, triage, and security reasoning |
| STANDARD | Claude Sonnet 4-6 | All remaining 47 agents | Future downgrade candidates when cheaper models match quality |

**Opus caveat:** Does NOT support the `temperature` parameter. `call_agent()` automatically skips it for Opus models.

**Decision rationale (June 15, 2026):** Open-source models (Qwen 3.5 122B, Llama 4 Maverick) are cheaper ($0.070/DBU) but NOT stronger than Sonnet. At ~$30-50/month total LLM spend, the ~33% per-call savings don't justify quality risk for production pipelines. Revisit when monthly spend crosses $200+ or a new model demonstrably outperforms Sonnet.

### Agent Types (AGENT_REGISTRY is source of truth)

- `agent` — Full LLM reasoning, use `call_agent()`
- `tool` — Deterministic Python function, no LLM, instant
- `skill` — Context injection into next agent's prompt, no standalone execution

---

## API Reference

### call_agent()
```python
def call_agent(agent_name: str, system_prompt: str, user_prompt: str, 
               temperature: float = 0.1, max_tokens: int = 4096) -> str:
    """Call LLM for a specific agent. Includes MLflow tracing + Delta logging.
    Note: temperature is automatically skipped for Opus models (unsupported param).
    """
```

### save_agent_output()
```python
def save_agent_output(agent_name: str, run_id: str, output_type: str, 
                      content: str, metadata: dict = None):
    """Save agent output artifact to mde_dev.test_schema.agent_outputs."""
```

### get_latest_agent_output()
```python
def get_latest_agent_output(agent_name: str, output_type: str = None) -> str:
    """Retrieve the most recent output from an agent (for chaining)."""
```

### generate_run_id()
```python
def generate_run_id() -> str:
    """Generate unique run ID: YYYYMMDD_HHMMSS_uuid8."""
```

### Phase 9 — Agent Intelligence Engine

```python
# 9.1: Semantic Memory
def remember(agent_name: str, content: str, metadata: dict = None) -> str:
    """Store durable fact with embedding + dedup. Returns memory_id."""

def recall(agent_name: str, query: str, top_k: int = 5, bank: str = None) -> list:
    """Hybrid semantic + keyword search over agent's memory bank."""

def reflect(agent_name: str, query: str, top_k: int = 10) -> str:
    """LLM synthesis over recalled memories."""

# 9.2: Content-Hash Verification
def hash_context(context: dict) -> str:
    """SHA256-based fingerprint of input context (stale-write detection)."""

def verified_save(agent_name: str, output: dict, context_hash: str, target_key: str) -> dict:
    """Compare-and-swap: write only if context hasn't changed since read."""

def context_aware_call(agent_name: str, system_prompt: str, user_prompt: str, 
                       context_keys: list = None, target_key: str = None) -> dict:
    """call_agent() wrapper with hash verification + auto-retry on stale."""

# 9.3: Auto-Compaction
def compact_context(messages: list, model: str = None, max_tokens: int = None) -> list:
    """Auto-compact conversation preserving protected zones."""

def maybe_compact(messages: list, model: str = None) -> list:
    """Drop-in pre-call hook: compact only if >80% context window used."""

# 9.4: Stream Rule Enforcement
def check_stream_rules(agent_name: str, response: str) -> dict:
    """Check completed response against regex stream rules."""

def call_agent_with_rules(agent_name: str, system_prompt: str, user_prompt: str, **kwargs) -> str:
    """call_agent() + stream rule enforcement (abort/retry on violation)."""

# 9.5: Session Consolidation
def consolidate_session(agent_name: str, session_id: str) -> dict:
    """End-of-session: extract durable facts into semantic memory."""

def session_preload(agent_name: str, max_memories: int = 10) -> str:
    """Load prior knowledge into system prompt for new session."""

def enhanced_call_agent(agent_name: str, system_prompt: str, user_prompt: str,
                        use_memory: bool = True, use_rules: bool = True, **kwargs) -> str:
    """Full-stack entry point: memory preload + stream rules + compaction."""
```

---

## Delta Tables

| Table | Purpose |
|-------|---------|
| `mde_dev.test_schema.agent_call_log` | Every LLM call (tokens, cost, latency, status) |
| `mde_dev.test_schema.agent_outputs` | All generated artifacts |
| `mde_dev.test_schema.agent_pipeline_status` | Pipeline execution tracking |
| `mde_dev.test_schema.agent_health_dashboard` | Daily health rollup |
| `mde_dev.test_schema.agent_cost_anomalies` | Billing anomaly detection |
| `mde_dev.test_schema.agent_memory` | Semantic memory per agent (extended Phase 9.1: embeddings, importance, veracity, content_hash) |
| `mde_dev.test_schema.agent_memory_index` | Vector index for semantic recall (embedding + keywords, 1024-dim BGE) |
| `mde_dev.test_schema.agent_stream_rules` | Mid-generation enforcement rules (regex patterns, abort/retry/log actions) |
| `mde_dev.test_schema.agent_events` | Event bus (pub/sub between agents) |
| `mde_dev.test_schema.agent_policies` | Governance policy definitions (Phase 8, 10 active) |
| `mde_dev.test_schema.agent_policy_log` | Policy evaluation audit trail (Phase 8) |
| `mde_dev.test_schema.agent_registry` | Agent catalog (name, layer, status, success_rate) |
| `mde_dev.test_schema.agent_trace_log` | Execution traces (tokens, latency, quality_score) |
| `mde_dev.test_schema.agent_circuit_breaker` | Failure tracking + auto-pause logic |
| `mde_dev.test_schema.idea_seed_library` | External AI idea catalog with NEXUS coverage status, Hologic relevance scoring, and audit columns |
| `mde_dev.test_schema.agent_build_backlog` | LLM-generated agent build proposals from W2 06_agent_proposal_generator, ranked by build_priority for W1 Agent 63 |

---

## Phase 8 — Governance Engine (Built July 1, 2026)

Adopted from [Omnigent](https://github.com/omnigent-ai/omnigent) (Apache 2.0). Five sub-phases in `00_agent_config` (Cells 13-17). Zero breaking changes.

| Sub-Phase | Capability | Key Functions | Cost |
|-----------|------------|---------------|------|
| 8.1 | Policy Table + Engine Core | `evaluate_policies()`, `_safe_eval()`, `policy_check()` | $0 |
| 8.2 | Pre-Execution Gate (inside `call_agent()`) | `_governance_policy_check`, PolicyDeniedError | $0 |
| 8.3 | Cost Budget + Rate Limiting | `get_cost_metrics()`, `get_rate_metrics()`, `check_budget_status()` | ~0.001 DBU/call |
| 8.4 | Risk Score + Cumulative Gating | `get_risk_score()`, `reset_risk_score()`, `_RISK_ACTION_WEIGHTS` | $0 |
| 8.5 | LLM-as-Judge (borderline cases) | `_llm_judge()`, `llm_judge_evaluate()` | ~$5-15/yr |

**Verdict model:** 3-way `ALLOW` / `DENY` / `ASK` — first DENY short-circuits, ASK routes to Supervisor.

**10 active policies:** global_daily_budget ($2), standard_rate_limit (100/day), token_cap (150K), hourly_burst_limit (30/hr), apex_agent_budget ($0.50), apex_rate_limit (20/day), risk_score_ask (≥40), risk_score_deny (≥60).

**Risk scoring:** Action-specific points (0–50) accumulate per session. Thresholds: 0-39=ALLOW, 40-59=ASK, 60+=DENY.

---

## Phase 9 — Agent Intelligence Engine (Built July 1, 2026)

Five additive sub-phases in `00_agent_config` (Cells 18-22). Zero breaking changes.

| Sub-Phase | Capability | Key Functions | Cost |
|-----------|------------|---------------|------|
| 9.1 | Semantic Memory | `remember()`, `recall()`, `reflect()` | ~$5-20/yr (BGE embeddings) |
| 9.2 | Content-Hash Verification | `hash_context()`, `verified_save()` | $0 (pure Python) |
| 9.3 | Auto-Compaction | `compact_context()`, `maybe_compact()` | ~$10-30/yr (summary calls) |
| 9.4 | Stream Rule Enforcement | `check_stream_rules()`, `call_agent_with_rules()` | ~$10-30/yr (retries) |
| 9.5 | Session Consolidation | `consolidate_session()`, `session_preload()` | ~$30-70/yr (extraction) |

**Entry point:** `enhanced_call_agent()` — combines memory preload + stream rules + compaction.

**Dependency chain:** 9.1 first → 9.2/9.3/9.4 parallel → 9.5 last (requires 9.1).

**Stream rules seeded (7):** no_hardcoded_rates, no_drop_production, no_select_star_large, no_pii_exposure, no_flat_rate_assumption, force_delta_format, no_md5_surrogate_keys.

**Embedding:** BGE-large via `databricks-bge-large-en` serving endpoint (1024-dim, with hash fallback).

**Inspired by:** [oh-my-pi](https://github.com/can1357/oh-my-pi) (Apache 2.0) — Mnemopi, Hashline, Snapcompact.

---

## Consultation Network

Specialists are consulted by other agents before making decisions:

| Primary Agent | Consults | For |
|---------------|----------|-----|
| 02 data_engineer | 32, 33, 49-59 | Source-specific patterns before building pipelines |
| 01 job_failure_triage | 44, 47, 49-52 | Domain knowledge for failure root cause |
| 37 data_modeler | 32, 33, 49, 52 | Business keys, SCD types for source systems |
| 06 solution_architect | All specialists | Integration patterns for HLD/LLD |
| 16 data_quality | 56_hcp, 33_sfdc | Domain-specific validation rules |

---

## Environment Notes

- **AI Builder Workspace** (4337650355687191): READ-ONLY access to `mde_dev`
- **DEV Workspace** (6617965257274108): Full read/write access
- **Databricks Apps blocked:** IP ACL prevents outbound calls from Apps to workspace API
- **Interactive interface:** Use `CHAT_Interactive_Supervisor` (LLM-only, no network restrictions)

---

## Cost Model

| Component | Rate | Monthly Est. |
|-----------|------|--------------|
| Foundation Model API | ~$0.003-$0.05/call | $25-40 |
| Serverless Jobs | $0.45/DBU | ~$5 |
| Delta Storage | Minimal | ~$1 |
| Phase 8 Governance (LLM Judge) | ~$0.003-0.01/uncertain call | ~$1 |
| Phase 9 Intelligence (embeddings, summaries) | ~$5-12/mo | ~$5-12 |
| **Total** | | **~$35-60/month** |

---

*Last updated: July 1, 2026 (Agent count updated to 133 — added W2 Agent 06 `agent_proposal_generator`, `agent_build_backlog`, and `agent_registry` seeded from AGENTS.md)*
