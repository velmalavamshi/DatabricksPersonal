---
description: Run a Qlik Migration step via NEXUS Agent 88 (Orchestrator) — all inference on Databricks FMAPI
allowed-tools: Bash, Read, Write
---

The user wants to execute a Qlik-to-Databricks migration step via NEXUS Agent 88.

## CRITICAL: All inference on Databricks FMAPI. You are a thin client.

Agent 88 orchestrates agents 89-96:
- 89: QVD Extraction (QVD → Delta)
- 90: Script Conversion (QVS/QVW → PySpark/SQL/SDP)
- 91: Data Model (Associative → Kimball star schema)
- 92: Expression Conversion (Set analysis, AGGR() → SQL)
- 93: UI Migration (Charts → Lakeview/Power BI)
- 94: Section Access (→ UC row filters, ABAC)
- 95: NPrinting (→ Jobs + Lakeview subscriptions)
- 96: Pre-Assessment (deterministic regex parse)

## Execution

```bash
# Run Agent 88 with step-by-step mode
RUN_OUTPUT=$(databricks jobs submit --json '{"run_name":"nexus_qlik_migration","tasks":[{"task_key":"qlik_step","notebook_task":{"notebook_path":"/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration/NEXUS_Qlik_Migration_Prompt","base_parameters":{"request":"$ARGUMENTS","mode":"step"}},"existing_cluster_id":"0925-054849-fb85h9tq"}]}' --profile DEV 2>&1)

RUN_ID=$(echo "$RUN_OUTPUT" | grep -o '"run_id":[0-9]*' | grep -o '[0-9]*')
echo "🔄 Qlik Migration step submitted: $RUN_ID"
echo "   Agent 88 orchestrating..."

# Poll (10 min timeout for heavy file parsing)
for i in $(seq 1 120); do
  STATUS=$(databricks runs get $RUN_ID --profile DEV 2>&1 | grep -o '"life_cycle_state":"[A-Z_]*"' | head -1 | cut -d'"' -f4)
  if [ "$STATUS" = "TERMINATED" ]; then
    echo "✅ Step complete"
    databricks runs get-output $RUN_ID --profile DEV 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('notebook_output',{}).get('result','No output'))"
    break
  elif [ "$STATUS" = "INTERNAL_ERROR" ] || [ "$STATUS" = "SKIPPED" ]; then
    echo "❌ Failed: $STATUS"
    break
  fi
  sleep 5
done
```

## User step request:
$ARGUMENTS
