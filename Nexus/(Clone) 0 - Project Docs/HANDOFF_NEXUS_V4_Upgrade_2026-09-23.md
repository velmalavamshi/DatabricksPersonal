# HANDOFF — Hologic AI Agent App (`hologic-ai-agents-v4`)

**Written for:** a fresh Claude Code session picking this up cold, and for Sameet as the one-page state of the app. Read this first, then the tracker it points to, before touching code.

**Last updated:** 2026-09-25 (running handoff — updated in place; the filename keeps its original 09-23 date). **Owner:** sameet.patel@hologic.com

**App:** `hologic-ai-agents-v4` (Databricks Apps, DEV workspace) · https://hologic-ai-agents-v4-6617965257274108.8.azure.databricksapps.com
**Deployed source:** `/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/5 - Agent Chat App - V4/`

---

## 1. Where things stand right now

| | |
|---|---|
| **Live deployment** | `01f1b90a…` (2026-09-25 17:58 UTC), serving `index-BAoQ10km.js`, `/api/health` 200 |
| **Uploaded, NOT yet live** | Page-scroll fix, build `index-C_7TFlcK.js` — in the Workspace `static/` folder, SHA-256 verified. **Needs Sameet to run `apps deploy`** (§4). |
| **Tests** | Backend 343/343 pytest (`phase1_tests/`) · Frontend 145/145 vitest, `tsc -b` + oxlint clean |
| **Local = deployed?** | Yes as of 2026-09-25: `deployed_snapshot/` backend matches the Workspace byte-for-byte for every file uploaded today; `frontend/` source built the current bundle |

**Where status lives (read these, don't re-derive):**

| Doc | Location | What it holds |
|---|---|---|
| **`TRACKER.md`** | `…\5 - AI Multi Agents\0 - All files\NEXUS_V4_Upgrade\` (**OneDrive only — not in the Workspace**, see G-34) | Phase status, full change + deployment log, **Gap Register G-01…G-45**, consolidation plan |
| `CAPABILITIES_INDEX.md` + `PHASE_10…17` docs | Workspace `0 - Project Docs/`, mirrored at `…\5 - AI Multi Agents with Databricks\0 - Project Docs\` | Per-phase scope and history (their status rows are partly stale — see G-27…G-30) |
| `AGENTIC_AI_CAPABILITIES_RESEARCH.md` | Same `0 - Project Docs` folder (local only so far) | 3-article agentic-AI capability research + NEXUS gap map + 10 ranked next steps |
| This file | Same folder (local + Workspace) | Handoff narrative |

---

## 2. What shipped on 2026-09-25

All live-verified unless marked otherwise. Full detail per item is in `TRACKER.md` → "Frontend changes".

### 2.1 Reasoning trace (replaces "🧠 NEXUS thoughts") — deployment `01f1b904…`
- Card with **live / paused-for-approval / complete** states; status nodes on a connected timeline (spinner, check, pink ✕ declined, pause).
- SVG tool icons + tool tags (SQL, Workspace file, Jobs API, Nutter, Azure DevOps, Notebook run, Quality review); SQL/path shown per step; per-step "Show output".
- Summary line when done ("Reasoned through 6 steps · 2 queries · 1 file read · 18.4s"); opens while running, collapses when finished unless the user toggled it; never spins on a stopped/reloaded turn.
- Sameet confirmed it in a real browser: "working amazing."

### 2.2 Trace v2 + approval card + speed fixes — deployment `01f1b90a…`
| Change | Detail |
|---|---|
| **Per-step timing** (backend) | `sql_tools.handle_tool_calls(timings=…)` — optional dict filled with elapsed ms per call. Default `None`, so every existing caller is unchanged; 3 tests prove identical results + call order either way. Both `chat_engine.py` call sites write `duration_ms` onto the trace step. |
| **Named stages** (frontend) | Traces with 4+ steps across 2+ stages group into numbered stages (Gathering context → Querying data → Checking jobs → Validating → Taking action → Refining the answer), **derived from the real tool calls, not an LLM plan** — no prompt/agent behavior change. |
| **Approval card** (frontend) | Tool tag + the model's own purpose as title, SQL in a code block, args in an aligned grid, segmented Approve/Deny, optional deny reason (backend already allow-lists `reason` and passes it to the model), Approve all / Deny all, tally, double-submit guard, raw-args toggle. |
| **"Looks hung" fixes** (backend) | S8 ownership check + HITL consume moved off the event loop (`await run_in_threadpool(...)`) — they were freezing **every** user's stream while blocking on SQL · `progress` events sent before the context build ("Preparing context…", "Summarizing earlier conversation…") · "Polishing response…" only when Loop Engineering will actually run · SSE headers `Cache-Control: no-cache` + `X-Accel-Buffering: no` |
| **"Looks hung" fixes** (frontend) | Status arriving after text started is shown as a live line under the answer (was invisible) · `Message` memoized so only the streaming message re-renders per token (was every message × markdown + highlight.js) · `useDeferredValue` for streaming text · `aria-live` removed from the whole thread |

**134-agent calling capability is unaffected** — the only backend execution-path change is the display-only timing dict (§ above); the 134-agent notebook platform wasn't touched.

### 2.3 Page-scroll regression — found live, fixed, **awaiting deploy**
- **Symptom (Sameet's screenshots):** the whole app shell scrolled up the page, exposing white below.
- **Cause (mine, from 2.1):** the trace's visually-hidden `.rt-sr` labels are `position: absolute` with no positioned ancestor, so they resolved against the page and stretched the document. Repro: 4,803 px document in an 807 px window.
- **Fix:** `.rt { position: relative }` + guard `.thread { position: relative }`. Verified: document = 807 px, page can't scroll, thread still scrolls internally.
- **Lesson for any future component:** anything `position: absolute` inside a message must have a positioned ancestor inside `.thread`.

### 2.4 Other work the same day
- **Tracker consolidated + Gap Register created** in `TRACKER.md` (was 3 weeks stale). Full Workspace walk (39,513 objects) confirmed `CAPABILITIES_INDEX.md` is the only master the Databricks Assistant is told to use; no tracker tables/dashboards exist.
- **Agentic AI research** (MightyBot / Akka / Cognipeer) → `AGENTIC_AI_CAPABILITIES_RESEARCH.md`.
- **New request logged — G-42:** commit to a user-named branch from within a conversation, following medallion notebook standards (design points in the tracker; must push to an **existing** branch only — never create one).

---

## 3. Waiting on Sameet

| # | Decision / action | Why it matters | Tracker |
|---|---|---|---|
| 1 | **Run `apps deploy`** for the scroll fix, then hard-refresh | Fix is uploaded but not live | — |
| 2 | **Loop Engineering**: off by default / keep eval only / stream the rewrite | Up to 4 non-streamed model calls **after** the answer is on screen (est. 30-120 s per rewrite), then the answer is swapped. Changes answer quality, so not done without a decision | G-43 |
| 3 | Composer stays busy after the answer (save runs before the stream closes) | Needs a deliberate design to avoid a save race with the next turn | G-44 |
| 4 | Cache the history summary + memory lookup | Summary is a fresh model call every turn from turn 4 on | G-45 |
| 5 | **Surrogate-key standard: `md5` or `xxhash64`?** | `.assistant_instructions.md` (Databricks Assistant) says xxhash64; the 134-agent platform was moved to md5 on 09-23 — they currently give opposite instructions | G-39 |
| 6 | Approve G-42 branch-commit design points | Before building | G-42 |
| 7 | Approve tracker consolidation (CAPABILITIES_INDEX = single tracker, push TRACKER.md to Workspace) | Stops status drifting across ~22 docs | G-27…G-37 |
| 8 | Fix S10 now? (image endpoint has no ownership check) | Last open security fix | G-01 |
| 9 | Run `az ad sp create-for-rbac --name "nexus-synapse-trigger" …` | Unblocks the Synapse trigger tool (classifier blocks it for Claude) | G-14 |
| 10 | Archive stale local copies + duplicate doc sets | Wrong-copy edits | G-31, G-36 |

---

## 4. How to ship a change (proven 3× on 2026-09-25)

1. **Check local = deployed** before editing backend files: export the Workspace copy, compare SHA-256 against `deployed_snapshot/`.
2. Edit → `cd phase1_tests && ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -o addopts="" -q` (the extra flags make the summary line print) · frontend: `npm run typecheck`, `npx oxlint`, `npm test`, `npm run build`.
3. **Visual QA** any UI change with the headless-Edge harness (`NEXUS_V4_Upgrade\qa_harness\README.md`).
4. **Back up** the Workspace target first (`databricks --profile DEV workspace export-dir …` into `NEXUS_V4_Upgrade\backups\`).
5. Upload per file with `databricks --profile DEV workspace import "<ws path>" --file "<local>" --format AUTO --overwrite` (keeps `.py` as FILE type), then **export each back and compare SHA-256**. Upload new asset files before `index.html`.
6. **Sameet runs `apps deploy`.** Claude Code's auto-mode classifier blocks `databricks apps deploy` for Claude, and the block says not to route around it — do not use another tool to deploy. Command:
   ```
   databricks --profile DEV apps deploy hologic-ai-agents-v4 --source-code-path "/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/5 - Agent Chat App - V4"
   ```
   *(Supersedes the 09-23 note that recommended deploying via `manage_app` as an alternative.)*
7. **Verify live:** `databricks --profile DEV apps get hologic-ai-agents-v4` (active deployment + `SUCCEEDED`), fetch `/` with a `databricks auth token` bearer and check the served asset hash, `/api/health` 200. Then delete superseded `static/assets` files.

**Rollback:** re-import the relevant backup folder with `workspace import-dir … --overwrite`, then `apps deploy`. Backups from today: `backups\static_react_backup_2026-09-25_pre_reasoning_trace\`, `backups\v4_full_backup_2026-09-25_pre_trace_v2_bundle\` (all 27 files), `backups\static_backup_2026-09-25_pre_scroll_fix\`.

**Superseded assets to delete after the scroll-fix deploy is verified:** `index-BeaM1AW4.js`, `index-C0-Cfba6.css`, `index-BAoQ10km.js`, `index-BcRuB6hB.css`.

---

## 5. Highest-value open gaps (full list: `TRACKER.md` Gap Register)

| Gap | Why | Tracker |
|---|---|---|
| **Empty response on heavy-grounding tasks** — whole output budget spent on tool calls (`tokens_out=16580, tool_only=True`) | Blocks trusting NEXUS with multi-object builds; root of research next-step #1 (curated context) | G-13 |
| S10 image ownership | Last open security fix | G-01 |
| No feature flag / staged rollout; rollback depends on local backups | Every deploy is all-or-nothing | G-08 |
| Replica-unsafe in-process caches | Silent breakage the day autoscaling is turned on | G-06 |
| `persistence.py` / `chat_engine.py` monoliths | Every fix makes them bigger | G-18 |
| No answer-quality regression evals | Nothing catches a prompt/model change that makes NEXUS worse | research §8 #3 |
| **G-07 (feature gap after React cutover) is probably stale** | The live app now shows model selector, Tools, folders, pinned/archived sessions, Routines, Memory, Stats, Agents, Settings (seen in Sameet's 09-25 screenshots; `frontend/src/features/` has matching panels) — re-verify and close what's done | G-07 |

---

## 6. Gotchas learned this week

- **`NEXUS_V4_Upgrade/` (tracker, plan, risk register, `deployed_snapshot/`, tests, backups) exists only on OneDrive.** Two local parent folders (`5 - AI Multi Agents\` and `5 - AI Multi Agents with Databricks\`) map to one Workspace folder.
- **Local `CANONICAL_NOTEBOOK_TEMPLATES.md` is stale** vs the Workspace copy (9,338 vs 13,266 bytes) — the Workspace copy is what `00_supervisor_agent` loads. Never push local over it (G-35).
- **`mcp__databricks__*` tools only reach DEV.** For UAT/POC/PRD use the `databricks` CLI with `--profile`.
- **PowerShell eats backticks** in double-quoted strings/here-strings — put SQL with backticked identifiers in a file and send it with `--json "@file"`.
- Headless Edge minimum viewport is ~496 px (see `qa_harness\README.md`).
- Frontend status text arrives as `"🔍 *Running query...*"` — `traceModel.cleanStatus()` strips the emoji/asterisks but must keep underscores inside object names (a real bug caught in QA).

---

## 7. Carried over from the 2026-09-23 architecture review (still true)

- **S10** — `GET /images/{image_key}` (`routers/misc.py`) has no ownership check; the key (`img_{exchange_num}_{timestamp}`) is guessable.
- **Process-local state** (`GENERATED_IMAGES`, `_*_CACHE` dicts, `query_cache` store) is replica-unsafe.
- **No schema-migration mechanism** — tables/columns are created with ad-hoc DDL.
- **No rate limiting or concurrency bounds** anywhere in the backend.
- **Accessibility:** the new trace and approval card carry real `aria-*`, but most of the app still has little; WCAG work (Phase 16 sub-phase 8) not started.
- The React cutover on 09-23 happened without a feature flag (Sameet's explicit instruction); legacy `static/` is archived at `NEXUS_V4_Upgrade\backups\static_legacy_backup_2026-09-23.tar.gz` (local only).
- Background agent `a0cdf405c9cf8d5a4` (09-23) **did complete**: it root-caused and fixed the `xxhash64`/`etl_*` standards leak in the 134-agent platform; the 3 bad `NEXUS_Generated` notebooks were archived per Sameet (see `PHASE_15_PROFESSIONAL_UPGRADE.md`).

---

## 8. Recommended next steps (in order)

1. Sameet deploys the scroll fix → verify live → delete the 4 superseded assets.
2. Get decisions on G-43 (Loop Engineering) and G-39 (SK standard) — both unblock real work.
3. Fix **G-13** (context overload / empty response): cap tool-read volume per turn, reserve an output-token floor.
4. Re-verify and close **G-07** rows that are already built.
5. Build **G-42** (branch commits) once its design is approved — per-tool autonomy levels (research §8 #2) fit naturally here.
6. S10, then a small golden-set eval run on every deploy.
7. The standard Definition of Done gate applies to every item — this handoff doesn't replace it.
