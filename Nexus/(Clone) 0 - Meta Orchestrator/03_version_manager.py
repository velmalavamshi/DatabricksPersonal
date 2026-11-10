# Databricks notebook source
# DBTITLE 1,Version Manager
# MAGIC %md
# MAGIC # NEXUS Governance — Version Manager (W0)
# MAGIC
# MAGIC **Purpose:** Tracks agent versions, deployment history, and enables rollback. Detects version drift (agents running outdated code) and enforces promotion gates.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Schedule | Daily 06:00 UTC |
# MAGIC | Inputs | nexus_agent_registry, notebook metadata API |
# MAGIC | Outputs | Version drift alerts, deployment log, rollback actions |

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Scan Agent Versions and Promotion Gate
# ======================================================================
# STEP 1 — SCAN VERSIONS & PROMOTION GATE
# ======================================================================

AGENT_NAME = "03_version_manager"
run_id = generate_run_id()
start_time = datetime.now(timezone.utc)

PROMOTION_CRITERIA = {"min_successful_runs": 3, "min_success_rate": 0.9}

# Get all agents with circuit breaker state
agents_df = spark.sql(f"""
    SELECT r.agent_name, r.workspace, r.version, r.status, r.total_runs,
           r.success_rate, r.updated_at, r.notebook_path,
           cb.state as circuit_state, cb.failure_count
    FROM {NEXUS_REGISTRY} r
    LEFT JOIN {NEXUS_CIRCUIT} cb ON r.agent_name = cb.agent_name
    ORDER BY r.workspace, r.agent_name
""")
agents = agents_df.collect()

# Detect stale agents (ACTIVE but no update in 30+ days)
stale = [a for a in agents if a['status'] == 'ACTIVE' and a['updated_at']
         and (start_time - a['updated_at'].replace(tzinfo=timezone.utc)).days > 30]

# Check promotion readiness for DEVELOPMENT agents
dev_agents = [a for a in agents if a['status'] == 'DEVELOPMENT']
promotion_ready = []
for a in dev_agents:
    runs = a['total_runs'] or 0
    rate = a['success_rate'] or 0
    if runs >= PROMOTION_CRITERIA['min_successful_runs'] and rate >= PROMOTION_CRITERIA['min_success_rate'] and a['circuit_state'] != 'OPEN':
        promotion_ready.append(a['agent_name'])

print(f"\U0001f4cb VERSION MANAGER REPORT")
print("=" * 60)
print(f"  Total agents: {len(agents)}")
print(f"  Active: {sum(1 for a in agents if a['status'] == 'ACTIVE')}")
print(f"  Development: {len(dev_agents)}")
print(f"  Planned: {sum(1 for a in agents if a['status'] == 'PLANNED')}")
print(f"  Stale (>30d): {len(stale)}")
print(f"  Promotion ready: {len(promotion_ready)}")
print(f"  Circuit breakers OPEN: {sum(1 for a in agents if a['circuit_state'] == 'OPEN')}")
print("=" * 60)

if promotion_ready:
    print(f"\n\u2705 Ready to promote to ACTIVE:")
    for name in promotion_ready[:10]:
        print(f"   {name}")