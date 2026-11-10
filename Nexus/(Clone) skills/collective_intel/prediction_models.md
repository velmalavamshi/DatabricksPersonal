# Failure Prediction & Risk Scoring

## Pipeline Failure Risk Model (Heuristic)

Score each pipeline 0-100 based on weighted risk factors:

| Factor | Weight | Scoring |
|--------|--------|---------|
| Historical failure rate (30d) | 30% | 0-5% = 0, 5-10% = 30, 10-20% = 60, >20% = 100 |
| Last failure recency | 20% | >7d ago = 0, 3-7d = 30, 1-3d = 60, today = 100 |
| Source system volatility | 15% | Stable = 0, Monthly changes = 40, Weekly changes = 80 |
| Dependency chain depth | 15% | 1-2 hops = 0, 3-4 hops = 40, 5+ hops = 80 |
| Resource contention risk | 10% | Off-peak = 0, Shared window = 50, Peak conflict = 100 |
| Data volume growth rate | 10% | <5%/mo = 0, 5-20%/mo = 40, >20%/mo = 80 |

**Risk Categories:**
- 0-25: LOW — monitor normally
- 26-50: MEDIUM — add alerting, review weekly
- 51-75: HIGH — active intervention needed, add retry logic
- 76-100: CRITICAL — imminent failure expected, pre-emptive action required

## Cost Spike Prediction

| Signal | Prediction | Confidence | Action |
|--------|-----------|------------|--------|
| Cluster auto-scale events >3x baseline | Cost spike within 24hr | 70% | Alert FinOps, check query patterns |
| New endpoint provisioned (STANDARD tier) | +$2.4K-$16.9K/year | 90% | Validate usage within 7 days |
| Job duration increasing >20% week-over-week | Capacity issue incoming | 65% | Profile queries, check data growth |
| Warehouse concurrency >80% sustained 1hr | Need larger warehouse or queueing | 80% | Right-size or add warehouse |

## Agent Performance Prediction

| Metric | Healthy | Degrading | Failing |
|--------|---------|-----------|--------|
| Success rate (7d rolling) | >95% | 85-95% | <85% |
| Avg response time | <5s | 5-15s | >15s |
| Token efficiency (output/input) | >0.3 | 0.1-0.3 | <0.1 |
| Retry rate | <5% | 5-15% | >15% |
| Quality score (user feedback) | >4.0 | 3.0-4.0 | <3.0 |

**Prediction rules:**
- If 2+ metrics in "Degrading" for 3+ consecutive days → predict failure within 7 days
- If any metric in "Failing" → trigger circuit breaker (OPEN state)
- If success rate drops >10% in 24hr → immediate alert + root cause investigation

## Trend Analysis Template

```
## Trend Analysis: [Metric/Topic]

**Period:** [Date range]
**Direction:** [Improving / Stable / Degrading]
**Confidence:** [High / Medium / Low]

### Data Points
| Period | Value | Change | |
|--------|-------|--------|---|
| [week/month] | [value] | [+/-X%] | [↑↓→] |

### Root Causes (ranked by likelihood)
1. [Cause] — [evidence] — [confidence %]
2. [Cause] — [evidence] — [confidence %]

### Forecast (next 30 days)
- Best case: [value] (if [action taken])
- Expected: [value] (status quo)
- Worst case: [value] (if [risk materializes])

### Recommended Actions
1. [Action] — expected impact: [X%] improvement
2. [Action] — expected impact: [X%] improvement
```
