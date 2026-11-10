# Databricks notebook source
# DBTITLE 1,Governance Dashboard
# MAGIC %md
# MAGIC # NEXUS Governance Dashboard (W0)
# MAGIC
# MAGIC **Single-pane view** of the entire platform: agent health, version drift, security findings, quality scores, circuit breaker states.
# MAGIC
# MAGIC Run all cells for a full governance report.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,SECTION 1: Platform Overview
# ======================================================================
# SECTION 1 — PLATFORM OVERVIEW
# ======================================================================

AGENT_NAME = "07_governance_dashboard"

overview = spark.sql(f"""
    SELECT
        workspace,
        COUNT(*) as total_agents,
        COUNT_IF(status = 'ACTIVE') as active,
        COUNT_IF(status = 'DEVELOPMENT') as development,
        COUNT_IF(status = 'PLANNED') as planned,
        ROUND(AVG(success_rate) * 100, 1) as avg_success_pct,
        SUM(total_runs) as total_runs
    FROM {NEXUS_REGISTRY}
    GROUP BY workspace
    ORDER BY workspace
""")

print("\U0001f3e2 NEXUS PLATFORM OVERVIEW")
print("=" * 70)
display(overview)

# COMMAND ----------

# DBTITLE 1,SECTION 2: Circuit Breaker Status
# ======================================================================
# SECTION 2 — CIRCUIT BREAKER STATUS
# ======================================================================

cb_status = spark.sql(f"""
    SELECT
        cb.state,
        COUNT(*) as count,
        COLLECT_LIST(CASE WHEN cb.state != 'CLOSED' THEN cb.agent_name END) as agents
    FROM {NEXUS_CIRCUIT} cb
    GROUP BY cb.state
    ORDER BY cb.state
""")

print("\U0001f6e1\ufe0f CIRCUIT BREAKER SUMMARY")
print("=" * 60)
display(cb_status)

# Show any OPEN or HALF_OPEN breakers
open_breakers = spark.sql(f"""
    SELECT cb.agent_name, cb.workspace, cb.state, cb.failure_count,
           cb.opened_at, cb.cooldown_minutes
    FROM {NEXUS_CIRCUIT} cb
    WHERE cb.state != 'CLOSED'
    ORDER BY cb.failure_count DESC
""")

if open_breakers.count() > 0:
    print("\n\u26a0\ufe0f AGENTS WITH OPEN/HALF_OPEN BREAKERS:")
    display(open_breakers)
else:
    print("\n\u2705 All circuit breakers CLOSED — platform healthy")

# COMMAND ----------

# DBTITLE 1,SECTION 3: Event Bus Health
# ======================================================================
# SECTION 3 — EVENT BUS HEALTH (7-day window)
# ======================================================================

event_health = spark.sql(f"""
    SELECT
        status,
        COUNT(*) as event_count,
        COUNT(DISTINCT event_type) as event_types,
        COUNT(DISTINCT source_agent) as unique_producers
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
    GROUP BY status
    ORDER BY status
""")

print("\U0001f4e8 EVENT BUS HEALTH (Last 7 Days)")
print("=" * 60)
display(event_health)

# Stale events (PUBLISHED but not consumed in 24h)
stale_events = spark.sql(f"""
    SELECT COUNT(*) as stale_count
    FROM {NEXUS_EVENTS}
    WHERE status = 'PUBLISHED'
      AND created_at < DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
""").collect()[0]['stale_count']

print(f"\n  Stale events (PUBLISHED > 24h): {stale_count}")
if stale_events > 0:
    print("  \u26a0\ufe0f Consider running 02_event_mesh to process or expire these")

# COMMAND ----------

# DBTITLE 1,SECTION 4: Governance Summary
# ======================================================================
# SECTION 4 — GOVERNANCE SUMMARY
# ======================================================================

total_agents = spark.sql(f"SELECT COUNT(*) as cnt FROM {NEXUS_REGISTRY}").collect()[0]['cnt']
active_agents = spark.sql(f"SELECT COUNT(*) as cnt FROM {NEXUS_REGISTRY} WHERE status = 'ACTIVE'").collect()[0]['cnt']
closed_breakers = spark.sql(f"SELECT COUNT(*) as cnt FROM {NEXUS_CIRCUIT} WHERE state = 'CLOSED'").collect()[0]['cnt']

# Platform health score
health_pct = (closed_breakers / max(total_agents, 1)) * 100

print(f"\n\U0001f3af NEXUS GOVERNANCE SUMMARY")
print("=" * 60)
print(f"  Total registered agents: {total_agents}")
print(f"  Active agents: {active_agents}")
print(f"  Circuit breakers healthy: {closed_breakers}/{total_agents}")
print(f"  Platform health: {health_pct:.0f}%")
print(f"  Governance agents: 5 (version, security, feedback, circuit, dashboard)")
print("=" * 60)

status_icon = '\U0001f7e2' if health_pct >= 95 else '\U0001f7e1' if health_pct >= 80 else '\U0001f534'
print(f"\n  {status_icon} Overall Status: {'HEALTHY' if health_pct >= 95 else 'DEGRADED' if health_pct >= 80 else 'CRITICAL'}")