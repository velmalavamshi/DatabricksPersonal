# Databricks notebook source
# DBTITLE 1,Agent 95: Qlik NPrinting Agent
# MAGIC %md
# MAGIC # Agent 95: Qlik NPrinting Agent
# MAGIC
# MAGIC **Purpose:** Converts Qlik NPrinting report templates and distribution schedules to Databricks equivalents (Lakeview subscriptions, Jobs + notebook report generation, email distribution).
# MAGIC
# MAGIC **Pipeline Position:** Specialist Layer → called by Agent 88 (orchestrator)
# MAGIC
# MAGIC **Inputs:**
# MAGIC - NPrinting report templates (Excel, Word, PowerPoint, HTML, PixelPerfect)
# MAGIC - Distribution schedules (daily/weekly/monthly, recipients, conditions)
# MAGIC - NPrinting connections (which QVW/QVF apps feed the reports)
# MAGIC - Filters/selections applied per report
# MAGIC
# MAGIC **Outputs:**
# MAGIC - Databricks Job definitions (scheduled report generation)
# MAGIC - Lakeview dashboard subscriptions (for interactive reports)
# MAGIC - Notebook-based report generators (Excel/PDF/PPTX via openpyxl/python-pptx)
# MAGIC - Email distribution config (SMTP or Teams webhook)
# MAGIC - Migration mapping: NPrinting template → Databricks equivalent
# MAGIC
# MAGIC **NPrinting Report Types:**
# MAGIC - Excel: Template-based with tags → openpyxl notebook
# MAGIC - Word: Merge fields with data → python-docx notebook  
# MAGIC - PowerPoint: Slide templates with charts/tables → python-pptx notebook
# MAGIC - HTML: Web reports → Lakeview dashboard (public link)
# MAGIC - PixelPerfect: Pixel-precise PDF → FPDF/ReportLab notebook
# MAGIC - QlikEntity: Embedded Qlik objects as images → Lakeview screenshots
# MAGIC
# MAGIC **NPrinting Distribution:**
# MAGIC - Publish to folder, email, hub
# MAGIC - Conditions (only send if data meets criteria)
# MAGIC - Recipient lists (static, dynamic from LDAP)
# MAGIC - Burst reports (one per filter value, e.g., per region)

# COMMAND ----------

# DBTITLE 1,Inherit Shared Config
# %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 1 - Widgets
# ══════════════════════════════════════════════════════════════════════
# STEP 1: Input Widgets
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "NPrinting Migration Request")
dbutils.widgets.multiline("nprinting_config", "", "NPrinting Report Config (paste details)")
dbutils.widgets.dropdown("report_type", "excel", ["excel", "word", "powerpoint", "html", "pixelperfect", "mixed"], "Primary Report Type")
dbutils.widgets.text("run_id", "", "Run ID")

request = dbutils.widgets.get("request")
nprinting_config = dbutils.widgets.get("nprinting_config")
report_type = dbutils.widgets.get("report_type")
run_id = dbutils.widgets.get("run_id") or generate_run_id()

# COMMAND ----------

# DBTITLE 1,STEP 2 - Context Gathering
# ══════════════════════════════════════════════════════════════════════
# STEP 2: Context — NPrinting → Databricks Equivalents
# ══════════════════════════════════════════════════════════════════════

# NPrinting report type → Databricks delivery mechanism
NPRINTING_TO_DATABRICKS = {
    "Excel (template-based)": {
        "mechanism": "Databricks Job + openpyxl notebook",
        "pattern": "Query Gold layer → format with openpyxl → save to Volume → email",
        "libraries": ["openpyxl", "xlsxwriter"],
    },
    "Word (merge fields)": {
        "mechanism": "Databricks Job + python-docx notebook",
        "pattern": "Query Gold layer → populate template with python-docx → save/email",
        "libraries": ["python-docx"],
    },
    "PowerPoint (slide templates)": {
        "mechanism": "Databricks Job + python-pptx notebook",
        "pattern": "Query Gold layer → build slides with python-pptx → save/email",
        "libraries": ["python-pptx", "matplotlib"],
    },
    "HTML (web reports)": {
        "mechanism": "Lakeview dashboard + subscription OR Databricks App",
        "pattern": "Create Lakeview dashboard → enable email subscription",
        "libraries": [],
    },
    "PixelPerfect (PDF)": {
        "mechanism": "Databricks Job + FPDF2/ReportLab notebook",
        "pattern": "Query Gold layer → generate PDF with precise layout → save/email",
        "libraries": ["fpdf2", "reportlab"],
    },
    "QlikEntity (object images)": {
        "mechanism": "Lakeview dashboard (screenshot/PDF export)",
        "pattern": "Recreate charts in Lakeview → use built-in export/subscribe",
        "libraries": [],
    },
}

# Distribution mechanism mapping
DISTRIBUTION_MAPPING = {
    "Email (SMTP)": "Databricks Job notification OR custom SMTP notebook cell",
    "Folder publish": "Write to UC Volume (/Volumes/catalog/schema/volume/reports/)",
    "Hub publish": "Lakeview dashboard (shared with workspace users)",
    "Conditional send": "Databricks Job with IF/ELSE task (check condition query first)",
    "Burst (per filter value)": "Databricks Job with FOR EACH task OR parameterized notebook",
    "Dynamic recipients (LDAP)": "Query Entra ID groups or recipient table in Gold",
}

# Schedule mapping
SCHEDULE_MAPPING = {
    "Daily": "cron: 0 0 7 * * ? *  (7 AM daily)",
    "Weekly (Monday)": "cron: 0 0 7 ? * MON *",
    "Monthly (1st)": "cron: 0 0 7 1 * ? *",
    "Monthly (last business day)": "cron: 0 0 7 L * ? * (with skip logic)",
    "On QVW reload": "Trigger: downstream task after data pipeline completes",
    "On demand": "Manual run or API trigger",
}

print(f"✅ NPrinting context loaded")
print(f"   {len(NPRINTING_TO_DATABRICKS)} report type mappings")
print(f"   {len(DISTRIBUTION_MAPPING)} distribution patterns")
print(f"   {len(SCHEDULE_MAPPING)} schedule mappings")

# COMMAND ----------

# DBTITLE 1,STEP 3 - Context Formatting
# ══════════════════════════════════════════════════════════════════════
# STEP 3: Context Formatting
# ══════════════════════════════════════════════════════════════════════

import json

system_prompt = f"""You are the Qlik NPrinting Agent (Agent 95) for Hologic's NEXUS platform.

You convert NPrinting report templates and distribution schedules to Databricks equivalents.

NPrinting → Databricks Mapping:
{json.dumps(NPRINTING_TO_DATABRICKS, indent=2)}

Distribution Mapping:
{json.dumps(DISTRIBUTION_MAPPING, indent=2)}

Schedule Mapping:
{json.dumps(SCHEDULE_MAPPING, indent=2)}

Your Deliverables:
1. REPORT INVENTORY: List all NPrinting reports with type, schedule, recipients
2. MECHANISM SELECTION: Choose Databricks equivalent for each report
3. JOB DEFINITION: Databricks Job config (schedule, tasks, notifications)
4. NOTEBOOK CODE: Report generation notebook (query + format + save)
5. DISTRIBUTION CONFIG: Email/Volume/subscription setup
6. BURST LOGIC: For parameterized reports (one per filter value)

Implementation Patterns:

Pattern A — Interactive Dashboard (HTML reports):
  NPrinting HTML → Lakeview dashboard
  - Create Lakeview dashboard with equivalent charts
  - Enable email subscription (daily/weekly PDF snapshot)
  - Share with recipients via workspace permissions

Pattern B — Formatted Report (Excel/Word/PPT):
  NPrinting template → Databricks Job + notebook
  - Notebook queries Gold layer tables
  - Uses openpyxl/python-pptx/python-docx to populate template
  - Saves to UC Volume: /Volumes/mde_prd/reports/{{report_name}}/
  - Job sends email notification with download link

Pattern C — Burst Reports (per filter value):
  NPrinting burst → Parameterized Job
  - FOR EACH task iterates over filter values (regions, customers)
  - Each iteration generates filtered report
  - Conditional: only generate if data meets threshold

Hologic Standards:
- Reports saved to: /Volumes/mde_prd/reports/ (prod) or /Volumes/mde_dev/reports/ (dev)
- Schedules: Databricks Jobs with cron expressions
- Notifications: email via Job notification or custom SMTP
- Audit: log report generation to mde_dev.test_schema.report_execution_log
"""

user_prompt = f"""Request: {request}
Report Type: {report_type}

NPrinting Configuration:
{nprinting_config or '[No config provided - provide general migration guidance]'}

Please create the NPrinting → Databricks migration plan for these reports."""

print(f"✅ Prompts formatted — Report type: {report_type}")

# COMMAND ----------

# DBTITLE 1,STEP 4 - LLM Call
# ══════════════════════════════════════════════════════════════════════
# STEP 4: LLM Call
# ══════════════════════════════════════════════════════════════════════

response = call_agent(
    agent_name="95_qlik_nprinting",
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
assert any(kw in response.lower() for kw in ["report", "job", "schedule", "email", "notebook", "distribution"]), \
    "Response missing NPrinting migration content"

save_agent_output(
    agent_name="95_qlik_nprinting",
    run_id=run_id,
    output_type=f"nprinting_migration_{report_type}",
    content=response,
    metadata={"report_type": report_type}
)

print(f"\n✅ Agent 95 complete — NPrinting migration plan saved")
print(f"📋 Run ID: {run_id}")

# COMMAND ----------

