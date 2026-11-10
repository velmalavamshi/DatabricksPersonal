# Databricks notebook source
# DBTITLE 1,Python Ecosystem Release Monitor
# MAGIC %md
# MAGIC # 🐍 Agent 86 — Python Ecosystem Release Monitor
# MAGIC
# MAGIC **Purpose:** Monitors major Python library breaking changes (pandas, numpy, pyarrow, etc.) that surface during DBR upgrades, preventing the "notebook broke after cluster restart" scenario.
# MAGIC
# MAGIC **Tier:** STANDARD | **Called by:** Agent 77 | **Schedule:** Monthly (aligned to DBR upgrades)

# COMMAND ----------

# DBTITLE 1,STEP 1 — Inherit shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,STEP 2+3 — Python Ecosystem Context + LLM Analysis
# ══════════════════════════════════════════════════════════════════════
import json
from datetime import datetime, timedelta

dbutils.widgets.text("days_lookback", "30", "Days to Look Back")
dbutils.widgets.text("triggered_by", "77_orchestrator", "Triggered By")
days_lookback = int(dbutils.widgets.get("days_lookback"))
run_id = generate_run_id()

PYTHON_ENV = {
    "critical_libraries": [
        "pandas (2.x → 3.x transition: copy-on-write default, removed deprecated APIs)",
        "numpy (1.x → 2.x: dtype changes, removed aliases, stricter casting)",
        "pyarrow (Arrow IPC changes, pandas backend)",
        "pyspark (API stability tied to Spark version)",
        "openai (client library for Foundation Model API)",
        "mlflow (3.x: new tracking API, UC registry changes)",
        "delta-spark (Delta Lake Python bindings)",
    ],
    "secondary_libraries": [
        "requests", "python-pptx", "openpyxl", "matplotlib",
        "scikit-learn", "sqlalchemy", "cryptography",
    ],
    "python_version": "3.11 (bundled in DBR 17.3)",
    "risk_scenarios": [
        "DBR upgrade pulls new pandas/numpy → agent notebooks break on import",
        "openai client API change → call_agent() breaks for all 112 agents",
        "pyarrow change → Delta Lake read/write behavior changes",
        "mlflow 3.x deprecations → experiment tracking code breaks",
    ],
}

PY_SYSTEM_PROMPT = """You are the Python Ecosystem Release Monitor for Hologic's Databricks platform.

Monitor: Major library version bumps that ship with DBR upgrades. Focus on pandas 3.x, numpy 2.x, pyarrow, openai client, mlflow 3.x.

Hologic uses: 112 NEXUS agents (PySpark + pandas + openai + mlflow), DBR 17.3 (Python 3.11).

Key concern: When Hologic upgrades DBR, bundled library versions change silently. A pandas 3.x breaking change in copy-on-write or a numpy 2.x dtype alias removal can break dozens of notebooks simultaneously.

Impact Rules:
- CRITICAL: openai client breaking change (breaks all 112 agents), pandas/numpy major version in next DBR
- HIGH: mlflow API deprecation, pyarrow breaking change, pyspark behavioral change
- MEDIUM: New library features worth adopting, deprecation warnings to address proactively
- LOW: Minor patch releases, security-only fixes, non-breaking additions

Return JSON: {vendor, items: [{title, impact_level, description, hologic_impact, affected_libraries, action_required, deadline}], summary}
"""

user_prompt = f"""Analyze Python ecosystem changes (last {days_lookback} days) that could impact Hologic on next DBR upgrade.

Current: Python {PYTHON_ENV['python_version']}
Critical libraries: {chr(10).join('- ' + l for l in PYTHON_ENV['critical_libraries'])}
Risk scenarios: {chr(10).join('- ' + r for r in PYTHON_ENV['risk_scenarios'])}

Key questions:
1. pandas 3.x — is copy-on-write default? What breaks?
2. numpy 2.x — removed aliases (np.float_, np.int_)?
3. openai client — any v2 breaking changes?
4. mlflow 3.x — deprecated APIs we might use?
5. pyarrow — changes affecting Delta Lake pandas integration?

Return JSON.
"""

response = call_agent("86_python_ecosystem_release_monitor", PY_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=4096)
try:
    json_str = response.split("```json")[1].split("```")[0] if "```json" in response else response
    py_result = json.loads(json_str.strip())
    print(f"\n✅ Python Ecosystem Analysis Complete: {len(py_result.get('items', []))} items")
except Exception as e:
    py_result = {"vendor": "python_ecosystem", "raw_response": response, "parse_error": str(e)}
    print(f"\n⚠️  Parse issue: {e}")
try:
    save_agent_output("86_python_ecosystem_release_monitor", run_id, "python_release_analysis", json.dumps(py_result, indent=2), {"python": PYTHON_ENV['python_version']})
except: pass