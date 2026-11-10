# Databricks notebook source
# DBTITLE 1,Agent 88: Qlik Migration Orchestrator
# MAGIC %md
# MAGIC # Agent 88: Qlik Migration Orchestrator
# MAGIC
# MAGIC **Purpose:** Top-level orchestrator for Qlik→Databricks migration. Manages inventory scanning, dependency mapping, migration wave planning, and progress tracking across all Qlik artifacts (QVW, QVD, QVS, QVF, QVX, NPrinting). **`mode="step"` (added 2026-08-12) runs a real, tool-using Steps 0-3 analysis** (file inventory, object inventory, Databricks medallion mapping, gap analysis) against a single Qlik app extract, live-verified against `mde_dev`, and writes the deliverable markdown file itself.
# MAGIC
# MAGIC **Pipeline Position:** Strategy Layer → coordinates agents 89–95 (pre-assessment via 96)
# MAGIC
# MAGIC **Inputs:**
# MAGIC - Qlik app inventory (file paths, app names, sizes)
# MAGIC - Migration scope (which apps, which waves)
# MAGIC - Target Databricks architecture (Bronze/Silver/Gold)
# MAGIC
# MAGIC **Outputs:**
# MAGIC - Migration inventory report (apps, dependencies, complexity scores)
# MAGIC - Wave plan (sequenced migration batches)
# MAGIC - Progress dashboard (migrated vs remaining)
# MAGIC - Risk register (blocking dependencies, circular refs, missing sources)
# MAGIC - **`mode="step"`:** a real Steps 0-3 markdown deliverable, written to `/NEXUS_Generated/`
# MAGIC
# MAGIC **Coordinates:**
# MAGIC | Agent | Artifact Type |
# MAGIC |-------|---------------|
# MAGIC | 89_qvd_extraction | QVD files → Delta tables |
# MAGIC | 90_qlik_script_conversion | QVS/load scripts → PySpark/SQL |
# MAGIC | 91_qlik_data_model | Data models → Kimball star schema |
# MAGIC | 92_qlik_expression | Set analysis/vars → SQL expressions |
# MAGIC | 93_qlik_ui_migration | Charts/objects → Lakeview/Power BI |
# MAGIC | 94_qlik_section_access | Row-level security → UC policies |
# MAGIC | 95_qlik_nprinting | NPrinting → Jobs + subscriptions |
# MAGIC | 96_qlik_preassessment | -prj folder parsing → inventory, expressions, variables, edges |
# MAGIC
# MAGIC **2026-07-30 patch:** STEP 2 now queries real assessment evidence from
# MAGIC `mde_dev.test_schema.qlik_complexity_matrix` / `qlik_business_rules` /
# MAGIC `qlik_migration_blockers` / `qlik_optimisation_register` (seeded from the P01
# MAGIC Procurement Analytics pilot assessment) instead of relying only on the static
# MAGIC `QLIK_ARTIFACT_MAP`/`COMPLEXITY_FACTORS` dictionaries below. Those dictionaries
# MAGIC are general domain knowledge for the LLM, not a substitute for real per-app data
# MAGIC — until an app has a row in these tables, this agent has no grounded evidence
# MAGIC for it and will say so explicitly rather than inventing a score.
# MAGIC
# MAGIC **2026-08-12 fix (real fix, not just the crash bug):** Two independent, confirmed
# MAGIC problems fixed:
# MAGIC 1. `%run ./00_agent_config` below was a plain Python comment (missing the
# MAGIC    `# MAGIC` prefix), so `generate_run_id`/`call_agent`/`save_agent_output` were
# MAGIC    never loaded — every job submitted without an explicit `run_id` crashed
# MAGIC    immediately with `NameError`, and even with that worked around, the very
# MAGIC    next call (`call_agent`) crashed identically. Fixed by restoring the `# MAGIC`
# MAGIC    prefix (same pattern already fixed on Agent 96, 2026-08-06).
# MAGIC 2. Even with that fixed, this agent was architecturally a single bounded LLM
# MAGIC    completion with no file-read, live-SQL, or file-write capability — it could
# MAGIC    not have produced a real Steps 0-3 deliverable regardless of the crash bug.
# MAGIC    Added a new `mode="step"` that uses `run_tool_loop()` (new in
# MAGIC    `00_agent_config`) with 5 real tools (list/read/write workspace files,
# MAGIC    execute read-only SQL, verify a write) so the agent can actually do the work
# MAGIC    end-to-end, the same way this was proven to work via direct tool use for
# MAGIC    37 apps earlier this session. Existing modes (inventory/wave_plan/progress/
# MAGIC    dependency_map) are unchanged.

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Workspace Filesystem Utilities (REST API)
# ══════════════════════════════════════════════════════════════════════
# Workspace Filesystem Utilities (REST API)
# Access /Workspace/Users/ paths via REST API — NOT via SQL Warehouse.
#
# The SQL Warehouse SP (eede202e40603750) only has UC catalog-level
# permissions. Workspace paths require the notebook runner's identity token.
# These functions use the Jobs Compute token (sameet.patel@hologic.com)
# which has full workspace traversal.
# ══════════════════════════════════════════════════════════════════════

import requests
import base64
import json

# Auth context (from notebook runner, NOT SQL Warehouse SP)
_WS_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
_WS_URL = f"https://{spark.conf.get('spark.databricks.workspaceUrl')}"
_WS_HEADERS = {"Authorization": f"Bearer {_WS_TOKEN}", "Content-Type": "application/json"}


def list_workspace_path(path: str) -> list:
    """List contents of a workspace directory via REST API."""
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/list",
        headers=_WS_HEADERS,
        json={"path": api_path}
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("objects", [])


def read_workspace_file(path: str, format: str = "SOURCE") -> str:
    """Read workspace file content (base64 decoded) via REST API."""
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/export",
        headers=_WS_HEADERS,
        params={"path": api_path, "format": format}
    )
    if response.status_code == 404:
        return f"[ERROR] Path not found: {path}"
    response.raise_for_status()
    content_b64 = response.json().get("content", "")
    try:
        return base64.b64decode(content_b64).decode("utf-8")
    except Exception as e:
        return f"[ERROR] Failed to decode: {e}"


def workspace_path_exists(path: str) -> bool:
    """Check if a workspace path exists (file or directory)."""
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/get-status",
        headers=_WS_HEADERS,
        json={"path": api_path}
    )
    return response.status_code == 200


def get_workspace_object_info(path: str) -> dict:
    """Get metadata about a workspace object."""
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/get-status",
        headers=_WS_HEADERS,
        json={"path": api_path}
    )
    return response.json() if response.status_code == 200 else {}


def list_workspace_recursive(path: str, max_depth: int = 3, _current_depth: int = 0) -> list:
    """Recursively list workspace contents up to max_depth."""
    if _current_depth >= max_depth:
        return []
    objects = list_workspace_path(path)
    all_objects = list(objects)
    for obj in objects:
        if obj.get("object_type") == "DIRECTORY":
            all_objects.extend(list_workspace_recursive(obj["path"], max_depth, _current_depth + 1))
    return all_objects


def write_workspace_file(path: str, content: str, overwrite: bool = True) -> str:
    """Write a plain markdown/text FILE to the workspace via REST API (import,
    format RAW — produces object_type FILE, not a notebook).

    Safety guard (2026-08-12): restricted to the established Steps 0-3 deliverable
    location (/NEXUS_Generated/) so a model error or bad instruction can't write
    arbitrary content elsewhere in the workspace.
    """
    _ALLOWED_PREFIX = "/Workspace/Users/sameet.patel@hologic.com/NEXUS_Generated/"
    norm_path = path if path.startswith("/Workspace") else f"/Workspace{path}" if path.startswith("/Users") else path
    if not norm_path.startswith(_ALLOWED_PREFIX):
        return (f"ERROR: write blocked — path must be under '{_ALLOWED_PREFIX}' "
                f"(this is the established Steps 0-3 deliverable location). Got: {path}")
    api_path = norm_path.replace('/Workspace', '')
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    response = requests.post(
        f"{_WS_URL}/api/2.0/workspace/import",
        headers=_WS_HEADERS,
        json={"path": api_path, "content": content_b64, "format": "RAW", "overwrite": overwrite}
    )
    if response.status_code not in (200, 201):
        return f"ERROR: write failed ({response.status_code}): {response.text[:500]}"
    info = get_workspace_object_info(norm_path)
    return json.dumps({"written_path": norm_path, "object_type": info.get("object_type"),
                        "size": info.get("size")})


# --- Quick validation ---
_target = "/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration"
_exists = workspace_path_exists(_target)
print(f"✅ Workspace Filesystem Utilities loaded")
print(f"   Identity: Notebook runner token (NOT SQL Warehouse SP)")
print(f"   Qlik Migration path exists: {_exists}")
print(f"   Functions: list_workspace_path, read_workspace_file, write_workspace_file, workspace_path_exists, get_workspace_object_info, list_workspace_recursive")

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "Migration Request")
dbutils.widgets.dropdown("mode", "inventory", ["inventory", "wave_plan", "progress", "dependency_map", "step"], "Mode")
dbutils.widgets.text("qlik_app_path", "", "Qlik App Path (optional)")
dbutils.widgets.text("run_id", "", "Run ID (auto-generated if blank)")

request = dbutils.widgets.get("request")
mode = dbutils.widgets.get("mode")
qlik_app_path = dbutils.widgets.get("qlik_app_path")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context Gathering — Qlik Inventory & Migration State
# ══════════════════════════════════════════════════════════════════════

# Qlik artifact types and their Databricks equivalents
QLIK_ARTIFACT_MAP = {
    "QVW": {"desc": "QlikView Workbook", "contains": ["script", "data_model", "ui", "variables", "section_access"], "agents": [90, 91, 92, 93, 94]},
    "QVD": {"desc": "QlikView Data file", "contains": ["columnar_data"], "agents": [89]},
    "QVS": {"desc": "QlikView Script include", "contains": ["etl_logic"], "agents": [90]},
    "QVF": {"desc": "Qlik Sense Application", "contains": ["script", "data_model", "ui", "master_items"], "agents": [90, 91, 92, 93]},
    "QVX": {"desc": "Data Exchange format", "contains": ["connector_output"], "agents": [89]},
    "NPrinting": {"desc": "Scheduled report distribution", "contains": ["templates", "schedules", "recipients"], "agents": [95]},
}

# Migration complexity scoring
COMPLEXITY_FACTORS = {
    "synthetic_keys": 3,        # Requires data model redesign
    "circular_references": 5,   # Hard — needs link tables or refactoring
    "set_analysis_depth": 2,    # Per nesting level
    "section_access": 2,        # Security translation needed
    "binary_loads": 3,          # Cross-app dependencies
    "qvd_layers": 1,            # Per layer in QVD architecture
    "nprinting_templates": 2,   # Report migration
    "custom_expressions": 1,    # Per 10 expressions
    "resident_loads": 1,        # In-memory transformations
    "mapping_loads": 1,         # Lookup translations
}

# Wave assignment rules
WAVE_RULES = {
    "wave_1": "Standalone apps (no binary loads, no shared QVDs, <50 expressions)",
    "wave_2": "Apps with shared QVD layer (standard ETL, moderate expressions)",
    "wave_3": "Complex apps (synthetic keys, circular refs, heavy set analysis)",
    "wave_4": "Cross-app dependencies (binary loads, shared Section Access)",
    "wave_5": "NPrinting + scheduled distribution (depends on waves 1-4)",
}

print(f"✅ Context loaded: {len(QLIK_ARTIFACT_MAP)} artifact types, {len(COMPLEXITY_FACTORS)} complexity factors")
print(f"📋 Mode: {mode}")

# COMMAND ----------

# DBTITLE 1,STEP 2b - Real Assessment Data Lookup
# ══════════════════════════════════════════════════════════════════════
# STEP 2b: Real Assessment Data Lookup — ground the LLM in actual findings
# ══════════════════════════════════════════════════════════════════════
# Added 2026-07-30. Matches `request` and `qlik_app_path` INDEPENDENTLY against
# asset_name / asset_id in qlik_complexity_matrix (case-insensitive substring
# match on each term separately, not the two fields concatenated into one
# search phrase — concatenating them turns "Procurement Analytics" +
# "Procurement Analytics" into a single "procurement analytics procurement
# analytics" phrase that matches nothing). Pulls every business rule, blocker,
# and optimisation finding tied to whatever asset_id(s) matched. If nothing
# matches, real_evidence_context says so explicitly — the LLM must not fill
# that gap with invented specifics.
#
# Skipped for mode="step": that mode does its own live grounding via the tool
# loop (reads the actual extract + queries mde_dev directly) rather than this
# pre-seeded assessment-table lookup, which is a separate, older evidence source.

search_terms = [t.strip().lower() for t in [request, qlik_app_path] if t and t.strip()]
search_terms = list(dict.fromkeys(search_terms))  # de-dupe, preserve order

matched_assets = []
if search_terms and mode != "step":
    where_clauses = []
    for term in search_terms:
        escaped_term = term.replace("'", "''")
        where_clauses.append(f"lower(asset_id) LIKE '%{escaped_term}%'")
        where_clauses.append(f"lower(asset_name) LIKE '%{escaped_term}%'")
    where_sql = " OR ".join(where_clauses)
    matched_assets_df = spark.sql(f"""
        SELECT asset_id, asset_name, complexity_band, raw_score, recommended_track,
               s1_blocker_count, review_status, notes
        FROM mde_dev.test_schema.qlik_complexity_matrix
        WHERE {where_sql}
    """)
    matched_assets = [row.asDict() for row in matched_assets_df.collect()]

real_evidence_context = ""

if matched_assets:
    asset_ids = [a["asset_id"] for a in matched_assets]
    asset_id_list_sql = ", ".join(f"'{a.replace(chr(39), chr(39)*2)}'" for a in asset_ids)

    business_rules = spark.sql(f"""
        SELECT rule_id, rule_name, source_asset_id, rule_statement_business_language,
               is_suspected_defect, defect_description, status
        FROM mde_dev.test_schema.qlik_business_rules
        WHERE source_asset_id IN ({asset_id_list_sql})
        ORDER BY rule_id
    """).collect()

    blockers = spark.sql(f"""
        SELECT blocker_instance_id, blocker_name, severity, asset_id,
               detection_evidence, resolution_approach, status
        FROM mde_dev.test_schema.qlik_migration_blockers
        WHERE asset_id IN ({asset_id_list_sql})
        ORDER BY blocker_instance_id
    """).collect()

    optimisations = spark.sql(f"""
        SELECT opportunity_id, opportunity, quantified_benefit, effort_days, status
        FROM mde_dev.test_schema.qlik_optimisation_register
        WHERE affected_assets IN ({asset_id_list_sql})
        ORDER BY opportunity_id
    """).collect()

    lines = ["REAL ASSESSMENT DATA (ground truth — from mde_dev.test_schema.qlik_* tables, "
             "seeded from an actual -prj/Sense-decode assessment, not LLM-generated):", ""]

    lines.append("## Matched assets")
    for a in matched_assets:
        lines.append(
            f"- **{a['asset_id']}** ({a['asset_name']}) — Band {a['complexity_band']}, "
            f"raw score {a['raw_score']}, {a['s1_blocker_count']} confirmed S1 blocker(s). "
            f"Recommended track: {a['recommended_track']}"
        )

    lines.append("")
    lines.append(f"## Business rules found ({len(business_rules)})")
    for r in business_rules:
        flag = " [SUSPECTED DEFECT]" if str(r["is_suspected_defect"]).upper() == "TRUE" else ""
        lines.append(f"- {r['rule_id']} ({r['source_asset_id']}): {r['rule_name']}{flag} — {r['status']}")

    lines.append("")
    lines.append(f"## Migration blockers ({len(blockers)})")
    for b in blockers:
        lines.append(f"- {b['blocker_instance_id']} [{b['severity']}] {b['blocker_name']} — {b['status']}")

    lines.append("")
    lines.append(f"## Optimisation opportunities ({len(optimisations)})")
    for o in optimisations:
        lines.append(f"- {o['opportunity_id']}: {o['opportunity']} (~{o['effort_days']}d, {o['status']})")

    real_evidence_context = "\n".join(lines)
    print(f"✅ Real evidence found: {len(matched_assets)} asset(s), {len(business_rules)} rules, "
          f"{len(blockers)} blockers, {len(optimisations)} optimisations")
elif mode != "step":
    real_evidence_context = (
        "REAL ASSESSMENT DATA: none found in mde_dev.test_schema.qlik_* tables for this request. "
        "No app matching this request has been assessed yet — do not invent specific findings "
        "(complexity scores, blocker counts, business rules) for it. State plainly that this app "
        "has not been assessed and that a real assessment (via the qlik-app-assess process) is "
        "needed before any number can be quoted."
    )
    print("⚠️ No real assessment data matched this request — LLM will be told to say so, not guess")

# COMMAND ----------

# DBTITLE 1,STEP 3a - mode="step": real tool-using Steps 0-3 analysis (2026-08-12)
# ══════════════════════════════════════════════════════════════════════
# STEP 3a: mode="step" — REAL Steps 0-3 analysis via the agentic tool loop
# ══════════════════════════════════════════════════════════════════════
# This is the actual fix: instead of one bounded LLM completion guessing at an
# analysis, the model gets real tools (list/read/write workspace files, execute
# read-only SQL against mde_dev) and does the work itself — reading the app's
# real extract, live-verifying every REUSE/CREATE/VERIFY claim, and writing the
# markdown deliverable. Runs ONLY when mode == "step"; every other mode is
# untouched and still uses the original single-shot call_agent() path below.

step_result = None

if mode == "step":

    STEP_TOOLS_SPEC = [
        {"type": "function", "function": {
            "name": "list_workspace_dir",
            "description": "List the files and subfolders in a Databricks Workspace directory.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Full /Workspace/... directory path"}
            }, "required": ["path"]}
        }},
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read the text content of a Databricks Workspace file (a Qlik extract JSON/text file, a notebook, or a plain markdown file). Large files are truncated — pass offset to page through.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Full /Workspace/... file path"},
                "offset": {"type": "integer", "description": "Character offset to start reading from (for paging through large files). Default 0."},
            }, "required": ["path"]}
        }},
        {"type": "function", "function": {
            "name": "execute_sql",
            "description": "Execute a live, READ-ONLY SQL query against the mde_dev Unity Catalog (via this notebook's own Spark session) and return up to 200 rows as JSON. For SHOW TABLES/SHOW SCHEMAS live-catalog verification, use glob '*' wildcards in LIKE clauses (e.g. LIKE '*item*') — NOT SQL '%' wildcards, which silently return zero rows.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "A SELECT / SHOW / DESCRIBE statement. DDL/DML is blocked."}
            }, "required": ["query"]}
        }},
        {"type": "function", "function": {
            "name": "write_deliverable_file",
            "description": "Write the final plain-markdown Steps 0-3 deliverable to /Workspace/Users/sameet.patel@hologic.com/NEXUS_Generated/. Must be a full path under that folder ending in .md. This produces a real workspace FILE object (not a notebook).",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Full output path, must start with /Workspace/Users/sameet.patel@hologic.com/NEXUS_Generated/ and end in .md"},
                "content": {"type": "string", "description": "The complete markdown document content."},
            }, "required": ["path", "content"]}
        }},
        {"type": "function", "function": {
            "name": "verify_written_file",
            "description": "Confirm a file you wrote actually exists and is object_type FILE (not a notebook/directory), with its byte size. Call this after write_deliverable_file to self-check before finishing.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}
            }, "required": ["path"]}
        }},
    ]

    def _tool_list_dir(path: str) -> str:
        try:
            items = list_workspace_path(path)
            return json.dumps([{"path": i.get("path"), "object_type": i.get("object_type")} for i in items])
        except Exception as e:
            return f"ERROR: {e}"

    def _tool_read_file(path: str, offset: int = 0) -> str:
        # Kept deliberately smaller than earlier drafts (2026-08-12): large chunks
        # compound across rounds (full history resent every call) and tripped the
        # model's per-minute input-token rate limit well before real work finished.
        MAX_CHARS = 7000
        try:
            text = read_workspace_file(path, format="AUTO")
            if text.startswith("[ERROR]"):
                text = read_workspace_file(path, format="SOURCE")
        except Exception as e:
            return f"ERROR: {e}"
        if text.startswith("[ERROR]"):
            return text
        total = len(text)
        chunk = text[offset:offset + MAX_CHARS]
        more = (offset + MAX_CHARS) < total
        return json.dumps({
            "path": path, "total_chars": total, "offset": offset,
            "returned_chars": len(chunk), "has_more": more,
            "next_offset": (offset + MAX_CHARS) if more else None,
            "content": chunk,
        })

    def _tool_write_deliverable(path: str, content: str) -> str:
        return write_workspace_file(path, content, overwrite=True)

    def _tool_verify_written(path: str) -> str:
        info = get_workspace_object_info(path)
        if not info:
            return json.dumps({"exists": False, "path": path})
        return json.dumps({"exists": True, "path": path, "object_type": info.get("object_type"),
                            "size": info.get("size")})

    _sql_tool = make_sql_query_tool()

    STEP_TOOL_IMPLS = {
        "list_workspace_dir": _tool_list_dir,
        "read_file": _tool_read_file,
        "execute_sql": _sql_tool,
        "write_deliverable_file": _tool_write_deliverable,
        "verify_written_file": _tool_verify_written,
    }

    step_system_prompt = """You are Agent 88 (Qlik Migration Orchestrator) for Hologic's NEXUS platform, running in
mode="step" — a real, tool-using Steps 0-3 migration analysis. You have 5 real tools:
list_workspace_dir, read_file, execute_sql, write_deliverable_file, verify_written_file. Use them —
do not guess, assume, or fabricate any table name, field, or verification result.

MANDATORY FIRST ACTIONS — before analyzing the target app, read these two documents in full with
read_file (page through with offset if truncated) and follow them exactly:
1. /Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration/NEXUS_Qlik_Migration_Deliverables_Prompt
   — the required Steps 0-3 process and output structure.
2. /Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration/NEXUS_Platform_Knowledge
   — read at least section 9: corrected ground truth for live-catalog verification syntax (glob
   '*' wildcards in SHOW TABLES/SHOW SCHEMAS LIKE clauses, NOT SQL '%', which silently returns
   zero rows) and real table names (no generic dim_date; Agile PLM Bronze schema is stg_agile,
   not stg_agile_plm).

THEN, for the target app given in the user message:
- List and read its actual source extract folder. Two formats exist — detect which one you have:
  (a) qvfs-extract/<App>/ — JSON-based (app.json, data-model.json, measures.json, dimensions.json,
      variables.json, sheets.json, load-model.json, masterobjects.json, script.qvs, summary.txt,
      plus tables/, raw/, assets/ subfolders), or
  (b) 01-prj/<App>-prj/ — older raw XML export (DocProperties.xml, DocInternals.xml,
      LoadScript.txt, QlikViewProject.xml, per-object XML files).
  Ground every claim in what these files actually contain — cite file names.
- Mirror the section headers of the reference template exactly: "STEP 0 File Inventory",
  "STEP 1 Object Inventory", "STEP 2 Databricks Medallion Mapping", "STEP 3 Gap Analysis",
  "Migration Complexity Scorecard" (read
  /Workspace/Users/sameet.patel@hologic.com/NEXUS_Generated/MIGRATION_STEPS_0_3_Global_Metrics.md
  with read_file if you want to see the exact structure/rigor bar to match).
- For EVERY REUSE/CREATE/VERIFY claim about a Databricks table in Step 3, you MUST have actually
  run execute_sql (SHOW TABLES ... LIKE '*name*' and DESCRIBE TABLE) in this session before writing
  the claim — cite the exact query. A name that merely looks similar is NOT sufficient — check
  actual columns/domain before accepting a match (this program has caught multiple false-positive
  name matches this way — e.g. a table that looks right by name but is actually a different
  workflow/domain — always verify, never assume).
- When you are done, call write_deliverable_file yourself with the complete markdown document, to
  a path under /Workspace/Users/sameet.patel@hologic.com/NEXUS_Generated/ named
  MIGRATION_STEPS_0_3_<App_Name_With_Underscores>.md — then call verify_written_file to confirm it
  landed as a real FILE with a real size before you finish. Only stop calling tools once that
  verification has succeeded.

If you cannot find or access something after a genuine attempt, say so explicitly in the document
as a flagged gap — never fabricate a plausible-sounding table name, column, or verification
result. Every unverified claim must be marked ⚠️ VERIFY or NOT LOCATED, not stated as fact."""

    step_user_prompt = f"""Target app / request: {request}
Qlik app path (if given): {qlik_app_path or 'not specified — determine from the request text or by listing the qvfs-extract/ and 01-prj/ folders'}

Do the real Steps 0-3 analysis now, using your tools, and write the deliverable file yourself."""

    step_result = run_tool_loop(
        agent_name="88_qlik_migration_orchestrator",
        system_prompt=step_system_prompt,
        user_prompt=step_user_prompt,
        tools_spec=STEP_TOOLS_SPEC,
        tool_impls=STEP_TOOL_IMPLS,
        max_rounds=90,
        max_tokens=8192,
        temperature=0.1,
    )

    print(f"✅ mode=\"step\" tool loop finished — {step_result['rounds']} rounds, "
          f"{len(step_result['tool_calls'])} tool calls, finish_reason={step_result['finish_reason']}")
    if step_result.get("error"):
        print(f"⚠️ {step_result['error']}")
    print()
    print(step_result["final_text"])

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting (modes other than "step")
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting — Build LLM Prompt (original single-shot path,
# used for inventory/wave_plan/progress/dependency_map — unchanged)
# ══════════════════════════════════════════════════════════════════════

if mode != "step":
    system_prompt = """You are the Qlik Migration Orchestrator (Agent 88) for the Hologic NEXUS platform.

You coordinate the full Qlik→Databricks migration across 7 specialist agents:
- Agent 89 (QVD Extraction): Converts QVD files to Delta tables
- Agent 90 (Script Conversion): Converts QVS/load scripts to PySpark/SQL
- Agent 91 (Data Model): Maps Qlik associative model to Kimball star schema
- Agent 92 (Expression): Converts set analysis/AGGR/variables to SQL
- Agent 93 (UI Migration): Maps charts/objects to Lakeview/Power BI
- Agent 94 (Section Access): Converts RLS to Unity Catalog policies
- Agent 95 (NPrinting): Converts scheduled reports to Jobs + subscriptions

Your responsibilities:
1. INVENTORY: Scan and catalog all Qlik artifacts (QVW, QVD, QVS, QVF, QVX, NPrinting)
2. DEPENDENCY MAP: Identify cross-app dependencies (binary loads, shared QVDs, shared Section Access)
3. COMPLEXITY SCORE: Rate each app 1-10 based on synthetic keys, circular refs, expression depth
4. WAVE PLAN: Sequence apps into migration waves (standalone first, complex last)
5. PROGRESS TRACK: Monitor migration status, blockers, and completion %

Qlik Architecture Patterns to recognize:
- QVD Layered Architecture: Extract QVDs → Transform QVDs → App QVDs → UI Layer
- Binary Load chains: App A loads from App B's QVW
- Shared Section Access: Multiple apps reference same access table
- Master Calendar pattern: Standard date dimension in QVS include

Target Architecture:
- Bronze: Raw QVD data → Delta tables (1:1 migration via Agent 89)
- Silver: Load script logic → Spark Declarative Pipelines (via Agent 90)
- Gold: Qlik data model → Kimball star schema (via Agent 91)
- Presentation: Charts → Lakeview dashboards (via Agent 93)
- Security: Section Access → UC row filters + ABAC (via Agent 94)
- Distribution: NPrinting → Databricks Jobs + email subscriptions (via Agent 95)

Hologic Standards (ENFORCE):
- Surrogate keys: xxhash64(CONCAT_WS('|', keys))
- Audit columns: etl_load_datetime, etl_source_system, etl_batch_id
- Liquid Clustering (NOT PARTITION BY)
- Catalog: mde_dev / mde_uat / mde_prd

CRITICAL — grounding rule: A "REAL ASSESSMENT DATA" block may appear in the user
prompt below. If it contains matched assets, treat every fact in it as ground
truth pulled from an actual QlikView/-prj or Sense-decode assessment — do not
contradict it, and do not invent additional complexity scores, blockers, or
business rules beyond what it lists. If it says no real data was found, you
MUST say plainly that this app has not been assessed yet and that a real
assessment is needed — never fabricate a plausible-sounding score, wave
assignment, or blocker list for an unassessed app.
"""

    user_prompt = f"""Mode: {mode}
Request: {request}
Qlik App Path: {qlik_app_path or 'Not specified'}

{real_evidence_context}

Please provide the {mode} analysis for this Qlik migration request, grounded in the
REAL ASSESSMENT DATA above where it was found."""

    print(f"✅ Prompts formatted — System: {len(system_prompt)} chars, User: {len(user_prompt)} chars")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call (modes other than "step")
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call — Execute Migration Orchestration (original single-shot
# path; mode="step" already ran its own tool loop above and populated
# step_result instead)
# ══════════════════════════════════════════════════════════════════════

if mode != "step":
    response = call_agent(
        agent_name="88_qlik_migration_orchestrator",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=4096
    )

    print(response)

# COMMAND ----------

# DBTITLE 1,STEP 5 - Validate and Persist
# ══════════════════════════════════════════════════════════════════════
# STEP 5: Validate & Persist
# ══════════════════════════════════════════════════════════════════════

if mode == "step":
    # The deliverable file was already written by the tool loop itself
    # (write_deliverable_file, self-checked via verify_written_file). Here we
    # just persist a record of the run for cost/observability tracking —
    # unlike the other modes, the real output is the workspace file, not this
    # Delta row.
    assert step_result is not None, "mode='step' but step_result was never set — internal error"
    _quality_ok = (step_result.get("error") is None) and len(step_result.get("final_text", "")) > 0
    save_agent_output(
        agent_name="88_qlik_migration_orchestrator",
        run_id=run_id,
        output_type="qlik_migration_step",
        content=step_result["final_text"],
        metadata={
            "mode": mode,
            "qlik_app_path": qlik_app_path,
            "rounds": step_result["rounds"],
            "tool_call_count": len(step_result["tool_calls"]),
            "finish_reason": step_result["finish_reason"],
            "error": step_result.get("error"),
        }
    )
    if not _quality_ok:
        # 2026-08-12 fix: a failed tool loop must fail the JOB, not just print a
        # warning while the job still reports SUCCESS — that's exactly the gap
        # that let a real 429 rate-limit failure look like a clean success on
        # the first end-to-end test.
        raise RuntimeError(
            f"mode='step' tool loop did not complete successfully after {step_result['rounds']} "
            f"round(s) / {len(step_result['tool_calls'])} tool call(s): {step_result.get('error')}"
        )
    print(f"\n✅ Agent 88 mode=\"step\" complete — {step_result['rounds']} rounds, "
          f"{len(step_result['tool_calls'])} tool calls")
    print(f"📋 Run ID: {run_id}")

else:
    # Quality gate: response must contain structured output
    assert len(response) > 100, "Response too short — likely LLM failure"
    assert any(kw in response.lower() for kw in ["wave", "inventory", "dependency", "progress", "migration"]), \
        "Response missing expected migration orchestration content"

    # Persist output
    save_agent_output(
        agent_name="88_qlik_migration_orchestrator",
        run_id=run_id,
        output_type=f"qlik_migration_{mode}",
        content=response,
        metadata={"mode": mode, "qlik_app_path": qlik_app_path, "matched_assets": [a["asset_id"] for a in matched_assets]}
    )

    print(f"\n✅ Agent 88 complete — output saved as 'qlik_migration_{mode}'")
    print(f"📋 Run ID: {run_id}")