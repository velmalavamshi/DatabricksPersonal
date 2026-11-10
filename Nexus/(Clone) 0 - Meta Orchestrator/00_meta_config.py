# Databricks notebook source
# DBTITLE 1,NEXUS Meta Orchestrator — Configuration
# ══════════════════════════════════════════════════════════════════════════════
# 00_meta_config
# NEXUS W0 Meta Orchestrator — Shared Configuration
# All W0 notebooks %run this to get workspace registry, table refs, LLM config
# ══════════════════════════════════════════════════════════════════════════════

import json
import uuid
import requests
from datetime import datetime, timezone

# ── Current User & Workspace ───────────────────────────────────────────────
USER_EMAIL = spark.sql("SELECT current_user()").collect()[0][0]
ROOT_PATH = f"/Workspace/Users/{USER_EMAIL}/5 - Personal Projects/5 - AI Multi Agents"

# ── Workspace Folder Registry ──────────────────────────────────────────────
WORKSPACE_REGISTRY = {
    "W0": {
        "name": "Meta Orchestrator",
        "path": f"{ROOT_PATH}/0 - Meta Orchestrator",
        "supervisor": "00_meta_supervisor",
        "purpose": "Routes requests across all workspaces, manages event mesh",
        "domains": ["routing", "orchestration", "cross-workspace", "meta", "governance", "monitoring", "audit", "circuit breaker", "version", "security"],
    },
    "W1": {
        "name": "Production Agents",
        "path": f"{ROOT_PATH}/1 - Production Agents",
        "supervisor": "00_supervisor_agent",
        "purpose": "Internal Databricks data operations, pipeline management, monitoring",
        "domains": ["jobs", "pipelines", "cost", "data quality", "deployment", "testing",
                    "architecture", "security", "documentation", "oracle", "salesforce",
                    "servicenow", "powerbi", "hcm", "ascp", "agile", "pbcs",
                    "consultation", "specialist", "extract", "triage", "failure", "briefing"],
    },
    "W2": {
        "name": "Value Discovery",
        "path": f"{ROOT_PATH}/2 - Value Discovery",
        "supervisor": "00_vd_supervisor",
        "purpose": "Client workspace scanning, AI use case scoring, assessment reports",
        "domains": ["assessment", "use cases", "client", "scanning", "maturity", "ROI"],
    },
    "W3": {
        "name": "Business Champions",
        "path": f"{ROOT_PATH}/3 - Business Champions",
        "supervisor": "00_bc_supervisor",
        "purpose": "Board-ready business cases, PowerPoint decks, champion coaching",
        "domains": ["business case", "board", "presentation", "champion", "executive"],
    },
    "W4": {
        "name": "Collective Intelligence",
        "path": f"{ROOT_PATH}/4 - Collective Intelligence",
        "supervisor": "00_ci_supervisor",
        "purpose": "Cross-client pattern learning, benchmarks, failure prediction",
        "domains": ["benchmark", "patterns", "prediction", "competitive", "pipeline", "trend", "forecast", "intelligence"],
    },
}

# ── LLM Configuration ──────────────────────────────────────────────────────
LLM_ENDPOINT = "databricks-claude-sonnet-4-6"
LLM_MAX_TOKENS = 2048
LLM_TEMPERATURE = 0.1  # Low temp for classification tasks

# ── NEXUS Delta Tables ─────────────────────────────────────────────────────
NEXUS_SCHEMA = "mde_dev.test_schema"
NEXUS_EVENTS = f"{NEXUS_SCHEMA}.nexus_agent_events"
NEXUS_REGISTRY = f"{NEXUS_SCHEMA}.nexus_agent_registry"
NEXUS_MEMORY = f"{NEXUS_SCHEMA}.agent_memory"  # Consolidated: shared_token_optimizer creates this
NEXUS_TRACE = f"{NEXUS_SCHEMA}.nexus_agent_trace_log"
NEXUS_CIRCUIT = f"{NEXUS_SCHEMA}.nexus_agent_circuit_breaker"

# ── Utility Functions ───────────────────────────────────────────────────────
def generate_run_id():
    """Generate a unique run ID for agent execution tracking."""
    return str(uuid.uuid4())

def call_llm(prompt, max_tokens=None, temperature=None):
    """Call Foundation Model API via OpenAI-compatible REST endpoint."""
    _workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
    _token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    url = f"https://{_workspace_url}/serving-endpoints/{LLM_ENDPOINT}/invocations"
    headers = {"Authorization": f"Bearer {_token}", "Content-Type": "application/json"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens or LLM_MAX_TOKENS,
        "temperature": temperature or LLM_TEMPERATURE,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def publish_event(source_agent, event_type, payload, target_agent=None, workspace="W0", priority="P3"):
    """Publish an event to the NEXUS event bus."""
    from pyspark.sql.types import StructType, StructField, StringType, TimestampType
    now = datetime.now(timezone.utc)
    event_data = [(
        str(uuid.uuid4()), event_type, source_agent, target_agent,
        workspace, json.dumps(payload), priority, "PUBLISHED",
        now, None, None, None, now, "NEXUS"
    )]
    schema = StructType([
        StructField("event_id", StringType(), False),
        StructField("event_type", StringType(), False),
        StructField("source_agent", StringType(), False),
        StructField("target_agent", StringType(), True),
        StructField("workspace", StringType(), False),
        StructField("payload", StringType(), False),
        StructField("priority", StringType(), False),
        StructField("status", StringType(), False),
        StructField("created_at", TimestampType(), False),
        StructField("consumed_at", TimestampType(), True),
        StructField("consumed_by", StringType(), True),
        StructField("run_id", StringType(), True),
        StructField("etl_load_datetime", TimestampType(), False),
        StructField("etl_source_system", StringType(), False),
    ])
    df = spark.createDataFrame(event_data, schema=schema)
    df.write.format("delta").mode("append").saveAsTable(NEXUS_EVENTS)
    return event_data[0][0]  # return event_id

def get_workspace_for_domain(domain_keywords):
    """Simple keyword matching to find the right workspace for a domain."""
    domain_lower = domain_keywords.lower()
    scores = {}
    for ws_id, ws_info in WORKSPACE_REGISTRY.items():
        score = sum(1 for d in ws_info['domains'] if d in domain_lower)
        if score > 0:
            scores[ws_id] = score
    if scores:
        return max(scores, key=scores.get)
    return "W1"  # default to Production Agents

print("✅ Meta config loaded")
print(f"   User: {USER_EMAIL}")
print(f"   Root: {ROOT_PATH}")
print(f"   LLM:  {LLM_ENDPOINT}")
print(f"   Workspaces: {', '.join(WORKSPACE_REGISTRY.keys())}")
# Shared memory + token budget utilities (single source of truth for all folders) loaded next

# COMMAND ----------

# DBTITLE 1,Load shared token optimizer
# MAGIC %run ../shared_token_optimizer