# Databricks notebook source
# DBTITLE 1,Azure DevOps Agent
# MAGIC %md
# MAGIC # Agent 14 — Azure DevOps
# MAGIC
# MAGIC **Purpose:** Generate Azure DevOps work items (Epics, Features, User Stories, Tasks) from project plans.
# MAGIC
# MAGIC **Output:** AzureDevOps_Backlog.md + optional REST API calls to create items
# MAGIC
# MAGIC **Safety:** Human-in-the-loop gate — ALWAYS confirms before creating items in ADO.
# MAGIC
# MAGIC | Input | Output | Gate |
# MAGIC | --- | --- | --- |
# MAGIC | Project plan (from Agent 13 or manual) | Structured backlog + REST payload | User approval required before POST |

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Azure DevOps agent execution
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Configuration & Inputs
# ══════════════════════════════════════════════════════════════════════════════

DEVOPS_PROMPT = """You are an Azure DevOps specialist at Hologic. From the project plan, generate a complete backlog structure:

1. EPICS - high-level business capabilities
2. FEATURES - deliverable components under each Epic
3. USER STORIES - from the BA agent's stories, linked to Features
4. TASKS - technical tasks with effort estimates (hours)
5. ACCEPTANCE CRITERIA - for each story

Format each as:
```
[Epic] Title
  [Feature] Title
    [Story] As a... I want... So that...
      [Task] Description | Estimate: Xh | Assigned: Role
```

Also generate the Azure DevOps REST API JSON payload for bulk import.

IMPORTANT: Format the output clearly with a SUMMARY section at the top showing:
- Total Epics, Features, Stories, Tasks
- Estimated total effort (hours)
- Suggested sprint allocation
"""

# ── Input: from supervisor, widget, or prior agent output ────────────────────
try:
    PLAN_INPUT = dbutils.widgets.get("plan")
except:
    PLAN_INPUT = get_latest_agent_output("project_manager", "project_plan") or "No project plan available."

# ── Mode: dry_run (default) vs execute ───────────────────────────────────────
try:
    dbutils.widgets.dropdown("ado_mode", "DRY_RUN", ["DRY_RUN", "EXECUTE"])
except:
    pass
ADO_MODE = dbutils.widgets.get("ado_mode") if "ado_mode" in [w.name for w in dbutils.widgets.getAll()] else "DRY_RUN"

print(f"📋 ADO Agent 14 | Mode: {ADO_MODE}")
print(f"   Input length: {len(PLAN_INPUT)} chars")
print(f"   Source: {'widget' if 'plan' in [w.name for w in dbutils.widgets.getAll()] else 'project_manager agent output'}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Generate backlog (LLM call)
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Generate ADO Backlog via LLM
# FIX: Previously called call_agent("data_engineer", ...) — WRONG agent.
#      Now correctly uses "azure_devops" for proper attribution & model routing.
# ══════════════════════════════════════════════════════════════════════════════

run_id = generate_run_id()

print(f"🧠 Calling LLM (azure_devops) to generate backlog...")
result = call_agent(
    "azure_devops",  # ✅ FIXED: was "data_engineer" (wrong attribution + model routing)
    DEVOPS_PROMPT, 
    f"Generate DevOps backlog from:\n\n{PLAN_INPUT}", 
    max_tokens=4096
)

print(f"\n✅ Backlog generated | {len(result)} chars | Run ID: {run_id}")
print("=" * 60)
print(result[:3000])  # Preview first 3000 chars
if len(result) > 3000:
    print(f"\n... [{len(result) - 3000} more chars — full output saved to Delta]")

# COMMAND ----------

# DBTITLE 1,STEP 3: Human-in-the-Loop Approval Gate
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: HUMAN-IN-THE-LOOP APPROVAL GATE
#
# SAFETY: Agent MUST confirm before creating items in Azure DevOps.
# Default mode is DRY_RUN — generates backlog but does NOT POST to ADO.
# User must explicitly switch to EXECUTE mode AND approve.
# ══════════════════════════════════════════════════════════════════════════════

# Count proposed items
def _count_ado_items(text: str) -> dict:
    """Parse LLM output to count proposed work items."""
    counts = {
        "epics": text.lower().count("[epic]"),
        "features": text.lower().count("[feature]"),
        "stories": text.lower().count("[story]"),
        "tasks": text.lower().count("[task]"),
    }
    counts["total"] = sum(counts.values())
    return counts

counts = _count_ado_items(result)

print("\n" + "═" * 60)
print("🛡️  APPROVAL GATE — Azure DevOps Work Item Creation")
print("═" * 60)
print(f"\n   Proposed items to create in ADO:")
print(f"   • Epics:    {counts['epics']}")
print(f"   • Features: {counts['features']}")
print(f"   • Stories:  {counts['stories']}")
print(f"   • Tasks:    {counts['tasks']}")
print(f"   ──────────────────")
print(f"   • TOTAL:    {counts['total']} work items")
print(f"\n   Current mode: {ADO_MODE}")

if ADO_MODE == "DRY_RUN":
    print("\n   ✅ DRY RUN — No items will be created in Azure DevOps.")
    print("   → Review the backlog above.")
    print("   → To create items: set ado_mode widget to 'EXECUTE' and re-run.")
    
    # Save as draft (not pushed to ADO)
    save_agent_output("azure_devops", run_id, "backlog_draft", result, 
                      {"status": "DRY_RUN", "item_counts": counts})
    print(f"\n   💾 Draft saved to agent_outputs | Run ID: {run_id}")

elif ADO_MODE == "EXECUTE":
    # ── SECOND GATE: Even in EXECUTE mode, require explicit confirmation ──
    try:
        dbutils.widgets.dropdown("confirm_ado_create", "NO", ["NO", "YES_CREATE_IN_ADO"])
    except:
        pass
    
    confirmation = dbutils.widgets.get("confirm_ado_create") if "confirm_ado_create" in [w.name for w in dbutils.widgets.getAll()] else "NO"
    
    if confirmation != "YES_CREATE_IN_ADO":
        print("\n   ⛔ BLOCKED — Confirmation required.")
        print("   → Set 'confirm_ado_create' widget to 'YES_CREATE_IN_ADO' and re-run.")
        save_agent_output("azure_devops", run_id, "backlog_pending_approval", result,
                          {"status": "PENDING_APPROVAL", "item_counts": counts})
    else:
        print("\n   ✅ APPROVED — Creating items in Azure DevOps...")
        # TODO: Implement execute_ado_rest_api() with ADO PAT from secrets
        # For now, save as approved and log the intent
        save_agent_output("azure_devops", run_id, "backlog_approved", result,
                          {"status": "APPROVED", "item_counts": counts,
                           "action": "CREATE_IN_ADO", "approved_by": "human"})
        print(f"   💾 Approved backlog saved | Run ID: {run_id}")
        print("   ⚠️  ADO REST API execution not yet wired — implement execute_ado_rest_api()")

print("\n" + "═" * 60)
print(f"✅ Agent 14 (Azure DevOps) completed | Run ID: {run_id} | Mode: {ADO_MODE}")