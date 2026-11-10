---
name: hologic-pr-review-fixes
description: Use whenever asked to check/fix/address PR review comments on a Databricks notebook in the HDA_MDE repo — finding the active PR touching a file, pulling real reviewer comments, fixing each against the hologic-databricks-standards skill with live verification, pushing, and replying to/resolving each thread with what was actually done. Trigger on "PR comments", "PR review", "address review feedback", "fix the PR", "reviewer left comments", or any ask to work through feedback on an open ADO pull request in this repo.
---

# Hologic PR Review Fixes

Codifies the exact sequence used 2026-09-03 to fix real reviewer comments on
`fact_servicerequest.sql` (PR #4402) — 3 real bugs (missing datetime import, missing
TBLPROPERTIES keys, a genuine duplicate-PK fan-out), each fixed, live-verified, pushed, and
closed out on the actual PR thread. Repeat this sequence for any future PR review pass in
HDA_MDE, not just this one incident.

**Always load `hologic-databricks-standards` alongside this skill** — that skill is the
reference every comment gets checked against, and the place new patterns get fed back into
(§7 below).

## 1. Find the real PR and the real (non-deleted) threads

- List PRs on the repo (`GET .../pullrequests?searchCriteria.status=all`) to find the one
  whose `sourceRefName` matches the branch actually being worked, and whose title/diff plausibly
  covers the file in question. **Don't assume "no PR opened" from an old handoff note** — branches
  in this repo can pick up a PR at any point; verify live.
- Pull that PR's comment threads (`GET .../pullRequests/{id}/threads`) and filter to
  `threadContext.filePath` matching the target file.
- **A thread can be `isDeleted: true`** (the reviewer removed their own comment) — these show
  `content: undefined` in a naive extraction. Always fetch the full raw thread JSON and check
  `isDeleted` before treating a thread as real feedback to act on. Skip deleted threads entirely.
- Note each live thread's `threadContext.rightFileStart.line` (or `leftFileStart` for a
  comment on removed code) to locate exactly what it's about in the current file.

## 2. Get the canonical file content, not a possibly-stale mirror

Fetch the file directly from the PR's source branch via the Items API
(`versionDescriptor.version=<branch>&versionDescriptor.versionType=branch&includeContent=true`),
not from a Databricks Repos workspace mirror that might be a commit or two behind. Same
canonical-source discipline as any other push in this codebase.

## 3. Cross-check every comment against `hologic-databricks-standards`, fix with live verification

For each real comment:
- Identify which standard it maps to (missing datetime boilerplate → §10.6; missing
  TBLPROPERTIES keys → §6; a join fan-out → §10.7 and the medallion/grain guidance).
- **Don't just patch the symptom — verify the real root cause live** before writing the fix,
  the same discipline as any other bug fix in this codebase: `count(*) = count(distinct <key>)`
  before AND after a proposed dedup fix, not just after. If the comment flags a duplicate-key
  bug, find the actual duplicated rows and diff them to see what really varies (this program's
  established working pattern for grain bugs) rather than guessing a filter.
- Syntax-check the fixed notebook's embedded Python cells locally (per
  `hologic-databricks-standards` §10.3) before pushing.

## 4. Push, deploy, and independently verify — never trust job status alone

- Push via the proven ADO REST API method (local PowerShell + Node + `Get-AdoPat`, or
  server-side `execute_code` if the content already lives in Databricks — see
  `ado-devops-org-info` memory for the exact mechanics).
- Deploy via a real one-time GIT-sourced job pointed at the PR's branch — never patch the live
  table with ad-hoc SQL and leave the notebook stale.
- **Independently re-verify the live result** (`count(*) = count(distinct <sk>)`, a spot-check
  of real rows) — this program's `LakeOrchestrator.exit_with_status` has a known cosmetic bug
  that reports SUCCESS jobs as FAILED and vice versa is not proven safe either; job status alone
  is never sufficient evidence.

## 5. Reply to each thread with what was actually done, then mark it fixed

- One reply per thread (`POST .../pullRequests/{id}/threads/{threadId}/comments`,
  `parentCommentId: 1`), stating the concrete fix and citing the real verification numbers (row
  counts, commit hash) — not just "fixed."
- Set the thread status to `fixed` (`PATCH .../threads/{threadId}` with `{"status": "fixed"}`).
  Only do this after the push AND the live re-verification both succeeded — never mark a thread
  fixed on the strength of a job status alone.

## 6. Update ADO and memory the same way every other real fix in this program does

- If a task exists for the object, add a substantive comment (root cause, before/after numbers,
  commit hash) — matching this program's ADO detail preference, not a terse "done."
- If the fix reveals something that could recur elsewhere (a framework gap, a naming
  assumption that turned out wrong), log it — a `Parking Lot Notes` item if it's visible-to-team
  worthy, a memory file if it's session-continuity detail.

## 7. Feed newly-discovered patterns back into `hologic-databricks-standards`

Every real bug a reviewer catches that an automated check *could* have caught is a gap in the
standards skill, not just a one-off fix. Add it as a new numbered item under the skill's §10
(Verification discipline) or the relevant existing section, with the real example (file, PR
number, what was wrong, what the live counts were before/after) — same pattern already used for
the missing-datetime and TBLPROPERTIES-keys findings. The goal is that the *next* notebook never
ships with the same class of bug, not just that this one got fixed.

## Known gotchas carried over from this program's other work (check these apply before assuming)

- `manage_workspace_files upload` + a raw git push together can produce duplicate
  double-extension files (`name.sql.sql`) — build content directly and push via the ADO REST API
  instead, per `qlik-opstrends-scrapmtl-scrapmdl-plt` memory.
- PowerShell's `ConvertTo-Json` can corrupt large JSON payloads — always use Node's
  `JSON.stringify` for the push payload, per `ado-devops-org-info` and `nexus-key-paths-reference`
  memory.
- A single-element PowerShell array collapses to a bare object under `ConvertTo-Json` (breaks
  ADO's `application/json-patch+json` body) — force array output with `@(,$singleOp)` if
  PowerShell-side JSON construction is used instead of Node.
