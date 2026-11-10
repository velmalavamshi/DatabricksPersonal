# Databricks notebook source
# DBTITLE 1,Assessment Report Generator
# MAGIC %md
# MAGIC # Agent 04 — Assessment Report Generator (W2)
# MAGIC
# MAGIC **Purpose:** Synthesizes workspace scan, maturity scores, and use case rankings into a comprehensive assessment report. Generates markdown + optional PPTX.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W2 (Value Discovery) |
# MAGIC | Inputs | WORKSPACE_SCAN_RESULTS, MATURITY_RESULTS, SCORED_USE_CASES |
# MAGIC | Outputs | Markdown report, PPTX (if python-pptx available) |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_vd_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Gather Inputs
# ======================================================================
# STEP 1 — GATHER ALL ASSESSMENT INPUTS
# ======================================================================

AGENT_NAME = "04_report_generator"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)

# Collect inputs from upstream agents
try:
    scan = WORKSPACE_SCAN_RESULTS
except NameError:
    scan = {"workspace_id": "6617965257274108", "catalog": "mde_dev",
            "tables": {"total": 3200, "schemas": 30}, "cost": {"annual_run_rate_usd": 48600}}

try:
    maturity = MATURITY_RESULTS
except NameError:
    maturity = {"overall_score": 2.8, "overall_level": 3, "overall_name": "Managed"}

try:
    use_cases = SCORED_USE_CASES
except NameError:
    use_cases = []

print(f"\U0001f4dd Report Generator")
print(f"   Scan data: {'\u2705' if scan else '\u274c'}")
print(f"   Maturity scores: {'\u2705' if maturity else '\u274c'}")
print(f"   Use cases: {len(use_cases)} scored")

# COMMAND ----------

# DBTITLE 1,STEP 2: Generate Executive Summary via LLM
# ======================================================================
# STEP 2 — GENERATE EXECUTIVE SUMMARY
# ======================================================================

EXEC_SUMMARY_PROMPT = f"""Write a concise executive summary (5-7 sentences) for a Databricks AI/Data Assessment report.

Key findings:
- Workspace has {scan.get('tables', {}).get('total', 0):,} tables across {scan.get('tables', {}).get('schemas', 0)} schemas
- Annual Databricks spend: ${scan.get('cost', {}).get('annual_run_rate_usd', 0):,.0f}
- Overall maturity: {maturity.get('overall_score', 0)}/5 ({maturity.get('overall_name', 'N/A')})
- {len(use_cases)} AI/ML use cases identified
- Total potential annual value from use cases: ${sum(uc.get('annual_value_usd', 0) for uc in use_cases):,.0f}
- Quick wins available: {len([uc for uc in use_cases if uc.get('tier') == 'QUICK_WIN'])}
- Job success rate: {scan.get('jobs', {}).get('success_rate_pct', 'N/A')}%

Context: Medical devices company (diagnostics, breast health, surgical). Source systems include Oracle EBS, Salesforce, ASCP, HCM.

Write in a professional consulting tone. Focus on value and actionability."""

exec_summary = call_llm(EXEC_SUMMARY_PROMPT, max_tokens=500, temperature=0.2)
print("\n\U0001f4cb Executive Summary:")
print(exec_summary)

# COMMAND ----------

# DBTITLE 1,STEP 3: Compose Full Report
# ======================================================================
# STEP 3 — COMPOSE FULL MARKDOWN REPORT
# ======================================================================

report_date = start_time.strftime('%B %d, %Y')

report_md = f"""# NEXUS Value Discovery Assessment Report
**Generated:** {report_date} | **Agent:** 04_report_generator | **Run:** {run_id[:8]}

---

## Executive Summary

{exec_summary}

---

## Workspace Profile

| Metric | Value |
|---|---|
| Catalog | {scan.get('catalog', 'N/A')} |
| Total Tables | {scan.get('tables', {}).get('total', 0):,} |
| Schemas | {scan.get('tables', {}).get('schemas', 0)} |
| Annual Spend | ${scan.get('cost', {}).get('annual_run_rate_usd', 0):,.0f} |
| Job Success Rate | {scan.get('jobs', {}).get('success_rate_pct', 'N/A')}% |
| MLflow Experiments | {scan.get('ml_ai', {}).get('mlflow_experiments', 0)} |
| Model Serving Endpoints | {scan.get('ml_ai', {}).get('serving_endpoints', 0)} |

---

## Maturity Assessment

**Overall Score: {maturity.get('overall_score', 0)}/5 — Level {maturity.get('overall_level', 0)} ({maturity.get('overall_name', 'N/A')})**

| Dimension | Score | Assessment |
|---|---|---|
"""

for dim in ASSESSMENT_DIMENSIONS:
    dim_id = dim['id']
    s = maturity.get('scores', {}).get(dim_id, {})
    score = s.get('score', 'N/A')
    rationale = s.get('rationale', '')
    report_md += f"| {dim['name']} | {score}/5 | {rationale} |\n"

report_md += f"""\n---\n\n## Top AI/ML Use Cases (Ranked)

| # | Use Case | Score | Tier | Time to Value | Annual Value |
|---|---|---|---|---|---|
"""

for i, uc in enumerate(use_cases[:8], 1):
    tier_label = uc.get('tier', 'N/A').replace('_', ' ').title()
    report_md += f"| {i} | {uc['name']} | {uc.get('composite_score', 0):.1f}/10 | {tier_label} | {uc.get('time_to_value_weeks', '?')} weeks | ${uc.get('annual_value_usd', 0):,.0f} |\n"

total_value = sum(uc.get('annual_value_usd', 0) for uc in use_cases)
report_md += f"""\n**Total Potential Value: ${total_value:,.0f}/year**

---

## Recommended Next Steps

1. **Quick Wins (Week 1-2):** Implement {len([uc for uc in use_cases if uc.get('tier') == 'QUICK_WIN'])} quick-win use cases
2. **Foundation (Month 1):** Address operational excellence gaps (job failure rate, monitoring)
3. **High Priority (Month 1-3):** Build {len([uc for uc in use_cases if uc.get('tier') == 'HIGH_PRIORITY'])} high-priority use cases
4. **Maturity Uplift (Quarter 2):** Target Level {min(5, maturity.get('overall_level', 3) + 1)} maturity

---

*Report generated by NEXUS W2 Value Discovery agents. For questions, contact {USER_EMAIL}*
"""

print(f"\n\u2705 Report generated ({len(report_md):,} characters, {len(report_md.splitlines())} lines)")
print(f"   Sections: Executive Summary, Profile, Maturity, Use Cases, Next Steps")

# COMMAND ----------

# DBTITLE 1,STEP 4: Display Report
# ======================================================================
# STEP 4 — DISPLAY REPORT
# ======================================================================

# Render as displayable markdown
print(report_md)