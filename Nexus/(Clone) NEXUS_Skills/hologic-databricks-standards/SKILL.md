---
name: hologic-databricks-standards
description: Use whenever creating, reviewing, or fixing a Silver/Gold/Platinum/Metric View Databricks notebook in Hologic's mde_dev medallion architecture (HDA_MDE repo) — naming conventions, Fact-vs-Dimension classification, which processor class to use (FactProcessor/DimensionProcessor/PlatinumProcessor/ViewProcessor/MetricViewProcessor), incremental-load patterns per class, medallion read rules, TBLPROPERTIES requirements, SQL coding standards, Unity Catalog Metric View YAML definitions, and the verification steps to run before committing or pushing. Trigger on "gold notebook", "silver view", "platinum notebook", "fact table", "dimension", "medallion standard", "Hologic naming convention", "DimensionProcessor", "FactProcessor", "PlatinumProcessor", "metric view", "MetricViewProcessor", "semantic model", or any ask to build/audit/fix a Databricks object in this codebase.
---

# Hologic Databricks Medallion Standards

Canonical source: HDA_MDE.wiki page 258 ("Development Standards - Databricks"). This skill
distills that page plus real framework behavior confirmed by reading `LakehouseUtilities.py`
directly and real committed sibling notebooks — not assumed from name/pattern alone. When this
skill and a real committed sibling notebook disagree, re-check the sibling before trusting either.

## 1. Naming

- **Table/view names**: lowercase, underscore-separated, e.g. `dim_customer_geography`,
  `fact_salesorder`. New objects (2026-08-31 standing rule) may freely use multiple underscores
  (`fact_opm_explosion`) — does not retroactively rename older mashed-style objects
  (`fact_scrapmtl`, `dim_opmformula`).
- **Gold/Platinum column names**: ProperCase-mashed, `_` ONLY immediately before a final `_ID` or
  `_SK` suffix. `OrderedDateTime`, `RcvTransactionDate`, `Employee_ID`, `RcvTransaction_SK` — never
  `Ordered_Date_Time` or `Employee_Id`. Exclusions: `dl_*` framework/audit columns, and the
  auto-generated `v_pbi_*` alias view's spaced human-readable names (a different, intentional
  display layer — don't flag its naming as a violation of the base table).
- **Silver view/notebook names**: `v_` + `mst` (reference) or `trn` (transaction) + source system
  (`oracle_ebs`, `agile`, `ascp`, `azure`, `cornerstone`, `mule`, `pbcs`, `salesforce`,
  `servicenow`) + object, e.g. `v_trn_oracle_ebs_mtl_material_transactions`. Notebook name = view
  name.
- **Platinum object/notebook names (standing rule, 2026-09-14, forward-only)**: every NEW Platinum
  object — Dimension-shaped or Fact-shaped, materialized table (`PlatinumProcessor`) or plain view
  (`ViewProcessor`/`DeltaProcessor.create_aliased_view()`) alike — gets the `_plt` suffix:
  `dim_<name>_plt` / `fact_<name>_plt`. This supersedes the older `v_dim_<name>.sql` (no suffix)
  pattern seen on some existing plain-view Platinum notebooks (e.g. `v_dim_customersiteservice.sql`,
  `v_dim_servicegeography.sql`) — those are **grandfathered under the old standard and must NOT be
  renamed retroactively**; the `_plt` rule applies only to objects created from this date forward.
  Real example: `Platinum/v_dim_customersite_uses.sql` (created 2026-09-14, wrongly following the
  old no-suffix pattern) was renamed to `Platinum/dim_customersite_uses_plt.sql` same day, per
  Sameet, specifically because it's new.
- **SK formula**: `md5(concat_ws('|', <natural key columns in order>))`.
- Before assuming a naming convention, check a real committed sibling notebook in the SAME target
  folder — don't infer from one example or from this file alone. **Exception: for Platinum naming
  specifically, an old sibling (no `_plt` suffix) is NOT authoritative for a new object** — the
  standing rule above overrides what an old sibling looks like; only use a sibling to confirm
  Platinum naming if it's confirmed to be recently created, not just present in the folder.

## 2. Fact vs. Dimension — how to classify a new object

Ask: does this object have a **business-event grain** — a transaction date, an order/batch
reference, a measurable thing that *happened*? If yes → `fact_`. If the object instead encodes a
**structural relationship** (a hierarchy, a BOM/formula explosion, a bridge with a weighting/ratio
column like quantity-per) with no event grain → `dim_`, even if it has a numeric "quantity" column
that superficially looks fact-like. This is the textbook Kimball bridge-table shape.

Cross-check: does this codebase already have a `dim_*` object for the simpler/un-exploded version
of the same relationship? If so, match it — don't classify a deeper/recursive version of the same
relationship as a Fact just because it's more complex. (Real precedent: `gold.dim_bom` /
`gold.dim_bom_inventory_component` are the single-level version of what `gold.dim_bomexplosion`
recursively explodes — both are Dimensions.)

## 3. Which processor class — real mechanics, not assumed

All four live in `LakehouseUtilities.py`. Read it directly before assuming behavior — this table is
current as of 2026-08-31 but the file can change.

| Class | Use for | Incremental support | Delete propagation |
|---|---|---|---|
| `FactProcessor` | Gold facts (event/transaction grain) | Real `MERGE` on `loadType='I'`, keyed by `nk_column_names`, `dl_rowhash` change-detection. Source view CAN be pre-filtered to a "dirty" subset. | **None** — flag as a known limitation if relevant. |
| `DimensionProcessor` | Gold dimensions (incl. bridge tables) | **No `loadType` param at all.** Always re-reads the FULL input view; does its own row-level diff in `merge()`. `dim_type='1'`=SCD1, `'2'`=SCD2. **The view must represent the full current universe every run** — a watermark-filtered partial view will make `whenNotMatchedBySourceDelete`/`whenNotMatchedBySourceUpdate` wrongly treat every untouched row as deleted. Auto-computes the SK from `nk_column_names` — do NOT pre-select a column matching `sk_column_name` in the view (`[COLUMN_ALREADY_EXISTS]`). | **Real hard-delete** (`dim_type='1'`) or expiry (`'2'`) — better than `FactProcessor` here. |
| `PlatinumProcessor` | Platinum marts | **No incremental/MERGE path at all** — `ctas()` is unconditionally `CREATE OR REPLACE TABLE AS SELECT *`. This is a program-wide framework gap, not a per-notebook bug. If a Platinum object genuinely needs incremental load, hand-roll a `MERGE` modeled on `FactProcessor`'s (see §4), calling `PlatinumProcessor` only for the full/bootstrap path. | None built in. |
| `ViewProcessor` | A plain reporting view with no materialized table | Trivial — just `create_aliased_view()`. Note: the ADO wiki's "Platinum uses ViewProcessor" describes this simpler pattern, NOT what real materialized Platinum objects (constraints, grants, aliasing) use — those use `PlatinumProcessor`. Don't flag a `PlatinumProcessor`-based notebook as non-compliant with the wiki without checking a real committed Platinum sibling first. |  |

## 4. Incremental-load patterns, by grain

Every Gold fact needs real incremental logic — "feels structural, no obvious watermark" is not a
valid exception until checked. Pick the pattern by the object's actual grain:

- **Pass-through grain** (1 output row per source row, `FactProcessor`): plain per-row watermark
  filter on the joined source's `dl_recordstartdateutc`. Reference: `fact_receiving.sql`.
- **Aggregated grain** (many source rows collapse into fewer output rows, `FactProcessor`): do NOT
  filter-then-aggregate (undercounts a group that only had SOME rows change). Instead: identify
  dirty grain-keys via the watermark (single-scan window function,
  `MAX(CASE WHEN src_watermark >= date_final THEN 1 ELSE 0 END) OVER (PARTITION BY <natural key>)`
  — computed inline, not via a separate CTE re-referencing the expensive base query, which Spark
  will physically re-scan), then re-derive those keys COMPLETELY from the full unfiltered source,
  then MERGE just the complete recomputed rows. Verify with `EXPLAIN FORMATTED` (count distinct scan
  nodes) that the base query isn't being scanned twice. Reference: `fact_opm_subledger.py`.
- **Recursive/hierarchical grain** (`DimensionProcessor`): cannot filter the view at all (§3) — so
  the pattern is different: cheap non-recursive "dirty-top-item" detection via a reverse lookup
  against the **already-materialized target table** (never re-derive the expensive recursion just
  to find what's dirty) joined to the source's own watermark, then recurse ONLY the dirty subset,
  then `UNION ALL` with untouched rows read straight back from the target — reconstructing the full
  current universe `DimensionProcessor` needs. Bootstrap (target doesn't exist) falls back to a full
  unfiltered recompute. Reference: `gold.dim_bomexplosion`/`gold.dim_opm_explosion` (built
  2026-08-31 — flagged in both as reasoned-through but not yet live-tested against real compute).
- **Platinum, reading already-incremental Gold**: usually needs nothing extra — a full CTAS over 2
  small, already-current Gold tables is cheap. Only hand-roll a Platinum MERGE (§3) if the Platinum
  transform itself does expensive work the Gold layer doesn't already absorb.
- Always pass `loadType=pLoadType` into `FactProcessor(...)` explicitly — a missing pass-through is
  a silent, easy-to-miss bug (found live **four** times this program now: `fact_opm_subledger`,
  `fact_scrapmtl` — a genuine pre-existing production bug, 26 versions of `DESCRIBE HISTORY` showing
  zero `MERGE` ever ran — and, 2026-09-03, `fact_lot_status_change` + `fact_lot_technical_parameter`,
  found while addressing a direct user report ("no incremental logic... all facts at gold layer
  should have incremental"), not a build-time check. Both had **zero** incremental scoping at all —
  the view always read the full unfiltered Silver source regardless of the `loadType` widget's
  value, and `loadType` was never passed into `FactProcessor` to begin with. Fixed by adding the
  full pass-through-grain pattern (§4 above) matching `fact_receiving.sql`'s reference exactly:
  `lastfactload1`/`lastfactload2` tracking columns added to the view output, `date_final`
  watermark computation cell, `WHERE (src1.dl_recordstartdateutc >= date_final OR
  src2.dl_recordstartdateutc >= date_final)`, `loadType=pLoadType` wired into `FactProcessor(...)`.
  **A grep across every Fact notebook on the same branch for `date_final`/`loadType=pLoadType`
  found a *third* instance with the same gap — `fact_servicerequest.sql` — which had already been
  through a full PR review (#4402) that caught 3 other real bugs but never this one.** Flagged, not
  yet fixed (a bigger edit to an already-twice-reviewed file). **Lesson: a passing PR review is not
  proof a Fact has real incremental logic — grep for `loadType=pLoadType` explicitly, don't assume
  it from review history.** The 2 most recently built Facts on the same branch
  (`fact_field_service_usage`, `fact_mrp_forecast`) already had this pattern correctly — the gap is
  specific to older builds, not universal on the branch.

## 5. Medallion read rule

**Gold reads Silver only. Platinum reads Gold only.** A Gold notebook reading Bronze directly, or a
Platinum notebook reading Silver directly, is a real bug — found and fixed live at least twice in
this program. A documented, flagged, temporary exception (e.g. a companion Silver view not yet
deployed) is acceptable only if stated explicitly in the notebook and tracked as an open item — not
silently permanent.

## 6. TBLPROPERTIES contract

Every Gold/Platinum transient view needs the config keys the target `Processor` class reads via
`SHOW TBLPROPERTIES`:

- Facts (`FactProcessor`): `config.sk_column_name`, `config.nk_column_names`, `config.cluster_by`,
  `config.fact_type` (`1` = full CTAS shape), `config.primary_key`, `config.foreign_key`.
- Dimensions (`DimensionProcessor`): `config.sk_column_name`, `config.nk_column_names`,
  `config.cluster_by`, `config.dim_type` (`1` or `2`), `config.primary_key`, `config.foreign_key`.
- Never hardcode the catalog name — always a widget + `spark.catalog.setCurrentCatalog(...)`.
- **Always include ALL SIX config keys on the TBLPROPERTIES block, even when three of them are
  legitimately empty**: `config.sk_column_name`, `config.primary_key`, `config.foreign_key`,
  `config.unique_constraints`, `config.not_null_constraints`, `config.check_constraints` (plus
  `nk_column_names`/`cluster_by`/`fact_type`|`dim_type`). Real PR review catch (2026-09-03,
  `fact_servicerequest.sql`, PR #4402): a notebook shipped with only 3 of the 9 keys present
  (missing `sk_column_name`/`primary_key`/`foreign_key`/`unique_constraints`/
  `not_null_constraints`/`check_constraints` entirely) — caught by a human reviewer, not by any
  automated check. Don't omit a key just because its value is `''`.

## 7. General SQL coding standards

CTEs over subqueries (flatten a nested subquery into its own named CTE); `CASE` over
`DECODE`/`IF`; `COALESCE`/`NULLIF` over `NVL`; `TO_DATE()`/`TO_TIMESTAMP()` over date casts;
explicit column lists over `SELECT *`; avoid `DISTINCT` past ~10 columns; broadcast hint for lookup
tables under 10MB; select only needed columns before a join; filter as early as possible; enable
AQE; avoid `GROUP BY ALL`; cache small tables reused multiple times, persist larger ones; use the
SQL Warehouse (not a personal cluster) for pure-SQL execution.

## 8. Notebook documentation — keep it short

Sameet's standing preference (2026-08-31): **no long `%md` description blocks or comment essays in
the notebook itself.** A short 1-3 line purpose statement is enough. Findings, evidence, live-check
numbers, design reasoning, and known-limitation writeups belong in the ADO task description, the
migration log, or a memory file — cite them from the notebook if needed, don't duplicate them into
it. (This does not apply retroactively to notebooks already written before this date.)

## 9. Reference notebooks — embedded verbatim, no need to re-pull from Databricks/git

5 real, committed, production notebooks from the `main` branch of HDA_MDE (`DataPlane/Databricks/src/
Workspace/DataEngineering/...`), copied byte-for-byte into `references/` alongside this file. Read
the actual file before pattern-matching off memory of it — this note is just an index.

| File | Real object | Demonstrates |
|---|---|---|
| `references/silver-sample-v_mst_oracle_ebs_po_vendors.py` | `silver.v_mst_oracle_ebs_po_vendors` | Minimal Silver view: 1:1 with Bronze, `WHERE dl_iscurrent = true`, no business logic. |
| `references/gold-fact-sample-fact_receiving.sql` | `gold.fact_receiving` | `FactProcessor`, **pass-through-grain** incremental (per-row `lastfactload1/2/3` watermark filter) + real hard-delete propagation (3 `MERGE ... WHEN MATCHED THEN DELETE` blocks, one per joined source). |
| `references/gold-fact-sample-fact_opm_subledger.py` | `gold.fact_opm_subledger` | `FactProcessor`, **aggregated-grain** incremental (single-scan dirty-batch window function, full re-aggregation of dirty keys — NOT filter-then-sum) + why a naive 2-CTE version double-scanned the source (see its own `%md` header for the `EXPLAIN FORMATTED` story). |
| `references/gold-dimension-sample-dim_opmformula.sql` | `gold.dim_opmformula` | `DimensionProcessor`, `dim_type=1` (SCD1), plain full-view rebuild — no watermark, no loadType widget at all. |
| `references/platinum-sample-fact_ops_mfg_variance_plt.py` | `platinum.fact_ops_mfg_variance_plt` | `PlatinumProcessor`, Gold-only read, `/*+ BROADCAST(...) */` hint usage, full CTAS (no incremental — matches §3's documented framework gap). |
| `references/metricview-sample-example_mv_sales_order_item.sql` | `mde_dev.semantic_models.mv_sales_order_item` | `MetricViewProcessor`, `CREATE VIEW ... WITH METRICS LANGUAGE YAML` — see §11. |
| `references/metricview-README.md` | n/a | The real `MetricViews/README.md` — full developer workflow, Power BI connection notes, requirements/prerequisites. |

Note the real-world contrast with §8: these are all pre-2026-08-31 notebooks and still carry
moderate `%md`/inline documentation — that's the pre-existing house style on `main`, not a
contradiction of the brevity rule going forward. The 2 metric-view reference files are the
exception — added 2026-09-02, after the brevity rule, and follow it.

## 10. Verification discipline — before considering any fix "done"

1. Read the real target notebook and a real committed sibling before assuming a convention or
   framework behavior — don't infer from name/pattern, don't trust an older doc (including this
   skill) over the actual `LakehouseUtilities.py` source if they conflict.
2. Testing an extracted SQL fragment proves the fragment, not the notebook as a deployable artifact.
   Either run the real notebook end-to-end, or diff its full structure (declared language,
   cell-magic markers, widget/config boilerplate) against a known-working sibling.
3. Where Databricks compute isn't available or shouldn't be spent: syntax-check the notebook's
   embedded Python cells with `py_compile` (strip `-- MAGIC %python` / `# MAGIC` prefixes first for
   SQL-native `.sql` files), and dry-run the view-building Python logic locally against a
   hand-mocked `spark.sql`/`spark.catalog.tableExists` to render the final SQL text end-to-end for
   inspection (paren balance, no leftover template placeholders, keyword presence like `RECURSIVE`
   on a self-referencing CTE). This has caught real bugs (a missing `RECURSIVE` keyword) before ever
   touching a SQL warehouse.
4. **Three-layer check before reporting anything "done"**: workspace-exists ≠ committed-to-git ≠
   deployed (a Job actually run against production). State explicitly which of the three is true.
5. Live-check against `information_schema`/a real `DESCRIBE` when a claim can be checked live —
   don't rely on memory of a prior session's numbers.
6. **Every notebook needs `from datetime import datetime, timezone` + `startTime =
   datetime.now(timezone.utc)` in its FIRST widgets cell** — not set later, not set inline right
   before `fact.process()`/`.process()` inside the `try` block. Real PR review catch (2026-09-03,
   `fact_servicerequest.sql`, PR #4402): the notebook set `startTime = datetime.utcnow()` inside the
   `try`, but never imported `datetime` anywhere — a guaranteed `NameError` the moment that line
   ran, which would also break the `except` block's own `LakeOrchestrator.exit_with_status(...,
   startTime=startTime)` call since `startTime` would never get assigned. `.utcnow()` is also
   deprecated Python — use `.now(timezone.utc)`, matching every other real notebook in this
   codebase.
7. **Before joining to ANY lookup/dimension source (not just verifying the fact's own natural
   key), confirm that source has at most one row per join key** — a duplicate on the *joined*
   side silently fans out the fact, producing duplicate SKs downstream even when the fact's own
   grain logic is otherwise correct. Real PR review catch (2026-09-03, `fact_servicerequest.sql`,
   PR #4402): `v_mst_oracle_ebs_cs_sr_owners_v` had 4 `RESOURCE_ID`s each carrying both an
   `RS_EMPLOYEE` row and an `RS_GROUP` row (real Oracle ID-space overlap) — the owner `LEFT JOIN`
   fanned out on exactly those 4 IDs, producing real duplicate `ServiceRequest_SK` values that a
   human reviewer caught, not any automated check. Fixed with a `ROW_NUMBER() OVER (PARTITION BY
   <join key> ORDER BY <deterministic tiebreak>) = 1` dedup CTE before joining — pick the tiebreak
   from a real business-meaningful column on that source (here: prefer `RS_EMPLOYEE` over
   `RS_GROUP`, a named person over a generic group label), don't just take an arbitrary row.
   `count(*) = count(distinct <sk column>)` on the final materialized fact is the check that would
   have caught this before a reviewer had to.
8. **A Silver view's `SELECT` should carry only `dl_recordstartdateutc` as its lineage column —
   never `dl_rowhash`, `dl_recordenddateutc`, or `dl_load_id`.** `dl_iscurrent` is a filter-only
   column (`WHERE dl_iscurrent = true`), never selected either. Confirmed against the real
   canonical reference (`references/silver-sample-v_mst_oracle_ebs_po_vendors.py`): its only
   framework-column output is `to_timestamp(dl_recordstartdateutc) as dl_recordstartdateutc`.
   Real finding (2026-09-03, `Sameet_main_opstrends_updates_02Sep26`): 7 of 9 Silver views added
   that session (`v_mst_oracle_ebs_cs_sr_incidents_v_sec`, `v_mst_oracle_ebs_cs_sr_owners_v`,
   `v_mst_oracle_ebs_gmd_tech_parameters_tl`, `v_mst_oracle_ebs_gmd_technical_data_hdr`,
   `v_trn_oracle_ebs_gmd_technical_data_dtl_ac1`, `v_trn_oracle_ebs_mtl_lot_numbers_ac1`,
   `v_trn_oracle_ebs_mtl_lot_numbers_av1`) wrongly carried `dl_rowhash`/`dl_recordenddateutc` in
   their output (one, `cs_sr_incidents_v_sec`, also had `dl_load_id`) — caught by the user, not by
   any build-time check. Before fixing, verify no downstream Gold Fact notebook actually reads
   these columns *from the Silver view* (grep the consuming Fact notebooks for the view name +
   the column names) — none did in this case, so removing them was a pure no-op for Gold's computed
   values, not a behavior change. Fixed via a targeted push (commit `dacada231b...`), not deployed
   without checking consumers first.
9. **Standing rule (Sameet, 2026-09-03, explicit and absolute): every non-`dl_*` Silver date field
   is `Cast(x AS DATE) as x` — no exceptions, regardless of real time-of-day content.**
   `dl_recordstartdateutc` is the sole exception, always `to_timestamp(dl_recordstartdateutc) as
   dl_recordstartdateutc` (per item 8). Do NOT profile non-midnight rates to decide otherwise — an
   earlier pass this session did exactly that (found `CREATION_DATE`/`LAST_UPDATE_DATE`/
   `INCIDENT_DATE`/etc. are 89-100% non-midnight, i.e. real timestamps, and switched them to
   `to_timestamp()`) and was explicitly told to revert: "this is correct for dl_ col" + "strict
   universal rule, no exceptions." Reverted via commit `7b2135aa9...`, superseding the data-driven
   version at `8c6a7e548...`.
   **Known, accepted, explicit tradeoff — do not "fix" this elsewhere either**: the already-deployed
   `fact_servicerequest.sql` does `SUBSTRING(CAST(i.INCIDENT_DATE AS STRING), -8) AS IncidentTime`,
   which produces a constant/meaningless value because Silver's `INCIDENT_DATE` is date-only by this
   rule — Sameet confirmed directly ("don't touch this fact_servicerequest.sql already does
   SUBSTRING(...)... AS IncidentTime") that `fact_servicerequest.sql` itself stays untouched and
   `IncidentTime` stays non-functional. This is a deliberate, informed call, not an oversight — don't
   re-open it without being asked. A `_TIMESTAMP`-suffixed column (e.g. `AUDIT_TIMESTAMP`) is a
   different naming convention and keeps `to_timestamp()` — this rule is specifically about
   `_DATE`-suffixed and other non-timestamp-named date columns.

10. **Before joining to a currency-rate or other "daily-sounding" reference/rate table, verify its
    real date-grain — don't trust the column name.** Real incident (2026-09-22, `gold.fact_ppv`):
    `gold.dim_currency` has a column literally named `CurrencyDaily_SK`, but is actually PERIOD
    grain — only 413 distinct `ConversionDate` values across 35 years (2000-2035), not one row per
    calendar day. Joining to it on currency codes alone (no date match) silently fanned out every
    fact row by however many rate rows existed for that currency pair (581 rows for just
    USD->USD) — 20,985,477 rows for 32,336 real keys, caught only by the `count(*) = count(distinct
    SK)` check in item 7 above. A follow-up exact-date-match join then produced 99%+ NULL rates,
    since 413 sparse dates almost never exact-match an arbitrary transaction date. The real fix is
    an as-of join: nearest available rate on/before the transaction date. **Spark SQL rejects a
    correlated scalar subquery inside a JOIN's `ON` clause**
    (`UNSUPPORTED_CORRELATED_SCALAR_SUBQUERY`, confirmed live) — don't reach for
    `ON x = (SELECT MAX(...) WHERE outer.col = ...)`. Use a window-function pattern instead: add a
    stable row id (`monotonically_increasing_id()`) to the driving side, `LEFT JOIN` to every
    candidate rate row on/before the date (temporary fan-out), then
    `ROW_NUMBER() OVER (PARTITION BY <row id> ORDER BY ConversionDate DESC) = 1` to collapse back to
    one row per input. Also check for a same-date multi-row trap on the OTHER dimensions of the rate
    table (here: `Scenario` — `ACTUAL` and `BUDGET` rows share the same `ConversionDate`, so the
    join also needs `Scenario = 'ACTUAL'` or the as-of collapse still leaves 2 candidates per date).

## 11. Metric Views — a 5th object type, not a Fact/Dim/Platinum variant

Confirmed 2026-09-02 by reading the real `MetricViews/example_mv_sales_order_item.sql` +
`MetricViews/README.md` directly (ground truth — don't infer this section from generic Databricks
Unity Catalog Metric View docs, Hologic's own house style differs in the details below).

**What it is**: a virtual, query-time-evaluated Unity Catalog object (`CREATE VIEW ... WITH METRICS
LANGUAGE YAML`) that governs dimensions/measures once instead of every report re-deriving its own
DAX totals. No physical table, no MERGE, no incremental watermark, no `dl_*` audit columns — freshness
is always "as of now."

**Where it lives**:
- **Notebook**: `DataEngineering/MetricViews/<name>.sql` (SQL-native, same `.sql` extension
  convention as a SQL-native Gold/Platinum notebook — §1/§3). One notebook per metric view, named
  `mv_<domain>_<subject>` (lowercase snake_case, `mv_` prefix — same convention as `dim_`/`fact_`).
- **Live object**: `<catalog>.semantic_models.<name>` — e.g. `mde_dev.semantic_models.mv_scrap`.
  (The `MetricViews/README.md` describes the target schema as `semantic`; the real notebook's own
  `deltaSchemaName` widget default, and the schema that actually exists live in `mde_dev`, is
  `semantic_models` — trust the notebook/live catalog over the README wording if they ever
  disagree.) `SHOW VIEWS IN <catalog>.semantic_models` flags these with `isMetric = true`.
- **Source**: only `gold`/`platinum` tables (or another metric view) — never straight from
  `silver`/Bronze, same medallion-read discipline as §5.

**Notebook template** (mirrors the Gold/Platinum widget boilerplate in §1/§6, nothing metric-view-specific
about the mechanics until the definition cell):
1. Widgets cell: `deltaSchemaName` (default `'semantic_models'`), `deltaTableName` (the `mv_...`
   name), `catalogName` (default `'mde_dev'`) — plus `startTime = datetime.now(timezone.utc)` for
   `LakeOrchestrator.exit_with_status`.
2. `%run ../LakehouseUtilities` (one level up from `MetricViews/`, same relative path every other
   folder under `DataEngineering/` uses) + `spark.catalog.setCurrentCatalog(pCatalogName)`.
3. The definition cell: `spark.sql(f"CREATE OR REPLACE VIEW {catalog}.{schema}.{name} WITH METRICS
   LANGUAGE YAML AS $$ ... $$")`. Inside the YAML: `version: 1.1`, a `comment` (what the metric view
   is, its owner, and — if a same-named/overlapping certified object already exists elsewhere, e.g. a
   `fact_revenue_*` — an explicit note that this is NOT that number), `source:` (one gold/platinum
   table), optional `joins:` (each with `rely: {at_most_one_match: true}` when the join target is a
   `dim_type=1` one-row-per-key dimension), optional top-level `filter:` (plain boolean expression,
   e.g. `source.dl_iscurrent = true` when the source dimension carries SCD history), `dimensions:`
   (each needs `name`, `expr`, `display_name`; add `synonyms:` for Genie discoverability), and
   `measures:` (each needs `name`, `expr` — a real aggregate function, `SUM`/`COUNT`/`AVG`/a ratio of
   two aggregates — `display_name`, and a `comment` explaining what it means; that comment is what
   makes it "certified" rather than just another view).

   **Corrected 2026-09-17, live-verified, supersedes the `fields:` guidance below (kept for
   history) — use `dimensions:` as the top-level key, NOT `fields:`.** Real incident: built
   `platinum.fact_asset_install_yield_plt` / `mv_asset_install_yield` and copied the `example_
   mv_sales_order_item.sql` reference notebook's `fields:` key verbatim (per this skill's own
   prior guidance). Running the real `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML`
   command as a job on the classic "Phoenix Shared Compute" cluster (DBR 17.3.x-scala2.13) failed
   with `[METRIC_VIEW_INVALID_VIEW_DEFINITION] ... Unrecognized field "fields" ... (8 known
   properties: "measures", "version", "joins", "source", "dimensions", "comment", "filter",
   "materialization")` — a real error straight from the engine's YAML deserializer, not a
   plausible-sounding guess. Fixed by renaming `fields:` to `dimensions:`; the corrected notebook
   then created successfully and a live `MEASURE()` smoke test returned real rows.
   **Genuinely confusing wrinkle, don't over-simplify it away**: the already-shipped
   `mv_eo_demand` notebook's checked-in source still literally says `fields:` at its top level,
   yet querying it live via the SQL warehouse (`SELECT ... MEASURE(...) FROM
   semantic_models.mv_eo_demand`) works fine today and returns real data. So `fields:` is not
   universally broken — it's specifically the classic-cluster-job `CREATE OR REPLACE VIEW`
   execution path (the one this skill's own template prescribes) that rejects it on this DBR
   version; whatever engine/version originally created `mv_eo_demand` accepted it, and the
   persisted object keeps working when only *queried* later via the warehouse. **How to apply**:
   for any NEW metric view built via this skill's notebook template (a job on an existing
   classic cluster), use `dimensions:` — it is the verified-working key for that execution path.
   Do not "fix" `mv_eo_demand`/`mv_eo_onhand`/`mv_eo_usage`'s already-working `fields:` definitions
   without being asked; they are not currently broken. If one of them is ever rebuilt/re-run
   through a classic-cluster job (not just queried), expect it to hit this same error and need the
   same `dimensions:` fix.

   **Corrected 2026-09-18, live-verified, same shape as the `fields:`/`dimensions:` finding above
   — `joins[].rely` is REJECTED on the classic-cluster job execution path too**, despite appearing
   in already-live views' `describe` output. Real incident: built `mv_sales_order_surgical` with
   `joins: - name: cal ... rely: {at_most_one_match: true}`, copied from the live `view_text` of
   `mv_combined_revenue`/`mv_sales_open_order`/`mv_forecast` (fetched via `manage_metric_views`
   describe). Running it as a job on "Phoenix Shared Compute" failed with
   `[METRIC_VIEW_INVALID_VIEW_DEFINITION] ... Unrecognized field "rely" (class
   com.databricks.sql.serde.v11.Join) ... (5 known properties: "joins", "name", "using", "on",
   "source")` — `rely` isn't in this execution path's Join schema at all. Fixed by deleting the
   `rely:` block from the join entirely; the corrected notebook then created successfully and a
   live smoke test returned real rows. Same wrinkle as `fields:`: those 3 sibling views (owner
   `vamshi.velumala@hologic.com`, June 2026) genuinely have `rely` in their live `view_text` and
   keep working when only *queried*. **How to apply**: for any NEW metric view built via this
   skill's notebook-job template, omit `rely` from every join — don't copy it from an existing
   view's `describe` output, even a currently-live sibling in the same schema. Document the
   many-to-one cardinality assumption in a comment instead; that guarantee isn't expressible on
   this execution path today.

   **Corrected 2026-09-22, live-verified — a literal `"` inside a double-quoted YAML `comment:`
   value breaks the parser**, same failure class as the two findings above (a real
   `[METRIC_VIEW_INVALID_VIEW_DEFINITION]` engine error, not a guess). Real incident: building
   `mv_sales_order_combined`, a measure comment read `... genuinely define "open" differently ...`
   inside an already-double-quoted `comment: "..."` value — the inner `"` prematurely closed the
   YAML string, producing `Failed to parse YAML: while parsing a block mapping ... expected ,
   but found ''`. Fixed by removing the inner quotes (a block scalar or escaped `\"` would also
   work, but plain removal was simplest here). **How to apply**: before writing any `comment:`
   string in a metric view's dimensions/measures YAML, check it for embedded `"` characters -
   don't rely on eyeballing a long comment during authoring; grep the draft for `comment: ".*".*"`
   style patterns before deploying.

   **Corrected 2026-09-25, live-verified — a top-level join's `on:` clause can only reference
   `source` and its own alias; it CANNOT reference a sibling join's alias, even though both appear
   in the same flat `joins:` list.** Real incident: building
   `mv_sales_order_performance_domestic_combined`, a join named `commitment` (source
   `platinum.dim_compliance_commitment_plt`) needed to join off `pricing_compliance.AgreedPriceGroup_ID`
   -- where `pricing_compliance` was itself a sibling join (source
   `platinum.dim_order_line_pricing_compliance_plt`, `on: source.OrderLine_ID =
   pricing_compliance.OrderLine_ID`) -- rather than off `source` directly. Written as two flat
   sibling entries in the top-level `joins:` list, this failed at real job-execution time with
   `[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column, variable, or function parameter with name
   pricing_compliance.AgreedPriceGroup_ID cannot be resolved. Did you mean one of the
   following? [commitment.AgreedPriceGroup_ID, ...]`. Root cause confirmed by the engine's own
   error schema for a Join object (the same 5-property list as the `rely:` finding above: `joins,
   name, using, on, source`) -- `joins` is itself one of a Join's own properties, so nesting is the
   supported mechanism for a join that depends on another join. Fixed by nesting the dependent join
   INSIDE its parent join's own `joins:` list, snowflake-style:
   ```yaml
   joins:
     - name: pricing_compliance
       source: platinum.dim_order_line_pricing_compliance_plt
       "on": source.OrderLine_ID = pricing_compliance.OrderLine_ID
       joins:
         - name: commitment
           source: platinum.dim_compliance_commitment_plt
           "on": pricing_compliance.AgreedPriceGroup_ID = commitment.AgreedPriceGroup_ID
   ```
   **How to apply**: whenever a new dimension's real FK is only reachable via an already-joined
   dimension rather than `source` directly, nest it under that parent join's own `joins:` list --
   don't add a second flat top-level join and expect cross-join references to resolve.
4. Validate + grants cell: `MetricViewProcessor(schema_name=, view_name=, catalog_name=).validate()`
   then `.apply_grants()`, wrapped in `try/except` calling
   `LakeOrchestrator.exit_with_status(success=False, ...)` on failure — same failure-signaling
   convention as every other processor class.
5. `LakeOrchestrator.exit_with_status(success=True, startTime=startTime)`.
6. A final plain-SQL smoke-test cell querying the new view with `MEASURE(...)` + `GROUP BY ALL` (metric
   views reject bare `SELECT *`/bare aggregation — every measure reference needs `MEASURE()`).

**Grants**: `MetricViewProcessor.apply_grants()` reads `main.governance.grants` the same way
`DimensionProcessor`/`FactProcessor`/`PlatinumProcessor` already do (same table, `schema_name='semantic_models'`,
`securable_type='VIEW'`). No grant row = no access even after a successful deploy — ask a platform
admin to add one for a genuinely new consumer.

**Power BI connection** (from `README.md`, worth knowing before promising a report author this "just
works" like a `v_pbi_*` table): DirectQuery + Native Query only — Import mode and the connector's
point-and-click builder don't work against metric views. Every measure reference needs `MEASURE(...)`
and the query needs `GROUP BY ALL`. Confirm the SQL Warehouse Power BI points at is DBR/DBSQL 16.4+
(17.3+ if using `window`/time-intelligence measures).

**Checklist for a new metric view**:
- [ ] Source is a real, live `gold`/`platinum` table (or another metric view) — checked with a real
  `DESCRIBE`/row count, not assumed from a name.
- [ ] Notebook follows the template above, placed at `DataEngineering/MetricViews/mv_<domain>_<subject>.sql`.
- [ ] Every measure has a `comment` explaining what it means; the view-level `comment` names the
  owner and flags any same-named/overlapping "official" object elsewhere if one exists.
- [ ] Structural check per §10 item 2 (real cell count via `ExportFormat.JUPYTER`, correct declared
  language) before running.
- [ ] Deployed via a real Databricks Job run (§10 item 4's three-layer rule applies here too —
  workspace-exists ≠ committed-to-git ≠ deployed) — never `CREATE VIEW` ad hoc and write the notebook
  to match afterward.
- [ ] Live-verified: `SHOW VIEWS IN <catalog>.semantic_models` shows `isMetric = true` for the new
  name, and a `MEASURE(...) ... GROUP BY ALL` smoke-test query returns sane numbers.
- [ ] Re-fetched from git independently after pushing (a fresh clone/export, not just the push
  response) to confirm it actually landed.
