"""Generate Copilot / Power BI-developer AI instructions from a Fabric semantic model.

Inspects the full join graph (active/inactive, star flow, bridges), table roles
(fact / dimension / calendar / bridge), measures, and ask-by attributes via
SemPy / TOM, then asks Fabric AI for a business-question-ready brief.
Generation is opt-in (``GENERATE_AI_INSTRUCTIONS = False`` by default).

This file is standalone. If ``%run Utilities`` already loaded Fabric / aifunc
in the same session, those handles are reused and aifunc is not imported again.
It does not run the metadata-sync engine in ``Utilities.py``.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Callable, Optional

import pandas as pd

_aii_logger = logging.getLogger("hda.ai_instructions")
if not _aii_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    _aii_logger.addHandler(_handler)
    _aii_logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Fabric bootstrap — reuse a session that already ran %run Utilities
# ---------------------------------------------------------------------------

_COPILOT_CHAR_LIMIT = 10000  # hard cap: generate / preview / apply never exceed this
_DAX_PREVIEW_CHARS = 180
_DESC_PREVIEW_CHARS = 160
_SNAPSHOT_CHAR_BUDGET = 40000
_TRUNCATION_NOTE = "\n\n[Truncated to 10,000 characters for Copilot.]"

# Known TOM annotation / extended-property names for Prep data for AI text.
# Copilot UI stores instructions in the model (PBIP: Copilot/Instructions/).
_COPILOT_INSTRUCTION_NAMES = (
    "PBI_AIInstructions",
    "PBI_CopilotInstructions",
    "CopilotInstructions",
    "AI_Instructions",
    "AIInstructions",
)

_AUDIENCE_ALIASES = {
    "copilot": "copilot",
    "qa": "copilot",
    "q&a": "copilot",
    "qna": "copilot",
    "pbi_developers": "pbi_developers",
    "pbi_developer": "pbi_developers",
    "pbi": "pbi_developers",
    "developer": "pbi_developers",
    "developers": "pbi_developers",
}

_TECHNICAL_COLUMN_PREFIXES = ("dl_",)
_TECHNICAL_COLUMN_NAMES = frozenset({"rownumber", "row_number", "row number"})

_FACT_ROLES = frozenset({"fact", "fact-like"})
_DIM_ROLES = frozenset({"dimension", "dimension-like", "calendar", "bridge"})
_MIN_USEFUL_AI_CHARS = 400

_ASK_BY_NAME_HINTS = (
    "name", "desc", "title", "label", "hierarchy", "category", "group",
    "type", "status", "region", "country", "customer", "product", "channel",
    "class", "family", "division", "segment", "brand", "line", "idn",
)
_ASK_BY_DATE_HINTS = (
    "date", "year", "month", "quarter", "period", "fiscal", "week", "day",
    "calendar",
)
_PROTECTED_HEADING_HINTS = (
    "facts and dimensions",
    "join flow",
    "how tables join",
    "relationship inventory",
)
_DROP_FIRST_HEADING_HINTS = (
    "example question",
    "do not",
    "copilot / q&a",
    "how to keep the model",
)
_DOMAIN_HINTS = (
    (("revenue", "sales", "asp", "bookings", "booking"), "revenue and sales"),
    (("order", "shipment", "ship", "fulfill"), "orders and fulfillment"),
    (("inventor", "on hand", "stock", "backorder"), "inventory"),
    (("margin", "cost", "cogs", "profit"), "cost and margin"),
    (("forecast", "quota", "pipeline"), "forecast and pipeline"),
)


def _session_already_bootstrapped() -> bool:
    """True when %run Utilities (same IPython namespace) already set Fabric/AI."""
    return bool(
        globals().get("fabric") is not None
        or globals().get("aifunc") is not None
        or globals().get("_SEMPY_AVAILABLE") is True
        or globals().get("_FABRIC_AI_AVAILABLE") is True
    )


def _adopt_bootstrap_from(src: Any) -> bool:
    """Copy Fabric / AI handles from a Utilities module object."""
    global fabric, labs, aifunc, connect_semantic_model
    global _SEMPY_AVAILABLE, _FABRIC_AI_AVAILABLE
    if src is None:
        return False
    fabric = getattr(src, "fabric", None)
    labs = getattr(src, "labs", None)
    aifunc = getattr(src, "aifunc", None)
    connect_semantic_model = getattr(src, "connect_semantic_model", None)
    _SEMPY_AVAILABLE = bool(getattr(src, "_SEMPY_AVAILABLE", fabric is not None))
    _FABRIC_AI_AVAILABLE = bool(getattr(src, "_FABRIC_AI_AVAILABLE", aifunc is not None))
    return True


def _aii_load_synapse_aifunc():
    import synapse.ml.aifunc as mod  # type: ignore

    return mod


def _aii_openai_has_azure_client() -> bool:
    try:
        from openai import AzureOpenAI  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def _aii_ensure_openai_v1_for_aifunc(reason: BaseException) -> None:
    if _aii_openai_has_azure_client():
        return
    flag = os.environ.get("HDA_UPGRADE_OPENAI", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        _aii_logger.warning(
            "openai.AzureOpenAI is missing (%s). Skipping openai upgrade "
            "(HDA_UPGRADE_OPENAI is disabled).",
            reason,
        )
        return
    _aii_logger.info("Installing openai>=1.0.0 so synapse.ml.aifunc can load.")
    try:
        get_ipython().run_line_magic("pip", "install openai>=1.0.0 --quiet")  # noqa: F821
    except Exception as pip_exc:  # noqa: BLE001
        _aii_logger.warning("Could not install openai>=1.0.0 for Fabric AI: %s", pip_exc)


if _session_already_bootstrapped():
    # Same IPython namespace as %run Utilities — do not re-import aifunc.
    fabric = globals().get("fabric")
    labs = globals().get("labs")
    aifunc = globals().get("aifunc")
    connect_semantic_model = globals().get("connect_semantic_model")
    _SEMPY_AVAILABLE = bool(globals().get("_SEMPY_AVAILABLE"))
    _FABRIC_AI_AVAILABLE = bool(globals().get("_FABRIC_AI_AVAILABLE"))
    print(
        "AI instructions: reusing Fabric bootstrap from this session"
        f" | sempy={_SEMPY_AVAILABLE}"
        f" | fabric-ai={_FABRIC_AI_AVAILABLE}"
    )
else:
    _util_mod = sys.modules.get("Utilities") or sys.modules.get("utilities.Utilities")
    if _util_mod is not None and (
        getattr(_util_mod, "fabric", None) is not None
        or getattr(_util_mod, "aifunc", None) is not None
        or getattr(_util_mod, "_SEMPY_AVAILABLE", False)
        or getattr(_util_mod, "_FABRIC_AI_AVAILABLE", False)
    ):
        _adopt_bootstrap_from(_util_mod)
        print(
            "AI instructions: reusing Fabric bootstrap from Utilities"
            f" | sempy={_SEMPY_AVAILABLE}"
            f" | fabric-ai={_FABRIC_AI_AVAILABLE}"
        )
    else:
        try:
            get_ipython().run_line_magic(  # noqa: F821
                "pip", "install semantic-link-labs --quiet"
            )
        except Exception:
            pass

        fabric = None
        labs = None
        aifunc = None
        connect_semantic_model = None
        _SEMPY_AVAILABLE = False
        _FABRIC_AI_AVAILABLE = False

        try:
            import sempy.fabric as fabric  # type: ignore
            import sempy_labs as labs  # type: ignore
            from sempy_labs.tom import connect_semantic_model  # type: ignore

            _SEMPY_AVAILABLE = True
        except ImportError as ex:
            _aii_logger.warning(
                "semantic-link / sempy not available (%s). Fabric TOM calls will degrade.",
                ex,
            )

        if "synapse.ml.aifunc" in sys.modules:
            aifunc = sys.modules["synapse.ml.aifunc"]
            _FABRIC_AI_AVAILABLE = True
        else:
            try:
                aifunc = _aii_load_synapse_aifunc()
                _FABRIC_AI_AVAILABLE = True
            except AttributeError as exc:
                _aii_logger.warning(
                    "Fabric AI import failed (%s). synapse.ml.aifunc requires openai>=1.x.",
                    exc,
                )
                _aii_ensure_openai_v1_for_aifunc(exc)
                try:
                    aifunc = _aii_load_synapse_aifunc()
                    _FABRIC_AI_AVAILABLE = True
                except Exception as retry_exc:  # noqa: BLE001
                    _aii_logger.warning(
                        "Fabric AI (synapse.ml.aifunc) unavailable: %s. "
                        "Inspect and fallback markdown still work.",
                        retry_exc,
                    )
                    aifunc = None
                    _FABRIC_AI_AVAILABLE = False
            except Exception as exc:  # noqa: BLE001
                _aii_logger.warning("Fabric AI (synapse.ml.aifunc) unavailable: %s", exc)
                aifunc = None
                _FABRIC_AI_AVAILABLE = False

        print(
            "AI instructions imports OK"
            f" | sempy={_SEMPY_AVAILABLE}"
            f" | fabric-ai={_FABRIC_AI_AVAILABLE}"
        )


# ---------------------------------------------------------------------------
# Small helpers (do not overwrite Utilities.py names if they already exist)
# ---------------------------------------------------------------------------

def _aii_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _aii_key(value) -> str:
    return _aii_text(value).lower()


def _aii_first_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    if df is None or getattr(df, "empty", True):
        return None
    for name in candidates:
        if name in df.columns:
            return name
    lower = {str(c).strip().lower(): c for c in df.columns}
    for name in candidates:
        hit = lower.get(name.lower())
        if hit:
            return hit
    return None


def _aii_is_hidden(value) -> bool:
    return _aii_key(value) in {"true", "1", "yes"}


def _aii_truncate(text: str, limit: int) -> str:
    text = _aii_text(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _trim_at_boundary(text: str) -> str:
    """Cut near the end at a paragraph, sentence, line, or word boundary."""
    text = text.rstrip()
    if not text:
        return text
    search_from = max(0, len(text) - 800)
    window = text[search_from:]
    para = window.rfind("\n\n")
    if para != -1:
        return text[: search_from + para].rstrip()
    for punct in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
        idx = window.rfind(punct)
        if idx != -1:
            return text[: search_from + idx + 1].rstrip()
    line = window.rfind("\n")
    if line != -1:
        return text[: search_from + line].rstrip()
    space = window.rfind(" ")
    if space != -1:
        return text[: search_from + space].rstrip()
    return text


def _split_md_sections(text: str) -> list[tuple[str, str]]:
    """Split on markdown H2. Returns [(heading_or_'', content_including_heading), ...]."""
    text = _aii_text(text).replace("\r\n", "\n")
    if not text:
        return []
    parts: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            if buf or heading:
                parts.append((heading, "\n".join(buf).rstrip()))
            heading = line.strip()
            buf = [line]
        else:
            buf.append(line)
    if buf or heading:
        parts.append((heading, "\n".join(buf).rstrip()))
    return parts


def _join_md_sections(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(content for _, content in sections if _aii_text(content)).rstrip()


def _heading_matches(heading: str, hints: tuple[str, ...]) -> bool:
    h = _aii_key(heading)
    return any(hint in h for hint in hints)


def _section_is_protected(heading: str, body: str) -> bool:
    if _heading_matches(heading, _PROTECTED_HEADING_HINTS):
        return True
    head = (body or "")[:900]
    return "JOIN FLOW" in head or head.lstrip().startswith("JOIN FLOW")


def _extract_join_flow_block(text: str) -> str:
    """Pull the JOIN FLOW / INACTIVE JOINS block out of markdown, if present."""
    text = _aii_text(text).replace("\r\n", "\n")
    start = text.find("JOIN FLOW")
    if start == -1:
        return ""
    rest = text[start:]
    # Stop at the next H2 after the inactive-joins block (if any).
    cut = len(rest)
    inactive_at = rest.find("INACTIVE JOINS")
    search_from = inactive_at if inactive_at != -1 else 0
    next_h2 = rest.find("\n## ", search_from)
    if next_h2 != -1:
        cut = next_h2
    return rest[:cut].strip()


def _enforce_char_limit(text: str, limit: int = _COPILOT_CHAR_LIMIT) -> str:
    """Hard-cap markdown. Drop example questions first; never drop JOIN FLOW first."""
    text = _aii_text(text)
    if len(text) <= limit:
        return text
    original = len(text)
    note = _TRUNCATION_NOTE
    if len(note) > limit:
        note = note[:limit]
    budget = max(0, limit - len(note))

    sections = _split_md_sections(text)
    if not sections:
        body = _trim_at_boundary(text[:budget])
        result = (body + note)[:limit]
        print(f"AI instructions truncated to {limit:,} characters (was {original}).")
        return result

    def _fits(secs: list[tuple[str, str]]) -> bool:
        return len(_join_md_sections(secs)) <= budget

    # 1) Drop example questions first, then do-not / trailing extras.
    for hint in _DROP_FIRST_HEADING_HINTS:
        if _fits(sections):
            break
        droppable = [
            i
            for i, (h, b) in enumerate(sections)
            if hint in _aii_key(h) and not _section_is_protected(h, b)
        ]
        for idx in reversed(droppable):
            if _fits(sections):
                break
            sections.pop(idx)

    # 2) Shrink remaining non-protected sections from the end.
    if not _fits(sections):
        i = len(sections) - 1
        while i >= 0 and not _fits(sections):
            h, body = sections[i]
            if _section_is_protected(h, body):
                i -= 1
                continue
            overflow = len(_join_md_sections(sections)) - budget
            keep_len = max(0, len(body) - overflow - 8)
            trimmed = _trim_at_boundary(body[:keep_len])
            if trimmed and trimmed != body:
                sections[i] = (h, trimmed)
            else:
                sections.pop(i)
            i -= 1

    # 3) If still over, keep preamble + purpose + how-to-ask + protected join flow.
    if not _fits(sections):
        join_block = _extract_join_flow_block(text)
        kept: list[tuple[str, str]] = []
        for h, body in _split_md_sections(text):
            key = _aii_key(h)
            if not h or "purpose" in key or "how to ask" in key or _section_is_protected(h, body):
                kept.append((h, body))
        if join_block and not any(_section_is_protected(h, b) for h, b in kept):
            kept.append(
                (
                    "## Facts and dimensions (join flow — complete)",
                    "## Facts and dimensions (join flow — complete)\n" + join_block,
                )
            )
        sections = kept

    body = _join_md_sections(sections)
    if len(body) > budget:
        # Last resort: keep as many JOIN FLOW lines as possible.
        join_block = _extract_join_flow_block(body) or _extract_join_flow_block(text)
        if join_block:
            prefix = ""
            for h, content in sections:
                if _section_is_protected(h, content):
                    continue
                if not h or "purpose" in _aii_key(h) or "how to ask" in _aii_key(h):
                    prefix = (prefix + "\n\n" + content).strip() if prefix else content
                    if len(prefix) > max(400, budget // 5):
                        prefix = _trim_at_boundary(prefix[: max(400, budget // 5)])
                        break
            room = budget - len(prefix) - (4 if prefix else 0)
            lines = join_block.splitlines()
            kept_lines: list[str] = []
            used = 0
            for line in lines:
                add = len(line) + (1 if kept_lines else 0)
                if used + add > max(0, room):
                    omitted = len(lines) - len(kept_lines)
                    if omitted > 0:
                        kept_lines.append(f"… {omitted} join lines omitted to fit Copilot limit")
                    break
                kept_lines.append(line)
                used += add
            body = (prefix + "\n\n" + "\n".join(kept_lines)).strip() if prefix else "\n".join(kept_lines)
        body = _trim_at_boundary(body[:budget])

    result = body + note
    if len(result) > limit:
        result = result[:limit]
    print(f"AI instructions truncated to {limit:,} characters (was {original}).")
    return result


def _aii_is_rate_limit_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in ("429", "rate limit", "too many requests", "throttl", "timeout", "temporar")
    )


def _aii_retry_call(
    fn: Callable[[], Any],
    *,
    attempts: int = 4,
    base_delay: float = 1.5,
    label: str = "operation",
) -> Any:
    last: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt >= attempts - 1 or not _aii_is_rate_limit_error(exc):
                _aii_logger.warning("%s failed: %s", label, exc)
                raise
            delay = base_delay * (2 ** attempt)
            _aii_logger.warning("%s failed (%s); retrying in %.1fs", label, exc, delay)
            time.sleep(delay)
    raise last  # pragma: no cover


def _aii_generate_response(df: pd.DataFrame, prompt: str, *, progress_label: str = "") -> list:
    """Call Fabric AISQL / SemPy AI with retries. Same pattern as Utilities.py."""
    existing = globals().get("_ai_generate_response")
    if not callable(existing) or getattr(existing, "__module__", "") == __name__:
        _util = sys.modules.get("Utilities") or sys.modules.get("utilities.Utilities")
        existing = getattr(_util, "_ai_generate_response", None) if _util is not None else None
    if callable(existing) and getattr(existing, "__module__", "") != __name__:
        return existing(df, prompt, progress_label=progress_label)

    if df is None or df.empty:
        return []
    if not _FABRIC_AI_AVAILABLE or aifunc is None:
        _aii_logger.warning("Fabric AI is unavailable; using a structured fallback brief.")
        return [""] * len(df)
    if not hasattr(df, "ai"):
        _aii_logger.warning("Fabric AI (DataFrame.ai) is unavailable; using a structured fallback brief.")
        return [""] * len(df)

    if progress_label:
        print(f"----- Fabric AI: {progress_label} -----", flush=True)

    def _call():
        return list(
            df.ai.generate_response(
                prompt=prompt,
                is_prompt_template=True,
                response_format={"type": "text"},
            )
        )

    try:
        generated = _aii_retry_call(_call, label="Fabric AI generate_response")
        return ["" if x is None else str(x).strip() for x in generated]
    except Exception as exc:  # noqa: BLE001
        _aii_logger.warning("AI generation degraded (%s). Using structured fallback.", exc)
        return [""] * len(df)


def _aii_require_sempy(action: str) -> None:
    if not _SEMPY_AVAILABLE or fabric is None:
        raise RuntimeError(
            f"Cannot {action}: semantic-link / sempy is not available in this environment. "
            "Run this notebook in a Fabric workspace with semantic-link-labs installed."
        )


def _normalize_audience(audience: str) -> str:
    key = _aii_key(audience).replace(" ", "_").replace("-", "_")
    if key not in _AUDIENCE_ALIASES:
        raise ValueError(
            f"audience must be 'copilot' or 'pbi_developers', got {audience!r}"
        )
    return _AUDIENCE_ALIASES[key]


def _is_technical_column(name: str, col_type: str, *, is_rel_key: bool) -> bool:
    if is_rel_key:
        return False
    n = _aii_key(name)
    t = _aii_key(col_type)
    if "rownumber" in t:
        return True
    if n in _TECHNICAL_COLUMN_NAMES:
        return True
    return any(n.startswith(prefix) for prefix in _TECHNICAL_COLUMN_PREFIXES)


def _looks_like_calendar_name(name: str) -> bool:
    n = _aii_key(name)
    if "calendar" in n:
        return True
    if n in {"date", "dates"} or n.endswith(" date") or n.startswith("date "):
        return True
    if "dim date" in n or "dim_date" in n or n.startswith("d_date"):
        return True
    return False


def _looks_like_calendar_table(name: str, columns: list[dict]) -> bool:
    if _looks_like_calendar_name(name):
        return True
    n = _aii_key(name)
    dateish = 0
    for col in columns:
        cn = _aii_key(col.get("name"))
        dt = _aii_key(col.get("data_type"))
        if "date" in dt or any(h in cn for h in _ASK_BY_DATE_HINTS):
            dateish += 1
    return dateish >= 4 and any(x in n for x in ("date", "fiscal", "period", "time"))


def _is_many_to_many(card: str) -> bool:
    c = _aii_key(card).replace(" ", "")
    return (
        "m:m" in c
        or "many:many" in c
        or "*:*" in c
        or "manytomany" in c
        or c in {"mm", "m-m"}
    )


def _is_surrogate_or_id(name: str) -> bool:
    n = _aii_key(name).replace(" ", "_")
    if n in {"id", "sk", "pk", "key", "rownumber"}:
        return True
    return n.endswith("_sk") or n.endswith("_id") or n.endswith("_key") or n.endswith("_pk")


def _classify_table(
    name: str,
    *,
    hidden: bool,
    table_type: str,
    many_side: int,
    one_side: int,
    measure_count: int,
    column_count: int,
) -> str:
    n = _aii_key(name)
    t = _aii_key(table_type)
    if n.startswith("__") or "parameter" in n:
        return "hidden/parameter"
    if n.startswith("_measure") or n in {"_measure", "measures"}:
        return "measure table"
    if "bridge" in n or n.startswith("br_"):
        return "bridge"
    if _looks_like_calendar_name(name):
        return "calendar"
    if n.startswith("fact_") or n.startswith("f_") or n.startswith("fact "):
        return "fact"
    if n.startswith("dim_") or n.startswith("d_") or n.startswith("dim "):
        return "dimension"
    if hidden:
        return "hidden"
    if "calc" in t and many_side == 0 and one_side == 0 and measure_count > 0 and column_count <= 2:
        return "measure table"
    if many_side >= 2 and one_side == 0:
        return "fact-like"
    if one_side >= 1 and many_side == 0:
        return "dimension-like"
    if "calc" in t:
        return "calculated"
    if measure_count > 0 and column_count <= 2:
        return "measure table"
    return "other"


def _first_heading(markdown: str) -> str:
    for line in _aii_text(markdown).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped
    return "(no heading)"


def _table_roles(tables: list[dict]) -> dict[str, str]:
    return {t["name"]: t["role"] for t in tables}


def _upgrade_special_roles(tables: list[dict], relationships: list[dict], columns: list[dict]) -> None:
    """Promote grouping / M2M tables to bridge and date-heavy tables to calendar."""
    cols_by: dict[str, list[dict]] = {}
    for col in columns:
        cols_by.setdefault(col["table"], []).append(col)
    m2m_tables: set[str] = set()
    degree: dict[str, int] = {}
    for rel in relationships:
        degree[rel["from_table"]] = degree.get(rel["from_table"], 0) + 1
        degree[rel["to_table"]] = degree.get(rel["to_table"], 0) + 1
        if _is_many_to_many(rel.get("cardinality") or ""):
            m2m_tables.add(rel["from_table"])
            m2m_tables.add(rel["to_table"])
    for table in tables:
        if table["role"] in {"hidden/parameter", "measure table"}:
            continue
        n = _aii_key(table["name"])
        if table["role"] != "bridge" and (
            "bridge" in n
            or ("grouping" in n and (table["name"] in m2m_tables or degree.get(table["name"], 0) >= 2))
        ):
            table["role"] = "bridge"
        elif table["role"] not in _FACT_ROLES | {"bridge"} and _looks_like_calendar_table(
            table["name"], cols_by.get(table["name"], [])
        ):
            table["role"] = "calendar"


def _ask_by_score(col: dict, role: str) -> int:
    name = _aii_key(col["name"])
    dtype = _aii_key(col.get("data_type"))
    if col.get("hidden"):
        return 0
    if col.get("is_relationship_key") and _is_surrogate_or_id(col["name"]):
        return 0
    if _is_technical_column(col["name"], col.get("type") or "", is_rel_key=False):
        return 0
    score = 0
    if role in {"dimension", "dimension-like", "calendar"}:
        score += 2
    elif role in _FACT_ROLES:
        score += 0
    elif role == "bridge":
        score += 1
    else:
        return 0
    if any(hint in name for hint in _ASK_BY_NAME_HINTS):
        score += 5
    if any(hint in name for hint in _ASK_BY_DATE_HINTS) or "date" in dtype:
        score += 5
    if "hierarch" in name:
        score += 4
    if role == "calendar":
        score += 3
    if dtype in {"string", "text", "widestring", "str"} and not _is_surrogate_or_id(col["name"]):
        score += 1
    if col.get("description"):
        score += 1
    return score


def _select_ask_by_columns(columns: list[dict], tables: list[dict], cap: int = 60) -> list[dict]:
    roles = _table_roles(tables)
    scored: list[tuple[int, dict]] = []
    for col in columns:
        score = _ask_by_score(col, roles.get(col["table"], ""))
        if score > 0:
            scored.append((score, col))
    scored.sort(key=lambda item: (-item[0], item[1]["table"], item[1]["name"]))
    return [col for _, col in scored[:cap]]


def _build_star_flow(tables: list[dict], relationships: list[dict]) -> dict[str, list[dict]]:
    roles = _table_roles(tables)
    star: dict[str, list[dict]] = {}
    for rel in relationships:
        if not rel.get("active", True):
            continue
        from_table, to_table = rel["from_table"], rel["to_table"]
        from_role, to_role = roles.get(from_table, ""), roles.get(to_table, "")
        fact = dim = None
        via_col, to_col = rel.get("from_column") or "", rel.get("to_column") or ""
        if from_role in _FACT_ROLES:
            fact, dim = from_table, to_table
        elif to_role in _FACT_ROLES:
            fact, dim = to_table, from_table
            via_col, to_col = to_col, via_col
        if not fact:
            continue
        star.setdefault(fact, []).append(
            {
                "dim": dim,
                "via": via_col,
                "to_column": to_col,
                "cardinality": rel.get("cardinality") or "",
                "role": roles.get(dim, ""),
            }
        )
    return star


def _format_join_flow_line(rel: dict, roles: dict[str, str]) -> str:
    from_table, to_table = rel["from_table"], rel["to_table"]
    from_col, to_col = rel.get("from_column") or "", rel.get("to_column") or ""
    if from_col and to_col and from_col != to_col:
        key = f"{from_col}→{to_col}"
    else:
        key = from_col or to_col
    tags: list[str] = []
    if roles.get(from_table) == "bridge" or roles.get(to_table) == "bridge":
        tags.append("bridge")
    if _is_many_to_many(rel.get("cardinality") or ""):
        tags.append("many-to-many")
    tag = f", {', '.join(tags)}" if tags else ""
    return f"{from_table} → {to_table} ({key}{tag})"


def _format_join_flow_block(inventory: dict) -> str:
    roles = _table_roles(inventory.get("tables") or [])
    active = [r for r in inventory.get("relationships") or [] if r.get("active", True)]
    inactive = [r for r in inventory.get("relationships") or [] if not r.get("active", True)]

    def _sort_key(rel: dict) -> tuple:
        from_role = roles.get(rel["from_table"], "")
        rank = 0 if from_role in _FACT_ROLES else 1
        return (rank, _aii_key(rel["from_table"]), _aii_key(rel["to_table"]), _aii_key(rel.get("from_column")))

    lines = ["JOIN FLOW"]
    if active:
        for rel in sorted(active, key=_sort_key):
            lines.append(_format_join_flow_line(rel, roles))
    else:
        lines.append("(none found)")
    lines.append("")
    lines.append("INACTIVE JOINS")
    if inactive:
        for rel in sorted(inactive, key=_sort_key):
            lines.append(_format_join_flow_line(rel, roles))
    else:
        lines.append("(none)")
    return "\n".join(lines)


def _format_relationship_line(rel: dict) -> str:
    edge = f"{rel['from_table']}[{rel['from_column']}] → {rel['to_table']}[{rel['to_column']}]"
    bits = []
    if rel.get("cardinality"):
        bits.append(rel["cardinality"])
    bits.append("active" if rel.get("active") else "inactive")
    return f"{edge} ({', '.join(bits)})"


def _infer_domains(inventory: dict) -> list[str]:
    blob = " ".join(
        [inventory.get("dataset_name") or ""]
        + [t["name"] for t in inventory.get("tables") or []]
        + [m["name"] for m in inventory.get("measures") or []]
    ).lower()
    found = []
    for tokens, label in _DOMAIN_HINTS:
        if any(token in blob for token in tokens):
            found.append(label)
    return found


def _visible_measures(inventory: dict) -> list[dict]:
    return [m for m in inventory.get("measures") or [] if not m.get("hidden")]


def _canonical_and_avoid_measures(inventory: dict) -> tuple[list[dict], list[str]]:
    visible = _visible_measures(inventory)
    hidden = [m for m in inventory.get("measures") or [] if m.get("hidden")]
    avoid_notes: list[str] = []
    if hidden:
        avoid_notes.append(f"hidden measures ({len(hidden)}) — do not use in Q&A")
    names = {_aii_key(m["name"]): m["name"] for m in visible}
    revenue = next((n for k, n in names.items() if "revenue" in k and "asp" not in k), None)
    asp = next((n for k, n in names.items() if "asp" in k or "average selling" in k), None)
    units = next(
        (n for k, n in names.items() if k in {"units", "qty", "quantity"} or "unit" in k or "qty" in k),
        None,
    )
    if revenue and asp:
        avoid_notes.append(f"do not substitute [{asp}] for [{revenue}] (price vs total)")
    if revenue and units:
        avoid_notes.append(f"do not treat [{units}] as [{revenue}] (volume vs dollars)")
    canonical = [
        m
        for m in visible
        if not _aii_key(m["name"]).startswith("_")
        and not any(tok in _aii_key(m["name"]) for tok in ("test", "debug", "deprecated", "do not use"))
    ]
    return canonical, avoid_notes


def _derive_example_questions(inventory: dict, limit: int = 10) -> list[str]:
    """Template questions from real measure / ask-by / calendar names."""
    measures = _canonical_and_avoid_measures(inventory)[0] or _visible_measures(inventory)
    if not measures:
        measures = inventory.get("measures") or []
    calendars = [t["name"] for t in inventory.get("tables") or [] if t["role"] == "calendar"]
    ask = inventory.get("ask_by_columns") or []
    facts = [t["name"] for t in inventory.get("tables") or [] if t["role"] in _FACT_ROLES]

    time_label = ""
    slice_labels: list[str] = []
    for col in ask:
        label = f"{col['table']}[{col['name']}]"
        is_time = col["table"] in calendars or any(
            hint in _aii_key(col["name"]) for hint in _ASK_BY_DATE_HINTS
        )
        if is_time and not time_label:
            time_label = label
        elif not is_time:
            slice_labels.append(label)
    if not time_label and calendars:
        time_label = calendars[0]
    if not slice_labels:
        dims = [t["name"] for t in inventory.get("tables") or [] if t["role"] in {"dimension", "dimension-like"}]
        slice_labels = dims[:4]

    def _q_what(measure: str, attr: str, time: str) -> str:
        if attr and time:
            return f"What was [{measure}] last fiscal period by {attr}?"
        if attr:
            return f"What was [{measure}] by {attr}?"
        if time:
            return f"What was [{measure}] last fiscal period ({time})?"
        return f"What was [{measure}] for the latest period?"

    def _q_trend(measure: str, attr: str, time: str) -> str:
        if time:
            return f"How did [{measure}] trend over {time}?"
        return f"How did [{measure}] change over time?"

    def _q_top(measure: str, attr: str, time: str) -> str:
        if attr:
            return f"Which values of {attr} had the highest [{measure}]?"
        return f"What was the highest [{measure}]?"

    def _q_compare(measure: str, attr: str, time: str) -> str:
        if attr:
            return f"Compare [{measure}] by {attr} for the current period."
        return f"What is [{measure}] for the current period?"

    def _q_ytd(measure: str, attr: str, time: str) -> str:
        if time:
            return f"What is year-to-date [{measure}] using {time}?"
        return f"What is year-to-date [{measure}]?"

    templates = (_q_what, _q_trend, _q_top, _q_compare, _q_ytd)
    questions: list[str] = []
    seen: set[str] = set()
    measure_names = [m["name"] for m in measures[:8]] or ["the primary measure"]
    attrs = slice_labels or [""]
    for i in range(max(limit, 5)):
        measure = measure_names[i % len(measure_names)]
        attr = attrs[i % len(attrs)] if attrs else ""
        text = templates[i % len(templates)](measure, attr, time_label)
        if text not in seen:
            seen.add(text)
            questions.append(text)
        if len(questions) >= limit:
            break
    if len(facts) >= 2 and measure_names:
        extra = (
            f"When asking about [{measure_names[0]}], slice only with dimensions joined to "
            f"{facts[0]} (see JOIN FLOW) — do not mix filters from {facts[1]}."
        )
        if extra not in seen and len(questions) < 12:
            questions.append(extra)
    return questions[:12]


def _example_questions_markdown(inventory: dict) -> str:
    lines = ["## Example questions"]
    for q in _derive_example_questions(inventory, limit=10):
        lines.append(f"- {q}")
    return "\n".join(lines)


def _has_join_flow(text: str, inventory: dict | None = None) -> bool:
    t = _aii_text(text)
    if "JOIN FLOW" in t:
        return True
    arrows = sum(1 for line in t.splitlines() if "→" in line or "->" in line)
    expected = sum(
        1 for rel in (inventory or {}).get("relationships") or [] if rel.get("active", True)
    )
    return expected > 0 and arrows >= expected


def _insert_section_after(text: str, section: str, after_hints: tuple[str, ...]) -> str:
    sections = _split_md_sections(text)
    if not sections:
        return section.rstrip() + "\n"
    insert_at = None
    for i, (heading, _) in enumerate(sections):
        if _heading_matches(heading, after_hints):
            insert_at = i + 1
    if insert_at is None:
        insert_at = 1 if sections[0][0] == "" and len(sections) > 1 else (1 if sections[0][0] else 0)
        if insert_at == 0 and sections[0][0]:
            insert_at = 1
    out: list[tuple[str, str]] = []
    inserted = False
    heading_line = section.strip().split("\n", 1)[0]
    for i, item in enumerate(sections):
        if i == insert_at:
            out.append((heading_line, section.rstrip()))
            inserted = True
        out.append(item)
    if not inserted:
        out.append((heading_line, section.rstrip()))
    return _join_md_sections(out)


def _ensure_join_flow_present(text: str, inventory: dict) -> str:
    if _has_join_flow(text, inventory):
        return text
    block = inventory.get("join_flow_text") or _format_join_flow_block(inventory)
    section = "## Facts and dimensions (join flow — complete)\n" + block
    return _insert_section_after(text, section, after_hints=("how to ask", "purpose"))


def _ensure_example_questions(text: str, inventory: dict) -> str:
    if "example question" in _aii_key(text):
        return text
    extras = _example_questions_markdown(inventory)
    return text.rstrip() + "\n\n" + extras


def _enrich_inventory(inventory: dict) -> dict:
    tables = inventory.get("tables") or []
    relationships = inventory.get("relationships") or []
    columns = inventory.get("columns") or []
    _upgrade_special_roles(tables, relationships, columns)
    inventory["star_flow"] = _build_star_flow(tables, relationships)
    inventory["join_flow_text"] = _format_join_flow_block(inventory)
    inventory["ask_by_columns"] = _select_ask_by_columns(columns, tables)
    inventory["calendar_tables"] = [t["name"] for t in tables if t["role"] == "calendar"]
    inventory["bridge_tables"] = [t["name"] for t in tables if t["role"] == "bridge"]
    inventory["inactive_joins"] = [r for r in relationships if not r.get("active", True)]
    inventory["m2m_joins"] = [r for r in relationships if _is_many_to_many(r.get("cardinality") or "")]
    stats = inventory.setdefault("stats", {})
    stats["active_relationships"] = sum(1 for r in relationships if r.get("active", True))
    stats["inactive_relationships"] = len(inventory["inactive_joins"])
    stats["calendars"] = len(inventory["calendar_tables"])
    return inventory


# ---------------------------------------------------------------------------
# Inspect (SemPy list_* with TOM fallback)
# ---------------------------------------------------------------------------

def _empty_frame(*columns: str) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _list_tables(dataset_name: str, workspace_name: str) -> pd.DataFrame:
    try:
        return fabric.list_tables(dataset=dataset_name, workspace=workspace_name)
    except Exception as exc:  # noqa: BLE001
        _aii_logger.warning("fabric.list_tables failed (%s).", exc)
        return _empty_frame("Name", "Description", "Hidden", "Type")


def _list_columns(dataset_name: str, workspace_name: str) -> pd.DataFrame:
    try:
        return fabric.list_columns(dataset=dataset_name, workspace=workspace_name)
    except Exception as exc:  # noqa: BLE001
        _aii_logger.warning("fabric.list_columns failed (%s).", exc)
        return _empty_frame("Table Name", "Column Name", "Description", "Data Type", "Type", "Hidden")


def _list_measures(dataset_name: str, workspace_name: str) -> pd.DataFrame:
    try:
        return fabric.list_measures(dataset=dataset_name, workspace=workspace_name)
    except Exception as exc:  # noqa: BLE001
        _aii_logger.warning("fabric.list_measures failed (%s).", exc)
        return _empty_frame("Table Name", "Measure Name", "Measure Expression", "Description")


def _list_relationships(dataset_name: str, workspace_name: str) -> pd.DataFrame:
    if hasattr(fabric, "list_relationships"):
        try:
            return fabric.list_relationships(dataset=dataset_name, workspace=workspace_name)
        except Exception as exc:  # noqa: BLE001
            _aii_logger.warning("fabric.list_relationships failed (%s). Trying TOM.", exc)
    return _relationships_from_tom(dataset_name, workspace_name)


def _relationships_from_tom(dataset_name: str, workspace_name: str) -> pd.DataFrame:
    cols = ["From Table", "From Column", "To Table", "To Column", "Active", "Cardinality"]
    if not _SEMPY_AVAILABLE or connect_semantic_model is None:
        return _empty_frame(*cols)
    rows = []
    try:
        with connect_semantic_model(
            dataset=dataset_name, workspace=workspace_name, readonly=True
        ) as tom:
            for rel in getattr(tom.model, "Relationships", []) or []:
                from_table = getattr(getattr(rel, "FromTable", None), "Name", "")
                from_col = getattr(getattr(rel, "FromColumn", None), "Name", "")
                to_table = getattr(getattr(rel, "ToTable", None), "Name", "")
                to_col = getattr(getattr(rel, "ToColumn", None), "Name", "")
                from_card = _aii_text(getattr(rel, "FromCardinality", ""))
                to_card = _aii_text(getattr(rel, "ToCardinality", ""))
                card = f"{from_card}:{to_card}" if from_card or to_card else ""
                rows.append(
                    {
                        "From Table": from_table,
                        "From Column": from_col,
                        "To Table": to_table,
                        "To Column": to_col,
                        "Active": bool(getattr(rel, "IsActive", True)),
                        "Cardinality": card,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        _aii_logger.warning("TOM relationship inspect failed (%s).", exc)
    return pd.DataFrame(rows, columns=cols) if rows else _empty_frame(*cols)


def _count_linguistic_synonyms(dataset_name: str, workspace_name: str) -> int:
    """How many linguistic entities already have terms (Q&A synonyms)."""
    if not _SEMPY_AVAILABLE or connect_semantic_model is None:
        return 0
    try:
        with connect_semantic_model(
            dataset=dataset_name, workspace=workspace_name, readonly=True
        ) as tom:
            cultures = getattr(tom.model, "Cultures", None)
            if not cultures:
                return 0
            import json

            count = 0
            for culture in cultures:
                metadata = getattr(culture, "LinguisticMetadata", None)
                content = getattr(metadata, "Content", None) if metadata is not None else None
                if not content:
                    continue
                lm = json.loads(content) if isinstance(content, str) else content
                entities = (lm or {}).get("Entities") or {}
                for entity in entities.values():
                    terms = (entity or {}).get("Terms") or []
                    if terms:
                        count += 1
            return count
    except Exception:
        return 0


def inspect_semantic_model(dataset_name: str, workspace_name: str) -> dict:
    """Collect tables, full relationships, measures, columns, and join-flow inventory."""
    _aii_require_sempy("inspect the semantic model")

    tables_df = _list_tables(dataset_name, workspace_name)
    columns_df = _list_columns(dataset_name, workspace_name)
    measures_df = _list_measures(dataset_name, workspace_name)
    rels_df = _list_relationships(dataset_name, workspace_name)

    t_name = _aii_first_col(tables_df, "Name", "Table Name")
    t_desc = _aii_first_col(tables_df, "Description", "Table Description")
    t_hidden = _aii_first_col(tables_df, "Hidden", "Is Hidden", "IsHidden")
    t_type = _aii_first_col(tables_df, "Type", "Table Type")

    c_table = _aii_first_col(columns_df, "Table Name", "Table")
    c_name = _aii_first_col(columns_df, "Column Name", "Name")
    c_desc = _aii_first_col(columns_df, "Description", "Column Description")
    c_type = _aii_first_col(columns_df, "Type")
    c_dtype = _aii_first_col(columns_df, "Data Type", "DataType", "Type Name")
    c_hidden = _aii_first_col(columns_df, "Hidden", "Is Hidden", "IsHidden")

    m_table = _aii_first_col(measures_df, "Table Name", "Table")
    m_name = _aii_first_col(measures_df, "Measure Name", "Name")
    m_expr = _aii_first_col(measures_df, "Measure Expression", "Expression")
    m_desc = _aii_first_col(measures_df, "Measure Description", "Description")
    m_hidden = _aii_first_col(measures_df, "Hidden", "Is Hidden", "IsHidden")

    r_from_t = _aii_first_col(rels_df, "From Table", "from_table")
    r_from_c = _aii_first_col(rels_df, "From Column", "from_column")
    r_to_t = _aii_first_col(rels_df, "To Table", "to_table")
    r_to_c = _aii_first_col(rels_df, "To Column", "to_column")
    r_active = _aii_first_col(rels_df, "Active", "Is Active", "IsActive")
    r_card = _aii_first_col(
        rels_df, "Cardinality", "Multiplicity", "From Cardinality", "Relationship Type"
    )

    relationships = []
    rel_keys = set()
    role_many: dict[str, int] = {}
    role_one: dict[str, int] = {}
    if r_from_t and r_to_t and not rels_df.empty:
        for _, row in rels_df.iterrows():
            ft = _aii_text(row.get(r_from_t))
            fc = _aii_text(row.get(r_from_c)) if r_from_c else ""
            tt = _aii_text(row.get(r_to_t))
            tc = _aii_text(row.get(r_to_c)) if r_to_c else ""
            if not ft or not tt:
                continue
            if r_active is None:
                active = True
            else:
                raw = row.get(r_active)
                if isinstance(raw, bool):
                    active = raw
                else:
                    active = _aii_key(raw) in {"true", "1", "yes", "active"}
            card = _aii_text(row.get(r_card)) if r_card else ""
            relationships.append(
                {
                    "from_table": ft,
                    "from_column": fc,
                    "to_table": tt,
                    "to_column": tc,
                    "active": active,
                    "cardinality": card,
                }
            )
            if fc:
                rel_keys.add((_aii_key(ft), _aii_key(fc)))
            if tc:
                rel_keys.add((_aii_key(tt), _aii_key(tc)))
            # From side is typically many; To side is typically one.
            role_many[ft] = role_many.get(ft, 0) + 1
            role_one[tt] = role_one.get(tt, 0) + 1

    measures = []
    measures_by_table: dict[str, int] = {}
    if m_name and not measures_df.empty:
        for _, row in measures_df.iterrows():
            name = _aii_text(row.get(m_name))
            table = _aii_text(row.get(m_table)) if m_table else ""
            if not name:
                continue
            hidden = _aii_is_hidden(row.get(m_hidden)) if m_hidden else False
            measures.append(
                {
                    "name": name,
                    "table": table,
                    "description": _aii_text(row.get(m_desc)) if m_desc else "",
                    "dax": _aii_text(row.get(m_expr)) if m_expr else "",
                    "hidden": hidden,
                }
            )
            measures_by_table[table] = measures_by_table.get(table, 0) + 1

    columns = []
    cols_by_table: dict[str, int] = {}
    if c_name and c_table and not columns_df.empty:
        for _, row in columns_df.iterrows():
            table = _aii_text(row.get(c_table))
            name = _aii_text(row.get(c_name))
            if not table or not name:
                continue
            col_type = _aii_text(row.get(c_type)) if c_type else ""
            is_key = (_aii_key(table), _aii_key(name)) in rel_keys
            if _is_technical_column(name, col_type, is_rel_key=is_key):
                continue
            hidden = _aii_is_hidden(row.get(c_hidden)) if c_hidden else False
            columns.append(
                {
                    "table": table,
                    "name": name,
                    "description": _aii_text(row.get(c_desc)) if c_desc else "",
                    "data_type": _aii_text(row.get(c_dtype)) if c_dtype else "",
                    "type": col_type,
                    "hidden": hidden,
                    "is_relationship_key": is_key,
                }
            )
            cols_by_table[table] = cols_by_table.get(table, 0) + 1

    tables = []
    if t_name and not tables_df.empty:
        for _, row in tables_df.iterrows():
            name = _aii_text(row.get(t_name))
            if not name:
                continue
            hidden = _aii_is_hidden(row.get(t_hidden)) if t_hidden else False
            table_type = _aii_text(row.get(t_type)) if t_type else ""
            tables.append(
                {
                    "name": name,
                    "description": _aii_text(row.get(t_desc)) if t_desc else "",
                    "hidden": hidden,
                    "type": table_type,
                    "role": _classify_table(
                        name,
                        hidden=hidden,
                        table_type=table_type,
                        many_side=role_many.get(name, 0),
                        one_side=role_one.get(name, 0),
                        measure_count=measures_by_table.get(name, 0),
                        column_count=cols_by_table.get(name, 0),
                    ),
                }
            )

    synonym_entities = _count_linguistic_synonyms(dataset_name, workspace_name)
    inventory = {
        "dataset_name": dataset_name,
        "workspace_name": workspace_name,
        "tables": tables,
        "relationships": relationships,
        "measures": measures,
        "columns": columns,
        "synonym_entity_count": synonym_entities,
        "stats": {
            "tables": len(tables),
            "relationships": len(relationships),
            "measures": len(measures),
            "columns": len(columns),
        },
    }
    return _enrich_inventory(inventory)


def build_model_snapshot(inventory: dict, *, audience: str) -> str:
    """Compact text inventory: join flow first, then measures and ask-by attributes."""
    if not inventory.get("join_flow_text"):
        _enrich_inventory(inventory)
    stats = inventory.get("stats") or {}
    domains = _infer_domains(inventory)
    header = [
        f"Semantic model: {inventory['dataset_name']}",
        f"Workspace: {inventory['workspace_name']}",
        f"Audience: {audience}",
        (
            f"Counts: {stats.get('tables', 0)} tables, "
            f"{stats.get('relationships', 0)} relationships "
            f"({stats.get('active_relationships', 0)} active / "
            f"{stats.get('inactive_relationships', 0)} inactive), "
            f"{stats.get('measures', 0)} measures, "
            f"{stats.get('columns', 0)} business columns "
            f"(dl_*/RowNumber omitted unless keys)."
        ),
        f"Inferred domain: {', '.join(domains) or 'see table/measure names'}.",
        f"Linguistic synonym entities already on the model: {inventory.get('synonym_entity_count') or 0}",
    ]
    calendars = inventory.get("calendar_tables") or []
    bridges = inventory.get("bridge_tables") or []
    if calendars:
        header.append("Calendars: " + ", ".join(calendars) + ".")
    if bridges:
        header.append("Bridges: " + ", ".join(bridges) + ".")

    star = inventory.get("star_flow") or {}
    star_lines = ["STAR (which dims connect to which facts)"]
    if star:
        for fact, dims in star.items():
            names = []
            seen = set()
            for item in dims:
                dim = item["dim"]
                if dim in seen:
                    continue
                seen.add(dim)
                via = f" via {item['via']}" if item.get("via") else ""
                names.append(f"{dim}{via}")
            star_lines.append(f"{fact}: {'; '.join(names)}")
    else:
        star_lines.append("(no fact→dimension paths classified)")

    role_lines = ["TABLE ROLES (do not repeat as a join list)"]
    for table in inventory.get("tables") or []:
        hid = "hidden" if table["hidden"] else "visible"
        role_lines.append(f"- {table['name']} [{table['role']}, {hid}]")

    join_block = inventory.get("join_flow_text") or _format_join_flow_block(inventory)

    measure_cap = 80 if audience == "pbi_developers" else 45
    dax_chars = _DAX_PREVIEW_CHARS if audience == "pbi_developers" else 90
    measures = inventory.get("measures") or []
    by_table: dict[str, list[dict]] = {}
    for measure in measures:
        by_table.setdefault(measure.get("table") or "(no table)", []).append(measure)
    measure_lines = ["MEASURES BY TABLE (description + short DAX; hidden = avoid in Q&A)"]
    shown = 0
    if not measures:
        measure_lines.append("(none found)")
    else:
        for table_name, group in by_table.items():
            if shown >= measure_cap:
                break
            measure_lines.append(f"[{table_name}]")
            for measure in group:
                if shown >= measure_cap:
                    break
                desc = _aii_truncate(measure.get("description"), _DESC_PREVIEW_CHARS) or "no description"
                hid = " HIDDEN" if measure.get("hidden") else ""
                if audience == "pbi_developers":
                    dax = _aii_truncate(measure.get("dax"), dax_chars) or "no DAX"
                    measure_lines.append(f"- [{measure['name']}]{hid}: {desc} | DAX: {dax}")
                else:
                    extra = f" | DAX: {_aii_truncate(measure.get('dax'), dax_chars)}" if measure.get("dax") else ""
                    measure_lines.append(f"- [{measure['name']}]{hid}: {desc}{extra}")
                shown += 1
        extra = len(measures) - shown
        if extra > 0:
            remaining = ", ".join(m["name"] for m in measures[shown:shown + 40])
            more = f" (+{extra - 40} more)" if extra > 40 else ""
            measure_lines.append(f"Unlisted measures: {remaining}{more}")

    ask = inventory.get("ask_by_columns") or []
    ask_lines = ["ASK BY (slice/filter attributes — names, dates, hierarchies; skip dl_*/RowNumber/SK keys)"]
    if ask:
        by_dim: dict[str, list[str]] = {}
        for col in ask:
            by_dim.setdefault(col["table"], []).append(col["name"])
        for table_name, names in by_dim.items():
            ask_lines.append(f"- {table_name}: {', '.join(names)}")
    else:
        ask_lines.append("(none scored)")

    sample_q = ["SAMPLE BUSINESS QUESTIONS (use these patterns; real names only)"]
    for q in _derive_example_questions(inventory, limit=6):
        sample_q.append(f"- {q}")

    header_text = "\n".join(header)
    rest = "\n\n".join(
        [
            "\n".join(star_lines),
            "\n".join(role_lines),
            "\n".join(measure_lines),
            "\n".join(ask_lines),
            "\n".join(sample_q),
        ]
    )
    snapshot = header_text + "\n\n" + join_block + "\n\n" + rest
    if len(snapshot) <= _SNAPSHOT_CHAR_BUDGET:
        return snapshot
    keep = header_text + "\n\n" + join_block + "\n\n"
    room = max(0, _SNAPSHOT_CHAR_BUDGET - len(keep))
    return keep + _aii_truncate(rest, room)


# ---------------------------------------------------------------------------
# Prompts (one / few batches — not per-row)
# ---------------------------------------------------------------------------

_COPILOT_PROMPT = (
    "You write Power BI Copilot / Q&A instructions a business user will use to ask questions. "
    "Think like a finance / ops analyst, not a model developer. "
    "Read the snapshot. Return markdown only (no preamble). "
    "Stay under 10,000 characters (Power BI Copilot / Prep data for AI hard limit). "
    "Be dense and useful — no padding, no repeating long table-name lists. "
    "Prioritize complete join coverage and how to ask questions. "
    "Use official object names in [Measure] or Table[Column] form. "
    "Do not invent tables, columns, measures, or joins that are not in the snapshot. "
    "Copy the JOIN FLOW and INACTIVE JOINS blocks into the output almost verbatim "
    "so every active relationship appears. Put that join flow near the top "
    "(after Purpose and How to ask) so it survives truncation. "
    "Sections, in this exact order:\n"
    "## Purpose\n"
    "2-3 business sentences: what this model is for "
    "(revenue, orders, inventory, etc. — infer from table/measure names).\n"
    "## How to ask (business Q&A)\n"
    "Tell a business user how to phrase questions. Pattern: "
    "Use measure X when asking about …; slice by dim Y; time is table Z. "
    "Name canonical measures vs avoid-if-redundant "
    "(e.g. ASP vs revenue vs units — do not treat them as interchangeable).\n"
    "## Facts and dimensions (join flow — complete)\n"
    "Paste JOIN FLOW then INACTIVE JOINS from the snapshot. "
    "Every active relationship must appear. "
    "Call out bridges, many-to-many, and inactive paths. "
    "Copilot must not invent joins.\n"
    "## Measures that answer common questions\n"
    "Group by table. One line each: when to use the measure. "
    "Short DAX only if it changes meaning. Prefer complete join flow over long DAX.\n"
    "## Time / grain\n"
    "Name calendar / date tables (Finance Calendar, Posted Calendar, etc.) "
    "and the fact grain implied by JOIN FLOW. Role-playing calendars are not interchangeable.\n"
    "## Example questions\n"
    "5–12 questions using real table/measure names from the snapshot "
    "(e.g. What was Combined Revenue last fiscal period by Product Hierarchy?).\n"
    "## Do not\n"
    "Don't mix incompatible facts; don't use hidden/parameter tables; "
    "don't use inactive relationships as default joins; "
    "don't double-count similar measures.\n"
    "Dataset: {Dataset}. Workspace: {Workspace}. Audience: Copilot.\n"
    "Model snapshot:\n{Model Snapshot}"
)

_PBI_DEV_PROMPT = (
    "You write a Power BI developer brief to make this semantic model AI-ready "
    "(Copilot / Q&A). Read the snapshot. Return markdown only (no preamble). "
    "Stay under 10,000 characters (Power BI Copilot / Prep data for AI hard limit). "
    "Be dense. Use official object names. Do not invent objects. "
    "Copy JOIN FLOW and INACTIVE JOINS almost verbatim so every active relationship appears. "
    "Sections, in this order:\n"
    "## Purpose\n"
    "## Facts and dimensions (join flow — complete)\n"
    "Paste JOIN FLOW then INACTIVE JOINS. Call out bridges, many-to-many, inactive, "
    "and which dims connect to which facts (STAR).\n"
    "## Measures\n"
    "Group by table. Business meaning, grain, time, short DAX note. "
    "Flag measures that can double-count or conflict (ASP vs revenue vs units).\n"
    "## Time / grain\n"
    "Calendar / date tables and role-playing date paths.\n"
    "## How to keep the model AI-ready\n"
    "Concrete next steps: fill blank descriptions, unique Q&A synonyms, hide unused "
    "technical columns (dl_*, RowNumber), verify relationship keys, Prep data for AI.\n"
    "Dataset: {Dataset}. Workspace: {Workspace}. Audience: Power BI developers.\n"
    "Model snapshot:\n{Model Snapshot}"
)


def _fallback_instructions(inventory: dict, audience: str) -> str:
    """Deterministic markdown when Fabric AI is unavailable or too short."""
    if not inventory.get("join_flow_text"):
        _enrich_inventory(inventory)
    stats = inventory.get("stats") or {}
    domains = _infer_domains(inventory)
    facts = [t["name"] for t in inventory["tables"] if t["role"] in _FACT_ROLES]
    dims = [
        t["name"]
        for t in inventory["tables"]
        if t["role"] in {"dimension", "dimension-like"}
    ]
    calendars = inventory.get("calendar_tables") or [
        t["name"] for t in inventory["tables"] if t["role"] == "calendar"
    ]
    bridges = inventory.get("bridge_tables") or [
        t["name"] for t in inventory["tables"] if t["role"] == "bridge"
    ]
    other = [
        t["name"]
        for t in inventory["tables"]
        if t["role"]
        not in _FACT_ROLES | {"dimension", "dimension-like", "calendar", "bridge"}
    ]
    canonical, avoid_notes = _canonical_and_avoid_measures(inventory)
    ask = inventory.get("ask_by_columns") or []
    ask_by_dim: dict[str, list[str]] = {}
    for col in ask:
        ask_by_dim.setdefault(col["table"], []).append(col["name"])
    star = inventory.get("star_flow") or {}
    primary_measure = canonical[0]["name"] if canonical else (
        inventory["measures"][0]["name"] if inventory.get("measures") else "the primary measure"
    )
    time_table = calendars[0] if calendars else (dims[0] if dims else "the date dimension")
    slice_dim = next(iter(ask_by_dim), dims[0] if dims else "the relevant dimension")
    slice_attr = ""
    if ask_by_dim.get(slice_dim):
        slice_attr = f"{slice_dim}[{ask_by_dim[slice_dim][0]}]"
    elif slice_dim:
        slice_attr = slice_dim

    purpose_bits = []
    if domains:
        purpose_bits.append(
            f"This model supports questions about {', '.join(domains)}."
        )
    else:
        purpose_bits.append(
            f"Semantic model **{inventory['dataset_name']}** answers business questions "
            "from its facts, dimensions, and measures."
        )
    if facts:
        purpose_bits.append(
            f"Core fact tables: {', '.join(facts[:6])}"
            + ("." if len(facts) <= 6 else f" (+{len(facts) - 6} more).")
        )
    purpose_bits.append(
        f"{stats.get('tables', 0)} tables, {stats.get('relationships', 0)} relationships, "
        f"{stats.get('measures', 0)} measures."
    )

    how_lines = [
        f"Use [{primary_measure}] when asking about "
        + (
            canonical[0].get("description")
            or primary_measure
        )
        + ".",
        f"Slice / group by {slice_attr or 'joined dimension attributes'} "
        f"(see ASK-BY attributes). Time is **{time_table}**.",
    ]
    if star:
        for fact, linked in list(star.items())[:4]:
            dim_names = []
            seen = set()
            for item in linked:
                if item["dim"] not in seen:
                    seen.add(item["dim"])
                    dim_names.append(item["dim"])
            how_lines.append(f"{fact} slices with: {', '.join(dim_names)}.")
    if canonical:
        how_lines.append(
            "Canonical measures: "
            + ", ".join(f"[{m['name']}]" for m in canonical[:12])
            + ("." if len(canonical) <= 12 else f" (+{len(canonical) - 12} more).")
        )
    if avoid_notes:
        how_lines.append("Avoid if redundant: " + "; ".join(avoid_notes) + ".")

    lines = [
        f"# AI instructions — {inventory['dataset_name']}",
        "",
        "## Purpose",
        " ".join(purpose_bits),
        "",
        "## How to ask (business Q&A)",
        *how_lines,
        "",
        "## Facts and dimensions (join flow — complete)",
        inventory.get("join_flow_text") or _format_join_flow_block(inventory),
    ]
    if bridges:
        lines.append(f"Bridge / many-to-many tables: {', '.join(bridges)}.")
    if other:
        lines.append(f"Hidden / calc / parameter / other (do not use as business dims): {', '.join(other)}.")

    lines.extend(["", "## Measures that answer common questions"])
    if not inventory.get("measures"):
        lines.append("No measures found.")
    else:
        by_table: dict[str, list[dict]] = {}
        for measure in canonical or inventory["measures"]:
            by_table.setdefault(measure.get("table") or "(no table)", []).append(measure)
        shown = 0
        cap = 36 if audience == "copilot" else 48
        for table_name, group in by_table.items():
            if shown >= cap:
                break
            lines.append(f"**{table_name}**")
            for measure in group:
                if shown >= cap:
                    break
                desc = _aii_truncate(measure.get("description"), 100) or "use only with official name"
                lines.append(f"- [{measure['name']}]: {desc}")
                shown += 1
        extra = len(inventory["measures"]) - shown
        if extra > 0:
            lines.append(f"- … {extra} additional measures on the model — use official names only.")

    lines.extend(["", "## Time / grain"])
    if calendars:
        lines.append(
            "Calendar / date tables: "
            + ", ".join(calendars)
            + ". Role-playing calendars are not interchangeable — pick the one joined to the fact in JOIN FLOW."
        )
    else:
        lines.append(
            "No dedicated calendar table was classified. Use the date column/table shown on the fact in JOIN FLOW."
        )
    if facts:
        lines.append(
            f"Fact grain follows the relationship keys on {', '.join(facts[:5])}"
            + ("." if len(facts) <= 5 else f" (+{len(facts) - 5} more).")
        )

    lines.extend(["", _example_questions_markdown(inventory)])
    lines.extend(
        [
            "",
            "## Do not",
            "- Do not mix incompatible facts in one question; only slice a measure with dimensions joined to its fact (JOIN FLOW).",
            "- Do not use hidden, `__`-prefixed, or parameter tables as business dimensions.",
            "- Do not treat inactive relationships as default join paths (see INACTIVE JOINS).",
            "- Do not double-count similar measures (revenue vs ASP vs units).",
            "- Do not invent joins, tables, or measures that are not listed here.",
            f"- Prefer synonyms already on the model "
            f"({inventory.get('synonym_entity_count') or 0} linguistic entities have terms).",
        ]
    )
    if audience == "pbi_developers":
        lines.extend(
            [
                "",
                "## How to keep the model AI-ready",
                "- Fill blank descriptions on tables, columns, and measures (metadata sync).",
                "- Keep Q&A synonyms unique across the model.",
                "- Hide unused technical columns (dl_*, RowNumber); keep relationship keys.",
                "- After reviewing this brief, paste a shorter Copilot version into "
                "**Prep data for AI → Add AI instructions** (10,000 character limit).",
            ]
        )
    return "\n".join(lines)


def generate_instructions(inventory: dict, audience: str) -> str:
    """Build the structured snapshot first, then one batched Fabric AI call."""
    if not inventory.get("join_flow_text"):
        _enrich_inventory(inventory)
    snapshot = build_model_snapshot(inventory, audience=audience)
    prompt = _COPILOT_PROMPT if audience == "copilot" else _PBI_DEV_PROMPT
    frame = pd.DataFrame(
        [
            {
                "Dataset": inventory["dataset_name"],
                "Workspace": inventory["workspace_name"],
                "Model Snapshot": snapshot,
            }
        ]
    )
    label = (
        f"AI instructions ({audience}, "
        f"{inventory['stats']['tables']} tables / "
        f"{inventory['stats']['measures']} measures)"
    )
    generated = _aii_generate_response(frame, prompt, progress_label=label)
    text = generated[0] if generated else ""
    if not _aii_text(text) or len(_aii_text(text)) < _MIN_USEFUL_AI_CHARS:
        text = _fallback_instructions(inventory, audience)
    else:
        text = _ensure_join_flow_present(text, inventory)
        text = _ensure_example_questions(text, inventory)
    return _enforce_char_limit(text, limit=_COPILOT_CHAR_LIMIT)


# ---------------------------------------------------------------------------
# Apply — TOM annotation / extended property, never fail the notebook
# ---------------------------------------------------------------------------

def _iter_annotations(model) -> list:
    anns = getattr(model, "Annotations", None)
    if anns is None:
        return []
    try:
        return list(anns)
    except Exception:
        return []


def _existing_instruction_name(model) -> Optional[str]:
    known = {_aii_key(n): n for n in _COPILOT_INSTRUCTION_NAMES}
    for ann in _iter_annotations(model):
        name = _aii_text(getattr(ann, "Name", ""))
        if _aii_key(name) in known:
            return name
    if hasattr(model, "ExtendedProperties"):
        try:
            for prop in model.ExtendedProperties:
                name = _aii_text(getattr(prop, "Name", ""))
                if _aii_key(name) in known:
                    return name
        except Exception:
            pass
    return None


def _write_copilot_instructions(tom, text: str) -> tuple[bool, str]:
    """Best-effort write. Returns (wrote, target_name). Never raises to the caller."""
    model = getattr(tom, "model", tom)
    target = _existing_instruction_name(model) or _COPILOT_INSTRUCTION_NAMES[0]

    if hasattr(tom, "set_annotation"):
        try:
            tom.set_annotation(model, target, text)
            return True, f"annotation:{target}"
        except Exception as exc:  # noqa: BLE001
            _aii_logger.warning("tom.set_annotation failed (%s).", exc)

    try:
        anns = getattr(model, "Annotations", None)
        if anns is not None:
            existing = None
            for ann in _iter_annotations(model):
                if _aii_text(getattr(ann, "Name", "")) == target:
                    existing = ann
                    break
            if existing is not None:
                existing.Value = text
                return True, f"annotation:{target}"
            try:
                from Microsoft.AnalysisServices.Tabular import Annotation  # type: ignore

                ann = Annotation()
                ann.Name = target
                ann.Value = text
                anns.Add(ann)
                return True, f"annotation:{target}"
            except Exception as exc:  # noqa: BLE001
                _aii_logger.warning("TOM Annotation add failed (%s).", exc)
    except Exception as exc:  # noqa: BLE001
        _aii_logger.warning("TOM Annotations write failed (%s).", exc)

    if hasattr(tom, "set_extended_property"):
        try:
            tom.set_extended_property(model, "String", target, text)
            return True, f"extended_property:{target}"
        except Exception as exc:  # noqa: BLE001
            _aii_logger.warning("tom.set_extended_property failed (%s).", exc)

    return False, ""


def _paste_instructions_message() -> str:
    return (
        "Could not write Copilot instructions via TOM "
        f"(tried {', '.join(_COPILOT_INSTRUCTION_NAMES)}). "
        "Preview-only: paste the markdown into Power BI "
        "**Prep data for AI → Add AI instructions** "
        f"(Copilot limit {_COPILOT_CHAR_LIMIT:,} characters). "
        "The notebook was not failed."
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_SESSION_AI_ENGINE: Optional["AIInstructionEngine"] = None


class AIInstructionEngine:
    """Inspect a Fabric semantic model and draft Copilot / developer AI instructions.

    ``build()`` reads SemPy/TOM and calls Fabric AI once (batched).
    ``preview()`` returns markdown. ``apply(apply_changes=False)`` is dry-run.
    Nothing is written until ``apply(apply_changes=True)``.
    """

    def __init__(
        self,
        dataset_name: str,
        workspace_name: str,
        audience: str = "copilot",
    ):
        self.dataset_name = _aii_text(dataset_name)
        self.workspace_name = _aii_text(workspace_name)
        if not self.dataset_name or not self.workspace_name:
            raise ValueError("dataset_name and workspace_name are required.")
        self.audience = _normalize_audience(audience)
        self.inventory: Optional[dict] = None
        self.markdown: str = ""
        self.last_summary: Optional[dict] = None

    def build(self) -> "AIInstructionEngine":
        print(f"=== AI instructions: build (audience={self.audience}) ===")
        self.inventory = inspect_semantic_model(self.dataset_name, self.workspace_name)
        stats = self.inventory["stats"]
        print(
            f"  Tables: {stats['tables']} | Relationships: {stats['relationships']} "
            f"| Measures: {stats['measures']}"
        )
        self.markdown = generate_instructions(self.inventory, self.audience)
        print("=== AI instructions ready (preview below) ===")
        return self

    def preview(self) -> str:
        if not self.markdown:
            return (
                "No AI instructions generated yet. "
                "Call build() after setting GENERATE_AI_INSTRUCTIONS=True."
            )
        self.markdown = _enforce_char_limit(self.markdown)
        return self.markdown

    def apply(self, apply_changes: bool = False) -> dict:
        """Dry-run by default. apply_changes=True writes Copilot instructions when TOM allows."""
        if not self.markdown:
            print("=== AI instructions: apply skipped (run build() first) ===")
            summary = {"status": "not_built", "wrote": False, "characters": 0}
            self.last_summary = summary
            return summary

        self.markdown = _enforce_char_limit(self.markdown)
        n = len(self.markdown)
        heading = _first_heading(self.markdown)
        if not apply_changes:
            print("=== AI instructions: dry-run ===")
            print(f"  Length: {n} characters")
            print(f"  First heading: {heading}")
            print("  Nothing written (apply_changes=False).")
            summary = {
                "status": "dry_run",
                "wrote": False,
                "characters": n,
                "first_heading": heading,
                "audience": self.audience,
            }
            self.last_summary = summary
            return summary

        print("=== AI instructions: apply ===")
        print(f"  Length: {n} characters")
        print(f"  First heading: {heading}")

        wrote = False
        target = ""
        if not _SEMPY_AVAILABLE or connect_semantic_model is None:
            print(f"  {_paste_instructions_message()}")
        else:
            try:
                with connect_semantic_model(
                    dataset=self.dataset_name,
                    workspace=self.workspace_name,
                    readonly=False,
                ) as tom:
                    wrote, target = _write_copilot_instructions(tom, self.markdown)
            except Exception as exc:  # noqa: BLE001
                _aii_logger.warning("connect_semantic_model write failed (%s).", exc)
                wrote = False

            if wrote:
                print(f"  Wrote Copilot instructions via TOM ({target}).")
            else:
                print(f"  {_paste_instructions_message()}")

        summary = {
            "status": "written" if wrote else "preview_only",
            "wrote": wrote,
            "target": target,
            "characters": n,
            "first_heading": heading,
            "audience": self.audience,
        }
        self.last_summary = summary
        return summary


def init_ai_instructions(
    dataset_name: str = None,
    workspace_name: str = None,
    audience: str = "copilot",
) -> AIInstructionEngine:
    """Create the session AI-instruction engine. Does not generate until ``build()``."""
    global _SESSION_AI_ENGINE
    if dataset_name is None:
        dataset_name = globals().get("DATASET_NAME")
    if workspace_name is None:
        workspace_name = globals().get("WORKSPACE_NAME")
    engine = AIInstructionEngine(
        dataset_name=dataset_name,
        workspace_name=workspace_name,
        audience=audience,
    )
    _SESSION_AI_ENGINE = engine
    return engine


def get_ai_instruction_engine() -> AIInstructionEngine:
    if _SESSION_AI_ENGINE is None:
        raise RuntimeError(
            "No AIInstructionEngine in this session. "
            "Call init_ai_instructions(...) first."
        )
    return _SESSION_AI_ENGINE
