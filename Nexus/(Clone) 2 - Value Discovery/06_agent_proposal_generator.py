# Databricks notebook source
# DBTITLE 1,Agent 06 Header
# MAGIC %md
# MAGIC # Agent 06 — Agent Proposal Generator (W2)
# MAGIC
# MAGIC **Purpose:** Reads the top-scored gap and partial ideas from `idea_seed_library`, generates structured Databricks-native agent build proposals via LLM, and persists a prioritised backlog to `agent_build_backlog` for consumption by W1 Agent 63 (agent_factory).
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W2 (Value Discovery) |
# MAGIC | Inputs | `mde_dev.test_schema.idea_seed_library`, NEXUS coverage context |
# MAGIC | Outputs | `mde_dev.test_schema.agent_build_backlog`, `PROPOSAL_RESULTS` payload |
# MAGIC | Upstream | 05_idea_scanner → idea_seed_library |
# MAGIC | Downstream | W1 63_agent_factory_agent (builds proposals from backlog) |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_vd_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Parameters and Setup
# ======================================================================
# STEP 1 — PARAMETERS AND SETUP
# ======================================================================

AGENT_NAME   = "06_agent_proposal_generator"
run_id       = str(uuid.uuid4())
start_time   = datetime.now(timezone.utc)

dbutils.widgets.text("top_n",            "15",    "Top N ideas to propose")
dbutils.widgets.text("min_composite",    "5.0",   "Min composite score")
dbutils.widgets.dropdown("domain_filter","ALL",
    ["ALL","HEALTHCARE","SUPPLY_CHAIN","GENAI","ANALYTICS","PLATFORM","HCM","SFDC","EBS","OTHER"],
    "Domain filter")
dbutils.widgets.dropdown("force_refresh", "false", ["false","true"], "Force refresh")

TOP_N          = max(1, int(dbutils.widgets.get("top_n") or "15"))
MIN_COMPOSITE  = float(dbutils.widgets.get("min_composite") or "5.0")
DOMAIN_FILTER  = dbutils.widgets.get("domain_filter").strip().upper()
FORCE_REFRESH  = dbutils.widgets.get("force_refresh").strip().lower() == "true"

SOURCE_TABLE = f"{NEXUS_SCHEMA}.idea_seed_library"
TARGET_TABLE = f"{NEXUS_SCHEMA}.agent_build_backlog"

print("\U0001f9e0 Agent Proposal Generator starting")
print(f"   Source:         {SOURCE_TABLE}")
print(f"   Target:         {TARGET_TABLE}")
print(f"   Top N:          {TOP_N}")
print(f"   Min composite:  {MIN_COMPOSITE}")
print(f"   Domain filter:  {DOMAIN_FILTER}")
print(f"   Run ID:         {run_id}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Load and Filter idea_seed_library
# ======================================================================
# STEP 2 — LOAD AND FILTER IDEA SEED LIBRARY
# ======================================================================

from pyspark.sql import types as T

load_error = None
ideas_raw   = None

try:
    ideas_raw = spark.table(SOURCE_TABLE)
except Exception as e:
    load_error = str(e)
    print(f"⚠️ Cannot load {SOURCE_TABLE}: {load_error}")
    print("   Run 05_idea_scanner first, then retry.")
    raise

# Filter: gap or partial, above min composite score, optionally by domain
filter_cond = (
    (F.col("coverage_status").isin("gap", "partial")) &
    (F.col("composite_score") >= F.lit(MIN_COMPOSITE))
)
if DOMAIN_FILTER != "ALL":
    filter_cond = filter_cond & (F.col("domain_tag") == F.lit(DOMAIN_FILTER))

candidates_df = (
    ideas_raw
    .filter(filter_cond)
    .orderBy(F.col("composite_score").desc(), F.col("hologic_relevance_score").desc())
    .limit(TOP_N)
)

candidate_rows = [row.asDict() for row in candidates_df.collect()]

print(f"\n\U0001f4da Candidate ideas loaded: {len(candidate_rows)}")
print(f"   Total ideas in library: {ideas_raw.count():,}")
print(f"   Gap/partial above {MIN_COMPOSITE}: {ideas_raw.filter(filter_cond).count():,}")
if candidate_rows:
    print("\n   Top 5 candidates:")
    for r in candidate_rows[:5]:
        print(f"   [{r.get('domain_tag','?')}] {r['idea_name'][:60]} (score={r.get('composite_score','?')})")
display(candidates_df.select("idea_name","domain_tag","coverage_status",
                              "hologic_relevance_score","complexity_score","composite_score",
                              "matched_agent"))

# COMMAND ----------

# DBTITLE 1,STEP 3: LLM Proposal Generation
# ======================================================================
# STEP 3 — LLM PROPOSAL GENERATION
# ======================================================================
# For each candidate idea, generate a complete Databricks-native agent
# build proposal. BATCH_SIZE=5 to keep prompts focused and responses clean.

BATCH_SIZE = 5
proposals  = []
llm_error  = None

WORKSPACE_CHOICES = ["W0","W1","W2","W3","W4"]
LAYER_CHOICES     = ["strategy","specialist","execution","tool","skill","discovery","intelligence"]
LLM_TIER_CHOICES  = ["APEX","CRITICAL","STANDARD"]

for batch_idx in range(0, len(candidate_rows), BATCH_SIZE):
    batch = candidate_rows[batch_idx : batch_idx + BATCH_SIZE]
    if not batch:
        continue

    ideas_payload = []
    for idea in batch:
        ideas_payload.append({
            "idea_id":               idea["idea_id"],
            "idea_name":             idea["idea_name"],
            "description":           (idea.get("description") or "")[:300],
            "domain_tag":            idea.get("domain_tag") or "OTHER",
            "coverage_status":       idea.get("coverage_status") or "gap",
            "matched_agent":         idea.get("matched_agent") or "",
            "hologic_relevance":     idea.get("hologic_relevance_score") or 5,
            "composite_score":       idea.get("composite_score") or 5.0,
        })

    prompt = f"""You are a senior Databricks architect designing production AI agents for Hologic's NEXUS platform.

For each idea below, produce a complete build proposal for a new NEXUS agent. Be concrete and Databricks-native.

Hologic's stack (ONLY use these):
- Compute: Serverless Jobs, SQL Warehouses, Serverless notebooks
- Data: Delta Lake, Unity Catalog (mde_dev catalog), Liquid Clustering
- AI: Databricks Foundation Models (claude-sonnet-4-6, claude-opus-4-8)
- Pipelines: Spark Declarative Pipelines (SDP), Lakeflow Jobs
- Source systems: Oracle EBS (1263t), Salesforce (768t), ASCP (238t), HCM (147t), Agile PLM (82t), HCP (81t), PBCS (42t)
- Surrogates: xxhash64(CONCAT_WS('|', keys)) — NEVER MD5
- Audit: etl_load_datetime, etl_source_system, etl_batch_id

NEXUS workspaces: W0=Meta, W1=Production(strategy/specialist/execution), W2=Value Discovery, W3=Business Champions, W4=Collective Intelligence
LLM tiers: APEX=claude-opus-4-8 (architects only), CRITICAL/STANDARD=claude-sonnet-4-6

Return ONLY a valid JSON array. One object per idea. Preserve idea_id exactly.

Ideas:
{json.dumps(ideas_payload, indent=2)}

JSON schema per proposal:
{{
  "idea_id": "string — copy exactly",
  "proposed_agent_name": "snake_case, suffix _agent",
  "proposed_workspace": "W0|W1|W2|W3|W4",
  "proposed_layer": "strategy|specialist|execution|tool|skill|discovery|intelligence",
  "purpose_statement": "one sentence, Databricks-native framing",
  "inputs": "comma-separated: source tables / APIs / Delta tables needed",
  "outputs": "comma-separated: Delta tables, payloads, reports produced",
  "suggested_llm_tier": "APEX|CRITICAL|STANDARD",
  "estimated_effort_days": 1,
  "key_tables": "comma-separated fully qualified Delta table names",
  "implementation_notes": "2-3 sentences on key design decisions",
  "feasibility_score": 1,
  "build_priority": 1,
  "rationale": "max 150 chars — why this agent matters for Hologic"
}}
"""

    try:
        raw = call_llm(prompt, max_tokens=3000, temperature=0.1)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            parsed = parsed.get("proposals") or parsed.get("agents") or []
        for p in parsed:
            if not isinstance(p, dict):
                continue
            proposals.append({
                "idea_id":             str(p.get("idea_id", "")).strip(),
                "proposed_agent_name": str(p.get("proposed_agent_name", "tbd_agent")).strip()[:80],
                "proposed_workspace":  str(p.get("proposed_workspace", "W1")).strip()[:4],
                "proposed_layer":      str(p.get("proposed_layer", "execution")).strip()[:30],
                "purpose_statement":   str(p.get("purpose_statement", "")).strip()[:400],
                "inputs":              str(p.get("inputs", "")).strip()[:400],
                "outputs":             str(p.get("outputs", "")).strip()[:400],
                "suggested_llm_tier":  str(p.get("suggested_llm_tier", "STANDARD")).strip()[:10],
                "estimated_effort_days": max(1, min(90, int(p.get("estimated_effort_days", 3) or 3))),
                "key_tables":          str(p.get("key_tables", "")).strip()[:600],
                "implementation_notes":str(p.get("implementation_notes", "")).strip()[:600],
                "feasibility_score":   max(1, min(10, int(p.get("feasibility_score", 5) or 5))),
                "build_priority":      max(1, min(10, int(p.get("build_priority", 5) or 5))),
                "rationale":           str(p.get("rationale", "")).strip()[:150],
            })
    except Exception as e:
        llm_error = str(e)
        print(f"⚠️ LLM batch {(batch_idx // BATCH_SIZE)+1} failed: {llm_error}")

print(f"\n\U0001f4dd Proposals generated: {len(proposals)}")
if llm_error:
    print(f"   Last LLM error: {llm_error}")
if proposals:
    print("\n   Sample proposals:")
    for p in proposals[:3]:
        print(f"   [{p['proposed_workspace']}/{p['proposed_layer']}] {p['proposed_agent_name']} (priority={p['build_priority']}, effort={p['estimated_effort_days']}d)")

# COMMAND ----------

# DBTITLE 1,STEP 4: Enrich with idea metadata
# ======================================================================
# STEP 4 — ENRICH PROPOSALS WITH IDEA METADATA + SURROGATE KEY
# ======================================================================

if not proposals:
    print("⚠️ No proposals generated. Check LLM errors above.")
else:
    # Build idea metadata lookup from candidates
    idea_meta = {
        r["idea_id"]: {
            "idea_name":             r["idea_name"],
            "domain_tag":            r.get("domain_tag") or "OTHER",
            "coverage_status":       r.get("coverage_status") or "gap",
            "hologic_relevance_score": r.get("hologic_relevance_score") or 5,
            "composite_score":       r.get("composite_score") or 5.0,
        }
        for r in candidate_rows
    }

    enriched = []
    load_dt  = datetime.now(timezone.utc).isoformat()
    for p in proposals:
        meta = idea_meta.get(p["idea_id"], {})
        enriched.append({
            "proposal_id":             None,   # filled by xxhash64 below
            "idea_id":                 p["idea_id"],
            "idea_name":               meta.get("idea_name", "unknown"),
            "domain_tag":              meta.get("domain_tag", "OTHER"),
            "coverage_status":         meta.get("coverage_status", "gap"),
            "hologic_relevance_score": int(meta.get("hologic_relevance_score") or 5),
            "composite_score":         float(meta.get("composite_score") or 5.0),
            "proposed_agent_name":     p["proposed_agent_name"],
            "proposed_workspace":      p["proposed_workspace"],
            "proposed_layer":          p["proposed_layer"],
            "purpose_statement":       p["purpose_statement"],
            "inputs":                  p["inputs"],
            "outputs":                 p["outputs"],
            "suggested_llm_tier":      p["suggested_llm_tier"],
            "estimated_effort_days":   p["estimated_effort_days"],
            "key_tables":              p["key_tables"],
            "implementation_notes":    p["implementation_notes"],
            "feasibility_score":       p["feasibility_score"],
            "build_priority":          p["build_priority"],
            "rationale":               p["rationale"],
            "run_id":                  run_id,
            "etl_load_datetime":       load_dt,
            "etl_source_system":       "06_agent_proposal_generator",
            "etl_batch_id":            run_id,
        })

    proposal_schema = T.StructType([
        T.StructField("proposal_id",              T.StringType(),  True),
        T.StructField("idea_id",                  T.StringType(),  False),
        T.StructField("idea_name",                T.StringType(),  True),
        T.StructField("domain_tag",               T.StringType(),  True),
        T.StructField("coverage_status",          T.StringType(),  True),
        T.StructField("hologic_relevance_score",  T.IntegerType(), True),
        T.StructField("composite_score",          T.DoubleType(),  True),
        T.StructField("proposed_agent_name",      T.StringType(),  True),
        T.StructField("proposed_workspace",       T.StringType(),  True),
        T.StructField("proposed_layer",           T.StringType(),  True),
        T.StructField("purpose_statement",        T.StringType(),  True),
        T.StructField("inputs",                   T.StringType(),  True),
        T.StructField("outputs",                  T.StringType(),  True),
        T.StructField("suggested_llm_tier",       T.StringType(),  True),
        T.StructField("estimated_effort_days",    T.IntegerType(), True),
        T.StructField("key_tables",               T.StringType(),  True),
        T.StructField("implementation_notes",     T.StringType(),  True),
        T.StructField("feasibility_score",        T.IntegerType(), True),
        T.StructField("build_priority",           T.IntegerType(), True),
        T.StructField("rationale",                T.StringType(),  True),
        T.StructField("run_id",                   T.StringType(),  True),
        T.StructField("etl_load_datetime",        T.StringType(),  True),
        T.StructField("etl_source_system",        T.StringType(),  False),
        T.StructField("etl_batch_id",             T.StringType(),  False),
    ])

    proposals_df = (
        spark.createDataFrame(enriched, schema=proposal_schema)
        .withColumn(
            "proposal_id",
            F.expr("CAST(xxhash64(CONCAT_WS('|', idea_id, proposed_agent_name, run_id)) AS STRING)")
        )
        .withColumn("etl_load_datetime", F.col("etl_load_datetime").cast("timestamp"))
        .orderBy(F.col("build_priority").desc(), F.col("composite_score").desc())
    )

    print(f"\u2705 Proposals enriched: {proposals_df.count()}")
    display(proposals_df.select(
        "proposed_agent_name", "proposed_workspace", "proposed_layer",
        "domain_tag", "build_priority", "feasibility_score",
        "estimated_effort_days", "suggested_llm_tier", "purpose_statement"
    ))

# COMMAND ----------

# DBTITLE 1,STEP 5: Persist, Validate, and Publish
# ======================================================================
# STEP 5 — PERSIST TO DELTA + VALIDATE + PUBLISH
# Always reassert TARGET_TABLE to guard against session variable override
# ======================================================================
TARGET_TABLE = f"{NEXUS_SCHEMA}.agent_build_backlog"

if not proposals or proposals_df is None:
    print("⚠️ No proposals to persist. Exiting.")
else:
    proposals_df.createOrReplaceTempView("agent_build_backlog_batch")

    spark.sql(f"""
    CREATE OR REPLACE TABLE {TARGET_TABLE}
    USING DELTA
    AS SELECT * FROM agent_build_backlog_batch
    """)

    try:
        spark.sql(f"ALTER TABLE {TARGET_TABLE} CLUSTER BY (domain_tag, proposed_workspace, build_priority)")
    except Exception:
        pass

    final_count = spark.table(TARGET_TABLE).count()
    top_priority = (
        spark.table(TARGET_TABLE)
        .filter(F.col("build_priority") >= 7)
        .orderBy(F.col("build_priority").desc(), F.col("composite_score").desc())
        .select("proposed_agent_name", "domain_tag", "build_priority",
                "estimated_effort_days", "suggested_llm_tier", "purpose_statement")
    )

    # ---- Summary ----
    ws_counts = {}
    for r in spark.table(TARGET_TABLE).groupBy("proposed_workspace").count().collect():
        ws_counts[r["proposed_workspace"]] = r["count"]

    tier_counts = {}
    for r in spark.table(TARGET_TABLE).groupBy("suggested_llm_tier").count().collect():
        tier_counts[r["suggested_llm_tier"]] = r["count"]

    avg_effort = spark.table(TARGET_TABLE).agg(F.avg("estimated_effort_days")).collect()[0][0] or 0

    PROPOSAL_RESULTS = {
        "agent_name":    AGENT_NAME,
        "run_id":        run_id,
        "source_table":  SOURCE_TABLE,
        "target_table":  TARGET_TABLE,
        "proposals":     final_count,
        "high_priority": top_priority.count(),
        "by_workspace":  ws_counts,
        "by_llm_tier":   tier_counts,
        "avg_effort_days": round(avg_effort, 1),
        "status":        "success",
    }

    print("\n" + "=" * 70)
    print("AGENT PROPOSAL GENERATOR COMPLETE")
    print("=" * 70)
    print(f"Total proposals:        {final_count}")
    print(f"High priority (>=7):    {PROPOSAL_RESULTS['high_priority']}")
    print(f"Avg estimated effort:   {avg_effort:.1f} days")
    print(f"By workspace:           {ws_counts}")
    print(f"By LLM tier:            {tier_counts}")
    print(f"Persisted to:           {TARGET_TABLE}")
    print("=" * 70)

    display(top_priority)

    try:
        save_agent_output(AGENT_NAME, run_id, "proposal_summary", json.dumps(PROPOSAL_RESULTS))
    except Exception:
        print("\u2139️ save_agent_output not available in W2 config; summary retained in PROPOSAL_RESULTS")

# COMMAND ----------

