# Databricks notebook source
# DBTITLE 1,W3 Business Champions — Configuration
# ======================================================================
# 00_bc_config
# W3 Business Champions — Shared Configuration
# Business case templates, ROI framework, PPTX settings, executive formats
# ======================================================================

import json
import uuid
import requests
from datetime import datetime, timezone

# ── Environment ────────────────────────────────────────────────────────
USER_EMAIL = spark.sql("SELECT current_user()").collect()[0][0]
NEXUS_SCHEMA = "mde_dev.test_schema"
NEXUS_EVENTS = f"{NEXUS_SCHEMA}.nexus_agent_events"
OUTPUT_PATH = f"/Workspace/Users/{USER_EMAIL}/5 - Personal Projects/5 - AI Multi Agents/3 - Business Champions/outputs"

LLM_ENDPOINT = "databricks-claude-sonnet-4-6"
WORKSPACE_URL = spark.conf.get("spark.databricks.workspaceUrl")
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

def call_llm(prompt, max_tokens=3000, temperature=0.2):
    """Call Foundation Model API."""
    url = f"https://{WORKSPACE_URL}/serving-endpoints/{LLM_ENDPOINT}/invocations"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ── Brand Colors (Hologic) ───────────────────────────────────────────
BRAND = {
    "dark_blue": "#1B2A4A",
    "teal": "#16A085",
    "blue": "#3498DB",
    "red": "#E74C3C",
    "green": "#27AE60",
    "orange": "#F39C12",
    "purple": "#8E44AD",
    "light_gray": "#F8F9FA",
    "font": "Calibri",
}

# ── ROI Calculation Framework ───────────────────────────────────────
ROI_CONFIG = {
    "discount_rate": 0.10,         # 10% annual for NPV
    "analysis_years": 3,           # 3-year projection
    "tax_rate": 0.21,              # Corporate tax rate
    "loaded_fte_cost": 180000,     # Fully loaded annual cost (data engineer)
    "analyst_fte_cost": 120000,    # Business analyst loaded cost
    "databricks_dbu_rate": 0.45,   # Serverless jobs (primary compute)
    "risk_contingency": 0.15,      # 15% buffer on costs
}

def calculate_roi(investment, annual_benefit, years=None):
    """Calculate ROI, NPV, and payback period."""
    years = years or ROI_CONFIG['analysis_years']
    r = ROI_CONFIG['discount_rate']
    
    # NPV of benefits
    npv_benefits = sum(annual_benefit / (1 + r)**y for y in range(1, years + 1))
    npv = npv_benefits - investment
    roi_pct = ((npv_benefits - investment) / investment) * 100 if investment > 0 else 0
    payback_months = (investment / annual_benefit * 12) if annual_benefit > 0 else float('inf')
    
    return {
        "investment": round(investment, 0),
        "annual_benefit": round(annual_benefit, 0),
        "npv_3yr": round(npv, 0),
        "roi_pct": round(roi_pct, 1),
        "payback_months": round(payback_months, 1),
        "total_benefit_3yr": round(annual_benefit * years, 0),
    }

# ── Business Case Template Sections ─────────────────────────────────
BUSINESS_CASE_SECTIONS = [
    "Executive Summary",
    "Problem Statement",
    "Proposed Solution",
    "Financial Analysis (NPV, ROI, Payback)",
    "Implementation Timeline",
    "Resource Requirements",
    "Risk Assessment & Mitigation",
    "Success Metrics & KPIs",
    "Stakeholder Impact",
    "Recommendation",
]

# ── PPTX Slide Templates ────────────────────────────────────────────
PPTX_SLIDES = [
    {"type": "title", "title": "{project_name}", "subtitle": "Business Case | {date}"},
    {"type": "executive_summary", "title": "Executive Summary"},
    {"type": "problem", "title": "The Challenge"},
    {"type": "solution", "title": "Proposed Solution"},
    {"type": "financials", "title": "Financial Impact"},
    {"type": "timeline", "title": "Implementation Roadmap"},
    {"type": "risks", "title": "Risk Assessment"},
    {"type": "kpis", "title": "Success Metrics"},
    {"type": "recommendation", "title": "Recommendation & Next Steps"},
    {"type": "appendix", "title": "Appendix: Detailed Analysis"},
]

# ── Stakeholder Personas ────────────────────────────────────────────
STAKEHOLDER_PERSONAS = {
    "cfo": {"priorities": ["ROI", "cost reduction", "payback period", "risk"], "tone": "numbers-driven, conservative"},
    "cto": {"priorities": ["scalability", "architecture", "security", "innovation"], "tone": "technical depth, future-proofing"},
    "coo": {"priorities": ["efficiency", "time savings", "process improvement", "headcount"], "tone": "operational impact, SLAs"},
    "board": {"priorities": ["strategic value", "competitive advantage", "market position", "risk"], "tone": "high-level, strategic, 2-3 sentences per point"},
    "vp_data": {"priorities": ["data quality", "governance", "self-service", "talent"], "tone": "balanced technical + business"},
}

# ── Champion Coaching Templates ─────────────────────────────────────
COMMON_OBJECTIONS = [
    {"objection": "We don't have budget for this", "category": "financial"},
    {"objection": "Our team is already stretched thin", "category": "resource"},
    {"objection": "We tried AI before and it didn't work", "category": "skepticism"},
    {"objection": "The data isn't ready", "category": "technical"},
    {"objection": "Security/compliance concerns", "category": "risk"},
    {"objection": "What's the competitive urgency?", "category": "strategic"},
    {"objection": "Can we just hire more people instead?", "category": "alternative"},
]

print("\u2705 W3 Business Champions config loaded")
print(f"   Business case sections: {len(BUSINESS_CASE_SECTIONS)}")
print(f"   PPTX slide templates: {len(PPTX_SLIDES)}")
print(f"   Stakeholder personas: {len(STAKEHOLDER_PERSONAS)}")
print(f"   Objection handlers: {len(COMMON_OBJECTIONS)}")

# COMMAND ----------

# DBTITLE 1,Load shared token optimizer
# Shared memory + token budget utilities (single source of truth for all folders)
%run ../shared_token_optimizer