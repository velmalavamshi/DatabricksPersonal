# NEXUS Capabilities Index — Master Tracker Pointer

> **Purpose:** Single entry point to every capability/phase tracker doc in this project. Do not scatter new phase docs elsewhere — always add them here per the Auto-Review Rule below.
> **Location:** `/5 - AI Multi Agents/0 - Project Docs/` (canonical doc home for active trackers) — fully-complete phase docs move to the sibling `/5 - AI Multi Agents/7 - Completed Upgrades/` folder instead (see Maintenance Notes)
> **Owner:** sameet.patel@hologic.com
> **Last Updated:** 2026-10-08 (G-74/G-75a–e merged: output caps, files built in pieces, resume, query→file, no-progress stop, prompt caching; tests 704 + 196). Prior: 2026-10-07 (G-73: HDA_PBI repo readable + folder browse/find in git_read_file). Prior: 2026-10-06 (Phase 10 Skill Fabric marked live — 10 skills incl. new `pbi-live-dataset-validation`; Phase 12 Tracks 1/7 marked done; Phase 14 7/7; Phase 18 row brought to G-70; latest deploy `01f1c1f3`; test totals 661 + 196). Prior: 2026-10-01 (Phase 18 doc added and linked; Phase 16/18 rows trimmed to one-line status; current test totals added). Prior: 2026-09-23 (new Phase 18 — agentic chat tools — added). Earlier history: see git-less change notes in TRACKER.md.

---

## Auto-Review Rule (before starting new phase/enhancement work)

1. Read [CHECKLIST.md](CHECKLIST.md) — outstanding sync items for any new agent/skill/tool/feature.
2. Read the highest-numbered `PHASE_<N>.md` below to understand current state.
3. Create the new doc in this same folder as `PHASE_<N>_<TOPIC>.md`, then **add a row to the table below**.

---

## Phase / Capability Trackers

| Phase | File | Topic | Status |
|---|---|---|---|
| 8 | [../7 - Completed Upgrades/PHASE_8_GOVERNANCE_OMNIGENT.md](../7%20-%20Completed%20Upgrades/PHASE_8_GOVERNANCE_OMNIGENT.md) | Governance Engine — Omnigent 3-way policy model (ALLOW/DENY/ASK) | ✅ COMPLETE (Jul 1, 2026) — every checklist item verified `[x]`, moved to `7 - Completed Upgrades/` Aug 11, 2026 |
| 9 | [../7 - Completed Upgrades/PHASE_9_AGENT_INTELLIGENCE_OMP.md](../7%20-%20Completed%20Upgrades/PHASE_9_AGENT_INTELLIGENCE_OMP.md) | Agent Intelligence Engine — semantic memory, verified outputs, context compaction (oh-my-pi) | ✅ COMPLETE (Jul 1, 2026) — every checklist item verified `[x]`, moved to `7 - Completed Upgrades/` Aug 11, 2026 |
| 10 | [PHASE_10_RELEASE.md](PHASE_10_RELEASE.md) | Skill Fabric — external knowledge injection at call-time | ✅ LIVE in the chat app since 2026-10-01 (G-23/G-65, `load_skill`) — **10 skills** in Workspace `NEXUS_Skills/` (edit there, live in ≤10 min, no deploy); newest: `pbi-live-dataset-validation` (2026-10-06, G-70) |
| 11 | [PHASE_11.md](PHASE_11.md) | Pending items & build backlog (post Phase 9/10) | 🟡 Active — Track A ✅ done (verified), Track B notebook built but never run, Track D2 ✅ done, D1 open |
| 12 | [PHASE_12_APP_CAPABILITIES.md](PHASE_12_APP_CAPABILITIES.md) | App capabilities — image upload, document generation, live workspace asset creation | 🟡 Tracks 1 (image upload, G-63), 2, 3, 4, 6, 7 (PBI dataset discovery, G-64), 9 ✅ done; Track 8 (NEXUS as an MCP server) = Sameet's decision — recommended not to build (managed Databricks MCP covers it) |
| 13 | [../7 - Completed Upgrades/PHASE_13_V3_FRONTEND_REDESIGN.md](../7%20-%20Completed%20Upgrades/PHASE_13_V3_FRONTEND_REDESIGN.md) | v3 full frontend redesign & feature expansion | ✅ COMPLETE AND DEPLOYED (verified — this is the active v4 production app) — moved to `7 - Completed Upgrades/` Aug 11, 2026 |
| 14 | [PHASE_14_OPENWEBUI_FEATURES.md](PHASE_14_OPENWEBUI_FEATURES.md) | Open WebUI-inspired feature expansion (7 features, cherry-picked) | ✅ 7 of 7 — 14.1 regenerate/edit verified 2026-10-01 (G-11: 3 real bugs fixed, live `01f1bdae`) |
| 15 | [PHASE_15_PROFESSIONAL_UPGRADE.md](PHASE_15_PROFESSIONAL_UPGRADE.md) | Professional-grade upgrade (behavior-preserving): baseline → tests → security hardening (per `NEXUS_V4_Professional_Upgrade_Instruction.docx`; artifacts in `0 - All files/NEXUS_V4_Upgrade/`) | 🟡 RESUMED (2026-09-22) — sub-phase 0 ✅, 1 ✅ (209 tests at the time; as of 2026-10-08 (deploy 01f1c2c3): backend 708 pytest, frontend 199 vitest — all passing), 2 🟡 **10 fixes LIVE** (S1/S1b/S1c/R7/B1/S3/S9 + **S2/S6/S8 new**). Open: S7 (deferred, not blocking), templates/skills decision, reliability R1/R3/R5. **Sub-phases 3-6 superseded by Phase 16.** |
| 16 | [PHASE_16_REACT_MODERNIZATION.md](PHASE_16_REACT_MODERNIZATION.md) | React + TypeScript frontend rewrite, backend modularization, durable/persisted HITL (per pasted 2026-09-19 engineering spec, corrected against the real deployed contract; source brief archived at `NEXUS_V4_React_Modernization_Instruction.md`) | 🟡 IN PROGRESS — React frontend live in production since 2026-09-23 (latest deploy `01f1c2c3`, 2026-10-08); sub-phase 4 shipped, 5 partly shipped, 6-9 not started. Detail: [PHASE_16_REACT_MODERNIZATION.md](PHASE_16_REACT_MODERNIZATION.md) |
| 17 | [PHASE_17_STANDALONE_MCP_PRODUCT.md](PHASE_17_STANDALONE_MCP_PRODUCT.md) | Future vision (Sameet, 2026-09-19): turn NEXUS into a standalone, locally-installable multi-agent product (Open-WebUI-style distribution) connecting via MCP to Databricks, ADO, and internal network sources | 🔵 FUTURE / not scoped — explicitly sequenced AFTER Phase 16 ships; placeholder only, do not start |
| 18 | [PHASE_18_AGENTIC_CHAT_TOOLS.md](PHASE_18_AGENTIC_CHAT_TOOLS.md) | Agentic chat tools — give `hologic-ai-agents-v4` real write-capable tools (run Nutter, create ADO tasks, run any notebook as a job) so it can do what Sameet uses Claude Code for, without leaving chat | 🟡 IN PROGRESS — G-49…G-70 live (latest deploy `01f1c2c3`, 2026-10-08): Workspace actions as the signed-in user, big workbooks by sheet, business users blocked from notebooks, Sonnet 5.5 / Opus 5.5, Power BI report validation, HDA_PBI semantic models readable, big deliverables built in pieces with resume, prompt caching (−63% on agentic turns), long turns reconnect past the platform's 5-minute request cut. Open: `trigger_synapse_pipeline` (G-14/G-15), agent-platform model sync (G-69 part 2), SQL as the user (G-56). Detail: [PHASE_18_AGENTIC_CHAT_TOOLS.md](PHASE_18_AGENTIC_CHAT_TOOLS.md) |
| — | [NEXUS_UI_ENHANCEMENTS_PHASE.md](NEXUS_UI_ENHANCEMENTS_PHASE.md) | Legacy complete phase & enhancement log (predates per-phase file split; superseded going forward by this index) | 📗 Historical reference — left in `0 - Project Docs/` (not a numbered phase tracker, didn't fit the move criteria cleanly; flag if you want it moved too) |

## Adjacent Reference (not a phase tracker, but load alongside)

| File | Purpose |
|---|---|
| [CHECKLIST.md](CHECKLIST.md) | Sync checklist run before any new agent/skill/tool/feature addition |
| [CANONICAL_NOTEBOOK_TEMPLATES.md](CANONICAL_NOTEBOOK_TEMPLATES.md) | Production notebook patterns (Gold Fact, Gold Dim, Platinum) — loaded at runtime by enterprise_standards skill injection in 00_supervisor_agent via `template_file` key |

---

## Maintenance Notes

- When a new `PHASE_<N>_<TOPIC>.md` file is created, add it to the table above in the same edit — this index must never fall out of sync.
- Status legend: ✅ COMPLETE · 🟡 In Progress/Active · 🔵 Planning · 📗 Historical reference.
- Current highest active phase: **18** (Agentic chat tools — live, see [PHASE_18_AGENTIC_CHAT_TOOLS.md](PHASE_18_AGENTIC_CHAT_TOOLS.md); updated 2026-10-06). Phase 16 (React + TypeScript) shipped with the 2026-09-23 cutover; Phase 17 is a captured future vision, not active work. Next new phase doc should be `PHASE_19_<TOPIC>.md`.
- **Split, 2026-09-19:** Phase 15's originally-planned sub-phases 3-6 (backend modularization/frontend/UX/perf) were superseded by the new Phase 16 rather than left open in two places — Phase 15 now closes on just its sub-phases 0-2. Phase 16's own source brief listed SSE event names that don't match the deployed app (`content/status/thinking/tool_call/...` vs. the real `routing/progress/delta/tool_trace_step/...`) — corrected in `PHASE_16_REACT_MODERNIZATION.md` before use; don't trust the archived brief's Section 2 as current-state fact.
- **Lesson learned (Aug 11, 2026):** These docs had drifted significantly behind actual shipped code — several tracker rows said ⬜/Planning for work that was already live in `5 - Agent Chat App - V4/`. Before trusting a tracker doc's status, spot-check the real notebook/app source (or run a quick SQL check against the target Delta table) rather than taking the doc at face value.
- **New table, same day:** `mde_dev.test_schema.nexus_user_memory` was added for V4's per-user Memory Panel. Do not confuse it with the pre-existing `mde_dev.test_schema.nexus_agent_memory` — that one is a different, unrelated table for the 134-agent platform's own internal per-agent learning (agent_name/workspace-keyed, no user concept, zero rows). This was checked and ruled out before building the new table, not assumed different.
- **Reorganization, same day:** created `/5 - AI Multi Agents/7 - Completed Upgrades/` and moved Phases 8, 9, and 13 into it — each verified complete first (8 and 9: every checklist item independently confirmed `[x]`, not just trusted from the doc's own header claim; 13: cross-confirmed all session as the live, running v4 production app). Moved via export→import→byte-diff-verify→delete-original, never a blind overwrite. Phases 10-12 and 14 stay in `0 - Project Docs/` since each has real, verified-open items. Going forward: when a phase doc's every checklist item is independently verified complete (not just labeled so), move it here and update its row's link to `../7 - Completed Upgrades/<file>.md`.
