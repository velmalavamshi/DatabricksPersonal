# Databricks notebook source
# DBTITLE 1,Job Failure Triage Agent
# MAGIC %md
# MAGIC # Agent 01 — Job Failure Triage
# MAGIC
# MAGIC **Purpose:** Automatically monitor, classify, and recommend fixes for job failures across all workspaces.
# MAGIC
# MAGIC **Problem solved:** 1,654 job failures/month in DEV alone (5 chronic jobs never fixed, failing every hour).
# MAGIC
# MAGIC **Data sources:**
# MAGIC - `system.lakeflow.job_run_timeline` — run outcomes
# MAGIC - `system.lakeflow.job_task_run_timeline` — task-level errors
# MAGIC - `system.compute.clusters` — cluster config context
# MAGIC
# MAGIC **Outputs:**
# MAGIC - `mde_dev.test_schema.agent_job_triage_results` — classified failures with recommendations
# MAGIC - Markdown triage report stored in `agent_outputs`

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Collect failure data from system tables
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Gather failure data (last 7 days)
# ══════════════════════════════════════════════════════════════════════════════

LOOKBACK_DAYS = 7  # Configurable via Workflow parameter

# Get job-level failures with frequency analysis
df_failures = spark.sql(f"""
WITH failure_summary AS (
    SELECT 
        workspace_id,
        job_id,
        job_name,
        result_state,
        COUNT(*) as failure_count,
        MIN(period_start_time) as first_failure,
        MAX(period_start_time) as last_failure,
        DATEDIFF(HOUR, MIN(period_start_time), MAX(period_start_time)) / NULLIF(COUNT(*) - 1, 0) as avg_hours_between_failures
    FROM system.lakeflow.job_run_timeline
    WHERE period_start_time >= DATEADD(DAY, -{LOOKBACK_DAYS}, CURRENT_DATE())
      AND result_state IN ('FAILED', 'ERROR')
    GROUP BY 1, 2, 3, 4
)
SELECT 
    *,
    CASE 
        WHEN failure_count >= 50 AND avg_hours_between_failures <= 2 THEN 'CHRONIC_REPEATING'
        WHEN failure_count >= 10 THEN 'FREQUENT'
        WHEN failure_count >= 3 THEN 'RECURRING'
        ELSE 'SPORADIC'
    END as failure_pattern,
    CASE
        WHEN failure_count >= 50 THEN 'CRITICAL'
        WHEN failure_count >= 10 THEN 'HIGH'
        WHEN failure_count >= 3 THEN 'MEDIUM'
        ELSE 'LOW'
    END as severity
FROM failure_summary
ORDER BY failure_count DESC
""")

print(f"✅ Found {df_failures.count()} failing jobs in last {LOOKBACK_DAYS} days")
df_failures.display()

# COMMAND ----------

# DBTITLE 1,Get task-level error messages for top failures
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Get error details from task-level timeline
# ══════════════════════════════════════════════════════════════════════════════

# Get the top 20 most-failing jobs for detailed analysis
top_job_ids = [row["job_id"] for row in df_failures.limit(20).collect()]

if top_job_ids:
    job_id_list = ",".join([f"'{jid}'" for jid in top_job_ids])
    
    df_task_errors = spark.sql(f"""
    SELECT 
        workspace_id,
        job_id,
        job_name,
        task_key,
        result_state,
        period_start_time,
        period_end_time,
        DATEDIFF(MINUTE, period_start_time, period_end_time) as duration_min
    FROM system.lakeflow.job_task_run_timeline
    WHERE period_start_time >= DATEADD(DAY, -{LOOKBACK_DAYS}, CURRENT_DATE())
      AND job_id IN ({job_id_list})
      AND result_state IN ('FAILED', 'ERROR')
    ORDER BY period_start_time DESC
    LIMIT 100
    """)
    
    print(f"✅ Collected {df_task_errors.count()} task-level failure records")
    df_task_errors.display()
else:
    print("✅ No failures found in the lookback window!")
    df_task_errors = spark.createDataFrame([], schema="workspace_id STRING, job_id STRING")

# COMMAND ----------

# DBTITLE 1,Classify failures with LLM
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: LLM-powered failure classification and recommendation
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a Senior Databricks Platform Engineer specializing in job failure diagnosis.

Your task: Analyze job failure data and provide:
1. ROOT CAUSE CLASSIFICATION — one of: CLUSTER_ISSUE, SCHEMA_DRIFT, PERMISSIONS, TIMEOUT, OOM, DATA_ISSUE, NETWORK, DEPENDENCY, CONFIG_ERROR, UNKNOWN
2. LIKELY ROOT CAUSE — specific explanation
3. RECOMMENDED FIX — actionable steps
4. PRIORITY — CRITICAL/HIGH/MEDIUM/LOW based on frequency and impact
5. AUTO_FIXABLE — whether this can be auto-remediated (true/false)

Respond in valid JSON format:
{
    "classification": "<category>",
    "root_cause": "<explanation>",
    "recommended_fix": "<specific steps>",
    "priority": "<level>",
    "auto_fixable": <boolean>,
    "estimated_fix_effort": "<hours>"
}

Context: This is a Hologic Databricks environment with:
- Medallion architecture (stg_ → silver → gold → platinum)
- 15+ source systems (Oracle EBS, Salesforce, ASCP, HCM, etc.)
- 3 environments (DEV/UAT/PRD)
- Heavy view-based architecture (95% of silver = views)
"""

run_id = generate_run_id()
results = []

# Process top 10 most-failing jobs
failure_rows = df_failures.limit(10).collect()

for row in failure_rows:
    user_prompt = f"""Analyze this failing Databricks job:

- Job ID: {row['job_id']}
- Job Name: {row['job_name'] or 'Unknown'}
- Workspace: {get_workspace_name(row['workspace_id'])}
- Result State: {row['result_state']}
- Failure Count (last {LOOKBACK_DAYS} days): {row['failure_count']}
- Failure Pattern: {row['failure_pattern']}
- Avg Hours Between Failures: {row['avg_hours_between_failures']}
- First Failure: {row['first_failure']}
- Last Failure: {row['last_failure']}

Classify this failure and recommend a fix."""

    try:
        response = call_agent("job_failure_triage", SYSTEM_PROMPT, user_prompt, max_tokens=1024)
        
        # Parse JSON response
        # Handle potential markdown wrapping
        clean_response = response.strip()
        if clean_response.startswith("```"):
            clean_response = clean_response.split("\n", 1)[1].rsplit("```", 1)[0]
        
        classification = json.loads(clean_response)
        classification["job_id"] = row["job_id"]
        classification["job_name"] = row["job_name"]
        classification["workspace_id"] = row["workspace_id"]
        classification["failure_count"] = row["failure_count"]
        classification["failure_pattern"] = row["failure_pattern"]
        classification["run_id"] = run_id
        classification["timestamp"] = datetime.now().isoformat()
        results.append(classification)
        
    except Exception as e:
        print(f"⚠️ Failed to classify job {row['job_id']}: {e}")
        results.append({
            "job_id": row["job_id"],
            "job_name": row["job_name"],
            "workspace_id": row["workspace_id"],
            "failure_count": row["failure_count"],
            "failure_pattern": row["failure_pattern"],
            "classification": "UNKNOWN",
            "root_cause": f"Classification failed: {str(e)[:100]}",
            "recommended_fix": "Manual investigation required",
            "priority": row["severity"] if "severity" in row.asDict() else "MEDIUM",
            "auto_fixable": False,
            "estimated_fix_effort": "Unknown",
            "run_id": run_id,
            "timestamp": datetime.now().isoformat()
        })

print(f"\n✅ Classified {len(results)} job failures")

# COMMAND ----------

# DBTITLE 1,Save results to Delta and generate report
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Persist results and generate triage report
# ══════════════════════════════════════════════════════════════════════════════

if results:
    # Save to Delta
    df_results = spark.createDataFrame(results)
    df_results.write.mode("overwrite").saveAsTable(
        f"{CATALOG}.{SCHEMA}.agent_job_triage_results"
    )
    print(f"✅ Results saved to {CATALOG}.{SCHEMA}.agent_job_triage_results")
    
    # Generate summary report
    critical_count = sum(1 for r in results if r.get("priority") == "CRITICAL")
    high_count = sum(1 for r in results if r.get("priority") == "HIGH")
    auto_fixable = sum(1 for r in results if r.get("auto_fixable") == True)
    
    # Classification distribution
    classifications = {}
    for r in results:
        cls = r.get("classification", "UNKNOWN")
        classifications[cls] = classifications.get(cls, 0) + 1
    
    report_sections = {
        "Executive Summary": f"""Analyzed **{len(results)} failing jobs** across all workspaces (last {LOOKBACK_DAYS} days).

| Metric | Value |
|--------|-------|
| Critical Issues | {critical_count} |
| High Priority | {high_count} |
| Auto-Fixable | {auto_fixable} |
| Total Classified | {len(results)} |""",
        
        "Classification Breakdown": "\n".join([f"- **{k}**: {v} jobs" for k, v in sorted(classifications.items(), key=lambda x: -x[1])]),
        
        "Top Recommendations": "\n".join([
            f"### Job: {r.get('job_name', r['job_id'])} ({get_workspace_name(r['workspace_id'])})\n"
            f"- **Classification:** {r.get('classification')}\n"
            f"- **Root Cause:** {r.get('root_cause')}\n"
            f"- **Fix:** {r.get('recommended_fix')}\n"
            f"- **Effort:** {r.get('estimated_fix_effort', 'TBD')} hours\n"
            for r in sorted(results, key=lambda x: {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}.get(x.get('priority', 'LOW'), 4))[:5]
        ])
    }
    
    report = format_agent_report("Job Failure Triage Report", report_sections)
    
    # Save report as agent output
    save_agent_output("job_failure_triage", run_id, "triage_report", report, 
                      {"jobs_analyzed": len(results), "critical": critical_count})
    
    print("\n" + report)
else:
    print("✅ No failures to report!")

# COMMAND ----------

# DBTITLE 1,Validation
# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

# Verify results table was created and has data
validation = spark.sql(f"""
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT classification) as distinct_classifications,
    SUM(CASE WHEN priority = 'CRITICAL' THEN 1 ELSE 0 END) as critical_count,
    SUM(CASE WHEN auto_fixable = true THEN 1 ELSE 0 END) as auto_fixable_count
FROM {CATALOG}.{SCHEMA}.agent_job_triage_results
WHERE run_id = '{run_id}'
""")

validation.display()
print(f"\n✅ Agent 01 (Job Failure Triage) completed successfully | Run ID: {run_id}")