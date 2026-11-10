# Cross-Client Performance Benchmarks

## Platform Health Benchmarks (Databricks)

| Metric | Poor | Average | Good | Elite | Hologic (Current) |
|--------|------|---------|------|-------|-------------------|
| Job success rate | <85% | 85-92% | 92-97% | >97% | ~89% (1,654 failures/mo) |
| Pipeline SLA adherence | <80% | 80-90% | 90-95% | >95% | ~85% (estimated) |
| Data freshness (gold layer) | >4hr | 2-4hr | 1-2hr | <1hr | ~2hr (batch) |
| Cost per TB processed | >$15 | $8-15 | $4-8 | <$4 | ~$9.50 |
| View-to-table ratio (gold) | >80% | 60-80% | 40-60% | <40% | 64% (high risk) |
| Cluster utilization | <30% | 30-50% | 50-70% | >70% | ~45% |
| DQ rule coverage | <20% | 20-50% | 50-80% | >80% | ~35% |

## Cost Benchmarks (by company size)

| Company Size | Annual Databricks Spend | Cost/Employee | Cost/TB Stored |
|-------------|------------------------|---------------|----------------|
| Mid-market (1-5K employees) | $100K-$400K | $50-$150 | $800-$2,000 |
| Enterprise (5-20K employees) | $400K-$2M | $40-$120 | $500-$1,500 |
| Large Enterprise (20K+) | $2M-$10M | $30-$100 | $300-$1,000 |
| **Hologic (~7K employees)** | **$184K** | **~$26** | **TBD** |

## AI/ML Adoption Benchmarks

| Capability | % Companies (2024) | % Companies (2026 est.) | Hologic |
|-----------|-------------------|------------------------|--------|
| ML models in production | 45% | 65% | No (Level 2) |
| GenAI use cases live | 30% | 55% | Experimental |
| AI agents (autonomous) | 8% | 25% | Building (NEXUS) |
| Self-service analytics | 60% | 75% | Partial (Genie) |
| Automated DQ monitoring | 50% | 70% | Partial |
| FinOps/cost optimization | 35% | 55% | Active |

## Source System Complexity Benchmarks

| Metric | Simple | Moderate | Complex | Hologic |
|--------|--------|----------|---------|--------|
| Source systems | 1-5 | 5-15 | 15+ | 12+ (complex) |
| Total source tables | <500 | 500-2,000 | 2,000+ | 2,900+ (complex) |
| ERP complexity | Single module | Multi-module | Multi-instance | Oracle EBS 1,263 tables |
| CRM tables | <100 | 100-500 | 500+ | Salesforce 768+280 |

## Output Template

```
## Benchmark Analysis: [Topic]

**Context:** [What's being benchmarked]
**Hologic Position:** [Where Hologic sits vs peers]

| Metric | Industry Avg | Hologic | Gap | Priority |
|--------|-------------|---------|-----|----------|
| ... | ... | ... | ... | P1/P2/P3 |

### Key Insights
1. [Insight with evidence]
2. [Insight with evidence]

### Recommendations
- [Action to close gap]
```
