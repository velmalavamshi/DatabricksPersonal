# Databricks notebook source
# DBTITLE 1,Business Case Builder
# MAGIC %md
# MAGIC # Agent 01 — Business Case Builder (W3)
# MAGIC
# MAGIC **Purpose:** Takes a scored use case (from W2) or ad-hoc request, and produces a full board-ready business case with NPV, ROI, risk analysis, and implementation timeline.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W3 (Business Champions) |
# MAGIC | Inputs | Use case description, cost estimates, benefit estimates |
# MAGIC | Outputs | Structured business case (JSON + markdown) |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_bc_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Define Use Case Input
# ======================================================================
# STEP 1 — USE CASE INPUT
# Accept from W2 scorer, widget, or parameter
# ======================================================================

AGENT_NAME = "01_business_case_builder"
run_id = str(uuid.uuid4())

dbutils.widgets.text("use_case_name", "Predictive Job Failure Prevention", "Use Case Name")
dbutils.widgets.text("investment_usd", "75000", "Total Investment ($)")
dbutils.widgets.text("annual_benefit_usd", "180000", "Annual Benefit ($)")
dbutils.widgets.text("target_audience", "cto", "Audience (cfo/cto/coo/board/vp_data)")

use_case_name = dbutils.widgets.get("use_case_name")
investment = float(dbutils.widgets.get("investment_usd"))
annual_benefit = float(dbutils.widgets.get("annual_benefit_usd"))
audience = dbutils.widgets.get("target_audience")

print(f"\U0001f4bc Building business case: {use_case_name}")
print(f"   Investment: ${investment:,.0f} | Annual benefit: ${annual_benefit:,.0f}")
print(f"   Audience: {audience} ({STAKEHOLDER_PERSONAS.get(audience, {}).get('tone', 'balanced')})")

# COMMAND ----------

# DBTITLE 1,STEP 2: Financial Analysis
# ======================================================================
# STEP 2 — FINANCIAL ANALYSIS
# NPV, ROI, payback period, sensitivity analysis
# ======================================================================

# Base case
base_roi = calculate_roi(investment, annual_benefit)

# Sensitivity: pessimistic (60% of benefits), optimistic (140%)
pessimistic_roi = calculate_roi(investment * 1.15, annual_benefit * 0.6)  # +15% cost, -40% benefit
optimistic_roi = calculate_roi(investment * 0.9, annual_benefit * 1.4)    # -10% cost, +40% benefit

print(f"\n\U0001f4ca FINANCIAL ANALYSIS")
print("=" * 60)
print(f"{'Scenario':<15} {'NPV (3yr)':<15} {'ROI %':<10} {'Payback':<12}")
print("-" * 60)
print(f"{'Pessimistic':<15} ${pessimistic_roi['npv_3yr']:>10,.0f} {pessimistic_roi['roi_pct']:>8.0f}% {pessimistic_roi['payback_months']:>8.1f}mo")
print(f"{'Base Case':<15} ${base_roi['npv_3yr']:>10,.0f} {base_roi['roi_pct']:>8.0f}% {base_roi['payback_months']:>8.1f}mo")
print(f"{'Optimistic':<15} ${optimistic_roi['npv_3yr']:>10,.0f} {optimistic_roi['roi_pct']:>8.0f}% {optimistic_roi['payback_months']:>8.1f}mo")
print("=" * 60)
print(f"\n   Break-even even in pessimistic scenario: {'YES' if pessimistic_roi['npv_3yr'] > 0 else 'NO'}")

# COMMAND ----------

# DBTITLE 1,STEP 3: Generate Full Business Case via LLM
# ======================================================================
# STEP 3 — GENERATE FULL BUSINESS CASE
# ======================================================================

persona = STAKEHOLDER_PERSONAS.get(audience, STAKEHOLDER_PERSONAS['board'])

BC_PROMPT = f"""Generate a complete business case document for the following initiative.

Project: {use_case_name}
Industry: Medical devices (Hologic - diagnostics, breast health, surgical)
Platform: Databricks Lakehouse (Unity Catalog, Delta Lake, Serverless)
Audience: {audience.upper()} - priorities: {', '.join(persona['priorities'])}
Tone: {persona['tone']}

Financial Summary:
- Total Investment: ${investment:,.0f}
- Annual Benefit: ${annual_benefit:,.0f}
- 3-Year NPV: ${base_roi['npv_3yr']:,.0f}
- ROI: {base_roi['roi_pct']:.0f}%
- Payback Period: {base_roi['payback_months']:.1f} months
- Break-even in pessimistic scenario: {'Yes' if pessimistic_roi['npv_3yr'] > 0 else 'No'}

Context:
- Current state: 1,654 job failures/month in DEV workspace, $48.6K/yr Databricks spend
- Source systems: Oracle EBS (1,263 tables), Salesforce (768), ASCP (238), HCM (147)
- Team: Small data engineering team, ML experiments in progress

Generate ALL of these sections (use markdown headers):
1. Executive Summary (3-4 sentences)
2. Problem Statement (what pain exists today)
3. Proposed Solution (what we'll build, how it works)
4. Financial Analysis (table with NPV, ROI, payback + sensitivity)
5. Implementation Timeline (3 phases with milestones)
6. Resource Requirements (people, tools, compute)
7. Risk Assessment (top 5 risks + mitigation)
8. Success Metrics (4-6 measurable KPIs)
9. Stakeholder Impact (who benefits and how)
10. Recommendation (clear go/no-go with conditions)

Be specific to medical devices industry. Reference real Databricks capabilities."""

print("Generating business case...")
business_case_text = call_llm(BC_PROMPT, max_tokens=4000, temperature=0.2)

# Store structured results
BUSINESS_CASE = {
    "name": use_case_name,
    "audience": audience,
    "financials": {
        "base": base_roi,
        "pessimistic": pessimistic_roi,
        "optimistic": optimistic_roi,
    },
    "content": business_case_text,
    "run_id": run_id,
    "generated_at": datetime.now(timezone.utc).isoformat(),
}

print(f"\n\u2705 Business case generated ({len(business_case_text):,} chars)")
print(f"   Sections: {len(BUSINESS_CASE_SECTIONS)}")
print(f"   Audience: {audience.upper()}")

# COMMAND ----------

# DBTITLE 1,STEP 4: Display Business Case
# ======================================================================
# STEP 4 — DISPLAY
# ======================================================================

print(business_case_text)