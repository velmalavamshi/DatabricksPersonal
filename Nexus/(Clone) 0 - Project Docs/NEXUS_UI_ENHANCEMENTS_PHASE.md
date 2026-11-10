# NEXUS Platform — Complete Phase & Enhancement Log

> **Project:** NEXUS Multi-Agent AI Platform  
> **Author:** sameet.patel@hologic.com  
> **Root Path:** `/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/`  
> **Last Updated:** July 1, 2026  
> **Total Agents:** 131 (122 built + 9 planned)  
> **Architecture:** Hierarchical hub-and-spoke + event bus (pure Databricks-native)

---

## Platform Timeline

| Date | Milestone | Impact |
|------|-----------|--------|
| Q1 2026 | Phase 1–3: Foundation, Agent Framework, Delta State | Core `00_agent_config`, `call_agent()`, Delta tables, MLflow tracing |
| Q1 2026 | Phase 4: Meta Orchestrator (W0) | Intent classification + routing, Supervisor hierarchy |
| Q1 2026 | Phase 5: Token Optimization (Safe Tier) | 3-layer cache, ~60-70% token reduction on catalog scans |
| Q2 2026 | Phase 6: Production Agents (W1) | 38+ initial agents, 7-cell template standard |
| June 8, 2026 | Phase 7: Collective Intelligence (W4) | Pattern learning, benchmarks, predictions |
| June 15, 2026 | Platform Specialist Agents (64–75) | 11 Databricks-native specialists (SDP, SQL WH, UC, MLflow, etc.) |
| June 16, 2026 | Release Intelligence Layer (77–87) | 11 vendor release monitors + weekly orchestrator |
| June 16, 2026 | App UI Enhancement Phase (v2.2) | Bubbles, timestamps, security, feedback, Release Intel routing |
| June 2026 | Qlik Migration Layer (88–95) | 8 agents: QVD, script, data model, expression, UI, RLS, NPrinting |
| June 2026 | Consultation Network (60–62) | Cross-domain agent-to-agent consultation routing |
| July 1, 2026 | **Phase 8: Governance Engine** | 5 sub-phases, 10 active policies, 3-way ALLOW/DENY/ASK gating |
| July 1, 2026 | **Phase 9: Agent Intelligence Engine** | 5 sub-phases, semantic memory, stream rules, compaction |

---

## Phase 8: Governance Engine (Omnigent Policy Model)

> **Status:** ✅ COMPLETE (July 1, 2026)  
> **Source:** [github.com/omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) (Apache 2.0)  
> **Location:** `00_agent_config` Cells 13–17  
> **Breaking changes:** NONE  
> **Annual cost:** ~$5-15/year (LLM Judge calls only)  
> **Effort:** 9-14 hours total  
> **Reference doc:** `0 - All files/PHASE_8_GOVERNANCE_OMNIGENT.md`

### What Was Built

Proactive pre-execution gating replacing the originally planned reactive circuit breaker. Policy gate lives INSIDE `call_agent()` — all 131 agents get governance for free without code changes.

### Sub-Phases

| Sub-Phase | Cell | Capability | Key Functions |
|-----------|------|------------|---------------|
| 8.1 | 6, 13 | Policy Table + Engine Core | `evaluate_policies()`, `_safe_eval()`, `policy_check()` |
| 8.2 | 4 | Pre-Execution Gate (inside `call_agent()`) | `_governance_policy_check`, PolicyDeniedError |
| 8.3 | 15 | Cost Budget + Rate Limiting | `get_cost_metrics()`, `get_rate_metrics()`, `check_budget_status()` |
| 8.4 | 16 | Risk Score + Cumulative Gating | `get_risk_score()`, `reset_risk_score()`, `_RISK_ACTION_WEIGHTS` |
| 8.5 | 17 | LLM-as-Judge (borderline cases) | `_llm_judge()`, `llm_judge_evaluate()` |

### Active Policies (10 total)

| Pri | Policy | Scope | Threshold |
|-----|--------|-------|-----------|
| 3 | `risk_score_deny` | global | cumulative_risk ≥ 60 → DENY |
| 4 | `risk_score_ask` | global | cumulative_risk ≥ 40 → ASK |
| 5 | `hourly_burst_limit` | global | calls_last_hour > 30 |
| 10 | `global_daily_budget` | global | session_cost_usd > $2.00 |
| 12 | `apex_agent_budget` | agent:solution_architect, agent:data_modeler | agent_cost > $0.50 |
| 15 | `apex_rate_limit` | agent:solution_architect, agent:peer_review | calls_today > 20 |
| 20 | `standard_rate_limit` | global | calls_today > 100 |
| 30 | `token_cap` | global | session_tokens > 150,000 |

### Risk Score Model

| Action | Points | Threshold Behavior |
|--------|--------|--------------------|
| Read catalog metadata | 0 | 0-39: ALLOW |
| Generate SQL SELECT | +5 | 40-59: ASK (Supervisor approval) |
| Generate DDL (CREATE/ALTER) | +15 | 60+: DENY (block + alert) |
| Generate DML (INSERT/UPDATE/MERGE) | +20 | |
| Propose DROP TABLE/VIEW | +50 | |
| Write to production (gold/platinum) | +30 | |
| Call external API (ADO, ServiceNow) | +20 | |
| Modify Workflow/Job configuration | +25 | |

### Delta Tables Added

| Table | Purpose |
|-------|---------|
| `mde_dev.test_schema.agent_policies` | Policy definitions (scope, phase, expression, parameters) |
| `mde_dev.test_schema.agent_policy_log` | Audit trail (timestamp, verdict, reason, context) |

---

## Phase 9: Agent Intelligence Engine (oh-my-pi Pattern)

> **Status:** ✅ COMPLETE (July 1, 2026)  
> **Source:** [github.com/can1357/oh-my-pi](https://github.com/can1357/oh-my-pi) (Apache 2.0, v16.x)  
> **Location:** `00_agent_config` Cells 18–22  
> **Breaking changes:** NONE  
> **Annual cost:** ~$55-150/year (net neutral after savings)  
> **Effort:** 13-18 hours total  
> **Reference doc:** `0 - All files/PHASE_9_AGENT_INTELLIGENCE_OMP.md`

### What Was Built

Four precision primitives upgrading NEXUS from basic key-value memory to semantic recall, content-verified outputs, automatic context compaction, and mid-generation enforcement.

| Before Phase 9 | After Phase 9 |
|----------------|---------------|
| Exact-key memory lookup | Semantic similarity search (embedding + BM25 hybrid) |
| Manual 3-layer token cache | Auto-compaction preserving injected corrections |
| No output integrity | Content-hash verification before Delta write |
| Pre/post execution only (Phase 8) | Mid-generation stream rules (abort + retry) |
| Session knowledge dies with session | Auto-consolidation → semantic recall across sessions |

### Sub-Phases

| Sub-Phase | Cell | Capability | Key Functions | Cost |
|-----------|------|------------|---------------|------|
| 9.1 | 18 | Semantic Memory | `remember()`, `recall()`, `reflect()` | ~$5-20/yr (BGE embeddings) |
| 9.2 | 19 | Content-Hash Verification | `hash_context()`, `verified_save()`, `context_aware_call()` | $0 (pure Python) |
| 9.3 | 20 | Auto-Compaction | `compact_context()`, `maybe_compact()` | ~$10-30/yr (summary calls) |
| 9.4 | 21 | Stream Rule Enforcement | `check_stream_rules()`, `call_agent_with_rules()` | ~$10-30/yr (retry calls) |
| 9.5 | 22 | Session Consolidation | `consolidate_session()`, `session_preload()`, `enhanced_call_agent()` | ~$30-70/yr (extraction) |

### Semantic Memory (9.1)

* **Embedding model:** `databricks-bge-large-en` (1024-dim)
* **Hybrid retrieval:** Cosine similarity (embedding) + keyword boost (BM25-style)
* **Dedup:** xxHash64 content_hash prevents duplicate memories
* **Memory banks:** project | global | session (per-agent scoped)
* **Fallback:** Hash embedding (zero-cost, deterministic pseudo-embedding via n-gram hashing)

### Stream Rules (9.4) — 7 Seeded Rules

| Pri | Rule | Action | Scope |
|-----|------|--------|-------|
| 1 | `no_pii_exposure` | abort_retry | global |
| 5 | `no_drop_production` | abort_retry | global |
| 8 | `no_md5_surrogate_keys` | abort_retry | global |
| 10 | `no_hardcoded_rates` | abort_retry | global |
| 10 | `no_flat_rate_assumption` | abort_retry | agent:cost_optimizer |
| 20 | `force_delta_format` | warn_continue | global |
| 30 | `no_select_star_large` | warn_continue | global |

### Auto-Compaction Protected Zones (9.3)

| Content Type | Compaction Rule |
|-------------|----------------|
| System prompt | NEVER compress |
| Phase 8 `[POLICY INJECTION]` tags | NEVER compress |
| User corrections | NEVER compress |
| Most recent 2 turns | NEVER compress |
| DDL/JSON schemas | NEVER compress |
| Older turns (3+ back) | Summarize to 1-2 sentences |
| Tool outputs (raw SQL results) | Extract key metrics only |
| Error traces | Keep root cause line only |

### Full-Stack Entry Point

```python
enhanced_call_agent(agent_name, system_prompt, user_prompt,
                    use_memory=True, use_rules=True, **kwargs)
# = memory preload + stream rules + compaction (opt-in)
```

### Delta Tables Added

| Table | Purpose |
|-------|---------|
| `mde_dev.test_schema.agent_memory` | Semantic memory per agent (extended: embeddings, importance, veracity, content_hash) |
| `mde_dev.test_schema.agent_memory_index` | Vector index for semantic recall (1024-dim BGE, keywords, bank) |
| `mde_dev.test_schema.agent_stream_rules` | Mid-generation enforcement (regex patterns, abort/retry/log) |

### Lessons Learned (Phase 9 Build)

* **BGE embedding = 1024-dim** (NOT 384 as omp docs suggested)
* **Explicit StructType required** for ARRAY<FLOAT> and nullable TIMESTAMP columns — Spark Connect cannot infer from None
* **ARRAY<FLOAT> vs ARRAY<DOUBLE>:** Python floats infer as DOUBLE; must cast explicitly
* **Orphan protection:** remember() wraps index write in try/except with rollback DELETE
* **ALTER TABLE noise:** Idempotent ALTER loop produces GRPC `FIELD_ALREADY_EXISTS` errors (cosmetic, not functional)

---

## Platform Specialist Agents (64–75)

> **Status:** ✅ COMPLETE (June 15, 2026)  
> **Location:** W1 (`1 - Production Agents/`)  
> **Count:** 11 agents

| ID | Agent | Domain | Notebook ID |
|----|-------|--------|-------------|
| 64 | sdp_agent | Spark Declarative Pipelines | 350235908256380 |
| 65 | sql_warehouse_agent | SQL Warehouse right-sizing | 350235908256385 |
| 66 | unity_catalog_agent | UC governance, RBAC, ABAC | 350235908256386 |
| 67 | mlflow_model_serving_agent | MLflow + Model Serving | 350235908256387 |
| 68 | ai_bi_dashboard_agent | Lakeview dashboards | 350235908256388 |
| 69 | cluster_management_agent | Cluster policies, sizing | 350235908256389 |
| 70 | vector_search_agent | Vector Search, RAG | 350235908256390 |
| 71 | notebook_lifecycle_agent | Notebook management | 350235908256391 |
| 73 | databricks_app_agent | Databricks Apps | 350235908256392 |
| 74 | genie_space_agent | Genie spaces | 350235908256393 |
| 75 | ai_gateway_agent | AI Gateway config | 350235908256394 |

**Design decision:** Each platform specialist provides deep expertise in one Databricks service. They are invoked via Consultation Network routing or direct supervisor dispatch when a request requires service-specific knowledge beyond the generalist engineers.

---

## Release Intelligence Layer (77–87)

> **Status:** ✅ COMPLETE (June 16, 2026)  
> **Location:** W1 (`1 - Production Agents/`)  
> **Count:** 11 agents  
> **Schedule:** Weekly Monday 7AM ET via Agent 77 orchestrator

| ID | Agent | Monitors | Notebook ID |
|----|-------|----------|-------------|
| 77 | release_intelligence_agent | Orchestrator — weekly consolidated report | 1025795174227706 |
| 78 | oracle_release_monitor_agent | Oracle EBS patches, CPUs, desupport (1,263 tables) | 1025795174227707 |
| 79 | salesforce_release_monitor_agent | SFDC seasonal releases, API deprecations (768 tables) | 1025795174227708 |
| 80 | powerbi_release_monitor_agent | Power BI monthly updates, Fabric | 1025795174227709 |
| 81 | databricks_release_monitor_agent | Runtime EOL, API deprecation, UC, model retirement | 1025795174227710 |
| 82 | azure_platform_release_monitor_agent | Azure service retirements, pricing, Entra ID | 1025795174227711 |
| 83 | mulesoft_release_monitor_agent | Connector deprecations, runtime EOL, CloudHub | 1025795174227712 |
| 84 | delta_spark_oss_release_monitor_agent | Delta protocol, Spark 4.0, MERGE/NULL | 1025795174227713 |
| 85 | azure_devops_release_monitor_agent | Pipeline agent, ADO API, YAML schema | 1025795174227714 |
| 86 | python_ecosystem_release_monitor_agent | pandas 3.x, numpy 2.x, openai, mlflow 3.x | 1025795174227715 |
| 87 | oracle_cloud_release_monitor_agent | PBCS + HCM Cloud quarterly, OCI API | 1025795174227716 |

**Impact scoring:** CRITICAL (48h action) | HIGH (30d) | MEDIUM (evaluate) | LOW (awareness)  
**Integrates with:** Agent 39 (Morning Briefing), Agent 01 (Triage), Agent 04 (Drift)

---

## Qlik Migration Layer (88–95)

> **Status:** ✅ COMPLETE  
> **Location:** W1 (`1 - Production Agents/`)  
> **Count:** 8 agents

| ID | Agent | Purpose | Notebook ID |
|----|-------|---------|-------------|
| 88 | qlik_migration_orchestrator_agent | Inventory, dependency mapping, wave planning | 3084094643406393 |
| 89 | qvd_extraction_agent | QVD schema extraction, data profiling → Delta | 3084094643406394 |
| 90 | qlik_script_conversion_agent | QVS/QVW load scripts → PySpark/SQL | 3084094643406395 |
| 91 | qlik_data_model_agent | Associative model → Kimball star schema | 3084094643406396 |
| 92 | qlik_expression_agent | Set analysis, AGGR() → Databricks SQL | 3084094643406397 |
| 93 | qlik_ui_migration_agent | Charts, KPIs → Lakeview / Power BI | 3084094643406398 |
| 94 | qlik_section_access_agent | Section Access (RLS) → UC row filters, ABAC | 3084094643406399 |
| 95 | qlik_nprinting_agent | NPrinting → Jobs + Lakeview subscriptions | 3084094643406400 |

---

## App UI Enhancement Phase (v2.2)

> **Status:** ✅ COMPLETE (June 16, 2026)  
> **File:** `5 - Agent Chat App/app.py`  
> **Backup:** `app_backup_v2.1_20260616.py` (1,276 lines)

### Changes Summary

| # | Area | Change |
|---|------|--------|
| 1 | CSS | `.nexus-bubble` assistant response container (white card, teal border) |
| 2 | Security | HTML-escape `user_input` before DOM injection |
| 3 | UX | `HH:MM UTC` timestamp on every message bubble |
| 4 | UX | Empty-state suggested prompts (8 quick-launch chips across W1–W4) |
| 5 | Data | Release Intelligence agents 77–87 in `AGENT_REGISTRY` |
| 6 | Data | Release Intelligence intents in `INTENT_AGENT_MAP` (22 keywords) |
| 7 | Data | Agent count corrected: 112 → 123 |
| 8 | UX | Per-message 👍/👎 feedback stored in session state |
| 9 | UX | Collapsible sidebar config (Model/Host/Auth/Persistence) |
| 10 | UX | Token budget warning at ~150K cumulative tokens |
| 11 | CSS | CSS margin replaces per-message `st.divider()` |

---

## Token Optimization (Safe Tier)

> **Status:** ✅ COMPLETE  
> **Location:** `00_agent_config` Cell 8 (via `%run shared_token_optimizer`)  
> **Impact:** ~60-70% token reduction on catalog scans

### Three Layers

| Layer | Mechanism | TTL |
|-------|-----------|-----|
| 1 | `agent_memory` Delta table (cross-session recall) | Permanent |
| 2 | `catalog_context_cache` (schema/table metadata) | 6 hours |
| 3 | `infer_relevant_schemas()` (lazy loading) | Per-session |

**Rules:** NEVER compresses DDL/JSON. Additive to existing `call_agent()` flow.

---

## LLM Configuration (3-Tier)

| Tier | Model | Agents | Rationale |
|------|-------|--------|-----------|
| APEX | `databricks-claude-opus-4-8` | solution_architect (06), peer_review (07), lakehouse_architect (15), data_modeler (37) | 7/7 quality vs Sonnet 6/7 on arch tasks |
| CRITICAL | `databricks-claude-sonnet-4-6` | supervisor (00), data_engineer (02), triage (01), security (17) | Fast + strong on code/triage |
| STANDARD | `databricks-claude-sonnet-4-6` | All remaining agents | Future downgrade candidates |

**Opus caveat:** Does NOT support `temperature` parameter — `call_agent()` auto-skips it.  
**Decision (June 15, 2026):** Open-source models (Qwen 3.5 122B, Llama 4 Maverick) are cheaper but NOT stronger. At ~$30-50/month total, savings don't justify quality risk.

---

## Delta Infrastructure Tables (Complete)

| Table | Purpose | Phase |
|-------|---------|-------|
| `agent_call_log` | Every LLM call (tokens, cost, latency, risk_points) | Foundation |
| `agent_outputs` | All generated artifacts | Foundation |
| `agent_pipeline_status` | Pipeline execution tracking | Foundation |
| `agent_health_dashboard` | Daily health rollup | Foundation |
| `agent_cost_anomalies` | Billing anomaly detection | Foundation |
| `agent_events` | Event bus (pub/sub between agents) | Phase 4 |
| `agent_registry` | Agent catalog (name, layer, status, success_rate) | Phase 4 |
| `agent_trace_log` | Execution traces (tokens, latency, quality_score) | Foundation |
| `agent_circuit_breaker` | Failure tracking + auto-pause logic | Foundation |
| `agent_policies` | Governance policy definitions (10 active) | Phase 8.1 |
| `agent_policy_log` | Policy evaluation audit trail | Phase 8.1 |
| `agent_memory` | Semantic memory per agent (extended: embeddings, importance, veracity) | Phase 9.1 |
| `agent_memory_index` | Vector index for semantic recall (1024-dim BGE) | Phase 9.1 |
| `agent_stream_rules` | Mid-generation enforcement (7 regex rules) | Phase 9.4 |

---

## `00_agent_config` Cell Map

| Cell | Component | Phase |
|------|-----------|-------|
| 3 | `AGENT_REGISTRY`, LLM config | Foundation |
| 4 | `call_agent()`, MLflow tracing, governance gate | Foundation + 8.2 |
| 5 | `log_agent_call()`, `save_agent_output()` | Foundation + 8.4 |
| 6 | Delta table DDL (CREATE IF NOT EXISTS) | Foundation + 8.1 |
| 7 | Utilities | Foundation |
| 8 | `%run shared_token_optimizer` | Phase 5 |
| 9–12 | Cache, catalog, seed, MLflow test | Phase 5 |
| 13 | Policy Engine Core (`evaluate_policies()`, `policy_check()`) | Phase 8.1/8.2 |
| 14 | Seed 4 base governance policies | Phase 8.1 |
| 15 | Cost/Rate Functions (`get_cost_metrics()`, `check_budget_status()`) | Phase 8.3 |
| 16 | Risk Accumulator (`get_risk_score()`, `_RISK_ACTION_WEIGHTS`) | Phase 8.4 |
| 17 | LLM-as-Judge (`_llm_judge()`, `llm_judge_evaluate()`) | Phase 8.5 |
| 18 | Semantic Memory (`remember()`, `recall()`, `reflect()`) | Phase 9.1 |
| 19 | Content-Hash Verification (`hash_context()`, `verified_save()`) | Phase 9.2 |
| 20 | Auto-Compaction (`compact_context()`, `maybe_compact()`) | Phase 9.3 |
| 21 | Stream Rules (`check_stream_rules()`, `call_agent_with_rules()`) | Phase 9.4 |
| 22 | Session Consolidation (`consolidate_session()`, `enhanced_call_agent()`) | Phase 9.5 |

---

## Cost Model (Annual, All Phases Combined)

| Category | Annual Cost |
|----------|-------------|
| Base platform (LLM calls, Jobs compute) | $329-470 |
| Phase 8 Governance (LLM Judge only) | $5-15 |
| Phase 9 Intelligence (embeddings, summaries, retries) | $55-150 |
| Phase 9 savings (fewer retries, less rediscovery) | -$70-150 |
| **Net total** | **~$340-470/year** |

---

## Workspace Structure

| Workspace | Path | Purpose | Agents |
|-----------|------|---------|--------|
| W0 | `0 - Meta Orchestrator/` | Meta Supervisor, intent router, event mesh, governance | 16 |
| W1 | `1 - Production Agents/` | Core engineering, specialists, release intel, Qlik migration | 102 |
| W2 | `2 - Value Discovery/` | Client scanning, use case scoring | 4 |
| W3 | `3 - Business Champions/` | Board-ready business cases, PowerPoint | 4 |
| W4 | `4 - Collective Intelligence/` | Pattern learning, benchmarks, predictions | 4 |

**Total:** 131 agents (122 built + 9 planned source-system specialists: 49-52, 55-59)

---

## Interactive Interfaces

| Interface | Location | Purpose |
|-----------|----------|---------|
| `CHAT_Interactive_Supervisor` | DEV workspace (ID: 1041804398715719) | Notebook-based chat — recommended, works from any workspace |
| `hologic-ai-agents` App | AI Builder workspace (Streamlit) | Deployed Databricks App — independent routing, Jobs API triggers |
| AI Playground | Any workspace | Copy-paste `SUPERVISOR_PROMPT_FOR_PLAYGROUND` into Playground |

---

## Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Pure Databricks-native (no Docker, K8s, Postgres, Redis, React) | Zero external dependencies, full Unity Catalog governance |
| Hub-and-spoke (NOT mesh) | Sparse, defined communication paths — predictable, auditable |
| Policy gate INSIDE `call_agent()` | All agents get governance for free — no per-notebook changes |
| Phase 8 complements Phase 9 | 8 = pre/post gates, 9.4 = mid-generation gates → full lifecycle |
| `mde_dev.test_schema` for all Delta state | Protected from gold/platinum pipeline refreshes |
| AI Builder workspace is read-only to `mde_dev` | Delta writes must happen from DEV workspace (6617965257274108) |
| BGE-large (1024-dim) via AI Gateway | Reuses existing `databricks-bge-large-en` serving endpoint |
| Serverless Jobs Compute ($0.45/DBU) | Lowest cost for scheduled async agent execution |

---

## Documentation Index

| Document | Path | Purpose |
|----------|------|---------|
| `AGENTS.md` | `/5 - AI Multi Agents/AGENTS.md` | Single source of truth — architecture, agent inventory, API reference |
| `CHECKLIST.md` | `/5 - AI Multi Agents/CHECKLIST.md` | Update checklist when adding/modifying agents, policies, or config |
| `PHASE_8_GOVERNANCE_OMNIGENT.md` | `/5 - AI Multi Agents/0 - All files/` | Phase 8 architecture reference (Omnigent patterns) |
| `PHASE_9_AGENT_INTELLIGENCE_OMP.md` | `/5 - AI Multi Agents/0 - All files/` | Phase 9 architecture reference (oh-my-pi patterns) |
| `NEXUS_UI_ENHANCEMENTS_PHASE.md` | `/5 - AI Multi Agents/` | This file — comprehensive platform evolution log |
| `.assistant_instructions.md` | User home | AI assistant session memory (agent counts, costs, lessons) |

---

*Complete platform log — Last updated July 1, 2026*
