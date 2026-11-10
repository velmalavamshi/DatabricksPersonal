# Databricks notebook source
# DBTITLE 1,NEXUS Master Scheduler
# MAGIC %md
# MAGIC # NEXUS Master Scheduler (W0)
# MAGIC
# MAGIC **Purpose:** Defines and deploys all NEXUS agent schedules as Databricks Serverless Jobs.
# MAGIC
# MAGIC ## Schedule Registry
# MAGIC | Job | Schedule | Agents | Cost/Run |
# MAGIC |---|---|---|---|
# MAGIC | NEXUS Morning Briefing | Daily 07:00 UTC | 39 → 40 | ~$0.05 |
# MAGIC | NEXUS Governance Cycle | Daily 06:00 UTC | 03→04→05→06→07 | ~$0.08 |
# MAGIC | NEXUS Monitoring Cycle | Daily 05:30 UTC | 10→11→12→13→14 | ~$0.10 |
# MAGIC | NEXUS W4 Intelligence | Weekly Sun 02:00 UTC | 01→02→03→04 | ~$0.12 |
# MAGIC | NEXUS Event Mesh | Every 15 min | 02_event_mesh | ~$0.01 |
# MAGIC | NEXUS Consultation Tracker | Every 30 min | 62_consultation_tracker | ~$0.01 |
# MAGIC
# MAGIC **Estimated monthly cost:** ~$12-16/month at $0.45/DBU serverless jobs.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Define Job Specifications
# ======================================================================
# STEP 1 — JOB SPECIFICATIONS
# All NEXUS scheduled jobs — Serverless Jobs Compute ($0.45/DBU)
# ======================================================================

import requests

BASE_PATH = "/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents"

NEXUS_JOBS = {
    "NEXUS_Morning_Briefing": {
        "description": "Daily morning briefing + auto-triage. Publishes critical alerts and creates ADO work items.",
        "schedule": {"quartz_cron_expression": "0 0 7 * * ?", "timezone_id": "UTC"},
        "tasks": [
            {"task_key": "briefing", "notebook_path": f"{BASE_PATH}/1 - Production Agents/39_morning_briefing_agent"},
            {"task_key": "triage", "notebook_path": f"{BASE_PATH}/1 - Production Agents/40_morning_triage_orchestrator", "depends_on": ["briefing"]},
        ],
        "tags": {"project": "NEXUS", "workspace": "W1", "priority": "P1"},
    },
    "NEXUS_Governance_Cycle": {
        "description": "Daily governance: versions, security, feedback, circuit breakers, dashboard.",
        "schedule": {"quartz_cron_expression": "0 0 6 * * ?", "timezone_id": "UTC"},
        "tasks": [
            {"task_key": "versions", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/03_version_manager"},
            {"task_key": "security", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/04_security_layer", "depends_on": ["versions"]},
            {"task_key": "feedback", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/05_feedback_system", "depends_on": ["versions"]},
            {"task_key": "breakers", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/06_circuit_breaker_manager", "depends_on": ["versions"]},
            {"task_key": "dashboard", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/07_governance_dashboard", "depends_on": ["security", "feedback", "breakers"]},
        ],
        "tags": {"project": "NEXUS", "workspace": "W0", "priority": "P2"},
    },
    "NEXUS_W4_Intelligence": {
        "description": "Weekly intelligence: pattern detection, benchmarks, failure prediction, digest.",
        "schedule": {"quartz_cron_expression": "0 0 2 ? * SUN", "timezone_id": "UTC"},
        "tasks": [
            {"task_key": "patterns", "notebook_path": f"{BASE_PATH}/4 - Collective Intelligence/01_pattern_detector"},
            {"task_key": "benchmarks", "notebook_path": f"{BASE_PATH}/4 - Collective Intelligence/02_benchmark_engine", "depends_on": ["patterns"]},
            {"task_key": "predictor", "notebook_path": f"{BASE_PATH}/4 - Collective Intelligence/03_failure_predictor", "depends_on": ["patterns"]},
            {"task_key": "publisher", "notebook_path": f"{BASE_PATH}/4 - Collective Intelligence/04_insight_publisher", "depends_on": ["benchmarks", "predictor"]},
        ],
        "tags": {"project": "NEXUS", "workspace": "W4", "priority": "P3"},
    },
    "NEXUS_Monitoring_Cycle": {
        "description": "Daily monitoring: audit trail, health dashboard, cost attribution, event bus monitor, leaderboard.",
        "schedule": {"quartz_cron_expression": "0 30 5 * * ?", "timezone_id": "UTC"},
        "tasks": [
            {"task_key": "audit", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/10_audit_trail"},
            {"task_key": "monitoring", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/11_monitoring_dashboard", "depends_on": ["audit"]},
            {"task_key": "cost", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/12_cost_attribution", "depends_on": ["audit"]},
            {"task_key": "eventbus", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/13_event_bus_monitor", "depends_on": ["audit"]},
            {"task_key": "leaderboard", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/14_agent_leaderboard", "depends_on": ["monitoring", "cost", "eventbus"]},
        ],
        "tags": {"project": "NEXUS", "workspace": "W0", "priority": "P2"},
    },
    "NEXUS_Event_Mesh": {
        "description": "Polls and dispatches events from the Delta event bus. Runs frequently.",
        "schedule": {"quartz_cron_expression": "0 */15 * * * ?", "timezone_id": "UTC"},
        "tasks": [
            {"task_key": "dispatch", "notebook_path": f"{BASE_PATH}/0 - Meta Orchestrator/02_event_mesh"},
        ],
        "tags": {"project": "NEXUS", "workspace": "W0", "priority": "P2"},
    },
    "NEXUS_Consultation_Tracker": {
        "description": "Monitors open specialist consultations, detects SLA breaches, publishes timeout events.",
        "schedule": {"quartz_cron_expression": "0 */30 * * * ?", "timezone_id": "UTC"},
        "tasks": [
            {"task_key": "tracker", "notebook_path": f"{BASE_PATH}/1 - Production Agents/62_consultation_tracker"},
        ],
        "tags": {"project": "NEXUS", "workspace": "W1", "priority": "P2"},
    },
}

print(f"📋 NEXUS Job Definitions: {len(NEXUS_JOBS)} jobs")
for name, spec in NEXUS_JOBS.items():
    tasks = len(spec['tasks'])
    cron = spec['schedule']['quartz_cron_expression']
    print(f"   {name:<30} {tasks} tasks | cron: {cron}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Deploy Jobs via REST API
# ======================================================================
# STEP 2 — DEPLOY JOBS VIA REST API
# Creates or resets jobs. All PAUSED by default (enable after testing)
# ======================================================================

def create_or_update_job(job_name, spec):
    """Create a Databricks Job from spec. If exists, resets it."""
    url = f"https://{WORKSPACE_URL}/api/2.1/jobs"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    # Build task list
    tasks = []
    for t in spec['tasks']:
        task = {
            "task_key": t['task_key'],
            "notebook_task": {"notebook_path": t['notebook_path'], "source": "WORKSPACE"},
            "environment_key": "default",
        }
        if 'depends_on' in t:
            task['depends_on'] = [{"task_key": dep} for dep in t['depends_on']]
        tasks.append(task)
    
    job_payload = {
        "name": job_name,
        "tasks": tasks,
        "schedule": spec['schedule'],
        "tags": spec.get('tags', {}),
        "queue": {"enabled": True},
        "environments": [{"environment_key": "default", "spec": {"client": "1"}}],
        "format": "MULTI_TASK",
    }
    
    # Check if job already exists
    list_resp = requests.get(f"{url}/list", headers=headers, params={"name": job_name}, timeout=30)
    existing = [j for j in list_resp.json().get('jobs', []) if j['settings']['name'] == job_name]
    
    if existing:
        job_id = existing[0]['job_id']
        # Reset (update) existing job
        reset_payload = {"job_id": job_id, "new_settings": job_payload}
        resp = requests.post(f"{url}/reset", headers=headers, json=reset_payload, timeout=30)
        if resp.status_code == 200:
            return job_id, "UPDATED"
        else:
            return None, f"RESET FAILED: {resp.text[:100]}"
    else:
        # Create new job (PAUSED)
        job_payload['schedule']['pause_status'] = 'PAUSED'
        resp = requests.post(f"{url}/create", headers=headers, json={"name": job_name, **job_payload}, timeout=30)
        if resp.status_code == 200:
            return resp.json().get('job_id'), "CREATED (PAUSED)"
        else:
            return None, f"CREATE FAILED: {resp.text[:100]}"

# Deploy all jobs
print("🚀 Deploying NEXUS Jobs...")
print("=" * 60)

deployed_jobs = {}
for job_name, spec in NEXUS_JOBS.items():
    job_id, status = create_or_update_job(job_name, spec)
    deployed_jobs[job_name] = {"job_id": job_id, "status": status}
    icon = '✅' if job_id else '❌'
    print(f"  {icon} {job_name:<30} → Job ID: {job_id} ({status})")

print("=" * 60)
print(f"\n⚠️ All new jobs created as PAUSED. Unpause after e2e testing.")