# Databricks notebook source
# DBTITLE 1,Champion Coach
# MAGIC %md
# MAGIC # Agent 04 — Champion Coach (W3)
# MAGIC
# MAGIC **Purpose:** Generates talking points, objection handlers, and stakeholder-specific messaging to help internal champions sell the initiative.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W3 (Business Champions) |
# MAGIC | Inputs | Business case, target stakeholder persona |
# MAGIC | Outputs | Coaching brief (talking points, objection responses, elevator pitch) |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_bc_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Generate Coaching Brief
# ======================================================================
# STEP 1 — GENERATE CHAMPION COACHING BRIEF
# ======================================================================

AGENT_NAME = "04_champion_coach"

dbutils.widgets.text("project_name", "Predictive Job Failure Prevention", "Project Name")
dbutils.widgets.text("stakeholder", "cto", "Target Stakeholder (cfo/cto/coo/board/vp_data)")

project_name = dbutils.widgets.get("project_name")
stakeholder = dbutils.widgets.get("stakeholder")
persona = STAKEHOLDER_PERSONAS.get(stakeholder, STAKEHOLDER_PERSONAS['board'])

# Get business case if available
try:
    bc_content = BUSINESS_CASE['content'][:2000]
    financials_str = f"NPV: ${BUSINESS_CASE['financials']['base']['npv_3yr']:,.0f}, ROI: {BUSINESS_CASE['financials']['base']['roi_pct']:.0f}%, Payback: {BUSINESS_CASE['financials']['base']['payback_months']:.1f} months"
except NameError:
    bc_content = "Business case not loaded. Using general context."
    financials_str = "TBD"

COACH_PROMPT = f"""You are a champion coaching assistant. Generate a comprehensive coaching brief for an internal champion who needs to sell this initiative to a {stakeholder.upper()}.

Project: {project_name}
Financials: {financials_str}
Stakeholder priorities: {', '.join(persona['priorities'])}
Desired tone: {persona['tone']}

Business context (summary): {bc_content[:1000]}

Generate the following sections:

## 30-Second Elevator Pitch
(Exactly what to say if you have 30 seconds in an elevator)

## Key Talking Points (5)
(Ordered by what {stakeholder.upper()} cares about most)

## Objection Responses
For each of these common objections, provide a 2-3 sentence response tailored to the {stakeholder.upper()}:
1. "We don't have budget for this"
2. "Our team is already stretched thin"
3. "We tried AI before and it didn't work"
4. "The data isn't ready"
5. "Security/compliance concerns"
6. "Can we just hire more people instead?"
7. "What's the competitive urgency?"

## Meeting Strategy
- Best time/format to present
- Who else should be in the room
- What NOT to say
- How to handle "let me think about it"

## Follow-Up Email Template
(Short email to send after the meeting - 5 sentences max)

Be specific to medical devices industry and Databricks platform."""

print(f"Generating coaching brief for {stakeholder.upper()} meeting...")
coaching_brief = call_llm(COACH_PROMPT, max_tokens=3000, temperature=0.3)

print(f"\n\u2705 Coaching brief generated ({len(coaching_brief):,} chars)")
print(f"   Project: {project_name}")
print(f"   Stakeholder: {stakeholder.upper()}")
print(f"   Tone: {persona['tone']}")
print("\n" + "=" * 60)
print(coaching_brief)