# Databricks notebook source
# DBTITLE 1,Feedback System
# MAGIC %md
# MAGIC # NEXUS Governance — Feedback System (W0)
# MAGIC
# MAGIC **Purpose:** Tracks quality scores for agent outputs. Aggregates success rates, latency, token efficiency. Identifies underperforming agents for retraining or prompt tuning.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Compute Agent Quality Scores
# ======================================================================
# STEP 1 — COMPUTE AGENT QUALITY SCORES
# Combines success rate, latency, and token efficiency into composite
# ======================================================================

AGENT_NAME = "05_feedback_system"
run_id = generate_run_id()

# Quality scoring weights
WEIGHTS = {
    "success_rate": 0.5,     # Most important: did it work?
    "latency_score": 0.2,   # Fast is better
    "efficiency_score": 0.15, # Low token usage is better
    "uptime_score": 0.15,   # Circuit breaker never opened
}

# Get agent performance data
perf_df = spark.sql(f"""
    SELECT
        r.agent_name, r.workspace, r.status, r.total_runs,
        COALESCE(r.success_rate, 0) as success_rate,
        COALESCE(r.avg_latency_ms, 0) as avg_latency_ms,
        cb.state as circuit_state,
        cb.failure_count
    FROM {NEXUS_REGISTRY} r
    LEFT JOIN {NEXUS_CIRCUIT} cb ON r.agent_name = cb.agent_name
    WHERE r.status IN ('ACTIVE', 'DEVELOPMENT')
      AND r.total_runs > 0
    ORDER BY r.success_rate ASC
""")

perf_data = perf_df.collect()
quality_scores = []

for agent in perf_data:
    # Success rate score (0-1)
    sr = agent['success_rate'] or 0
    
    # Latency score (lower is better, normalize to 0-1)
    latency_ms = agent['avg_latency_ms'] or 0
    latency_score = max(0, 1.0 - (latency_ms / 300000))  # 5 min = 0 score
    
    # Circuit breaker uptime
    uptime_score = 1.0 if agent['circuit_state'] == 'CLOSED' else 0.3
    
    # Composite quality score
    composite = (
        sr * WEIGHTS['success_rate'] +
        latency_score * WEIGHTS['latency_score'] +
        0.8 * WEIGHTS['efficiency_score'] +  # Default until trace log has token data
        uptime_score * WEIGHTS['uptime_score']
    )
    
    quality_scores.append({
        "agent_name": agent['agent_name'],
        "workspace": agent['workspace'],
        "composite_score": round(composite, 3),
        "success_rate": sr,
        "runs": agent['total_runs'],
        "grade": 'A' if composite >= 0.9 else 'B' if composite >= 0.75 else 'C' if composite >= 0.6 else 'D' if composite >= 0.4 else 'F',
    })

# Sort by score
quality_scores.sort(key=lambda x: x['composite_score'])

print(f"\U0001f4ca AGENT QUALITY SCORECARD")
print("=" * 65)
print(f"{'Agent':<35} {'Grade':<6} {'Score':<8} {'Success':<10} {'Runs'}")
print("-" * 65)

# Show bottom performers first (need attention)
for qs in quality_scores[:10]:
    print(f"  {qs['agent_name'][:33]:<35} {qs['grade']:<6} {qs['composite_score']:<8.3f} {qs['success_rate']:<10.1%} {qs['runs']}")

print("=" * 65)
if quality_scores:
    avg_score = sum(q['composite_score'] for q in quality_scores) / len(quality_scores)
    print(f"  Platform average: {avg_score:.3f} | Agents with runs: {len(quality_scores)}")
    print(f"  Grade distribution: A={sum(1 for q in quality_scores if q['grade']=='A')} B={sum(1 for q in quality_scores if q['grade']=='B')} C={sum(1 for q in quality_scores if q['grade']=='C')} D={sum(1 for q in quality_scores if q['grade']=='D')} F={sum(1 for q in quality_scores if q['grade']=='F')}")