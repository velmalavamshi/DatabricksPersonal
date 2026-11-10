# Databricks notebook source
# DBTITLE 1,Agent 93: Qlik UI Migration Agent
﻿# Databricks notebook source
%md
# Agent 93: Qlik UI Migration Agent

**Purpose:** Maps QlikView/Qlik Sense visualization objects (charts, tables, KPIs, listboxes, filters) to Lakeview dashboards or Power BI reports.

**Pipeline Position:** Specialist Layer → called by Agent 88 (orchestrator)

**Inputs:**
- QVW/QVF sheet layouts and object definitions
- Chart types, dimensions, measures, expressions
- Object properties (colors, sorting, conditional visibility)

**Outputs:**
- Lakeview dashboard specs (datasets, widgets, filters)
- Power BI measure definitions (if PBI target)
- UI migration mapping report
- Unsupported feature log (requires manual design)

**QlikView Object Types:**
- Listbox, Multi Box, Table Box, Statistics Box
- Bar Chart, Line Chart, Combo Chart, Pie Chart, Scatter Plot
- Pivot Table, Straight Table
- Gauge, KPI Object, Text Object
- Container, Tab Container
- Current Selections Box, Bookmark Object
- Input Box, Slider/Calendar Object

**Qlik Sense Object Types:**
- Filter Pane, KPI, Bar/Line/Area/Pie/Donut/Scatter/Treemap
- Table, Pivot Table, Combo Chart, Waterfall
- Map, Distribution Plot, Box Plot, Bullet Chart
- Text & Image, Button, Container, Tabs

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "UI Migration Request")
dbutils.widgets.multiline("object_definitions", "", "Qlik Object Definitions (paste JSON/text)")
dbutils.widgets.dropdown("target_platform", "lakeview", ["lakeview", "powerbi", "both"], "Target Platform")
dbutils.widgets.text("app_name", "", "Source Qlik App Name")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
object_definitions = dbutils.widgets.get("object_definitions")
target_platform = dbutils.widgets.get("target_platform")
app_name = dbutils.widgets.get("app_name")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context — Qlik Object → Databricks Visualization Mapping
# ══════════════════════════════════════════════════════════════════════

# QlikView objects → Lakeview widget types
QLIKVIEW_TO_LAKEVIEW = {
    "Listbox": "Filter widget (dropdown/multi-select)",
    "Multi Box": "Multiple filter widgets (one per field)",
    "Current Selections Box": "Active filters display (built-in to Lakeview)",
    "Bar Chart": "Bar chart widget",
    "Line Chart": "Line chart widget",
    "Combo Chart": "Combo chart widget (bar + line)",
    "Pie Chart": "Pie/donut chart widget",
    "Scatter Plot": "Scatter plot widget",
    "Straight Table": "Table widget",
    "Pivot Table": "Table widget with grouping (limited pivot in Lakeview)",
    "Gauge": "KPI widget with conditional formatting",
    "KPI Object": "Counter/KPI widget",
    "Text Object": "Text widget (markdown)",
    "Container": "Tab layout (Lakeview pages)",
    "Slider": "Parameter widget (range input)",
    "Calendar Object": "Date range filter widget",
    "Input Box": "Parameter widget (text input)",
    "Statistics Box": "KPI widgets (one per stat: sum, avg, count)",
    "Table Box": "Table widget (simplified)",
    "Bookmark Object": "⚠️ No direct equivalent — use saved filter presets",
    "Map Chart": "⚠️ Limited — use Power BI for geospatial",
}

# Qlik Sense objects → Lakeview
QLIK_SENSE_TO_LAKEVIEW = {
    "Filter Pane": "Filter widget(s)",
    "KPI": "Counter widget",
    "Bar Chart": "Bar chart widget",
    "Line Chart": "Line chart widget",
    "Area Chart": "Area chart widget",
    "Combo Chart": "Combo chart widget",
    "Pie Chart": "Pie chart widget",
    "Donut Chart": "Pie chart widget (donut mode)",
    "Scatter Plot": "Scatter widget",
    "Treemap": "⚠️ No direct equivalent — use bar chart or Power BI",
    "Table": "Table widget",
    "Pivot Table": "Table widget (limited grouping)",
    "Waterfall": "⚠️ No direct equivalent — use stacked bar or Power BI",
    "Box Plot": "⚠️ Limited — use Power BI",
    "Bullet Chart": "Bar chart with reference lines",
    "Map": "⚠️ No direct equivalent — use Power BI Map visual",
    "Distribution Plot": "Histogram widget",
    "Text & Image": "Text widget (markdown)",
    "Button": "⚠️ Actions not supported — use navigation links",
    "Container": "Tabs/pages",
}

# Interaction patterns that differ
INTERACTION_DIFFERENCES = {
    "Click-to-filter (associative)": "Lakeview: explicit filter widgets; PBI: cross-filter",
    "Green/White/Gray selections": "Lakeview: dropdown multi-select (no color coding)",
    "Alternate states": "⚠️ Not supported — use separate dashboard pages",
    "Set analysis in expressions": "Pre-computed in SQL dataset (Agent 92 handles)",
    "Cyclic dimensions": "Parameter widget to switch dimension column",
    "Drill-down dimensions": "Lakeview supports drill-down on hierarchies",
    "Conditional show/hide": "Limited — use separate pages or dynamic SQL",
}

print(f"✅ UI mapping context loaded")
print(f"   {len(QLIKVIEW_TO_LAKEVIEW)} QlikView object mappings")
print(f"   {len(QLIK_SENSE_TO_LAKEVIEW)} Qlik Sense object mappings")
print(f"   {len(INTERACTION_DIFFERENCES)} interaction pattern notes")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting
# ══════════════════════════════════════════════════════════════════════

import json

system_prompt = f"""You are the Qlik UI Migration Agent (Agent 93) for Hologic's NEXUS platform.

You map Qlik visualization objects to {target_platform} equivalents.

QlikView → Lakeview Mapping:
{json.dumps(QLIKVIEW_TO_LAKEVIEW, indent=2)}

Qlik Sense → Lakeview Mapping:
{json.dumps(QLIK_SENSE_TO_LAKEVIEW, indent=2)}

Interaction Pattern Differences:
{json.dumps(INTERACTION_DIFFERENCES, indent=2)}

Your Output:
1. OBJECT INVENTORY: List all objects in the source app with type classification
2. MIGRATION MAP: Source object → target widget/visual (1:1 or 1:N mapping)
3. UNSUPPORTED LOG: Objects requiring manual redesign (with alternatives)
4. DASHBOARD SPEC: Proposed layout (pages, widgets, filters, datasets)
5. EXPRESSION DEPENDENCIES: Flag expressions needing Agent 92 conversion

Lakeview-Specific Guidance:
- Datasets = SQL queries against Gold layer views
- Widgets bind to dataset columns (no inline expressions)
- Filters are cross-widget within a page
- Parameters can simulate Qlik variables
- Max ~15-20 widgets per page for usability

Power BI-Specific Guidance (if target=powerbi):
- Measures in DAX (similar to Qlik expressions)
- Cross-filter behavior (closest to Qlik associative)
- Custom visuals available for unsupported types
- DirectQuery mode for Databricks connection
"""

user_prompt = f"""Request: {request}
Target Platform: {target_platform}
Source App: {app_name or 'Not specified'}

Object Definitions:
{object_definitions or '[No object definitions provided - provide general migration guidance]'}

Please create the UI migration mapping and dashboard specification."""

print(f"✅ Prompts formatted — Target: {target_platform}")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call
# ══════════════════════════════════════════════════════════════════════

response = call_agent(
    agent_name="93_qlik_ui_migration",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=6144
)

print(response)

# COMMAND ----------

# DBTITLE 1,STEP 5 - Validate and Persist
# ══════════════════════════════════════════════════════════════════════
# STEP 5: Validate & Persist
# ══════════════════════════════════════════════════════════════════════

assert len(response) > 100, "Response too short"

save_agent_output(
    agent_name="93_qlik_ui_migration",
    run_id=run_id,
    output_type=f"ui_migration_{target_platform}",
    content=response,
    metadata={"target_platform": target_platform, "app_name": app_name}
)

print(f"\n✅ Agent 93 complete — UI migration spec saved")
print(f"📋 Run ID: {run_id}")

# COMMAND ----------

