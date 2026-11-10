# Databricks notebook source
# DBTITLE 1,Solution Recommender Agent
# MAGIC %md
# MAGIC # Agent 38 — Solution Recommender
# MAGIC
# MAGIC **Purpose:** Given a business requirement (raw or scoped), recommend the optimal Databricks artifact type to implement — with justification on cost, complexity, self-service capability, governance, and audience fit.
# MAGIC
# MAGIC **Responsibilities:**
# MAGIC - Evaluate 13 Databricks artifact types against requirement characteristics
# MAGIC - Score each option on 7 weighted criteria
# MAGIC - Produce a ranked recommendation with trade-off analysis
# MAGIC - Identify when multiple artifacts should be combined (e.g., Table + Metric View + Genie Space)
# MAGIC
# MAGIC **Input:** Scoped requirement from Agent 12 (Scope) or raw business requirement
# MAGIC **Output:** `solution_recommendation` document with ranked options, scores, and implementation guidance
# MAGIC
# MAGIC **Pipeline Position:** Between Scope (12) and Solution Architect (06)
# MAGIC ```
# MAGIC BA (11) → Scope (12) → Solution Recommender (38) → Solution Architect (06) → Data Engineer (02)
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,System prompt and decision framework
# ══════════════════════════════════════════════════════════════════════════════
# SOLUTION RECOMMENDER AGENT — System Prompt & Decision Framework
# ══════════════════════════════════════════════════════════════════════════════

RECOMMENDER_SYSTEM_PROMPT = """You are a Solution Recommender at Hologic specializing in Databricks Lakehouse platform capabilities.

Your role: Given a business requirement, recommend the OPTIMAL Databricks artifact type(s) to implement.
You evaluate options systematically, not default to "build a table" for everything.

## Artifact Types You Evaluate

| # | Artifact | Best For | Cost Profile |
|---|----------|----------|-------------|
| 1 | **Delta Table (Fact/Dim)** | Persistent governed data, joins, historical tracking | Storage + compute on write |
| 2 | **SQL View** | Logical abstraction, always-current reads, no storage cost | Compute on read |
| 3 | **Materialized View** | Expensive aggregations needing fast reads | Storage + incremental refresh |
| 4 | **Streaming Table (SDP)** | Real-time/near-real-time ingestion, CDC | Continuous compute |
| 5 | **Metric View** | Standardized KPIs with drill-down dimensions for AI/BI | Minimal (metadata only) |
| 6 | **Genie Space** | Self-service NL access for business users | Serverless SQL on query |
| 7 | **AI/BI Dashboard** | Interactive visual reports for defined audience | Serverless SQL on refresh |
| 8 | **Saved SQL Query** | Analyst-facing reusable parameterized queries | Compute on execution |
| 9 | **Alert** | Proactive notification on data conditions/thresholds | Scheduled SQL check |
| 10 | **Notebook** | Exploratory analysis, ML, one-off investigations | Interactive compute |
| 11 | **Databricks App** | Custom UI/UX beyond dashboard capabilities | App hosting + backend |
| 12 | **Model Serving Endpoint** | Real-time ML inference, embeddings, GenAI | SRTI $0.07/DBU |
| 13 | **Workflow/Job** | Orchestrated scheduled execution of pipelines | Jobs compute $0.30/DBU |

## Scoring Criteria (weighted)

Score each viable option 1-5 on these criteria:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Consumer Fit** | 25% | Does the artifact match how the consumer wants to interact? |
| **Self-Service** | 20% | Can the consumer use it without engineering support? |
| **Governance** | 15% | Unity Catalog lineage, access control, auditability |
| **Cost Efficiency** | 15% | DBU cost relative to value delivered |
| **Time to Deliver** | 10% | Engineering effort to build and deploy |
| **Maintainability** | 10% | Ongoing operational burden |
| **Scalability** | 5% | Handles growth in data volume and user count |

## Decision Shortcuts (apply before full scoring)

- Consumer is **executive/business user** + need is **metrics/KPIs** → Start with Metric View + Genie Space
- Consumer is **analyst** + need is **ad-hoc exploration** → Start with Genie Space or Saved Query
- Consumer is **engineer** + need is **pipeline output** → Start with Delta Table
- Need is **real-time** (< 5 min latency) → Streaming Table or Model Serving
- Need is **alerting/monitoring** → Alert + underlying query
- Need is **one-time analysis** → Notebook (don't over-engineer)
- Need is **custom application** → Databricks App + backing tables

## Combination Patterns (common)

Often the right answer is MULTIPLE artifacts working together:

| Pattern | When |
|---------|------|
| Table + View + Dashboard | Standard reporting on governed data |
| Table + Metric View + Genie Space | Self-service metrics for business users |
| Streaming Table + Alert | Real-time monitoring with notifications |
| Table + Model Endpoint + App | ML-powered business application |
| View + Saved Query + Alert | Lightweight monitoring without materialization |

## Output Format

Produce a structured recommendation:

### 1. Requirement Classification
- Consumer type: [Executive / Business User / Analyst / Engineer / Application]
- Interaction mode: [Visual / NL Query / SQL / API / Scheduled]
- Refresh need: [Real-time / Near-real-time / Daily / Weekly / Ad-hoc / One-time]
- Data volume: [Small < 1M rows / Medium 1-100M / Large 100M+ / Streaming]
- Governance need: [High (PII/Financial) / Medium / Low]

### 2. Recommended Solution (Ranked)
For each recommended artifact (top 3):
- Artifact type + rationale
- Score breakdown (7 criteria)
- Weighted total score
- Estimated delivery effort (T-shirt: S/M/L/XL)
- Annual cost estimate

### 3. Combination Recommendation
- Which artifacts should be combined
- Dependency order (build sequence)
- Why this combination vs. a single artifact

### 4. Anti-Patterns to Avoid
- What NOT to build for this requirement and why

### 5. Next Agent
- Which agent should execute: Solution Architect (06), Data Engineer (02), or direct implementation

## Hologic Context
- Catalog: mde_dev / mde_uat / mde_prd
- Existing Gold: 388 tables (195 dim, 159 fact)
- Existing Platinum: 104 tables
- 95% of Silver = views (intentional — avoids storage duplication)
- SK pattern: xxhash64 (NEVER MD5)
- Consumers: Finance, Supply Chain, HR, Sales, Quality, Compliance teams
- BI Tool: Power BI (connected via Databricks SQL Warehouse)
"""


# ── Artifact metadata for structured output ──────────────────────────────────────────

ARTIFACT_TYPES = {
    "delta_table": {"name": "Delta Table (Fact/Dim)", "category": "storage", "cost_sku": "PREMIUM_JOBS_COMPUTE"},
    "sql_view": {"name": "SQL View", "category": "logical", "cost_sku": "PREMIUM_SERVERLESS_SQL_COMPUTE"},
    "materialized_view": {"name": "Materialized View", "category": "storage", "cost_sku": "PREMIUM_DLT_ADVANCED_COMPUTE"},
    "streaming_table": {"name": "Streaming Table (SDP)", "category": "pipeline", "cost_sku": "PREMIUM_DLT_ADVANCED_COMPUTE"},
    "metric_view": {"name": "Metric View", "category": "semantic", "cost_sku": "PREMIUM_SERVERLESS_SQL_COMPUTE"},
    "genie_space": {"name": "Genie Space", "category": "self_service", "cost_sku": "PREMIUM_SERVERLESS_SQL_COMPUTE"},
    "aibi_dashboard": {"name": "AI/BI Dashboard", "category": "visualization", "cost_sku": "PREMIUM_SERVERLESS_SQL_COMPUTE"},
    "saved_query": {"name": "Saved SQL Query", "category": "analyst", "cost_sku": "PREMIUM_SERVERLESS_SQL_COMPUTE"},
    "alert": {"name": "Alert", "category": "monitoring", "cost_sku": "PREMIUM_SERVERLESS_SQL_COMPUTE"},
    "notebook": {"name": "Notebook", "category": "exploration", "cost_sku": "PREMIUM_ALL_PURPOSE_COMPUTE"},
    "databricks_app": {"name": "Databricks App", "category": "application", "cost_sku": "PREMIUM_SERVERLESS_REAL_TIME_INFERENCE"},
    "model_serving": {"name": "Model Serving Endpoint", "category": "ml", "cost_sku": "PREMIUM_SERVERLESS_REAL_TIME_INFERENCE"},
    "workflow_job": {"name": "Workflow/Job", "category": "orchestration", "cost_sku": "PREMIUM_JOBS_COMPUTE"},
}

SCORING_WEIGHTS = {
    "consumer_fit": 0.25,
    "self_service": 0.20,
    "governance": 0.15,
    "cost_efficiency": 0.15,
    "time_to_deliver": 0.10,
    "maintainability": 0.10,
    "scalability": 0.05,
}

print(f"✅ Solution Recommender agent loaded | {len(ARTIFACT_TYPES)} artifact types | {len(SCORING_WEIGHTS)} scoring criteria")

# COMMAND ----------

# DBTITLE 1,STEP 1: Gather requirement input
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Gather requirement input (from Workflow parameter or prior agent)
# ══════════════════════════════════════════════════════════════════════════════

try:
    REQUIREMENT = dbutils.widgets.get("requirement")
except:
    # Fallback: try to read scoped requirement from Agent 12, then BRD from Agent 11
    REQUIREMENT = (
        get_latest_agent_output("scope", "scope_document")
        or get_latest_agent_output("business_analyst", "brd")
        or """We need a supplier performance scorecard that shows on-time delivery rate,
        quality rejection rate, and invoice accuracy by supplier. Finance and Procurement
        teams should be able to explore the data themselves without asking engineering.
        Data comes from Oracle EBS (PO, AP, Quality modules) and refreshes daily."""
    )

try:
    CONSUMER_CONTEXT = dbutils.widgets.get("consumer")
except:
    CONSUMER_CONTEXT = ""  # Optional: explicit consumer type override

print(f"Requirement ({len(REQUIREMENT)} chars):")
print(f"  {REQUIREMENT[:300]}{'...' if len(REQUIREMENT) > 300 else ''}")
if CONSUMER_CONTEXT:
    print(f"\nExplicit consumer context: {CONSUMER_CONTEXT}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Check existing assets for reuse opportunities
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Scan existing catalog for reuse opportunities
# ══════════════════════════════════════════════════════════════════════════════

def scan_existing_assets() -> str:
    """Check gold/platinum layers for tables that might already satisfy the requirement."""
    try:
        existing = spark.sql(f"""
            SELECT 
                table_schema,
                table_name,
                table_type,
                comment
            FROM {CATALOG}.information_schema.tables
            WHERE table_schema IN ('gold', 'platinum', 'silver')
            ORDER BY table_schema, table_name
        """).collect()
        
        summary_lines = []
        for schema in ['platinum', 'gold', 'silver']:
            schema_tables = [r for r in existing if r['table_schema'] == schema]
            summary_lines.append(f"\n**{schema.upper()}** ({len(schema_tables)} objects):")
            for t in schema_tables[:20]:  # Top 20 per layer
                comment_str = f" -- {t['comment'][:60]}" if t['comment'] else ""
                summary_lines.append(f"  - {t['table_name']} ({t['table_type']}){comment_str}")
            if len(schema_tables) > 20:
                summary_lines.append(f"  ... and {len(schema_tables) - 20} more")
        
        return "\n".join(summary_lines)
    except Exception as e:
        return f"[Could not scan catalog: {e}]"


def scan_existing_genie_spaces() -> str:
    """Check for existing Genie Spaces that might already cover the requirement."""
    # Note: No system table for Genie Spaces yet; this is a placeholder
    # for future API integration
    return "[Genie Space inventory not available via system tables — manual check recommended]"


existing_assets = scan_existing_assets()
print(f"Existing asset scan complete")
print(f"  First 500 chars: {existing_assets[:500]}")

# COMMAND ----------

# DBTITLE 1,STEP 3: Generate solution recommendation
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Generate solution recommendation via LLM
# ══════════════════════════════════════════════════════════════════════════════

run_id = generate_run_id()

user_prompt = f"""## Business Requirement
{REQUIREMENT}

{f'## Explicit Consumer Context: {CONSUMER_CONTEXT}' if CONSUMER_CONTEXT else ''}

## Existing Assets in Catalog ({CATALOG})
{existing_assets}

## Instructions
1. Classify the requirement (consumer type, interaction mode, refresh need, volume, governance)
2. Apply decision shortcuts first — if a shortcut clearly applies, lead with it
3. Score the top 3-5 artifact types using the 7 weighted criteria
4. Recommend a combination pattern if appropriate
5. Identify anti-patterns (what NOT to build)
6. Specify which agent should execute next

Be specific to Hologic's environment. Reference existing tables when they can be reused.
Do NOT default to "build a new table" unless the data genuinely doesn't exist yet.
"""

recommendation = call_agent(
    "solution_recommender",  # Uses LLM_CRITICAL for architecture decisions
    RECOMMENDER_SYSTEM_PROMPT,
    user_prompt,
    temperature=0.2,
    max_tokens=4096
)

print(recommendation)

# COMMAND ----------

# DBTITLE 1,STEP 4: Parse and structure the recommendation
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Parse recommendation and extract structured metadata
# ══════════════════════════════════════════════════════════════════════════════

def extract_primary_recommendation(text: str) -> dict:
    """Extract the primary recommended artifact type from the LLM output."""
    text_lower = text.lower()
    
    # Detect which artifact types are mentioned as primary recommendations
    detected = []
    for key, meta in ARTIFACT_TYPES.items():
        name_lower = meta["name"].lower()
        # Check if mentioned in a recommendation context (not just anti-pattern)
        if name_lower in text_lower:
            detected.append(key)
    
    # Detect combination patterns
    is_combination = any(phrase in text_lower for phrase in [
        "combination", "combined", "together", "plus", "paired with",
        "along with", "complemented by", "layered"
    ])
    
    # Detect next agent routing
    next_agent = "06_solution_architect"  # default
    if "data engineer" in text_lower or "agent 02" in text_lower:
        next_agent = "02_data_engineer"
    elif "direct implementation" in text_lower:
        next_agent = "direct_implementation"
    elif "data modeler" in text_lower or "agent 37" in text_lower:
        next_agent = "37_data_modeler"
    
    return {
        "detected_artifacts": detected,
        "is_combination": is_combination,
        "next_agent": next_agent,
        "artifact_count": len(detected)
    }


parsed = extract_primary_recommendation(recommendation)
print(f"\n── Parsed Recommendation Metadata ───────────────────────────────")
print(f"  Detected artifacts: {parsed['detected_artifacts']}")
print(f"  Combination pattern: {parsed['is_combination']}")
print(f"  Next agent: {parsed['next_agent']}")
print(f"  Total artifacts recommended: {parsed['artifact_count']}")

# COMMAND ----------

# DBTITLE 1,STEP 5: Save output and validate
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Save output and validate quality
# ══════════════════════════════════════════════════════════════════════════════

save_agent_output(
    agent_name="solution_recommender",
    run_id=run_id,
    output_type="solution_recommendation",
    content=recommendation,
    metadata={
        "requirement_preview": REQUIREMENT[:500],
        "consumer_context": CONSUMER_CONTEXT,
        "detected_artifacts": parsed["detected_artifacts"],
        "is_combination": parsed["is_combination"],
        "next_agent": parsed["next_agent"],
    }
)

# ── Validation checks ──────────────────────────────────────────────────────────

rec_lower = recommendation.lower()

validation_checks = {
    "Contains requirement classification": any(kw in rec_lower for kw in ["consumer type", "interaction mode", "refresh", "classification"]),
    "Recommends at least one artifact": parsed["artifact_count"] >= 1,
    "Includes scoring/rationale": any(kw in rec_lower for kw in ["score", "rating", "rationale", "criteria", "weight"]),
    "Identifies anti-patterns": any(kw in rec_lower for kw in ["anti-pattern", "avoid", "do not", "don't build", "overkill"]),
    "Specifies next agent": any(kw in rec_lower for kw in ["next agent", "agent 06", "agent 02", "solution architect", "data engineer"]),
    "References existing assets": any(kw in rec_lower for kw in ["existing", "reuse", "already", "current"]),
    "Includes cost consideration": any(kw in rec_lower for kw in ["cost", "dbu", "$", "expense", "budget"]),
    "Includes delivery effort": any(kw in rec_lower for kw in ["effort", "t-shirt", "days", "sprint", "complexity"]),
}

print("\n" + "─" * 60)
print("Solution Recommendation Validation")
print("─" * 60)

passed = 0
for check, result in validation_checks.items():
    status = "✅" if result else "❌"
    print(f"  {status} {check}")
    if result:
        passed += 1

total = len(validation_checks)
score_pct = (passed / total) * 100

print(f"\n  Score: {passed}/{total} ({score_pct:.0f}%)")

if score_pct >= 75:
    print(f"\n✅ Agent 38 (Solution Recommender) completed | Run ID: {run_id}")
    print(f"   Next agent: {parsed['next_agent']}")
elif score_pct >= 50:
    print(f"\n⚠️ Agent 38 completed with warnings | Run ID: {run_id}")
    print(f"   Recommendation may be incomplete — review before routing to next agent")
else:
    print(f"\n❌ Agent 38 failed quality gate | Run ID: {run_id}")
    print(f"   Recommendation does not meet minimum quality — consider re-running with more context")