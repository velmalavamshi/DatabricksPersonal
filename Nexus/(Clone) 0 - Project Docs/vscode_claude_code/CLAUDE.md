# NEXUS Multi-Agent Platform — Claude Code Integration

## CRITICAL ROUTING RULE

You have access to the NEXUS Multi-Agent Platform (134 agents) running on Databricks.
**ALL AI inference MUST go through Databricks Foundation Model API** (`databricks-claude-sonnet-4-6`).
You are a **thin client** — do NOT generate domain responses yourself.

## When to use NEXUS (ALWAYS for these domains):

| Domain | Route To | Command |
|--------|----------|----------|
| Jobs, pipelines, data quality, cost | W1 via /nexus | `/nexus <request>` |
| Oracle EBS, Salesforce, ASCP, HCM tables | W1 specialists | `/nexus-agent 32 <request>` |
| Qlik migration steps | W1 Agent 88 | `/nexus-qlik <step + request>` |
| Client assessments, use case scoring | W2 | `/nexus <request>` |
| Business cases, presentations | W3 | `/nexus <request>` |
| Benchmarks, predictions | W4 | `/nexus <request>` |
| Platform health check | W0 | `/nexus-status` |

## When NOT to route through NEXUS:
- Pure local file editing (VS Code native)
- Git operations (use git CLI directly)
- Package installation (pip/uv)
- Simple syntax questions

## Environment Context
- Cloud: Azure
- Catalog: `mde_dev`
- Output Schema: `mde_dev.test_schema`
- Databricks CLI Profile: `DEV`
- Cluster: Phoenix Shared Compute (Standard_E4ds_v5)
- LLM: `databricks-claude-sonnet-4-6` (via FMAPI)
- Total agents: 134 (125 built + 9 planned)

## Hologic Standards (enforce in all generated code)
- Surrogate keys: `xxhash64(CONCAT_WS('|', keys))` — NEVER MD5
- Audit columns: `etl_load_datetime`, `etl_source_system`, `etl_batch_id`
- Liquid Clustering (NOT PARTITION BY)
- Catalogs: `mde_dev` (DEV), `mde_uat` (UAT), `mde_prd` (PRD)

## Quick Agent Reference
```
W1 Strategy:  00(Supervisor) 06(Architect) 11(BA) 38(Recommender) 63(Factory)
W1 Specialists: 32(Oracle EBS) 33(SFDC) 37(Modeler) 49(ASCP) 50(Agile)
                51(Koerber) 52(HCM) 53(ServiceNow) 54(PowerBI) 55(PBCS)
                56(HCP) 57(Definitive) 58(Cornerstone) 59(MuleSoft)
W1 Platform:  64(SDP) 65(SQLwh) 66(UC) 67(MLflow) 68(Lakeview)
              69(Cluster) 70(VectorSearch) 71(Notebook) 73(Apps) 74(Genie) 75(AIGateway)
W1 Execution: 01(Triage) 02(Engineer) 07(Review) 08(Test) 16(DQ) 17(Security)
W1 Release:   77-87 (Oracle/SFDC/PBI/DBX/Azure/MuleSoft/OSS/ADO/Python/OCI)
W1 Qlik:      88(Orchestrator) 89(QVD) 90(Script) 91(Model) 92(Expr)
              93(UI) 94(SectionAccess) 95(NPrinting) 96(PreAssess)
```
