# Databricks notebook source
# DBTITLE 1,Business Analyst Agent
# MAGIC %md
# MAGIC # Agent 11 — Business Analyst
# MAGIC
# MAGIC **Purpose:** Gather and analyze requirements, produce Business Requirements Document (BRD), user stories, and acceptance criteria from natural language input.
# MAGIC
# MAGIC **Capabilities:**
# MAGIC - Parse unstructured requirements into structured BRD format
# MAGIC - Generate user stories with acceptance criteria (Given/When/Then)
# MAGIC - Identify data sources, consumers, and integration points
# MAGIC - Validate requirements against existing schema in Unity Catalog
# MAGIC
# MAGIC **Input:** Natural language requirement or email/meeting notes
# MAGIC **Output:** BRD.md, UserStories.md stored in `agent_outputs`

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Business Analyst system prompt and execution
# ══════════════════════════════════════════════════════════════════════════════
# BUSINESS ANALYST AGENT
# ══════════════════════════════════════════════════════════════════════════════

BA_SYSTEM_PROMPT = """You are a Senior Business Analyst at Hologic specializing in data platform requirements.

Your job: Take unstructured input (emails, meeting notes, verbal requirements) and produce:

## 1. Business Requirements Document (BRD)
- Business Objective
- Stakeholders
- Current State
- Desired State
- Functional Requirements (FR-001, FR-002, ...)
- Non-Functional Requirements (NFR-001, ...)
- Data Requirements (source systems, volumes, frequency)
- Assumptions
- Constraints
- Out of Scope
- Success Criteria

## 2. User Stories
Format:
```
As a [role]
I want [capability]
So that [business value]

Acceptance Criteria:
- Given [context] When [action] Then [outcome]
```

## Context
- Platform: Databricks Lakehouse (Unity Catalog)
- Architecture: Medallion (stg_ → silver → gold → platinum)
- Source Systems: Oracle EBS (1,263 objects), Salesforce (768), ASCP (238), HCM (147), Agile (82)
- Environments: DEV → UAT → PRD

Always identify:
- Which source system(s) are involved
- Which Medallion layer(s) are impacted
- Data volume and refresh frequency
- Security/PII considerations

Format output as clean markdown.
"""

try:
    REQUIREMENT_INPUT = dbutils.widgets.get("requirement")
except:
    REQUIREMENT_INPUT = """We need a supplier performance dashboard that shows:
    - On-time delivery rate by supplier
    - Quality rejection rate
    - Invoice accuracy
    - Payment terms compliance
    Data should come from Oracle EBS (PO, AP, Quality modules) and refresh daily.
    Finance and Procurement teams are the primary consumers."""

run_id = generate_run_id()

user_prompt = f"""Analyze the following requirement and produce a BRD and User Stories:

---
{REQUIREMENT_INPUT}
---

Identify source systems, Medallion layers, and produce complete documentation."""

result = call_agent("data_engineer", BA_SYSTEM_PROMPT, user_prompt, max_tokens=4096)

# Save outputs
save_agent_output("business_analyst", run_id, "brd", result,
                  {"input_length": len(REQUIREMENT_INPUT)})

print(result)
print(f"\n✅ Agent 11 (Business Analyst) completed | Run ID: {run_id}")