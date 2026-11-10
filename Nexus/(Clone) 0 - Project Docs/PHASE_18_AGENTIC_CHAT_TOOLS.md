# Phase 18 — Agentic Chat Tools

> **Status:** 🟡 IN PROGRESS. Most tools are live. `trigger_synapse_pipeline` is blocked (see below).
> **App:** `hologic-ai-agents-v4` (Databricks Apps, DEV) · **Started:** 2026-09-23 · **Owner:** sameet.patel@hologic.com
> **Latest deploy:** `01f1bd49…` (2026-09-30 11:41 PM ET) · **Tests as of 2026-10-01 (deploy 01f1bd49):** backend 596 pytest, frontend 180 vitest, all passing.
> **Detailed tracking:** `TRACKER.md` → Gap Register **section C, "App — agentic tools (Phase 18)"**, plus the deployment log in the same file. TRACKER.md is only on OneDrive (`5 - AI Multi Agents\0 - All files\NEXUS_V4_Upgrade\TRACKER.md`), not in the Workspace (TRACKER G-34). Each row there has the full evidence. This doc is a summary.

## What Phase 18 is

Phase 18 gives the NEXUS chat app tools that act, not just answer. The goal (Sameet, 2026-09-23) is for the chat app to do what he uses Claude Code for: create and run Databricks objects, run Nutter tests, update Azure DevOps (ADO), and trigger Synapse pipelines, without leaving chat. Write actions go through server-side approval gates. The model's own arguments never approve a write.

## Wave 1 — the original tools (2026-09-23)

All four were built, deployed and live-verified on 2026-09-23. A real chat message called each tool on the deployed app.

| Tool | Module | What it does | Status |
|---|---|---|---|
| `run_nutter_test` | `nutter_runner.py` | Runs a Nutter test notebook, saves the output to the Workspace and posts pass/fail to an ADO work item | ✅ Live |
| `create_ado_task` | `ado_client.py` | Creates an ADO Task. The server sets AssignedTo and Original Estimate; the LLM never decides them | ✅ Live (real Task #27267 created from chat) |
| `run_workspace_notebook` | `jobs_api.py` | Runs any notebook as a job, so a created notebook can actually build its table | ✅ Live |
| `prerequisites.py` | — | Checks at startup that the Nutter cluster and the ADO PAT are available, and reports the result in `/api/health` | ✅ Live (both checks `ok:true`) |

Five bugs were found and fixed live during Wave 1:
- Serverless job submits were missing their `environments` block.
- Nutter needs the classic "Phoenix Shared Compute" cluster, not serverless, and a 900 s job timeout instead of 300 s.
- The PyPI package is `nutter`, not `databricks-nutter`. The 134-agent platform's Agent 08 template had the same error and was fixed too.
- Nutter's `@tag` decorator only works on a `run_` method.
- ADO Tasks need `OriginalEstimate`, or ADO rejects them with `TF401320`.

## Later tool additions (2026-09-28 → 2026-09-30)

| ID | Tool / capability | Status |
|---|---|---|
| G-49 | `ask_user_question`: a question popup with a recommended option and "Other" | ✅ Live `01f1bb74` (2026-09-28 19:43 UTC); browser check pending |
| G-50 | `parse_pbix_file`: reads a `.pbix`/`.pbit`, including the compressed DataModel | ✅ Live `01f1bcd6` (2026-09-30 13:52 UTC) |
| G-51 | `create_document` (hologic-style docx/xlsx/pptx) and `create_erd` (ERD built from the real schema) | ✅ Live `01f1bd0e` (2026-09-30 20:32 UTC); live chat test pending |
| G-52 | Live Lucid import of ERDs | ✅ Live `01f1bd10` (2026-09-30 20:48 UTC) |
| G-53 | `verify_in_lucid`: reads the imported ERD back to check it | ✅ Live `01f1bd20` (2026-09-30 22:44 UTC) |
| G-55 | `execute_sql_write` (approval-gated, `mde_dev` only) and the Manual / Ask / Auto mode switch | ✅ Live `01f1bd3c` |
| G-57 | `search_docs` / `fetch_doc` (Microsoft Learn only) | ✅ Live `01f1bd44` (2026-09-30 11:04 PM ET) |
| G-58 | `edit_workspace_file`: edits existing files in the user's own folder, with a diff shown for approval | ✅ Live `01f1bd44` |
| G-59 | ADO Git: read PRs, files and branches; commit to an existing branch only; reply to PR comments | 🟡 Live `01f1bd44`; needs Code (Read & Write) scope on the app's ADO PAT |
| G-60 | `execute_sql_env`: read-only SQL against UAT/PRD | 🟡 Code live but dormant. The chosen route is a Unity Catalog READ_ONLY binding of `mde_prd`/`mde_uat` to the DEV workspace, which the catalog owner groups have to add |
| G-22 | Dashboards created with content (`dashboard_spec.py`) | ✅ Live `01f1bd49` |
| G-63 | Image input (vision) | ✅ Live `01f1bd49` |
| G-64 | `find_powerbi_usage`: shows which Power BI usage reads a table, across DEV/UAT/PRD | ✅ Live `01f1bd49` |
| G-65 | `load_skill` (Skill Fabric, 9 skills in `NEXUS_Skills`) | ✅ Live `01f1bd49` |

## Supporting work on agentic turns

| ID | Item | Status |
|---|---|---|
| G-13 | Empty responses when the whole output budget went to tool calls | ✅ Closed 2026-09-30. No empty answers across all users since 09-24 |
| G-46 / G-47 | Background turns with keepalive; asset creation shown as trace steps | ✅ Live `01f1b945` (2026-09-26 01:01 UTC); browser check pending |
| G-54 | Turn cap raised to 15 min and enforced during streaming | ✅ Live `01f1bd3c` |
| G-43 | Loop Engineering made a per-chat toggle, off by default | ✅ Live `01f1bd3c` |
| G-61 | Parallel chats (per-user cap of 4) | ✅ Live `01f1bd44` |
| G-42 | Branch-aware commits | 🟡 Points 1/3/4 built as G-59. Still open: session branch pin, standards pre-commit check, work-item link |
| G-56 | All users' SQL runs with Sameet's PAT | 🟡 Workspace actions run as the signed-in user since `01f1bdb8` (2026-10-01); SQL as the user waits on warehouse CAN USE for all users |
| G-45 | Per-turn context cost (summary and memory lookup on every turn) | ✅ Live `01f1bddc` — summary once per 3 turns, memory cached per user |

## 2026-10-01 → 10-06 additions

| ID | Capability | Status |
|---|---|---|
| G-67 | Big workbooks read by sheet (`read_workbook_sheet`), wrong Workspace path found by file name, an answer even after very long tool runs | ✅ Live `01f1bdb8` |
| G-68 | Notebook create / run / commit and file edits limited to data engineers (Databricks group `HDA Developers`, deny list for the Data Analytics team) | ✅ Live `01f1c0de8319` |
| G-69 | Models upgraded to Sonnet 5.5 / Opus 5.5; app reads model names from the shared notebook `00_nexus_models` | 🟡 Chat app live `01f1c1c1`; agent-platform configs pending Sameet |
| G-70 | **Power BI report validation**: skill `pbi-live-dataset-validation` in `NEXUS_Skills`; `parse_pbix_file` now returns every report/page/visual filter **with its values** and each slicer's saved selection; an attached .pbix can be read section by section by its file name | ✅ Live `01f1c1f3` — real test: BSH Flash report filters listed correctly, incl. the line chart's extra GL Division 700 exclusion |
| G-73 | **HDA_PBI readable** (Power BI semantic models, PBIP/TMDL) — reads only, commits stay HDA_MDE; `git_read_file` lists folders and finds paths (`find`) | ✅ Live `01f1c258` — found the PRD Item Master model and its 10 `v_pbi_*` views (verified 10/10) |
| G-74 / G-74c | "Output reached 80,000 token limit" fixed — per-call output cap by model (128K for Sonnet/Opus 5.5), cut tool calls detected, turn cap 256K | ✅ Live `01f1c2a2` |
| G-75a | Big files built in pieces: `start_document` → `append_to_document` (saved after every append) → `finalize_document` | ✅ Live `01f1c2a5` — 700/700 rows in 4 appends |
| G-75b | "Continue" resumes the same open draft instead of restarting | ✅ Live `01f1c2a6` — 600 rows over 2 turns, clean seam |
| G-75c | `append_query_to_document` — the server writes a read-only query's rows (≤20,000) into the file | ✅ Live `01f1c2aa` — 11,645-row data dictionary, 1,336 output tokens |
| G-75d | No-progress detector (replaces the fixed call count; 120-call ceiling) + FMAPI list-content fix | ✅ Live `01f1c2abe21a` |
| G-75e | Prompt caching on every model call; cost is cache-aware | ✅ Live `01f1c2ac` — −63% on a real 10-call turn |
| G-76 | Long turns reconnect after the Databricks Apps front door's ~300 s per-request cut (`GET /api/chat/stream`, replay from the last frame) — fixes "Connection dropped — still finishing in the background" | ✅ Live `01f1c2c3` — 651 s test turn, 2 cuts, 2 reattaches, nothing lost |

**Not possible yet:** querying the live Power BI dataset (no Power BI credential in the app) — the skill has NEXUS write the DAX for the user to run.

## Blocked: `trigger_synapse_pipeline`

Not built. There are two separate blockers:

| ID | Blocker | Waiting on |
|---|---|---|
| G-14 | The app has no Azure AD credential. An Azure AD service principal (`az ad sp create-for-rbac --name "nexus-synapse-trigger" …`) has to be created first. Claude Code's classifier blocks Claude from running that command | Sameet |
| G-15 | The new service principal would also need its own grant on the `[state]` database, which both Synapse pipelines look up. It is not confirmed whether that grant is possible, or who would give it | Sameet / DBA (unknown) |

Planned design once G-14 is resolved: a new `synapse_api.py` that uses `azure-identity` and mirrors `jobs_api.py`'s `trigger_agent_run()`, with a forced approval pause. The full plan is in the `nexus-synapse-pipeline-tool-backlog` memory. The two proven Synapse runs from 09-23 (G-16) were triggered manually on 2026-09-30, not by the app. Both succeeded.
