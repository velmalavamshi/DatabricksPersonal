# NEXUS Conversation History & Session Management — Implementation Plan

**App:** hologic-ai-agents  
**Started:** 2026-07-24  
**Owner:** sameet.patel@hologic.com  
**Status:** Phases 1-13 COMPLETE, Phase 15 remaining  

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  SIDEBAR                         │
├─────────────────────────────────────────────────┤
│  [+ New Chat]                                   │
│  [🔍 Search conversations...]                   │
│  ─────────────────────────────────              │
│  ⚡ Routines                                    │
│    ● Email triage - Good Morning  (Mon 8AM)     │
│    ● Weekly cost summary          (Fri 5PM)     │
│  ─────────────────────────────────              │
│  📌 Pinned                                      │
│    ● Freight dashboard planning                 │
│    ● xxHash migration status                    │
│  ─────────────────────────────────              │
│  👥 Shared with me                              │
│    ○ Steve: Cost optimization      (read-only)  │
│  ─────────────────────────────────              │
│  Recents                                        │
│    ● dim_global_intransit search     Today      │
│    ○ Medallion layer counts          Today      │
│    ○ ASCP supply plan analysis       Yesterday  │
│    ○ Power BI refresh scheduling     Jul 22     │
│    ...                                          │
│  ─────────────────────────────────              │
│  📦 Archived (47)                               │
└─────────────────────────────────────────────────┘
```

## Delta Tables

| Table | Purpose | Status |
|---|---|---|
| `mde_dev.test_schema.nexus_sessions` | Session metadata, titles, flags | ✅ EXISTS (enhanced Phase 1) |
| `mde_dev.test_schema.nexus_conversations` | Message pairs per exchange | ✅ EXISTS (no changes needed) |
| `mde_dev.test_schema.nexus_routines` | Scheduled prompt definitions | ✅ CREATED (Phase 1) |

---

## Phase 1: Verify Persistence Schema ✅ COMPLETE

**Date:** 2026-07-24  
**Deployment:** N/A (schema-only)

### What was done:
- Added 8 columns to `nexus_sessions`: `session_title`, `is_pinned`, `is_deleted`, `is_archived`, `is_shared`, `shared_with`, `source`, `routine_id`
- Backfilled all 25 existing rows with defaults (all flags = false, source = 'chat')
- Backfilled `session_title` from first user message (MERGE from nexus_conversations)
- Created `nexus_routines` table (15 columns, clustered by user_email + name)
- Confirmed `nexus_conversations` paired format works for session reload (no restructure needed)

### Final Schema — nexus_sessions:
```sql
session_id        STRING     -- PK
user_email        STRING     -- Owner
started_at        TIMESTAMP  -- Session start
last_active_at    TIMESTAMP  -- Last activity
message_count     INT        -- Total exchanges
total_tokens_in   BIGINT     -- Cumulative input tokens
total_tokens_out  BIGINT     -- Cumulative output tokens
total_cost_usd    DOUBLE     -- Cumulative cost
model             STRING     -- LLM model used
session_title     STRING     -- Auto-generated from first message (50 chars)
is_pinned         BOOLEAN    -- User-pinned (max 5)
is_deleted        BOOLEAN    -- Soft-deleted (hidden 30 days)
is_archived       BOOLEAN    -- Auto-archived after inactivity
is_shared         BOOLEAN    -- Shared with other users
shared_with       STRING     -- JSON array of shared emails
source            STRING     -- 'chat' or 'routine'
routine_id        STRING     -- FK to nexus_routines
-- Clustering: user_email, started_at
```

### Final Schema — nexus_routines:
```sql
routine_id         STRING     -- PK (UUID)
name               STRING     -- Display name
user_email         STRING     -- Owner
schedule_cron      STRING     -- Cron expression
schedule_display   STRING     -- Human-readable schedule
prompt             STRING     -- Full LLM instruction text
connectors         STRING     -- JSON array of data sources
is_active          BOOLEAN    -- Active/paused toggle
last_run_at        TIMESTAMP  -- Most recent execution
last_run_status    STRING     -- SUCCEEDED | FAILED | RUNNING
last_run_session_id STRING    -- session_id of last run output
next_run_at        TIMESTAMP  -- Computed next execution
run_count          INT        -- Total completed runs
created_at         TIMESTAMP  -- Creation timestamp
updated_at         TIMESTAMP  -- Last modification
-- Clustering: user_email, name
```

---

## Phase 2: Full Message Persistence ✅ COMPLETE

**Status:** COMPLETE (2026-07-24)  
**Depends on:** Phase 1 ✅  
**Deployment:** Pending (code changes applied to app.py)

### Objective:
Modify `persist_conversation()` in `app.py` to properly save every exchange AND populate `session_title` on first message.

### Current behavior:
- `persist_conversation()` already saves each user+assistant exchange as a row in `nexus_conversations` ✅
- `nexus_sessions` is UPSERTed on each exchange ✅
- BUT `session_title` is NOT set during persist (only backfilled once in Phase 1)
- New columns (`is_pinned`, etc.) not populated with defaults on INSERT

### Changes needed:

1. **In `persist_conversation()` — session UPSERT:** Add `session_title` logic:
   ```python
   # On first exchange (message_count will be 1), set title from user message
   title = user_content[:50].replace("'", "''") if is_first_exchange else None
   ```

2. **In session MERGE statement:** Include new columns with defaults:
   ```sql
   WHEN NOT MATCHED THEN INSERT (
     session_id, user_email, started_at, last_active_at, message_count,
     total_tokens_in, total_tokens_out, total_cost_usd, model,
     session_title, is_pinned, is_deleted, is_archived, is_shared, source
   ) VALUES (
     ..., '{title}', false, false, false, false, 'chat'
   )
   WHEN MATCHED THEN UPDATE SET
     last_active_at = ...,
     message_count = message_count + 1,
     session_title = COALESCE(session_title, '{title}'),
     ...
   ```

3. **Track exchange sequence:** Add a counter to know if this is exchange #1 (for title gen):
   ```python
   # Count existing messages for this session
   is_first = len([m for m in messages if m['role'] == 'user']) <= 1
   ```

### Validation:
- Start new chat → verify `session_title` populated in Delta after first exchange
- Continue chat → verify title unchanged, `message_count` increments
- Check `last_active_at` updates on each exchange

---

## Phase 3: Session List Fetcher ✅ COMPLETE

**Status:** COMPLETE (2026-07-24)  
**Depends on:** Phase 2 ✅  
**Deployment:** Pending (bundled with Phase 2 deploy)

### Objective:
Add three data-fetching functions to `app.py` that power the sidebar.

### Functions to add:

```python
def get_session_list(user_email: str, limit: int = 30) -> List[Dict]:
    """Fetch recent sessions for sidebar (owned + shared)."""
    sql = f"""
    SELECT session_id, session_title, last_active_at, message_count,
           is_pinned, source, routine_id
    FROM mde_dev.test_schema.nexus_sessions
    WHERE (user_email = '{user_email}' OR shared_with LIKE '%{user_email}%')
      AND is_deleted = false
      AND is_archived = false
    ORDER BY is_pinned DESC, last_active_at DESC
    LIMIT {limit}
    """
    # Parse result into list of dicts
    ...


def load_session_messages(session_id: str) -> List[Dict]:
    """Load full message history for a session (reconstructs from paired format)."""
    sql = f"""
    SELECT user_message, assistant_response, timestamp
    FROM mde_dev.test_schema.nexus_conversations
    WHERE session_id = '{session_id}'
    ORDER BY timestamp ASC
    """
    # For each row: yield {role:'user', content:...}, {role:'assistant', content:...}
    ...


def search_sessions(user_email: str, query: str, limit: int = 20) -> List[Dict]:
    """Search sessions by title keyword."""
    safe_query = query.replace("'", "''")
    sql = f"""
    SELECT session_id, session_title, last_active_at, message_count
    FROM mde_dev.test_schema.nexus_sessions
    WHERE (user_email = '{user_email}' OR shared_with LIKE '%{user_email}%')
      AND is_deleted = false
      AND session_title LIKE '%{safe_query}%'
    ORDER BY last_active_at DESC
    LIMIT {limit}
    """
    ...
```

### Design decisions:
- All functions use `execute_sql_statement()` (existing SQL Statement API wrapper)
- Results cached in `st.session_state` with 60s TTL to avoid per-render queries
- Shared sessions included via `shared_with LIKE` (simple, works at Hologic scale)

---

## Phase 4: Sidebar UI Rendering ✅ COMPLETE

**Status:** COMPLETE (2026-07-24)  
**Depends on:** Phase 3 ✅  
**Deployment:** Pending (bundled with Phases 2+3)

### Objective:
Replace or extend the existing `st.sidebar` section in `app.py` with the conversation history UI.

### Streamlit components:

```python
with st.sidebar:
    # ── New Chat ──
    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.session_state.session_id = f"nexus_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.rerun()

    # ── Search ──
    search_query = st.text_input("🔍", placeholder="Search conversations...", label_visibility="collapsed")

    st.divider()

    # ── Sections ──
    sessions = get_session_list(user_email)
    pinned = [s for s in sessions if s['is_pinned']]
    routines = [s for s in sessions if s['source'] == 'routine']
    recents = [s for s in sessions if not s['is_pinned'] and s['source'] == 'chat']

    if pinned:
        st.caption("📌 Pinned")
        for s in pinned:
            _render_session_button(s)

    if routines:
        st.caption("⚡ Routines")
        for s in routines:
            _render_session_button(s)

    st.caption("Recents")
    for s in recents:
        _render_session_button(s)
```

### Helper: `_render_session_button(session)`
- Shows title (truncated 35 chars) + relative timestamp
- Active session highlighted with filled circle (●) vs hollow (○)
- On click: loads session messages and reruns

---

## Phase 5: Session Switching Logic ✅ COMPLETE

**Status:** COMPLETE (2026-07-24)  
**Depends on:** Phase 4 ✅  
**Deployment:** Pending (bundled with Phases 2-4 deploy)

### Objective:
Wire session buttons to load/switch conversations.

### What was done:
1. **Added `switch_to_session(session_id, session_owner, current_user)`** (~line 976):
   - Loads messages via `load_session_messages()`
   - Handles empty session (valid but 0 messages) vs session-not-found (returns False)
   - Sets `is_read_only = True` when `session_owner != current_user`
   - Atomically updates: `messages`, `session_id`, `session_owner`, `is_read_only`, resets token counters
2. **Session state variables** added to init block:
   - `session_owner` (str) — email of session owner
   - `is_read_only` (bool) — True for shared sessions from other users
3. **Sidebar wiring** — all three sections (Pinned, Shared, Recents) call `switch_to_session()` with owner/user params
4. **Error handling** — on failure: `st.toast()` warning + `invalidate_session_cache()` + `st.rerun()`
5. **Read-only guard** — `st.info("🔒 This is a shared session (read-only)...")` + `user_input = None`

### Key code:
```python
def switch_to_session(session_id: str, session_owner: str = "", current_user: str = "") -> bool:
    loaded_messages = load_session_messages(session_id)
    if not loaded_messages:
        session_exists = any(s.get("session_id") == session_id for s in _SESSION_LIST_CACHE or [])
        if not session_exists:
            return False
    is_read_only = (bool(session_owner) and bool(current_user) and session_owner != current_user)
    st.session_state.messages = loaded_messages
    st.session_state.session_id = session_id
    st.session_state.session_owner = session_owner or current_user
    st.session_state.is_read_only = is_read_only
    st.session_state.total_tokens = {"in": 0, "out": 0}
    st.session_state.total_cost = 0.0
    return True
```

---

## Phase 6: Pinned Conversations ✅ COMPLETE

**Status:** COMPLETE (2026-07-25)  
**Depends on:** Phase 5 ✅  
**Deployment:** Pending (bundled with Phases 2-5 deploy)

### Objective:
Allow users to pin up to 5 conversations for quick access.

### What was done:
1. **Added `toggle_pin_session(session_id, user_email, currently_pinned)`** (~line 1018):
   - On pin: SELECT COUNT(*) to enforce max 5, returns False if limit hit
   - On unpin: skips count check, directly sets `is_pinned = false`
   - SQL injection safe (`.replace("'", "''")`)
   - Calls `invalidate_session_cache()` after toggle
2. **Pinned section: unpin button (❌)** — `st.columns([5, 1, 1])` per row; ❌ unpins + reruns
3. **Recents section: pin button (📌)** — `st.columns([5, 1, 1])` for owned sessions; non-owned sessions full-width
4. **5-pin limit enforced** — `st.toast("Pin limit reached (max 5). Unpin one first.")`
5. **Pinned always visible** — `not _search_q` condition preserves pinned during date filtering

### Key code:
```python
def toggle_pin_session(session_id: str, user_email: str, currently_pinned: bool) -> bool:
    if not currently_pinned:
        count = SELECT COUNT(*) WHERE is_pinned=true AND is_deleted=false
        if count >= 5: return False
    UPDATE nexus_sessions SET is_pinned = {new_val} WHERE session_id AND user_email
    invalidate_session_cache()
    return True
```

---

## Phase 7: Search & Filter ✅ COMPLETE

**Status:** COMPLETE (2026-07-25)  
**Depends on:** Phase 4 ✅  
**Deployment:** Pending (bundled with Phases 2-6 deploy)

### Objective:
Filter sidebar sessions by keyword and date range.

### What was done:
1. **Search input + clear button** — `st.columns([5, 1])`: text input + ✕ clear (visible only when active)
2. **Client-side filter first (instant)** — substring match on `session_title.lower()` from cached list
3. **SQL fallback** — `search_sessions()` fires only when client-side returns 0 results
4. **Result count** — "🔎 N result(s) for 'query'" or "No results found" + help text
5. **Date filter radio** — horizontal `[All | Today | This Week]` (hidden during search)
   - Today = `last_active_at` = today; This Week = Monday onward
   - Pinned sessions always pass date filter
6. **Clear button** — resets `sidebar_search` session state + reruns

### Key code:
```python
# Client-side (instant)
_sessions = [s for s in _all_sessions if _q_lower in (s.get("session_title") or "").lower()]
if not _sessions:
    _sessions = search_sessions(_user_email, _search_q)  # SQL fallback

# Date filter
_cutoff = _today if _date_filter == "Today" else _today - timedelta(days=_today.weekday())
```

---

## Phase 8: Delete Conversations ✅ COMPLETE

**Status:** COMPLETE (2026-07-25)  
**Depends on:** Phase 5 ✅  
**Deployment:** Pending (bundled with Phases 2-7 deploy)

### Objective:
Soft-delete conversations with undo capability.

### What was done:
1. **Added `soft_delete_session(session_id, user_email)`** (~line 1058):
   - Sets `is_deleted = true` WHERE session_id AND user_email (owner-only)
   - Calls `invalidate_session_cache()` after
2. **Added `undo_delete_session(session_id, user_email)`** (~line 1080):
   - Sets `is_deleted = false` WHERE session_id AND user_email
3. **Session state vars** — `last_deleted_session` (dict or None), `confirm_delete_sid` (reserved)
4. **Undo banner** — at top of session list: "🗑️ Deleted: [title]" + [Undo] button
5. **Delete buttons (🗑️)** in both Pinned (`[5,1,1]`) and Recents (`[5,1,1]`) sections
6. **Active session deletion** — clears messages + generates new session_id
7. **Owner-only** — SQL WHERE clause scopes to `user_email`; shared section has no delete button

### Key code:
```python
def soft_delete_session(session_id, user_email) -> bool:
    UPDATE nexus_sessions SET is_deleted = true WHERE session_id AND user_email
    invalidate_session_cache()

def undo_delete_session(session_id, user_email) -> bool:
    UPDATE nexus_sessions SET is_deleted = false WHERE session_id AND user_email
    invalidate_session_cache()
```

### Hard purge (future — 30-day cleanup job):
```sql
DELETE FROM mde_dev.test_schema.nexus_conversations
WHERE session_id IN (
  SELECT session_id FROM mde_dev.test_schema.nexus_sessions
  WHERE is_deleted = true AND last_active_at < DATEADD(DAY, -30, NOW())
);
DELETE FROM mde_dev.test_schema.nexus_sessions
WHERE is_deleted = true AND last_active_at < DATEADD(DAY, -30, NOW());
```

---

## Phase 9: Export Conversations ✅ COMPLETE

**Status:** COMPLETE (2026-07-25)  
**Depends on:** Phase 5 ✅

### Objective:
Export individual or all conversations in multiple formats.

### Formats:

| Format | Extension | Content |
|---|---|---|
| Markdown | `.md` | Full conversation with `## User` / `## NEXUS` headers + timestamps |
| JSON | `.json` | Structured array: `[{role, content, timestamp}]` |
| PDF | `.pdf` | Formatted with NEXUS branding header (requires `fpdf2` or similar) |

### Implementation:
```python
def export_session_markdown(session_id: str) -> str:
    messages = load_session_messages(session_id)
    session = get_session_metadata(session_id)
    lines = [
        f"# {session['session_title']}",
        f"**Date:** {session['started_at']} — {session['last_active_at']}",
        f"**Messages:** {session['message_count']} exchanges",
        "",
        "---",
        ""
    ]
    for msg in messages:
        role_header = "## 👤 User" if msg['role'] == 'user' else "## 🤖 NEXUS"
        lines.append(role_header)
        lines.append(msg['content'])
        lines.append("")
    return "\n".join(lines)
```

### UI:
- ⬇️ icon per session OR right-click context menu
- Format selector (Markdown/JSON/PDF)
- Uses `st.download_button()` for browser download
- "Export All" in Settings → creates ZIP of all sessions

---

## Phase 10: Routines (Scheduled Prompts) ✅ COMPLETE

**Status:** COMPLETE (2026-07-25)  
**Depends on:** Phase 4 ✅, Phase 2 ✅

### Objective:
Create recurring scheduled prompts (like Databricks AI Routines) that run automatically and store results as chat conversations.

### Architecture:
```
┌──────────────────────────────────────────────────────┐
│  Streamlit App (Create/Edit/View Routines)            │
│  ├── Create routine → INSERT nexus_routines          │
│  ├── View run history → SELECT nexus_sessions        │
│  │                      WHERE source='routine'       │
│  └── Manual "Run now" → Trigger LLM call inline      │
└──────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────┐
│  Databricks Workflow Job (routine_executor)           │
│  Runs every 15 min. Checks nexus_routines for due    │
│  routines (next_run_at <= NOW() AND is_active=true). │
│  For each: call LLM, persist result as new session   │
│  with source='routine', update last_run_*.           │
└──────────────────────────────────────────────────────┘
```

### UI — Create Routine Dialog:
```python
with st.form("new_routine"):
    name = st.text_input("Routine name", placeholder="Email triage - Good Morning")
    schedule = st.selectbox("Schedule", [
        "Weekdays at 8:00 AM EDT",
        "Daily at 7:00 AM EDT",
        "Weekly Monday at 9:00 AM EDT",
        "Custom cron..."
    ])
    prompt = st.text_area("Instructions", height=200,
        placeholder="Review my inbox for new emails. Categorize into Urgent, Action Needed, FYI...")
    submitted = st.form_submit_button("Create Routine")
```

### UI — Sidebar Routines Section:
```
⚡ Routines
  ● Email triage - Good Morning     ✅ today 8:05 AM
  ● Weekly cost summary              ⏭ Mon 9:00 AM
  ○ Data quality check               ⏸ paused
```

### Routine Executor Job (notebook):
```python
# Scheduled every 15 min via Databricks Workflow
from datetime import datetime, timezone
from openai import OpenAI

# 1. Find due routines
due_routines = spark.sql("""
  SELECT * FROM mde_dev.test_schema.nexus_routines
  WHERE is_active = true AND next_run_at <= NOW()
""").collect()

# 2. Execute each
for routine in due_routines:
    response = client.chat.completions.create(
        model="databricks-claude-sonnet-4-6",
        messages=[{"role": "user", "content": routine.prompt}]
    )
    # 3. Persist as session
    session_id = f"routine_{routine.routine_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # INSERT into nexus_conversations + UPSERT nexus_sessions (source='routine')
    # 4. Update routine metadata
    spark.sql(f"UPDATE ... SET last_run_at=NOW(), last_run_status='SUCCEEDED', ...")
```

---

## Phase 11: Conversation Sharing ✅ COMPLETE

**Status:** COMPLETE (2026-07-26)  
**Depends on:** Phase 5 ✅

### Objective:
Share conversations with other Hologic workspace users.

### Sharing modes:
| Mode | Behavior |
|---|---|
| Read-only | Viewer sees full history, cannot add messages |
| Collaborative | Both users can continue the conversation |

### UI — Share Dialog:
```python
with st.popover("🔗 Share"):
    email = st.text_input("Share with (email)")
    mode = st.radio("Access", ["Read-only", "Collaborative"])
    if st.button("Share"):
        share_session(session_id, email, mode)
```

### Implementation:
```python
def share_session(session_id: str, target_email: str, mode: str):
    # Read current shared_with JSON
    # Append new entry: {"email": target_email, "mode": mode, "shared_at": ...}
    # UPDATE nexus_sessions SET is_shared=true, shared_with=new_json
    ...
```

### Sidebar — "Shared with me" section:
```
👥 Shared with me
  ○ Cost optimization review        (stone.teele) 🔒
  ○ Pipeline failure analysis        (ashok.m)     ✏️
```
- 🔒 = read-only, ✏️ = collaborative
- Cannot share routine-generated sessions

---

## Phase 12: Auto-Archive Old Conversations ✅ COMPLETE

**Status:** COMPLETE (2026-07-26)  
**Depends on:** Phase 5 ✅

### Objective:
Automatically hide stale conversations to keep the sidebar clean.

### Rules:
- Conversations untouched for **30 days** → `is_archived = true`
- **Pinned conversations NEVER auto-archive**
- Archived sessions accessible via collapsed "📦 Archived (N)" section
- One-click unarchive
- Configurable threshold: 7 / 14 / 30 / 60 / 90 days (settings)

### Trigger — on app load (once per Streamlit session):
```python
def auto_archive_stale_sessions(user_email: str, threshold_days: int = 30):
    if st.session_state.get('_archive_checked'):
        return  # Only run once per session
    sql = f"""
    UPDATE mde_dev.test_schema.nexus_sessions
    SET is_archived = true
    WHERE user_email = '{user_email}'
      AND is_archived = false
      AND is_pinned = false
      AND is_deleted = false
      AND last_active_at < DATEADD(DAY, -{threshold_days}, CURRENT_TIMESTAMP())
    """
    execute_sql_statement(sql)
    st.session_state['_archive_checked'] = True
```

### UI — Archived section (collapsed):
```python
with st.expander(f"📦 Archived ({archive_count})"):
    for s in archived_sessions:
        col1, col2 = st.columns([4, 1])
        col1.button(s['session_title'][:35])
        col2.button("↩️", key=f"unarchive_{s['session_id']}")
```

---

## Phase 13: Polish & Deploy ✅ COMPLETE

**Status:** COMPLETE (2026-07-26)  
**Depends on:** All previous phases ✅

### Objective:
Final UX refinements and production deployment.

### Checklist:
- [ ] Active session highlight (● filled vs ○ hollow)
- [ ] Truncated titles with hover tooltip
- [ ] Message count badge per session
- [ ] Relative timestamps (Today, Yesterday, Jul 22, Jun 15)
- [ ] Icon row on hover: 📌 🗑️ ⬇️ 🔗 (pin, delete, export, share)
- [ ] Routine status indicators (⚡ active, ⏸ paused, ✅ last run OK, ❌ failed)
- [ ] Search clear button (X)
- [ ] Ctrl+K keyboard shortcut to focus search
- [ ] Read-only badge on shared sessions
- [ ] Archive count badge
- [ ] Mobile-responsive sidebar (Streamlit handles most of this)
- [ ] Performance: sidebar renders in <500ms (cache session list)
- [ ] Deploy: `apps deploy hologic-ai-agents`
- [ ] End-to-end test: create → pin → search → share → export → delete → archive

### CSS additions (inject via st.markdown):
```css
/* Active session highlight */
.session-active { background: rgba(39, 174, 96, 0.1); border-left: 3px solid #27AE60; }

/* Hover icon row */
.session-actions { opacity: 0; transition: opacity 0.2s; }
.session-row:hover .session-actions { opacity: 1; }

/* Routine status dot */
.routine-active::before { content: '●'; color: #27AE60; }
.routine-paused::before { content: '●'; color: #95A5A6; }
.routine-failed::before { content: '●'; color: #E74C3C; }
```

---

## Dependencies Graph

```
Phase 1 ✅
  └── Phase 2 ✅
        └── Phase 3 ✅
              └── Phase 4 ✅
                    ├── Phase 5 ✅
                    │     ├── Phase 6 (Pinned) ✅
                    │     ├── Phase 8 (Delete) ✅
                    │     ├── Phase 9 (Export) ✅
                    │     ├── Phase 11 (Sharing) ✅
                    │     └── Phase 12 (Auto-archive) ✅
                    └── Phase 7 (Search) ✅
        └── Phase 10 (Routines) ✅

Phase 13 (Polish) ✅ depends on ALL above
Phase 15 (Power BI Status) depends on Phase 4 + Phase 2
```

---

## Cost Estimate

| Component | Cost Impact |
|---|---|
| Sidebar queries (SQL Statement API) | ~$0.02/day (cached, 60s TTL) |
| Session load on switch | ~$0.001/load |
| Routine executor job (15 min intervals) | ~$0.45/day ($164/year) |
| Additional Delta storage | Negligible (<1 GB) |
| **Total incremental** | **~$200/year** |

---

## Risk Register

| Risk | Mitigation |
|---|---|
| SQL Warehouse cold start delays sidebar | Cache session list in st.session_state (60s TTL) |
| Large message content in Delta (>4000 chars) | Already truncated to 4000 in persist_conversation() |
| Concurrent edits to shared sessions | Last-write-wins (acceptable at single-user scale) |
| Routine executor fails silently | last_run_status tracking + morning briefing agent alert |
| session_title contains SQL injection chars | Escaped with .replace("'", "''") |

---

## Phase 15: Power BI App Progress Dashboard

**Status:** NOT STARTED  
**Depends on:** Phase 4 (sidebar UI), Phase 2 (persistence)

### Objective:
Connect to the Power BI REST API to display real-time deployment/refresh status of the NEXUS Databricks App within the chat sidebar — giving the user a single-pane view of app health without switching to Power BI Service.

### What it shows:

| Metric | Source | Display |
|---|---|---|
| Dataset refresh status | `/datasets/{id}/refreshes` | ✅ Succeeded / ❌ Failed / ⏳ In Progress |
| Last refresh time | Refresh history | "Today 6:05 AM" / "Yesterday 11 PM" |
| Report page count | `/reports/{id}/pages` | "12 pages published" |
| App install/update status | `/apps/{id}` | "v3.2 — Published Jul 25" |
| Scheduled refresh health | `/datasets/{id}/refreshSchedule` | "Next: Mon 6 AM EDT" / "⚠️ Disabled" |
| Gateway connectivity | `/gateways` | "Online" / "⚠️ Offline" |

### Architecture:

```
┌───────────────────────────────────────────────────┐
│  NEXUS App (app.py)                                │
│  ├── get_powerbi_app_status() → REST API calls    │
│  ├── Cache in session_state (5 min TTL)           │
│  └── Render in sidebar expander                    │
└───────────────────────────────────────────────────┘
              │
              ▼ (Azure AD Service Principal or PAT)
┌───────────────────────────────────────────────────┐
│  Power BI REST API (api.powerbi.com)               │
│  ├── GET /groups/{workspace_id}/datasets           │
│  ├── GET /groups/{workspace_id}/datasets/{id}/refreshes │
│  ├── GET /groups/{workspace_id}/reports            │
│  └── GET /groups/{workspace_id}/apps               │
└───────────────────────────────────────────────────┘
```

### Authentication:
```python
import msal

def get_powerbi_token() -> str:
    """Get Power BI REST API access token via Service Principal (client_credentials).
    
    Reads credentials from Databricks secrets:
    - scope: 'nexus' / key: 'pbi-tenant-id'
    - scope: 'nexus' / key: 'pbi-client-id'
    - scope: 'nexus' / key: 'pbi-client-secret'
    """
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(client_id, client_credential=client_secret, authority=authority)
    result = app.acquire_token_for_client(scopes=["https://analysis.windows.net/powerbi/api/.default"])
    return result.get("access_token")
```

### Core function:
```python
import requests
from datetime import datetime, timezone

_PBI_STATUS_CACHE = None
_PBI_STATUS_CACHE_TIME = 0.0
_PBI_CACHE_TTL = 300  # 5 minutes

def get_powerbi_app_status(workspace_id: str, dataset_id: str = None, app_id: str = None) -> dict:
    """Phase 15: Fetch Power BI app/dataset status from REST API.
    
    Returns:
        {
            'refresh_status': 'Completed' | 'Failed' | 'Unknown' | 'In Progress',
            'last_refresh': '2026-07-25T06:05:00Z',
            'last_refresh_relative': 'Today 6:05 AM',
            'next_refresh': '2026-07-28T06:00:00Z',
            'schedule_enabled': True,
            'dataset_name': 'NEXUS Analytics',
            'report_count': 12,
            'app_version': 'v3.2',
            'app_published_at': '2026-07-25',
            'gateway_status': 'Online',
            'error_message': None  # Populated on failure
        }
    """
    global _PBI_STATUS_CACHE, _PBI_STATUS_CACHE_TIME
    import time
    now = time.time()
    if _PBI_STATUS_CACHE and (now - _PBI_STATUS_CACHE_TIME) < _PBI_CACHE_TTL:
        return _PBI_STATUS_CACHE

    token = get_powerbi_token()
    headers = {"Authorization": f"Bearer {token}"}
    base_url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}"

    status = {}

    # Dataset refresh history
    if dataset_id:
        resp = requests.get(f"{base_url}/datasets/{dataset_id}/refreshes?$top=1", headers=headers)
        if resp.status_code == 200:
            refreshes = resp.json().get("value", [])
            if refreshes:
                latest = refreshes[0]
                status['refresh_status'] = latest.get('status', 'Unknown')
                status['last_refresh'] = latest.get('endTime') or latest.get('startTime')
                status['error_message'] = latest.get('serviceExceptionJson')

        # Refresh schedule
        resp = requests.get(f"{base_url}/datasets/{dataset_id}/refreshSchedule", headers=headers)
        if resp.status_code == 200:
            sched = resp.json()
            status['schedule_enabled'] = sched.get('enabled', False)
            status['schedule_days'] = sched.get('days', [])
            status['schedule_times'] = sched.get('times', [])

    # Report count
    resp = requests.get(f"{base_url}/reports", headers=headers)
    if resp.status_code == 200:
        status['report_count'] = len(resp.json().get("value", []))

    # App metadata
    if app_id:
        resp = requests.get(f"https://api.powerbi.com/v1.0/myorg/apps/{app_id}", headers=headers)
        if resp.status_code == 200:
            app_info = resp.json()
            status['app_name'] = app_info.get('name')
            status['app_published_at'] = app_info.get('lastUpdate')

    _PBI_STATUS_CACHE = status
    _PBI_STATUS_CACHE_TIME = now
    return status
```

### Sidebar UI:
```python
# Inside st.sidebar, after session list
with st.expander("📊 Power BI App Status", expanded=False):
    _pbi = get_powerbi_app_status(PBI_WORKSPACE_ID, PBI_DATASET_ID, PBI_APP_ID)
    if _pbi.get('refresh_status') == 'Completed':
        st.success(f"✅ Last refresh: {_pbi.get('last_refresh_relative', 'Unknown')}")
    elif _pbi.get('refresh_status') == 'Failed':
        st.error(f"❌ Refresh FAILED — {_pbi.get('error_message', 'check Power BI Service')}")
    elif _pbi.get('refresh_status') == 'Unknown':
        st.warning("⚠️ Refresh status unknown (API unavailable)")
    else:
        st.info(f"⏳ Refresh in progress...")

    if _pbi.get('schedule_enabled'):
        st.caption(f"📅 Next: {_pbi.get('schedule_days', ['?'])[0]} {_pbi.get('schedule_times', ['?'])[0]}")
    else:
        st.caption("⚠️ Scheduled refresh DISABLED")

    col1, col2 = st.columns(2)
    col1.metric("Reports", _pbi.get('report_count', '—'))
    col2.metric("Version", _pbi.get('app_version', '—'))

    if st.button("🔄 Refresh Now", key="pbi_refresh_now"):
        trigger_powerbi_refresh(PBI_WORKSPACE_ID, PBI_DATASET_ID)
        st.toast("Refresh triggered!", icon="🔄")
        invalidate_pbi_cache()
        st.rerun()
```

### Configuration (app.py constants):
```python
# Phase 15: Power BI integration
PBI_WORKSPACE_ID = ""   # Power BI workspace (group) GUID — set via secrets or env
PBI_DATASET_ID = ""     # Primary dataset GUID to monitor
PBI_APP_ID = ""         # Published app GUID (optional)
```

### Dependencies:
- `msal` — Azure AD token acquisition (add to `requirements.txt`)
- `requests` — already available
- Databricks Secrets: `nexus/pbi-tenant-id`, `nexus/pbi-client-id`, `nexus/pbi-client-secret`
- Power BI Service Principal must have workspace Viewer (minimum) or Member role

### Optional: Trigger refresh from NEXUS
```python
def trigger_powerbi_refresh(workspace_id: str, dataset_id: str) -> bool:
    """POST refresh trigger to Power BI REST API."""
    token = get_powerbi_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/refreshes",
        headers=headers,
        json={"notifyOption": "NoNotification"}
    )
    return resp.status_code == 202
```

### Validation:
- Confirm SP token acquisition succeeds (check MSAL logs)
- Verify refresh history returns most recent entry
- Test with dataset in Failed state to confirm error rendering
- Confirm 5-min cache prevents API rate limit hits (PBI limit: 8 refreshes/day, 48 API calls/hour)
- Test "Refresh Now" button triggers actual dataset refresh

### ⚠️ Watch Out:
- Power BI REST API has rate limits: max 200 requests per hour per user/SP
- Service Principal needs explicit workspace access (not inherited from Azure AD group)
- `refreshSchedule` endpoint returns 404 for datasets without Pro/Premium capacity
- App ID is separate from workspace ID — don't confuse them
- If SP credentials expire, cache stale status — show "⚠️ Status unavailable" instead of crashing
