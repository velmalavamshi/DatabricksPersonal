# Databricks notebook source
# DBTITLE 1,Agent 96: Qlik Pre-Assessment Agent
# MAGIC %md
# MAGIC # Agent 96: Qlik Pre-Assessment Agent
# MAGIC
# MAGIC **Purpose:** Deterministic parser that batch-processes QlikView `-prj` folder trees and produces structured assessment artifacts in Delta. This is the **upstream feeder** for Agent 88 — without it, the orchestrator has no grounded evidence.
# MAGIC
# MAGIC **Pipeline Position:** Pre-Assessment Layer → feeds Agent 88 (orchestrator) via Delta tables
# MAGIC
# MAGIC **Inputs:**
# MAGIC - Root path to QlikView `-prj` folder tree (workspace or volume mount)
# MAGIC - Optional path variable substitutions (e.g., `vQVDPath=D:/QVD/`)
# MAGIC
# MAGIC **Outputs (Delta tables in `mde_dev.test_schema`):**
# MAGIC - `qlik_inventory` — one row per app (script metrics, object counts, blockers)
# MAGIC - `qlik_expressions_corpus` — full expression corpus (all roles, normalised, deduped)
# MAGIC - `qlik_variables` — all SET/LET/DOC variables with auto-classification
# MAGIC - `qlik_dependency_edges` — source→qvd→app DAG edges
# MAGIC
# MAGIC **Approach:** Hybrid
# MAGIC - **Deterministic** (95%): Regex + XML parsing, comment stripping, path normalisation, blocker detection
# MAGIC - **LLM-augmented** (5%): Edge-case classification, complexity narrative, migration readiness summary
# MAGIC
# MAGIC **Feeds into:**
# MAGIC - Agent 88 STEP 2b (`qlik_complexity_matrix`, `qlik_migration_blockers`)
# MAGIC - Agent 90 (script conversion — prioritised by complexity)
# MAGIC - Agent 92 (expression conversion — sorted by reuse count)

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Input Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "Pre-Assessment Request")
dbutils.widgets.text("prj_root", "", "Root path to *-prj folders")
dbutils.widgets.text("path_vars", "", "Path var subs (NAME=VALUE|NAME2=VALUE2)")
dbutils.widgets.dropdown("output_mode", "delta", ["delta", "display_only"], "Output Mode")
dbutils.widgets.text("target_schema", "mde_dev.test_schema", "Target Schema")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
prj_root = dbutils.widgets.get("prj_root")
path_vars_raw = dbutils.widgets.get("path_vars")
output_mode = dbutils.widgets.get("output_mode")
target_schema = dbutils.widgets.get("target_schema")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# Parse path variable substitutions
path_vars = {}
for pv in path_vars_raw.split("|"):
    if "=" in pv:
        k, v = pv.split("=", 1)
        path_vars[k.strip()] = v.strip()

print(f"✅ Widgets loaded")
print(f"   Root: {prj_root or '(not set - will prompt)'}")
print(f"   Path vars: {len(path_vars)} defined")
print(f"   Output: {output_mode} → {target_schema}")
print(f"   Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,STEP 2 - Deterministic Parser Core
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Deterministic Parser Core
# Ported from qvw_prj_extractor.py -- zero LLM, pure regex + XML.
# Conservative: under-claims rather than guesses. UNKNOWN = countable gap.
# ══════════════════════════════════════════════════════════════════════

from __future__ import annotations
import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------------
# Script cleaning
# --------------------------------------------------------------------------------------

_RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RE_LINE_COMMENT = re.compile(r"//[^\n]*")
_RE_REM_COMMENT = re.compile(r"(?im)^\s*REM\b[^;]*;")


def strip_comments(script: str) -> str:
    """Remove QlikView's three comment forms. Order matters: block first."""
    script = _RE_BLOCK_COMMENT.sub(" ", script)
    script = _RE_REM_COMMENT.sub(" ", script)
    # Avoid eating '//' inside quoted strings (UNC paths, URLs)
    quoted: list[str] = []

    def _mask(m: re.Match) -> str:
        quoted.append(m.group(0))
        return f"\x00{len(quoted) - 1}\x00"

    script = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"", _mask, script)
    script = _RE_LINE_COMMENT.sub(" ", script)
    return re.sub(r"\x00(\d+)\x00", lambda m: quoted[int(m.group(1))], script)


# --------------------------------------------------------------------------------------
# Script-level regex patterns
# --------------------------------------------------------------------------------------

P = {
    "connect": re.compile(
        r"(?i)\b(?:LIB\s+CONNECT\s+TO|CONNECT(?:32|64)?\s+TO)\s+(?:'([^']*)'|\"([^\"]*)\"|(\[[^\]]*\])|([^;\n]+))",
    ),
    "sql_select": re.compile(r"(?i)\bSQL\s+SELECT\b"),
    "sql_from": re.compile(r"(?i)\bSQL\s+SELECT\b.*?\bFROM\s+([\[\]\w.\"$#]+)", re.DOTALL),
    "qvd_read": re.compile(
        r"(?i)\bFROM\s+\[([^\[\]]+?\.qvd)\]\s*\(\s*qvd\s*\)"
        r"|\bFROM\s+([^\s;\[\]]+?\.qvd)\s*\(\s*qvd\s*\)"
    ),
    "qvd_store": re.compile(r"(?i)\bSTORE\b[^;]*?\bINTO\s+\[?([^\s;\[\]]+?\.qvd)\]?"),
    "binary": re.compile(r"(?i)\bBINARY\s+\[?([^\];\n]+?)\]?\s*;"),
    "include": re.compile(r"(?i)\$\(\s*(?:Must_)?Include\s*=\s*([^)]+?)\s*\)"),
    "resident": re.compile(r"(?i)\bRESIDENT\b"),
    "join": re.compile(r"(?i)\b(?:INNER|LEFT|RIGHT|OUTER)?\s*JOIN\s*\("),
    "keep": re.compile(r"(?i)\b(?:INNER|LEFT|RIGHT)?\s*KEEP\s*\("),
    "concatenate": re.compile(r"(?i)\bCONCATENATE\s*\("),
    "mapping_load": re.compile(r"(?i)\bMAPPING\s+LOAD\b"),
    "applymap": re.compile(r"(?i)\bApplyMap\s*\("),
    "intervalmatch": re.compile(r"(?i)\bINTERVALMATCH\b"),
    "hierarchy": re.compile(r"(?i)\bHIERARCHY(?:BELONGSTO)?\s*\("),
    "generic_load": re.compile(r"(?i)\bGENERIC\s+LOAD\b"),
    "crosstable": re.compile(r"(?i)\bCROSSTABLE\s*\("),
    "loop": re.compile(r"(?i)\b(?:FOR\s+EACH\b|FOR\s+\w+\s*=|DO\s+WHILE\b|DO\s+UNTIL\b|SUB\s+\w+)"),
    "peek_prev": re.compile(r"(?i)\b(?:Peek|Previous)\s*\("),
    "autonumber": re.compile(r"(?i)\bAutoNumber(?:Hash128|Hash256)?\s*\("),
    "section_access": re.compile(r"(?i)\bSECTION\s+ACCESS\b"),
    "inputfield": re.compile(r"(?i)\bINPUTFIELD\b"),
    "partial_reload": re.compile(r"(?i)\b(?:PARTIAL\s+RELOAD|ADD\s+(?:ONLY\s+)?LOAD|REPLACE\s+(?:ONLY\s+)?LOAD)\b"),
    "execute": re.compile(r"(?i)\bEXECUTE\b"),
    "sleep": re.compile(r"(?i)\bSLEEP\b"),
    "set_let": re.compile(r"(?i)^\s*(SET|LET)\s+([A-Za-z_]\w*)\s*=\s*(.*?);", re.MULTILINE | re.DOTALL),
    "cred_leak": re.compile(r"(?i)\b(?:XUserId|XPassword|Password\s*=|PWD\s*=|User\s*ID\s*=)"),
    "table_label": re.compile(r"(?im)^\s*([A-Za-z_][\w \-]*?):\s*$"),
    "hardcoded_year": re.compile(r"(?i)\bWHERE\b[^;]*?\b(?:19|20)\d{2}\b"),
}

# Expression-level patterns
P_EXPR = {
    "set_analysis": re.compile(r"\{[^{}]*<[^{}]*>[^{}]*\}|\{\s*[$1]\s*\}"),
    "set_current": re.compile(r"\{\s*\$"),
    "set_ignore_all": re.compile(r"\{\s*1"),
    "aggr": re.compile(r"(?i)\baggr\s*\("),
    "rank": re.compile(r"(?i)\brank\s*\("),
    "total": re.compile(r"(?i)\btotal\b"),
    "inter_record": re.compile(r"(?i)\b(?:above|below|before|after|top|bottom)\s*\("),
    "alt_state": re.compile(r"(?i)\{\s*[A-Za-z_]\w*\s*[<}]"),
    "getselect": re.compile(r"(?i)\bGet(?:Selected|Current|Field|Possible)\w*\s*\("),
    "dollar_expand": re.compile(r"\$\("),
    "if_open": re.compile(r"(?i)\bif\s*\("),
    "func": re.compile(r"(?i)\b([a-z_]\w*)\s*\("),
}

MEASURE_HINT = re.compile(
    r"(?i)\b(?:sum|count|avg|min|max|only|median|mode|stdev|concat|firstsortedvalue|aggr|rangesum)\s*\(|[{}]"
)
PATHISH = re.compile(r"(?i)(?:^[a-z]:[\\\\//]|^\\\\\\\\|.qvd$|.qvs$|.txt$|.xlsx?$|[\\\\//]$)")
COLOUR_FN = re.compile(r"(?i)\b(?:RGB|ARGB|Color|LightGreen|Red|Green|Yellow|Blue)\s*\(")


def _count(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text))


def normalise_expression(expr: str) -> str:
    """Collapse whitespace and lowercase so structurally identical expressions dedupe."""
    e = re.sub(r"\s+", " ", expr.strip())
    e = re.sub(r"\s*([(),=<>+\-*/&])\s*", r"\1", e)
    return e.lower()


def max_paren_depth(text: str) -> int:
    depth = best = 0
    for ch in text:
        if ch == "(":
            depth += 1
            best = max(best, depth)
        elif ch == ")":
            depth = max(0, depth - 1)
    return best


def canonical_path(raw: str, pvars: dict[str, str]) -> str:
    """Resolve $(vVar) path variables and normalise separators."""
    p = raw.strip().strip("[]'\"")
    for _ in range(5):
        before = p
        for name, value in pvars.items():
            p = re.sub(r"(?i)\$\(\s*" + re.escape(name) + r"\s*\)", value, p)
        if p == before:
            break
    p = p.replace("\\", "/")
    p = re.sub(r"/{3,}", "//", p)
    p = re.sub(r"(?<!^)//", "/", p)
    lead = "//" if p.startswith("//") else ("/" if p.startswith("/") else "")
    parts: list[str] = []
    for seg in p.lstrip("/").split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg not in (".", ""):
            parts.append(seg)
    p = lead + "/".join(parts)
    return p.rstrip("/").lower()


print("✅ Parser core loaded: strip_comments, 30+ regex patterns, canonical_path, normalise_expression")

# COMMAND ----------

# DBTITLE 1,STEP 2b - Data Structures & Parse Functions
# ══════════════════════════════════════════════════════════════════════
# STEP 2b: Data Structures & Parse Functions
# ══════════════════════════════════════════════════════════════════════

@dataclass
class AppRecord:
    asset_id: str = ""
    asset_name: str = ""
    full_path: str = ""
    asset_type: str = "UNKNOWN"
    script_lines: int = 0
    table_count: int = 0
    sheet_count: int = 0
    chart_object_count: int = 0
    expression_count: int = 0
    distinct_expression_count: int = 0
    set_analysis_count: int = 0
    variable_count: int = 0
    measure_variable_count: int = 0
    calculated_dimension_count: int = 0
    if_nesting_max_depth: int = 0
    macro_line_count: int = 0
    extension_count: int = 0
    aggr_count: int = 0
    nested_aggr_count: int = 0
    alt_state_count: int = 0
    resident_count: int = 0
    join_count: int = 0
    loop_count: int = 0
    generic_load_count: int = 0
    intervalmatch_count: int = 0
    hierarchy_count: int = 0
    applymap_count: int = 0
    peek_previous_count: int = 0
    autonumber_count: int = 0
    sql_select_count: int = 0
    connect_count: int = 0
    source_systems: list = field(default_factory=list)
    qvd_inputs: list = field(default_factory=list)
    qvd_outputs: list = field(default_factory=list)
    binary_load_source: str = ""
    include_files: list = field(default_factory=list)
    blocker_flags: list = field(default_factory=list)
    dollar_expansion_max_depth: int = 0
    top_functions: str = ""
    parse_warnings: list = field(default_factory=list)
    _vars: list = field(default_factory=list, repr=False)


def read_text(p: Path) -> str:
    """Read a file trying common Qlik encodings."""
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return p.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return p.read_bytes().decode("latin-1", errors="replace")


def parse_script(rec: AppRecord, script_raw: str, pvars: dict) -> None:
    """Extract metrics from QlikView load script."""
    rec.script_lines = script_raw.count("\n") + 1
    s = strip_comments(script_raw)

    rec.connect_count = _count(P["connect"], s)
    rec.sql_select_count = _count(P["sql_select"], s)
    rec.resident_count = _count(P["resident"], s)
    rec.join_count = _count(P["join"], s) + _count(P["keep"], s)
    rec.loop_count = _count(P["loop"], s)
    rec.generic_load_count = _count(P["generic_load"], s)
    rec.intervalmatch_count = _count(P["intervalmatch"], s)
    rec.hierarchy_count = _count(P["hierarchy"], s)
    rec.applymap_count = _count(P["applymap"], s)
    rec.peek_previous_count = _count(P["peek_prev"], s)
    rec.autonumber_count = _count(P["autonumber"], s)
    rec.table_count = max(rec.table_count, len(set(P["table_label"].findall(s))))

    rec.qvd_inputs = sorted({
        canonical_path(a or b, pvars) for a, b in P["qvd_read"].findall(s)
    })
    rec.qvd_outputs = sorted({canonical_path(m, pvars) for m in P["qvd_store"].findall(s)})
    rec.include_files = sorted({canonical_path(m, pvars) for m in P["include"].findall(s)})

    bm = P["binary"].search(s)
    if bm:
        rec.binary_load_source = canonical_path(bm.group(1), pvars)

    # Source systems from CONNECT strings
    systems: set = set()
    for groups in P["connect"].findall(s):
        conn = next((g for g in groups if g), "")
        got = re.search(r"(?i)(?:Data\s*Source|Server|Host|DSN|DATABASE)\s*=\s*([^;'\"\)\s]+)", conn)
        systems.add(got.group(1) if got else (conn.strip("[]'\" ") or "UNKNOWN"))
    if rec.qvd_inputs and not systems:
        systems.add("(qvd-only: upstream)")
    rec.source_systems = sorted(systems)

    # Blocker detection (section 2.9 of assessment doc)
    if P["inputfield"].search(s):       rec.blocker_flags.append("B05")
    if P["section_access"].search(s):   rec.blocker_flags.append("B09")
    if P["partial_reload"].search(s):   rec.blocker_flags.append("B15")
    if P["cred_leak"].search(s):        rec.blocker_flags.append("B17")
    if P["execute"].search(s) or P["sleep"].search(s):
        rec.blocker_flags.append("B01?")

    # Variables
    for kind, name, value in P["set_let"].findall(s):
        v = value.strip()
        rec.variable_count += 1
        if MEASURE_HINT.search(v) and not PATHISH.search(v):
            rec.measure_variable_count += 1
        rec.dollar_expansion_max_depth = max(rec.dollar_expansion_max_depth, v.count("$("))
        rec._vars.append((kind.upper(), name, v))

    # Dynamic variable generation inside loops => B13
    for m in P["loop"].finditer(s):
        window = s[m.end(): m.end() + 3000]
        if re.search(r"(?im)^\s*(?:SET|LET)\s+[\w$()]+\s*=", window):
            rec.blocker_flags.append("B13")
            break
    if rec.dollar_expansion_max_depth >= 2:
        rec.blocker_flags.append("B13")


def parse_objects(rec: AppRecord, prj: Path) -> list:
    """Walk every object XML, harvesting expressions in ALL roles."""
    rows = []
    seen_norm: set = set()
    func_counter: Counter = Counter()

    role_by_tag = {
        "expression": "measure", "definition": "measure", "expr": "measure",
        "dimension": "dimension", "dimensiontitle": "dimension",
        "sortcriteria": "sort", "sortexpression": "sort",
        "backgroundcolor": "colour", "textcolor": "colour", "colorexpression": "colour",
        "visualcueupper": "colour", "visualcuelower": "colour",
        "showcondition": "conditional_show", "calccondition": "conditional_show",
        "enablecondition": "conditional_show",
        "caption": "caption", "title": "caption", "label": "caption",
        "referenceline": "reference_line",
        "v": "text_value",
    }

    for xml_path in sorted(prj.glob("*.xml")):
        stem = xml_path.stem.lower()
        if stem.startswith("sheet"):
            rec.sheet_count += 1
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError as exc:
            rec.parse_warnings.append(f"{xml_path.name}: {exc}")
            continue

        obj_type = root.findtext("./ObjectType") or root.tag
        if any(k in obj_type.lower() for k in ("chart", "table", "text", "gauge", "pivot")):
            rec.chart_object_count += 1
        if "extension" in obj_type.lower():
            rec.extension_count += 1
            rec.blocker_flags.append("B03?")

        for el in root.iter():
            role = role_by_tag.get(el.tag.lower())
            if role is None or not (el.text and el.text.strip()):
                continue
            raw = el.text.strip()
            if role in ("caption", "dimension") and not raw.startswith("="):
                if role == "dimension":
                    pass
                else:
                    continue
            if len(raw) < 2:
                continue

            norm = normalise_expression(raw)
            is_calc_dim = role == "dimension" and raw.startswith("=")
            if is_calc_dim:
                rec.calculated_dimension_count += 1

            sa = _count(P_EXPR["set_analysis"], raw)
            aggr = _count(P_EXPR["aggr"], raw)

            rec.expression_count += 1
            rec.set_analysis_count += sa
            rec.aggr_count += aggr
            if aggr >= 2:
                rec.nested_aggr_count += 1
                rec.blocker_flags.append("B12")
            if P_EXPR["alt_state"].search(raw) and not re.match(r"^\s*\{\s*[$1]", raw):
                rec.alt_state_count += 1
            rec.if_nesting_max_depth = max(
                rec.if_nesting_max_depth, _count(P_EXPR["if_open"], raw)
            )
            if role == "colour" and MEASURE_HINT.search(raw):
                rec.blocker_flags.append("B19")

            for fn in P_EXPR["func"].findall(raw):
                func_counter[fn.lower()] += 1

            if norm not in seen_norm:
                seen_norm.add(norm)

            rows.append({
                "asset_id": rec.asset_id,
                "asset_name": rec.asset_name,
                "object_file": xml_path.name,
                "object_type": obj_type,
                "role": role,
                "is_calculated_dimension": is_calc_dim,
                "raw_text": raw,
                "normalised_text": norm,
                "expr_hash": hashlib.sha1(norm.encode()).hexdigest()[:12],
                "char_length": len(raw),
                "nesting_depth": max_paren_depth(raw),
                "set_analysis_count": sa,
                "uses_current_selection": bool(P_EXPR["set_current"].search(raw)),
                "uses_ignore_all": bool(P_EXPR["set_ignore_all"].search(raw)),
                "aggr_count": aggr,
                "rank_count": _count(P_EXPR["rank"], raw),
                "total_qualifier": bool(P_EXPR["total"].search(raw)),
                "inter_record_fn": bool(P_EXPR["inter_record"].search(raw)),
                "get_selection_fn": bool(P_EXPR["getselect"].search(raw)),
                "dollar_expansion": _count(P_EXPR["dollar_expand"], raw),
                "if_count": _count(P_EXPR["if_open"], raw),
            })

    rec.distinct_expression_count = len(seen_norm)
    if rec.alt_state_count:
        rec.blocker_flags.append("B04")
    rec.top_functions = "|".join(f"{f}:{n}" for f, n in func_counter.most_common(15))
    return rows


def parse_doc_properties(rec: AppRecord, prj: Path) -> None:
    """Document-level variables and VBScript/JScript macro module."""
    for name in ("DocProperties.xml", "DocInternals.xml"):
        f = prj / name
        if not f.exists():
            continue
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError as exc:
            rec.parse_warnings.append(f"{name}: {exc}")
            continue

        for el in root.iter():
            tag = el.tag.lower()
            if tag in ("module", "macro", "modulecode", "script") and el.text:
                body = el.text.strip()
                if len(body) > 20 and tag != "script":
                    rec.macro_line_count += body.count("\n") + 1
                    low = body.lower()
                    if any(k in low for k in ("adodb", "opentextfile", 'createobject("scripting', "connection.execute")):
                        rec.blocker_flags.append("B01")
                    if re.search(r"(?i)\b(?:function|sub)\b.*\b(?:sum|total|calc|alloc|rate)\b", body):
                        rec.blocker_flags.append("B02")
            if tag in ("variable", "documentvariable"):
                nm = el.findtext("./Name") or el.get("Name") or ""
                val = el.findtext("./Value") or el.get("Value") or (el.text or "")
                if nm:
                    rec.variable_count += 1
                    if MEASURE_HINT.search(val) and not PATHISH.search(val):
                        rec.measure_variable_count += 1
                    rec._vars.append(("DOC", nm, val.strip()))


def classify_asset_type(rec: AppRecord) -> str:
    has_ui = rec.chart_object_count > 2
    reads_src = rec.sql_select_count > 0 or rec.connect_count > 0
    writes_qvd = bool(rec.qvd_outputs)
    reads_qvd = bool(rec.qvd_inputs)

    if reads_src and writes_qvd and not has_ui and not reads_qvd:
        return "extractor"
    if reads_qvd and writes_qvd and not has_ui:
        return "transformer"
    if reads_qvd and not writes_qvd and not has_ui:
        return "data_model"
    if has_ui and reads_src and writes_qvd:
        return "monolith"
    if has_ui:
        return "frontend"
    if writes_qvd:
        return "transformer"
    return "UNKNOWN"


def classify_variable(name: str, value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1].strip()
    if not v:
        return "empty"
    if COLOUR_FN.search(v):
        return "colour_format"
    if PATHISH.search(v):
        return "config_path"
    if re.search(r"\$\d", v):
        return "parameterised_measure"
    if MEASURE_HINT.search(v):
        return "reusable_measure"
    if re.search(r"(?i)\b(?:today|now|date|monthstart|yearstart|addmonths|makedate)\s*\(", v):
        return "date_anchor"
    if re.fullmatch(r"-?[\d.,]+%?", v):
        return "static_scalar"
    if v.count("$(") >= 1:
        return "dynamic_generated"
    if re.fullmatch(r"[\w \-.,:/]+", v):
        return "label_caption"
    return "UNKNOWN"


print("✅ Data structures and parse functions loaded")
print("   AppRecord dataclass, parse_script, parse_objects, parse_doc_properties")
print("   classify_asset_type, classify_variable")

# COMMAND ----------

# DBTITLE 1,STEP 2c - Batch Processing Driver
# ══════════════════════════════════════════════════════════════════════
# STEP 2c: Batch Processing Driver
# Walks the -prj tree, calls parse functions, collects all rows.
# ══════════════════════════════════════════════════════════════════════

from datetime import datetime

INVENTORY_COLUMNS = [
    "asset_id", "asset_name", "full_path", "asset_type", "script_lines", "table_count",
    "sheet_count", "chart_object_count", "expression_count", "distinct_expression_count",
    "set_analysis_count", "variable_count", "measure_variable_count",
    "calculated_dimension_count", "if_nesting_max_depth", "macro_line_count",
    "extension_count", "aggr_count", "nested_aggr_count", "alt_state_count",
    "resident_count", "join_count", "loop_count", "generic_load_count",
    "intervalmatch_count", "hierarchy_count", "applymap_count", "peek_previous_count",
    "autonumber_count", "sql_select_count", "connect_count",
    "dollar_expansion_max_depth", "source_systems", "qvd_inputs", "qvd_outputs",
    "binary_load_source", "include_files", "blocker_flags", "top_functions",
    "parse_warnings",
]


def process_prj(prj: Path, asset_id: str, pvars: dict):
    """Process a single -prj folder. Returns (record_dict, expr_rows, var_rows, edge_rows)."""
    rec = AppRecord(
        asset_id=asset_id,
        asset_name=prj.name[:-4] if prj.name.lower().endswith("-prj") else prj.name,
        full_path=str(prj.parent / (prj.name[:-4] + ".qvw")),
    )

    # Load script
    script_file = next(
        (p for p in prj.iterdir() if p.name.lower() in ("loadscript.txt", "script.txt")), None
    )
    if script_file:
        parse_script(rec, read_text(script_file), pvars)
    else:
        rec.parse_warnings.append("no LoadScript.txt found")

    # Document properties (macros, doc variables)
    parse_doc_properties(rec, prj)

    # Object XML (expressions, sheets, charts)
    expr_rows = parse_objects(rec, prj)

    # Classify asset type
    rec.asset_type = classify_asset_type(rec)
    rec.blocker_flags = sorted(set(rec.blocker_flags))

    # Variable rows
    var_rows = [
        {
            "asset_id": rec.asset_id,
            "asset_name": rec.asset_name,
            "scope": scope,
            "variable_name": nm,
            "value": val,
            "auto_class": classify_variable(nm, val),
            "dollar_expansion_count": val.count("$("),
            "is_measure_class": classify_variable(nm, val) in ("reusable_measure", "parameterised_measure"),
        }
        for scope, nm, val in rec._vars
    ]

    # Dependency edges
    edges = []
    def edge(src, src_t, tgt, tgt_t, dep, hard=False):
        edges.append({
            "source": src, "source_type": src_t, "target": tgt, "target_type": tgt_t,
            "dependency_type": dep, "is_hard_constraint": hard,
        })

    for sysname in rec.source_systems:
        edge(sysname, "source_system", rec.asset_id, "qvw", "source_to_qvw")
    for q in rec.qvd_inputs:
        edge(q, "qvd", rec.asset_id, "qvw", "qvd_read_by_qvw")
    for q in rec.qvd_outputs:
        edge(rec.asset_id, "qvw", q, "qvd", "qvw_writes_qvd")
    for inc in rec.include_files:
        edge(inc, "include", rec.asset_id, "qvw", "include")
    if rec.binary_load_source:
        edge(rec.binary_load_source, "qvw", rec.asset_id, "qvw", "binary_load", hard=True)

    # Convert record to dict (lists -> pipe-delimited strings for Delta)
    inv_row = {}
    for k in INVENTORY_COLUMNS:
        v = getattr(rec, k)
        inv_row[k] = "|".join(v) if isinstance(v, list) else v
    
    return inv_row, expr_rows, var_rows, edges


def run_batch_assessment(root_path: str, pvars: dict) -> tuple:
    """Walk all *-prj folders under root_path and produce assessment data."""
    root = Path(root_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Root not found: {root}")

    prj_dirs = sorted(p for p in root.rglob("*-prj") if p.is_dir())
    if not prj_dirs:
        raise ValueError(f"No *-prj folders under {root}. Enable 'Generate .prj folder' in QlikView.")

    inventory, expressions, variables, edges = [], [], [], []
    errors = []

    for i, prj in enumerate(prj_dirs, start=1):
        asset_id = f"QVW-{i:04d}"
        try:
            inv_row, e, v, g = process_prj(prj, asset_id, pvars)
            inventory.append(inv_row)
            expressions.extend(e)
            variables.extend(v)
            edges.extend(g)
            print(f"  [{asset_id}] {inv_row['asset_name']}: {inv_row['asset_type']}, "
                  f"{inv_row['script_lines']} lines, {inv_row['expression_count']} expr, "
                  f"blockers={inv_row['blocker_flags'] or 'none'}")
        except Exception as exc:
            errors.append(f"{prj.name}: {type(exc).__name__}: {exc}")
            print(f"  !! {prj.name}: {exc}")

    print(f"\n✅ Batch complete: {len(inventory)} apps parsed, {len(errors)} errors")
    print(f"   Expressions: {sum(r['expression_count'] for r in inventory)} total")
    print(f"   Variables: {len(variables)} total")
    print(f"   Edges: {len(edges)} total")

    return inventory, expressions, variables, edges, errors


print("✅ Batch driver loaded: process_prj(), run_batch_assessment()")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Execute Assessment
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Execute Assessment
# ══════════════════════════════════════════════════════════════════════

if not prj_root:
    print("⚠️ No prj_root specified. Set the widget or pass via orchestrator.")
    print("   Expected: path to folder containing *-prj subdirectories")
    print("   Examples:")
    print("     /Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration/prj-exports/")
    print("     /Volumes/mde_dev/test_schema/qlik_exports/")
    dbutils.notebook.exit("NO_ROOT_PATH")

print(f"🚀 Starting pre-assessment scan...")
print(f"   Root: {prj_root}")
print(f"   Path vars: {path_vars}")
print(f"   Timestamp: {datetime.utcnow().isoformat()}Z")
print("=" * 70)

inventory, expressions, variables, edges, errors = run_batch_assessment(prj_root, path_vars)

# COMMAND ----------

# DBTITLE 1,STEP 4 - Write to Delta Tables
# ══════════════════════════════════════════════════════════════════════
# STEP 4: Write to Delta Tables
# Persists all 4 assessment artifacts to mde_dev.test_schema.
# These tables feed Agent 88 STEP 2b grounded evidence lookup.
# ══════════════════════════════════════════════════════════════════════

from pyspark.sql import functions as F
from pyspark.sql.types import *

assessment_ts = datetime.utcnow().isoformat() + "Z"

if output_mode == "delta" and inventory:
    # --- 1. INVENTORY ---
    inv_schema = StructType([
        StructField("asset_id", StringType()),
        StructField("asset_name", StringType()),
        StructField("full_path", StringType()),
        StructField("asset_type", StringType()),
        StructField("script_lines", IntegerType()),
        StructField("table_count", IntegerType()),
        StructField("sheet_count", IntegerType()),
        StructField("chart_object_count", IntegerType()),
        StructField("expression_count", IntegerType()),
        StructField("distinct_expression_count", IntegerType()),
        StructField("set_analysis_count", IntegerType()),
        StructField("variable_count", IntegerType()),
        StructField("measure_variable_count", IntegerType()),
        StructField("calculated_dimension_count", IntegerType()),
        StructField("if_nesting_max_depth", IntegerType()),
        StructField("macro_line_count", IntegerType()),
        StructField("extension_count", IntegerType()),
        StructField("aggr_count", IntegerType()),
        StructField("nested_aggr_count", IntegerType()),
        StructField("alt_state_count", IntegerType()),
        StructField("resident_count", IntegerType()),
        StructField("join_count", IntegerType()),
        StructField("loop_count", IntegerType()),
        StructField("generic_load_count", IntegerType()),
        StructField("intervalmatch_count", IntegerType()),
        StructField("hierarchy_count", IntegerType()),
        StructField("applymap_count", IntegerType()),
        StructField("peek_previous_count", IntegerType()),
        StructField("autonumber_count", IntegerType()),
        StructField("sql_select_count", IntegerType()),
        StructField("connect_count", IntegerType()),
        StructField("dollar_expansion_max_depth", IntegerType()),
        StructField("source_systems", StringType()),
        StructField("qvd_inputs", StringType()),
        StructField("qvd_outputs", StringType()),
        StructField("binary_load_source", StringType()),
        StructField("include_files", StringType()),
        StructField("blocker_flags", StringType()),
        StructField("top_functions", StringType()),
        StructField("parse_warnings", StringType()),
    ])

    inv_df = spark.createDataFrame(inventory, schema=inv_schema)
    inv_df = inv_df.withColumn("run_id", F.lit(run_id)) \
                   .withColumn("assessed_at", F.lit(assessment_ts))

    inv_df.write.mode("overwrite").option("overwriteSchema", "true") \
        .saveAsTable(f"{target_schema}.qlik_inventory")
    print(f"✅ {target_schema}.qlik_inventory: {len(inventory)} rows")

    # --- 2. EXPRESSIONS CORPUS ---
    if expressions:
        expr_df = spark.createDataFrame(expressions)
        expr_df = expr_df.withColumn("run_id", F.lit(run_id)) \
                         .withColumn("assessed_at", F.lit(assessment_ts))
        expr_df.write.mode("overwrite").option("overwriteSchema", "true") \
            .saveAsTable(f"{target_schema}.qlik_expressions_corpus")
        print(f"✅ {target_schema}.qlik_expressions_corpus: {len(expressions)} rows")

    # --- 3. VARIABLES ---
    if variables:
        var_df = spark.createDataFrame(variables)
        var_df = var_df.withColumn("run_id", F.lit(run_id)) \
                       .withColumn("assessed_at", F.lit(assessment_ts))
        var_df.write.mode("overwrite").option("overwriteSchema", "true") \
            .saveAsTable(f"{target_schema}.qlik_variables")
        print(f"✅ {target_schema}.qlik_variables: {len(variables)} rows")

    # --- 4. DEPENDENCY EDGES ---
    if edges:
        edge_df = spark.createDataFrame(edges)
        edge_df = edge_df.withColumn("run_id", F.lit(run_id)) \
                         .withColumn("assessed_at", F.lit(assessment_ts))
        edge_df.write.mode("overwrite").option("overwriteSchema", "true") \
            .saveAsTable(f"{target_schema}.qlik_dependency_edges")
        print(f"✅ {target_schema}.qlik_dependency_edges: {len(edges)} rows")

    print(f"\n🌟 All 4 Delta tables written to {target_schema}")
    print(f"   Agent 88 can now query grounded evidence via STEP 2b.")

elif output_mode == "display_only" and inventory:
    print("📊 Display-only mode (no Delta writes):")
    display(spark.createDataFrame(inventory))

else:
    print("⚠️ No inventory data to persist. Check prj_root path.")

# COMMAND ----------

# DBTITLE 1,STEP 5 - LLM Augmentation (Migration Readiness Summary)
# ══════════════════════════════════════════════════════════════════════
# STEP 5: LLM Augmentation (Migration Readiness Summary)
# The 5% that benefits from LLM: narrative summary, risk prioritisation,
# and edge-case classification that regex can't reliably determine.
# ══════════════════════════════════════════════════════════════════════

import json

if not inventory:
    print("⚠️ No inventory to summarise.")
    dbutils.notebook.exit("NO_DATA")

# Build summary statistics for LLM context
total_apps = len(inventory)
total_expr = sum(int(r.get("expression_count", 0)) for r in inventory)
total_blockers = sum(1 for r in inventory if r.get("blocker_flags"))
type_dist = Counter(r["asset_type"] for r in inventory)
blocker_dist = Counter(
    b for r in inventory
    for b in (r.get("blocker_flags", "") or "").split("|")
    if b
)
monoliths = [r["asset_name"] for r in inventory if r["asset_type"] == "monolith"]

system_prompt = """You are the Qlik Pre-Assessment Agent (Agent 96) for Hologic's NEXUS platform.

You receive DETERMINISTIC parsing results (exact counts, no hallucination risk) and produce:
1. A migration readiness narrative (2-3 paragraphs)
2. Risk-ranked list of apps requiring manual review
3. Recommended wave sequencing (extractors first, then transformers, then frontends)
4. Blocker resolution priority (which B-codes to address first)

Rules:
- NEVER invent numbers — you are given the exact counts from regex parsing
- If something is UNKNOWN, say so; do not guess
- Monoliths (apps with both source connections AND UI) are highest complexity
- B01 (external calls) and B09 (Section Access) are hard blockers
- B13 (dynamic variables) and B12 (nested AGGR) are soft blockers that need manual review
- Express estimated migration effort in person-days per app category
"""

user_prompt = f"""Pre-Assessment Results (deterministic, verified):

EstateOverview:
- Total apps: {total_apps}
- Total expressions: {total_expr}
- Total variables: {len(variables)}
- Total dependency edges: {len(edges)}
- Apps with blockers: {total_blockers}/{total_apps}

Asset Type Distribution:
{json.dumps(dict(type_dist), indent=2)}

Blocker Distribution:
{json.dumps(dict(blocker_dist), indent=2)}

Monolith Apps (highest complexity): {monoliths or 'None detected'}

Errors during parsing: {len(errors)}
{chr(10).join(errors[:5]) if errors else 'None'}

Please provide the migration readiness summary and recommended wave plan."""

response = call_agent(
    agent_name="96_qlik_preassessment",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=3072
)

print(response)

# COMMAND ----------

# DBTITLE 1,STEP 6 - Validate & Persist Summary
# ══════════════════════════════════════════════════════════════════════
# STEP 6: Validate & Persist Summary
# ══════════════════════════════════════════════════════════════════════

assert len(response) > 100, "LLM response too short"
assert any(kw in response.lower() for kw in ["migration", "wave", "blocker", "complexity"]), \
    "Response missing expected assessment content"

save_agent_output(
    agent_name="96_qlik_preassessment",
    run_id=run_id,
    output_type="preassessment_summary",
    content=response,
    metadata={
        "total_apps": total_apps,
        "total_expressions": total_expr,
        "total_variables": len(variables),
        "total_edges": len(edges),
        "blocker_count": total_blockers,
        "errors": len(errors),
        "prj_root": prj_root,
    }
)

print(f"\n{'='*70}")
print(f"✅ Agent 96 Pre-Assessment COMPLETE")
print(f"{'='*70}")
print(f"   Run ID: {run_id}")
print(f"   Apps parsed: {total_apps}")
print(f"   Delta tables: {target_schema}.qlik_inventory")
print(f"                 {target_schema}.qlik_expressions_corpus")
print(f"                 {target_schema}.qlik_variables")
print(f"                 {target_schema}.qlik_dependency_edges")
print(f"   LLM summary: saved to agent_outputs")
print(f"\n   ➡️  Agent 88 can now run with grounded evidence.")
print(f"   ➡️  Agent 90 can prioritise scripts by complexity.")
print(f"   ➡️  Agent 92 can sort expressions by reuse count.")