# Databricks notebook source
# DBTITLE 1,View Dependency Agent
# MAGIC %md
# MAGIC # Agent 03 — View Dependency & Performance
# MAGIC
# MAGIC **Purpose:** Map view-on-view dependency chains and identify performance bottlenecks from cascading views.
# MAGIC
# MAGIC **Problem solved:** 95% of Silver layer is views, 64% of Gold is views. Deep chains cause query-time performance issues and make impact analysis difficult.
# MAGIC
# MAGIC **Data sources:**
# MAGIC - `system.information_schema.views` — view definitions
# MAGIC - `system.information_schema.view_table_usage` — dependency graph
# MAGIC - `system.information_schema.tables` — table metadata
# MAGIC
# MAGIC **Outputs:**
# MAGIC - `mde_dev.test_schema.agent_view_dependencies` — full dependency map with depth
# MAGIC - `mde_dev.test_schema.agent_view_recommendations` — materialization recommendations
# MAGIC - Markdown report in `agent_outputs`

# COMMAND ----------

# DBTITLE 1,Load shared config
# MAGIC %run ./00_agent_config

# COMMAND ----------

# DBTITLE 1,Map view dependency graph
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Build view dependency graph using information_schema
# ══════════════════════════════════════════════════════════════════════════════

TARGET_CATALOG = "mde_dev"

# Build dependency graph: which views reference which tables/views
df_dependencies = spark.sql(f"""
WITH view_deps AS (
    SELECT 
        view_catalog,
        view_schema,
        view_name,
        CONCAT(view_catalog, '.', view_schema, '.', view_name) as view_full_name,
        table_catalog,
        table_schema,
        table_name,
        CONCAT(table_catalog, '.', table_schema, '.', table_name) as referenced_full_name
    FROM system.information_schema.view_table_usage
    WHERE view_catalog = '{TARGET_CATALOG}'
)
SELECT 
    vd.*,
    t.table_type as referenced_type
FROM view_deps vd
LEFT JOIN system.information_schema.tables t
    ON vd.table_catalog = t.table_catalog
    AND vd.table_schema = t.table_schema
    AND vd.table_name = t.table_name
""")

print(f"✅ Found {df_dependencies.count()} view→table/view dependencies")
df_dependencies.cache()

# Summary by schema
df_dependencies.groupBy("view_schema", "referenced_type").count().orderBy("view_schema", "count").display()

# COMMAND ----------

# DBTITLE 1,Calculate dependency depth (view chain length)
# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Calculate view chain depth using recursive CTE
# Views referencing views referencing views = performance risk
# ══════════════════════════════════════════════════════════════════════════════

df_depth = spark.sql(f"""
WITH RECURSIVE view_chain AS (
    -- Base: views that reference physical tables (depth = 1)
    SELECT 
        vtu.view_catalog,
        vtu.view_schema,
        vtu.view_name,
        CONCAT(vtu.view_catalog, '.', vtu.view_schema, '.', vtu.view_name) as view_full_name,
        CONCAT(vtu.table_catalog, '.', vtu.table_schema, '.', vtu.table_name) as base_table,
        1 as depth
    FROM system.information_schema.view_table_usage vtu
    JOIN system.information_schema.tables t
        ON vtu.table_catalog = t.table_catalog
        AND vtu.table_schema = t.table_schema
        AND vtu.table_name = t.table_name
    WHERE vtu.view_catalog = '{TARGET_CATALOG}'
      AND t.table_type IN ('MANAGED', 'EXTERNAL')  -- physical tables only
    
    UNION ALL
    
    -- Recursive: views referencing other views
    SELECT 
        vtu.view_catalog,
        vtu.view_schema,
        vtu.view_name,
        CONCAT(vtu.view_catalog, '.', vtu.view_schema, '.', vtu.view_name) as view_full_name,
        vc.base_table,
        vc.depth + 1 as depth
    FROM system.information_schema.view_table_usage vtu
    JOIN view_chain vc
        ON vtu.table_catalog = vc.view_catalog
        AND vtu.table_schema = vc.view_schema
        AND vtu.table_name = vc.view_name
    WHERE vtu.view_catalog = '{TARGET_CATALOG}'
      AND vc.depth < 10  -- safety limit
)
SELECT 
    view_full_name,
    view_schema,
    view_name,
    MAX(depth) as max_chain_depth,
    COUNT(DISTINCT base_table) as distinct_base_tables,
    COLLECT_SET(base_table) as base_tables
FROM view_chain
GROUP BY 1, 2, 3
ORDER BY max_chain_depth DESC
""")

print(f"✅ Calculated dependency depth for {df_depth.count()} views")

# Show deepest chains (performance risk)
print("\n🚨 Deepest view chains (potential performance bottlenecks):")
df_depth.filter("max_chain_depth >= 3").orderBy(F.desc("max_chain_depth")).display()

# COMMAND ----------

# DBTITLE 1,Identify materialization candidates
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Score views for materialization priority
# High score = should be materialized as a table
# ══════════════════════════════════════════════════════════════════════════════

# Count how many downstream views reference each view (fan-out)
df_fanout = spark.sql(f"""
SELECT 
    CONCAT(table_catalog, '.', table_schema, '.', table_name) as referenced_view,
    COUNT(DISTINCT CONCAT(view_catalog, '.', view_schema, '.', view_name)) as downstream_count
FROM system.information_schema.view_table_usage
WHERE view_catalog = '{TARGET_CATALOG}'
GROUP BY 1
""")

# Join depth + fan-out for materialization scoring
df_depth.createOrReplaceTempView("view_depths")
df_fanout.createOrReplaceTempView("view_fanout")

df_scored = spark.sql("""
SELECT 
    d.view_full_name,
    d.view_schema,
    d.view_name,
    d.max_chain_depth,
    d.distinct_base_tables,
    COALESCE(f.downstream_count, 0) as downstream_consumers,
    -- Materialization score: depth * 2 + downstream * 3 + base_tables
    (d.max_chain_depth * 2) + (COALESCE(f.downstream_count, 0) * 3) + d.distinct_base_tables as materialization_score,
    CASE 
        WHEN (d.max_chain_depth * 2) + (COALESCE(f.downstream_count, 0) * 3) + d.distinct_base_tables >= 15 THEN 'CRITICAL'
        WHEN (d.max_chain_depth * 2) + (COALESCE(f.downstream_count, 0) * 3) + d.distinct_base_tables >= 10 THEN 'HIGH'
        WHEN (d.max_chain_depth * 2) + (COALESCE(f.downstream_count, 0) * 3) + d.distinct_base_tables >= 5 THEN 'MEDIUM'
        ELSE 'LOW'
    END as materialization_priority
FROM view_depths d
LEFT JOIN view_fanout f ON d.view_full_name = f.referenced_view
ORDER BY materialization_score DESC
""")

print("✅ Materialization candidates scored")
print("\n🎯 Top candidates for materialization (highest impact):")
df_scored.filter("materialization_priority IN ('CRITICAL', 'HIGH')").display()

# COMMAND ----------

# DBTITLE 1,LLM analysis and recommendations
# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: LLM-powered analysis of top materialization candidates
# ══════════════════════════════════════════════════════════════════════════════

VIEW_AGENT_PROMPT = """You are a Databricks performance architect. Analyze this view dependency data and provide:

1. SUMMARY: Overall health assessment of the view architecture
2. TOP RISKS: Views most likely causing performance issues and why
3. MATERIALIZATION PLAN: Which views to materialize first, in what order
4. ESTIMATED IMPACT: Expected query time improvement
5. IMPLEMENTATION: Whether to use materialized views, Delta tables, or DLT streaming tables

Consider:
- Deep chains (depth >= 3) multiply query planning time
- High fan-out views (many downstream consumers) benefit most from materialization
- Silver-to-Gold transition is the optimal materialization boundary
- Storage cost vs compute savings trade-off

Format as a structured markdown report."""

run_id = generate_run_id()

# Prepare summary data for LLM
top_candidates = df_scored.filter("materialization_score >= 5").limit(30).collect()
summary_data = "\n".join([
    f"| {r['view_full_name']} | depth={r['max_chain_depth']} | downstream={r['downstream_consumers']} | score={r['materialization_score']} | priority={r['materialization_priority']} |"
    for r in top_candidates
])

# Layer distribution
layer_stats = df_scored.groupBy("view_schema", "materialization_priority").count().collect()
layer_summary = "\n".join([f"- {r['view_schema']}: {r['materialization_priority']} = {r['count']}" for r in layer_stats])

user_prompt = f"""## View Architecture Analysis for mde_dev

### Statistics
- Total views analyzed: {df_depth.count()}
- Views with depth >= 3: {df_depth.filter('max_chain_depth >= 3').count()}
- CRITICAL priority candidates: {df_scored.filter("materialization_priority = 'CRITICAL'").count()}
- HIGH priority candidates: {df_scored.filter("materialization_priority = 'HIGH'").count()}

### Top Materialization Candidates
| View | Depth | Downstream | Score | Priority |
{summary_data}

### Distribution by Layer
{layer_summary}

Provide your analysis and actionable recommendations."""

analysis = call_agent("view_dependency", VIEW_AGENT_PROMPT, user_prompt, max_tokens=3000)
print(analysis)

# COMMAND ----------

# DBTITLE 1,Save results to Delta
# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Persist all results
# ══════════════════════════════════════════════════════════════════════════════

# Save dependency map
df_scored.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.agent_view_dependencies")
print(f"✅ Saved dependency map to {CATALOG}.{SCHEMA}.agent_view_dependencies")

# Save LLM analysis as agent output
save_agent_output("view_dependency", run_id, "analysis_report", analysis,
                  {"views_analyzed": df_depth.count(), 
                   "critical_candidates": df_scored.filter("materialization_priority = 'CRITICAL'").count()})

print(f"✅ Agent 03 (View Dependency) completed | Run ID: {run_id}")