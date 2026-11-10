---
description: Check NEXUS platform health — agent registry, event bus, circuit breakers
allowed-tools: Bash, Read
---

Check the health and status of the NEXUS Multi-Agent Platform on Databricks.

## Execution

```bash
echo "═══════════════════════════════════════════════════"
echo "🧠 NEXUS Platform Status"
echo "═══════════════════════════════════════════════════"

# Query agent registry
echo "
📋 Agent Registry:"
databricks api post /api/2.0/sql/statements   --profile DEV   --json '{"warehouse_id":"SQL_WAREHOUSE_ID","statement":"SELECT workspace, COUNT(*) as agent_count, SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) as active FROM mde_dev.test_schema.nexus_agent_registry GROUP BY workspace ORDER BY workspace","wait_timeout":"30s"}' 2>&1 | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    for row in r.get('result',{}).get('data_array',[]):
        print(f'  {row[0]}: {row[1]} agents ({row[2]} active)')
except: print('  ⚠️ Could not query registry')
"

# Check recent events
echo "
📡 Recent Events (last 1h):"
databricks api post /api/2.0/sql/statements   --profile DEV   --json '{"warehouse_id":"SQL_WAREHOUSE_ID","statement":"SELECT event_type, COUNT(*) as cnt FROM mde_dev.test_schema.nexus_agent_events WHERE created_at > DATEADD(HOUR, -1, CURRENT_TIMESTAMP()) GROUP BY event_type ORDER BY cnt DESC LIMIT 5","wait_timeout":"30s"}' 2>&1 | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    for row in r.get('result',{}).get('data_array',[]):
        print(f'  {row[0]}: {row[1]} events')
except: print('  ⚠️ No recent events')
"

# Check circuit breakers
echo "
🔌 Circuit Breakers:"
databricks api post /api/2.0/sql/statements   --profile DEV   --json '{"warehouse_id":"SQL_WAREHOUSE_ID","statement":"SELECT agent_name, state, failure_count FROM mde_dev.test_schema.nexus_agent_circuit_breaker WHERE state != 'CLOSED' ORDER BY failure_count DESC LIMIT 5","wait_timeout":"30s"}' 2>&1 | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    rows = r.get('result',{}).get('data_array',[])
    if rows:
        for row in rows:
            print(f'  ⚠️ {row[0]}: {row[1]} (failures: {row[2]})')
    else:
        print('  ✅ All circuits CLOSED (healthy)')
except: print('  ⚠️ Could not query circuit breakers')
"

echo "
═══════════════════════════════════════════════════"
echo "Platform: 134 agents | 5 workspaces | LLM: databricks-claude-sonnet-4-6"
echo "═══════════════════════════════════════════════════"
```
