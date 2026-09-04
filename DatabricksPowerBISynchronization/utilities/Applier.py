# =========================
# Cell 1: Load utilities
# =========================
%run Utilities

# =========================
# Cell 2: Dataset configuration (PBI Developer)
# =========================

DATASET_NAME = "Global Revenue Analytics_Dataset_Descriptions_Synonyms"
WORKSPACE_NAME = "DEV IT Finance Datasets"
SYNONYM_CULTURE = "en-US"
KEY_VAULT_NAME = None

DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_ACCESS_TOKEN = load_databricks_credentials(
    key_vault_name=KEY_VAULT_NAME
)

# =========================
# Cell 3: Databricks <-> Power BI mapping (PBI Developer)
# =========================
# Preferred: Power BI table -> Databricks table(s)
TABLE_MAPPING = {
    "fact_onhanddetails": "fact_onhand_global_inv_plt",
    "fact_intransit": "fact_global_intransit",
    "fact_wip_value_mfg": "fact_wip_value_mfg",
    "fact_perpetual_wip": "fact_opm_perpetual_wip",
    "fact_receiving": "fact_receiving_value",
    "fact_inventory_snapshot_plt": "fact_inventory_snapshot_plt",
    "fact_materialtransaction": "fact_material_transaction_supply_chain_plt",
    "dim_calendar": "dim_financecalendar",
    "dim_divisionheir": "dim_divisionhierarchy",
    "dim_item": "dim_item",
    "dim_itemlookup": "dim_item",
    "dim_itemcategory": "dim_itemcategory",
    "dim_opm_cost_class": "dim_itemcategory",
    "dim_itemglobalprodline": "dim_itemcategory",
    "dim_itemcost": "v_pbi_dim_itemcost_usd_plt",
    "dim_producthie": "dim_producthierarchy",
    "dim_subinventory": "dim_subinventory",
    "dim_warehouse": "dim_warehouse",
    "dim_itemcost_usd": "dim_item_cost_conversion_rate",
    "dim_buyer": "dim_buyer",
    "dim_planner": "dim_planner",
}

# Legacy orientation still accepted by the engine: Databricks table -> Power BI table(s)
TABLE_NAME_MAP = invert_table_mapping(TABLE_MAPPING)

COLUMN_NAME_MAP = {
    "fact_onhand_global_inv_plt": {
        "InventoryItem_ID": "INVENTORY_ITEM_ID",
        "Organization_ID": "Organization_ID",
        "ContainerizedFlag": "CONTAINERIZED_FLAG",
    },
    "gold.fact_global_intransit": {
        "FromOrg": "FROM_ORG",
        "ToOrg": "TO_ORG",
        "ToOrg_ID": "TO_ORG_ID",
    },
}

DATABRICKS_METADATA_SQL = build_databricks_metadata_sql(table_mapping=TABLE_MAPPING)

# =========================
# Cell 4: Optional overwrite lists
# =========================

OVERWRITE_TABLES = []
OVERWRITE_COLUMNS = []
OVERWRITE_MEASURES = []
OVERWRITE_COLUMN_SYNONYMS = []
OVERWRITE_MEASURE_SYNONYMS = []

# =========================
# Cell 5: AI description switches + build proposed metadata (no model writes)
# =========================

# AI descriptions for objects not covered by Databricks comments
GENERATE_MISSING_TABLE_DESCRIPTIONS = True    # mapped tables missing UC comments + model-only tables
GENERATE_MISSING_COLUMN_DESCRIPTIONS = True   # calculated + unmapped/source columns
GENERATE_MISSING_MEASURE_DESCRIPTIONS = True  # measures with blank descriptions

# AI synonyms (independent of description flags; leave True for current behavior)
GENERATE_TABLE_SYNONYMS = True    # 3-5 unique synonyms per table
GENERATE_COLUMN_SYNONYMS = True   # 5-10 per column: calculated + unmapped/source + Databricks-mapped
GENERATE_MEASURE_SYNONYMS = True  # ≥10 per measure

engine = init_metadata_sync(
    dataset_name=DATASET_NAME,
    workspace_name=WORKSPACE_NAME,
    table_mapping=TABLE_MAPPING,
    table_name_map=TABLE_NAME_MAP,
    column_name_map=COLUMN_NAME_MAP,
    databricks_server_hostname=DATABRICKS_SERVER_HOSTNAME,
    databricks_http_path=DATABRICKS_HTTP_PATH,
    databricks_access_token=DATABRICKS_ACCESS_TOKEN,
    auto_discover_tables="no",
    synonym_culture=SYNONYM_CULTURE,
    generate_missing_table_descriptions=GENERATE_MISSING_TABLE_DESCRIPTIONS,
    generate_missing_column_descriptions=GENERATE_MISSING_COLUMN_DESCRIPTIONS,
    generate_missing_measure_descriptions=GENERATE_MISSING_MEASURE_DESCRIPTIONS,
    generate_table_synonyms=GENERATE_TABLE_SYNONYMS,
    generate_column_synonyms=GENERATE_COLUMN_SYNONYMS,
    generate_measure_synonyms=GENERATE_MEASURE_SYNONYMS,
)
engine.build()
# Edit this list to preview a subset: "tables", "columns", "measures"
# Source: Databricks | AI | Existing | Missing | Manual | Cleared
PREVIEW_OBJECT_TYPES = ["tables", "columns", "measures"]
preview_df = engine.preview(object_types=PREVIEW_OBJECT_TYPES)
display(preview_df)
engine.summary()

# =========================
# Cell 6: Filter preview rows and update proposed metadata
# =========================
# Path A — many objects: copy filtered rows into updates_df / UPDATES, edit, apply.
# Path B — one object: uncomment the single-object call at the bottom.
# Filters are case-insensitive. Leave a filter as None / empty to skip it.
# MATCH_MODE applies to FILTER_TABLE_NAME and FILTER_OBJECT_NAME only.

# --- What to update (filters apply to preview_df) ---
FILTER_OBJECT_TYPES = ["columns"]          # "tables", "columns", "measures" or mix
FILTER_TABLE_NAME = None                   # exact table, e.g. "fact_onhanddetails"; None = all
FILTER_OBJECT_NAME = None                  # exact object name, or substring if MATCH_MODE = "contains"
FILTER_SOURCE = None                       # "AI", "Databricks", "Existing", "Missing", "Manual"; None = all
MATCH_MODE = "exact"                       # "exact" or "contains" for table/object name

_preview = globals().get("preview_df")
try:
    filtered_df = filter_preview_for_update(
        _preview,
        object_types=FILTER_OBJECT_TYPES,
        table_name=FILTER_TABLE_NAME,
        object_name=FILTER_OBJECT_NAME,
        source=FILTER_SOURCE,
        match_mode=MATCH_MODE,
    )
except Exception as exc:
    print(f"Could not filter preview: {type(exc).__name__}: {exc}")
    raise

n_filtered = 0 if filtered_df is None else len(filtered_df)
print(f"Filtered preview: {n_filtered} row(s).")
try:
    display(filtered_df)
except Exception:
    print(filtered_df.to_string() if filtered_df is not None else "(no DataFrame)")

# Path A — Filter preview, then edit many rows as a list / DataFrame
# Copy filtered rows into an editable updates table.
# Change Proposed Description / Proposed Synonyms on the rows you want, delete rows you do not want.
updates_df = filtered_df.copy() if filtered_df is not None else filtered_df
# Optional: edits in code
# updates_df.loc[updates_df["Object Name"] == "DIOH Card", "Proposed Description"] = "..."

APPLY_FILTERED_UPDATES = False
# False: print one update_proposed_metadata(...) per row (bulk list form + per-row form)
# True: update_proposed_metadata(updates=updates_df)

UPDATES = [
    {
        "object_name": "DIOH Card",
        "table_name": "_Measure",
        "object_type": "measure",
        "new_desc": "Average number of days of inventory on hand.",
        "new_synonyms": ["days of inventory", "inventory days", "stock coverage days"],
    },
    # add more dicts: mix tables, columns, measures
]

# update_proposed_metadata(updates=UPDATES)   # uncomment to apply

# Path B — One object (kwargs, or one preview-column dict)
# update_proposed_metadata(
#     object_name="DIOH Card",
#     new_desc="Average number of days of inventory on hand.",
#     new_synonyms=["days of inventory", "inventory days", "stock coverage days"],
#     table_name="_Measure",
#     object_type="measure",
# )

# Same keys as preview_df columns. Source / Original Description are ignored.
# update_proposed_metadata(updates={
#     "Object Type": "Measure",
#     "Table Name": "__Measures",
#     "Object Name": "ASP Prior PTD",
#     "Source (Databricks vs AI)": "AI",
#     "Original Description": "",
#     "Proposed Description": "Prior period-to-date average selling price per unit (ASP Prior PTD).",
#     "Proposed Synonyms": "prior period to date average price, average unit price prior period to date",
# })
# Also valid: update_proposed_metadata(updates=[{...preview columns...}, {...}])
# Also valid: update_proposed_metadata(updates=filtered_df)

if filtered_df is None or getattr(filtered_df, "empty", True):
    print("No preview rows matched the filters. Adjust FILTER_* and re-run.")
elif APPLY_FILTERED_UPDATES:
    update_proposed_metadata(updates=updates_df)
    preview_df = engine.preview(object_types=FILTER_OBJECT_TYPES, announce=False)
    filtered_df = filter_preview_for_update(
        preview_df,
        object_types=FILTER_OBJECT_TYPES,
        table_name=FILTER_TABLE_NAME,
        object_name=FILTER_OBJECT_NAME,
        source=FILTER_SOURCE,
        match_mode=MATCH_MODE,
    )
    print(f"Filtered preview: {len(filtered_df)} row(s).")
    try:
        display(filtered_df)
    except Exception:
        print(filtered_df.to_string() if filtered_df is not None else "(no DataFrame)")
else:
    calls = format_update_calls(filtered_df)
    for call in calls:
        print(call)
        print()
    print(
        f"Printed bulk + per-row update_proposed_metadata(...) for {n_filtered} row(s). "
        "Set APPLY_FILTERED_UPDATES = True to run update_proposed_metadata(updates=updates_df)."
    )

# =========================
# Cell 6b: Review / edit / clear (proposed state only)
# =========================
# update_proposed_metadata("DIOH Card", new_desc="Average days of inventory on hand.", table_name="_Measure")
# clear_metadata(scope="measures", target_name="DIOH Card")
# clear_metadata(scope="all")
# Session: column descriptions on one table; Proposed Synonyms left unchanged.
# clear_metadata(
#     scope="columns",
#     target_name="fact_onhanddetails",  # or ["fact_a", "fact_b"]
#     clear_descriptions=True,
#     clear_synonyms=False,
# )
# Session: column synonyms on one table; descriptions / comments left unchanged.
# Write-through sets Replace Synonyms so apply removes live Q&A synonyms.
# clear_metadata(
#     scope="columns",
#     target_name="fact_onhanddetails",  # or ["fact_a", "fact_b"]
#     clear_descriptions=False,
#     clear_synonyms=True,
# )
# Live: column descriptions on one table only (synonym switches stay "no").
# Review the dry-run first, then dry_run="no".
# clear_semantic_model_metadata(
#     DATASET_NAME,
#     WORKSPACE_NAME,
#     only_tables=["fact_onhanddetails"],
#     clear_column_descriptions="yes",
#     dry_run="yes",
# )
# Live: column synonyms on one table only. clear_column_descriptions stays "no"
# by default, so comments are not wiped. Review the dry-run, then dry_run="no".
# clear_semantic_model_metadata(
#     DATASET_NAME,
#     WORKSPACE_NAME,
#     only_tables=["fact_onhanddetails"],
#     clear_column_synonyms="yes",
#     dry_run="yes",
# )
# Session clear only. To regenerate AI after wiping the live model:
# clear_semantic_model_metadata(DATASET_NAME, WORKSPACE_NAME, clear_everything="yes", dry_run="no")
# engine.build()

# =========================
# Cell 7: Dry-run (default) then optional apply
# =========================

APPLY_CHANGES = False

summary = engine.apply(
    apply_changes=APPLY_CHANGES,
    overwrite_tables=OVERWRITE_TABLES,
    overwrite_columns=OVERWRITE_COLUMNS,
    overwrite_measures=OVERWRITE_MEASURES,
    overwrite_column_synonyms=OVERWRITE_COLUMN_SYNONYMS,
    overwrite_measure_synonyms=OVERWRITE_MEASURE_SYNONYMS,
)

# =========================
# Cell 8: AI instructions (optional — default OFF)
# =========================
%run Utilities_AIInstruction   # after %run Utilities; this file also works standalone

GENERATE_AI_INSTRUCTIONS = False          # default skip
AI_INSTRUCTION_AUDIENCE = "copilot"       # "copilot" | "pbi_developers"

ai_engine = init_ai_instructions(
    dataset_name=DATASET_NAME,
    workspace_name=WORKSPACE_NAME,
    audience=AI_INSTRUCTION_AUDIENCE,
)
if GENERATE_AI_INSTRUCTIONS:
    ai_engine.build()          # inspect model + Fabric AI
    print(ai_engine.preview()) # markdown string
    # ai_engine.apply(apply_changes=False)  # dry-run
    # ai_engine.apply(apply_changes=True)   # write Copilot instructions if TOM supports it
else:
    print("=== AI instructions: skipped (GENERATE_AI_INSTRUCTIONS=False) ===")
