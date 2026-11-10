# Databricks notebook source
# DBTITLE 1,Registry Bootstrap
# MAGIC %md
# MAGIC # NEXUS Agent Registry Bootstrap
# MAGIC
# MAGIC One-time (idempotent) seed for `mde_dev.test_schema.agent_registry`.
# MAGIC
# MAGIC Run this whenever new agents are added or the table needs to be rebuilt from AGENTS.md. Safe to re-run — uses `CREATE OR REPLACE TABLE`.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Target | `mde_dev.test_schema.agent_registry` |
# MAGIC | Source | AGENTS.md inventory (132 agents) |
# MAGIC | Key | `xxhash64(CONCAT_WS('\|', agent_key, workspace))` |
# MAGIC | Clustering | `(workspace, layer)` |

# COMMAND ----------

# DBTITLE 1,Seed agent_registry
# ======================================================================
# NEXUS AGENT REGISTRY BOOTSTRAP
# Seeds mde_dev.test_schema.agent_registry from AGENTS.md
# Idempotent — safe to re-run.
# ======================================================================

from pyspark.sql import functions as F
from pyspark.sql import types as T
from datetime import datetime, timezone
import uuid

NEXUS_SCHEMA = "mde_dev.test_schema"
TARGET_TABLE = f"{NEXUS_SCHEMA}.agent_registry"
BATCH_ID      = str(uuid.uuid4())
LOAD_DT       = datetime.now(timezone.utc)

# ── Agent master list (source of truth = AGENTS.md) ────────────────────
# Columns: agent_key, agent_name, workspace, layer, purpose, domain_keywords, notebook_id, status

AGENTS = [
    # ── W0 Meta Orchestrator ──────────────────────────────────────────
    ("00_meta_supervisor",          "meta_supervisor",           "W0", "orchestrator",  "Top-level meta supervisor, intent classification, workspace routing",       "routing,orchestration,supervisor,intent,classify",                      None,              "active"),
    ("02_event_mesh",               "event_mesh",                "W0", "orchestrator",  "Event bus pub/sub, agent_events Delta table, decoupled messaging",          "event,bus,pubsub,messaging,async",                                       None,              "active"),
    ("03_version_manager",          "version_manager",           "W0", "orchestrator",  "Agent version control, schema migration, backward compatibility",           "version,migration,schema,compatibility",                                 None,              "active"),
    ("04_security_layer",           "security_layer",            "W0", "orchestrator",  "Cross-agent security policy enforcement, PII guards",                       "security,pii,policy,enforcement,access",                                 None,              "active"),
    ("05_feedback_system",          "feedback_system",           "W0", "orchestrator",  "Collect and route agent feedback, quality signals",                         "feedback,quality,signal,rating,improvement",                             None,              "active"),
    ("06_circuit_breaker",          "circuit_breaker_manager",   "W0", "orchestrator",  "Circuit breaker pattern for failing agents, fallback routing",              "circuit breaker,fallback,retry,resilience,failure",                      None,              "active"),
    ("07_governance_dashboard",     "governance_dashboard",      "W0", "orchestrator",  "Governance metrics dashboard, policy compliance reporting",                 "governance,compliance,dashboard,policy,audit",                           None,              "active"),
    ("08_nexus_scheduler",          "nexus_scheduler",           "W0", "orchestrator",  "Lakeflow job orchestration, agent scheduling, dependency management",       "schedule,job,orchestration,dependency,cron",                             None,              "active"),
    ("09_nexus_e2e_test",           "nexus_e2e_test",            "W0", "orchestrator",  "End-to-end integration testing across all agent workspaces",                "test,e2e,integration,validation,quality",                                None,              "active"),
    ("10_audit_trail",              "audit_trail",               "W0", "orchestrator",  "Immutable audit log of all agent actions and decisions",                    "audit,trail,log,compliance,immutable",                                   None,              "active"),
    ("11_monitoring_dashboard",     "monitoring_dashboard",      "W0", "orchestrator",  "Real-time platform health monitoring, SLA tracking",                        "monitor,health,sla,alert,dashboard",                                     None,              "active"),
    ("12_cost_attribution",         "cost_attribution",          "W0", "orchestrator",  "Per-agent DBU cost attribution, budget tracking",                          "cost,dbu,budget,billing,attribution",                                    None,              "active"),
    ("13_event_bus_monitor",        "event_bus_monitor",         "W0", "orchestrator",  "Monitor agent_events Delta table, detect stale or unprocessed events",     "event,monitor,stale,queue,lag",                                          None,              "active"),
    ("14_agent_leaderboard",        "agent_leaderboard",         "W0", "orchestrator",  "Agent performance leaderboard, success rate ranking",                       "leaderboard,rank,performance,success rate,score",                        None,              "active"),
    # ── W1 Strategy ───────────────────────────────────────────────────
    ("00_supervisor_agent",         "supervisor_agent",          "W1", "strategy",      "Routes within W1, orchestrates pipelines, agent coordination",              "routing,orchestration,pipeline,coordination,supervisor",                 None,              "active"),
    ("06_solution_architect_agent", "solution_architect_agent",  "W1", "strategy",      "HLD/LLD architecture design, medallion patterns, data mesh",                "architecture,design,hld,lld,medallion,data mesh,blueprint",              None,              "active"),
    ("11_business_analyst_agent",   "business_analyst_agent",    "W1", "strategy",      "BRDs, user stories, requirements gathering, gap analysis",                  "requirements,brd,user story,gap analysis,business analyst",              None,              "active"),
    ("38_solution_recommender_agent","solution_recommender_agent","W1","strategy",      "Cross-domain solution recommendations, build vs buy analysis",              "recommend,solution,build vs buy,options analysis,evaluation",            None,              "active"),
    ("63_agent_factory_agent",      "agent_factory_agent",       "W1", "strategy",      "Creates Hologic-standard agent notebooks, 7-cell template, registers agents","agent factory,create agent,notebook template,register agent",            None,              "active"),
    # ── W1 Specialists ────────────────────────────────────────────────
    ("15_lakehouse_architect_agent", "lakehouse_architect_agent", "W1", "specialist",   "Medallion architecture, Unity Catalog, Data Mesh design",                   "lakehouse,medallion,unity catalog,data mesh,bronze,silver,gold",         None,              "active"),
    ("32_oracle_ebs_specialist_agent","oracle_ebs_specialist_agent","W1","specialist",  "Oracle EBS AP, AR, GL, PO, INV — 1,263 tables",                            "oracle,ebs,ap,ar,gl,po,inv,invoice,purchase order,financial,erp",       None,              "active"),
    ("33_salesforce_sync_agent",    "salesforce_sync_agent",     "W1", "specialist",    "Salesforce CRM CDC, deduplication — 768 tables",                            "salesforce,sfdc,crm,cdc,lead,opportunity,account,contact",               None,              "active"),
    ("37_data_modeler_agent",       "data_modeler_agent",        "W1", "specialist",    "Kimball star schema design, fact/dim tables, DDL generation",               "data model,kimball,star schema,fact,dimension,ddl,surrogate key",        None,              "active"),
    ("44_oracle_ebs_extract_agent", "oracle_ebs_extract_agent",  "W1", "specialist",    "Oracle EBS extract pipeline monitoring, ADF integration",                   "oracle,ebs,extract,adf,pipeline,monitor,etl",                            None,              "active"),
    ("47_salesforce_extract_agent", "salesforce_extract_agent",  "W1", "specialist",    "Salesforce extract pipeline monitoring, CDC processing",                    "salesforce,extract,pipeline,cdc,monitor,etl",                            None,              "active"),
    ("49_ascp_specialist_agent",    "ascp_specialist_agent",     "W1", "specialist",    "Oracle ASCP supply chain planning — 238 tables",                            "supply chain,ascp,planning,forecast,inventory,demand,replenishment",     None,              "active"),
    ("50_agile_plm_agent",          "agile_plm_agent",           "W1", "specialist",    "Agile PLM product lifecycle, BOM, change orders — 82 tables",              "product lifecycle,plm,bom,change order,agile,engineering change",        None,              "active"),
    ("51_koerber_specialist_agent", "koerber_specialist_agent",  "W1", "specialist",    "Koerber warehouse management system — 2 tables",                            "warehouse,wms,koerber,logistics,fulfillment,inventory location",         None,              "active"),
    ("52_oracle_hcm_specialist_agent","oracle_hcm_specialist_agent","W1","specialist", "Oracle HCM workforce, payroll, benefits — 147 tables",                     "hcm,hr,workforce,payroll,benefits,headcount,oracle cloud",               None,              "active"),
    ("53_servicenow_agent",         "servicenow_agent",          "W1", "specialist",    "ServiceNow ITSM bidirectional integration, incident/change management",     "servicenow,itsm,incident,change,ticket,service desk,itil",               None,              "active"),
    ("54_powerbi_agent",            "powerbi_agent",             "W1", "specialist",    "Power BI refresh monitoring, dataset/report health",                        "power bi,pbi,refresh,dataset,report,fabric,connector",                   None,              "active"),
    ("55_pbcs_specialist_agent",    "pbcs_specialist_agent",     "W1", "specialist",    "Oracle PBCS financial planning, budgeting, forecasting — 42 tables",       "pbcs,planning,budgeting,forecast,financial planning,epm",                None,              "active"),
    ("56_hcp_specialist_agent",     "hcp_specialist_agent",      "W1", "specialist",    "Healthcare providers, PII, Sunshine Act compliance — 81 tables",           "healthcare,hcp,provider,sunshine act,pii,compliance,clinical",           None,              "active"),
    ("57_definitive_specialist_agent","definitive_specialist_agent","W1","specialist", "Market intelligence, hospital data — 34 tables",                           "market intelligence,hospital,definitive,competitive,benchmark",          None,              "active"),
    ("58_cornerstone_specialist_agent","cornerstone_specialist_agent","W1","specialist","Cornerstone LMS, learning management, compliance training — 29 tables",   "learning,lms,cornerstone,training,compliance,course,certification",      None,              "active"),
    ("59_mulesoft_specialist_agent","mulesoft_specialist_agent", "W1", "specialist",    "MuleSoft API health, integration monitoring — 4 tables",                   "mulesoft,api,integration,connector,anypoint,runtime",                    None,              "active"),
    ("60_consultation_router",      "consultation_router",       "W1", "specialist",    "Routes consultation requests to the right specialist agent",                "consultation,routing,specialist,domain,dispatch",                        None,              "active"),
    ("64_sdp_agent",                "sdp_agent",                 "W1", "specialist",    "Author/monitor Spark Declarative Pipelines — Bronze/Silver/Gold, expectations, Auto CDC", "spark declarative pipeline,sdp,dlt,streaming table,materialized view,auto cdc,expectations", "350235908256380", "active"),
    ("65_sql_warehouse_agent",      "sql_warehouse_agent",       "W1", "specialist",    "SQL Warehouse right-sizing, auto-stop, Photon, result cache tuning",       "sql warehouse,photon,auto stop,serverless sql,result cache,t-shirt",     "350235908256385", "active"),
    ("66_unity_catalog_agent",      "unity_catalog_agent",       "W1", "specialist",    "UC governance — RBAC, tags, column masks, row filters, ABAC, lineage",    "unity catalog,rbac,governance,lineage,column mask,row filter,abac,tags","350235908256386", "active"),
    ("67_mlflow_model_serving_agent","mlflow_model_serving_agent","W1","specialist",   "MLflow tracking, UC model registry, endpoint deployment, A/B routing",    "mlflow,model serving,model registry,experiment,endpoint,a/b test",      "350235908256387", "active"),
    ("68_ai_bi_dashboard_agent",    "ai_bi_dashboard_agent",     "W1", "specialist",    "Lakeview AI/BI dashboard creation, widget authoring, dataset binding",     "dashboard,lakeview,ai/bi,widget,visualization,report",                   "350235908256388", "active"),
    ("69_cluster_management_agent", "cluster_management_agent",  "W1", "specialist",    "Cluster policies, autoscaling, compute right-sizing, idle termination",    "cluster,autoscaling,idle,compute,right-sizing,node type,policy",         "350235908256389", "active"),
    ("70_vector_search_agent",      "vector_search_agent",       "W1", "specialist",    "Vector Search endpoint/index creation, embeddings, RAG pipeline design",   "vector search,embedding,rag,semantic search,similarity,index",           "350235908256390", "active"),
    ("71_notebook_lifecycle_agent", "notebook_lifecycle_agent",  "W1", "specialist",    "Create standard notebooks, Git sync, version tagging, cleanup/archive",    "notebook,git,version,lifecycle,archive,template",                        "350235908256391", "active"),
    ("73_databricks_app_agent",     "databricks_app_agent",      "W1", "specialist",    "Scaffold/deploy/diagnose Databricks Apps, SP permissions, IP ACL",         "databricks app,streamlit,scaffold,deploy,app.py,permissions",            "350235908256392", "active"),
    ("74_genie_space_agent",        "genie_space_agent",         "W1", "specialist",    "Create Genie spaces, register gold/platinum tables, curate question sets",  "genie,genie space,natural language,question,ai/bi,register table",       "350235908256393", "active"),
    ("75_ai_gateway_agent",         "ai_gateway_agent",          "W1", "specialist",    "AI Gateway endpoint config, rate limits, guardrails, inference table",     "ai gateway,rate limit,guardrail,pii,toxicity,inference,llm proxy",       "350235908256394", "active"),
    # ── W1 Execution ──────────────────────────────────────────────────
    ("01_job_failure_triage_agent", "job_failure_triage_agent",  "W1", "execution",     "Classify job failures, root cause analysis, auto-remediation steps",      "job failure,triage,root cause,remediation,error,pipeline failure",       None,              "active"),
    ("02_data_engineer_agent",      "data_engineer_agent",       "W1", "execution",     "Production PySpark/SQL code generation, pipeline authoring",               "data engineer,pyspark,sql,code,pipeline,etl,transformation",             None,              "active"),
    ("03_view_dependency_agent",    "view_dependency_agent",     "W1", "execution",     "View dependency analysis, performance bottleneck identification",           "view,dependency,performance,bottleneck,lineage,graph",
     None, "active"),
    ("04_source_drift_detector",    "source_drift_detector_agent","W1","execution",     "Schema change detection, source drift alerting across 1,263+ tables",     "schema drift,change detection,schema change,source,alert",               None,              "active"),
    ("07_peer_review_agent",        "peer_review_agent",         "W1", "execution",     "Code quality scoring (blocks deployment on score < 6/10)",                 "peer review,code quality,score,review,gate,checklist",                   None,              "active"),
    ("08_unit_test_agent",          "unit_test_agent",           "W1", "execution",     "PyTest + Nutter test notebook generation, test matrix documentation",      "unit test,pytest,nutter,test notebook,test case,test matrix",            None,              "active"),
    ("16_data_quality_agent",       "data_quality_agent",        "W1", "execution",     "DQX rules, DLT expectations, data quality monitoring",                     "data quality,dqx,expectations,dlt,null check,range check,freshness",     None,              "active"),
    ("17_security_agent",           "security_agent",            "W1", "execution",     "RBAC review, PII detection, GDPR compliance checks",                       "security,rbac,pii,gdpr,compliance,access control,data classification",   None,              "active"),
    ("20_integration_test_agent",   "integration_test_agent",    "W1", "execution",     "End-to-end test suites for pipeline integration validation",               "integration test,e2e,pipeline,validation,test suite",                    None,              "active"),
    ("39_morning_briefing_agent",   "morning_briefing_agent",    "W1", "execution",     "Daily morning briefing via Teams + Email with overnight job status",       "morning briefing,daily report,teams,email,overnight,job status",         None,              "active"),
    ("40_morning_triage_orchestrator","morning_triage_orchestrator","W1","execution",  "Auto-creates ADO work items from failed overnight jobs",                    "triage,ado,work item,azure devops,overnight failure,auto-create",        None,              "active"),
    ("76_layer_validation_agent",   "layer_validation_agent",    "W1", "execution",     "Silver/Gold/Platinum DQX + Nutter gate before promotion",                  "layer validation,dqx,nutter,promotion gate,silver,gold,platinum",        None,              "active"),
    # ── W1 Release Intelligence ───────────────────────────────────────
    ("77_release_intelligence_agent","release_intelligence_agent","W1","release_intelligence","Weekly consolidated vendor release impact report orchestrator",       "release,vendor,impact,report,weekly,orchestrator",                       "1025795174227706","active"),
    ("78_oracle_release_monitor_agent","oracle_release_monitor_agent","W1","release_intelligence","Oracle EBS patches, CPUs, desupport monitoring",              "oracle,patch,cpu,desupport,release,ebs update",                          "1025795174227707","active"),
    ("79_salesforce_release_monitor_agent","salesforce_release_monitor_agent","W1","release_intelligence","Salesforce seasonal releases, API deprecations",        "salesforce,api deprecation,release,sfdc update,spring release",          "1025795174227708","active"),
    ("80_powerbi_release_monitor_agent","powerbi_release_monitor_agent","W1","release_intelligence","Power BI monthly updates, connector/DAX changes",             "power bi,connector,dax,release,fabric,pbi update",                       "1025795174227709","active"),
    ("81_databricks_release_monitor_agent","databricks_release_monitor_agent","W1","release_intelligence","Databricks Runtime EOL, API deprecation, UC changes",       "databricks,runtime,eol,deprecation,uc,model retirement,release",        "1025795174227710","active"),
    ("82_azure_platform_release_monitor_agent","azure_platform_release_monitor_agent","W1","release_intelligence","Azure service retirements, pricing, Entra ID",           "azure,entra,private link,service retirement,pricing change",             "1025795174227711","active"),
    ("83_mulesoft_release_monitor_agent","mulesoft_release_monitor_agent","W1","release_intelligence","MuleSoft connector deprecations, runtime EOL",                "mulesoft,connector deprecation,cloudhub,anypoint,runtime eol",           "1025795174227712","active"),
    ("84_delta_spark_oss_release_monitor_agent","delta_spark_oss_release_monitor_agent","W1","release_intelligence","Delta protocol, Spark 4.0 transition",              "delta,spark 4,protocol,null semantics,merge change,oss",                 "1025795174227713","active"),
    ("85_azure_devops_release_monitor_agent","azure_devops_release_monitor_agent","W1","release_intelligence","ADO pipeline agent changes, API deprecations",               "ado,azure devops,pipeline agent,yaml,api deprecation",                   "1025795174227714","active"),
    ("86_python_ecosystem_release_monitor_agent","python_ecosystem_release_monitor_agent","W1","release_intelligence","Python library releases — pandas, numpy, mlflow",        "pandas,numpy,pyarrow,mlflow,openai,python library,release",              "1025795174227715","active"),
    ("87_oracle_cloud_release_monitor_agent","oracle_cloud_release_monitor_agent","W1","release_intelligence","PBCS + HCM Cloud quarterly updates, OCI API",                "pbcs,hcm cloud,oci,oracle cloud,quarterly,epm update",                   "1025795174227716","active"),
    # ── W1 Qlik Migration ─────────────────────────────────────────────
    ("88_qlik_migration_orchestrator_agent","qlik_migration_orchestrator_agent","W1","qlik_migration","Qlik migration orchestrator — inventory, wave planning, progress", "qlik,qlikview,migration,wave planning,inventory,qvw",                    "3084094643406393","active"),
    ("89_qvd_extraction_agent",      "qvd_extraction_agent",      "W1", "qlik_migration","QVD schema extraction, data profiling → Delta tables",                    "qvd,qlik,extraction,schema,profiling,delta",                             "3084094643406394","active"),
    ("90_qlik_script_conversion_agent","qlik_script_conversion_agent","W1","qlik_migration","QVS/QVW load scripts → PySpark/SQL conversion",                      "qvs,qvw,load script,pyspark,sql,conversion,qlik script",                 "3084094643406395","active"),
    ("91_qlik_data_model_agent",     "qlik_data_model_agent",     "W1", "qlik_migration","Associative model → Kimball star schema conversion",                       "associative model,kimball,synthetic key,circular ref,star schema",       "3084094643406396","active"),
    ("92_qlik_expression_agent",     "qlik_expression_agent",     "W1", "qlik_migration","Set analysis, AGGR(), variables → Databricks SQL",                        "set analysis,aggr,applymap,qlik expression,databricks sql",              "3084094643406397","active"),
    ("93_qlik_ui_migration_agent",   "qlik_ui_migration_agent",   "W1", "qlik_migration","QlikView/Sense objects → Lakeview / Power BI migration",                  "qlik ui,chart,kpi,table,lakeview,power bi,migration",                   "3084094643406398","active"),
    ("94_qlik_section_access_agent", "qlik_section_access_agent", "W1", "qlik_migration","Section Access → UC row filters, column masks, ABAC",                     "section access,rls,row filter,column mask,abac,rbac",                    "3084094643406399","active"),
    ("95_qlik_nprinting_agent",      "qlik_nprinting_agent",      "W1", "qlik_migration","NPrinting → Databricks Jobs + Lakeview subscriptions",                    "nprinting,report,subscription,email,lakeview,job schedule",             "3084094643406400","active"),
    # ── W2 Value Discovery ────────────────────────────────────────────
    ("w2_01_workspace_scanner",     "workspace_scanner",         "W2", "discovery",     "Scans target workspace via system tables for inventory, cost, jobs, AI footprint", "workspace scan,system tables,inventory,cost,job,ai footprint",  "276762526488006",  "active"),
    ("w2_02_use_case_scorer",        "use_case_scorer",           "W2", "discovery",     "LLM scoring to rank AI/ML opportunities from workspace scan",               "use case,score,rank,opportunity,ai/ml,roi",                              "276762526488007",  "active"),
    ("w2_03_maturity_assessor",      "maturity_assessor",         "W2", "discovery",     "Databricks maturity assessment across governance, pipelines, cost, BI, AI", "maturity,assessment,governance,pipeline,cost,bi,ai,readiness",          "276762526488008",  "active"),
    ("w2_04_report_generator",       "report_generator",          "W2", "discovery",     "Assessment report and executive summary from W2 outputs",                  "report,executive,summary,assessment,findings,recommendation",            "276762526488009",  "active"),
    ("w2_05_idea_scanner",           "idea_scanner",              "W2", "discovery",     "Scans external idea libraries, cross-references NEXUS coverage, scores relevance", "idea,scan,gap analysis,idea library,coverage,seed,external",   "1405118320738450",  "active"),
    # ── W3 Business Champions ─────────────────────────────────────────
    ("w3_01_business_case_builder",  "business_case_builder",     "W3", "champion",      "Board-ready business case generation with ROI, risk, timeline",            "business case,roi,board,executive,financial,stakeholder",                None,              "active"),
    ("w3_02_pptx_generator",         "pptx_generator",            "W3", "champion",      "PowerPoint deck generation for executive and board presentations",          "powerpoint,pptx,deck,presentation,slide,executive",                      None,              "active"),
    ("w3_03_executive_summary",      "executive_summary",         "W3", "champion",      "Executive-level narrative summary of technical findings",                   "executive summary,narrative,summary,management,c-suite",                 None,              "active"),
    ("w3_04_champion_tracker",       "champion_tracker",          "W3", "champion",      "Track business champion engagement, adoption metrics, and wins",            "champion,adoption,engagement,track,win,metric",                          None,              "active"),
    # ── W4 Collective Intelligence ────────────────────────────────────
    ("w4_01_benchmark_agent",        "benchmark_agent",           "W4", "intelligence",  "Cross-client pattern benchmarking and industry comparison",                "benchmark,pattern,industry,cross-client,compare,percentile",             None,              "active"),
    ("w4_02_pattern_library",        "pattern_library",           "W4", "intelligence",  "Curated library of proven data engineering patterns and anti-patterns",    "pattern,anti-pattern,best practice,template,playbook",                   None,              "active"),
    ("w4_03_prediction_model",       "prediction_model",          "W4", "intelligence",  "Predictive models for failure likelihood, cost trends, adoption",          "prediction,forecast,model,failure likelihood,trend,ml",                  None,              "active"),
    ("w4_04_intelligence_aggregator","intelligence_aggregator",   "W4", "intelligence",  "Aggregates signals across all workspaces for strategic insights",          "intelligence,aggregate,signal,strategic,insight,cross-workspace",        None,              "active"),
]

# ── Build Spark DataFrame ───────────────────────────────────────────────
schema = T.StructType([
    T.StructField("agent_key",        T.StringType(),    False),
    T.StructField("agent_name",       T.StringType(),    False),
    T.StructField("workspace",        T.StringType(),    False),
    T.StructField("layer",            T.StringType(),    False),
    T.StructField("purpose",          T.StringType(),    True),
    T.StructField("domain_keywords",  T.StringType(),    True),
    T.StructField("notebook_id",      T.StringType(),    True),
    T.StructField("status",           T.StringType(),    False),
])

raw_df = spark.createDataFrame(AGENTS, schema=schema)

registry_df = (
    raw_df
    .withColumn(
        "agent_id",
        F.expr("CAST(xxhash64(CONCAT_WS('|', agent_key, workspace)) AS STRING)")
    )
    .withColumn("agent_count",       F.lit(len(AGENTS)).cast("int"))
    .withColumn("etl_load_datetime", F.lit(LOAD_DT.isoformat()).cast("timestamp"))
    .withColumn("etl_source_system", F.lit("agents_md_bootstrap"))
    .withColumn("etl_batch_id",      F.lit(BATCH_ID))
    .select(
        "agent_id", "agent_key", "agent_name", "workspace", "layer",
        "purpose", "domain_keywords", "notebook_id", "status",
        "etl_load_datetime", "etl_source_system", "etl_batch_id"
    )
)

registry_df.createOrReplaceTempView("agent_registry_seed")

spark.sql(f"""
CREATE OR REPLACE TABLE {TARGET_TABLE}
USING DELTA
AS SELECT * FROM agent_registry_seed
""")

spark.sql(f"ALTER TABLE {TARGET_TABLE} CLUSTER BY (workspace, layer)")

final_count = spark.table(TARGET_TABLE).count()
print(f"✅ {TARGET_TABLE} seeded successfully")
print(f"   Total agents: {final_count}")
print()
for ws in ["W0","W1","W2","W3","W4"]:
    n = spark.table(TARGET_TABLE).filter(F.col("workspace") == ws).count()
    print(f"   {ws}: {n} agents")

display(spark.table(TARGET_TABLE).orderBy("workspace", "layer", "agent_key").select("agent_key", "agent_name", "workspace", "layer", "purpose"))

# COMMAND ----------

