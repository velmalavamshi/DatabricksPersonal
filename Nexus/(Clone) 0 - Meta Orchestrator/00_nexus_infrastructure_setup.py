# Databricks notebook source
# DBTITLE 1,NEXUS Infrastructure Setup
# MAGIC %md
# MAGIC # 🏗️ NEXUS — Infrastructure Setup
# MAGIC
# MAGIC **Purpose:** One-click deployment of the entire NEXUS Multi-Agent Platform foundation.  
# MAGIC **Run this ONCE per workspace** to create all required infrastructure.
# MAGIC
# MAGIC ## What This Notebook Creates:
# MAGIC | # | Component | Details |
# MAGIC |---|---|---|
# MAGIC | 1 | Folder Structure | W0, W1, W2, W3, W4 logical workspace folders |
# MAGIC | 2 | Delta Tables (5) | `nexus_agent_events`, `agent_memory` (via shared_token_optimizer), `nexus_agent_registry`, `nexus_agent_trace_log`, `nexus_agent_circuit_breaker` |
# MAGIC | 3 | Secret Scope | `nexus` (Databricks-backed) for all agent credentials |
# MAGIC | 4 | Agent Registry Seed | All 39 W1 Production Agents registered |
# MAGIC | 5 | Circuit Breakers | Initialized to CLOSED for all agents |
# MAGIC
# MAGIC ## Prerequisites:
# MAGIC - `CREATE TABLE` permission on target schema (default: `mde_dev.test_schema`)
# MAGIC - Network access to workspace REST API (for secret scope creation)
# MAGIC
# MAGIC ## Idempotency:
# MAGIC All operations use `IF NOT EXISTS` / `CREATE OR REPLACE` — safe to re-run.

# COMMAND ----------

# DBTITLE 1,STEP 1: Configuration
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — CONFIGURATION
# Edit these values for your target workspace before running
# ══════════════════════════════════════════════════════════════════════════════

import requests
import json
import uuid
from datetime import datetime, timezone
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, LongType, DoubleType, TimestampType

# ── Target Catalog & Schema ─────────────────────────────────────────────────
CATALOG = "mde_dev"
SCHEMA = "test_schema"
TABLE_PREFIX = "nexus_"  # All NEXUS tables prefixed for namespacing

# ── Workspace Folder Root (auto-detected from current user) ───────────────
USER_EMAIL = spark.sql("SELECT current_user()").collect()[0][0]
ROOT_PATH = f"/Workspace/Users/{USER_EMAIL}/5 - Personal Projects/5 - AI Multi Agents"

# ── Logical Workspace Folders ───────────────────────────────────────────────
WORKSPACE_FOLDERS = {
    "W0": "0 - Meta Orchestrator",
    "W1": "1 - Production Agents",
    "W2": "2 - Value Discovery",
    "W3": "3 - Business Champions",
    "W4": "4 - Collective Intelligence",
}

# ── Secret Scope ───────────────────────────────────────────────────────────
SECRET_SCOPE = "nexus"

# ── Owner & Metadata ───────────────────────────────────────────────────────
OWNER = USER_EMAIL
ETL_SOURCE = "NEXUS"
NOW = datetime.now(timezone.utc)

# ── Derived ────────────────────────────────────────────────────────────────
FULL_SCHEMA = f"{CATALOG}.{SCHEMA}"
def tbl(name):
    """Returns fully qualified table name with prefix."""
    return f"{FULL_SCHEMA}.{TABLE_PREFIX}{name}"

print(f"✅ Configuration loaded")
print(f"   Catalog.Schema : {FULL_SCHEMA}")
print(f"   Table prefix   : {TABLE_PREFIX}")
print(f"   Root path      : {ROOT_PATH}")
print(f"   Owner          : {OWNER}")
print(f"   Timestamp      : {NOW.strftime('%Y-%m-%d %H:%M UTC')}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Create Folder Structure
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — CREATE FOLDER STRUCTURE
# Creates the 5 logical workspace folders via Workspace API
# ══════════════════════════════════════════════════════════════════════════════

context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
host = context.apiUrl().get()
token = context.apiToken().get()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def create_folder(path):
    """Creates a workspace folder via REST API. Idempotent (ignores RESOURCE_ALREADY_EXISTS)."""
    resp = requests.post(
        f"{host}/api/2.0/workspace/mkdirs",
        headers=headers,
        json={"path": path}
    )
    if resp.status_code == 200:
        return "created"
    elif "RESOURCE_ALREADY_EXISTS" in resp.text or resp.status_code == 200:
        return "exists"
    else:
        return f"ERROR: {resp.status_code} - {resp.text}"

print("📁 Creating NEXUS folder structure...")
print(f"   Root: {ROOT_PATH}")
print()

for workspace_id, folder_name in WORKSPACE_FOLDERS.items():
    full_path = f"{ROOT_PATH}/{folder_name}"
    result = create_folder(full_path)
    status = "✅" if result in ("created", "exists") else "❌"
    print(f"   {status} {workspace_id}: {folder_name} [{result}]")

print("\n✅ Folder structure complete")

# COMMAND ----------

# DBTITLE 1,STEP 3: Create Delta Tables
# MAGIC %sql
# MAGIC -- ══════════════════════════════════════════════════════════════════════════════
# MAGIC -- STEP 3 — CREATE DELTA INFRASTRUCTURE TABLES
# MAGIC -- All tables use Liquid Clustering, auto-optimize, and full commenting
# MAGIC -- ══════════════════════════════════════════════════════════════════════════════
# MAGIC
# MAGIC -- 3a: Agent Events (Event Bus)
# MAGIC CREATE TABLE IF NOT EXISTS mde_dev.test_schema.nexus_agent_events (
# MAGIC   event_id          STRING        NOT NULL COMMENT 'UUID for the event',
# MAGIC   event_type        STRING        NOT NULL COMMENT 'Event classification (e.g., JOB_FAILURE, DQ_ALERT, BRIEFING_COMPLETE)',
# MAGIC   source_agent      STRING        NOT NULL COMMENT 'Agent that published this event',
# MAGIC   target_agent      STRING        COMMENT 'Specific target agent (NULL = broadcast to subscribers)',
# MAGIC   workspace         STRING        NOT NULL COMMENT 'Logical workspace folder (W0, W1, W2, W3, W4)',
# MAGIC   payload           STRING        NOT NULL COMMENT 'JSON payload with event details',
# MAGIC   priority          STRING        NOT NULL COMMENT 'P1 (critical), P2 (high), P3 (normal)',
# MAGIC   status            STRING        NOT NULL COMMENT 'PUBLISHED | CONSUMED | EXPIRED',
# MAGIC   created_at        TIMESTAMP     NOT NULL COMMENT 'When the event was published',
# MAGIC   consumed_at       TIMESTAMP     COMMENT 'When the event was consumed by target',
# MAGIC   consumed_by       STRING        COMMENT 'Agent that consumed this event',
# MAGIC   run_id            STRING        COMMENT 'Run ID of the publishing agent execution',
# MAGIC   etl_load_datetime TIMESTAMP     NOT NULL COMMENT 'Row insert time',
# MAGIC   etl_source_system STRING        NOT NULL COMMENT 'Source system identifier'
# MAGIC )
# MAGIC USING DELTA
# MAGIC CLUSTER BY (source_agent, created_at)
# MAGIC COMMENT 'NEXUS event bus — pub/sub communication between agents.'
# MAGIC TBLPROPERTIES (
# MAGIC   'delta.enableChangeDataFeed' = 'true',
# MAGIC   'delta.autoOptimize.optimizeWrite' = 'true',
# MAGIC   'delta.autoOptimize.autoCompact' = 'true'
# MAGIC );
# MAGIC
# MAGIC -- 3b: Agent Memory — CONSOLIDATED into shared_token_optimizer
# MAGIC -- The canonical agent_memory table is created by:
# MAGIC --   /5 - AI Multi Agents/shared_token_optimizer
# MAGIC -- All folders inherit it via %run ../shared_token_optimizer
# MAGIC -- Schema: agent_name, memory_key, memory_value, confidence, source_folder,
# MAGIC --         created_at, updated_at, access_count, expires_at
# MAGIC -- 
# MAGIC -- NOTE: The legacy nexus_agent_memory table (created pre-June 2026) is DEPRECATED.
# MAGIC --       Use mde_dev.test_schema.agent_memory instead.
# MAGIC -- DROP TABLE IF EXISTS mde_dev.test_schema.nexus_agent_memory;  -- uncomment to clean up
# MAGIC
# MAGIC -- 3c: Agent Registry (Agent Catalog)
# MAGIC CREATE TABLE IF NOT EXISTS mde_dev.test_schema.nexus_agent_registry (
# MAGIC   agent_name        STRING        NOT NULL COMMENT 'Unique agent identifier (e.g., 39_morning_briefing_agent)',
# MAGIC   agent_number      INT           NOT NULL COMMENT 'Numeric agent ID for ordering',
# MAGIC   workspace         STRING        NOT NULL COMMENT 'Logical workspace folder (W0, W1, W2, W3, W4)',
# MAGIC   layer             STRING        NOT NULL COMMENT 'STRATEGY | SPECIALIST | EXECUTION',
# MAGIC   parent_agents     STRING        COMMENT 'Comma-separated list of parent agent names',
# MAGIC   description       STRING        NOT NULL COMMENT 'One-line purpose description',
# MAGIC   owner             STRING        NOT NULL COMMENT 'Owner email or team name',
# MAGIC   version           STRING        NOT NULL COMMENT 'Semantic version (e.g., 1.0.0)',
# MAGIC   status            STRING        NOT NULL COMMENT 'ACTIVE | PAUSED | DEVELOPMENT | RETIRED',
# MAGIC   notebook_path     STRING        COMMENT 'Full workspace path to the agent notebook',
# MAGIC   capabilities      STRING        COMMENT 'JSON array of capability tags',
# MAGIC   last_run          TIMESTAMP     COMMENT 'Timestamp of most recent execution',
# MAGIC   total_runs        BIGINT        COMMENT 'Total number of executions',
# MAGIC   success_rate      DOUBLE        COMMENT 'Success rate (0.0 to 1.0)',
# MAGIC   avg_latency_ms    DOUBLE        COMMENT 'Average execution time in milliseconds',
# MAGIC   registered_at     TIMESTAMP     NOT NULL COMMENT 'When agent was first registered',
# MAGIC   updated_at        TIMESTAMP     NOT NULL COMMENT 'When registry entry was last modified',
# MAGIC   etl_load_datetime TIMESTAMP     NOT NULL COMMENT 'Row insert time',
# MAGIC   etl_source_system STRING        NOT NULL COMMENT 'Source system identifier'
# MAGIC )
# MAGIC USING DELTA
# MAGIC CLUSTER BY (workspace, layer)
# MAGIC COMMENT 'NEXUS agent registry — catalog of all agents with metadata, status, and performance metrics.'
# MAGIC TBLPROPERTIES (
# MAGIC   'delta.autoOptimize.optimizeWrite' = 'true',
# MAGIC   'delta.autoOptimize.autoCompact' = 'true'
# MAGIC );
# MAGIC
# MAGIC -- 3d: Agent Trace Log (Execution Telemetry)
# MAGIC CREATE TABLE IF NOT EXISTS mde_dev.test_schema.nexus_agent_trace_log (
# MAGIC   trace_id          STRING        NOT NULL COMMENT 'UUID for this trace entry',
# MAGIC   run_id            STRING        NOT NULL COMMENT 'Execution run ID (groups all traces in one agent run)',
# MAGIC   agent_name        STRING        NOT NULL COMMENT 'Agent that produced this trace',
# MAGIC   workspace         STRING        NOT NULL COMMENT 'Logical workspace folder (W0, W1, W2, W3, W4)',
# MAGIC   step_name         STRING        COMMENT 'Specific step within the agent',
# MAGIC   tokens_in         INT           COMMENT 'Input tokens consumed (LLM calls)',
# MAGIC   tokens_out        INT           COMMENT 'Output tokens generated (LLM calls)',
# MAGIC   latency_ms        BIGINT        NOT NULL COMMENT 'Execution time in milliseconds',
# MAGIC   status            STRING        NOT NULL COMMENT 'SUCCESS | WARNING | FAILED | TIMEOUT',
# MAGIC   quality_score     DOUBLE        COMMENT 'Self-assessed quality (0.0 to 1.0)',
# MAGIC   error_message     STRING        COMMENT 'Error details if status is FAILED',
# MAGIC   metadata          STRING        COMMENT 'JSON with additional trace context',
# MAGIC   created_at        TIMESTAMP     NOT NULL COMMENT 'When this trace was recorded',
# MAGIC   etl_load_datetime TIMESTAMP     NOT NULL COMMENT 'Row insert time',
# MAGIC   etl_source_system STRING        NOT NULL COMMENT 'Source system identifier'
# MAGIC )
# MAGIC USING DELTA
# MAGIC CLUSTER BY (agent_name, created_at)
# MAGIC COMMENT 'NEXUS agent execution traces — detailed logging for observability, cost tracking, and performance tuning.'
# MAGIC TBLPROPERTIES (
# MAGIC   'delta.autoOptimize.optimizeWrite' = 'true',
# MAGIC   'delta.autoOptimize.autoCompact' = 'true'
# MAGIC );
# MAGIC
# MAGIC -- 3e: Agent Circuit Breaker (Health State Machine)
# MAGIC CREATE TABLE IF NOT EXISTS mde_dev.test_schema.nexus_agent_circuit_breaker (
# MAGIC   agent_name        STRING        NOT NULL COMMENT 'Agent this circuit breaker monitors',
# MAGIC   workspace         STRING        NOT NULL COMMENT 'Logical workspace folder (W0, W1, W2, W3, W4)',
# MAGIC   state             STRING        NOT NULL COMMENT 'CLOSED (healthy) | OPEN (paused) | HALF_OPEN (testing)',
# MAGIC   failure_count     INT           NOT NULL COMMENT 'Consecutive failures since last reset',
# MAGIC   failure_threshold INT           NOT NULL COMMENT 'Number of failures before OPEN (default: 3)',
# MAGIC   cooldown_minutes  INT           NOT NULL COMMENT 'Minutes to wait before HALF_OPEN test (default: 30)',
# MAGIC   last_failure_at   TIMESTAMP     COMMENT 'Timestamp of most recent failure',
# MAGIC   last_failure_msg  STRING        COMMENT 'Error message from most recent failure',
# MAGIC   opened_at         TIMESTAMP     COMMENT 'When circuit was opened (paused)',
# MAGIC   half_open_at      TIMESTAMP     COMMENT 'When circuit entered half-open test state',
# MAGIC   reset_at          TIMESTAMP     COMMENT 'When circuit was last reset to CLOSED',
# MAGIC   updated_at        TIMESTAMP     NOT NULL COMMENT 'When this record was last modified',
# MAGIC   etl_load_datetime TIMESTAMP     NOT NULL COMMENT 'Row insert time',
# MAGIC   etl_source_system STRING        NOT NULL COMMENT 'Source system identifier'
# MAGIC )
# MAGIC USING DELTA
# MAGIC CLUSTER BY (agent_name)
# MAGIC COMMENT 'NEXUS circuit breaker — 3 consecutive failures in 1 hour = OPEN (agent paused). After 30 min = HALF_OPEN (1 test run).'
# MAGIC TBLPROPERTIES (
# MAGIC   'delta.autoOptimize.optimizeWrite' = 'true',
# MAGIC   'delta.autoOptimize.autoCompact' = 'true'
# MAGIC );

# COMMAND ----------

# DBTITLE 1,STEP 4: Create Secret Scope
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — CREATE SECRET SCOPE
# Databricks-backed scope for all NEXUS agent credentials
# ══════════════════════════════════════════════════════════════════════════════

resp = requests.post(
    f"{host}/api/2.0/secrets/scopes/create",
    headers=headers,
    json={"scope": SECRET_SCOPE, "scope_backend_type": "DATABRICKS"}
)

if resp.status_code == 200:
    print(f"✅ Created '{SECRET_SCOPE}' secret scope")
elif "RESOURCE_ALREADY_EXISTS" in resp.text or resp.status_code == 409:
    print(f"✅ Secret scope '{SECRET_SCOPE}' already exists")
else:
    print(f"⚠️  Could not create scope: {resp.status_code} - {resp.text}")
    print("   Admin action needed: databricks secrets create-scope nexus")

# Document required secrets (not populated here — that's manual)
print(f"\n🔑 Required secrets for scope '{SECRET_SCOPE}':")
required_secrets = [
    ("TEAMS_WEBHOOK_URL", "Microsoft Teams Incoming Webhook URL"),
    ("SENDGRID_API_KEY", "SendGrid API key for email delivery"),
    ("AZURE_DEVOPS_TOKEN", "ADO Personal Access Token (Work Items read)"),
    ("AZURE_DEVOPS_ORG_URL", "ADO org URL (https://dev.azure.com/your-org)"),
    ("AZURE_DEVOPS_PROJECT", "ADO project name"),
]
for key, desc in required_secrets:
    print(f"   • {key} — {desc}")
print("\n   Populate via: dbutils.secrets.put(scope='nexus', key='KEY', string_value='VALUE')")
print("   Or CLI: databricks secrets put-secret nexus KEY")

# COMMAND ----------

# DBTITLE 1,STEP 5: Seed Agent Registry
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — SEED AGENT REGISTRY
# Registers all W1 Production Agents (idempotent via MERGE)
# ══════════════════════════════════════════════════════════════════════════════

W1_BASE = f"{ROOT_PATH}/{WORKSPACE_FOLDERS['W1']}"

# (agent_number, agent_name, layer, parent_agents, description)
W1_AGENTS = [
    (0,  "00_supervisor_agent",              "STRATEGY",   None, "Master W1 orchestrator — routes requests across all registered agents"),
    (1,  "01_job_failure_triage_agent",      "EXECUTION",  "00_supervisor_agent", "Detects, classifies, and triages job failures"),
    (2,  "02_data_engineer_agent",           "EXECUTION",  "00_supervisor_agent", "PySpark, DLT, Workflows pipeline building"),
    (3,  "03_view_dependency_agent",         "EXECUTION",  "02_data_engineer_agent", "Maps view and table dependencies"),
    (4,  "04_source_drift_detector_agent",   "EXECUTION",  "02_data_engineer_agent", "Schema and data drift detection"),
    (5,  "05_cost_anomaly_agent",            "EXECUTION",  "00_supervisor_agent", "DBU cost spike detection and alerting"),
    (6,  "06_solution_architect_agent",      "STRATEGY",   "00_supervisor_agent", "HLD, LLD, architecture decisions"),
    (7,  "07_peer_review_agent",             "EXECUTION",  "06_solution_architect_agent", "Code review and SOLID principles"),
    (8,  "08_unit_test_agent",               "EXECUTION",  "02_data_engineer_agent", "PyTest, Chispa unit test generation"),
    (9,  "09_environment_promotion_agent",   "EXECUTION",  "23_dataops_agent", "Dev to Staging to Prod promotion"),
    (10, "10_medallion_validation_agent",    "EXECUTION",  "02_data_engineer_agent", "Bronze/Silver/Gold integrity validation"),
    (11, "11_business_analyst_agent",        "STRATEGY",   "00_supervisor_agent", "BRD, user stories, acceptance criteria"),
    (12, "12_scope_agent",                   "EXECUTION",  "11_business_analyst_agent", "Scope documents, risk registers"),
    (13, "13_project_manager_agent",         "EXECUTION",  "11_business_analyst_agent", "Sprint planning, RACI, roadmaps"),
    (14, "14_azure_devops_agent",            "EXECUTION",  "13_project_manager_agent", "ADO work items, sprints, backlog"),
    (15, "15_lakehouse_architect_agent",     "SPECIALIST", "06_solution_architect_agent", "Medallion design, Unity Catalog governance"),
    (16, "16_data_quality_agent",            "EXECUTION",  "02_data_engineer_agent", "DQ rules, constraints, Great Expectations"),
    (17, "17_security_agent",                "EXECUTION",  "00_supervisor_agent", "RBAC, PII masking, GDPR/CCPA"),
    (18, "18_cost_optimization_agent",       "EXECUTION",  "05_cost_anomaly_agent", "Cluster right-sizing, OPTIMIZE, VACUUM"),
    (19, "19_unit_test_documentation_agent", "EXECUTION",  "08_unit_test_agent", "Test case documents, coverage reporting"),
    (20, "20_integration_test_agent",        "EXECUTION",  "08_unit_test_agent", "End-to-end pipeline integration tests"),
    (21, "21_observability_agent",           "EXECUTION",  "00_supervisor_agent", "Alerting, runbooks, monitoring dashboards"),
    (22, "22_metadata_lineage_agent",        "EXECUTION",  "15_lakehouse_architect_agent", "Column lineage, business glossary"),
    (23, "23_dataops_agent",                 "EXECUTION",  "00_supervisor_agent", "Git strategy, environment promotion"),
    (24, "24_cicd_agent",                    "EXECUTION",  "23_dataops_agent", "Azure Pipelines YAML, GitHub Actions"),
    (25, "25_deployment_agent",              "EXECUTION",  "24_cicd_agent", "Deployment guides, rollback procedures"),
    (26, "26_platform_reliability_agent",    "EXECUTION",  "00_supervisor_agent", "DR planning, RTO/RPO, backup"),
    (27, "27_ai_governance_agent",           "EXECUTION",  "17_security_agent", "Hallucination validation, AI risk"),
    (28, "28_enterprise_standards_agent",    "EXECUTION",  "06_solution_architect_agent", "Naming conventions, compliance"),
    (29, "29_documentation_agent",           "EXECUTION",  "00_supervisor_agent", "Auto-generates pipeline documentation"),
    (30, "30_monitoring_agent",              "EXECUTION",  "21_observability_agent", "Production monitoring, SLA tracking"),
    (31, "31_release_approval_board_agent",  "EXECUTION",  "25_deployment_agent", "Final production gate approval"),
    (32, "32_oracle_ebs_specialist_agent",   "SPECIALIST", "02_data_engineer_agent", "Oracle EBS integration specialist"),
    (33, "33_salesforce_sync_agent",         "SPECIALIST", "02_data_engineer_agent", "Salesforce data sync"),
    (34, "34_hash_migration_agent",          "EXECUTION",  "02_data_engineer_agent", "Hash migration validation (MD5 to xxHash64)"),
    (35, "35_documentation_sync_agent",      "EXECUTION",  "29_documentation_agent", "Docs sync with code changes"),
    (36, "36_workspace_hygiene_agent",       "EXECUTION",  "00_supervisor_agent", "Cleans stale notebooks and clusters"),
    (37, "37_data_modeler_agent",            "SPECIALIST", "15_lakehouse_architect_agent", "Auto-generates Kimball star schema models"),
    (38, "38_solution_recommender_agent",    "STRATEGY",   "06_solution_architect_agent", "Recommends architectural solutions"),
    (76, "76_layer_validation_agent",         "EXECUTION",  "16_data_quality_agent",       "Silver/Gold/Platinum DQX + Nutter gate — PASS/WARN/FAIL before Agent 31"),
]

# Check if registry already has data
existing_count = spark.sql(f"SELECT COUNT(*) as cnt FROM {tbl('agent_registry')}").collect()[0][0]

if False:  # Replaced by idempotent MERGE below — safe to re-run at any time
    pass
else:
    # Build DataFrame
    data = []
    for agent_num, agent_name, layer, parent, description in W1_AGENTS:
        data.append((
            agent_name, agent_num, 'W1', layer, parent, description,
            OWNER, '1.0.0', 'ACTIVE', f'{W1_BASE}/{agent_name}',
            None, None, 0, None, None, NOW, NOW, NOW, ETL_SOURCE
        ))

    schema = StructType([
        StructField("agent_name", StringType(), False),
        StructField("agent_number", IntegerType(), False),
        StructField("workspace", StringType(), False),
        StructField("layer", StringType(), False),
        StructField("parent_agents", StringType(), True),
        StructField("description", StringType(), False),
        StructField("owner", StringType(), False),
        StructField("version", StringType(), False),
        StructField("status", StringType(), False),
        StructField("notebook_path", StringType(), True),
        StructField("capabilities", StringType(), True),
        StructField("last_run", TimestampType(), True),
        StructField("total_runs", LongType(), True),
        StructField("success_rate", DoubleType(), True),
        StructField("avg_latency_ms", DoubleType(), True),
        StructField("registered_at", TimestampType(), False),
        StructField("updated_at", TimestampType(), False),
        StructField("etl_load_datetime", TimestampType(), False),
        StructField("etl_source_system", StringType(), False),
    ])

    df = spark.createDataFrame(data, schema=schema)
    # Idempotent MERGE: inserts new agents, updates descriptions for existing ones
    df.createOrReplaceTempView("_w1_agents_seed")
    spark.sql(f"""
        MERGE INTO {tbl('agent_registry')} AS target
        USING _w1_agents_seed AS source
        ON target.agent_name = source.agent_name
        WHEN MATCHED THEN UPDATE SET
            description   = source.description,
            layer         = source.layer,
            parent_agents = source.parent_agents,
            updated_at    = source.updated_at
        WHEN NOT MATCHED THEN INSERT *
    """)
    final_count = spark.sql(f"SELECT COUNT(*) as cnt FROM {tbl('agent_registry')}").collect()[0][0]
    print(f"✅ Agent registry synced via MERGE — {final_count} agents registered")

# COMMAND ----------

# DBTITLE 1,STEP 6: Initialize Circuit Breakers
# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — INITIALIZE CIRCUIT BREAKERS
# Every registered agent gets a CLOSED circuit breaker
# ══════════════════════════════════════════════════════════════════════════════

existing_cb = spark.sql(f"SELECT COUNT(*) as cnt FROM {tbl('agent_circuit_breaker')}").collect()[0][0]

if existing_cb >= len(W1_AGENTS):
    print(f"✅ Circuit breakers already initialized ({existing_cb} records) — skipping")
else:
    spark.sql(f"""
        INSERT INTO {tbl('agent_circuit_breaker')}
        SELECT
            agent_name,
            workspace,
            'CLOSED' as state,
            0 as failure_count,
            3 as failure_threshold,
            30 as cooldown_minutes,
            NULL as last_failure_at,
            NULL as last_failure_msg,
            NULL as opened_at,
            NULL as half_open_at,
            CURRENT_TIMESTAMP() as reset_at,
            CURRENT_TIMESTAMP() as updated_at,
            CURRENT_TIMESTAMP() as etl_load_datetime,
            'NEXUS' as etl_source_system
        FROM {tbl('agent_registry')}
        WHERE agent_name NOT IN (SELECT agent_name FROM {tbl('agent_circuit_breaker')})
    """)
    final_cb = spark.sql(f"SELECT COUNT(*) as cnt FROM {tbl('agent_circuit_breaker')}").collect()[0][0]
    print(f"✅ Circuit breakers initialized — {final_cb} agents in CLOSED state")

# COMMAND ----------

# DBTITLE 1,STEP 7: Validation
# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — VALIDATION
# Confirms all infrastructure was created successfully
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "─" * 60)
print("📊 NEXUS INFRASTRUCTURE VALIDATION")
print("─" * 60)

all_passed = True

# Check tables exist
# Note: agent_memory is managed by shared_token_optimizer (no nexus_ prefix)
expected_tables = ['agent_events', 'agent_registry', 'agent_trace_log', 'agent_circuit_breaker']
for table_name in expected_tables:
    try:
        count = spark.sql(f"SELECT COUNT(*) as cnt FROM {tbl(table_name)}").collect()[0][0]
        print(f"  ✅ {tbl(table_name)} — {count} rows")
    except Exception as e:
        print(f"  ❌ {tbl(table_name)} — MISSING: {e}")
        all_passed = False

# Check folder structure
print()
for wid, folder in WORKSPACE_FOLDERS.items():
    folder_path = f"{ROOT_PATH}/{folder}"
    # Use workspace API to check
    resp = requests.get(
        f"{host}/api/2.0/workspace/get-status",
        headers=headers,
        params={"path": folder_path}
    )
    if resp.status_code == 200:
        print(f"  ✅ {wid}: {folder}")
    else:
        print(f"  ❌ {wid}: {folder} — NOT FOUND")
        all_passed = False

# Check secret scope
print()
scopes = [s.name for s in dbutils.secrets.listScopes()]
if SECRET_SCOPE in scopes:
    print(f"  ✅ Secret scope: '{SECRET_SCOPE}'")
else:
    print(f"  ❌ Secret scope: '{SECRET_SCOPE}' — NOT FOUND")
    all_passed = False

# Summary
print()
print("─" * 60)
if all_passed:
    print("✅ ALL CHECKS PASSED — NEXUS infrastructure is ready!")
    print()
    print("Next steps:")
    print("  1. Populate secrets: dbutils.secrets.put('nexus', 'KEY', string_value='...')")
    print("  2. Deploy Agent 39 (Morning Briefing) to W1")
    print("  3. Create Databricks Workflow for scheduled agents")
else:
    print("❌ SOME CHECKS FAILED — review errors above")

print("─" * 60)

# COMMAND ----------

# DBTITLE 1,NEXUS Architecture Diagram (PPT-ready)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ── Hologic brand colors ─────────────────────────────────────────────────────
DARK_BLUE = '#1B2A4A'
TEAL = '#16A085'
BLUE = '#3498DB'
RED = '#E74C3C'
GREEN = '#27AE60'
ORANGE = '#F39C12'
PURPLE = '#8E44AD'
LIGHT_GRAY = '#F8F9FA'
MID_GRAY = '#ECF0F1'
DARK_GRAY = '#2C3E50'
GOLD = '#F1C40F'

fig, ax = plt.subplots(1, 1, figsize=(16, 11))
ax.set_xlim(0, 16)
ax.set_ylim(0, 11)
ax.axis('off')
fig.patch.set_facecolor('white')

# ── Title ────────────────────────────────────────────────────────────────────
ax.text(8, 10.6, 'NEXUS Multi-Agent Platform', fontsize=20, fontweight='bold',
        ha='center', va='center', color=DARK_BLUE, fontfamily='sans-serif')
ax.text(8, 10.2, 'Token-Optimized Architecture · 88 Agents (79 Built + 9 Planned) · 5 Folders · Single Delta State',
        fontsize=10, ha='center', va='center', color='#666', fontfamily='sans-serif')

# ── Helper: draw a rounded box ───────────────────────────────────────────────
def draw_box(x, y, w, h, color, label, sublabel=None, fontsize=9, alpha=0.15, border_alpha=0.8):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                         facecolor=color, alpha=alpha, edgecolor=color,
                         linewidth=2, mutation_scale=0.5)
    box.set_alpha(alpha)
    box.set_edgecolor((*plt.cm.colors.to_rgba(color)[:3], border_alpha))
    ax.add_patch(box)
    ax.text(x + w/2, y + h/2 + (0.12 if sublabel else 0), label,
            fontsize=fontsize, fontweight='bold', ha='center', va='center', color=DARK_BLUE)
    if sublabel:
        ax.text(x + w/2, y + h/2 - 0.18, sublabel,
                fontsize=7, ha='center', va='center', color='#555')

def draw_arrow(x1, y1, x2, y2, color=DARK_BLUE, style='->', lw=1.5):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                connectionstyle='arc3,rad=0'))

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: Folder Configs (top row)
# ══════════════════════════════════════════════════════════════════════════════
folder_configs = [
    (0.5,  8.8, 'W0', '00_meta_config', '16 agents', PURPLE),
    (3.5,  8.8, 'W1', '00_agent_config', '60 agents', BLUE),
    (6.5,  8.8, 'W2', '00_vd_config', '4 agents', TEAL),
    (9.5,  8.8, 'W3', '00_bc_config', '4 agents', ORANGE),
    (12.5, 8.8, 'W4', '00_ci_config', '4 agents', RED),
]

for x, y, wid, config, count, color in folder_configs:
    draw_box(x, y, 2.7, 0.9, color, f'{wid}: {config}', count, fontsize=8)

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: Shared Token Optimizer (center hub)
# ══════════════════════════════════════════════════════════════════════════════
# Large central box
shared_x, shared_y = 4.5, 6.8
shared_w, shared_h = 7.0, 1.4
box = FancyBboxPatch((shared_x, shared_y), shared_w, shared_h,
                     boxstyle="round,pad=0.15",
                     facecolor=GREEN, alpha=0.12,
                     edgecolor=GREEN, linewidth=3)
ax.add_patch(box)
ax.text(shared_x + shared_w/2, shared_y + shared_h - 0.35,
        'shared_token_optimizer', fontsize=12, fontweight='bold',
        ha='center', va='center', color=DARK_BLUE)
ax.text(shared_x + shared_w/2, shared_y + 0.55,
        'save_agent_memory()  ·  get_agent_memory(cross_folder=True)  ·  estimate_tokens()  ·  trim_to_budget()',
        fontsize=7.5, ha='center', va='center', color='#444', fontfamily='monospace')
ax.text(shared_x + shared_w/2, shared_y + 0.2,
        'Single Source of Truth — inherited by ALL folders via %run',
        fontsize=8, ha='center', va='center', color=GREEN, fontstyle='italic')

# ── Arrows from configs down to shared optimizer ─────────────────────────────
for x, y, wid, config, count, color in folder_configs:
    draw_arrow(x + 1.35, y, x + 1.35, shared_y + shared_h + 0.05, color=color, style='->', lw=1.2)

# Labels on arrows
ax.text(2.0, 8.55, '%run', fontsize=6.5, ha='center', color='#777', fontstyle='italic', rotation=90)

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3: Delta Tables (data layer)
# ══════════════════════════════════════════════════════════════════════════════
table_y = 4.8
tables = [
    (0.3,  table_y, 'agent_memory', 'Cross-session recall\nConfidence + TTL + Folder', GREEN),
    (3.3,  table_y, 'catalog_context_cache', '6hr TTL\nW1 catalog snapshots', BLUE),
    (6.3,  table_y, 'nexus_agent_events', 'Event bus\nPub/sub between agents', PURPLE),
    (9.3,  table_y, 'agent_call_log', 'Cost tracking\nTokens in/out + duration', ORANGE),
    (12.3, table_y, 'nexus_agent_registry', 'Agent catalog\n88 agents registered', DARK_GRAY),
]

for x, y, name, desc, color in tables:
    draw_box(x, y, 2.7, 1.1, color, name, desc, fontsize=7.5, alpha=0.12)

# Arrow from shared optimizer to agent_memory
draw_arrow(shared_x + 1.0, shared_y, 1.65, table_y + 1.15, color=GREEN, style='->', lw=2)
# Arrow from W1 config to catalog_cache
draw_arrow(shared_x + 2.5, shared_y, 4.65, table_y + 1.15, color=BLUE, style='->', lw=1.5)

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4: Token Optimization Safe Tier (bottom-left)
# ══════════════════════════════════════════════════════════════════════════════
opt_x, opt_y = 0.3, 2.2
opt_w, opt_h = 7.5, 2.2
box2 = FancyBboxPatch((opt_x, opt_y), opt_w, opt_h,
                      boxstyle="round,pad=0.12",
                      facecolor=GOLD, alpha=0.08,
                      edgecolor=GOLD, linewidth=2)
ax.add_patch(box2)
ax.text(opt_x + opt_w/2, opt_y + opt_h - 0.25,
        'Token Optimization — Safe Tier (Zero Accuracy Loss)',
        fontsize=10, fontweight='bold', ha='center', va='center', color=DARK_BLUE)

# Three sub-boxes inside
sub_items = [
    (0.6, 2.5, 2.0, 1.3, 'Agent Memory', '5-10× per session\nRemember decisions\nacross runs', GREEN),
    (3.0, 2.5, 2.0, 1.3, 'Catalog Cache', '50-70× vs live scan\n6hr TTL\nShared snapshot', BLUE),
    (5.4, 2.5, 2.0, 1.3, 'Lazy Loading', '3-5× reduction\nOnly scan relevant\nschemas', TEAL),
]
for x, y, w, h, label, desc, color in sub_items:
    draw_box(x, y, w, h, color, label, desc, fontsize=8, alpha=0.18)

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4: Safety Guarantees (bottom-right)
# ══════════════════════════════════════════════════════════════════════════════
safe_x, safe_y = 8.2, 2.2
safe_w, safe_h = 7.5, 2.2
box3 = FancyBboxPatch((safe_x, safe_y), safe_w, safe_h,
                      boxstyle="round,pad=0.12",
                      facecolor=RED, alpha=0.06,
                      edgecolor=RED, linewidth=2)
ax.add_patch(box3)
ax.text(safe_x + safe_w/2, safe_y + safe_h - 0.25,
        'Safety Guarantees — Data Integrity Rules',
        fontsize=10, fontweight='bold', ha='center', va='center', color=DARK_BLUE)

guarantees = [
    '✗  NEVER compress DDL, JSON, SQL, or bus matrices',
    '✗  NEVER skip catalog scan entirely (cache OR live)',
    '✗  NEVER hard-cap tokens mid-generation',
    '✓  Memory IMPROVES accuracy (avoids repeated mistakes)',
    '✓  Structured outputs pass through UNTOUCHED',
    '✓  Conservative: when in doubt, include more context',
]
for i, g in enumerate(guarantees):
    color = RED if g.startswith('✗') else GREEN
    ax.text(safe_x + 0.4, safe_y + safe_h - 0.7 - i*0.28, g,
            fontsize=7.5, ha='left', va='center', color=color, fontfamily='monospace')

# ══════════════════════════════════════════════════════════════════════════════
# FOOTER: Stats bar
# ══════════════════════════════════════════════════════════════════════════════
ax.axhline(y=1.8, xmin=0.02, xmax=0.98, color='#ddd', linewidth=1)

stats = [
    ('88', 'Agents'),
    ('5', 'Folders'),
    ('1', 'Memory Table'),
    ('6hr', 'Cache TTL'),
    ('60-70%', 'Token Savings'),
    ('$329-470', 'Annual Cost'),
]
for i, (val, label) in enumerate(stats):
    x_pos = 1.3 + i * 2.5
    ax.text(x_pos, 1.35, val, fontsize=14, fontweight='bold',
            ha='center', va='center', color=DARK_BLUE)
    ax.text(x_pos, 1.0, label, fontsize=8,
            ha='center', va='center', color='#777')

# ── Footer note ──────────────────────────────────────────────────────────────
ax.text(8, 0.5, 'mde_dev.test_schema  ·  Databricks Foundation Model APIs  ·  Serverless Jobs Compute ($0.45/DBU)',
        fontsize=8, ha='center', va='center', color='#999', fontfamily='sans-serif')
ax.text(8, 0.2, 'NEXUS v1.0 — June 2026 · Hologic Data Engineering',
        fontsize=7, ha='center', va='center', color='#bbb', fontfamily='sans-serif')

plt.tight_layout(pad=0.5)
plt.savefig('/tmp/nexus_architecture.png', dpi=200, bbox_inches='tight',
            facecolor='white', edgecolor='none')
print("✅ Diagram saved to /tmp/nexus_architecture.png (200 DPI, PPT-ready)")
print("   Copy to: /Workspace/Users/sameet.patel@hologic.com/2 - In Progress - Models/")
display(fig)