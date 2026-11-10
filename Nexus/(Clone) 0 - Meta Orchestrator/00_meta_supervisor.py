# Databricks notebook source
# DBTITLE 1,Meta Supervisor
# MAGIC %md
# MAGIC # NEXUS Meta Supervisor (W0)
# MAGIC
# MAGIC **Purpose:** Top-level orchestrator that receives natural language requests, classifies intent, and routes to the correct workspace supervisor (W1–W4).
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | STRATEGY |
# MAGIC | Workspace | W0 (Meta Orchestrator) |
# MAGIC | Inputs | Natural language request |
# MAGIC | Outputs | Routed response from target workspace supervisor |
# MAGIC | LLM | databricks-claude-sonnet-4-6 (intent classification + response synthesis) |

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Intent Classification
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — INTENT CLASSIFICATION
# Uses LLM to classify user request into workspace + confidence
# ══════════════════════════════════════════════════════════════════════════════

INTENT_PROMPT_TEMPLATE = """You are the NEXUS Meta Supervisor. Classify the user's request into the correct workspace.

Workspaces:
- W1 (Production Agents): Internal Databricks operations — jobs, pipelines, cost, data quality, deployment, testing, architecture, security, documentation, source system specialists (Oracle EBS, Salesforce, ASCP, HCM, Agile, PBCS, HCP, ServiceNow, Power BI, Cornerstone, MuleSoft, Koerber, Definitive)
- W2 (Value Discovery): Client assessments — scanning client workspaces, scoring AI use cases, maturity analysis, ROI estimates, assessment reports
- W3 (Business Champions): Board-ready deliverables — business cases, PowerPoint decks, executive summaries, champion coaching, value signals
- W4 (Collective Intelligence): Cross-client learning — benchmarks, pattern detection, failure prediction, competitive intelligence, commercial pipeline

Respond ONLY with valid JSON:
{{
  "workspace": "W1" or "W2" or "W3" or "W4",
  "confidence": 0.0 to 1.0,
  "reasoning": "one sentence why",
  "suggested_agent": "agent_name or null if unsure"
}}

User request: {user_request}
"""

def classify_intent(user_request):
    """Classifies user intent into a target workspace using LLM."""
    # First try keyword matching (fast, no LLM cost)
    quick_match = get_workspace_for_domain(user_request)
    
    # If keywords give clear signal, use that
    keyword_score = sum(
        1 for d in WORKSPACE_REGISTRY[quick_match]['domains']
        if d.lower() in user_request.lower()
    )
    
    if keyword_score >= 2:
        return {
            "workspace": quick_match,
            "confidence": min(0.7 + keyword_score * 0.1, 0.95),
            "reasoning": f"Keyword match ({keyword_score} domain terms) for {WORKSPACE_REGISTRY[quick_match]['name']}",
            "suggested_agent": None,
            "method": "keyword"
        }
    
    # LLM classification for ambiguous requests
    try:
        prompt = INTENT_PROMPT_TEMPLATE.format(user_request=user_request)
        response = call_llm(prompt, max_tokens=200, temperature=0.0)
        
        # Parse JSON from response
        # Handle potential markdown code blocks
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        
        result = json.loads(clean)
        result["method"] = "llm"
        return result
    except Exception as e:
        # Fallback to keyword match
        return {
            "workspace": quick_match,
            "confidence": 0.5,
            "reasoning": f"LLM classification failed ({str(e)[:50]}), using keyword fallback",
            "suggested_agent": None,
            "method": "fallback"
        }

print("✅ Intent classification engine ready")

# COMMAND ----------

# DBTITLE 1,STEP 2: Request Router
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — REQUEST ROUTER
# Routes classified intent to the correct workspace supervisor
# ══════════════════════════════════════════════════════════════════════════════

def route_request(user_request, run_id=None):
    """Full pipeline: classify intent → route to workspace supervisor → return response."""
    if not run_id:
        run_id = generate_run_id()
    
    start = datetime.now(timezone.utc)
    
    # 1. Classify intent
    classification = classify_intent(user_request)
    target_ws = classification['workspace']
    confidence = classification.get('confidence', 0.5)
    ws_info = WORKSPACE_REGISTRY[target_ws]
    
    print(f"🎯 Routed to: {target_ws} ({ws_info['name']}) | Confidence: {confidence:.0%}")
    print(f"   Method: {classification.get('method', 'unknown')} | Reason: {classification.get('reasoning', '')}")
    
    # 2. Build context for workspace supervisor
    supervisor_context = {
        "user_request": user_request,
        "classification": classification,
        "meta_run_id": run_id,
        "timestamp": start.isoformat(),
    }
    
    # 3. Route to workspace supervisor
    # For W1: use the existing call_agent pattern from 00_supervisor_agent
    # For W2-W4: publish event for async processing or call directly
    if target_ws == "W1":
        # W1 supervisor already exists — call it via LLM with its system prompt
        w1_prompt = f"""You are the W1 Production Agents Supervisor. 
A request has been routed to you by the Meta Orchestrator.

User request: {user_request}

Classification: {json.dumps(classification)}

You have access to these specialist agents:
{json.dumps([{"name": a[1], "desc": a[4]} for a in get_w1_agents()], indent=2)}

Provide a helpful response. If you need to delegate to a specific agent, name it."""
        try:
            response = call_llm(w1_prompt, max_tokens=1500, temperature=0.2)
            return {
                "status": "SUCCESS",
                "workspace": target_ws,
                "response": response,
                "classification": classification,
                "run_id": run_id,
                "duration_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            }
        except Exception as e:
            return {"status": "FAILED", "workspace": target_ws, "error": str(e), "run_id": run_id}
    else:
        # W2/W3/W4: publish as event for their supervisors to consume
        event_id = publish_event(
            source_agent="00_meta_supervisor",
            event_type="REQUEST_ROUTED",
            payload=supervisor_context,
            target_agent=ws_info['supervisor'],
            workspace=target_ws,
            priority="P2"
        )
        return {
            "status": "ROUTED_ASYNC",
            "workspace": target_ws,
            "event_id": event_id,
            "message": f"Request published to {target_ws} ({ws_info['name']}). Supervisor '{ws_info['supervisor']}' will process.",
            "classification": classification,
            "run_id": run_id,
        }

def get_w1_agents():
    """Get active W1 agents from registry."""
    rows = spark.sql(f"""
        SELECT agent_number, agent_name, layer, parent_agents, description
        FROM {NEXUS_REGISTRY}
        WHERE workspace = 'W1' AND status IN ('ACTIVE', 'DEVELOPMENT')
        ORDER BY agent_number
    """).collect()
    return [(r['agent_number'], r['agent_name'], r['layer'], r['parent_agents'], r['description']) for r in rows]

print("✅ Request router ready")

# COMMAND ----------

# DBTITLE 1,STEP 3: Interactive Entry Point
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — INTERACTIVE ENTRY POINT
# Widget-based interface for ad-hoc queries
# ══════════════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "Enter your request")
user_input = dbutils.widgets.get("request")

if user_input.strip():
    print(f"\n📨 Processing: {user_input}")
    print("─" * 60)
    result = route_request(user_input)
    print("─" * 60)
    
    if result['status'] == 'SUCCESS':
        print(f"\n💬 Response from {result['workspace']}:")
        print(result['response'])
    elif result['status'] == 'ROUTED_ASYNC':
        print(f"\n📡 {result['message']}")
        print(f"   Event ID: {result.get('event_id', 'N/A')}")
    else:
        print(f"\n❌ Error: {result.get('error', 'Unknown')}")
else:
    print("👋 NEXUS Meta Supervisor ready.")
    print("   Enter a request in the widget above, or call route_request('your question') directly.")
    print(f"\n   Available workspaces:")
    for ws_id, ws_info in WORKSPACE_REGISTRY.items():
        print(f"   • {ws_id}: {ws_info['name']} — {ws_info['purpose']}")