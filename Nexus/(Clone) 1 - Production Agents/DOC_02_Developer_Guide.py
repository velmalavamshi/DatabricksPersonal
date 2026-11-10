# Databricks notebook source
# DBTITLE 1,Developer Guide - Cover
# MAGIC %md
# MAGIC # Hologic Multi-Agent AI Platform — Developer Guide
# MAGIC
# MAGIC **Version:** 1.0  
# MAGIC **Last Updated:** June 2026  
# MAGIC **Audience:** Data Engineers extending or maintaining the platform  
# MAGIC **Platform:** Databricks (Azure) | AI Builder Workspace (4337650355687191)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Document Purpose
# MAGIC
# MAGIC This guide covers the technical internals of the Multi-Agent Platform:
# MAGIC - Architecture decisions and trade-offs
# MAGIC - How to create new agents
# MAGIC - LLM integration patterns
# MAGIC - State management via Delta tables
# MAGIC - Testing and validation
# MAGIC - Performance tuning
# MAGIC - Security considerations

# COMMAND ----------

# DBTITLE 1,Architecture
# MAGIC %md
# MAGIC ## 1. Architecture
# MAGIC
# MAGIC ### Design Principles
# MAGIC
# MAGIC 1. **Databricks-native** — No external infrastructure. All compute, state, and orchestration within Databricks.
# MAGIC 2. **Pay-per-use** — No always-on endpoints for agent logic. Jobs Compute ($0.30/DBU) for execution.
# MAGIC 3. **Auditable** — Every LLM call logged with tokens, duration, and status.
# MAGIC 4. **Idempotent** — Every notebook can be re-run safely (CREATE IF NOT EXISTS, MERGE patterns).
# MAGIC 5. **Modular** — Each agent is an independent notebook. Add/remove without affecting others.
# MAGIC
# MAGIC ### Component Map
# MAGIC
# MAGIC | Component | Implementation | Location |
# MAGIC | --- | --- | --- |
# MAGIC | Shared Config | `00_agent_config` notebook | `%run` by every agent |
# MAGIC | LLM Access | OpenAI-compatible client → Foundation Model APIs | Via AI Gateway ($0.07/DBU) |
# MAGIC | State (logs) | `mde_dev.test_schema.agent_call_log` | Delta table (append-only) |
# MAGIC | State (outputs) | `mde_dev.test_schema.agent_outputs` | Delta table (append-only) |
# MAGIC | Orchestration | Databricks Workflow (multi-task job) | Lakeflow Jobs |
# MAGIC | Scheduling | Cron-based triggers on Workflow | Daily/Weekly/Hourly |
# MAGIC | Secrets | Databricks Secrets scope | Workspace-managed |
# MAGIC
# MAGIC ### Data Flow
# MAGIC
# MAGIC ```
# MAGIC ┌─────────────┐     ┌─────────────────┐     ┌──────────────────────┐
# MAGIC │ System      │     │ Agent Notebook  │     │ Foundation Model    │
# MAGIC │ Tables      │───▶│ (Python logic)  │───▶│ APIs (via Gateway)  │
# MAGIC │ (billing,   │     │                 │     │ Claude Sonnet 4     │
# MAGIC │  lakeflow)  │     │                 │◀───│ (JSON response)     │
# MAGIC └─────────────┘     └────────┬────────┘     └──────────────────────┘
# MAGIC                            │
# MAGIC                     ┌──────▼─────────┐
# MAGIC                     │ Delta Tables    │
# MAGIC                     │ (agent_outputs, │
# MAGIC                     │  agent_call_log)│
# MAGIC                     └────────────────┘
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Creating a New Agent
# MAGIC %md
# MAGIC ## 2. Creating a New Agent
# MAGIC
# MAGIC ### Step-by-Step
# MAGIC
# MAGIC **Step 1: Create the notebook**
# MAGIC
# MAGIC Name it: `XX_your_agent_name` where XX is the next available number.
# MAGIC
# MAGIC **Step 2: Standard structure**
# MAGIC
# MAGIC Every agent notebook MUST have this structure:
# MAGIC
# MAGIC ```python
# MAGIC # Cell 1: Markdown header (purpose, inputs, outputs)
# MAGIC # Cell 2: %run ./00_agent_config
# MAGIC # Cell 3: System prompt definition
# MAGIC # Cell 4: Data gathering (from system tables, user input, or prior agent)
# MAGIC # Cell 5: LLM call via call_agent()
# MAGIC # Cell 6: Save results via save_agent_output()
# MAGIC # Cell 7: Validation
# MAGIC ```
# MAGIC
# MAGIC **Step 3: Register the agent**
# MAGIC
# MAGIC Add to `AGENT_REGISTRY` in `00_agent_config`:
# MAGIC
# MAGIC ```python
# MAGIC AGENT_REGISTRY = {
# MAGIC     ...
# MAGIC     "your_agent_name": {"id": 37, "model": LLM_STANDARD, "priority": "MEDIUM"},
# MAGIC }
# MAGIC ```
# MAGIC
# MAGIC **Step 4: Write the system prompt**
# MAGIC
# MAGIC Guidelines:
# MAGIC - Be specific to Hologic's environment (mention actual schema names, source systems)
# MAGIC - Include output format (JSON for structured, markdown for reports)
# MAGIC - Include constraints (xxHash64, audit columns, naming conventions)
# MAGIC - Keep under 2,000 tokens for the system prompt
# MAGIC
# MAGIC **Step 5: Test interactively**
# MAGIC
# MAGIC Run the notebook manually and verify:
# MAGIC - LLM responds correctly
# MAGIC - Results are saved to `agent_outputs`
# MAGIC - `agent_call_log` shows the call
# MAGIC
# MAGIC **Step 6: Add to Workflow**
# MAGIC
# MAGIC If the agent should run on schedule, add it as a task in the multi-agent Workflow.

# COMMAND ----------

# DBTITLE 1,LLM Integration
# MAGIC %md
# MAGIC ## 3. LLM Integration Patterns
# MAGIC
# MAGIC ### How LLM Calls Work
# MAGIC
# MAGIC ```python
# MAGIC # All agents use this function (defined in 00_agent_config)
# MAGIC result = call_agent(
# MAGIC     agent_name="your_agent",      # Used for logging and registry lookup
# MAGIC     system_prompt=SYSTEM_PROMPT,   # Agent personality and instructions
# MAGIC     user_prompt=user_prompt,       # The specific task/data
# MAGIC     temperature=0.1,               # Low = deterministic, High = creative
# MAGIC     max_tokens=4096                # Max output length
# MAGIC )
# MAGIC ```
# MAGIC
# MAGIC ### Under the Hood
# MAGIC
# MAGIC 1. `call_agent()` looks up the model from `AGENT_REGISTRY`
# MAGIC 2. Creates an OpenAI-compatible client pointing to `https://{workspace}/serving-endpoints`
# MAGIC 3. Sends the request to the Foundation Model API (e.g., `databricks-claude-sonnet-4-6`)
# MAGIC 4. Logs the call (tokens, duration, status) to `agent_call_log`
# MAGIC 5. Returns the raw response text
# MAGIC
# MAGIC ### Token Usage Guidelines
# MAGIC
# MAGIC | Use Case | Input Tokens | Output Tokens | Model |
# MAGIC | --- | --- | --- | --- |
# MAGIC | Classification (Triage) | ~500–1,000 | ~200–500 | Standard |
# MAGIC | Code Generation | ~2,000–5,000 | ~2,000–4,000 | Critical |
# MAGIC | Document Generation | ~1,500–3,000 | ~2,000–4,000 | Standard |
# MAGIC | Review/Validation | ~3,000–5,000 | ~1,000–2,000 | Critical |
# MAGIC
# MAGIC ### Error Handling
# MAGIC
# MAGIC ```python
# MAGIC # call_agent() handles errors internally:
# MAGIC # - Logs ERROR status to agent_call_log
# MAGIC # - Raises the exception for the caller to handle
# MAGIC # - Agents should wrap in try/except with fallback logic
# MAGIC
# MAGIC try:
# MAGIC     result = call_agent(...)
# MAGIC except Exception as e:
# MAGIC     # Log error and provide default output
# MAGIC     results.append({"status": "error", "message": str(e)})
# MAGIC ```
# MAGIC
# MAGIC ### Prompt Engineering Best Practices
# MAGIC
# MAGIC 1. **Be explicit about output format** — "Respond in valid JSON" works better than "format nicely"
# MAGIC 2. **Include Hologic context** — Source systems, naming conventions, architecture patterns
# MAGIC 3. **Limit scope per call** — One task per LLM call, not multiple
# MAGIC 4. **Use temperature 0.1** for deterministic outputs (code, classification)
# MAGIC 5. **Use temperature 0.3–0.5** for creative outputs (documentation, recommendations)

# COMMAND ----------

# DBTITLE 1,State Management
# MAGIC %md
# MAGIC ## 4. State Management
# MAGIC
# MAGIC ### Delta Table Schema
# MAGIC
# MAGIC **`agent_call_log`** — Audit trail (append-only)
# MAGIC ```
# MAGIC timestamp STRING       -- ISO 8601
# MAGIC agent_name STRING      -- Registry key
# MAGIC model STRING           -- LLM model used
# MAGIC tokens_in INT          -- Prompt tokens
# MAGIC tokens_out INT         -- Completion tokens
# MAGIC duration_sec DOUBLE    -- Wall clock time
# MAGIC status STRING          -- SUCCESS or ERROR: <message>
# MAGIC workspace_id STRING    -- Source workspace
# MAGIC ```
# MAGIC
# MAGIC **`agent_outputs`** — All generated artifacts (append-only)
# MAGIC ```
# MAGIC timestamp STRING       -- ISO 8601
# MAGIC agent_name STRING      -- Which agent produced this
# MAGIC run_id STRING          -- Unique run identifier (YYYYMMDD_HHMMSS_hash)
# MAGIC output_type STRING     -- Category (triage_report, generated_code, etc.)
# MAGIC content STRING         -- The actual output (markdown, JSON, code)
# MAGIC metadata STRING        -- JSON metadata about the output
# MAGIC workspace_id STRING    -- Source workspace
# MAGIC ```
# MAGIC
# MAGIC ### Retrieving Outputs
# MAGIC
# MAGIC ```python
# MAGIC # Get latest output from any agent
# MAGIC content = get_latest_agent_output("data_engineer", "generated_code")
# MAGIC
# MAGIC # Chain agents: Peer Review reads Data Engineer's output
# MAGIC code_to_review = get_latest_agent_output("data_engineer", "generated_code")
# MAGIC review = call_agent("peer_review", REVIEW_PROMPT, code_to_review)
# MAGIC ```
# MAGIC
# MAGIC ### Run IDs
# MAGIC
# MAGIC Every agent execution gets a unique `run_id` (format: `20260601_143022_a7b3c4d5`). Use this to:
# MAGIC - Trace all outputs from a single execution
# MAGIC - Correlate LLM calls with their outputs
# MAGIC - Debug issues by filtering logs to a specific run

# COMMAND ----------

# DBTITLE 1,Testing and Security
# MAGIC %md
# MAGIC ## 5. Testing
# MAGIC
# MAGIC ### Unit Testing an Agent
# MAGIC
# MAGIC 1. Run the agent with a known input
# MAGIC 2. Verify the output structure (JSON parsing, required fields)
# MAGIC 3. Check `agent_call_log` for the call record
# MAGIC 4. Check `agent_outputs` for the persisted result
# MAGIC
# MAGIC ### Validation Pattern
# MAGIC
# MAGIC Every agent should end with a validation cell:
# MAGIC ```python
# MAGIC # Verify results were saved
# MAGIC assert spark.sql(f"""
# MAGIC     SELECT COUNT(*) as cnt 
# MAGIC     FROM {CATALOG}.{SCHEMA}.agent_outputs 
# MAGIC     WHERE run_id = '{run_id}'
# MAGIC """).collect()[0]["cnt"] > 0, "No outputs saved!"
# MAGIC ```
# MAGIC
# MAGIC ### Integration Testing
# MAGIC
# MAGIC Run the full feature delivery chain:
# MAGIC ```
# MAGIC Agent 11 (BA) → Agent 12 (Scope) → Agent 13 (PM) → Agent 02 (Engineer) → Agent 07 (Review)
# MAGIC ```
# MAGIC
# MAGIC Verify each agent correctly reads the previous agent's output.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 6. Security
# MAGIC
# MAGIC ### Authentication
# MAGIC
# MAGIC - LLM access uses the notebook's **workspace token** (auto-injected)
# MAGIC - No credentials stored in code — uses `dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken()`
# MAGIC - For Azure DevOps integration: use Databricks Secrets scope
# MAGIC
# MAGIC ### Data Access
# MAGIC
# MAGIC - Agents read system tables (requires `system` catalog access)
# MAGIC - Agents write to `mde_dev.test_schema` (requires INSERT privilege)
# MAGIC - No cross-workspace writes — agents only read cross-workspace system tables
# MAGIC
# MAGIC ### PII Considerations
# MAGIC
# MAGIC - Agent prompts should NEVER include raw PII data
# MAGIC - For HCM/HR data: pass only column names and metadata, never actual values
# MAGIC - LLM responses are logged to `agent_outputs` — ensure this table has appropriate access controls
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 7. Cost Management
# MAGIC
# MAGIC ### Per-Call Costs (Claude Sonnet 4 via Foundation Model APIs)
# MAGIC
# MAGIC | Input Tokens | Output Tokens | Estimated Cost |
# MAGIC | --- | --- | --- |
# MAGIC | 1,000 | 500 | ~$0.003 |
# MAGIC | 5,000 | 3,000 | ~$0.04 |
# MAGIC | 10,000 | 4,000 | ~$0.07 |
# MAGIC
# MAGIC ### Reducing Costs
# MAGIC
# MAGIC 1. **Use GPT-OSS/Llama for non-critical agents** (10x cheaper)
# MAGIC 2. **Cache common outputs** — Don't re-classify the same failure twice
# MAGIC 3. **Limit lookback windows** — 7 days is usually sufficient
# MAGIC 4. **Batch similar requests** — Send multiple items in one prompt where possible
# MAGIC
# MAGIC ### Monitoring Spend
# MAGIC
# MAGIC ```sql
# MAGIC SELECT 
# MAGIC     DATE(timestamp) as day,
# MAGIC     agent_name,
# MAGIC     SUM(tokens_in + tokens_out) as total_tokens,
# MAGIC     -- Rough estimate: $3/M input + $15/M output for Sonnet
# MAGIC     ROUND(SUM(tokens_in) * 3.0 / 1000000 + SUM(tokens_out) * 15.0 / 1000000, 4) as est_llm_cost
# MAGIC FROM mde_dev.test_schema.agent_call_log
# MAGIC WHERE status = 'SUCCESS'
# MAGIC GROUP BY 1, 2 ORDER BY 1 DESC;
# MAGIC ```