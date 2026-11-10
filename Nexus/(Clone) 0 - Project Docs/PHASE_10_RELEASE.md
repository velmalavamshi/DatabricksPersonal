# Phase 10: Skill Fabric — External Knowledge Integration

> **Release:** Phase 10 | **Status:** Planned | **Target:** July 2026
> **Predecessor:** Phase 9 (Agent Intelligence Engine)
> **Inspired by:** [databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills) — Databricks' official skill injection system for AI coding agents

---

## Executive Summary

Phase 10 introduces a **Skill Fabric** — a formalized system for injecting structured, versioned domain knowledge into NEXUS agents at call-time. Where Phase 9 gave agents *memory* (recall past interactions), Phase 10 gives them *expertise* (curated knowledge they never had to discover).

This closes the gap between NEXUS (active orchestration) and the Databricks Agent Skills pattern (passive knowledge injection) by combining both: agents that execute AND have up-to-date platform knowledge hot-loaded into their prompts.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SKILL FABRIC                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Skill        │    │ Skill        │    │ Skill        │  │
│  │ Registry     │───▶│ Resolver     │───▶│ Injector     │  │
│  │ (Delta)      │    │ (match agent │    │ (prompt      │  │
│  │              │    │  to skills)  │    │  assembly)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                                       │           │
│         ▼                                       ▼           │
│  ┌──────────────┐                      ┌──────────────┐    │
│  │ Skill Store  │                      │ enhanced_    │    │
│  │ (Volumes)    │                      │ call_agent() │    │
│  │ .md files    │                      │ Phase 9.5+   │    │
│  └──────────────┘                      └──────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | UC Volume (`/Volumes/mde_dev/test_schema/nexus_skills/`) | Versioned, accessible from all compute, no notebook dependency |
| Format | Markdown (`.md`) with YAML frontmatter | Matches databricks-agent-skills pattern; token-efficient |
| Resolution | Keyword + domain match (reuses `agent_registry.domain_keywords`) | Zero-cost, no embedding needed |
| Injection | Pre-pended to system prompt in `enhanced_call_agent()` | Transparent, debuggable, respects context window |
| Versioning | Semantic (`major.minor.patch`) in frontmatter | Agents pin to compatible versions |

---

## Sub-Phases

### 10.1 — Skill Registry & Store

**Delta table:** `mde_dev.test_schema.agent_skills`

```sql
CREATE TABLE IF NOT EXISTS mde_dev.test_schema.agent_skills (
  skill_id          STRING NOT NULL,          -- e.g. "databricks-pipelines"
  skill_name        STRING NOT NULL,          -- Human-readable
  version           STRING NOT NULL,          -- semver
  description       STRING,                   -- What this skill teaches
  domain_keywords   ARRAY<STRING>,            -- Matching keywords
  applicable_agents ARRAY<STRING>,            -- Agent keys that should load this
  token_budget      INT DEFAULT 2000,         -- Max tokens for injection
  source            STRING,                   -- "internal" | "databricks-oss" | "custom"
  volume_path       STRING,                   -- /Volumes/.../skill_id/SKILL.md
  is_active         BOOLEAN DEFAULT TRUE,
  created_at        TIMESTAMP,
  updated_at        TIMESTAMP
)
USING DELTA
CLUSTER BY (source, is_active);
```

**Volume structure:**
```
/Volumes/mde_dev/test_schema/nexus_skills/
├── internal/
│   ├── hologic-enterprise-standards/
│   │   └── SKILL.md              -- xxHash64, audit cols, Liquid Clustering
│   ├── hologic-cost-formulas/
│   │   └── SKILL.md              -- DBU rates, list_prices pattern
│   └── hologic-source-systems/
│       └── SKILL.md              -- EBS/SFDC/ASCP table inventory
├── databricks-oss/
│   ├── databricks-pipelines/
│   │   └── SKILL.md              -- Decision tree (ST vs MV vs CDC)
│   ├── databricks-aibi-dashboards/
│   │   └── SKILL.md              -- Widget specs, SQL validation
│   ├── databricks-ai-functions/
│   │   └── SKILL.md              -- ai_query, ai_forecast, ai_parse_document
│   ├── databricks-metric-views/
│   │   └── SKILL.md              -- MEASURE() syntax, governed KPIs
│   ├── databricks-dabs/
│   │   └── SKILL.md              -- Declarative Automation Bundles
│   ├── databricks-lakeflow-connect/
│   │   └── SKILL.md              -- Managed ingestion connectors
│   └── databricks-vector-search/
│       └── SKILL.md              -- Endpoint/index patterns
└── custom/
    └── (user-defined skills)
```

### 10.2 — Skill Resolver

Deterministic matching — no LLM call needed:

```python
def resolve_skills(agent_name: str, user_prompt: str = None, max_skills: int = 3) -> list:
    """
    Resolve applicable skills for an agent call.
    
    Priority order:
    1. Explicit mapping (applicable_agents contains agent_name)
    2. Keyword overlap (agent's domain_keywords ∩ skill's domain_keywords)
    3. Prompt keyword scan (if user_prompt provided)
    
    Returns: List of skill_ids, capped at max_skills to respect token budget.
    """
```

**Resolution rules:**
- Max 3 skills per call (prevents context bloat)
- Total injection ≤ 6,000 tokens (leaves room for memory + user prompt)
- `internal` skills always take priority over `databricks-oss`
- Skills can declare `conflicts_with` to prevent contradictory injection

### 10.3 — Skill Injector (Prompt Assembly)

Extends `enhanced_call_agent()` from Phase 9.5:

```python
def enhanced_call_agent(
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    use_memory: bool = True,     # Phase 9.1
    use_rules: bool = True,      # Phase 9.4
    use_skills: bool = True,     # Phase 10 (NEW)
    skill_override: list = None, # Force specific skills
    **kwargs
) -> str:
    """
    Full-stack entry point (Phase 9 + 10):
    1. Skill resolution + injection (NEW)
    2. Memory preload (Phase 9.5)
    3. Stream rule enforcement (Phase 9.4)
    4. Auto-compaction (Phase 9.3)
    """
```

**Prompt assembly order:**
```
┌─────────────────────────────────────┐
│ [SYSTEM PROMPT - agent's base]      │
├─────────────────────────────────────┤
│ [SKILL INJECTION - Phase 10]        │  ← NEW
│ --- Skill: databricks-pipelines --- │
│ (decision tree, patterns, etc.)     │
├─────────────────────────────────────┤
│ [MEMORY PRELOAD - Phase 9.5]        │
│ (prior knowledge from recall)       │
├─────────────────────────────────────┤
│ [POLICY INJECTION - Phase 8]        │
│ (governance rules)                  │
├─────────────────────────────────────┤
│ [USER PROMPT]                       │
└─────────────────────────────────────┘
```

### 10.4 — Databricks-OSS Skill Sync

Automated pull from `databricks/databricks-agent-skills` repo:

```python
def sync_databricks_skills(skills: list = None, force: bool = False) -> dict:
    """
    Pull latest SKILL.md files from databricks-agent-skills GitHub repo
    into /Volumes/mde_dev/test_schema/nexus_skills/databricks-oss/.
    
    - Checks version in frontmatter vs. local
    - Only updates if remote version > local
    - Truncates to token_budget if needed
    - Updates agent_skills Delta table
    
    Schedule: Weekly (alongside Release Intelligence, Monday 7AM ET)
    """
```

**Priority skills to sync (from gap analysis):**

| DB Skill | NEXUS Agents Benefiting | Value |
|----------|------------------------|-------|
| `databricks-pipelines` | 64_sdp_agent | Decision tree prevents ST/MV/CDC confusion |
| `databricks-aibi-dashboards` | 68_ai_bi_dashboard_agent | Widget specs + SQL validation workflow |
| `databricks-ai-functions` | 32-59 (all specialists) | ai_query() for scoring, ai_parse_document() for intake |
| `databricks-metric-views` | 37_data_modeler_agent | MEASURE() syntax for gold/platinum KPIs |
| `databricks-dabs` | 71_notebook_lifecycle_agent | Bundle-based deployment vs. manual |
| `databricks-lakeflow-connect` | 44, 47 (extract agents) | Managed ingestion replaces hand-built ADF |
| `databricks-vector-search` | 70_vector_search_agent | Endpoint patterns, filter syntax |

### 10.5 — Hologic Internal Skills (Migration)

Migrate existing Skills (agents 19, 27-29, 31, 35) from "context injection cells" to first-class Skill Fabric files:

| Current Agent | Migrates To | Content |
|---------------|------------|---------|
| 19_unit_test_documentation | `internal/hologic-test-matrix/SKILL.md` | Test matrix template, Nutter patterns |
| 27_ai_governance | `internal/hologic-ai-governance/SKILL.md` | Model risk, bias, fairness rules |
| 28_enterprise_standards | `internal/hologic-enterprise-standards/SKILL.md` | xxHash64, audit cols, Liquid Clustering, naming |
| 29_documentation | `internal/hologic-documentation/SKILL.md` | Wiki format, changelog template |
| 31_release_approval_board | `internal/hologic-release-gate/SKILL.md` | HARD GATE checklist (PASS/WARN/FAIL) |
| 35_documentation_sync | `internal/hologic-doc-sync/SKILL.md` | Stale detection, auto-changelog rules |

**Benefit:** Skills become editable without touching agent notebooks. Version independently. Apply to multiple agents without duplication.

---

## New Capabilities Unlocked

### AI Functions Integration (via `databricks-ai-functions` skill)

Once injected, agents 32-59 can leverage:

```sql
-- Agent 32 (Oracle EBS) can score invoice anomalies:
SELECT ai_classify(invoice_description, 
  ARRAY('duplicate', 'fraud_risk', 'normal')) AS risk_class
FROM mde_dev.bronze.ap_invoices_all;

-- Agent 77 (Release Intelligence) can parse changelogs:
SELECT ai_extract(changelog_text, 
  ARRAY('breaking_changes', 'deprecations', 'new_features')) AS parsed
FROM release_monitor_raw;

-- Agent 37 (Data Modeler) can forecast table growth:
SELECT ai_forecast(row_count, ds, INTERVAL 90 DAY) AS forecast
FROM mde_dev.test_schema.table_growth_history;
```

### Lakeflow Connect (via `databricks-lakeflow-connect` skill)

Replaces hand-built extract agents (44, 47) with managed ingestion:

| Current | Future (Phase 10) |
|---------|-------------------|
| 44_oracle_ebs_extract_agent (ADF + custom) | Lakeflow Connect Oracle connector |
| 47_salesforce_extract_agent (CDC + custom) | Lakeflow Connect Salesforce connector |
| Custom ServiceNow polling | Lakeflow Connect ServiceNow connector |

### Metric Views (via `databricks-metric-views` skill)

Agent 37 (Data Modeler) gains ability to create governed metrics:

```sql
CREATE METRIC VIEW mde_dev.gold.revenue_metrics AS
SELECT
  fiscal_quarter,
  MEASURE SUM(revenue_amount) AS total_revenue,
  MEASURE COUNT(DISTINCT customer_id) AS unique_customers,
  MEASURE SUM(revenue_amount) / COUNT(DISTINCT customer_id) AS arpu
FROM mde_dev.gold.fact_revenue
GROUP BY fiscal_quarter;
```

### Declarative Automation Bundles (via `databricks-dabs` skill)

Agent 71 (Notebook Lifecycle) + Agent 08 (Scheduler) gain:
- Bundle-based deployment of agent notebooks
- Environment promotion (DEV → UAT → PRD) via `databricks bundle deploy --target`
- Version-pinned agent releases

---

## Integration with Existing Phases

| Phase | Integration Point |
|-------|-------------------|
| Phase 8 (Governance) | Skills respect policy injection order; skill content is policy-checked |
| Phase 9.1 (Memory) | Skills are NOT memorized — they're ephemeral injection. Memory stores discoveries, skills store expertise |
| Phase 9.3 (Compaction) | Skills are PROTECTED from compaction (same as system prompts) |
| Phase 9.4 (Stream Rules) | Skills can declare their own stream rules (e.g., "never use MD5") |
| Phase 9.5 (Session) | Skills load BEFORE memory preload (expertise > experience) |

---

## Cost Analysis

| Component | Cost | Frequency |
|-----------|------|-----------|
| Volume storage (skill .md files) | ~$0.02/month | Static |
| Skill resolution (Delta read) | ~0.001 DBU/call | Per agent call |
| Token overhead (injected content) | +500-2000 tokens/call | Per agent call |
| GitHub sync job | ~0.5 DBU/week | Weekly |
| **Total incremental** | **~$2-5/month** | — |

**Token budget impact:** At average 1,500 tokens/skill × 2 skills/call = 3,000 additional input tokens. With Sonnet 4-6 pricing, this adds ~$0.009/call. At 500 calls/month = **$4.50/month**.

---

## Implementation Plan

| Step | Sub-Phase | Effort | Dependency |
|------|-----------|--------|------------|
| 1 | Create Volume + seed internal skills (10.1) | 2 hours | None |
| 2 | Build `agent_skills` Delta table (10.1) | 1 hour | Step 1 |
| 3 | Implement `resolve_skills()` (10.2) | 2 hours | Step 2 |
| 4 | Extend `enhanced_call_agent()` (10.3) | 2 hours | Step 3 |
| 5 | Sync 7 priority Databricks-OSS skills (10.4) | 3 hours | Step 1 |
| 6 | Migrate 6 internal skills from agents (10.5) | 2 hours | Step 1 |
| 7 | Validation — run agents 64, 68, 70 with skills | 1 hour | Steps 4-6 |
| **Total** | | **~13 hours** | |

---

## Success Metrics

| Metric | Baseline (Phase 9) | Target (Phase 10) | Measurement |
|--------|--------------------|--------------------|-------------|
| Agent output quality (peer review scores) | 6.2/10 avg | 7.5/10 avg | Agent 07 scores |
| Platform knowledge accuracy | Manual (stale) | Auto-updated weekly | Skill version freshness |
| Skill reuse (agents sharing same skill) | 0 (bespoke prompts) | 4+ agents per skill | Registry query |
| Time to onboard new platform feature | Days (rewrite prompts) | Hours (add skill file) | Change log |
| Agent hallucination on Databricks APIs | Unmeasured | < 5% per review cycle | Stream rule violations |

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Skill content exceeds context window | Agent fails or truncates | Token budget cap (6,000 max), auto-compaction |
| Databricks-OSS skill contradicts Hologic standard | Incorrect output | Internal skills ALWAYS override OSS; conflict detection |
| Stale OSS skill (repo lags platform) | Outdated guidance | Weekly sync + Agent 81 (Databricks Release Monitor) cross-check |
| Over-injection (too many skills) | Diluted focus | Max 3 skills/call, relevance scoring |
| Volume access from AI Builder workspace | Read fails | Volume is in `mde_dev` — verify cross-workspace read access |

---

## Relationship to databricks/databricks-agent-skills

| Aspect | DB Agent Skills | NEXUS Phase 10 |
|--------|----------------|----------------|
| Purpose | Teach external coding agents Databricks patterns | Teach NEXUS agents platform + domain expertise |
| Consumer | Claude Code, Cursor, Copilot, Codex | NEXUS agents (132) via `enhanced_call_agent()` |
| Content | Generic Databricks best practices | Hologic-specific + curated Databricks subset |
| Delivery | Loaded into IDE context window | Injected into agent system prompt |
| Updates | Plugin marketplace / CLI | Automated Volume sync + Delta versioning |
| Customization | None (one-size-fits-all) | Per-agent resolution, token budgets, priority |

**Philosophy:** We don't fork the OSS skills — we *consume* them through a resolution layer that adds Hologic context and respects our standards. Internal skills always win conflicts.

---

## Future (Phase 11+ candidates)

- **Skill authoring agent** — Auto-generates new skills from agent output patterns
- **Skill effectiveness scoring** — Track which skills improve peer review scores
- **Cross-agent skill sharing** — W2/W3/W4 agents inherit W1 skill resolutions
- **Dynamic skill generation** — LLM condenses long reference docs into token-efficient skills on-demand
- **Community skill marketplace** — Publish Hologic-internal skills back as anonymized OSS contributions

---

*Document version: 1.0 | Created: July 1, 2026 | Author: NEXUS Platform Team*
