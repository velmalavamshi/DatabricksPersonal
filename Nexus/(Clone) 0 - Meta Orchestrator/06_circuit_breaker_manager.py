# Databricks notebook source
# DBTITLE 1,Circuit Breaker Manager
# MAGIC %md
# MAGIC # NEXUS Governance — Circuit Breaker Manager (W0)
# MAGIC
# MAGIC **Purpose:** Active management of the circuit breaker system. Monitors failure rates, transitions breaker states (CLOSED → OPEN → HALF_OPEN → CLOSED), handles cooldown, and tests recovery.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Process Circuit Breakers
# ======================================================================
# STEP 1 — PROCESS CIRCUIT BREAKER STATE TRANSITIONS
# CLOSED: normal operation
# OPEN: agent paused (failure_count >= threshold)
# HALF_OPEN: testing recovery after cooldown
# ======================================================================

AGENT_NAME = "06_circuit_breaker_manager"
run_id = generate_run_id()
start_time = datetime.now(timezone.utc)

# Get all circuit breakers
breakers = spark.sql(f"""
    SELECT cb.*, r.status as agent_status, r.total_runs
    FROM {NEXUS_CIRCUIT} cb
    JOIN {NEXUS_REGISTRY} r ON cb.agent_name = r.agent_name
    ORDER BY cb.state DESC, cb.failure_count DESC
""").collect()

transitions = []

for cb in breakers:
    agent = cb['agent_name']
    state = cb['state']
    failures = cb['failure_count']
    threshold = cb['failure_threshold']
    cooldown_min = cb['cooldown_minutes']
    opened_at = cb['opened_at']
    
    new_state = state
    
    if state == 'CLOSED' and failures >= threshold:
        # OPEN the breaker
        new_state = 'OPEN'
        transitions.append({"agent": agent, "from": state, "to": new_state, "reason": f"{failures} failures >= threshold {threshold}"})
        
    elif state == 'OPEN' and opened_at:
        # Check if cooldown has elapsed
        elapsed_min = (start_time - opened_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
        if elapsed_min >= cooldown_min:
            new_state = 'HALF_OPEN'
            transitions.append({"agent": agent, "from": state, "to": new_state, "reason": f"Cooldown elapsed ({cooldown_min}min)"})
    
    elif state == 'HALF_OPEN':
        # In HALF_OPEN: next successful run closes it, next failure re-opens
        # For now, auto-close after being in HALF_OPEN for 5 minutes (allow one test run)
        if opened_at:
            elapsed_min = (start_time - opened_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if elapsed_min >= cooldown_min + 5:
                new_state = 'CLOSED'
                transitions.append({"agent": agent, "from": state, "to": new_state, "reason": "Recovery test window passed"})
    
    # Apply transitions
    if new_state != state:
        if new_state == 'OPEN':
            spark.sql(f"""
                UPDATE {NEXUS_CIRCUIT}
                SET state = '{new_state}', opened_at = CURRENT_TIMESTAMP(), updated_at = CURRENT_TIMESTAMP()
                WHERE agent_name = '{agent}'
            """)
        elif new_state == 'CLOSED':
            spark.sql(f"""
                UPDATE {NEXUS_CIRCUIT}
                SET state = '{new_state}', failure_count = 0, opened_at = NULL,
                    next_retry_at = NULL, updated_at = CURRENT_TIMESTAMP()
                WHERE agent_name = '{agent}'
            """)
        else:
            spark.sql(f"""
                UPDATE {NEXUS_CIRCUIT}
                SET state = '{new_state}', updated_at = CURRENT_TIMESTAMP()
                WHERE agent_name = '{agent}'
            """)

# Summary
state_counts = {}
for cb in breakers:
    s = cb['state']
    state_counts[s] = state_counts.get(s, 0) + 1

print(f"\U0001f6e1\ufe0f CIRCUIT BREAKER MANAGER")
print("=" * 60)
print(f"  Total breakers: {len(breakers)}")
for state, count in sorted(state_counts.items()):
    icon = {'CLOSED': '\u2705', 'OPEN': '\U0001f534', 'HALF_OPEN': '\U0001f7e1'}[state]
    print(f"    {icon} {state}: {count}")
print(f"  Transitions this run: {len(transitions)}")
print("=" * 60)

for t in transitions:
    print(f"  {t['agent']}: {t['from']} \u2192 {t['to']} ({t['reason']})")