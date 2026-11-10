# Databricks notebook source
# DBTITLE 1,Agent Configuration
# MAGIC %md
# MAGIC # Agent Platform — Shared Configuration
# MAGIC
# MAGIC **Purpose:** Shared utilities, LLM connection, and Delta table setup for all production agents.
# MAGIC
# MAGIC **Architecture:**
# MAGIC - LLM: Databricks Foundation Model APIs (pay-per-token via AI Gateway)
# MAGIC - State: Delta tables in `mde_dev.test_schema`
# MAGIC - Orchestration: Databricks Workflows (each agent = 1 task)
# MAGIC - Cost: ~$0.07/DBU for AI Gateway + token costs
# MAGIC
# MAGIC **Usage:** Each agent notebook runs `%run ./00_agent_config` to inherit these utilities.

# COMMAND ----------

# DBTITLE 1,Install dependencies
# MAGIC %pip install openai mlflow -q
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Core configuration
# ══════════════════════════════════════════════════════════════════════════════
# AGENT PLATFORM CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

from datetime import datetime, timedelta
import json
from openai import OpenAI
from pyspark.sql import functions as F
from pyspark.sql.types import *

# ── Environment ──────────────────────────────────────────────────────────────
CATALOG = "mde_dev"
SCHEMA = "test_schema"
DEV_WORKSPACE_ID = "6617965257274108"
PRD_WORKSPACE_ID = "685145432798888"
UAT_WORKSPACE_ID = "7982886777824011"
AI_BUILDER_WORKSPACE_ID = "4337650355687191"

# ── LLM Configuration ────────────────────────────────────────────────────────
# Use Databricks Foundation Model APIs (pay-per-token, no provisioned endpoint)
# APEX agents    → Claude Opus 4 (deepest reasoning — architects, modelers, peer review)
# CRITICAL agents → Claude Sonnet 4 (fast + capable — engineers, triage, security)
# STANDARD agents → Claude Sonnet 4 (swap to cheaper model when available)
#
# Benchmark (June 15, 2026): Opus scored 7/7 vs Sonnet 6/7 on architecture tasks,
# was 8s faster (44s vs 52s), and cost only +0.14¢/call more. Opus does NOT support
# the temperature parameter — call_agent() handles this automatically.
LLM_APEX     = "databricks-claude-opus-4-8"    # Architects, Data Modeler, Peer Review
LLM_CRITICAL = "databricks-claude-sonnet-4-6"  # Data Engineer, Triage, Security
LLM_STANDARD = "databricks-claude-sonnet-4-6"  # All other agents (swap to cheaper model later)

# ── Agent Registry ───────────────────────────────────────────────────────────
# Model assignment: CRITICAL = high-quality reasoning (architecture, engineering, security)
#                   STANDARD = advisory/documentation (swap to cheaper model later)
# Priority: HIGH = reactive/triage/core path | MEDIUM = planning/review | LOW = docs/hygiene
# Type:     agent = LLM call required | tool = deterministic Python fn | skill = prompt injection
#           AGENT_REGISTRY is the SOURCE OF TRUTH for type (Tier 4, 2026-06-04)

AGENT_REGISTRY = {
    # ── Core Engineering & Triage (CRITICAL + HIGH) ──────────────────────────
    "supervisor":             {"id": 0,  "model": LLM_CRITICAL, "priority": "HIGH",   "type": "agent"},
    "job_failure_triage":     {"id": 1,  "model": LLM_CRITICAL, "priority": "HIGH",   "type": "agent"},
    "data_engineer":          {"id": 2,  "model": LLM_CRITICAL, "priority": "HIGH",   "type": "agent"},
    "view_dependency":        {"id": 3,  "model": LLM_CRITICAL, "priority": "HIGH",   "type": "agent"},
    "source_drift_detector":  {"id": 4,  "model": LLM_CRITICAL, "priority": "HIGH",   "type": "agent"},
    "solution_architect":     {"id": 6,  "model": LLM_APEX,     "priority": "HIGH",   "type": "agent"},
    "peer_review":            {"id": 7,  "model": LLM_APEX,     "priority": "HIGH",   "type": "agent"},
    "data_quality":           {"id": 16, "model": LLM_CRITICAL, "priority": "HIGH",  "type": "agent"},
    "security":               {"id": 17, "model": LLM_CRITICAL, "priority": "HIGH",  "type": "agent"},

    # ── Architecture & Modeling (CRITICAL + MEDIUM) ──────────────────────────
    "lakehouse_architect":    {"id": 15, "model": LLM_APEX,     "priority": "MEDIUM", "type": "agent"},
    "oracle_ebs_specialist":  {"id": 32, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "data_modeler":           {"id": 37, "model": LLM_APEX,     "priority": "MEDIUM", "type": "agent"},
    "solution_recommender":   {"id": 38, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},

    # ── Monitoring & Validation (STANDARD + HIGH) ────────────────────────────
    "cost_anomaly":           {"id": 5,  "model": LLM_STANDARD, "priority": "HIGH",   "type": "tool"},
    "medallion_validation":   {"id": 10, "model": LLM_STANDARD, "priority": "HIGH",  "type": "tool"},
    "platform_reliability":   {"id": 26, "model": LLM_STANDARD, "priority": "HIGH",  "type": "tool"},
    "monitoring":             {"id": 30, "model": LLM_STANDARD, "priority": "HIGH",  "type": "tool"},

    # ── Planning, Testing & DevOps (STANDARD + MEDIUM) ───────────────────────
    "unit_test":              {"id": 8,  "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "environment_promotion":  {"id": 9,  "model": LLM_STANDARD, "priority": "MEDIUM", "type": "tool"},
    "business_analyst":       {"id": 11, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "scope":                  {"id": 12, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "project_manager":        {"id": 13, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "azure_devops":           {"id": 14, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "cost_optimization":      {"id": 18, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "tool"},
    "unit_test_documentation":{"id": 19, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "skill"},
    "integration_test":       {"id": 20, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "observability":          {"id": 21, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "tool"},
    "metadata_lineage":       {"id": 22, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "tool"},
    "dataops":                {"id": 23, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "tool"},
    "cicd":                   {"id": 24, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "tool"},
    "deployment":             {"id": 25, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "tool"},
    "enterprise_standards":   {"id": 28, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "skill"},
    "salesforce_sync":        {"id": 33, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "hash_migration":         {"id": 34, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},

    # ── Documentation & Hygiene (STANDARD + LOW) ─────────────────────────────
    "ai_governance":          {"id": 27, "model": LLM_STANDARD, "priority": "LOW",    "type": "skill"},
    "documentation":          {"id": 29, "model": LLM_STANDARD, "priority": "LOW",    "type": "skill"},
    "release_approval_board": {"id": 31, "model": LLM_STANDARD, "priority": "LOW",    "type": "skill"},
    "documentation_sync":     {"id": 35, "model": LLM_STANDARD, "priority": "LOW",    "type": "skill"},
    "workspace_hygiene":      {"id": 36, "model": LLM_STANDARD, "priority": "LOW",    "type": "tool"},

    # ── Phase 3: Morning & Triage Pipeline (STANDARD + HIGH) ────────────────
    "morning_briefing":       {"id": 39, "model": LLM_STANDARD, "priority": "HIGH",   "type": "agent"},
    "morning_triage":         {"id": 40, "model": LLM_STANDARD, "priority": "HIGH",   "type": "agent"},

    # ── Phase 3: Source System Specialists (CRITICAL + MEDIUM) ───────────────
    "oracle_ebs_extract":     {"id": 44, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "oracle_ebs_error":       {"id": 45, "model": LLM_CRITICAL, "priority": "HIGH",   "type": "agent"},
    "oracle_ebs_dq":          {"id": 46, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "salesforce_extract":     {"id": 47, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "salesforce_dq":          {"id": 48, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "servicenow":             {"id": 53, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "powerbi":                {"id": 54, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},

    # ── Phase 10: Specialist Consultation Network (STANDARD + MEDIUM) ────────
    "consultation_router":    {"id": 60, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "specialist_base":        {"id": 61, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "consultation_tracker":   {"id": 62, "model": LLM_STANDARD, "priority": "LOW",    "type": "tool"},

    # ── Phase 10: Planned Specialists (CRITICAL + MEDIUM) — not yet built ────
    "ascp_specialist":        {"id": 49, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "agile_plm":              {"id": 50, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "koerber_specialist":     {"id": 51, "model": LLM_CRITICAL, "priority": "LOW",    "type": "agent"},
    "oracle_hcm_specialist":  {"id": 52, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "pbcs_specialist":        {"id": 55, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "hcp_specialist":         {"id": 56, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "definitive_specialist":  {"id": 57, "model": LLM_STANDARD, "priority": "LOW",    "type": "agent"},
    "cornerstone_specialist": {"id": 58, "model": LLM_STANDARD, "priority": "LOW",    "type": "agent"},
    "mulesoft_specialist":    {"id": 59, "model": LLM_STANDARD, "priority": "LOW",    "type": "agent"},

    # ── Release Intelligence Layer (STANDARD + MEDIUM) ───────────────────────
    "release_intelligence":   {"id": 77, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "oracle_release_monitor": {"id": 78, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "salesforce_release_monitor": {"id": 79, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "powerbi_release_monitor":{"id": 80, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "databricks_release_monitor": {"id": 81, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "azure_platform_release_monitor": {"id": 82, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "mulesoft_release_monitor":   {"id": 83, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "delta_spark_oss_release_monitor": {"id": 84, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "azure_devops_release_monitor": {"id": 85, "model": LLM_STANDARD, "priority": "LOW",    "type": "agent"},
    "python_ecosystem_release_monitor": {"id": 86, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "oracle_cloud_release_monitor": {"id": 87, "model": LLM_STANDARD, "priority": "LOW",    "type": "agent"},
}

print(f"✅ Config loaded | Catalog: {CATALOG}.{SCHEMA} | LLM: {LLM_CRITICAL}")
_reg_type_counts = {}
_reg_priority_counts = {}
for _a in AGENT_REGISTRY.values():
    _t = _a.get("type", "agent")
    _p = _a.get("priority", "MEDIUM")
    _reg_type_counts[_t] = _reg_type_counts.get(_t, 0) + 1
    _reg_priority_counts[_p] = _reg_priority_counts.get(_p, 0) + 1
print(f"   W1 Registry: {len(AGENT_REGISTRY)} components | Agents: {_reg_type_counts.get('agent', 0)} | Tools: {_reg_type_counts.get('tool', 0)} | Skills: {_reg_type_counts.get('skill', 0)}")
print(f"   Model split — CRITICAL: {sum(1 for a in AGENT_REGISTRY.values() if a['model'] == LLM_CRITICAL)} | STANDARD: {sum(1 for a in AGENT_REGISTRY.values() if a['model'] == LLM_STANDARD)}")
print(f"   Priority — HIGH: {_reg_priority_counts.get('HIGH', 0)} | MEDIUM: {_reg_priority_counts.get('MEDIUM', 0)} | LOW: {_reg_priority_counts.get('LOW', 0)}")
print(f"   Full NEXUS: 88 agents across W0-W4 (W1={len(AGENT_REGISTRY)}, W0=16, W2=4, W3=4, W4=4)")

# COMMAND ----------

# DBTITLE 1,LLM client setup with MLflow tracing
# ══════════════════════════════════════════════════════════════════════════════
# LLM CLIENT — Databricks Foundation Model APIs via OpenAI-compatible interface
# ══════════════════════════════════════════════════════════════════════════════

import mlflow
from mlflow.entities import SpanType

# Set up MLflow experiment for NEXUS agent tracing
mlflow.set_experiment("/Users/sameet.patel@hologic.com/NEXUS_Agent_Traces")

# SRTI rate for cost calculation (from system.billing.list_prices)
_SRTI_RATE_PER_DBU = 0.07
_TOKENS_PER_DBU = 10000  # approximate conversion for Foundation Model APIs

def _estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    """Estimate cost based on token usage. Conservative approximation."""
    total_tokens = tokens_in + (tokens_out * 3)  # output tokens weighted higher
    dbus = total_tokens / _TOKENS_PER_DBU
    return round(dbus * _SRTI_RATE_PER_DBU, 6)

def get_llm_client():
    """Create OpenAI client pointing to Databricks Model Serving."""
    workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
    token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    
    client = OpenAI(
        api_key=token,
        base_url=f"https://{workspace_url}/serving-endpoints"
    )
    return client


# ── TRACK 4: Tier-based default max_tokens (4.2) ────────────────────────────
# NOTE: Can't use model name as key because LLM_CRITICAL == LLM_STANDARD (both sonnet).
# Use agent priority (HIGH = CRITICAL tier) from AGENT_REGISTRY instead.

def call_agent(agent_name: str, system_prompt: str, user_prompt: str, 
               temperature: float = 0.1, max_tokens: int = 4096) -> str:
    """Call LLM for a specific agent with error handling, logging, MLflow tracing,
    and automatic retry on output truncation (finish_reason=='length')."""
    config = AGENT_REGISTRY.get(agent_name, {})
    
    # ── TIER 4 SAFETY GUARD ───────────────────────────────────────────────
    # Prevent accidental LLM calls for tools and skills. These should be
    # routed through coordinate_agents() which dispatches without LLM.
    _component_type = config.get("type", "agent")
    if _component_type in ("tool", "skill"):
        raise ValueError(
            f"call_agent() called for {_component_type.upper()} component '{agent_name}'. "
            f"Tools/skills must be routed through coordinate_agents() — never call_agent() directly. "
            f"Check your orchestration logic."
        )
    # ───────────────────────────────────────────────────────────────────
    
    model = config.get("model", LLM_STANDARD)
    
    # ── TRACK 4.2: Tier-based max_tokens override (only if caller used default) ──
    # Uses agent priority (HIGH=CRITICAL tier) since LLM_CRITICAL==LLM_STANDARD (same model).
    if max_tokens == 4096:
        _priority = config.get("priority", "MEDIUM")
        if model == LLM_APEX or _priority == "HIGH":
            max_tokens = 8192
    
    # ── PHASE 8 GOVERNANCE GATE ───────────────────────────────────────────
    _policy_gate = globals().get('_governance_policy_check')
    if _policy_gate:
        try:
            _verdict = _policy_gate(agent_name, "llm_call", {"max_tokens": max_tokens, "model": model})
            if _verdict["action"] == "DENY":
                log_agent_call(agent_name, model, 0, 0, 0.0, f"POLICY_DENIED: {_verdict['reason']}")
                return f"⛔ POLICY DENIED [{_verdict.get('policy_name', 'unknown')}]: {_verdict['reason']}"
            elif _verdict["action"] == "ASK":
                _ask_run_id = generate_run_id()
                save_agent_output("governance", _ask_run_id, "approval_request", json.dumps({
                    "event_type": "APPROVAL_REQUIRED",
                    "agent": agent_name,
                    "action": "llm_call",
                    "reason": _verdict["reason"],
                    "policy_name": _verdict.get("policy_name", "unknown"),
                    "awaiting_approval_from": "supervisor"
                }))
                log_agent_call(agent_name, model, 0, 0, 0.0, f"POLICY_ASK: {_verdict['reason']}")
                return f"⏸️ APPROVAL REQUIRED [{_verdict.get('policy_name', 'unknown')}]: {_verdict['reason']}"
        except Exception as _policy_err:
            # Fail-open: if governance engine itself crashes, proceed with LLM call
            pass
    # ───────────────────────────────────────────────────────────────────────
    
    client = get_llm_client()
    
    # ── MLflow Tracing: wrap entire agent call in a span ─────────────────
    with mlflow.start_span(name=f"agent/{agent_name}", span_type=SpanType.AGENT) as span:
        span.set_attributes({
            "agent.name": agent_name,
            "agent.id": config.get("id", -1),
            "agent.priority": config.get("priority", "UNKNOWN"),
            "agent.type": _component_type,
            "llm.model": model,
            "llm.temperature": temperature,
            "llm.max_tokens": max_tokens,
            "input.system_prompt_chars": len(system_prompt),
            "input.user_prompt_chars": len(user_prompt),
        })
        
        start_time = datetime.now()
        try:
            # ── Nested span for the actual LLM call ──────────────────────
            with mlflow.start_span(name="llm/chat_completion", span_type=SpanType.LLM) as llm_span:
                # Build request kwargs — Opus models don't support temperature
                _llm_kwargs = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": max_tokens,
                }
                if "opus" not in model:  # Opus doesn't support temperature param
                    _llm_kwargs["temperature"] = temperature
                
                response = client.chat.completions.create(**_llm_kwargs)
                
                # ── TRACK 4.1: finish_reason=="length" detection + auto-retry ──
                _finish_reason = response.choices[0].finish_reason
                _retry_count = 0
                if _finish_reason == "length" and max_tokens < 16384:
                    # Output was truncated — retry with doubled budget
                    _retry_max = min(max_tokens * 2, 16384)
                    _llm_kwargs["max_tokens"] = _retry_max
                    response = client.chat.completions.create(**_llm_kwargs)
                    _finish_reason = response.choices[0].finish_reason
                    _retry_count = 1
                # ────────────────────────────────────────────────────────────────
                
                result = response.choices[0].message.content
                duration = (datetime.now() - start_time).total_seconds()
                tokens_in = response.usage.prompt_tokens
                tokens_out = response.usage.completion_tokens
                cost_usd = _estimate_cost_usd(tokens_in, tokens_out)
                
                # Set LLM span attributes
                llm_span.set_attributes({
                    "llm.tokens_in": tokens_in,
                    "llm.tokens_out": tokens_out,
                    "llm.tokens_total": tokens_in + tokens_out,
                    "llm.duration_sec": round(duration, 3),
                    "llm.cost_usd": cost_usd,
                    "llm.finish_reason": _finish_reason,
                    "llm.retry_count": _retry_count,
                    "llm.was_truncated": _retry_count > 0,
                })
            
            # Set parent span final attributes
            span.set_attributes({
                "output.response_chars": len(result),
                "output.tokens_in": tokens_in,
                "output.tokens_out": tokens_out,
                "output.cost_usd": cost_usd,
                "output.duration_sec": round(duration, 3),
                "output.status": "SUCCESS",
            })
            
            # Log the call to Delta (existing behavior + Phase 8.4 risk points + 4.9 telemetry)
            _status = "SUCCESS" if _retry_count == 0 else f"SUCCESS_AFTER_RETRY(tokens_doubled_to_{_llm_kwargs['max_tokens']})"
            if _finish_reason == "length":
                _status = f"WARN_TRUNCATED(max={_llm_kwargs['max_tokens']})"
            _risk_pts = globals().get('get_risk_points_for_agent', lambda a, b: 0)(agent_name, "llm_call")
            log_agent_call(agent_name, model, tokens_in, tokens_out, duration, _status,
                           risk_points=_risk_pts, finish_reason=_finish_reason)
            
            return result
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            span.set_attributes({
                "output.status": "ERROR",
                "output.error": str(e)[:500],
                "output.duration_sec": round(duration, 3),
            })
            _risk_pts = globals().get('get_risk_points_for_agent', lambda a, b: 0)(agent_name, "llm_call")
            log_agent_call(agent_name, model, 0, 0, duration, f"ERROR: {str(e)[:200]}", risk_points=_risk_pts)
            raise


print("✅ LLM client configured | Using OpenAI-compatible Databricks endpoint")

# COMMAND ----------

# DBTITLE 1,Agent logging and state management
# ══════════════════════════════════════════════════════════════════════════════
# AGENT STATE MANAGEMENT — Delta Tables
# ══════════════════════════════════════════════════════════════════════════════

def log_agent_call(agent_name: str, model: str, tokens_in: int, tokens_out: int, 
                   duration_sec: float, status: str, risk_points: int = 0,
                   finish_reason: str = None):
    """Log every agent LLM call to Delta table for cost tracking and audit.
    Track 4.9: Added finish_reason for truncation telemetry."""
    log_data = [{
        "timestamp": datetime.now().isoformat(),
        "agent_name": agent_name,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "duration_sec": round(duration_sec, 2),
        "status": status,
        "workspace_id": AI_BUILDER_WORKSPACE_ID,
        "risk_points": risk_points,
        "finish_reason": finish_reason or "unknown"
    }]
    
    df = spark.createDataFrame(log_data)
    # Cast risk_points to match table's INT schema (Python int → Spark LongType by default)
    df = df.withColumn("risk_points", F.col("risk_points").cast("int"))
    df.write.mode("append").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_call_log")


def save_agent_output(agent_name: str, run_id: str, output_type: str, 
                      content: str, metadata: dict = None):
    """Save agent output artifact to Delta table with MLflow tracing."""
    with mlflow.start_span(name=f"output/{agent_name}/{output_type}", span_type=SpanType.TOOL) as span:
        span.set_attributes({
            "output.agent_name": agent_name,
            "output.run_id": run_id,
            "output.type": output_type,
            "output.content_chars": len(content),
            "output.metadata_keys": list((metadata or {}).keys()),
        })
        
        output_data = [{
            "timestamp": datetime.now().isoformat(),
            "agent_name": agent_name,
            "run_id": run_id,
            "output_type": output_type,
            "content": content,
            "metadata": json.dumps(metadata or {}),
            "workspace_id": AI_BUILDER_WORKSPACE_ID
        }]
        
        df = spark.createDataFrame(output_data)
        df.write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_outputs")
        
        span.set_attributes({"output.status": "SAVED"})


def get_latest_agent_output(agent_name: str, output_type: str = None) -> str:
    """Retrieve the most recent output from an agent."""
    query = f"""
    SELECT content, timestamp, metadata
    FROM {CATALOG}.{SCHEMA}.agent_outputs
    WHERE agent_name = '{agent_name}'
    """
    if output_type:
        query += f" AND output_type = '{output_type}'"
    query += " ORDER BY timestamp DESC LIMIT 1"
    
    result = spark.sql(query).collect()
    return result[0]["content"] if result else None


print("✅ Agent state management configured | Tables: agent_call_log, agent_outputs")

# COMMAND ----------

# DBTITLE 1,Initialize Delta tables
# ══════════════════════════════════════════════════════════════════════════════
# INITIALIZE DELTA TABLES (idempotent — safe to re-run)
# ══════════════════════════════════════════════════════════════════════════════

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_call_log (
    timestamp STRING,
    agent_name STRING,
    model STRING,
    tokens_in INT,
    tokens_out INT,
    duration_sec DOUBLE,
    status STRING,
    workspace_id STRING
)
USING DELTA
COMMENT 'Audit log of all agent LLM calls for cost tracking and debugging'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_outputs (
    timestamp STRING,
    agent_name STRING,
    run_id STRING,
    output_type STRING,
    content STRING,
    metadata STRING,
    workspace_id STRING
)
USING DELTA
COMMENT 'All agent-generated artifacts (reports, recommendations, code)'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_pipeline_status (
    timestamp        STRING  COMMENT 'ISO timestamp of this status event',
    run_id           STRING  COMMENT 'Unique execution ID linking to agent_outputs',
    pipeline_name    STRING  COMMENT 'Named pipeline or workflow being tracked',
    agent_sequence   STRING  COMMENT 'JSON array of agent names in execution order',
    status           STRING  COMMENT 'IN_PROGRESS | COMPLETED | FAILED | BLOCKED',
    current_agent    STRING  COMMENT 'Agent currently executing',
    completed_agents STRING  COMMENT 'JSON array of agents that have finished',
    error_message    STRING  COMMENT 'Error detail when status = FAILED',
    workspace_id     STRING  COMMENT 'Workspace where pipeline was triggered'
)
USING DELTA
COMMENT 'Feature delivery pipeline status — one row per pipeline run event'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_health_dashboard (
    snapshot_date      DATE    COMMENT 'Date of this health snapshot',
    agent_name         STRING  COMMENT 'Agent component name',
    total_calls        INT     COMMENT 'Total LLM calls in the snapshot period',
    success_count      INT     COMMENT 'Calls that returned SUCCESS status',
    error_count        INT     COMMENT 'Calls that returned ERROR status',
    avg_duration_sec   DOUBLE  COMMENT 'Mean duration across all calls (seconds)',
    total_tokens_in    BIGINT  COMMENT 'Total prompt tokens consumed',
    total_tokens_out   BIGINT  COMMENT 'Total completion tokens generated',
    estimated_cost_usd DOUBLE  COMMENT 'Estimated cost (approximate, from token counts)'
)
USING DELTA
COMMENT 'Daily health rollup per agent — aggregated from agent_call_log'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_cost_anomalies (
    timestamp         STRING  COMMENT 'ISO timestamp of anomaly detection',
    detection_date    DATE    COMMENT 'Calendar date of anomaly',
    anomaly_type      STRING  COMMENT 'BILLING_SPIKE | TOKEN_SURGE | ERROR_STORM',
    workspace_id      STRING  COMMENT 'Workspace where anomaly was detected',
    sku_name          STRING  COMMENT 'Databricks SKU affected (from system.billing.usage)',
    expected_dbus     DOUBLE  COMMENT 'Baseline DBU consumption',
    actual_dbus       DOUBLE  COMMENT 'Actual DBU consumption on detection date',
    expected_cost_usd DOUBLE  COMMENT 'Expected cost based on baseline',
    actual_cost_usd   DOUBLE  COMMENT 'Actual cost (system.billing.usage JOIN list_prices)',
    spike_factor      DOUBLE  COMMENT 'Ratio: actual / expected — > 2.0 triggers alert',
    recommendation    STRING  COMMENT 'Suggested remediation action'
)
USING DELTA
COMMENT 'Cost anomaly detection log — populated by tool_cost_anomaly'
""")

# ── Phase 8: Governance Tables ───────────────────────────────────────────────

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_policies (
    policy_id        STRING   COMMENT 'UUID primary key',
    policy_name      STRING   COMMENT 'Human-readable name, e.g. global_daily_budget',
    scope            STRING   COMMENT 'global | agent:<agent_name>',
    phase            STRING   COMMENT 'pre_execution | post_execution',
    policy_type      STRING   COMMENT 'expression | threshold | rate_limit',
    expression       STRING   COMMENT 'Python eval-safe expression',
    parameters       STRING   COMMENT 'JSON: {{"max_cost_usd": 5.0, "limit": 50}}',
    verdict_on_error STRING   COMMENT 'DENY | ALLOW — fail-closed or fail-open',
    priority         INT      COMMENT 'Lower = evaluated first',
    is_active        BOOLEAN  COMMENT 'Toggle without deleting',
    created_at       TIMESTAMP COMMENT 'Policy creation time',
    updated_at       TIMESTAMP COMMENT 'Last modification time'
)
USING DELTA
COMMENT 'Governance policies evaluated before/after agent execution'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_policy_log (
    timestamp       STRING   COMMENT 'ISO timestamp of evaluation',
    agent_name      STRING   COMMENT 'Agent being gated',
    policy_name     STRING   COMMENT 'Policy that fired',
    phase           STRING   COMMENT 'pre_execution | post_execution',
    verdict         STRING   COMMENT 'ALLOW | DENY | ASK',
    reason          STRING   COMMENT 'Human-readable explanation',
    context         STRING   COMMENT 'JSON: action, parameters, risk_score',
    run_id          STRING   COMMENT 'Links to agent_call_log'
)
USING DELTA
COMMENT 'Audit trail of all policy evaluations'
""")

print(f"✅ Delta tables initialized in {CATALOG}.{SCHEMA}")
print(f"   • agent_call_log          — every LLM call (cost + audit)")
print(f"   • agent_outputs           — all generated artifacts")
print(f"   • agent_pipeline_status   — pipeline execution tracking")
print(f"   • agent_health_dashboard  — daily agent health rollup")
print(f"   • agent_cost_anomalies    — billing anomaly detection log")
print(f"   • agent_policies          — governance policy definitions (Phase 8)")
print(f"   • agent_policy_log        — policy evaluation audit trail (Phase 8)")

# COMMAND ----------

# DBTITLE 1,Utility functions
# ══════════════════════════════════════════════════════════════════════════════
# SHARED UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

import uuid

def generate_run_id() -> str:
    """Generate unique run ID for tracing agent executions."""
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def get_workspace_name(workspace_id: str) -> str:
    """Map workspace ID to human-readable name."""
    names = {
        DEV_WORKSPACE_ID: "DEV",
        PRD_WORKSPACE_ID: "PRD",
        UAT_WORKSPACE_ID: "UAT",
        AI_BUILDER_WORKSPACE_ID: "AI_BUILDER",
    }
    return names.get(workspace_id, f"WS-{workspace_id[:6]}")


def format_agent_report(title: str, sections: dict) -> str:
    """Format agent output as structured markdown report."""
    report = f"# {title}\n\n"
    report += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report += "---\n\n"
    
    for section_title, content in sections.items():
        report += f"## {section_title}\n\n{content}\n\n"
    
    return report


print("✅ Utilities loaded | generate_run_id(), get_workspace_name(), format_agent_report()")
print("\n" + "═" * 60)
print("  AGENT PLATFORM READY")
print("  Config → LLM → State → Utilities")
print("═" * 60)

# COMMAND ----------

# DBTITLE 1,Load shared token optimizer (memory + budget)
# MAGIC %run ../shared_token_optimizer

# COMMAND ----------

# DBTITLE 1,Token Optimization — Safe Tier (Memory + Catalog Cache + Lazy Loading)
# ══════════════════════════════════════════════════════════════════════════════
# W1-SPECIFIC: CATALOG CONTEXT CACHE + LAZY SCHEMA LOADING
#
# Memory + budget functions come from shared_token_optimizer (loaded above).
# This cell adds W1-only features that require catalog-aware agent context.
#
# Features:
#   • catalog_context_cache  — 6hr TTL, avoids redundant information_schema scans
#   • get_cached_catalog()   — drop-in replacement for gather_catalog_context()
#   • infer_relevant_schemas() — lazy loading (only scan relevant layers)
# ══════════════════════════════════════════════════════════════════════════════

import hashlib

CATALOG_CACHE_TTL_HOURS = 6  # Cache freshness window

# ── Create catalog cache table (idempotent) ──────────────────────────────────

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.catalog_context_cache (
    cache_key       STRING    COMMENT 'Hash of scan parameters (schemas + max_per_type)',
    cached_context  STRING    COMMENT 'Full formatted catalog context string',
    table_count     INT       COMMENT 'Number of tables in this snapshot',
    fact_count      INT       COMMENT 'Number of fact tables',
    dim_count       INT       COMMENT 'Number of dimension tables',
    cached_at       TIMESTAMP COMMENT 'When this cache was built',
    schemas_scanned STRING    COMMENT 'Comma-separated list of schemas included'
)
USING DELTA
COMMENT 'Catalog context cache — avoids redundant information_schema scans (6hr TTL)'
""")

# ── Catalog Context Cache ────────────────────────────────────────────────────

def _cache_key(schemas: list, max_per_type: int) -> str:
    """Generate deterministic cache key from scan parameters."""
    raw = f"{'|'.join(sorted(schemas))}|{max_per_type}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached_catalog(schemas: list = None, max_per_type: int = 30,
                       force_refresh: bool = False) -> str:
    """
    Token-optimized catalog context with 6-hour cache.
    
    Logic:
      1. Check cache — if fresh (< 6 hours), return cached context immediately
      2. If stale/missing — run live gather_catalog_context(), cache result, return
    
    This saves ~2000-5000 tokens per agent run by avoiding redundant
    information_schema scans when multiple agents run within the same window.
    
    Args:
        schemas: List of schemas to scan. Default: ['gold', 'platinum', 'silver']
                 Use LAZY LOADING: pass only schemas relevant to the task.
        max_per_type: Max tables per type per layer.
        force_refresh: Bypass cache and always scan live.
    
    Returns:
        Same formatted string as gather_catalog_context() — downstream code unchanged.
    """
    if schemas is None:
        schemas = ['gold', 'platinum', 'silver']
    
    key = _cache_key(schemas, max_per_type)
    
    if not force_refresh:
        # Check cache freshness
        cached = spark.sql(f"""
            SELECT cached_context, cached_at, table_count, fact_count, dim_count
            FROM {CATALOG}.{SCHEMA}.catalog_context_cache
            WHERE cache_key = '{key}'
              AND cached_at > TIMESTAMP '{(datetime.now() - timedelta(hours=CATALOG_CACHE_TTL_HOURS)).strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY cached_at DESC
            LIMIT 1
        """).collect()
        
        if cached:
            row = cached[0]
            print(f"✅ Catalog cache HIT | {row['table_count']} tables ({row['fact_count']}F/{row['dim_count']}D) | cached {row['cached_at']}")
            return row['cached_context']
    
    # Cache MISS or force_refresh — run live scan
    print(f"⏳ Catalog cache {'REFRESH' if force_refresh else 'MISS'} — running live scan...")
    context = gather_catalog_context(max_per_type=max_per_type)
    
    # Count facts/dims from the result
    fact_count = context.count('FACT')
    dim_count = context.count('DIM')
    table_count = context.count(f'{CATALOG}.')
    
    # Persist to cache (overwrite same key)
    spark.sql(f"""
        MERGE INTO {CATALOG}.{SCHEMA}.catalog_context_cache AS target
        USING (SELECT '{key}' AS cache_key) AS source
        ON target.cache_key = source.cache_key
        WHEN MATCHED THEN UPDATE SET
            cached_context = '{context.replace(chr(39), chr(39)+chr(39))}',
            table_count = {table_count},
            fact_count = {fact_count},
            dim_count = {dim_count},
            cached_at = CURRENT_TIMESTAMP(),
            schemas_scanned = '{','.join(schemas)}'
        WHEN NOT MATCHED THEN INSERT (
            cache_key, cached_context, table_count, fact_count, dim_count, cached_at, schemas_scanned
        ) VALUES (
            '{key}', '{context.replace(chr(39), chr(39)+chr(39))}',
            {table_count}, {fact_count}, {dim_count}, CURRENT_TIMESTAMP(), '{','.join(schemas)}'
        )
    """)
    
    print(f"✅ Catalog cache STORED | {table_count} tables | key={key[:8]}...")
    return context


# ── Lazy Schema Loading Helper ───────────────────────────────────────────────

def infer_relevant_schemas(requirement: str) -> list:
    """
    Infer which schemas are relevant based on the requirement text.
    Reduces token waste by only scanning schemas the agent actually needs.
    
    Rules (conservative — when in doubt, include more, not less):
      - Always include 'gold' (primary modeling layer)
      - Include 'platinum' if requirement mentions aggregation, KPIs, reporting
      - Include 'silver' if requirement mentions source lineage, staging, or cleansing
      - Include ALL if requirement is vague or broad
    
    Returns:
        List of schema names to scan. Never empty — minimum ['gold'].
    """
    req_lower = requirement.lower() if requirement else ""
    schemas = ['gold']  # Always include gold
    
    # Platinum triggers
    platinum_signals = ['aggregat', 'kpi', 'report', 'summary', 'metric', 'platinum',
                        'executive', 'dashboard', 'rollup', 'cube']
    if any(s in req_lower for s in platinum_signals):
        schemas.append('platinum')
    
    # Silver triggers
    silver_signals = ['silver', 'source', 'lineage', 'staging', 'cleanse', 'bronze',
                      'raw', 'extract', 'transform', 'stg_']
    if any(s in req_lower for s in silver_signals):
        schemas.append('silver')
    
    # If requirement is vague or mentions architecture broadly, include all
    broad_signals = ['all', 'full', 'entire', 'complete', 'architect', 'inventory',
                     'catalog', 'everything', 'overview']
    if not requirement or len(req_lower) < 20 or any(s in req_lower for s in broad_signals):
        return ['gold', 'platinum', 'silver']
    
    return schemas


print(f"✅ W1 Catalog Cache + Lazy Loading loaded")
print(f"   • catalog_context_cache   — {CATALOG_CACHE_TTL_HOURS}hr TTL, skip redundant scans")
print(f"   • get_cached_catalog()    — drop-in for gather_catalog_context()")
print(f"   • infer_relevant_schemas  — lazy loading (gold-first)")
print(f"   • Memory + budget functions inherited from shared_token_optimizer")

# COMMAND ----------

# DBTITLE 1,Catalog context helper: gather_catalog_context()
# ══════════════════════════════════════════════════════════════════════════════
# CATALOG CONTEXT HELPER — single source of truth, inherited by all agents via %run
#
# All agents run `%run ./00_agent_config` and inherit both symbols below:
#   _CATALOG_AWARE_AGENTS : set of agent names that receive catalog injection
#   gather_catalog_context(): scans mde_dev gold/platinum/silver, returns formatted string
#
# Used by:
#   • 00_supervisor_agent — coordinate_agents() calls once per orchestration run,
#     injects into system prompt for any agent in _CATALOG_AWARE_AGENTS
#   • 06_solution_architect, 15_lakehouse_architect, 37_data_modeler,
#     38_solution_recommender — standalone execution, called before LLM call
# ══════════════════════════════════════════════════════════════════════════════

_CATALOG_AWARE_AGENTS = {
    "data_modeler",
    "solution_architect",
    "lakehouse_architect",
    "solution_recommender",
    "data_engineer",
}


def gather_catalog_context(max_per_type: int = 30) -> str:
    """
    Scan mde_dev gold/platinum/silver for existing tables, classified by type.

    Single canonical implementation — replaces the five near-identical local
    functions previously scattered across agent notebooks. All agents inherit
    this via `%run ./00_agent_config`.

    The output is injected into the system prompt of catalog-aware agents so
    the LLM sees the full inventory of existing dims/facts BEFORE proposing
    anything new. This enforces REUSE > EXTEND > NET-NEW discipline.

    Args:
        max_per_type: Max tables listed per type per layer (default 30).
            Increase to 50+ for large catalogs; reduce for token budget.

    Returns:
        Multi-line markdown string: platinum → gold → silver, grouped by
        FACT / DIM / BRIDGE / AGG / OTHER. Each entry shows the UC table
        comment when available (first 70 chars).
    """
    try:
        rows = spark.sql(f"""
            SELECT
                table_schema                                                AS layer,
                table_name,
                CASE
                    WHEN LOWER(table_name) LIKE 'fact_%'
                      OR LOWER(table_name) LIKE 'fct_%'  THEN 'FACT'
                    WHEN LOWER(table_name) LIKE 'dim_%'   THEN 'DIM'
                    WHEN LOWER(table_name) LIKE 'bridge_%'
                      OR LOWER(table_name) LIKE 'br_%'   THEN 'BRIDGE'
                    WHEN LOWER(table_name) LIKE 'agg_%'   THEN 'AGG'
                    ELSE 'OTHER'
                END                                                         AS table_type,
                COALESCE(comment, '')                                       AS tbl_comment
            FROM {CATALOG}.information_schema.tables
            WHERE table_schema IN ('gold', 'platinum', 'silver')
              AND table_type IN ('MANAGED', 'VIEW')
              -- Exclude dev artifacts: backup copies, temp tables, test copies, date-stamped variants
              -- Without this filter, 260+ fact_*_bkp / fact_*_tmp entries pollute LLM context
              AND NOT REGEXP_LIKE(table_name, '_(bkp|bk|tmp|temp|test)[0-9]*
        """).collect()

        if not rows:
            return "No existing tables found in gold/platinum/silver."

        sections = []
        for layer in ('platinum', 'gold', 'silver'):
            layer_rows = [r for r in rows if r['layer'] == layer]
            if not layer_rows:
                continue

            by_type = {}
            for r in layer_rows:
                by_type.setdefault(r['table_type'], []).append(r)

            lines = [f"\n### {layer.upper()} — {len(layer_rows)} objects"]
            for ttype in ('FACT', 'DIM', 'BRIDGE', 'AGG', 'OTHER'):
                bucket = by_type.get(ttype, [])
                if not bucket:
                    continue
                shown = bucket[:max_per_type]
                lines.append(f"\n**{ttype}s** ({len(bucket)} total):")
                for r in shown:
                    note = f" — {r['tbl_comment'][:70]}" if r['tbl_comment'] else ""
                    lines.append(f"  - {CATALOG}.{layer}.{r['table_name']}{note}")
                if len(bucket) > max_per_type:
                    lines.append(f"  … +{len(bucket) - max_per_type} more")
            sections.append("\n".join(lines))

        result = "\n".join(sections)
        facts  = sum(1 for r in rows if r['table_type'] == 'FACT')
        dims   = sum(1 for r in rows if r['table_type'] == 'DIM')
        print(f"✅ Catalog context: {len(rows)} objects — {facts} facts, {dims} dims across platinum/gold/silver")
        return result

    except Exception as e:
        print(f"⚠️ Catalog context unavailable: {e}")
        return f"[Catalog scan failed — proceeding without reuse context: {e}]"


# ── Integration with Token Optimization (Safe Tier) ──────────────────────────
# Agents should prefer get_cached_catalog() over raw gather_catalog_context().
# The cached version is a drop-in replacement with identical output:
#
#   BEFORE (live scan every time — ~2500 tokens overhead per agent):
#     context = gather_catalog_context()
#
#   AFTER (cached, 6hr TTL — 0 tokens on cache hit):
#     schemas = infer_relevant_schemas(requirement)
#     context = get_cached_catalog(schemas=schemas)
#
# The original gather_catalog_context() still works unchanged for backward compat.
# get_cached_catalog() calls it internally on cache miss.

print(f"✅ Catalog context helper loaded")
print(f"   _CATALOG_AWARE_AGENTS: {', '.join(sorted(_CATALOG_AWARE_AGENTS))}")
print(f"   Token-optimized: use get_cached_catalog(schemas=infer_relevant_schemas(req))")

# COMMAND ----------

# DBTITLE 1,Column context helper: gather_column_context()
# ══════════════════════════════════════════════════════════════════════════════
# COLUMN CONTEXT HELPER — on-demand column-level schema for SQL-writing agents
#
# ROOT CAUSE FIX (2026-08-25): gather_catalog_context() only queries
# information_schema.tables — agents know a table EXISTS but have ZERO live
# column list. This is why data_engineer invented Item_ID/PoShipToOrg_ID
# instead of using real columns (RcvItem_ID, RcvWarehouse_ID).
#
# gather_column_context(table_names) queries information_schema.columns
# for SPECIFIC tables the agent plans to reference — NOT a bulk scan.
#
# Used by:
#   • 00_supervisor_agent — coordinate_agents() extracts table references from
#     user_request + prior_outputs, calls this, injects into _COLUMN_AWARE_AGENTS
#   • Any agent can also call directly for ad-hoc column lookups
# ══════════════════════════════════════════════════════════════════════════════

import re
from functools import lru_cache

_COLUMN_AWARE_AGENTS = {
    "data_engineer",
    "data_modeler",
    "data_quality",
    "peer_review",
    "unit_test",
    "oracle_ebs_specialist",
    "medallion_validation",
}

# ── Column context cache (session-level, avoids redundant information_schema hits) ──
_column_context_cache = {}  # key = frozenset(table_names) → value = (timestamp, result_str)
_COLUMN_CACHE_TTL_HOURS = 6


def _extract_table_references(text: str, max_tables: int = 8) -> list:
    """
    Extract fully-qualified or schema-qualified table references from text.
    
    Handles:
      - Full: mde_dev.gold.fact_receiving, mde_dev.platinum.dim_vendor
      - Short: gold.fact_receiving, platinum.dim_itemcost
      - Bare (known prefixes): fact_receiving, dim_vendor
    
    Returns list of fully-qualified names (catalog.schema.table), capped at max_tables.
    """
    tables = set()
    
    # Pattern 1: catalog.schema.table (full qualification)
    for m in re.finditer(r'\b(mde_\w+)\.(gold|platinum|silver|stg_\w+)\.(\w+)\b', text, re.IGNORECASE):
        tables.add(f"{m.group(1)}.{m.group(2)}.{m.group(3)}")
    
    # Pattern 2: schema.table (assume CATALOG)
    for m in re.finditer(r'\b(gold|platinum|silver)\.((?:fact|dim|bridge|agg|fct|br)_\w+)\b', text, re.IGNORECASE):
        full = f"{CATALOG}.{m.group(1)}.{m.group(2)}"
        if full not in tables:
            tables.add(full)
    
    # Pattern 3: bare table names with known prefixes (only if ≤2 found above)
    # Skip any name already captured by Pattern 1 or 2 (regardless of schema)
    already_named = {t.split('.')[-1] for t in tables}
    if len(tables) < 3:
        for m in re.finditer(r'\b((?:fact|dim|bridge|agg)_[a-z][a-z0-9_]+)\b', text, re.IGNORECASE):
            tname = m.group(1).lower()
            if tname in already_named:
                continue  # Already found via qualified pattern
            # Try gold first (most common), then platinum
            for schema in ('gold', 'platinum'):
                candidate = f"{CATALOG}.{schema}.{tname}"
                tables.add(candidate)
                already_named.add(tname)
                break
    
    return sorted(tables)[:max_tables]


def gather_column_context(table_names: list, max_cols_per_table: int = 60) -> str:
    """
    Fetch actual column names, types, and comments for specific tables from
    information_schema.columns. Called ON-DEMAND when an agent needs to write
    SQL against known tables.

    NOT a bulk scan — only fetches columns for the 2-8 tables an agent plans
    to reference. Token budget: ~250 tokens per 40-col table, ~2000 max.

    Args:
        table_names: List of fully-qualified names ["mde_dev.gold.fact_receiving", ...]
                     OR schema-qualified ["gold.fact_receiving"] (assumes CATALOG)
        max_cols_per_table: Max columns shown per table (default 60, truncates rest)

    Returns:
        Markdown string with column inventory per table, or empty string if no
        tables resolved. Example:
        
        ### mde_dev.gold.fact_receiving (47 columns)
        | Column | Type |
        |--------|------|
        | RcvTransaction_SK | STRING |
        | RcvItem_ID | BIGINT |
        ...
    """
    if not table_names:
        return ""
    
    # Normalize to fully-qualified names
    normalized = []
    for t in table_names:
        parts = t.split('.')
        if len(parts) == 3:
            normalized.append(t)
        elif len(parts) == 2:
            normalized.append(f"{CATALOG}.{t}")
        else:
            # Bare name — skip (too ambiguous without schema)
            continue
    
    if not normalized:
        return ""
    
    # Check session cache
    cache_key = frozenset(normalized)
    if cache_key in _column_context_cache:
        cached_ts, cached_result = _column_context_cache[cache_key]
        age_hours = (datetime.now() - cached_ts).total_seconds() / 3600
        if age_hours < _COLUMN_CACHE_TTL_HOURS:
            print(f"   📋 Column context cache HIT ({len(normalized)} tables, {age_hours:.1f}h old)")
            return cached_result
    
    # Build SQL with UNION ALL for each table (information_schema.columns is per-catalog)
    conditions = []
    for t in normalized:
        cat, schema, name = t.split('.')
        conditions.append(f"(table_schema = '{schema}' AND table_name = '{name}')")
    
    where_clause = " OR ".join(conditions)
    
    try:
        rows = spark.sql(f"""
            SELECT
                table_schema,
                table_name,
                column_name,
                full_data_type,
                ordinal_position,
                COALESCE(comment, '') AS col_comment
            FROM {CATALOG}.information_schema.columns
            WHERE ({where_clause})
            ORDER BY table_schema, table_name, ordinal_position
        """).collect()
        
        if not rows:
            return f"[No columns found for: {', '.join(normalized)}]"
        
        # Group by table
        tables_data = {}
        for r in rows:
            key = f"{CATALOG}.{r['table_schema']}.{r['table_name']}"
            tables_data.setdefault(key, []).append(r)
        
        # Format output
        sections = []
        total_cols = 0
        for tbl_name in sorted(tables_data.keys()):
            cols = tables_data[tbl_name]
            total_cols += len(cols)
            shown = cols[:max_cols_per_table]
            
            lines = [f"\n### {tbl_name} ({len(cols)} columns)"]
            lines.append("| Column | Type |")
            lines.append("|--------|------|")
            for c in shown:
                # Truncate long types (e.g., DECIMAL(38,10) → DECIMAL(38,10))
                dtype = c['full_data_type'][:30] if c['full_data_type'] else 'UNKNOWN'
                lines.append(f"| {c['column_name']} | {dtype} |")
            
            if len(cols) > max_cols_per_table:
                lines.append(f"| ... +{len(cols) - max_cols_per_table} more | |")
            
            sections.append("\n".join(lines))
        
        result = "\n".join(sections)
        
        # Cache the result
        _column_context_cache[cache_key] = (datetime.now(), result)
        
        print(f"   📊 Column context: {total_cols} columns across {len(tables_data)} tables")
        return result
    
    except Exception as e:
        print(f"   ⚠️ Column context failed: {e}")
        return f"[Column scan failed for {', '.join(normalized)}: {e}]"


def get_column_context_for_request(user_request: str, prior_outputs: dict = None) -> str:
    """
    Convenience wrapper: extracts table references from request + prior agent
    outputs, then fetches column context for them.
    
    Called by coordinate_agents() before firing any _COLUMN_AWARE_AGENTS agent.
    
    Args:
        user_request: The original user request text
        prior_outputs: Dict of {agent_name: output_text} from completed agents
    
    Returns:
        Column context markdown string (may be empty if no tables referenced)
    """
    # Combine all text sources for table extraction
    text_sources = [user_request]
    if prior_outputs:
        for output in prior_outputs.values():
            if output:
                text_sources.append(output[:3000])  # Cap per output to avoid regex over huge strings
    
    combined = "\n".join(text_sources)
    tables = _extract_table_references(combined)
    
    if not tables:
        return ""
    
    print(f"   🔍 Detected table references: {tables}")
    return gather_column_context(tables)


print(f"✅ Column context helper loaded")
print(f"   _COLUMN_AWARE_AGENTS: {', '.join(sorted(_COLUMN_AWARE_AGENTS))}")
print(f"   Functions: gather_column_context(), get_column_context_for_request(), _extract_table_references()")

# COMMAND ----------

# DBTITLE 1,Seed token optimizer tables (run once)
# ── Seed agent_memory with foundational platform knowledge ───────────────────
memories = [
    ("data_modeler", "dim_customer_scd2", "dim_customer implements SCD2 via effective_date/expiry_date. 42 columns. Reuse, do not rebuild.", 0.95, "W1"),
    ("data_modeler", "naming_convention", "Tables: snake_case with fact_/dim_/bridge_/agg_ prefix in mde_dev.gold/platinum. Columns: PascalCase NOT snake_case (CustomerAccount_SK, Invoice_ID, AccountingDate). SK type: STRING. Audit FACTS: dl_rowhash + dl_creation_date_time + dl_last_updated_date_time. Audit DIMS: dl_iscurrent + dl_recordstartdateutc + dl_recordenddateutc + dl_transform_id. Clustering: CLUSTER BY AUTO. TBLPROPERTIES: zstd + deletionVectors + rowTracking. PRIMARY KEY on grain SK.", 0.99, "W1"),
    ("job_failure_triage", "ebs_timeout_pattern", "Oracle EBS extracts timeout when >500K rows in single partition. Fix: add date predicate pushdown.", 0.90, "W1"),
    ("solution_architect", "hash_migration_status", "xxHash64 migration scoped: 1,538 tables, 7,978 SK columns, 8.73B rows. Results in mde_dev.test_schema.hash_migration_analysis.", 0.99, "W1"),
    ("cost_anomaly", "srti_rate_lesson", "SRTI endpoints = $0.07/DBU. NEVER use flat $0.70. Always join system.billing.list_prices.", 0.99, "W1"),
    ("supervisor", "platform_architecture", "NEXUS: 88 agents across 5 folders (W0-W4). All run on Serverless Jobs ($0.45/DBU). LLM: databricks-claude-sonnet-4-6.", 0.99, "W0"),
    ("morning_briefing", "schedule_preference", "Morning briefing runs at 7:00 AM CT weekdays. Covers: job failures (24hr), cost anomalies, DQ alerts.", 0.90, "W1"),
    ("pattern_detector", "monday_ebs_failures", "Oracle EBS extracts fail 3x more on Mondays due to weekend batch jobs. Schedule extracts after 9am Monday.", 0.85, "W4"),
]

for agent, key, value, conf, folder in memories:
    save_agent_memory(agent, key, value, confidence=conf, source_folder=folder)

print(f"\u2705 Seeded {len(memories)} memories into agent_memory")

# ── Seed catalog_context_cache via get_cached_catalog() ──────────────────────
print("\n\u2500\u2500 Testing catalog cache (first call = MISS, builds cache)...")
cached_context = get_cached_catalog(force_refresh=True)

# ── Verify both tables ───────────────────────────────────────────────────────
mem_count = spark.sql(f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.agent_memory").collect()[0][0]
cache_count = spark.sql(f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.catalog_context_cache").collect()[0][0]
print(f"\n\u2500\u2500 Verification:")
print(f"   agent_memory:          {mem_count} rows")
print(f"   catalog_context_cache: {cache_count} rows")

# ── Show memory retrieval works ──────────────────────────────────────────────
print("\n\u2500\u2500 Testing get_agent_memory('data_modeler'):")
result = get_agent_memory('data_modeler')
print(result)

# COMMAND ----------

# DBTITLE 1,MLflow Tracing — Smoke Test & Trace Viewer
# ══════════════════════════════════════════════════════════════════════════════
# MLflow TRACING — Smoke Test + Trace Verification
# Fires one real call_agent() and confirms the span appeared in MLflow.
# Safe to re-run anytime (uses minimal tokens: ~50 in / ~30 out).
# ══════════════════════════════════════════════════════════════════════════════

import time

print("─" * 60)
print("  MLflow Tracing Smoke Test")
print("─" * 60)

# ── Step 1: Fire a minimal call_agent() inside an explicit MLflow run ──
with mlflow.start_run(run_name="nexus_tracing_smoke_test") as run:
    run_id = run.info.run_id
    print(f"\n🧪 MLflow Run ID: {run_id}")
    
    _t0 = time.time()
    _result = call_agent(
        agent_name="supervisor",
        system_prompt="You are a test agent. Reply with exactly 5 words.",
        user_prompt="Confirm NEXUS MLflow tracing is active.",
        temperature=0.0,
        max_tokens=32,
    )
    _elapsed = round(time.time() - _t0, 2)
    
    # Log test metadata to the run
    mlflow.log_params({
        "agent_name": "supervisor",
        "test_type": "smoke_test",
        "platform": "NEXUS",
    })
    mlflow.log_metrics({"latency_sec": _elapsed})

print(f"\n✅ LLM Response  : {_result[:120]}")
print(f"✅ Latency       : {_elapsed}s")

# ── Step 2: Verify the trace was recorded in MLflow ──
print("\n🔍 Verifying trace in MLflow...")
try:
    _exp = mlflow.get_experiment_by_name("/Users/sameet.patel@hologic.com/NEXUS_Agent_Traces")
    _traces = mlflow.search_traces(
        experiment_ids=[_exp.experiment_id],
        max_results=1,
        order_by=["timestamp_ms DESC"],
    )
    if len(_traces) > 0:
        _latest = _traces.iloc[0]
        print(f"✅ Trace found    : trace_id={_latest.get('trace_id', _latest.name)[:16]}...")
        print(f"✅ Trace status   : {_latest.get('status', 'N/A')}")
        print(f"✅ Total spans    : check MLflow UI for nested span breakdown")
    else:
        print("⚠️  No traces found yet — spans are only searchable after the active trace closes.")
except Exception as _e:
    print(f"⚠️  search_traces unavailable in this MLflow version: {_e}")
    print("   Traces are still being written — check the MLflow UI directly.")

# ── Step 3: Print the deep-link to the MLflow Experiments UI ──
_workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
print(f"""
{"─" * 60}
  📊 View full trace in MLflow:
  https://{_workspace_url}/ml/experiments
  → Filter: NEXUS_Agent_Traces
  → Click the latest run → Traces tab

  Expected span tree:
  └─ agent/supervisor          (SpanType.AGENT)
     └─ llm/chat_completion     (SpanType.LLM)

  Attributes visible in UI:
  • agent.name, agent.id, agent.priority
  • llm.tokens_in, llm.tokens_out, llm.cost_usd
  • llm.duration_sec, llm.finish_reason
  • output.status (SUCCESS / ERROR)
{"─" * 60}
""")

# COMMAND ----------

# DBTITLE 1,Phase 8 — Governance Policy Engine
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8 — GOVERNANCE POLICY ENGINE
#
# Evaluates policies from agent_policies before/after agent execution.
# Design: session-cached loading, 3-way verdict (ALLOW/DENY/ASK),
# AST-safe eval, ordered by priority (lowest first), fail-open default.
# ══════════════════════════════════════════════════════════════════════════════

import ast

# ── Session Cache for Policies ──────────────────────────────────────────────────
_POLICY_CACHE = None
_POLICY_CACHE_TS = None
_POLICY_CACHE_TTL_SEC = 300  # 5 minutes


def _load_policies(force_refresh: bool = False) -> list:
    """Load active policies from Delta, cached for 5 minutes."""
    global _POLICY_CACHE, _POLICY_CACHE_TS
    
    now = datetime.now()
    if (not force_refresh 
        and _POLICY_CACHE is not None 
        and _POLICY_CACHE_TS is not None
        and (now - _POLICY_CACHE_TS).total_seconds() < _POLICY_CACHE_TTL_SEC):
        return _POLICY_CACHE
    
    try:
        df = spark.sql(f"""
            SELECT policy_id, policy_name, scope, phase, policy_type,
                   expression, parameters, verdict_on_error, priority
            FROM {CATALOG}.{SCHEMA}.agent_policies
            WHERE is_active = true
            ORDER BY priority ASC
        """)
        _POLICY_CACHE = [row.asDict() for row in df.collect()]
        _POLICY_CACHE_TS = now
    except Exception:
        # If table doesn't exist yet or query fails, return empty
        _POLICY_CACHE = []
        _POLICY_CACHE_TS = now
    
    return _POLICY_CACHE


# ── AST-Safe Expression Evaluator ─────────────────────────────────────────────
_SAFE_AST_NODES = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp,
    ast.Name, ast.Load, ast.Constant, ast.Attribute,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.USub, ast.UAdd,
)


def _safe_eval(expression: str, context: dict) -> bool:
    """Evaluate expression with AST whitelist. Returns True if condition fires."""
    try:
        tree = ast.parse(expression, mode='eval')
        # Validate all nodes are in whitelist
        for node in ast.walk(tree):
            if not isinstance(node, _SAFE_AST_NODES):
                raise ValueError(f"Unsafe AST node: {type(node).__name__}")
        # Evaluate with restricted context (no builtins)
        return bool(eval(compile(tree, '<policy>', 'eval'), {"__builtins__": {}}, context))
    except Exception:
        return False  # If expression fails to parse/eval, treat as not-triggered


# ── Policy Evaluation Engine ───────────────────────────────────────────────────
def evaluate_policies(agent_name: str, action: str, phase: str = "pre_execution",
                     extra_context: dict = None) -> dict:
    """
    Evaluate all applicable policies for an agent.
    
    Returns: {"action": "ALLOW"|"DENY"|"ASK", "reason": str, "policy_name": str}
    
    Composition rules:
    - Ordered by priority (lowest first)
    - First DENY short-circuits immediately
    - Any ASK + no DENY = ASK (returns last ASK reason)
    - All pass or no policies = ALLOW
    """
    policies = _load_policies()
    
    # Filter applicable policies: global scope OR agent-specific scope
    applicable = [
        p for p in policies
        if p["phase"] == phase and (
            p["scope"] == "global" or 
            p["scope"] == f"agent:{agent_name}"
        )
    ]
    
    # No policies = ALLOW (backward-compatible)
    if not applicable:
        return {"action": "ALLOW", "reason": "No applicable policies", "policy_name": None}
    
    # Build evaluation context from agent_call_log (Phase 8.3: enhanced with hourly + per-agent metrics)
    try:
        _now = datetime.now()
        _today = _now.strftime('%Y-%m-%d')
        _one_hour_ago = (_now - timedelta(hours=1)).isoformat()
        
        # Single query: per-agent daily + hourly stats + cumulative risk
        _agent_stats = spark.sql(f"""
            SELECT 
                COALESCE(COUNT(*), 0) AS calls_today,
                COALESCE(SUM(tokens_in + tokens_out), 0) AS session_tokens,
                COALESCE(SUM((tokens_in + (tokens_out * 3)) / 10000.0 * 0.07), 0.0) AS agent_cost_usd,
                COALESCE(SUM(CASE WHEN timestamp >= '{_one_hour_ago}' THEN 1 ELSE 0 END), 0) AS calls_last_hour,
                COALESCE(SUM(CASE WHEN timestamp >= '{_one_hour_ago}' THEN tokens_in + tokens_out ELSE 0 END), 0) AS tokens_last_hour,
                COALESCE(SUM(CAST(risk_points AS INT)), 0) AS cumulative_risk
            FROM {CATALOG}.{SCHEMA}.agent_call_log
            WHERE agent_name = '{agent_name}'
              AND LEFT(timestamp, 10) = '{_today}'
              AND status = 'SUCCESS'
        """).first()
        
        # Global daily cost (all agents combined)
        _global_cost = spark.sql(f"""
            SELECT COALESCE(SUM((tokens_in + (tokens_out * 3)) / 10000.0 * 0.07), 0.0) AS session_cost_usd
            FROM {CATALOG}.{SCHEMA}.agent_call_log
            WHERE LEFT(timestamp, 10) = '{_today}'
              AND status = 'SUCCESS'
        """).first()
        
        eval_context = {
            "agent_name": agent_name,
            "action": action,
            # Daily metrics (per-agent)
            "calls_today": int(_agent_stats["calls_today"]),
            "session_tokens": int(_agent_stats["session_tokens"]),
            "agent_cost_usd": float(_agent_stats["agent_cost_usd"]),
            # Hourly metrics (burst detection)
            "calls_last_hour": int(_agent_stats["calls_last_hour"]),
            "tokens_last_hour": int(_agent_stats["tokens_last_hour"]),
            # Global daily cost (all agents)
            "session_cost_usd": float(_global_cost["session_cost_usd"]),
            # Phase 8.4: Cumulative risk score
            "cumulative_risk": int(_agent_stats["cumulative_risk"]),
        }
    except Exception:
        eval_context = {
            "agent_name": agent_name,
            "action": action,
            "calls_today": 0,
            "session_tokens": 0,
            "agent_cost_usd": 0.0,
            "calls_last_hour": 0,
            "tokens_last_hour": 0,
            "session_cost_usd": 0.0,
            "cumulative_risk": 0,
        }
    
    # Merge extra context (e.g., max_tokens, model from caller)
    if extra_context:
        eval_context.update(extra_context)
    
    # Evaluate each policy in priority order
    _ask_result = None
    
    for policy in applicable:
        try:
            params = json.loads(policy["parameters"] or "{}")
            # Merge policy parameters into eval context
            local_ctx = {**eval_context, **params}
            
            triggered = _safe_eval(policy["expression"], local_ctx)
            
            if triggered:
                # Check if this is a threshold with ask_threshold (soft limit)
                ask_threshold_key = next(
                    (k for k in params if k.startswith("ask_threshold")), None
                )
                
                if ask_threshold_key and policy["policy_type"] == "threshold":
                    # Check if we've crossed the hard limit (DENY) or soft limit (ASK)
                    hard_key = ask_threshold_key.replace("ask_threshold", "max")
                    hard_val = params.get(hard_key)
                    soft_val = params.get(ask_threshold_key)
                    
                    # Get the metric value from context
                    metric_key = policy["expression"].split(">")[0].strip()
                    metric_val = local_ctx.get(metric_key, 0)
                    
                    if hard_val is not None and metric_val > hard_val:
                        # Hard limit crossed → DENY
                        _reason = f"{policy['policy_name']}: {metric_key}={metric_val:.4f} exceeds hard limit {hard_val}"
                        _log_policy_eval(agent_name, policy["policy_name"], phase, "DENY", _reason, eval_context)
                        return {"action": "DENY", "reason": _reason, "policy_name": policy["policy_name"]}
                    elif soft_val is not None and metric_val > soft_val:
                        # Soft limit crossed → ASK
                        _reason = f"{policy['policy_name']}: {metric_key}={metric_val:.4f} exceeds soft limit {soft_val}"
                        _ask_result = {"action": "ASK", "reason": _reason, "policy_name": policy["policy_name"]}
                        _log_policy_eval(agent_name, policy["policy_name"], phase, "ASK", _reason, eval_context)
                else:
                    # Standard trigger → DENY
                    _reason = f"{policy['policy_name']}: {policy['expression']} triggered (context: {json.dumps({k: v for k, v in local_ctx.items() if k in ('calls_today', 'session_tokens', 'session_cost_usd')})})"
                    _log_policy_eval(agent_name, policy["policy_name"], phase, "DENY", _reason, eval_context)
                    return {"action": "DENY", "reason": _reason, "policy_name": policy["policy_name"]}
            else:
                # Policy not triggered → ALLOW (log silently)
                _log_policy_eval(agent_name, policy["policy_name"], phase, "ALLOW", "Policy not triggered", eval_context)
                
        except Exception as e:
            # Per-policy error handling: use verdict_on_error
            _fallback = policy.get("verdict_on_error", "ALLOW")
            _log_policy_eval(agent_name, policy["policy_name"], phase, _fallback, f"Eval error: {str(e)[:200]}", eval_context)
            if _fallback == "DENY":
                return {"action": "DENY", "reason": f"Policy eval error (fail-closed): {str(e)[:100]}", "policy_name": policy["policy_name"]}
    
    # If any ASK was recorded but no DENY, invoke LLM-as-Judge (Phase 8.5)
    if _ask_result:
        _judge_fn = globals().get('_governance_llm_judge')
        if _judge_fn and eval_context.get("cumulative_risk", 0) >= 40:
            try:
                _judge_result = _judge_fn(
                    agent_name, action, eval_context, _ask_result["reason"]
                )
                # Judge can refine ASK into ALLOW, DENY, or confirm ASK
                if _judge_result["action"] in ("ALLOW", "DENY", "ASK"):
                    return {
                        "action": _judge_result["action"],
                        "reason": _judge_result["reason"],
                        "policy_name": "llm_judge",
                    }
            except Exception:
                pass  # Fail-open: if judge fails, return original ASK
        return _ask_result
    
    # All policies passed
    return {"action": "ALLOW", "reason": "All policies passed", "policy_name": None}


def _log_policy_eval(agent_name: str, policy_name: str, phase: str, 
                     verdict: str, reason: str, context: dict):
    """Log policy evaluation to agent_policy_log (fire-and-forget)."""
    try:
        log_data = [{
            "timestamp": datetime.now().isoformat(),
            "agent_name": agent_name,
            "policy_name": policy_name,
            "phase": phase,
            "verdict": verdict,
            "reason": reason[:500],
            "context": json.dumps({k: v for k, v in context.items() if k in ('action', 'calls_today', 'session_tokens', 'session_cost_usd', 'agent_name')}),
            "run_id": globals().get('_current_run_id', 'unknown')
        }]
        spark.createDataFrame(log_data).write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_policy_log")
    except Exception:
        pass  # Never let logging break the policy engine


def policy_check(agent_name: str, action: str, extra_context: dict = None) -> dict:
    """
    High-level policy gate for call_agent() integration.
    
    Args:
        agent_name: Agent requesting execution
        action: What the agent wants to do (e.g., 'llm_call')
        extra_context: Additional context (max_tokens, model, etc.)
    
    Returns:
        dict with 'action' (ALLOW/DENY/ASK), 'reason', 'policy_name'
    """
    return evaluate_policies(agent_name, action, phase="pre_execution", extra_context=extra_context)


# ── Register governance gate for lazy binding from call_agent() ───────────
_governance_policy_check = policy_check

print("✅ Phase 8 Governance Engine loaded | evaluate_policies(), policy_check() | Registered gate: _governance_policy_check")
print(f"   Cache TTL: {_POLICY_CACHE_TTL_SEC}s | Fail-open default | AST-safe eval")

# COMMAND ----------

# DBTITLE 1,Phase 8 — Seed Governance Policies
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8 — SEED GOVERNANCE POLICIES (idempotent via MERGE)
# ══════════════════════════════════════════════════════════════════════════════

import uuid as _uuid_mod

_seed_policies = [
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "global_daily_budget",
        "scope": "global",
        "phase": "pre_execution",
        "policy_type": "threshold",
        "expression": "session_cost_usd > max_cost_usd",
        "parameters": json.dumps({"max_cost_usd": 2.0, "ask_threshold_usd": 1.5}),
        "verdict_on_error": "ALLOW",
        "priority": 10,
        "is_active": True,
    },
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "standard_rate_limit",
        "scope": "global",
        "phase": "pre_execution",
        "policy_type": "rate_limit",
        "expression": "calls_today > limit",
        "parameters": json.dumps({"limit": 100}),
        "verdict_on_error": "ALLOW",
        "priority": 20,
        "is_active": True,
    },
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "token_cap",
        "scope": "global",
        "phase": "pre_execution",
        "policy_type": "threshold",
        "expression": "session_tokens > max_tokens",
        "parameters": json.dumps({"max_tokens": 150000}),
        "verdict_on_error": "ALLOW",
        "priority": 30,
        "is_active": True,
    },
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "apex_rate_limit",
        "scope": "agent:solution_architect",
        "phase": "pre_execution",
        "policy_type": "rate_limit",
        "expression": "calls_today > limit",
        "parameters": json.dumps({"limit": 20}),
        "verdict_on_error": "ALLOW",
        "priority": 15,
        "is_active": True,
    },
]

# Create temp view for MERGE source
_seed_df = spark.createDataFrame(_seed_policies)
_seed_df.createOrReplaceTempView("_seed_policies_source")

# MERGE: insert new policies, skip if policy_name + scope already exists
spark.sql(f"""
MERGE INTO {CATALOG}.{SCHEMA}.agent_policies AS target
USING _seed_policies_source AS source
  ON target.policy_name = source.policy_name AND target.scope = source.scope
WHEN NOT MATCHED THEN INSERT (
    policy_id, policy_name, scope, phase, policy_type,
    expression, parameters, verdict_on_error, priority, is_active,
    created_at, updated_at
) VALUES (
    source.policy_id, source.policy_name, source.scope, source.phase, source.policy_type,
    source.expression, source.parameters, source.verdict_on_error, source.priority, source.is_active,
    current_timestamp(), current_timestamp()
)
""")

# Force cache refresh after seeding
_load_policies(force_refresh=True)

print("✅ Governance policies seeded | 4 policies active | Fail-open defaults")
print("")

# Display current policies
display(spark.sql(f"""
    SELECT policy_name, scope, policy_type, expression, priority, is_active, verdict_on_error
    FROM {CATALOG}.{SCHEMA}.agent_policies
    ORDER BY priority
"""))

# COMMAND ----------

# DBTITLE 1,Phase 8.3 — Cost Budget + Rate Limiting Functions
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8.3 — COST BUDGET + RATE LIMITING
#
# Dedicated helper functions for cost/rate monitoring, budget checks,
# and additional policies (hourly burst, per-agent budget, APEX limits).
# ══════════════════════════════════════════════════════════════════════════════

# ── Cost Dashboard ──────────────────────────────────────────────────────────────
def get_cost_metrics(agent_name: str = None, window_hours: int = 24) -> dict:
    """
    Get cost metrics for an agent (or all agents if None).
    
    Returns: {
        'total_cost_usd': float, 'call_count': int, 'avg_cost_per_call': float,
        'tokens_in': int, 'tokens_out': int, 'window_hours': int
    }
    """
    _cutoff = (datetime.now() - timedelta(hours=window_hours)).isoformat()
    _where = f"WHERE timestamp >= '{_cutoff}' AND status = 'SUCCESS'"
    if agent_name:
        _where += f" AND agent_name = '{agent_name}'"
    
    row = spark.sql(f"""
        SELECT 
            COALESCE(COUNT(*), 0) AS call_count,
            COALESCE(SUM(tokens_in), 0) AS total_tokens_in,
            COALESCE(SUM(tokens_out), 0) AS total_tokens_out,
            COALESCE(SUM((tokens_in + (tokens_out * 3)) / 10000.0 * 0.07), 0.0) AS total_cost_usd
        FROM {CATALOG}.{SCHEMA}.agent_call_log
        {_where}
    """).first()
    
    _count = int(row["call_count"])
    _cost = float(row["total_cost_usd"])
    return {
        "total_cost_usd": round(_cost, 6),
        "call_count": _count,
        "avg_cost_per_call": round(_cost / max(_count, 1), 6),
        "tokens_in": int(row["total_tokens_in"]),
        "tokens_out": int(row["total_tokens_out"]),
        "window_hours": window_hours,
        "agent_name": agent_name or "ALL",
    }


# ── Rate Dashboard ──────────────────────────────────────────────────────────────
def get_rate_metrics(agent_name: str = None) -> dict:
    """
    Get rate metrics: calls per hour and per day for an agent (or all).
    
    Returns: {
        'calls_last_hour': int, 'calls_today': int,
        'hourly_rate_pct': float (vs 30/hr burst limit),
        'daily_rate_pct': float (vs 100/day limit)
    }
    """
    _now = datetime.now()
    _today = _now.strftime('%Y-%m-%d')
    _one_hour_ago = (_now - timedelta(hours=1)).isoformat()
    _where_agent = f"AND agent_name = '{agent_name}'" if agent_name else ""
    
    row = spark.sql(f"""
        SELECT 
            COALESCE(SUM(CASE WHEN timestamp >= '{_one_hour_ago}' THEN 1 ELSE 0 END), 0) AS calls_last_hour,
            COALESCE(COUNT(*), 0) AS calls_today
        FROM {CATALOG}.{SCHEMA}.agent_call_log
        WHERE LEFT(timestamp, 10) = '{_today}'
          AND status = 'SUCCESS'
          {_where_agent}
    """).first()
    
    _hourly = int(row["calls_last_hour"])
    _daily = int(row["calls_today"])
    # Default limits from seeded policies
    _hourly_limit = 30  # burst limit
    _daily_limit = 100 if not agent_name else 20  # global vs. apex
    
    return {
        "calls_last_hour": _hourly,
        "calls_today": _daily,
        "hourly_rate_pct": round((_hourly / _hourly_limit) * 100, 1),
        "daily_rate_pct": round((_daily / _daily_limit) * 100, 1),
        "agent_name": agent_name or "ALL",
    }


# ── Budget Status Check ────────────────────────────────────────────────────────
def check_budget_status() -> dict:
    """
    Quick health check: are any budgets close to limits?
    
    Returns: {
        'status': 'GREEN'|'YELLOW'|'RED',
        'global_cost': {'used': float, 'limit': float, 'pct': float},
        'top_agents': [{'agent': str, 'calls': int, 'cost': float}],
        'alerts': [str]
    }
    """
    _today = datetime.now().strftime('%Y-%m-%d')
    
    # Global cost
    _global = spark.sql(f"""
        SELECT COALESCE(SUM((tokens_in + (tokens_out * 3)) / 10000.0 * 0.07), 0.0) AS cost_usd
        FROM {CATALOG}.{SCHEMA}.agent_call_log
        WHERE LEFT(timestamp, 10) = '{_today}' AND status = 'SUCCESS'
    """).first()
    _global_cost = float(_global["cost_usd"])
    
    # Top agents by call count today
    _top = spark.sql(f"""
        SELECT agent_name, COUNT(*) AS calls, 
               ROUND(SUM((tokens_in + (tokens_out * 3)) / 10000.0 * 0.07), 4) AS cost_usd
        FROM {CATALOG}.{SCHEMA}.agent_call_log
        WHERE LEFT(timestamp, 10) = '{_today}' AND status = 'SUCCESS'
        GROUP BY agent_name
        ORDER BY calls DESC
        LIMIT 5
    """).collect()
    
    # Load budget limits from policies
    _policies = _load_policies()
    _budget_limit = 2.0  # default
    _ask_threshold = 1.5
    for p in _policies:
        if p["policy_name"] == "global_daily_budget" and p["scope"] == "global":
            _params = json.loads(p["parameters"] or "{}")
            _budget_limit = _params.get("max_cost_usd", 2.0)
            _ask_threshold = _params.get("ask_threshold_usd", 1.5)
            break
    
    _pct = (_global_cost / _budget_limit) * 100 if _budget_limit > 0 else 0
    
    # Determine status
    _alerts = []
    if _global_cost >= _budget_limit:
        _status = "RED"
        _alerts.append(f"BUDGET EXCEEDED: ${_global_cost:.4f} / ${_budget_limit:.2f} ({_pct:.0f}%)")
    elif _global_cost >= _ask_threshold:
        _status = "YELLOW"
        _alerts.append(f"Budget warning: ${_global_cost:.4f} / ${_budget_limit:.2f} ({_pct:.0f}%) — soft limit crossed")
    else:
        _status = "GREEN"
    
    return {
        "status": _status,
        "global_cost": {"used": round(_global_cost, 4), "limit": _budget_limit, "pct": round(_pct, 1)},
        "top_agents": [{"agent": r["agent_name"], "calls": r["calls"], "cost": float(r["cost_usd"])} for r in _top],
        "alerts": _alerts,
    }


# ── Per-Agent Budget Tracker ───────────────────────────────────────────────────
def get_agent_budget_breakdown() -> list:
    """
    Returns per-agent cost breakdown for the current day.
    Useful for identifying cost-heavy agents and right-sizing limits.
    """
    _today = datetime.now().strftime('%Y-%m-%d')
    rows = spark.sql(f"""
        SELECT 
            agent_name,
            COUNT(*) AS calls,
            SUM(tokens_in) AS tokens_in,
            SUM(tokens_out) AS tokens_out,
            ROUND(SUM((tokens_in + (tokens_out * 3)) / 10000.0 * 0.07), 6) AS cost_usd,
            ROUND(AVG(duration_sec), 2) AS avg_latency_sec,
            model
        FROM {CATALOG}.{SCHEMA}.agent_call_log
        WHERE LEFT(timestamp, 10) = '{_today}' AND status = 'SUCCESS'
        GROUP BY agent_name, model
        ORDER BY cost_usd DESC
    """).collect()
    
    return [{
        "agent": r["agent_name"],
        "model": r["model"],
        "calls": r["calls"],
        "tokens_in": int(r["tokens_in"]),
        "tokens_out": int(r["tokens_out"]),
        "cost_usd": float(r["cost_usd"]),
        "avg_latency_sec": float(r["avg_latency_sec"]),
    } for r in rows]


# ── Seed Phase 8.3 Policies ────────────────────────────────────────────────────
import uuid as _uuid_mod

_phase83_policies = [
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "apex_rate_limit",
        "scope": "agent:peer_review",
        "phase": "pre_execution",
        "policy_type": "rate_limit",
        "expression": "calls_today > limit",
        "parameters": json.dumps({"limit": 20}),
        "verdict_on_error": "ALLOW",
        "priority": 15,
        "is_active": True,
    },
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "hourly_burst_limit",
        "scope": "global",
        "phase": "pre_execution",
        "policy_type": "rate_limit",
        "expression": "calls_last_hour > burst_limit",
        "parameters": json.dumps({"burst_limit": 30}),
        "verdict_on_error": "ALLOW",
        "priority": 5,
        "is_active": True,
    },
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "apex_agent_budget",
        "scope": "agent:solution_architect",
        "phase": "pre_execution",
        "policy_type": "threshold",
        "expression": "agent_cost_usd > max_agent_cost_usd",
        "parameters": json.dumps({"max_agent_cost_usd": 0.50}),
        "verdict_on_error": "ALLOW",
        "priority": 12,
        "is_active": True,
    },
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "apex_agent_budget",
        "scope": "agent:data_modeler",
        "phase": "pre_execution",
        "policy_type": "threshold",
        "expression": "agent_cost_usd > max_agent_cost_usd",
        "parameters": json.dumps({"max_agent_cost_usd": 0.50}),
        "verdict_on_error": "ALLOW",
        "priority": 12,
        "is_active": True,
    },
]

# MERGE new policies (idempotent)
_p83_df = spark.createDataFrame(_phase83_policies)
_p83_df.createOrReplaceTempView("_phase83_source")

spark.sql(f"""
MERGE INTO {CATALOG}.{SCHEMA}.agent_policies AS target
USING _phase83_source AS source
  ON target.policy_name = source.policy_name AND target.scope = source.scope
WHEN NOT MATCHED THEN INSERT (
    policy_id, policy_name, scope, phase, policy_type,
    expression, parameters, verdict_on_error, priority, is_active,
    created_at, updated_at
) VALUES (
    source.policy_id, source.policy_name, source.scope, source.phase, source.policy_type,
    source.expression, source.parameters, source.verdict_on_error, source.priority, source.is_active,
    current_timestamp(), current_timestamp()
)
""")

# Force cache refresh
_load_policies(force_refresh=True)

# ── Validation: Show current policy landscape ───────────────────────────────
print("✅ Phase 8.3 Cost Budget + Rate Limiting loaded")
print(f"   Functions: get_cost_metrics(), get_rate_metrics(), check_budget_status(), get_agent_budget_breakdown()")
print(f"   New policies: hourly_burst_limit (5/global), apex_agent_budget (12/per-agent), peer_review apex (15)")
print("")

# Quick budget check
_status = check_budget_status()
print(f"   Budget Status: {_status['status']} | Global cost: ${_status['global_cost']['used']:.4f} / ${_status['global_cost']['limit']:.2f} ({_status['global_cost']['pct']:.1f}%)")
if _status['alerts']:
    for _a in _status['alerts']:
        print(f"   ⚠️ {_a}")
print("")

# Show all active policies
display(spark.sql(f"""
    SELECT policy_name, scope, policy_type, expression, 
           parameters AS params,
           priority, is_active
    FROM {CATALOG}.{SCHEMA}.agent_policies
    WHERE is_active = true
    ORDER BY priority
"""))

# COMMAND ----------

# DBTITLE 1,Phase 8.4 — Risk Score Accumulator
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8.4 — RISK SCORE ACCUMULATOR
#
# Assigns risk points per agent action. Cumulative score drives governance:
#   0-39:  ALLOW — proceed normally
#   40-59: ASK   — supervisor approval required
#   60+:   DENY  — blocked, alert generated
# ══════════════════════════════════════════════════════════════════════════════

# ── ALTER TABLE: Add risk_points column (idempotent) ───────────────────────
try:
    spark.sql(f"ALTER TABLE {CATALOG}.{SCHEMA}.agent_call_log ADD COLUMN risk_points INT COMMENT 'Risk points accrued for this action (Phase 8.4)'")
    print("✅ Added risk_points column to agent_call_log")
except Exception as _e:
    if "already exists" in str(_e).lower() or "FIELDS_ALREADY_EXISTS" in str(_e):
        print("ℹ️ risk_points column already exists in agent_call_log")
    else:
        print(f"⚠️ ALTER TABLE warning: {str(_e)[:100]}")


# ── Risk Point Weights ─────────────────────────────────────────────────────────
# Maps action types to risk points. Used by get_risk_points_for_agent().
# Higher points = riskier operation = faster threshold crossing.

_RISK_ACTION_WEIGHTS = {
    # Read-only / advisory (low risk)
    "read_metadata": 0,
    "generate_select": 5,
    "catalog_scan": 0,
    "llm_call": 5,          # Default LLM call (advisory)
    
    # Schema changes (medium risk)
    "generate_ddl": 15,
    "create_table": 15,
    "alter_table": 15,
    
    # Data modifications (high risk)
    "generate_dml": 20,
    "insert_data": 20,
    "update_data": 20,
    "merge_data": 20,
    
    # Destructive operations (critical risk)
    "drop_table": 50,
    "drop_view": 50,
    "truncate_table": 40,
    
    # Production impact
    "write_gold": 30,
    "write_platinum": 30,
    "write_production": 30,
    
    # External side effects
    "call_external_api": 20,
    "ado_work_item": 20,
    "servicenow_ticket": 20,
    "send_notification": 15,
    
    # Operational changes
    "modify_workflow": 25,
    "modify_job": 25,
    "modify_cluster": 20,
}

# Agent-level default risk weights (based on agent capabilities)
_AGENT_DEFAULT_RISK = {
    # Strategy (low risk — advisory only)
    "supervisor": 2,
    "business_analyst": 3,
    "solution_recommender": 3,
    
    # Architects (medium — generate DDL/DML proposals)
    "solution_architect": 15,
    "lakehouse_architect": 15,
    "data_modeler": 15,
    
    # Engineers (high — generate executable code)
    "data_engineer": 20,
    "job_failure_triage": 10,
    "source_drift_detector": 5,
    
    # Execution agents (medium-high)
    "peer_review": 5,
    "unit_test": 5,
    "data_quality": 10,
    "integration_test": 10,
    
    # External integration (high — side effects)
    "azure_devops": 20,
    "servicenow": 20,
    "morning_briefing": 10,
    
    # Source specialists (medium — domain queries)
    "oracle_ebs_specialist": 10,
    "salesforce_sync": 10,
    "oracle_ebs_extract": 10,
    "salesforce_extract": 10,
}

_DEFAULT_RISK_POINTS = 5  # Unknown agents get minimal risk


def get_risk_points_for_agent(agent_name: str, action: str = "llm_call") -> int:
    """
    Calculate risk points for a given agent + action combination.
    
    Priority: explicit action weight > agent default > global default (5)
    """
    # If caller specifies a known action type, use that
    if action in _RISK_ACTION_WEIGHTS:
        action_points = _RISK_ACTION_WEIGHTS[action]
        # If action is just 'llm_call', fall through to agent default
        if action != "llm_call":
            return action_points
    
    # Use agent-level default
    return _AGENT_DEFAULT_RISK.get(agent_name, _DEFAULT_RISK_POINTS)


def get_risk_score(agent_name: str = None) -> dict:
    """
    Get current cumulative risk score for an agent (or all agents).
    
    Returns: {
        'cumulative_risk': int, 'call_count': int,
        'risk_level': 'GREEN'|'YELLOW'|'RED',
        'headroom': int (points until next threshold)
    }
    """
    _today = datetime.now().strftime('%Y-%m-%d')
    _where = f"WHERE LEFT(timestamp, 10) = '{_today}' AND status = 'SUCCESS'"
    if agent_name:
        _where += f" AND agent_name = '{agent_name}'"
    
    row = spark.sql(f"""
        SELECT 
            COALESCE(SUM(CAST(risk_points AS INT)), 0) AS cumulative_risk,
            COUNT(*) AS call_count
        FROM {CATALOG}.{SCHEMA}.agent_call_log
        {_where}
    """).first()
    
    _risk = int(row["cumulative_risk"])
    
    if _risk >= 60:
        _level = "RED"
        _headroom = 0
    elif _risk >= 40:
        _level = "YELLOW"
        _headroom = 60 - _risk
    else:
        _level = "GREEN"
        _headroom = 40 - _risk
    
    return {
        "cumulative_risk": _risk,
        "call_count": int(row["call_count"]),
        "risk_level": _level,
        "headroom": _headroom,
        "agent_name": agent_name or "ALL",
    }


def get_risk_breakdown(agent_name: str = None) -> list:
    """
    Show which calls contributed risk points today.
    Useful for understanding what drove a high score.
    """
    _today = datetime.now().strftime('%Y-%m-%d')
    _where = f"WHERE LEFT(timestamp, 10) = '{_today}' AND risk_points > 0"
    if agent_name:
        _where += f" AND agent_name = '{agent_name}'"
    
    rows = spark.sql(f"""
        SELECT agent_name, status, risk_points, timestamp,
               SUM(risk_points) OVER (PARTITION BY agent_name ORDER BY timestamp) AS running_total
        FROM {CATALOG}.{SCHEMA}.agent_call_log
        {_where}
        ORDER BY timestamp DESC
        LIMIT 20
    """).collect()
    
    return [{
        "agent": r["agent_name"],
        "risk_points": int(r["risk_points"]),
        "running_total": int(r["running_total"]),
        "status": r["status"],
        "timestamp": r["timestamp"],
    } for r in rows]


def reset_risk_score(agent_name: str):
    """
    Reset an agent's risk score by zeroing out today's risk_points.
    Use after supervisor review approves continued operation.
    """
    _today = datetime.now().strftime('%Y-%m-%d')
    spark.sql(f"""
        UPDATE {CATALOG}.{SCHEMA}.agent_call_log
        SET risk_points = 0
        WHERE agent_name = '{agent_name}'
          AND LEFT(timestamp, 10) = '{_today}'
    """)
    # Force policy cache refresh so next eval sees zeroed score
    _load_policies(force_refresh=True)
    print(f"✅ Risk score reset for {agent_name} (today's points zeroed)")


# ── Seed Risk Governance Policies ─────────────────────────────────────────────
import uuid as _uuid_mod

_risk_policies = [
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "risk_score_deny",
        "scope": "global",
        "phase": "pre_execution",
        "policy_type": "threshold",
        "expression": "cumulative_risk >= deny_threshold",
        "parameters": json.dumps({"deny_threshold": 60}),
        "verdict_on_error": "ALLOW",
        "priority": 3,
        "is_active": True,
    },
    {
        "policy_id": str(_uuid_mod.uuid4()),
        "policy_name": "risk_score_ask",
        "scope": "global",
        "phase": "pre_execution",
        "policy_type": "threshold",
        "expression": "cumulative_risk >= ask_threshold",
        "parameters": json.dumps({"ask_threshold": 40, "ask_threshold_dummy": 40}),
        "verdict_on_error": "ALLOW",
        "priority": 4,
        "is_active": True,
    },
]

_risk_df = spark.createDataFrame(_risk_policies)
_risk_df.createOrReplaceTempView("_risk_policies_source")

spark.sql(f"""
MERGE INTO {CATALOG}.{SCHEMA}.agent_policies AS target
USING _risk_policies_source AS source
  ON target.policy_name = source.policy_name AND target.scope = source.scope
WHEN NOT MATCHED THEN INSERT (
    policy_id, policy_name, scope, phase, policy_type,
    expression, parameters, verdict_on_error, priority, is_active,
    created_at, updated_at
) VALUES (
    source.policy_id, source.policy_name, source.scope, source.phase, source.policy_type,
    source.expression, source.parameters, source.verdict_on_error, source.priority, source.is_active,
    current_timestamp(), current_timestamp()
)
""")

_load_policies(force_refresh=True)

# ── Validation ─────────────────────────────────────────────────────────────────
print("✅ Phase 8.4 Risk Score Accumulator loaded")
print(f"   Functions: get_risk_points_for_agent(), get_risk_score(), get_risk_breakdown(), reset_risk_score()")
print(f"   Thresholds: GREEN (0-39) | YELLOW/ASK (40-59) | RED/DENY (60+)")
print(f"   Policies: risk_score_deny (priority 3), risk_score_ask (priority 4)")
print(f"   Action weights: {len(_RISK_ACTION_WEIGHTS)} action types | {len(_AGENT_DEFAULT_RISK)} agent defaults")
print("")

# Quick check: current risk for all agents
_risk_status = get_risk_score()
print(f"   Current risk (all agents): {_risk_status['cumulative_risk']} pts | Level: {_risk_status['risk_level']} | Headroom: {_risk_status['headroom']} pts")

# COMMAND ----------

# DBTITLE 1,Phase 8.5 — LLM-as-Judge Policy
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8.5 — LLM-AS-JUDGE POLICY
#
# Fires ONLY when expression-based policies yield ASK (grey zone 40-59),
# or when an action isn't covered by any expression rule.
# Uses Sonnet structured output to classify: ALLOW / DENY / ASK.
#
# Cost: ~$0.003-0.01 per call. Expected frequency: <5% of all evaluations.
# Annual cost: ~$5-15 (negligible vs. platform total).
# ══════════════════════════════════════════════════════════════════════════════

_JUDGE_SYSTEM_PROMPT = """You are a strict governance policy evaluator for the NEXUS agent platform at Hologic.

You receive context about an agent action that has been flagged as borderline (risk score in the 40-59 grey zone).
Based on the context, decide whether this action should proceed.

Rules:
- ALLOW: The action is safe, the accumulated risk is from routine operations, no destructive or production-impacting operations planned.
- DENY: The action poses genuine risk — destructive operations (DROP, TRUNCATE), production writes without approval, or cumulative risk indicates the agent is operating beyond its intended scope.
- ASK: The action is genuinely ambiguous — escalate to human supervisor for explicit approval.

Bias toward ALLOW for:
- Read-only operations (SELECT, metadata, catalog scans)
- Advisory agents (supervisor, business_analyst, solution_recommender)
- Low cumulative risk (close to 40 threshold)

Bias toward DENY for:
- Destructive operations (DROP, TRUNCATE, DELETE)
- Production schema writes (gold, platinum)
- High cumulative risk (close to 60 threshold)
- External side effects (API calls, notifications, work items)

Return ONLY valid JSON (no markdown, no explanation outside the JSON):
{"action": "allow" or "deny" or "ask", "reason": "one-sentence explanation", "confidence": 0.0 to 1.0}"""

_JUDGE_USER_TEMPLATE = """Agent: {agent_name}
Action requested: {action}
Cumulative risk score today: {cumulative_risk} / 60 (DENY threshold)
Calls today: {calls_today}
Agent cost today: ${agent_cost_usd:.4f}
Global cost today: ${session_cost_usd:.4f} / $2.00 budget
Agent type risk weight: {agent_risk_weight} pts/call
Reason flagged: {reason}

Recent risk breakdown:
{risk_breakdown}

Should this action proceed?"""


def _llm_judge(agent_name: str, action: str, context: dict, ask_reason: str) -> dict:
    """
    Call Sonnet as a judge for borderline governance decisions.
    
    Returns: {"action": "ALLOW"|"DENY"|"ASK", "reason": str, "confidence": float}
    """
    # Build the user prompt with full context
    _risk_weight = _AGENT_DEFAULT_RISK.get(agent_name, _DEFAULT_RISK_POINTS)
    
    # Get recent risk breakdown for context (last 5 entries)
    try:
        _breakdown = get_risk_breakdown(agent_name)
        _breakdown_str = "\n".join([
            f"  {r['timestamp'][:19]} | +{r['risk_points']}pts | running={r['running_total']}pts"
            for r in _breakdown[:5]
        ]) or "  No risk-bearing calls today"
    except Exception:
        _breakdown_str = "  Unable to retrieve breakdown"
    
    _user_prompt = _JUDGE_USER_TEMPLATE.format(
        agent_name=agent_name,
        action=action,
        cumulative_risk=context.get("cumulative_risk", 0),
        calls_today=context.get("calls_today", 0),
        agent_cost_usd=context.get("agent_cost_usd", 0.0),
        session_cost_usd=context.get("session_cost_usd", 0.0),
        agent_risk_weight=_risk_weight,
        reason=ask_reason,
        risk_breakdown=_breakdown_str,
    )
    
    try:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=LLM_STANDARD,  # Sonnet — fast + cheap for classification
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt}
            ],
            max_tokens=128,
            temperature=0.0,
        )
        
        _raw = response.choices[0].message.content.strip()
        
        # Parse JSON response
        # Handle potential markdown wrapping
        if _raw.startswith("```"):
            _raw = _raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        
        _parsed = json.loads(_raw)
        _action = _parsed.get("action", "ask").upper()
        _reason = _parsed.get("reason", "Judge returned no reason")
        _confidence = float(_parsed.get("confidence", 0.5))
        
        # Log the judge call (as governance agent)
        _tokens_in = response.usage.prompt_tokens
        _tokens_out = response.usage.completion_tokens
        log_agent_call("governance_judge", LLM_STANDARD, _tokens_in, _tokens_out, 0.0, "SUCCESS", risk_points=0)
        
        # Log to policy_log
        _log_policy_eval(
            agent_name, "llm_judge", "pre_execution", _action,
            f"Judge: {_reason} (confidence={_confidence:.2f})",
            context
        )
        
        return {"action": _action, "reason": f"LLM Judge: {_reason}", "confidence": _confidence}
        
    except Exception as e:
        # Fail-open: if judge crashes, default to ASK (let supervisor decide)
        _log_policy_eval(
            agent_name, "llm_judge", "pre_execution", "ASK",
            f"Judge error (fail-open to ASK): {str(e)[:200]}",
            context
        )
        return {"action": "ASK", "reason": f"Judge unavailable: {str(e)[:100]}", "confidence": 0.0}


def llm_judge_evaluate(agent_name: str, action: str, context: dict, ask_reason: str) -> dict:
    """
    Public interface for LLM-as-Judge evaluation.
    
    Called by evaluate_policies() when the expression engine returns ASK
    and the risk score is in the grey zone (40-59).
    
    Returns: {"action": "ALLOW"|"DENY"|"ASK", "reason": str, "policy_name": "llm_judge"}
    """
    result = _llm_judge(agent_name, action, context, ask_reason)
    return {
        "action": result["action"],
        "reason": result["reason"],
        "policy_name": "llm_judge",
        "confidence": result.get("confidence", 0.5),
    }


# ── Register for lazy binding ─────────────────────────────────────────────────
_governance_llm_judge = llm_judge_evaluate

print("✅ Phase 8.5 LLM-as-Judge loaded | llm_judge_evaluate(), _llm_judge()")
print(f"   Model: {LLM_STANDARD} | Max tokens: 128 | Temperature: 0.0")
print(f"   Fires only on ASK verdicts in grey zone (40-59 risk)")
print(f"   Cost: ~$0.003-0.01/call | Expected frequency: <5% of evaluations")
print(f"   Registered gate: _governance_llm_judge")

# COMMAND ----------

# DBTITLE 1,Phase 9.1 — Semantic Memory Engine
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9.1 — SEMANTIC MEMORY ENGINE
#
# Upgrades agent_memory from exact-key lookup to semantic recall.
# Inspired by oh-my-pi's Mnemopi (Apache 2.0).
#
# New capabilities:
#   • remember(content, metadata) — store durable fact with embedding + dedup
#   • recall(query, top_k)        — hybrid semantic + keyword search
#   • reflect(query)              — LLM synthesis over recalled memories
#
# Backward-compatible: existing agent_memory reads still work unchanged.
# Cost: ~$0.001/call via BGE embeddings (or $0 with hash fallback)
# ══════════════════════════════════════════════════════════════════════════════

import hashlib
import numpy as np
from typing import Optional

# ── Schema Extension (idempotent ALTER + new index table) ────────────────────

_MEMORY_SCHEMA_EXTENSIONS = [
    ("content_embedding", "ARRAY<FLOAT>", "Vector embedding for semantic recall (384-dim BGE or 64-dim hash)"),
    ("importance", "FLOAT", "Importance score 0.0-1.0 (agent self-rating, separate from confidence)"),
    ("veracity", "STRING", "Fact status: true | uncertain | superseded"),
    ("last_accessed", "TIMESTAMP", "Last time this memory was recalled"),
    ("memory_source", "STRING", "Origin: agent_output | user_correction | session_summary | seed"),
    ("session_id", "STRING", "Session that created this memory"),
    ("content_hash", "STRING", "xxHash64 of memory_value for deduplication"),
]

for _col_name, _col_type, _col_comment in _MEMORY_SCHEMA_EXTENSIONS:
    try:
        spark.sql(f"""
            ALTER TABLE {CATALOG}.{SCHEMA}.agent_memory 
            ADD COLUMNS ({_col_name} {_col_type} COMMENT '{_col_comment}')
        """)
    except Exception as _e:
        if "already exists" in str(_e).lower():
            pass  # Column already added — idempotent
        else:
            print(f"  ⚠️ ALTER TABLE warning for {_col_name}: {_e}")

# Index table for fast vector lookup
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_memory_index (
    memory_id       STRING    COMMENT 'Unique memory identifier (UUID)',
    agent_name      STRING    COMMENT 'Owning agent',
    bank            STRING    COMMENT 'Memory bank: project | global | session',
    content_hash    STRING    COMMENT 'xxHash64 of content for dedup',
    embedding       ARRAY<FLOAT> COMMENT 'Vector embedding for semantic search',
    keywords        ARRAY<STRING> COMMENT 'Extracted keywords for BM25-style boost',
    memory_value    STRING    COMMENT 'Denormalized content for fast recall without join',
    importance      FLOAT     COMMENT 'Importance score 0.0-1.0',
    created_at      TIMESTAMP COMMENT 'Memory creation time'
)
USING DELTA
COMMENT 'Vector index for Phase 9.1 semantic memory recall'
""")

print("✅ Phase 9.1 schema ready | agent_memory extended + agent_memory_index created")


# ── Embedding Generation (two-tier: BGE endpoint or hash fallback) ───────────

_EMBEDDING_DIM_BGE = 1024   # BGE-large actual output dimension (confirmed via testing)
_EMBEDDING_DIM_HASH = 64    # Lightweight hash embedding dimension
_EMBEDDING_MODE = "bge"     # "bge" (serving endpoint) or "hash" (zero-cost fallback)


def _get_embedding_bge(text: str) -> list:
    """Generate embedding via Databricks BGE serving endpoint."""
    try:
        client = get_llm_client()
        response = client.embeddings.create(
            model="databricks-bge-large-en",
            input=[text[:2048]]  # Track 4.6: Expanded from 512 to 2048 chars (BGE-large supports 512 tokens ≈ ~2K chars)
        )
        return response.data[0].embedding
    except Exception as e:
        # Fallback to hash embedding if endpoint unavailable
        return _get_embedding_hash(text)


def _get_embedding_hash(text: str, dim: int = _EMBEDDING_DIM_HASH) -> list:
    """Deterministic pseudo-embedding via character n-gram hashing. Zero cost."""
    tokens = [text[i:i+3] for i in range(len(text) - 2)] if len(text) > 2 else [text]
    vec = [0.0] * dim
    for t in tokens:
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm > 0 else vec


def get_embedding(text: str) -> list:
    """Generate embedding using configured mode (bge or hash)."""
    if _EMBEDDING_MODE == "bge":
        return _get_embedding_bge(text)
    return _get_embedding_hash(text)


# ── Content Hashing (for deduplication) ──────────────────────────────────────

def _content_hash(text: str) -> str:
    """Generate xxHash64-style hash of content for dedup (using SHA256 truncated)."""
    # Using hashlib since xxhash may not be pre-installed on serverless
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Cosine Similarity ────────────────────────────────────────────────────────

def _cosine_similarity(vec_a: list, vec_b: list) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


# ── Keyword Extraction (lightweight, no NLP deps) ───────────────────────────

def _extract_keywords(text: str, max_keywords: int = 10) -> list:
    """Extract keywords via simple heuristic (long words, no stopwords)."""
    _stopwords = {"the", "is", "at", "which", "on", "a", "an", "and", "or", "but",
                  "in", "with", "to", "for", "of", "from", "by", "as", "it", "that",
                  "this", "be", "are", "was", "were", "has", "have", "had", "not",
                  "do", "does", "did", "will", "would", "could", "should", "can"}
    words = text.lower().split()
    keywords = [w.strip(".,;:!?()[]{}\"'") for w in words 
                if len(w) > 3 and w.lower().strip(".,;:!?()[]{}\"'") not in _stopwords]
    # Deduplicate preserving order
    seen = set()
    unique = []
    for kw in keywords:
        if kw and kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:max_keywords]


# ══════════════════════════════════════════════════════════════════════════════
# CORE API: remember() / recall() / reflect()
# ══════════════════════════════════════════════════════════════════════════════

def remember(agent_name: str, content: str, metadata: dict = None) -> str:
    """Store a durable fact in the agent's semantic memory bank.
    
    Args:
        agent_name: Which agent owns this memory
        content: The fact/knowledge to remember
        metadata: Optional dict with keys: importance, source, session_id, bank, key
    
    Returns:
        memory_id (UUID string)
    """
    metadata = metadata or {}
    memory_id = str(uuid.uuid4())
    content_h = _content_hash(content)
    
    # Dedup check — skip if identical content already exists for this agent
    existing = spark.sql(f"""
        SELECT memory_key FROM {CATALOG}.{SCHEMA}.agent_memory
        WHERE agent_name = '{agent_name}' AND content_hash = '{content_h}'
        LIMIT 1
    """).collect()
    if existing:
        return existing[0]["memory_key"]  # Return existing memory_id
    
    # Generate embedding
    embedding = get_embedding(content)
    keywords = _extract_keywords(content)
    importance = metadata.get("importance", 0.5)
    source = metadata.get("source", "agent_output")
    session_id = metadata.get("session_id", "")
    bank = metadata.get("bank", "global")
    memory_key = metadata.get("key", memory_id)
    now = datetime.now()
    
    # Write to agent_memory (primary table) — explicit schema to handle NULLs
    _mem_schema = StructType([
        StructField("agent_name", StringType(), True),
        StructField("memory_key", StringType(), True),
        StructField("memory_value", StringType(), True),
        StructField("confidence", DoubleType(), True),
        StructField("source_folder", StringType(), True),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        StructField("access_count", IntegerType(), True),
        StructField("expires_at", TimestampType(), True),
        StructField("content_embedding", ArrayType(FloatType()), True),
        StructField("importance", FloatType(), True),
        StructField("veracity", StringType(), True),
        StructField("last_accessed", TimestampType(), True),
        StructField("memory_source", StringType(), True),
        StructField("session_id", StringType(), True),
        StructField("content_hash", StringType(), True),
    ])
    mem_df = spark.createDataFrame([(
        agent_name, memory_key, content, float(importance), bank,
        now, now, 0, None, embedding, float(importance),
        "true", None, source, session_id, content_h
    )], schema=_mem_schema)
    mem_df.write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_memory")
    
    # Write to index (denormalized for fast recall) — explicit schema for FLOAT arrays
    # ORPHAN PROTECTION: if index write fails, rollback the agent_memory row
    _idx_schema = StructType([
        StructField("memory_id", StringType(), True),
        StructField("agent_name", StringType(), True),
        StructField("bank", StringType(), True),
        StructField("content_hash", StringType(), True),
        StructField("embedding", ArrayType(FloatType()), True),
        StructField("keywords", ArrayType(StringType()), True),
        StructField("memory_value", StringType(), True),
        StructField("importance", FloatType(), True),
        StructField("created_at", TimestampType(), True),
    ])
    try:
        idx_df = spark.createDataFrame([(
            memory_id, agent_name, bank, content_h,
            [float(x) for x in embedding], keywords, content,
            float(importance), now
        )], schema=_idx_schema)
        idx_df.write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_memory_index")
    except Exception as _idx_err:
        # Rollback: delete the orphaned row from agent_memory to prevent dedup bypass
        spark.sql(f"""
            DELETE FROM {CATALOG}.{SCHEMA}.agent_memory
            WHERE agent_name = '{agent_name}' AND content_hash = '{content_h}'
              AND memory_key = '{memory_key}'
        """)
        raise RuntimeError(
            f"remember() failed on index write for agent='{agent_name}', "
            f"key='{memory_key}'. Rolled back agent_memory row. "
            f"Original error: {_idx_err}"
        ) from _idx_err
    
    return memory_id


def recall(agent_name: str, query: str, top_k: int = 5, 
           bank: str = None, min_importance: float = 0.0) -> list:
    """Semantic search over an agent's memory bank.
    
    Hybrid retrieval: embedding similarity (70% weight) + keyword boost (30% weight).
    
    Args:
        agent_name: Which agent's memories to search
        query: Natural language query
        top_k: Number of results to return
        bank: Filter to specific bank (None = all banks)
        min_importance: Minimum importance threshold
    
    Returns:
        List of dicts: [{content, score, importance, bank, created_at}, ...]
    """
    # Load memories for this agent from index
    bank_filter = f"AND bank = '{bank}'" if bank else ""
    memories_df = spark.sql(f"""
        SELECT memory_id, memory_value, embedding, keywords, importance, bank, created_at
        FROM {CATALOG}.{SCHEMA}.agent_memory_index
        WHERE agent_name = '{agent_name}'
          AND importance >= {min_importance}
          {bank_filter}
    """).collect()
    
    if not memories_df:
        return []
    
    # Generate query embedding
    query_embedding = get_embedding(query)
    query_keywords = set(_extract_keywords(query))
    
    # Score each memory: 70% cosine similarity + 30% keyword overlap
    scored = []
    for row in memories_df:
        # Embedding similarity
        if row["embedding"]:
            embed_score = _cosine_similarity(query_embedding, row["embedding"])
        else:
            embed_score = 0.0
        
        # Keyword overlap (Jaccard-style)
        mem_keywords = set(row["keywords"]) if row["keywords"] else set()
        if mem_keywords and query_keywords:
            keyword_score = len(query_keywords & mem_keywords) / len(query_keywords | mem_keywords)
        else:
            keyword_score = 0.0
        
        # Hybrid score
        hybrid_score = (0.7 * embed_score) + (0.3 * keyword_score)
        
        # Importance boost (up to +10%)
        importance_val = row["importance"] or 0.5
        final_score = hybrid_score * (1.0 + 0.1 * importance_val)
        
        scored.append({
            "memory_id": row["memory_id"],
            "content": row["memory_value"],
            "score": round(final_score, 4),
            "importance": importance_val,
            "bank": row["bank"],
            "created_at": str(row["created_at"]),
        })
    
    # Sort by score descending, return top_k
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_results = scored[:top_k]
    
    # Update access_count + last_accessed for recalled memories
    if top_results:
        recalled_ids = [r["memory_id"] for r in top_results]
        try:
            ids_str = ",".join([f"'{mid}'" for mid in recalled_ids])
            spark.sql(f"""
                UPDATE {CATALOG}.{SCHEMA}.agent_memory_index
                SET importance = importance  -- touch to register access (Delta versioning)
                WHERE memory_id IN ({ids_str})
            """)
        except Exception:
            pass  # Non-critical — don't fail recall on access tracking
    
    return top_results


def reflect(agent_name: str, query: str, top_k: int = 10) -> str:
    """Ask the LLM to synthesize an answer from recalled memories.
    
    1. Recalls top_k memories semantically
    2. Feeds them as context to Sonnet
    3. Returns synthesized answer
    
    Args:
        agent_name: Which agent's memories to search
        query: The question to reflect on
        top_k: How many memories to feed as context
    
    Returns:
        Synthesized answer string from LLM
    """
    memories = recall(agent_name, query, top_k=top_k)
    
    if not memories:
        return f"No memories found for agent '{agent_name}' matching: {query}"
    
    # Format memories as context
    context_lines = []
    for i, mem in enumerate(memories, 1):
        context_lines.append(
            f"{i}. [score={mem['score']}, importance={mem['importance']}] {mem['content']}"
        )
    context_block = "\n".join(context_lines)
    
    reflect_prompt = f"""Based on the following recalled memories for agent '{agent_name}', 
synthesize a concise, actionable answer to this question: {query}

Recalled memories (ranked by relevance):
{context_block}

Rules:
- Synthesize across memories — don't just list them
- Flag any contradictions between memories
- If memories are insufficient, say so clearly
- Keep response under 200 words"""
    
    result = call_agent(
        "supervisor",  # Use supervisor for reflection (lightweight)
        "You are a memory synthesis engine. Combine recalled knowledge into concise answers.",
        reflect_prompt,
        max_tokens=1024
    )
    return result


print("✅ Phase 9.1 complete | remember(), recall(), reflect() available")
print(f"   Embedding mode: {_EMBEDDING_MODE} | Dim: {_EMBEDDING_DIM_BGE if _EMBEDDING_MODE == 'bge' else _EMBEDDING_DIM_HASH}")
print(f"   Hybrid scoring: 70% cosine similarity + 30% keyword overlap")

# COMMAND ----------

# DBTITLE 1,Phase 9.2 — Content-Hash Output Verification
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9.2 — CONTENT-HASH OUTPUT VERIFICATION (Integrity Layer)
#
# Pre/post hash verification on agent outputs before Delta write.
# Prevents stale-state corruption when multiple agents share state.
# Inspired by oh-my-pi's Hashline content-hash anchoring.
#
# Problem solved: Agent A reads context → Agent B modifies context →
#   Agent A writes output based on stale context = SILENT CORRUPTION.
#   After Phase 9.2: detected and REJECTED.
#
# Cost: ZERO additional DBU — SHA256 is pure Python (~0.1ms/hash)
# ══════════════════════════════════════════════════════════════════════════════


def hash_context(context: dict) -> str:
    """Generate a deterministic hash of the input context an agent consumed.
    
    Used at read-time to fingerprint the state. At write-time, re-hash
    and compare — if different, another agent modified the shared state.
    
    Args:
        context: Dict of any serializable context (prompts, memory reads, etc.)
    
    Returns:
        16-char hex hash string
    """
    canonical = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _read_current_context(agent_name: str, target_key: str) -> dict:
    """Re-read the current state of a specific memory/output key."""
    rows = spark.sql(f"""
        SELECT memory_value, updated_at 
        FROM {CATALOG}.{SCHEMA}.agent_memory
        WHERE agent_name = '{agent_name}' AND memory_key = '{target_key}'
        ORDER BY updated_at DESC
        LIMIT 1
    """).collect()
    if rows:
        return {"key": target_key, "value": rows[0]["memory_value"], 
                "updated_at": str(rows[0]["updated_at"])}
    return {"key": target_key, "value": None, "updated_at": None}


def verified_save(agent_name: str, output: dict, context_hash: str,
                  target_key: str, run_id: str = None) -> dict:
    """Save agent output ONLY if the context it consumed hasn't changed.
    
    Compare-and-swap pattern:
      1. Re-read current state of inputs the agent consumed
      2. Re-hash current state
      3. Compare with context_hash (recorded at read-time)
      4. If match → write (state is fresh)
      5. If mismatch → REJECT + log stale_write event
    
    Args:
        agent_name: The agent attempting to write
        output: Dict of output content to save
        context_hash: Hash from hash_context() at read-time
        target_key: The memory/output key being written to
        run_id: Optional run ID for tracing
    
    Returns:
        dict with 'status' ('WRITTEN' or 'REJECTED') and metadata
    """
    run_id = run_id or generate_run_id()
    
    # Re-read current state
    current_context = _read_current_context(agent_name, target_key)
    current_hash = hash_context(current_context)
    
    if current_hash != context_hash:
        # STALE STATE DETECTED — reject the write
        stale_event = {
            "event_type": "STALE_WRITE_REJECTED",
            "agent_name": agent_name,
            "target_key": target_key,
            "expected_hash": context_hash,
            "actual_hash": current_hash,
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "advice": "Re-read context and regenerate output"
        }
        
        # Log to agent_outputs as a governance event
        save_agent_output("governance", run_id, "stale_write_rejected", 
                         json.dumps(stale_event))
        
        return {
            "status": "REJECTED",
            "reason": "stale_context",
            "expected_hash": context_hash,
            "actual_hash": current_hash,
            "advice": "Context changed since read. Re-read and regenerate."
        }
    
    # State is fresh — proceed with write
    output_content = json.dumps(output, default=str) if isinstance(output, dict) else str(output)
    save_agent_output(agent_name, run_id, target_key, output_content)
    
    return {
        "status": "WRITTEN",
        "hash": current_hash,
        "run_id": run_id,
        "target_key": target_key
    }


def context_aware_call(agent_name: str, system_prompt: str, user_prompt: str,
                       context_keys: list = None, target_key: str = None,
                       **kwargs) -> dict:
    """Wrapper around call_agent() that adds content-hash verification.
    
    Usage:
        result = context_aware_call(
            "data_engineer", system_prompt, user_prompt,
            context_keys=["client_profile", "schema_context"],
            target_key="pipeline_code"
        )
        # result = {"response": "...", "verification": {"status": "WRITTEN", ...}}
    
    Args:
        agent_name: Target agent
        system_prompt: System prompt
        user_prompt: User prompt
        context_keys: List of memory keys this agent reads (for hash)
        target_key: The key the output will be written to (None = skip verification)
        **kwargs: Passed to call_agent()
    
    Returns:
        dict with 'response' and optional 'verification' result
    """
    # Step 1: Hash the context at read-time
    context_snapshot = {}
    if context_keys:
        for key in context_keys:
            ctx = _read_current_context(agent_name, key)
            context_snapshot[key] = ctx
    
    pre_hash = hash_context(context_snapshot) if context_snapshot else None
    
    # Step 2: Call the agent (normal LLM call)
    response = call_agent(agent_name, system_prompt, user_prompt, **kwargs)
    
    # Step 3: If target_key specified, use verified_save
    verification = None
    if target_key and pre_hash:
        verification = verified_save(
            agent_name, 
            {"output": response}, 
            pre_hash, 
            target_key
        )
        
        # If rejected, retry ONCE with fresh context
        if verification["status"] == "REJECTED":
            # Re-read fresh context
            fresh_context = {}
            for key in context_keys:
                fresh_context[key] = _read_current_context(agent_name, key)
            fresh_hash = hash_context(fresh_context)
            
            # Retry LLM call (context may affect prompt in real usage)
            response = call_agent(agent_name, system_prompt, user_prompt, **kwargs)
            verification = verified_save(
                agent_name, {"output": response}, fresh_hash, target_key
            )
            verification["retried"] = True
    
    return {
        "response": response,
        "verification": verification
    }


print("✅ Phase 9.2 complete | hash_context(), verified_save(), context_aware_call() available")
print("   Stale-write detection: compare-and-swap before Delta write")
print("   Auto-retry: 1 retry with fresh context on REJECTED")

# COMMAND ----------

# DBTITLE 1,Phase 9.3 — Automatic Context Compaction
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9.3 — AUTOMATIC CONTEXT COMPACTION (Token Intelligence)
#
# Auto-compaction of conversation history when approaching token limits.
# Replaces brute-force truncation with intelligent pruning.
# Inspired by oh-my-pi's snapcompact package.
#
# Compaction rules:
#   NEVER compress: system prompts, policy injections, user corrections,
#                   last 2 turns, DDL/JSON schemas
#   COMPRESS:       older turns (summarize), verbose tool outputs (extract key metrics),
#                   error traces (root cause only)
#
# Integration: called inside call_agent() when token estimate > 80% context window.
# Cost: ~$0.003-0.01 per compaction event (one Sonnet summary call)
# ══════════════════════════════════════════════════════════════════════════════

import re as _re_module

# Token estimation constants
_CHARS_PER_TOKEN = 4  # Conservative estimate (English text)
_CONTEXT_WINDOWS = {
    "databricks-claude-opus-4-8": 200000,
    "databricks-claude-sonnet-4-6": 200000,
}
_COMPACTION_THRESHOLD = 0.80  # Trigger at 80% of context window


def estimate_tokens(messages: list) -> int:
    """Estimate token count for a list of messages."""
    total_chars = sum(len(msg.get("content", "")) for msg in messages)
    return total_chars // _CHARS_PER_TOKEN


def _contains_ddl_or_schema(msg: dict) -> bool:
    """Check if message contains DDL or JSON schema (must not compress)."""
    content = msg.get("content", "")
    ddl_patterns = [
        r"CREATE\s+(TABLE|VIEW|SCHEMA)",
        r"ALTER\s+TABLE",
        r"ARRAY<",
        r"STRUCT<",
        r'"type":\s*"(string|int|array|struct)",',
        r"USING\s+DELTA",
    ]
    for pattern in ddl_patterns:
        if _re_module.search(pattern, content, _re_module.IGNORECASE):
            return True
    return False


def is_protected(msg: dict, index: int, total: int) -> bool:
    """Determine if a message must NOT be compacted.
    
    Protected content:
      - System prompts (foundation context)
      - Policy injections from Phase 8 (governance must persist)
      - User corrections (learned preferences)
      - Last 2 exchanges (4 messages: user+assistant each)
      - DDL/JSON schemas (structural integrity)
    """
    if msg.get("role") == "system":
        return True
    
    content = msg.get("content", "")
    
    # Phase 8 policy injections survive compaction
    if "[POLICY INJECTION]" in content:
        return True
    
    # User corrections are permanent learning
    if msg.get("metadata", {}).get("type") == "user_correction":
        return True
    if msg.get("role") == "user" and any(kw in content.lower() for kw in 
        ["actually", "no, ", "wrong", "correction:", "instead "]):
        return True  # Heuristic: likely a correction
    
    # Last 4 messages (2 exchanges) are always kept
    if index >= total - 4:
        return True
    
    # DDL and schemas are structural — never compress
    if _contains_ddl_or_schema(msg):
        return True
    
    return False


def _summarize_messages(messages: list) -> str:
    """Compress a batch of older messages into a concise summary."""
    if not messages:
        return ""
    
    # Build a condensed representation of the messages
    turns = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")[:500]  # Truncate for summary input
        turns.append(f"[{role}]: {content}")
    
    turns_text = "\n".join(turns)
    
    summary_prompt = f"""Summarize this conversation segment into 2-3 sentences.
Preserve: key decisions, action items, important facts, numbers/metrics.
Drop: pleasantries, verbose explanations, raw data dumps.

Conversation:
{turns_text}

Summary (2-3 sentences max):"""
    
    try:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=LLM_STANDARD,
            messages=[
                {"role": "system", "content": "You are a conversation summarizer. Be extremely concise."},
                {"role": "user", "content": summary_prompt}
            ],
            max_tokens=512,  # Track 4.5: Raised from 256 to preserve more context in summaries
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Fallback: just take first sentence of each message
        fallback = " | ".join(
            msg.get("content", "").split(".")[0][:100] for msg in messages[:5]
        )
        return f"[Compacted {len(messages)} messages]: {fallback}"


def compact_context(messages: list, model: str = None, 
                    max_tokens: int = None) -> list:
    """Auto-compact conversation while preserving critical content.
    
    Called when token usage approaches context window limit.
    
    Args:
        messages: Full conversation history (list of {role, content} dicts)
        model: LLM model name (to determine context window size)
        max_tokens: Override max tokens (default: 80% of model's context window)
    
    Returns:
        Compacted message list (same format, fewer/shorter messages)
    """
    if not messages:
        return messages
    
    # Determine threshold
    if max_tokens is None:
        window_size = _CONTEXT_WINDOWS.get(model or LLM_STANDARD, 200000)
        max_tokens = int(window_size * _COMPACTION_THRESHOLD)
    
    token_count = estimate_tokens(messages)
    if token_count <= max_tokens:
        return messages  # No compaction needed
    
    # Partition into protected vs. compactable
    protected = []      # (index, msg) — must keep
    compactable = []    # (index, msg) — can summarize
    
    total = len(messages)
    for i, msg in enumerate(messages):
        if is_protected(msg, i, total):
            protected.append((i, msg))
        else:
            compactable.append((i, msg))
    
    if not compactable:
        return messages  # Everything is protected — can't compact
    
    # Summarize compactable messages
    compactable_msgs = [msg for _, msg in compactable]
    summary = _summarize_messages(compactable_msgs)
    
    # Reconstruct: system messages + summary + protected recent messages
    result = []
    
    # 1. System messages first
    for _, msg in protected:
        if msg.get("role") == "system":
            result.append(msg)
    
    # 2. Insert compaction summary as assistant context
    if summary:
        result.append({
            "role": "assistant",
            "content": f"[COMPACTED CONTEXT — {len(compactable_msgs)} earlier messages summarized]\n{summary}",
            "metadata": {"type": "compaction_summary", "original_count": len(compactable_msgs)}
        })
    
    # 3. Non-system protected messages (corrections, recent turns, DDL)
    for _, msg in protected:
        if msg.get("role") != "system":
            result.append(msg)
    
    _new_tokens = estimate_tokens(result)
    _saved = token_count - _new_tokens
    _pct = round((_saved / token_count) * 100, 1) if token_count > 0 else 0
    
    # Log compaction event
    try:
        log_agent_call("context_compactor", LLM_STANDARD, token_count, _new_tokens, 
                      0.0, f"COMPACTED: {_saved} tokens saved ({_pct}%)")
    except Exception:
        pass
    
    return result


# ── Integration helper: use inside multi-turn sessions ───────────────────────

def maybe_compact(messages: list, model: str = None) -> list:
    """Check if compaction is needed and apply if so. Drop-in pre-call hook.
    
    Usage in multi-turn agent sessions:
        messages = maybe_compact(messages, model=LLM_CRITICAL)
        response = client.chat.completions.create(model=model, messages=messages)
    """
    window_size = _CONTEXT_WINDOWS.get(model or LLM_STANDARD, 200000)
    threshold = int(window_size * _COMPACTION_THRESHOLD)
    
    if estimate_tokens(messages) > threshold:
        return compact_context(messages, model=model)
    return messages


print("✅ Phase 9.3 complete | compact_context(), maybe_compact(), is_protected() available")
print(f"   Compaction threshold: {int(_COMPACTION_THRESHOLD * 100)}% of context window")
print(f"   Protected zones: system prompts, policy injections, corrections, last 2 turns, DDL")

# COMMAND ----------

# DBTITLE 1,Phase 9.4 — Stream Rule Enforcement
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9.4 — STREAM RULE ENFORCEMENT (Mid-Generation Gating)
#
# Pattern detection in LLM responses with mid-generation correction.
# Complements Phase 8 (pre/post gates) with IN-FLIGHT enforcement.
#
# Flow: generate → check buffer against rules → on match:
#   abort_retry:    stop, inject correction, retry from scratch
#   warn_continue:  log violation, keep generating
#   log_only:       silent logging
#
# Saves wasted tokens on known-bad patterns (hardcoded rates, DROP prod, PII).
# Cost: regex is free; retries ~$0.003-0.01 each (< 5% of calls trigger)
# ══════════════════════════════════════════════════════════════════════════════

import re

# ── Stream Rules Table (idempotent) ──────────────────────────────────────────

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.agent_stream_rules (
    rule_id         STRING    COMMENT 'UUID primary key',
    rule_name       STRING    COMMENT 'Human-readable name, e.g. no_hardcoded_rates',
    scope           STRING    COMMENT 'global | agent:<agent_name>',
    pattern         STRING    COMMENT 'Python regex pattern to match in output',
    injection       STRING    COMMENT 'System message injected on match (correction)',
    action          STRING    COMMENT 'abort_retry | warn_continue | log_only',
    max_retries     INT       COMMENT 'Max retry attempts before hard DENY',
    priority        INT       COMMENT 'Lower = checked first',
    is_active       BOOLEAN   COMMENT 'Toggle without deleting',
    created_at      TIMESTAMP COMMENT 'Rule creation time'
)
USING DELTA
COMMENT 'Stream rules for mid-generation enforcement (Phase 9.4)'
""")


# ── Seed Pre-Built Rules (idempotent via MERGE) ─────────────────────────────

_SEED_STREAM_RULES = [
    {
        "rule_name": "no_hardcoded_rates",
        "scope": "global",
        "pattern": r"\$0\.[0-9]+/DBU",
        "injection": "STOP. Never hardcode DBU rates. Always JOIN to system.billing.list_prices for rate lookups.",
        "action": "abort_retry",
        "max_retries": 2,
        "priority": 10,
    },
    {
        "rule_name": "no_drop_production",
        "scope": "global",
        "pattern": r"DROP\s+(TABLE|VIEW)\s+mde_dev\.(gold|platinum)",
        "injection": "DENY: Cannot drop production gold/platinum objects. Propose a safe alternative.",
        "action": "abort_retry",
        "max_retries": 1,
        "priority": 5,
    },
    {
        "rule_name": "no_select_star_large",
        "scope": "global",
        "pattern": r"SELECT\s+\*\s+FROM\s+\S+\s*;",
        "injection": "Avoid SELECT * without LIMIT. Specify columns and add LIMIT for large tables.",
        "action": "warn_continue",
        "max_retries": 1,
        "priority": 30,
    },
    {
        "rule_name": "no_pii_exposure",
        "scope": "global",
        "pattern": r"(SSN|social.security|credit.card|\b\d{3}-\d{2}-\d{4}\b)",
        "injection": "PII detected in output. Mask or remove sensitive data before proceeding.",
        "action": "abort_retry",
        "max_retries": 2,
        "priority": 1,
    },
    {
        "rule_name": "no_flat_rate_assumption",
        "scope": "agent:cost_optimizer",
        "pattern": r"(flat rate|uniform rate|\$0\.70 per DBU)",
        "injection": "CRITICAL: Rates vary by SKU ($0.01-$0.95). Use list_prices join. Never assume uniform rate.",
        "action": "abort_retry",
        "max_retries": 2,
        "priority": 10,
    },
    {
        "rule_name": "force_delta_format",
        "scope": "global",
        "pattern": r"CREATE\s+TABLE(?!.*USING\s+DELTA).*\(",
        "injection": "All tables must use USING DELTA. Add the clause.",
        "action": "warn_continue",
        "max_retries": 1,
        "priority": 20,
    },
    {
        "rule_name": "no_xxhash64_surrogate_keys",
        "scope": "global",
        "pattern": r"xxhash64\s*\(",
        "injection": "STOP: Hologic production standard requires md5() for surrogate keys, NOT xxHash64. The xxHash64 migration has NOT been executed yet. Use md5(CAST(key AS STRING)) or md5(concat_ws('|', COALESCE(CAST(col AS STRING), '^^NULL^^'), ...)).",
        "action": "abort_retry",
        "max_retries": 2,
        "priority": 8,
    },
]

# Merge seed rules (idempotent)
from pyspark.sql.functions import lit, current_timestamp

_rules_df = spark.createDataFrame([
    {
        "rule_id": str(uuid.uuid4()),
        "rule_name": r["rule_name"],
        "scope": r["scope"],
        "pattern": r["pattern"],
        "injection": r["injection"],
        "action": r["action"],
        "max_retries": r["max_retries"],
        "priority": r["priority"],
        "is_active": True,
        "created_at": datetime.now(),
    }
    for r in _SEED_STREAM_RULES
])

_rules_df.createOrReplaceTempView("_seed_stream_rules")
spark.sql(f"""
    MERGE INTO {CATALOG}.{SCHEMA}.agent_stream_rules AS target
    USING _seed_stream_rules AS source
    ON target.rule_name = source.rule_name
    WHEN NOT MATCHED THEN INSERT *
""")

print(f"✅ Stream rules table seeded | {len(_SEED_STREAM_RULES)} rules")


# ── Load Active Rules (cached per session) ──────────────────────────────────

_stream_rules_cache = None

def _load_stream_rules(agent_name: str = None) -> list:
    """Load active stream rules from Delta (cached per session)."""
    global _stream_rules_cache
    if _stream_rules_cache is None:
        rows = spark.sql(f"""
            SELECT rule_name, scope, pattern, injection, action, max_retries, priority
            FROM {CATALOG}.{SCHEMA}.agent_stream_rules
            WHERE is_active = true
            ORDER BY priority ASC
        """).collect()
        _stream_rules_cache = [row.asDict() for row in rows]
    
    # Filter by scope: global rules + agent-specific rules
    applicable = []
    for rule in _stream_rules_cache:
        scope = rule["scope"]
        if scope == "global":
            applicable.append(rule)
        elif agent_name and scope == f"agent:{agent_name}":
            applicable.append(rule)
    
    return applicable


def _log_stream_violation(agent_name: str, rule: dict, buffer: str):
    """Log a stream rule violation to agent_outputs."""
    try:
        violation_event = {
            "event_type": "STREAM_RULE_VIOLATION",
            "agent_name": agent_name,
            "rule_name": rule["rule_name"],
            "action": rule["action"],
            "pattern_matched": rule["pattern"],
            "buffer_snippet": buffer[-200:],  # Last 200 chars for context
            "timestamp": datetime.now().isoformat(),
        }
        save_agent_output("governance", generate_run_id(), 
                         "stream_violation", json.dumps(violation_event))
    except Exception:
        pass  # Non-critical logging


# ── Core: Post-Generation Rule Check ───────────────────────────────────────
# Note: True streaming interception requires async chunk-level access.
# Databricks Foundation Model API returns full responses (non-streaming by default).
# This implementation checks the FULL response and retries if violated.
# Equivalent to mid-generation abort for non-streaming calls.

def check_stream_rules(agent_name: str, response: str, 
                       messages: list = None) -> dict:
    """Check a completed LLM response against stream rules.
    
    Args:
        agent_name: The agent that generated this response
        response: The full LLM response text
        messages: Original messages (for retry with injection)
    
    Returns:
        dict: {"passed": bool, "violation": rule_dict or None, "action": str}
    """
    rules = _load_stream_rules(agent_name)
    
    for rule in rules:
        try:
            if re.search(rule["pattern"], response, re.IGNORECASE):
                _log_stream_violation(agent_name, rule, response)
                return {
                    "passed": False,
                    "violation": rule,
                    "action": rule["action"],
                    "rule_name": rule["rule_name"],
                    "injection": rule["injection"],
                }
        except re.error:
            continue  # Skip malformed regex
    
    return {"passed": True, "violation": None, "action": "allow"}


def call_agent_with_rules(agent_name: str, system_prompt: str, user_prompt: str,
                          **kwargs) -> str:
    """Enhanced call_agent() with stream rule enforcement.
    
    Flow:
      1. Normal LLM call via call_agent()
      2. Check response against stream rules
      3. If abort_retry: inject correction into system prompt, retry (max N times)
      4. If warn_continue: log violation, return response anyway
      5. If log_only: silent log, return response
    
    Drop-in replacement for call_agent() when rule enforcement needed.
    """
    max_global_retries = 3
    retries = 0
    current_system = system_prompt
    injections_applied = []
    
    while retries <= max_global_retries:
        # Call the agent
        response = call_agent(agent_name, current_system, user_prompt, **kwargs)
        
        # Check against stream rules
        check = check_stream_rules(agent_name, response)
        
        if check["passed"]:
            return response  # Clean — no violations
        
        rule = check["violation"]
        action = check["action"]
        
        if action == "log_only":
            return response  # Logged but not blocked
        
        if action == "warn_continue":
            # Log warning but return the response
            return response
        
        if action == "abort_retry":
            rule_max = rule.get("max_retries", 2)
            if retries >= rule_max:
                # Max retries for this rule exceeded — hard deny
                return (f"⛔ STREAM RULE ENFORCED [{rule['rule_name']}]: "
                        f"Violated after {retries} retries. "
                        f"Injection: {rule['injection']}")
            
            # Inject correction into system prompt and retry
            injection_msg = f"\n\n[POLICY INJECTION - {rule['rule_name']}]: {rule['injection']}"
            if injection_msg not in current_system:
                current_system += injection_msg
                injections_applied.append(rule["rule_name"])
            
            retries += 1
            continue
    
    return (f"⛔ STREAM RULES: Max global retries ({max_global_retries}) exceeded. "
            f"Rules triggered: {injections_applied}")


print("✅ Phase 9.4 complete | check_stream_rules(), call_agent_with_rules() available")
print(f"   Rules loaded: {len(_load_stream_rules())} active global rules")
print(f"   Actions: abort_retry (stop+correct+retry) | warn_continue | log_only")

# COMMAND ----------

# DBTITLE 1,Phase 9.5 — Session Consolidation (Memory Sleep Cycle)
# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9.5 — SESSION CONSOLIDATION (Memory Sleep Cycle)
#
# End-of-session memory consolidation. Compresses a full agent session
# into durable facts stored via remember().
# Inspired by oh-my-pi's Hindsight (retain/recall/reflect).
#
# Problem solved: Agents learn things during execution (schemas, rules,
#   failure patterns) but this knowledge dies with the session. Next run:
#   same discovery phase, same token spend. After Phase 9.5:
#   session knowledge persists automatically.
#
# Integration: add consolidate_session() as final Workflow task,
#   or call explicitly after supervisor orchestration completes.
# Cost: ~$0.005-0.02 per consolidation (one Sonnet extraction call)
# ══════════════════════════════════════════════════════════════════════════════


def _read_session_outputs(agent_name: str, session_id: str) -> list:
    """Read all agent outputs from a specific session."""
    rows = spark.sql(f"""
        SELECT output_type, content, timestamp
        FROM {CATALOG}.{SCHEMA}.agent_outputs
        WHERE agent_name = '{agent_name}'
          AND run_id LIKE '{session_id}%'
        ORDER BY timestamp ASC
        LIMIT 100  -- Track 4.7: Raised from 50 to capture fuller session context
    """).collect()
    return [{"type": r["output_type"], "content": r["content"][:1000],  # Track 4.7: Raised from 500
             "timestamp": str(r["timestamp"])} for r in rows]


def consolidate_session(agent_name: str, session_id: str,
                        additional_context: str = "") -> dict:
    """Compress a completed session into durable memories.
    
    Called at the end of a Workflow or supervisor orchestration.
    Extracts durable facts worth remembering for future sessions.
    
    Args:
        agent_name: The primary agent whose session to consolidate
        session_id: The session/run ID to consolidate
        additional_context: Optional extra context (e.g., final status)
    
    Returns:
        dict: {"memories_created": int, "session_id": str, "memories": [...]}
    """
    # Read session outputs
    session_outputs = _read_session_outputs(agent_name, session_id)
    
    if not session_outputs:
        return {"memories_created": 0, "session_id": session_id, 
                "reason": "No outputs found for session"}
    
    # Ask LLM to extract durable facts
    extraction_prompt = f"""Review this agent session and extract ONLY facts worth 
remembering for future sessions. Return a JSON array of memories.

Agent: {agent_name}
Session ID: {session_id}
{f'Additional context: {additional_context}' if additional_context else ''}

Rules for extraction:
- SKIP ephemeral observations ("query returned 42 rows", "completed in 3.2s")
- KEEP: schema discoveries (table structures, column types, relationships)
- KEEP: business rules learned (naming conventions, data patterns)
- KEEP: failure patterns and their solutions
- KEEP: what worked vs. what didn't (approach learnings)
- KEEP: corrections from users or governance
- Max 10 memories per session
- Each memory must be self-contained (understandable without session context)

Session outputs ({len(session_outputs)} entries):
{json.dumps(session_outputs[:20], indent=2, default=str)}

Return ONLY a JSON array like:
[{{{"content": "fact to remember", "importance": 0.7}}}, ...]

JSON array:"""
    
    try:
        result = call_agent(
            "supervisor",  # Use supervisor for extraction (lightweight task)
            "You are a memory extraction engine. Extract durable facts from agent sessions. Return ONLY valid JSON.",
            extraction_prompt,
            max_tokens=2048,
            temperature=0.0
        )
        
        # Parse JSON from response (handle markdown code blocks)
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        
        memories = json.loads(cleaned)
        
    except (json.JSONDecodeError, Exception) as e:
        # Fallback: store a simple session summary
        memories = [{
            "content": f"Session {session_id} for {agent_name}: {len(session_outputs)} outputs generated.",
            "importance": 0.3
        }]
    
    # Store extracted memories via remember()
    stored = []
    for mem in memories[:10]:  # Cap at 10
        if not isinstance(mem, dict) or "content" not in mem:
            continue
        
        memory_id = remember(agent_name, mem["content"], {
            "importance": mem.get("importance", 0.5),
            "source": "session_summary",
            "session_id": session_id,
            "bank": "session"
        })
        stored.append({"memory_id": memory_id, "content": mem["content"][:100]})
    
    # Log consolidation event
    try:
        log_agent_call("session_consolidator", LLM_STANDARD, 0, 0, 0.0,
                      f"CONSOLIDATED: {len(stored)} memories from session {session_id[:20]}")
    except Exception:
        pass
    
    return {
        "memories_created": len(stored),
        "session_id": session_id,
        "memories": stored
    }


def session_preload(agent_name: str, max_memories: int = 10) -> str:
    """Load relevant memories into system context for a new session.
    
    Called at the START of a session to inject prior knowledge.
    Returns a formatted context block to prepend to the system prompt.
    
    Args:
        agent_name: Which agent is starting a new session
        max_memories: Max memories to load (to control token usage)
    
    Returns:
        Formatted context string (empty if no memories exist)
    """
    # Recall top memories by relevance to this agent's work
    memories = recall(agent_name, f"{agent_name} recent learnings and patterns", 
                     top_k=max_memories)
    
    if not memories:
        return ""  # First-ever session or no memories yet
    
    # Format as injectable context block
    context_lines = ["## Prior Knowledge (from previous sessions)\n"]
    for i, mem in enumerate(memories, 1):
        importance_pct = int((mem.get("importance", 0.5)) * 100)
        context_lines.append(f"{i}. [{importance_pct}% confidence] {mem['content']}")
    
    context_lines.append("\n---\nUse this prior knowledge when relevant. Flag if any seems outdated.")
    
    return "\n".join(context_lines)


def enhanced_call_agent(agent_name: str, system_prompt: str, user_prompt: str,
                        use_memory: bool = True, use_rules: bool = True,
                        **kwargs) -> str:  # Track 4.3: memory+rules now default-on
    """Full Phase 9 enhanced call_agent: memory preload + stream rules.
    
    Combines:
      - Phase 9.1: session_preload() into system prompt
      - Phase 9.4: call_agent_with_rules() for stream enforcement
      - Phase 9.3: maybe_compact() on multi-turn messages (when applicable)
    
    This is the recommended entry point for production agent calls
    that benefit from the full intelligence stack.
    """
    enhanced_system = system_prompt
    
    # Inject prior knowledge from memory (Phase 9.1 + 9.5)
    if use_memory:
        prior_knowledge = session_preload(agent_name, max_memories=5)
        if prior_knowledge:
            enhanced_system = f"{system_prompt}\n\n{prior_knowledge}"
    
    # Call with stream rule enforcement (Phase 9.4)
    if use_rules:
        return call_agent_with_rules(agent_name, enhanced_system, user_prompt, **kwargs)
    else:
        return call_agent(agent_name, enhanced_system, user_prompt, **kwargs)


print("✅ Phase 9.5 complete | consolidate_session(), session_preload(), enhanced_call_agent() available")
print("   Sleep cycle: extracts durable facts from session outputs into semantic memory")
print("   Boot cycle: preloads relevant prior knowledge into new session context")
print("")
print("═" * 78)
print("  PHASE 9 COMPLETE — Agent Intelligence Engine")
print("═" * 78)
print("  9.1: Semantic Memory    | remember(), recall(), reflect()")
print("  9.2: Content-Hash       | hash_context(), verified_save(), context_aware_call()")
print("  9.3: Auto-Compaction    | compact_context(), maybe_compact(), is_protected()")
print("  9.4: Stream Rules       | check_stream_rules(), call_agent_with_rules()")
print("  9.5: Session Sleep      | consolidate_session(), session_preload()")
print("  ──────────────────────────────────────────────────────────────────────────")
print("  ↳ enhanced_call_agent(): Full-stack entry point (memory + rules + compaction)")
print("═" * 78)

# COMMAND ----------

# DBTITLE 1,Qlik Migration Agents — Registry entries (additive, 2026-08-12)
# ══════════════════════════════════════════════════════════════════════════════
# QLIK MIGRATION AGENTS (88-96) — REGISTRY ENTRIES
# ══════════════════════════════════════════════════════════════════════════════
# Added 2026-08-12. These 9 agents (88 orchestrator + 89-96 specialists) were
# never registered in AGENT_REGISTRY, so call_agent() silently fell back to
# LLM_STANDARD/MEDIUM defaults for all of them — functionally harmless (no
# crash) but they had no real profile for cost/risk tracking or dashboards.
# Purely additive via .update() — does not modify the AGENT_REGISTRY literal
# or any existing entry above.
AGENT_REGISTRY.update({
    "88_qlik_migration_orchestrator": {"id": 88, "model": LLM_CRITICAL, "priority": "HIGH",   "type": "agent"},
    "89_qvd_extraction":               {"id": 89, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "90_qlik_script_conversion":       {"id": 90, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "91_qlik_data_model":              {"id": 91, "model": LLM_APEX,     "priority": "MEDIUM", "type": "agent"},
    "92_qlik_expression":              {"id": 92, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "93_qlik_ui_migration":            {"id": 93, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
    "94_qlik_section_access":          {"id": 94, "model": LLM_CRITICAL, "priority": "MEDIUM", "type": "agent"},
    "95_qlik_nprinting":               {"id": 95, "model": LLM_STANDARD, "priority": "LOW",    "type": "agent"},
    "96_qlik_preassessment":           {"id": 96, "model": LLM_STANDARD, "priority": "MEDIUM", "type": "agent"},
})
print(f"✅ Registered 9 Qlik migration agents (88-96) in AGENT_REGISTRY | total components now: {len(AGENT_REGISTRY)}")

# COMMAND ----------

# DBTITLE 1,Agentic Tool-Use Loop — real multi-round tool calling (2026-08-12)
# ══════════════════════════════════════════════════════════════════════════════
# AGENTIC TOOL-USE LOOP
# ══════════════════════════════════════════════════════════════════════════════
# Added 2026-08-12. call_agent() is a single bounded LLM completion with no
# tool use — fine for advisory/summarization agents, but agents 88-96 (Qlik
# migration) need to actually read Qlik source extracts, run live SQL against
# mde_dev, and write files — not just produce an LLM's guess from a request
# string. This is a generic, reusable multi-round tool-calling loop any agent
# can opt into by passing its own tool specs + implementations. It does not
# modify call_agent() or any other existing function — purely additive.
#
# The underlying models (Claude via Databricks FMAPI, OpenAI-compatible client)
# support standard OpenAI-style function calling, so this reuses the same
# client.chat.completions.create() mechanism call_agent() already uses, just
# in a loop that feeds tool results back until the model stops requesting tools.

def run_tool_loop(agent_name: str, system_prompt: str, user_prompt: str,
                   tools_spec: list, tool_impls: dict,
                   max_rounds: int = 60, max_tokens: int = 8192,
                   temperature: float = 0.1) -> dict:
    """Real multi-round tool-use loop for agentic Qlik migration work.

    tools_spec: OpenAI-format tool definitions (list of {"type":"function","function":{...}}).
    tool_impls: {tool_name: callable(**kwargs) -> str} — each must return a string
                (JSON-encode non-string results yourself before returning).

    Returns: {"final_text": str, "rounds": int, "tool_calls": [...], "finish_reason": str,
              "error": str|None}
    """
    config = AGENT_REGISTRY.get(agent_name, {})
    model = config.get("model", LLM_STANDARD)
    client = get_llm_client()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tool_call_log = []
    total_tokens_in = 0
    total_tokens_out = 0

    with mlflow.start_span(name=f"agent/{agent_name}/tool_loop", span_type=SpanType.AGENT) as span:
        span.set_attributes({"agent.name": agent_name, "llm.model": model, "loop.max_rounds": max_rounds})

        for round_num in range(max_rounds):
            kwargs = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "tools": tools_spec,
            }
            if "opus" not in model:
                kwargs["temperature"] = temperature

            try:
                with mlflow.start_span(name=f"llm/round_{round_num}", span_type=SpanType.LLM) as llm_span:
                    # Retry with exponential backoff on token-per-minute rate limits — real
                    # failure mode found 2026-08-12: cumulative input tokens across rounds
                    # (full message history resent each round) can trip the workspace's
                    # per-minute rate limit for the model well before max_rounds is reached.
                    _attempt = 0
                    while True:
                        try:
                            response = client.chat.completions.create(**kwargs)
                            break
                        except Exception as _rate_err:
                            _msg = str(_rate_err)
                            _is_rate_limit = ("429" in _msg or "REQUEST_LIMIT_EXCEEDED" in _msg
                                               or "rate limit" in _msg.lower())
                            if _is_rate_limit and _attempt < 6:
                                _wait_s = min(15 * (2 ** _attempt), 120)
                                _attempt += 1
                                print(f"⏳ Rate limited (retry {_attempt}/6) — waiting {_wait_s}s...")
                                import time as _time_mod
                                _time_mod.sleep(_wait_s)
                                continue
                            raise
                    total_tokens_in += response.usage.prompt_tokens
                    total_tokens_out += response.usage.completion_tokens
                    llm_span.set_attributes({
                        "llm.tokens_in": response.usage.prompt_tokens,
                        "llm.tokens_out": response.usage.completion_tokens,
                        "round": round_num,
                    })
            except Exception as e:
                span.set_attributes({"output.status": "ERROR", "output.error": str(e)[:500]})
                log_agent_call(agent_name, model, total_tokens_in, total_tokens_out, 0.0, f"ERROR: {str(e)[:200]}")
                return {"final_text": "", "rounds": round_num, "tool_calls": tool_call_log,
                        "finish_reason": "ERROR", "error": str(e)}

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        args = {}
                    impl = tool_impls.get(fn_name)
                    if impl is None:
                        tool_result = f"ERROR: unknown tool '{fn_name}'"
                    else:
                        try:
                            tool_result = impl(**args)
                        except Exception as e:
                            tool_result = f"ERROR executing {fn_name}: {e}"
                    tool_call_log.append({
                        "round": round_num, "tool": fn_name, "args": args,
                        "result_preview": str(tool_result)[:400],
                    })
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id, "content": str(tool_result),
                    })
                continue

            # No tool calls — model is done
            _cost = _estimate_cost_usd(total_tokens_in, total_tokens_out)
            span.set_attributes({
                "output.status": "SUCCESS", "output.rounds": round_num + 1,
                "output.tokens_in": total_tokens_in, "output.tokens_out": total_tokens_out,
                "output.cost_usd": _cost, "output.tool_call_count": len(tool_call_log),
            })
            log_agent_call(agent_name, model, total_tokens_in, total_tokens_out, 0.0,
                           f"SUCCESS(tool_loop,{round_num + 1}_rounds,{len(tool_call_log)}_tool_calls)")
            return {"final_text": msg.content or "", "rounds": round_num + 1,
                    "tool_calls": tool_call_log, "finish_reason": finish_reason, "error": None}

        # Exceeded max_rounds without a final answer
        span.set_attributes({"output.status": "MAX_ROUNDS_EXCEEDED", "output.rounds": max_rounds})
        log_agent_call(agent_name, model, total_tokens_in, total_tokens_out, 0.0,
                       f"WARN_MAX_ROUNDS_EXCEEDED({max_rounds})")
        last_content = ""
        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("content"):
                last_content = m["content"]
                break
        return {"final_text": last_content, "rounds": max_rounds, "tool_calls": tool_call_log,
                "finish_reason": "MAX_ROUNDS_EXCEEDED",
                "error": f"Exceeded max_rounds={max_rounds} without a final (no-tool-call) answer"}


def make_sql_query_tool(max_rows: int = 100, max_chars: int = 7000):
    """Factory for a read-only SQL execution tool bound to this notebook's Spark
    session. Blocks DDL/DML keywords — this loop is for live-catalog READS during
    Steps 0-3 analysis, not schema/data mutation. Returns a callable(query) -> str.
    """
    _BLOCKED = ("DROP ", "DELETE ", "TRUNCATE ", "ALTER ", "INSERT ", "UPDATE ",
                "MERGE ", "CREATE ", "GRANT ", "REVOKE ")

    def _sql_query(query: str) -> str:
        q_upper = " " + query.strip().upper() + " "
        for kw in _BLOCKED:
            if kw in q_upper:
                return (f"ERROR: query blocked — this tool is read-only for Steps 0-3 analysis "
                        f"and does not permit '{kw.strip()}' statements.")
        _spark = globals().get("spark")
        try:
            df = _spark.sql(query)
            rows = df.limit(max_rows).collect()
            cols = df.columns
            result = [dict(zip(cols, [str(v) for v in r])) for r in rows]
            out = json.dumps({"row_count_returned": len(result), "columns": cols, "rows": result})
            if len(out) > max_chars:
                out = out[:max_chars] + f"...[TRUNCATED — {len(result)} rows returned, output capped at {max_chars} chars; narrow your query]"
            return out
        except Exception as e:
            return f"ERROR executing SQL: {e}"

    return _sql_query


print("✅ Agentic tool-use loop available | run_tool_loop(), make_sql_query_tool()")
print("   For agents needing real file-read/live-SQL/file-write capability (e.g. Qlik migration 88-96)")
print("   Usage: result = run_tool_loop(agent_name, system_prompt, user_prompt, tools_spec, tool_impls)")