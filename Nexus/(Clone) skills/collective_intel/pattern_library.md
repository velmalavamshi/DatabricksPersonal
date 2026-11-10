# Pattern Library — Known Patterns & Anti-Patterns

## Success Patterns

### P1: Medallion with Views (Performance-Aware)
- **Description:** Silver/Gold layers use views for flexibility, but materialize high-traffic views
- **When to use:** Exploratory phase, schema-volatile sources
- **Risk:** Query performance degrades as view chains deepen (Hologic: 64% gold = views)
- **Mitigation:** Monitor query latency; materialize any view accessed >100x/day

### P2: Source Specialist Consultation
- **Description:** Primary agents consult domain specialists before acting on unfamiliar source data
- **When to use:** Multi-source environments (>5 source systems)
- **Evidence:** Reduces incorrect schema assumptions by ~70%
- **Implementation:** Agent calls specialist's `get_context()` before generating code

### P3: xxHash64 Surrogate Keys
- **Description:** Replace MD5/SHA with xxHash64 for surrogate key generation
- **Benefits:** 53% smaller keys, 75% less I/O, downstream BI refresh acceleration
- **Evidence:** Hologic migration: 1,538 tables, 7,978 columns, projected $60-120K Power BI savings

### P4: Event-Driven Agent Communication
- **Description:** Agents publish results to shared Delta table; consumers poll or subscribe
- **When to use:** Async workflows, decoupled agent pipelines
- **Pattern:** `agent_events` table with (event_id, producer, consumer, payload, status, timestamp)

### P5: Circuit Breaker for Agent Failures
- **Description:** Track consecutive failures; auto-pause agent after threshold
- **States:** CLOSED (healthy) → OPEN (paused) → HALF_OPEN (testing) → CLOSED
- **Thresholds:** 3 consecutive failures = OPEN; 1 success in HALF_OPEN = CLOSED

## Anti-Patterns

### AP1: Flat-Rate Cost Estimation
- **Description:** Using a single $/DBU rate for all SKU types
- **Symptom:** Cost reports showing 3-5x actual spend
- **Root cause:** Rates range from $0.01 (networking) to $0.95 (serverless)
- **Fix:** Always JOIN `system.billing.usage` to `system.billing.list_prices`
- **Evidence:** Hologic had 3 failed cost reports before discovering this (May 2026)

### AP2: Deep View Chains
- **Description:** Gold views built on silver views built on bronze views (3+ levels)
- **Symptom:** Dashboard queries timing out; SQL warehouse scaling to max
- **Risk level:** HIGH at Hologic (64% gold = views)
- **Fix:** Materialize any view in chain accessed >100x/day; max 2 levels deep

### AP3: Over-Provisioned Vector Search
- **Description:** STANDARD tier Vector Search endpoints left idle
- **Symptom:** $2.4K-$16.9K/year per idle endpoint
- **Evidence:** Hologic phoenix_vs_endpoint: 7 units, idle since March 2026 = $16.9K/year
- **Fix:** Downscale to 1 unit or delete; use BUDGET tier for dev/test

### AP4: Agent Mesh (Everyone Calls Everyone)
- **Description:** All agents can call all other agents directly
- **Symptom:** Circular dependencies, unpredictable latency, debugging nightmare
- **Fix:** Hub-and-spoke with defined consultation paths (not mesh)

### AP5: Unbounded Context Windows
- **Description:** Loading full table DDLs and catalog metadata into every agent prompt
- **Symptom:** Token costs spike; response quality drops (needle-in-haystack)
- **Fix:** Lazy loading with TTL cache; infer relevant schemas from request keywords

## Pattern Recognition Heuristics

When analyzing a new client environment, look for these signals:

| Signal | Likely Pattern/Anti-Pattern | Action |
|--------|----------------------------|--------|
| >50% views in gold layer | AP2 (Deep View Chains) | Audit query latency |
| Single cost rate in reports | AP1 (Flat-Rate) | Recalculate with list_prices |
| Idle serving endpoints | AP3 (Over-Provisioned) | Check last_request_time |
| Job failure rate >10% | Needs P5 (Circuit Breaker) | Implement auto-pause |
| >5 source systems | Needs P2 (Specialist Consultation) | Map domain experts |
| MD5 in surrogate keys | Needs P3 (xxHash64) | Plan migration |
