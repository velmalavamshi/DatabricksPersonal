# Databricks notebook source
# DBTITLE 1,Supervisor Agent
# MAGIC %md
# MAGIC # Agent 00 — Supervisor / Orchestrator
# MAGIC
# MAGIC **Purpose:** The central brain of the Multi-Agent Platform. It is the **single entry point** for all user requests — it understands intent, decomposes work, dispatches to specialized agents, validates outputs, and produces unified responses.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Core Responsibilities
# MAGIC
# MAGIC | # | Responsibility | Description |
# MAGIC | --- | --- | --- |
# MAGIC | 1 | **Understand Request & Intent** | Parse the user's natural language input and classify what type of work is needed |
# MAGIC | 2 | **Identify Work Type** | Map intent to agent categories: Feature Delivery, Monitoring, Optimization, Investigation |
# MAGIC | 3 | **Task Decomposition** | Break complex requests into atomic sub-tasks when multiple agents are needed |
# MAGIC | 4 | **Agent Assignment** | Select the most suitable agent(s) for each sub-task based on capability matching |
# MAGIC | 5 | **Multi-Agent Coordination** | Orchestrate multiple agents in sequence or parallel, passing outputs between them |
# MAGIC | 6 | **Output Validation** | Verify agent outputs are complete, relevant, non-empty, and safe (no PII leakage) |
# MAGIC | 7 | **Conflict Resolution** | Reconcile contradictions between agent responses (e.g., Architect vs Cost Optimization) |
# MAGIC | 8 | **Consolidated Response** | Merge multiple agent outputs into a single, coherent final deliverable for the user |
# MAGIC | 9 | **Clarification Requests** | Ask the user targeted questions only when required to proceed safely or accurately |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Additional Operational Duties
# MAGIC
# MAGIC | # | Duty | Description |
# MAGIC | --- | --- | --- |
# MAGIC | 10 | Health Monitoring | Track agent success/failure rates, detect stuck pipelines |
# MAGIC | 11 | Pipeline Tracking | Track feature delivery progress through the agent chain |
# MAGIC | 12 | Smart Routing | If Peer Review rejects → loop back to Data Engineer with feedback |
# MAGIC | 13 | Retry Logic | Auto-retry failed LLM calls with exponential backoff |
# MAGIC | 14 | Gate Enforcement | Block Release Approval unless all prior agents succeeded |
# MAGIC | 15 | Daily Summary | Executive digest of all agent activity |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Data Sources
# MAGIC - `mde_dev.test_schema.agent_call_log` — LLM call audit trail
# MAGIC - `mde_dev.test_schema.agent_outputs` — All generated artifacts
# MAGIC - `system.lakeflow.job_run_timeline` — Workflow execution status
# MAGIC
# MAGIC ## Outputs
# MAGIC - `mde_dev.test_schema.agent_pipeline_status` — Feature delivery tracking
# MAGIC - `mde_dev.test_schema.agent_health_dashboard` — Agent health metrics
# MAGIC - Consolidated response to the user
# MAGIC - Daily summary report

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Core 1-2: Intent understanding and work type classification
# ══════════════════════════════════════════════════════════════════════════════
# CORE RESPONSIBILITY 1 & 2: Intent Understanding + Work Type Classification
# The Supervisor's first job: understand WHAT the user wants and classify it.
# ══════════════════════════════════════════════════════════════════════════════

INTENT_CLASSIFIER_PROMPT = """You are the Supervisor of a 40-agent AI platform for Databricks data engineering.

Your job: Classify the user's request into exactly ONE work type and identify which agents are needed.

## Work Types

1. FEATURE_DELIVERY — New pipeline, table, transformation, report, or integration
   Agents: business_analyst → scope → project_manager → architect → enterprise_standards → data_engineer → data_quality → unit_test → layer_validation → peer_review → deployment

2. INVESTIGATION — Debug a failure, explain behavior, root cause analysis
   Agents: job_failure_triage, view_dependency, source_drift_detector

3. OPTIMIZATION — Improve performance, reduce cost, optimize queries
   Agents: cost_anomaly, cost_optimization, view_dependency

4. GOVERNANCE — Security review, compliance check, documentation
   Agents: security, enterprise_standards, documentation, metadata_lineage

5. MONITORING — Health check, status report, SLA validation
   Agents: observability, medallion_validation, monitoring

6. CODE_GENERATION — Generate specific code without full feature lifecycle
   Agents: enterprise_standards, data_engineer, unit_test, peer_review

7. ARCHITECTURE — Design decisions, HLD/LLD, Medallion patterns, data modeling
   Agents: solution_recommender, solution_architect, lakehouse_architect, data_modeler

8. SOLUTION_SELECTION — What type of artifact to build (table vs view vs dashboard vs Genie Space etc)
   Agents: solution_recommender

9. CLARIFICATION_NEEDED — Request is ambiguous, need more info from user
   Agents: none (ask user)

Respond in JSON:
{
    "work_type": "<one of the 9 types above>",
    "confidence": <0.0-1.0>,
    "agents_needed": ["agent_name1", "agent_name2"],
    "execution_mode": "SEQUENTIAL" or "PARALLEL",
    "clarification_question": null or "<question if work_type is CLARIFICATION_NEEDED>",
    "summary": "<1-sentence description of what the user wants>"
}
"""


def understand_request(user_request: str) -> dict:
    """Core Responsibility 1 & 2: Classify user intent and identify work type."""
    response = call_agent(
        "supervisor",  # Supervisor uses its own registry key for classification
        INTENT_CLASSIFIER_PROMPT,
        f"Classify this user request:\n\n{user_request}",
        temperature=0.1,
        max_tokens=500
    )
    
    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        classification = json.loads(clean)
    except:
        classification = {
            "work_type": "CLARIFICATION_NEEDED",
            "confidence": 0.0,
            "agents_needed": [],
            "execution_mode": "SEQUENTIAL",
            "clarification_question": "I couldn't classify your request. Could you rephrase or provide more detail?",
            "summary": "Unclassifiable request"
        }
    
    return classification


print("✅ Core 1-2: Intent understanding + work type classification loaded")

# COMMAND ----------

# DBTITLE 1,Core 3-4: Task decomposition and agent assignment
# ══════════════════════════════════════════════════════════════════════════════
# CORE RESPONSIBILITY 3 & 4: Task Decomposition + Agent Assignment
# Break complex requests into sub-tasks and assign to best-fit agents.
# ══════════════════════════════════════════════════════════════════════════════

# Agent capability registry — ALL 38 components with TYPE classification
# type: "agent" = LLM reasoning | "tool" = deterministic Python function | "skill" = Supervisor prompt injection
# cost: low = advisory/docs | medium = code/review | high = critical reasoning
#
# TIER 4 REFACTORING (2026-06-04):
# - AGENT: Requires LLM judgment (routing, evaluation, complex reasoning)
# - TOOL:  Deterministic execution (API calls, SQL queries, validations)
# - SKILL: Checklist/audit patterns injected into Supervisor context
#
AGENT_CAPABILITIES = {
    # ── Core Engineering & Triage (AGENTS — require judgment) ─────────────────
    "job_failure_triage":     {"type": "agent", "skills": ["failures", "debugging", "errors", "triage", "root_cause"], "cost": "high"},
    "data_engineer":          {"type": "agent", "skills": ["pyspark", "sql", "dlt", "etl", "pipeline", "code", "merge"], "cost": "high"},
    "view_dependency":        {"type": "agent", "skills": ["views", "performance", "materialization", "dependency_graph"], "cost": "high"},
    "source_drift_detector":  {"type": "agent", "skills": ["schema", "drift", "changes", "compatibility", "source_compare"], "cost": "high"},
    "solution_architect":     {"type": "agent", "skills": ["hld", "lld", "architecture", "design", "data_flow"], "cost": "high"},
    "peer_review":            {"type": "agent", "skills": ["review", "quality", "standards", "refactor", "scoring"], "cost": "high"},
    "data_quality":           {"type": "agent", "skills": ["validation", "expectations", "reconciliation", "profiling"], "cost": "high"},
    "security":               {"type": "agent", "skills": ["rbac", "pii", "gdpr", "masking", "encryption", "access_control"], "cost": "high"},

    # ── Architecture & Modeling (AGENTS — high reasoning) ────────────────────
    "lakehouse_architect":    {"type": "agent", "skills": ["medallion", "domains", "governance", "unity_catalog", "data_mesh"], "cost": "high"},
    "oracle_ebs_specialist":  {"type": "agent", "skills": ["oracle", "ebs", "ap", "ar", "gl", "po", "inv", "om"], "cost": "high"},
    "data_modeler":           {"type": "agent", "skills": ["logical_model", "physical_model", "facts", "dimensions", "star_schema", "bus_matrix", "ddl", "kimball", "conformed_dimensions", "scd"], "cost": "high"},
    "solution_recommender":   {"type": "agent", "skills": ["artifact_selection", "metric_view", "genie_space", "dashboard", "table_vs_view", "cost_benefit", "self_service"], "cost": "high"},

    # ── Monitoring & Validation ──────────────────────────────────────────────
    "cost_anomaly":           {"type": "tool", "skills": ["billing", "anomalies", "idle", "waste", "endpoint_cost"], "cost": "low"},
    "medallion_validation":   {"type": "tool", "skills": ["layers", "freshness", "naming", "integrity", "completeness"], "cost": "low"},
    "platform_reliability":   {"type": "tool", "skills": ["uptime", "sla", "cluster_health", "warehouse_health", "alerts"], "cost": "low"},
    "monitoring":             {"type": "tool", "skills": ["health_check", "dashboards", "metrics", "status_report", "trends"], "cost": "low"},

    # ── Planning & Requirements ──────────────────────────────────────────────
    "business_analyst":       {"type": "agent", "skills": ["requirements", "brd", "user_stories", "acceptance_criteria"], "cost": "low"},
    "scope":                  {"type": "agent", "skills": ["scope", "assumptions", "risks", "constraints", "exclusions"], "cost": "low"},
    "project_manager":        {"type": "agent", "skills": ["planning", "sprints", "roadmap", "milestones", "tracking"], "cost": "low"},
    "azure_devops":           {"type": "tool", "skills": ["work_items", "epics", "backlog", "boards", "repos"], "cost": "low"},

    # ── Testing ──────────────────────────────────────────────────────────────
    "unit_test":              {"type": "agent", "skills": ["pytest", "testing", "mocking", "assertions", "fixtures"], "cost": "medium"},
    "unit_test_documentation":{"type": "skill", "skills": ["test_docs", "coverage_report", "test_plan", "test_matrix"], "cost": "low"},
    "integration_test":       {"type": "agent", "skills": ["e2e_test", "pipeline_test", "data_validation", "regression"], "cost": "medium"},
    "layer_validation":        {"type": "agent", "skills": ["dqx", "nutter", "layer_gate", "dqx_rules", "validation_gate", "promotion_gate", "nutter_fixture", "layer_validation", "silver_gate", "gold_gate"], "cost": "medium"},

    # ── DevOps & Deployment ──────────────────────────────────────────────────
    "environment_promotion":  {"type": "tool", "skills": ["deployment", "promotion", "dev_uat_prd", "migration"], "cost": "low"},
    "cicd":                   {"type": "tool", "skills": ["ci_cd", "github_actions", "azure_pipelines", "build", "release"], "cost": "medium"},
    "deployment":             {"type": "tool", "skills": ["deploy", "rollback", "blue_green", "canary", "release_notes"], "cost": "medium"},
    "dataops":                {"type": "tool", "skills": ["orchestration", "scheduling", "dependencies", "monitoring"], "cost": "medium"},

    # ── Cost & Optimization ──────────────────────────────────────────────────
    "cost_optimization":      {"type": "tool", "skills": ["cost", "cluster", "dbu", "performance", "right_sizing"], "cost": "low"},

    # ── Observability & Lineage ──────────────────────────────────────────────
    "observability":          {"type": "tool", "skills": ["logging", "tracing", "metrics", "alerting", "apm"], "cost": "medium"},
    "metadata_lineage":       {"type": "tool", "skills": ["lineage", "catalog", "provenance", "impact_analysis"], "cost": "medium"},

    # ── Governance & Standards ───────────────────────────────────────────────
    "enterprise_standards":   {"type": "skill", "skills": ["naming", "conventions", "patterns", "anti_patterns", "guardrails"], "cost": "low", "context": "MANDATORY Hologic Standards (corrected 2026-09-22 — the SK rule below was previously backwards and had already leaked xxhash64-keyed SKs into fact_change_order/fact_change_p2p3/platinum_agg_ap_vendor_working_capital in NEXUS_Generated/): (1) COLUMNS = PascalCase-mashed, underscore ONLY right before a final _ID/_SK (e.g. CustomerAccount_SK, InvoiceLine_SK, AccountingDate). (2) SKs = md5(CONCAT_WS('|', keys)) as STRING with _SK suffix — NEVER xxhash64/SHA1/SHA256, that is not and has never been the real Hologic standard. (3) AUDIT COLUMNS for FACTS: dl_rowhash STRING, dl_creation_date_time TIMESTAMP, dl_last_updated_date_time TIMESTAMP. For DIMS: dl_iscurrent BOOLEAN, dl_recordstartdateutc TIMESTAMP, dl_recordenddateutc TIMESTAMP, dl_transform_id INT, dl_rowhash STRING. NEVER use etl_load_datetime/etl_source_system/etl_batch_id. (4) CLUSTER BY AUTO — not PARTITION BY, not explicit columns. (5) TBLPROPERTIES: autoCompact=true, optimizeWrite=true, compression=zstd, deletionVectors=true, rowTracking=true, plus the config.* keys (sk_column_name, nk_column_names, cluster_by, fact_type/dim_type, primary_key, foreign_key, unique_constraints, not_null_constraints, check_constraints) FactProcessor/DimensionProcessor read via SHOW TBLPROPERTIES — include all of them even when a value is empty. (6) PRIMARY KEY constraint on grain SK. (7) Table + column COMMENTs required. (8) Table names: snake_case with fact_/dim_/bridge_/agg_ prefix for Gold/Platinum (stg_ is Bronze only, never a Gold/Platinum table prefix). (9) MEDALLION READ RULE: Gold reads Silver only, Platinum reads Gold only — never stg_*/Bronze from Gold, never Silver from Platinum. (10) New Platinum objects get a _plt suffix (fact_<name>_plt / dim_<name>_plt).", "template_file": "/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/0 - Project Docs/CANONICAL_NOTEBOOK_TEMPLATES.md"},
    "ai_governance":          {"type": "skill", "skills": ["ai_policy", "model_risk", "bias", "fairness", "explainability"], "cost": "low"},
    "release_approval_board": {"type": "skill", "skills": ["approval", "gate", "checklist", "sign_off", "compliance"], "cost": "low"},

    # ── Source-Specific ──────────────────────────────────────────────────────
    "salesforce_sync":        {"type": "agent", "skills": ["salesforce", "sfdc", "cdc", "sync", "systemmodstamp"], "cost": "medium"},
    "hash_migration":         {"type": "agent", "skills": ["md5", "xxhash64", "surrogate_key", "migration", "validation"], "cost": "medium"},

    # ── Databricks Platform Specialists (Agents 64-75) ───────────────────────
    "sdp_specialist":             {"type": "agent", "skills": ["sdp", "dlt", "streaming_table", "materialized_view", "expectations", "auto_cdc", "pipeline"], "cost": "high"},
    "sql_warehouse_specialist":   {"type": "agent", "skills": ["sql_warehouse", "sizing", "auto_stop", "photon", "concurrency", "serverless_sql"], "cost": "medium"},
    "unity_catalog_specialist":   {"type": "agent", "skills": ["unity_catalog", "rbac", "grants", "tags", "column_mask", "row_filter", "abac"], "cost": "high"},
    "mlflow_serving_specialist":  {"type": "agent", "skills": ["mlflow", "model_registry", "serving_endpoint", "ab_routing", "inference_table"], "cost": "high"},
    "ai_bi_dashboard_specialist": {"type": "agent", "skills": ["lakeview", "dashboard", "widgets", "dataset", "filters", "scheduled_refresh"], "cost": "medium"},
    "cluster_management_specialist": {"type": "agent", "skills": ["cluster_policy", "autoscaling", "instance_pool", "spark_config", "idle_termination"], "cost": "medium"},
    "vector_search_specialist":   {"type": "agent", "skills": ["vector_search", "embeddings", "rag", "similarity", "delta_sync_index"], "cost": "high"},
    "notebook_lifecycle_specialist": {"type": "agent", "skills": ["notebook", "git_sync", "template", "archive", "workspace_api"], "cost": "low"},
    "databricks_app_specialist":  {"type": "agent", "skills": ["databricks_app", "app_yaml", "service_principal", "ip_acl", "deploy"], "cost": "medium"},
    "genie_space_specialist":     {"type": "agent", "skills": ["genie", "natural_language", "table_registration", "instructions", "sample_questions"], "cost": "medium"},
    "ai_gateway_specialist":      {"type": "agent", "skills": ["ai_gateway", "rate_limit", "guardrails", "pii", "fallback_routing", "inference_logging"], "cost": "high"},

    # ── Release Intelligence Layer (Agents 77-81) ─────────────────────────────────
    "release_intelligence":       {"type": "agent", "skills": ["release", "update", "patch", "deprecation", "version", "eol", "breaking_change", "vendor_update", "impact_assessment"], "cost": "medium"},
    "oracle_release_monitor":     {"type": "agent", "skills": ["oracle_release", "cpu", "critical_patch", "ebs_patch", "desupport", "oracle_version"], "cost": "medium"},
    "salesforce_release_monitor": {"type": "agent", "skills": ["sfdc_release", "api_version", "seasonal_release", "sfdc_deprecation", "cdc_change"], "cost": "medium"},
    "powerbi_release_monitor":    {"type": "agent", "skills": ["pbi_release", "connector_update", "dax_change", "gateway_update", "fabric"], "cost": "medium"},
    "databricks_release_monitor": {"type": "agent", "skills": ["runtime_eol", "api_deprecation", "dbr_update", "delta_protocol", "model_retirement", "serverless_change"], "cost": "medium"},
    "azure_platform_release_monitor": {"type": "agent", "skills": ["azure_update", "service_retirement", "region_change", "pricing_change", "entra_id", "private_link", "adls"], "cost": "medium"},
    "mulesoft_release_monitor":   {"type": "agent", "skills": ["mulesoft_update", "connector_deprecation", "mule_runtime", "cloudhub", "dataweave", "api_policy"], "cost": "medium"},
    "delta_spark_oss_release_monitor": {"type": "agent", "skills": ["delta_protocol", "spark_4", "merge_behavior", "null_handling", "type_coercion", "ansi_mode", "cdf"], "cost": "medium"},
    "azure_devops_release_monitor": {"type": "agent", "skills": ["ado_update", "pipeline_agent", "yaml_schema", "ado_api", "task_version"], "cost": "low"},
    "python_ecosystem_release_monitor": {"type": "agent", "skills": ["pandas_3", "numpy_2", "pyarrow", "openai_client", "mlflow_3", "library_breaking"], "cost": "medium"},
    "oracle_cloud_release_monitor": {"type": "agent", "skills": ["pbcs", "hcm_cloud", "epm_cloud", "oci_api", "oracle_saas"], "cost": "low"},

    # ── Documentation & Hygiene ──────────────────────────────────────────────
    "documentation":          {"type": "skill", "skills": ["docs", "runbook", "user_guide", "technical", "wiki"], "cost": "low"},
    "documentation_sync":     {"type": "skill", "skills": ["doc_freshness", "stale_docs", "auto_update", "changelog"], "cost": "low"},
    "workspace_hygiene":      {"type": "tool", "skills": ["cleanup", "unused_objects", "orphaned", "naming_audit"], "cost": "low"},
}


def decompose_and_assign(classification: dict, user_request: str) -> list:
    """Core Responsibility 3 & 4: Break into tasks and assign agents."""
    agents_needed = classification.get("agents_needed", [])
    execution_mode = classification.get("execution_mode", "SEQUENTIAL")
    
    tasks = []
    for i, agent_name in enumerate(agents_needed):
        task = {
            "task_id": i + 1,
            "agent_name": agent_name,
            "status": "PENDING",
            "depends_on": [i] if i > 0 and execution_mode == "SEQUENTIAL" else [],
            "input": user_request if i == 0 else f"Output from {agents_needed[i-1]}",
            "output": None,
            "capability": AGENT_CAPABILITIES.get(agent_name, {}).get("skills", []),
        }
        tasks.append(task)
    
    return tasks


# Component type counts for reporting
_type_counts = {}
for _cap in AGENT_CAPABILITIES.values():
    _t = _cap.get("type", "agent")
    _type_counts[_t] = _type_counts.get(_t, 0) + 1

print(f"✅ Core 3-4: Task decomposition + agent assignment loaded")
print(f"   Components: {len(AGENT_CAPABILITIES)} total | Agents: {_type_counts.get('agent', 0)} | Tools: {_type_counts.get('tool', 0)} | Skills: {_type_counts.get('skill', 0)}")

# COMMAND ----------

# DBTITLE 1,Core 5: Multi-agent coordination
# ══════════════════════════════════════════════════════════════════════════════
# CORE RESPONSIBILITY 5: Multi-Agent Coordination
# Orchestrate sequential or parallel agent execution, pass outputs between them.
# ══════════════════════════════════════════════════════════════════════════════

def coordinate_agents(tasks: list, user_request: str) -> list:
    """
    Core Responsibility 5: Execute components in order, routing by type.
    
    TIER 4 ROUTING:
    - AGENT: Call via LLM (full reasoning, uses call_agent)
    - TOOL:  Call Python function directly (no LLM, deterministic)
    - SKILL: Inject context into next agent's prompt (no separate call)
    """
    completed_outputs = {}  # agent_name -> output
    skill_context = []      # Accumulated skill context for injection

    # Gather existing catalog context ONCE per orchestration run.
    # Injected into prompts for catalog-aware agents (_CATALOG_AWARE_AGENTS) so
    # the LLM sees existing dims/facts before proposing new structures.
    catalog_ctx = gather_catalog_context()
    
    for task in tasks:
        agent_name = task["agent_name"]
        component_config = AGENT_CAPABILITIES.get(agent_name, {})
        # AGENT_REGISTRY (from 00_agent_config) is the source of truth for type.
        # AGENT_CAPABILITIES is fallback for any component not yet in AGENT_REGISTRY.
        component_type = (
            AGENT_REGISTRY.get(agent_name, {}).get("type")
            or component_config.get("type", "agent")
        )
        
        task["status"] = "RUNNING"
        type_icon = {"agent": "🧠", "tool": "🛠️", "skill": "📝"}.get(component_type, "▶️")
        print(f"\n{type_icon} Running: {agent_name} [{component_type.upper()}] (Task {task['task_id']})")
        
        # Build input context from prior outputs
        if task["task_id"] == 1:
            agent_input = user_request
        else:
            prior_context = "\n\n---\n\n".join([
                f"## Output from {name}:\n{output[:2000]}"
                for name, output in completed_outputs.items()
            ])
            agent_input = f"""## Original Request:\n{user_request}\n\n## Prior Agent Outputs:\n{prior_context}"""
        
        try:
            # ═══════════════════════════════════════════════════════════════════
            # TIER 4 ROUTING: Branch based on component type
            # ═══════════════════════════════════════════════════════════════════
            
            if component_type == "tool":
                # TOOL: Call deterministic Python function (no LLM)
                tool_fn_name = component_config.get("function", f"tool_{agent_name}")
                if tool_fn_name in globals():
                    output = globals()[tool_fn_name](agent_input, completed_outputs)
                else:
                    # Fallback: tool function not yet implemented, log warning
                    output = f"[TOOL_NOT_IMPLEMENTED] {tool_fn_name} is registered but not yet defined. Returning placeholder."
                    print(f"   ⚠️ Tool function '{tool_fn_name}' not found — define it in a Tools cell")
                
            elif component_type == "skill":
                # SKILL: Accumulate context for injection into next agent (no separate call)
                skill_ctx = component_config.get("context", f"Apply {agent_name} best practices.")
                skill_context.append(f"[{agent_name.upper()}]: {skill_ctx}")
                
                # Load template file if configured (canonical notebook examples)
                template_path = component_config.get("template_file")
                if template_path:
                    try:
                        with open(template_path, "r") as tf:
                            template_content = tf.read()
                        skill_context.append(f"[{agent_name.upper()}_TEMPLATES]:\n{template_content}")
                        print(f"   📄 Template file loaded: {template_path} ({len(template_content)} chars)")
                    except Exception as te:
                        print(f"   ⚠️ Template file not found: {template_path} ({te})")
                
                output = f"[SKILL_INJECTED] {agent_name} context will be included in next agent's prompt."
                print(f"   📌 Skill context accumulated: {skill_ctx[:80]}...")
                
            else:
                # AGENT: Full LLM call with reasoning (original behavior)
                agent_prompt = get_agent_system_prompt(agent_name)
                
                # Inject catalog context (existing dims/facts) for catalog-aware agents
                if agent_name in _CATALOG_AWARE_AGENTS and catalog_ctx:
                    agent_prompt = (
                        f"{agent_prompt}\n\n"
                        "## Existing Catalog Inventory (mde_dev — live scan):\n"
                        "IMPORTANT: Before proposing any new tables, dimensions, or facts, "
                        "review the inventory below. Recommend REUSE or EXTENSION of existing "
                        "objects wherever possible. Only propose NET-NEW builds for gaps not "
                        "covered by existing structures.\n"
                        f"{catalog_ctx}"
                    )

                # Inject any accumulated skill context into the prompt
                if skill_context:
                    injected_skills = "\n".join(skill_context)
                    agent_prompt = f"{agent_prompt}\n\n## Additional Guidelines (from prior skills):\n{injected_skills}"
                    skill_context.clear()  # Reset after injection
                
                # Inject column-level schema for SQL-writing agents (ROOT CAUSE FIX 2026-08-25)
                # Without this, agents know tables EXIST but not their ACTUAL columns,
                # causing hallucinated column names (e.g. Item_ID instead of RcvItem_ID).
                if agent_name in _COLUMN_AWARE_AGENTS:
                    col_ctx = get_column_context_for_request(user_request, completed_outputs)
                    if col_ctx:
                        agent_prompt = (
                            f"{agent_prompt}\n\n"
                            "## Live Column Schema (from information_schema.columns):\n"
                            "IMPORTANT: Use ONLY the column names below when writing SQL against "
                            "these tables. Do NOT invent or guess column names.\n"
                            f"{col_ctx}"
                        )
                
                output = retry_with_backoff(agent_name, agent_prompt, agent_input, max_retries=2)
            
            # ═══════════════════════════════════════════════════════════════════
            # Common: Update task state and save output
            # ═══════════════════════════════════════════════════════════════════
            task["output"] = output
            task["status"] = "COMPLETED"
            task["component_type"] = component_type  # Track type in task for reporting
            completed_outputs[agent_name] = output
            
            output_len = len(output) if output else 0
            print(f"   ✅ {agent_name}: {output_len} chars produced")
            
            # Save intermediate output (skip skill injections)
            if component_type != "skill":
                save_agent_output(agent_name, run_id, "supervised_output", output,
                                {"triggered_by": "supervisor", "task_id": task["task_id"], 
                                 "component_type": component_type})
                                 
        except Exception as e:
            task["status"] = "FAILED"
            task["output"] = f"ERROR: {str(e)}"
            task["component_type"] = component_type
            print(f"   ❌ {agent_name} FAILED: {e}")
    
    return tasks


def get_agent_system_prompt(agent_name: str) -> str:
    """Retrieve the system prompt for a given agent."""
    # Default prompts per agent type (in production, these come from the agent notebooks)
    prompts = {
        # Core Engineering & Triage
        "job_failure_triage": "You are a Platform Engineer at Hologic. Classify job failures by root cause, severity, and recommend actionable fixes with runbook references.",
        "data_engineer": "You are a Principal Data Engineer at Hologic. Generate production-ready PySpark/SQL code following Medallion architecture. MANDATORY STANDARDS: (1) PascalCase-mashed columns, underscore only before a final _ID/_SK (e.g. CustomerAccount_SK, PaymentStatusFlag). (2) SKs = md5(CONCAT_WS('|', keys)) as STRING with _SK suffix — never xxhash64/SHA1/SHA256 (corrected 2026-09-22; do not trust an older memory of this prompt saying xxhash64). (3) Audit columns: FACTS = dl_rowhash, dl_creation_date_time, dl_last_updated_date_time; DIMS = dl_iscurrent, dl_recordstartdateutc, dl_recordenddateutc, dl_transform_id, dl_rowhash. NEVER etl_*. (4) CLUSTER BY AUTO. (5) TBLPROPERTIES: autoCompact, optimizeWrite, zstd, deletionVectors, rowTracking, plus all nine config.* keys FactProcessor/DimensionProcessor read (sk_column_name, nk_column_names, cluster_by, fact_type/dim_type, primary_key, foreign_key, unique_constraints, not_null_constraints, check_constraints) even when a value is empty. (6) PRIMARY KEY + COMMENTs. (7) MEDALLION READ RULE: Gold reads Silver only, Platinum reads Gold only — never read stg_*/Bronze from a Gold view, never Silver from a Platinum view. (8) New Platinum objects get a _plt suffix. NOTEBOOK STRUCTURE: Use the view-first materialization pattern: (a) Widgets cell (deltaSchemaName, deltaTableName, storageAccountEndpoint, catalogName, transformId). (b) Variables cell. (c) %run LakehouseUtilities. (d) spark.catalog.setCurrentCatalog(pCatalogName). (e) CREATE OR REPLACE VIEW with TBLPROPERTIES (config.sk_column_name, config.nk_column_names, config.cluster_by, config.fact_type/dim_type, config.primary_key). (f) FactProcessor or DimensionProcessor instantiation. (g) try/except with LakeOrchestrator.exit_with_status. Reference: CANONICAL_NOTEBOOK_TEMPLATES.md in 0 - Project Docs.",
        "view_dependency": "You are a View Performance Analyst. Map view dependency chains, identify costly stacked views, and recommend materialization strategies.",
        "source_drift_detector": "You are a Schema Compatibility Specialist. Detect upstream schema changes in source systems and assess impact on downstream pipelines.",
        "solution_architect": "You are a Solution Architect. Produce HLD and LLD documents for the Hologic Databricks Lakehouse, incorporating Medallion patterns and enterprise standards.",
        "peer_review": "You are a Senior Code Reviewer at Hologic. Score code 1-10 across quality dimensions with CRITICAL/HIGH/MEDIUM/LOW findings. ENFORCE: PascalCase-mashed columns (_ only before final _ID/_SK), md5(concat_ws('|', ...)) SKs (STRING, _SK suffix — flag xxhash64/sha1/sha256 as CRITICAL; corrected 2026-09-22, this prompt previously flagged the CORRECT md5 pattern as a violation), dl_* audit columns (flag etl_* as CRITICAL violation), CLUSTER BY AUTO (flag PARTITION BY as HIGH), TBLPROPERTIES (autoCompact, optimizeWrite, zstd, deletionVectors, rowTracking, plus all config.* keys), PRIMARY KEY constraints, table/column COMMENTs, medallion read rule (flag Gold reading stg_*/Bronze, or Platinum reading Silver, as CRITICAL), new Platinum objects missing the _plt suffix (flag as HIGH).",
        "data_quality": "You are a Data Quality Engineer. Generate DLT expectations, validation rules, and reconciliation queries for Silver→Gold layer boundaries.",
        "security": "You are a Security Specialist. Review for RBAC compliance, PII exposure, credential leakage, GDPR requirements, and Unity Catalog access control best practices.",

        # Architecture & Modeling
        "lakehouse_architect": "You are a Lakehouse Architect. Design Medallion architecture, data domains, Unity Catalog structure, ingestion patterns, and governance frameworks for Hologic.",
        "oracle_ebs_specialist": "You are an Oracle EBS integration specialist. Map EBS modules (AP, AR, GL, INV, OM, PO) to Lakehouse tables, handle incremental loading via LAST_UPDATE_DATE, and resolve Oracle-specific data patterns.",
        "data_modeler": "You are a Kimball Data Modeler at Hologic. Produce logical and physical models with star schemas, conformed dimensions, bus matrix, and SCD strategies. MANDATORY DDL STANDARDS: PascalCase-mashed columns (_ only before final _ID/_SK), SKs as STRING via md5(CONCAT_WS('|', keys)) with _SK suffix (never xxhash64 — corrected 2026-09-22), audit columns (FACTS: dl_rowhash, dl_creation_date_time, dl_last_updated_date_time; DIMS: dl_iscurrent, dl_recordstartdateutc, dl_recordenddateutc, dl_transform_id, dl_rowhash), CLUSTER BY AUTO, PRIMARY KEY constraints, table/column COMMENTs, TBLPROPERTIES (autoCompact, optimizeWrite, zstd, deletionVectors, rowTracking, plus config.* keys), medallion read rule (Gold reads Silver only, Platinum reads Gold only), new Platinum objects get a _plt suffix.",
        "solution_recommender": "You are a Solution Recommender. Given a business requirement, evaluate 13 Databricks artifact types (Table, View, Metric View, Genie Space, Dashboard, etc.) and recommend the optimal implementation with scored trade-offs.",

        # Monitoring & Validation
        "cost_anomaly": "You are a FinOps Specialist. Identify billing anomalies, idle resources, and waste in Databricks usage by analyzing system.billing.usage joined to list_prices.",
        "medallion_validation": "You are a Medallion Architecture Validator. Check layer integrity, naming conventions, freshness SLAs, and data completeness across Bronze/Silver/Gold/Platinum.",
        "platform_reliability": "You are a Platform Reliability Engineer. Monitor cluster health, warehouse availability, job SLAs, and generate reliability reports.",
        "monitoring": "You are a Monitoring Agent. Produce health dashboards, status reports, and trend analyses for the Hologic data platform.",

        # Planning & Requirements
        "business_analyst": "You are a Senior Business Analyst at Hologic. Produce a BRD with functional/non-functional requirements, user stories, and acceptance criteria from natural language input.",
        "scope": "You are a Technical Scope Manager. Define project scope, assumptions, risks, constraints, exclusions, and T-shirt effort estimates.",
        "project_manager": "You are a Technical Project Manager. Produce sprint plans, milestones, RACI matrices, and track delivery against roadmap.",
        "azure_devops": "You are an Azure DevOps Specialist. Create work items, epics, user stories, and manage backlog in ADO format.",

        # Testing
        "unit_test": "You are a QA Engineer. Generate PyTest test suites with schema, null, uniqueness, referential integrity, and business logic tests.",
        "unit_test_documentation": "You are a Test Documentation Specialist. Produce test plans, coverage matrices, and test result summaries from test suite outputs.",
        "integration_test": "You are an Integration Test Engineer. Design end-to-end pipeline tests, regression suites, and data validation checks across Medallion layers.",

        # DevOps & Deployment
        "environment_promotion": "You are a Deployment Engineer. Produce promotion checklists and migration scripts for DEV→UAT→PRD moves across Unity Catalog environments.",
        "cicd": "You are a CI/CD Engineer. Design build/release pipelines using Azure DevOps or GitHub Actions for Databricks notebooks and libraries.",
        "deployment": "You are a Release Engineer. Manage deployment strategies (blue/green, canary), rollback procedures, and release notes.",
        "dataops": "You are a DataOps Engineer. Design workflow orchestration, scheduling strategies, dependency management, and operational monitoring.",

        # Cost & Optimization
        "cost_optimization": "You are a Cost Optimization Analyst. Identify right-sizing opportunities, cluster policies, auto-scaling improvements, and SKU optimization.",

        # Observability & Lineage
        "observability": "You are an Observability Engineer. Design logging, tracing, metrics, and alerting strategies for data pipelines and platform health.",
        "metadata_lineage": "You are a Metadata & Lineage Specialist. Map data provenance, impact analysis, and Unity Catalog lineage across the Hologic platform.",

        # Governance & Standards
        "enterprise_standards": "You are an Enterprise Standards Guardian. Enforce naming conventions, coding patterns, anti-pattern detection, and architectural guardrails.",
        "ai_governance": "You are an AI Governance Specialist. Review AI/ML implementations for model risk, bias, fairness, explainability, and policy compliance.",
        "release_approval_board": "You are the Release Approval Board. Evaluate readiness gates, verify all predecessor agents completed, and issue APPROVED/BLOCKED/CHANGES_REQUIRED decisions.",

        # Source-Specific
        "salesforce_sync": "You are a Salesforce Integration Specialist. Handle CDC via SystemModstamp, soft deletes, polymorphic relationships, and SFDC-to-Lakehouse sync patterns.",
        "hash_migration": "You are a Surrogate Key Optimization Analyst. A PROPOSED (NOT approved, NOT live) MD5->xxHash64 idea exists in mde_dev.test_schema.hash_migration_analysis (VertiPaq/Power-BI size savings). Corrected 2026-09-22: this is not the current Hologic standard — real production HDA_MDE notebooks all use md5(concat_ws('|', ...)) today, with no active migration underway. Treat any output from this agent as a cost/size proposal for Sameet to evaluate, never as confirmation that xxHash64 is the standard — do NOT let this agent's premise leak into other agents' 'MANDATORY STANDARDS' text (it already had, see CANONICAL_NOTEBOOK_TEMPLATES.md correction note).",

        # Documentation & Hygiene
        "documentation": "You are a Technical Writer. Generate comprehensive runbooks, user guides, API docs, and architectural decision records.",
        "documentation_sync": "You are a Documentation Freshness Monitor. Identify stale docs, auto-generate changelogs, and sync documentation with code changes.",
        "workspace_hygiene": "You are a Workspace Hygiene Auditor. Identify unused objects, orphaned notebooks, naming violations, and cleanup opportunities.",
    }
    return prompts.get(agent_name, f"You are the {agent_name} agent at Hologic. Complete the assigned task professionally following Databricks and Medallion architecture best practices.")


print("✅ Core 5: Multi-agent coordination loaded")

# COMMAND ----------

# DBTITLE 1,Tool functions for deterministic components
# ══════════════════════════════════════════════════════════════════════════════
# TOOL FUNCTIONS — Deterministic Python functions (no LLM)
# These replace agent LLM calls for components marked type="tool"
# ══════════════════════════════════════════════════════════════════════════════
#
# BENEFITS vs Agent LLM calls:
# - No LLM latency (instant execution)
# - No token cost
# - Deterministic output (no hallucination)
# - Easier unit testing
#
# SIGNATURE: tool_xxx(user_input: str, prior_outputs: dict) -> str
# ──────────────────────────────────────────────────────────────────────────────

def tool_cost_anomaly(user_input: str, prior_outputs: dict) -> str:
    """Query system.billing.usage for cost anomalies. No LLM needed."""
    df = spark.sql(f"""
    SELECT 
        u.sku_name,
        u.billing_origin_product,
        u.usage_metadata.endpoint_name,
        SUM(u.usage_quantity) AS dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) AS cost_usd
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.usage_date >= DATEADD(DAY, -7, CURRENT_DATE())
    GROUP BY u.sku_name, u.billing_origin_product, u.usage_metadata.endpoint_name
    HAVING cost_usd > 100
    ORDER BY cost_usd DESC
    LIMIT 20
    """)
    
    result = df.toPandas().to_markdown(index=False)
    return f"## Cost Anomaly Report (Last 7 Days)\n\n{result}\n\n*Generated by tool_cost_anomaly (no LLM)*"


def tool_monitoring(user_input: str, prior_outputs: dict) -> str:
    """Query agent health metrics. No LLM needed."""
    df = spark.sql(f"""
    SELECT 
        agent_name,
        COUNT(*) as total_calls,
        SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
        ROUND(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as success_rate,
        ROUND(AVG(duration_sec), 2) as avg_duration_sec
    FROM {CATALOG}.{SCHEMA}.agent_call_log
    WHERE timestamp >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
    GROUP BY agent_name
    ORDER BY total_calls DESC
    """)
    
    result = df.toPandas().to_markdown(index=False) if df.count() > 0 else "No agent activity in last 24h."
    return f"## Agent Health Report (Last 24h)\n\n{result}\n\n*Generated by tool_monitoring (no LLM)*"


def tool_metadata_lineage(user_input: str, prior_outputs: dict) -> str:
    """Query Unity Catalog lineage. No LLM needed."""
    # Extract table name from input if present
    table_pattern = r'([a-z_]+\.[a-z_]+\.[a-z_]+)'
    import re
    match = re.search(table_pattern, user_input.lower())
    
    if match:
        table_name = match.group(1)
        df = spark.sql(f"""
        SELECT 
            source_table_full_name,
            target_table_full_name,
            source_column_name,
            target_column_name
        FROM system.access.column_lineage
        WHERE target_table_full_name = '{table_name}'
        LIMIT 50
        """)
        result = df.toPandas().to_markdown(index=False) if df.count() > 0 else "No lineage found."
        return f"## Lineage for {table_name}\n\n{result}\n\n*Generated by tool_metadata_lineage (no LLM)*"
    
    return "[TOOL_INFO] Provide a fully qualified table name (catalog.schema.table) for lineage lookup."


def tool_workspace_hygiene(user_input: str, prior_outputs: dict) -> str:
    """List stale notebooks and unused objects. No LLM needed."""
    # Placeholder — in production, query workspace API for unused assets
    return """## Workspace Hygiene Report

| Check | Status | Count |
|-------|--------|-------|
| Notebooks not run in 90d | ⚠️ PENDING | TBD |
| Orphaned tables | ⚠️ PENDING | TBD |
| Naming violations | ⚠️ PENDING | TBD |

*Generated by tool_workspace_hygiene (no LLM) — Full implementation requires workspace API access*"""


# Placeholder stubs for remaining tools (implement as needed)
def tool_medallion_validation(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_medallion_validation — implement layer integrity checks"

def tool_platform_reliability(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_platform_reliability — implement cluster/warehouse health checks"

def tool_azure_devops(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_azure_devops — implement ADO API integration"

def tool_environment_promotion(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_environment_promotion — implement DEV→UAT→PRD checklist"

def tool_cicd(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_cicd — implement pipeline status query"

def tool_deployment(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_deployment — implement deployment checklist"

def tool_dataops(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_dataops — implement workflow status query"

def tool_cost_optimization(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_cost_optimization — implement right-sizing recommendations"

def tool_observability(user_input: str, prior_outputs: dict) -> str:
    return "[TOOL_STUB] tool_observability — implement logging/tracing query"


# Count implemented vs stub tools (inspect source — never execute at load time)
import inspect
_tool_fns = {fn: globals()[fn] for fn in dir() if fn.startswith('tool_') and callable(globals().get(fn))}
_stub_count = sum(1 for f in _tool_fns.values() if '[TOOL_STUB]' in inspect.getsource(f))
_impl_count = len(_tool_fns) - _stub_count
print(f"✅ Tool functions loaded: {len(_tool_fns)} total | {_impl_count} implemented | {_stub_count} stubs")
print(f"   Implemented: tool_cost_anomaly, tool_monitoring, tool_metadata_lineage, tool_workspace_hygiene")
print(f"   Stubs: tool_medallion_validation, tool_platform_reliability, tool_azure_devops,")
print(f"          tool_environment_promotion, tool_cicd, tool_deployment, tool_dataops,")
print(f"          tool_cost_optimization, tool_observability")

# COMMAND ----------

# DBTITLE 1,Core 6-7: Output validation and conflict resolution
# ══════════════════════════════════════════════════════════════════════════════
# CORE RESPONSIBILITY 6 & 7: Output Validation + Conflict Resolution
# Verify agent outputs are complete, relevant, and consistent.
# ══════════════════════════════════════════════════════════════════════════════

def validate_output(agent_name: str, output: str, user_request: str) -> dict:
    """Core Responsibility 6: Validate agent output for completeness and safety."""
    validation = {
        "agent_name": agent_name,
        "is_valid": True,
        "issues": [],
        "quality_score": 10
    }
    
    # Check 1: Non-empty
    if not output or len(output.strip()) < 50:
        validation["is_valid"] = False
        validation["issues"].append("OUTPUT_EMPTY: Agent produced empty or trivial response")
        validation["quality_score"] -= 5
    
    # Check 2: No refusal patterns
    refusal_patterns = ["I cannot", "I'm unable to", "I don't have access", "As an AI"]
    if any(p.lower() in output.lower() for p in refusal_patterns):
        validation["issues"].append("POSSIBLE_REFUSAL: Agent may have declined the task")
        validation["quality_score"] -= 3
    
    # Check 3: PII safety (basic check)
    pii_patterns = ["SSN", "social security", "credit card", "password", "secret_key"]
    if any(p.lower() in output.lower() for p in pii_patterns):
        if agent_name != "security":  # Security agent legitimately discusses PII
            validation["issues"].append("PII_WARNING: Output may contain sensitive data references")
            validation["quality_score"] -= 2
    
    # Check 4: Relevance (does output reference the original request?)
    request_keywords = [w.lower() for w in user_request.split() if len(w) > 4][:5]
    keyword_hits = sum(1 for kw in request_keywords if kw in output.lower())
    if keyword_hits == 0 and len(request_keywords) > 0:
        validation["issues"].append("LOW_RELEVANCE: Output may not address the original request")
        validation["quality_score"] -= 2
    
    # Check 5: Hologic standards (for code outputs)
    # Corrected 2026-09-22: this check previously enforced the WRONG direction on both
    # rules below (flagged correct md5 as a violation, required etl_* instead of dl_*)
    # — see CANONICAL_NOTEBOOK_TEMPLATES.md's correction note for the real-notebook evidence.
    if agent_name == "data_engineer":
        if "xxhash64(" in output.lower() or "sha1(" in output.lower() or "sha256(" in output.lower():
            validation["issues"].append("STANDARDS_VIOLATION: Uses xxHash64/SHA instead of md5 for surrogate keys")
            validation["quality_score"] -= 4
        if "dl_" not in output:
            validation["issues"].append("MISSING_AUDIT: No dl_* audit columns detected")
            validation["quality_score"] -= 2
        if "etl_load_datetime" in output or "etl_source_system" in output or "etl_batch_id" in output:
            validation["issues"].append("STANDARDS_VIOLATION: Uses etl_* audit columns instead of Hologic's dl_* pattern")
            validation["quality_score"] -= 2
    
    validation["is_valid"] = validation["quality_score"] >= 5
    return validation


def resolve_conflicts(tasks: list) -> list:
    """Core Responsibility 7: Resolve contradictions between agent outputs."""
    conflicts = []
    
    # Check for conflicting recommendations
    architect_output = next((t["output"] for t in tasks if t["agent_name"] == "solution_architect" and t["output"]), None)
    cost_output = next((t["output"] for t in tasks if t["agent_name"] == "cost_optimization" and t["output"]), None)
    
    if architect_output and cost_output:
        # Check if architect recommends expensive patterns that cost agent flags
        if "streaming" in architect_output.lower() and "batch" in cost_output.lower():
            conflicts.append({
                "type": "ARCHITECTURE_VS_COST",
                "agent_a": "solution_architect",
                "agent_b": "cost_optimization",
                "description": "Architect recommends streaming but Cost agent suggests batch for savings",
                "resolution": "Present both options to user with cost/benefit trade-off"
            })
    
    # Check peer review vs data engineer
    review_output = next((t["output"] for t in tasks if t["agent_name"] == "peer_review" and t["output"]), None)
    if review_output and "REJECTED" in str(review_output).upper():
        conflicts.append({
            "type": "CODE_REJECTED",
            "agent_a": "data_engineer",
            "agent_b": "peer_review",
            "description": "Peer Review rejected the generated code",
            "resolution": "Re-trigger Data Engineer with peer review feedback"
        })
    
    return conflicts


print("✅ Core 6-7: Output validation + conflict resolution loaded")

# COMMAND ----------

# DBTITLE 1,Core 8-9: Consolidated response and clarification
# ══════════════════════════════════════════════════════════════════════════════
# CORE RESPONSIBILITY 8 & 9: Consolidated Response + Clarification
# Merge multiple agent outputs into a single deliverable.
# ══════════════════════════════════════════════════════════════════════════════

CONSOLIDATION_PROMPT = """You are the Supervisor Agent producing a final consolidated response.

You have multiple agent outputs to merge into ONE coherent deliverable for the user.

Rules:
1. Remove redundancy — don't repeat the same information from different agents
2. Maintain structure — use clear headers for each section
3. Highlight conflicts — if agents disagree, present both views with trade-offs
4. Lead with the answer — put the most important output first
5. Include all code — if code was generated, include the complete final version
6. Add a summary — end with a 3-sentence executive summary

Format as clean markdown suitable for direct use.
"""


def consolidate_response(tasks: list, user_request: str, conflicts: list) -> str:
    """Core Responsibility 8: Merge all agent outputs into one response."""
    
    # Collect successful outputs
    outputs = []
    for task in tasks:
        if task["status"] == "COMPLETED" and task["output"]:
            outputs.append(f"## {task['agent_name']} Output\n\n{task['output']}")
    
    if not outputs:
        return "No agents produced output. Please check agent health or rephrase your request."
    
    # If only one agent, return its output directly (no consolidation needed)
    if len(outputs) == 1:
        return tasks[0]["output"]
    
    # Multiple outputs → LLM consolidation
    conflict_section = ""
    if conflicts:
        conflict_section = "\n\n## Conflicts Detected\n" + "\n".join([
            f"- {c['type']}: {c['description']} → Resolution: {c['resolution']}"
            for c in conflicts
        ])
    
    consolidation_input = f"""## User's Original Request\n{user_request}

## Agent Outputs to Consolidate\n{chr(10).join(outputs[:5])}  # Limit to 5 to stay within token limits
{conflict_section}

Produce the final consolidated response."""
    
    final = call_agent("data_engineer", CONSOLIDATION_PROMPT, consolidation_input, max_tokens=4096)
    return final


def request_clarification(classification: dict) -> str:
    """Core Responsibility 9: Generate a targeted clarification question."""
    question = classification.get("clarification_question")
    if question:
        return f"🤔 **Clarification needed:** {question}"
    return "🤔 **Clarification needed:** Could you provide more detail about what you'd like to accomplish?"


print("✅ Core 8-9: Consolidated response + clarification loaded")

# COMMAND ----------

# DBTITLE 1,Main orchestration loop: process_request()
# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATION LOOP: process_request()
# This is the single entry point. All 9 core responsibilities execute here.
# ══════════════════════════════════════════════════════════════════════════════

def process_request(user_request: str) -> str:
    """
    THE MAIN ENTRY POINT FOR ALL USER REQUESTS.
    
    Executes all 9 core responsibilities:
    1. Understand intent
    2. Classify work type
    3. Decompose into tasks
    4. Assign agents
    5. Coordinate execution
    6. Validate outputs
    7. Resolve conflicts
    8. Consolidate response
    9. Request clarification (if needed)
    
    Args:
        user_request: Natural language request from the user
    
    Returns:
        Final consolidated response string
    """
    global run_id
    run_id = generate_run_id()
    
    print("\n" + "═" * 70)
    print("  SUPERVISOR AGENT — PROCESSING REQUEST")
    print("═" * 70)
    print(f"  Request: {user_request[:100]}{'...' if len(user_request) > 100 else ''}")
    print(f"  Run ID: {run_id}")
    print("═" * 70)
    
    # --- STEP 1 & 2: Understand and classify ---
    print("\n🧠 Step 1-2: Understanding request and classifying work type...")
    classification = understand_request(user_request)
    
    work_type = classification.get("work_type", "CLARIFICATION_NEEDED")
    confidence = classification.get("confidence", 0)
    agents_needed = classification.get("agents_needed", [])
    
    print(f"   Work Type: {work_type} (confidence: {confidence})")
    print(f"   Agents: {agents_needed}")
    print(f"   Mode: {classification.get('execution_mode', 'SEQUENTIAL')}")
    
    # --- STEP 9 (early exit): Clarification needed? ---
    if work_type == "CLARIFICATION_NEEDED" or confidence < 0.5:
        clarification = request_clarification(classification)
        save_agent_output("supervisor", run_id, "clarification", clarification,
                         {"classification": classification})
        return clarification
    
    # --- STEP 3 & 4: Decompose and assign ---
    print("\n🔧 Step 3-4: Decomposing tasks and assigning agents...")
    tasks = decompose_and_assign(classification, user_request)
    print(f"   Tasks created: {len(tasks)}")
    for task in tasks:
        print(f"   [{task['task_id']}] {task['agent_name']} → {task['status']}")
    
    # --- STEP 5: Coordinate agents ---
    print("\n🚀 Step 5: Coordinating agent execution...")
    tasks = coordinate_agents(tasks, user_request)
    
    # --- STEP 6: Validate outputs ---
    print("\n✅ Step 6: Validating agent outputs...")
    validations = []
    for task in tasks:
        if task["status"] == "COMPLETED" and task["output"]:
            v = validate_output(task["agent_name"], task["output"], user_request)
            validations.append(v)
            status_icon = "✅" if v["is_valid"] else "⚠️"
            print(f"   {status_icon} {task['agent_name']}: score={v['quality_score']}/10 | issues={len(v['issues'])}")
    
    # --- STEP 7: Resolve conflicts ---
    print("\n🔀 Step 7: Checking for conflicts...")
    conflicts = resolve_conflicts(tasks)
    if conflicts:
        for c in conflicts:
            print(f"   ⚠️ {c['type']}: {c['description']}")
    else:
        print("   ✅ No conflicts detected")
    
    # --- STEP 8: Consolidate response ---
    print("\n📝 Step 8: Consolidating final response...")
    final_response = consolidate_response(tasks, user_request, conflicts)
    
    # Save final output
    save_agent_output("supervisor", run_id, "final_response", final_response,
                     {"work_type": work_type, "agents_used": agents_needed,
                      "conflicts": len(conflicts), "tasks_completed": sum(1 for t in tasks if t['status'] == 'COMPLETED')})
    
    print("\n" + "═" * 70)
    print("  ✅ SUPERVISOR COMPLETE")
    print(f"  Work Type: {work_type} | Agents: {len(agents_needed)} | Conflicts: {len(conflicts)}")
    print("═" * 70)
    
    return final_response


print("✅ Main orchestration loop loaded")
print("\n🌟 Usage:")
print('   result = process_request("Create a Silver-layer supplier dimension from Oracle EBS")')
print('   result = process_request("Why is job 613621324309790 failing every hour?")')
print('   result = process_request("Optimize our most expensive SQL queries")')

# COMMAND ----------

# DBTITLE 1,Agent health monitoring
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Agent Health Dashboard
# Check success rates, last run times, error patterns
# ══════════════════════════════════════════════════════════════════════════════

LOOKBACK_HOURS = 24

# Health metrics per agent
df_health = spark.sql(f"""
SELECT 
    agent_name,
    COUNT(*) as total_calls,
    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN status LIKE 'ERROR%' THEN 1 ELSE 0 END) as errors,
    ROUND(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as success_rate,
    ROUND(AVG(duration_sec), 2) as avg_duration_sec,
    ROUND(AVG(tokens_in + tokens_out), 0) as avg_tokens,
    MAX(timestamp) as last_run,
    -- Staleness: hours since last successful run
    ROUND(
        (UNIX_TIMESTAMP(CURRENT_TIMESTAMP()) - UNIX_TIMESTAMP(MAX(CASE WHEN status = 'SUCCESS' THEN timestamp END))) / 3600, 1
    ) as hours_since_last_success
FROM {CATALOG}.{SCHEMA}.agent_call_log
WHERE timestamp >= DATEADD(HOUR, -{LOOKBACK_HOURS}, CURRENT_TIMESTAMP())
GROUP BY agent_name
ORDER BY errors DESC, success_rate ASC
""")

# Determine health status per agent
from pyspark.sql import functions as F

df_health_scored = df_health.withColumn(
    "health_status",
    F.when(F.col("success_rate") >= 95, "HEALTHY")
     .when(F.col("success_rate") >= 80, "DEGRADED")
     .when(F.col("success_rate") >= 50, "UNHEALTHY")
     .otherwise("CRITICAL")
).withColumn(
    "action_needed",
    F.when(F.col("health_status") == "CRITICAL", "IMMEDIATE: Check LLM endpoint and system prompt")
     .when(F.col("health_status") == "UNHEALTHY", "INVESTIGATE: Review error patterns in agent_call_log")
     .when(F.col("health_status") == "DEGRADED", "MONITOR: Intermittent failures, may self-resolve")
     .otherwise("None")
)

print(f"📊 Agent Health Dashboard (last {LOOKBACK_HOURS} hours)")
print("=" * 60)
df_health_scored.display()

# COMMAND ----------

# DBTITLE 1,Pipeline tracking for feature delivery
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Feature Delivery Pipeline Tracker
# Track where each feature request is in the agent chain
# ══════════════════════════════════════════════════════════════════════════════

# Define the feature delivery agent sequence
FEATURE_PIPELINE = [
    {"step": 1,  "agent": "business_analyst",    "name": "Business Analyst",      "output_type": "brd"},
    {"step": 2,  "agent": "scope",               "name": "Scope",                 "output_type": "scope_document"},
    {"step": 3,  "agent": "solution_recommender", "name": "Solution Recommender",  "output_type": "solution_recommendation"},
    {"step": 4,  "agent": "project_manager",      "name": "Project Manager",       "output_type": "project_plan"},
    {"step": 5,  "agent": "lakehouse_architect",  "name": "Lakehouse Architect",   "output_type": "lakehouse_design"},
    {"step": 6,  "agent": "data_modeler",         "name": "Data Modeler",          "output_type": "data_model"},
    {"step": 7,  "agent": "solution_architect",   "name": "Solution Architect",    "output_type": "architecture_document"},
    {"step": 8,  "agent": "data_engineer",        "name": "Data Engineer",         "output_type": "generated_code"},
    {"step": 9,  "agent": "data_quality",         "name": "Data Quality",          "output_type": "quality_framework"},
    {"step": 10, "agent": "security",             "name": "Security",              "output_type": "security_review"},
    {"step": 11, "agent": "peer_review",          "name": "Peer Review",           "output_type": "review_report"},
    {"step": 12, "agent": "unit_test",             "name": "Unit Test",             "output_type": "test_suite"},
    {"step": 13, "agent": "layer_validation",      "name": "Layer Validation Gate", "output_type": "gate_report"},
    {"step": 14, "agent": "environment_promotion", "name": "Env Promotion",         "output_type": "promotion_checklist"},
    {"step": 15, "agent": "release_approval_board","name": "Release Approval",      "output_type": "approval_decision"},
]

# Check which agents have produced output in the last 24h (active pipeline)
df_pipeline_status = spark.sql(f"""
SELECT 
    agent_name,
    output_type,
    run_id,
    timestamp,
    LENGTH(content) as output_length,
    metadata
FROM {CATALOG}.{SCHEMA}.agent_outputs
WHERE timestamp >= DATEADD(HOUR, -{LOOKBACK_HOURS}, CURRENT_TIMESTAMP())
ORDER BY timestamp DESC
""")

# Build pipeline progress view
pipeline_progress = []
recent_outputs = {row['agent_name']: row.asDict() for row in df_pipeline_status.collect()}

for step in FEATURE_PIPELINE:
    agent = step["agent"]
    status = "COMPLETED" if agent in recent_outputs else "PENDING"
    last_run = recent_outputs.get(agent, {}).get("timestamp", "Never")
    output_size = recent_outputs.get(agent, {}).get("output_length", 0)
    
    pipeline_progress.append({
        "step": step["step"],
        "agent_name": step["name"],
        "status": status,
        "last_output": str(last_run),
        "output_chars": output_size
    })

df_progress = spark.createDataFrame(pipeline_progress)
print("\n🚀 Feature Delivery Pipeline Status (last 24h)")
print("=" * 60)
df_progress.display()

# COMMAND ----------

# DBTITLE 1,Smart routing and retry logic
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Smart Routing Logic
# Detect rejection/failure and trigger corrective actions
# ══════════════════════════════════════════════════════════════════════════════

import time

# --- ROUTING RULES ---
ROUTING_RULES = {
    "peer_review_rejection": {
        "condition": "Peer Review score < 6 or approval = CHANGES_REQUIRED/REJECTED",
        "action": "Re-trigger Data Engineer with peer review feedback",
        "max_retries": 2
    },
    "llm_call_failure": {
        "condition": "agent_call_log status LIKE 'ERROR%'",
        "action": "Retry with exponential backoff (5s, 15s, 45s)",
        "max_retries": 3
    },
    "empty_output": {
        "condition": "agent_outputs.content is empty or NULL",
        "action": "Retry with increased max_tokens and temperature adjustment",
        "max_retries": 2
    },
    "gate_enforcement": {
        "condition": "Release Approval triggered without all predecessors completed",
        "action": "Block and report which agents are missing",
        "max_retries": 0
    }
}


def check_peer_review_routing():
    """If Peer Review rejected, re-route to Data Engineer with feedback."""
    latest_review = get_latest_agent_output("peer_review", "review_report")
    if not latest_review:
        return None
    
    try:
        review_data = json.loads(latest_review)
        score = review_data.get("score", 10)
        approval = review_data.get("approval", "APPROVED")
        
        if score < 6 or approval in ("CHANGES_REQUIRED", "REJECTED"):
            # Extract feedback for Data Engineer
            findings = review_data.get("findings", [])
            critical_findings = [f for f in findings if f.get("severity") in ("CRITICAL", "HIGH")]
            
            feedback = "\n".join([
                f"- [{f.get('severity')}] {f.get('finding')}: {f.get('recommendation')}"
                for f in critical_findings
            ])
            
            return {
                "action": "REROUTE_TO_DATA_ENGINEER",
                "reason": f"Peer Review score: {score}/10, Approval: {approval}",
                "feedback": feedback,
                "retry_count": 1
            }
    except (json.JSONDecodeError, TypeError):
        pass
    
    return None


def retry_with_backoff(agent_name: str, system_prompt: str, user_prompt: str, 
                       max_retries: int = 3, base_delay: float = 5.0):
    """Retry LLM call with exponential backoff."""
    for attempt in range(max_retries):
        try:
            result = call_agent(agent_name, system_prompt, user_prompt)
            if result and len(result.strip()) > 50:  # non-empty meaningful response
                return result
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (3 ** attempt)  # 5s, 15s, 45s
                print(f"⚠️ Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"❌ All {max_retries} attempts failed for {agent_name}")
                raise
    return None


def check_release_gate():
    """Verify all required agents have completed before allowing release."""
    required_agents = [
        "solution_architect", "data_engineer", "data_quality",
        "unit_test", "layer_validation",
        "security", "peer_review", "environment_promotion"
    ]
    
    missing = []
    for agent in required_agents:
        output = get_latest_agent_output(agent)
        if not output:
            missing.append(agent)
    
    if missing:
        return {
            "gate_status": "BLOCKED",
            "missing_agents": missing,
            "message": f"Release blocked. {len(missing)} agents have not completed: {', '.join(missing)}"
        }
    return {"gate_status": "PASSED", "missing_agents": [], "message": "All gates passed. Ready for release."}


# Execute routing checks
print("🔀 Routing Rules Check")
print("=" * 60)

# Check peer review routing
routing = check_peer_review_routing()
if routing:
    print(f"\n⚠️ REROUTE NEEDED: {routing['reason']}")
    print(f"   Feedback for Data Engineer:\n{routing['feedback'][:300]}")
else:
    print("✅ Peer Review: No rerouting needed")

# Check release gate
gate = check_release_gate()
gate_icon = '✅' if gate['gate_status'] == 'PASSED' else '❌'
print(f"\n{gate_icon} Release Gate: {gate['gate_status']}")
if gate['missing_agents']:
    print(f"   Missing: {', '.join(gate['missing_agents'])}")

# COMMAND ----------

# DBTITLE 1,Trigger downstream agents via Jobs API
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Agent Trigger API
# Programmatically trigger agents via Databricks Jobs REST API
# ══════════════════════════════════════════════════════════════════════════════

import requests

def trigger_agent_notebook(notebook_path: str, parameters: dict = None):
    """Trigger an agent notebook as a one-time run via Jobs API."""
    workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
    token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    
    payload = {
        "run_name": f"Supervisor-triggered: {notebook_path.split('/')[-1]}",
        "existing_cluster_id": spark.conf.get("spark.databricks.clusterUsageTags.clusterId", None),
        "notebook_task": {
            "notebook_path": notebook_path,
            "base_parameters": parameters or {}
        }
    }
    
    # If no cluster, use serverless
    if not payload["existing_cluster_id"]:
        del payload["existing_cluster_id"]
        # Use jobs compute via submit run
    
    response = requests.post(
        f"https://{workspace_url}/api/2.1/jobs/runs/submit",
        headers={"Authorization": f"Bearer {token}"},
        json=payload
    )
    
    if response.status_code == 200:
        run_id = response.json().get("run_id")
        print(f"✅ Triggered: {notebook_path.split('/')[-1]} | Run ID: {run_id}")
        return run_id
    else:
        print(f"❌ Failed to trigger: {response.status_code} - {response.text}")
        return None


# Agent notebook paths — ALL 38 agents
AGENT_BASE_PATH = "/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/1 - Production Agents"

AGENT_NOTEBOOKS = {
    "job_failure_triage":     f"{AGENT_BASE_PATH}/01_job_failure_triage_agent",
    "data_engineer":          f"{AGENT_BASE_PATH}/02_data_engineer_agent",
    "view_dependency":        f"{AGENT_BASE_PATH}/03_view_dependency_agent",
    "source_drift_detector":  f"{AGENT_BASE_PATH}/04_source_drift_detector_agent",
    "cost_anomaly":           f"{AGENT_BASE_PATH}/05_cost_anomaly_agent",
    "solution_architect":     f"{AGENT_BASE_PATH}/06_solution_architect_agent",
    "peer_review":            f"{AGENT_BASE_PATH}/07_peer_review_agent",
    "unit_test":              f"{AGENT_BASE_PATH}/08_unit_test_agent",
    "environment_promotion":  f"{AGENT_BASE_PATH}/09_environment_promotion_agent",
    "medallion_validation":   f"{AGENT_BASE_PATH}/10_medallion_validation_agent",
    "business_analyst":       f"{AGENT_BASE_PATH}/11_business_analyst_agent",
    "scope":                  f"{AGENT_BASE_PATH}/12_scope_agent",
    "project_manager":        f"{AGENT_BASE_PATH}/13_project_manager_agent",
    "azure_devops":           f"{AGENT_BASE_PATH}/14_azure_devops_agent",
    "lakehouse_architect":    f"{AGENT_BASE_PATH}/15_lakehouse_architect_agent",
    "data_quality":           f"{AGENT_BASE_PATH}/16_data_quality_agent",
    "security":               f"{AGENT_BASE_PATH}/17_security_agent",
    "cost_optimization":      f"{AGENT_BASE_PATH}/18_cost_optimization_agent",
    "unit_test_documentation":f"{AGENT_BASE_PATH}/19_unit_test_documentation_agent",
    "integration_test":       f"{AGENT_BASE_PATH}/20_integration_test_agent",
    "observability":          f"{AGENT_BASE_PATH}/21_observability_agent",
    "metadata_lineage":       f"{AGENT_BASE_PATH}/22_metadata_lineage_agent",
    "dataops":                f"{AGENT_BASE_PATH}/23_dataops_agent",
    "cicd":                   f"{AGENT_BASE_PATH}/24_cicd_agent",
    "deployment":             f"{AGENT_BASE_PATH}/25_deployment_agent",
    "platform_reliability":   f"{AGENT_BASE_PATH}/26_platform_reliability_agent",
    "ai_governance":          f"{AGENT_BASE_PATH}/27_ai_governance_agent",
    "enterprise_standards":   f"{AGENT_BASE_PATH}/28_enterprise_standards_agent",
    "documentation":          f"{AGENT_BASE_PATH}/29_documentation_agent",
    "monitoring":             f"{AGENT_BASE_PATH}/30_monitoring_agent",
    "release_approval_board": f"{AGENT_BASE_PATH}/31_release_approval_board_agent",
    "oracle_ebs_specialist":  f"{AGENT_BASE_PATH}/32_oracle_ebs_specialist_agent",
    "salesforce_sync":        f"{AGENT_BASE_PATH}/33_salesforce_sync_agent",
    "hash_migration":         f"{AGENT_BASE_PATH}/34_hash_migration_agent",
    "documentation_sync":     f"{AGENT_BASE_PATH}/35_documentation_sync_agent",
    "workspace_hygiene":      f"{AGENT_BASE_PATH}/36_workspace_hygiene_agent",
    "data_modeler":           f"{AGENT_BASE_PATH}/37_data_modeler_agent",
    "solution_recommender":   f"{AGENT_BASE_PATH}/38_solution_recommender_agent",
}


def run_feature_pipeline(requirement: str, source_tables: str = ""):
    """Trigger the full feature delivery pipeline sequentially."""
    print(f"🚀 Starting Feature Delivery Pipeline")
    print(f"   Requirement: {requirement[:100]}...")
    print("=" * 60)
    
    # Step 1: Business Analyst
    trigger_agent_notebook(AGENT_NOTEBOOKS["business_analyst"], {"requirement": requirement})
    
    # Note: In production, each subsequent step would wait for the prior
    # to complete (via polling run status) before triggering next.
    # For the Workflow approach, use task dependencies instead.
    print("\nℹ️  For sequential execution, use the Feature Delivery Workflow.")
    print("   This function triggers the first agent. The Workflow handles sequencing.")


print("✅ Agent trigger API loaded")
print(f"   Available agents: {len(AGENT_NOTEBOOKS)}")
print(f"   Usage: trigger_agent_notebook(AGENT_NOTEBOOKS['data_engineer'], {{'requirement': '...'}})")

# COMMAND ----------

# DBTITLE 1,STEP 4.5: Workspace Filesystem Utilities (REST API)
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4.5: Workspace Filesystem Utilities
# Access workspace paths via REST API (runs under notebook owner's identity)
# 
# WHY: SQL Warehouse SPs (e.g. eede202e40603750) only have UC catalog-level
# SQL permissions. /Workspace/Users/ paths sit in the Databricks workspace
# layer — a completely separate permission domain. These utilities use the
# notebook runner's PAT token to access workspace paths via REST API.
# ══════════════════════════════════════════════════════════════════════════════

import requests
import base64
import json

# --- Auth context (from notebook runner identity, NOT SQL Warehouse SP) ---
_WS_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
_WS_URL = f"https://{spark.conf.get('spark.databricks.workspaceUrl')}"
_WS_HEADERS = {"Authorization": f"Bearer {_WS_TOKEN}", "Content-Type": "application/json"}


def list_workspace_path(path: str) -> list:
    """
    List contents of a workspace directory.
    Returns list of dicts with keys: path, object_type, object_id, language (if notebook).
    
    Args:
        path: Workspace path, e.g. '/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration'
    
    Returns:
        List of objects in the directory, or empty list if path doesn't exist.
    """
    # Strip /Workspace prefix if present (API uses paths without it)
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/list",
        headers=_WS_HEADERS,
        json={"path": api_path}
    )
    
    if response.status_code == 404:
        return []
    
    response.raise_for_status()
    data = response.json()
    
    return data.get("objects", [])


def read_workspace_file(path: str, format: str = "AUTO") -> str:
    """
    Read a workspace file's content (notebooks, SQL files, Python files, markdown).
    
    Args:
        path: Workspace path to the file
        format: 'SOURCE' for raw text, 'HTML' for rendered, 'AUTO' (default) picks SOURCE
    
    Returns:
        Decoded text content of the file, or error message.
    """
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    export_format = "SOURCE" if format == "AUTO" else format
    
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/export",
        headers=_WS_HEADERS,
        params={"path": api_path, "format": export_format}
    )
    
    if response.status_code == 404:
        return f"[ERROR] Path not found: {path}"
    
    response.raise_for_status()
    data = response.json()
    
    # Content is base64-encoded
    content_b64 = data.get("content", "")
    try:
        return base64.b64decode(content_b64).decode("utf-8")
    except Exception as e:
        return f"[ERROR] Failed to decode content: {e}"


def workspace_path_exists(path: str) -> bool:
    """
    Check if a workspace path exists (file or directory).
    
    Args:
        path: Workspace path to check
    
    Returns:
        True if the path exists, False otherwise.
    """
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/get-status",
        headers=_WS_HEADERS,
        json={"path": api_path}
    )
    
    return response.status_code == 200


def get_workspace_object_info(path: str) -> dict:
    """
    Get metadata about a workspace object (type, language, created_at, modified_at).
    
    Args:
        path: Workspace path
    
    Returns:
        Dict with object metadata, or empty dict if not found.
    """
    api_path = path.replace('/Workspace', '') if path.startswith('/Workspace') else path
    
    response = requests.get(
        f"{_WS_URL}/api/2.0/workspace/get-status",
        headers=_WS_HEADERS,
        json={"path": api_path}
    )
    
    if response.status_code != 200:
        return {}
    
    return response.json()


def list_workspace_recursive(path: str, max_depth: int = 3, _current_depth: int = 0) -> list:
    """
    Recursively list workspace contents up to max_depth.
    Returns flat list of all objects found.
    
    Args:
        path: Starting directory path
        max_depth: Maximum recursion depth (default 3 to avoid runaway)
    
    Returns:
        Flat list of all workspace objects found.
    """
    if _current_depth >= max_depth:
        return []
    
    objects = list_workspace_path(path)
    all_objects = list(objects)
    
    for obj in objects:
        if obj.get("object_type") == "DIRECTORY":
            sub_objects = list_workspace_recursive(
                obj["path"], max_depth, _current_depth + 1
            )
            all_objects.extend(sub_objects)
    
    return all_objects


# --- Validation ---
_test_path = "/Users/sameet.patel@hologic.com"
_exists = workspace_path_exists(_test_path)
print(f"✅ Workspace Filesystem Utilities loaded (REST API)")
print(f"   Identity: Notebook runner token (NOT SQL Warehouse SP)")
print(f"   Base URL: {_WS_URL}")
print(f"   Validation: workspace_path_exists('{_test_path}') = {_exists}")
print(f"")
print(f"   Available functions:")
print(f"     • list_workspace_path(path) — List directory contents")
print(f"     • read_workspace_file(path) — Read file content (base64 decoded)")
print(f"     • workspace_path_exists(path) — Check if path exists")
print(f"     • get_workspace_object_info(path) — Get object metadata")
print(f"     • list_workspace_recursive(path, max_depth=3) — Recursive listing")
print(f"")
print(f"   Example:")
print(f"     files = list_workspace_path('/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration')")
print(f"     content = read_workspace_file('/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/7 - Qlik Migration/4.4.1 Procurement Analytics')")

# COMMAND ----------

# DBTITLE 1,Generate daily executive summary
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Daily Executive Summary
# LLM-generated digest of all agent activity
# ══════════════════════════════════════════════════════════════════════════════

SUPERVISOR_PROMPT = """You are the Supervisor Agent for the Hologic Multi-Agent AI Platform.

You manage 36 specialized agents running on Databricks. Generate a concise daily executive summary.

Provide:
1. PLATFORM STATUS: Overall health (GREEN/YELLOW/RED)
2. AGENT ACTIVITY: Which agents ran, how many calls, success rate
3. KEY FINDINGS: Most important outputs from today's agent runs
4. ISSUES: Any agents failing or degraded
5. ROUTING ACTIONS: Any reroutes or retries triggered
6. COST SUMMARY: Total tokens consumed, estimated cost
7. RECOMMENDATIONS: Actions for the team

Keep it to 1 page. Use bullet points. Be specific with numbers.
"""

run_id = generate_run_id()

# Gather metrics for the summary
try:
    metrics = spark.sql(f"""
    SELECT 
        COUNT(*) as total_calls,
        COUNT(DISTINCT agent_name) as active_agents,
        SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
        SUM(CASE WHEN status LIKE 'ERROR%' THEN 1 ELSE 0 END) as errors,
        ROUND(SUM(tokens_in + tokens_out) / 1000.0, 1) as total_tokens_k,
        ROUND(AVG(duration_sec), 1) as avg_duration,
        COUNT(DISTINCT agent_name) as distinct_agents
    FROM {CATALOG}.{SCHEMA}.agent_call_log
    WHERE timestamp >= DATEADD(HOUR, -{LOOKBACK_HOURS}, CURRENT_TIMESTAMP())
    """).collect()[0]
    
    health_data_str = df_health_scored.toPandas().to_string() if df_health_scored.count() > 0 else "No agent activity."
    gate_status = json.dumps(gate)
    routing_status = json.dumps(routing) if routing else "No routing needed."
    
    user_prompt = f"""Generate the daily executive summary for the Multi-Agent Platform.

## Metrics (Last {LOOKBACK_HOURS} hours)
- Total LLM calls: {metrics['total_calls']}
- Active agents: {metrics['active_agents']}
- Successes: {metrics['successes']}
- Errors: {metrics['errors']}
- Total tokens: {metrics['total_tokens_k']}K
- Avg duration: {metrics['avg_duration']}s

## Agent Health
{health_data_str}

## Release Gate
{gate_status}

## Routing Status
{routing_status}

Generate the executive summary."""
    
    summary = call_agent("data_engineer", SUPERVISOR_PROMPT, user_prompt, max_tokens=2000)
    
    # Save summary
    save_agent_output("supervisor", run_id, "daily_summary", summary,
                      {"total_calls": int(metrics['total_calls']), 
                       "active_agents": int(metrics['active_agents']),
                       "errors": int(metrics['errors'])})
    
    print(summary)
    
except Exception as e:
    print(f"⚠️ Could not generate summary (likely no agent activity yet): {e}")
    print("   Run some agents first, then the Supervisor will have data to summarize.")

print(f"\n✅ Supervisor Agent completed | Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,Save health dashboard to Delta
# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Persist health metrics for trending
# ══════════════════════════════════════════════════════════════════════════════

try:
    # Add timestamp for trending
    df_to_save = df_health_scored.withColumn("snapshot_timestamp", F.current_timestamp())
    
    df_to_save.write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_health_dashboard")
    print(f"✅ Health metrics saved to {CATALOG}.{SCHEMA}.agent_health_dashboard")
except Exception as e:
    # First run — table doesn't exist yet, create it
    try:
        df_to_save.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_health_dashboard")
        print(f"✅ Health dashboard table created: {CATALOG}.{SCHEMA}.agent_health_dashboard")
    except:
        print(f"⚠️ No health data to save (run agents first)")

print(f"\n{'='*60}")
print("  SUPERVISOR AGENT — COMPLETE")
print(f"{'='*60}")
print(f"  Health: Monitored")
print(f"  Pipeline: Tracked")
print(f"  Routing: Checked")
print(f"  Gate: Enforced")
print(f"  Summary: Generated")
print(f"{'='*60}")

# COMMAND ----------

# DBTITLE 1,Register Data Modeler in coordinator prompt
# Extend the coordinator to know about the Data Modeler's system prompt
_orig_prompt_fn = get_agent_system_prompt

def get_agent_system_prompt(agent_name: str) -> str:
    """Extended prompt registry including Data Modeler."""
    if agent_name == "data_modeler":
        return (
            "You are a Senior Data Modeler for Hologic's Databricks Lakehouse. "
            "Design Kimball star schema models (facts + dimensions) for Gold/Platinum layers. "
            "Analyze existing catalog for reusable conformed dimensions. "
            "Use md5(CONCAT_WS('|', cols)) for surrogate keys — never xxhash64 (corrected 2026-09-22; "
            "no active md5->xxhash64 migration is approved or live in production). "
            "Include Liquid Clustering (CLUSTER BY AUTO), Hologic dl_* audit columns (dl_rowhash, "
            "dl_creation_date_time, dl_last_updated_date_time for facts; dl_iscurrent, "
            "dl_recordstartdateutc, dl_recordenddateutc, dl_transform_id, dl_rowhash for dims — "
            "never etl_load_datetime/etl_source_system/etl_batch_id), "
            "full CREATE TABLE DDL, Bus Matrix, and data lineage notes. "
            "Naming: snake_case, fact_/dim_/bridge_ prefixes. "
            "Output format: Reuse Analysis, Logical Model, Physical DDL, Bus Matrix, Lineage."
        )
    return _orig_prompt_fn(agent_name)

print("✅ Data Modeler system prompt registered for Supervisor coordination")

# COMMAND ----------

# DBTITLE 1,Core 10: Agent fleet review and recommendations
# ══════════════════════════════════════════════════════════════════════════════
# CORE RESPONSIBILITY 10: Agent Fleet Review & Recommendations
# Periodically review ALL agents for performance, quality, and improvements.
# ══════════════════════════════════════════════════════════════════════════════

AGENT_REVIEW_PROMPT = """You are the Supervisor Agent performing a periodic fleet review of all agents in the Hologic Multi-Agent AI Platform.

You are reviewing performance metrics, output quality, and operational patterns for each agent.

For each agent, evaluate:
1. PERFORMANCE: Success rate, avg duration, token efficiency
2. OUTPUT QUALITY: Are outputs actionable? Complete? Following Hologic standards?
3. UTILIZATION: Is the agent being used? Over-used? Under-used?
4. PROMPT EFFECTIVENESS: Based on output quality, does the system prompt need refinement?
5. COST EFFICIENCY: Is the agent using the right model tier? Could it use a cheaper model?
6. OVERLAP: Does this agent duplicate another agent's capabilities?
7. GAPS: Is there missing capability that should be added?

For each finding, provide:
- Agent name
- Category (PERFORMANCE | QUALITY | UTILIZATION | PROMPT | COST | OVERLAP | GAP)
- Severity (CRITICAL | HIGH | MEDIUM | LOW | INFO)
- Finding description
- Specific recommendation
- Expected impact (cost savings, quality improvement, etc.)

Respond in JSON:
{
    "review_date": "<date>",
    "total_agents_reviewed": <n>,
    "overall_health": "GREEN | YELLOW | RED",
    "findings": [
        {
            "agent_name": "<name>",
            "category": "<category>",
            "severity": "<severity>",
            "finding": "<description>",
            "recommendation": "<action>",
            "expected_impact": "<impact>"
        }
    ],
    "summary": "<2-3 sentence executive summary>"
}
"""


def review_all_agents(lookback_days: int = 30) -> dict:
    """
    Core Responsibility 10: Review all agents and generate improvement recommendations.
    
    Analyzes:
    - Performance metrics from agent_call_log (success rate, duration, tokens)
    - Output quality from agent_outputs (length, frequency)
    - Cost patterns (model usage, token spend)
    - Agent utilization (which agents are never called?)
    
    Returns: dict with findings and recommendations
    """
    review_run_id = generate_run_id()
    
    print("\n" + "═" * 70)
    print("  SUPERVISOR — AGENT FLEET REVIEW")
    print("═" * 70)
    print(f"  Lookback: {lookback_days} days | Run ID: {review_run_id}")
    print("═" * 70)
    
    # --- Gather performance metrics ---
    print("\n📊 Gathering performance metrics...")
    
    df_metrics = spark.sql(f"""
    SELECT 
        agent_name,
        COUNT(*) as total_calls,
        SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
        SUM(CASE WHEN status LIKE 'ERROR%' THEN 1 ELSE 0 END) as errors,
        ROUND(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as success_rate,
        ROUND(AVG(duration_sec), 2) as avg_duration_sec,
        ROUND(AVG(tokens_in), 0) as avg_tokens_in,
        ROUND(AVG(tokens_out), 0) as avg_tokens_out,
        ROUND(SUM(tokens_in + tokens_out) / 1000.0, 1) as total_tokens_k,
        MAX(timestamp) as last_call,
        MIN(timestamp) as first_call,
        model
    FROM {CATALOG}.{SCHEMA}.agent_call_log
    WHERE timestamp >= DATEADD(DAY, -{lookback_days}, CURRENT_TIMESTAMP())
    GROUP BY agent_name, model
    ORDER BY total_calls DESC
    """)
    
    # --- Gather output quality metrics ---
    print("📋 Gathering output quality metrics...")
    
    df_outputs = spark.sql(f"""
    SELECT
        agent_name,
        COUNT(*) as total_outputs,
        ROUND(AVG(LENGTH(content)), 0) as avg_output_length,
        SUM(CASE WHEN LENGTH(content) < 100 THEN 1 ELSE 0 END) as short_outputs,
        SUM(CASE WHEN content IS NULL OR content = '' THEN 1 ELSE 0 END) as empty_outputs,
        COUNT(DISTINCT output_type) as output_types,
        MAX(timestamp) as last_output
    FROM {CATALOG}.{SCHEMA}.agent_outputs
    WHERE timestamp >= DATEADD(DAY, -{lookback_days}, CURRENT_TIMESTAMP())
    GROUP BY agent_name
    ORDER BY total_outputs DESC
    """)
    
    # --- Identify never-used agents ---
    all_agents = list(AGENT_CAPABILITIES.keys())
    active_agents = [row['agent_name'] for row in df_metrics.collect()]
    never_used = [a for a in all_agents if a not in active_agents]
    
    # --- Build review context for LLM ---
    metrics_str = df_metrics.toPandas().to_string() if df_metrics.count() > 0 else "No metrics available."
    outputs_str = df_outputs.toPandas().to_string() if df_outputs.count() > 0 else "No outputs available."
    
    review_context = f"""## Agent Performance Metrics (last {lookback_days} days)
{metrics_str}

## Agent Output Quality (last {lookback_days} days)
{outputs_str}

## Never-Used Agents (no calls in {lookback_days} days)
{', '.join(never_used) if never_used else 'All agents have been called.'}

## Registered Agents ({len(all_agents)} total)
{', '.join(all_agents)}

## Hologic Standards to Check Against
- Surrogate keys: md5(CONCAT_WS('|', cols)) — never xxhash64 (corrected 2026-09-22)
- Audit columns: dl_* pattern (dl_rowhash, dl_recordstartdateutc, dl_iscurrent, etc.) — never etl_*
- Liquid Clustering (CLUSTER BY AUTO) for new tables
- MERGE pattern for incremental loads (real watermark + dirty-batch, not full recompute)
- Medallion read rule: Gold reads Silver only, Platinum reads Gold only
- Naming convention: snake_case tables, catalog.schema.table, new Platinum objects get _plt
- Cost model: LLM_CRITICAL for Architect/Engineer/Review, LLM_STANDARD for others

Perform the fleet review and produce findings."""
    
    # --- LLM-powered review ---
    print("🧠 Running LLM-powered fleet review...")
    
    try:
        review_result = call_agent(
            "data_engineer",  # Using critical model for this analysis
            AGENT_REVIEW_PROMPT,
            review_context,
            temperature=0.2,
            max_tokens=4096
        )
        
        # Parse JSON response
        clean = review_result.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        
        try:
            review_data = json.loads(clean)
        except json.JSONDecodeError:
            review_data = {
                "review_date": str(datetime.now().date()),
                "total_agents_reviewed": len(all_agents),
                "overall_health": "YELLOW",
                "findings": [],
                "summary": review_result[:500],
                "raw_response": review_result
            }
        
        # --- Display findings ---
        print(f"\n🎯 Fleet Review Complete")
        print(f"   Overall Health: {review_data.get('overall_health', 'UNKNOWN')}")
        print(f"   Agents Reviewed: {review_data.get('total_agents_reviewed', 0)}")
        print(f"   Findings: {len(review_data.get('findings', []))}")
        
        findings = review_data.get('findings', [])
        if findings:
            print("\n" + "-" * 70)
            print("  FINDINGS (sorted by severity)")
            print("-" * 70)
            
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
            sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.get('severity', 'INFO'), 5))
            
            for i, f in enumerate(sorted_findings, 1):
                icon = {
                    "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "🔵"
                }.get(f.get('severity', 'INFO'), "⚪")
                
                print(f"\n  {icon} [{f.get('severity')}] {f.get('agent_name', 'unknown')} — {f.get('category', '')}")
                print(f"     Finding: {f.get('finding', '')}")
                print(f"     Recommendation: {f.get('recommendation', '')}")
                print(f"     Impact: {f.get('expected_impact', '')}")
        
        print(f"\n\n📝 Summary: {review_data.get('summary', 'No summary')}")
        
        # --- Save review to Delta ---
        save_agent_output("supervisor", review_run_id, "fleet_review", json.dumps(review_data, indent=2),
                         {"lookback_days": lookback_days, "agents_reviewed": len(all_agents),
                          "findings_count": len(findings)})
        
        print(f"\n✅ Review saved to agent_outputs (run_id: {review_run_id})")
        return review_data
        
    except Exception as e:
        print(f"❌ Fleet review failed: {e}")
        # Fall back to rule-based review
        return _rule_based_review(df_metrics, df_outputs, never_used)


def _rule_based_review(df_metrics, df_outputs, never_used) -> dict:
    """Fallback: rule-based review without LLM (if LLM call fails)."""
    findings = []
    
    # Rule 1: Flag agents with < 80% success rate
    for row in df_metrics.filter("success_rate < 80").collect():
        findings.append({
            "agent_name": row['agent_name'],
            "category": "PERFORMANCE",
            "severity": "HIGH" if row['success_rate'] < 50 else "MEDIUM",
            "finding": f"Success rate is {row['success_rate']}% ({row['errors']} errors in {row['total_calls']} calls)",
            "recommendation": "Review system prompt for ambiguity. Check if input data is malformed. Consider adding input validation.",
            "expected_impact": "Improved reliability, fewer retries"
        })
    
    # Rule 2: Flag agents with high avg duration (> 60s)
    for row in df_metrics.filter("avg_duration_sec > 60").collect():
        findings.append({
            "agent_name": row['agent_name'],
            "category": "PERFORMANCE",
            "severity": "MEDIUM",
            "finding": f"Average duration is {row['avg_duration_sec']}s — may indicate prompt bloat or large context",
            "recommendation": "Reduce system prompt size. Limit input context. Consider splitting into 2 focused calls.",
            "expected_impact": "Faster execution, lower token cost"
        })
    
    # Rule 3: Flag never-used agents
    for agent in never_used:
        findings.append({
            "agent_name": agent,
            "category": "UTILIZATION",
            "severity": "LOW",
            "finding": f"Agent has never been called in the review period",
            "recommendation": "Verify agent is wired into the correct workflow. Consider if it's still needed or should be merged with another agent.",
            "expected_impact": "Simplified fleet, reduced maintenance"
        })
    
    # Rule 4: Flag agents producing short/empty outputs
    if df_outputs.count() > 0:
        for row in df_outputs.filter("empty_outputs > 0 OR short_outputs > total_outputs * 0.3").collect():
            findings.append({
                "agent_name": row['agent_name'],
                "category": "QUALITY",
                "severity": "HIGH",
                "finding": f"{row['empty_outputs']} empty outputs, {row['short_outputs']} short outputs (<100 chars)",
                "recommendation": "Increase max_tokens. Review if system prompt is too restrictive. Validate input data is being passed correctly.",
                "expected_impact": "Higher output quality, fewer re-runs"
            })
    
    # Rule 5: Flag agents using CRITICAL model for low-complexity tasks
    for row in df_metrics.collect():
        if row['agent_name'] in ('documentation', 'scope', 'project_manager') and row.get('model') == LLM_CRITICAL:
            findings.append({
                "agent_name": row['agent_name'],
                "category": "COST",
                "severity": "MEDIUM",
                "finding": f"Using critical model ({LLM_CRITICAL}) for non-critical tasks",
                "recommendation": f"Switch to LLM_STANDARD or cheaper model (Llama/GPT-OSS). This agent doesn't require highest quality.",
                "expected_impact": "~50-80% cost reduction for this agent's calls"
            })
    
    review_data = {
        "review_date": str(datetime.now().date()),
        "total_agents_reviewed": len(AGENT_CAPABILITIES),
        "overall_health": "GREEN" if len(findings) < 3 else ("YELLOW" if len(findings) < 8 else "RED"),
        "findings": findings,
        "summary": f"Rule-based review found {len(findings)} findings. {len(never_used)} agents are unused."
    }
    
    return review_data


print("✅ Core 10: Agent fleet review & recommendations loaded")
print("\n🌟 Usage:")
print('   review = review_all_agents(lookback_days=30)  # Full fleet review')
print('   review = review_all_agents(lookback_days=7)   # Quick weekly review')