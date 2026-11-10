# Databricks notebook source
# DBTITLE 1,Solution Architect Agent
# MAGIC %md
# MAGIC # Agent 06 — Solution Architect
# MAGIC
# MAGIC **Purpose:** Generate High-Level Design (HLD) and Low-Level Design (LLD) documents from business requirements, incorporating Hologic's specific Medallion architecture patterns.
# MAGIC
# MAGIC **Capabilities:**
# MAGIC - Produces HLD (system context, data flow, integration points)
# MAGIC - Produces LLD (table designs, column mappings, CDC patterns, SCD strategy)
# MAGIC - Incorporates existing schema context from Unity Catalog
# MAGIC - Validates against enterprise standards (naming, governance, security)
# MAGIC
# MAGIC **Input:** Business requirement + scope document + target source systems
# MAGIC **Output:** Architecture documents stored in `agent_outputs`

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,System prompt and context builders
# ══════════════════════════════════════════════════════════════════════════════
# SOLUTION ARCHITECT AGENT — System Prompt
# ══════════════════════════════════════════════════════════════════════════════

ARCHITECT_SYSTEM_PROMPT = """You are a Principal Solution Architect at Hologic specializing in Databricks Lakehouse design.

You produce enterprise-grade architecture documents following these standards:

## Architecture Principles
1. **Medallion Architecture:** Bronze/Staging (stg_*) → Silver (cleansed, conformed) → Gold (business logic) → Platinum (curated for BI)
2. **Unity Catalog Governance:** All objects in `mde_dev` (DEV), `mde_uat` (UAT), `mde_prd` (PRD)
3. **Surrogate Keys:** xxHash64 ONLY (never MD5). Pattern: `xxhash64(CONCAT_WS('|', natural_key_cols))`
4. **SCD Strategy:** Type 1 default, Type 2 only when business requires historical tracking
5. **Incremental Loading:** MERGE pattern for large tables, CREATE OR REPLACE for small dimensions
6. **Data Quality:** Expectations at every layer boundary

## Source System Knowledge
- **Oracle EBS** (1,263 objects): AP, AR, GL, INV, OM, PO modules. Incremental via LAST_UPDATE_DATE.
- **Salesforce** (768 objects): CDC via SystemModstamp, soft deletes, polymorphic relationships.
- **ASCP** (238 objects): Supply chain planning, snapshot-based, date-bounded validity.
- **Oracle HCM** (147 objects): HR data, sensitive PII, requires masking.
- **Agile PLM** (82 objects): Product lifecycle, hierarchical BOMs.

## Output Format
Produce TWO documents:

### HLD (High-Level Design)
- System Context Diagram (describe in markdown)
- Data Flow Diagram (source → staging → silver → gold → platinum → consumers)
- Integration Points
- Non-Functional Requirements (volume, latency, SLA)
- Security & Governance

### LLD (Low-Level Design)
- Table Designs (columns, types, keys, clustering)
- ETL Patterns (load strategy per table)
- Data Quality Rules
- Error Handling Strategy
- Dependencies & Sequencing

## Hologic Production Standards (MANDATORY — from production DDL, not generic conventions)
- Column naming: **PascalCase — NEVER snake_case**. Examples: CustomerAccount_SK, Invoice_ID, AccountingDate, PaymentStatusFlag, InvoiceCurrencyCode
- SK type: STRING. Pattern: `xxhash64(CONCAT_WS('|', business_key_cols)) AS EntityName_SK STRING COLLATE UTF8_BINARY`
- Audit cols — FACTS: `dl_rowhash STRING`, `dl_creation_date_time TIMESTAMP`, `dl_last_updated_date_time TIMESTAMP`
- Audit cols — DIMS: `dl_iscurrent BOOLEAN`, `dl_recordstartdateutc TIMESTAMP`, `dl_recordenddateutc TIMESTAMP`, `dl_transform_id INT`, `dl_rowhash STRING`
- NEVER use etl_load_datetime / etl_source_system / etl_batch_id — not the Hologic standard
- Clustering: `CLUSTER BY AUTO` only — NEVER `CLUSTER BY (col1, col2)` with explicit columns
- TBLPROPERTIES on all tables: delta.autoOptimize.autoCompact=true, delta.autoOptimize.optimizeWrite=true, delta.parquet.compression.codec=zstd, delta.enableDeletionVectors=true, delta.enableRowTracking=true, delta.checkpointPolicy=v2
- PRIMARY KEY: `CONSTRAINT <table>_pk PRIMARY KEY (<GrainSK>)` on every table
- Data types: FLOAT for amounts/quantities, BIGINT for IDs, STRING for codes, BOOLEAN for is*/has* flags

Be specific to Hologic's environment. Use actual schema names, table patterns, and conventions.
"""


def gather_existing_context(source_system: str) -> str:
    """Pull existing schema info for a source system to inform architecture."""
    try:
        tables = spark.sql(f"""
            SELECT table_name, table_type, 
                   (SELECT COUNT(*) FROM system.information_schema.columns c 
                    WHERE c.table_catalog = t.table_catalog AND c.table_schema = t.table_schema AND c.table_name = t.table_name) as col_count
            FROM system.information_schema.tables t
            WHERE table_catalog = '{CATALOG}' AND table_schema = '{source_system}'
            ORDER BY table_name
            LIMIT 50
        """).collect()
        
        return "\n".join([f"- {r['table_name']} ({r['table_type']}, {r['col_count']} cols)" for r in tables])
    except Exception as e:
        return f"[Could not retrieve schema: {e}]"


def gather_gold_platinum_context() -> str:  # DEPRECATED — use gather_catalog_context() from 00_agent_config
    """
    Scan mde_dev gold/platinum/silver for existing facts, dims, and bridges.

    This is the reuse analysis step. The Solution Architect must check what
    already exists before proposing any new table designs. Output is injected
    directly into the LLM user prompt as a catalog inventory section.

    Returns:
        Formatted string grouped by layer and table type with UC comments.
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
            return "No existing tables found in gold/platinum/silver."

        sections = []
        for layer in ('platinum', 'gold', 'silver'):
            lrows = [r for r in rows if r['layer'] == layer]
            if not lrows:
                continue
            by_type = {}
            for r in lrows:
                by_type.setdefault(r['table_type'], []).append(r)
            lines = [f"\n### {layer.upper()} ({len(lrows)} objects)"]
            for ttype in ('FACT', 'DIM', 'BRIDGE', 'AGG', 'OTHER'):
                bucket = by_type.get(ttype, [])
                if not bucket:
                    continue
                lines.append(f"\n**{ttype}s** ({len(bucket)}):")
                for r in bucket[:25]:
                    note = f" — {r['tbl_comment'][:80]}" if r['tbl_comment'] else ""
                    lines.append(f"  - {CATALOG}.{layer}.{r['table_name']}{note}")
                if len(bucket) > 25:
                    lines.append(f"  … +{len(bucket) - 25} more")
            sections.append("\n".join(lines))

        result = "\n".join(sections)
        facts = sum(1 for r in rows if r['table_type'] == 'FACT')
        dims  = sum(1 for r in rows if r['table_type'] == 'DIM')
        print(f"✅ Gold/Platinum/Silver context: {len(rows)} objects ({facts} facts, {dims} dims)")
        return result

    except Exception as e:
        print(f"⚠️ Catalog scan failed: {e}")
        return f"[Catalog scan unavailable: {e}]"


print("✅ Solution Architect agent loaded"))
              AND NOT REGEXP_LIKE(table_name, '_[0-9]{8}
        """).collect()

        if not rows:
            return "No existing tables found in gold/platinum/silver."

        sections = []
        for layer in ('platinum', 'gold', 'silver'):
            lrows = [r for r in rows if r['layer'] == layer]
            if not lrows:
                continue
            by_type = {}
            for r in lrows:
                by_type.setdefault(r['table_type'], []).append(r)
            lines = [f"\n### {layer.upper()} ({len(lrows)} objects)"]
            for ttype in ('FACT', 'DIM', 'BRIDGE', 'AGG', 'OTHER'):
                bucket = by_type.get(ttype, [])
                if not bucket:
                    continue
                lines.append(f"\n**{ttype}s** ({len(bucket)}):")
                for r in bucket[:25]:
                    note = f" — {r['tbl_comment'][:80]}" if r['tbl_comment'] else ""
                    lines.append(f"  - {CATALOG}.{layer}.{r['table_name']}{note}")
                if len(bucket) > 25:
                    lines.append(f"  … +{len(bucket) - 25} more")
            sections.append("\n".join(lines))

        result = "\n".join(sections)
        facts = sum(1 for r in rows if r['table_type'] == 'FACT')
        dims  = sum(1 for r in rows if r['table_type'] == 'DIM')
        print(f"✅ Gold/Platinum/Silver context: {len(rows)} objects ({facts} facts, {dims} dims)")
        return result

    except Exception as e:
        print(f"⚠️ Catalog scan failed: {e}")
        return f"[Catalog scan unavailable: {e}]"


print("✅ Solution Architect agent loaded"))
              AND table_name NOT LIKE '%_tmp%'
              AND table_name NOT LIKE '%_temp%'
            ORDER BY table_schema, table_type, table_name
        """).collect()

        if not rows:
            return "No existing tables found in gold/platinum/silver."

        sections = []
        for layer in ('platinum', 'gold', 'silver'):
            lrows = [r for r in rows if r['layer'] == layer]
            if not lrows:
                continue
            by_type = {}
            for r in lrows:
                by_type.setdefault(r['table_type'], []).append(r)
            lines = [f"\n### {layer.upper()} ({len(lrows)} objects)"]
            for ttype in ('FACT', 'DIM', 'BRIDGE', 'AGG', 'OTHER'):
                bucket = by_type.get(ttype, [])
                if not bucket:
                    continue
                lines.append(f"\n**{ttype}s** ({len(bucket)}):")
                for r in bucket[:25]:
                    note = f" — {r['tbl_comment'][:80]}" if r['tbl_comment'] else ""
                    lines.append(f"  - {CATALOG}.{layer}.{r['table_name']}{note}")
                if len(bucket) > 25:
                    lines.append(f"  … +{len(bucket) - 25} more")
            sections.append("\n".join(lines))

        result = "\n".join(sections)
        facts = sum(1 for r in rows if r['table_type'] == 'FACT')
        dims  = sum(1 for r in rows if r['table_type'] == 'DIM')
        print(f"✅ Gold/Platinum/Silver context: {len(rows)} objects ({facts} facts, {dims} dims)")
        return result

    except Exception as e:
        print(f"⚠️ Catalog scan failed: {e}")
        return f"[Catalog scan unavailable: {e}]"


print("✅ Solution Architect agent loaded")

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

# DBTITLE 1,Generate architecture from requirement
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Define requirement (Workflow parameter or default)
# ══════════════════════════════════════════════════════════════════════════════

try:
    REQUIREMENT = dbutils.widgets.get("requirement")
except:
    REQUIREMENT = """Design the architecture for integrating Oracle EBS Accounts Payable (AP) data 
    into the Lakehouse. Include: AP Invoices, AP Invoice Lines, AP Payments, AP Suppliers.
    The Gold layer should support a Payables Aging report and Supplier Spend Analysis.
    Expected volume: 5M invoices, 20M invoice lines, growing at 500K invoices/year."""

try:
    SOURCE_SYSTEM = dbutils.widgets.get("source_system")
except:
    SOURCE_SYSTEM = "stg_oracle_ebs"

print(f"Requirement: {REQUIREMENT[:200]}...")
print(f"Source system: {SOURCE_SYSTEM}")

# ── Source schema context (inputs for this architecture)
existing_tables = gather_existing_context(SOURCE_SYSTEM)
print(f"\nExisting source tables in {SOURCE_SYSTEM}: {len(existing_tables.splitlines())} found")

# ── Gold/Platinum/Silver reuse context (existing dims/facts to extend or reuse)
# gather_catalog_context() is the canonical function — defined in 00_agent_config, inherited via %run
catalog_ctx = gather_catalog_context()

# COMMAND ----------

# DBTITLE 1,Generate HLD and LLD
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Generate architecture documents
# ══════════════════════════════════════════════════════════════════════════════

run_id = generate_run_id()

user_prompt = f"""## Canonical Hologic DDL Standards — FOLLOW EXACTLY (from production tables)
{HOLOGIC_CANONICAL_STANDARDS}

## Business Requirement
{REQUIREMENT}

## Source System: {SOURCE_SYSTEM}
### Existing Tables in this schema:
{existing_tables}

## Existing Conformed Dimensions & Facts (Reuse Analysis)
BEFORE proposing any new tables, check if existing structures satisfy this requirement.
Recommend REUSE or EXTENSION of existing objects wherever possible. Only propose
NET-NEW builds for genuine gaps:
{catalog_ctx}

## Target Environment
- Catalog: mde_dev (DEV), mde_uat (UAT), mde_prd (PRD)
- Silver schema: silver
- Gold schema: gold
- Platinum schema: platinum

## Constraints
- Must use xxHash64 for surrogate keys (STRING type, PascalCase SK name)
- Audit cols FACTS: dl_rowhash, dl_creation_date_time, dl_last_updated_date_time — NEVER etl_load_datetime
- Audit cols DIMS: dl_iscurrent, dl_recordstartdateutc, dl_recordenddateutc, dl_transform_id, dl_rowhash
- Column naming: PascalCase — NEVER snake_case
- Must support incremental loading via MERGE
- Must include data quality expectations at Silver→Gold boundary
- Clustering: CLUSTER BY AUTO — NOT CLUSTER BY (col1, col2)
- TBLPROPERTIES: standard block (autoOptimize, zstd, deletionVectors, rowTracking, v2Checkpoint)
- PRIMARY KEY constraint on grain SK column

Generate the complete HLD and LLD documents."""

architecture = call_agent(
    "data_engineer",  # Using critical model for architecture
    ARCHITECT_SYSTEM_PROMPT, 
    user_prompt, 
    temperature=0.2, 
    max_tokens=4096
)

print(architecture)

# COMMAND ----------

# DBTITLE 1,Save architecture and validate
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Save and validate
# ══════════════════════════════════════════════════════════════════════════════

save_agent_output(
    agent_name="solution_architect",
    run_id=run_id,
    output_type="architecture_document",
    content=architecture,
    metadata={
        "requirement": REQUIREMENT[:500],
        "source_system": SOURCE_SYSTEM,
        "doc_type": "HLD+LLD"
    }
)

# Validate key elements are present
validation_checks = {
    "Contains HLD section": "hld" in architecture.lower() or "high-level" in architecture.lower(),
    "Contains LLD section": "lld" in architecture.lower() or "low-level" in architecture.lower(),
    "References xxHash64": "xxhash64" in architecture.lower(),
    "References dl_* audit cols": "dl_rowhash" in architecture or "dl_creation_date_time" in architecture,
    "No etl_* audit cols (non-Hologic)": "etl_load_datetime" not in architecture,
    "References Medallion layers": "silver" in architecture.lower() and "gold" in architecture.lower(),
    "Includes data quality": "quality" in architecture.lower() or "expectation" in architecture.lower(),
    "Includes incremental strategy": "merge" in architecture.lower() or "incremental" in architecture.lower(),
}

print("\nArchitecture Validation:")
print("-" * 50)
for check, passed in validation_checks.items():
    print(f"  {'✅' if passed else '❌'} {check}")

print(f"\n✅ Agent 06 (Solution Architect) completed | Run ID: {run_id}")