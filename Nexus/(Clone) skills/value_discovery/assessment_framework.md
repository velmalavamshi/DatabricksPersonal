# AI Maturity Assessment Framework

## 5-Level Maturity Model

| Level | Name | Description | Indicators |
|-------|------|-------------|------------|
| 1 | Ad Hoc | No formal data strategy. Spreadsheets and manual processes dominate. | No catalog, no governance, siloed data, reactive reporting |
| 2 | Foundational | Basic data platform exists. Some pipelines automated. | Lakehouse deployed, basic ETL, limited catalog usage, some dashboards |
| 3 | Standardized | Governed data platform with defined standards. Proactive monitoring. | Unity Catalog enforced, CI/CD pipelines, DQ rules, cost monitoring |
| 4 | Advanced | AI/ML integrated into operations. Self-service analytics. Predictive capabilities. | ML models in production, Genie/AI-BI, automated triage, feature store |
| 5 | Autonomous | AI agents orchestrate operations. Self-healing pipelines. Continuous optimization. | Multi-agent platform, autonomous remediation, predictive scheduling |

## Assessment Dimensions (score each 1-5)

### 1. Data Platform Maturity
- Infrastructure: Cloud-native? Lakehouse? Legacy warehouse?
- Governance: Unity Catalog? Row/column security? Lineage?
- Quality: Automated DQ rules? Monitoring? Alerting?
- Cost: Optimization active? FinOps? Right-sizing?

### 2. Analytics Maturity
- Reporting: Ad hoc vs self-service vs embedded
- Real-time: Batch only vs streaming vs real-time dashboards
- Advanced: Statistical analysis? ML models? Forecasting?

### 3. AI/ML Readiness
- Data readiness: Feature engineering? Training data? Labeling?
- Model lifecycle: MLflow? Registry? A/B testing? Monitoring?
- GenAI: LLM integration? RAG? Agents? Guardrails?

### 4. Operational Excellence
- Automation: Manual vs scheduled vs event-driven
- Observability: Logging? Tracing? Alerting? SLAs?
- Resilience: Retry logic? Circuit breakers? Disaster recovery?

### 5. Organization & Culture
- Skills: Data literacy? ML competency? Platform fluency?
- Collaboration: Cross-functional teams? Data mesh? Self-service?
- Innovation: Experimentation culture? Hackathons? CoE?

## Scoring Rubric

**Overall Score = Average of 5 dimensions (weighted)**

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Data Platform | 30% | Foundation for everything else |
| Analytics | 20% | Current value delivery |
| AI/ML Readiness | 20% | Future value potential |
| Operational Excellence | 20% | Sustainability & reliability |
| Organization & Culture | 10% | Enablement & adoption |

## Output Template

```
## Assessment Summary: [Client Name]

**Overall Maturity: Level [X] — [Level Name]**
**Composite Score: [X.X] / 5.0**

| Dimension | Score | Level | Key Finding |
|-----------|-------|-------|-------------|
| Data Platform | X.X | [name] | [1-line summary] |
| Analytics | X.X | [name] | [1-line summary] |
| AI/ML Readiness | X.X | [name] | [1-line summary] |
| Operational Excellence | X.X | [name] | [1-line summary] |
| Organization & Culture | X.X | [name] | [1-line summary] |

### Top 3 Strengths
1. ...
2. ...
3. ...

### Top 3 Gaps (with recommended actions)
1. Gap: ... → Action: ...
2. Gap: ... → Action: ...
3. Gap: ... → Action: ...

### Recommended Next Steps (90-day roadmap)
- Month 1: ...
- Month 2: ...
- Month 3: ...
```
