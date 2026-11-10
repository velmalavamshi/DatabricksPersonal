# NEXUS chat app — rollback runbook

**App:** `hologic-ai-agents-v4` (DEV workspace, CLI profile `DEV`) · **Owner:** Sameet Patel · **Written:** 2026-10-08 (G-08)

## Where the rollback copies live

Every `apps deploy` leaves a complete snapshot of the app's source in the Workspace, owned by the app's service principal:

`/Workspace/Users/5ab326f3-eaa2-41b7-84a5-ff58a9e68b55/src/<deployment_id>/`

Each snapshot holds `main.py`, `app.yaml`, `static/` (the built frontend) and every module. As of 2026-10-08 there are
**115 snapshots**. **76 of them still hold the legacy pre-React frontend** (`static/app.js`); the newest of those is
`01f1b74189db1d859dc849008fa0a261` (before the 2026-09-23 React cutover). Rollback therefore needs nothing from anyone's
laptop. The local `backups/` folders in `NEXUS_V4_Upgrade\` are a second copy, not the primary one.

## When to roll back

Roll back the latest deploy if, within 30 minutes of it, any of these holds and a fix isn't a few minutes away:

1. The app isn't `RUNNING`, or `/api/health` isn't `"status": "ok"`.
2. A real chat turn fails (error event, empty answer, or the page doesn't load) for a case that worked before.
3. A security or permission regression: a user can see or do something they couldn't before (another user's chats,
   writes outside their folder, notebook rights for a business user).
4. Several users report the same new failure.

A single user's slow turn, or a model/FMAPI outage that also affects the previous version, is **not** a reason to roll back.

## How to roll back

1. **Find the previous good deployment:**
   `MSYS_NO_PATHCONV=1 databricks apps list-deployments hologic-ai-agents-v4 --profile DEV`
   Pick the newest `SUCCEEDED` deployment before the bad one. Its snapshot path is shown under `deployment_artifacts.source_code_path`.
2. **Check nothing is mid-turn:** `py ci/idle_check.py` (in `NEXUS_V4_Upgrade\`; exit 0 = idle). A deploy kills any turn in flight.
3. **Deploy the snapshot:**
   `MSYS_NO_PATHCONV=1 databricks apps deploy hologic-ai-agents-v4 --source-code-path "/Workspace/Users/5ab326f3-eaa2-41b7-84a5-ff58a9e68b55/src/<previous_deployment_id>" --profile DEV`
4. **Verify:** app `RUNNING`, `/api/health` ok, one real chat turn works.
5. **Record it:** TRACKER.md deployment log + the daily log, with the bad deployment id and the reason.

**Important:** the next normal deploy uses the main source folder
(`.../5 - AI Multi Agents/5 - Agent Chat App - V4`) again, so the bad change is still there. Fix or revert it in that
folder (and in `deployed_snapshot\`) before the next deploy.

## Status of this runbook

- Snapshots verified readable and complete on 2026-10-08 (read-only check).
- **A rollback deploy from a snapshot path has not been exercised yet.** Doing so restarts the app and would kill users'
  running turns, so it should be tried in a quiet window (or the first time it's genuinely needed).
- Not built: feature flags / staged rollout (G-08 remainder).
