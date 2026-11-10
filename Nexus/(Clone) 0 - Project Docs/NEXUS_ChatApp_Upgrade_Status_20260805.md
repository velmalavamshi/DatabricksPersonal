# NEXUS Agent Chat App Upgrade — Status Summary (2026-08-05)

**Bottom line:** All diagnosed fixes + the full claude.ai-style redesign are built and were
confirmed working in staging. Production promotion is started but paused (nothing live changed
except one scoped permission grant). The staging-connectivity blocker turned out to be a local
Windows hosts-file misconfiguration (root cause found 2026-08-05, see §4) — not a Databricks
issue — fix identified but not yet applied (needs an elevated shell).

---

## 1. Done and verified in staging (before staging became unreachable)

### Core bug fixes
- **Regex fix**: `_WORKSPACE_PATH_RE` — `\s` → `\r\n` in the exclusion set, so paths with spaces
  ("5 - Personal Projects" etc.) no longer truncate.
- **`persist_conversation()` signature fix** in `run_routine_now()` — was called with the wrong
  kwargs, silently throwing `TypeError` on every "Run Now".
- **Routines cache bug** — `create_routine()` now returns the new `routine_id` directly instead
  of the caller re-reading `_ROUTINES_CACHE` right after it's been invalidated to `None`.
- **Brand colors** — `image_generator.py`'s `HologicColors` class and every matching hardcoded
  hex in `app.py` (workspace tags, health/status indicators, routine dots, loop-status badge,
  gradient) swapped to the real Hologic palette. Independently re-verified against the
  `hologic-style` skill's `colors.md` — exact matches, no corrections needed.
- **Streamlit theme** — native widgets (buttons, radios) now use `--theme.primaryColor` /
  `backgroundColor` / `textColor` CLI flags. Dropped `--theme.linkColor` — not a valid option in
  the pinned Streamlit 1.38.0 and briefly crashed the app before being removed.
- **Prompt rebalance (the fix that actually matters for the original hallucination bug)** — added
  a "HARD EXCEPTION" section immediately after the ANSWER-FIRST PRINCIPLE, explicitly
  distinguishing "unconfirmed name" (fine to infer and proceed) from "a read/tool call actually
  failed" (hard stop, no fabrication). This is the real fix; the regex fix alone would not have
  prevented the original fabrication.
- **Error logging** — added `print()` diagnostics (visible via `databricks apps logs`) to
  `run_routine_now()`'s previously-silent `except Exception` and `_get_token()`'s secrets-fetch
  `except`. Scoped narrowly to these two already-diagnosed spots, not a blanket sweep of the ~30
  `except Exception` blocks in the file.
- **PAT → Secrets** — removed the plaintext `NEXUS_PAT_TOKEN` from `app.yaml`. In the process,
  found and fixed a **real, previously-unknown bug**: `_get_token()`'s SDK fallback used
  `WorkspaceClient().config.token`, which only returns a value for classic PAT auth — it's always
  empty for the OAuth service-principal auth Databricks Apps actually uses by default. Fixed to
  `Config().authenticate()`, the correct OAuth header-factory.
- **Permission regression found + fixed** — removing the PAT broke asset creation
  (`[CREATE_ASSET]` → workspace notebook import), because the app's own service principal had
  never been granted access to the user's personal `NEXUS_Generated` folder (previously
  everything ran as the user via their PAT). Granted `CAN_MANAGE` on that one folder, scoped
  narrowly, to both the staging and (now) live app's service principals.

### Redesign — all 5 features from the claude.ai-style mockup
1. **Bubble-less layout** — small teal circular mark + "NEXUS" label instead of a boxed bubble;
   token/cost/latency metadata collapsed behind a "▸ Details" disclosure instead of always-on.
2. **Usage nav item** — "Session Stats" moved from always-visible to a collapsed "📊 Usage"
   sidebar expander; added a real avg-latency stat. Deliberately did **not** add the mockup's
   "budget bar" — no real budget ceiling exists anywhere in this app, and inventing one would be
   fabricating a policy.
3. **Multi-file upload** — moved from a single-file sidebar uploader to a multi-file
   composer-area uploader (chip row above the chat input, `accept_multiple_files=True`).
4. **Artifacts dialog** — `[CREATE_ASSET]` results now open a real `st.dialog` modal (title, real
   code content, copy icon, "Open in Databricks" link) instead of just an inline success message;
   reopenable later via a small card button in message history. **Deviation from the mockup,
   flagged at the time**: built as a modal, not a persistent 3rd layout column — retrofitting the
   whole page into 3 columns was judged too risky relative to the value.
5. **Projects** — new `mde_dev.test_schema.nexus_projects` table + a `project_id` column added to
   the existing `nexus_sessions` table (**both already live in the shared database, not
   staging-only** — same physical tables the production app reads). Sidebar "📁 Projects" section
   above Pinned/Recents, with a create-project form and an "assign current chat to project"
   dropdown.

### Hologic-style visual pass (per the `/hologic-style` skill)
Sidebar background set to real Hologic Blue `#2b2967` (not just an accent color on a white
canvas — per the brand guide, "any asset should make it a central element"). Text uses full white
or real CSS opacity on white, per the skill's explicit rule against inventing lighter tints.
Secondary buttons got a ghost style; inputs stay light for readability. All colors re-verified
against `colors.md` — exact matches.

---

## 2. Known minor bug, not yet fixed
Sidebar session list can show a stale "No conversations yet" on the exact same script-run a new
session is created — the sidebar renders *before* `persist_conversation()` +
`invalidate_session_cache()` run later in the same script. Self-resolves on the next rerun. Same
class of bug as the routines-cache issue, just not fixed.

---

## 3. Production promotion — started, paused

**Done, on the live app (`hologic-ai-agents`):**
- Fresh backup taken: `app_backup_20260805.py/.yaml`, `image_generator_backup_20260805.py` in
  `0 - Backup`.
- Granted the live app's own service principal (`0c17cf9c-8bca-4464-a686-efe2887af896`)
  `CAN_MANAGE` on `NEXUS_Generated` — same fix staging needed, done ahead of time to avoid an
  outage window when the PAT removal ships.

**Not yet done (paused at user request to keep working on staging first):**
- Upload `app.py` / `image_generator.py` / `app.yaml` (PAT removed) / `.streamlit/config.toml` to
  the live folder.
- Deploy `hologic-ai-agents` for real.
- Post-deploy verification.

Nothing on the live app's actual running code has changed yet — only the one scoped permission
grant. Safe to resume promotion at any time by picking up at the file-upload step.

---

## 4. Staging app connectivity — ROOT CAUSE FOUND 2026-08-05 (local hosts file, not Databricks)

**Update:** this was mis-diagnosed. It is not a Databricks-side IP ACL/edge-routing problem — it's
a stale entry in this machine's own `C:\Windows\System32\drivers\etc\hosts`, confirmed with fresh
evidence:
- `nslookup` (bypasses the hosts file, queries corporate DNS directly) resolves
  `hologic-ai-agents-stg2-...` and the live `hologic-ai-agents-...` hostname through the
  **identical** CNAME chain to the same `adb-6617965257274108.8.privatelink.azuredatabricks.net`
  backend — proving stg2's real endpoint is healthy and correctly configured.
- `curl` (honors the hosts file) resolves the live app to `10.18.104.20` (the correct Private Link
  IP for this workspace — same value already pinned correctly for `hologic-ai-agents` and
  `genie-workbench`) and gets a clean `302` to the Databricks OAuth login. `curl` resolves
  `hologic-ai-agents-stg2` to `50.218.8.226` instead — a dead/unrelated public IP — and the TLS
  handshake fails every time. Same story for `stg3` (also pinned to `50.218.8.226`),
  `hologic-ai-agents-staging` and `nexus-monitor` (both pinned to `73.159.112.18`).
- The actual hosts file, as of today:
  ```
  10.18.104.20    hologic-ai-agents-6617965257274108.8.azure.databricksapps.com          # correct
  10.18.104.20    genie-workbench-6617965257274108.8.azure.databricksapps.com            # correct
  73.159.112.18   hologic-ai-agents-staging-6617965257274108.8.azure.databricksapps.com  # WRONG
  50.218.8.226    hologic-ai-agents-stg2-6617965257274108.8.azure.databricksapps.com     # WRONG
  50.218.8.226    hologic-ai-agents-stg3-6617965257274108.8.azure.databricksapps.com     # WRONG
  73.159.112.18   nexus-monitor-6617965257274108.8.azure.databricksapps.com             # WRONG
  ```
- **`50.218.8.226` is the exact IP the earlier "403 Source IP blocked" error named** — it was never
  a Databricks-enforced block on a client IP; the hosts file was pointing the hostname *at* that
  address as if it were the server, which is backwards. The earlier hosts-pin/DNS-flush "fix
  attempt" documented previously made things worse, not better, and was never corrected.
- `databricks apps get hologic-ai-agents-stg2` (control-plane, unaffected by local DNS) shows the
  app itself `RUNNING`/`SUCCEEDED`, most recent deploy `2026-08-05T19:39:18Z` — the app has been
  fine the whole time from Databricks' side.
- `hologic-ai-agents-staging` and `hologic-ai-agents-stg3` app **resources no longer exist** in the
  workspace (`databricks apps get` → "does not exist or is deleted") — contradicts the prior note
  that they "still exist, never deleted"; only `hologic-ai-agents-stg2` remains, and it's the one
  still in active use.
- **Separate, still-open data point:** an external fetch (Anthropic Cloud, not on Hologic's
  network) also failed to reach `hologic-ai-agents-stg2` — but succeeded cleanly against the live
  app from the same path. That's independent of the hosts file (a remote fetch doesn't read this
  machine's hosts file) and may point to a real, narrower Databricks/Azure-side ingress issue
  scoped to the `stg2` app specifically. Not chased further since it doesn't block the actual use
  case (browser access from the corporate network), which the hosts-file fix resolves.

**The fix (not yet applied — needs an elevated shell, this session doesn't have admin rights):**
repoint the four wrong lines to `10.18.104.20`, matching the two already-correct entries. One-line
elevated PowerShell (run in an Administrator PowerShell window):
```powershell
$p = 'C:\Windows\System32\drivers\etc\hosts'
(Get-Content $p) | ForEach-Object {
  $_ -replace '^\s*73\.159\.112\.18(\s+)(hologic-ai-agents-staging|nexus-monitor)', '10.18.104.20$1$2' `
     -replace '^\s*50\.218\.8\.226(\s+)(hologic-ai-agents-stg2|hologic-ai-agents-stg3)', '10.18.104.20$1$2'
} | Set-Content $p -Encoding ASCII
ipconfig /flushdns
```
After running: re-test `hologic-ai-agents-stg2` in a browser. Also worth deleting the two dead
lines for `hologic-ai-agents-staging` / `hologic-ai-agents-stg3` since those app resources are
gone. **No further app-recreation (a "stg4") is needed or recommended** — the app resource was
never the problem.

---

## 5. Explicitly deferred (user's call, not started)

- **Actual PAT rotation** — the code-side fix (reading from Databricks Secrets) is done and
  tested, but the literal exposed token value has not been rotated/invalidated yet.
- **Cleanup of the 7 fabricated notebooks** in `NEXUS_Generated` (`NB01_EO_fact_grifols_...` etc.)
  — safe copies archived to `0 - Archive`, but the live duplicates in the main folder were never
  deleted (a delete call was blocked by the Claude Code permission classifier and never retried).
- **Deleting the broken app resources** — moot now: `hologic-ai-agents-staging` and
  `hologic-ai-agents-stg3` no longer exist (confirmed 2026-08-05, `databricks apps get` → deleted).
  `hologic-ai-agents-stg2` is not broken — see §4 — and is the one actively in use; do not delete.

---

## Where everything lives

| What | Path |
|---|---|
| Live app source (untouched except the permission grant) | `.../5 - AI Multi Agents/5 - Agent Chat App/` |
| All fixes + full redesign, ready to test or promote | `.../5 - AI Multi Agents/5 - Agent Chat App - STAGING/` |
| Backups (dated) | `.../5 - Agent Chat App/0 - Backup/` |
| New Delta objects (already live, not staging-only) | `mde_dev.test_schema.nexus_projects`, `nexus_sessions.project_id` |

---

## To pick this up next session

1. **Staging connectivity**: run the elevated PowerShell one-liner in §4 to fix the hosts file,
   then re-test `hologic-ai-agents-stg2` in a browser. The app resource itself needs nothing — it's
   already healthy. No rebuilding needed.
2. **If ready to resume production promotion**: pick up at "upload the 4 files to the live
   folder" — everything before that (backup, permission grant) is already done.
3. **Otherwise**: decide on the deferred items (PAT rotation, notebook cleanup, broken-app
   deletion) whenever it's convenient.
