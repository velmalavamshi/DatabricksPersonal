---
name: hologic-azure-synapse-orchestration
description: Use whenever running, triggering, or debugging a Databricks Silver/Gold/Platinum notebook or a staging extract in Hologic's HDA_MDE environments (DEV/UAT/PRD) via Azure Synapse Pipelines — Databricks CLI + Azure CLI profile setup, the two orchestration pipelines (Transform_Databricks_Notebook_PL, ExtractAndLoad_PL), the shared "state" database that backs both, diagnosing the "firstRow doesn't exist" registration-gap failure, distinguishing run-date from data-date staleness, and verifying a deployed notebook's real current dependencies instead of trusting a stale PR diff. Trigger on "run this in UAT/DEV/PRD", "Synapse pipeline", "Transform_Databricks_Notebook_PL", "ExtractAndLoad_PL", "state DB", "TryGetTransformProcess", "GetObjectForExtract", "is the data stale", "run the stg extract", or any ask to trigger/verify a Databricks object's execution across environments.
---

# HDA_MDE: Databricks + Azure Synapse Orchestration

Built 2026-09-04 from a real end-to-end session running `fact_demand_consumption_plt` across
DEV/UAT and tracing a 2-year staging-extract staleness gap. Distills what's actually true about
this platform's execution model — not assumed from job/pipeline names.

## 1. The three environments, and how to get access

Three fully separate Azure subscriptions/Databricks workspaces/Synapse workspaces, same AAD tenant
(`hologic.onmicrosoft.com`, tenant `0553647d-4da8-44a1-9fed-7b122277b6b0`):

| Env | Databricks host | Synapse workspace | Azure subscription |
|---|---|---|---|
| DEV | `adb-6617965257274108.8.azuredatabricks.net` | `holx-hda-mde-synw-dev-01` | `2bbb7d70-36d4-4cf3-98b9-435c7af96e64` |
| UAT | `adb-7982886777824011.11.azuredatabricks.net` | `holx-hda-mde-synw-uat-01` | `8b922e72-a4c9-4ff6-b87a-dd1fb6b31edf` |
| PRD | `adb-685145432798888.8.azuredatabricks.net` | (assume `holx-hda-mde-synw-prd-01`, unconfirmed) | `0a513baa-a64e-461d-80be-1820831bbe67` |

Catalogs follow the same pattern: `mde_dev`, `mde_uat`, (presumably `mde_prd`).

**Setup (one-time per machine):**
```bash
databricks auth login --host https://adb-<workspace>.<n>.azuredatabricks.net --profile <DEV|UAT|PRD>
```
Saves to `~/.databrickscfg` — durable across sessions, not tied to any one Claude Code conversation.

Azure CLI (`az`) — install via `winget install -e --id Microsoft.AzureCLI --silent
--accept-package-agreements --accept-source-agreements` if missing, then `az login
--allow-no-subscriptions` (interactive, opens a browser). Also durable (`~/.azure/`). Then, per
environment: `az account set --subscription <sub-id-from-table-above>` before any `az synapse ...`
call — pipeline runs are scoped to whichever subscription/workspace they actually ran in.

**Git Bash gotcha**: a bare leading `/` in a `databricks workspace ...` path gets mangled into a
Windows path by MSYS. Prefix with `MSYS_NO_PATHCONV=1`.

**Databricks MCP tool vs CLI**: the `mcp__databricks__*` MCP tools can be IP-ACL-blocked for a given
machine/workspace even when the CLI works fine (different network path). If an MCP call fails with
"Source IP address ... is blocked by Databricks IP ACL", fall back to the `databricks` CLI via Bash.

## 2. The orchestration layer is Azure Synapse, NOT raw Databricks Jobs

`databricks jobs list --profile <UAT|PRD>` returns **empty** — there's no persisted Databricks Job
object per notebook to just "run by name" in these environments. Everything real is triggered
through two generic, metadata-driven Synapse pipelines:

### `Transform_Databricks_Notebook_PL` — runs a Silver/Gold/Platinum notebook
```bash
az synapse pipeline create-run --workspace-name <synapse-workspace> \
  --name Transform_Databricks_Notebook_PL \
  --parameters '{"ShortName":"AzureDatabricks","TransformName":"<bare notebook name, e.g. fact_demand>"}'
```
Internally: a Lookup activity (`LookupTransformationMetadata`) calls stored proc
**`[state].[TryGetTransformProcess]`** in an Azure SQL "state" database (via linked service
`StateDb_LS`), keyed on `(ShortName, TransformName)`. That row supplies:
- `TransformReference` — the actual Databricks notebook path (so this table is what maps a bare
  `TransformName` to `/DataEngineering/.../fact_demand`)
- `DataLakeCatalogName` — becomes the notebook's `catalogName` widget (this is where `mde_uat` vs
  `mde_dev` actually comes from — the notebook itself does NOT know its own environment)
- `LoadType` — becomes the `loadType` widget, a string `"F"` (full) or `"I"` (incremental)
- `CalculatedComputeSize` — drives cluster sizing (worker count, SingleNodeJob vs MultiNodeJob)
- `TransformId`/`TransformProcessId` — state tracking, logged via
  `[state].[AddUpdateTransformProcessStatus]` (PROCESSING → DONE/FAILED, captures `runError` and
  `runPageUrl` on failure)

### `ExtractAndLoad_PL` — runs a Bronze/staging extract from a source system
```bash
az synapse pipeline create-run --workspace-name <synapse-workspace> \
  --name ExtractAndLoad_PL \
  --parameters '{"ObjectName":"<SOURCE_TABLE_NAME>","ObjectSchema":"<source schema>","ShortName":"<source system short name>"}'
```
Only 3 parameters total (confirmed via the pipeline's own parameter schema — nothing hidden).
Internally calls `Extract_Oracle_Standard_PL` (or the equivalent for the source type), whose
`GetObjectMetadata` activity calls stored proc **`[state].[GetObjectForExtract]`** — same `[state]`
Azure SQL database, keyed on `(objectName, objectSchema, shortName)`. Supplies `LoadIncremental`
(boolean) and a watermark column, among other fields.

Known working `ShortName`/`ObjectSchema` conventions (confirmed via real recent runs, not guessed):
- Oracle EBS core financials: `ShortName: Oracle_EBS`, `ObjectSchema: APPS` (e.g. `GL_JE_HEADERS`)
- ASCP (Advanced Supply Chain Planning): `ShortName: ASCP`, `ObjectSchema: APPS` (e.g.
  `MSC_PLANS`, `MSC_FORECAST_UPDATES`, `MSC_FULL_PEGGING`, `MSC_PERIOD_START_DATES`)
- A whole source system can be run as a batch: `ExtractAndLoad_RunShortName_PL {"ShortName":
  "ASCP", "LoadGroup": "1"}` — but a batch run silently EXCLUDES any object not registered in
  `[state]` for that ShortName (see §4) — no error, no alert, it just never gets attempted.

**Don't guess parameters cold.** Before triggering any object for the first time, pull recent
pipeline runs and find a working sibling to copy the exact convention:
```bash
az synapse pipeline-run query-by-workspace --workspace-name <ws> \
  --last-updated-after <ISO8601> --last-updated-before <ISO8601>
```
(No `--filters` needed for this — that flag takes `KEY=VALUE` syntax, not JSON, and errors
unhelpfully if you pass JSON. Just pull a window and grep locally.) **Note: Synapse's pipeline-run
monitoring history only retains ~45 days** — a run older than that returns `Not Found` even by
exact run ID. For anything older, check the target Delta table's own `DESCRIBE HISTORY` instead
(retained independently, not subject to Synapse's retention) — the `job` column's
`jobName`/`runId` reveals which pipeline/run actually wrote that data, confirming object identity
even when the literal historical parameters are unrecoverable.

## 3. Diagnosing the "firstRow doesn't exist" failure — a registration gap, not a code bug

Both pipelines fail the same distinctive way when their target `TransformName`/`ObjectName` has no
matching row in `[state]`:
```
Operation on target RecordStartOfTransformation failed: The expression
'activity('LookupTransformationMetadata').output.firstRow.DatabaseId' cannot be evaluated because
property 'firstRow' doesn't exist, available properties are 'effectiveIntegrationRuntime,
durationInQueue'.
```
(Extract-side: same shape, `GetObjectMetadata`/`GetWaterMark`/`LoadIncremental` instead.)

**This means the Lookup query returned zero rows** — the object was never registered in `[state]`,
or its registration was removed/deactivated. It is a **completely different failure class** from
"notebook not deployed to the workspace" (`Unable to access the notebook "..."`) — different owner,
different fix:
- "Unable to access the notebook" → someone needs to push the notebook file to the target
  workspace (a git-deploy problem).
- "firstRow doesn't exist" → someone with `[state]` database write access needs to INSERT a
  registration row (an orchestration-config problem, unrelated to whether the code exists).

**This failure happens fast** (within the first ~30 seconds, before any Databricks cluster spins
up) — so test-triggering a batch of objects to check registration status is cheap even for objects
whose upstream dependencies aren't ready yet; a Lookup-stage failure doesn't burn real cluster time.

**I do not have write access to `[state]`** and have never found who does in-session — this always
needs to go back to whoever owns/administers that Azure SQL database (ask the person who set up the
Synapse pipelines, or the person who does DEV→UAT/PRD promotions).

## 4. Run-date vs. data-date: two very different freshness questions

"Did fact_demand run today?" (yes, probably — `DESCRIBE HISTORY <table>` shows a `CREATE OR REPLACE
TABLE AS SELECT` today) is a **completely different question** from "is the data in fact_demand
current?" — a Gold transform can run flawlessly every day forever and still only ever reprocess
stale Bronze data if the upstream extract is broken. Always check both:
```sql
-- run freshness (when did the transform last execute)
DESCRIBE HISTORY <catalog>.<schema>.<table> LIMIT 5  -- look for CREATE OR REPLACE TABLE AS SELECT / MERGE, not VACUUM (housekeeping, not data)

-- data freshness (how current is the actual business data)
SELECT max(LastUpdateDate), max(CreationDate) FROM <table>  -- NOT a forward-looking planned/due date column
```
Trace staleness to its root by walking the Bronze → Silver → Gold chain and checking each layer's
own `DESCRIBE HISTORY`/max-date — the `job` field on each version shows exactly which upstream
pipeline/run produced it, letting you find precisely where the chain actually stalled.

## 5. A PR diff's file paths are NOT the ground truth for what's currently deployed

Once meaningful time has passed since a PR was authored, the actual deployed implementation can
diverge from what the diff shows — folders get flattened, prefixes get dropped, a single view can
get split into two. Live-verified example: a PR added
`MetricViews/OPS_Manufacturing_Variance/mv_ops_gl_journal.sql`, but the real deployed object is
flat at `MetricViews/mv_ops_gl_journal` (no subfolder); another PR's
`Silver/v_trn_oracle_ebs_gmf_xla_opm_subledger` was refactored into two separate views,
`_extract_headers` + `_extract_lines`, discoverable only by reading the live downstream notebook's
own docstring ("Split into two 1:1 Silver views").

**Don't conclude "missing" from a per-path `get-status` check alone.** If an expected path 404s,
`list` the parent folder to look for a rename before reporting a gap, and re-derive real
dependencies by exporting and reading the CURRENTLY deployed notebook's actual `FROM`/`JOIN`
clauses — not the dependency set implied by an old PR diff.

## 6a. A notebook's filename is NOT always the real object name it manages

Real mistake, 2026-09-26: flagged `platinum.dim_customersite_uses_plt` as a reproducing framework
anomaly (`[state]` reported `Succeeded`/no error twice, but nothing existed under that name in
`mde_uat`) — treated it as a platform bug worth escalating. It wasn't. Reading the actual notebook
source showed it doesn't `CREATE`/`CREATE OR REPLACE` anything named `dim_customersite_uses_plt` at
all — it runs `ALTER VIEW` against three pre-existing, differently-named views
(`platinum.v_dim_billto`/`v_dim_shipto`/`v_dim_deliverto`), each commented `ALTER VIEW, not CREATE
OR REPLACE: this view is Delta-Shared and UC blocks a DROP+CREATE against an actively shared
securable`. The pipeline had been succeeding the whole time; checking `last_altered` on the three
real view names (matching the exact trigger timestamp) confirmed it. **Before declaring any object
"missing" or "anomalous" from a folder+filename-based name guess, read the notebook's actual
`CREATE`/`CREATE OR REPLACE`/`ALTER` statements and check catalog existence under the name it
really writes to** — this is the same discipline as §5 (don't trust a PR diff's paths) one level
deeper: don't trust the *notebook's own filename* either when its body targets something else,
which is more likely for `ALTER VIEW`-pattern notebooks (Delta-Shared objects, view-only wrappers)
than for a normal `CREATE OR REPLACE TABLE`/`CREATE OR REPLACE VIEW` object.

## 6. Verification checklist before reporting an object "done" or "blocked"

1. Notebook file exists at the expected path in the target workspace — `databricks workspace
   get-status`, cross-checked with a folder `list` if the direct path 404s (see §5).
2. Object is registered in `[state]` for that environment — inferred from whether
   `Transform_Databricks_Notebook_PL`/`ExtractAndLoad_PL` gets past the Lookup step (see §3).
3. All of the notebook's OWN dependencies (read from its real current source, not an old diff) also
   pass #1 and #2 — trace the full chain, don't stop at the first table.
4. After a "Succeeded" pipeline status, verify the actual table with a real `SELECT count(*)` (and
   a relevant max-date) against the target catalog — a green pipeline status is not itself proof of
   real data; confirm the artifact, not just the run outcome.

## 7. Multi-object dependency-aware trigger sweep ("the whole lineage" procedure)

Live-proven 2026-09-25 promoting Sameet's Qlik Retirement PR bucket to UAT: 27 Silver views → 12
Gold dims/facts → Platinum, ~90 objects total, zero blind fires. **Never trigger a batch of objects
by just firing every registered TransformName in parallel** — build the real dependency graph
first, execute it layer by layer, and verify each layer landed before starting the next. Sameet's
own words: *"you cannot just run gold directly... you have to first go and open up the gold and
check what are the silvers, then check if the silver tables are available or not... if it's not
available, then you have to run the silver first."*

**Step-by-step, for a batch of N target Gold/Platinum objects:**

1. **Resolve the real dependency for every target**, not a folder-convention guess:
   - Fastest source: if the object was already attempted, its own captured `state.TransformProcess`
     error often names the exact missing dependency verbatim (`TABLE_OR_VIEW_NOT_FOUND
     silver.v_mst_...` / `gold.dim_...`) — read it before doing anything else, it's a free answer.
   - Otherwise, export and read the real current notebook source (`databricks workspace export
     <path> --format SOURCE`) and grep its `FROM`/`JOIN`/YAML `source:` for the real upstream
     table(s) — never infer from the object's name or folder alone.
2. **Dedupe.** Multiple Gold/Platinum objects often share one upstream Silver/Gold dependency (e.g.
   one Silver view feeding both a Gold fact and, transitively, a Platinum object; one Gold dim
   feeding two Platinum facts). Build a single name→dependents map so each shared node is verified
   and triggered exactly once, not once per downstream consumer.
3. **Layer the plan**: Silver (leaf nodes, Bronze-only reads) → Gold (reads Silver, possibly other
   Gold) → Platinum (reads Gold, possibly other Platinum). Within a layer, objects with no
   dependency on each other fire in parallel (verify this — grep each candidate's source for
   cross-references to the others in the same wave, don't assume independence); an object that
   depends on a sibling in the same layer (e.g. a Gold dim reading another Gold dim) waits for that
   sibling specifically, not the whole layer.
4. **Before firing ANY object**, confirm both (§6 #1-2, restated as a hard gate here): the notebook
   file really exists in the target workspace (not just registered in `[state]`, see the
   registration-vs-existence rule in `sameet-check-statedb-before-synapse-trigger-rule` memory), and
   its resolved dependency (step 1) is CURRENTLY live in the target catalog. If the dependency is
   not live, recurse: apply this whole procedure to the dependency first, wait for it to verify
   live, then proceed.

   **Real mistake, 2026-09-25 (Sameet's direct correction) — this gate must actually block firing,
   not just get documented and overridden.** During a 9-object Platinum wave, 7 of 9 were fired
   despite ALREADY having a captured, unchanged root cause on record (a missing notebook, a known
   code bug, or a cascade off a Gold object with an already-known unchanged bug) — reasoning at the
   time was "fire everything so every error is freshly tracked." That reasoning is wrong: if the
   root cause is already captured AND nothing upstream of it changed since, firing again burns real
   cluster time (~13-15 min each) to reproduce information already in hand. Sameet: *"you're not
   checking the dependency... you have to check the dependency first, na?"* **The corrected rule:
   only fire an object when there is a genuine reason the outcome might differ from what's already
   known** — a dependency you just fixed this session, the object's first-ever attempt, or a
   deliberate re-check of something suspicious (like the anomaly in §8). If the dependency check
   in this step comes back "still broken, nothing changed" — record the ALREADY-CAPTURED error in
   the tracker directly and skip the trigger; don't re-run to "get a fresh timestamp" on an answer
   that hasn't changed.
5. **Go one more layer down than "Gold reads Silver" suggests — check Bronze too.** A Silver view
   can create successfully and return real rows while still reading a Bronze `stg_*` table that's
   registered `IncludeInLoad=False` in `state.ObjectList` (extract-excluded) and frozen months or
   years old. This doesn't block the Silver view from building, but it means "available" is not the
   same as "fresh" — check `state.ObjectList.IncludeInLoad` and a real `DESCRIBE DETAIL
   <table>.lastModified` for the Bronze sources feeding any Silver view in the sweep, and report
   staleness as its own finding even when everything technically succeeded.
6. **After each layer completes, verify with an independent catalog diff** — snapshot
   `information_schema.tables` before the layer starts and after it finishes; the true "succeeded"
   count is objects that newly appear, not the pipeline's own reported status count (a poll script
   bug, an ID-matching bug, or a job-owner permission gap can all make Synapse's own status
   unreliable to trust blindly — the catalog is the ground truth). Only then start the next layer.
7. **Track every object** (PR, layer, object name, notebook-exists Y/N, registered Y/N, triggered
   Y/N + real runId, final status, real captured error text) in a living tracker — every attempt,
   including ones you're confident will fail, so the current real error is on record for later
   debugging rather than re-derived from memory next time.

**Don't re-discover this each session.** This section exists so the check-Silver-before-Gold
discipline is automatic, not something Sameet has to restate — if this procedure gets extended or
corrected in a future session, update this section in place rather than leaving the improvement
stranded in a session memory note.
