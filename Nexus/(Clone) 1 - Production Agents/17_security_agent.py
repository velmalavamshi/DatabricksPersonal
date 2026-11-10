# Databricks notebook source
# DBTITLE 1,Security Agent
# MAGIC %md
# MAGIC # Agent 17 — Security
# MAGIC
# MAGIC **Purpose:** Review code, architecture, and data access patterns for RBAC compliance, PII exposure, credential leakage, and GDPR readiness.
# MAGIC
# MAGIC **Output:** SecurityReview.md — severity-graded findings with remediation steps.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Security review execution
SECURITY_PROMPT = """You are a Databricks Security Specialist at Hologic. Review for:

1. RBAC & ACCESS CONTROL
   - Unity Catalog privileges (least privilege)
   - Row/column level security needs
   - Service principal vs personal token usage

2. PII / SENSITIVE DATA
   - Identify PII columns (name, email, SSN, DOB, address, phone)
   - Recommend masking functions or dynamic views
   - Flag any PII in logs or outputs

3. CREDENTIAL MANAGEMENT
   - No hardcoded tokens, passwords, or connection strings
   - Must use Databricks Secrets or Unity Catalog connections
   - Check for credentials in notebook outputs

4. GDPR / COMPLIANCE
   - Right to erasure support (soft delete patterns)
   - Data retention policies
   - Cross-border data transfer flags

5. NETWORK & ENCRYPTION
   - Private Link / VNet usage
   - Encryption at rest (Delta default) and in transit
   - IP access lists

For each finding produce:
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- Finding: What's wrong
- Location: Where in the code/architecture
- Recommendation: Specific fix
- Compliance: Which regulation applies (GDPR, SOX, HIPAA, internal)

Respond in structured markdown."""

try:
    INPUT = dbutils.widgets.get("code")
except:
    INPUT = get_latest_agent_output("data_engineer", "generated_code") or "Review the overall security posture of the mde_dev catalog."

run_id = generate_run_id()
result = call_agent("data_engineer", SECURITY_PROMPT, f"Perform security review on:\n\n{INPUT}", max_tokens=3000)
save_agent_output("security", run_id, "security_review", result, {})
print(result)
print(f"\n✅ Agent 17 (Security) completed | Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,Security Agent
# MAGIC %md
# MAGIC # Agent 17 — Security
# MAGIC
# MAGIC **Purpose:** Validate RBAC, Unity Catalog permissions, PII handling, and GDPR compliance.
# MAGIC
# MAGIC **Output:** SecurityReview.md with findings and remediation steps

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Security agent execution
SECURITY_PROMPT = """You are a Data Security specialist. Review and validate:

1. RBAC - Role-based access control via Unity Catalog grants
2. PII DETECTION - Identify columns containing personal data
3. DATA MASKING - Recommend dynamic views or column masks
4. CREDENTIAL MANAGEMENT - No hardcoded secrets (use Databricks Secrets)
5. NETWORK SECURITY - Private endpoints, IP restrictions
6. AUDIT TRAIL - system.access.audit logging verification
7. GDPR COMPLIANCE - data retention, right to erasure, consent tracking

For each finding provide: SEVERITY, FINDING, REMEDIATION, EFFORT.
Context: Hologic (medical devices), HCM data contains PII, Unity Catalog governance.
"""

try:
    REVIEW_INPUT = dbutils.widgets.get("code")
except:
    REVIEW_INPUT = get_latest_agent_output("data_engineer", "generated_code") or "Review security for Oracle HCM employee data pipeline."

run_id = generate_run_id()
result = call_agent("data_engineer", SECURITY_PROMPT, f"Security review for:\n\n{REVIEW_INPUT}", max_tokens=3000)
save_agent_output("security", run_id, "security_review", result, {})
print(result)
print(f"\n✅ Agent 17 (Security) completed | Run ID: {run_id}")