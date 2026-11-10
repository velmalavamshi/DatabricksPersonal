# Metric Views

Certified, reusable business metrics on top of the `gold`/`platinum` layer, built as native Unity Catalog
**Metric Views** and served to Power BI (and Genie, dashboards, SQL editor, etc.) from a new **`semantic`**
schema. This replaces one-off DAX measures rebuilt in every report with a single governed definition.

## Why this exists

Today Power BI reads `gold`/`platinum` tables through their `v_pbi_*` aliased views, and every report author
re-derives their own totals, ratios, and time-intelligence in DAX. That means the same "Total Revenue" can be
defined three different ways across three workbooks. A metric view defines the dimensions and measures once,
in Unity Catalog, and every consumer - Power BI, Genie, SQL, another metric view - gets the same numbers. 

## Where things live

| Path | Purpose |
|---|---|
| `LakehouseUtilities.py` | `MetricViewProcessor` class (new) alongside the existing `DimensionProcessor` / `FactProcessor` / `PlatinumProcessor` |
| `MetricViews/create_semantic_schema.sql` | One-time, per-environment bootstrap of the `semantic` schema |
| `MetricViews/_template_metric_view.sql` | Copy this to start a new metric view |
| `MetricViews/example_mv_sales_order_item.sql` | A filled-in worked example to read alongside the template |

## The `semantic` schema

One new Unity Catalog schema per catalog/environment (`mde_dev.semantic`, `mde_uat.semantic`, `mde_prd.semantic`),
sitting next to `bronze`/`silver`/`gold`/`platinum`. It holds **only** metric view objects - no physical tables.
An admin runs `create_semantic_schema.sql` once per environment before the first metric view is deployed there
(or the first deploy creates it automatically - see below). 

## How a metric view is different from a dimension/fact/platinum table

| | Dimension / Fact / Platinum | Metric View |
|---|---|---|
| Storage | Physical Delta table (CTAS/MERGE) | Virtual - a view definition only |
| Freshness | As of the last job run | Always current - evaluated at query time |
| `db_control_table` / `pbi_control_table` | Required for incremental facts | Not used - nothing to schedule |
| `dl_iscurrent`, `dl_rowhash`, audit columns | Yes | No |
| How Power BI reads it | The `v_pbi_*` aliased view | The metric view itself, via `MEASURE()` |

Because a metric view is virtual, deploying one is much lighter than a fact/dimension build: create (or replace)
the view, apply grants, done. There's no merge, no clustering, no vacuum, no incremental watermark.

## Developer workflow: adding a new metric view

1. **Pick a certified source.** Build only from `gold`/`platinum` tables (or another metric view) - never
   straight from `silver`/bronze staging. If the metric doesn't exist as a clean `platinum` fact yet, build
   that first using the normal `PlatinumProcessor` pattern.
2. **Copy the template.** `cp MetricViews/_template_metric_view.sql MetricViews/mv_<domain>_<subject>.sql`
   (e.g. `mv_service_contract_performance.sql`). Naming: lowercase, snake_case, `mv_` prefix - same convention
   as `dim_`/`fact_`.
3. **Fill in the YAML**: `source`, any `joins` to dimension tables, `fields` (dimensions, with business-friendly
   `display_name`s and coded values translated to labels), and `measures` (simple aggregates first, then
   derived ratios built from those). Give every measure a `comment` - that's what makes it "certified" instead
   of just another view.
4. **Request grants.** Ask a platform admin to add a row to `main.governance.grants` for the new object
   (`schema_name='semantic'`, `securable_type='VIEW'`, `object_name='mv_...'`, plus the Power BI principal /
   consumer group). `MetricViewProcessor.apply_grants()` (called automatically by the notebook) reads that
   table the same way `DimensionProcessor`/`FactProcessor`/`PlatinumProcessor` already do - no grant row means
   no access, even after a successful deploy.
5. **Run the notebook.** It creates the `semantic` schema if needed, deploys the view, validates it exists,
   and applies grants.
6. **Smoke-test it** (metric views don't support `SELECT *` or bare aggregation - every measure must go through
   `MEASURE()`, with `GROUP BY ALL`):
   ```sql
   SELECT `Some Dimension`, MEASURE(`Total Amount`)
   FROM semantic.mv_your_view_name
   GROUP BY ALL
   ```
7. **Add it to the job/orchestration** the same way `UpdateDimensionViews.py` chains dimension notebooks with
   `%run`, if it needs to be redeployed on a schedule (e.g. because the YAML changes, or as part of environment
   promotion dev -> uat -> prd).

## Connecting Power BI

- Use the standard **Databricks Power BI connector**, in **DirectQuery** mode, with the **Native Query** option
  enabled. Import mode and the connector's plain point-and-click query builder do not work against metric
  views - only a native SQL query does.
- Every measure reference in that native query must use `MEASURE(...)`, and the query needs `GROUP BY ALL`
  (metric views also don't support `SELECT *`). Example:
  ```sql
  SELECT `Order Month`, `Item Division`, MEASURE(`Order Line Amount`)
  FROM mde_prd.semantic.mv_sales_order_item
  GROUP BY ALL
  ```
- **The Power BI connector's "Metric View BI Compatibility Mode" option has been removed** - don't rely on it.
  Check the current Databricks partner docs for Power BI before building reports, since this area is still
  evolving: [Query metric views in Power BI](https://learn.microsoft.com/en-us/azure/databricks/partners/bi/power-bi-metric-views),
  [Use metric views with external BI tools](https://docs.databricks.com/aws/en/uc-semantics/metric-views/bi-tools).
- Report authors will need a short heads-up: this is a different query pattern than the flat `v_pbi_*` tables
  they're used to importing today.

## Requirements / prerequisites to confirm before rolling this out

- **Runtime**: the SQL Warehouse (or DBR cluster) serving Power BI needs **DBR/DBSQL 16.4+** for basic metric
  views, **17.3+** if any view uses `window` measures (trailing/cumulative time intelligence). Confirm the
  warehouse Power BI points at is on a recent enough channel.
- **Compute**: Power BI should point at a **SQL Warehouse** (ideally Serverless), not an all-purpose cluster.
- **Catalog/schema grants**: `GrantProcessor` (in `LakehouseUtilities.py`) deliberately does **not** apply
  `USE CATALOG`/`USE SCHEMA` grants - those are a one-time bootstrap. `create_semantic_schema.sql` prints the
  statements to run; an admin still has to execute them once per environment for the developer group and the
  Power BI service principal.
- **`main.governance.grants` rows** for every metric view, same as any other gold/platinum object - see step 4
  above. Nothing is exposed by default.

## A bug fixed along the way

While wiring `MetricViewProcessor` into `LakehouseUtilities.py`, `DeltaProcessor.schema_exists()` turned out to
have a latent bug: it referenced an undefined variable (`create_if_not_exist` instead of the parameter
`create_if_not_exists`), and separately double-quoted the `MANAGED LOCATION` clause when one was passed. Both
were dormant because every schema anyone has ever called `schema_exists(True)` against (`gold`, `platinum`,
`silver`) already existed - `semantic` is the first schema that will actually exercise that code path. Fixed in
this change; see the comment left in `LakehouseUtilities.py` for details. Worth a regression test the next time
a brand-new schema is created anywhere in this codebase.

## Other things to plan for (not built here - flagging for the platform team)

- **CI/CD for YAML**: the metric definition lives inside a `CREATE VIEW ... WITH METRICS LANGUAGE YAML` SQL
  string. Treat it like the `dim_`/`fact_` SQL notebooks already in source control - PR review on the YAML is
  the actual metric governance, so don't let people edit metric views directly in Catalog Explorer's UI editor
  in higher environments.
- **Testing**: there's an existing Nutter-based validation framework (`Hologic Nutter Validation Audit
  Framework.sql`) for facts/dimensions. Consider a lightweight equivalent for metric views - e.g. assert the
  view exists, assert a known measure returns a non-null, sane value for a known slice.
- **Materialization**: a few Platinum facts are very large (`fact_otif_with_rootcauses_plt`,
  `fact_sales_order_nocharge_plt`, etc.). If a metric view built over one of these is slow in Power BI, the YAML
  spec supports a `materialization` block (pre-aggregated backing materialized views) - not used in the
  template/example here, but worth knowing it exists before reaching for a workaround.
- **Discoverability**: there's no registry of "which metric views exist and who owns them" beyond Unity
  Catalog itself. Comments/`display_name`/`synonyms` in the YAML help Genie and Catalog Explorer surface them;
  consider whether that's enough or whether this needs a row in some catalog/wiki, the same way the
  `pbi_control_table`/`db_control_table` track load config today.
- **Naming collisions**: nothing stops a metric view and a `gold`/`platinum` table from covering the same
  business concept once these exist side by side (e.g. a `mv_revenue_*` next to `fact_revenue_*_plt`). Decide
  and document which one is the "source of truth" for report authors before this grows.
