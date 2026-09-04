from __future__ import annotations

# Fabric notebooks: install once. Local/dev imports skip the magic.
try:
    get_ipython().run_line_magic(  # noqa: F821
        "pip", "install semantic-link-labs databricks-sql-connector --quiet"
    )
except Exception:
    pass

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Callable, Iterable, Optional, Union

import pandas as pd

logger = logging.getLogger("hda.metadata_sync")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

fabric = None
labs = None
aifunc = None
databricks_sql = None
connect_semantic_model = None
_SEMPY_AVAILABLE = False
_DATABRICKS_SQL_AVAILABLE = False
_FABRIC_AI_AVAILABLE = False

try:
    import sempy.fabric as fabric  # type: ignore
    import sempy_labs as labs  # type: ignore
    from sempy_labs.tom import connect_semantic_model  # type: ignore

    _SEMPY_AVAILABLE = True
except ImportError as ex:
    logger.warning("semantic-link / sempy not available (%s). Fabric TOM calls will degrade.", ex)


def _openai_has_azure_client() -> bool:
    """True when openai>=1.x is loaded (AzureOpenAI exists). Fabric often ships 0.x."""
    try:
        from openai import AzureOpenAI  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def _ensure_openai_v1_for_aifunc(reason: BaseException) -> None:
    """Install openai>=1.x only when aifunc cannot load because AzureOpenAI is missing."""
    if _openai_has_azure_client():
        return
    flag = os.environ.get("HDA_UPGRADE_OPENAI", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        logger.warning(
            "openai.AzureOpenAI is missing (%s). Skipping openai upgrade "
            "(HDA_UPGRADE_OPENAI is disabled).",
            reason,
        )
        return
    logger.info(
        "Installing openai>=1.0.0 so synapse.ml.aifunc can load (needs AzureOpenAI)."
    )
    try:
        get_ipython().run_line_magic(  # noqa: F821
            "pip", "install openai>=1.0.0 --quiet"
        )
    except Exception as pip_exc:  # noqa: BLE001
        logger.warning("Could not install openai>=1.0.0 for Fabric AI: %s", pip_exc)
        return
    for name in list(sys.modules):
        if name == "openai" or name.startswith("openai."):
            del sys.modules[name]


def _load_synapse_aifunc():
    import synapse.ml.aifunc as mod  # type: ignore

    return mod


try:
    aifunc = _load_synapse_aifunc()
    _FABRIC_AI_AVAILABLE = True
except AttributeError as exc:
    # openai 0.x: module 'openai' has no attribute 'AzureOpenAI'
    logger.warning(
        "Fabric AI import failed (%s). synapse.ml.aifunc requires openai>=1.x.",
        exc,
    )
    _ensure_openai_v1_for_aifunc(exc)
    try:
        aifunc = _load_synapse_aifunc()
        _FABRIC_AI_AVAILABLE = True
    except (ImportError, AttributeError, Exception) as retry_exc:  # noqa: BLE001
        logger.warning(
            "Fabric AI (synapse.ml.aifunc) unavailable: %s. "
            "Mapping, preview, edit, and dry-run still work without AI.",
            retry_exc,
        )
        aifunc = None
        _FABRIC_AI_AVAILABLE = False
except ImportError as exc:
    logger.warning("Fabric AI (synapse.ml.aifunc) unavailable: %s", exc)
    aifunc = None
except Exception as exc:  # noqa: BLE001
    logger.warning("Fabric AI (synapse.ml.aifunc) unavailable: %s", exc)
    aifunc = None

try:
    from databricks import sql as databricks_sql  # type: ignore

    _DATABRICKS_SQL_AVAILABLE = True
except ImportError as ex:
    logger.warning("databricks-sql-connector not available (%s). Warehouse queries will degrade.", ex)

try:
    display  # type: ignore  # noqa: F821
except NameError:  # local/dev
    def display(obj):  # type: ignore
        if isinstance(obj, pd.DataFrame):
            print(obj.to_string(index=False))
        else:
            print(obj)

print(
    "Imports OK"
    f" | sempy={_SEMPY_AVAILABLE}"
    f" | databricks-sql={_DATABRICKS_SQL_AVAILABLE}"
    f" | fabric-ai={_FABRIC_AI_AVAILABLE}"
)


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in ("429", "rate limit", "too many requests", "throttl", "timeout", "temporar")
    )


def _retry_call(
    fn: Callable[[], Any],
    *,
    attempts: int = 4,
    base_delay: float = 1.5,
    label: str = "operation",
) -> Any:
    """Retry transient / rate-limit failures with exponential backoff."""
    last: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt >= attempts - 1 or not _is_rate_limit_error(exc):
                logger.warning("%s failed: %s", label, exc)
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning("%s failed (%s); retrying in %.1fs", label, exc, delay)
            time.sleep(delay)
    raise last  # pragma: no cover


_FABRIC_AI_SKIP_PRINTED = False


def _reset_fabric_ai_skip_log() -> None:
    global _FABRIC_AI_SKIP_PRINTED
    _FABRIC_AI_SKIP_PRINTED = False


def _log_fabric_ai_unavailable(reason: str) -> None:
    """Print once per build so Proposed Description / Synonyms are never silently blank."""
    global _FABRIC_AI_SKIP_PRINTED
    logger.warning("Fabric AI unavailable (%s); skipping generation.", reason)
    if _FABRIC_AI_SKIP_PRINTED:
        return
    _FABRIC_AI_SKIP_PRINTED = True
    print(
        "Step 2/3 — Fabric AI unavailable "
        f"({reason}). Blank uncovered descriptions and Proposed Synonyms "
        "will stay empty until Fabric AI (synapse.ml.aifunc / DataFrame.ai) is available.",
        flush=True,
    )


def _ai_generate_response(df: pd.DataFrame, prompt: str, *, progress_label: str = "") -> list:
    """Call Fabric AISQL / SemPy AI with retries. Returns one string per row.

    Fabric's tqdm bar is hardcoded as ``ai.generate_response`` (no desc= on the
    pandas API). Print a banner immediately before the call so the notebook
    shows what is being generated above that bar.
    """
    if df is None or df.empty:
        return []
    if not _FABRIC_AI_AVAILABLE or aifunc is None:
        _log_fabric_ai_unavailable("synapse.ml.aifunc is not loaded")
        return [""] * len(df)
    if not hasattr(df, "ai"):
        _log_fabric_ai_unavailable("DataFrame.ai accessor is not registered")
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
        generated = _retry_call(_call, label="Fabric AI generate_response")
        return ["" if x is None else str(x).strip() for x in generated]
    except Exception as exc:  # noqa: BLE001
        _log_fabric_ai_unavailable(str(exc))
        logger.warning("AI generation degraded (%s). Returning empty descriptions.", exc)
        return [""] * len(df)


def _require_sempy(action: str) -> None:
    if not _SEMPY_AVAILABLE or fabric is None or connect_semantic_model is None:
        raise RuntimeError(
            f"Cannot {action}: semantic-link / sempy is not available in this environment. "
            "Run this notebook in a Fabric workspace with semantic-link-labs installed."
        )


def _get_spark():
    """Return an active SparkSession when running on Databricks / Fabric Spark."""
    try:
        from pyspark.sql import SparkSession  # type: ignore

        return SparkSession.getActiveSession()
    except Exception:
        return None


def _first_col(df: pd.DataFrame, *candidates: str):
    for name in candidates:
        if name in df.columns:
            return name
    return None


def _is_hidden(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def _clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip()


def _blank_text_mask(series: pd.Series) -> pd.Series:
    """True where values are null, NaN, or whitespace-only."""
    return _clean_text(series).eq("")


def _mark_generated_description_source(
    frame: pd.DataFrame,
    generated_mask: pd.Series,
    was_blank_mask: pd.Series,
    desc_col: str = "Desc",
) -> None:
    """Label this run's AI output. Empty results stay Missing, never Existing."""
    still_blank = _blank_text_mask(frame[desc_col])
    filled = generated_mask & ~still_blank
    frame.loc[filled & was_blank_mask, "Description Source"] = "Generated now"
    frame.loc[filled & ~was_blank_mask, "Description Source"] = "Regenerated"
    frame.loc[generated_mask & still_blank, "Description Source"] = "Missing, not generated"


def _apply_snapshot_originals(
    frame: pd.DataFrame,
    existing_descriptions: Optional[dict],
    kind: str,
    table_col: str,
    name_col: str,
    desc_col: str = "Desc",
) -> None:
    """Prefer a live-model snapshot so a wipe is visible to generate_missing_*."""
    if not existing_descriptions or frame is None or frame.empty:
        return
    sample = next(iter(existing_descriptions), None)
    if not (isinstance(sample, tuple) and len(sample) == 3):
        return

    def pick(row):
        tkey = _key(row.get(table_col))
        nkey = _key(row.get(name_col)) if name_col else tkey
        key = (kind, tkey, nkey)
        if key in existing_descriptions:
            return _text(existing_descriptions[key])
        return _text(row.get(desc_col))

    frame[desc_col] = frame.apply(pick, axis=1)


def _table_originals_from_snapshot(existing_descriptions: Optional[dict]) -> Optional[dict]:
    """{table_key: desc} from a snapshot dict, or None when nothing was passed."""
    if not existing_descriptions:
        return None
    sample = next(iter(existing_descriptions), None)
    if isinstance(sample, tuple) and len(sample) == 3:
        return {
            table_key: desc
            for (kind, table_key, _object_key), desc in existing_descriptions.items()
            if kind == "table"
        }
    return dict(existing_descriptions)


MIN_SYNONYMS = 5
MAX_SYNONYMS = 10
MIN_COLUMN_SYNONYMS = 5
MAX_COLUMN_SYNONYMS = 10
MIN_MEASURE_SYNONYMS = 10
MAX_MEASURE_SYNONYMS = 12
MIN_TABLE_SYNONYMS = 3
MAX_TABLE_SYNONYMS = 5

COLUMN_SYNONYM_PROMPT = (
    "You write Power BI Q&A and Copilot synonyms for a column. "
    "Read the descriptions first and understand the business meaning. Then invent everyday phrases a report user would type to find this field. "
    "Return 5 to 10 synonyms. "
    "Each synonym must be 2 to 6 ordinary business words. "
    "Do not repeat or lightly rephrase the column name. "
    "Do not change only spacing, hyphens, capitalization, or underscores in the column name. "
    "Do not use technical IDs, camel case, snake_case, or DAX. "
    "If the description explains an acronym, expand that acronym in some synonyms. "
    "Include a mix of short labels, longer phrases, and natural question fragments. "
    "Return only a comma-separated list. No numbering, quotes, or extra text. "
    "Column name, do not reuse this wording: {Column Name}. "
    "Table name: {Table Name}. "
    "Table description: {Table Description}. "
    "Column description: {Desc}."
)

COLUMN_SYNONYM_RETRY_PROMPT = (
    "Previous synonyms were too close to the column name. Try again. "
    "Invent 8 everyday business phrases based only on the descriptions. "
    "Do not use any wording from the forbidden list. "
    "Return only a comma-separated list. "
    "Forbidden wording: {Forbidden}. "
    "Table name: {Table Name}. "
    "Table description: {Table Description}. "
    "Column name: {Column Name}. "
    "Column description: {Desc}."
)

MEASURE_SYNONYM_PROMPT = (
    "You write Power BI Q&A and Copilot synonyms for a measure. "
    "The business description is the source of truth. Use it to understand what the KPI means to a business user. "
    "Use the DAX only to understand the calculation type, such as total, average, percent, days, snapshot, or balance. Never copy DAX names or function names. "
    "Return at least 10 unique synonyms a business user would actually say or type. "
    "Each synonym must be 2 to 6 ordinary words. "
    "Do not repeat or lightly rephrase the measure name. "
    "Do not return the measure name with different spacing, hyphens, capitalization, or underscores. "
    "Do not use camel case, snake_case, technical IDs, or DAX function names. "
    "If the description explains an acronym, expand that acronym in several synonyms. "
    "Cover different ask styles: a short KPI label, a longer business phrase, a how-much/how-many fragment, a common alias, and a plain-English restatement of the description. "
    "Good example: measure 'DIOH Card', description 'Average number of days of inventory on hand' -> "
    "days of inventory, inventory days, stock coverage days, days on hand, days of supply, inventory holding period, how many days of stock, inventory runout days, stock day cover, days inventory outstanding. "
    "Bad example: DIOH Card, DIOH, dioh_card, DIOHCard, DIOH Measure. "
    "Good example: measure 'Total On Hand Value', description 'Total inventory value currently on hand' -> "
    "inventory value, stock value, on-hand inventory dollars, warehouse inventory worth, current inventory amount, value of available stock, inventory dollars on hand, stock valuation, available inventory value. "
    "Bad example: Total On Hand Value, total_on_hand_value, On Hand Value, TotalOnHandValue. "
    "Return only a comma-separated list. No numbering, quotes, or extra text. "
    "Measure name, do not reuse this wording: {Measure Name}. "
    "Business description: {Desc}. "
    "DAX expression: {Measure Expression}."
)

MEASURE_SYNONYM_RETRY_PROMPT = (
    "Previous synonyms were just restating the measure name. That is not acceptable. "
    "Read the business description again and invent 8 plain-English phrases for this KPI. "
    "Do not use any wording from the forbidden list. "
    "Do not use the measure name, abbreviations of the measure name, or underscored versions of it. "
    "Return only a comma-separated list. "
    "Forbidden wording: {Forbidden}. "
    "Measure name: {Measure Name}. "
    "Business description: {Desc}. "
    "DAX expression: {Measure Expression}."
)

TABLE_SYNONYM_PROMPT = (
    "You write Power BI Q&A and Copilot synonyms for a table. "
    "Return 3 to 5 unique everyday names a report user would type to find this table. "
    "Each synonym must be 2 to 6 ordinary business words. "
    "Do not repeat or lightly rephrase the table name. "
    "Do not use technical IDs, camel case, snake_case, or warehouse prefixes. "
    "Return only a comma-separated list. No numbering, quotes, or extra text. "
    "Table name, do not reuse this wording: {Table}. "
    "Table description: {Desc}."
)

TABLE_SYNONYM_RETRY_PROMPT = (
    "Previous table synonyms were too close to the table name or already used. Try again. "
    "Invent 4 everyday business phrases based only on the description. "
    "Do not use any wording from the forbidden list. "
    "Return only a comma-separated list. "
    "Forbidden wording: {Forbidden}. "
    "Table name: {Table}. "
    "Table description: {Desc}."
)


def _parse_synonyms(value, limit: int = MAX_SYNONYMS) -> list:
    """Parse AI output or stored synonyms into a clean list of phrases.

    Pass limit=None to keep every phrase, which is what manual overrides need.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []

    items = []
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = value.get("synonyms") or value.get("Synonyms") or []
    else:
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return _parse_synonyms(parsed, limit=limit)
        except (json.JSONDecodeError, TypeError):
            text = re.sub(r"^\s*[\-\*\d]+[\.\)]\s*", "", text, flags=re.M)
            text = text.replace("\n", ",")
            items = [p.strip(" .;\"'`") for p in text.split(",")]

    cleaned = []
    seen = set()
    for item in items:
        term = str(item).strip(" .;\"'`")
        term = re.sub(r"\s+", " ", term)
        if not term:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(term)
    return cleaned if limit is None else cleaned[:limit]


def _name_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _name_tokens(text: str) -> set:
    stop = {"the", "a", "an", "of", "for", "and", "to", "in", "on", "by", "per"}
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if t not in stop}


def _is_too_similar_to_name(synonym: str, *object_names: str) -> bool:
    syn_key = _name_key(synonym)
    syn_tokens = _name_tokens(synonym)
    if not syn_key:
        return True

    for name in object_names:
        if not name or not str(name).strip():
            continue
        name_key = _name_key(name)
        name_tokens = _name_tokens(name)
        if not name_key:
            continue
        if syn_key == name_key:
            return True
        if syn_key in name_key or name_key in syn_key:
            if abs(len(syn_key) - len(name_key)) <= 4:
                return True
        if syn_tokens and syn_tokens == name_tokens:
            return True
        if syn_tokens and name_tokens and syn_tokens.issubset(name_tokens):
            if len(syn_tokens) >= max(1, len(name_tokens) - 1):
                return True
    return False


def _drop_self_name_synonyms(synonyms: list, *object_names: str, limit: int = MAX_SYNONYMS) -> list:
    cleaned = []
    seen = set()
    for term in _parse_synonyms(synonyms, limit=None):
        if _is_too_similar_to_name(term, *object_names):
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(term)
    return cleaned if limit is None else cleaned[:limit]


def _blank_synonym_column(df: pd.DataFrame) -> pd.Series:
    return pd.Series([[] for _ in range(len(df))], index=df.index, dtype="object")


def _set_synonym_lists(df: pd.DataFrame, mask: pd.Series, values) -> None:
    """Assign variable-length synonym lists without a NumPy shape error."""
    if "Synonyms" not in df.columns or str(df["Synonyms"].dtype) != "object":
        df["Synonyms"] = _blank_synonym_column(df)

    target_index = df.index[mask.fillna(False).astype(bool)]
    for idx, value in zip(target_index, values):
        df.at[idx, "Synonyms"] = list(value or [])


def _generate_synonyms_with_ai(
    df: pd.DataFrame, prompt: str, *, progress_label: str = ""
) -> list:
    if df is None or df.empty:
        return []
    return [
        _parse_synonyms(x)
        for x in _ai_generate_response(df, prompt, progress_label=progress_label)
    ]


def _unique_keep_order(items: list) -> list:
    seen = set()
    out = []
    for item in items:
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


class SynonymRegistry:
    """
    Keeps one synonym phrase to one object across the whole run.

    Two fields answering to the same phrase makes Q&A ambiguous, so a phrase is
    owned by the first object to claim it. Everything generated afterwards has to
    find different wording, and rows left short are re-prompted with the lost
    phrases marked forbidden.

    Seed it with the synonyms already in the model so new text cannot collide with
    what is there. Hand-written rows claim with priority=True and take a phrase off
    a generated row, because a developer's wording should win.
    """

    def __init__(self, enabled="yes"):
        self.enabled = _yes_no(enabled, "unique_synonyms")
        self._owner = {}
        self.conflicts = []

    @staticmethod
    def _term_key(term) -> str:
        return re.sub(r"\s+", " ", str(term or "").strip().lower())

    @staticmethod
    def _owner_key(kind, table, name) -> tuple:
        return (_key(kind), _key(table), _key(name))

    @staticmethod
    def _label(owner) -> str:
        kind, table, name = owner
        return f"{table}[{name}]" if name else str(table)

    def seed_from_model(self, existing_synonyms: dict) -> None:
        """Reserve every synonym already authored in the model."""
        for (table, name, kind), terms in (existing_synonyms or {}).items():
            owner = self._owner_key(kind, table, name)
            for term in terms or []:
                self._owner.setdefault(self._term_key(term), owner)

    def claim(self, terms, kind, table, name, priority: bool = False) -> list:
        """Return the phrases this object may keep, recording what it lost."""
        if not self.enabled:
            return list(terms or [])

        me = self._owner_key(kind, table, name)
        kept = []
        for term in terms or []:
            key = self._term_key(term)
            if not key:
                continue

            holder = self._owner.get(key)
            if holder is None or holder == me:
                self._owner[key] = me
                kept.append(term)
                continue

            if priority:
                self.conflicts.append(
                    {
                        "Synonym": term,
                        "Kept By": self._label(me),
                        "Dropped From": self._label(holder),
                        "Action": "reassigned to manual row",
                    }
                )
                self._owner[key] = me
                kept.append(term)
            else:
                self.conflicts.append(
                    {
                        "Synonym": term,
                        "Kept By": self._label(holder),
                        "Dropped From": self._label(me),
                        "Action": "dropped as duplicate",
                    }
                )
        return kept

    @property
    def dropped_count(self) -> int:
        return sum(1 for c in self.conflicts if c["Action"] == "dropped as duplicate")

    def conflicts_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.conflicts)


class DescriptionRegistry:
    """
    Keep every generated description unique across columns and measures.

    If the model repeats wording, the second object gets a short disambiguator
    so Copilot / Q&A never see two identical descriptions.
    """

    def __init__(self):
        self._owner: dict = {}
        self.conflicts: list = []

    @staticmethod
    def _desc_key(text) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower())

    def claim(self, description: str, kind: str, table: str, name: str) -> str:
        text = str(description or "").strip()
        if not text:
            return text
        key = self._desc_key(text)
        me = (_key(kind), _key(table), _key(name))
        holder = self._owner.get(key)
        if holder is None or holder == me:
            self._owner[key] = me
            return text

        disambiguated = f"{text.rstrip('.')} ({table} {name})."
        unique_key = self._desc_key(disambiguated)
        suffix = 2
        while unique_key in self._owner and self._owner[unique_key] != me:
            disambiguated = f"{text.rstrip('.')} ({table} {name} {suffix})."
            unique_key = self._desc_key(disambiguated)
            suffix += 1
        self._owner[unique_key] = me
        self.conflicts.append(
            {
                "Original": text,
                "Unique": disambiguated,
                "Kept By": f"{table}[{name}]",
                "Collided With": f"{holder[1]}[{holder[2]}]",
            }
        )
        return disambiguated

    def seed(self, description: str, kind: str, table: str, name: str) -> None:
        key = self._desc_key(description)
        if key:
            self._owner.setdefault(key, (_key(kind), _key(table), _key(name)))


def _enforce_unique_descriptions(
    records: list,
    *,
    kind: str,
    table_key: str,
    name_key: str,
    desc_key: str = "Desc",
    registry: DescriptionRegistry = None,
) -> DescriptionRegistry:
    """Mutate records in place so every description is model-unique."""
    registry = registry or DescriptionRegistry()
    for rec in records or []:
        rec[desc_key] = registry.claim(
            rec.get(desc_key) or "",
            kind,
            rec.get(table_key) or "",
            rec.get(name_key) or rec.get(table_key) or "",
        )
    return registry


def _generate_synonyms_with_quality_gate(
    df: pd.DataFrame,
    prompt: str,
    retry_prompt: str,
    name_cols: list,
    registry: SynonymRegistry = None,
    owner_kind: str = None,
    owner_table_col: str = None,
    owner_name_col: str = None,
    min_count: int = MIN_SYNONYMS,
    max_count: int = MAX_SYNONYMS,
    progress_label: str = "",
    retry_label: str = "",
) -> list:
    """Generate synonyms, drop name clones and duplicates, and retry weak rows.

    progress_label / retry_label are notebook banners. retry_label may include
    ``{n}`` for the number of rows that failed the first pass.
    """
    if df is None or df.empty:
        return []

    _announce_step3_synonyms()

    def claim(row, terms):
        if registry is None or not owner_kind:
            return list(terms), []
        kept = registry.claim(
            terms,
            owner_kind,
            row.get(owner_table_col) if owner_table_col else "",
            row.get(owner_name_col) if owner_name_col else "",
        )
        lost = [t for t in terms if t not in kept]
        return kept, lost

    first_pass = _generate_synonyms_with_ai(df, prompt, progress_label=progress_label)
    finalized = []
    retry_records = []
    retry_positions = []

    for i, (_, row) in enumerate(df.iterrows()):
        names = [row.get(c) for c in name_cols]
        cleaned = _drop_self_name_synonyms(
            first_pass[i] if i < len(first_pass) else [], *names, limit=max_count
        )
        cleaned, lost = claim(row, cleaned)
        finalized.append(cleaned)

        if len(cleaned) < min_count:
            rec = row.to_dict()
            rec["Forbidden"] = ", ".join(
                [str(n) for n in names if n and str(n).strip()] + cleaned + lost
            )
            retry_records.append(rec)
            retry_positions.append(i)

    if retry_records:
        n_retry = len(retry_records)
        retry_kind = {
            "table": "tables",
            "column": "columns",
            "measure": "measures",
        }.get(owner_kind or "", "objects")
        print(f"Step 3 — Synonyms: retry: {n_retry} {retry_kind}.")
        retry_progress = (
            retry_label.format(n=n_retry)
            if retry_label
            else f"retry pass for unique synonyms ({n_retry})"
        )
        retry_df = pd.DataFrame(retry_records)
        second_pass = _generate_synonyms_with_ai(
            retry_df, retry_prompt, progress_label=retry_progress
        )
        for pos, syns, rec in zip(retry_positions, second_pass, retry_records):
            names = [rec.get(c) for c in name_cols]
            extra = _drop_self_name_synonyms(
                syns, *names, rec.get("Forbidden"), limit=max_count
            )
            extra, _ = claim(rec, extra)
            finalized[pos] = _unique_keep_order(finalized[pos] + extra)[:max_count]

    return finalized


# =========================
# Manual overrides for descriptions and synonyms
# =========================

MODE_OVERWRITE = "overwrite"
MODE_APPEND = "append"
MODE_FILL = "fill"
MODE_KEEP = "keep"

# Kept for older cells that referenced these names.
SYNONYM_MODE_OVERWRITE = MODE_OVERWRITE
SYNONYM_MODE_APPEND = MODE_APPEND

_SYNONYM_MODE_ALIASES = {
    "overwrite": MODE_OVERWRITE,
    "replace": MODE_OVERWRITE,
    "force": MODE_OVERWRITE,
    "append": MODE_APPEND,
    "add": MODE_APPEND,
    "merge": MODE_APPEND,
    "fill": MODE_FILL,
    "if blank": MODE_FILL,
    "if empty": MODE_FILL,
    "only if empty": MODE_FILL,
    "missing": MODE_FILL,
    "keep": MODE_KEEP,
    "skip": MODE_KEEP,
    "ignore": MODE_KEEP,
    "leave": MODE_KEEP,
    "none": MODE_KEEP,
    "no": MODE_KEEP,
}

_DESCRIPTION_MODE_ALIASES = {
    key: value for key, value in _SYNONYM_MODE_ALIASES.items() if value != MODE_APPEND
}


def _key(value) -> str:
    return str(value or "").strip().lower()


def _synonym_list_filled(value) -> bool:
    return bool(_parse_synonyms(value, limit=None))


def _lookup_mapped_column_synonyms(mapped_syn, pbi_table, pbi_col) -> list:
    """Read mapped-column synonyms with stripped/lowercase keys (generation and preview)."""
    if not mapped_syn:
        return []
    key = (_key(pbi_table), _key(pbi_col))
    if key in mapped_syn:
        return list(mapped_syn.get(key) or [])
    for stored_key, syns in mapped_syn.items():
        if not (isinstance(stored_key, (tuple, list)) and len(stored_key) >= 2):
            continue
        if _key(stored_key[0]) == key[0] and _key(stored_key[1]) == key[1]:
            return list(syns or [])
    return []


def _count_filled_generated_synonyms(frame) -> int:
    """Count rows marked generated this run that actually have Proposed-ready lists."""
    if frame is None or getattr(frame, "empty", True):
        return 0
    if "Synonym Source" not in getattr(frame, "columns", []):
        return 0
    generated = frame["Synonym Source"].isin(["Generated now", "Regenerated"])
    if "Synonyms" not in frame.columns:
        return int(generated.sum())
    filled = frame["Synonyms"].map(_synonym_list_filled)
    return int((generated & filled).sum())


def _resolve_mode(value, aliases: dict, default: str, label: str) -> str:
    """
    Read a per-row mode, accepting a few everyday spellings.

    Unknown words raise rather than falling back to a default, so a typo can
    never quietly change more or less of the model than intended.
    """
    text = _key(value)
    if not text:
        return default
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"{label} must be one of {sorted(set(aliases.values()))}, got {value!r}"
    )


def normalize_manual_rows(rows, object_key: str = "Column") -> list:
    """
    Normalize a hand-written override list into one predictable shape.

    Supported keys per row:
      Table             required
      Column            required (also accepts Measure or Name)
      Desc              optional description text
      Description Mode  optional; "overwrite" (default) writes Desc over whatever
                        exists, "fill" writes it only when the object has none,
                        "keep" leaves the description completely alone
      Synonyms          optional; list or comma-separated string
      Synonym Mode      optional; "overwrite" (default) replaces existing synonyms,
                        "append" adds to them, "fill" writes only when the object
                        has none, "keep" leaves synonyms completely alone

    The two modes are independent, which is the point: set Description Mode to
    "keep" to edit synonyms without touching the description, or Synonym Mode to
    "keep" to edit a description without touching synonyms.
    """
    normalized = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue

        table = str(raw.get("Table") or "").strip()
        name = str(
            raw.get(object_key)
            or raw.get("Column")
            or raw.get("Measure")
            or raw.get("Measure Name")
            or raw.get("Name")
            or ""
        ).strip()
        if not table or not name:
            continue

        label = f"{table}[{name}]"
        synonym_mode = _resolve_mode(
            raw.get("Synonym Mode") or raw.get("Mode"),
            _SYNONYM_MODE_ALIASES,
            MODE_OVERWRITE,
            f'Synonym Mode for {label}',
        )
        description_mode = _resolve_mode(
            raw.get("Description Mode") or raw.get("Desc Mode"),
            _DESCRIPTION_MODE_ALIASES,
            MODE_OVERWRITE,
            f'Description Mode for {label}',
        )

        raw_synonyms = raw.get("Synonyms")
        replace_synonyms = bool(
            raw.get("Replace Synonyms") or raw.get("Synonym Override")
        )
        # Empty [] still counts when Replace Synonyms is set, so apply can wipe.
        has_synonyms = (
            ("Synonyms" in raw and raw_synonyms not in (None, "", []))
            or replace_synonyms
        )
        desc = str(raw.get("Desc") or "").strip()

        normalized.append(
            {
                "Table": table,
                "Column": name,
                "Desc": desc,
                "Has Desc": bool(desc),
                "Description Mode": description_mode,
                "Synonyms": _parse_synonyms(raw_synonyms, limit=None)
                if "Synonyms" in raw
                else [],
                "Has Synonyms": has_synonyms,
                "Synonym Mode": synonym_mode,
                "Replace Synonyms": replace_synonyms,
            }
        )
    return normalized


def merge_manual_rows(generated_rows, manual_rows, object_key: str = "Column") -> list:
    """
    Overlay manual rows on generated rows.

    Description Mode and Synonym Mode are applied independently, so a row can
    change one half and leave the other exactly as it is:

      Description Mode  overwrite  write Desc over whatever exists, no
                                   OVERWRITE_COLUMNS / OVERWRITE_MEASURES needed
                        fill       write Desc only where the object has none
                        keep       do not touch the description at all
      Synonym Mode      overwrite  replace the existing synonyms
                        append     add to the existing synonyms
                        fill       write only where the object has none
                        keep       do not touch the synonyms at all

    Manual rows for objects that were never generated (for example a Databricks
    mapped column) are appended so they still get applied.
    """
    manual = normalize_manual_rows(manual_rows, object_key=object_key)
    manual_by_key = {(_key(m["Table"]), _key(m["Column"])): m for m in manual}

    def overlay(out: dict, override: dict) -> dict:
        desc_mode = override["Description Mode"]
        if desc_mode == MODE_KEEP:
            out["Description Mode"] = MODE_KEEP
            out["Skip Description"] = True
            out.pop("Force", None)
        elif override["Has Desc"]:
            out["Desc"] = override["Desc"]
            out["Description Mode"] = desc_mode
            out.pop("Skip Description", None)
            if desc_mode == MODE_OVERWRITE:
                out["Force"] = True
            else:
                out.pop("Force", None)

        syn_mode = override["Synonym Mode"]
        if syn_mode == MODE_KEEP:
            out["Synonym Mode"] = MODE_KEEP
            out["Skip Synonyms"] = True
            out.pop("Synonym Override", None)
            out.pop("Replace Synonyms", None)
        elif override["Has Synonyms"]:
            out["Synonyms"] = list(override["Synonyms"])
            out["Synonym Mode"] = syn_mode
            out["Synonym Override"] = True
            out.pop("Skip Synonyms", None)
            if override.get("Replace Synonyms") or syn_mode == MODE_OVERWRITE:
                out["Replace Synonyms"] = True
        return out

    merged = []
    matched = set()
    for row in generated_rows or []:
        out = dict(row)
        row_key = (_key(out.get("Table")), _key(out.get("Column")))
        override = manual_by_key.get(row_key)
        if override:
            matched.add(row_key)
            overlay(out, override)
        merged.append(out)

    for override in manual:
        row_key = (_key(override["Table"]), _key(override["Column"]))
        if row_key in matched:
            continue

        merged.append(
            overlay(
                {
                    "Table": override["Table"],
                    "Column": override["Column"],
                    "Desc": override["Desc"],
                    "Synonyms": list(override["Synonyms"]),
                },
                override,
            )
        )

    return merged


def row_description_mode(row) -> str:
    """
    What will happen to this row's description, as one word.

    Rows carry flags rather than a mode, so this reads them back: a forced row
    overwrites, a skipped row keeps, and anything else only fills a blank.
    """
    if (row or {}).get("Skip Description"):
        return MODE_KEEP
    stored = _key((row or {}).get("Description Mode"))
    if stored in _DESCRIPTION_MODE_ALIASES:
        return _DESCRIPTION_MODE_ALIASES[stored]
    return MODE_OVERWRITE if (row or {}).get("Force") else MODE_FILL


def row_synonym_mode(row) -> str:
    """What will happen to this row's synonyms, as one word."""
    if (row or {}).get("Skip Synonyms"):
        return MODE_KEEP
    stored = _key((row or {}).get("Synonym Mode"))
    if stored in _SYNONYM_MODE_ALIASES:
        return _SYNONYM_MODE_ALIASES[stored]
    if (row or {}).get("Synonym Override") or (row or {}).get("Replace Synonyms"):
        return MODE_OVERWRITE
    return MODE_FILL


def summarize_manual_overrides(merged_rows, label: str = "rows") -> None:
    """Print what the manual block actually changed (counts only)."""
    rows = merged_rows or []
    desc_written = [r for r in rows if r.get("Force")]
    desc_kept = [r for r in rows if r.get("Skip Description")]
    syn_written = [r for r in rows if r.get("Synonym Override")]
    syn_kept = [r for r in rows if r.get("Skip Synonyms")]

    print(f"{label}: {len(rows)} total")
    print(f"  descriptions to overwrite: {len(desc_written)}")
    print(f"  descriptions left alone (keep): {len(desc_kept)}")
    print(f"  synonyms from the manual block: {len(syn_written)}")
    print(f"  synonyms left alone (keep): {len(syn_kept)}")


def _regenerated_flags(description_source, synonym_source) -> dict:
    """
    Turn a rebuild of existing metadata into apply permission.

    When a developer asks to regenerate something that already had a value, the
    intent is to replace it, so the row carries the same flags a manual override
    uses. Freshly filled blanks need no flag; they apply on their own.
    """
    flags = {}
    if str(description_source or "") == "Regenerated":
        flags["Force"] = True
    if str(synonym_source or "") == "Regenerated":
        flags["Replace Synonyms"] = True
    return flags


def measure_rows_from_catalog(catalog_df: pd.DataFrame) -> list:
    """Turn the measure catalog DataFrame into MEASURE_ROWS shape."""
    if catalog_df is None or catalog_df.empty:
        return []
    return [
        {
            "Table": str(r.get("Table") or "").strip(),
            "Column": str(r.get("Measure Name") or "").strip(),
            "Desc": str(r.get("Desc") or "").strip(),
            "Synonyms": _parse_synonyms(r.get("Synonyms"), limit=None),
            **_regenerated_flags(r.get("Description Source"), r.get("Synonym Source")),
        }
        for r in catalog_df.to_dict("records")
    ]


# =========================
# Copy/paste output blocks
# =========================


def _filter_rows(rows, tables=None, names=None, contains=None) -> list:
    table_filter = {_key(t) for t in (tables or []) if str(t).strip()}
    name_filter = {_key(n) for n in (names or []) if str(n).strip()}
    needle = _key(contains)

    selected = []
    for row in rows or []:
        table_key = _key(row.get("Table"))
        name_key = _key(row.get("Column"))
        if table_filter and table_key not in table_filter:
            continue
        if name_filter and name_key not in name_filter:
            continue
        if needle and needle not in name_key and needle not in table_key:
            continue
        selected.append(row)
    return selected


MANUAL_ROW_FIELDS = (
    "Table",
    "Column",
    "Desc",
    "Description Mode",
    "Synonyms",
    "Synonym Mode",
)
DESCRIPTION_ROW_FIELDS = ("Table", "Column", "Desc", "Description Mode")
SYNONYM_ROW_FIELDS = ("Table", "Column", "Synonyms", "Synonym Mode")


def format_manual_block(
    rows,
    var_name: str,
    fields=MANUAL_ROW_FIELDS,
    tables=None,
    names=None,
    contains=None,
    limit=None,
    comment_out: bool = False,
    sort_rows: bool = True,
) -> str:
    """
    Render rows as a Python literal you can paste into the manual override cell.

    fields controls the shape. MANUAL_ROW_FIELDS is the full row with both modes,
    DESCRIPTION_ROW_FIELDS and SYNONYM_ROW_FIELDS render one half only.
    """
    selected = _filter_rows(rows, tables=tables, names=names, contains=contains)
    if sort_rows:
        selected = sorted(selected, key=lambda r: (_key(r.get("Table")), _key(r.get("Column"))))
    if limit:
        selected = selected[:limit]

    prefix = "# " if comment_out else ""
    lines = [f"{prefix}{var_name} = ["]
    for row in selected:
        lines.append(f"{prefix}    {{")
        for field in fields:
            if field == "Synonyms":
                value = _parse_synonyms(row.get("Synonyms"), limit=None)
            elif field == "Synonym Mode":
                value = row_synonym_mode(row)
            elif field == "Description Mode":
                value = row_description_mode(row)
            else:
                value = str(row.get(field) or "").strip()
            lines.append(f'{prefix}        "{field}": {json.dumps(value, ensure_ascii=False)},')
        lines.append(f"{prefix}    }},")
    lines.append(f"{prefix}]")

    if not selected:
        lines.insert(1, f"{prefix}    # no rows matched the filters")
    return "\n".join(lines)


def print_manual_row_block(rows, var_name: str = "MANUAL_CAL_COLUMN_ROWS", **filters) -> str:
    """Print the full row shape: description, synonyms, and both modes."""
    block = format_manual_block(rows, var_name, fields=MANUAL_ROW_FIELDS, **filters)
    print(block)
    return block


def print_description_block(rows, var_name: str = "MANUAL_CAL_COLUMN_ROWS", **filters) -> str:
    block = format_manual_block(rows, var_name, fields=DESCRIPTION_ROW_FIELDS, **filters)
    print(block)
    return block


def print_synonym_block(rows, var_name: str = "MANUAL_CAL_COLUMN_ROWS", **filters) -> str:
    block = format_manual_block(rows, var_name, fields=SYNONYM_ROW_FIELDS, **filters)
    print(block)
    return block


def print_manual_blocks(
    calculated_column_rows=None,
    measure_rows=None,
    column_var: str = "MANUAL_CAL_COLUMN_ROWS",
    measure_var: str = "MANUAL_MEASURE_ROWS",
    shape: str = "full",
    **filters,
) -> dict:
    """
    Print paste-ready blocks for calculated columns and measures.

    shape="full" (default) prints one block per object type holding the
    description, the synonyms, and both modes. Use "descriptions" or "synonyms"
    to print just that half.
    """
    shapes = {
        "full": (MANUAL_ROW_FIELDS, "description + synonyms"),
        "descriptions": (DESCRIPTION_ROW_FIELDS, "descriptions"),
        "synonyms": (SYNONYM_ROW_FIELDS, "synonyms"),
    }
    if _key(shape) not in shapes:
        raise ValueError(f"shape must be one of {sorted(shapes)}, got {shape!r}")
    fields, shape_label = shapes[_key(shape)]

    blocks = {}
    sections = [
        ("calculated columns", calculated_column_rows, column_var),
        ("measures", measure_rows, measure_var),
    ]

    for label, rows, var_name in sections:
        if rows is None:
            continue
        print(f"\n# ---------- {label}: {shape_label} ----------")
        print("# Copy into Cell 4.3 and edit. Set a mode to 'keep' to leave that half untouched.")
        block = format_manual_block(rows, var_name, fields=fields, **filters)
        print(block)
        blocks[label] = block
    return blocks


def build_synonym_preview(rows, object_label: str = "Column") -> pd.DataFrame:
    """Flat table of what each row will write, easier to scan than nested lists."""
    records = []
    for row in rows or []:
        synonyms = _parse_synonyms(row.get("Synonyms"), limit=None)
        records.append(
            {
                "Table": row.get("Table"),
                object_label: row.get("Column"),
                "Desc": row.get("Desc"),
                "Description Mode": row_description_mode(row),
                "Synonym Count": len(synonyms),
                "Synonyms": ", ".join(synonyms),
                "Synonym Mode": row_synonym_mode(row),
                "From Manual Block": bool(
                    row.get("Synonym Override")
                    or row.get("Skip Synonyms")
                    or row.get("Skip Description")
                ),
            }
        )
    return pd.DataFrame(records)


def load_existing_synonyms_map(
    dataset_name: str,
    workspace_name: str,
    culture: str = "en-US",
) -> dict:
    """
    Return {(table_lower, object_lower, kind): [synonym, ...]}
    kind is 'column' or 'measure'.
    """
    try:
        syn_df = labs.list_synonyms(dataset=dataset_name, workspace=workspace_name)
    except Exception as ex:
        print("Could not list existing synonyms. Treating all as missing.")
        logger.warning("Could not list existing synonyms (%s).", ex)
        return {}

    if syn_df is None or syn_df.empty:
        return {}

    culture_col = _first_col(syn_df, "Culture Name", "Culture")
    table_col = _first_col(syn_df, "Table Name", "Table")
    object_col = _first_col(syn_df, "Object Name", "Name")
    type_col = _first_col(syn_df, "Object Type", "Type")
    synonym_col = _first_col(syn_df, "Synonym")
    state_col = _first_col(syn_df, "State")

    if not all([table_col, object_col, type_col, synonym_col]):
        return {}

    work = syn_df.copy()
    if culture_col:
        work = work[work[culture_col].astype(str).str.lower() == culture.lower()]
    if state_col:
        work = work[~work[state_col].astype(str).str.lower().isin(["deleted", "suggested"])]

    out = {}
    for _, row in work.iterrows():
        obj_type = str(row[type_col]).strip().lower()
        if "measure" in obj_type:
            kind = "measure"
        elif "column" in obj_type:
            kind = "column"
        elif "table" in obj_type:
            kind = "table"
        else:
            continue

        key = (
            str(row[table_col]).strip().lower(),
            str(row[object_col]).strip().lower(),
            kind,
        )
        term = str(row[synonym_col]).strip()
        if not term:
            continue
        out.setdefault(key, [])
        if term.lower() not in {x.lower() for x in out[key]}:
            out[key].append(term)
    return out


CALCULATED_COLUMN_DESCRIPTION_PROMPT = (
    "Write a concise business description of this Power BI calculated column "
    "for report authors. Align the wording with the table's purpose. "
    "1-2 sentences. Do not mention DAX function names or syntax. "
    "Do not repeat the column name as the first words. "
    "Table name: {Table Name}. "
    "Table description: {Table Description}. "
    "Column name: {Column Name}. "
    "DAX: {Column Expression}."
)

SOURCE_COLUMN_DESCRIPTION_PROMPT = (
    "Write a concise business description of this Power BI column for report authors. "
    "The column is loaded from a source table, so describe what the value means to the "
    "business, not how it is stored. Align the wording with the table's purpose. "
    "1-2 sentences. Do not mention Power BI, DAX, or data types. "
    "Do not repeat the column name as the first words. "
    "If the name is an abbreviation or ends in ID, CD, AMT, QTY or similar, expand it. "
    "Table name: {Table Name}. "
    "Table description: {Table Description}. "
    "Column name: {Column Name}. "
    "Data type: {Data Type}."
)


def build_column_description_rows(
    dataset_name: str,
    workspace_name: str,
    include_hidden: bool = False,
    column_scope: str = "calculated",
    skip_columns=None,
    generate_descriptions="yes",
    force_regenerate_descriptions="no",
    generate_synonyms="yes",
    force_regenerate_synonyms="no",
    synonym_culture: str = "en-US",
    synonym_registry: SynonymRegistry = None,
    unique_synonyms="yes",
    existing_descriptions: Optional[dict] = None,
    pending_step2_measure_skip: bool = False,
):
    """
    Build CAL_COLUMN_ROWS for the columns Databricks does not already describe.

    column_scope   "calculated" only DAX calculated columns
                   "all"        every visible column, which is how a plain source
                                column with no Unity Catalog comment gets described
    skip_columns   (table, column) pairs already covered by a Databricks comment, so
                   the warehouse stays the source of truth and no AI call is wasted

    Each switch takes "yes"/"no" (or True/False):
      generate_descriptions        write AI descriptions where the column has none
      force_regenerate_descriptions  rewrite descriptions that already exist, and
                                     flag those rows so the apply step applies them
      generate_synonyms            build synonyms where the column has none
      force_regenerate_synonyms    rebuild synonyms that already exist, and flag
                                   those rows so the apply step replaces them

    A force switch implies its generate switch.
    """
    scope = _key(column_scope) or "calculated"
    if scope not in {"calculated", "all"}:
        raise ValueError(f"column_scope must be 'calculated' or 'all', got {column_scope!r}")
    generate_descriptions = _yes_no(generate_descriptions, "generate_descriptions")
    force_regenerate_descriptions = _yes_no(
        force_regenerate_descriptions, "force_regenerate_descriptions"
    )
    generate_synonyms = _yes_no(generate_synonyms, "generate_synonyms")
    force_regenerate_synonyms = _yes_no(force_regenerate_synonyms, "force_regenerate_synonyms")
    generate_descriptions = generate_descriptions or force_regenerate_descriptions
    generate_synonyms = generate_synonyms or force_regenerate_synonyms
    columns_df = fabric.list_columns(
        dataset=dataset_name,
        workspace=workspace_name,
        additional_xmla_properties=["Expression"],
    )
    tables_df = fabric.list_tables(dataset=dataset_name, workspace=workspace_name)

    table_name_col = _first_col(tables_df, "Name", "Table Name")
    table_desc_col = _first_col(tables_df, "Description", "Table Description")

    tables_lookup = tables_df[[table_name_col]].copy()
    tables_lookup["Table Description"] = (
        _clean_text(tables_df[table_desc_col]) if table_desc_col else ""
    )
    tables_lookup = tables_lookup.rename(columns={table_name_col: "Table Name"})

    col_hidden_col = _first_col(columns_df, "Hidden", "Is Hidden", "IsHidden")
    col_desc_col = _first_col(columns_df, "Description", "Column Description")
    expr_col = _first_col(columns_df, "Expression", "Source", "Source Column")
    data_type_col = _first_col(columns_df, "Data Type", "DataType", "Type Name")

    column_types = columns_df["Type"].astype(str)
    if scope == "all":
        # RowNumber is an engine-generated key, never something a report author reads.
        keep_mask = ~column_types.isin(["RowNumber"])
    else:
        keep_mask = column_types.isin(["Calculated", "CalculatedTableColumn"])
    calc_df = columns_df[keep_mask].copy()

    if not include_hidden and col_hidden_col:
        calc_df = calc_df[~_is_hidden(calc_df[col_hidden_col])].copy()

    covered = {
        (_key(t), _key(c))
        for t, c in (skip_columns or set())
        if _text(t) and _text(c)
    }
    if covered:
        before = len(calc_df)
        calc_df = calc_df[
            ~calc_df.apply(
                lambda r: (_key(r["Table Name"]), _key(r["Column Name"])) in covered,
                axis=1,
            )
        ].copy()
        print(
            f"Step 2 — Descriptions: {before - len(calc_df)} columns already have a "
            "Databricks comment (left as-is)."
        )

    result = calc_df[["Table Name", "Column Name"]].copy()
    result["Desc"] = _clean_text(calc_df[col_desc_col]) if col_desc_col else ""
    result["Column Expression"] = _clean_text(calc_df[expr_col]) if expr_col else ""
    result["Data Type"] = _clean_text(calc_df[data_type_col]) if data_type_col else ""
    result = result.merge(tables_lookup, on="Table Name", how="left")
    result["Table Description"] = _clean_text(result["Table Description"])
    _apply_snapshot_originals(
        result, existing_descriptions, "column", "Table Name", "Column Name"
    )

    blank_desc_mask = _blank_text_mask(result["Desc"])
    result["Description Source"] = "Missing, not generated"
    result.loc[~blank_desc_mask, "Description Source"] = "Already exists"

    if not generate_descriptions:
        _log_skip_ai_descriptions("column", "generate_missing_column_descriptions")
        missing_mask = pd.Series(False, index=result.index)
    elif force_regenerate_descriptions:
        missing_mask = pd.Series(True, index=result.index)
    else:
        missing_mask = blank_desc_mask

    if missing_mask.any():
        # A calculated column is best described from its DAX; a loaded column has none,
        # so it is described from the table it belongs to and its own name.
        has_expression = result["Column Expression"].ne("")
        batches = [
            (
                missing_mask & has_expression,
                ["Table Name", "Table Description", "Column Name", "Column Expression"],
                CALCULATED_COLUMN_DESCRIPTION_PROMPT,
                "column descriptions ({n} calculated columns)",
            ),
            (
                missing_mask & ~has_expression,
                ["Table Name", "Table Description", "Column Name", "Data Type"],
                SOURCE_COLUMN_DESCRIPTION_PROMPT,
                "column descriptions ({n} columns)",
            ),
        ]

        for batch_mask, fields, prompt, label in batches:
            if not batch_mask.any():
                continue
            n = int(batch_mask.sum())
            generated = _ai_generate_response(
                result.loc[batch_mask, fields].copy(),
                prompt,
                progress_label=label.format(n=n),
            )
            result.loc[batch_mask, "Desc"] = generated

        _mark_generated_description_source(result, missing_mask, blank_desc_mask)

    if generate_descriptions:
        n_generated = _count_generated_descriptions(result)
        _log_generated_ai_descriptions("column", n_generated)
        if not result.empty:
            n_still_blank = int(_blank_text_mask(result["Desc"]).sum())
            if n_still_blank and n_generated == 0:
                print(
                    f"Step 2 — Descriptions: {n_still_blank} uncovered columns still blank "
                    "(Fabric AI returned no text or was unavailable).",
                    flush=True,
                )

    # Finish Step 2 measure skip before column-synonym work starts Step 3.
    if pending_step2_measure_skip:
        _log_skip_ai_descriptions("measure", "generate_missing_measure_descriptions")

    result["Synonyms"] = _blank_synonym_column(result)
    result["Synonym Source"] = "Skipped"
    if not generate_synonyms:
        _log_skip_ai_synonyms("column", "generate_column_synonyms")
    elif not result.empty:
        _announce_step3_synonyms()
        existing_syn = load_existing_synonyms_map(
            dataset_name, workspace_name, culture=synonym_culture
        )
        registry = synonym_registry
        if registry is None:
            registry = SynonymRegistry(unique_synonyms)
            registry.seed_from_model(existing_syn)

        has_syn_mask = result.apply(
            lambda r: bool(
                existing_syn.get(
                    (
                        str(r["Table Name"]).strip().lower(),
                        str(r["Column Name"]).strip().lower(),
                        "column",
                    ),
                    [],
                )
            ),
            axis=1,
        )
        need_syn_mask = ~has_syn_mask
        if force_regenerate_synonyms:
            need_syn_mask = pd.Series(True, index=result.index)

        already_mask = ~need_syn_mask
        result.loc[already_mask, "Synonym Source"] = "Already exists"
        _set_synonym_lists(
            result,
            already_mask,
            [
                existing_syn.get(
                    (
                        str(r["Table Name"]).strip().lower(),
                        str(r["Column Name"]).strip().lower(),
                        "column",
                    ),
                    [],
                )
                for _, r in result.loc[already_mask].iterrows()
            ],
        )

        if need_syn_mask.any():
            to_syn = result.loc[
                need_syn_mask,
                ["Table Name", "Table Description", "Column Name", "Desc"],
            ].copy()
            syn_lists = _generate_synonyms_with_quality_gate(
                to_syn,
                prompt=COLUMN_SYNONYM_PROMPT,
                retry_prompt=COLUMN_SYNONYM_RETRY_PROMPT,
                name_cols=["Column Name", "Table Name"],
                registry=registry,
                owner_kind="column",
                owner_table_col="Table Name",
                owner_name_col="Column Name",
                min_count=MIN_COLUMN_SYNONYMS,
                max_count=MAX_COLUMN_SYNONYMS,
                progress_label=f"column synonyms ({len(to_syn)} columns)",
                retry_label="column synonyms, unique-wording retry ({n} columns)",
            )
            _set_synonym_lists(result, need_syn_mask, syn_lists)
            result.loc[need_syn_mask, "Synonym Source"] = "Generated now"
            result.loc[need_syn_mask & has_syn_mask, "Synonym Source"] = "Regenerated"

    cal_column_rows = [
        {
            "Table": r["Table Name"],
            "Column": r["Column Name"],
            "Desc": r["Desc"],
            "Synonyms": list(r.get("Synonyms") or []),
            **_regenerated_flags(r.get("Description Source"), r.get("Synonym Source")),
        }
        for r in result.to_dict("records")
    ]
    return cal_column_rows, result


def build_calculated_column_rows(dataset_name: str, workspace_name: str, **kwargs):
    """Calculated columns only. Kept for cells written against the older name."""
    kwargs.setdefault("column_scope", "calculated")
    return build_column_description_rows(dataset_name, workspace_name, **kwargs)


def build_measure_catalog(
    dataset_name: str,
    workspace_name: str,
    generate_descriptions="yes",
    force_regenerate_descriptions="no",
    generate_synonyms="yes",
    force_regenerate_synonyms="no",
    synonym_culture: str = "en-US",
    synonym_registry: SynonymRegistry = None,
    unique_synonyms="yes",
    existing_descriptions: Optional[dict] = None,
    announce_skip: bool = True,
) -> pd.DataFrame:
    """
    Build a measure catalog. Same switches as build_calculated_column_rows:
    generate only what is missing, or force a rebuild of what already exists.
    """
    generate_descriptions = _yes_no(generate_descriptions, "generate_descriptions")
    force_regenerate_descriptions = _yes_no(
        force_regenerate_descriptions, "force_regenerate_descriptions"
    )
    generate_synonyms = _yes_no(generate_synonyms, "generate_synonyms")
    force_regenerate_synonyms = _yes_no(force_regenerate_synonyms, "force_regenerate_synonyms")
    generate_descriptions = generate_descriptions or force_regenerate_descriptions
    generate_synonyms = generate_synonyms or force_regenerate_synonyms

    measures_df = fabric.list_measures(dataset=dataset_name, workspace=workspace_name)

    desc_col = (
        "Measure Description"
        if "Measure Description" in measures_df.columns
        else "Description"
    )
    out = measures_df[["Table Name", "Measure Name", "Measure Expression", desc_col]].copy()
    out.columns = ["Table", "Measure Name", "Measure Expression", "Desc"]
    out["Desc"] = _clean_text(out["Desc"])
    _apply_snapshot_originals(out, existing_descriptions, "measure", "Table", "Measure Name")

    blank_desc_mask = _blank_text_mask(out["Desc"])
    out["Description Source"] = "Missing, not generated"
    out.loc[~blank_desc_mask, "Description Source"] = "Already exists"

    if not generate_descriptions:
        if announce_skip:
            _log_skip_ai_descriptions("measure", "generate_missing_measure_descriptions")
        missing_mask = pd.Series(False, index=out.index)
    elif force_regenerate_descriptions:
        missing_mask = pd.Series(True, index=out.index)
    else:
        missing_mask = blank_desc_mask

    if missing_mask.any():
        to_generate = out.loc[missing_mask, ["Measure Name", "Measure Expression"]].copy()
        generated = _ai_generate_response(
            to_generate,
            (
                "Write a concise business description of this Power BI measure for report authors. "
                "Use the measure name and DAX only. "
                "1-2 sentences. Do not mention DAX function names, tables, or syntax. "
                "Do not repeat the measure name as the first words. "
                "Every description must be unique and executive-friendly. "
                "Measure name: {Measure Name}. DAX: {Measure Expression}."
            ),
            progress_label=f"measure descriptions ({len(to_generate)} measures)",
        )
        out.loc[missing_mask, "Desc"] = generated
        _mark_generated_description_source(out, missing_mask, blank_desc_mask)

    if generate_descriptions:
        _log_generated_ai_descriptions("measure", _count_generated_descriptions(out))

    out["Synonyms"] = _blank_synonym_column(out)
    out["Synonym Source"] = "Skipped"
    if not generate_synonyms:
        _log_skip_ai_synonyms("measure", "generate_measure_synonyms")
    else:
        _announce_step3_synonyms()
        if not out.empty:
            existing_syn = load_existing_synonyms_map(
                dataset_name, workspace_name, culture=synonym_culture
            )
            registry = synonym_registry
            if registry is None:
                registry = SynonymRegistry(unique_synonyms)
                registry.seed_from_model(existing_syn)

            has_syn_mask = out.apply(
                lambda r: bool(
                    existing_syn.get(
                        (
                            str(r["Table"]).strip().lower(),
                            str(r["Measure Name"]).strip().lower(),
                            "measure",
                        ),
                        [],
                    )
                ),
                axis=1,
            )
            need_syn_mask = ~has_syn_mask
            if force_regenerate_synonyms:
                need_syn_mask = pd.Series(True, index=out.index)

            already_mask = ~need_syn_mask
            out.loc[already_mask, "Synonym Source"] = "Already exists"
            _set_synonym_lists(
                out,
                already_mask,
                [
                    existing_syn.get(
                        (
                            str(r["Table"]).strip().lower(),
                            str(r["Measure Name"]).strip().lower(),
                            "measure",
                        ),
                        [],
                    )
                    for _, r in out.loc[already_mask].iterrows()
                ],
            )

            if need_syn_mask.any():
                # Table comes along only so the registry knows which object owns a phrase.
                to_syn = out.loc[
                    need_syn_mask,
                    ["Table", "Measure Name", "Desc", "Measure Expression"],
                ].copy()
                syn_lists = _generate_synonyms_with_quality_gate(
                    to_syn,
                    prompt=MEASURE_SYNONYM_PROMPT,
                    retry_prompt=MEASURE_SYNONYM_RETRY_PROMPT,
                    name_cols=["Measure Name"],
                    registry=registry,
                    owner_kind="measure",
                    owner_table_col="Table",
                    owner_name_col="Measure Name",
                    min_count=MIN_MEASURE_SYNONYMS,
                    max_count=MAX_MEASURE_SYNONYMS,
                    progress_label=f"measure synonyms ({len(to_syn)} measures)",
                    retry_label="measure synonyms, unique-wording retry ({n} measures)",
                )
                _set_synonym_lists(out, need_syn_mask, syn_lists)
                out.loc[need_syn_mask, "Synonym Source"] = "Generated now"
                out.loc[need_syn_mask & has_syn_mask, "Synonym Source"] = "Regenerated"

        n_meas_syn = 0
        if not out.empty and "Synonym Source" in out.columns:
            n_meas_syn = int(
                out["Synonym Source"].isin(["Generated now", "Regenerated"]).sum()
            )
        _log_generated_ai_synonyms("measure", n_meas_syn, "≥10 each")

    return out


# =========================
# Clear existing descriptions and synonyms
# =========================

_YES_VALUES = {"yes", "y", "true", "1", "on"}
_NO_VALUES = {"no", "n", "false", "0", "off", "", "none"}


def _yes_no(value, label: str = "value") -> bool:
    """Read a yes/no switch. Anything unrecognized raises, so typos never fall through as 'no'."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _YES_VALUES:
        return True
    if text in _NO_VALUES:
        return False
    raise ValueError(f"{label} must be 'yes' or 'no', got {value!r}")


def _coalesce_yes_no(preferred, fallback, default: bool, label: str) -> bool:
    """Prefer generate_missing_*; fall back to the older generate_* name; else default."""
    if preferred is not None:
        return _yes_no(preferred, label)
    if fallback is not None:
        return _yes_no(fallback, label)
    return bool(default)


def _log_skip_ai_descriptions(kind: str, flag_name: str) -> None:
    print(f"Step 2 — Descriptions: skipped {kind}s ({flag_name}=False).")


def _log_generated_ai_descriptions(kind: str, count: int) -> None:
    print(f"Step 2 — Descriptions: {kind}s — {count} generated.")


def _count_generated_descriptions(frame) -> int:
    if frame is None or getattr(frame, "empty", True):
        return 0
    if "Description Source" not in getattr(frame, "columns", []):
        return 0
    return int(frame["Description Source"].isin(["Generated now", "Regenerated"]).sum())


_STEP3_SYNONYM_INTRO_PRINTED = False


def _reset_step3_synonym_logs() -> None:
    global _STEP3_SYNONYM_INTRO_PRINTED
    _STEP3_SYNONYM_INTRO_PRINTED = False
    _reset_fabric_ai_skip_log()


def _announce_step3_synonyms() -> None:
    """Print the Step 3 intro once, before the first skip or generate line."""
    global _STEP3_SYNONYM_INTRO_PRINTED
    if _STEP3_SYNONYM_INTRO_PRINTED:
        return
    _STEP3_SYNONYM_INTRO_PRINTED = True
    print(
        "Step 3 — Synonyms: generating unique business synonyms "
        "(collision-free across the model)."
    )


def _log_skip_ai_synonyms(kind: str, flag_name: str) -> None:
    _announce_step3_synonyms()
    print(f"Step 3 — Synonyms: skipped {kind}s ({flag_name}=False).")


def _log_generated_ai_synonyms(kind: str, count: int, detail: str) -> None:
    _announce_step3_synonyms()
    print(f"Step 3 — Synonyms: {kind}s — {count} generated ({detail}).")


def _apply_table_synonyms(table_rows, registry, generate: bool) -> list:
    """Gate table synonym generation. Late-binds generate_table_synonyms (defined below)."""
    if not generate:
        _log_skip_ai_synonyms("table", "generate_table_synonyms")
        return list(table_rows or [])
    _announce_step3_synonyms()
    rows = globals()["generate_table_synonyms"](table_rows, registry=registry)
    n_table_syn = sum(1 for r in rows if r.get("Synonyms"))
    _log_generated_ai_synonyms("table", n_table_syn, "3–5 each")
    return rows


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _read_linguistic_json(tom, culture: str = "en-US"):
    """Return the linguistic schema dict, or None when the culture has no schema."""
    culture_obj = next((c for c in tom.model.Cultures if c.Name == culture), None)
    if culture_obj is None:
        return None
    metadata = getattr(culture_obj, "LinguisticMetadata", None)
    content = getattr(metadata, "Content", None) if metadata is not None else None
    if not content:
        return None

    lm = json.loads(content)
    lm.setdefault("Entities", {})
    return lm


def _save_linguistic_json(tom, culture: str, lm: dict) -> None:
    tom.model.Cultures[culture].LinguisticMetadata.Content = json.dumps(lm, indent=4)


def _ensure_linguistic_schema(tom, culture: str = "en-US") -> None:
    if hasattr(tom, "_add_linguistic_schema"):
        tom._add_linguistic_schema(culture=culture)
        return

    if not any(c.Name == culture for c in tom.model.Cultures):
        raise ValueError(
            f"Culture '{culture}' does not exist in the model. "
            "Add an en-US linguistic schema in Power BI / Tabular Editor first."
        )


def _load_linguistic_json(tom, culture: str = "en-US") -> dict:
    _ensure_linguistic_schema(tom, culture)
    lm = json.loads(tom.model.Cultures[culture].LinguisticMetadata.Content)
    lm.setdefault("Entities", {})
    return lm


def _authored_terms(entity: dict) -> list:
    terms = []
    for term_obj in (entity or {}).get("Terms") or []:
        if not isinstance(term_obj, dict):
            continue
        for name, props in term_obj.items():
            state = str((props or {}).get("State") or "").lower()
            if state in {"deleted", "suggested"}:
                continue
            terms.append(name)
    return terms


def _strip_entity_terms(entity: dict, keep_auto_generated: bool = False) -> int:
    """
    Drop synonym terms from one linguistic entity and return how many were removed.

    'Deleted' tombstones are always kept. When keep_auto_generated is True the
    terms Power BI derives from object names ('Generated'/'Suggested') survive.
    """
    protected = {"deleted"}
    if keep_auto_generated:
        protected |= {"generated", "suggested"}

    kept = []
    removed = 0
    for term_obj in entity.get("Terms") or []:
        if not isinstance(term_obj, dict):
            continue
        keep_obj = {}
        for name, props in term_obj.items():
            state = str((props or {}).get("State") or "").lower()
            if state in protected:
                keep_obj[name] = props
            else:
                removed += 1
        if keep_obj:
            kept.append(keep_obj)

    entity["Terms"] = kept
    return removed


def _target_names(items, label: str) -> dict:
    """{table_key: "Original Name"} for a list of table names."""
    targets = {}
    for item in items or []:
        name = _text(item)
        if not name:
            continue
        if not isinstance(item, str):
            raise ValueError(f"{label} entries must be table names, got {item!r}")
        targets[_key(name)] = name
    return targets


def _target_pairs(items, label: str) -> dict:
    """
    {(table_key, object_key): "Table[Object]"} for a list of object references.

    Accepts ("Table", "Object"), {"Table": ..., "Column": ...} (or "Measure"),
    and the "Table[Object]" text printed in the clear summary.
    """
    targets = {}
    for item in items or []:
        if isinstance(item, dict):
            table = _text(item.get("Table"))
            name = _text(item.get("Column") or item.get("Measure") or item.get("Name"))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            table, name = _text(item[0]), _text(item[1])
        elif isinstance(item, str) and item.strip().endswith("]") and "[" in item:
            head, _, tail = item.strip().partition("[")
            table, name = _text(head), _text(tail[:-1])
        else:
            raise ValueError(
                f'{label} entries must look like ("Table", "Object Name"), got {item!r}'
            )
        if not table or not name:
            raise ValueError(
                f"{label} entries need both a table and an object name, got {item!r}"
            )
        targets[(_key(table), _key(name))] = f"{table}[{name}]"
    return targets


def clear_semantic_model_metadata(
    dataset_name: str,
    workspace_name: str,
    clear_everything="no",
    clear_table_descriptions="no",
    clear_column_descriptions="no",
    clear_measure_descriptions="no",
    clear_hierarchy_descriptions="no",
    clear_table_synonyms="no",
    clear_column_synonyms="no",
    clear_measure_synonyms="no",
    only_tables=None,
    description_tables=None,
    description_columns=None,
    description_measures=None,
    synonym_tables=None,
    synonym_columns=None,
    synonym_measures=None,
    keep_auto_generated_synonyms="no",
    dry_run="yes",
    synonym_culture: str = "en-US",
) -> dict:
    """
    Wipe existing descriptions and/or Q&A synonyms so the model can be rebuilt from scratch.

    Two ways to choose what gets cleared, and they combine:

      Bulk    every clear_* switch takes "yes" or "no", clear_everything turns them
              all on, and only_tables narrows them to named tables (empty = whole model).
      Named   description_columns / description_measures / description_tables and
              synonym_columns / synonym_measures / synonym_tables clear exactly the
              objects listed, even when the matching bulk switch is "no". Named
              targets ignore only_tables, because naming an object is already explicit.

    Object lists take ("Table", "Object Name") pairs, {"Table": ..., "Column": ...}
    dicts, or the "Table[Object]" text this function prints. Names that match nothing
    in the model are reported at the end so typos surface instead of passing silently.

    dry_run="yes" reports what would be removed and changes nothing.

    Column descriptions on one table, synonyms left alone::

        clear_semantic_model_metadata(
            dataset_name, workspace_name,
            only_tables=["fact_onhanddetails"],
            clear_column_descriptions="yes",
            dry_run="yes",
        )

    All clear_*_synonyms default to "no", so that call does not wipe Q&A
    synonyms. Review the dry-run, then dry_run="no".

    Column synonyms on one table, descriptions / comments left alone::

        clear_semantic_model_metadata(
            dataset_name, workspace_name,
            only_tables=["fact_onhanddetails"],
            clear_column_synonyms="yes",
            dry_run="yes",
        )

    clear_column_descriptions stays "no" by default, so Unity Catalog comments
    and model descriptions are not wiped. Review the dry-run, then dry_run="no".

    Run this before the generation cells: once descriptions are gone the builders
    treat them as missing and regenerate. For synonyms also set
    force_regenerate_synonyms=True in the builders.
    """
    everything = _yes_no(clear_everything, "clear_everything")
    flags = {
        "table_descriptions": everything or _yes_no(clear_table_descriptions, "clear_table_descriptions"),
        "column_descriptions": everything or _yes_no(clear_column_descriptions, "clear_column_descriptions"),
        "measure_descriptions": everything or _yes_no(clear_measure_descriptions, "clear_measure_descriptions"),
        "hierarchy_descriptions": everything or _yes_no(clear_hierarchy_descriptions, "clear_hierarchy_descriptions"),
        "table_synonyms": everything or _yes_no(clear_table_synonyms, "clear_table_synonyms"),
        "column_synonyms": everything or _yes_no(clear_column_synonyms, "clear_column_synonyms"),
        "measure_synonyms": everything or _yes_no(clear_measure_synonyms, "clear_measure_synonyms"),
    }
    preview = _yes_no(dry_run, "dry_run")
    keep_generated = _yes_no(keep_auto_generated_synonyms, "keep_auto_generated_synonyms")

    targets = {
        "table_descriptions": _target_names(description_tables, "description_tables"),
        "column_descriptions": _target_pairs(description_columns, "description_columns"),
        "measure_descriptions": _target_pairs(description_measures, "description_measures"),
        "table_synonyms": _target_names(synonym_tables, "synonym_tables"),
        "column_synonyms": _target_pairs(synonym_columns, "synonym_columns"),
        "measure_synonyms": _target_pairs(synonym_measures, "synonym_measures"),
    }
    matched = {key: set() for key in targets}

    counts = {key: 0 for key in flags}
    counts["hierarchy_level_descriptions"] = 0
    counts["orphan_synonym_entities"] = 0
    samples = {key: [] for key in counts}

    summary = {
        "dry_run": preview,
        "switches": flags,
        "scope_tables": sorted({_text(t) for t in (only_tables or []) if _text(t)}),
        "named_targets": {k: sorted(v.values()) for k, v in targets.items() if v},
        "unmatched_targets": {},
        "counts": counts,
        "samples": samples,
    }

    if not any(flags.values()) and not any(targets.values()):
        print("Clear step skipped. Every clear_* switch is 'no' and no objects were listed.")
        return summary

    scope = {_key(t) for t in (only_tables or []) if _text(t)}
    clearing_synonyms = any(
        flags[k] or targets[k]
        for k in ("table_synonyms", "column_synonyms", "measure_synonyms")
    )

    def in_scope(table_name) -> bool:
        return not scope or _key(table_name) in scope

    def record(bucket: str, label: str) -> None:
        counts[bucket] += 1
        if len(samples[bucket]) < 25:
            samples[bucket].append(label)

    def clear_description(bucket: str, obj, label: str) -> None:
        if not _text(getattr(obj, "Description", None)):
            return
        record(bucket, label)
        if not preview:
            obj.Description = ""

    mode = "DRY RUN — nothing will be saved" if preview else "LIVE — changes will be saved"
    print(f"=== Clear model metadata ({mode}) ===")
    print(f"  Switches on: {sorted(k for k, v in flags.items() if v) or 'none'}")
    scoped = summary["scope_tables"]
    print(f"  Table scope: {len(scoped)} named table(s)" if scoped else "  Table scope: entire model")
    for key, listed in summary["named_targets"].items():
        print(f"  Named {key}: {len(listed)} object(s)")

    with connect_semantic_model(
        dataset=dataset_name,
        workspace=workspace_name,
        readonly=preview,
    ) as tom:

        for table in tom.model.Tables:
            table_key = _key(table.Name)
            scoped = in_scope(table.Name)

            if table_key in targets["table_descriptions"]:
                matched["table_descriptions"].add(table_key)
                clear_description("table_descriptions", table, table.Name)
            elif flags["table_descriptions"] and scoped:
                clear_description("table_descriptions", table, table.Name)

            for column in table.Columns:
                pair = (table_key, _key(column.Name))
                named = pair in targets["column_descriptions"]
                if named:
                    matched["column_descriptions"].add(pair)
                elif not (flags["column_descriptions"] and scoped):
                    continue
                clear_description(
                    "column_descriptions", column, f"{table.Name}[{column.Name}]"
                )

            for measure in table.Measures:
                pair = (table_key, _key(measure.Name))
                named = pair in targets["measure_descriptions"]
                if named:
                    matched["measure_descriptions"].add(pair)
                elif not (flags["measure_descriptions"] and scoped):
                    continue
                clear_description(
                    "measure_descriptions", measure, f"{table.Name}[{measure.Name}]"
                )

            if flags["hierarchy_descriptions"] and scoped:
                for hierarchy in getattr(table, "Hierarchies", []) or []:
                    clear_description(
                        "hierarchy_descriptions", hierarchy, f"{table.Name}.{hierarchy.Name}"
                    )
                    for level in getattr(hierarchy, "Levels", []) or []:
                        clear_description(
                            "hierarchy_level_descriptions",
                            level,
                            f"{table.Name}.{hierarchy.Name}.{level.Name}",
                        )

        if clearing_synonyms:
            lm = _read_linguistic_json(tom, synonym_culture)
            if lm is None:
                print(f"  No '{synonym_culture}' linguistic schema found, no synonyms to clear.")
            else:
                model_tables = {_key(t.Name): t for t in tom.model.Tables}
                clear_unresolved = all(
                    flags[k] for k in ("table_synonyms", "column_synonyms", "measure_synonyms")
                )
                removed_terms = 0

                for entity in (lm.get("Entities") or {}).values():
                    binding = ((entity or {}).get("Definition") or {}).get("Binding") or {}
                    table_name = _text(binding.get("ConceptualEntity"))
                    object_name = _text(binding.get("ConceptualProperty"))
                    if not table_name:
                        continue

                    table = model_tables.get(_key(table_name))
                    pair = (_key(table_name), _key(object_name))
                    if not object_name:
                        bucket = "table_synonyms"
                        label = table_name
                        named_in = (
                            ["table_synonyms"]
                            if _key(table_name) in targets["table_synonyms"]
                            else []
                        )
                    else:
                        label = f"{table_name}[{object_name}]"
                        named_in = [
                            key
                            for key in ("column_synonyms", "measure_synonyms")
                            if pair in targets[key]
                        ]
                        if table is not None and any(
                            _key(c.Name) == _key(object_name) for c in table.Columns
                        ):
                            bucket = "column_synonyms"
                        elif table is not None and any(
                            _key(m.Name) == _key(object_name) for m in table.Measures
                        ):
                            bucket = "measure_synonyms"
                        else:
                            bucket = "orphan_synonym_entities"

                    for key in named_in:
                        matched[key].add(
                            _key(table_name) if key == "table_synonyms" else pair
                        )

                    if not named_in:
                        if bucket == "orphan_synonym_entities":
                            if not clear_unresolved:
                                continue
                        elif not (flags[bucket] and in_scope(table_name)):
                            continue

                    if not (entity.get("Terms") or []):
                        continue

                    # A shallow copy is enough to count without touching the schema.
                    target = dict(entity) if preview else entity
                    removed = _strip_entity_terms(target, keep_generated)
                    if not preview and removed:
                        entity.pop("State", None)

                    if removed:
                        removed_terms += removed
                        record(bucket, f"{label} ({removed} terms)")

                print(f"  Synonym terms removed: {removed_terms}")
                if not preview and removed_terms:
                    _save_linguistic_json(tom, synonym_culture, lm)

    print("\n===== Clear summary =====")
    for bucket in [
        "table_descriptions",
        "column_descriptions",
        "measure_descriptions",
        "hierarchy_descriptions",
        "hierarchy_level_descriptions",
        "table_synonyms",
        "column_synonyms",
        "measure_synonyms",
        "orphan_synonym_entities",
    ]:
        verb = "would clear" if preview else "cleared"
        print(f"  {bucket}: {verb} {counts[bucket]}")

    summary["unmatched_targets"] = {
        key: sorted(display for target, display in listed.items() if target not in matched[key])
        for key, listed in targets.items()
        if any(target not in matched[key] for target in listed)
    }
    unmatched_n = sum(len(v) for v in summary["unmatched_targets"].values())
    if unmatched_n:
        print(f"  Named objects not found (check spelling): {unmatched_n}")

    if preview:
        print("\nDry run only. Set the dry run switch to 'no' to apply these removals.")

    return summary


class SemanticModelDescriptionApplier:
    """
    Apply table/column/measure descriptions and Q&A synonyms to a Power BI semantic model.

    Rules:
      1) Fill blank descriptions from Databricks metadata
      2) Do NOT overwrite existing descriptions by default
      3) Overwrite only objects listed in overwrite_* inputs
      4) Support one Databricks table -> many Power BI tables
      5) Support Databricks -> Power BI column renames via COLUMN_NAME_MAP
      6) Generate/apply column synonyms from table name + descriptions
      7) Apply measure synonyms generated from description + expression
    """

    def __init__(
        self,
        dataset_name: str,
        workspace_name: str,
        databricks_server_hostname: str = None,
        databricks_http_path: str = None,
        databricks_access_token: str = None,
        databricks_sql_query: str = None,
        databricks_comments=None,
        table_name_map: dict = None,
        column_name_map: dict = None,
        overwrite_tables=None,
        overwrite_columns=None,
        overwrite_measures=None,
        overwrite_column_synonyms=None,
        overwrite_measure_synonyms=None,
        calculated_table_descriptions=None,
        calculated_column_descriptions=None,
        measure_descriptions=None,
        generate_mapped_column_synonyms="yes",
        mapped_column_synonyms=None,
        apply_descriptions="yes",
        apply_synonyms="yes",
        synonym_culture: str = "en-US",
        synonym_registry=None,
        unique_synonyms="yes",
    ):
        self.dataset_name = dataset_name
        self.workspace_name = workspace_name

        self.databricks_server_hostname = databricks_server_hostname
        self.databricks_http_path = databricks_http_path
        self.databricks_access_token = databricks_access_token
        self.databricks_sql_query = databricks_sql_query
        self.databricks_comments = databricks_comments

        self.table_name_map = self._normalize_table_name_map(table_name_map or {})
        self.column_name_map = self._normalize_column_name_map(column_name_map or {})

        self.overwrite_tables = {
            t.strip().lower() for t in (overwrite_tables or []) if t and str(t).strip()
        }
        self.overwrite_columns = {
            (t.strip().lower(), c.strip().lower())
            for t, c in (overwrite_columns or [])
            if t and c
        }
        self.overwrite_measures = {
            (t.strip().lower(), m.strip().lower())
            for t, m in (overwrite_measures or [])
            if t and m
        }
        self.overwrite_column_synonyms = {
            (t.strip().lower(), c.strip().lower())
            for t, c in (overwrite_column_synonyms or [])
            if t and c
        }
        self.overwrite_measure_synonyms = {
            (t.strip().lower(), m.strip().lower())
            for t, m in (overwrite_measure_synonyms or [])
            if t and m
        }

        self.calculated_table_descriptions = calculated_table_descriptions or []
        self.calculated_column_descriptions = calculated_column_descriptions or []
        self.measure_descriptions = measure_descriptions or []

        # Rows flagged by merge_manual_rows win over anything generated, so the
        # generated and Databricks passes must not touch the same object. A "keep"
        # mode counts here too: it claims the object in order to leave it alone.
        self._manual_synonym_keys = {
            ("column", _key(r.get("Table")), _key(r.get("Column")))
            for r in self.calculated_column_descriptions
            if r.get("Synonym Override")
            or r.get("Skip Synonyms")
            or r.get("Replace Synonyms")
        } | {
            ("measure", _key(r.get("Table")), _key(r.get("Column")))
            for r in self.measure_descriptions
            if r.get("Synonym Override")
            or r.get("Skip Synonyms")
            or r.get("Replace Synonyms")
        }
        self._skip_synonym_keys = {
            ("column", _key(r.get("Table")), _key(r.get("Column")))
            for r in self.calculated_column_descriptions
            if r.get("Skip Synonyms")
        } | {
            ("measure", _key(r.get("Table")), _key(r.get("Column")))
            for r in self.measure_descriptions
            if r.get("Skip Synonyms")
        }
        self._skip_description_keys = {
            (_key(r.get("Table")), _key(r.get("Column")))
            for r in list(self.calculated_column_descriptions) + list(self.measure_descriptions)
            if r.get("Skip Description")
        }

        self.generate_mapped_column_synonyms = _yes_no(
            generate_mapped_column_synonyms, "generate_mapped_column_synonyms"
        )
        # Synonyms generated during the plan phase, so re-applying costs nothing.
        self.mapped_column_synonyms = mapped_column_synonyms
        self.apply_descriptions = _yes_no(apply_descriptions, "apply_descriptions")
        self.apply_synonyms = _yes_no(apply_synonyms, "apply_synonyms")
        self.synonym_culture = synonym_culture or "en-US"

        self.synonym_registry = synonym_registry or SynonymRegistry(unique_synonyms)
        self.duplicate_synonyms_dropped = 0

        self.table_desc_applied = 0
        self.column_desc_applied = 0
        self.measure_desc_applied = 0
        self.column_syn_applied = 0
        self.measure_syn_applied = 0
        self.table_syn_applied = 0
        self.manual_desc_applied = 0
        self.manual_syn_applied = 0
        self.table_not_found = 0
        self.column_not_found = 0
        self.skipped_existing = 0
        self.skipped_existing_synonyms = 0

        self.tables_with_changes = set()
        self.tables_processed = set()
        self.tables_not_found_list = set()
        self.columns_not_found_list = []
        self.columns_skipped_existing_list = []

    @staticmethod
    def _norm(s):
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return None
        s = str(s).strip()
        return s if s else None

    @staticmethod
    def _bare_name(name: str) -> str:
        if not name:
            return name
        return name.rsplit(".", 1)[-1]

    @staticmethod
    def _existing_desc(obj) -> str:
        return SemanticModelDescriptionApplier._norm(getattr(obj, "Description", None)) or ""

    @staticmethod
    def _normalize_table_name_map(raw_map: dict) -> dict:
        normalized = {}
        for k, v in raw_map.items():
            key = k.strip().lower()
            values = v if isinstance(v, (list, tuple, set)) else [v]
            cleaned = [str(x).strip() for x in values if x and str(x).strip()]
            if not cleaned:
                continue
            normalized.setdefault(key, [])
            for name in cleaned:
                if name not in normalized[key]:
                    normalized[key].append(name)
        return normalized

    @staticmethod
    def _normalize_column_name_map(raw_map: dict) -> dict:
        normalized = {}
        for t_name, cols in raw_map.items():
            if not t_name or cols is None:
                continue
            t_key = str(t_name).strip().lower()
            if not t_key:
                continue
            normalized.setdefault(t_key, {})
            for c_name, pbi_name in cols.items():
                if not c_name or pbi_name is None:
                    continue
                c_key = str(c_name).strip().lower()
                if not c_key:
                    continue
                normalized[t_key][c_key] = str(pbi_name).strip()
        return normalized

    def _resolve_pbi_column_name(self, dbr_table_name: str, dbr_column_name: str) -> str:
        t = (dbr_table_name or "").strip().lower()
        c = (dbr_column_name or "").strip().lower()
        if not t or not c:
            return dbr_column_name
        table_map = self.column_name_map.get(t, {})
        return table_map.get(c, dbr_column_name)

    def _pbi_table_name_candidates(self, dbr_table: str) -> list:
        dbr_table = self._norm(dbr_table)
        if not dbr_table:
            return []

        candidates = []
        candidates.extend(self.table_name_map.get(dbr_table.lower(), []))

        bare = self._bare_name(dbr_table)
        if bare.lower() != dbr_table.lower():
            candidates.extend(self.table_name_map.get(bare.lower(), []))

        if not candidates:
            candidates = [bare]

        unique = []
        seen = set()
        for name in candidates:
            key = str(name).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(str(name).strip())
        return unique

    def _can_overwrite(self, kind: str, table_name: str, object_name: str = None) -> bool:
        t = (table_name or "").strip().lower()
        o = (object_name or "").strip().lower() if object_name else None

        if kind == "table":
            return t in self.overwrite_tables
        if kind == "column":
            return (t, o) in self.overwrite_columns
        if kind == "measure":
            return (t, o) in self.overwrite_measures
        if kind == "column_synonym":
            return (t, o) in self.overwrite_column_synonyms
        if kind == "measure_synonym":
            return (t, o) in self.overwrite_measure_synonyms
        if kind == "table_synonym":
            return t in self.overwrite_tables
        return False

    def _should_apply_description(
        self,
        obj,
        new_desc: str,
        kind: str,
        table_name: str,
        object_name: str = None,
        force: bool = False,
    ) -> bool:
        if not self.apply_descriptions:
            return False
        if object_name and (_key(table_name), _key(object_name)) in self._skip_description_keys:
            return False

        new_desc = self._norm(new_desc)
        if not new_desc:
            return False

        existing = self._existing_desc(obj)
        if not existing:
            return True

        if existing == new_desc:
            return False

        # force comes from a manual override row, which does not need to be
        # repeated in the overwrite_* lists.
        return force or self._can_overwrite(kind, table_name, object_name)

    def _find_table(self, tom, name: str):
        if not name:
            return None
        target = name.strip().lower()
        for t in tom.model.Tables:
            if t.Name and t.Name.strip().lower() == target:
                return t
        return None

    def _find_column(self, table, name: str):
        if not name:
            return None
        target = name.strip().lower()
        for c in table.Columns:
            if c.Name and c.Name.strip().lower() == target:
                return c
        return None

    def _find_measure(self, table, name: str):
        if not name:
            return None
        target = name.strip().lower()
        for m in table.Measures:
            if m.Name and m.Name.strip().lower() == target:
                return m
        return None

    def resolve_pbi_tables(self, tom, dbr_table: str):
        tables = []
        seen = set()
        for name in self._pbi_table_name_candidates(dbr_table):
            t = self._find_table(tom, name)
            if t is None:
                continue
            key = t.Name.lower()
            if key in seen:
                continue
            seen.add(key)
            tables.append(t)
        return tables

    def load_comments_from_databricks(self) -> pd.DataFrame:
        # Reuse comments the plan already fetched instead of querying twice.
        if self.databricks_comments is not None:
            return _normalize_comment_columns(self.databricks_comments)
        if not self.databricks_sql_query:
            raise ValueError(
                "Provide either databricks_comments or databricks_sql_query."
            )

        return _normalize_comment_columns(
            _run_databricks_query(
                self.databricks_server_hostname,
                self.databricks_http_path,
                self.databricks_access_token,
                self.databricks_sql_query,
            )
        )

    def _ensure_linguistic_schema(self, tom):
        _ensure_linguistic_schema(tom, self.synonym_culture)

    def _load_linguistic_json(self, tom) -> dict:
        return _load_linguistic_json(tom, self.synonym_culture)

    @staticmethod
    def _find_entity_key(lm: dict, table_name: str, object_name: str = None):
        for key, ent in (lm.get("Entities") or {}).items():
            binding = ((ent or {}).get("Definition") or {}).get("Binding") or {}
            if str(binding.get("ConceptualEntity") or "") != table_name:
                continue
            prop = binding.get("ConceptualProperty")
            if object_name is None and not prop:
                return key
            if object_name is not None and str(prop or "") == object_name:
                return key
        return None

    @staticmethod
    def _authored_terms(entity: dict) -> list:
        return _authored_terms(entity)

    def _queue_synonyms(
        self,
        pending: list,
        kind: str,
        table_name: str,
        object_name: str,
        synonyms,
        existing_terms: list,
        manual: bool = False,
        mode: str = SYNONYM_MODE_OVERWRITE,
        force_replace: bool = False,
    ):
        key = (kind, _key(table_name), _key(object_name))
        if key in self._skip_synonym_keys:
            return
        if not manual and key in self._manual_synonym_keys:
            return

        if manual:
            # Hand-written terms are kept verbatim; no name-similarity filtering.
            syns = _parse_synonyms(synonyms, limit=None)
        else:
            syns = _drop_self_name_synonyms(_parse_synonyms(synonyms), object_name, table_name)
        # Empty list is a no-op unless Replace Synonyms / force_replace asked
        # to wipe live Q&A terms.
        if not syns and not force_replace:
            return

        # One phrase belongs to one object; a hand-written row outranks a generated one.
        if syns:
            before = len(syns)
            syns = self.synonym_registry.claim(
                syns, kind, table_name, object_name, priority=manual
            )
            self.duplicate_synonyms_dropped += before - len(syns)
            if not syns and not force_replace:
                return

        if manual:
            resolved = _SYNONYM_MODE_ALIASES.get(_key(mode), MODE_OVERWRITE)
            if resolved == MODE_KEEP:
                return
            if resolved == MODE_FILL:
                if existing_terms:
                    self.skipped_existing_synonyms += 1
                    return
                replace = False
            else:
                replace = resolved == MODE_OVERWRITE
        else:
            overwrite = force_replace or self._can_overwrite(
                "column_synonym" if kind == "column" else "measure_synonym",
                table_name,
                object_name,
            )
            if existing_terms and not overwrite:
                self.skipped_existing_synonyms += 1
                return
            replace = bool(force_replace or (existing_terms and overwrite))

        pending.append(
            {
                "kind": kind,
                "table": table_name,
                "name": object_name,
                "synonyms": syns,
                "replace": replace,
                "manual": manual,
            }
        )

    def _commit_synonyms(self, tom, pending: list):
        if not pending:
            return

        lm = self._load_linguistic_json(tom)
        entities = lm.setdefault("Entities", {})
        now = datetime.now().isoformat(timespec="milliseconds") + "Z"
        syn_props = {"Type": "Noun", "State": "Authored", "LastModified": now}

        def unique_entity_key(table_name, object_name):
            base = f"{table_name}.{object_name}".lower().replace(" ", "_")
            key = base
            counter = 1
            existing_keys = set(entities.keys())
            while key in existing_keys:
                key = f"{base}_{counter}"
                counter += 1
            return key

        for item in pending:
            table_name = item["table"]
            object_name = item["name"]
            key = self._find_entity_key(lm, table_name, object_name)
            is_table = item["kind"] == "table"
            if key is None:
                key = unique_entity_key(table_name, object_name or table_name)
                binding = {"ConceptualEntity": table_name}
                if not is_table:
                    binding["ConceptualProperty"] = object_name
                entities[key] = {
                    "Definition": {"Binding": binding},
                    "Terms": [],
                }

            entity = entities[key]
            stripped = False
            if item["replace"]:
                kept = []
                for term_obj in entity.get("Terms") or []:
                    if not isinstance(term_obj, dict):
                        continue
                    new_term_obj = {}
                    for name, props in term_obj.items():
                        state = str((props or {}).get("State") or "").lower()
                        if state == "suggested":
                            new_term_obj[name] = props
                    if new_term_obj:
                        kept.append(new_term_obj)
                stripped = kept != (entity.get("Terms") or [])
                entity["Terms"] = kept

            existing_lower = {t.lower() for t in self._authored_terms(entity)}
            added = 0
            for syn in item["synonyms"]:
                if syn.lower() in existing_lower:
                    continue
                entity.setdefault("Terms", []).append({syn: dict(syn_props)})
                existing_lower.add(syn.lower())
                added += 1

            if "State" in entity:
                del entity["State"]

            # Count a Replace Synonyms wipe (empty list) as applied too.
            if added or stripped:
                if item["kind"] == "measure":
                    self.measure_syn_applied += 1
                elif item["kind"] == "table":
                    self.table_syn_applied += 1
                else:
                    self.column_syn_applied += 1
                if item.get("manual"):
                    self.manual_syn_applied += 1
                self.tables_with_changes.add(table_name)

        if getattr(self, "_apply_changes", False):
            _save_linguistic_json(tom, self.synonym_culture, lm)

    def _generate_mapped_column_synonyms(self, df: pd.DataFrame, existing_syn: dict) -> dict:
        rows = []
        seen = set()
        for _, row in df.iterrows():
            dbr_table = self._norm(row.get("databricks_table"))
            dbr_column_name = self._norm(row.get("column_name"))
            column_desc = self._norm(row.get("column_description")) or ""
            table_desc = self._norm(row.get("table_description")) or ""
            if not dbr_table or not dbr_column_name:
                continue

            pbi_column_name = self._resolve_pbi_column_name(dbr_table, dbr_column_name)
            for pbi_table in self._pbi_table_name_candidates(dbr_table):
                key = (_key(pbi_table), _key(pbi_column_name))
                if key in seen:
                    continue
                seen.add(key)

                if ("column", key[0], key[1]) in self._manual_synonym_keys:
                    continue

                existing = existing_syn.get((key[0], key[1], "column"), [])
                overwrite = self._can_overwrite("column_synonym", pbi_table, pbi_column_name)
                if existing and not overwrite:
                    continue

                rows.append(
                    {
                        "Table Name": pbi_table,
                        "Table Description": table_desc,
                        "Column Name": pbi_column_name,
                        "Desc": column_desc,
                    }
                )

        result = {}
        if not rows:
            return result

        to_syn = pd.DataFrame(rows)
        syn_lists = _generate_synonyms_with_quality_gate(
            to_syn,
            prompt=COLUMN_SYNONYM_PROMPT,
            retry_prompt=COLUMN_SYNONYM_RETRY_PROMPT,
            name_cols=["Column Name", "Table Name"],
            registry=self.synonym_registry,
            owner_kind="column",
            owner_table_col="Table Name",
            owner_name_col="Column Name",
            min_count=MIN_COLUMN_SYNONYMS,
            max_count=MAX_COLUMN_SYNONYMS,
            progress_label=f"column synonyms ({len(to_syn)} Databricks-mapped columns)",
            retry_label=(
                "column synonyms, unique-wording retry ({n} Databricks-mapped columns)"
            ),
        )
        for rec, syns in zip(to_syn.to_dict("records"), syn_lists):
            result[(_key(rec["Table Name"]), _key(rec["Column Name"]))] = list(syns or [])
        return result

    def _assign_description(self, obj, desc) -> None:
        if getattr(self, "_apply_changes", False):
            obj.Description = desc

    def apply(self, apply_changes: bool = False) -> dict:
        """
        Enrich the semantic model from Databricks comments plus generated rows.

        Dry-run is the default. Pass apply_changes=True to write via TOM / SemPy.
        """
        _require_sempy("apply descriptions and synonyms to a semantic model")
        self._apply_changes = bool(apply_changes)

        try:
            df = self.load_comments_from_databricks()
        except Exception as exc:  # noqa: BLE001
            if self.calculated_column_descriptions or self.measure_descriptions or self.calculated_table_descriptions:
                logger.warning("Databricks comments unavailable (%s); applying generated rows only.", exc)
                df = _empty_comments_frame()
            else:
                raise

        if df is None or df.empty:
            df = _empty_comments_frame()
            print("No Databricks comment rows; applying generated table/column/measure rows only.")

        n_uc = int(df["databricks_table"].nunique()) if not df.empty and "databricks_table" in df.columns else 0
        if apply_changes:
            print("=== Metadata sync: LIVE apply (changes will be saved) ===")
        else:
            print("=== Metadata sync: DRY RUN (nothing will be saved) ===")
        print(f"  Databricks comments: {len(df)} column(s) from {n_uc} table(s)")
        ow_t = len(self.overwrite_tables)
        ow_c = len(self.overwrite_columns)
        ow_m = len(self.overwrite_measures)
        ow_cs = len(self.overwrite_column_synonyms)
        ow_ms = len(self.overwrite_measure_synonyms)
        if ow_t or ow_c or ow_m or ow_cs or ow_ms:
            print(
                f"  Overwrite lists: {ow_t} table(s), {ow_c} column(s), {ow_m} measure(s), "
                f"{ow_cs} column synonym(s), {ow_ms} measure synonym(s)"
            )
        print(
            f"  Writing: descriptions={'yes' if self.apply_descriptions else 'no'} | "
            f"synonyms={'yes' if self.apply_synonyms else 'no'} ({self.synonym_culture})"
        )

        self.table_desc_applied = 0
        self.column_desc_applied = 0
        self.measure_desc_applied = 0
        self.column_syn_applied = 0
        self.measure_syn_applied = 0
        self.table_syn_applied = 0
        self.manual_desc_applied = 0
        self.manual_syn_applied = 0
        self.table_not_found = 0
        self.column_not_found = 0
        self.skipped_existing = 0
        self.skipped_existing_synonyms = 0
        self.tables_with_changes.clear()
        self.tables_processed.clear()
        self.tables_not_found_list.clear()
        self.columns_not_found_list.clear()
        self.columns_skipped_existing_list.clear()
        table_description_assigned = set()

        existing_syn = {}
        mapped_column_synonyms = {}
        if self.apply_synonyms:
            existing_syn = load_existing_synonyms_map(
                self.dataset_name, self.workspace_name, culture=self.synonym_culture
            )
            self.synonym_registry.seed_from_model(existing_syn)

            # Hand-written rows claim their phrases before anything generated, so a
            # developer's wording is never the one that loses a collision.
            for kind, rows in (
                ("column", self.calculated_column_descriptions),
                ("measure", self.measure_descriptions),
            ):
                for r in rows:
                    if not r.get("Synonym Override"):
                        continue
                    self.synonym_registry.claim(
                        _parse_synonyms(r.get("Synonyms"), limit=None),
                        kind,
                        r.get("Table"),
                        r.get("Column"),
                        priority=True,
                    )

            if self.mapped_column_synonyms is not None:
                mapped_column_synonyms = self.mapped_column_synonyms
            elif self.generate_mapped_column_synonyms:
                mapped_column_synonyms = self._generate_mapped_column_synonyms(df, existing_syn)

        pending_synonyms = []

        with connect_semantic_model(
            dataset=self.dataset_name,
            workspace=self.workspace_name,
            readonly=not apply_changes,
        ) as tom:

            for _, row in df.iterrows():
                dbr_table = self._norm(row.get("databricks_table"))
                dbr_column_name = self._norm(row.get("column_name"))
                column_desc = self._norm(row.get("column_description"))
                table_desc = self._norm(row.get("table_description"))

                if not dbr_table or not dbr_column_name or not column_desc:
                    continue

                tables = self.resolve_pbi_tables(tom, dbr_table)
                if not tables:
                    self.table_not_found += 1
                    self.tables_not_found_list.add(dbr_table)
                    continue

                pbi_column_name = self._resolve_pbi_column_name(dbr_table, dbr_column_name)

                for table in tables:
                    self.tables_processed.add(table.Name)

                    if table_desc and table.Name.lower() not in table_description_assigned:
                        table_description_assigned.add(table.Name.lower())
                        if self._should_apply_description(table, table_desc, "table", table.Name):
                            self._assign_description(table, table_desc)
                            self.table_desc_applied += 1
                            self.tables_with_changes.add(table.Name)
                        elif self._existing_desc(table):
                            self.skipped_existing += 1

                    col = self._find_column(table, pbi_column_name)
                    if col is None:
                        self.column_not_found += 1
                        if len(self.columns_not_found_list) < 100:
                            self.columns_not_found_list.append((table.Name, pbi_column_name))
                        continue

                    if self._should_apply_description(col, column_desc, "column", table.Name, col.Name):
                        self._assign_description(col, column_desc)
                        self.column_desc_applied += 1
                        self.tables_with_changes.add(table.Name)
                    elif self._existing_desc(col):
                        self.skipped_existing += 1
                        if len(self.columns_skipped_existing_list) < 100:
                            self.columns_skipped_existing_list.append((table.Name, col.Name))

                    if self.apply_synonyms:
                        syns = _lookup_mapped_column_synonyms(
                            mapped_column_synonyms, table.Name, col.Name
                        )
                        self._queue_synonyms(
                            pending_synonyms,
                            "column",
                            table.Name,
                            col.Name,
                            syns,
                            existing_syn.get((table.Name.lower(), col.Name.lower(), "column"), []),
                        )

            for r in self.calculated_table_descriptions:
                t_name = self._norm(r.get("Table"))
                desc = self._norm(r.get("Desc"))
                if not t_name:
                    continue

                table = self._find_table(tom, t_name)
                if table is None:
                    self.table_not_found += 1
                    self.tables_not_found_list.add(t_name)
                    continue

                self.tables_processed.add(table.Name)
                force = bool(r.get("Force"))

                if desc and not r.get("Skip Description"):
                    if self._should_apply_description(
                        table, desc, "table", table.Name, force=force
                    ):
                        self._assign_description(table, desc)
                        self.table_desc_applied += 1
                        if force:
                            self.manual_desc_applied += 1
                        self.tables_with_changes.add(table.Name)
                    elif self._existing_desc(table):
                        self.skipped_existing += 1

                if self.apply_synonyms and (
                    r.get("Synonyms") or r.get("Replace Synonyms")
                ):
                    self._queue_synonyms(
                        pending_synonyms,
                        "table",
                        table.Name,
                        table.Name,
                        r.get("Synonyms"),
                        existing_syn.get((table.Name.lower(), "", "table"), []),
                        manual=bool(r.get("Synonym Override")),
                        mode=r.get("Synonym Mode") or SYNONYM_MODE_OVERWRITE,
                        force_replace=bool(r.get("Replace Synonyms")),
                    )

            for r in self.calculated_column_descriptions:
                t_name = self._norm(r.get("Table"))
                c_name = self._norm(r.get("Column"))
                desc = self._norm(r.get("Desc"))
                if not t_name or not c_name:
                    continue

                table = self._find_table(tom, t_name)
                if table is None:
                    self.table_not_found += 1
                    self.tables_not_found_list.add(t_name)
                    continue

                self.tables_processed.add(table.Name)

                col = self._find_column(table, c_name)
                if col is None:
                    self.column_not_found += 1
                    if len(self.columns_not_found_list) < 100:
                        self.columns_not_found_list.append((table.Name, c_name))
                    continue

                force = bool(r.get("Force"))
                if desc and self._should_apply_description(
                    col, desc, "column", table.Name, col.Name, force=force
                ):
                    self._assign_description(col, desc)
                    self.column_desc_applied += 1
                    if force:
                        self.manual_desc_applied += 1
                    self.tables_with_changes.add(table.Name)
                elif desc and self._existing_desc(col):
                    self.skipped_existing += 1
                    if len(self.columns_skipped_existing_list) < 100:
                        self.columns_skipped_existing_list.append((table.Name, col.Name))

                if self.apply_synonyms:
                    self._queue_synonyms(
                        pending_synonyms,
                        "column",
                        table.Name,
                        col.Name,
                        r.get("Synonyms"),
                        existing_syn.get((table.Name.lower(), col.Name.lower(), "column"), []),
                        manual=bool(r.get("Synonym Override")),
                        mode=r.get("Synonym Mode") or SYNONYM_MODE_OVERWRITE,
                        force_replace=bool(r.get("Replace Synonyms")),
                    )

            for r in self.measure_descriptions:
                t_name = self._norm(r.get("Table"))
                m_name = self._norm(r.get("Column"))
                desc = self._norm(r.get("Desc"))
                if not t_name or not m_name:
                    continue

                table = self._find_table(tom, t_name)
                if table is None:
                    self.table_not_found += 1
                    self.tables_not_found_list.add(t_name)
                    continue

                self.tables_processed.add(table.Name)

                measure = self._find_measure(table, m_name)
                if measure is None:
                    self.column_not_found += 1
                    if len(self.columns_not_found_list) < 100:
                        self.columns_not_found_list.append((table.Name, m_name))
                    continue

                force = bool(r.get("Force"))
                if desc and self._should_apply_description(
                    measure, desc, "measure", table.Name, measure.Name, force=force
                ):
                    self._assign_description(measure, desc)
                    self.measure_desc_applied += 1
                    if force:
                        self.manual_desc_applied += 1
                    self.tables_with_changes.add(table.Name)
                elif desc and self._existing_desc(measure):
                    self.skipped_existing += 1
                    if len(self.columns_skipped_existing_list) < 100:
                        self.columns_skipped_existing_list.append((table.Name, measure.Name))

                if self.apply_synonyms:
                    self._queue_synonyms(
                        pending_synonyms,
                        "measure",
                        table.Name,
                        measure.Name,
                        r.get("Synonyms"),
                        existing_syn.get((table.Name.lower(), measure.Name.lower(), "measure"), []),
                        manual=bool(r.get("Synonym Override")),
                        mode=r.get("Synonym Mode") or SYNONYM_MODE_OVERWRITE,
                        force_replace=bool(r.get("Replace Synonyms")),
                    )

            if self.apply_synonyms:
                self._commit_synonyms(tom, pending_synonyms)

        summary = {
            "table_descriptions_applied": self.table_desc_applied,
            "column_descriptions_applied": self.column_desc_applied,
            "measure_descriptions_applied": self.measure_desc_applied,
            "column_synonyms_applied": self.column_syn_applied,
            "measure_synonyms_applied": self.measure_syn_applied,
            "table_synonyms_applied": self.table_syn_applied,
            "manual_descriptions_applied": self.manual_desc_applied,
            "manual_synonyms_applied": self.manual_syn_applied,
            "duplicate_synonyms_dropped": self.duplicate_synonyms_dropped,
            "skipped_existing": self.skipped_existing,
            "skipped_existing_synonyms": self.skipped_existing_synonyms,
            "table_not_found": self.table_not_found,
            "column_or_measure_not_found": self.column_not_found,
            "tables_processed_count": len(self.tables_processed),
            "tables_with_changes_count": len(self.tables_with_changes),
            "tables_processed": sorted(self.tables_processed),
            "tables_with_changes": sorted(self.tables_with_changes),
            "tables_not_found_list": sorted(self.tables_not_found_list),
            "columns_not_found_samples": self.columns_not_found_list[:20],
            "columns_skipped_existing_samples": self.columns_skipped_existing_list[:20],
        }

        print("=== Apply summary ===")
        print(
            f"  Tables processed: {summary['tables_processed_count']} | "
            f"tables with changes: {summary['tables_with_changes_count']}"
        )
        print(
            f"  Descriptions applied: {summary['table_descriptions_applied']} table(s), "
            f"{summary['column_descriptions_applied']} column(s), "
            f"{summary['measure_descriptions_applied']} measure(s)"
        )
        print(
            f"  Synonyms applied: {summary['table_synonyms_applied']} table(s), "
            f"{summary['column_synonyms_applied']} column(s), "
            f"{summary['measure_synonyms_applied']} measure(s)"
        )
        print(
            f"  Manual overrides: {summary['manual_descriptions_applied']} description(s), "
            f"{summary['manual_synonyms_applied']} synonym set(s)"
        )
        print(
            f"  Skipped (already present): {summary['skipped_existing']} description(s), "
            f"{summary['skipped_existing_synonyms']} synonym set(s)"
        )
        print(
            f"  Not found in the model: {summary['table_not_found']} table row(s), "
            f"{summary['column_or_measure_not_found']} column/measure row(s)"
        )
        if summary["duplicate_synonyms_dropped"]:
            print(
                f"  Duplicate synonym phrases dropped: {summary['duplicate_synonyms_dropped']}"
            )

        return summary


# =========================
# Auto discovery: replaces the hand-maintained maps
# =========================

REQUIRED_COMMENT_COLUMNS = (
    "databricks_table",
    "column_name",
    "column_description",
    "table_description",
)

# Pieces of a warehouse object name that carry no business meaning, so they are
# dropped before comparing a Databricks view name to a Power BI table name.
_SOURCE_NAME_PREFIXES = ("v_pbi_", "vw_pbi_", "pbi_", "vw_", "v_")
_SOURCE_NAME_TAGS = ("fact_", "dim_", "bridge_", "agg_", "lkp_", "ref_")
_SOURCE_NAME_SUFFIXES = (
    "_globalrevenue",
    "_global_revenue",
    "_global_inv",
    "_plt",
    "_gld",
    "_vw",
    "_v",
)


def _normalize_comment_columns(df) -> pd.DataFrame:
    """Give a Databricks comment result set the column names the applier expects."""
    if df is None:
        raise ValueError("No Databricks comment data provided.")

    work = pd.DataFrame(df).copy()
    rename_map = {
        "databricks_table_name": "databricks_table",
        "table_name": "databricks_table",
        "col_name": "column_name",
        "comment": "column_description",
    }
    work.columns = [str(c).strip().lower() for c in work.columns]
    work = work.rename(columns={k: v for k, v in rename_map.items() if k in work.columns})

    missing = [c for c in REQUIRED_COMMENT_COLUMNS if c not in work.columns]
    if missing:
        raise ValueError(
            f"Databricks comment data is missing required columns: {missing}. "
            f"Found: {sorted(work.columns)}"
        )
    return work[list(REQUIRED_COMMENT_COLUMNS)]


def _canonical_source_name(name) -> str:
    """
    Reduce a table name to comparable letters and digits.

    'v_pbi_dim_territorysite' and 'Territory Sites' both land on 'territorysite',
    which is what lets the mapping fall back to names when a Power BI table has no
    readable source query.
    """
    text = _key(name).rsplit(".", 1)[-1]

    changed = True
    while changed:
        changed = False
        for prefix in _SOURCE_NAME_PREFIXES + _SOURCE_NAME_TAGS:
            if text.startswith(prefix):
                text = text[len(prefix):]
                changed = True
        for suffix in _SOURCE_NAME_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                changed = True

    text = re.sub(r"[^a-z0-9]+", "", text)
    if len(text) > 4 and text.endswith("s"):
        text = text[:-1]
    return text


def _source_table_candidates(text: str) -> set:
    """
    Pull the warehouse object names a source query mentions.

    Used twice with the same rules, so the names asked for and the names matched
    can never disagree: once to build the IN filter for the catalog listing, and
    once to match a Power BI table to the view that came back.
    """
    low = str(text or "").lower()
    found = set()

    # Power Query navigation, e.g. gold{[Item="v_pbi_dim_item"]}
    for match in re.finditer(r'(?:item|name)\s*=\s*"?([a-z0-9_.]+)"?', low):
        found.add(match.group(1))

    # Native SQL, e.g. from gold.v_pbi_dim_item
    for match in re.finditer(r"\b(?:from|join)\s+([a-z0-9_.]+)", low):
        found.add(match.group(1))

    # Anything else shaped like a warehouse object name
    for token in re.findall(r"[a-z][a-z0-9_]{3,}", low):
        if "_" in token:
            found.add(token)

    return {name.rsplit(".", 1)[-1] for name in found if name.rsplit(".", 1)[-1]}


def _empty_comments_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(REQUIRED_COMMENT_COLUMNS))


def _partition_source_text(table) -> str:
    """Best-effort read of a table's source query, whatever partition style it uses."""
    chunks = []
    for partition in getattr(table, "Partitions", []) or []:
        source = getattr(partition, "Source", None)
        if source is None:
            continue
        for attr in ("Expression", "Query", "DataSource", "EntityName", "SchemaName"):
            value = getattr(source, attr, None)
            if value:
                chunks.append(str(value))
    return "\n".join(chunks)


def _run_databricks_query(
    server_hostname: str = None,
    http_path: str = None,
    access_token: str = None,
    query: str = "",
) -> pd.DataFrame:
    """
    Run a Unity Catalog SQL statement.

    Prefers an active Spark session (Databricks / Fabric Spark). Falls back to
    the SQL warehouse connector. Retries transient warehouse errors.
    """
    if not query or not str(query).strip():
        raise ValueError("Databricks query is empty.")

    spark = _get_spark()
    if spark is not None:
        try:
            return spark.sql(query).toPandas()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Spark SQL failed (%s); falling back to SQL warehouse.", exc)

    if not _DATABRICKS_SQL_AVAILABLE or databricks_sql is None:
        raise RuntimeError(
            "Cannot query Databricks: no Spark session and databricks-sql-connector "
            "is not installed. Provide a comments DataFrame, or run in Fabric / Databricks."
        )
    if not all([server_hostname, http_path, access_token]):
        raise ValueError(
            "Databricks warehouse credentials are missing. Set DATABRICKS_SERVER_HOSTNAME, "
            "DATABRICKS_HTTP_PATH and DATABRICKS_ACCESS_TOKEN (or a Key Vault secret), "
            "or pass a preloaded comments DataFrame."
        )

    def _call():
        with databricks_sql.connect(
            server_hostname=server_hostname,
            http_path=http_path,
            access_token=access_token,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                cols = [d[0] for d in cursor.description]
        return pd.DataFrame(rows, columns=cols)

    return _retry_call(_call, label="Databricks SQL warehouse query")


def load_databricks_table_catalog(
    server_hostname: str,
    http_path: str,
    access_token: str,
    catalog_pattern: str = "%mde%",
    schemas=("gold", "platinum"),
    table_names=None,
) -> pd.DataFrame:
    """
    List view names and their table comments. One row per view, not per column.

    This is the authority on whether a view has a table comment, because the column
    query only returns columns that carry a comment and would miss a view whose
    table is documented but whose columns are not.
    """
    schema_list = ", ".join(f"'{_text(s)}'" for s in schemas if _text(s))
    table_filter = ""
    names = sorted({_key(t) for t in (table_names or []) if _text(t)})
    if names:
        table_filter = "AND lower(t.table_name) IN (" + ", ".join(f"'{n}'" for n in names) + ")"

    query = f"""
        SELECT
            t.table_schema,
            t.table_name AS databricks_table,
            t.comment AS table_description
        FROM system.information_schema.tables t
        WHERE t.table_catalog LIKE '{catalog_pattern}'
          AND t.table_schema IN ({schema_list})
          {table_filter}
    """
    df = _run_databricks_query(server_hostname, http_path, access_token, query)
    df.columns = [str(c).strip().lower() for c in df.columns]
    print(
        f"Step 1 — Databricks: listed {len(df)} Unity Catalog tables "
        f"in {catalog_pattern} {list(schemas)}."
    )
    return df


def load_databricks_comments(
    server_hostname: str,
    http_path: str,
    access_token: str,
    catalog_pattern: str = "%mde%",
    schemas=("gold", "platinum"),
    table_names=None,
) -> pd.DataFrame:
    """
    Pull column and table comments for the given views only.

    table_names is the resolved list of views the model actually reads, so the
    query carries an IN filter instead of scanning the whole catalog. Passing an
    empty list would fetch everything, so that is refused.
    """
    names = sorted({_key(t) for t in (table_names or []) if _text(t)})
    if not names:
        raise ValueError(
            "No Databricks tables resolved, so there is nothing to load. "
            "Set TABLE_NAME_MAP, or leave auto discovery on so the model's source "
            "queries can be read."
        )
    query = build_databricks_metadata_sql(
        table_name_map={name: name for name in names},
        catalog_pattern=catalog_pattern,
        schemas=schemas,
    )

    df = _normalize_comment_columns(
        _run_databricks_query(server_hostname, http_path, access_token, query)
    )
    n_tables = int(df["databricks_table"].nunique()) if not df.empty else 0
    print(
        f"Step 1 — Databricks: extracted {len(df)} column comments "
        f"from {n_tables} Unity Catalog tables."
    )

    returned = {_key(t) for t in df["databricks_table"].unique()}
    empty_n = sum(1 for n in names if n not in returned)
    if empty_n:
        print(f"  {empty_n} mapped table(s) had no column comments.")
    return df


def read_model_source_tables(dataset_name: str, workspace_name: str) -> list:
    """
    Read every table's source query once and note the view names it mentions.

    The result feeds both the catalog listing filter and the mapping, so the model
    is opened once instead of twice.
    """
    snapshot = []
    with connect_semantic_model(
        dataset=dataset_name, workspace=workspace_name, readonly=True
    ) as tom:
        for table in tom.model.Tables:
            snapshot.append(
                {
                    "Power BI Table": _text(table.Name),
                    "Candidates": _source_table_candidates(_partition_source_text(table)),
                }
            )
    return snapshot


def load_databricks_metadata(
    table_name_map: dict,
    server_hostname: str,
    http_path: str,
    access_token: str,
    catalog_pattern: str = "%mde%",
    schemas=("gold", "platinum"),
) -> pd.DataFrame:
    """
    Run the mapped-table metadata query, with the IN list built from table_name_map.

    One query for both column comments and table comments, filtered to the views the
    map names. Because the query keeps only columns that carry a comment, a view with
    no commented columns returns no rows at all and therefore no table comment; those
    tables are the ones build_mapped_table_description_rows hands to the AI.
    """
    normalized = SemanticModelDescriptionApplier._normalize_table_name_map(
        table_name_map or {}
    )
    if not normalized:
        raise ValueError(
            "table_name_map is empty, so there is nothing to query. Add "
            "'databricks_view': 'Power BI Table' entries."
        )

    query = build_databricks_metadata_sql(
        table_name_map=normalized,
        catalog_pattern=catalog_pattern,
        schemas=schemas,
    )

    df = _normalize_comment_columns(
        _run_databricks_query(server_hostname, http_path, access_token, query)
    )
    returned = {_key(t) for t in df["databricks_table"].unique()}
    print(
        f"Step 1 — Databricks: extracted {len(df)} column comments "
        f"from {len(returned)} of {len(normalized)} mapped tables."
    )

    silent_n = len(set(normalized) - returned)
    if silent_n:
        print(
            f"  {silent_n} mapped table(s) had no column comments "
            "(AI will describe those tables)."
        )
    return df


def read_model_table_descriptions(dataset_name: str, workspace_name: str) -> dict:
    """{table_key: current description} so a re-run does not redo finished work."""
    with connect_semantic_model(
        dataset=dataset_name, workspace=workspace_name, readonly=True
    ) as tom:
        return {
            _key(t.Name): _text(getattr(t, "Description", "")) for t in tom.model.Tables
        }


def build_mapped_table_description_rows(
    table_name_map: dict,
    comments_df: pd.DataFrame,
    table_comments: pd.DataFrame = None,
    generate_missing="yes",
    force_regenerate="no",
    existing_descriptions: dict = None,
    announce_skip: bool = True,
) -> tuple:
    """
    Give every Power BI table in the map a description.

    The view's table comment is used where the query returned one, and it lands on
    each Power BI table that view feeds, so one view mapped to three tables describes
    all three. Where the query has no table comment, Fabric writes one from the table
    name, the view name, and whatever column comments did come back.

    existing_descriptions is what the model already holds. A table that is already
    described is left alone rather than sent to the AI again, which is what makes a
    second run cheap. Pass force_regenerate="yes" to rewrite regardless.

    Returns (rows, preview). Rows are TABLE_ROWS shaped and carry a force flag only
    when force_regenerate asked for a rewrite.
    """
    generate_missing = _yes_no(generate_missing, "generate_missing")
    force_regenerate = _yes_no(force_regenerate, "force_regenerate")
    generate_missing = generate_missing or force_regenerate
    already_described = {
        _key(name): _text(desc) for name, desc in (existing_descriptions or {}).items()
    }
    normalized = SemanticModelDescriptionApplier._normalize_table_name_map(
        table_name_map or {}
    )
    if not normalized:
        return [], pd.DataFrame()

    comments = _normalize_comment_columns(comments_df) if comments_df is not None else _empty_comments_frame()

    # Column comments give the AI something concrete to describe the table with.
    context = {}
    for row in comments.to_dict("records"):
        view = _key(row.get("databricks_table"))
        if view not in normalized:
            continue
        entry = context.setdefault(view, {"description": "", "columns": []})
        if not entry["description"]:
            entry["description"] = _text(row.get("table_description"))
        column = _text(row.get("column_name"))
        if column and len(entry["columns"]) < 25:
            note = _text(row.get("column_description"))
            entry["columns"].append(f"{column} ({note})" if note else column)

    # A table comment may also be known from the catalog listing, which sees views
    # whose columns carry no comments.
    if table_comments is not None and not table_comments.empty:
        for row in table_comments.to_dict("records"):
            view = _key(row.get("databricks_table"))
            if view not in normalized:
                continue
            entry = context.setdefault(view, {"description": "", "columns": []})
            if not entry["description"]:
                entry["description"] = _text(row.get("table_description"))

    records = []
    for view, pbi_tables in normalized.items():
        entry = context.get(view, {"description": "", "columns": []})
        for pbi in pbi_tables:
            records.append(
                {
                    "Table": pbi,
                    "Source View": view,
                    "Desc": entry["description"],
                    "Column Context": ", ".join(entry["columns"]),
                    "In Model": already_described.get(_key(pbi), ""),
                }
            )

    preview = pd.DataFrame(records)
    if preview.empty:
        return [], preview

    blank_mask = _blank_text_mask(preview["Desc"])
    has_model_text = ~_blank_text_mask(preview["In Model"])

    preview["Description Source"] = "From Databricks"
    preview.loc[blank_mask & has_model_text, "Description Source"] = "Already in the model"
    preview.loc[blank_mask & ~has_model_text, "Description Source"] = "Missing, not generated"

    # Only describe what nothing else has described yet.
    generate_mask = blank_mask if force_regenerate else (blank_mask & ~has_model_text)

    if not generate_missing:
        if announce_skip:
            _log_skip_ai_descriptions("table", "generate_missing_table_descriptions")
    elif generate_mask.any():
        to_generate = preview.loc[
            generate_mask, ["Table", "Source View", "Column Context"]
        ].copy()
        generated = _ai_generate_response(
            to_generate,
            (
                "Write a concise business description of this Power BI table for report authors. "
                "Say what the table holds and what it is used for. "
                "1-2 sentences. Do not list the column names back. "
                "Do not mention Databricks, views, DAX, or Power BI internals. "
                "Every description must be unique and executive-friendly. "
                "Table name: {Table}. "
                "Source view name: {Source View}. "
                "Columns and their meanings: {Column Context}."
            ),
            progress_label=f"table descriptions ({len(to_generate)} mapped tables)",
        )
        preview.loc[generate_mask, "Desc"] = generated
        _mark_generated_description_source(preview, generate_mask, ~has_model_text)

    rows = [
        {
            "Table": r["Table"],
            "Desc": r["Desc"],
            **({"Force": True} if force_regenerate else {}),
        }
        for r in preview.to_dict("records")
        if _text(r["Desc"]) and r["Description Source"] != "Already in the model"
    ]
    return rows, preview


def discover_table_name_map(
    dataset_name: str,
    workspace_name: str,
    databricks_tables,
    overrides: dict = None,
    ignore_tables=None,
    model_sources: list = None,
) -> tuple:
    """
    Work out which Databricks view feeds each Power BI table.

    Two signals, strongest first:
      source   the table's own source query names the view, so this is certain
      name     the names reduce to the same words once warehouse prefixes go

    Returns (table_name_map, report_df). The map is keyed by Databricks view name
    with a list of Power BI tables, matching what the applier expects, and one
    view feeding several tables falls out naturally. Anything unmatched is listed
    in the report with a paste-ready override line.
    """
    candidates = {_key(t) for t in databricks_tables if _text(t)}
    canonical_lookup = {}
    for name in candidates:
        canonical_lookup.setdefault(_canonical_source_name(name), []).append(name)

    ignore = {_key(t) for t in (ignore_tables or []) if _text(t)}
    override_map = {}
    for dbr_name, pbi_tables in (overrides or {}).items():
        values = pbi_tables if isinstance(pbi_tables, (list, tuple, set)) else [pbi_tables]
        for pbi in values:
            if _text(pbi):
                override_map[_key(pbi)] = (_key(dbr_name), _text(pbi))

    if model_sources is None:
        model_sources = read_model_source_tables(dataset_name, workspace_name)

    records = []
    for entry in model_sources:
        pbi_name = _text(entry.get("Power BI Table"))
        pbi_key = _key(pbi_name)

        if pbi_key in ignore:
            records.append({"Power BI Table": pbi_name, "Databricks Table": "", "Matched By": "ignored"})
            continue

        if pbi_key in override_map:
            records.append(
                {
                    "Power BI Table": pbi_name,
                    "Databricks Table": override_map[pbi_key][0],
                    "Matched By": "override",
                }
            )
            continue

        hits = sorted(set(entry.get("Candidates") or set()) & candidates)
        if hits:
            for hit in hits:
                records.append(
                    {"Power BI Table": pbi_name, "Databricks Table": hit, "Matched By": "source"}
                )
            continue

        by_name = canonical_lookup.get(_canonical_source_name(pbi_name), [])
        if len(by_name) == 1:
            records.append(
                {"Power BI Table": pbi_name, "Databricks Table": by_name[0], "Matched By": "name"}
            )
        elif len(by_name) > 1:
            records.append(
                {
                    "Power BI Table": pbi_name,
                    "Databricks Table": "",
                    "Matched By": f"ambiguous: {', '.join(sorted(by_name))}",
                }
            )
        else:
            records.append(
                {
                    "Power BI Table": pbi_name,
                    "Databricks Table": "",
                    "Matched By": "no source found",
                }
            )

    report = pd.DataFrame(records)

    table_map = {}
    for record in records:
        dbr = _key(record["Databricks Table"])
        if not dbr or record["Matched By"].startswith("ambiguous"):
            continue
        table_map.setdefault(dbr, [])
        if record["Power BI Table"] not in table_map[dbr]:
            table_map[dbr].append(record["Power BI Table"])

    return table_map, report


def discover_column_renames(
    dataset_name: str,
    workspace_name: str,
    table_name_map: dict,
    comments_df: pd.DataFrame,
    overrides: dict = None,
) -> tuple:
    """
    Fill in COLUMN_NAME_MAP automatically.

    A Databricks column only needs an entry when the Power BI name differs. Case
    and punctuation differences (INVENTORY_ITEM_ID vs InventoryItem_ID) are matched
    here so nobody types them out; genuinely renamed columns are reported instead.

    Returns (column_name_map, report_df).
    """
    comments = _normalize_comment_columns(comments_df)
    wanted = {}
    for dbr_table, pbi_tables in (table_name_map or {}).items():
        wanted[_key(dbr_table)] = [_text(t) for t in pbi_tables]

    with connect_semantic_model(
        dataset=dataset_name, workspace=workspace_name, readonly=True
    ) as tom:
        model_columns = {
            _key(t.Name): {_key(c.Name): _text(c.Name) for c in t.Columns}
            for t in tom.model.Tables
        }

    column_map = {}
    for dbr_table, cols in (overrides or {}).items():
        column_map.setdefault(_key(dbr_table), {})
        for dbr_col, pbi_col in (cols or {}).items():
            column_map[_key(dbr_table)][_key(dbr_col)] = _text(pbi_col)

    records = []
    seen = set()
    for row in comments.to_dict("records"):
        dbr_table = _key(row["databricks_table"])
        dbr_column = _text(row["column_name"])
        if dbr_table not in wanted or not dbr_column:
            continue

        for pbi_table in wanted[dbr_table]:
            key = (dbr_table, _key(dbr_column), _key(pbi_table))
            if key in seen:
                continue
            seen.add(key)

            columns = model_columns.get(_key(pbi_table), {})
            if column_map.get(dbr_table, {}).get(_key(dbr_column)):
                matched_by = "override"
            elif _key(dbr_column) in columns:
                matched_by = "exact"
            else:
                squashed = {
                    re.sub(r"[^a-z0-9]+", "", k): v for k, v in columns.items()
                }
                target = squashed.get(re.sub(r"[^a-z0-9]+", "", _key(dbr_column)))
                if target:
                    column_map.setdefault(dbr_table, {})[_key(dbr_column)] = target
                    matched_by = "renamed"
                else:
                    matched_by = "not in model"

            records.append(
                {
                    "Databricks Table": dbr_table,
                    "Databricks Column": dbr_column,
                    "Power BI Table": pbi_table,
                    "Matched By": matched_by,
                }
            )

    return column_map, pd.DataFrame(records)


def build_table_description_rows(
    dataset_name: str,
    workspace_name: str,
    skip_tables=None,
    generate_descriptions="yes",
    force_regenerate_descriptions="no",
    include_hidden: bool = False,
    announce_skip: bool = True,
    existing_descriptions: Optional[dict] = None,
) -> tuple:
    """
    Describe only the tables Databricks does not describe, so TABLE_ROWS stops being manual.

    skip_tables are the ones whose view carries a table comment; that comment is used
    instead. Whatever is left is a calculated table, a model-only table, or a view
    with no table comment, and gets described from its own name and column list.
    """
    generate_descriptions = _yes_no(generate_descriptions, "generate_descriptions")
    force_regenerate_descriptions = _yes_no(
        force_regenerate_descriptions, "force_regenerate_descriptions"
    )
    generate_descriptions = generate_descriptions or force_regenerate_descriptions

    skip = {_key(t) for t in (skip_tables or []) if _text(t)}
    records = []
    with connect_semantic_model(
        dataset=dataset_name, workspace=workspace_name, readonly=True
    ) as tom:
        for table in tom.model.Tables:
            if _key(table.Name) in skip:
                continue
            if not include_hidden and bool(getattr(table, "IsHidden", False)):
                continue

            columns = [_text(c.Name) for c in table.Columns][:25]
            measures = [_text(m.Name) for m in table.Measures][:25]
            records.append(
                {
                    "Table": _text(table.Name),
                    "Desc": _text(getattr(table, "Description", "")),
                    "Column List": ", ".join(columns),
                    "Measure List": ", ".join(measures),
                }
            )

    result = pd.DataFrame(records)
    if result.empty:
        return [], result

    _apply_snapshot_originals(result, existing_descriptions, "table", "Table", "Table")
    blank_mask = _blank_text_mask(result["Desc"])
    result["Description Source"] = "Missing, not generated"
    result.loc[~blank_mask, "Description Source"] = "Already exists"

    if not generate_descriptions:
        if announce_skip:
            _log_skip_ai_descriptions("table", "generate_missing_table_descriptions")
        target_mask = pd.Series(False, index=result.index)
    elif force_regenerate_descriptions:
        target_mask = pd.Series(True, index=result.index)
    else:
        target_mask = blank_mask

    if target_mask.any():
        to_generate = result.loc[
            target_mask, ["Table", "Column List", "Measure List"]
        ].copy()
        generated = _ai_generate_response(
            to_generate,
            (
                "Write a concise business description of this Power BI table for report authors. "
                "Say what the table holds and what it is used for. "
                "1-2 sentences. Do not list the column names back. "
                "Do not mention DAX or Power BI internals. "
                "Every description must be unique and executive-friendly. "
                "Table name: {Table}. "
                "Columns: {Column List}. "
                "Measures: {Measure List}."
            ),
            progress_label=f"table descriptions ({len(to_generate)} model-only tables)",
        )
        result.loc[target_mask, "Desc"] = generated
        _mark_generated_description_source(result, target_mask, blank_mask)

    # Only rows this function actually wrote text for. Tables that already had a
    # description are left out so they do not clutter the preview or the blocks.
    rows = [
        {
            "Table": r["Table"],
            "Desc": r["Desc"],
            **({"Force": True} if r["Description Source"] == "Regenerated" else {}),
        }
        for r in result.to_dict("records")
        if _text(r["Desc"]) and r["Description Source"] in ("Generated now", "Regenerated")
    ]
    return rows, result


# =========================
# One plan object for the whole run
# =========================


class DocumentationPlan:
    """
    Everything the run needs, built once so editing by hand never re-runs the AI.

    build_documentation_plan() does the expensive work: it reads the model, maps it
    to Databricks, and generates the missing descriptions and synonyms. After that,
    set_manual() / print_blocks() / apply() are cheap and can be re-run freely while
    wording is polished.
    """

    def __init__(
        self,
        dataset_name: str,
        workspace_name: str,
        comments: pd.DataFrame,
        table_name_map: dict,
        column_name_map: dict,
        table_report: pd.DataFrame,
        column_report: pd.DataFrame,
        table_rows: list,
        table_preview: pd.DataFrame,
        calculated_column_rows: list,
        calculated_column_preview: pd.DataFrame,
        measure_rows: list,
        measure_preview: pd.DataFrame,
        mapped_column_synonyms: dict,
        synonym_registry: SynonymRegistry,
        settings: dict,
    ):
        self.dataset_name = dataset_name
        self.workspace_name = workspace_name
        self.comments = comments
        self.table_name_map = table_name_map
        self.column_name_map = column_name_map
        self.table_report = table_report
        self.column_report = column_report

        self.generated_table_rows = table_rows
        self.generated_calculated_column_rows = calculated_column_rows
        self.generated_measure_rows = measure_rows

        self.table_preview = table_preview
        self.calculated_column_preview = calculated_column_preview
        self.measure_preview = measure_preview
        self.mapped_column_synonyms = mapped_column_synonyms
        self.synonym_registry = synonym_registry
        self.settings = settings

        self.manual_table_rows = []
        self.manual_calculated_column_rows = []
        self.manual_measure_rows = []

    # ---------- manual edits ----------

    def set_manual(
        self,
        calculated_column_rows=None,
        measure_rows=None,
        table_rows=None,
        quiet: bool = False,
    ) -> "DocumentationPlan":
        """Attach hand-edited rows. Safe to re-run; it never regenerates anything."""
        self.manual_calculated_column_rows = list(calculated_column_rows or [])
        self.manual_measure_rows = list(measure_rows or [])
        self.manual_table_rows = list(table_rows or [])

        if not quiet:
            summarize_manual_overrides(self.calculated_column_rows, "Calculated columns")
            summarize_manual_overrides(self.measure_rows, "Measures")
        return self

    @property
    def calculated_column_rows(self) -> list:
        return merge_manual_rows(
            self.generated_calculated_column_rows, self.manual_calculated_column_rows
        )

    @property
    def measure_rows(self) -> list:
        return merge_manual_rows(self.generated_measure_rows, self.manual_measure_rows)

    @property
    def table_rows(self) -> list:
        # Table rows have no column, but the merge keys on one, so stand in a
        # placeholder and drop it again afterwards.
        placeholder = "(table)"
        merged = merge_manual_rows(
            [dict(r, Column=placeholder) for r in self.generated_table_rows],
            [dict(r, Column=placeholder) for r in self.manual_table_rows],
        )
        return [{k: v for k, v in row.items() if k != "Column"} for row in merged]

    # ---------- reporting ----------

    def print_report(self) -> None:
        """Count-only mapping and generation recap. Object names stay in preview()."""
        report = self.table_report
        print("=== Mapping recap ===")
        if report is None or report.empty:
            print("  No tables found in the model.")
            return

        mapped = int(report["Databricks Table"].ne("").sum())
        unmatched = report[report["Databricks Table"].eq("")]
        unmatched = unmatched[~unmatched["Matched By"].eq("ignored")]
        print(
            f"  Power BI tables: {len(report)} | mapped to Databricks: {mapped} | "
            f"no Databricks source: {len(unmatched)}"
        )

        col_report = self.column_report
        if col_report is not None and not col_report.empty:
            renamed = col_report[col_report["Matched By"].eq("renamed")]
            missing = col_report[col_report["Matched By"].eq("not in model")]
            print(
                f"  Columns: {len(col_report)} Databricks comments matched | "
                f"{len(renamed)} renamed | {len(missing)} not in the model"
            )

        print("  Descriptions:")
        for label, preview in [
            ("tables", self.table_preview),
            ("columns", self.calculated_column_preview),
            ("measures", self.measure_preview),
        ]:
            if preview is None or preview.empty:
                print(f"    {label}: none")
                continue
            bits = []
            for val, n in preview["Description Source"].value_counts().items():
                bits.append(f"{_source_label(val)} {int(n)}")
            extra = ""
            if "Synonym Source" in preview.columns:
                syn_n = int(
                    preview["Synonym Source"].isin(["Generated now", "Regenerated"]).sum()
                )
                extra = f" | synonyms generated {syn_n}"
            print(f"    {label}: {len(preview)} | {', '.join(bits)}{extra}")

        registry = self.synonym_registry
        if registry is not None and registry.enabled and registry.dropped_count:
            print(
                f"  Synonym uniqueness: {registry.dropped_count} duplicate phrase(s) dropped."
            )

    def synonym_conflicts(self) -> pd.DataFrame:
        """Every phrase two objects both wanted, and which one kept it."""
        if self.synonym_registry is None:
            return pd.DataFrame()
        return self.synonym_registry.conflicts_frame()

    def print_blocks(self, shape: str = "full", **filters) -> dict:
        """Print paste-ready MANUAL_* blocks for the current state of the plan."""
        return print_manual_blocks(
            calculated_column_rows=self.calculated_column_rows,
            measure_rows=self.measure_rows,
            shape=shape,
            **filters,
        )

    def preview(self) -> None:
        """Display the working tables, including what each row will write."""
        for label, frame in [
            ("Tables", self.table_preview),
            ("Calculated columns", self.calculated_column_preview),
            ("Measures", self.measure_preview),
        ]:
            if frame is not None and not frame.empty:
                print(f"\n{label}")
                display(frame)  # noqa: F821

        display(build_synonym_preview(self.calculated_column_rows, "Column"))  # noqa: F821
        display(build_synonym_preview(self.measure_rows, "Measure"))  # noqa: F821

    # ---------- write back ----------

    def apply(
        self,
        overwrite_tables=None,
        overwrite_columns=None,
        overwrite_measures=None,
        overwrite_column_synonyms=None,
        overwrite_measure_synonyms=None,
        apply_changes: bool = False,
        **applier_kwargs,
    ) -> dict:
        """Write the plan to the model. Dry-run unless apply_changes=True."""
        settings = dict(self.settings)
        settings.update(applier_kwargs)

        applier = SemanticModelDescriptionApplier(
            dataset_name=self.dataset_name,
            workspace_name=self.workspace_name,
            databricks_comments=self.comments,
            table_name_map=self.table_name_map,
            column_name_map=self.column_name_map,
            overwrite_tables=overwrite_tables,
            overwrite_columns=overwrite_columns,
            overwrite_measures=overwrite_measures,
            overwrite_column_synonyms=overwrite_column_synonyms,
            overwrite_measure_synonyms=overwrite_measure_synonyms,
            calculated_table_descriptions=self.table_rows,
            calculated_column_descriptions=self.calculated_column_rows,
            measure_descriptions=self.measure_rows,
            generate_mapped_column_synonyms=settings.get(
                "generate_mapped_column_synonyms",
                settings.get("generate_column_synonyms", "yes"),
            ),
            mapped_column_synonyms=self.mapped_column_synonyms,
            synonym_registry=self.synonym_registry,
            apply_descriptions=settings.get("apply_descriptions", "yes"),
            apply_synonyms=settings.get("apply_synonyms", "yes"),
            synonym_culture=settings.get("synonym_culture", "en-US"),
        )
        return applier.apply(apply_changes=apply_changes)


def build_documentation_plan(
    dataset_name: str,
    workspace_name: str,
    databricks_server_hostname: str = None,
    databricks_http_path: str = None,
    databricks_access_token: str = None,
    databricks_comments=None,
    catalog_pattern: str = "%mde%",
    schemas=("gold", "platinum"),
    table_name_map: dict = None,
    auto_discover_tables="yes",
    ignore_tables=None,
    column_rename_overrides: dict = None,
    generate_table_descriptions=None,
    generate_missing_table_descriptions=None,
    regenerate_table_descriptions="no",
    column_scope: str = "all",
    generate_column_descriptions=None,
    generate_missing_column_descriptions=None,
    regenerate_column_descriptions="no",
    generate_table_synonyms="yes",
    generate_column_synonyms="yes",
    regenerate_column_synonyms="no",
    generate_measure_descriptions=None,
    generate_missing_measure_descriptions=None,
    regenerate_measure_descriptions="no",
    generate_measure_synonyms="yes",
    regenerate_measure_synonyms="no",
    generate_mapped_column_synonyms=None,
    unique_synonyms="yes",
    apply_descriptions="yes",
    apply_synonyms="yes",
    synonym_culture: str = "en-US",
    include_hidden_columns: bool = False,
    show_report: bool = True,
    existing_descriptions: Optional[dict] = None,
) -> DocumentationPlan:
    """
    Do the whole discovery and generation pass in one call.

    Nothing is written to the model here, so this is safe to run and review.

      1 list the view names in scope, names only, no column data
      2 match Power BI tables to Databricks views using their source queries
      3 load column comments for those matched views only, never the whole catalog
      4 match columns, ignoring case and punctuation differences
      5 Databricks first: its table and column comments are the source of truth
      6 then fill the gaps, so any table, column or measure still without a
        description gets one written in Fabric
      7 build synonyms for anything that has none

    column_scope="all" (the default) means step 6 covers every column the warehouse
    did not describe. Use "calculated" to restrict it to DAX calculated columns.

    table_name_map entries always win. Leave it empty to let step 2 work the mapping
    out, or set auto_discover_tables="no" to use only what you listed, which is the
    filtered behaviour of the earlier notebook.

    AI descriptions for objects Databricks did not comment (all default True):
      generate_missing_table_descriptions   mapped tables missing UC comments
                                            and model-only / unmapped tables
      generate_missing_column_descriptions  calculated columns and unmapped /
                                            source columns
      generate_missing_measure_descriptions measures with blank descriptions
    generate_*_descriptions remains accepted as an alias. Databricks comments
    still apply when a flag is False.

    AI synonym switches (all default True; independent of description flags):
      generate_table_synonyms    3-5 unique synonyms per table
      generate_column_synonyms   5-10 per column (calculated, unmapped/source,
                                 and Databricks-mapped). Also drives mapped
                                 column synonyms unless generate_mapped_column_synonyms
                                 is passed explicitly.
      generate_measure_synonyms  ≥10 per measure
    """
    _reset_step3_synonym_logs()
    auto_discover = _yes_no(auto_discover_tables, "auto_discover_tables")
    generate_table_descriptions = _coalesce_yes_no(
        generate_missing_table_descriptions,
        generate_table_descriptions,
        True,
        "generate_missing_table_descriptions",
    )
    generate_column_descriptions = _coalesce_yes_no(
        generate_missing_column_descriptions,
        generate_column_descriptions,
        True,
        "generate_missing_column_descriptions",
    )
    generate_measure_descriptions = _coalesce_yes_no(
        generate_missing_measure_descriptions,
        generate_measure_descriptions,
        True,
        "generate_missing_measure_descriptions",
    )
    want_table_synonyms = _yes_no(generate_table_synonyms, "generate_table_synonyms")
    want_column_synonyms = _yes_no(generate_column_synonyms, "generate_column_synonyms")
    want_measure_synonyms = _yes_no(generate_measure_synonyms, "generate_measure_synonyms")
    if generate_mapped_column_synonyms is None:
        want_mapped_column_synonyms = want_column_synonyms
    else:
        want_mapped_column_synonyms = _yes_no(
            generate_mapped_column_synonyms, "generate_mapped_column_synonyms"
        )
    declared_map = SemanticModelDescriptionApplier._normalize_table_name_map(
        table_name_map or {}
    )

    have_credentials = all(
        [databricks_server_hostname, databricks_http_path, databricks_access_token]
    )
    if databricks_comments is None and not have_credentials:
        raise ValueError(
            "Provide databricks_comments, or all of databricks_server_hostname, "
            "databricks_http_path and databricks_access_token."
        )

    # Step 1 and 2: settle the table list before asking for any column data.
    catalog_df = None
    comments = None
    mapped_query_used = False
    if not auto_discover:
        if not declared_map:
            raise ValueError(
                "auto_discover_tables is 'no', so table_name_map must list the "
                "Databricks views to document."
            )
        resolved_map = declared_map
        table_report = pd.DataFrame(
            [
                {"Power BI Table": pbi, "Databricks Table": dbr, "Matched By": "declared"}
                for dbr, pbi_tables in declared_map.items()
                for pbi in pbi_tables
            ]
        )

        # The map is already definitive, so one query serves both column and table
        # comments and nothing else is read.
        mapped_query_used = True
        if databricks_comments is None:
            comments = load_databricks_metadata(
                table_name_map=declared_map,
                server_hostname=databricks_server_hostname,
                http_path=databricks_http_path,
                access_token=databricks_access_token,
                catalog_pattern=catalog_pattern,
                schemas=schemas,
            )
    else:
        # Read the model first so the catalog listing can be filtered to the view
        # names the model actually mentions, the same discipline as the column query.
        model_sources = read_model_source_tables(dataset_name, workspace_name)
        wanted_names = set(declared_map)
        for entry in model_sources:
            wanted_names |= entry["Candidates"]

        if not wanted_names:
            print(
                "Step 1 — Databricks: no mapped tables and no source queries named a "
                "Unity Catalog table, so comments were not loaded. Descriptions and "
                "synonyms will come from the model and Fabric AI only."
            )
            resolved_map = {}
            table_report = pd.DataFrame(
                [
                    {
                        "Power BI Table": e["Power BI Table"],
                        "Databricks Table": "",
                        "Matched By": "no source found",
                    }
                    for e in model_sources
                ]
            )
            databricks_comments = _empty_comments_frame()
        else:
            if databricks_comments is not None:
                available = _normalize_comment_columns(databricks_comments)[
                    "databricks_table"
                ].unique().tolist()
            else:
                catalog_df = load_databricks_table_catalog(
                    server_hostname=databricks_server_hostname,
                    http_path=databricks_http_path,
                    access_token=databricks_access_token,
                    catalog_pattern=catalog_pattern,
                    schemas=schemas,
                    table_names=sorted(wanted_names),
                )
                available = catalog_df["databricks_table"].tolist()

            # Declared views count as available even if the listing missed them.
            available = list({_key(t) for t in available} | set(declared_map))

            resolved_map, table_report = discover_table_name_map(
                dataset_name=dataset_name,
                workspace_name=workspace_name,
                databricks_tables=available,
                overrides=table_name_map,
                ignore_tables=ignore_tables,
                model_sources=model_sources,
            )

    # Step 3: column comments for those views only.
    if comments is not None:
        pass
    elif not resolved_map:
        print(
            "Step 1 — Databricks: no Power BI tables mapped, so no comments were loaded."
        )
        comments = _empty_comments_frame()
    elif databricks_comments is None:
        comments = load_databricks_comments(
            server_hostname=databricks_server_hostname,
            http_path=databricks_http_path,
            access_token=databricks_access_token,
            catalog_pattern=catalog_pattern,
            schemas=schemas,
            table_names=list(resolved_map),
        )
    else:
        comments = _normalize_comment_columns(databricks_comments)
        wanted = set(resolved_map)
        comments = comments[
            comments["databricks_table"].map(lambda v: _key(v) in wanted)
        ].copy()

    table_name_map = resolved_map

    column_name_map, column_report = discover_column_renames(
        dataset_name=dataset_name,
        workspace_name=workspace_name,
        table_name_map=table_name_map,
        comments_df=comments,
        overrides=column_rename_overrides,
    )

    n_mapped_pbi = len({pbi for pbis in resolved_map.values() for pbi in pbis})
    n_comment_cols = 0 if comments is None or comments.empty else len(comments)
    print(
        f"Step 1 — Mapping: {n_mapped_pbi} Power BI tables mapped; "
        f"{n_comment_cols} columns already described from Databricks."
    )

    # Table comments come from the tables catalog rather than the column rows. The
    # column query only returns commented columns, so a view that documents its table
    # but not its columns would otherwise look undescribed and get AI text.
    if not resolved_map:
        table_comments = pd.DataFrame(columns=["databricks_table", "table_description"])
    elif catalog_df is not None:
        table_comments = catalog_df[["databricks_table", "table_description"]].copy()
    elif databricks_comments is None and not mapped_query_used:
        table_comments = load_databricks_table_catalog(
            server_hostname=databricks_server_hostname,
            http_path=databricks_http_path,
            access_token=databricks_access_token,
            catalog_pattern=catalog_pattern,
            schemas=schemas,
            table_names=list(resolved_map),
        )[["databricks_table", "table_description"]].copy()
    else:
        table_comments = comments[["databricks_table", "table_description"]].copy()
    table_comments = table_comments.drop_duplicates()

    # Every mapped table gets the view's table comment, or AI text when the query has
    # none, exactly as a column takes its comment or nothing. Tables the model already
    # describes are left alone, so a second run does not pay for them again.
    regenerate_tables = _yes_no(
        regenerate_table_descriptions, "regenerate_table_descriptions"
    )
    print(
        "Step 2 — Descriptions: generating AI text for objects with no Databricks comment."
    )
    if not (generate_table_descriptions or regenerate_tables):
        _log_skip_ai_descriptions("table", "generate_missing_table_descriptions")
    table_existing = _table_originals_from_snapshot(existing_descriptions)
    if table_existing is None:
        table_existing = read_model_table_descriptions(dataset_name, workspace_name)
    databricks_table_rows, mapped_table_preview = build_mapped_table_description_rows(
        table_name_map=resolved_map,
        comments_df=comments,
        table_comments=table_comments,
        generate_missing=generate_table_descriptions,
        force_regenerate=regenerate_table_descriptions,
        existing_descriptions=table_existing,
        announce_skip=False,
    )

    # Mapped tables are settled above, so the model-only pass never revisits them.
    described_by_databricks = {pbi for pbis in resolved_map.values() for pbi in pbis}

    # One registry for the whole run, seeded with what the model already has, so no
    # two objects end up sharing a synonym.
    registry = SynonymRegistry(unique_synonyms)
    registry.seed_from_model(
        load_existing_synonyms_map(dataset_name, workspace_name, culture=synonym_culture)
    )

    generated_table_rows, table_preview = build_table_description_rows(
        dataset_name=dataset_name,
        workspace_name=workspace_name,
        skip_tables=described_by_databricks,
        generate_descriptions=generate_table_descriptions,
        force_regenerate_descriptions=regenerate_table_descriptions,
        announce_skip=False,
        existing_descriptions=existing_descriptions,
    )
    table_rows = databricks_table_rows + generated_table_rows

    if mapped_table_preview is not None and not mapped_table_preview.empty:
        table_preview = pd.concat(
            [
                mapped_table_preview[["Table", "Desc", "Description Source"]],
                table_preview,
            ],
            ignore_index=True,
        )
        from_databricks = int(
            (mapped_table_preview["Description Source"] == "From Databricks").sum()
        )
    else:
        from_databricks = 0

    already_in_model = 0
    if mapped_table_preview is not None and not mapped_table_preview.empty:
        already_in_model = int(
            (mapped_table_preview["Description Source"] == "Already in the model").sum()
        )
    print(
        f"Step 2 — Descriptions: tables — {from_databricks} from Databricks, "
        f"{len(databricks_table_rows) - from_databricks} generated (mapped), "
        f"{already_in_model} already in the model, "
        f"{len(generated_table_rows)} generated (model-only)."
    )

    # Columns the Databricks pass will describe. Everything else is fair game for AI,
    # so the warehouse always wins and the AI only fills what it leaves behind.
    covered_columns = set()
    for row in comments.to_dict("records"):
        view = _key(row.get("databricks_table"))
        source_column = _text(row.get("column_name"))
        if not source_column or not _text(row.get("column_description")):
            continue
        pbi_column = column_name_map.get(view, {}).get(_key(source_column), source_column)
        for pbi_table in resolved_map.get(view, []):
            covered_columns.add((_key(pbi_table), _key(pbi_column)))

    calculated_column_rows, calculated_column_preview = build_column_description_rows(
        dataset_name=dataset_name,
        workspace_name=workspace_name,
        include_hidden=include_hidden_columns,
        column_scope=column_scope,
        skip_columns=covered_columns,
        generate_descriptions=generate_column_descriptions,
        force_regenerate_descriptions=regenerate_column_descriptions,
        generate_synonyms=want_column_synonyms,
        force_regenerate_synonyms=regenerate_column_synonyms,
        synonym_culture=synonym_culture,
        synonym_registry=registry,
        existing_descriptions=existing_descriptions,
        pending_step2_measure_skip=not generate_measure_descriptions,
    )

    measure_preview = build_measure_catalog(
        dataset_name=dataset_name,
        workspace_name=workspace_name,
        generate_descriptions=generate_measure_descriptions,
        force_regenerate_descriptions=regenerate_measure_descriptions,
        generate_synonyms=want_measure_synonyms,
        force_regenerate_synonyms=regenerate_measure_synonyms,
        synonym_culture=synonym_culture,
        synonym_registry=registry,
        existing_descriptions=existing_descriptions,
        announce_skip=generate_measure_descriptions,
    )
    measure_rows = measure_rows_from_catalog(measure_preview)

    # Synonyms for the Databricks-mapped columns are generated here rather than at
    # apply time, so polishing wording and re-applying never re-runs the AI.
    # Driven by generate_column_synonyms unless generate_mapped_column_synonyms is set.
    # Do not gate on apply_synonyms: preview Proposed Synonyms must be filled even
    # when the later apply step is description-only.
    mapped_column_synonyms = {}
    if not want_mapped_column_synonyms:
        if want_column_synonyms:
            _log_skip_ai_synonyms("mapped column", "generate_mapped_column_synonyms")
    else:
        scout = SemanticModelDescriptionApplier(
            dataset_name=dataset_name,
            workspace_name=workspace_name,
            databricks_comments=comments,
            table_name_map=table_name_map,
            column_name_map=column_name_map,
            synonym_culture=synonym_culture,
            synonym_registry=registry,
        )
        mapped_column_synonyms = scout._generate_mapped_column_synonyms(
            comments,
            load_existing_synonyms_map(
                dataset_name, workspace_name, culture=synonym_culture
            ),
        ) or {}

    if want_column_synonyms:
        n_col_syn = _count_filled_generated_synonyms(calculated_column_preview)
        n_col_syn += sum(1 for syns in mapped_column_synonyms.values() if _synonym_list_filled(syns))
        _log_generated_ai_synonyms(
            "column",
            n_col_syn,
            "5–10 each; calculated + unmapped + Databricks-mapped",
        )

    table_rows = _apply_table_synonyms(
        table_rows, registry, generate=want_table_synonyms
    )

    plan = DocumentationPlan(
        dataset_name=dataset_name,
        workspace_name=workspace_name,
        comments=comments,
        table_name_map=table_name_map,
        column_name_map=column_name_map,
        table_report=table_report,
        column_report=column_report,
        table_rows=table_rows,
        table_preview=table_preview,
        calculated_column_rows=calculated_column_rows,
        calculated_column_preview=calculated_column_preview,
        measure_rows=measure_rows,
        measure_preview=measure_preview,
        mapped_column_synonyms=mapped_column_synonyms,
        synonym_registry=registry,
        settings={
            "generate_missing_table_descriptions": generate_table_descriptions,
            "generate_missing_column_descriptions": generate_column_descriptions,
            "generate_missing_measure_descriptions": generate_measure_descriptions,
            "generate_table_synonyms": want_table_synonyms,
            "generate_column_synonyms": want_column_synonyms,
            "generate_measure_synonyms": want_measure_synonyms,
            "generate_mapped_column_synonyms": want_mapped_column_synonyms,
            "apply_descriptions": apply_descriptions,
            "apply_synonyms": apply_synonyms,
            "synonym_culture": synonym_culture,
        },
    )

    if show_report:
        plan.print_report()
    return plan


# =========================
# TABLE_MAPPING (Power BI -> Databricks) and session engine
# =========================

PREVIEW_COLUMNS = (
    "Object Type",
    "Table Name",
    "Object Name",
    "Source (Databricks vs AI)",
    "Original Description",
    "Proposed Description",
    "Synonym Existed",
    "Existing Synonyms",
    "Proposed Synonyms",
)

PREVIEW_OBJECT_TYPES = ("tables", "columns", "measures")
_PREVIEW_OBJECT_TYPE_ALIASES = {
    "table": "table",
    "tables": "table",
    "column": "column",
    "columns": "column",
    "measure": "measure",
    "measures": "measure",
}


def _normalize_preview_object_type(value) -> Optional[str]:
    """One preview 'Object Type' cell or filter alias → table | column | measure.

    Accepts Table/Column/Measure (title case from _put), table/column/measure,
    and tables/columns/measures. Blank or unknown → None (does not raise).

    Sanity: Measure/measures/measure → measure; Column/columns → column;
    Table/tables → table. Used by both preview() and filter_preview_for_update.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return _PREVIEW_OBJECT_TYPE_ALIASES.get(_key(value)) or None


def _preview_object_type_alias_sanity() -> None:
    """Tiny check that title-case preview labels and plural filters share one key."""
    pairs = (
        ("Measure", "measures", "measure"),
        ("Column", "columns", "column"),
        ("Table", "tables", "table"),
    )
    for titled, plural, want in pairs:
        assert _normalize_preview_object_type(titled) == want
        assert _normalize_preview_object_type(plural) == want
        assert _normalize_preview_object_type(want) == want


_preview_object_type_alias_sanity()


def _normalize_preview_object_types(
    object_types: Optional[Union[str, Iterable[str]]],
) -> Optional[set]:
    """Canonical kinds for preview(); None means all types."""
    if object_types is None:
        return None
    if isinstance(object_types, str):
        items = [object_types]
    elif isinstance(object_types, (list, tuple)):
        items = list(object_types)
    else:
        raise ValueError(
            "object_types must be a string or a list/tuple of "
            f"{list(PREVIEW_OBJECT_TYPES)}, got {type(object_types).__name__}"
        )
    kinds = set()
    for raw in items:
        mapped = _normalize_preview_object_type(raw)
        if mapped is None:
            raise ValueError(
                f"Invalid object type {raw!r}. Allowed: "
                f"{', '.join(PREVIEW_OBJECT_TYPES)} "
                "(aliases: table, column, measure)."
            )
        kinds.add(mapped)
    return kinds


_SOURCE_COUNT_ORDER = (
    "Databricks",
    "AI",
    "Existing",
    "Missing",
    "Manual",
    "Cleared",
    "Cleared for description",
    "Cleared for synonyms",
)


def _source_counts(frame: pd.DataFrame) -> dict:
    """Counts by preview Source label. Always includes Missing (0 when none)."""
    counts = {name: 0 for name in _SOURCE_COUNT_ORDER}
    if frame is not None and not frame.empty and "Source (Databricks vs AI)" in frame.columns:
        for val, n in frame["Source (Databricks vs AI)"].fillna("Missing").value_counts().items():
            label = val if val in counts else _source_label(val)
            counts[label] = counts.get(label, 0) + int(n)
    return counts


def _preview_counts_line(frame: pd.DataFrame) -> str:
    counts = {"table": 0, "column": 0, "measure": 0}
    if frame is not None and not frame.empty and "Object Type" in frame.columns:
        for val, n in frame["Object Type"].map(_normalize_preview_object_type).value_counts().items():
            if val in counts:
                counts[val] = int(n)
    line = (
        f"Preview: {counts['table']} table(s), "
        f"{counts['column']} column(s), "
        f"{counts['measure']} measure(s)"
    )
    sources = _source_counts(frame)
    source_bits = [
        f"{name} {n}" for name, n in sources.items() if n or name == "Missing"
    ]
    if source_bits:
        line += " | " + ", ".join(source_bits)
    return line

_SESSION_ENGINE = None


def invert_table_mapping(table_mapping: Optional[dict]) -> dict:
    """
    Convert developer TABLE_MAPPING (Power BI table -> Databricks table(s))
    into the existing table_name_map shape (Databricks table -> [Power BI tables]).
    """
    inverted: dict = {}
    for pbi, dbr in (table_mapping or {}).items():
        pbi_name = str(pbi or "").strip()
        if not pbi_name:
            logger.warning("Skipping TABLE_MAPPING entry with a blank Power BI table name: %r", pbi)
            continue
        values = dbr if isinstance(dbr, (list, tuple, set)) else [dbr]
        named = [str(v).strip() for v in values if v and str(v).strip()]
        if not named:
            logger.warning("TABLE_MAPPING[%r] has no Databricks table name.", pbi_name)
            continue
        for view in named:
            inverted.setdefault(view, [])
            if pbi_name not in inverted[view]:
                inverted[view].append(pbi_name)
    return inverted


def unique_databricks_table_names(
    table_mapping: Optional[dict] = None,
    table_name_map: Optional[dict] = None,
) -> list:
    """All unique Databricks table names referenced by either mapping orientation."""
    names = set()
    for value in (table_mapping or {}).values():
        values = value if isinstance(value, (list, tuple, set)) else [value]
        names.update(str(v).rsplit(".", 1)[-1].strip() for v in values if v and str(v).strip())
    for key in (table_name_map or {}):
        if key and str(key).strip():
            names.add(str(key).rsplit(".", 1)[-1].strip())
    return sorted({n for n in names if n})


def build_table_name_filter(
    table_mapping: Optional[dict] = None,
    table_name_map: Optional[dict] = None,
) -> str:
    """SQL-safe quoted list for WHERE t.table_name IN (...)."""
    names = unique_databricks_table_names(table_mapping, table_name_map)
    if not names:
        raise ValueError(
            "No Databricks table names found. Provide TABLE_MAPPING "
            "(Power BI -> Databricks) or TABLE_NAME_MAP (Databricks -> Power BI)."
        )
    return ",\n".join(f"'{name}'" for name in names)


def build_databricks_metadata_sql(
    table_mapping: Optional[dict] = None,
    table_name_map: Optional[dict] = None,
    catalog_pattern: str = "%mde_dev%",
    schemas: Iterable[str] = ("gold", "platinum"),
) -> str:
    """Golden-comments query filtered to the mapped Databricks tables.

    Reads ``main.governance.metadata_comments_golden`` (view names union source
    table names). ``catalog_pattern`` is unused — the source is catalog-qualified.
    """
    table_name_filter = build_table_name_filter(table_mapping, table_name_map)
    schema_list = ", ".join(f"'{_text(s)}'" for s in schemas if _text(s))
    return f"""
select * from
        (
            select
                c.source_schema as table_schema,
                c.view_table as databricks_table_name,
                c.view_column as column_name,
                c.approved_comment as column_description,
                t.approved_comment as table_description
            from main.governance.metadata_comments_golden c
            left join main.governance.metadata_comments_golden t
                on c.source_schema = t.source_schema
                and c.view_table = t.view_table
                and t.object_level = 'TABLE'
            where c.source_schema in ({schema_list})
            and c.object_level = 'COLUMN'
            and c.approved_comment is not null
            --and c.view_table like 'v_pbi_dim_accounthierarchy%'
            union all
            select
                c.source_schema as table_schema,
                c.source_table as databricks_table_name,
                c.source_column as column_name,
                c.approved_comment as column_description,
                t.approved_comment as table_description
            from main.governance.metadata_comments_golden c
            left join main.governance.metadata_comments_golden t
                on c.source_schema = t.source_schema
                and c.source_table = t.source_table
                and t.object_level = 'TABLE'
            where c.source_schema in ({schema_list})
            and c.object_level = 'COLUMN'
            and c.approved_comment is not null
            --and c.source_table like 'dim_accounthierarchy%'
        ) t
        where 1=1
        AND databricks_table_name IN ({table_name_filter})
"""


def load_databricks_credentials(
    key_vault_name: Optional[str] = None,
    hostname_secret: str = "databricks-server-hostname",
    http_path_secret: str = "databricks-http-path",
    token_secret: str = "databricks-access-token",
) -> tuple:
    """
    Resolve warehouse credentials without hardcoding secrets.

    Order: environment variables, then Fabric / Synapse Key Vault via notebookutils.
    Returns (hostname, http_path, token). Missing values are None.
    """
    hostname = (
        os.environ.get("DATABRICKS_SERVER_HOSTNAME")
        or os.environ.get("DATABRICKS_HOST")
        or ""
    ).strip() or None
    http_path = (os.environ.get("DATABRICKS_HTTP_PATH") or "").strip() or None
    token = (
        os.environ.get("DATABRICKS_ACCESS_TOKEN")
        or os.environ.get("DATABRICKS_TOKEN")
        or ""
    ).strip() or None

    vault = key_vault_name or os.environ.get("FABRIC_KEY_VAULT_NAME") or os.environ.get(
        "KEY_VAULT_NAME"
    )

    def _read_secret(secret_name: str) -> Optional[str]:
        if not vault or not secret_name:
            return None
        for getter in (
            lambda: __import__("notebookutils").credentials.getSecret(vault, secret_name),
            lambda: __import__("notebookutils").mssparkutils.credentials.getSecret(
                vault, secret_name
            ),
        ):
            try:
                value = getter()
                if value:
                    return str(value).strip()
            except Exception:
                continue
        return None

    hostname = hostname or _read_secret(hostname_secret)
    http_path = http_path or _read_secret(http_path_secret)
    token = token or _read_secret(token_secret)
    return hostname, http_path, token


def generate_table_synonyms(
    table_rows: list,
    registry: Optional[SynonymRegistry] = None,
) -> list:
    """Add 3-5 collision-free table synonyms onto TABLE_ROWS-shaped dicts."""
    rows = list(table_rows or [])
    if not rows:
        return rows
    work = pd.DataFrame(
        [
            {"Table": _text(r.get("Table")), "Desc": _text(r.get("Desc"))}
            for r in rows
        ]
    )
    if work.empty:
        return rows
    syn_lists = _generate_synonyms_with_quality_gate(
        work,
        prompt=TABLE_SYNONYM_PROMPT,
        retry_prompt=TABLE_SYNONYM_RETRY_PROMPT,
        name_cols=["Table"],
        registry=registry,
        owner_kind="table",
        owner_table_col="Table",
        owner_name_col="Table",
        min_count=MIN_TABLE_SYNONYMS,
        max_count=MAX_TABLE_SYNONYMS,
        progress_label=f"table synonyms ({len(work)} tables)",
        retry_label="table synonyms, unique-wording retry ({n} tables)",
    )
    for row, syns in zip(rows, syn_lists):
        existing = _parse_synonyms(row.get("Synonyms"), limit=None)
        row["Synonyms"] = _unique_keep_order(existing + list(syns or []))[:MAX_TABLE_SYNONYMS]
    return rows


def _source_label(raw) -> str:
    """Map internal Description Source values to preview labels.

    Databricks — Unity Catalog comment this run
    AI         — Fabric generated or regenerated this run
    Existing   — non-blank description already on the semantic model, left as-is
    Missing    — blank in the model and not generated this run
    Manual     — edited in proposed state
    Cleared    — proposed description and synonyms cleared, no rebuild yet
    Cleared for description — proposed description cleared; synonyms left as-is
    Cleared for synonyms    — proposed synonyms cleared; description left as-is
    """
    text = _text(raw)
    low = text.lower()
    if "databricks" in low or low == "from databricks":
        return "Databricks"
    if low in {"generated now", "regenerated", "generated", "ai"}:
        return "AI"
    if low in {"manual", "edited"}:
        return "Manual"
    if low in {"cleared for description", "cleared description"}:
        return "Cleared for description"
    if low in {"cleared for synonyms", "cleared synonyms"}:
        return "Cleared for synonyms"
    if low in {"cleared"}:
        return "Cleared"
    if low in {"missing, not generated", "missing", "skipped"}:
        return "Missing"
    if low in {"already exists", "already in the model", "existing"}:
        return "Existing"
    return text or "Missing"


def snapshot_model_descriptions(dataset_name: str, workspace_name: str) -> dict:
    """{(kind, table_key, object_key): original description} from the live model.

    Prefer TOM so a wipe via clear_semantic_model_metadata is visible on rebuild.
    Fall back to fabric.list_* when TOM is unavailable.
    """
    out = {}
    if _SEMPY_AVAILABLE and connect_semantic_model is not None:
        try:
            with connect_semantic_model(
                dataset=dataset_name, workspace=workspace_name, readonly=True
            ) as tom:
                for table in tom.model.Tables:
                    tname = _text(table.Name)
                    if not tname:
                        continue
                    tkey = _key(tname)
                    out[("table", tkey, tkey)] = _text(getattr(table, "Description", ""))
                    for col in table.Columns:
                        cname = _text(col.Name)
                        if cname:
                            out[("column", tkey, _key(cname))] = _text(
                                getattr(col, "Description", "")
                            )
                    for meas in table.Measures:
                        mname = _text(meas.Name)
                        if mname:
                            out[("measure", tkey, _key(mname))] = _text(
                                getattr(meas, "Description", "")
                            )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not snapshot descriptions via TOM (%s). Falling back to fabric.list_*.",
                exc,
            )

    if not _SEMPY_AVAILABLE or fabric is None:
        return out
    try:
        tables_df = fabric.list_tables(dataset=dataset_name, workspace=workspace_name)
        table_name_col = _first_col(tables_df, "Name", "Table Name")
        table_desc_col = _first_col(tables_df, "Description", "Table Description")
        for _, row in tables_df.iterrows():
            name = _text(row.get(table_name_col))
            if name:
                out[("table", _key(name), _key(name))] = _text(row.get(table_desc_col))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not snapshot table descriptions (%s).", exc)

    try:
        columns_df = fabric.list_columns(dataset=dataset_name, workspace=workspace_name)
        tcol = _first_col(columns_df, "Table Name", "Table")
        ccol = _first_col(columns_df, "Column Name", "Name")
        dcol = _first_col(columns_df, "Description", "Column Description")
        for _, row in columns_df.iterrows():
            table, name = _text(row.get(tcol)), _text(row.get(ccol))
            if table and name:
                out[("column", _key(table), _key(name))] = _text(row.get(dcol))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not snapshot column descriptions (%s).", exc)

    try:
        measures_df = fabric.list_measures(dataset=dataset_name, workspace=workspace_name)
        tcol = _first_col(measures_df, "Table Name", "Table")
        mcol = _first_col(measures_df, "Measure Name", "Name")
        dcol = _first_col(measures_df, "Measure Description", "Description")
        for _, row in measures_df.iterrows():
            table, name = _text(row.get(tcol)), _text(row.get(mcol))
            if table and name:
                out[("measure", _key(table), _key(name))] = _text(row.get(dcol))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not snapshot measure descriptions (%s).", exc)
    return out


def _normalize_clear_targets(target_name) -> list:
    """Return stripped display names. Empty list means no name filter."""
    if target_name is None:
        return []
    if isinstance(target_name, str):
        text = target_name.strip()
        return [text] if text else []
    if isinstance(target_name, (list, tuple, set)):
        out = []
        for item in target_name:
            text = str(item).strip() if item is not None else ""
            if text:
                out.append(text)
        return out
    text = str(target_name).strip()
    return [text] if text else []


def _clear_metadata_status(
    cleared: int,
    do_desc: bool,
    do_syn: bool,
    kind_filter: Optional[str],
    target_labels: list,
) -> str:
    """Status line after a session clear. Default (both flags) keeps the old wording."""
    if do_desc and do_syn:
        return f"Cleared proposed metadata on {cleared} object(s)."
    noun = {"column": "column(s)", "measure": "measure(s)", "table": "table(s)"}.get(
        kind_filter, "object(s)"
    )
    what = "descriptions" if do_desc else "synonyms"
    left = "synonyms" if do_desc else "descriptions"
    if not target_labels:
        loc = ""
    elif len(target_labels) == 1:
        loc = f" in table {target_labels[0]}"
    else:
        loc = f" in tables {', '.join(target_labels)}"
    return f"Cleared {what} on {cleared} {noun}{loc} ({left} left unchanged)."


class MetadataSyncEngine:
    """
    Session-level proposed-state engine for Databricks -> Power BI metadata sync.

    Build once (extraction + AI), then preview / edit / clear / dry-run / apply
    against the same in-memory proposed records. Nothing is written until
    apply(apply_changes=True).

    generate_missing_table_descriptions / generate_missing_column_descriptions /
    generate_missing_measure_descriptions default True. Set a flag False to skip
    Fabric AI descriptions for that object type; Databricks comments still apply.

    generate_table_synonyms / generate_column_synonyms / generate_measure_synonyms
    default True. Set a flag False to skip the matching AI synonym batches
    (including quality-gate retries). generate_column_synonyms covers calculated,
    unmapped/source, and Databricks-mapped columns.
    """

    def __init__(
        self,
        dataset_name: str,
        workspace_name: str,
        table_mapping: Optional[dict] = None,
        table_name_map: Optional[dict] = None,
        column_name_map: Optional[dict] = None,
        databricks_server_hostname: Optional[str] = None,
        databricks_http_path: Optional[str] = None,
        databricks_access_token: Optional[str] = None,
        databricks_comments=None,
        catalog_pattern: str = "%mde%",
        schemas: Iterable[str] = ("gold", "platinum"),
        auto_discover_tables: Union[str, bool] = "yes",
        synonym_culture: str = "en-US",
        generate_missing_table_descriptions: Union[str, bool] = True,
        generate_missing_column_descriptions: Union[str, bool] = True,
        generate_missing_measure_descriptions: Union[str, bool] = True,
        generate_table_synonyms: Union[str, bool] = True,
        generate_column_synonyms: Union[str, bool] = True,
        generate_measure_synonyms: Union[str, bool] = True,
        **plan_kwargs,
    ):
        self.dataset_name = dataset_name
        self.workspace_name = workspace_name
        self.table_mapping = dict(table_mapping or {})
        self.table_name_map = SemanticModelDescriptionApplier._normalize_table_name_map(
            invert_table_mapping(self.table_mapping)
        )
        for key, values in SemanticModelDescriptionApplier._normalize_table_name_map(
            table_name_map or {}
        ).items():
            self.table_name_map.setdefault(key, [])
            for name in values:
                if name not in self.table_name_map[key]:
                    self.table_name_map[key].append(name)
        self.column_name_map = SemanticModelDescriptionApplier._normalize_column_name_map(
            column_name_map or {}
        )
        self.databricks_server_hostname = databricks_server_hostname
        self.databricks_http_path = databricks_http_path
        self.databricks_access_token = databricks_access_token
        self.databricks_comments = databricks_comments
        self.catalog_pattern = catalog_pattern
        self.schemas = tuple(schemas)
        self.auto_discover_tables = auto_discover_tables
        self.synonym_culture = synonym_culture or "en-US"
        self.generate_missing_table_descriptions = generate_missing_table_descriptions
        self.generate_missing_column_descriptions = generate_missing_column_descriptions
        self.generate_missing_measure_descriptions = generate_missing_measure_descriptions
        self.generate_table_synonyms = generate_table_synonyms
        self.generate_column_synonyms = generate_column_synonyms
        self.generate_measure_synonyms = generate_measure_synonyms
        self.plan_kwargs = plan_kwargs

        self.plan: Optional[DocumentationPlan] = None
        self.comments: Optional[pd.DataFrame] = None
        self.originals: dict = {}
        self.original_synonyms: dict = {}
        self.proposed: dict = {}
        self.description_registry = DescriptionRegistry()
        self.last_summary: dict = {}

        global _SESSION_ENGINE
        _SESSION_ENGINE = self

    # ---------- build ----------

    def build(self, show_report: bool = True) -> "MetadataSyncEngine":
        """Run Steps 1-3: extract Databricks comments, generate AI gaps, unique synonyms."""
        print("=== Metadata sync: build ===")
        hostname = self.databricks_server_hostname
        http_path = self.databricks_http_path
        token = self.databricks_access_token
        if not all([hostname, http_path, token]) and self.databricks_comments is None:
            hostname, http_path, token = load_databricks_credentials()
            self.databricks_server_hostname = hostname
            self.databricks_http_path = http_path
            self.databricks_access_token = token

        comments = self.databricks_comments
        have_credentials = all([hostname, http_path, token])
        if comments is None and not have_credentials:
            logger.warning(
                "Databricks credentials are not configured. Step 1 is skipped; "
                "descriptions will come from the model and Fabric AI only."
            )
            print(
                "Step 1 — Databricks: skipped (credentials not configured). "
                "Descriptions will come from the model and Fabric AI only."
            )
            comments = _empty_comments_frame()

        if comments is None and self.table_name_map and have_credentials:
            try:
                sql = build_databricks_metadata_sql(
                    table_name_map=self.table_name_map,
                    catalog_pattern=self.catalog_pattern,
                    schemas=self.schemas,
                )
                comments = _normalize_comment_columns(
                    _run_databricks_query(hostname, http_path, token, sql)
                )
                n_tables = int(comments["databricks_table"].nunique()) if not comments.empty else 0
                print(
                    f"Step 1 — Databricks: extracted {len(comments)} column comments "
                    f"from {n_tables} Unity Catalog tables."
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Step 1 Databricks extraction failed (%s). Continuing without Unity Catalog comments.",
                    exc,
                )
                print(
                    "Step 1 — Databricks: extract failed. Continuing without Unity Catalog comments."
                )
                comments = _empty_comments_frame()
        elif comments is not None and not getattr(comments, "empty", True):
            work = comments
            if "databricks_table" in getattr(work, "columns", []):
                n_tables = int(work["databricks_table"].nunique())
            else:
                n_tables = 0
            print(
                f"Step 1 — Databricks: using {len(work)} preloaded column comments "
                f"from {n_tables} Unity Catalog tables."
            )

        self.comments = comments if comments is not None else _empty_comments_frame()
        # Re-read the live model every build so a wipe is visible to generate_missing_*.
        self.originals = snapshot_model_descriptions(self.dataset_name, self.workspace_name)
        # Live Q&A synonyms at this build. Session edits must not overwrite this snapshot.
        raw_syn = load_existing_synonyms_map(
            self.dataset_name, self.workspace_name, culture=self.synonym_culture
        )
        self.original_synonyms = {
            (_key(kind), _key(table), _key(name)): list(syns or [])
            for (table, name, kind), syns in (raw_syn or {}).items()
        }

        try:
            plan_kwargs = {
                key: value
                for key, value in self.plan_kwargs.items()
                if key
                not in {
                    "generate_missing_table_descriptions",
                    "generate_missing_column_descriptions",
                    "generate_missing_measure_descriptions",
                    "generate_table_synonyms",
                    "generate_column_synonyms",
                    "generate_measure_synonyms",
                    "existing_descriptions",
                }
            }
            self.plan = build_documentation_plan(
                dataset_name=self.dataset_name,
                workspace_name=self.workspace_name,
                databricks_server_hostname=hostname,
                databricks_http_path=http_path,
                databricks_access_token=token,
                databricks_comments=self.comments,
                catalog_pattern=self.catalog_pattern,
                schemas=self.schemas,
                table_name_map=self.table_name_map or None,
                auto_discover_tables=self.auto_discover_tables,
                column_rename_overrides=self.column_name_map,
                synonym_culture=self.synonym_culture,
                generate_missing_table_descriptions=self.generate_missing_table_descriptions,
                generate_missing_column_descriptions=self.generate_missing_column_descriptions,
                generate_missing_measure_descriptions=self.generate_missing_measure_descriptions,
                generate_table_synonyms=self.generate_table_synonyms,
                generate_column_synonyms=self.generate_column_synonyms,
                generate_measure_synonyms=self.generate_measure_synonyms,
                show_report=show_report,
                existing_descriptions=self.originals,
                **plan_kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Documentation plan failed: %s", exc)
            raise

        if self.plan.table_name_map:
            self.table_name_map = self.plan.table_name_map
        if self.plan.column_name_map:
            self.column_name_map = self.plan.column_name_map

        self._enforce_description_uniqueness()
        self._rebuild_proposed()
        preview = self.preview(announce=False)
        print(f"=== Proposed metadata ready: {len(self.proposed)} objects ===")
        sources = _source_counts(preview)
        print(
            "  Source: "
            + " | ".join(
                f"{name} {sources[name]}"
                for name in ("Databricks", "AI", "Existing", "Missing")
            )
        )
        return self

    def _enforce_description_uniqueness(self) -> None:
        if self.plan is None:
            return
        registry = self.description_registry
        _enforce_unique_descriptions(
            self.plan.generated_table_rows,
            kind="table",
            table_key="Table",
            name_key="Table",
            registry=registry,
        )
        _enforce_unique_descriptions(
            self.plan.generated_calculated_column_rows,
            kind="column",
            table_key="Table",
            name_key="Column",
            registry=registry,
        )
        _enforce_unique_descriptions(
            self.plan.generated_measure_rows,
            kind="measure",
            table_key="Table",
            name_key="Column",
            registry=registry,
        )

    def _put(
        self,
        object_type: str,
        table_name: str,
        object_name: str,
        source: str,
        proposed_description: str,
        proposed_synonyms,
    ) -> None:
        kind = _key(object_type) or "column"
        table = _text(table_name)
        name = _text(object_name) or table
        if not table or not name:
            return
        key = (kind, _key(table), _key(name))
        original = _text(self.originals.get(key, ""))
        proposed = _text(proposed_description) or original
        label = _source_label(source)
        existing_synonyms = list(self.original_synonyms.get(key, []))
        new_syns = _parse_synonyms(proposed_synonyms, limit=None)
        prev = self.proposed.get(key)
        if prev:
            # Same object can be written from Databricks comments and from the
            # AI column pass. Never let a later empty write wipe a filled value.
            if not proposed and _text(prev.get("Proposed Description")):
                proposed = _text(prev.get("Proposed Description"))
                if label == "Missing":
                    label = prev.get("Source (Databricks vs AI)") or label
            if not new_syns and prev.get("Proposed Synonyms"):
                new_syns = list(prev.get("Proposed Synonyms") or [])
        if not original and not proposed and label not in {"Manual", "Cleared"}:
            label = "Missing"
        self.proposed[key] = {
            "Object Type": object_type.title(),
            "Table Name": table,
            "Object Name": name,
            "Source (Databricks vs AI)": label,
            "Original Description": original,
            "Proposed Description": proposed,
            "Synonym Existed": "Yes" if existing_synonyms else "No",
            "Existing Synonyms": existing_synonyms,
            "Proposed Synonyms": new_syns,
        }

    def _rebuild_proposed(self) -> None:
        self.proposed = {}
        if self.plan is None:
            return

        preview = self.plan.table_preview if self.plan.table_preview is not None else pd.DataFrame()
        source_by_table = {}
        desc_by_table = {}
        if not preview.empty and "Table" in preview.columns:
            src_col = (
                "Description Source"
                if "Description Source" in preview.columns
                else None
            )
            desc_col = "Desc" if "Desc" in preview.columns else None
            for _, row in preview.iterrows():
                tkey = _key(row.get("Table"))
                source_by_table[tkey] = (
                    row.get(src_col) if src_col else "Databricks"
                )
                if desc_col:
                    desc_by_table[tkey] = row.get(desc_col)

        syn_by_table = {}
        for row in self.plan.table_rows:
            tkey = _key(row.get("Table"))
            syn_by_table[tkey] = row.get("Synonyms")
            if row.get("Desc"):
                desc_by_table[tkey] = row.get("Desc")

        seen_tables = set()
        if not preview.empty and "Table" in preview.columns:
            for _, row in preview.iterrows():
                table = _text(row.get("Table"))
                if not table:
                    continue
                seen_tables.add(_key(table))
                self._put(
                    "Table",
                    table,
                    table,
                    source_by_table.get(_key(table), "AI"),
                    desc_by_table.get(_key(table), ""),
                    syn_by_table.get(_key(table)),
                )
        for row in self.plan.table_rows:
            table = _text(row.get("Table"))
            if not table or _key(table) in seen_tables:
                continue
            self._put(
                "Table",
                table,
                table,
                source_by_table.get(_key(table), "AI"),
                row.get("Desc"),
                row.get("Synonyms"),
            )

        mapped_syn = self.plan.mapped_column_synonyms or {}
        comments = self.plan.comments if self.plan.comments is not None else _empty_comments_frame()
        for rec in comments.to_dict("records"):
            view = _text(rec.get("databricks_table"))
            source_col = _text(rec.get("column_name"))
            desc = _text(rec.get("column_description"))
            if not view or not source_col or not desc:
                continue
            pbi_col = self.column_name_map.get(_key(view), {}).get(_key(source_col), source_col)
            pbi_tables = (
                self.table_name_map.get(_key(view))
                or self.table_name_map.get(view)
                or self.table_name_map.get(_key(view.rsplit(".", 1)[-1]))
                or []
            )
            for pbi_table in pbi_tables:
                syns = _lookup_mapped_column_synonyms(mapped_syn, pbi_table, pbi_col)
                self._put("Column", pbi_table, pbi_col, "Databricks", desc, syns)

        col_preview = self.plan.calculated_column_preview
        col_source = {}
        if col_preview is not None and not col_preview.empty:
            tcol = _first_col(col_preview, "Table Name", "Table")
            ccol = _first_col(col_preview, "Column Name", "Column")
            scol = _first_col(col_preview, "Description Source")
            for _, row in col_preview.iterrows():
                col_source[(_key(row.get(tcol)), _key(row.get(ccol)))] = row.get(scol)

        for row in self.plan.calculated_column_rows:
            table, name = _text(row.get("Table")), _text(row.get("Column"))
            syns = list(row.get("Synonyms") or [])
            if not syns:
                syns = _lookup_mapped_column_synonyms(mapped_syn, table, name)
            self._put(
                "Column",
                table,
                name,
                col_source.get((_key(table), _key(name)), "AI"),
                row.get("Desc"),
                syns,
            )

        meas_preview = self.plan.measure_preview
        meas_source = {}
        if meas_preview is not None and not meas_preview.empty:
            tcol = _first_col(meas_preview, "Table", "Table Name")
            mcol = _first_col(meas_preview, "Measure Name", "Column")
            scol = _first_col(meas_preview, "Description Source")
            for _, row in meas_preview.iterrows():
                meas_source[(_key(row.get(tcol)), _key(row.get(mcol)))] = row.get(scol)

        for row in self.plan.measure_rows:
            table, name = _text(row.get("Table")), _text(row.get("Column"))
            self._put(
                "Measure",
                table,
                name,
                meas_source.get((_key(table), _key(name)), "AI"),
                row.get("Desc"),
                row.get("Synonyms"),
            )

    # ---------- review ----------

    def preview(
        self,
        object_types: Optional[Union[str, Iterable[str]]] = None,
        announce: bool = True,
    ) -> pd.DataFrame:
        """Interactive preview of the proposed metadata.

        object_types: None for all types, or a string / list of
        table(s), column(s), measure(s).
        """
        empty = pd.DataFrame(columns=list(PREVIEW_COLUMNS))
        kinds = _normalize_preview_object_types(object_types)
        if not self.proposed:
            if announce:
                print(_preview_counts_line(empty))
            return empty
        frame = pd.DataFrame(list(self.proposed.values()))
        for col in ("Existing Synonyms", "Proposed Synonyms"):
            if col in frame.columns:
                frame[col] = frame[col].map(
                    lambda v: ", ".join(v) if isinstance(v, list) else v
                )
        frame = frame[list(PREVIEW_COLUMNS)]
        if kinds is not None:
            frame = frame[
                frame["Object Type"].map(_normalize_preview_object_type).isin(kinds)
            ].copy()
        if frame.empty:
            if announce:
                print(_preview_counts_line(empty))
            return empty
        type_order = {"Table": 0, "Column": 1, "Measure": 2}
        frame["_type_order"] = frame["Object Type"].map(type_order).fillna(9)
        frame = frame.sort_values(
            ["_type_order", "Table Name", "Object Name"], ignore_index=True
        ).drop(columns="_type_order")
        if announce:
            print(_preview_counts_line(frame))
        return frame

    def _find_proposed(
        self,
        object_name: str,
        table_name: Optional[str] = None,
        object_type: Optional[str] = None,
    ) -> list:
        name_key = _key(object_name)
        table_key = _key(table_name) if table_name else None
        type_key = _normalize_preview_object_type(object_type) if object_type else None
        if object_type and type_key is None:
            raise ValueError(
                f"Invalid object_type {object_type!r}. Allowed: "
                f"{', '.join(PREVIEW_OBJECT_TYPES)} "
                "(aliases: table, column, measure)."
            )
        matches = []
        for key, rec in self.proposed.items():
            kind, table, name = key
            if name != name_key and not (kind == "table" and table == name_key):
                continue
            if table_key and table != table_key:
                continue
            if type_key and kind != type_key:
                continue
            matches.append(key)
        return matches

    def update_proposed_metadata(
        self,
        object_name=None,
        new_desc: Optional[str] = None,
        new_synonyms=None,
        table_name: Optional[str] = None,
        object_type: Optional[str] = None,
        updates=None,
    ) -> pd.DataFrame:
        """
        Edit one proposed object, or many via updates=.

        Single object (unchanged)::

            update_proposed_metadata(
                object_name="DIOH Card",
                new_desc="...",
                new_synonyms=["..."],
                table_name="_Measure",
                object_type="measure",
            )

        Bulk — any of: updates= as one preview-column dict, a list of dicts,
        a DataFrame, or the first positional arg as that payload. Mix tables,
        columns, and measures in one batch. Omit / None for new_desc or
        new_synonyms to leave that field unchanged.

        Preview-column aliases (Object Name, Proposed Description, ...) are
        accepted so a filtered preview_df, a list of those rows, or a single
        preview-column dict can be passed straight in. Source (Databricks vs
        AI), Original Description, Synonym Existed, and Existing Synonyms
        are display-only and ignored on write.
        Per-row errors in a list/DataFrame are skipped; a summary is printed.
        A single updates= dict raises on the first error.

        Pass table_name when object_name is not unique. Pass either a single
        object_name= or updates=, not both.

        Updates the in-memory proposed state and the underlying plan rows so
        apply() writes the edited wording.
        """
        object_name, updates = _resolve_update_payload(object_name, updates)
        if self.plan is None:
            raise RuntimeError("Call build() before editing or clearing proposed metadata.")
        if updates is not None:
            return self._update_proposed_metadata_bulk(updates)
        if object_name is None or not str(object_name).strip():
            raise ValueError(
                "Pass object_name= for a single update or updates= for a batch."
            )
        return self._update_proposed_metadata_one(
            object_name,
            new_desc=new_desc,
            new_synonyms=new_synonyms,
            table_name=table_name,
            object_type=object_type,
        )

    def _apply_one_proposed_update(
        self,
        object_name: str,
        new_desc=None,
        new_synonyms=None,
        table_name=None,
        object_type=None,
    ) -> list:
        """Find + uniqueness + write-through for one object. Returns match keys."""
        matches = self._find_proposed(object_name, table_name, object_type)
        if not matches:
            raise KeyError(
                f"No proposed object named {object_name!r}"
                + (f" in table {table_name!r}" if table_name else "")
                + ". Check preview() for exact names."
            )
        if len(matches) > 1 and not table_name:
            tables = sorted({self.proposed[k]["Table Name"] for k in matches})
            raise ValueError(
                f"{object_name!r} is ambiguous across {tables}. "
                "Pass table_name= (and object_type= if needed)."
            )

        for key in matches:
            rec = self.proposed[key]
            if new_desc is not None:
                rec["Proposed Description"] = str(new_desc).strip()
                rec["Source (Databricks vs AI)"] = "Manual"
            if new_synonyms is not None:
                rec["Proposed Synonyms"] = _parse_synonyms(new_synonyms, limit=None)
                rec["Source (Databricks vs AI)"] = "Manual"
            self._write_through(rec)
        return matches

    def _update_proposed_metadata_one(
        self,
        object_name: str,
        new_desc: Optional[str] = None,
        new_synonyms=None,
        table_name: Optional[str] = None,
        object_type: Optional[str] = None,
    ) -> pd.DataFrame:
        self._apply_one_proposed_update(
            object_name, new_desc, new_synonyms, table_name, object_type
        )
        return self.preview(announce=False).query(
            "`Object Name` == @object_name"
            + (" and `Table Name` == @table_name" if table_name else "")
        )

    def _update_proposed_metadata_bulk(self, updates) -> pd.DataFrame:
        records = _coerce_update_records(updates)
        raise_first = isinstance(updates, dict)
        n_ok = 0
        n_fail = 0
        ok_keys = []
        for i, rec in enumerate(records):
            try:
                args = _normalize_update_record(rec)
                matches = self._apply_one_proposed_update(
                    args["object_name"],
                    new_desc=args["new_desc"],
                    new_synonyms=args["new_synonyms"],
                    table_name=args["table_name"],
                    object_type=args["object_type"],
                )
                ok_keys.extend(matches)
                n_ok += 1
            except Exception as exc:
                if raise_first:
                    raise
                print(f"Skipped row {i}: {type(exc).__name__}: {exc}")
                n_fail += 1
        print(f"Updated {n_ok} object(s). Failed {n_fail}.")
        preview = self.preview(announce=False)
        empty = pd.DataFrame(columns=list(PREVIEW_COLUMNS))
        if preview is None or preview.empty or not ok_keys:
            return empty if preview is None or preview.empty else preview.iloc[0:0].copy()
        ok_set = set(ok_keys)

        def _row_key(row):
            kind = _normalize_preview_object_type(row.get("Object Type")) or _key(
                row.get("Object Type")
            )
            return (kind, _key(row.get("Table Name")), _key(row.get("Object Name")))

        mask = preview.apply(_row_key, axis=1).map(ok_set.__contains__)
        return preview.loc[mask].reset_index(drop=True)

    def _write_through(
        self,
        rec: dict,
        write_description: bool = True,
        write_synonyms: bool = True,
    ) -> None:
        """Copy proposed fields onto the plan. Omit a half to leave that plan side alone.

        write_synonyms=False never sets Replace Synonyms or writes an empty
        synonym list, so apply will not wipe live Q&A synonyms.
        write_description=False never blanks Desc or sets Force.
        write_synonyms=True always sets Replace Synonyms (or the table
        equivalent) so apply can remove live synonyms, including an empty list.
        """
        kind = _normalize_preview_object_type(rec["Object Type"]) or _key(rec["Object Type"])
        table, name = rec["Table Name"], rec["Object Name"]
        desc, syns = rec["Proposed Description"], rec["Proposed Synonyms"]
        if kind == "table":
            found = False
            for row in self.plan.generated_table_rows:
                if _key(row.get("Table")) == _key(table):
                    if write_description:
                        row["Desc"] = desc
                        row["Force"] = True
                    if write_synonyms:
                        row["Synonyms"] = list(syns)
                        row["Replace Synonyms"] = True
                    found = True
            if not found:
                payload = {"Table": table}
                if write_description:
                    payload["Desc"] = desc
                    payload["Force"] = True
                else:
                    payload["Description Mode"] = MODE_KEEP
                if write_synonyms:
                    payload["Synonyms"] = list(syns)
                    payload["Replace Synonyms"] = True
                else:
                    payload["Synonym Mode"] = MODE_KEEP
                self.plan.manual_table_rows.append(payload)
            return

        bucket = (
            self.plan.generated_measure_rows
            if kind == "measure"
            else self.plan.generated_calculated_column_rows
        )
        manual = (
            self.plan.manual_measure_rows
            if kind == "measure"
            else self.plan.manual_calculated_column_rows
        )
        found = False
        for row in bucket:
            if _key(row.get("Table")) == _key(table) and _key(row.get("Column")) == _key(name):
                if write_description:
                    row["Desc"] = desc
                    row["Force"] = True
                if write_synonyms:
                    row["Synonyms"] = list(syns)
                    row["Replace Synonyms"] = True
                found = True
        if not found:
            payload = {"Table": table, "Column": name}
            if write_description:
                payload["Desc"] = desc
                payload["Force"] = True
            else:
                payload["Description Mode"] = MODE_KEEP
            if write_synonyms:
                payload["Synonyms"] = list(syns)
                payload["Replace Synonyms"] = True
            else:
                payload["Synonym Mode"] = MODE_KEEP
            manual.append(payload)

        if write_synonyms and kind == "column":
            mapped = getattr(self.plan, "mapped_column_synonyms", None)
            if isinstance(mapped, dict):
                mapped[(_key(table), _key(name))] = list(syns)

    def clear_metadata(
        self,
        scope: str = "all",
        target_name: Optional[Union[str, Iterable[str]]] = None,
        clear_descriptions=True,
        clear_synonyms=True,
    ) -> pd.DataFrame:
        """
        Clear proposed descriptions and/or synonyms.

        scope: 'all' | 'measures' | 'columns' | 'tables'
        target_name: optional object or table name (string or list) to narrow
            the clear. A table name with scope='columns' clears every proposed
            column on that table.
        clear_descriptions / clear_synonyms: default True so omitted flags
            still clear both (old behavior). Pass clear_synonyms=False to
            blank proposed descriptions only and leave Proposed Synonyms
            (and plan Replace Synonyms flags) unchanged. Pass
            clear_descriptions=False and clear_synonyms=True to empty
            Proposed Synonyms only; descriptions stay as they are and
            write-through sets Replace Synonyms so apply removes live
            Q&A synonyms without blanking Desc.
        Resets proposed text to the original model description (or blank)
            when descriptions are cleared.
        Does not touch the live semantic model by itself.
        """
        if self.plan is None:
            raise RuntimeError("Call build() before editing or clearing proposed metadata.")
        allowed = {"all", "measures", "columns", "tables", "measure", "column", "table"}
        scope_key = _key(scope)
        if scope_key not in allowed:
            raise ValueError(f"scope must be one of all|measures|columns|tables, got {scope!r}")
        kind_filter = {
            "measures": "measure",
            "measure": "measure",
            "columns": "column",
            "column": "column",
            "tables": "table",
            "table": "table",
        }.get(scope_key)

        do_desc = _yes_no(clear_descriptions, "clear_descriptions")
        do_syn = _yes_no(clear_synonyms, "clear_synonyms")
        if not do_desc and not do_syn:
            print("Clear skipped. Set clear_descriptions and/or clear_synonyms to True.")
            return self.preview(announce=False)

        target_labels = _normalize_clear_targets(target_name)
        targets = {_key(name) for name in target_labels}
        if do_desc and do_syn:
            source_label = "Cleared"
        elif do_desc:
            source_label = "Cleared for description"
        else:
            source_label = "Cleared for synonyms"

        cleared = 0
        for key, rec in list(self.proposed.items()):
            kind, table, name = key
            if kind_filter and kind != kind_filter:
                continue
            if targets and name not in targets and table not in targets:
                continue
            if do_desc:
                rec["Proposed Description"] = rec.get("Original Description") or ""
            if do_syn:
                rec["Proposed Synonyms"] = []
            rec["Source (Databricks vs AI)"] = source_label
            self._write_through(rec, write_description=do_desc, write_synonyms=do_syn)
            cleared += 1
        print(_clear_metadata_status(cleared, do_desc, do_syn, kind_filter, target_labels))
        return self.preview(announce=False)

    def summary(self) -> dict:
        preview = self.preview(announce=False)
        by_source = _source_counts(preview)
        by_type = preview["Object Type"].value_counts().to_dict() if not preview.empty else {}
        changed = 0
        if not preview.empty:
            changed = int(
                (
                    preview["Original Description"].fillna("")
                    != preview["Proposed Description"].fillna("")
                ).sum()
            )
        self.last_summary = {
            "objects": len(preview),
            "by_type": by_type,
            "by_source": by_source,
            "descriptions_changed": changed,
            "databricks_tables_mapped": len(self.table_name_map),
            "dataset": self.dataset_name,
            "workspace": self.workspace_name,
        }
        print("=== Metadata sync: proposed-state summary ===")
        print(
            f"  Objects: {self.last_summary['objects']} "
            f"({by_type.get('Table', 0)} table(s), "
            f"{by_type.get('Column', 0)} column(s), "
            f"{by_type.get('Measure', 0)} measure(s))"
        )
        print(
            "  Source: "
            + " | ".join(
                f"{name} {by_source[name]}"
                for name in ("Databricks", "AI", "Existing", "Missing")
            )
        )
        print(f"  Descriptions different from the model: {changed}")
        return self.last_summary

    def apply(
        self,
        apply_changes: bool = False,
        overwrite_tables=None,
        overwrite_columns=None,
        overwrite_measures=None,
        overwrite_column_synonyms=None,
        overwrite_measure_synonyms=None,
        **kwargs,
    ) -> dict:
        """Dry-run by default. Pass apply_changes=True to commit via TOM / SemPy."""
        if self.plan is None:
            raise RuntimeError("Call build() before apply().")
        self.last_summary = self.plan.apply(
            overwrite_tables=overwrite_tables,
            overwrite_columns=overwrite_columns,
            overwrite_measures=overwrite_measures,
            overwrite_column_synonyms=overwrite_column_synonyms,
            overwrite_measure_synonyms=overwrite_measure_synonyms,
            apply_changes=apply_changes,
            **kwargs,
        )
        self.last_summary["apply_changes"] = apply_changes
        if not apply_changes:
            print("Dry run only. Re-run apply(apply_changes=True) to write the semantic model.")
        return self.last_summary


def init_metadata_sync(
    dataset_name: str = None,
    workspace_name: str = None,
    **kwargs,
) -> MetadataSyncEngine:
    """Create the session engine. Subsequent preview/edit/clear/apply share this state.

    Pass generate_missing_table_descriptions / generate_missing_column_descriptions /
    generate_missing_measure_descriptions (default True) to opt out of Fabric AI
    descriptions for objects Databricks did not comment.

    Pass generate_table_synonyms / generate_column_synonyms / generate_measure_synonyms
    (default True) to skip AI synonym batches independently of descriptions.
    generate_column_synonyms covers calculated, unmapped/source, and Databricks-mapped
    columns.
    """
    if dataset_name is not None:
        kwargs["dataset_name"] = dataset_name
    if workspace_name is not None:
        kwargs["workspace_name"] = workspace_name
    return MetadataSyncEngine(**kwargs)


def get_engine() -> MetadataSyncEngine:
    if _SESSION_ENGINE is None:
        raise RuntimeError(
            "No MetadataSyncEngine in this session. "
            "Call init_metadata_sync(...) or MetadataSyncEngine(...) first."
        )
    return _SESSION_ENGINE


def _is_updates_payload(value) -> bool:
    """True when value is a one-record dict, list/tuple of records, or DataFrame."""
    if value is None:
        return False
    if isinstance(value, pd.DataFrame):
        return True
    if isinstance(value, dict):
        return _looks_like_update_record(value)
    return isinstance(value, (list, tuple))


def _resolve_update_payload(object_name, updates):
    """Split single-object vs bulk. First positional list/DataFrame/record dict is updates."""
    positional_bulk = _is_updates_payload(object_name)
    if positional_bulk and updates is not None:
        raise ValueError("Pass either a single object_name= or updates=, not both.")
    if positional_bulk:
        return None, object_name
    if updates is not None and object_name is not None:
        raise ValueError("Pass either a single object_name= or updates=, not both.")
    return object_name, updates


def _is_omitted_update_value(value) -> bool:
    """True when a bulk-record field should be left unchanged."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return False


_UPDATE_FIELD_ALIASES = {
    "object_name": ("object_name", "Object Name"),
    "table_name": ("table_name", "Table Name"),
    "object_type": ("object_type", "Object Type"),
    "new_desc": ("new_desc", "Proposed Description", "Desc"),
    "new_synonyms": ("new_synonyms", "Proposed Synonyms", "Synonyms"),
}

# Preview / alias keys that identify one update record (not a column-oriented map).
_UPDATE_RECORD_KEY_ALIASES = frozenset(
    str(name).strip().lower()
    for names in _UPDATE_FIELD_ALIASES.values()
    for name in names
)


def _looks_like_update_record(value) -> bool:
    """True when a dict is keyed like one preview row or one update record.

    Detects Object Name / Object Type / Table Name / Proposed Description /
    Proposed Synonyms and snake_case aliases (object_name, new_desc, ...).
    Display-only preview columns (Source, Original Description,
    Synonym Existed, Existing Synonyms) do not count.
    """
    if not isinstance(value, dict):
        return False
    keys = {str(k).strip().lower() for k in value.keys()}
    return bool(keys & _UPDATE_RECORD_KEY_ALIASES)


def _record_lookup(rec: dict, *names):
    """Return (value, found) using exact then case-insensitive key aliases."""
    for name in names:
        if name in rec:
            return rec[name], True
    lower_map = {str(k).strip().lower(): k for k in rec.keys()}
    for name in names:
        key = lower_map.get(str(name).strip().lower())
        if key is not None:
            return rec[key], True
    return None, False


def _coerce_update_records(updates) -> list:
    """Normalize updates= to a list of dicts.

    A plain dict whose keys look like preview columns is one record. Do not
    pass it to DataFrame() — pandas would treat it as a column-oriented map.
    """
    if isinstance(updates, pd.DataFrame):
        return [row.to_dict() for _, row in updates.iterrows()]
    if isinstance(updates, dict):
        return [updates]
    if isinstance(updates, (list, tuple)):
        records = []
        for item in updates:
            if isinstance(item, pd.Series):
                records.append(item.to_dict())
            else:
                records.append(item)
        return records
    raise TypeError(
        "updates must be a dict (one record), a list of dicts, or a pandas "
        f"DataFrame, got {type(updates).__name__}"
    )


def _normalize_update_record(rec) -> dict:
    """Map one bulk record (dict or Series) onto single-update kwargs."""
    if isinstance(rec, pd.Series):
        rec = rec.to_dict()
    if not isinstance(rec, dict):
        raise TypeError(f"Each update must be a dict, got {type(rec).__name__}")

    object_name, found_name = _record_lookup(rec, *_UPDATE_FIELD_ALIASES["object_name"])
    if found_name and not _is_omitted_update_value(object_name):
        object_name = _text(object_name)
    else:
        object_name = ""
    if not object_name:
        raise ValueError(
            "Each update dict needs 'Object Name' or 'object_name'. "
            f"Got keys: {list(rec.keys())}"
        )

    table_name, found_table = _record_lookup(rec, *_UPDATE_FIELD_ALIASES["table_name"])
    if not found_table or _is_omitted_update_value(table_name) or not _text(table_name):
        table_name = None
    else:
        table_name = _text(table_name)

    object_type, found_type = _record_lookup(rec, *_UPDATE_FIELD_ALIASES["object_type"])
    if not found_type or _is_omitted_update_value(object_type) or not _text(object_type):
        object_type = None
    else:
        mapped = _normalize_preview_object_type(object_type)
        if mapped is None:
            raise ValueError(
                f"Invalid object_type {object_type!r}. Allowed: "
                f"{', '.join(PREVIEW_OBJECT_TYPES)} "
                "(aliases: table, column, measure)."
            )
        object_type = mapped

    new_desc, found_desc = _record_lookup(rec, *_UPDATE_FIELD_ALIASES["new_desc"])
    if not found_desc or _is_omitted_update_value(new_desc):
        new_desc = None
    else:
        new_desc = _text(new_desc)

    new_synonyms, found_syns = _record_lookup(rec, *_UPDATE_FIELD_ALIASES["new_synonyms"])
    if not found_syns or _is_omitted_update_value(new_synonyms):
        new_synonyms = None
    else:
        new_synonyms = _parse_synonyms(new_synonyms, limit=None)

    return {
        "object_name": object_name,
        "table_name": table_name,
        "object_type": object_type,
        "new_desc": new_desc,
        "new_synonyms": new_synonyms,
    }


def update_proposed_metadata(
    object_name=None,
    new_desc: Optional[str] = None,
    new_synonyms=None,
    table_name: Optional[str] = None,
    object_type: Optional[str] = None,
    updates=None,
) -> pd.DataFrame:
    """Edit proposed description/synonyms on the session engine.

    Single object::

        update_proposed_metadata(
            object_name="DIOH Card",
            new_desc="...",
            new_synonyms=["days of inventory"],
            table_name="_Measure",
            object_type="measure",
        )

    Bulk (one preview-column dict, list of dicts, DataFrame, or first
    positional payload)::

        update_proposed_metadata(updates={...preview columns...})
        update_proposed_metadata(updates=[{...}, {...}])
        update_proposed_metadata(updates=preview_df)
        update_proposed_metadata([...])

    Mix tables, columns, and measures. Omit / None for new_desc or
    new_synonyms to leave that field unchanged. Source (Databricks vs AI),
    Original Description, Synonym Existed, and Existing Synonyms are
    ignored. Do not pass both object_name= and updates=.
    """
    return get_engine().update_proposed_metadata(
        object_name,
        new_desc=new_desc,
        new_synonyms=new_synonyms,
        table_name=table_name,
        object_type=object_type,
        updates=updates,
    )


def clear_metadata(
    scope: str = "all",
    target_name: Optional[Union[str, Iterable[str]]] = None,
    clear_descriptions=True,
    clear_synonyms=True,
) -> pd.DataFrame:
    """Clear proposed metadata on the session engine (not the live model).

    Defaults clear both descriptions and synonyms. Pass clear_synonyms=False
    to blank proposed descriptions only (Proposed Synonyms stay as they are).
    Pass clear_descriptions=False and clear_synonyms=True to empty Proposed
    Synonyms only; descriptions stay as they are and apply can remove live
    Q&A synonyms. target_name may be one name or a list of table / object names.
    """
    return get_engine().clear_metadata(
        scope=scope,
        target_name=target_name,
        clear_descriptions=clear_descriptions,
        clear_synonyms=clear_synonyms,
    )


def _is_blank_filter(value) -> bool:
    """True when a filter argument means 'no restriction'."""
    if value is None:
        return True
    if isinstance(value, (list, tuple, set)) and len(value) == 0:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return False


def _name_filter_mask(series: pd.Series, needle, match_mode: str = "exact") -> pd.Series:
    """Case-insensitive exact/contains mask. Blank needle matches every row."""
    if _is_blank_filter(needle):
        return pd.Series(True, index=series.index)
    mode = _key(match_mode)
    if mode not in {"exact", "contains"}:
        raise ValueError(f"match_mode must be 'exact' or 'contains', got {match_mode!r}")
    hay = series.map(_key)
    pin = _key(needle)
    if mode == "contains":
        return hay.str.contains(re.escape(pin), regex=True, na=False)
    return hay == pin


def _singular_object_type(value) -> str:
    """Preview 'Object Type' / filter alias → table | column | measure."""
    mapped = _normalize_preview_object_type(value)
    if not mapped:
        raise ValueError(f"Could not normalize object type {value!r}.")
    return mapped


def _preview_row_update_args(row, new_desc=None, new_synonyms=None) -> dict:
    """Build update_proposed_metadata kwargs from one preview row."""
    desc = new_desc if new_desc is not None else row.get("Proposed Description")
    syns = (
        _parse_synonyms(new_synonyms, limit=None)
        if new_synonyms is not None
        else _parse_synonyms(row.get("Proposed Synonyms"), limit=None)
    )
    return {
        "object_name": _text(row.get("Object Name")),
        "new_desc": _text(desc),
        "new_synonyms": syns,
        "table_name": _text(row.get("Table Name")) or None,
        "object_type": _singular_object_type(row.get("Object Type")),
    }


def display_or_print(frame) -> None:
    """Show a DataFrame via IPython/Fabric display, else print(to_string())."""
    show = None
    try:
        from IPython.display import display as _ipy_display

        show = _ipy_display
    except Exception:
        show = globals().get("display")
    if callable(show):
        try:
            show(frame)
            return
        except Exception:
            pass
    if frame is None:
        print("(no DataFrame)")
        return
    print(frame.to_string() if hasattr(frame, "to_string") else frame)


def filter_preview_for_update(
    preview_df,
    object_types=None,
    table_name=None,
    object_name=None,
    source=None,
    match_mode: str = "exact",
) -> pd.DataFrame:
    """Filter a preview frame for bulk update_proposed_metadata calls.

    Empty / None filters impose no restriction. Name matching is case-insensitive
    and uses match_mode ('exact' or 'contains') for table_name and object_name.

    Object Type matching uses _normalize_preview_object_type so "measures",
    "measure", and preview's title-case "Measure" all match.

    If preview_df is None or empty, loads engine.preview(announce=False).
    Always prints at least one status line.
    """
    empty = pd.DataFrame(columns=list(PREVIEW_COLUMNS))
    try:
        if preview_df is None or getattr(preview_df, "empty", True):
            preview_df = get_engine().preview(object_types=None, announce=False)
            n_loaded = 0 if preview_df is None else len(preview_df)
            print(f"Loaded {n_loaded} row(s) from engine.preview().")

        if preview_df is None:
            print("Filtered preview: 0 row(s).")
            print("No preview rows matched the filters. Searched 0 preview row(s).")
            return empty

        frame = preview_df.copy()
        searched = len(frame)
        missing = [c for c in ("Object Type", "Table Name", "Object Name") if c not in frame.columns]
        if missing:
            raise ValueError(
                "Preview is missing required column(s): "
                + ", ".join(repr(c) for c in missing)
                + f". Columns present: {list(frame.columns)}"
            )

        mask = pd.Series(True, index=frame.index)

        if not _is_blank_filter(object_types):
            kinds = _normalize_preview_object_types(object_types)
            mask &= frame["Object Type"].map(_normalize_preview_object_type).isin(kinds)

        mask &= _name_filter_mask(frame["Table Name"], table_name, match_mode)
        mask &= _name_filter_mask(frame["Object Name"], object_name, match_mode)

        if not _is_blank_filter(source):
            if "Source (Databricks vs AI)" not in frame.columns:
                raise ValueError(
                    "Preview is missing column 'Source (Databricks vs AI)'. "
                    f"Columns present: {list(frame.columns)}"
                )
            want = _key(_source_label(source))
            mask &= frame["Source (Databricks vs AI)"].map(
                lambda v: _key(_source_label(v)) == want
            )

        filtered = frame.loc[mask].reset_index(drop=True)
        keep = [c for c in PREVIEW_COLUMNS if c in filtered.columns]
        filtered = filtered[keep] if keep else filtered

        print(f"Filtered preview: {len(filtered)} row(s).")
        if filtered.empty:
            print(
                "No preview rows matched the filters. "
                f"Searched {searched} preview row(s)."
            )
        return filtered
    except Exception as exc:
        print(f"filter_preview_for_update failed: {type(exc).__name__}: {exc}")
        raise


def _repr_synonym_list(syns) -> str:
    if syns is None:
        return "None"
    if not isinstance(syns, (list, tuple)):
        syns = _parse_synonyms(syns, limit=None)
    return "[" + ", ".join(repr(s) for s in syns) + "]"


def _format_single_update_call(args: dict) -> str:
    syns_fmt = _repr_synonym_list(args.get("new_synonyms"))
    return (
        "update_proposed_metadata(\n"
        f"    object_name={args['object_name']!r},\n"
        f"    new_desc={args['new_desc']!r},\n"
        f"    new_synonyms={syns_fmt},\n"
        f"    table_name={args['table_name']!r},\n"
        f"    object_type={args['object_type']!r},\n"
        ")"
    )


def _format_bulk_update_call(records: list) -> str:
    if not records:
        return "update_proposed_metadata(updates=[])"
    chunks = []
    for args in records:
        syns_fmt = _repr_synonym_list(args.get("new_synonyms"))
        chunks.append(
            "    {\n"
            f"        \"object_name\": {args['object_name']!r},\n"
            f"        \"table_name\": {args['table_name']!r},\n"
            f"        \"object_type\": {args['object_type']!r},\n"
            f"        \"new_desc\": {args['new_desc']!r},\n"
            f"        \"new_synonyms\": {syns_fmt},\n"
            "    }"
        )
    return "update_proposed_metadata(updates=[\n" + ",\n".join(chunks) + ",\n])"


def format_update_calls(
    filtered_df,
    new_desc=None,
    new_synonyms=None,
) -> list:
    """Copy-pasteable update_proposed_metadata calls for filtered rows.

    Primary format is one bulk update_proposed_metadata(updates=[...]) snippet,
    followed by the per-row single-object calls.

    new_desc / new_synonyms None → use that row's Proposed Description / Synonyms.
    Proposed Synonyms may be a list or a comma-separated string.
    Always prints a no-match line when the frame is empty.
    """
    if filtered_df is None or getattr(filtered_df, "empty", True):
        print("No preview rows matched the filters.")
        return []
    records = []
    per_row = []
    for idx, row in filtered_df.iterrows():
        try:
            args = _preview_row_update_args(row, new_desc, new_synonyms)
            syns = args["new_synonyms"]
            if not isinstance(syns, (list, tuple)):
                syns = _parse_synonyms(syns, limit=None)
            args = dict(args)
            args["new_synonyms"] = syns
            records.append(args)
            per_row.append(_format_single_update_call(args))
        except Exception as exc:
            print(
                f"format_update_calls skipped row {idx}: "
                f"{type(exc).__name__}: {exc}"
            )
    if not records:
        print("No preview rows matched the filters.")
        return []
    return [_format_bulk_update_call(records), *per_row]


def apply_preview_updates(
    filtered_df,
    new_desc=None,
    new_synonyms=None,
    apply: bool = False,
) -> pd.DataFrame:
    """Optionally run update_proposed_metadata for every filtered preview row.

    apply=False leaves proposed state unchanged and returns filtered_df.
    apply=True writes proposed state via updates= on the session engine
    (continue-on-error; prints Updated N / Failed M).
    """
    if filtered_df is None or getattr(filtered_df, "empty", True):
        print("No preview rows matched the filters. Nothing to update.")
        return filtered_df if filtered_df is not None else pd.DataFrame(columns=list(PREVIEW_COLUMNS))
    if not apply:
        return filtered_df

    updates = filtered_df
    if new_desc is not None or new_synonyms is not None:
        updates = []
        for _, row in filtered_df.iterrows():
            rec = row.to_dict()
            if new_desc is not None:
                rec["new_desc"] = new_desc
            if new_synonyms is not None:
                rec["new_synonyms"] = new_synonyms
            updates.append(rec)
    return get_engine().update_proposed_metadata(updates=updates)