# Hologic Canonical Notebook Templates

> **Purpose:** Reference patterns for all code-generating agents. Every new Gold/Platinum/Dim notebook MUST follow these structures.
> **Source:** Derived from production notebooks in `/HDA_MDE/DataPlane/Databricks/src/Workspace/DataEngineering/`
> **Last Updated:** 2026-09-22 — corrected SK formula + medallion-read bug found live-generating `fact_change_order`, `fact_change_p2p3`, and `platinum_agg_ap_vendor_working_capital` under `xxhash64` (see CORRECTION note below)

---

## ⚠️ CORRECTION (2026-09-22) — SK formula was wrong in this file since inception

This file previously said the SK standard was "migrating to xxHash64" and told every code-generating
agent to NEVER use MD5. That was never true in real production — every real, committed HDA_MDE
notebook (`fact_receiving.sql`, `fact_opm_subledger.py`, `dim_opmformula.sql`, and every other live
Gold/Platinum object) uses `md5(concat_ws('|', ...))`, confirmed against `hologic-databricks-standards`
(HDA_MDE.wiki page 258) and against `LakehouseUtilities.py` directly. There is no active migration.
**The real standard is `md5(concat_ws('|', <natural key columns in order>))` — full stop.** The
`xxhash64` guidance below (Templates 1/2, the Naming Conventions table, and the old Anti-Patterns
entry) already propagated into real generated output — `fact_change_order`, `fact_change_p2p3`, and
`platinum_agg_ap_vendor_working_capital` in `NEXUS_Generated/` all materialized SKs with `xxhash64`
before this fix. Those existing generated notebooks are flagged, not yet remediated — see the ADO
follow-up note at the bottom of this file.

## Architecture: View-First Materialization Pattern

All Hologic Gold/Platinum tables use a **two-step pattern**:
1. **Transient View** — `CREATE OR REPLACE VIEW` with business logic + TBLPROPERTIES config
2. **Processor Class** — `FactProcessor` or `DimensionProcessor` reads the view, materializes as Delta table with audit columns, SK generation, CLUSTER BY AUTO, and PK constraint

The processor classes (in `LakehouseUtilities`) handle:
- Delta table creation/merge (CTAS on first run, MERGE on incremental)
- `dl_*` audit column injection
- SK column generation — **`md5(concat_ws('|', ...))`. Never `xxhash64`/`sha1`/`sha256` — see the
  CORRECTION note above.**
- CLUSTER BY AUTO application
- PRIMARY KEY constraint
- Companion `v_pbi_*` view for Power BI consumption

## ⚠️ MEDALLION READ RULE — enforced, not optional

**Gold reads Silver only. Platinum reads Gold only.** A Gold notebook reading a `stg_*`/Bronze
table directly, or a Platinum notebook reading Silver directly, is a real, previously-confirmed bug
in this program — do not template it, do not generate it. If a genuinely needed Silver view doesn't
exist yet, generate the Silver view first (or state the gap explicitly as a flagged, tracked
exception in the notebook) — never silently join to `stg_*`/Bronze from a Gold or Platinum
transient view.

---

## Template 1: Gold Fact Table

**Source:** `fact_opm_subledger` (ID: 1370838525524959)

```python
# Cell 1: Widgets
from datetime import datetime, timezone
startTime = datetime.now(timezone.utc)
dbutils.widgets.text("deltaSchemaName", 'gold')
dbutils.widgets.text("deltaTableName", 'fact_<table_name>')
dbutils.widgets.text("storageAccountEndpoint", 'https://hdamdesacdev01.dfs.core.windows.net/')
dbutils.widgets.text("catalogName", 'mde_dev')
dbutils.widgets.text("transformId", '-1')  # TransformId from statedb
```

```python
# Cell 2: Variables
pSchemaName = dbutils.widgets.get("deltaSchemaName")
pTableName = dbutils.widgets.get("deltaTableName")
pInputSchemaName = 'gold'
pInputTableOrViewName = f"v_{pTableName}"
pContainer = 'gold'
pStorageAccountEndpoint = dbutils.widgets.get("storageAccountEndpoint")
pCatalogName = dbutils.widgets.get("catalogName")
pFolderPath = 'databricks/'
pTransformId = int(dbutils.widgets.get("transformId"))
```

```python
# Cell 3: Shared Utilities
%run ../../LakehouseUtilities
```

```python
# Cell 4: Catalog Context
spark.catalog.setCurrentCatalog(pCatalogName)
```

```sql
-- Cell 5: Transient View (BUSINESS LOGIC GOES HERE)
CREATE OR REPLACE VIEW gold.v_fact_<table_name>
TBLPROPERTIES (
  'config.sk_column_name' = '<Grain>_SK',
  'config.nk_column_names' = '<NaturalKey1>,<NaturalKey2>',
  'config.cluster_by' = '<ClusterCol1>,<ClusterCol2>,<DateCol>',
  'config.fact_type' = 1,
  'config.primary_key' = '<Grain>_SK',
  'config.foreign_key' = ''
)
AS
SELECT
  -- Surrogate Key (Hologic standard: md5)
  md5(concat_ws('|', <nk_col1>, <nk_col2>)) AS <Grain>_SK,

  -- Foreign Keys to Dimensions
  md5(concat_ws('|', <dim_nk>)) AS <Dim>_SK,

  -- Natural Keys & Attributes
  src.Column1,
  src.Column2,

  -- Measures
  src.Amount,
  src.Quantity

FROM silver.<source_view_or_table> src
LEFT JOIN gold.<dim_table> d ON src.Key = d.Key
```

```python
# Cell 6: FactProcessor
fact = FactProcessor(
    schema_name=pSchemaName,
    table_name=pTableName,
    input_schema_name=pInputSchemaName,
    input_view_or_table_name=pInputTableOrViewName,
    delta_path=f"abfss://{pContainer}@{pStorageAccountEndpoint.replace('https://','')}{pFolderPath}{pTableName}",
    transform_id=pTransformId,
)
```

```python
# Cell 7: Execute
try:
    fact.process()
except Exception as e:
    LakeOrchestrator.exit_with_status(success=False, startTime=startTime, message=str(e))
```

```python
# Cell 8: Exit
LakeOrchestrator.exit_with_status(success=True, startTime=startTime)
```

**Key config.fact_type values:**
- `1` = Standard fact (CTAS/full replace)
- `2` = Incremental fact (MERGE by SK)

---

## Template 2: Gold Dimension Table

**Source:** `dim_customersite` (ID: 1012341636191053)

```python
# Cell 1: Widgets
from datetime import datetime, timezone
startTime = datetime.now(timezone.utc)
dbutils.widgets.text("deltaSchemaName", 'gold')
dbutils.widgets.text("deltaTableName", 'dim_<table_name>')
dbutils.widgets.text("storageAccountEndpoint", 'https://hdamdesacdev01.dfs.core.windows.net/')
dbutils.widgets.text("catalogName", 'mde_dev')
dbutils.widgets.text("transformId", '-1')
```

```python
# Cell 2: Variables
pDimSchemaName = dbutils.widgets.get("deltaSchemaName")
pDimTableName = dbutils.widgets.get("deltaTableName")
pInputSchemaName = 'gold'
pInputTableOrViewName = f"v_{pDimTableName}"
pDimContainer = 'gold'
pStorageAccountEndpoint = dbutils.widgets.get("storageAccountEndpoint")
pCatalogName = dbutils.widgets.get("catalogName")
pDimFolderPath = 'databricks/'
pTransformId = int(dbutils.widgets.get("transformId"))
```

```sql
-- Cell 5: Dimension View (BUSINESS LOGIC)
CREATE OR REPLACE VIEW gold.v_dim_<table_name>
TBLPROPERTIES (
  'config.nk_column_names' = '<NaturalKey>_ID',
  'config.sk_column_name' = '<Dim>_SK',
  'config.cluster_by' = '<Dim>_SK,<NaturalKey>_ID',
  'config.dim_type' = 1,
  'config.primary_key' = '<Dim>_SK',
  'config.foreign_key' = ''
)
AS
SELECT
  -- Natural Key
  src.<NaturalKey>_ID,

  -- Surrogate Key (Hologic standard: md5)
  md5(concat_ws('|', src.<NaturalKey>_ID)) AS <Dim>_SK,

  -- Descriptive Attributes (PascalCase)
  src.AttributeName,
  src.StatusFlag,
  src.CategoryCode,

  -- Foreign Keys to other dims
  md5(concat_ws('|', src.<OtherDim>_ID)) AS <OtherDim>_SK

-- MEDALLION READ RULE: Gold reads Silver ONLY — never stg_*/Bronze directly.
-- If no Silver view exists yet for this source, build it first (see MEDALLION READ RULE above).
FROM silver.v_mst_<source_system>_<source_table> src
LEFT JOIN <other_joins>
```

```python
# Cell 6: DimensionProcessor
dim = DimensionProcessor(
    schema_name=pDimSchemaName,
    table_name=pDimTableName,
    input_schema_name=pInputSchemaName,
    input_view_or_table_name=pInputTableOrViewName,
    delta_path=f"abfss://{pDimContainer}@{pStorageAccountEndpoint.replace('https://','')}{pDimFolderPath}{pDimTableName}",
    transform_id=pTransformId,
)
```

```python
# Cell 7: Execute
try:
    dim.process()
except Exception as e:
    LakeOrchestrator.exit_with_status(success=False, startTime=startTime, message=str(e))
```

**Key config.dim_type values:**
- `1` = SCD Type 1 (overwrite)
- `2` = SCD Type 2 (history: dl_iscurrent, dl_recordstartdateutc, dl_recordenddateutc)

**DimensionProcessor auto-adds these audit columns:**
- `dl_iscurrent BOOLEAN`
- `dl_recordstartdateutc TIMESTAMP`
- `dl_recordenddateutc TIMESTAMP`
- `dl_transform_id INT`
- `dl_rowhash STRING`

---

## Template 3: Platinum Table (Cross-Domain)

**Source:** `fact_job_application_event_plt` (ID: 1897457470711405)

Platinum = cross-domain mashups that join multiple Gold tables for specific reporting needs.

```python
# Key differences from Gold:
pSchemaName = 'platinum'
pContainer = 'platinum'
pInputSchemaName = 'platinum'

# For secure catalog (HR data):
pStorageAccountEndpoint += 'secure/'
pCatalogName += '_secure'
```

```sql
-- Platinum views read FROM gold tables (already materialized)
CREATE OR REPLACE VIEW platinum.v_fact_<name>_plt
TBLPROPERTIES (
  'config.nk_column_names' = '<Grain>_SK',
  'config.sk_column_name' = '<Grain>_SK',
  'config.cluster_by' = '',
  'config.primary_key' = '<Grain>_SK',
  'config.foreign_key' = ''
)
AS
SELECT
  fact.Column1,
  fact.Column2,
  dim.Attribute1,
  dim.dl_iscurrent  -- Pass through SCD columns when filtering on current
FROM gold.<fact_table> fact
LEFT JOIN gold.<dim_table> dim
  ON fact.<Key> = dim.<Key>
  AND dim.dl_iscurrent = true  -- Filter to current dimension records
```

**Platinum naming:** `<entity>_plt` suffix (e.g., `fact_job_application_event_plt`, `dim_itemcost_usd_plt`)

---

## TBLPROPERTIES Config Reference

| Key | Purpose | Example |
|-----|---------|--------|
| `config.sk_column_name` | Surrogate key column name | `'CustomerSite_SK'` |
| `config.nk_column_names` | Natural key(s), comma-separated | `'Site_ID'` or `'Batch_ID,Organization_ID'` |
| `config.cluster_by` | Columns for CLUSTER BY AUTO | `'SK,NK,DateCol'` |
| `config.fact_type` | 1=Full, 2=Incremental | `1` |
| `config.dim_type` | 1=SCD1, 2=SCD2 | `1` |
| `config.primary_key` | PK column (usually = SK) | `'CustomerSite_SK'` |
| `config.foreign_key` | FK relationships (optional) | `''` |

---

## Naming Conventions Summary

| Element | Convention | Example |
|---------|-----------|--------|
| Table (fact) | `fact_<domain>` | `fact_opm_subledger` |
| Table (dim) | `dim_<entity>` | `dim_customersite` |
| Table (platinum) | `<type>_<entity>_plt` | `fact_job_application_event_plt` |
| Transient view | `v_<table_name>` | `v_fact_opm_subledger` |
| PBI view | `v_pbi_<table_name>` | `v_pbi_fact_opm_subledger` |
| Columns | PascalCase-mashed, `_` only right before a final `_ID`/`_SK` | `CustomerSite_SK`, `AccountName` |
| SK formula | `md5(concat_ws('|', <natural keys>))` — never `xxhash64`/`sha1`/`sha256` | |
| SK columns | `<Entity>_SK` (STRING) | `OpmSubledger_SK` |
| NK columns | `<Entity>_ID` (BIGINT) | `Batch_ID`, `Organization_ID` |
| Audit (fact) | `dl_rowhash`, `dl_creation_date_time`, `dl_last_updated_date_time` | |
| Audit (dim) | `dl_iscurrent`, `dl_recordstartdateutc`, `dl_recordenddateutc`, `dl_transform_id`, `dl_rowhash` | |

---

## Anti-Patterns (flag as violations)

- `xxhash64()`/`sha1()`/`sha256()` for SKs in **any** table — the real standard is `md5()`
  (corrected 2026-09-22; this file previously said the opposite — see CORRECTION note up top)
- A Gold transient view reading `stg_*`/Bronze directly, or a Platinum view reading Silver
  directly — medallion read rule violation (Gold reads Silver only, Platinum reads Gold only)
- A new Platinum object without the `_plt` suffix
- `etl_load_datetime`, `etl_source_system`, `etl_batch_id` (wrong standard)
- `PARTITION BY` (use CLUSTER BY AUTO)
- snake_case columns (use PascalCase-mashed, `_` only before `_ID`/`_SK`)
- Hardcoded catalog names (use widget `pCatalogName`)
- SELECT * in production views
- Missing TBLPROPERTIES config keys (all six: `sk_column_name`, `primary_key`, `foreign_key`,
  `unique_constraints`, `not_null_constraints`, `check_constraints`, plus `nk_column_names`/
  `cluster_by`/`fact_type`|`dim_type` — include all of them even when a value is legitimately empty)
- Missing error handling (try/except + LakeOrchestrator.exit_with_status)
- A Gold fact with no real incremental logic (watermark + dirty-batch) — a full recompute every
  run is not acceptable; see `hologic-databricks-standards` skill §4 for the pattern by grain

---

## Open follow-up (not fixed by this correction — needs Sameet)

Three notebooks already live in `NEXUS_Generated/` were generated from this file before the
2026-09-22 correction and materialize SKs with `xxhash64` instead of `md5`:
`fact_change_order`, `fact_change_p2p3` (and its `fact_change_p2p3_fixed` sibling), and
`platinum_agg_ap_vendor_working_capital`. `fact_change_order`'s header also documents reading
`mde_dev.stg_agile.*` directly at the Gold layer (medallion read rule violation — no Silver view
for Agile PLM change data exists yet). None of these three have been remediated as part of this
fix — remediating a live SK formula changes every downstream join/dedup key, which needs an
explicit go-ahead and a real before/after validation pass, not a silent rewrite. Flagged here as a
tracked, open item.
