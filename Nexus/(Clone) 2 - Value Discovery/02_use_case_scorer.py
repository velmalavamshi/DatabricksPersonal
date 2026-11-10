# Databricks notebook source
# DBTITLE 1,Use Case Scorer
# MAGIC %md
# MAGIC # Agent 02 — AI Use Case Scorer (W2)
# MAGIC
# MAGIC **Purpose:** Takes workspace scan results + business context and uses LLM to identify, score, and rank AI/ML use cases by feasibility and impact.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W2 (Value Discovery) |
# MAGIC | Inputs | Workspace scan results, business context (optional) |
# MAGIC | Outputs | Scored & ranked use case list with ROI estimates |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_vd_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Generate Use Cases from Scan
# ======================================================================
# STEP 1 — GENERATE USE CASES FROM WORKSPACE SCAN
# Uses LLM to identify AI/ML opportunities based on data landscape
# ======================================================================

AGENT_NAME = "02_use_case_scorer"
run_id = str(uuid.uuid4())

# Accept scan results from workspace scanner or use widget
dbutils.widgets.text("scan_json", "", "Scan Results JSON (optional)")
scan_input = dbutils.widgets.get("scan_json")

if scan_input:
    scan_data = json.loads(scan_input)
else:
    # Try to use variable from chained execution
    try:
        scan_data = WORKSPACE_SCAN_RESULTS
    except NameError:
        # Default: run a quick scan of current workspace
        scan_data = {
            "catalog": "mde_dev",
            "tables": {"total": 3200, "bronze_tables": 2100, "silver_tables": 600, "gold_tables": 120, "schemas": 30},
            "jobs": {"total_runs_30d": 15000, "success_rate_pct": 89.0, "failed_30d": 1654},
            "cost": {"annual_run_rate_usd": 48600},
            "ml_ai": {"mlflow_experiments": 12, "serving_endpoints": 3, "vector_search_dbus_30d": 8000},
        }

USE_CASE_PROMPT = f"""Based on this workspace data landscape, identify the top 8 AI/ML use cases.

Workspace Profile:
- Total tables: {scan_data['tables']['total']:,}
- Bronze (source): {scan_data['tables'].get('bronze_tables', 0):,}
- Silver: {scan_data['tables'].get('silver_tables', 0):,}
- Gold: {scan_data['tables'].get('gold_tables', 0):,}
- Job runs (30d): {scan_data.get('jobs', {}).get('total_runs_30d', 'N/A')}
- Job failure rate: {100 - scan_data.get('jobs', {}).get('success_rate_pct', 90):.1f}%
- Annual spend: ${scan_data.get('cost', {}).get('annual_run_rate_usd', 0):,.0f}
- MLflow experiments: {scan_data.get('ml_ai', {}).get('mlflow_experiments', 0)}
- Model serving endpoints: {scan_data.get('ml_ai', {}).get('serving_endpoints', 0)}

Source systems (from Bronze schemas): Oracle EBS (1,263 tables - financials, procurement, inventory), Salesforce (768 - CRM), ASCP (238 - supply chain), Oracle HCM (147 - workforce), Agile PLM (82 - product lifecycle), HCP (81 - healthcare providers), PBCS (42 - financial planning).

Industry: Medical devices (Hologic - diagnostics, breast health, surgical)

For each use case, provide JSON with:
- name: concise name
- description: 2 sentences
- category: one of [PREDICTIVE_ANALYTICS, GENAI, AUTOMATION, OPTIMIZATION, NLP, COMPUTER_VISION]
- data_sources: which Bronze schemas needed
- feasibility_score: 1-10 (10=easiest to implement)
- impact_score: 1-10 (10=highest business value)
- time_to_value_weeks: estimated weeks to MVP
- annual_value_usd: estimated annual value (conservative)
- quick_win: true/false (achievable in < 2 weeks)

Return ONLY a JSON array of 8 use cases. No other text."""

print("Generating AI use cases from workspace profile...")
response = call_llm(USE_CASE_PROMPT, max_tokens=3000, temperature=0.3)

# Parse response
clean = response.strip()
if clean.startswith("```"):
    clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]

use_cases = json.loads(clean)
print(f"\u2705 Generated {len(use_cases)} use cases")
for i, uc in enumerate(use_cases, 1):
    composite = (uc['feasibility_score'] * 0.4 + uc['impact_score'] * 0.6)
    print(f"   {i}. [{composite:.1f}] {uc['name']} ({'QUICK WIN' if uc.get('quick_win') else f"{uc['time_to_value_weeks']}w"})")

# COMMAND ----------

# DBTITLE 1,STEP 2: Rank and Prioritize
# ======================================================================
# STEP 2 — RANK & PRIORITIZE
# Composite score = 40% feasibility + 60% impact
# ======================================================================

for uc in use_cases:
    uc['composite_score'] = round(uc['feasibility_score'] * 0.4 + uc['impact_score'] * 0.6, 2)

# Sort by composite score
use_cases_ranked = sorted(use_cases, key=lambda x: x['composite_score'], reverse=True)

# Classify into tiers
for uc in use_cases_ranked:
    if uc.get('quick_win'):
        uc['tier'] = 'QUICK_WIN'
    elif uc['composite_score'] >= 7.5:
        uc['tier'] = 'HIGH_PRIORITY'
    elif uc['composite_score'] >= 5.5:
        uc['tier'] = 'MEDIUM_PRIORITY'
    else:
        uc['tier'] = 'BACKLOG'

# Summary
total_value = sum(uc.get('annual_value_usd', 0) for uc in use_cases_ranked)
quick_wins = [uc for uc in use_cases_ranked if uc['tier'] == 'QUICK_WIN']
high_priority = [uc for uc in use_cases_ranked if uc['tier'] == 'HIGH_PRIORITY']

print(f"\n\U0001f3c6 USE CASE RANKING")
print("=" * 60)
print(f"{'#':<3} {'Score':<7} {'Tier':<14} {'Name':<35} {'Value/yr'}")
print("-" * 60)
for i, uc in enumerate(use_cases_ranked, 1):
    tier_icon = {'QUICK_WIN': '\u26a1', 'HIGH_PRIORITY': '\U0001f525', 'MEDIUM_PRIORITY': '\U0001f7e1', 'BACKLOG': '\u26aa'}[uc['tier']]
    print(f"{i:<3} {uc['composite_score']:<7.1f} {tier_icon} {uc['tier']:<12} {uc['name'][:34]:<35} ${uc.get('annual_value_usd', 0):>10,.0f}")
print("-" * 60)
print(f"{'TOTAL POTENTIAL VALUE:':<55} ${total_value:>10,.0f}/year")
print(f"\n   Quick wins: {len(quick_wins)} | High priority: {len(high_priority)}")

# Store for downstream
SCORED_USE_CASES = use_cases_ranked