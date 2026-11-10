# Databricks notebook source
# DBTITLE 1,Idea Scanner
# MAGIC %md
# MAGIC # Agent 05 — Idea Scanner (W2)
# MAGIC
# MAGIC **Purpose:** Scans external idea libraries, normalizes candidate AI agent ideas, cross-references current NEXUS coverage, and ranks the best net-new opportunities for Hologic.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W2 (Value Discovery) |
# MAGIC | Inputs | External idea source URL, NEXUS registry, optional prior W2 outputs |
# MAGIC | Outputs | `mde_dev.test_schema.idea_seed_library`, ranked gap list, `IDEA_SCAN_RESULTS` payload |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_vd_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Parameters and Setup
# ======================================================================
# STEP 1 — PARAMETERS AND SETUP
# ======================================================================

AGENT_NAME = "05_idea_scanner"
run_id = str(uuid.uuid4())
start_time = datetime.now(timezone.utc)

# External source and ranking controls
dbutils.widgets.text(
    "source_url",
    "https://raw.githubusercontent.com/ashishpatel26/500-AI-Agents-Projects/main/README.md",
    "Source URL"
)
dbutils.widgets.text("top_n", "10", "Top N ideas")
dbutils.widgets.dropdown("force_refresh", "false", ["false", "true"], "Force Refresh")

SOURCE_URL = dbutils.widgets.get("source_url").strip()
TOP_N = max(1, int(dbutils.widgets.get("top_n") or "10"))
FORCE_REFRESH = dbutils.widgets.get("force_refresh").strip().lower() == "true"
SCRAPE_DATE = datetime.now(timezone.utc).date().isoformat()
TARGET_TABLE = f"{NEXUS_SCHEMA}.idea_seed_library"
OUTPUT_TABLE = f"{NEXUS_SCHEMA}.agent_outputs"
REGISTRY_CANDIDATES = [
    f"{NEXUS_SCHEMA}.agent_registry",
    NEXUS_REGISTRY,
]

print("🔎 Idea Scanner starting")
print(f"   Source URL: {SOURCE_URL}")
print(f"   Top N: {TOP_N}")
print(f"   Force refresh: {FORCE_REFRESH}")
print(f"   Target table: {TARGET_TABLE}")
print(f"   Run ID: {run_id}")

# COMMAND ----------

# DBTITLE 1,STEP 2: Fetch and Parse Ideas
# ======================================================================
# STEP 2 — FETCH AND PARSE IDEA LIBRARY
# ======================================================================

import re
from pyspark.sql import Row
from pyspark.sql import types as T

readme_text = ""
fetch_status = "not_started"
fetch_error = None
idea_records = []
source_metadata = {}


def _clean_text(value: str) -> str:
    if value is None:
        return ""
    value = re.sub(r"`+", "", value)
    value = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("|", " - ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -:\t")


def _looks_like_idea(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    if len(text) < 12:
        return False
    if lower.startswith(("#", "---", "table of contents", "license", "contributing")):
        return False
    keywords = [
        "agent", "assistant", "copilot", "automation", "predict", "forecast",
        "anomaly", "recommend", "optimi", "monitor", "triage", "generate",
        "summar", "classif", "detect", "planner", "scorer", "search", "chatbot",
        "diagnostic", "insight", "fraud", "inventory", "pricing", "claims", "clinical"
    ]
    return any(k in lower for k in keywords)


def _append_idea(name: str, description: str, section: str, collector: list):
    clean_name = _clean_text(name)
    clean_desc = _clean_text(description)
    if not clean_name or len(clean_name) < 5:
        return
    if len(clean_name) > 180:
        clean_desc = (clean_name[180:] + " " + clean_desc).strip()
        clean_name = clean_name[:180].rsplit(" ", 1)[0]
    if not _looks_like_idea(clean_name + " " + clean_desc):
        return
    collector.append({
        "idea_name": clean_name,
        "description": clean_desc[:4000],
        "source_section": section or "General",
        "source_repo": SOURCE_URL,
        "scrape_date": SCRAPE_DATE,
        "run_id": run_id,
    })


try:
    response = requests.get(SOURCE_URL, timeout=60)
    response.raise_for_status()
    readme_text = response.text
    fetch_status = "success"
except Exception as e:
    fetch_status = "failed"
    fetch_error = str(e)
    print(f"⚠️ GitHub fetch failed: {fetch_error}")

if readme_text:
    current_section = "General"
    lines = readme_text.splitlines()
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            current_section = _clean_text(stripped.lstrip("#").strip()) or current_section
            continue

        if re.match(r"^\|.+\|$", stripped):
            cells = [_clean_text(part) for part in stripped.strip("|").split("|")]
            if len(cells) >= 2 and not all(set(c) <= {"-", ":"} for c in cells):
                joined = " ".join(cells).lower()
                if "project" in joined or "idea" in joined or "agent" in joined or _looks_like_idea(joined):
                    name = cells[0]
                    description = " | ".join(cells[1:])
                    _append_idea(name, description, current_section, idea_records)
            continue

        bullet_match = re.match(r"^\s*[-*+]\s+(.*)$", stripped)
        ordered_match = re.match(r"^\s*\d+[.)]\s+(.*)$", stripped)
        content = None
        if bullet_match:
            content = bullet_match.group(1)
        elif ordered_match:
            content = ordered_match.group(1)

        if content:
            if " - " in content:
                name, description = content.split(" - ", 1)
            elif ": " in content:
                name, description = content.split(": ", 1)
            else:
                name, description = content, current_section
            _append_idea(name, description, current_section, idea_records)
            continue

        if _looks_like_idea(stripped) and len(stripped.split()) <= 14:
            _append_idea(stripped, current_section, current_section, idea_records)

    deduped = {}
    for item in idea_records:
        key = (item["idea_name"].lower(), item["source_section"].lower())
        if key not in deduped or len(item["description"]) > len(deduped[key]["description"]):
            deduped[key] = item
    idea_records = list(deduped.values())

source_metadata = {
    "fetch_status": fetch_status,
    "fetch_error": fetch_error,
    "source_url": SOURCE_URL,
    "raw_length": len(readme_text),
    "ideas_parsed": len(idea_records),
}

idea_schema = T.StructType([
    T.StructField("idea_name", T.StringType(), False),
    T.StructField("description", T.StringType(), True),
    T.StructField("source_section", T.StringType(), True),
    T.StructField("source_repo", T.StringType(), True),
    T.StructField("scrape_date", T.StringType(), True),
    T.StructField("run_id", T.StringType(), True),
])

if idea_records:
    ideas_df = spark.createDataFrame(idea_records, schema=idea_schema)
else:
    fallback_record = [{
        "idea_name": "Idea source fetch failure",
        "description": fetch_error or "No ideas parsed from source",
        "source_section": "Error",
        "source_repo": SOURCE_URL,
        "scrape_date": SCRAPE_DATE,
        "run_id": run_id,
    }]
    ideas_df = spark.createDataFrame(fallback_record, schema=idea_schema)

ideas_df = (
    ideas_df
    .withColumn("idea_id", F.expr("CAST(xxhash64(concat_ws('|', coalesce(idea_name,''), coalesce(source_section,''), coalesce(source_repo,''))) AS STRING)"))
    .withColumn("scrape_date", F.to_date("scrape_date"))
    .withColumn("etl_load_datetime", F.current_timestamp())
    .withColumn("etl_source_system", F.lit("github_500_ai_agents"))
    .withColumn("etl_batch_id", F.lit(run_id))
    .withColumn("domain_tag", F.lit(None).cast("string"))
    .withColumn("hologic_relevance_score", F.lit(None).cast("int"))
    .withColumn("coverage_status", F.lit("unclassified"))
    .withColumn("matched_agent", F.lit(None).cast("string"))
    .withColumn("complexity_score", F.lit(None).cast("int"))
    .withColumn("composite_score", F.lit(None).cast("double"))
)

print(f"\n📥 Fetch status: {fetch_status}")
print(f"   Parsed ideas: {ideas_df.count():,}")
print(f"   Raw README chars: {len(readme_text):,}")
if fetch_error:
    print(f"   Fetch error: {fetch_error}")
display(ideas_df.select("idea_name", "source_section", "description").limit(10))

# COMMAND ----------

# DBTITLE 1,STEP 3: Cross Reference NEXUS Coverage
# ======================================================================
# STEP 3 — CROSS-REFERENCE NEXUS COVERAGE
# ======================================================================

registry_df = None
registry_source = None
registry_error = None

for candidate in REGISTRY_CANDIDATES:
    try:
        # Use fully-qualified single-arg form — 2-arg form is deprecated in Spark Connect
        exists = spark.catalog.tableExists(candidate)
        if exists:
            registry_df = spark.table(candidate)
            registry_source = candidate
            break
        else:
            registry_error = f"{candidate} not found"
    except Exception as e:
        registry_error = str(e)

if registry_df is None:
    print(f"⚠️ Registry not available. Coverage will default to gap. Last error: {registry_error}")
    coverage_df = (
        ideas_df
        .withColumn("coverage_status", F.lit("gap"))
        .withColumn("matched_agent", F.lit(None).cast("string"))
    )
else:
    registry_cols = {c.lower(): c for c in registry_df.columns}
    print(f"   Registry columns available: {list(registry_cols.keys())}")

    agent_name_col = (registry_cols.get("agent_name") or registry_cols.get("agent_key")
                      or registry_cols.get("name") or registry_cols.get("agent"))
    desc_col       = (registry_cols.get("purpose") or registry_cols.get("description")
                      or registry_cols.get("summary"))
    domain_col     = (registry_cols.get("domain_keywords") or registry_cols.get("domain")
                      or registry_cols.get("keywords") or registry_cols.get("capabilities"))

    if agent_name_col is None:
        print(f"⚠️ Cannot detect agent_name column in registry. Defaulting to gap.")
        registry_df = None
    else:
        selected_cols = [c for c in [agent_name_col, desc_col, domain_col] if c]
        registry_base = registry_df.select(*selected_cols).dropna(subset=[agent_name_col]).dropDuplicates([agent_name_col])
    if desc_col and domain_col:
        registry_base = registry_base.withColumn(
            "search_text",
            F.lower(F.concat_ws(" ", F.col(agent_name_col), F.col(desc_col), F.col(domain_col)))
        )
    elif desc_col:
        registry_base = registry_base.withColumn(
            "search_text",
            F.lower(F.concat_ws(" ", F.col(agent_name_col), F.col(desc_col)))
        )
    else:
        registry_base = registry_base.withColumn("search_text", F.lower(F.col(agent_name_col)))

    keywords = [
        ("oracle", "oracle_ebs_specialist_agent", "covered"),
        ("ebs", "oracle_ebs_specialist_agent", "covered"),
        ("salesforce", "salesforce_sync_agent", "covered"),
        ("hcm", "oracle_hcm_specialist_agent", "covered"),
        ("supply chain", "ascp_specialist_agent", "covered"),
        ("inventory", "ascp_specialist_agent", "partial"),
        ("forecast", "use_case_scorer", "partial"),
        ("vector search", "vector_search_agent", "covered"),
        ("rag", "vector_search_agent", "covered"),
        ("dashboard", "ai_bi_dashboard_agent", "covered"),
        ("genie", "genie_space_agent", "covered"),
        ("cost", "cost_optimization", "partial"),
        ("governance", "unity_catalog_agent", "covered"),
        ("pipeline", "sdp_agent", "covered"),
        ("mlflow", "mlflow_model_serving_agent", "covered"),
    ]

    keyword_df = spark.createDataFrame(keywords, ["keyword", "matched_agent_hint", "coverage_hint"])

if registry_df is None:
    print(f"⚠️ Registry not available. Coverage will default to gap. Last error: {registry_error}")
    coverage_df = (
        ideas_df
        .withColumn("coverage_status", F.lit("gap"))
        .withColumn("matched_agent", F.lit(None).cast("string"))
    )
else:
    # Continue with registry-based coverage (registry_base already built above)
    pass

if registry_df is not None:
    registry_map = (
        registry_base
        .withColumnRenamed(agent_name_col, "matched_agent_name")
        .select("matched_agent_name", "search_text")
    )

    idea_keywords = (
        ideas_df
        .withColumn("idea_text", F.lower(F.concat_ws(" ", F.col("idea_name"), F.col("description"), F.col("source_section"))))
        .crossJoin(keyword_df)
        .where(F.instr(F.col("idea_text"), F.col("keyword")) > 0)
        .groupBy("idea_id")
        .agg(
            F.first("matched_agent_hint").alias("matched_agent_hint"),
            F.first("coverage_hint").alias("coverage_hint")
        )
    )

    idea_agent_matches = (
        ideas_df
        .withColumn("idea_text", F.lower(F.concat_ws(" ", F.col("idea_name"), F.col("description"), F.col("source_section"))))
        .crossJoin(registry_map)
        .where(
            (F.length("matched_agent_name") > 3) & (
                (F.instr(F.col("idea_text"), F.regexp_replace(F.lower(F.col("matched_agent_name")), "_agent|_tool|_", " ")) > 0) |
                (F.instr(F.col("search_text"), F.col("idea_name")) > 0)
            )
        )
        .groupBy("idea_id")
        .agg(F.first("matched_agent_name").alias("registry_match"))
    )

    coverage_df = (
        ideas_df
        .join(idea_keywords, on="idea_id", how="left")
        .join(idea_agent_matches, on="idea_id", how="left")
        .withColumn(
            "matched_agent",
            F.coalesce(F.col("registry_match"), F.col("matched_agent_hint"))
        )
        .withColumn(
            "coverage_status",
            F.when(F.col("registry_match").isNotNull(), F.lit("covered"))
             .when(F.col("coverage_hint").isNotNull(), F.col("coverage_hint"))
             .otherwise(F.lit("gap"))
        )
        .drop("idea_text", "matched_agent_hint", "coverage_hint", "registry_match")
    )

    print(f"✅ Registry source: {registry_source}")
    print(f"   Registry columns used: {selected_cols}")

coverage_summary = coverage_df.groupBy("coverage_status").count().orderBy("coverage_status")
display(coverage_summary)

# COMMAND ----------

# DBTITLE 1,STEP 4: Score Gap and Partial Ideas
# ======================================================================
# STEP 4 — SCORE GAP AND PARTIAL IDEAS
# ======================================================================

import math

SCORING_DOMAINS = ["EBS", "SFDC", "HCM", "SUPPLY_CHAIN", "HEALTHCARE", "GENAI", "ANALYTICS", "PLATFORM", "OTHER"]
BATCH_SIZE = 15
MAX_BATCHES = 4

scoring_candidates = (
    coverage_df
    .filter(F.col("coverage_status").isin("gap", "partial"))
    .select("idea_id", "idea_name", "description", "source_section", "coverage_status", "matched_agent")
    .limit(BATCH_SIZE * MAX_BATCHES)
)

candidate_rows = [row.asDict() for row in scoring_candidates.collect()]
llm_scores = []
llm_error = None

for batch_idx in range(0, len(candidate_rows), BATCH_SIZE):
    batch = candidate_rows[batch_idx:batch_idx + BATCH_SIZE]
    if not batch:
        continue

    prompt_payload = []
    for item in batch:
        prompt_payload.append({
            "idea_id": item["idea_id"],
            "idea_name": item["idea_name"],
            "description": item.get("description") or "",
            "source_section": item.get("source_section") or "",
            "coverage_status": item.get("coverage_status") or "gap",
            "matched_agent": item.get("matched_agent") or "",
        })

    score_prompt = f"""You are scoring external AI agent ideas for Hologic inside Databricks.
Return ONLY valid JSON array. One object per input idea.

Allowed domain_tag values: {SCORING_DOMAINS}
Rules:
- hologic_relevance_score: integer 1-10
- complexity_score: integer 1-10 where 10 is hardest to implement on Databricks
- keep rationale under 140 characters
- preserve idea_id exactly
- prefer Databricks-native framing (Unity Catalog, Delta Lake, Lakeflow Jobs, Lakehouse AI)

Ideas to score:
{json.dumps(prompt_payload, indent=2)}

JSON schema:
[
  {{
    "idea_id": "string",
    "domain_tag": "one allowed value",
    "hologic_relevance_score": 1,
    "complexity_score": 1,
    "rationale": "short text"
  }}
]
"""

    try:
        raw_response = call_llm(score_prompt, max_tokens=2500, temperature=0.1)
        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            parsed = parsed.get("ideas") or parsed.get("results") or []
        for scored in parsed:
            if not isinstance(scored, dict):
                continue
            idea_id = str(scored.get("idea_id", "")).strip()
            domain_tag = str(scored.get("domain_tag", "OTHER")).strip().upper()
            if domain_tag not in SCORING_DOMAINS:
                domain_tag = "OTHER"
            try:
                relevance = int(scored.get("hologic_relevance_score", 5))
            except Exception:
                relevance = 5
            try:
                complexity = int(scored.get("complexity_score", 5))
            except Exception:
                complexity = 5
            llm_scores.append({
                "idea_id": idea_id,
                "domain_tag": domain_tag,
                "hologic_relevance_score": max(1, min(10, relevance)),
                "complexity_score": max(1, min(10, complexity)),
                "llm_rationale": str(scored.get("rationale", "")).strip()[:140],
            })
    except Exception as e:
        llm_error = str(e)
        print(f"⚠️ LLM scoring batch {(batch_idx // BATCH_SIZE) + 1} failed: {llm_error}")

score_schema = T.StructType([
    T.StructField("idea_id", T.StringType(), False),
    T.StructField("domain_tag", T.StringType(), True),
    T.StructField("hologic_relevance_score", T.IntegerType(), True),
    T.StructField("complexity_score", T.IntegerType(), True),
    T.StructField("llm_rationale", T.StringType(), True),
])

if llm_scores:
    scores_df = spark.createDataFrame(llm_scores, schema=score_schema)
else:
    fallback_scores = [
        {
            "idea_id": row["idea_id"],
            "domain_tag": "OTHER",
            "hologic_relevance_score": 5,
            "complexity_score": 5,
            "llm_rationale": "Defaulted because LLM scoring was unavailable"
        }
        for row in candidate_rows
    ]
    scores_df = spark.createDataFrame(fallback_scores, schema=score_schema) if fallback_scores else spark.createDataFrame([], schema=score_schema)

scores_lookup_df = (
    scores_df
    .withColumnRenamed("domain_tag", "scored_domain_tag")
    .withColumnRenamed("hologic_relevance_score", "scored_hologic_relevance_score")
    .withColumnRenamed("complexity_score", "scored_complexity_score")
)

scored_df = (
    coverage_df
    .join(scores_lookup_df, on="idea_id", how="left")
    .withColumn("domain_tag", F.coalesce(F.col("scored_domain_tag"), F.col("domain_tag"), F.lit("OTHER")))
    .withColumn("hologic_relevance_score", F.coalesce(F.col("scored_hologic_relevance_score"), F.col("hologic_relevance_score"), F.lit(5)))
    .withColumn("complexity_score", F.coalesce(F.col("scored_complexity_score"), F.col("complexity_score"), F.lit(5)))
    .withColumn(
        "composite_score",
        F.round(F.col("hologic_relevance_score") * F.lit(0.6) + (F.lit(11) - F.col("complexity_score")) * F.lit(0.4), 2)
    )
    .withColumn("scoring_rationale", F.col("llm_rationale"))
    .drop("scored_domain_tag", "scored_hologic_relevance_score", "scored_complexity_score", "llm_rationale")
)

print(f"\n🧠 Scoring candidates: {len(candidate_rows):,}")
print(f"   LLM scored rows: {scores_df.count():,}")
if llm_error:
    print(f"   Last LLM error: {llm_error}")

# COMMAND ----------

# DBTITLE 1,STEP 5: Persist Delta Table
# ======================================================================
# STEP 5 — PERSIST TO DELTA
# ======================================================================
# Guard: always reassert TARGET_TABLE regardless of session variable state
TARGET_TABLE = f"{NEXUS_SCHEMA}.idea_seed_library"

final_df = (
    scored_df
    .select(
        "idea_id",
        "idea_name",
        "description",
        "source_section",
        "source_repo",
        "scrape_date",
        "run_id",
        "domain_tag",
        "hologic_relevance_score",
        "coverage_status",
        "matched_agent",
        "complexity_score",
        "composite_score",
        "etl_load_datetime",
        "etl_source_system",
        "etl_batch_id"
    )
    .dropDuplicates(["idea_id"])
)

final_df.createOrReplaceTempView("idea_seed_library_current_batch")

spark.sql(f"""
CREATE OR REPLACE TABLE {TARGET_TABLE}
USING DELTA
AS SELECT * FROM idea_seed_library_current_batch
""")

try:
    spark.sql(f"ALTER TABLE {TARGET_TABLE} CLUSTER BY (domain_tag, coverage_status)")
except Exception:
    pass

final_count = final_df.count()
print(f"✅ Persisted current snapshot to {TARGET_TABLE}")
print(f"   Snapshot rows: {final_count:,}")
print(f"   Batch ID: {run_id}")

coverage_counts = {
    row["coverage_status"]: row["count"]
    for row in final_df.groupBy("coverage_status").count().collect()
}

top_opportunities_df = (
    final_df
    .filter(F.col("coverage_status").isin("gap", "partial"))
    .orderBy(F.col("composite_score").desc_nulls_last(), F.col("hologic_relevance_score").desc_nulls_last(), F.col("idea_name"))
    .limit(TOP_N)
)

top_opportunities = [row.asDict() for row in top_opportunities_df.collect()]

summary_payload = {
    "agent_name": AGENT_NAME,
    "run_id": run_id,
    "source_url": SOURCE_URL,
    "fetch_status": source_metadata.get("fetch_status"),
    "ideas_parsed": int(final_count),
    "coverage_counts": coverage_counts,
    "top_n": TOP_N,
    "top_opportunities": top_opportunities,
    "generated_at": datetime.now(timezone.utc).isoformat(),
}

IDEA_SCAN_RESULTS = summary_payload
REPORT_GENERATOR_PAYLOAD = {
    "idea_scan_summary": summary_payload,
    "top_idea_opportunities": top_opportunities,
}

print("\n" + "=" * 70)
print("IDEA SCAN COMPLETE")
print("=" * 70)
print(f"Total ideas parsed: {summary_payload['ideas_parsed']:,}")
print(f"Covered: {coverage_counts.get('covered', 0):,}")
print(f"Partial: {coverage_counts.get('partial', 0):,}")
print(f"Gap: {coverage_counts.get('gap', 0):,}")
print(f"Top opportunities returned: {len(top_opportunities):,}")
print("=" * 70)

display(
    top_opportunities_df.select(
        "idea_name",
        "domain_tag",
        "coverage_status",
        "matched_agent",
        "hologic_relevance_score",
        "complexity_score",
        "composite_score"
    )
)

summary_json = json.dumps(summary_payload, default=str)
summary_md = "\n".join([
    f"# Idea Scanner Summary",
    f"* Run ID: {run_id}",
    f"* Source URL: {SOURCE_URL}",
    f"* Total ideas parsed: {summary_payload['ideas_parsed']}",
    f"* Covered: {coverage_counts.get('covered', 0)}",
    f"* Partial: {coverage_counts.get('partial', 0)}",
    f"* Gap: {coverage_counts.get('gap', 0)}",
])

try:
    if "save_agent_output" in globals():
        save_agent_output(
            agent_name=AGENT_NAME,
            run_id=run_id,
            output_type="idea_scan_summary",
            content=summary_json,
            metadata={"source_url": SOURCE_URL, "top_n": TOP_N}
        )
        print("✅ Saved summary via save_agent_output")
    else:
        print("ℹ️ save_agent_output helper not available in W2 config; summary retained in IDEA_SCAN_RESULTS")
        print(summary_md)
except Exception as e:
    print(f"⚠️ Could not persist summary artifact: {e}")
    print(summary_md)