# NEXUS App Patch Handoff

**Status:** ✅ ALL 3 PATCHES RESOLVED (2026-07-26). No further action needed.  
**Created:** 2026-07-20  
**File to fix:** `/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/5 - Agent Chat App/app.py`  
**App name:** `hologic-ai-agents`

---

## Problem

NEXUS still answers "25 tables in Gold / 10 tables in Platinum" after redeploy.
Root cause: 3 code changes planned in previous sessions never persisted to disk.

---

## 3 Exact Changes Required

Apply in order. All are simple string replacements — no structural changes.

---

### Change 1 — Remove wrong table counts from SUPERVISOR_PROMPT (~line 1094)

Find (two separate lines in the DATA MODEL DISCOVERY section):

```
- PLATINUM (mde_dev.platinum — 10 tables): Pre-aggregated, best for reporting/Genie/Power BI. Check for reuse first.
- GOLD (mde_dev.gold — 25 tables): Kimball star schema facts + dims. Reuse before rebuilding.
```

Replace with:

```
- PLATINUM (mde_dev.platinum): Pre-aggregated, best for reporting/Genie/Power BI. Check for reuse first.
- GOLD (mde_dev.gold): Kimball star schema facts + dims. Reuse before rebuilding.
```

---

### Change 2 — Insert catalog loader block before `classify_workspace` (~line 873)

Find this line:

```python
def classify_workspace(req: str) -> Tuple[str, str, str, str]:
```

Insert the block below **immediately before** that line (keep two blank lines as separator):

```python
# =============================================================================
# CATALOG CONTEXT LOADER — Medallion-first prompt augmentation
# =============================================================================

_SKILLS_BASE = "/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/skills"
_CATALOG_PATH = f"{_SKILLS_BASE}/medallion_catalog/gold_platinum_catalog.md"
_CATALOG_KEYWORDS = {
    "table", "fact_", "dim_", "dimension", "data model",
    "what tables", "existing object", "mde_dev", "medallion",
    "catalog", "gold table", "platinum table", "gold schema",
    "platinum schema", "fact table", "dim table", "which table",
    "available tables", "show tables", "list tables",
    "invoice", "journal", "opportunity", "headcount", "budget",
    "supply plan", "bom", "hcp",
}
_catalog_cache: Optional[str] = None


def _load_catalog() -> str:
    """Load the confirmed medallion object catalog (cached in module scope)."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    try:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            _catalog_cache = f.read()
    except Exception:
        _catalog_cache = ""  # Graceful no-op if file missing
    return _catalog_cache


def _needs_catalog(user_message: str) -> bool:
    """Return True if the message likely needs medallion object names."""
    msg_lower = user_message.lower()
    return any(kw in msg_lower for kw in _CATALOG_KEYWORDS)


def get_active_prompt(user_message: str) -> str:
    """Return SUPERVISOR_PROMPT, optionally augmented with the medallion catalog."""
    if not _needs_catalog(user_message):
        return SUPERVISOR_PROMPT
    catalog_text = _load_catalog()
    if not catalog_text:
        return SUPERVISOR_PROMPT
    return (
        SUPERVISOR_PROMPT
        + "\n\n## MEDALLION CATALOG — CONFIRMED PRODUCTION OBJECTS\n\n"
        + catalog_text
    )
```

---

### Change 3 — Update LLM call to use `get_active_prompt` (~line 1643)

Find:

```python
    messages = summarize_history(st.session_state.messages, SUPERVISOR_PROMPT)
```

Replace with:

```python
    messages = summarize_history(st.session_state.messages, get_active_prompt(_llm_user_input))
```

---

## Verification Checks

Run after applying all 3 changes:

```python
file_path = "/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/5 - Agent Chat App/app.py"
with open(file_path) as f:
    c = f.read()

checks = [
    ("get_active_prompt(_llm_user_input)" in c,   "LLM call uses get_active_prompt"),
    ("def _load_catalog()" in c,                  "_load_catalog() defined"),
    ("def _needs_catalog(" in c,                  "_needs_catalog() defined"),
    ("def get_active_prompt(" in c,               "get_active_prompt() defined"),
    ("MEDALLION CATALOG" in c,                    "catalog header string present"),
    ("\u2014 10 tables)" not in c,                "old platinum count removed"),
    ("\u2014 25 tables)" not in c,                "old gold count removed"),
    (c.count("summarize_history(st.session_state.messages, SUPERVISOR_PROMPT)") == 0,
                                                  "bare SUPERVISOR_PROMPT gone"),
]
for ok, label in checks:
    print(f"{'OK' if ok else 'FAIL'} {label}")
```

---

## After Applying

1. Redeploy `hologic-ai-agents` from the Apps page
2. Test prompt: *"What Gold tables exist for Oracle EBS AP invoices?"*
3. Expected: real table names from the catalog file, not "25 tables" placeholder

---

## Catalog File

Already exists — do not recreate:

```
/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/skills/medallion_catalog/gold_platinum_catalog.md
```

- 462 lines, 22,790 bytes
- 15 business domains (GL, AP, AR, SFDC, HCM, PBCS, ASCP, Agile PLM, HCP, etc.)
- 449 canonical Gold objects + 135 canonical Platinum objects
- Filtered from 1,742 Gold and 655 Platinum total objects in mde_dev

---

## Why Previous Attempts Failed

- `editAsset` not available on the file editor page context
- `executeCode` writes to workspace files are safety-blocked by the sandbox
- `workspaceUpdateFile` requires the full 88KB file as a parameter — ran out of
  context space before completing the assembly

## Recommended Fix Method

**Option A (fastest):** Open `app.py` in the workspace editor, use Ctrl+H (find and
replace) to apply the 3 changes manually, then redeploy the app.

**Option B:** Start a fresh conversation on the `app.py` file page and paste this file.
Ask the assistant to apply the 3 changes — with a clean context it can assemble the
full file and call `workspaceUpdateFile` without hitting length limits.
