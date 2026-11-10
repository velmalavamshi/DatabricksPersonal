# Databricks notebook source
# DBTITLE 1,Specialist Base Template
# MAGIC %md
# MAGIC # Agent 61 — Specialist Base Template (W1)
# MAGIC
# MAGIC **Purpose:** Provides the base class and standard interface that ALL specialist agents (32-59) implement. Defines the 5 core consultation capabilities and the response protocol.
# MAGIC
# MAGIC Specialists `%run` this notebook to inherit the base class, then override methods with domain-specific logic.

# COMMAND ----------

# DBTITLE 1,Load consultation config
# MAGIC %run ./00_consultation_config

# COMMAND ----------

# DBTITLE 1,Specialist Base Class
# ======================================================================
# SPECIALIST BASE CLASS
# All specialists inherit from this and override methods
# ======================================================================

class SpecialistBase:
    """Base class for all NEXUS specialist agents."""
    
    def __init__(self, agent_name, source_system, schemas, domains):
        self.agent_name = agent_name
        self.source_system = source_system
        self.schemas = schemas
        self.domains = domains
        self.run_id = generate_run_id()
    
    # ==================== CORE CAPABILITIES ====================
    
    def get_schema_context(self, table_pattern=None):
        """Return schema metadata for the source system.
        Override with domain-specific table groupings and descriptions.
        """
        schema_list = self.schemas[0] if self.schemas else 'unknown'
        query = f"""
            SELECT table_name, table_type,
                   (SELECT COUNT(*) FROM {schema_list}.information_schema.columns c
                    WHERE c.table_name = t.table_name) as column_count
            FROM {schema_list}.information_schema.tables t
        """
        if table_pattern:
            query += f" WHERE t.table_name LIKE '%{table_pattern}%'"
        query += " ORDER BY table_name LIMIT 50"
        
        try:
            tables = spark.sql(query).collect()
            return {
                "source_system": self.source_system,
                "schema": schema_list,
                "table_count": len(tables),
                "tables": [{"name": t['table_name'], "type": t['table_type'], "columns": t['column_count']} for t in tables],
            }
        except Exception as e:
            return {"error": str(e), "source_system": self.source_system}
    
    def get_known_issues(self):
        """Return known issues, quirks, and gotchas for this source system.
        Override with domain-specific knowledge.
        """
        # Base implementation: check recent failures related to this source
        failures = spark.sql(f"""
            SELECT run_name, result_state, termination_code, period_start_time
            FROM system.lakeflow.job_run_timeline
            WHERE workspace_id = '{DEV_WORKSPACE_ID}'
              AND run_name LIKE '%{self.source_system}%'
              AND result_state IN ('FAILED', 'TIMEDOUT', 'ERROR')
              AND period_start_time >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
              AND (run_type = 'JOB_RUN' OR run_type = 'SUBMIT_RUN')
            ORDER BY period_start_time DESC
            LIMIT 10
        """).collect()
        
        return {
            "source_system": self.source_system,
            "recent_failures_30d": len(failures),
            "failure_details": [{"job": f['run_name'], "state": f['result_state'], "when": str(f['period_start_time'])} for f in failures[:5]],
            "known_quirks": [],  # Override in specialist
        }
    
    def validate_approach(self, proposed_approach):
        """Validate a proposed technical approach against domain knowledge.
        Override with domain-specific validation rules.
        """
        prompt = f"""You are the {self.source_system} specialist agent.
        
Validate this proposed approach:
{proposed_approach}

Consider:
1. Does it align with {self.source_system} best practices?
2. Are there known pitfalls with this source system?
3. Are the assumptions about data grain/keys correct?
4. What risks should the caller be aware of?

Respond with:
- APPROVED / APPROVED_WITH_CAVEATS / REJECTED
- Reasoning (3 bullet points max)
- Recommendations (if any)"""
        
        response = call_llm(prompt, max_tokens=500)
        return {
            "source_system": self.source_system,
            "specialist": self.agent_name,
            "validation_result": response,
        }
    
    def recommend_dq_rules(self, table_name=None, context=None):
        """Recommend data quality rules for this source system.
        Override with domain-specific DQ knowledge.
        """
        prompt = f"""You are the {self.source_system} data quality specialist.
        
Recommend DQ rules for {'table: ' + table_name if table_name else 'this source system'}.
Context: {context or 'General DQ rule recommendation'}

Provide 5-8 rules in this format:
- Rule name | Column(s) | Check type | Threshold | Severity

Focus on: completeness, accuracy, timeliness, uniqueness, referential integrity."""
        
        response = call_llm(prompt, max_tokens=600)
        return {
            "source_system": self.source_system,
            "specialist": self.agent_name,
            "table": table_name,
            "rules": response,
        }
    
    def get_pipeline_health(self):
        """Return current pipeline health metrics for this source system."""
        health = spark.sql(f"""
            SELECT
                COUNT(*) as total_runs_7d,
                COUNT_IF(result_state = 'SUCCESS') as success_7d,
                COUNT_IF(result_state IN ('FAILED', 'TIMEDOUT', 'ERROR')) as failed_7d,
                ROUND(COUNT_IF(result_state = 'SUCCESS') * 100.0 / NULLIF(COUNT(*), 0), 1) as success_rate,
                ROUND(AVG(CASE WHEN result_state = 'SUCCESS' THEN run_duration_seconds END) / 60.0, 1) as avg_duration_min
            FROM system.lakeflow.job_run_timeline
            WHERE workspace_id = '{DEV_WORKSPACE_ID}'
              AND run_name LIKE '%{self.source_system}%'
              AND period_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
              AND (run_type = 'JOB_RUN' OR run_type = 'SUBMIT_RUN')
        """).collect()[0]
        
        return {
            "source_system": self.source_system,
            "period": "7d",
            "total_runs": health['total_runs_7d'],
            "success_rate": float(health['success_rate'] or 0),
            "failures": health['failed_7d'],
            "avg_duration_min": float(health['avg_duration_min'] or 0),
            "status": "HEALTHY" if (health['success_rate'] or 0) >= 95 else "DEGRADED" if (health['success_rate'] or 0) >= 80 else "UNHEALTHY",
        }
    
    # ==================== CONSULTATION HANDLER ====================
    
    def handle_consultation(self, consultation_payload):
        """Process an inbound CONSULTATION_ROUTED event."""
        question = consultation_payload.get('question', '')
        capability = consultation_payload.get('capability_needed', 'validate_approach')
        context = consultation_payload.get('context', {})
        consultation_id = consultation_payload.get('consultation_id', '')
        
        # Dispatch to the right capability
        if capability == 'get_schema_context':
            result = self.get_schema_context(context.get('table_pattern'))
        elif capability == 'get_known_issues':
            result = self.get_known_issues()
        elif capability == 'validate_approach':
            result = self.validate_approach(question)
        elif capability == 'recommend_dq_rules':
            result = self.recommend_dq_rules(context.get('table_name'), question)
        elif capability == 'get_pipeline_health':
            result = self.get_pipeline_health()
        else:
            result = self.validate_approach(question)  # Default
        
        # Build response
        response = build_consultation_response(consultation_id, self.agent_name, result)
        return response


print("\u2705 SpecialistBase class loaded")
print("   Capabilities: get_schema_context, get_known_issues, validate_approach, recommend_dq_rules, get_pipeline_health")
print("   Usage: class MySpecialist(SpecialistBase): ... override methods ...")