# Databricks notebook source
# DBTITLE 1,Documentation Agent
# MAGIC %md
# MAGIC # Agent 29 — Documentation
# MAGIC
# MAGIC **Purpose:** Generate technical documentation, user guides, runbooks, and operational procedures.
# MAGIC
# MAGIC **Output:** TechnicalDocs.md, UserGuide.md, Runbook.md.

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Documentation execution
DOC_PROMPT = """You are a Senior Technical Writer for Hologic's data platform.

Generate comprehensive documentation including:

1. TECHNICAL DOCUMENTATION
   - Architecture overview (with diagrams in markdown/mermaid)
   - Data flow description (source → target)
   - Configuration parameters and defaults
   - Dependencies and prerequisites
   - Error handling and recovery

2. USER GUIDE
   - Step-by-step usage instructions
   - Parameter descriptions with examples
   - Common use cases
   - FAQ section

3. RUNBOOK (for operations)
   - Normal operation procedures
   - Incident response steps
   - Escalation matrix
   - Health check commands
   - Recovery procedures with Delta Time Travel

4. API DOCUMENTATION (if applicable)
   - Endpoint descriptions
   - Request/response formats
   - Authentication requirements

5. CHANGE LOG
   - Version history
   - Breaking changes highlighted
   - Migration steps between versions

Format: Clean markdown with ToC, headers, code blocks, and tables.
Audience: Both technical (engineers) and semi-technical (analysts).
"""

try:
    INPUT = dbutils.widgets.get("requirement")
except:
    INPUT = get_latest_agent_output("data_engineer", "generated_code") or "Generate documentation for the Multi-Agent Platform."

run_id = generate_run_id()
result = call_agent("data_engineer", DOC_PROMPT, f"Generate documentation for:\n\n{INPUT}", max_tokens=4000)
save_agent_output("documentation", run_id, "technical_docs", result, {})
print(result)
print(f"\n✅ Agent 29 (Documentation) completed | Run ID: {run_id}")