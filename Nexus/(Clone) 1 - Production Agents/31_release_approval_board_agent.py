# Databricks notebook source
# DBTITLE 1,Release Approval Board Agent
# MAGIC %md
# MAGIC # Agent 31 — Release Approval Board
# MAGIC
# MAGIC **Purpose:** HARD GATE — Final production approval. Validates all prior agents completed, generates ProductionApproval.md and ReleaseChecklist.md.
# MAGIC
# MAGIC **Output:** ProductionApproval.md, ReleaseChecklist.md (APPROVE/REJECT with reasoning).

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Release approval execution
RELEASE_PROMPT = """You are the Release Approval Board (RAB) for Hologic. This is the FINAL GATE before production.

You MUST verify ALL of the following before approving:

## MANDATORY GATES (ALL must pass)

1. ✅ Architecture Review (Agent 06) — HLD/LLD produced and approved
2. ✅ Code Generated (Agent 02) — Production-ready code exists
3. ✅ Data Quality Rules (Agent 16) — DQ expectations defined
4. ✅ Security Review (Agent 17) — No CRITICAL findings
5. ✅ Peer Review (Agent 07) — Score >= 7/10, no CRITICAL findings
6. ✅ Unit Tests (Agent 08) — Test suite generated
7. ✅ Environment Promotion (Agent 09) — DEV→UAT validated

## APPROVAL DECISION

Respond with:
{
    "decision": "APPROVED" or "REJECTED" or "CONDITIONAL",
    "gates_passed": ["list of passed gates"],
    "gates_failed": ["list of failed gates"],
    "conditions": ["conditions that must be met if CONDITIONAL"],
    "risk_level": "LOW" or "MEDIUM" or "HIGH",
    "approved_by": "Release Approval Board (AI Agent 31)",
    "notes": "any additional notes"
}

If ANY mandatory gate has no output: REJECT immediately.
If Security has CRITICAL findings: REJECT immediately.
If Peer Review score < 6: REJECT immediately.
"""

# Check all gates
run_id = generate_run_id()
gates = {
    "architecture": get_latest_agent_output("solution_architect", "architecture_document"),
    "code": get_latest_agent_output("data_engineer", "generated_code"),
    "data_quality": get_latest_agent_output("data_quality", "quality_framework"),
    "security": get_latest_agent_output("security", "security_review"),
    "peer_review": get_latest_agent_output("peer_review", "review_report"),
    "unit_test": get_latest_agent_output("unit_test", "test_suite"),
    "promotion": get_latest_agent_output("environment_promotion", "promotion_checklist"),
}

gate_summary = "\n".join([f"- {k}: {'\u2705 EXISTS' if v else '\u274c MISSING'}" for k, v in gates.items()])
missing = [k for k, v in gates.items() if not v]

if missing:
    user_prompt = f"""## Gate Status\n{gate_summary}\n\nMISSING GATES: {', '.join(missing)}\n\nMake your approval decision."""
else:
    user_prompt = f"""## Gate Status (ALL PRESENT)\n{gate_summary}\n\n## Gate Contents (summaries)\n"""
    for k, v in gates.items():
        if v:
            user_prompt += f"\n### {k}\n{v[:500]}\n"
    user_prompt += "\nMake your approval decision."

result = call_agent("data_engineer", RELEASE_PROMPT, user_prompt, max_tokens=1500)
save_agent_output("release_approval", run_id, "approval_decision", result, {"missing_gates": missing})
print(result)
print(f"\n✅ Agent 31 (Release Approval Board) completed | Run ID: {run_id}")