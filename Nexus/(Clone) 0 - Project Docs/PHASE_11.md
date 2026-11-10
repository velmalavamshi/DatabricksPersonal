# NEXUS Phase 11 — Pending Items & Build Backlog

> **Status:** Active  
> **Created:** 2026-07-01  
> **Owner:** sameet.patel@hologic.com  
> **Context:** Picks up after Phase 9 (Agent Intelligence Engine) and Phase 10 (W2 idea scanning + agent_registry seeding).

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 | Blocked / Immediate action required |
| 🟡 | In-progress / partially complete |
| 🟢 | Complete |
| ⬜ | Not started |
| ⏭️ | Deferred / batched |

---

## Track A — 05_idea_scanner Completion

| # | Item | Status | Notes |
|---|------|--------|-------|
| A1 | Re-run Cell 5 (STEP 3 — Coverage Cross-Ref) with live 91-agent registry | 🟢 | Cell patched + executed at 2026-07-01T21:51:15Z |
| A2 | Re-run Cell 6 (STEP 4 — LLM Scoring) | 🟢 | Executed at 2026-07-01T21:53:33Z |
| A3 | Re-run Cell 7 (STEP 5 — Persist `idea_seed_library`) | 🟢 | Executed at 2026-07-01T21:53:50Z |
| A4 | Confirm real covered/partial/gap breakdown (target: >0 covered with 91-agent registry) | 🟢 | VERIFIED Aug 11, 2026 — 8 covered, 94 gap, 2 partial (104 total). Target (>0 covered) met. |
| A5 | Validate `mde_dev.test_schema.idea_seed_library` row count + coverage_status distribution | 🟢 | VERIFIED — query run live: covered=8, gap=94, partial=2. Track A is fully complete. |

---

## Track B — W2 Agent 06: `06_agent_proposal_generator`

> **VERIFIED Aug 11, 2026:** The notebook at `2 - Value Discovery/06_agent_proposal_generator` (ID 1405118320738458) is **fully built** — all 8 cells present, all 5 STEPs (widgets, load/filter, LLM generation, enrichment, persist/validate/publish) match the B1/B2 spec below almost exactly (xxhash64 proposal_id, `CLUSTER BY (domain_tag, proposed_workspace, build_priority)`). **It has never been executed** — every cell shows `state: input`, and `mde_dev.test_schema.agent_build_backlog` does not exist yet (`SHOW TABLES` returns 0 rows). The remaining work on Track B is to **run the notebook**, not write more code. AGENTS.md W2 inventory already lists this agent (B3 step 2 done); other B3 steps (SKILL_REGISTRY keywords, SUPERVISOR_PROMPT sections) are unverified.

### B1 — Notebook Build

| # | Item | Status | Notes |
|---|------|--------|-------|
| B1.1 | Create `06_agent_proposal_generator` notebook in `2 - Value Discovery/` | 🟢 | DONE — 8-cell notebook exists (ID 1405118320738458) |
| B1.2 | Cell 1 — Markdown header (purpose, I/O, pipeline position) | 🟢 | DONE — matches spec |
| B1.3 | Cell 2 — `%run ./00_vd_config` | 🟢 | DONE |
| B1.4 | Cell 3 — STEP 1: Widgets (`top_n`, `min_composite_score`, `domain_filter`, `force_refresh`) | 🟢 | DONE — widgets present, incl. domain dropdown w/ 10 choices |
| B1.5 | Cell 4 — STEP 2: Read top-scored gap/partial ideas from `idea_seed_library` | 🟢 | DONE — filters `coverage_status IN ('gap','partial')`, orders by `composite_score DESC` |
| B1.6 | Cell 5 — STEP 3: LLM proposal generation (batch per idea, `databricks-claude-sonnet-4-6`) | 🟢 | DONE — batched (BATCH_SIZE=5) |
| B1.7 | Cell 6 — STEP 4: Validate + enrich proposals (deduplicate, assign proposal_id via `xxhash64`) | 🟢 | DONE |
| B1.8 | Cell 7 — STEP 5: Persist to `mde_dev.test_schema.agent_build_backlog` | 🟢 | DONE (code) / 🔴 NOT YET RUN — table does not exist in the catalog yet |

### B2 — `agent_build_backlog` Schema Design

```sql
CREATE OR REPLACE TABLE mde_dev.test_schema.agent_build_backlog
USING DELTA
AS SELECT
  xxhash64(CONCAT_WS('|', idea_id, run_id))        AS proposal_id,
  idea_id,
  idea_name,
  proposed_agent_name,
  proposed_agent_key,
  domain_tag,
  coverage_status,
  composite_score,
  hologic_relevance_score,
  complexity_score,
  -- LLM-generated fields
  agent_purpose,
  input_spec,
  output_spec,
  tech_stack,
  effort_days_estimate,
  priority,                  -- CRITICAL / HIGH / MEDIUM / LOW
  rationale,
  -- Audit
  run_id,
  etl_load_datetime,
  etl_source_system,
  etl_batch_id
FROM proposals_view;
```

**Liquid Clustering:** `CLUSTER BY (domain_tag, priority)`

### B3 — Agent Creation Checklist for Agent 06

| Step | Action | Target | Status |
|------|--------|--------|--------|
| 1 | Create notebook in `2 - Value Discovery/` | `06_agent_proposal_generator` | ⬜ |
| 2 | Add to AGENTS.md W2 inventory | AGENTS.md | ⬜ |
| 3 | Update total agent count `132 → 133` | AGENTS.md Quick Reference | 🟢 | AGENTS.md now shows 134 total (superseded this count) |
| 4 | Add domain keywords to `SKILL_REGISTRY["W2"]` | `CHAT_Interactive_Supervisor` Cell 6 | ⬜ |
| 5 | Add agent section to `SUPERVISOR_PROMPT` | `CHAT_Interactive_Supervisor` Cell 6 | ⬜ |
| 6 | Add agent section to `SUPERVISOR_PROMPT_FOR_PLAYGROUND` | `CHAT_Interactive_Supervisor` Cell 3 | ⬜ |
| 7 | Update `app.py` system prompt | `2 - Agent Chat App/app.py` | ⏭️ Batch |
| 8 | Update `.assistant_instructions.md` | User home | ⬜ |
| 9 | Re-run Cell 6 in CHAT_Interactive_Supervisor | Reload registry | ⬜ |

### B4 — Suggested Keywords for SKILL_REGISTRY["W2"]

```python
"proposal", "build proposal", "agent proposal", "agent backlog",
"build backlog", "proposal generator", "agent_build_backlog",
"what should we build", "new agent proposal", "agent design"
```

---

## Track C — Agent Registry Completion

| # | Item | Status | Notes |
|---|------|--------|-------|
| C1 | Seed remaining agents into `agent_registry` (currently 91, target now 134 per updated AGENTS.md) | ⬜ | STILL OPEN — verified `agent_registry` row count is still 91 as of Aug 11, 2026 |
| C2 | Add Agent 06 to `agent_registry` once notebook built | ⬜ | B1 notebook is built but not yet run — run `00_registry_bootstrap` after Agent 06's first execution |
| C3 | Verify registry completeness: `SELECT workspace, COUNT(*) FROM mde_dev.test_schema.agent_registry GROUP BY workspace` | ⬜ | STILL OPEN — target updated to 134 (was 133) |

---

## Track D — Platform / Infrastructure Debt

| # | Item | Status | Priority | Notes |
|---|------|--------|----------|-------|
| D1 | Regenerate `Databricks_Cost_Optimization_Action_Plan.pptx` | ⬜ | HIGH | Current PPTX contains V1 inflated figures ($638K). Correct total: $183,607/year |
| D2 | Action on `phoenix_vs_endpoint` idle waste | 🟢 | HIGH | RESOLVED — decommissioned. `system.billing.usage` confirms zero usage on any date after 2026-05-19 (steady ~$47/day, ~672 DBU/day before that). $16,872/year recovered. Owner: stone.teele@hologic.com |
| D3 | Batch `app.py` update for Agents 05 + 06 | ⬜ | LOW | Batched per skip list — do together |
| D4 | Phase 10 — Define and document (bridge between Phase 9 AIE and Phase 11) | ⬜ | LOW | Phase 10 is implicitly agent_registry seeding + idea_scanner launch |

---

## Track E — NEXUS Observability & Health

| # | Item | Status | Notes |
|---|------|--------|-------|
| E1 | Query `idea_seed_library` top opportunities once Track A is confirmed | ⬜ | `SELECT idea_name, domain_tag, composite_score FROM mde_dev.test_schema.idea_seed_library WHERE coverage_status='gap' ORDER BY composite_score DESC LIMIT 20` |
| E2 | Wire `05_idea_scanner` output → `06_agent_proposal_generator` input (Lakeflow Job) | ⬜ | Job: W2_value_discovery_pipeline, task dependency: idea_scanner → proposal_generator |
| E3 | Add W2 pipeline to `agent_pipeline_status` tracking | ⬜ | Include both Agent 05 and Agent 06 run metadata |

---

## Completion Criteria for Phase 11

- [x] `idea_seed_library` confirmed with real covered/partial/gap split (Track A) — VERIFIED Aug 11, 2026 (8/94/2)
- [ ] `agent_build_backlog` populated with LLM-generated proposals (Track B) — notebook fully built, just needs to be RUN
- [ ] Agent 06 fully registered across AGENTS.md, SUPERVISOR, SKILL_REGISTRY (Track B3) — AGENTS.md done, SUPERVISOR/SKILL_REGISTRY unverified
- [ ] Total agent count at 133 — superseded, AGENTS.md now targets 134
- [ ] Cost PPTX regenerated with correct $183,607 figures (Track D1) — still outstanding (D2 endpoint waste item now resolved separately)

---

## Reference

| Asset | ID / Path |
|-------|-----------|
| `05_idea_scanner` | Notebook ID: 1405118320738450 |
| `00_registry_bootstrap` | Notebook ID: 1405118320738454 |
| `CHAT_Interactive_Supervisor` | Notebook ID: 1041804398715719 |
| `mde_dev.test_schema.idea_seed_library` | Delta table, Liquid Clustered `(domain_tag, coverage_status)` |
| `mde_dev.test_schema.agent_build_backlog` | Delta table — TO BE CREATED in Track B |
| `mde_dev.test_schema.agent_registry` | 91/132 agents seeded |
