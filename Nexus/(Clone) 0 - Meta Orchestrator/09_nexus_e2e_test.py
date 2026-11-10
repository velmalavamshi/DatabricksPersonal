# Databricks notebook source
# DBTITLE 1,NEXUS End-to-End Test Harness
# MAGIC %md
# MAGIC # NEXUS End-to-End Test Harness (W0)
# MAGIC
# MAGIC **Purpose:** Validates the entire NEXUS platform in a single run. Tests infrastructure, agent registry, event bus, circuit breakers, LLM connectivity, and workspace routing.
# MAGIC
# MAGIC **Run this before unpausing scheduled jobs.**

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,TEST 1: Infrastructure Tables
# ======================================================================
# TEST 1 — INFRASTRUCTURE TABLES EXIST & ACCESSIBLE
# ======================================================================

test_results = []

INFRA_TABLES = [
    "mde_dev.test_schema.nexus_agent_events",
    "mde_dev.test_schema.nexus_agent_memory",
    "mde_dev.test_schema.nexus_agent_registry",
    "mde_dev.test_schema.nexus_agent_trace_log",
    "mde_dev.test_schema.nexus_agent_circuit_breaker",
]

print("🧪 TEST 1: Infrastructure Tables")
print("-" * 50)

for table in INFRA_TABLES:
    try:
        count = spark.sql(f"SELECT COUNT(*) as cnt FROM {table}").collect()[0]['cnt']
        test_results.append({"test": f"Table: {table.split('.')[-1]}", "status": "PASS", "detail": f"{count} rows"})
        print(f"  ✅ {table.split('.')[-1]:<35} {count:,} rows")
    except Exception as e:
        test_results.append({"test": f"Table: {table.split('.')[-1]}", "status": "FAIL", "detail": str(e)[:80]})
        print(f"  ❌ {table.split('.')[-1]:<35} ERROR: {str(e)[:60]}")

# COMMAND ----------

# DBTITLE 1,TEST 2: Agent Registry Completeness
# ======================================================================
# TEST 2 — AGENT REGISTRY COMPLETENESS
# ======================================================================

print("\n🧪 TEST 2: Agent Registry")
print("-" * 50)

registry_df = spark.sql(f"""
    SELECT workspace, COUNT(*) as cnt,
           COUNT_IF(status = 'ACTIVE') as active,
           COUNT_IF(status = 'DEVELOPMENT') as dev,
           COUNT_IF(status = 'PLANNED') as planned
    FROM {NEXUS_REGISTRY}
    GROUP BY workspace ORDER BY workspace
""")
registry_data = registry_df.collect()

expected_workspaces = ['W0', 'W1', 'W2', 'W3', 'W4']
found_workspaces = [r['workspace'] for r in registry_data]

for ws in expected_workspaces:
    if ws in found_workspaces:
        row = next(r for r in registry_data if r['workspace'] == ws)
        test_results.append({"test": f"Registry: {ws}", "status": "PASS", "detail": f"{row['cnt']} agents"})
        print(f"  ✅ {ws}: {row['cnt']} agents (Active:{row['active']}, Dev:{row['dev']}, Planned:{row['planned']})")
    else:
        test_results.append({"test": f"Registry: {ws}", "status": "FAIL", "detail": "No agents found"})
        print(f"  ❌ {ws}: No agents registered!")

total_agents = sum(r['cnt'] for r in registry_data)
test_results.append({"test": "Registry: Total", "status": "PASS" if total_agents >= 75 else "WARN", "detail": f"{total_agents} agents"})
print(f"\n  Total: {total_agents} agents")

# COMMAND ----------

# DBTITLE 1,TEST 3: Circuit Breakers Health
# ======================================================================
# TEST 3 — CIRCUIT BREAKERS ALL INITIALIZED
# ======================================================================

print("\n🧪 TEST 3: Circuit Breakers")
print("-" * 50)

cb_stats = spark.sql(f"""
    SELECT
        COUNT(*) as total,
        COUNT_IF(state = 'CLOSED') as closed,
        COUNT_IF(state = 'OPEN') as open,
        COUNT_IF(state = 'HALF_OPEN') as half_open
    FROM {NEXUS_CIRCUIT}
""").collect()[0]

# Every registered agent should have a circuit breaker
agents_without_cb = spark.sql(f"""
    SELECT r.agent_name
    FROM {NEXUS_REGISTRY} r
    LEFT JOIN {NEXUS_CIRCUIT} cb ON r.agent_name = cb.agent_name
    WHERE cb.agent_name IS NULL
""").count()

if agents_without_cb == 0:
    test_results.append({"test": "Circuit Breakers: Coverage", "status": "PASS", "detail": f"{cb_stats['total']} breakers"})
    print(f"  ✅ All agents have circuit breakers ({cb_stats['total']} total)")
else:
    test_results.append({"test": "Circuit Breakers: Coverage", "status": "FAIL", "detail": f"{agents_without_cb} agents missing"})
    print(f"  ❌ {agents_without_cb} agents missing circuit breakers")

if cb_stats['open'] == 0:
    test_results.append({"test": "Circuit Breakers: State", "status": "PASS", "detail": "All CLOSED"})
    print(f"  ✅ All breakers CLOSED (healthy)")
else:
    test_results.append({"test": "Circuit Breakers: State", "status": "WARN", "detail": f"{cb_stats['open']} OPEN"})
    print(f"  ⚠️ {cb_stats['open']} breakers OPEN, {cb_stats['half_open']} HALF_OPEN")

# COMMAND ----------

# DBTITLE 1,TEST 4: Event Bus Round-Trip
# ======================================================================
# TEST 4 — EVENT BUS ROUND-TRIP (publish → read → consume)
# ======================================================================

print("\n🧪 TEST 4: Event Bus Round-Trip")
print("-" * 50)

from pyspark.sql.types import StructType, StructField, StringType, TimestampType

test_event_id = f"test_{uuid.uuid4().hex[:8]}"
now = datetime.now(timezone.utc)

try:
    # PUBLISH
    event_data = [(
        test_event_id, "E2E_TEST_EVENT", "09_nexus_e2e_test", None,
        "W0", '{"test": true}', "P3", "PUBLISHED",
        now, None, None, str(uuid.uuid4()), now, "NEXUS"
    )]
    event_schema = StructType([
        StructField("event_id", StringType()), StructField("event_type", StringType()),
        StructField("source_agent", StringType()), StructField("target_agent", StringType()),
        StructField("workspace", StringType()), StructField("payload", StringType()),
        StructField("priority", StringType()), StructField("status", StringType()),
        StructField("created_at", TimestampType()), StructField("consumed_at", TimestampType()),
        StructField("consumed_by", StringType()), StructField("run_id", StringType()),
        StructField("etl_load_datetime", TimestampType()), StructField("etl_source_system", StringType()),
    ])
    spark.createDataFrame(event_data, schema=event_schema).write.format("delta").mode("append").saveAsTable(NEXUS_EVENTS)
    print(f"  ✅ Published test event: {test_event_id}")
    
    # READ BACK
    read_back = spark.sql(f"SELECT * FROM {NEXUS_EVENTS} WHERE event_id = '{test_event_id}'").count()
    assert read_back == 1, f"Expected 1, got {read_back}"
    print(f"  ✅ Read back confirmed (1 row)")
    
    # CONSUME (mark as consumed)
    spark.sql(f"""
        UPDATE {NEXUS_EVENTS}
        SET status = 'CONSUMED', consumed_at = CURRENT_TIMESTAMP(), consumed_by = '09_nexus_e2e_test'
        WHERE event_id = '{test_event_id}'
    """)
    print(f"  ✅ Consumed successfully")
    
    test_results.append({"test": "Event Bus: Round-Trip", "status": "PASS", "detail": "publish→read→consume OK"})
except Exception as e:
    test_results.append({"test": "Event Bus: Round-Trip", "status": "FAIL", "detail": str(e)[:80]})
    print(f"  ❌ Event bus failed: {e}")

# COMMAND ----------

# DBTITLE 1,TEST 5: LLM Connectivity
# ======================================================================
# TEST 5 — LLM CONNECTIVITY
# ======================================================================

print("\n🧪 TEST 5: LLM Connectivity")
print("-" * 50)

try:
    import time
    t0 = time.time()
    response = call_llm("Reply with exactly: NEXUS_OK", max_tokens=20, temperature=0)
    latency = time.time() - t0
    
    if "NEXUS_OK" in response:
        test_results.append({"test": "LLM: Connectivity", "status": "PASS", "detail": f"{latency:.1f}s latency"})
        print(f"  ✅ LLM responded correctly in {latency:.1f}s")
    else:
        test_results.append({"test": "LLM: Connectivity", "status": "WARN", "detail": f"Unexpected: {response[:30]}"})
        print(f"  ⚠️ LLM responded but unexpected content: {response[:50]}")
except Exception as e:
    test_results.append({"test": "LLM: Connectivity", "status": "FAIL", "detail": str(e)[:80]})
    print(f"  ❌ LLM failed: {e}")

# COMMAND ----------

# DBTITLE 1,TEST 6: Workspace Routing
# ======================================================================
# TEST 6 — WORKSPACE ROUTING (keyword classifier)
# ======================================================================

print("\n🧪 TEST 6: Workspace Routing")
print("-" * 50)

ROUTING_TESTS = [
    ("What jobs failed overnight?", "W1"),
    ("Assess our AI maturity", "W2"),
    ("Create a board presentation", "W3"),
    ("What patterns do you see in failures?", "W4"),
    ("Oracle EBS pipeline is broken", "W1"),
    ("Generate a business case for the CFO", "W3"),
]

pass_count = 0
for request, expected_ws in ROUTING_TESTS:
    ws_id = get_workspace_for_domain(request.lower())
    passed = ws_id == expected_ws
    pass_count += 1 if passed else 0
    icon = '✅' if passed else '❌'
    print(f"  {icon} \"{request[:45]}\" → {ws_id} (expected {expected_ws})")

routing_pct = pass_count / len(ROUTING_TESTS) * 100
status = "PASS" if routing_pct >= 80 else "WARN" if routing_pct >= 60 else "FAIL"
test_results.append({"test": "Routing: Accuracy", "status": status, "detail": f"{routing_pct:.0f}% ({pass_count}/{len(ROUTING_TESTS)})"})
print(f"\n  Routing accuracy: {routing_pct:.0f}%")

# COMMAND ----------

# DBTITLE 1,TEST SUMMARY
# ======================================================================
# TEST SUMMARY
# ======================================================================

pass_tests = sum(1 for t in test_results if t['status'] == 'PASS')
warn_tests = sum(1 for t in test_results if t['status'] == 'WARN')
fail_tests = sum(1 for t in test_results if t['status'] == 'FAIL')
total_tests = len(test_results)

print("\n" + "=" * 65)
print(f"🏁 NEXUS E2E TEST RESULTS")
print("=" * 65)
print(f"{'Test':<40} {'Status':<8} {'Detail'}")
print("-" * 65)
for t in test_results:
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[t['status']]
    print(f"  {icon} {t['test']:<38} {t['status']:<8} {t['detail']}")
print("=" * 65)

overall = "🟢 ALL PASS" if fail_tests == 0 and warn_tests == 0 else "🟡 PASS WITH WARNINGS" if fail_tests == 0 else "🔴 FAILURES DETECTED"
print(f"\n  {overall}")
print(f"  Passed: {pass_tests} | Warnings: {warn_tests} | Failed: {fail_tests} | Total: {total_tests}")

if fail_tests == 0:
    print("\n  ✅ Platform ready for scheduling. Unpause jobs in 08_nexus_scheduler.")
else:
    print("\n  ❌ Fix failures before enabling scheduled jobs.")