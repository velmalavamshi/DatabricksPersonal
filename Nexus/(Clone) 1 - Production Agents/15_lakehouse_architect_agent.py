# Databricks notebook source
# DBTITLE 1,Lakehouse Architect Agent
# MAGIC %md
# MAGIC # Agent 15 — Lakehouse Architect
# MAGIC
# MAGIC **Purpose:** Design enterprise Lakehouse solutions with Medallion Architecture, Data Mesh domains, and Unity Catalog governance.
# MAGIC
# MAGIC **Output:** LakehouseArchitecture.md, DataDomainModel.md, MedallionDesign.md, GovernanceFramework.md

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Catalog Discovery — existing layers
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Catalog Discovery
# Scan Gold/Platinum/Silver for existing facts, dims, and bridges.
# gather_catalog_context() is defined in 00_agent_config — inherited via %run.
# Local _scan_existing_layers() below is kept for reference but no longer called.
# ══════════════════════════════════════════════════════════════════════════════

def _scan_existing_layers(max_per_type: int = 25) -> str:
    """
    Scan mde_dev gold/platinum/silver for existing tables, classified by type.
    Returns a formatted string injected into the LLM prompt for reuse analysis.
    """
    try:
        rows = spark.sql(f"""
            SELECT
                table_schema                                            AS layer,
                table_name,
                CASE
                    WHEN LOWER(table_name) LIKE 'fact_%'
                      OR LOWER(table_name) LIKE 'fct_%' THEN 'FACT'
                    WHEN LOWER(table_name) LIKE 'dim_%'  THEN 'DIM'
                    WHEN LOWER(table_name) LIKE 'bridge_%'
                      OR LOWER(table_name) LIKE 'br_%'  THEN 'BRIDGE'
                    WHEN LOWER(table_name) LIKE 'agg_%'  THEN 'AGG'
                    ELSE 'OTHER'
                END                                                     AS table_type,
                COALESCE(comment, '')                                   AS tbl_comment
            FROM {CATALOG}.information_schema.tables
            WHERE table_schema IN ('gold', 'platinum', 'silver')
              AND table_type IN ('MANAGED', 'VIEW')
              -- Exclude dev artifacts: backups, temp tables, test copies
              AND NOT REGEXP_LIKE(table_name, '_(bkp|bk|tmp|temp|test)[0-9]*
        """).collect()

        if not rows:
            return "No existing tables found."

        sections = []
        for layer in ('platinum', 'gold', 'silver'):
            lrows = [r for r in rows if r['layer'] == layer]
            if not lrows:
                continue
            by_type = {}
            for r in lrows:
                by_type.setdefault(r['table_type'], []).append(r)
            lines = [f"\n### {layer.upper()} ({len(lrows)} total)"]
            for ttype in ('FACT', 'DIM', 'BRIDGE', 'AGG', 'OTHER'):
                bucket = by_type.get(ttype, [])
                if not bucket:
                    continue
                lines.append(f"\n**{ttype}s** ({len(bucket)}):")
                for r in bucket[:max_per_type]:
                    note = f" — {r['tbl_comment'][:80]}" if r['tbl_comment'] else ""
                    lines.append(f"  - {CATALOG}.{layer}.{r['table_name']}{note}")
                if len(bucket) > max_per_type:
                    lines.append(f"  … +{len(bucket) - max_per_type} more")
            sections.append("\n".join(lines))

        result = "\n".join(sections)
        facts = sum(1 for r in rows if r['table_type'] == 'FACT')
        dims  = sum(1 for r in rows if r['table_type'] == 'DIM')
        print(f"✅ Layer scan: {len(rows)} objects ({facts} facts, {dims} dims) across platinum/gold/silver")
        return result

    except Exception as e:
        print(f"⚠️ Layer scan failed: {e}")
        return f"[Layer scan unavailable: {e}]"


# Use canonical implementation from 00_agent_config
catalog_ctx = gather_catalog_context()
print(f"   Catalog context ready ({len(catalog_ctx):,} chars)"))
              AND NOT REGEXP_LIKE(table_name, '_[0-9]{8}
        """).collect()

        if not rows:
            return "No existing tables found."

        sections = []
        for layer in ('platinum', 'gold', 'silver'):
            lrows = [r for r in rows if r['layer'] == layer]
            if not lrows:
                continue
            by_type = {}
            for r in lrows:
                by_type.setdefault(r['table_type'], []).append(r)
            lines = [f"\n### {layer.upper()} ({len(lrows)} total)"]
            for ttype in ('FACT', 'DIM', 'BRIDGE', 'AGG', 'OTHER'):
                bucket = by_type.get(ttype, [])
                if not bucket:
                    continue
                lines.append(f"\n**{ttype}s** ({len(bucket)}):")
                for r in bucket[:max_per_type]:
                    note = f" — {r['tbl_comment'][:80]}" if r['tbl_comment'] else ""
                    lines.append(f"  - {CATALOG}.{layer}.{r['table_name']}{note}")
                if len(bucket) > max_per_type:
                    lines.append(f"  … +{len(bucket) - max_per_type} more")
            sections.append("\n".join(lines))

        result = "\n".join(sections)
        facts = sum(1 for r in rows if r['table_type'] == 'FACT')
        dims  = sum(1 for r in rows if r['table_type'] == 'DIM')
        print(f"✅ Layer scan: {len(rows)} objects ({facts} facts, {dims} dims) across platinum/gold/silver")
        return result

    except Exception as e:
        print(f"⚠️ Layer scan failed: {e}")
        return f"[Layer scan unavailable: {e}]"


# Use canonical implementation from 00_agent_config
catalog_ctx = gather_catalog_context()
print(f"   Catalog context ready ({len(catalog_ctx):,} chars)"))
              AND table_name NOT LIKE '%_tmp%'
              AND table_name NOT LIKE '%_temp%'
            ORDER BY table_schema, table_type, table_name
        """).collect()

        if not rows:
            return "No existing tables found."

        sections = []
        for layer in ('platinum', 'gold', 'silver'):
            lrows = [r for r in rows if r['layer'] == layer]
            if not lrows:
                continue
            by_type = {}
            for r in lrows:
                by_type.setdefault(r['table_type'], []).append(r)
            lines = [f"\n### {layer.upper()} ({len(lrows)} total)"]
            for ttype in ('FACT', 'DIM', 'BRIDGE', 'AGG', 'OTHER'):
                bucket = by_type.get(ttype, [])
                if not bucket:
                    continue
                lines.append(f"\n**{ttype}s** ({len(bucket)}):")
                for r in bucket[:max_per_type]:
                    note = f" — {r['tbl_comment'][:80]}" if r['tbl_comment'] else ""
                    lines.append(f"  - {CATALOG}.{layer}.{r['table_name']}{note}")
                if len(bucket) > max_per_type:
                    lines.append(f"  … +{len(bucket) - max_per_type} more")
            sections.append("\n".join(lines))

        result = "\n".join(sections)
        facts = sum(1 for r in rows if r['table_type'] == 'FACT')
        dims  = sum(1 for r in rows if r['table_type'] == 'DIM')
        print(f"✅ Layer scan: {len(rows)} objects ({facts} facts, {dims} dims) across platinum/gold/silver")
        return result

    except Exception as e:
        print(f"⚠️ Layer scan failed: {e}")
        return f"[Layer scan unavailable: {e}]"


# Use canonical implementation from 00_agent_config
catalog_ctx = gather_catalog_context()
print(f"   Catalog context ready ({len(catalog_ctx):,} chars)")

# COMMAND ----------

# DBTITLE 1,Load Hologic canonical DDL standards
# ══════════════════════════════════════════════════════════════════════════════
# CANONICAL HOLOGIC DDL STANDARDS
# Fetched live from production tables — LLM must pattern-match against these.
# Canonical tables: dim_customeraccount (SCD dim), fact_ap_invoice (transactional fact)
# ══════════════════════════════════════════════════════════════════════════════

def get_hologic_canonical_standards() -> str:
    """
    Fetch DDL from canonical production Hologic gold tables.
    Returns a markdown string with DDL that the LLM must treat as the
    MANDATORY Hologic standard — PascalCase columns, dl_* audit, CLUSTER BY AUTO, zstd.
    """
    canonical_tables = [
        f"{CATALOG}.gold.dim_customeraccount",   # Canonical SCD dimension
        f"{CATALOG}.gold.fact_ap_invoice",       # Canonical transactional fact
    ]
    parts = ["## CANONICAL HOLOGIC DDL (production) — FOLLOW THESE PATTERNS EXACTLY"]
    for tbl in canonical_tables:
        try:
            ddl = spark.sql(f"SHOW CREATE TABLE {tbl}").collect()[0][0]
            # Keep full column section + CLUSTER BY; standardise TBLPROPERTIES block
            tbl_props_idx = ddl.find("TBLPROPERTIES")
            if tbl_props_idx > 0:
                ddl_short = ddl[:tbl_props_idx] + "TBLPROPERTIES (\n  'delta.autoOptimize.autoCompact' = 'true',\n  'delta.autoOptimize.optimizeWrite' = 'true',\n  'delta.parquet.compression.codec' = 'zstd',\n  'delta.enableDeletionVectors' = 'true',\n  'delta.enableRowTracking' = 'true',\n  'delta.checkpointPolicy' = 'v2')"
            else:
                ddl_short = ddl
            parts.append(f"\n### {tbl}\n```sql\n{ddl_short}\n```")
        except Exception as e:
            parts.append(f"\n### {tbl}\n  [Schema read failed: {e}]")
    return "\n".join(parts)

HOLOGIC_CANONICAL_STANDARDS = get_hologic_canonical_standards()
print(f"✅ Canonical Hologic DDL loaded ({len(HOLOGIC_CANONICAL_STANDARDS)} chars)")
print("   Key patterns: PascalCase columns | dl_* audit | CLUSTER BY AUTO | FLOAT amounts | zstd+deletionVectors")

# COMMAND ----------

# DBTITLE 1,Lakehouse Architect execution
LAKEHOUSE_PROMPT = """You are a Lakehouse Architect at Hologic. Design the Lakehouse architecture:

1. MEDALLION DESIGN - Bronze/Silver/Gold/Platinum layer specifics
2. DATA DOMAINS - logical domains (Finance, Supply Chain, HR, Sales, Quality)
3. UNITY CATALOG STRUCTURE - catalog.schema.table naming
4. INGESTION PATTERNS - batch vs streaming, CDC strategy per source
5. GOVERNANCE FRAMEWORK - ownership, access policies, PII handling
6. NAMING STANDARDS - table, column, view conventions
7. DATA PRODUCT STRATEGY - how Gold/Platinum serves consumers

Existing environment:
- Catalog: mde_dev / mde_uat / mde_prd
- Sources: Oracle EBS (1,263 obj), Salesforce (768), ASCP (238), HCM (147)
- Current: 95% of Silver = views, 64% of Gold = views
- SK pattern: xxhash64(CONCAT_WS('|', key_cols))
- Audit cols FACTS: dl_rowhash STRING, dl_creation_date_time TIMESTAMP, dl_last_updated_date_time TIMESTAMP
- Audit cols DIMS: dl_iscurrent BOOLEAN, dl_recordstartdateutc TIMESTAMP, dl_recordenddateutc TIMESTAMP, dl_transform_id INT, dl_rowhash STRING
- NEVER generate etl_load_datetime / etl_source_system / etl_batch_id — not the Hologic standard
- Column naming: PascalCase (CustomerAccount_SK, Invoice_ID, AccountingDate) — NEVER snake_case
- SK type: STRING. Pattern: xxhash64(CONCAT_WS('|', business_keys)) AS EntityName_SK
- Clustering: CLUSTER BY AUTO only — NEVER CLUSTER BY (col1, col2) with explicit columns
- TBLPROPERTIES on all tables: delta.autoOptimize.autoCompact=true, delta.autoOptimize.optimizeWrite=true, delta.parquet.compression.codec=zstd, delta.enableDeletionVectors=true, delta.enableRowTracking=true, delta.checkpointPolicy=v2
- PRIMARY KEY constraint on grain SK: CONSTRAINT <table>_pk PRIMARY KEY (<GrainSK>)
- Data types: FLOAT for amounts/quantities, BIGINT for IDs, STRING for codes, BOOLEAN for flags
"""

try:
    REQ_INPUT = dbutils.widgets.get("requirement")
except:
    REQ_INPUT = get_latest_agent_output("solution_architect", "architecture_document") or "Design a complete Lakehouse architecture for the Hologic data platform."

run_id = generate_run_id()
result = call_agent(
    "data_engineer",
    LAKEHOUSE_PROMPT,
    f"""## Canonical Hologic DDL Standards — FOLLOW EXACTLY (from production tables)
{HOLOGIC_CANONICAL_STANDARDS}

## Design Request
{REQ_INPUT}

## Existing Catalog State (mde_dev — live scan)
Review before proposing any layer structures or domain models.
Recommend REUSE or EXTENSION of existing objects. Propose net-new only for genuine gaps.
Note: This scan excludes _bkp, _tmp, _temp dev artifacts — production tables only.
{catalog_ctx}""",
    max_tokens=4096
)
save_agent_output("lakehouse_architect", run_id, "lakehouse_design", result, {})
print(result)
print(f"\n✅ Agent 15 (Lakehouse Architect) completed | Run ID: {run_id}")