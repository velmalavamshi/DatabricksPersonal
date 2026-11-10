# NEXUS Update Checklist

> **Purpose:** Every time a new agent, skill, tool, or feature is added/modified in NEXUS, use this checklist to ensure ALL dependent components stay in sync.

---

## When Adding a NEW AGENT

- [ ] Create agent notebook in correct workspace folder (W0–W4) using 7-cell template
- [ ] Register in `00_agent_config` Cell 3 — `AGENT_REGISTRY` dict (name, layer, type, model tier, priority)
- [ ] Add to `00_supervisor_agent` routing logic — `AGENT_ROUTING` map + intent keywords
- [ ] Update `CHAT_Interactive_Supervisor` Cell 5 — `AGENT_REGISTRY` domains list + system prompt agent inventory
- [ ] Update `CHAT_Interactive_Supervisor` Cell 2 — `SUPERVISOR_PROMPT_FOR_PLAYGROUND` agent list
- [ ] Update `AGENTS.md` — Agent Inventory table (ID, name, purpose, notebook ID)
- [ ] Update `.assistant_instructions.md` — Agent Memories → agent count + any new details
- [ ] Update Databricks App `app.py` — agent routing sidebar + system prompt (if app is active)
- [ ] Add agent to `mde_dev.test_schema.agent_registry` Delta table (when created from DEV workspace)
- [ ] If specialist: add to Consultation Network table in `AGENTS.md`
- [ ] If platform specialist (64–75): verify `call_agent()` model tier mapping
- [ ] If APEX agent: add to `_AGENT_DEFAULT_RISK` in Cell 16 with appropriate risk weight
- [ ] If high-risk agent: consider adding agent-specific policy (e.g., `apex_agent_budget`, `apex_rate_limit`)
- [ ] Run smoke test — send a request that should route to the new agent

---

## When MODIFYING an Existing Agent

- [ ] Update agent notebook (preserve 7-cell structure)
- [ ] If domain/routing keywords changed → update `00_supervisor_agent` routing
- [ ] If domain keywords changed → update `CHAT_Interactive_Supervisor` Cell 5 domains
- [ ] If agent name/purpose changed → update `AGENTS.md`
- [ ] If model tier changed → update `00_agent_config` tier mapping
- [ ] If input/output contract changed → notify downstream agents in pipeline chain
- [ ] Update `agent_registry` Delta table status/metadata

---

## When Adding a NEW SKILL (context injection)

- [ ] Create `.md` skill file(s) in `/skills/<skill_name>/`
- [ ] Register in `CHAT_Interactive_Supervisor` Cell 5 — `SKILL_REGISTRY` dict
- [ ] Update `CHAT_Interactive_Supervisor` Cell 2 — Playground prompt skills section
- [ ] Update `AGENTS.md` — Skills table
- [ ] If injected by supervisor: update `00_supervisor_agent` skill-loading logic

---

## When Adding a NEW TOOL (deterministic, no LLM)

- [ ] Create tool function in appropriate notebook or shared module
- [ ] Register in `00_agent_config` — `TOOL_REGISTRY` if applicable
- [ ] Update `00_supervisor_agent` tool dispatch logic
- [ ] Update `CHAT_Interactive_Supervisor` system prompt — Tools section
- [ ] Update `AGENTS.md` — Tools table

---

## When Changing the SYSTEM PROMPT

- [ ] Update `CHAT_Interactive_Supervisor` Cell 5 — `SUPERVISOR_PROMPT` variable
- [ ] Update `CHAT_Interactive_Supervisor` Cell 2 — `SUPERVISOR_PROMPT_FOR_PLAYGROUND` (keep in sync)
- [ ] Update Databricks App `app.py` system prompt (if app is active)
- [ ] Update `GENIE_CODE_PROMPT` master context (if applicable)
- [ ] Verify response format instructions are consistent across all copies

---

## When Changing CONFIG (`00_agent_config`)

- [ ] Verify all agents using `%run ./00_agent_config` still work
- [ ] If `call_agent()` signature changed → update all agent notebooks
- [ ] If new shared utility added → document in `AGENTS.md` API Reference
- [ ] If model endpoint name changed → update all tier references
- [ ] If Delta table schema changed → update downstream readers
- [ ] If governance cells (13–17) modified → run `_load_policies(force_refresh=True)` and verify
- [ ] If `log_agent_call()` schema changed → verify `risk_points` column still INT-compatible
- [ ] If `evaluate_policies()` context enriched → test all expression-based policies still eval correctly
- [ ] If Phase 9 cells (18–22) modified → run all 5 cells sequentially and verify print output
- [ ] Test from AI Builder workspace (read-only access to `mde_dev`)

---

## When Changing GOVERNANCE POLICIES (Phase 8)

- [ ] Edit policies via MERGE INTO `mde_dev.test_schema.agent_policies` (idempotent)
- [ ] After insert/update: call `_load_policies(force_refresh=True)` to refresh session cache
- [ ] If adding a new policy: assign unique `policy_id` (UUID), set `priority` (lower = first), set `is_active = true`
- [ ] If changing thresholds: verify against current usage (`check_budget_status()`, `get_risk_score()`)
- [ ] If adding new eval context variable: update `evaluate_policies()` SQL in Cell 13
- [ ] If adding agent-specific policy: use scope `agent:<agent_name>` (must match AGENT_REGISTRY key)
- [ ] If changing risk weights: update `_RISK_ACTION_WEIGHTS` or `_AGENT_DEFAULT_RISK` in Cell 16
- [ ] If changing risk thresholds (40 ASK / 60 DENY): update `risk_score_ask` + `risk_score_deny` policy parameters
- [ ] If LLM Judge prompt changed: update `_JUDGE_SYSTEM_PROMPT` in Cell 17
- [ ] Verify `PHASE_8_GOVERNANCE_OMNIGENT.md` policy table matches reality
- [ ] Run verification: `policy_check("<agent_name>", "llm_call")` should return expected verdict
- [ ] Check `agent_policy_log` to confirm evaluations are being audited

### Governance Quick Reference

| Cell | Component | Contains |
|------|-----------|----------|
| 4 | `call_agent()` | Governance gate via `globals().get('_governance_policy_check')` |
| 5 | `log_agent_call()` | `risk_points: int = 0` parameter (Phase 8.4) |
| 6 | Delta table DDL | `agent_policies` + `agent_policy_log` CREATE IF NOT EXISTS |
| 13 | Policy Engine Core | `evaluate_policies()`, `_safe_eval()`, `policy_check()`, `_governance_policy_check` |
| 14 | Seed Policies | 4 base policies via MERGE (idempotent) |
| 15 | Cost/Rate Functions | `get_cost_metrics()`, `get_rate_metrics()`, `check_budget_status()` + 4 additional policies |
| 16 | Risk Accumulator | `_RISK_ACTION_WEIGHTS`, `_AGENT_DEFAULT_RISK`, `get_risk_score()`, `reset_risk_score()` + 2 risk policies |
| 17 | LLM-as-Judge | `_llm_judge()`, `llm_judge_evaluate()`, `_governance_llm_judge` |
| 18 | Phase 9.1 | Semantic Memory: `remember()`, `recall()`, `reflect()`, schema extensions |
| 19 | Phase 9.2 | Content-Hash: `hash_context()`, `verified_save()`, `context_aware_call()` |
| 20 | Phase 9.3 | Auto-Compaction: `compact_context()`, `maybe_compact()`, `is_protected()` |
| 21 | Phase 9.4 | Stream Rules: `check_stream_rules()`, `call_agent_with_rules()`, seed rules |
| 22 | Phase 9.5 | Session Consolidation: `consolidate_session()`, `session_preload()`, `enhanced_call_agent()` |

### Active Policies (10 total, ordered by priority)

| Pri | Policy | Scope | Expression |
|-----|--------|-------|------------|
| 3 | `risk_score_deny` | global | `cumulative_risk >= 60` |
| 4 | `risk_score_ask` | global | `cumulative_risk >= 40` |
| 5 | `hourly_burst_limit` | global | `calls_last_hour > 30` |
| 10 | `global_daily_budget` | global | `session_cost_usd > $2.00` |
| 12 | `apex_agent_budget` | agent:solution_architect, agent:data_modeler | `agent_cost_usd > $0.50` |
| 15 | `apex_rate_limit` | agent:solution_architect, agent:peer_review | `calls_today > 20` |
| 20 | `standard_rate_limit` | global | `calls_today > 100` |
| 30 | `token_cap` | global | `session_tokens > 150,000` |

---

## When Changing PHASE 9 (Agent Intelligence Engine)

- [ ] If `remember()` / `recall()` logic changed → verify dedup still works (`content_hash` match)
- [ ] If embedding model changed → update `_EMBEDDING_DIM_BGE` constant (currently 1024) + clear `agent_memory_index`
- [ ] If `agent_memory` schema extended → use idempotent ALTER (try/except pattern in Cell 18)
- [ ] If `agent_memory_index` schema changed → DROP + recreate (index is denormalized, rebuildable)
- [ ] If stream rules added/modified → MERGE into `agent_stream_rules` (idempotent, match on `rule_name`)
- [ ] After rule changes: set `_stream_rules_cache = None` to force reload
- [ ] If compaction thresholds changed → update `_COMPACTION_THRESHOLD` and `_CONTEXT_WINDOWS` in Cell 20
- [ ] If `is_protected()` logic changed → verify Phase 8 `[POLICY INJECTION]` tags still survive compaction
- [ ] If `consolidate_session()` extraction prompt changed → test JSON parsing still works
- [ ] If switching from BGE to hash embeddings → update `_EMBEDDING_MODE` in Cell 18
- [ ] Run all 5 Phase 9 cells sequentially (18→22) after ANY change — they have cross-dependencies
- [ ] Verify orphan check: `SELECT ... FROM agent_memory LEFT JOIN agent_memory_index WHERE index IS NULL`
- [ ] Update `AGENTS.md` Phase 9 section if capabilities/costs changed
- [ ] Update `PHASE_9_AGENT_INTELLIGENCE_OMP.md` implementation checklist

### Phase 9 Quick Reference

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `agent_memory` | Primary memory store (extended) | content_hash, content_embedding, importance, veracity, memory_source |
| `agent_memory_index` | Vector index for semantic recall | embedding (1024-dim BGE), keywords, bank |
| `agent_stream_rules` | Mid-generation enforcement | pattern (regex), injection, action, scope, priority |

### Stream Rules (7 seeded, ordered by priority)

| Pri | Rule | Action | Scope |
|-----|------|--------|-------|
| 1 | `no_pii_exposure` | abort_retry | global |
| 5 | `no_drop_production` | abort_retry | global |
| 8 | `no_md5_surrogate_keys` | abort_retry | global |
| 10 | `no_hardcoded_rates` | abort_retry | global |
| 10 | `no_flat_rate_assumption` | abort_retry | agent:cost_optimizer |
| 20 | `force_delta_format` | warn_continue | global |
| 30 | `no_select_star_large` | warn_continue | global |

### Known Issues / Lessons Learned (Phase 9)

- **Embedding dim:** BGE-large returns 1024-dim (NOT 384 as omp doc assumed). Constant `_EMBEDDING_DIM_BGE` updated.
- **Orphan risk:** If `agent_memory` write succeeds but `agent_memory_index` write fails (type mismatch, network), orphaned rows result. Fix: `remember()` wraps index write in try/except with rollback DELETE.
- **ALTER TABLE noise:** Idempotent ALTER loop produces verbose GRPC `FIELD_ALREADY_EXISTS` errors in logs (caught correctly, but noisy). Acceptable — not a bug.
- **Schema inference:** Always use explicit `StructType` schemas when calling `spark.createDataFrame()` with NULL-able TIMESTAMP or ARRAY<FLOAT> columns. Spark Connect cannot infer types from None values.
- **ARRAY<FLOAT> vs ARRAY<DOUBLE>:** Python float lists infer as ARRAY<DOUBLE>. Delta table expects ARRAY<FLOAT>. Must cast via explicit schema OR `[float(x) for x in embedding]` + FloatType schema.

---

## When Changing the DATABRICKS APP (v3 Architecture)

> **App:** `hologic-ai-agents-v3` (FastAPI + vanilla JS frontend, build-free)  
> **Source:** `/5 - AI Multi Agents/5 - Agent Chat App - V3/`  
> **Backup:** `/5 - AI Multi Agents/5 - Agent Chat App - V3-backup/`  
> **Phase 13 doc:** `PHASE_13_V3_FRONTEND_REDESIGN.md`

### Backend Changes
- [ ] If new endpoint: add to appropriate router (`routers/chat.py`, `sessions.py`, `misc.py`, `enhancements.py`)
- [ ] If new router file: register in `main.py` (`app.include_router()`)
- [ ] If new dependency: add to `requirements.txt`
- [ ] If new env var: add to `app.yaml` env section
- [ ] If auth/token logic changed: verify `auth.py` refresh middleware still works
- [ ] If system prompt changed: update `chat_engine.py` `SUPERVISOR_PROMPT` (verbatim copy rule)
- [ ] If agent registry changed: update `config.py` `AGENT_REGISTRY` dict
- [ ] Verify SP permissions (CAN_QUERY on serving endpoints)

### Frontend Changes
- [ ] If UI component changed: edit `static/app.js` (single file, clearly sectioned)
- [ ] If styling changed: edit `static/styles.css` (design tokens at top)
- [ ] If new CSS component needed: append to end of `styles.css`
- [ ] Never modify `static/assets/index-*.js` or `index-*.css` (dead files from old React bundle)
- [ ] Test dark mode (Ctrl+D toggle) after style changes
- [ ] Test mobile layout (hamburger menu, slide-out rail)

### Deployment
- [ ] Run `databricks apps get hologic-ai-agents-v3` to check current state
- [ ] Only deploy when status=RUNNING and no pending_deployment
- [ ] Deploy: `databricks apps deploy hologic-ai-agents-v3 --source-code-path "/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/5 - Agent Chat App - V3"`
- [ ] Verify deployment succeeded: check `app_status.state = RUNNING`
- [ ] Test LLM calls work (check for 401/token issues — auth.py auto-refreshes every 20min)

### Rollback
- [ ] Deploy from backup: `--source-code-path "...V3-backup"`
- [ ] Or restore individual files from backup directory

### Documentation
- [ ] Update `PHASE_13_V3_FRONTEND_REDESIGN.md` if new endpoints/features added
- [ ] Update `.assistant_instructions.md` app details if status/config changed
- [ ] Update `PHASE_12_APP_CAPABILITIES.md` track status if Track 1-9 items implemented

### API Endpoint Inventory (28 total as of Phase 13)

| Router | Endpoints | Purpose |
|--------|-----------|--------|
| `chat.py` | POST /api/chat | SSE streaming chat |
| `sessions.py` | 13 endpoints | Session CRUD, projects, routines, export, sharing |
| `misc.py` | 6 endpoints | Health, identity, agents, images, feedback |
| `enhancements.py` | 14 endpoints | Templates, skills, preferences, notifications, search, audit, shortcuts, app info |

---

## When Adding a NEW WORKSPACE FOLDER (W5+)

- [ ] Create folder under `/5 - AI Multi Agents/`
- [ ] Add to `CHAT_Interactive_Supervisor` Cell 5 — `ALL_REGISTRY`
- [ ] Add to `00_supervisor_agent` workspace routing
- [ ] Update `AGENTS.md` — Workspace Structure table
- [ ] Update `.assistant_instructions.md` — workspace list
- [ ] Update system prompts (both notebook and Playground versions)

---

## When Changing LLM MODELS

- [ ] Update `00_agent_config` — `LLM_APEX`, `LLM_CRITICAL`, `LLM_STANDARD` constants
- [ ] Update `CHAT_Interactive_Supervisor` Cell 5 — `MODEL` variable
- [ ] Update `AGENTS.md` — Quick Reference + LLM Configuration tables
- [ ] Update `.assistant_instructions.md` — LLM tier references
- [ ] Update Databricks App resource permissions in `app.yaml`
- [ ] Verify `call_agent()` handles new model's parameter support (e.g., Opus skips temperature)
- [ ] Verify LLM Judge in Cell 17 uses appropriate model for classification

---

## When Changing DELTA INFRASTRUCTURE TABLES

- [ ] Update schema in DEV workspace (6617965257274108) — AI Builder is read-only
- [ ] Update `AGENTS.md` — Delta Tables section
- [ ] Update any agents that read/write the changed table
- [ ] If `agent_call_log` schema changed → update monitoring tools (05, 30) + `log_agent_call()` in Cell 5
- [ ] If `agent_call_log.risk_points` changed → update Cell 13 context builder + Cell 16 risk functions
- [ ] If `agent_policies` schema changed → update Cell 13 `_load_policies()` query + Cell 14/15/16 seed logic
- [ ] If `agent_policy_log` schema changed → update Cell 13 `_log_policy_eval()` function
- [ ] If `agent_events` schema changed → update event bus publishers/subscribers
- [ ] If `agent_memory` extended → verify backward compat (new cols must be nullable)
- [ ] If `agent_memory_index` rebuilt → re-run orphan backfill query
- [ ] If `agent_stream_rules` modified → set `_stream_rules_cache = None` in session

---

## When Updating DOCUMENTATION

- [ ] Keep `AGENTS.md` as single source of truth for architecture
- [ ] Keep `.assistant_instructions.md` as single source of truth for AI assistant context
- [ ] Keep `PHASE_8_GOVERNANCE_OMNIGENT.md` as Phase 8 architecture reference
- [ ] Keep `PHASE_9_AGENT_INTELLIGENCE_OMP.md` as Phase 9 architecture reference
- [ ] Keep this `CHECKLIST.md` updated when new component types are introduced
- [ ] Increment "Last updated" in `AGENTS.md` footer

---

## Quick Sync Verification

After any update, verify these are consistent:

| Component | Location | What to Check |
|-----------|----------|---------------|
| Agent count | `AGENTS.md`, `.assistant_instructions.md`, system prompts | All say same number |
| Agent list | `AGENT_REGISTRY` (config), supervisor routing, CHAT Cell 5 | Same agents registered |
| Model names | `00_agent_config`, CHAT Cell 5, App `app.py` | Same endpoint names |
| Workspace structure | Folder tree, `AGENTS.md`, system prompts | Same W0–W4 descriptions |
| Domain keywords | Supervisor routing, CHAT Cell 5 domains | No orphaned keywords |
| Policy count | Cell 14/15/16 seeds, `agent_policies` table, Phase 8 doc | All say 10 active |
| Risk weights | Cell 16 `_AGENT_DEFAULT_RISK`, Phase 8 doc | Same agent → points mapping |
| Governance thresholds | Cell 16 policies, `check_budget_status()`, Phase 8 doc | ASK=40, DENY=60, budget=$2 |
| Stream rules | Cell 21 `_SEED_STREAM_RULES`, `agent_stream_rules` table, CHECKLIST | All say 7 rules |
| Embedding dim | Cell 18 `_EMBEDDING_DIM_BGE`, `AGENTS.md` Phase 9 section | Both say 1024 |
| Phase 9 functions | Cell 18–22, `AGENTS.md` API Reference | Same function signatures |

---

*Last updated: July 1, 2026 — Added Phase 9 Agent Intelligence Engine section + lessons learned*
