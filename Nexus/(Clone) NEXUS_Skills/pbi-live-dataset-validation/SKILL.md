---
name: pbi-live-dataset-validation
description: Validate a Databricks object (metric view, Gold/Platinum fact) against a production Power BI report — read the .pbix, audit every report/page/visual filter and slicer, rebuild the report's scope in Databricks SQL, and reconcile in layers (base data, object integrity, object vs report, row-level residual) into one validation workbook. Use when someone attaches or points to a .pbix and asks to validate, reconcile or compare a metric view or fact against a Power BI report, asks "why doesn't Databricks match the PBI report", or says "validate against the PBI dataset". Proven 6 times by the Data Engineering team (Surgical, BSH x2, Service Contract Revenue BSH/DX/Surgical).
---

# Power BI report validation (NEXUS edition)

The Data Engineering team's method for proving a Databricks object matches a production Power BI report, adapted to
NEXUS's tools. Everything here is read-only. Never explain a gap by theory — every number in the answer must come from a
query or the .pbix you actually read.

**NEXUS tools used:** `parse_pbix_file` (the .pbix), `execute_sql` (DEV), `execute_sql_env` (UAT/PRD, only when offered),
`find_powerbi_usage` (which PBI datasets read a table), `read_workspace_file`, `read_workbook_sheet` (attached exports),
`create_document` with `kind: "xlsx"` (the validation workbook), `ask_user_question` (scope decisions).

**What NEXUS cannot do yet:** query the live Power BI dataset (no Power BI credential in the app). When a step needs the
report's own numbers, write the exact DAX for the user (section 2) and ask them to run it in Power BI Desktop's DAX query
view or DAX Studio and paste or attach the result — or to export the visual's data (… → Export data) and attach it.

## 0. Get the report

- A .pbix attached to the chat is parsed automatically; one in the Workspace or a Volume: `parse_pbix_file` with its path
  (`section: "overview"` first). If the user only names a report, use `find_powerbi_usage` on the Databricks object to see
  which datasets read it, and ask for the .pbix.
- A dataset-only .pbix (no report pages) has no report/page/visual filters to audit — say so.
- Before reconciling, read `section: "tables"`, `"relationships"`, `"measures"` and ask: can this model express the
  object's scope at all? If a needed attribute is missing (e.g. no Account/Geography table), define the comparable slice
  yourself, map the attribute from the Databricks dimension, and put the target-report question to the user with
  `ask_user_question` — never silently pivot to a different comparison.

## 1. Audit every filter — before trusting any number

`parse_pbix_file` `section: "report"` (page through it with `offset`) lists, per page: report-level filters, page filters,
every visual with its fields, each **visual filter with its values** and each **slicer's saved selection**.

- A missed visual-level filter explained most of a 10–30% gap once; a missed GL Category filter explained $1.9M another time.
- Note filters that differ between visuals of the same page (one visual excluding an extra value). Test whether the
  difference matters before choosing one.
- Measure filters shown without a condition ("__Measures.Daily Rate") are advanced filters whose condition isn't saved
  in the file — list them as "not auditable from the .pbix".
- Read `section: "power_query"` / `"overview"` for the Databricks objects and catalog parameter the dataset reads
  (`__catalog` = mde_dev / mde_uat / mde_prd) — validate against the same environment.
- Which date column drives the calendar: check `"relationships"` (in the sales-order models it was `Incentive Date`, not
  the ship date; in the revenue model `Date Combined`).

## 2. The report's own numbers (DAX the user runs)

Write one `EVALUATE SUMMARIZECOLUMNS(...)` per comparison, with the report's filters applied as
`TREATAS({...}, 'Table'[Column])` and `FILTER(ALL('Table'[Column]), ...)` arguments, grouped by fiscal quarter (and by
Source / Category where the report splits). Rules learned:
- `INFO.VIEW.TABLES/COLUMNS/MEASURES/RELATIONSHIPS()` work; `INFO.TABLES()` / `INFO.MEASURES()` are blocked, and
  `INFO.VIEW.MEASURES()` omits the DAX — measure logic is not retrievable, validate it empirically against a Databricks base.
- Hidden columns (e.g. `GLCode_SK`) are still queryable in DAX — group by them and map to Account/Division/Geography
  in Databricks from `dim_glcode`.
- Test string literals: two visuals used `'31060 - ...'` with spaces and matched nothing.
- Freshness: query the `Extraction Timestamp` table if it exists; measures can silently cap at the prior day.
- Dates before the Calendar table's start land in a blank fiscal-period bucket — treat it as the earlier year.

## 3. Reconcile in layers — stop at the layer that breaks

1. **Base ↔ report.** Rebuild the report's scope from the Databricks base table + dimensions (`execute_sql`) and compare
   by fiscal quarter. This proves the data layer and separates scope rules from object defects. Expect rules PBI applies
   implicitly: PBI-only calculated columns (ask for the map via DAX), one-row-per-key dimensions (Databricks rollup dims
   can carry several rows per key — `SELECT DISTINCT` the key set or revenue multiplies), date caps (a dataset that stops
   at a date drops far-future rows the base still has — apply the same window).
2. **Object integrity.** Metric view total = underlying fact total to the cent; rows = distinct primary key. Rules out
   fan-out from the view's joins.
3. **Object ↔ report.** Compare the object as shipped with the report slice it should cover. If it differs, re-cut the
   fact on the suspected axis (date column, scope) to separate "wrong data" from "wrong definition". Decompose the gap
   into named effects (contract link + scope + calendar) with a zero check column so nothing is left to theory.
4. **Row-level residual.** `FULL OUTER JOIN` the two row sets on the key for the worst quarter and classify the unmatched
   rows against the source tables. A subset that exceeds its superset always means the superset drops rows.

Always give per-column or per-category breakdowns plus a before/after sample — never a row-count match alone. Dedupe
Qlik territory fan-out before summing Qlik exports (rows identical except AE Territory = one line).

## 4. Deliverable

One workbook per validation, built with `create_document` (`kind: "xlsx"`): Summary (result, headline, decisions) →
ROC_Index (ID, severity, evidence, action, owner) → FY_Quarter → detail sheets → Report_Filters (the section-1 audit) →
Method (the SQL and DAX used). A follow-up drill-down adds sheets to the same workbook's content — never a new workbook
per question. Re-check every figure quoted in the Summary against the query results before answering. Root-cause labels
stay short and summary-level (about 5 buckets), each backed by evidence.

## Prior findings to remember

- Surgical, BSH Performance and BSH Performance-SM reports key Fiscal Year off `Sales Order[Incentive Date]`.
- `dim_territorysite` is a Type-1 snapshot; dedupe on `RulePriority` after filtering to the target territory.
- Service Contract Revenue MV joined its calendar on `InvoiceDate` instead of `DistDate` (24–33% of $ in the wrong FY).
- DX Flash: report scope differs per BU even on the same model (DX = Diagnostics, 4 GL accounts, no Category filter) —
  read the report filters before reusing another BU's query. The DX contract fact was 37.9% International, which the MV
  cannot filter. Bridge each quarter as `Fact − PBI = (Base − PBI) − unlinked rows` with a zero check column.
- Surgical revenue model: GL-level Combined Revenue but no Account/Geography/contract table — map locally from
  `dim_glcode`; the dataset's date cap (2027-09-25) must be applied to the base too.
