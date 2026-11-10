# AI Use Case Scoring & Prioritization

## Scoring Criteria (each scored 1-5)

| Criterion | Weight | 1 (Low) | 3 (Medium) | 5 (High) |
|-----------|--------|---------|------------|----------|
| Business Value | 25% | <$50K annual impact | $50K-$500K impact | >$500K impact |
| Feasibility | 20% | No data, no skills, 12+ months | Partial data, some skills, 6-12 months | Data ready, skills in-house, <6 months |
| Strategic Alignment | 20% | Nice-to-have, no exec sponsor | Supports 1 strategic pillar | Core to company strategy, CEO-level |
| Data Readiness | 15% | No relevant data exists | Data exists but needs cleanup | Clean, governed, accessible data |
| Risk & Complexity | 10% | Regulatory, PII, cross-border | Some compliance, moderate scope | Low risk, contained scope |
| Time to Value | 10% | >12 months to first value | 3-6 months | <3 months (quick win) |

## Priority Matrix

**Composite Score = Weighted sum of all criteria**

| Score Range | Priority | Action |
|-------------|----------|--------|
| 4.0 - 5.0 | 🟢 P1 - Do Now | Start immediately, allocate resources |
| 3.0 - 3.9 | 🟡 P2 - Plan Next | Queue for next quarter, begin scoping |
| 2.0 - 2.9 | 🟠 P3 - Investigate | Needs more data or feasibility study |
| 1.0 - 1.9 | 🔴 P4 - Defer | Not ready, revisit in 6-12 months |

## Use Case Categories (by Databricks capability)

### Data Engineering & Platform
- Automated pipeline monitoring & self-healing
- Cost optimization & right-sizing
- Data quality anomaly detection
- Schema drift detection & auto-remediation

### Analytics & BI
- Self-service analytics (Genie/AI-BI)
- Real-time operational dashboards
- Embedded analytics in applications
- Natural language querying

### Machine Learning
- Demand forecasting
- Customer churn prediction
- Anomaly detection (fraud, quality, performance)
- Recommendation engines

### Generative AI
- Document processing & extraction (ai_parse_document)
- Knowledge base Q&A (RAG)
- Agent-based automation
- Code generation & review

## Output Template

```
## Use Case Scoring: [Use Case Name]

**Client:** [Client Name]
**Submitted by:** [Stakeholder]
**Date:** [Date]

### Scoring Summary

| Criterion | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Business Value | X | 25% | X.XX |
| Feasibility | X | 20% | X.XX |
| Strategic Alignment | X | 20% | X.XX |
| Data Readiness | X | 15% | X.XX |
| Risk & Complexity | X | 10% | X.XX |
| Time to Value | X | 10% | X.XX |
| **TOTAL** | | **100%** | **X.XX** |

**Priority: [P1/P2/P3/P4] — [Action]**

### Rationale
[2-3 sentences explaining the score and priority]

### Prerequisites
- [ ] Data: [what's needed]
- [ ] Skills: [what's needed]
- [ ] Infrastructure: [what's needed]

### Estimated ROI
- Investment: $[X]K (implementation) + $[X]K/year (running)
- Return: $[X]K/year (savings) or [X]% improvement in [metric]
- Payback period: [X] months
```
