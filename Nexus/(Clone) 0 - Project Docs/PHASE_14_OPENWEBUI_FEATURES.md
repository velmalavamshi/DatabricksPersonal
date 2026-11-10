# NEXUS Phase 14 — Open WebUI-Inspired Feature Expansion

> **Status:** 🟡 SUBSTANTIALLY IMPLEMENTED (backend) — re-verified against live app source Aug 11, 2026. This doc said "Planning" but the app's own `GET /api/app/info` endpoint already reports `"phase": 14` with 5 of 7 features listed as shipped. See per-feature verification notes added below. Frontend wiring (static/app.js) was NOT verified in this pass — only backend endpoints.
> **Update (same day, later):** 14.3 (Memory Panel) closed for real — moved off the in-memory list onto a real Delta table with system-prompt injection, verified end-to-end against live data. 14.4 (Citations) confirmed fully done on a direct frontend read (was marked unverified below). 14.2 (Fork) and folder persistence remain real stubs — not touched this pass, see updated notes below.
> **Update 2026-09-23 — 14.2 and 14.5 CLOSED FOR REAL:** Fork now actually copies conversation history (new `persistence.fork_session()`, real ownership check via `user_can_access_session` — the old stub had none) into a genuinely new, persisted session with `parent_session_id` set; live-verified end-to-end (real fork of a real historical session, confirmed correct copied content/tokens/owner). Folders moved off the in-memory `_FOLDERS` dict onto a real `nexus_folders` Delta table, AND gained the session-assignment mechanism that never existed before (`POST /api/sessions/{id}/folder` — a new route, not just a persistence swap); live-verified: create → assign → list shows it → delete → session's `folder_id` correctly clears. 26 new tests. Both remaining "Future Work" items below are now done.
> **Created:** 2026-08-07  
> **Owner:** sameet.patel@hologic.com  
> **App:** `hologic-ai-agents-v3`  
> **Inspiration:** Open WebUI (https://docs.openwebui.com)  
> **Depends on:** Phase 13 (v3 frontend redesign, COMPLETE)  
> **Approach:** Cherry-pick high-value Open WebUI patterns that fit a Databricks-native agent platform. Skip consumer-facing features (voice, arena) that don't fit our data engineering workflow.

---

## Executive Summary

Open WebUI is an open-source LLM frontend (similar to Claude/ChatGPT) with features that map well to NEXUS v3's architecture. This phase adds **7 features** inspired by Open WebUI's best patterns while keeping NEXUS Databricks-native. The 13-capability tracker from Phase 13 is preserved — these are additive.

---

## Feature Comparison: What V3 Already Has

| Open WebUI Feature | NEXUS V3 Equivalent | Status |
|---|---|---|
| Multi-model chat | `MODEL` config + AI Gateway routing (3-tier LLM) | DONE |
| Knowledge/RAG | Agent 70 (Vector Search) + workspace file read | DONE |
| Custom Tools/Functions | 8 skills (SQL, Files, Images, Agent Routing, etc.) | DONE |
| Image Generation | `image_generator.py` (Hologic-branded visuals) | DONE |
| Prompt Library | 6 session templates + custom template CRUD | DONE |
| Chat Organization (tags) | Session tagging + pin/archive | DONE |
| Dark Mode | Full theme toggle + persistence | DONE |
| Keyboard Shortcuts | 7 shortcuts (Ctrl+K, N, D, /, E, 1-9, Esc) | DONE |
| Export/Import | MD, JSON, PDF, Word (.docx), Print, ZIP export (PDF/Word/Print added 2026-08-08, after this table was first written) | DONE |
| Admin/User Roles | OAuth identity + share modes | DONE |
| Collaborative sharing | Session share (read-only/edit) | DONE |
| Markdown + Code rendering | Client-side parser + code copy | DONE |
| Onboarding wizard | First-run modal | DONE |
| Notifications | Polling notification system with badge | DONE |

---

## Phase 14 Features (7 items, ordered by priority)

### 14.1 — Regenerate / Edit Messages ⚡ QUICK WIN

> **VERIFIED:** Listed in `/api/app/info`'s `phase_features`. Doc correctly notes no backend change needed (existing `/api/chat` replays any history array) — cannot confirm frontend UI without reading `static/app.js`.

**Open WebUI pattern:** Click any user message to edit and re-send; click assistant message to regenerate.

**NEXUS implementation:**
- Add "Edit" icon on user message hover → opens inline editor
- Add "Regenerate" icon on assistant message hover
- Re-sends to `/api/chat` with history truncated to that point
- Frontend only (backend already supports arbitrary history replay)

| Aspect | Detail |
|---|---|
| Effort | LOW (2-4 hours) |
| Files changed | `static/app.js` (message render + new handlers) |
| Backend changes | None — existing `/api/chat` handles any history array |
| UX | Pencil icon on user msgs, refresh icon on assistant msgs |

---

### 14.2 — Chat Branching / Forking

> **VERIFIED (partial):** `POST /api/sessions/fork` exists in `routers/enhancements.py` and is listed in `/api/app/info`. However it is a **stub** — it generates a `fork-<uuid>` id and returns metadata (`forked_from`, `fork_at_index`, `title`) but does NOT call `persistence.py` to actually copy messages into a new persisted session. Frontend/backend wiring to make forking actually work is still open.

**Open WebUI pattern:** Fork a conversation at any message to explore alternative paths without losing the original thread.

**NEXUS implementation:**
- "Fork" button on any message → creates new session with history up to that point
- Original session untouched; new session gets a "Forked from X" label
- Enables exploring different agent routing strategies

| Aspect | Detail |
|---|---|
| Effort | MED (6-8 hours) |
| Files changed | `static/app.js` (fork button + handler), `routers/sessions.py` (new POST /api/sessions/fork endpoint) |
| Backend | New endpoint: `POST /api/sessions/{id}/fork` — copies messages up to index N into new session |
| Data model | Add `forked_from` field to session metadata |

---

### 14.3 — Persistent Memory Panel (Wire Phase 9)

> **✅ SHIPPED 2026-08-11:** `GET/POST/DELETE /api/memories` now back a real Delta table,
> `mde_dev.test_schema.nexus_user_memory` (memory_id/user_email/content/created_at, Liquid
> Clustered on user_email) — real persistence.py functions (`get_user_memories`/`add_user_memory`/
> `delete_user_memory`) replaced the old `_MEMORIES` global list, which was lost on every redeploy.
> **Correction to this doc's original scoping:** the target was never `mde_dev.test_schema.agent_memory`
> — the real existing table with that similar name is `nexus_agent_memory`, and it's an unrelated
> thing (keyed by agent_name/workspace for the 134-agent platform's own internal per-agent learning,
> no user_email concept, zero rows) — reusing it was considered and ruled out before building the new
> table, not assumed. Memories are now also injected into `chat_engine.py`'s system prompt as a frozen
> snapshot per turn (fetched once via a new `user_email` param on `stream_chat_response()`), so this
> is a full close of the original "wire Phase 9 remember/recall" intent for the *user-facing* memory
> panel specifically (not literally Phase 9's own agent-side `remember()`/`recall()` in
> `00_agent_config`, which is a separate, still-untouched system on the notebook platform side).
> Real ownership-authorization bug fixed in the same pass: the old delete endpoint had no ownership
> check at all (any user who knew another user's memory_id could delete it) — the new version scopes
> the DELETE to the requesting user's own email, verified via a live test, not just code inspection.

**Open WebUI pattern:** "Memory" panel showing what the AI remembers about you across sessions.

**NEXUS implementation:**
- Phase 9 already has `remember()` / `recall()` / `reflect()` in `00_agent_config` Cell 18
- Add "Memories" view in the context panel (alongside Skills, Agents)
- Show stored memories with ability to delete/edit
- Add explicit "Remember this" button on any message

| Aspect | Detail |
|---|---|
| Effort | MED (4-6 hours) — actual, matched the estimate |
| Files changed | `persistence.py` (new table + functions), `chat_engine.py`/`routers/chat.py` (injection wiring), `routers/enhancements.py` (endpoints now call persistence.py instead of the old list) |
| Backend | Real Delta table `mde_dev.test_schema.nexus_user_memory`, owned by this app (not a cross-workspace proxy to the agent platform's `nexus_agent_memory` — that table doesn't fit this use case) |
| Note | No cross-workspace access needed — same SP/warehouse this app already uses for every other table |

---

### 14.4 — Citations / Source Attribution

> **✅ VERIFIED COMPLETE 2026-08-11** (this doc previously marked it unverified): `chat_engine.py`
> populates a real `citations` list on `msg_record` from actual SQL/file/job-diagnostic tool calls
> (deduped, capped at 6), and `static/app.js:597` renders `m.citations` as `[Source]` tags with a
> detail tooltip. Confirmed via direct source read on both ends, not just the doc's own claim.

**Open WebUI pattern:** Show which documents/sources contributed to each response with clickable citations.

**NEXUS implementation:**
- When SQL results are used → show inline `[SQL: query]` citation with expandable result
- When workspace files are read → show `[File: /path/to/file]` with link
- When agent is routed → show `[Agent: 32_oracle_ebs_specialist]` with routing reason
- SSE already sends tool call metadata (`sql_result`, `file_content`, `agent_routed`)
- Frontend just needs to parse and render provenance cards

| Aspect | Detail |
|---|---|
| Effort | MED (6-8 hours) |
| Files changed | `static/app.js` (citation rendering in message area) |
| Backend | Minor — ensure SSE events include source metadata (mostly already there) |
| UX | Expandable citation cards below each message, numbered superscripts in text |

---

### 14.5 — Chat Folders / Hierarchy

> **VERIFIED:** `GET/POST/DELETE /api/folders` fully implemented in `routers/enhancements.py`, matching this spec's CRUD shape. Frontend rail tree view / drag-and-drop not verified.

**Open WebUI pattern:** Organize chats into nested folders (not just a flat list with tags).

**NEXUS implementation:**
- Add `folder` field to session metadata (nullable, default = root)
- Rail shows: Pinned → Folders (expandable) → Recent
- Drag-and-drop sessions into folders
- Create/rename/delete folders

| Aspect | Detail |
|---|---|
| Effort | LOW-MED (4-6 hours) |
| Files changed | `static/app.js` (rail tree view), `routers/sessions.py` (add folder CRUD), `persistence.py` (folder field) |
| Backend | New endpoints: `GET/POST/DELETE /api/folders`, `POST /api/sessions/{id}/move` |
| Storage | In-memory dict (Phase 15 can persist to Delta) |

---

### 14.6 — Model Selector Per Chat

> **VERIFIED COMPLETE:** `GET /api/models` (auto/sonnet/opus) in `routers/enhancements.py`, and `routers/chat.py`'s `/api/chat` accepts `model_override` and resolves it to the real endpoint name (`databricks-claude-sonnet-4-6` / `databricks-claude-opus-4-8`), passed through to `chat_engine.stream_chat_response()`. This one is genuinely fully wired end-to-end, not just a stub.

**Open WebUI pattern:** Dropdown to switch between models mid-conversation.

**NEXUS implementation:**
- Show model selector in composer area (dropdown: Sonnet 4, Opus 4, or "Auto" for 3-tier routing)
- Maps to existing APEX/CRITICAL/STANDARD tiers
- Override stored per-session; defaults to "Auto" (current behavior)
- Useful when user wants Opus-quality for complex architecture questions

| Aspect | Detail |
|---|---|
| Effort | LOW (2-3 hours) |
| Files changed | `static/app.js` (model selector UI), `routers/chat.py` (accept `model_override` param) |
| Backend | Pass model override through to `chat_engine.py` → override `MODEL` for that call |
| Cost note | Opus = $0.105/DBU vs Sonnet = $0.105/DBU (same via AI Gateway). Real cost is token count, not rate. |

---

### 14.7 — Disclaimer Footer

**Open WebUI / Claude / ChatGPT pattern:** Persistent footer below the composer: "X can make mistakes. Check important info."

**NEXUS implementation:**
- Static text below composer: "NEXUS can make mistakes. Verify critical data against source systems."
- Styled subtly (muted text, small font)
- Always visible, not dismissable

| Aspect | Detail |
|---|---|
| Effort | TRIVIAL (15 min) |
| Files changed | `static/app.js` (add to Composer), `static/styles.css` (disclaimer style) |
| Status | ✅ IMPLEMENTED (2026-08-07) — also listed in `/api/app/info` |

---

## Features Explicitly NOT Added (and why)

| Open WebUI Feature | Why Skip |
|---|---|
| Voice Input/Output (STT/TTS) | Databricks Apps compute lacks audio codecs; overkill for data engineering |
| Evaluation/Arena | Phase 8 LLM-as-Judge already handles quality scoring |
| Generic Web Search | Agents hit live APIs (Oracle, SFDC, Azure); web search adds hallucination risk |
| Webhooks/Integrations | Future consideration — Agent 01 ServiceNow integration handles the primary need |
| Pipelines/Filters (visible middleware) | Phase 8 governance does this invisibly; surfacing it adds complexity without value |
| User-defined Modelfiles/Personas | Agent Factory (63) already creates agents; custom persona UI is redundant |

---

## Verification Summary (Aug 11, 2026 — updated same day after shipping 14.3)

| # | Feature | Real Status |
|---|---|---|
| 14.1 | Regenerate/Edit | 🟡 Backend needs nothing; frontend unverified |
| 14.2 | Forking | ✅ SHIPPED 2026-09-23 — real Delta copy + ownership check, live-verified |
| 14.3 | Memory Panel | ✅ SHIPPED — real Delta persistence + system-prompt injection, verified end-to-end |
| 14.4 | Citations | ✅ Complete — backend populates, frontend renders, confirmed on direct source read |
| 14.5 | Folders | ✅ SHIPPED 2026-09-23 — real Delta table + new session-assignment endpoint, live-verified |
| 14.6 | Model Selector | 🟢 Fully wired end-to-end |
| 14.7 | Disclaimer Footer | ✅ Complete (per doc + app_info) |

**Net (updated 2026-09-23):** 14.2, 14.3, 14.4, 14.5 all genuinely closed and live-verified. Remaining real gap: frontend verification still outstanding for 14.1 (legacy `static/app.js` regenerate/edit — backend needs nothing, never independently confirmed the UI wiring).

---

## Implementation Priority

| Sprint | Items | Estimated Effort |
|---|---|---|
| Sprint 1 (immediate) | 14.1 (Regenerate/Edit), 14.7 (Footer) | 3-4 hours |
| Sprint 2 (this week) | 14.2 (Branching), 14.5 (Folders) | 10-14 hours |
| Sprint 3 (next week) | 14.3 (Memory Panel), 14.4 (Citations), 14.6 (Model Selector) | 12-17 hours |

**Total estimated effort:** 25-35 hours

---

## 13-Capability Tracker Preservation

Phase 13 delivered these capabilities (all retained, no regressions):

1. SSE Streaming Chat
2. Session CRUD (create/read/update/delete/search)
3. Pin/Archive/Share
4. Multi-Session Tabs
5. Global Search (Ctrl+K)
6. Skills/Plugins Panel
7. Session Templates
8. Notifications System
9. User Preferences
10. Keyboard Shortcuts
11. Dark Mode
12. Onboarding Wizard
13. Export (MD/JSON/PDF/Word/Print/ZIP — PDF/Word/Print added 2026-08-08)

Phase 14 adds capabilities **14-20** without touching the above.

---

## Risks & Considerations

| Risk | Mitigation |
|---|---|
| ~~Memory panel requires Delta table access from app SP~~ | RESOLVED — built `nexus_user_memory` as this app's own table, no cross-workspace access ever needed |
| Chat branching could create session sprawl | Limit to 5 forks per session; show fork count |
| Model selector may confuse users who don't know tiers | Default to "Auto" with tooltip explaining tiers |
| Citation parsing may break on complex SSE events | Add graceful fallback — show raw tool name if parsing fails |

---

## Future Work (Phase 15 candidates)

- [x] Persist memories to a Delta table (currently in-memory) — DONE 2026-08-11, see 14.3
- [x] Persist folders to a Delta table (currently in-memory, `_FOLDERS` dict) — DONE 2026-09-23, see 14.5
- [ ] Artifacts pane (inline code execution + HTML/SVG rendering)
- [ ] Split-pane diff view for agent-proposed code changes
- [ ] Push notifications via Service Worker
- [ ] Custom skill/plugin upload (user-defined tools)
- [ ] Session import from other LLM tools (ChatGPT export format)
