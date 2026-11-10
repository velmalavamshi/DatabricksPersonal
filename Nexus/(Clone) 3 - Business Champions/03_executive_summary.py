# Databricks notebook source
# DBTITLE 1,Executive Summary Generator
# MAGIC %md
# MAGIC # Agent 03 — Executive Summary Generator (W3)
# MAGIC
# MAGIC **Purpose:** Generates a concise 1-page executive summary from a full business case. Supports multiple tones (CFO, Board, Technical).
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W3 (Business Champions) |
# MAGIC | Inputs | BUSINESS_CASE from 01_business_case_builder |
# MAGIC | Outputs | 1-page executive summary (markdown, HTML, or PDF-ready) |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_bc_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Generate Executive Summary
# ======================================================================
# STEP 1 — GENERATE 1-PAGE EXECUTIVE SUMMARY
# ======================================================================

AGENT_NAME = "03_executive_summary"

dbutils.widgets.dropdown("format", "one_pager", ["one_pager", "email", "slack"], "Output Format")
output_format = dbutils.widgets.get("format")

try:
    bc = BUSINESS_CASE
except NameError:
    bc = {"name": "Sample Project", "audience": "board", "content": "Sample content",
          "financials": {"base": {"npv_3yr": 250000, "roi_pct": 340, "payback_months": 5.0}}}

format_instructions = {
    "one_pager": "Write a 1-page executive summary (300-400 words). Use bullet points for key metrics. Include a clear recommendation at the end.",
    "email": "Write a concise email (150 words max) that a VP could forward to their C-suite. Subject line + body. No attachments reference.",
    "slack": "Write a Slack message (100 words max) with emoji headers. Must be scannable in 15 seconds.",
}

EXEC_PROMPT = f"""Convert this business case into a {output_format} format.

Project: {bc['name']}
Audience: {bc.get('audience', 'board').upper()}
NPV (3yr): ${bc['financials']['base']['npv_3yr']:,.0f}
ROI: {bc['financials']['base']['roi_pct']:.0f}%
Payback: {bc['financials']['base']['payback_months']:.1f} months

Full business case (excerpt):
{bc['content'][:2500]}

Instructions: {format_instructions[output_format]}

Context: Medical devices company (Hologic), Databricks platform, data engineering team."""

print(f"Generating {output_format} for {bc['name']}...")
exec_summary = call_llm(EXEC_PROMPT, max_tokens=1000, temperature=0.2)

print(f"\n\u2705 Executive summary generated ({output_format})")
print(f"   Length: {len(exec_summary)} chars / {len(exec_summary.split())} words")
print("\n" + "=" * 60)
print(exec_summary)