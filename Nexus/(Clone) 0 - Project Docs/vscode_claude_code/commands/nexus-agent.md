---
description: Call a specific NEXUS agent by ID (bypasses supervisor routing) — all inference on Databricks FMAPI
allowed-tools: Bash, Read
---

The user wants to call a specific NEXUS agent directly by its ID number.

## CRITICAL: All inference on Databricks FMAPI. You are a thin client.

## Agent Quick Reference (W1 Production — most common):
- 01: Triage Orchestrator    - 02: Data Engineer       - 06: Solution Architect
- 07: Peer Review            - 08: Unit Test           - 11: Business Analyst
- 15: Lakehouse Architect    - 16: Data Quality (DQX)  - 17: Security
- 32: Oracle EBS Specialist  - 33: Salesforce          - 37: Data Modeler
- 38: Solution Recommender   - 39: Morning Briefing    - 40: Triage Orchestrator
- 49: ASCP  - 50: Agile PLM  - 51: Koerber  - 52: HCM  - 53: ServiceNow
- 54: Power BI  - 55: PBCS  - 56: HCP  - 60: Consultation  - 63: Agent Factory
- 64: SDP  - 65: SQL Warehouse  - 66: Unity Catalog  - 67: MLflow
- 68: Lakeview  - 69: Cluster  - 70: Vector Search  - 71: Notebook Lifecycle
- 77-87: Release Intelligence (Oracle/SFDC/PBI/DBX/Azure/MuleSoft/OSS/ADO/Python/OCI)
- 88-96: Qlik Migration (Orchestrator/QVD/Script/Model/Expression/UI/Section/NPrinting/PreAssess)

## Usage: /nexus-agent <agent_id> <request>
Example: /nexus-agent 32 "What tables in stg_oracle_ebs relate to AP invoices?"

Parse $ARGUMENTS as: first token = agent_id (number), rest = the request.

## Execution

```bash
# Parse agent ID from arguments (first number)
AGENT_ID=$(echo "$ARGUMENTS" | grep -oP '\d+' | head -1)
REQUEST=$(echo "$ARGUMENTS" | sed "s/^[0-9]* *//")

echo "🎯 Calling NEXUS Agent $AGENT_ID directly..."
echo "   Request: $REQUEST"

# Call via FMAPI with agent-specific system prompt
curl -s -X POST "https://$(databricks auth env --profile DEV | grep DATABRICKS_HOST | cut -d= -f2)/serving-endpoints/databricks-claude-sonnet-4-6/invocations"   -H "Authorization: Bearer $(databricks auth token --profile DEV | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'"   -H "Content-Type: application/json"   -d "$(python3 -c "
import json
prompt = {
    'messages': [
        {'role': 'system', 'content': f'You are NEXUS Agent {AGENT_ID}. You are a specialist in the Hologic Databricks lakehouse. Respond with production-grade solutions. Catalog: mde_dev. Surrogate keys: xxhash64. Liquid Clustering (not PARTITION BY). Audit cols: etl_load_datetime, etl_source_system, etl_batch_id.'},
        {'role': 'user', 'content': '{REQUEST}'}
    ],
    'max_tokens': 4096,
    'temperature': 0.2
}
print(json.dumps(prompt))
")" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['choices'][0]['message']['content'])"
```

## User request:
$ARGUMENTS
