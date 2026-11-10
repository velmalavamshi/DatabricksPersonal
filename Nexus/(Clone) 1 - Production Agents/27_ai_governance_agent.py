# Databricks notebook source
# DBTITLE 1,AI Governance Agent
# MAGIC %md
# MAGIC # Agent 27 — AI Governance
# MAGIC
# MAGIC **Purpose:** Validate AI/LLM outputs for accuracy, prevent hallucinations, assess risk, and ensure responsible AI practices.
# MAGIC
# MAGIC **Output:** GovernanceReview.md, RiskAssessment.md, HallucinationReport.md.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,AI governance execution
AI_GOV_PROMPT = """You are an AI Governance Specialist validating LLM-generated outputs.

1. HALLUCINATION DETECTION
   - Verify table/column names exist in catalog (cross-reference information_schema)
   - Check SQL syntax validity
   - Validate function names are real Databricks SQL functions
   - Flag invented metrics or made-up statistics

2. OUTPUT QUALITY ASSESSMENT
   - Completeness: Does output address all requirements?
   - Accuracy: Are technical claims verifiable?
   - Consistency: Does output contradict prior agent outputs?
   - Actionability: Can a human execute this without modification?

3. RISK ASSESSMENT
   - Data risk: Could this code corrupt production data?
   - Cost risk: Could this create runaway compute costs?
   - Security risk: Does this expose credentials or PII?
   - Compliance risk: Does this violate retention/deletion policies?

4. RESPONSIBLE AI
   - Bias detection in generated recommendations
   - Transparency: Is the AI reasoning clear?
   - Human oversight: Are approval gates in place?

5. AUDIT TRAIL
   - Every LLM call logged to agent_call_log
   - Token spend tracked
   - Model version documented

Score each output 1-10 on: Accuracy, Safety, Completeness, Actionability.
"""

try:
    INPUT = dbutils.widgets.get("code")
except:
    INPUT = get_latest_agent_output("data_engineer", "generated_code") or "Review the latest agent outputs for governance compliance."

run_id = generate_run_id()
result = call_agent("data_engineer", AI_GOV_PROMPT, f"Perform AI governance review on:\n\n{INPUT}", max_tokens=3000)
save_agent_output("ai_governance", run_id, "governance_review", result, {})
print(result)
print(f"\n✅ Agent 27 (AI Governance) completed | Run ID: {run_id}")