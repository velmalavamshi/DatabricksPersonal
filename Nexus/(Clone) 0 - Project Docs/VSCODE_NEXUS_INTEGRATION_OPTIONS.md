# VS Code → NEXUS Supervisor Integration Options

**Goal:** Route requests from VS Code through the NEXUS 134-agent platform, with all LLM inference happening on Databricks Foundation Model APIs (`databricks-claude-sonnet-4-6` / `databricks-claude-opus-4-8`) — NOT direct Anthropic calls.

**Date:** 2026-08-03  
**Author:** NEXUS Agent 88 (Orchestrator)

---

## Option A: Claude Code + Databricks MCP Server (RECOMMENDED — Fastest to Deploy)

**How it works:** Claude Code in VS Code connects to a Databricks MCP server that exposes NEXUS as callable tools. Claude Code handles the UI/chat; the MCP server routes to your NEXUS Supervisor which dispatches to the 134 agents via Databricks FMAPI.

**Architecture:**
```
VS Code (Claude Code) 
  → MCP Protocol (stdio/HTTP) 
    → Databricks MCP Server (UC Functions) 
      → nexus_route_request() UC Function 
        → FMAPI (databricks-claude-sonnet-4-6) 
          → NEXUS Meta Supervisor logic 
            → W1/W2/W3/W4 Agent routing
```

**Setup Steps:**

### Step 1: Create UC Functions that wrap NEXUS

```sql
-- In mde_dev.test_schema (or a dedicated catalog.schema for MCP)
CREATE OR REPLACE FUNCTION mde_dev.test_schema.nexus_route_request(
  user_request STRING COMMENT 'Natural language request to route through NEXUS'
)
RETURNS STRING
LANGUAGE PYTHON
DETERMINISTIC
COMMENT 'Routes a request through the NEXUS Meta Supervisor to 134+ agents. All inference happens on Databricks FMAPI.'
AS $
import requests, json

# Call the NEXUS Supervisor serving endpoint or notebook job
# Option A1: Via a lightweight Model Serving endpoint
# Option A2: Via Databricks Jobs API (run notebook)
workspace_url = "https://<DEV-workspace-url>"
token = "<use-service-principal-token-from-secret-scope>"

# Classify intent
intent_prompt = f"""Classify into W1/W2/W3/W4:\n{user_request}"""
resp = requests.post(
    f"{workspace_url}/serving-endpoints/databricks-claude-sonnet-4-6/invocations",
    headers={"Authorization": f"Bearer {token}"},
    json={"messages": [{"role": "user", "content": intent_prompt}], "max_tokens": 500}
)
return resp.json()["choices"][0]["message"]["content"]
$;
```

### Step 2: Configure Claude Code MCP in VS Code

Run in terminal:
```bash
# Using Databricks CLI auth (you already have this configured)
claude mcp add-json nexus-supervisor \
  '{"type":"stdio","command":"uvx","args":["uc-mcp-proxy","--url","https://<workspace>.azuredatabricks.net/api/2.0/mcp/functions/mde_dev/test_schema","--auth-type","databricks-cli","--profile","DEV"]}'
```

Or add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "nexus-supervisor": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "uc-mcp-proxy",
        "--url", "https://<workspace>.azuredatabricks.net/api/2.0/mcp/functions/mde_dev/test_schema",
        "--auth-type", "databricks-cli",
        "--profile", "DEV"
      ]
    }
  }
}
```

### Step 3: Claude Code System Prompt (`.claude/CLAUDE.md`)

```markdown
# NEXUS Integration

You have access to the NEXUS Multi-Agent Platform via MCP tools.
When the user makes ANY request, route it through `nexus_route_request()` first.
All AI inference happens on Databricks Foundation Model APIs — not locally.

Available NEXUS functions:
- nexus_route_request(request) — Routes to the correct agent among 134 specialists
- nexus_run_agent(agent_id, request) — Calls a specific agent directly
- nexus_get_status() — Check platform health and agent availability
```

**Pros:** Native MCP support, no custom code to maintain, uses existing Databricks CLI auth  
**Cons:** UC Functions have 10-min timeout, limited to text in/text out  
**Effort:** ~2 hours

---

## Option B: Databricks App as REST Gateway (Most Flexible)

**How it works:** Deploy a Databricks App (Flask/FastAPI) that exposes a `/chat` endpoint. VS Code hits this endpoint via a custom MCP server or direct REST. The App runs the full NEXUS Supervisor logic server-side.

**Architecture:**
```
VS Code (Claude Code or custom extension)
  → HTTP POST to Databricks App
    → app.py (FastAPI)
      → FMAPI call (databricks-claude-sonnet-4-6)
        → NEXUS Meta Supervisor routing
          → Agent execution (notebooks via Jobs API)
            → Response back to VS Code
```

**app.py:**
```python
from fastapi import FastAPI, Request
from databricks.sdk import WorkspaceClient
import json

app = FastAPI(title="NEXUS Gateway")
w = WorkspaceClient()  # Auto-auth in Databricks Apps

WORKSPACE_REGISTRY = {
    "W1": {"name": "Production Agents", "domains": ["jobs", "pipelines", "cost", "data quality", "oracle", "salesforce"]},
    "W2": {"name": "Value Discovery", "domains": ["assessment", "use cases", "scanning", "maturity"]},
    "W3": {"name": "Business Champions", "domains": ["business case", "board", "presentation"]},
    "W4": {"name": "Collective Intelligence", "domains": ["benchmark", "patterns", "prediction"]},
}

@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_message = body["message"]
    
    # Route through FMAPI (all inference on Databricks)
    from databricks.sdk.service.serving import ChatMessage
    response = w.serving_endpoints.query(
        name="databricks-claude-sonnet-4-6",
        messages=[{
            "role": "system",
            "content": NEXUS_SUPERVISOR_SYSTEM_PROMPT  # Full 134-agent routing prompt
        }, {
            "role": "user", 
            "content": user_message
        }],
        max_tokens=4096
    )
    return {"response": response.choices[0].message.content}

@app.post("/agent/{agent_id}")
async def call_agent(agent_id: int, request: Request):
    """Direct agent invocation — bypasses supervisor routing."""
    body = await request.json()
    # Trigger notebook via Jobs API
    run = w.jobs.submit(
        run_name=f"nexus_agent_{agent_id}",
        tasks=[{
            "task_key": "agent_run",
            "notebook_task": {
                "notebook_path": f"/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/1 - Production Agents/{agent_id:02d}_*",
                "base_parameters": {"request": body["message"]}
            }
        }]
    )
    return {"run_id": run.run_id, "status": "submitted"}
```

**app.yaml:**
```yaml
command:
  - uvicorn
  - app:app
  - --host=0.0.0.0
  - --port=8000
env:
  - name: DATABRICKS_HOST
    value: "https://<workspace>.azuredatabricks.net"
```

**VS Code MCP config (connects to the App):**
```json
{
  "mcpServers": {
    "nexus-app": {
      "type": "http",
      "url": "https://<app-name>-<workspace-id>.apps.azuredatabricks.net/mcp"
    }
  }
}
```

**Pros:** Full control, can run notebooks/jobs, streaming support, no timeout limits  
**Cons:** Requires App deployment, ongoing maintenance  
**Effort:** ~4-6 hours

---

## Option C: Claude Code Custom Commands + Databricks CLI (Simplest — Zero Infra)

**How it works:** Create custom slash commands in Claude Code that use the Databricks CLI/REST API to trigger NEXUS notebooks as jobs. No MCP server, no App deployment.

**Architecture:**
```
VS Code (Claude Code)
  → /nexus slash command
    → Databricks CLI (databricks jobs submit)
      → Runs 00_meta_supervisor notebook
        → FMAPI (databricks-claude-sonnet-4-6)
          → Agent routing + execution
            → Results written to Delta
              → CLI polls for output
```

**Setup:**

Create `.claude/commands/nexus.md`:
```markdown
---
description: Route a request through the NEXUS 134-agent platform on Databricks
allowed-tools: Bash, Read
---

The user wants to use the NEXUS Multi-Agent Platform. Route their request through Databricks.

## Steps:
1. Submit the request to the NEXUS Meta Supervisor notebook via Databricks Jobs API
2. Poll for completion
3. Return the agent response

## Execution:
```bash
# Submit NEXUS supervisor job
RUN_ID=$(databricks jobs submit --json '{
  "run_name": "nexus_vscode_request",
  "tasks": [{
    "task_key": "supervisor",
    "notebook_task": {
      "notebook_path": "/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/0 - Meta Orchestrator/00_meta_supervisor",
      "base_parameters": {
        "request": "$ARGUMENTS"
      }
    },
    "new_cluster": {
      "spark_version": "17.3.x-scala2.13",
      "node_type_id": "Standard_E4ds_v5",
      "num_workers": 0,
      "data_security_mode": "USER_ISOLATION"
    }
  }]
}' --profile DEV | jq -r '.run_id')

echo "Submitted NEXUS run: $RUN_ID"

# Poll until complete
while true; do
  STATUS=$(databricks runs get $RUN_ID --profile DEV | jq -r '.state.life_cycle_state')
  if [ "$STATUS" = "TERMINATED" ]; then
    break
  fi
  sleep 5
done

# Get output
databricks runs get-output $RUN_ID --profile DEV | jq -r '.notebook_output.result'
```

The NEXUS supervisor will:
- Classify intent (W1/W2/W3/W4)
- Route to the correct specialist agent(s)
- Execute using Databricks FMAPI (databricks-claude-sonnet-4-6)
- Return the consolidated response

User's request: $ARGUMENTS
```

Create `.claude/commands/nexus-qlik.md`:
```markdown
---
description: Run a Qlik Migration step via NEXUS Agent 88
allowed-tools: Bash, Read
---

Run a specific Qlik Migration step using Agent 88 (Orchestrator).

```bash
databricks jobs submit --json '{
  "run_name": "nexus_qlik_step",
  "tasks": [{
    "task_key": "qlik_migration",
    "notebook_task": {
      "notebook_path": "/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/1 - Production Agents/88_qlik_migration_orchestrator",
      "base_parameters": {
        "request": "$ARGUMENTS",
        "mode": "inventory"
      }
    },
    "existing_cluster_id": "<phoenix-cluster-id>"
  }]
}' --profile DEV
```

User's step request: $ARGUMENTS
```

**Pros:** Zero infrastructure, works today with existing CLI auth, no deployment  
**Cons:** Cold-start latency (cluster spin-up), no streaming, batch-only  
**Effort:** ~30 minutes

---

## Option D: Custom MCP Server (Python — Full NEXUS Integration)

**How it works:** Build a local Python MCP server that wraps the full NEXUS routing logic. It calls Databricks FMAPI directly for inference and uses the Jobs/Notebooks API for execution. Runs locally but ALL LLM calls go to Databricks.

**Architecture:**
```
VS Code (Claude Code / Cursor / Copilot)
  → stdio MCP connection
    → Local Python MCP server (nexus_mcp_server.py)
      → Databricks SDK (WorkspaceClient)
        → FMAPI: databricks-claude-sonnet-4-6 (intent classification)
        → FMAPI: databricks-claude-sonnet-4-6 (agent response)
        → Jobs API: notebook execution for complex tasks
        → SQL API: Delta table reads/writes
```

**nexus_mcp_server.py:**
```python
#!/usr/bin/env python3
"""NEXUS MCP Server — Routes VS Code requests through Databricks FMAPI."""

import asyncio
import json
from mcp.server import Server
from mcp.types import Tool, TextContent
from databricks.sdk import WorkspaceClient

app = Server("nexus-mcp")
w = WorkspaceClient(profile="DEV")  # Uses existing Databricks CLI auth

# Full NEXUS system prompt (same as CHAT_Interactive_Supervisor)
NEXUS_SYSTEM_PROMPT = open(
    "/path/to/nexus_supervisor_prompt.txt", "r"
).read()

WORKSPACE_REGISTRY = {
    "W1": {"name": "Production Agents", "agent_count": 103,
           "domains": ["jobs", "pipelines", "cost", "data quality", "deployment",
                       "oracle", "salesforce", "servicenow", "powerbi", "hcm"]},
    "W2": {"name": "Value Discovery", "agent_count": 6,
           "domains": ["assessment", "use cases", "client", "scanning", "maturity"]},
    "W3": {"name": "Business Champions", "agent_count": 4,
           "domains": ["business case", "board", "presentation", "champion"]},
    "W4": {"name": "Collective Intelligence", "agent_count": 4,
           "domains": ["benchmark", "patterns", "prediction", "competitive"]},
}

def call_fmapi(messages, max_tokens=4096, temperature=0.2):
    """Call Databricks Foundation Model API — ALL inference on Databricks."""
    response = w.serving_endpoints.query(
        name="databricks-claude-sonnet-4-6",
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )
    return response.choices[0].message.content


@app.tool()
async def nexus_route(request: str) -> list[TextContent]:
    """Route a request through the NEXUS Meta Supervisor to 134+ agents.
    All inference happens on Databricks FMAPI, not locally."""
    
    # Step 1: Classify intent
    classification = call_fmapi([
        {"role": "system", "content": "Classify into W1/W2/W3/W4 workspace. Respond JSON only."},
        {"role": "user", "content": request}
    ], max_tokens=200, temperature=0.0)
    
    # Step 2: Route to agent
    response = call_fmapi([
        {"role": "system", "content": NEXUS_SYSTEM_PROMPT},
        {"role": "user", "content": request}
    ])
    
    return [TextContent(type="text", text=response)]


@app.tool()
async def nexus_run_notebook(notebook_path: str, parameters: dict) -> list[TextContent]:
    """Execute a NEXUS agent notebook on Databricks compute."""
    run = w.jobs.submit(
        run_name="nexus_vscode",
        tasks=[{
            "task_key": "agent",
            "notebook_task": {
                "notebook_path": notebook_path,
                "base_parameters": {k: str(v) for k, v in parameters.items()}
            },
            "new_cluster": {
                "spark_version": "17.3.x-scala2.13",
                "node_type_id": "Standard_E4ds_v5",
                "num_workers": 0,
                "data_security_mode": "USER_ISOLATION"
            }
        }]
    )
    # Wait for completion
    result = w.jobs.wait_get_run_job_terminated_or_skipped(run_id=run.run_id)
    output = w.jobs.get_run_output(run.run_id)
    return [TextContent(type="text", text=output.notebook_output.result or "Complete")]


@app.tool()
async def nexus_query_delta(sql: str) -> list[TextContent]:
    """Query NEXUS Delta tables (agent memory, event bus, registry)."""
    result = w.statement_execution.execute_statement(
        warehouse_id="<sql-warehouse-id>",
        statement=sql,
        catalog="mde_dev",
        schema="test_schema"
    )
    return [TextContent(type="text", text=json.dumps(result.result.data_array[:50]))]


@app.tool()
async def nexus_agent_direct(agent_id: int, request: str) -> list[TextContent]:
    """Call a specific NEXUS agent by ID (bypasses supervisor routing)."""
    agent_prompt = f"""You are NEXUS Agent {agent_id}. Execute this request:
    {request}"""
    response = call_fmapi([
        {"role": "user", "content": agent_prompt}
    ])
    return [TextContent(type="text", text=response)]


if __name__ == "__main__":
    import mcp
    mcp.run(app)
```

**VS Code config (`.claude/settings.json`):**
```json
{
  "mcpServers": {
    "nexus": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/nexus_mcp_server.py"]
    }
  }
}
```

**Pros:** Full control, streaming capable, all NEXUS tools available, works offline from MCP perspective  
**Cons:** Requires local Python environment, SDK dependency  
**Effort:** ~3-4 hours

---

## Option E: Databricks AI Playground + VS Code Terminal (Zero Code)

**How it works:** Use the existing `CHAT_Interactive_Supervisor` notebook pattern but call it from VS Code terminal via the Databricks CLI. No custom server needed.

**Architecture:**
```
VS Code Terminal
  → databricks workspace execute-command (or REST API)
    → Existing CHAT_Interactive_Supervisor notebook
      → FMAPI (databricks-claude-sonnet-4-6)
        → Full NEXUS routing
```

**VS Code Task (`.vscode/tasks.json`):**
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "NEXUS: Route Request",
      "type": "shell",
      "command": "databricks",
      "args": [
        "jobs", "submit",
        "--json", "{\"run_name\":\"nexus_vscode\",\"tasks\":[{\"task_key\":\"sup\",\"notebook_task\":{\"notebook_path\":\"/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/1 - Production Agents/CHAT_Interactive_Supervisor\",\"base_parameters\":{\"request\":\"${input:nexusRequest}\",\"mode\":\"interactive\"}},\"existing_cluster_id\":\"<cluster-id>\"}]}",
        "--profile", "DEV"
      ],
      "problemMatcher": []
    }
  ],
  "inputs": [
    {
      "id": "nexusRequest",
      "type": "promptString",
      "description": "Enter your NEXUS request"
    }
  ]
}
```

**Pros:** Zero code, uses existing notebook infrastructure  
**Cons:** No streaming, cluster cold-start, clunky UX  
**Effort:** ~15 minutes

---

## Comparison Matrix

| Criterion | A: MCP+UC Functions | B: Databricks App | C: CLI Commands | D: Custom MCP | E: Tasks+CLI |
|-----------|:---:|:---:|:---:|:---:|:---:|
| Setup time | 2h | 4-6h | 30min | 3-4h | 15min |
| Streaming responses | ❌ | ✅ | ❌ | ✅ | ❌ |
| All 134 agents | ✅ | ✅ | ✅ | ✅ | ✅ |
| Notebook execution | ❌ | ✅ | ✅ | ✅ | ✅ |
| Zero infra to deploy | ❌ | ❌ | ✅ | ✅ (local) | ✅ |
| Works in Claude Code | ✅ | ✅ | ✅ | ✅ | ❌ (terminal) |
| Works in Cursor/Windsurf | ✅ | ✅ | ❌ | ✅ | ❌ |
| Cold-start latency | Low | Low | High (cluster) | Low | High (cluster) |
| Token limit concerns | 10min UC timeout | None | None | None | None |
| Maintenance | Low | Medium | Low | Low | Low |
| All LLM on Databricks | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Recommended Approach: Hybrid (C now → D next week)

**Phase 1 (Today):** Deploy **Option C** (Claude Code slash commands). Takes 30 minutes, works immediately with your existing Databricks CLI profile. Gives you `/nexus` and `/nexus-qlik` commands.

**Phase 2 (This week):** Build **Option D** (Custom MCP Server). The `nexus_mcp_server.py` gives full streaming, all tools exposed, and works across Claude Code, Cursor, and Windsurf. ~3 hours.

**Phase 3 (Optional):** If you need team-wide access, deploy **Option B** (Databricks App) as the shared gateway.

---

## Critical: Ensuring ALL Inference Stays on Databricks

Regardless of which option you choose, the key architectural guarantee is:

1. **Claude Code (local)** only handles the chat UI and tool orchestration
2. **All LLM inference** goes through `databricks-claude-sonnet-4-6` endpoint via FMAPI
3. **All data access** goes through Databricks APIs (Delta tables, Jobs, SQL)
4. **All agent logic** runs server-side on Databricks compute

The local Claude Code instance acts as a **thin client** — it calls MCP tools which call Databricks. It does NOT generate agent responses locally.

---

## Environment Prerequisites

```bash
# Already done (per user context):
# ✅ VS Code connected to Databricks DEV profile
# ✅ Claude Code extension installed
# ✅ Databricks CLI authenticated

# For Option D (Custom MCP Server):
pip install databricks-sdk mcp

# For Option A (UC MCP Proxy):
pip install uc-mcp-proxy
```
