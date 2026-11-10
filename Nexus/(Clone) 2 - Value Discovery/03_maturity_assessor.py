# Databricks notebook source
# DBTITLE 1,Maturity Assessor
# MAGIC %md
# MAGIC # Agent 03 — Maturity Assessor (W2)
# MAGIC
# MAGIC **Purpose:** Scores the target workspace across 6 dimensions of data/AI maturity (1-5 scale) using workspace scan metrics and LLM analysis. Produces a radar chart profile.
# MAGIC
# MAGIC | Dimension | Indicators |
# MAGIC |---|---|
# MAGIC | Data Governance | UC adoption, PII tagging, access policies |
# MAGIC | Pipeline Maturity | CI/CD, DQ expectations, SLA monitoring |
# MAGIC | Cost Efficiency | Idle compute, right-sizing, serverless adoption |
# MAGIC | Analytics & BI | Dashboards, Genie, SQL warehouse utilization |
# MAGIC | ML/AI Readiness | Feature store, MLflow, model serving, GenAI |
# MAGIC | Operational Excellence | Job success rate, MTTR, alerting, docs |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_vd_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Score Each Dimension
# ======================================================================
# STEP 1 — SCORE EACH MATURITY DIMENSION
# Uses scan data + LLM to produce 1-5 scores per dimension
# ======================================================================

AGENT_NAME = "03_maturity_assessor"
run_id = str(uuid.uuid4())

# Get scan results
try:
    scan_data = WORKSPACE_SCAN_RESULTS
except NameError:
    scan_data = {"tables": {"total": 3200, "schemas": 30, "managed": 2800, "views": 400},
                 "jobs": {"success_rate_pct": 89.0, "total_runs_30d": 15000, "failed_30d": 1654},
                 "cost": {"annual_run_rate_usd": 48600},
                 "ml_ai": {"mlflow_experiments": 12, "serving_endpoints": 3, "vector_search_dbus_30d": 8000, "genai_dbus_30d": 500}}

MATURITY_PROMPT = f"""You are a Databricks maturity assessor. Score this workspace on 6 dimensions (1-5 scale).

Maturity Scale:
1 = Ad-hoc (no governance, manual, siloed)
2 = Defined (some standards, basic scheduling, catalog exists)
3 = Managed (Unity Catalog enforced, CI/CD, DQ rules, cost monitoring)
4 = Optimized (predictive optimization, auto-scaling, ML in production, full lineage)
5 = Innovating (AI agents, self-healing pipelines, real-time, GenAI in production)

Workspace Metrics:
- Tables: {scan_data['tables']['total']:,} ({scan_data['tables']['schemas']} schemas, {scan_data['tables'].get('managed', 0):,} managed)
- Views: {scan_data['tables'].get('views', 0):,}
- Job success rate (30d): {scan_data.get('jobs', {}).get('success_rate_pct', 'N/A')}%
- Job failures (30d): {scan_data.get('jobs', {}).get('failed_30d', 'N/A')}
- Annual cost: ${scan_data.get('cost', {}).get('annual_run_rate_usd', 0):,.0f}
- MLflow experiments: {scan_data.get('ml_ai', {}).get('mlflow_experiments', 0)}
- Serving endpoints: {scan_data.get('ml_ai', {}).get('serving_endpoints', 0)}
- Vector Search DBUs (30d): {scan_data.get('ml_ai', {}).get('vector_search_dbus_30d', 0):,.0f}
- GenAI DBUs (30d): {scan_data.get('ml_ai', {}).get('genai_dbus_30d', 0):,.0f}

Additional context: Medical devices company, 1,654 job failures/month, Oracle EBS + Salesforce as primary sources, some ML experiments but limited production ML.

Score each dimension. Return ONLY valid JSON:
{{
  "data_governance": {{"score": N, "rationale": "one sentence"}},
  "pipeline_maturity": {{"score": N, "rationale": "one sentence"}},
  "cost_efficiency": {{"score": N, "rationale": "one sentence"}},
  "analytics_adoption": {{"score": N, "rationale": "one sentence"}},
  "ml_ai_readiness": {{"score": N, "rationale": "one sentence"}},
  "operational_excellence": {{"score": N, "rationale": "one sentence"}}
}}"""

print("Assessing maturity across 6 dimensions...")
response = call_llm(MATURITY_PROMPT, max_tokens=800, temperature=0.1)

clean = response.strip()
if clean.startswith("```"):
    clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]

maturity_scores = json.loads(clean)

# Calculate overall maturity
weighted_sum = 0
weight_total = 0
for dim in ASSESSMENT_DIMENSIONS:
    dim_id = dim['id']
    score = maturity_scores.get(dim_id, {}).get('score', 2)
    weighted_sum += score * dim['weight']
    weight_total += dim['weight']

overall_maturity = round(weighted_sum / weight_total, 1)
overall_level = min(5, max(1, round(overall_maturity)))

print(f"\n\U0001f4ca MATURITY ASSESSMENT")
print("=" * 60)
for dim in ASSESSMENT_DIMENSIONS:
    dim_id = dim['id']
    s = maturity_scores.get(dim_id, {})
    score = s.get('score', 2)
    bar = '\u2588' * score + '\u2591' * (5 - score)
    print(f"  {dim['name']:<25} {bar} {score}/5  {s.get('rationale', '')}")
print("=" * 60)
print(f"  OVERALL: {overall_maturity}/5 — Level {overall_level} ({MATURITY_LEVELS[overall_level]['name']})")
print(f"  {MATURITY_LEVELS[overall_level]['description']}")

MATURITY_RESULTS = {
    "scores": maturity_scores,
    "overall_score": overall_maturity,
    "overall_level": overall_level,
    "overall_name": MATURITY_LEVELS[overall_level]['name'],
}