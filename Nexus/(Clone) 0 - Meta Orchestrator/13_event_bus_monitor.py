# Databricks notebook source
# DBTITLE 1,Event Bus Monitor
# MAGIC %md
# MAGIC # NEXUS Phase 11 — Event Bus Monitor (W0)
# MAGIC
# MAGIC **Purpose:** Deep observability into the Delta event bus: throughput, publish-to-consume latency, stale event alerts, top producer/consumer rankings, bottleneck detection.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Event Bus Throughput and Latency
# ======================================================================
# STEP 1 — EVENT BUS THROUGHPUT & LATENCY
# ======================================================================

AGENT_NAME = "13_event_bus_monitor"
run_id = generate_run_id()

# Hourly event throughput (24h)
throughput = spark.sql(f"""
    SELECT
        DATE_TRUNC('HOUR', created_at) as hour_bucket,
        COUNT(*) as events_published,
        COUNT_IF(status = 'CONSUMED') as events_consumed,
        COUNT_IF(status = 'EXPIRED') as events_expired,
        ROUND(AVG(CASE WHEN consumed_at IS NOT NULL
            THEN TIMESTAMPDIFF(SECOND, created_at, consumed_at) END), 1) as avg_consume_latency_sec
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
    GROUP BY DATE_TRUNC('HOUR', created_at)
    ORDER BY hour_bucket DESC
""")

throughput_data = throughput.collect()

print(f"\U0001f4e8 EVENT BUS THROUGHPUT (Last 24h)")
print("=" * 70)
print(f"{'Hour':<20} {'Published':<12} {'Consumed':<12} {'Expired':<10} {'Avg Latency'}")
print("-" * 70)
for row in throughput_data[:12]:  # Last 12 hours
    hour = row['hour_bucket'].strftime('%Y-%m-%d %H:00') if row['hour_bucket'] else 'N/A'
    latency = f"{row['avg_consume_latency_sec']}s" if row['avg_consume_latency_sec'] else '-'
    print(f"  {hour:<20} {row['events_published']:<12} {row['events_consumed']:<12} {row['events_expired']:<10} {latency}")
print("=" * 70)

# Overall stats
total_24h = sum(r['events_published'] for r in throughput_data)
total_consumed = sum(r['events_consumed'] for r in throughput_data)
consumption_rate = (total_consumed / max(total_24h, 1)) * 100
print(f"\n  Total events (24h): {total_24h}")
print(f"  Consumption rate: {consumption_rate:.1f}%")

# COMMAND ----------

# DBTITLE 1,STEP 2: Producer and Consumer Rankings
# ======================================================================
# STEP 2 — TOP PRODUCERS & CONSUMERS
# ======================================================================

# Top producers
producers = spark.sql(f"""
    SELECT source_agent, workspace,
           COUNT(*) as events_produced,
           COUNT(DISTINCT event_type) as event_types
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      AND source_agent IS NOT NULL
    GROUP BY source_agent, workspace
    ORDER BY events_produced DESC
    LIMIT 10
""").collect()

# Top consumers
consumers = spark.sql(f"""
    SELECT consumed_by, 
           COUNT(*) as events_consumed,
           ROUND(AVG(TIMESTAMPDIFF(SECOND, created_at, consumed_at)), 1) as avg_latency_sec
    FROM {NEXUS_EVENTS}
    WHERE consumed_at >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      AND consumed_by IS NOT NULL
    GROUP BY consumed_by
    ORDER BY events_consumed DESC
    LIMIT 10
""").collect()

# Event type distribution
event_types = spark.sql(f"""
    SELECT event_type, priority, COUNT(*) as count
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
    GROUP BY event_type, priority
    ORDER BY count DESC
    LIMIT 15
""").collect()

print(f"\n\U0001f3c6 TOP PRODUCERS (7d)")
print("-" * 55)
for p in producers[:5]:
    print(f"  {p['source_agent']:<35} {p['events_produced']} events ({p['event_types']} types)")

print(f"\n\U0001f3c6 TOP CONSUMERS (7d)")
print("-" * 55)
for c in consumers[:5]:
    print(f"  {c['consumed_by']:<35} {c['events_consumed']} consumed (avg {c['avg_latency_sec']}s)")

print(f"\n\U0001f4cb EVENT TYPE DISTRIBUTION (7d)")
print("-" * 55)
for et in event_types[:10]:
    print(f"  [{et['priority']}] {et['event_type']:<35} {et['count']}")

# COMMAND ----------

# DBTITLE 1,STEP 3: Bottleneck and Stale Event Detection
# ======================================================================
# STEP 3 — BOTTLENECK & STALE EVENT DETECTION
# ======================================================================

# Events stuck in PUBLISHED for too long
stale_events = spark.sql(f"""
    SELECT event_id, event_type, source_agent, target_agent, priority,
           created_at,
           TIMESTAMPDIFF(MINUTE, created_at, CURRENT_TIMESTAMP()) as minutes_stale
    FROM {NEXUS_EVENTS}
    WHERE status = 'PUBLISHED'
      AND created_at < DATEADD(HOUR, -1, CURRENT_TIMESTAMP())
    ORDER BY created_at ASC
    LIMIT 20
""")

stale_data = stale_events.collect()

print(f"\n\u26a0\ufe0f STALE EVENTS (Published > 1h, not consumed)")
print("=" * 70)
if stale_data:
    print(f"{'Event Type':<30} {'Source':<25} {'Priority':<6} {'Stale (min)'}")
    print("-" * 70)
    for s in stale_data:
        print(f"  {s['event_type'][:28]:<30} {s['source_agent'][:23]:<25} {s['priority']:<6} {s['minutes_stale']}m")
    print(f"\n  \U0001f534 {len(stale_data)} stale events detected — check 02_event_mesh dispatcher")
else:
    print("  \u2705 No stale events — event bus flowing normally")

print(f"\n\u2705 Event bus monitor complete")