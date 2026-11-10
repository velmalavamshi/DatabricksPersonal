---
description: Route any request through the NEXUS 134-agent platform on Databricks (all inference via FMAPI)
allowed-tools: Bash, Read, Write
---

The user wants to route a request through the NEXUS Multi-Agent AI Platform running on Databricks.

## CRITICAL: All AI inference happens on Databricks FMAPI — NOT locally.

You are acting as a **thin client**. Your job is:
1. Submit the request to the NEXUS Meta Supervisor via Databricks Jobs API
2. Wait for completion
3. Return the agent response verbatim

Do NOT attempt to answer the request yourself. NEXUS has 134 specialized agents.

## Architecture
- W0: Meta Orchestrator (16 agents) — routing, governance, monitoring
- W1: Production Agents (103 agents) — jobs, pipelines, cost, data quality, Oracle EBS, Salesforce, ASCP, Qlik Migration
- W2: Value Discovery (6 agents) — client scanning, use case scoring
- W3: Business Champions (4 agents) — board-ready business cases
- W4: Collective Intelligence (4 agents) — pattern learning, benchmarks

## Execution

```bash
# Submit to NEXUS Meta Supervisor
RUN_OUTPUT=$(databricks jobs submit --json '{"run_name":"nexus_vscode","tasks":[{"task_key":"supervisor","notebook_task":{"notebook_path":"/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/0 - Meta Orchestrator/00_meta_supervisor","base_parameters":{"request":"$ARGUMENTS"}},"existing_cluster_id":"0925-054849-fb85h9tq"}]}' --profile DEV 2>&1)

RUN_ID=$(echo "$RUN_OUTPUT" | grep -o '"run_id":[0-9]*' | grep -o '[0-9]*')
echo "⚡ NEXUS run submitted: $RUN_ID"
echo "   Routing through Meta Supervisor → W1/W2/W3/W4..."

# Poll for completion (timeout 5 min)
for i in $(seq 1 60); do
  STATUS=$(databricks runs get $RUN_ID --profile DEV 2>&1 | grep -o '"life_cycle_state":"[A-Z_]*"' | head -1 | cut -d'"' -f4)
  if [ "$STATUS" = "TERMINATED" ]; then
    echo "✅ Complete"
    databricks runs get-output $RUN_ID --profile DEV 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('notebook_output',{}).get('result','No output'))"
    break
  elif [ "$STATUS" = "INTERNAL_ERROR" ] || [ "$STATUS" = "SKIPPED" ]; then
    echo "❌ Failed: $STATUS"
    databricks runs get $RUN_ID --profile DEV 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('state_message','Unknown error'))"
    break
  fi
  sleep 5
done
```

## User request:
$ARGUMENTS
