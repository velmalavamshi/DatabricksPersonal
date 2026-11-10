# Databricks notebook source
# DBTITLE 1,Deploy Supervisor Agent to Playground
# MAGIC %md
# MAGIC # Deploy Supervisor Agent as Serving Endpoint
# MAGIC
# MAGIC **Purpose:** Package the Supervisor Agent as an MLflow `ChatModel`, register in Unity Catalog, and deploy as a Model Serving endpoint — making it accessible from **AI Playground**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Architecture
# MAGIC
# MAGIC | Component | Details |
# MAGIC | --- | --- |
# MAGIC | Model Type | `mlflow.pyfunc.ChatModel` |
# MAGIC | LLM Backend | `databricks-claude-sonnet-4-6` via Foundation Model APIs |
# MAGIC | Registry | `mde_dev.test_schema.supervisor_agent_model` |
# MAGIC | Serving SKU | SRTI @ $0.07/DBU |
# MAGIC | Estimated Cost | ~$2,400/year (1 unit, always-on) |
# MAGIC
# MAGIC ## Cost Breakdown
# MAGIC
# MAGIC - **Serving endpoint (SRTI):** $0.07/DBU × ~34,300 DBU/year = **~$2,400/year**
# MAGIC - **LLM tokens (Anthropic passthrough):** $0.105/DBU — usage-dependent, ~$50-200/month with moderate use
# MAGIC - **Total:** ~$3,000-$4,800/year depending on usage
# MAGIC
# MAGIC ⚠️ **Watch Out:** Scale-to-zero is available for serving endpoints. Use it to minimize cost during development.

# COMMAND ----------

# DBTITLE 1,Install dependencies
# MAGIC %pip install mlflow>=2.14 databricks-sdk openai -q
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Configuration
# ══════════════════════════════════════════════════════════════════════════════
# DEPLOYMENT CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

MODEL_NAME = "mde_dev.test_schema.supervisor_agent_model"  # UC model registry
ENDPOINT_NAME = "hologic-supervisor-agent"  # Serving endpoint name (appears in Playground)
LLM_MODEL = "databricks-claude-sonnet-4-6"
EXPERIMENT_NAME = "/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/supervisor_agent_experiment"

print(f"Model: {MODEL_NAME}")
print(f"Endpoint: {ENDPOINT_NAME}")
print(f"LLM: {LLM_MODEL}")

# COMMAND ----------

# DBTITLE 1,Define ChatModel wrapper
# ══════════════════════════════════════════════════════════════════════════════
# SUPERVISOR AGENT — ChatModel WRAPPER
# This class packages the supervisor as an MLflow ChatModel that:
# 1. Receives chat messages from Playground
# 2. Routes through intent classification → decomposition → agent execution
# 3. Returns consolidated response in chat format
# ══════════════════════════════════════════════════════════════════════════════

import mlflow
import mlflow.deployments
from mlflow.pyfunc import ChatModel
from mlflow.types.llm import (
    ChatMessage, ChatParams, ChatCompletionResponse, ChatChoice, TokenUsageStats
)
import json
import os


class SupervisorAgent(ChatModel):
    """
    MLflow ChatModel wrapper for the Hologic Multi-Agent Supervisor.
    
    When deployed as a serving endpoint, this class:
    - Receives user messages via the /invocations API (OpenAI-compatible)
    - Uses Databricks Foundation Model APIs for all LLM calls
    - Orchestrates intent classification, task decomposition, and agent coordination
    - Returns a consolidated response
    
    Accessible from AI Playground once deployed.
    """

    def __init__(self):
        """Initialize — credentials auto-injected by Model Serving runtime."""
        pass
    
    def _get_client(self):
        """Get MLflow deployments client (auto-authenticated in serving context)."""
        return mlflow.deployments.get_deploy_client("databricks")
    
    def _call_llm(self, system_prompt: str, user_prompt: str, 
                  temperature: float = 0.1, max_tokens: int = 4096) -> str:
        """Call LLM via MLflow deployments (works in both notebook and serving).
        Includes error handling so a single LLM failure doesn't crash the chain."""
        try:
            client = self._get_client()
            response = client.predict(
                endpoint=LLM_MODEL,
                inputs={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Agent error: {type(e).__name__}: {str(e)[:200]}]"
    
    # ── Intent Classification ─────────────────────────────────────────────────
    
    INTENT_CLASSIFIER_PROMPT = """You are the Supervisor of a 36-agent AI platform for Databricks data engineering.

Your job: Classify the user's request into exactly ONE work type and identify which agents are needed.

## Work Types

1. FEATURE_DELIVERY — New pipeline, table, transformation, report, or dashboard
2. MONITORING — Job failures, data quality issues, SLA breaches, drift detection
3. OPTIMIZATION — Cost reduction, performance tuning, query optimization
4. INVESTIGATION — Root cause analysis, impact assessment, dependency tracing
5. MAINTENANCE — Schema changes, documentation updates, access requests
6. CLARIFICATION_NEEDED — Request is ambiguous; ask a follow-up question

## Available Agents

business_analyst, scope, architect, data_engineer, sql_developer, 
peer_review, testing, deployment, documentation, cost_anomaly,
job_failure_triage, data_quality_monitor, view_dependency,
source_drift_detector, performance_tuner, data_modeler

## Response Format (JSON only)

{"work_type": "...", "confidence": 0.0-1.0, "agents_needed": [...], "execution_mode": "SEQUENTIAL|PARALLEL", "reasoning": "..."}"""

    def _classify_intent(self, user_request: str) -> dict:
        """Step 1-2: Understand and classify the request."""
        response = self._call_llm(
            self.INTENT_CLASSIFIER_PROMPT,
            f"Classify this request:\n\n{user_request}"
        )
        try:
            # Extract JSON from response
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except (json.JSONDecodeError, IndexError):
            return {"work_type": "CLARIFICATION_NEEDED", "confidence": 0.3, 
                    "agents_needed": [], "reasoning": "Failed to parse classification"}
    
    # ── Agent Capabilities ────────────────────────────────────────────────────
    
    AGENT_CAPABILITIES = {
        "business_analyst": {"skills": ["requirements", "brd", "user_stories"], "cost": "low"},
        "scope": {"skills": ["scope", "assumptions", "risks"], "cost": "low"},
        "architect": {"skills": ["design", "medallion", "delta_schema"], "cost": "medium"},
        "data_engineer": {"skills": ["pipeline", "etl", "spark", "sql"], "cost": "high"},
        "sql_developer": {"skills": ["queries", "views", "stored_procedures"], "cost": "medium"},
        "peer_review": {"skills": ["code_review", "standards", "quality"], "cost": "medium"},
        "testing": {"skills": ["test_cases", "validation", "edge_cases"], "cost": "medium"},
        "deployment": {"skills": ["cicd", "workflows", "rollback"], "cost": "medium"},
        "documentation": {"skills": ["docs", "runbook", "data_dictionary"], "cost": "low"},
        "cost_anomaly": {"skills": ["billing", "cost_spikes", "optimization"], "cost": "medium"},
        "job_failure_triage": {"skills": ["error_analysis", "root_cause", "fix"], "cost": "high"},
        "data_quality_monitor": {"skills": ["null_rates", "schema_drift", "freshness"], "cost": "medium"},
        "view_dependency": {"skills": ["lineage", "impact_analysis", "refactoring"], "cost": "medium"},
        "source_drift_detector": {"skills": ["schema_changes", "source_monitoring"], "cost": "medium"},
        "performance_tuner": {"skills": ["slow_queries", "clustering", "caching"], "cost": "high"},
        "data_modeler": {"skills": ["logical_model", "physical_model", "facts", "dimensions"], "cost": "high"},
    }
    
    # ── Task Execution ─────────────────────────────────────────────────────────
    
    AGENT_EXECUTION_PROMPT = """You are the {agent_name} agent in a Databricks data engineering AI platform.

Your specialized skills: {skills}

Context from previous agents:
{previous_context}

User's original request:
{user_request}

Your specific task:
{task_description}

Provide a detailed, actionable response for your specialty area. Include code, configurations, or recommendations as appropriate. Use Databricks-native solutions."""

    def _execute_agent(self, agent_name: str, user_request: str, 
                      task_description: str, previous_context: str = "") -> str:
        """Execute a single specialized agent."""
        skills = self.AGENT_CAPABILITIES.get(agent_name, {}).get("skills", [])
        prompt = self.AGENT_EXECUTION_PROMPT.format(
            agent_name=agent_name,
            skills=", ".join(skills),
            previous_context=previous_context or "(First agent — no prior context)",
            user_request=user_request,
            task_description=task_description
        )
        return self._call_llm(
            f"You are the {agent_name} agent. Be thorough and Databricks-native.",
            prompt,
            max_tokens=4096
        )
    
    # ── Response Consolidation ────────────────────────────────────────────────
    
    CONSOLIDATION_PROMPT = """You are the Supervisor Agent producing a final consolidated response.

You have multiple agent outputs to merge into ONE coherent response for the user.

Rules:
1. Synthesize — don't just concatenate
2. Resolve any conflicts between agents
3. Present in a logical order (analysis → design → implementation → testing)
4. Include a brief summary at top
5. Flag any gaps or items needing user input

User's original request: {user_request}

Agent outputs:
{agent_outputs}

Produce the final consolidated response:"""

    def _consolidate(self, user_request: str, agent_outputs: dict) -> str:
        """Consolidate multiple agent outputs into a unified response."""
        outputs_text = "\n\n".join([
            f"--- {agent} ---\n{output}" 
            for agent, output in agent_outputs.items()
        ])
        return self._call_llm(
            "You are a senior Databricks expert synthesizing multiple specialist opinions.",
            self.CONSOLIDATION_PROMPT.format(
                user_request=user_request,
                agent_outputs=outputs_text
            ),
            max_tokens=8192
        )

    # ── Main Chat Interface ───────────────────────────────────────────────────
    
    def predict(self, context, messages: list[ChatMessage], params: ChatParams) -> ChatCompletionResponse:
        """
        Main entry point called by Model Serving when a request arrives.
        This is what Playground calls when you send a message.
        """
        # Extract user's latest message
        user_message = messages[-1].content if messages else ""
        
        # Build conversation context from previous messages
        conversation_history = ""
        if len(messages) > 1:
            history = [f"{m.role}: {m.content}" for m in messages[:-1]]
            conversation_history = f"\n\nConversation history:\n" + "\n".join(history[-6:])  # Last 3 exchanges
        
        full_request = user_message + conversation_history
        
        # --- STEP 1-2: Classify intent ---
        classification = self._classify_intent(full_request)
        work_type = classification.get("work_type", "CLARIFICATION_NEEDED")
        confidence = classification.get("confidence", 0)
        agents_needed = classification.get("agents_needed", [])
        
        # --- Handle clarification ---
        if work_type == "CLARIFICATION_NEEDED" or confidence < 0.5:
            clarification_response = self._call_llm(
                "You are a helpful Databricks assistant. Ask a clarifying question.",
                f"The user said: {user_message}\n\nThis was classified as needing clarification. Reasoning: {classification.get('reasoning', 'ambiguous')}\n\nAsk ONE specific clarifying question to help route their request."
            )
            return ChatCompletionResponse(
                choices=[ChatChoice(
                    message=ChatMessage(role="assistant", content=clarification_response)
                )],
                model=LLM_MODEL,
                usage=TokenUsageStats()
            )
        
        # --- STEP 3-5: Decompose, assign, execute ---
        agent_outputs = {}
        previous_context = ""
        
        for agent_name in agents_needed[:5]:  # Cap at 5 agents per request for cost control
            if agent_name in self.AGENT_CAPABILITIES:
                task_desc = f"Handle the '{work_type}' aspect of: {user_message}"
                output = self._execute_agent(
                    agent_name, user_message, task_desc, previous_context
                )
                agent_outputs[agent_name] = output
                previous_context += f"\n\n[{agent_name}]: {output[:500]}"  # Truncate for context window
        
        # --- STEP 6-8: Validate and consolidate ---
        if len(agent_outputs) == 0:
            # Direct response if no specialized agents needed
            final_response = self._call_llm(
                "You are a senior Databricks data engineering expert.",
                f"Answer this directly: {user_message}",
                max_tokens=4096
            )
        elif len(agent_outputs) == 1:
            # Single agent — no consolidation needed
            final_response = list(agent_outputs.values())[0]
        else:
            # Multiple agents — consolidate
            final_response = self._consolidate(user_message, agent_outputs)
        
        # Add routing metadata as a footer
        metadata_footer = f"\n\n---\n*Routed as `{work_type}` (confidence: {confidence}) → agents: {', '.join(agents_needed[:5])}*"
        
        return ChatCompletionResponse(
            choices=[ChatChoice(
                message=ChatMessage(role="assistant", content=final_response + metadata_footer)
            )],
            model=LLM_MODEL,
            usage=TokenUsageStats()
        )


print("✅ SupervisorAgent ChatModel defined")
print("   Entry point: predict(context, messages, params) -> ChatResponse")

# COMMAND ----------

# DBTITLE 1,Test locally before deployment
# ══════════════════════════════════════════════════════════════════════════════
# LOCAL TEST — Verify the agent works before deploying
# ══════════════════════════════════════════════════════════════════════════════

agent = SupervisorAgent()

# Test with a sample message
test_messages = [
    ChatMessage(role="user", content="What agents do you have available and what can they do?")
]

print("🧪 Testing locally...")
response = agent.predict(context=None, messages=test_messages, params=ChatParams())
print(f"\n✅ Response received ({len(response.choices[0].message.content)} chars)")
print(f"\nPreview:\n{response.choices[0].message.content[:500]}...")

# COMMAND ----------

# DBTITLE 1,Log model to MLflow
# ══════════════════════════════════════════════════════════════════════════════
# LOG MODEL TO MLFLOW + UNITY CATALOG REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
# FIX: Previous failures caused by input_example triggering full multi-agent
# LLM chain during log_model() validation. This runs 3-7 API calls to
# databricks-claude-sonnet-4-6, causing timeout/serialization failure.
#
# Solution: Skip input_example validation entirely. The model signature is
# inferred from ChatModel base class (OpenAI-compatible schema).
# ══════════════════════════════════════════════════════════════════════════════

import mlflow

# Set experiment
mlflow.set_experiment(EXPERIMENT_NAME)
mlflow.set_registry_uri("databricks-uc")

with mlflow.start_run(run_name="supervisor_agent_v2") as run:
    # Log the ChatModel WITHOUT input_example to skip validation predict()
    # ChatModel base class auto-provides the correct OpenAI-compatible signature
    model_info = mlflow.pyfunc.log_model(
        artifact_path="supervisor_agent",
        python_model=SupervisorAgent(),
        registered_model_name=MODEL_NAME,
        # NO input_example — prevents validation predict() that triggers full LLM chain
        pip_requirements=[
            "mlflow>=2.14",
            "openai",
            "databricks-sdk",  # Required for mlflow.deployments in serving container
        ],
    )
    
    # Log parameters for tracking
    mlflow.log_params({
        "llm_model": LLM_MODEL,
        "num_agents": len(SupervisorAgent.AGENT_CAPABILITIES),
        "max_agents_per_request": 5,
        "endpoint_name": ENDPOINT_NAME,
    })
    
    print(f"✅ Model logged successfully")
    print(f"   Run ID: {run.info.run_id}")
    print(f"   Model URI: {model_info.model_uri}")
    print(f"   Registered: {MODEL_NAME}")
    print(f"\n   Previous failures fixed:")
    print(f"   • Removed input_example (was triggering full LLM chain during validation)")
    print(f"   • Added databricks-sdk to pip_requirements (needed in serving container)")

# COMMAND ----------

# DBTITLE 1,Deploy serving endpoint
# ══════════════════════════════════════════════════════════════════════════════
# DEPLOY AS SERVING ENDPOINT (appears in Playground)
# ══════════════════════════════════════════════════════════════════════════════

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
)

w = WorkspaceClient()

# Get latest model version
latest_version = None
for mv in w.model_versions.list(MODEL_NAME):
    if latest_version is None or int(mv.version) > int(latest_version):
        latest_version = mv.version

print(f"📦 Deploying model version: {latest_version}")

# Create or update endpoint
try:
    # Try to get existing endpoint
    existing = w.serving_endpoints.get(ENDPOINT_NAME)
    print(f"⚡ Updating existing endpoint: {ENDPOINT_NAME}")
    
    w.serving_endpoints.update_config_and_wait(
        name=ENDPOINT_NAME,
        served_entities=[
            ServedEntityInput(
                entity_name=MODEL_NAME,
                entity_version=latest_version,
                workload_size="Small",  # Smallest for dev/personal use
                scale_to_zero_enabled=True,  # Critical: avoid cost when idle
            )
        ],
    )
except Exception as e:
    if "RESOURCE_DOES_NOT_EXIST" in str(e) or "NOT_FOUND" in str(e):
        print(f"🆕 Creating new endpoint: {ENDPOINT_NAME}")
        
        w.serving_endpoints.create_and_wait(
            name=ENDPOINT_NAME,
            config=EndpointCoreConfigInput(
                served_entities=[
                    ServedEntityInput(
                        entity_name=MODEL_NAME,
                        entity_version=latest_version,
                        workload_size="Small",
                        scale_to_zero_enabled=True,
                    )
                ],
                auto_capture_config=AutoCaptureConfigInput(
                    enabled=True,  # Log requests to inference table for debugging
                    catalog_name="mde_dev",
                    schema_name="test_schema",
                ),
            ),
        )
    else:
        raise e

print(f"\n✅ Endpoint deployed: {ENDPOINT_NAME}")
print(f"   Scale-to-zero: ENABLED (no cost when idle)")
print(f"   Inference table: mde_dev.test_schema (auto-capture)")
print(f"\n🎯 Go to AI Playground → Select '{ENDPOINT_NAME}' from the model dropdown")

# COMMAND ----------

# DBTITLE 1,Verify endpoint in Playground
# ══════════════════════════════════════════════════════════════════════════════
# VERIFY — Test the deployed endpoint
# ══════════════════════════════════════════════════════════════════════════════

import time

# Wait for endpoint to be ready
print("⏳ Waiting for endpoint to be ready...")
endpoint = w.serving_endpoints.get(ENDPOINT_NAME)
print(f"   Status: {endpoint.state.ready}")

# Test query
if endpoint.state.ready == "READY":
    response = w.serving_endpoints.query(
        name=ENDPOINT_NAME,
        messages=[
            {"role": "user", "content": "List all available agents and their capabilities"}
        ]
    )
    print(f"\n✅ Endpoint responding!")
    print(f"   Response preview: {str(response.choices[0].message.content)[:300]}...")
    print(f"\n🎯 NOW GO TO PLAYGROUND:")
    print(f"   1. Open AI Playground (left nav → Machine Learning → Playground)")
    print(f"   2. Click the model dropdown")
    print(f"   3. Select '{ENDPOINT_NAME}'")
    print(f"   4. Start chatting with your Supervisor Agent!")
else:
    print(f"\n⏳ Endpoint still provisioning. Check back in 2-3 minutes.")
    print(f"   URL: https://adb-6617965257274108.8.azuredatabricks.net/ml/endpoints/{ENDPOINT_NAME}")

# COMMAND ----------

# DBTITLE 1,Cleanup instructions
# MAGIC %md
# MAGIC ## Cleanup (when no longer needed)
# MAGIC
# MAGIC ```python
# MAGIC # Delete endpoint to stop all charges
# MAGIC w.serving_endpoints.delete(ENDPOINT_NAME)
# MAGIC print(f"Deleted endpoint: {ENDPOINT_NAME}")
# MAGIC ```
# MAGIC
# MAGIC ## Cost Summary
# MAGIC
# MAGIC | Component | Cost | Notes |
# MAGIC | --- | --- | --- |
# MAGIC | Serving endpoint (SRTI) | $0.07/DBU | Scale-to-zero enabled — $0 when idle |
# MAGIC | LLM calls (Anthropic) | $0.105/DBU | Only charged per actual token usage |
# MAGIC | Inference table storage | ~$0.02/GB/month | Delta table in mde_dev.test_schema |
# MAGIC
# MAGIC **With scale-to-zero:** You only pay when actually chatting. Cold start is ~30-60 seconds.
# MAGIC
# MAGIC **Without scale-to-zero:** ~$2,400/year baseline for the serving container.