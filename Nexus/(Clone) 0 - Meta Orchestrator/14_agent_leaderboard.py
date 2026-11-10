# Databricks notebook source
# DBTITLE 1,Agent Leaderboard
# MAGIC %md
# MAGIC # NEXUS Phase 11 — Agent Leaderboard (W0)
# MAGIC
# MAGIC **Purpose:** Performance rankings across all 80+ agents. Identifies top performers, degrading agents, and improvement trends. Powers weekly intelligence digest.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Build Leaderboard
# ======================================================================
# STEP 1 — BUILD AGENT LEADERBOARD
# Composite ranking: success rate (50%) + speed (25%) + reliability (25%)
# ======================================================================

AGENT_NAME = "14_agent_leaderboard"
run_id = generate_run_id()

leaderboard_df = spark.sql(f"""
    SELECT
        r.agent_name,
        r.workspace,
        r.layer,
        r.status,
        COALESCE(r.total_runs, 0) as total_runs,
        COALESCE(r.success_rate, 0) as success_rate,
        COALESCE(r.avg_latency_ms, 0) as avg_latency_ms,
        cb.state as circuit_state,
        cb.failure_count,
        DATEDIFF(CURRENT_TIMESTAMP(), r.updated_at) as days_since_update
    FROM {NEXUS_REGISTRY} r
    LEFT JOIN {NEXUS_CIRCUIT} cb ON r.agent_name = cb.agent_name
    WHERE r.total_runs > 0
    ORDER BY r.success_rate DESC, r.total_runs DESC
""")

leaderboard = leaderboard_df.collect()

# Compute composite score
ranked_agents = []
for agent in leaderboard:
    # Success score (0-50 pts)
    success_pts = float(agent['success_rate'] or 0) * 50
    
    # Speed score (0-25 pts) - lower latency = higher score
    latency_ms = float(agent['avg_latency_ms'] or 0)
    speed_pts = max(0, 25 - (latency_ms / 12000))  # 5min = 0 pts
    
    # Reliability score (0-25 pts) - circuit breaker + freshness
    reliability_pts = 25 if agent['circuit_state'] == 'CLOSED' else 5
    if agent['days_since_update'] and agent['days_since_update'] > 30:
        reliability_pts -= 10  # Penalty for staleness
    
    composite = success_pts + speed_pts + reliability_pts
    
    ranked_agents.append({
        "agent": agent['agent_name'],
        "workspace": agent['workspace'],
        "layer": agent['layer'],
        "runs": agent['total_runs'],
        "success_rate": float(agent['success_rate'] or 0),
        "latency_ms": latency_ms,
        "composite": round(composite, 1),
        "circuit": agent['circuit_state'],
    })

# Sort by composite score
ranked_agents.sort(key=lambda x: x['composite'], reverse=True)

print(f"\U0001f3c6 NEXUS AGENT LEADERBOARD")
print("=" * 80)
print(f"{'#':<4} {'Agent':<35} {'WS':<4} {'Runs':<6} {'Success':<9} {'Score':<7} {'Status'}")
print("-" * 80)

for i, agent in enumerate(ranked_agents[:20], 1):
    medal = '\U0001f947' if i == 1 else '\U0001f948' if i == 2 else '\U0001f949' if i == 3 else '  '
    circuit_icon = '\u2705' if agent['circuit'] == 'CLOSED' else '\U0001f534'
    print(f"{medal}{i:<3} {agent['agent'][:33]:<35} {agent['workspace']:<4} {agent['runs']:<6} {agent['success_rate']:.0%}{'':>4} {agent['composite']:<7.1f} {circuit_icon}")

print("=" * 80)
print(f"  Agents with runs: {len(ranked_agents)} | Avg composite: {sum(a['composite'] for a in ranked_agents)/max(len(ranked_agents),1):.1f}/100")

# COMMAND ----------

# DBTITLE 1,STEP 2: Trend Analysis and Weekly Digest
# ======================================================================
# STEP 2 — WORKSPACE RANKINGS & BOTTOM PERFORMERS
# ======================================================================

# Workspace averages
ws_scores = {}
for agent in ranked_agents:
    ws = agent['workspace']
    if ws not in ws_scores:
        ws_scores[ws] = []
    ws_scores[ws].append(agent['composite'])

print(f"\n\U0001f4ca WORKSPACE RANKINGS")
print("-" * 45)
ws_ranked = sorted(ws_scores.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)
for rank, (ws, scores) in enumerate(ws_ranked, 1):
    avg = sum(scores) / len(scores)
    medal = '\U0001f947' if rank == 1 else '\U0001f948' if rank == 2 else '\U0001f949' if rank == 3 else '  '
    print(f"  {medal} {ws}: avg={avg:.1f}/100 ({len(scores)} agents with runs)")

# Bottom performers (need attention)
print(f"\n\u26a0\ufe0f BOTTOM PERFORMERS (Improvement Needed)")
print("-" * 60)
bottom = ranked_agents[-5:] if len(ranked_agents) >= 5 else ranked_agents
for agent in reversed(bottom):
    issues = []
    if agent['success_rate'] < 0.8:
        issues.append(f"low success ({agent['success_rate']:.0%})")
    if agent['circuit'] == 'OPEN':
        issues.append("breaker OPEN")
    if agent['latency_ms'] > 60000:
        issues.append(f"slow ({agent['latency_ms']/1000:.0f}s)")
    issue_str = "; ".join(issues) if issues else "borderline"
    print(f"  {agent['agent'][:33]:<35} Score: {agent['composite']:.1f} | {issue_str}")

print(f"\n\u2705 Leaderboard complete | {len(ranked_agents)} agents ranked")