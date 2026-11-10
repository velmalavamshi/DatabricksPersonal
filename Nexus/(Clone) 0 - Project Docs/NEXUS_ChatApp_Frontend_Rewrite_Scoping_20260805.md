# NEXUS Chat App — Frontend Rewrite Scoping (2026-08-05)

**Question this answers:** what would it actually take to get NEXUS to a real claude.ai look/feel
(existing features intact, room for more), given Streamlit's ceiling documented in
[[nexus-redesign-gap-analysis]]?

**Method:** read every backend file in `5 - Agent Chat App - STAGING` line by line (`app.py`
4,800+ lines, `sql_tools.py` 213, `query_cache.py` 336, `image_generator.py` 1,064) to find every
Streamlit-coupling point, then read the `databricks-apps` skill's actual platform rules (not
assumed) for what's supported and what isn't.

---

## 1. Recommendation: don't rewrite this on AppKit — hand-rolled FastAPI + React, one app

Two platform facts settle this, straight from the `databricks-apps` skill:

1. **AppKit's plugins don't fit what this app does.** Its own custom-endpoints guide restricts
   custom Express routes to "mutations / external APIs / business logic no plugin covers" —
   `analytics` (SQL dashboards), `lakebase` (Postgres CRUD), `genie` (Databricks' own
   natural-language-to-SQL), `serving` (model-endpoint proxy) are the built-in plugins, and
   **none of them match NEXUS's actual core** — a bespoke multi-tool LLM orchestration loop with
   its own system prompts, its own tool-calling protocol, and its own Databricks REST API
   wrappers (notebook/dashboard/Genie-space creation). Every one of those would be a "custom
   endpoint" under AppKit anyway. Choosing AppKit here buys nothing except forcing the entire
   backend into TypeScript for no structural benefit.
2. **Splitting into two Databricks Apps (a Python API + a separate AppKit frontend) is a dead
   end.** Per the platform guide: cross-app calls return a 302 redirect to the login page instead
   of the expected response, and only one process per app can bind the exposed port. Frontend and
   backend have to ship as one app, one process.

**Recommended architecture:** one Databricks App, one Python process (FastAPI + Uvicorn) that
both serves the built React static bundle and exposes `/api/*` endpoints (chat completions over
SSE, session/project/routine CRUD, file upload, image generation, artifact creation). No
dual-runtime container, no internal reverse-proxy, no CORS — same origin, same process.

---

## 2. What's genuinely reusable (checked file-by-file, not assumed)

| File | Streamlit coupling found | Verdict |
|---|---|---|
| `sql_tools.py` (213 lines) | **Zero** — no `streamlit` import, no `st.*` call anywhere | Reuse as-is |
| `query_cache.py` (336 lines) | **Zero** — self-contained TTL cache class, own dict storage, only imports `re`/`time`/`logging`/`xxhash` | Reuse as-is |
| `image_generator.py` (1,064 lines) | **Zero** in the generation logic itself — pure `matplotlib`/`numpy`, returns PNG bytes | Reuse as-is; only the *call site* changes (`st.image(bytes)` → an `/api/images/{key}` endpoint returning `image/png`) |
| `app.py` (4,800+ lines) | Concentrated in ~1,500–2,000 lines: all CSS, sidebar rendering, message rendering, composer/uploader UI, `st.chat_input`/`st.rerun()` flow | See breakdown below |

**Inside `app.py`, ~45 standalone functions carry the actual business logic and are already
framework-agnostic Python** — not entangled with rendering, just called *from* rendering code.
Confirmed by function signature, not guessed:

- **Session/project/routine persistence:** `persist_conversation`, `get_session_list`,
  `load_session_messages`, `switch_to_session`, `toggle_pin_session`, `soft_delete_session`,
  `share_session`, `search_sessions`, `get_user_projects`, `create_project`,
  `assign_session_to_project`, `get_user_routines`, `create_routine`, `run_routine_now`, and their
  `invalidate_*_cache` counterparts.
- **SQL execution:** `execute_sql_statement`, `execute_parameterized_sql`,
  `cached_execute_sql_statement`.
- **Databricks workspace API wrappers:** `resolve_workspace_asset`, `create_workspace_notebook`,
  `create_workspace_dashboard`, `create_genie_space`, `format_creation_result`.
- **Auth/identity:** `_get_token`, `get_user_identity`.
- **Agent orchestration:** `identify_agents`, `trigger_agent_run`, `get_run_status`,
  `poll_run_until_terminal`, `classify_workspace`.
- **Response quality:** `summarize_history`, `_generate_summary`, `_evaluate_response`,
  `_refine_response`, `_loop_engineering_refine` (the loop-detection/refinement system).
- **The ~1,000+ lines of system-prompt text** — the actual "NEXUS brain" — is just a string.
  100% reusable, zero rework.

**Bottom line: the vast majority of what makes NEXUS *NEXUS* is not Streamlit-shaped.** It's
already organized as plain functions that happen to be called from a Streamlit script today.

---

## 3. What has to be rebuilt, and why

| # | What | Why it can't just be ported |
|---|---|---|
| 1 | **The entire frontend** (~1,500–2,000 lines of CSS + sidebar/message/composer rendering) | This is the actual point of the exercise — rebuilt as real React components, which is what makes claude.ai-style behavior (no full-rerun flicker, unified composer, resizable panels) possible at all. |
| 2 | **The main chat "script flow"** | Today it's a top-to-bottom Streamlit script reacting to `st.session_state`/`st.rerun()`, with streaming implemented as repeated `response_placeholder.markdown()` repaints. Same *logic*, but it has to become a proper async generator yielding real SSE chunks for a stateless HTTP request/response cycle. Bounded work — a few hundred lines — but genuinely new code, not a copy-paste. |
| 3 | **Auth/session model** | Streamlit's per-browser-tab `st.session_state` doesn't exist in a stateless API. Needs a real per-request auth story (Databricks OBO header, per the platform's own documented pattern) — which, as a side effect, **fixes a real bug already on record**: [[nexus-agent-chat-app-findings]] notes Streamlit caches the OBO token at first page load and it goes stale with "no clean in-Streamlit solution" — reading it per-request in FastAPI removes that problem entirely rather than working around it. |
| 4 | **Connection pooling** | `st.cache_resource`-based pooling becomes a normal FastAPI startup-time global/dependency. Mechanical, not risky. |
| 5 | **File upload** | `st.file_uploader` becomes a multipart POST endpoint. Mechanical. |

---

## 4. Rough phase breakdown

1. **Backend extraction** — strip Streamlit calls out of the ~45 functions (mostly already clean),
   wrap each in a FastAPI route, stand up the real SSE streaming chat endpoint, solve the
   OBO-per-request auth story. Medium effort — the functions are ready: the streaming loop and
   auth model are the real work here.
2. **Frontend skeleton** — React app scaffold, base layout (sidebar/main/composer), routing, the
   Hologic color tokens already established this session.
3. **Core chat experience** — message rendering (real markdown + code syntax highlighting),
   genuinely smooth streaming, the unified composer pill (attach + input + send in one control —
   impossible in Streamlit, straightforward in React), sidebar (Chats/Routines/Projects/Usage).
4. **Feature parity** — Artifacts as a **real resizable 3rd column this time** (the one thing
   explicitly deferred as "too risky" when it was a Streamlit modal — a real frontend removes that
   constraint), export, sharing, feedback, loop-detection badges, and the callout component built
   today (its detection logic ports over almost unchanged, just needs a React component instead of
   an HTML string).
5. **"+more"** — keyboard shortcuts, message edit/regenerate, per-conversation topbar, smooth
   transitions, real mobile responsiveness. None of this is achievable in Streamlit at all; all of
   it is normal React work once the skeleton exists.
6. **Deploy** — single `app.yaml`, `databricks apps validate`, smoke tests.

**Realistic scale:** still a genuine multi-week solo project, even with ~90% of the backend
reusable almost as-is — because the frontend rebuild is the majority of the effort by volume, and
there was never a way to get real claude.ai behavior without writing real React UI. What this
scoping changes is *risk*, not *size*: the business logic (system prompts, tool-calling, all the
Databricks integrations) survives nearly intact, so the work that's left is bounded and
well-understood rather than an open-ended full-stack rewrite.

---

## 5. Open questions worth deciding before starting, not during

- **`image_generator.py` renders static PNGs via matplotlib.** A true claude.ai-style artifact
  would ideally be live-rendered (SVG/HTML), not a screenshot. Fine to keep PNG generation as-is
  for v1 and revisit later — flagging so it's a decision, not a surprise.
- **`mcp_server.py`/`main.py`** — per [[nexus-agent-chat-app-findings]], a complete but currently
  dead MCP server implementation (not launched, dependencies commented out). Worth an explicit
  yes/no on whether this rewrite is also the moment to revive it, rather than carrying it forward
  unexamined.
- **Auth model change (#3 above) is the one piece of backend work that's a genuine behavior
  change**, not a mechanical port. Worth scoping and testing carefully on its own rather than
  folding it into the general "backend extraction" phase estimate.

---

## Where this leaves things

Nothing has been started — this is a scoping document only, produced at your request before
committing to either direction. The other project docs
(`NEXUS_ChatApp_Redesign_Gap_Analysis_20260805.md`, `NEXUS_ChatApp_Upgrade_Status_20260805.md`)
describe the current Streamlit app's state; this one is the case for, and rough shape of, moving
off it entirely.
