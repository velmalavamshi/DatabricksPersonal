# Databricks notebook source
# DBTITLE 1,Specialist Consultation Network — Configuration
# ======================================================================
# 00_consultation_config
# Phase 10 — Specialist Consultation Network Configuration
# Defines routes, capabilities, timeouts, and event schemas
# ======================================================================

import json
import uuid
import requests
from datetime import datetime, timezone, timedelta
from pyspark.sql import functions as F

# ── Environment ────────────────────────────────────────────────────────
NEXUS_SCHEMA = "mde_dev.test_schema"
NEXUS_EVENTS = f"{NEXUS_SCHEMA}.nexus_agent_events"
NEXUS_REGISTRY = f"{NEXUS_SCHEMA}.nexus_agent_registry"
NEXUS_CIRCUIT = f"{NEXUS_SCHEMA}.nexus_agent_circuit_breaker"

LLM_ENDPOINT = "databricks-claude-sonnet-4-6"
WORKSPACE_URL = spark.conf.get("spark.databricks.workspaceUrl")
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
DEV_WORKSPACE_ID = "6617965257274108"

def call_llm(prompt, max_tokens=2048, temperature=0.1):
    """Call Foundation Model API."""
    url = f"https://{WORKSPACE_URL}/serving-endpoints/{LLM_ENDPOINT}/invocations"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def generate_run_id():
    return str(uuid.uuid4())

# ======================================================================
# SPECIALIST REGISTRY — Domain expertise capabilities
# Maps each specialist to their source system, schemas, and capabilities
# ======================================================================

SPECIALIST_REGISTRY = {
    "32_oracle_ebs_specialist_agent": {
        "source_system": "oracle_ebs",
        "schemas": ["mde_dev.stg_oracle_ebs"],
        "table_count": 1263,
        "domains": ["AP", "AR", "GL", "PO", "INV", "OM", "BOM", "WIP"],
        "capabilities": ["get_schema_context", "get_known_issues", "validate_approach", "recommend_dq_rules", "get_pipeline_health"],
    },
    "33_salesforce_sync_agent": {
        "source_system": "salesforce",
        "schemas": ["mde_dev.stg_salesforce", "mde_dev.stg_poc_salesforce"],
        "table_count": 768,
        "domains": ["Account", "Contact", "Opportunity", "Lead", "Case", "Campaign"],
        "capabilities": ["get_schema_context", "get_known_issues", "validate_approach", "recommend_dq_rules", "get_pipeline_health"],
    },
    "44_oracle_ebs_extract_agent": {
        "source_system": "oracle_ebs",
        "schemas": ["mde_dev.stg_oracle_ebs"],
        "table_count": 1263,
        "domains": ["extract", "ingestion", "incremental", "full_load"],
        "capabilities": ["get_pipeline_health", "get_known_issues", "recommend_extract_strategy"],
    },
    "45_oracle_ebs_error_agent": {
        "source_system": "oracle_ebs",
        "schemas": ["mde_dev.stg_oracle_ebs"],
        "table_count": 1263,
        "domains": ["error_handling", "retry", "dead_letter", "reconciliation"],
        "capabilities": ["get_known_issues", "classify_error", "recommend_retry_strategy"],
    },
    "46_oracle_ebs_dq_agent": {
        "source_system": "oracle_ebs",
        "schemas": ["mde_dev.stg_oracle_ebs"],
        "table_count": 1263,
        "domains": ["data_quality", "completeness", "accuracy", "timeliness"],
        "capabilities": ["recommend_dq_rules", "validate_approach", "get_known_issues"],
    },
    "47_salesforce_extract_agent": {
        "source_system": "salesforce",
        "schemas": ["mde_dev.stg_salesforce"],
        "table_count": 488,
        "domains": ["extract", "CDC", "bulk_api", "incremental"],
        "capabilities": ["get_pipeline_health", "get_known_issues", "recommend_extract_strategy"],
    },
    "48_salesforce_dq_agent": {
        "source_system": "salesforce",
        "schemas": ["mde_dev.stg_salesforce"],
        "table_count": 488,
        "domains": ["data_quality", "deduplication", "merge_rules"],
        "capabilities": ["recommend_dq_rules", "validate_approach"],
    },
    "49_ascp_specialist_agent": {
        "source_system": "ascp",
        "schemas": ["mde_dev.stg_ascp"],
        "table_count": 238,
        "domains": ["supply_chain", "demand_planning", "supply_planning", "ATP"],
        "capabilities": ["get_schema_context", "get_known_issues", "validate_approach", "recommend_dq_rules"],
    },
    "50_agile_plm_agent": {
        "source_system": "agile",
        "schemas": ["mde_dev.stg_agile"],
        "table_count": 82,
        "domains": ["BOM", "ECO", "product_lifecycle", "engineering_change"],
        "capabilities": ["get_schema_context", "get_known_issues", "validate_approach"],
    },
    "51_koerber_specialist_agent": {
        "source_system": "koerber",
        "schemas": ["mde_dev.stg_koerber"],
        "table_count": 2,
        "domains": ["warehouse", "WMS", "inventory", "shipping"],
        "capabilities": ["get_schema_context", "get_known_issues"],
    },
    "52_oracle_hcm_specialist_agent": {
        "source_system": "oracle_hcm",
        "schemas": ["mde_dev.stg_oracle_hcm"],
        "table_count": 147,
        "domains": ["workforce", "payroll", "recruitment", "absence", "benefits"],
        "capabilities": ["get_schema_context", "get_known_issues", "validate_approach", "recommend_dq_rules"],
    },
    "53_servicenow_agent": {
        "source_system": "servicenow",
        "schemas": ["mde_dev.stg_servicenow"],
        "table_count": 2,
        "domains": ["ITSM", "incidents", "change_requests", "CMDB"],
        "capabilities": ["get_schema_context", "get_known_issues"],
    },
    "55_pbcs_specialist_agent": {
        "source_system": "pbcs",
        "schemas": ["mde_dev.stg_pbcs"],
        "table_count": 42,
        "domains": ["planning", "budgeting", "forecasting", "financial_close"],
        "capabilities": ["get_schema_context", "get_known_issues", "validate_approach"],
    },
    "56_hcp_specialist_agent": {
        "source_system": "hcp",
        "schemas": ["mde_dev.stg_hcp"],
        "table_count": 81,
        "domains": ["healthcare_providers", "PII", "Sunshine_Act", "NPI", "compliance"],
        "capabilities": ["get_schema_context", "get_known_issues", "validate_approach", "recommend_dq_rules"],
    },
    "57_definitive_specialist_agent": {
        "source_system": "definitive",
        "schemas": ["mde_dev.stg_definitive"],
        "table_count": 34,
        "domains": ["market_intelligence", "hospital_data", "IDN", "GPO"],
        "capabilities": ["get_schema_context", "get_known_issues"],
    },
    "58_cornerstone_specialist_agent": {
        "source_system": "cornerstone",
        "schemas": ["mde_dev.stg_cornerstone"],
        "table_count": 29,
        "domains": ["LMS", "training", "compliance", "certifications"],
        "capabilities": ["get_schema_context", "get_known_issues"],
    },
    "59_mulesoft_specialist_agent": {
        "source_system": "mulesoft",
        "schemas": ["mde_dev.stg_mule"],
        "table_count": 4,
        "domains": ["API", "integration", "middleware", "ESB"],
        "capabilities": ["get_schema_context", "get_known_issues", "get_pipeline_health"],
    },
}

# ======================================================================
# CONSULTATION ROUTES — Who consults whom
# Caller agent → list of specialists they can consult
# ======================================================================

CONSULTATION_ROUTES = {
    "01_job_failure_triage_agent": {
        "triggers": ["pipeline_failure", "job_failure", "timeout", "error"],
        "specialists": ["44_oracle_ebs_extract_agent", "45_oracle_ebs_error_agent", "47_salesforce_extract_agent", "49_ascp_specialist_agent", "50_agile_plm_agent", "51_koerber_specialist_agent", "52_oracle_hcm_specialist_agent"],
        "routing": "source_system",  # Route by which source system failed
    },
    "02_data_engineer_agent": {
        "triggers": ["pipeline_design", "schema_change", "new_table", "migration"],
        "specialists": ["32_oracle_ebs_specialist_agent", "33_salesforce_sync_agent", "49_ascp_specialist_agent", "50_agile_plm_agent", "52_oracle_hcm_specialist_agent", "55_pbcs_specialist_agent"],
        "routing": "source_system",
    },
    "16_data_quality_agent": {
        "triggers": ["dq_rules", "anomaly_detected", "completeness_failure"],
        "specialists": ["46_oracle_ebs_dq_agent", "48_salesforce_dq_agent", "56_hcp_specialist_agent"],
        "routing": "source_system",
    },
    "37_data_modeler_agent": {
        "triggers": ["star_schema_design", "business_key_identification", "grain_definition"],
        "specialists": ["32_oracle_ebs_specialist_agent", "33_salesforce_sync_agent", "49_ascp_specialist_agent", "52_oracle_hcm_specialist_agent", "56_hcp_specialist_agent", "57_definitive_specialist_agent"],
        "routing": "source_system",
    },
    "06_solution_architect_agent": {
        "triggers": ["integration_pattern", "architecture_review", "tech_stack"],
        "specialists": ["53_servicenow_agent", "59_mulesoft_specialist_agent", "54_powerbi_agent"],
        "routing": "domain",
    },
}

# ======================================================================
# CONSULTATION EVENT SCHEMA
# ======================================================================

CONSULTATION_EVENT_TYPES = {
    "CONSULTATION_REQUEST": "Caller requests domain expertise from a specialist",
    "CONSULTATION_RESPONSE": "Specialist provides response with recommendations",
    "CONSULTATION_TIMEOUT": "Specialist did not respond within SLA",
    "CONSULTATION_ESCALATION": "Escalated to human or alternate specialist",
}

CONSULTATION_SLA = {
    "P1": {"timeout_minutes": 5, "escalation": "immediate"},
    "P2": {"timeout_minutes": 15, "escalation": "next_specialist"},
    "P3": {"timeout_minutes": 60, "escalation": "log_only"},
}

def build_consultation_request(caller, specialist, question, context, priority="P2"):
    """Build a CONSULTATION_REQUEST event payload."""
    return {
        "consultation_id": str(uuid.uuid4()),
        "caller_agent": caller,
        "specialist_agent": specialist,
        "question": question,
        "context": context,
        "priority": priority,
        "requested_capabilities": [],  # Filled by router
        "timeout_minutes": CONSULTATION_SLA[priority]['timeout_minutes'],
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }

def build_consultation_response(consultation_id, specialist, recommendation, confidence=0.8):
    """Build a CONSULTATION_RESPONSE event payload."""
    return {
        "consultation_id": consultation_id,
        "specialist_agent": specialist,
        "recommendation": recommendation,
        "confidence": confidence,
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }

def find_specialist_for_source(source_system, capability_needed=None):
    """Find the best specialist for a given source system."""
    matches = []
    for agent_name, spec in SPECIALIST_REGISTRY.items():
        if spec['source_system'] == source_system:
            if capability_needed is None or capability_needed in spec['capabilities']:
                matches.append(agent_name)
    return matches

print("\u2705 Consultation Network config loaded")
print(f"   Specialists registered: {len(SPECIALIST_REGISTRY)}")
print(f"   Consultation routes: {len(CONSULTATION_ROUTES)} callers")
print(f"   Total consultable paths: {sum(len(r['specialists']) for r in CONSULTATION_ROUTES.values())}")
print(f"   SLA tiers: {list(CONSULTATION_SLA.keys())}")