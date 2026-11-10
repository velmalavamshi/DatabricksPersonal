# NEXUS Phase 12 — App Capabilities Enhancement (hologic-ai-agents)

> **Status:** In Progress (Track 1 ⬜ NOT STARTED, Track 2 🟢 COMPLETE (verified via export_docs.py — PDF/DOCX, not PPTX as originally scoped), Track 3 🟢 Core done (7/10), Track 4 🟢 COMPLETE (8/10), Track 5 🟡 — prompt integration in testing, Track 6 🟢 COMPLETE, Track 7 ⬜ NOT STARTED, Track 8 ⬜ NOT STARTED, Track 9 🟢 COMPLETE (verified via query_cache.py)) — re-verified against live app source Aug 11, 2026  
> **Created:** 2026-07-27  
> **Last Updated:** 2026-07-28  
> **Owner:** sameet.patel@hologic.com  
> **Context:** Extends the `hologic-ai-agents` Databricks App with advanced input/output capabilities — image upload, document generation, and live workspace asset creation.  
> **Depends on:** Phase 11 (agent registry completion), App deployment stability

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 | Blocked / Immediate action required |
| 🟡 | In-progress / partially complete |
| 🟢 | Complete |
| ⬜ | Not started |
| ⏭️ | Deferred / batched |

---

## Executive Summary

The `hologic-ai-agents` app currently supports text-based chat and SQL query execution. Phase 12 extends it with three major capability tracks:

1. **Image Upload** — Accept image inputs for visual analysis, OCR, document parsing
2. **Document Generation** — Create PowerPoint and PDF deliverables from agent outputs
3. **Live Asset Creation** — Programmatically create Databricks dashboards, notebooks, Genie spaces, and AI/BI dashboards from within the app
4. **Token Limit Hardening** — Resolve silent truncation and context budget issues across all 132 agents
5. **Image Generation** — Produce colorful dashboard mockups, architecture diagrams, ERDs, and branded infographics from natural language
6. **Live Asset Query** — Paste a workspace path (notebook, SQL file, .py, .md) and have NEXUS read, display, and analyze the content live
7. **Power BI Dataset Discovery** — Connect to Power BI REST API, inventory existing datasets/reports, and redirect users to existing assets instead of suggesting duplicate builds
8. **MCP-to-Claude Integration** — Expose the NEXUS MCP endpoint to Claude Desktop and Claude.ai, enabling Claude to use all 132 NEXUS agents as tools natively
9. **Query Result Caching** — Session-scoped cache with xxHash64 keys + tiered TTL (6hr DDL, 15-30min data) to eliminate redundant live queries and reduce token consumption by 60-70%

These capabilities elevate the app from a chat-only interface to a full **action-oriented agent platform** — users can ask questions, see visual analysis, generate mockups, and get production-ready artifacts delivered directly into the workspace.

---

## Track 1 — Image Upload Support

### Objective

Allow users to upload images (screenshots, diagrams, photos) into the chat interface for analysis by vision-capable models.

### Use Cases

| # | Use Case | Example |
|---|----------|--------|
| 1.1 | Error screenshot triage | Upload job failure screenshot → Agent 01 diagnoses root cause |
| 1.2 | Architecture diagram review | Upload HLD diagram → Agent 06 provides feedback |
| 1.3 | Data quality visual checks | Upload chart/report → identify anomalies |
| 1.4 | Document parsing / OCR | Upload PDF page image → extract structured data |
| 1.5 | Dashboard mockup interpretation | Upload whiteboard sketch → Agent 68 generates Lakeview spec |

### Technical Considerations

| Aspect | Detail |
|--------|--------|
| Model requirement | Vision-capable model (Claude Sonnet 4/Opus 4 support image inputs natively) |
| Input format | Base64-encoded image in API `content` array (type: `image`) |
| Max size | TBD — check AI Gateway payload limits |
| Supported formats | PNG, JPEG, GIF, WebP (model-dependent) |
| UI component | File upload widget in Gradio/Streamlit chat input |
| Storage | Transient (in-memory for current session) vs. persisted (UC Volume) — TBD |
| Token cost | Images consume tokens (~1,600 tokens per 1024x1024 image) |
| Governance | Phase 8 policies may need `image_tokens` as new cost metric |

### Sub-Tasks

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.1 | Add file upload widget to app.py chat interface | ⬜ | Gradio `gr.File()` or `gr.Image()` component |
| 1.2 | Implement base64 encoding + content array formatting | ⬜ | Match Claude API multimodal message format |
| 1.3 | Route image messages through AI Gateway | ⬜ | Verify `databricks-claude-sonnet-4-6` accepts image content |
| 1.4 | Add image size validation + compression | ⬜ | Reject >20MB, auto-resize if >4096px |
| 1.5 | Update system prompt to acknowledge vision capability | ⬜ | Tell agents they can "see" uploaded images |
| 1.6 | Test with all use cases (1.1–1.5) | ⬜ | |
| 1.7 | Add governance: track image token cost in `log_agent_call()` | ⬜ | New column or metadata field |

---

## Track 2 — Document Generation (PPT, PDF)

> **VERIFIED Aug 11, 2026:** Implemented in `export_docs.py` (added 2026-08-08) — but via **reportlab (PDF) + python-docx (DOCX)**, not `python-pptx` as originally scoped below. Objective met (agents/sessions produce downloadable documents with Hologic branding) via a different, working mechanism: `build_session_pdf()` + a shared `parse_markdown_blocks()` parser reused across PDF/DOCX/print-HTML. Wired to real endpoints in `routers/sessions.py`: `GET /api/sessions/{id}/export.pdf`, `.docx`, `/print`. Scope is session-export-triggered (client clicks Export), not yet agent-triggered (Track 2.7 — "wire Agent 39/06/77 to produce doc-ready output" — not found in code, likely still open).

### Objective

Allow agents to produce downloadable PowerPoint and PDF documents as output — not just text responses.

### Use Cases

| # | Use Case | Agent(s) | Output |
|---|----------|----------|--------|
| 2.1 | Executive briefing | Agent 39 (Morning Briefing) | PPTX with KPI boxes, RAG status |
| 2.2 | Architecture design | Agent 06 (Solution Architect) | PDF with HLD diagrams, component specs |
| 2.3 | Data quality report | Agent 16 (Data Quality) | PDF with DQ scores, trend charts |
| 2.4 | Cost analysis deck | Agent 05 (Cost Anomaly) | PPTX with spend breakdowns, savings recs |
| 2.5 | Release impact report | Agent 77 (Release Intelligence) | PDF with vendor impact matrix |
| 2.6 | Business case | W3 agents (Business Champions) | PPTX board-ready presentation |

### Technical Considerations

| Aspect | Detail |
|--------|--------|
| PPTX library | `python-pptx` (already used in cost/hash reports) |
| PDF library | `fpdf2` or `reportlab` (lightweight) or `weasyprint` (HTML→PDF) |
| Template approach | Pre-built Hologic-branded templates with placeholder slides |
| Color palette | DARK_BLUE=#1B2A4A, RED=#E74C3C, GREEN=#27AE60 (existing standard) |
| Download mechanism | Gradio `gr.File()` output component or download link |
| Storage | Generate to UC Volume (`/Volumes/mde_dev/test_schema/app_outputs/`) or workspace path |
| Charts in docs | `matplotlib` → image → embed in PPTX/PDF |
| Size limits | PPTX ~5-20 slides max, PDF ~10-50 pages max |

### Sub-Tasks

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | Add `python-pptx` and PDF library to `requirements.txt` | ⬜ | Check current requirements |
| 2.2 | Create Hologic PPTX template (title slide, content, KPI, table layouts) | ⬜ | Reuse existing template from cost report |
| 2.3 | Build `generate_pptx()` utility function | ⬜ | Input: structured JSON from agent → Output: .pptx bytes |
| 2.4 | Build `generate_pdf()` utility function | ⬜ | Input: markdown/HTML from agent → Output: .pdf bytes |
| 2.5 | Add download button/link to chat UI | ⬜ | Display inline preview + download |
| 2.6 | Define agent output format for doc generation | ⬜ | JSON schema: `{type: "pptx", slides: [...]}` |
| 2.7 | Wire Agent 39, 06, 77 to produce doc-ready output | ⬜ | New output_type in `save_agent_output()` |
| 2.8 | Add UC Volume storage for generated docs | ⬜ | `/Volumes/mde_dev/test_schema/app_generated_docs/` |
| 2.9 | Test end-to-end: user asks → agent generates → doc downloads | ⬜ | |

---

## Track 9 — Query Result Caching

> **VERIFIED Aug 11, 2026:** Fully implemented in `query_cache.py` (header comment explicitly says "Phase 12, Track 9"). Tiered TTL matches spec closely: SCHEMA=6hr, METADATA=1hr, DATA=30min, CONTEXT=24hr, NOCACHE=0. Uses `xxhash64` cache keys (NEXUS hash standard) via `cache_key()`. Wired to live endpoints `GET /api/cache/stats` and `POST /api/cache/reset` in `routers/enhancements.py`. **This track should be marked COMPLETE.**

---

## Track 3 — Live Workspace Asset Creation

### Objective

Allow the app to create real, live Databricks workspace assets on behalf of the user — dashboards, notebooks, Genie spaces, and AI/BI dashboards.

### Use Cases

| # | Use Case | Asset Created | API |
|---|----------|---------------|-----|
| 3.1 | "Create a dashboard showing monthly revenue" | Lakeview Dashboard | Lakeview API |
| 3.2 | "Generate a notebook for this ETL pipeline" | Notebook | Workspace API |
| 3.3 | "Set up a Genie space for the sales team" | Genie Space | Genie API |
| 3.4 | "Build an AI/BI dashboard for cost monitoring" | AI/BI Dashboard | Lakeview + AI API |
| 3.5 | "Create a notebook to investigate this issue" | Notebook with pre-filled code | Workspace Import API |

### Technical Considerations

| Aspect | Detail |
|--------|--------|
| Authentication | App Service Principal (SP) — must have workspace-level CREATE permissions |
| Notebook creation | `POST /api/2.0/workspace/import` with base64-encoded content |
| Dashboard creation | `POST /api/2.0/lakeview/dashboards` with serialized dashboard JSON |
| Genie Space creation | Genie API — requires table identifiers (fully qualified) |
| Permissions | SP needs: CAN_MANAGE on target folders, USE_CATALOG/USE_SCHEMA on tables |
| Output location | User-configurable or default: `/Workspace/Users/<user>/NEXUS_Generated/` |
| IP ACL constraint | ⚠️ Current blocker: Apps blocked from workspace API by IP ACL (see Environment Notes) |
| Workaround options | (a) Whitelist app IP, (b) Use Jobs API to trigger creation, (c) Proxy through serverless |
| Naming convention | Auto-generated: `NEXUS_<type>_<topic>_<YYYYMMDD>` |
| Idempotency | Check if asset exists before creating; offer overwrite or version suffix |

### Sub-Tasks

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | Resolve IP ACL blocker for workspace API access from app | 🟢 | Done — resolved via host file update on drivers/etc. Track 6 reads confirmed working. |
| 3.2 | Grant app SP necessary workspace permissions | 🟡 | SP has workspace.workspace scope. Needs CAN_MANAGE on NEXUS_Generated folder — test on first creation. |
| 3.3 | Implement `create_notebook()` in app backend | 🟢 | Done — `create_workspace_notebook()` in app.py lines 165-225. Uses Workspace Import API + base64. |
| 3.4 | Implement `create_dashboard()` in app backend | 🟢 | Done — `create_workspace_dashboard()` in app.py lines 228-270. Uses Lakeview REST API. |
| 3.5 | Implement `create_genie_space()` in app backend | 🟢 | Done — `create_genie_space()` in app.py lines 273-310. Uses Genie REST API. |
| 3.6 | Implement `create_aibi_dashboard()` in app backend | ⬜ | Deferred — Lakeview + natural language spec. Can reuse 3.4 with AI-generated spec. |
| 3.7 | Build agent-to-asset translation layer | 🟢 | Done — LLM outputs `[CREATE_ASSET]{...}[/CREATE_ASSET]` JSON blocks. Post-processor parses and executes. |
| 3.8 | Add asset creation confirmation + link in chat UI | 🟢 | Done — `format_creation_result()` renders emoji + path + clickable URL link. |
| 3.9 | Add to governance: track asset creation in `agent_policy_log` | ⬜ | P2 — New action type: `create_asset` |
| 3.10 | Test all 5 use cases end-to-end | ⬜ | Needs live testing — SP may need CAN_MANAGE grant on output folder |

---

## API Reference (for implementation)

### Notebook Creation
```python
import base64
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
content = base64.b64encode(notebook_source.encode()).decode()
w.workspace.import_(
    path="/Workspace/Users/.../NEXUS_Generated/my_notebook",
    format="SOURCE",
    language="PYTHON",
    content=content,
    overwrite=True
)
```

### Dashboard Creation
```python
w.lakeview.create(
    display_name="NEXUS_Dashboard_Revenue_20260727",
    warehouse_id="<sql_warehouse_id>",
    serialized_dashboard=json.dumps(dashboard_spec)
)
```

### Genie Space Creation
```python
# Via REST API (SDK may not have full Genie support yet)
response = requests.post(
    f"https://{host}/api/2.0/genie/spaces",
    headers=headers,
    json={
        "title": "Sales Team Genie Space",
        "table_identifiers": ["mde_dev.gold.fact_sales", "mde_dev.gold.dim_customer"],
        "warehouse_id": "<warehouse_id>"
    }
)
```

---

## Track 4 — Token Limit Hardening

### Objective

Resolve token budget constraints across all 132 NEXUS agents that silently degrade output quality — truncated JSON, lost context, missed memories, and incomplete reports.

### Critical Findings (Audit: July 2026)

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 4.1 | `max_tokens=4096` hard output cap (default in `call_agent()`) | 🔴 CRITICAL | JSON-generating agents (77, 37, 06) silently truncate. Broken JSON falls to `except` handler and stored as raw text |
| 4.2 | No `finish_reason=="length"` detection | 🔴 CRITICAL | Truncated responses pass silently — no retry, no error, no alert. Only failure mode with zero signal |
| 4.3 | `enhanced_call_agent()` adoption gap | 🟠 HIGH | Phase 9 protections (memory, compaction, stream rules) are opt-in. Agent 77 and most agents use bare `call_agent()`, bypassing all intelligence features |
| 4.4 | Token budget caps too tight | 🟠 HIGH | `memory_injection: 800` tokens (3.2K chars) overflows with 10 memories × 500 chars = 5K chars. `upstream_context: 2000` insufficient for cross-agent DDL passing |
| 4.5 | Compaction summarizer `max_tokens=256` | 🟡 MEDIUM | Dozens of compacted messages summarized into ~190 words — guaranteed information loss for complex sessions |
| 4.6 | BGE embedding input truncation `text[:512]` | 🟡 MEDIUM | Only first 512 characters embedded. Long memories lose semantic accuracy in `recall()` |
| 4.7 | Session consolidation lossy boundaries | 🟡 MEDIUM | `_read_session_outputs()` applies `LIMIT 50` + `content[:500]` — rich sessions lose facts from output 51+ permanently |
| 4.8 | `trim_to_budget()` safety bypass for structured content | 🟡 MEDIUM | DDL/JSON/SQL passes through untouched regardless of budget — correct for integrity but can blow context window without triggering compaction |
| 4.9 | Token estimation imprecision (`len//4`) | 🟢 LOW | `_CHARS_PER_TOKEN=4` is 30-40% inaccurate for code/JSON (actual ratio ~2.5-3). Compaction triggers too late for structured content |
| 4.10 | Stream rules retry cost (APEX agents) | 🟢 LOW | `abort_retry` discards full generation. 3× cost on APEX agents (~$0.42 wasted per triple-retry) |

### Token Budget Analysis

| Budget Key | Current Limit | Effective Chars | Problem | Recommended |
|------------|--------------|-----------------|---------|-------------|
| `memory_injection` | 800 tokens | ~3,200 chars | 10 memories × 500 chars = 5,000 chars → overflows | 1,500 tokens |
| `upstream_context` | 2,000 tokens | ~8,000 chars | Cross-agent DDL/schema payloads easily exceed 8K | 4,000 tokens |
| `catalog_scan` | 3,000 tokens | ~12,000 chars | Insufficient for agents scanning 1,263 Oracle tables | 5,000 tokens |
| `system_prompt` | 6,000 tokens | ~24,000 chars | Agent 77 system prompt (~2K) + memory + context = tight | 8,000 tokens |

### Output Token Cap Risk Matrix

| Agent | Output Type | Why 4,096 Tokens Is Insufficient | Recommended `max_tokens` |
|-------|-------------|----------------------------------|-------------------------|
| 77 (Release Intelligence) | Multi-vendor JSON report | 4-6 vendors × structured impact items | 8,192 |
| 37 (Data Modeler) | Full Kimball schema DDL | Multiple fact/dim CREATE statements + relationships | 8,192 |
| 06 (Solution Architect) | HLD/LLD with component specs | Architecture decisions + rationale + diagrams-as-text | 8,192 |
| 39 (Morning Briefing) | Daily consolidated brief | All overnight failures + KPIs + action items | 6,144 |
| 16 (Data Quality) | DQ rule generation + scoring | DQX expectations across multiple tables | 6,144 |
| 88 (Qlik Orchestrator) | Migration plan + wave schedule | 1,263 table mapping + dependency graph | 8,192 |
| All APEX agents | Complex reasoning outputs | Architecture, peer review, data modeling | 8,192 |

### Sub-Tasks

| # | Task | Status | Priority | Effort | Notes |
|---|------|--------|----------|--------|-------|
| 4.1 | Add `finish_reason=="length"` detection in `call_agent()` — auto-retry with 2× `max_tokens` | 🟢 | 🔴 P0 | 15 min | Done — retries once with min(max_tokens*2, 16384), logs WARN_TRUNCATED if still cut |
| 4.2 | Raise default `max_tokens` to 8192 for CRITICAL/APEX agents | 🟢 | 🔴 P0 | 5 min | Done — `_TIER_MAX_TOKENS` dict, overrides default 4096 when caller doesn't specify |
| 4.3 | Make Phase 9 features default-on in `enhanced_call_agent()` | 🟢 | 🟠 P1 | 1 hr | Done — `use_memory=True, use_rules=True` already default; confirmed as canonical entry point |
| 4.4 | Increase token budgets: `memory_injection→1500`, `upstream_context→4000`, `catalog_scan→5000` | 🟢 | 🟠 P1 | 5 min | Done — updated `_TOKEN_BUDGETS` in shared_token_optimizer + system_prompt→8000 |
| 4.5 | Raise compaction summarizer `max_tokens` from 256 → 512 | 🟢 | 🟡 P2 | 2 min | Done — in `_summarize_messages()` Phase 9.3 |
| 4.6 | Increase BGE embedding input from `text[:512]` → `text[:2048]` | 🟢 | 🟡 P2 | 2 min | Done — in `_get_embedding_bge()` Phase 9.1 |
| 4.7 | Raise session consolidation limits: `LIMIT 50→100`, `content[:500]→content[:1000]` | 🟢 | 🟡 P2 | 5 min | Done — in `_read_session_outputs()` Phase 9.5 |
| 4.8 | Add per-tier `max_tokens` to `AGENT_REGISTRY` schema | ⬜ | 🟡 P2 | 15 min | Deferred — _TIER_MAX_TOKENS dict handles this globally for now |
| 4.9 | Add token usage telemetry: log `finish_reason` to `agent_call_log` | 🟢 | 🟡 P2 | 10 min | Done — new param in log_agent_call(), mergeSchema adds column on first write |
| 4.10 | Improve token estimation for structured content (calibrate `_CHARS_PER_TOKEN`) | ⬜ | ⏭️ | 30 min | Deferred — requires tiktoken benchmarking |

### Implementation Notes

**Fix 4.1 — `finish_reason` detection (pseudocode):**
```python
# Inside call_agent(), after response = client.chat.completions.create(...):
if response.choices[0].finish_reason == "length":
    # Output was truncated — retry with doubled budget
    _llm_kwargs["max_tokens"] = min(max_tokens * 2, 16384)
    response = client.chat.completions.create(**_llm_kwargs)
    if response.choices[0].finish_reason == "length":
        # Still truncated — log warning, return what we have
        log_agent_call(agent_name, model, tokens_in, tokens_out, 
                      duration, "WARN_TRUNCATED")
```

**Fix 4.2 — Tier-based output caps:**
```python
# In call_agent(), derive max_tokens from registry tier:
_DEFAULT_MAX_TOKENS = {
    LLM_APEX: 8192,
    LLM_CRITICAL: 8192,
    LLM_STANDARD: 4096,
}
if max_tokens == 4096:  # Only override if caller used default
    max_tokens = _DEFAULT_MAX_TOKENS.get(model, 4096)
```

**Fix 4.3 — Phase 9 default-on (non-breaking migration):**
```python
# Rename existing call_agent → _call_agent_raw
# New call_agent wraps enhanced_call_agent with defaults:
def call_agent(agent_name, system_prompt, user_prompt, 
              temperature=0.1, max_tokens=4096,
              use_memory=True, use_rules=True):
    return enhanced_call_agent(agent_name, system_prompt, user_prompt,
                               use_memory=use_memory, use_rules=use_rules,
                               temperature=temperature, max_tokens=max_tokens)
```

### Cost Impact

| Change | Token Increase | Est. Cost Delta | Justification |
|--------|---------------|-----------------|---------------|
| Raise APEX/CRITICAL to 8192 | ~2× output tokens on truncated calls | +$2-5/mo | Only triggers when 4K was insufficient — prevents data loss |
| `finish_reason` retry | ~1.5× on ~5% of calls | +$1-3/mo | Better than corrupted output requiring human re-run |
| Memory budget 800→1500 | +700 tokens/call input | +$0.50/mo | Minimal — input tokens are 3× cheaper than output |
| Compaction summary 256→512 | +256 tokens per compaction event | +$0.10/mo | Compaction fires rarely (<5% of calls) |
| **Total incremental** | | **~$4-9/mo** | **Well within $35-60/mo platform budget** |

---

## Track 5 — Image Generation (Mockups, Diagrams, Visualizations)

### Objective

Allow the app to generate colorful, high-fidelity images on demand — dashboard mockups, app wireframes, architecture diagrams, data flow visuals, and branded report graphics — directly from natural language descriptions.

### Use Cases

| # | Use Case | Example | Output |
|---|----------|---------|--------|
| 5.1 | Dashboard mockup | "Show me what a revenue dashboard would look like" | PNG/SVG mockup with KPI boxes, charts, Hologic branding |
| 5.2 | App UI wireframe | "Generate a mockup of the NEXUS chat interface with image upload" | PNG wireframe with components |
| 5.3 | Architecture diagram | "Draw the medallion architecture for the EBS pipeline" | PNG/SVG with Bronze→Silver→Gold flow |
| 5.4 | Data flow visualization | "Visualize the agent communication pattern for Release Intelligence" | PNG with nodes, edges, labels |
| 5.5 | Executive infographic | "Create a one-pager showing our $183K cost breakdown" | Branded infographic PNG |
| 5.6 | ERD / schema diagram | "Generate an ERD for the fact_sales star schema" | PNG with tables, relationships, keys |
| 5.7 | Status/progress visual | "Show Phase 12 progress as a visual roadmap" | Gantt-style or roadmap PNG |

### Technical Approaches

| Approach | Tool/Library | Pros | Cons | Cost |
|----------|-------------|------|------|------|
| **A. Programmatic (matplotlib/plotly)** | `matplotlib`, `plotly`, `seaborn` | Free, deterministic, full control, Hologic colors | Limited to charts/graphs, no creative mockups | $0 |
| **B. Diagram-as-code** | `diagrams`, `graphviz`, `mermaid` | Architecture diagrams, ERDs, flowcharts | Not for UI mockups, limited styling | $0 |
| **C. HTML/CSS → Image** | `playwright`, `imgkit`, `html2image` | Full UI mockups via HTML templates, pixel-perfect | Requires headless browser, heavier deps | $0 |
| **D. AI Image Generation** | DALL-E 3 / Stable Diffusion via API | Creative, natural language driven, photorealistic | Cost per image, less deterministic, may hallucinate UI | ~$0.04-0.08/image |
| **E. SVG Template Engine** | Custom Jinja2 + SVG templates | Deterministic, Hologic-branded, lightweight | Requires template per visual type | $0 |

### Implemented Strategy (Hybrid — Zero Browser Deps)

```
User Request → classify_visual_type() → Route to renderer:

├── dashboard_mockup       → generate_dashboard_mockup()  [matplotlib patches]
├── kpi_card              → generate_kpi_cards()         [matplotlib patches]
├── architecture          → generate_architecture_diagram() [matplotlib layers]
├── erd                   → generate_erd()               [matplotlib tables + lines]
├── flowchart             → generate_flowchart()         [matplotlib horizontal steps]
├── timeline              → generate_timeline()          [matplotlib milestones]
├── chart (bar/line/pie)  → generate_chart()             [plotly+kaleido, mpl fallback]
├── infographic           → ⚠️ FALLS BACK TO chart (no dedicated generator yet)
└── Creative/Abstract     → ⚠️ NOT YET IMPLEMENTED (planned: AI Gateway → DALL-E 3)
```

### Technical Considerations (UPDATED — reflects actual implementation)

| Aspect | Detail |
|--------|--------|
| Primary renderer | `matplotlib` FancyBboxPatch compositions (zero browser dependency) |
| Chart engine | `plotly` + `kaleido` (static PNG export), `matplotlib` fallback if plotly unavailable |
| Diagram engine | `matplotlib` patches + annotations (NOT graphviz — avoids binary dep) |
| AI fallback | ⚠️ NOT YET: planned route through AI Gateway to DALL-E 3 for creative/abstract |
| Color palette | `HologicColors` class: DARK_BLUE=#1B2A4A, RED=#E74C3C, GREEN=#27AE60, LIGHT_GRAY=#F8F9FA, + CHART_PALETTE |
| Output format | PNG only (via `fig.savefig()` at 150 DPI default, configurable) |
| Resolution | 16×10 inches @ 150 DPI = 2400×1500px (dashboard), configurable per generator |
| Delivery | `st.image()` inline + `st.download_button()` for PNG download |
| Template library | matplotlib patch-based composable components (header, KPI row, chart area, table, footer) |
| Caching | ⚠️ NOT YET: planned hash → cache in `/Volumes/mde_dev/test_schema/app_generated_images/` |
| Streamlit compat | ⚠️ Container Streamlit uses `use_column_width` for `st.image()` (NOT `use_container_width`). Buttons/forms use `use_container_width`. |
| System prompt | SUPERVISOR_PROMPT must include visual generation as explicit capability — without it, LLM rejects as "Outside Platform Capability" |

### Dashboard Mockup Template System

```
Dashboard mockup components (HTML/CSS blocks):
├── Header bar (title, date range, filters)
├── KPI row (4-6 metric cards with sparklines)
├── Chart area (bar, line, pie, heatmap placeholders)
├── Table widget (sortable columns with sample data)
├── Filter sidebar (dropdowns, date pickers)
└── Footer (data source, last refresh timestamp)
```

Agent generates a JSON spec → Template engine assembles HTML → Renderer captures PNG:
```json
{
  "type": "dashboard_mockup",
  "title": "Monthly Revenue Dashboard",
  "kpis": [
    {"label": "Total Revenue", "value": "$4.2M", "trend": "+12%", "color": "green"},
    {"label": "Active Accounts", "value": "1,847", "trend": "-3%", "color": "red"}
  ],
  "charts": [
    {"type": "bar", "title": "Revenue by Region", "position": "left"},
    {"type": "line", "title": "Monthly Trend", "position": "right"}
  ],
  "tables": [
    {"title": "Top 10 Accounts", "columns": ["Account", "Revenue", "Growth"]}
  ]
}
```

### Sub-Tasks

| # | Task | Status | Priority | Notes |
|---|------|--------|----------|-------|
| 5.1 | Add `plotly`, `kaleido`, `matplotlib`, `Pillow` to `requirements.txt` | 🟢 | P1 | Done — no graphviz needed (matplotlib handles diagrams) |
| 5.2 | Evaluate rendering approach for app container | 🟢 | P1 | Decision: matplotlib patches (zero browser deps, works in any container) |
| 5.3 | Build Hologic-branded dashboard template library (5 layouts) | 🟢 | P1 | Done — matplotlib patch-based: header, KPI row, chart area, table, footer |
| 5.4 | Build `generate_dashboard_mockup()` function — JSON spec → PNG | 🟢 | P1 | Done — `image_generator.py` with full Hologic branding |
| 5.5 | Build `generate_architecture_diagram()` + `generate_erd()` + `generate_flowchart()` | 🟢 | P2 | Done — layered architecture, star schema ERD, horizontal pipeline flow |
| 5.5b | Build `generate_timeline()` + `generate_kpi_cards()` | 🟢 | P2 | Done — horizontal roadmap with milestone nodes + standalone KPI cards with trend badges |
| 5.6 | Build `generate_chart()` function — plotly → PNG via kaleido | 🟢 | P2 | Done — bar, line, pie, scatter + matplotlib fallback |
| 5.6b | Build `generate_infographic()` function | ⬜ | P2 | ⚠️ GAP — classifier returns `infographic` but no dedicated renderer; falls back to chart |
| 5.7 | Add AI image generation route through AI Gateway (DALL-E 3) | ⬜ | P3 | For creative/abstract requests only |
| 5.8 | Build visual type classifier in agent routing | 🟢 | P1 | Done — `classify_visual_type()` routes to 7 renderer types (+ infographic fallback) |
| 5.9 | Add inline image display in Streamlit chat UI | 🟢 | P1 | Done — `st.image()` + `st.download_button()` in app.py. Bug fix: `use_column_width=True` required (not `use_container_width`) for container Streamlit version. |
| 5.9b | Add image history re-render on Streamlit re-run | 🟢 | P1 | Done — stores `image_key` in `msg_record`, history loop re-renders from `st.session_state.generated_images` with download button |
| 5.9c | Update SUPERVISOR_PROMPT to allow visual generation | 🟢 | P0 | Done — Added `## ⚡ CRITICAL: VISUAL GENERATION IS A PLATFORM CAPABILITY` as #2 behavioral rule + TYPE 5 engagement route. Without this, LLM rejects image requests as "Outside Platform Capability" |
| 5.10 | Add image download + save to UC Volume option | ⬜ | P2 | `/Volumes/mde_dev/test_schema/app_generated_images/` |
| 5.11 | Create 5 example mockups for demo/testing | ⬜ | P2 | Revenue dashboard, ETL pipeline, agent architecture, ERD, cost report |
| 5.12 | Wire to Agent 68 (AI/BI Dashboard) for pre-build previews | ⬜ | P3 | "Preview before creating live" workflow |

### Integration with Other Tracks

| Integration | How |
|-------------|-----|
| Track 2 (PPT/PDF) | Generated images embed directly into PPTX slides and PDF pages |
| Track 3 (Live Assets) | Mockup → user approves → create live dashboard with same spec |
| Track 1 (Image Upload) | User uploads sketch → AI interprets → generates polished mockup |
| Track 4 (Token) | Image generation prompts are short — minimal token impact |

### Cost Impact

| Component | Est. Monthly Cost | Notes |
|-----------|-------------------|-------|
| Programmatic rendering (A/B/C/E) | $0 | Runs in app container |
| AI image generation (D) — if used | ~$2-8/mo | ~$0.04/image × 50-200 images/mo |
| UC Volume storage | ~$0.01/mo | PNGs are small (~100KB-2MB each) |
| **Total** | **~$2-8/mo** | Only if AI generation is enabled |

---

## Track 6 — Live Asset Query (Workspace Path Resolution)

### Objective

Allow users to paste a workspace path (e.g., `/Workspace/DataEngineering/Transform/Facts/fact_wip_value_mfg`) into the chat and have NEXUS resolve, read, and display the asset content live — notebooks, SQL files, Python scripts, or Delta table metadata.

### Use Cases

| # | Use Case | Example Input | Action |
|---|----------|---------------|--------|
| 6.1 | Read notebook content | `/Workspace/DataEngineering/Transform/Facts/fact_wip_value_mfg` | Fetch notebook cells, display code + markdown, summarize logic |
| 6.2 | Inspect SQL file | `/Workspace/Shared/queries/monthly_revenue.sql` | Read file, parse SQL, explain transformations |
| 6.3 | Read Python module | `/Workspace/Users/sameet.patel@hologic.com/5 - AI Multi Agents/5 - Agent Chat App/image_generator.py` | Display source, summarize exports/functions |
| 6.4 | Table lineage from path | `/Workspace/.../fact_wip_value_mfg` | Infer table name → query UC metadata, show schema + row counts |
| 6.5 | Diff two assets | "Compare `/path/a` with `/path/b`" | Read both, show side-by-side diff |
| 6.6 | Review pipeline code | `/Workspace/DataEngineering/Pipelines/bronze_to_silver` | Read SDP pipeline notebook, summarize medallion flow |

### Technical Design

```
User Input Detection:
  Regex: r'/Workspace/[^\s]+' → extract path(s) from message

Resolution Flow:
  1. Detect path(s) in user_input
  2. Call Workspace API: GET /api/2.0/workspace/get-status → get object type + language
  3. Based on type:
     - NOTEBOOK → GET /api/2.0/workspace/export (format=SOURCE) → decode base64
     - FILE → GET /api/2.0/workspace/export (format=AUTO) → read raw content
     - DIRECTORY → GET /api/2.0/workspace/list → show tree
  4. Inject content into LLM context as structured block:
     ```
     [WORKSPACE ASSET: /path/to/asset]
     Type: NOTEBOOK | Language: PYTHON
     --- Content ---
     <cell contents>
     --- End ---
     ```
  5. LLM responds with analysis/summary of the asset
```

### Implementation Approach

```python
import re, base64

def detect_workspace_paths(text: str) -> list[str]:
    """Extract workspace paths from user input."""
    return re.findall(r'/Workspace/[^\s\'"`,;)}\]]+', text)

def resolve_workspace_asset(path: str, w: WorkspaceClient) -> dict:
    """Resolve a workspace path to its content."""
    status = w.workspace.get_status(path)
    obj_type = status.object_type  # NOTEBOOK, FILE, DIRECTORY
    
    if obj_type in ("NOTEBOOK", "FILE"):
        export = w.workspace.export(path, format="SOURCE")
        content = base64.b64decode(export.content).decode("utf-8")
        return {
            "path": path,
            "type": obj_type.value,
            "language": getattr(status, "language", "UNKNOWN"),
            "content": content,
            "size": len(content),
        }
    elif obj_type == "DIRECTORY":
        items = list(w.workspace.list(path))
        return {
            "path": path,
            "type": "DIRECTORY",
            "items": [{"name": i.path.split("/")[-1], "type": i.object_type.value} for i in items],
        }
    return {"path": path, "type": "UNKNOWN", "error": "Unsupported object type"}

def format_asset_context(asset: dict, max_chars: int = 12000) -> str:
    """Format resolved asset for LLM context injection."""
    if asset.get("error"):
        return f"[WORKSPACE ASSET ERROR: {asset['path']}]\n{asset['error']}"
    
    if asset["type"] == "DIRECTORY":
        tree = "\n".join(f"  {'📁' if i['type']=='DIRECTORY' else '📄'} {i['name']}" for i in asset["items"])
        return f"[WORKSPACE DIRECTORY: {asset['path']}]\n{tree}"
    
    content = asset["content"]
    truncated = ""
    if len(content) > max_chars:
        content = content[:max_chars]
        truncated = f"\n⚠️ TRUNCATED (showing {max_chars:,} of {asset['size']:,} chars)"
    
    return (
        f"[WORKSPACE ASSET: {asset['path']}]\n"
        f"Type: {asset['type']} | Language: {asset.get('language', 'N/A')}\n"
        f"--- Content ({asset['size']:,} chars) ---\n"
        f"{content}{truncated}\n"
        f"--- End ---"
    )
```

### Integration Points in `app.py`

| Location | Change |
|----------|--------|
| Before LLM call (~line 3431) | Detect paths in `user_input`, resolve assets, inject into `_llm_user_input` |
| `_IMAGE_KEYWORDS` area (~line 3706) | Add path detection BEFORE image keyword check (paths take priority) |
| SUPERVISOR_PROMPT | Add instruction: "When the user provides a workspace path, read and analyze the asset content provided in [WORKSPACE ASSET] blocks" |
| Error handling | Graceful fallback if path doesn't exist or SP lacks permissions |

### Sub-Tasks

| # | Task | Status | Priority | Notes |
|---|------|--------|----------|-------|
| 6.1 | Implement `detect_workspace_paths()` regex extraction | 🟢 | P1 | Done — `_WORKSPACE_PATH_RE` regex at line 31, `detect_workspace_paths()` at line 34 |
| 6.2 | Implement `resolve_workspace_asset()` via Workspace API | 🟢 | P1 | Done — REST API calls (get-status, export, list) at lines 39-100. Handles NOTEBOOK, FILE, DIRECTORY |
| 6.3 | Implement `format_asset_context()` with truncation safety | 🟢 | P1 | Done — lines 103-122. f-string backslash bug fixed 2026-07-28 |
| 6.4 | Wire into `app.py` — inject resolved content before LLM call | 🟢 | P1 | Done — inserted after line 3538, caps at 3 paths, uses DATABRICKS_HOST/TOKEN env vars |
| 6.5 | Update SUPERVISOR_PROMPT with asset analysis instructions | 🟢 | P1 | Done — Added `## LIVE WORKSPACE ASSET QUERY` section (#3 behavioral rule) + TYPE 6 engagement route |
| 6.6 | Handle DIRECTORY type — show tree + offer to drill into items | 🟢 | P2 | Done — file/folder count summary + [DRILL-DOWN] hint for LLM to suggest files |
| 6.7 | Handle permissions errors gracefully | 🟢 | P2 | Done — 403/404/timeout-specific hints + try/except wrapper in wiring code |
| 6.8 | Add `.md` file rendering (markdown preview in chat) | 🟢 | P2 | Done — detects .md extension, adds [RENDER HINT] for LLM to format inline |
| 6.9 | Multi-path support: resolve + inject all detected paths | 🟢 | P2 | Done — [MULTI-ASSET CONTEXT] hint when 2+ paths detected for comparison |
| 6.10 | Token budget guard: skip injection if total > 15K tokens | 🟢 | P2 | Done — _TOKEN_BUDGET_CHARS=60000, [BUDGET EXCEEDED] message + break |
| 6.11 | Test with real workspace paths (notebooks, SQL, .py, .md) | 🟢 | P1 | Done — confirmed working in production 2026-07-28 |
| 6.12 | Deploy and validate end-to-end | 🟢 | P1 | Done — deployment 01f18a99b5bf16cba0bc6337b3b1eb24 SUCCEEDED, user confirmed working |

### Blockers

| # | Blocker | Impact | Resolution |
|---|---------|--------|------------|
| 1 | App SP needs workspace read permissions | Cannot read assets from other users' folders | Grant SP `CAN_READ` on shared folders, or use user token passthrough |
| 2 | IP ACL may block Workspace API from app container | Same as Track 3 blocker | Whitelist app egress IP |
| 3 | Large notebooks (>100 cells) blow context window | LLM degrades with >16K injected chars | Truncation + summarization fallback |

### Cost Impact

| Component | Est. Monthly Cost | Notes |
|-----------|-------------------|-------|
| Workspace API calls | $0 | Free — no DBU cost |
| Token overhead | ~$1-3/mo | Extra input tokens for injected asset content |
| **Total** | **~$1-3/mo** | Negligible |

---

## Track 7 — Power BI Dataset Discovery (Deduplication Guard)

### Objective

Connect the NEXUS app to the Power BI REST API to retrieve the full inventory of existing datasets, reports, and dashboards. Use this inventory to prevent duplicate work — when a user asks to "build a dashboard for X" or "create a report on Y", NEXUS checks against Power BI first and redirects to the existing asset with a direct link if one already covers the use case.

### Use Cases

| # | Use Case | Example | NEXUS Behavior |
|---|----------|---------|----------------|
| 7.1 | Duplicate prevention | "Create a revenue dashboard" | Check PBI inventory → find existing "Monthly Revenue Report" → respond: "This already exists: [link]. Want to enhance it or build something different?" |
| 7.2 | Asset discovery | "What dashboards do we have for manufacturing?" | Query cached PBI inventory → return list with direct links |
| 7.3 | Gap analysis | "What metrics are NOT covered in Power BI?" | Compare PBI datasets against Gold/Platinum tables → identify uncovered domains |
| 7.4 | Migration targeting | "Which PBI reports could move to Lakeview?" | Inventory PBI reports → flag candidates by complexity, data source, refresh pattern |
| 7.5 | Ownership lookup | "Who owns the GL Cost Center report?" | Return PBI report owner, last refresh, workspace membership |
| 7.6 | Stale report detection | "Which reports haven't been viewed in 90 days?" | Cross-reference usage metrics → flag retirement candidates |

### Technical Design

```
Power BI REST API (https://api.powerbi.com/v1.0/myorg/)
├── Authentication: Azure AD Service Principal (client_credentials flow)
├── Endpoints used:
│   ├── GET /groups                          → List workspaces
│   ├── GET /groups/{id}/datasets            → List datasets per workspace
│   ├── GET /groups/{id}/reports              → List reports per workspace
│   ├── GET /groups/{id}/dashboards           → List dashboards per workspace
│   └── GET /admin/reports (admin API)        → Usage metrics, last accessed
├── Caching: Delta table `mde_dev.test_schema.pbi_asset_inventory`
│   ├── Refresh: Daily via scheduled job OR on-demand from app
│   └── Schema: workspace_name, asset_type, asset_name, dataset_id, report_id,
│            web_url, owner, last_refresh, tables_used[], description
└── Integration: LLM context injection (like Track 6 workspace assets)
```

### Authentication Approach

| Method | Pros | Cons | Recommended |
|--------|------|------|-------------|
| **Service Principal (App Registration)** | Non-interactive, automated, no user token needed | Requires PBI admin to grant SP access to workspaces | ✅ Yes — same pattern as Databricks App SP |
| User delegated (OAuth2 PKCE) | Per-user access, respects RLS | Requires interactive login, token refresh complexity | No — app runs headless |
| Master user account | Simple setup | Security risk, password rotation, MFA issues | No |

**Required Azure AD App Registration:**
```
App Name: NEXUS-PowerBI-Connector
API Permissions:
  - Power BI Service → Dataset.Read.All
  - Power BI Service → Report.Read.All  
  - Power BI Service → Dashboard.Read.All
  - Power BI Service → Workspace.Read.All
  - Power BI Service → Metadata.ViewAny (admin API for usage metrics)
Grant Type: client_credentials
Secret: stored in Databricks secret scope `nexus-pbi`
```

### Implementation

```python
import requests
from datetime import datetime, timedelta

class PowerBIConnector:
    """Connect to Power BI REST API and retrieve asset inventory."""
    
    PBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"
    PBI_ADMIN_BASE = "https://api.powerbi.com/v1.0/myorg/admin"
    TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._token_expiry = datetime.min
    
    def _get_token(self) -> str:
        """Get or refresh Azure AD access token for Power BI."""
        if self._token and datetime.now() < self._token_expiry:
            return self._token
        resp = requests.post(
            self.TOKEN_URL.format(tenant_id=self.tenant_id),
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://analysis.windows.net/powerbi/api/.default",
            },
            timeout=10,
        )
        resp.raise_for_status()
        token_data = resp.json()
        self._token = token_data["access_token"]
        self._token_expiry = datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600) - 60)
        return self._token
    
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}
    
    def list_workspaces(self) -> list:
        """List all Power BI workspaces the SP has access to."""
        resp = requests.get(f"{self.PBI_API_BASE}/groups", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json().get("value", [])
    
    def list_datasets(self, workspace_id: str) -> list:
        """List datasets in a workspace."""
        resp = requests.get(
            f"{self.PBI_API_BASE}/groups/{workspace_id}/datasets",
            headers=self._headers(), timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])
    
    def list_reports(self, workspace_id: str) -> list:
        """List reports in a workspace."""
        resp = requests.get(
            f"{self.PBI_API_BASE}/groups/{workspace_id}/reports",
            headers=self._headers(), timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])
    
    def get_full_inventory(self) -> list:
        """Scan all workspaces and build full asset inventory."""
        inventory = []
        for ws in self.list_workspaces():
            ws_id = ws["id"]
            ws_name = ws["name"]
            # Datasets
            for ds in self.list_datasets(ws_id):
                inventory.append({
                    "workspace_name": ws_name,
                    "workspace_id": ws_id,
                    "asset_type": "DATASET",
                    "asset_name": ds["name"],
                    "asset_id": ds["id"],
                    "web_url": ds.get("webUrl", ""),
                    "configured_by": ds.get("configuredBy", ""),
                    "is_refreshable": ds.get("isRefreshable", False),
                    "last_refresh": ds.get("lastRefreshTime", ""),
                })
            # Reports
            for rpt in self.list_reports(ws_id):
                inventory.append({
                    "workspace_name": ws_name,
                    "workspace_id": ws_id,
                    "asset_type": "REPORT",
                    "asset_name": rpt["name"],
                    "asset_id": rpt["id"],
                    "web_url": rpt.get("webUrl", ""),
                    "dataset_id": rpt.get("datasetId", ""),
                    "report_type": rpt.get("reportType", ""),
                })
        return inventory


def search_pbi_inventory(query: str, inventory: list, top_k: int = 5) -> list:
    """Fuzzy-match user query against PBI asset names and return top matches."""
    query_lower = query.lower()
    scored = []
    for item in inventory:
        name_lower = item["asset_name"].lower()
        # Simple keyword overlap scoring
        query_words = set(query_lower.split())
        name_words = set(name_lower.replace("_", " ").replace("-", " ").split())
        overlap = len(query_words & name_words)
        if overlap > 0 or query_lower in name_lower:
            score = overlap + (2 if query_lower in name_lower else 0)
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:top_k]]


def format_pbi_results(matches: list) -> str:
    """Format PBI matches for LLM context injection."""
    if not matches:
        return ""
    lines = ["[EXISTING POWER BI ASSETS — check before building new]"]
    for m in matches:
        url = m.get("web_url", "https://app.powerbi.com/home")
        lines.append(
            f"  \u2022 {m['asset_type']}: {m['asset_name']} "
            f"(workspace: {m['workspace_name']}) \u2192 {url}"
        )
    lines.append("[END PBI ASSETS]")
    return "\n".join(lines)
```

### Integration Points in `app.py`

| Location | Change |
|----------|--------|
| Top of file (imports) | Import `PowerBIConnector`, load credentials from env/secrets |
| Session init | Load PBI inventory from Delta cache (`mde_dev.test_schema.pbi_asset_inventory`) into `st.session_state.pbi_inventory` |
| Before LLM call (~line 3549) | If user mentions dashboards/reports/metrics → `search_pbi_inventory()` → inject `[EXISTING POWER BI ASSETS]` block into `_llm_user_input` |
| SUPERVISOR_PROMPT | Add instruction: "When [EXISTING POWER BI ASSETS] blocks appear, ALWAYS mention existing reports first with links before suggesting new builds" |
| Scheduled refresh | Daily job or `@st.cache_data(ttl=3600)` to refresh inventory from PBI API |

### Delta Cache Schema

```sql
CREATE TABLE IF NOT EXISTS mde_dev.test_schema.pbi_asset_inventory (
    workspace_name STRING,
    workspace_id STRING,
    asset_type STRING COMMENT 'DATASET | REPORT | DASHBOARD',
    asset_name STRING,
    asset_id STRING,
    web_url STRING COMMENT 'Direct Power BI link',
    configured_by STRING COMMENT 'Dataset owner / report creator',
    dataset_id STRING COMMENT 'For reports: linked dataset ID',
    report_type STRING,
    is_refreshable BOOLEAN,
    last_refresh TIMESTAMP,
    tables_used ARRAY<STRING> COMMENT 'Source tables referenced by dataset',
    description STRING,
    scan_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    _etl_load_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
USING DELTA
COMMENT 'Power BI asset inventory for NEXUS deduplication guard (Track 7)'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
```

### SUPERVISOR_PROMPT Addition

```
## POWER BI DEDUPLICATION GUARD (Phase 12 Track 7)

When the user asks to "create a dashboard", "build a report", "visualize metrics", or any request
that implies building a NEW reporting/analytics asset:
→ Check the [EXISTING POWER BI ASSETS] context block (injected automatically when matches found).
→ If a matching PBI report/dataset exists: ALWAYS mention it FIRST with the direct link.
→ Response pattern: "📊 An existing Power BI report already covers this: [Name](link). 
   Would you like to: (a) use this as-is, (b) enhance it, or (c) build something new in Lakeview?"
→ If NO match exists: proceed normally with Lakeview/notebook creation.
→ NEVER silently ignore existing PBI assets — duplicating work wastes engineering time.
This is your #4 behavioral rule.
```

### Sub-Tasks

| # | Task | Status | Priority | Notes |
|---|------|--------|----------|-------|
| 7.1 | Create Azure AD App Registration for Power BI API access | ⬜ | P0 | Requires Azure AD admin. App name: `NEXUS-PowerBI-Connector` |
| 7.2 | Store client_id + client_secret in Databricks secret scope `nexus-pbi` | ⬜ | P0 | Keys: `tenant-id`, `client-id`, `client-secret` |
| 7.3 | Grant SP access to Power BI workspaces (PBI admin portal) | ⬜ | P0 | Admin → Tenant settings → Allow SPs to use PBI APIs |
| 7.4 | Implement `PowerBIConnector` class in `pbi_connector.py` | ⬜ | P1 | Token management, workspace/dataset/report listing |
| 7.5 | Create Delta cache table `mde_dev.test_schema.pbi_asset_inventory` | ⬜ | P1 | DDL above. Run from DEV workspace (mde_dev is read-only from AI Builder) |
| 7.6 | Build inventory scan job (full refresh) | ⬜ | P1 | Scheduled daily 6AM ET or triggered from app |
| 7.7 | Implement `search_pbi_inventory()` fuzzy matching | ⬜ | P1 | Keyword overlap + substring match. Consider embedding-based search later |
| 7.8 | Wire into `app.py` — detect reporting intent, inject PBI matches | ⬜ | P1 | Same pattern as Track 6 (before LLM call, enrich `_llm_user_input`) |
| 7.9 | Update SUPERVISOR_PROMPT with deduplication guard (#4 behavioral rule) | ⬜ | P1 | See prompt addition above |
| 7.10 | Add `pbi_connector.py` to `requirements.txt` deps (if any beyond `requests`) | ⬜ | P2 | `msal` for more robust token management (optional) |
| 7.11 | Add PBI workspace filter config (include/exclude specific workspaces) | ⬜ | P2 | Not all PBI workspaces may be relevant |
| 7.12 | Build admin UI in Streamlit sidebar for manual inventory refresh | ⬜ | P2 | Button: "🔄 Refresh PBI Inventory" |
| 7.13 | Test end-to-end: user asks to build existing report → redirect with link | ⬜ | P1 | |
| 7.14 | Deploy and validate | ⬜ | P1 | |

### Blockers

| # | Blocker | Impact | Resolution |
|---|---------|--------|------------|
| 1 | Azure AD App Registration required | Cannot authenticate to PBI API without it | Azure AD admin creates app + grants API permissions |
| 2 | PBI admin must enable SP API access | Tenant-level setting blocks SP auth by default | PBI Admin → Tenant settings → "Allow service principals to use Power BI APIs" |
| 3 | App SP network access to `login.microsoftonline.com` + `api.powerbi.com` | IP ACL may block outbound HTTPS | Verify from app container; whitelist if needed |
| 4 | Delta table write requires DEV workspace | `mde_dev` is read-only from AI Builder (4337650355687191) | Run inventory scan job from DEV workspace, app reads cached Delta table |

### Cost Impact

| Component | Est. Monthly Cost | Notes |
|-----------|-------------------|-------|
| Power BI API calls | $0 | Free — included in PBI Pro/Premium license |
| Delta cache storage | ~$0.01/mo | Tiny table (~1-5K rows of metadata) |
| Token overhead | ~$0.50/mo | Small context injection per matching query |
| Scheduled scan job | ~$0.15/mo | 1 daily run, <30s on serverless |
| **Total** | **~$0.66/mo** | Negligible |

### Integration with Other Tracks

| Integration | How |
|-------------|-----|
| Track 2 (PPT/PDF) | Include PBI asset links in generated reports as "Related Existing Reports" |
| Track 3 (Live Assets) | Before creating Lakeview dashboard, check PBI for existing coverage |
| Track 5 (Image Gen) | Generate visual mockup, then note: "Similar report already exists in PBI: [link]" |
| Track 6 (Asset Query) | If user pastes PBI URL, resolve workspace/report name and show metadata |
| Qlik Migration (88-95) | Cross-reference migrated Qlik reports against PBI to avoid double-migration |

---

## Track 8 — MCP-to-Claude Integration (NEXUS as Claude Tool Server)

### Objective

Expose the NEXUS platform as a remote MCP (Model Context Protocol) server that Claude Desktop and Claude.ai can connect to directly. This turns Claude into a NEXUS client — giving Claude access to all 132 agents, live SQL execution, workspace asset reading, image generation, and the full Hologic data platform without switching apps.

### Current State (Already Built)

The MCP server infrastructure is **already deployed** in `mcp_server.py`:

| Component | Status | Location |
|-----------|--------|----------|
| FastMCP server | 🟢 Built | `mcp_server.py` |
| Streamable HTTP transport | 🟢 Mounted | `main.py` → `/mcp` route |
| 8 MCP tools | 🟢 Defined | route_request, list_agents, invoke_agent, query_sql, get_agent_health, classify_intent, search_memory, get_platform_status |
| Public URL | 🟢 Live | `https://hologic-ai-agents-6617965257274108.8.azure.databricksapps.com/mcp` |
| Auth (bearer token) | 🟡 Partial | App uses internal SP token; no external auth layer for Claude yet |

### What's Needed for Claude Integration

```
Claude Desktop / Claude.ai
    │
    │  MCP (Streamable HTTP)
    │  Authorization: Bearer <token>
    ▼
https://hologic-ai-agents-....azure.databricksapps.com/mcp
    │
    ├── route_request()      → Full Meta Supervisor reasoning (132 agents)
    ├── query_sql()          → Live SQL against 5,902 tables
    ├── list_agents()        → Registry lookup by layer/workspace/keyword
    ├── invoke_agent()       → Direct agent trigger via Jobs API
    ├── get_agent_health()   → Health metrics from agent_call_log
    ├── classify_intent()    → Zero-LLM workspace + agent classification
    ├── search_memory()      → Semantic memory recall
    ├── get_platform_status()→ Live platform summary
    ├── read_workspace_asset() → (NEW) Read notebook/file content by path
    ├── generate_visual()    → (NEW) Generate branded diagrams/mockups
    └── search_pbi_reports() → (NEW, Track 7) Search Power BI inventory
```

### Use Cases

| # | Use Case | Example in Claude | What Happens |
|---|----------|-------------------|---------------|
| 8.1 | Ask Claude about job failures | "Use NEXUS to check last night's job failures" | Claude calls `route_request` → gets full triage response |
| 8.2 | Run SQL from Claude | "Query the Oracle EBS staging table for AP invoices" | Claude calls `query_sql` → returns live results |
| 8.3 | Check platform costs | "What's our Databricks spend this month?" | Claude calls `query_sql` with billing query → cost breakdown |
| 8.4 | Invoke specific agent | "Run the morning briefing agent" | Claude calls `invoke_agent("39_morning_briefing_agent")` |
| 8.5 | Read workspace code | "What does the fact_wip_value_mfg notebook do?" | Claude calls `read_workspace_asset` → analyzes code |
| 8.6 | Architecture guidance | "Design a medallion pipeline for HCM data" | Claude calls `route_request` → Agent 06 + 15 + 37 respond |
| 8.7 | Visual generation | "Generate an ERD for the sales star schema" | Claude calls `generate_visual` → returns PNG as base64 |
| 8.8 | Multi-tool workflow | "Check if a revenue dashboard exists in PBI, if not create a Lakeview one" | Claude chains `search_pbi_reports` → `route_request` |

### Claude Desktop Configuration

```json
// ~/.claude/claude_desktop_config.json (macOS/Linux)
// %APPDATA%\Claude\claude_desktop_config.json (Windows)
{
  "mcpServers": {
    "nexus": {
      "transport": "streamable-http",
      "url": "https://hologic-ai-agents-6617965257274108.8.azure.databricksapps.com/mcp",
      "headers": {
        "Authorization": "Bearer ${NEXUS_MCP_TOKEN}"
      },
      "description": "Hologic NEXUS Multi-Agent Platform — 132 AI agents for data engineering, architecture, and operations on Databricks"
    }
  }
}
```

### Claude.ai Integration (Remote MCP Servers)

Claude.ai supports remote MCP servers via the Integrations panel (Settings → Integrations):

1. Navigate to: https://claude.ai/settings/integrations
2. Click "Add Integration" → "MCP Server"
3. Enter:
   - Name: `NEXUS Platform`
   - URL: `https://hologic-ai-agents-6617965257274108.8.azure.databricksapps.com/mcp`
   - Auth: Bearer token
4. Claude.ai will discover tools automatically via MCP `tools/list`

### Authentication Design

| Approach | Mechanism | Pros | Cons | Recommended |
|----------|-----------|------|------|-------------|
| **API Key (header)** | `Authorization: Bearer <static-key>` stored in app secrets | Simple, Claude Desktop supports it natively | Key rotation is manual; single key = no per-user audit | ✅ Phase 1 (MVP) |
| **Databricks PAT passthrough** | User's own PAT in header | Per-user identity, full audit trail, respects UC permissions | Each user needs their own PAT configured in Claude | ✅ Phase 2 (production) |
| **OAuth2 (Entra ID)** | PKCE flow via Azure AD app | Enterprise SSO, token refresh, MFA | Complex setup, requires redirect URI handling in MCP | Phase 3 (enterprise) |

**Phase 1 (MVP) Implementation:**
```python
# In main.py — add auth middleware for /mcp route
import hashlib, hmac

_MCP_API_KEYS = set(os.environ.get("MCP_API_KEYS", "").split(","))  # comma-separated valid keys

async def mcp_auth_middleware(request: Request, call_next):
    """Validate bearer token for MCP endpoints."""
    if request.url.path.startswith("/mcp"):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "Missing Authorization header"}, status_code=401)
        token = auth[7:]
        if token not in _MCP_API_KEYS:
            return JSONResponse({"error": "Invalid API key"}, status_code=403)
    return await call_next(request)
```

### New Tools to Add (extend `mcp_server.py`)

| Tool | Purpose | Inputs | Notes |
|------|---------|--------|-------|
| `read_workspace_asset` | Read any workspace path (reuses Track 6) | `path: str` | Calls `resolve_workspace_asset()` from app.py |
| `generate_visual` | Generate branded diagram/mockup (reuses Track 5) | `prompt: str, type: str` | Returns base64 PNG + description |
| `search_pbi_reports` | Search Power BI inventory (reuses Track 7) | `query: str, top_k: int` | Returns matching reports with links |
| `list_medallion_tables` | Browse catalog structure | `schema: str, pattern: str` | SHOW TABLES + metadata |
| `get_cost_summary` | Quick cost rollup (no custom SQL needed) | `days: int` | Pre-built billing query |
| `run_data_quality_check` | DQ profiling on a table | `table: str` | Triggers Agent 16 |

### Sub-Tasks

| # | Task | Status | Priority | Notes |
|---|------|--------|----------|-------|
| 8.1 | Add auth middleware to `/mcp` route in `main.py` | ⬜ | P0 | Bearer token validation, reject unauthenticated requests |
| 8.2 | Generate MCP API key, store in secret scope `nexus-app-secrets` key `mcp-api-key` | ⬜ | P0 | Use `openssl rand -hex 32` for strong key |
| 8.3 | Add `MCP_API_KEYS` env var to `app.yaml` | ⬜ | P0 | Reference: `valueFrom: secrets/nexus-app-secrets/mcp-api-key` |
| 8.4 | Test MCP endpoint from `curl` with bearer auth | ⬜ | P1 | `curl -H "Authorization: Bearer <key>" https://<app-url>/mcp` |
| 8.5 | Add `read_workspace_asset` tool to `mcp_server.py` | ⬜ | P1 | Import and wrap Track 6 functions |
| 8.6 | Add `generate_visual` tool to `mcp_server.py` | ⬜ | P1 | Import from `image_generator.py`, return base64 PNG |
| 8.7 | Add `search_pbi_reports` tool to `mcp_server.py` | ⬜ | P2 | Depends on Track 7 completion |
| 8.8 | Add `list_medallion_tables` tool | ⬜ | P2 | Quick catalog browse without custom SQL |
| 8.9 | Add `get_cost_summary` tool | ⬜ | P2 | Pre-built billing query (last N days) |
| 8.10 | Configure Claude Desktop `claude_desktop_config.json` and test | ⬜ | P1 | Verify all 8+ tools appear in Claude's tool list |
| 8.11 | Configure Claude.ai remote MCP integration and test | ⬜ | P1 | Settings → Integrations → Add MCP Server |
| 8.12 | Add rate limiting to MCP endpoint (prevent runaway tool calls) | ⬜ | P2 | Max 30 calls/min per API key |
| 8.13 | Add MCP request logging to `agent_call_log` Delta table | ⬜ | P2 | Source: "mcp", track tool name + tokens + caller |
| 8.14 | Document tool descriptions for Claude context (improve tool selection) | ⬜ | P2 | Rich descriptions help Claude pick the right tool |
| 8.15 | Add OAuth2/PAT passthrough for per-user identity (Phase 2) | ⬜ | P3 | Entra ID app registration, PKCE flow |
| 8.16 | Test multi-tool chaining: Claude uses 3+ NEXUS tools in one conversation | ⬜ | P1 | |
| 8.17 | Deploy and validate end-to-end | ⬜ | P1 | |

### Network & Security Considerations

| Concern | Detail | Mitigation |
|---------|--------|------------|
| App URL publicly accessible | `*.azure.databricksapps.com` is internet-facing | Auth middleware (Task 8.1) blocks unauthenticated access |
| API key exposure | Key stored on user's machine in `claude_desktop_config.json` | Use environment variable reference `${NEXUS_MCP_TOKEN}`, rotate quarterly |
| Token forwarding to Databricks APIs | MCP tools call Workspace API, SQL API, Jobs API | App SP token has scoped permissions (cannot escalate) |
| Rate abuse from Claude | Claude may call tools aggressively in agentic mode | Rate limiter (Task 8.12) + daily cost cap via Phase 8 governance |
| Data exfiltration | SQL results flow through Claude's context | Governance: Phase 8 policies + PII stream rule blocks sensitive data |

### Claude Prompt Engineering Tips

For best results when using NEXUS tools from Claude, prime with:
```
You have access to the Hologic NEXUS platform via MCP tools. Use them to:
- route_request: For complex questions needing multi-agent reasoning
- query_sql: For direct data queries (use mde_dev catalog, join to list_prices for costs)
- list_agents: To discover which agents handle specific domains
- classify_intent: For quick routing without LLM cost
- invoke_agent: When you know exactly which specialist to call

Prefer query_sql for data questions (fast, cheap) and route_request for architecture/strategy (comprehensive, uses LLM).
```

### Cost Impact

| Component | Est. Monthly Cost | Notes |
|-----------|-------------------|-------|
| MCP endpoint (no additional infra) | $0 | Runs on existing app compute (MEDIUM) |
| LLM calls via route_request | ~$5-15/mo | Depends on Claude usage frequency |
| SQL calls via query_sql | ~$1-3/mo | Serverless SQL at $0.70/DBU, minimal per-query |
| Jobs API calls via invoke_agent | ~$2-5/mo | Serverless Jobs at $0.45/DBU, ~5min/run |
| **Total** | **~$8-23/mo** | Scales with usage; governance caps prevent runaway |

### Integration with Other Tracks

| Integration | How |
|-------------|-----|
| Track 5 (Image Gen) | `generate_visual` tool returns base64 PNG → Claude renders inline |
| Track 6 (Asset Query) | `read_workspace_asset` tool gives Claude access to any workspace file |
| Track 7 (PBI Discovery) | `search_pbi_reports` tool lets Claude check PBI before suggesting new builds |
| Phase 8 (Governance) | All MCP tool calls pass through `policy_check()` → budget/rate/risk enforcement |
| Phase 9 (Memory) | `search_memory` tool gives Claude access to NEXUS semantic memory bank |

---

## Dependencies & Blockers

| # | Blocker | Impact | Resolution Path |
|---|---------|--------|----------------|
| 1 | IP ACL blocks app → workspace API | Track 3 entirely blocked | Whitelist app egress IP or use serverless proxy |
| 2 | App SP permissions | Track 3 blocked until SP has CAN_MANAGE | Admin grants via workspace admin console |
| 3 | AI Gateway image payload limits | Track 1 may have size constraints | Test with varying image sizes, check docs |
| 4 | Phase 11 incomplete | Not a hard blocker but Track 3 uses agent registry | Can proceed in parallel |

---

## Cost Estimates

| Track | Component | Est. Monthly Cost | Notes |
|-------|-----------|-------------------|-------|
| Track 1 | Image tokens (vision) | ~$5-15/mo | ~1,600 tokens/image × usage frequency |
| Track 2 | Doc generation compute | ~$0 incremental | Runs in app container, no DBU |
| Track 3 | Asset creation API calls | ~$0 incremental | API calls are free, only storage matters |
| Track 7 | PBI API + Delta cache + scan job | ~$0.66/mo | API calls free, minimal storage |
| Track 8 | MCP endpoint LLM + SQL + Jobs calls | ~$8-23/mo | Scales with Claude usage frequency |
| **Total** | | **~$14-39/mo incremental** | Well within $35-60/mo platform budget |

---

## Success Criteria

- [ ] User can upload an image and receive analysis in chat response (Track 1)
- [ ] User can request a PPT/PDF and download it from the chat interface (Track 2)
- [ ] User can say "create a dashboard for X" and get a live Lakeview dashboard with a clickable link (Track 3)
- [ ] User can say "create a notebook for Y" and get a live notebook with pre-filled code (Track 3)
- [ ] User can say "set up a Genie space for Z tables" and get a working Genie space (Track 3)
- [ ] All creations are tracked in governance logs (Phase 8 integration)
- [ ] IP ACL blocker resolved or workaround implemented (Track 3 prerequisite)
- [ ] Silent truncation eliminated — `finish_reason=="length"` auto-retries (Track 4)
- [ ] User can say "show me a mockup of X dashboard" and get a colorful PNG rendered inline (Track 5)
- [ ] User can say "draw the architecture for Y" and get a professional diagram (Track 5)
- [ ] Generated images can embed into PPTX/PDF output (Track 5 + Track 2 integration)
- [ ] User asks to "create a revenue dashboard" and NEXUS responds with existing PBI report link first (Track 7)
- [ ] User asks "what reports do we have for manufacturing?" and gets a list with direct PBI links (Track 7)
- [ ] PBI inventory refreshes daily and deduplication guard fires before any new build suggestion (Track 7)
- [ ] Claude Desktop can connect to NEXUS MCP endpoint and discover all tools (Track 8)
- [ ] Claude can call `route_request` and get full multi-agent response (Track 8)
- [ ] Claude can call `query_sql` and get live data from mde_dev catalog (Track 8)
- [ ] MCP endpoint rejects unauthenticated requests with 401 (Track 8)

---

## Checklist Sync (from CHECKLIST.md)

When implementing Phase 12:

- [ ] Update `app.py` — new endpoints/handlers for upload, doc gen, asset creation
- [ ] Update `requirements.txt` — add `python-pptx`, PDF library, image processing
- [ ] Update `AGENTS.md` — document new app capabilities in Environment Notes
- [ ] Update `.assistant_instructions.md` — note Phase 12 status
- [ ] If new tools added to app: register in TOOL_REGISTRY
- [ ] If new agent output types: update `save_agent_output()` schema
- [ ] Test from app deployment (not just local)

---

## Reference

| Asset | ID / Path |
|-------|-----------|
| `hologic-ai-agents` app | Databricks App (DEV workspace) |
| `app.py` | `/5 - AI Multi Agents/5 - Agent Chat App/app.py` (File ID: 1041804398715760) |
| `requirements.txt` | `/5 - AI Multi Agents/5 - Agent Chat App/requirements.txt` (File ID: 1041804398715761) |
| `sql_tools.py` | `/5 - AI Multi Agents/5 - Agent Chat App/sql_tools.py` (File ID: 4057529505252766) |
| `image_generator.py` | `/5 - AI Multi Agents/5 - Agent Chat App/image_generator.py` (File ID: 2376352189321060) |
| PHASE_11.md | `/5 - AI Multi Agents/0 - Project Docs/PHASE_11.md` |
| CHECKLIST.md | `/5 - AI Multi Agents/0 - Project Docs/CHECKLIST.md` |

---

## Implementation Log

| Date | Change | Details |
|------|--------|---------|
| 2026-07-27 | Track 5 core implementation | Created `image_generator.py` (7 visual types), added to `requirements.txt` (matplotlib, plotly, kaleido, Pillow), integrated into `app.py` lines 3702-3750 |
| 2026-07-27 | Bug fix: `use_container_width` | Streamlit in container doesn't support `use_container_width` on `st.image()`. Fixed to `use_column_width=True`. Buttons/forms remain `use_container_width`. |
| 2026-07-28 | Image history re-render | Added `image_key` to `msg_record` + history loop re-renders stored images from `st.session_state.generated_images` with download button |
| 2026-07-28 | System prompt visual capability | Added `## ⚡ CRITICAL: VISUAL GENERATION IS A PLATFORM CAPABILITY` (#2 rule) + TYPE 5 engagement route to SUPERVISOR_PROMPT. Without this, LLM classifies visual requests as out-of-scope |
| 2026-07-29 | Track 9 cache implementation verified | `query_cache.py` fully implemented: `QueryCache` class (512-entry, tiered TTL), `classify_tier()` (4 tiers via regex), `cache_key()` (xxHash64), `execute_with_cache()` transparent wrapper. Process-level singleton, not per-user. |
| 2026-07-29 | Track 9 prompt integration | Added `## SESSION CACHE AWARENESS` section to SUPERVISOR_PROMPT (after LIVE SQL TOOL rules). Instructs LLM to: reuse prior tool results, use injected medallion counts, skip redundant chained checks. Saves ~500-2000 tokens/avoided call. |

### `image_generator.py` — Module Reference

| Export | Signature | Description |
|--------|-----------|-------------|
| `classify_visual_type(prompt)` | `str → str` | Returns one of: `dashboard_mockup`, `kpi_card`, `architecture`, `erd`, `flowchart`, `timeline`, `chart` |
| `generate_image(prompt, spec=None)` | `(str, Optional[dict]) → Tuple[bytes, str, str]` | Main entry point. Returns `(png_bytes, visual_type, description)`. Routes to type-specific renderer. |
| `image_to_base64(img_bytes)` | `bytes → str` | Base64 encode for embedding |
| `image_to_data_uri(img_bytes)` | `bytes → str` | `data:image/png;base64,...` URI |
| `HologicColors` | class | `DARK_BLUE=#1B2A4A`, `RED=#E74C3C`, `GREEN=#27AE60`, `LIGHT_GRAY=#F8F9FA`, `CHART_PALETTE` |

### `app.py` Integration Points

| Location | Purpose |
|----------|---------|
| Line ~3706 | `_IMAGE_KEYWORDS` list — triggers `_should_generate_image` |
| Line ~3714 | Keyword check: `any(kw in user_input.lower() for kw in _IMAGE_KEYWORDS)` |
| Line ~3728 | `generate_image(user_input, _img_spec)` call |
| Line ~3735 | Store in `st.session_state.generated_images[_img_key]` |
| Line ~3740 | `st.image(_img_bytes, caption=_img_desc, use_column_width=True)` |
| Line ~3313 (history) | Re-render: `msg.get("image_key")` → retrieve → `st.image()` + download |
| SUPERVISOR_PROMPT | `## ⚡ CRITICAL: VISUAL GENERATION IS A PLATFORM CAPABILITY — NEVER REJECT` |

---

*Created: 2026-07-27. Last updated: 2026-07-29.*

---

## Track 9 — Query Result Caching (Token Optimization)

### Objective

Reduce live query execution and token consumption by caching repeated query results, schema/DDL lookups, and formatted context strings in session memory. Currently every user question triggers fresh SQL execution — even when the same metadata or data was fetched seconds earlier.

### Problem Statement

| Issue | Impact |
|-------|--------|
| Schema/DDL lookups re-executed every turn | ~2,000-4,000 tokens wasted per turn on repeated catalog scans |
| Identical data queries run within same session | Unnecessary SQL Warehouse DBU burn + latency |
| Formatted context strings re-serialized per call | Redundant LLM input tokens on unchanging metadata |
| No cache invalidation awareness | N/A currently — no cache exists |

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                SESSION CACHE LAYER                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │ Cache Key    │    │ Cache Store  │    │ TTL       │  │
│  │ (xxHash64)   │───▶│ (dict/Delta) │───▶│ Manager   │  │
│  │              │    │              │    │           │  │
│  └──────────────┘    └──────────────┘    └───────────┘  │
│                                                          │
│  Tier 1: Schema/DDL    → 6hr TTL (rarely changes)       │
│  Tier 2: Query Results → 15-30min TTL (data freshness)  │
│  Tier 3: Context Strings → session-scoped (no TTL)      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Implementation Options

| Option | Mechanism | Persistence | Pros | Cons |
|--------|-----------|-------------|------|------|
| A | In-process `functools.lru_cache` | App compute lifetime | Zero infra, instant | Lost on redeploy |
| B | Session-scoped dict + xxHash64 keys + TTL | App process memory | Configurable TTL, lightweight | Lost on redeploy |
| C | Delta-backed cache (`mde_dev.test_schema.app_query_cache`) | Survives restarts | Persistent, auditable | Extra write cost |

**Recommended:** Option B (session dict) for hot path + Option C (Delta) for expensive schema scans only. Mirrors proven `catalog_context_cache` pattern from `00_agent_config` Cell 8.

### Cache Key Strategy

```python
import xxhash, time

def cache_key(sql: str, tier: str = "query") -> str:
    """Generate cache key using xxHash64 (consistent with NEXUS hash standard)."""
    return f"{tier}:{xxhash.xxh64(sql.encode()).hexdigest()}"

def query_with_cache(sql: str, ttl_seconds: int = 1800) -> dict:
    key = cache_key(sql)
    if key in _cache and time.time() < _cache[key]["expires"]:
        return _cache[key]["result"]  # HIT — zero tokens, zero DBU
    result = execute_sql(sql)
    _cache[key] = {"result": result, "expires": time.time() + ttl_seconds}
    return result
```

### TTL Configuration

| Cache Tier | TTL | Rationale |
|------------|-----|----------|
| Schema/DDL (DESCRIBE, SHOW COLUMNS) | 6 hours | Table schemas rarely change intra-day |
| Metadata (table counts, list_prices) | 1 hour | Moderate freshness |
| Live data queries | 15-30 min | Balance freshness vs. cost |
| Formatted context strings | Session lifetime | Only changes if underlying data changes |

### Estimated Token Savings

| Scenario | Without Cache | With Cache | Savings |
|----------|--------------|------------|--------|
| 10-turn session, same tables | ~40,000 tokens (DDL × 10) | ~4,000 tokens (DDL × 1) | **90%** |
| Repeated cost queries | ~8,000 tokens/query × N | ~8,000 tokens × 1 | **N-1 × 8K saved** |
| Context string re-serialization | ~3,000 tokens/turn | ~3,000 tokens × 1 | **60-70%** overall |

### Sub-Tasks

| # | Task | Status | Notes |
|---|------|--------|-------|
| 9.1 | Add `_session_cache` dict + TTL logic to `app.py` | 🟢 | Done — `QueryCache` class in `query_cache.py` (module-level singleton, 512-entry dict, TTL per tier). Process-scoped, shared across all users. |
| 9.2 | Wrap `execute_sql()` / `sql_tools.py` with cache-aware layer | 🟢 | Done — `cached_execute_sql_statement()` in app.py line 1056. Wraps `execute_sql_statement()` transparently via `execute_with_cache()`. Falls back to bare execution on error. |
| 9.3 | Add cache tier classification (DDL vs. data vs. context) | 🟢 | Done — `classify_tier()` in `query_cache.py` lines 78-103. Compiled regex patterns classify: SCHEMA (DESCRIBE/SHOW/INFO_SCHEMA → 6hr), METADATA (COUNT/list_prices → 1hr), DATA (SELECT → 30min), NOCACHE (DML/volatile). |
| 9.4 | Add xxHash64 key generation (`xxhash` already in env) | 🟢 | Done — `cache_key()` in `query_cache.py` lines 110-134. Normalizes SQL (collapse whitespace, lowercase), hashes with xxh64, format: `tier:hexdigest`. MD5 fallback if xxhash unavailable. |
| 9.5 | Add cache hit/miss logging to `log_agent_call()` | 🟡 | Partial — `_stats` dict tracks hits/misses/evictions/bypasses internally. Not yet wired to `agent_call_log` Delta table. |
| 9.6 | Add manual cache invalidation (admin command) | 🟢 | Done — `invalidate_cache(pattern, tier)` + `reset_cache()` exported from `query_cache.py`. Supports pattern-based and tier-based invalidation. |
| 9.7 | Optional: Delta-backed persistence for Tier 1 | ⬜ | Not yet — current impl is in-process only (lost on redeploy). May not be needed given 6hr TTL fills within minutes. |
| 9.8 | Add cache stats to app sidebar (hit rate, size, age) | 🟡 | `cache_stats()` function exists and returns {hits, misses, hit_rate, entries, tiers}. Not yet rendered in sidebar UI. |
| 9.9 | Test: verify stale data doesn't surface after DDL changes | ⬜ | Edge case: schema change mid-session. Mitigation: `invalidate_cache(tier="schema")` after DML detected. |
| 9.10 | Integrate with MCP access tier (Track 8) — cache per user role | ⬜ | Cache is process-level (not per-user). Keys are SQL-content-based so different user queries get separate entries, but no user isolation on eviction. Enhancement: add user email to `cache_key()` input. |
| 9.11 | Add SESSION CACHE AWARENESS instruction to SUPERVISOR_PROMPT | 🟢 | Done 2026-07-29 — Instructs LLM to reuse prior tool results, reference medallion counts from context, skip redundant calls. Saves ~500-2000 tokens per avoided round-trip. |

### Integration with Other Tracks

| Integration | How |
|-------------|-----|
| Track 4 (Token Hardening) | Cached results bypass token budget pressure — fewer input tokens per turn |
| Track 8 (MCP) | MCP callers benefit from same cache; role-scoped cache prevents data leakage |
| Phase 9 (Memory) | Complements `catalog_context_cache` — memory = cross-session, this = intra-session |
| Phase 10 (Skill Fabric) | Skills inject static knowledge; cache handles dynamic query results |

### Cost Impact

| Component | Current Cost (no cache) | With Cache | Savings |
|-----------|------------------------|------------|---------|
| SQL Warehouse DBU (repeated queries) | ~$5-10/mo | ~$2-4/mo | 50-60% |
| LLM tokens (repeated context) | ~$15-25/mo | ~$5-10/mo | 60-70% |
| **Total** | **~$20-35/mo** | **~$7-14/mo** | **~$13-21/mo saved** |

---

## Track 10 — Qlik-to-Power BI In-House Transpiler

### Objective

Build an in-house equivalent of PortBI's Qlik Sense→Power BI migration accelerator — entirely Databricks-native. Combines deterministic expression rewriting (high-confidence patterns) with LLM-powered transpilation (complex Set Analysis, variables, conditional logic) and automated Power BI semantic model + report generation.

### Rationale

- PortBI charges SaaS fees and requires Azure Marketplace procurement (EA admin approval)
- In-house version connects directly to `mde_dev` Delta tables — validates Qlik load scripts map to real source tables
- Extends existing agents 88-95 with the two missing capability layers: expression transpilation + PBIX output generation
- Full IP ownership; integrates with NEXUS governance, memory, and cost tracking

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                 QLIK → POWER BI TRANSPILER PIPELINE                    │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────────┐   │
│  │ QVF/QVW     │    │ Expression       │    │ PBIX Generator     │   │
│  │ Parser      │───▶│ Transpiler       │───▶│ (Model + Report)   │   │
│  │ (Agent 89)  │    │ (Agent 96/89+)   │    │ (App Endpoint)     │   │
│  └─────────────┘    └──────────────────┘    └────────────────────┘   │
│        │                     │                        │              │
│        ▼                     ▼                        ▼              │
│  Delta: qlik_         Delta: expression_       .pbix download /     │
│  parsed_artifacts     mapping_validated        UC Volume output      │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ Validation Layer: Compare Qlik expression output vs DAX output  │ │
│  │ against sample data (Agent 95)                                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Capability 10A — Expression Mapping (Deterministic Rules + LLM Transpiler)

| Aspect | Detail |
|--------|--------|
| Owner | New agent 96 (`96_qlik_expression_transpiler_agent`) OR extend Agent 89 |
| Approach | Two-tier: (1) Rule-based rewriting for deterministic patterns (Sum, Count, If, Date, Text, Aggr → DAX equivalents), (2) LLM fallback for complex Set Analysis, nested Aggr, dollar-sign expansion, variable chains |
| LLM model | `databricks-claude-sonnet-4-6` (STANDARD tier) with few-shot prompt bank |
| Input | Qlik expressions from `mde_dev.test_schema.qlik_parsed_expressions` (populated by Agent 92) |
| Output | DAX expressions + confidence score (DETERMINISTIC=1.0, LLM_HIGH≥0.9, LLM_MEDIUM≥0.7, LLM_LOW<0.7) |
| Validation | Side-by-side eval: execute Qlik expression on sample QVD data vs. DAX on equivalent Delta table |
| Storage | `mde_dev.test_schema.qlik_to_dax_mapping` (source_expr, dax_expr, method, confidence, validated) |
| Known hard patterns | Set Analysis with exclusions `{<Year={$(vCurrentYear)}>}`, Aggr() with multiple dims, Total qualifier, Above/Below/RangeSum |
| Estimated coverage | Rule-based: ~60-70% of expressions; LLM: remaining 30-40% |

#### Sub-Tasks

| # | Task | Status | Notes |
|---|------|--------|-------|
| 10A.1 | Build deterministic rule engine (Qlik→DAX pattern map) | ⬜ | Start with Procurement Analytics expressions as training set |
| 10A.2 | Create few-shot prompt bank for LLM transpilation | ⬜ | 20-30 validated Qlik→DAX pairs covering Set Analysis, Aggr, variables |
| 10A.3 | Build confidence scoring module | ⬜ | AST parse success = DETERMINISTIC; LLM self-rating + heuristics |
| 10A.4 | Create `qlik_to_dax_mapping` Delta table schema | ⬜ | In `mde_dev.test_schema` |
| 10A.5 | Wire to Agent 92 output (parsed expressions) as input | ⬜ | Agent 92 already extracts Set Analysis/vars |
| 10A.6 | Build validation harness (Qlik eval vs DAX eval) | ⬜ | Sample data comparison on Procurement Analytics pilot |
| 10A.7 | Create/extend agent notebook (96 or 89) | ⬜ | Decision: new agent 96 preferred (SRP) |
| 10A.8 | Register in `QLIK_ARTIFACT_MAP` in Agent 88 | ⬜ | Add transpiler coordination to orchestrator |
| 10A.9 | Test on full Procurement Analytics expression set | ⬜ | Target: ≥85% automated conversion with ≥0.9 confidence |
| 10A.10 | Benchmark vs PortBI (if trial available) | ⬜ | Compare accuracy, coverage, speed |

### Capability 10B — Model Generation (TMSL/Report JSON Builder)

| Aspect | Detail |
|--------|--------|
| Owner | New agent 97 (`97_powerbi_model_generator_agent`) OR App endpoint in `hologic-ai-agents` |
| Approach | Generate complete Power BI artifacts: (1) Tabular Model (TMSL/TMDL) with tables, relationships, measures, (2) Report Layout JSON with pages, visuals, filters |
| Input | Kimball star schema from Agent 91 + DAX measures from 10A + UI layout from Agent 93 |
| Output format | `.pbix` file (ZIP containing DataModelSchema + Report/Layout JSON) |
| Connection mode | Import mode (Delta → Parquet snapshot) OR DirectQuery via Databricks SQL connector |
| Target | Power BI Service deployment via REST API OR downloadable .pbix |
| Storage | `/Volumes/mde_dev/test_schema/generated_pbix/` OR app download endpoint |
| Constraints | PBIX internal format is undocumented but reverse-engineered; consider Tabular Editor CLI as alternative output path |

#### Sub-Tasks

| # | Task | Status | Notes |
|---|------|--------|-------|
| 10B.1 | Reverse-engineer PBIX internal structure (DataModelSchema, Report/Layout) | ⬜ | Use existing .pbix from team as reference; document JSON schema |
| 10B.2 | Build TMSL/TMDL generator from Kimball model (Agent 91 output) | ⬜ | Tables, columns, relationships, hierarchies |
| 10B.3 | Build DAX measures injector (from 10A output) | ⬜ | Insert validated DAX into model measures collection |
| 10B.4 | Build Report Layout JSON generator (from Agent 93 UI mapping) | ⬜ | Pages, visuals (bar/line/table/card), filters, slicers |
| 10B.5 | Implement .pbix ZIP assembly | ⬜ | Python `zipfile` — assemble DataModelSchema + Report + metadata |
| 10B.6 | Add DirectQuery connection string generation (Databricks SQL endpoint) | ⬜ | Alternative to Import mode — live connection to Delta |
| 10B.7 | Build download endpoint in `hologic-ai-agents` app | ⬜ | `/api/generate-pbix` → returns .pbix file for download |
| 10B.8 | Optional: Power BI REST API deployment (publish to workspace) | ⬜ | Requires Power BI Service Principal + API permissions |
| 10B.9 | Test with Procurement Analytics pilot (end-to-end) | ⬜ | QVF → parse → transpile → model → .pbix → validate in PBI Desktop |
| 10B.10 | Create/extend agent notebook (97 or App endpoint) | ⬜ | Decision: App endpoint preferred for download UX |

### Integration with Existing Agents

| Agent | Provides | Consumes |
|-------|----------|----------|
| 88 (Orchestrator) | Migration wave plan, progress tracking | Transpiler status, model gen completion |
| 89 (QVD Extraction) | Parsed QVD metadata, Delta table mappings | — |
| 91 (Data Model) | Kimball star schema (facts, dims, relationships) | — |
| 92 (Expression) | Parsed Qlik expressions, variables, Set Analysis | Validated DAX from 10A |
| 93 (UI Migration) | Visual layout mapping (chart types, positions) | Report JSON for 10B |
| 95 (Validation) | Validation framework | Expression comparison results |

### Cost Estimate

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| LLM transpilation (Sonnet 4) | ~$5-15/mo | ~500-1500 expressions × ~2K tokens each |
| Validation queries (SQL Warehouse) | ~$2-5/mo | Sample data comparisons |
| Storage (Delta + Volume) | <$1/mo | Mapping tables + generated .pbix files |
| **Total** | **~$8-21/mo** | vs. PortBI SaaS license (unknown $/mo) |

### Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Expression conversion coverage | ≥85% automated | Expressions successfully transpiled / total |
| Conversion accuracy (validated) | ≥95% match | DAX output matches Qlik output on sample data |
| End-to-end time (per app) | <5 minutes | QVF upload → .pbix download |
| Manual intervention rate | <15% | Expressions requiring human review |
| PortBI parity | ≥70% feature match | Expression types handled vs. PortBI claims |

### Capability 10C — Power BI Template Deployment via REST API (.pbit + Service Instantiation)

| Aspect | Detail |
|--------|--------|
| Owner | Agent 97 (`97_powerbi_model_generator_agent`) OR new Agent 98 (`98_powerbi_deployment_agent`) |
| Rationale | **Cannot generate raw .pbix from scratch** — the file format is a proprietary Microsoft package containing compressed layouts, security bindings, and an encrypted data model. However, CAN achieve programmatic Power BI generation via .pbit template blueprints + REST API. |
| Approach | (1) Create parameterized .pbit templates (Power BI Template files) with placeholders for connection strings, parameters, and dataset bindings, (2) Upload via Power BI REST API, (3) Inject parameters dynamically (Databricks SQL endpoint, catalog, schema), (4) Let PBI Service instantiate as a full report |
| Python equivalent of | `MicrosoftPowerBIMgmt` PowerShell module — all operations available via `requests` + Entra ID OAuth |
| Authentication | Entra ID Service Principal with Power BI API permissions (`Dataset.ReadWrite.All`, `Workspace.ReadWrite.All`, `Report.ReadWrite.All`) |
| Token exchange | App SP → Entra ID token (`https://analysis.windows.net/powerbi/api`) — handled externally since Databricks Apps OAuth scopes don't cover Power BI API |
| Connection mode | DirectQuery to Databricks SQL Warehouse (preferred) OR Import with scheduled refresh |
| Template storage | `/Volumes/mde_dev/test_schema/powerbi_templates/` (.pbit files per domain) |
| Deployed report location | Power BI Service workspace (configurable per environment: DEV/UAT/PRD) |

#### Key API Endpoints (Python `requests` equivalents of MicrosoftPowerBIMgmt cmdlets)

| PowerShell Cmdlet | REST API Equivalent | Python Pattern |
|-------------------|--------------------|-----------------|
| `New-PowerBIReport` (from .pbix) | `POST /groups/{workspace}/imports` | Upload .pbit, PBI Service instantiates |
| `Set-PowerBIDatasetParameter` | `POST /datasets/{id}/Default.UpdateParameters` | Inject Databricks SQL endpoint, catalog, schema |
| `Invoke-PowerBIRestMethod` (refresh) | `POST /datasets/{id}/refreshes` | Trigger initial data load after param injection |
| `New-PowerBIWorkspace` | `POST /groups` | Create target workspace programmatically |
| `Add-PowerBIWorkspaceUser` | `POST /groups/{id}/users` | Grant access to report consumers |
| `Set-PowerBIDatasetDatasource` | `POST /datasets/{id}/Default.SetAllConnections` | Rebind to different SQL Warehouse (env promotion) |
| `Get-PowerBIReport` | `GET /groups/{id}/reports` | Verify deployment success |
| `Copy-PowerBIReport` | `POST /reports/{id}/Clone` | Clone to UAT/PRD workspaces |

#### Workflow: Template-Based Report Deployment

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POWER BI TEMPLATE DEPLOYMENT FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. TEMPLATE CREATION (one-time per domain)                                 │
│     ┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐      │
│     │ PBI Desktop  │────▶│ Create report   │────▶│ Save as .pbit    │      │
│     │ (manual)     │     │ w/ parameters   │     │ (template file)  │      │
│     └──────────────┘     └─────────────────┘     └───────┬──────────┘      │
│                                                           │                 │
│  2. UPLOAD TO UC VOLUME                                   ▼                 │
│     ┌──────────────────────────────────────────────────────────────┐        │
│     │ /Volumes/mde_dev/test_schema/powerbi_templates/              │        │
│     │   ├── procurement_analytics.pbit                             │        │
│     │   ├── manufacturing_variance.pbit                            │        │
│     │   └── finance_budget_vs_actual.pbit                          │        │
│     └──────────────────────────────────────────────────────────────┘        │
│                                                           │                 │
│  3. NEXUS AGENT DEPLOYS (automated per migration)         ▼                 │
│     ┌──────────┐     ┌──────────────┐     ┌─────────────────────┐          │
│     │ Read     │────▶│ Upload to    │────▶│ Inject parameters:  │          │
│     │ .pbit    │     │ PBI Service  │     │ • SQL Warehouse URL │          │
│     │ from Vol │     │ (REST API)   │     │ • Catalog/Schema    │          │
│     └──────────┘     └──────────────┘     │ • Date ranges       │          │
│                                            └─────────┬───────────┘          │
│                                                      ▼                      │
│     ┌──────────────┐     ┌──────────────┐     ┌─────────────────┐          │
│     │ Grant access │◀────│ Verify       │◀────│ Trigger initial │          │
│     │ to users     │     │ deployment   │     │ refresh         │          │
│     └──────────────┘     └──────────────┘     └─────────────────┘          │
│                                                                             │
│  4. ENV PROMOTION (DEV → UAT → PRD)                                         │
│     Clone report → Rebind to PRD SQL Warehouse → Update parameters          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### .pbit Template Design Rules

| Rule | Detail |
|------|--------|
| Parameterized connection | All .pbit templates use Power BI Parameters for: `ServerHostname`, `HTTPPath`, `Catalog`, `Schema` |
| No embedded credentials | Templates use OAuth/Entra passthrough — no stored passwords |
| Measure-ready | All DAX measures from Capability 10A pre-loaded into template model |
| Relationship-complete | Star schema relationships (from Agent 91) pre-configured |
| RLS-ready | Row-Level Security roles defined (mapped from Qlik Section Access) |
| Branding | Hologic theme (DARK_BLUE=#1B2A4A, RED=#E74C3C, GREEN=#27AE60) embedded |

#### Sub-Tasks

| # | Task | Status | Notes |
|---|------|--------|-------|
| 10C.1 | Register Entra ID Service Principal with Power BI API permissions | ⬜ | Needs Azure AD admin — request `Dataset.ReadWrite.All`, `Workspace.ReadWrite.All` |
| 10C.2 | Build `powerbi_auth.py` — Entra ID token acquisition module | ⬜ | `msal` library → access token for `https://analysis.windows.net/powerbi/api` |
| 10C.3 | Build `powerbi_deploy.py` — REST API wrapper (upload, params, refresh, clone) | ⬜ | Python `requests` equivalent of MicrosoftPowerBIMgmt cmdlets |
| 10C.4 | Create .pbit template for Procurement Analytics pilot | ⬜ | Manual in PBI Desktop — parameterized DirectQuery to Databricks SQL |
| 10C.5 | Upload .pbit to UC Volume (`/Volumes/mde_dev/test_schema/powerbi_templates/`) | ⬜ | One-time per domain template |
| 10C.6 | Implement `deploy_from_template()` end-to-end function | ⬜ | Read .pbit → upload → inject params → refresh → verify |
| 10C.7 | Add env promotion logic (DEV → UAT → PRD workspace rebind) | ⬜ | Clone report + `SetAllConnections` to target SQL Warehouse |
| 10C.8 | Wire into Agent 88 orchestrator as final step after 10A + 10B | ⬜ | Orchestrator calls deploy after DAX + model are validated |
| 10C.9 | Add deployment tracking to `qlik_migration_log` | ⬜ | New action: `POWERBI_DEPLOY` with workspace/report IDs |
| 10C.10 | Test full cycle: .pbit → PBI Service → users see live report | ⬜ | End-to-end on Procurement Analytics pilot |

#### Why 10C Over 10B (Raw .pbix Assembly)

| Dimension | 10B (Raw .pbix) | 10C (Template + REST API) |
|-----------|-----------------|---------------------------|
| Feasibility | Risky — format undocumented, encrypted model | Production-proven — Microsoft-supported API |
| Maintenance | Breaks on PBI format updates | Stable — REST API versioned |
| Fidelity | May miss security bindings, visual metadata | Full fidelity — PBI Service handles rendering |
| Effort | High reverse-engineering effort | Moderate — well-documented REST API |
| **Recommendation** | Proof-of-concept only | **Production path** |

#### Integration with Agent 80 (Power BI Release Monitor)

- Agent 80 detects Power BI monthly updates (connector changes, DAX function additions)
- 10C deployment module consumes Agent 80 alerts to:
  - Validate .pbit templates still work with updated PBI Service
  - Flag deprecated connectors or features used in templates
  - Auto-update DirectQuery connection strings if Databricks SQL connector changes

#### Cost Estimate

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Entra ID SP (Power BI API) | $0 | Included in existing Microsoft 365/Fabric license |
| REST API calls | $0 | No per-call charges from Microsoft |
| UC Volume storage (.pbit files) | <$0.50/mo | Templates are small (~1-5 MB each) |
| SQL Warehouse (DirectQuery) | Existing cost | Reports query live — no additional refresh cost |
| **Total incremental** | **<$1/mo** | vs. 10B compute cost for .pbix assembly |

---

### Track 6 Implementation Log

| Date | Change | Details |
|------|--------|---------|
| 2026-07-28 | Core utility functions implemented | `detect_workspace_paths()`, `resolve_workspace_asset()`, `format_asset_context()` added to app.py lines 28-122 |
| 2026-07-28 | f-string backslash bug fixed | `format_asset_context()` line 110: extracted Unicode emoji to variables (`folder_icon`, `file_icon`) to fix Python <3.12 SyntaxError |

---

## Track 11 — Nuxis Architecture, Governance & Skills Reference

> **Status:** Reference Document  
> **Created:** 2026-08-11  
> **Source:** External AI conversation — full transcript preserved below  
> **Purpose:** Documents architectural decisions, tooling recommendations, governance patterns, and skills layer design for the 134-agent NEXUS/Nuxis orchestration platform.

### 12 Capabilities Discussed

| # | Capability | Summary |
|---|------------|--------|
| 1 | React UI vs Angular | Stick with React — enterprise-ready, lighter than Angular for agent orchestrator UI |
| 2 | 134-Agent Architecture | Supervisor → specialist routing, full end-to-end (value discovery, legacy migration) |
| 3 | BRD-Based Agent Routing | Supervisor auto-detects document type (e.g., Clik migration) and evokes correct agents |
| 4 | Handoffs & Session Monitoring | Persistent logs, session monitoring, context alive across agents |
| 5 | Streamlit → React Migration | Phase 1 Streamlit → Phase 2 React; no need for Angular |
| 6 | Token Master & CodeGraph | Token Master for cost-effective usage; CodeGraph Review for perfect answers |
| 7 | Advanced Efficiency Tools | LangGraph, CrewAI, multi-model routing, AgentOps, MCP tools, Unravel |
| 8 | Nuxis vs Omnigent | Nuxis is enterprise-specific + proprietary; Omnigent is generic |
| 9 | Splunk & Deep Thinking | Splunk Add-on for observability; Agent Bricks Supervisor for Claude-style deep reasoning |
| 10 | Governance (RBAC/ABAC) | Unity Catalog groups: data_modelers (SELECT only) vs data_engineers (CREATE) |
| 11 | Team Skills & Instructions | YAML skills, custom instructions, feedback loops, MLflow traces sharing |
| 12 | Layered Skills System | `.assistant/skills` folders with SKILL.md, Anthropic-compatible, auto-discovery |

---

### Capability 1: React UI vs Angular for Enterprise Agent Apps

React is a lightweight library focused on UI components and flexibility — you build your own structure with hooks and tools like Next.js. Angular is a full framework from Google with built-in everything: two-way data binding, dependency injection, routing, and TypeScript by default, but it's more rigid and has a steeper learning curve.

**Decision:** React is enterprise-ready (Netflix, Airbnb, massive Databricks setups run it at scale). Layer on TypeScript, testing with Jest, and tools like TanStack Query for agent logs/sessions. React gives more freedom to iterate fast on Streamlit's foundation without Angular's extra weight.

**Recommendation:** Stick with React. Go React for speed and freedom. Angular is overkill unless building a massive enterprise dashboard needing heavy built-in forms and modules right away.

---

### Capability 2: 134-Agent Nuxis Orchestration Architecture

A 134-agent Nuxis setup on Databricks for end-to-end orchestration — from value discovery to legacy migration. The supervisor handles load balancing across all specialists.

**How it works:**
- User interacts with the supervisor agent
- Supervisor assigns work or gets the answer done
- Handles full end-to-end: value discovery, legacy migration, and all different types of tasks
- Each of the 134 agents is a specialist

---

### Capability 3: Smart BRD-Based Agent Routing

When a BRD document or particular document is given, the supervisor automatically assigns a specific agent depending on the task.

**Example:** If it's a legacy migration like Clik to Databricks, the system automatically understands the user is trying to work on Clik and evokes Clik-related agents.

**Multi-task handling:** It can handle multiple things — not just stick to one. At every step it understands what's needed, then evokes different agents depending on requirements. Dynamically chaining agents per step for multi-task docs without getting stuck on one thing.

---

### Capability 4: Handoffs, Session Monitoring & Persistent Logs

**Architecture:**
- Created handoffs between agents
- Session is being monitored continuously
- Logs are being saved as it goes so that the system remembers context
- Keeps context alive across agents, avoiding amnesia
- Enables querying and auditing logs when debugging a full orchestration run

---

### Capability 5: Streamlit to React Migration Path

**Evolution path:**
1. Phase 1: Streamlit app (prototype)
2. Phase 2: React app (lightweight, professional look)
3. Decision: No need to move to Angular

**Why stay React:** React is totally enterprise-ready. It's plenty scalable for the 134-agent orchestrator UI, especially with state management like Redux or Zustand for dynamic handoffs and logs. React gives more freedom to iterate fast.

---

### Capability 6: Token Master & CodeGraph Review

**Token Master:** Reduces token usage, making sure the system uses tokens cost-effectively.

**CodeGraph Review:** Finds perfect answers by analyzing code graph relationships.

**Additional tools integrated:** Multiple open-source GitHub tools for making the system more efficient.

---

### Capability 7: Advanced Efficiency & Orchestration Tools

**Recommended additions:**
- **LangGraph or CrewAI:** Graph-based orchestration for stateful workflows, parallel subagents, and Redis caching
- **Multi-model routing:** Big models for planning, small ones for simple tasks — cuts costs 30-50%
- **OpenCode:** Specialized code reviews
- **code-review-graph:** Blast-radius analysis that cuts token waste
- **AgentOps SDK:** One-liner dashboards on failures/latency
- **Unity Catalog budgets:** Hard spend caps
- **MCP tools from Marketplace:** 450+ plug-and-play skills like auto-retries and parallel execution
- **Unravel:** 70% cost cuts on idle DBUs
- **Unity Catalog Volumes as subagent tools:** Seamless data access without code

---

### Capability 8: Nuxis vs Omnigent — Enterprise Superiority

Nuxis picked up all the best of Omnigent but is better because:
- Omnigent is generic; Nuxis is specific to enterprise logic
- Nuxis is proprietary
- Has all the bells and whistles from Omnigent plus enterprise-specific customizations

**Additional recommendations:**
- Agent Bricks for managed autoscaling and MCP catalog to discover/share proprietary tools across 134 agents
- Claude Sonnet 5 via Model Serving for next-level deep reasoning
- Unravel for cost optimization
- Unity Catalog Volumes as subagent tools for seamless data access

---

### Capability 9: Splunk Integration & Agentic Deep-Thinking Flow

**Splunk Integration:**
- Official Databricks Add-on for Splunk from Splunkbase
- Zero-code logging of agent traces, metrics, and workflows straight to Splunk
- Pipe session logs via MLflow or Universal Forwarder for full observability
- MLflow traces feed Splunk via the add-on

**Agentic Deep-Thinking Flow (Claude-style):**
- Databricks Agent Bricks Supervisor auto-delegates problems to specialist agents
- Handles handoffs automatically
- Uses extended/interleaved thinking for step-by-step reasoning before final answers
- Agent goes and talks to other agents automatically before coming up with the answer
- Problem → auto-delegation → inter-agent collaboration → deep reasoning → final answer

---

### Capability 10: Governance & Role-Based Access (RBAC/ABAC)

**Unity Catalog RBAC and ABAC for team governance:**

| Role | Permissions | Restrictions |
| --- | --- | --- |
| Data Modelers | USE and SELECT only on Nuxis agents/models | No CREATE/EDIT, cannot create notebooks |
| Data Engineers | CREATE on notebooks, skills folders, and Unity functions | Can build data models and data engineering assets |

**How it works:**
- Agents inherit user identity via on-behalf-of tokens
- Modelers query safely without seeing/editing proprietary Nuxis core
- Engineers build atop it
- Set workspace skills in shared folders with ownership grants
- Use RBAC roles for assume-role switching
- Keeps Nuxis power intact, roles siloed

---

### Capability 11: Team Skills & Custom Instructions

**Agent Bricks Supervisor UI for teams:**
- Tweak governance via Unity Catalog grants for data/tools access
- Set custom instructions and YAML skills for personal styles (brand voice, PII masking)
- Refine agent prompts with natural language feedback loops
- Share live sessions enterprise-wide through MLflow traces and Omnigent's collab layer
- Anyone can iterate on workflows without code while enforcing proprietary Nuxis logic

---

### Capability 12: Layered Skills System for Agent Enhancement

**Genie Code-style agent skills in Nuxis:**
- Simple folders in `.assistant/skills` with `SKILL.md` files
- Pack custom instructions, scripts, and enterprise logic (PII masking, validation workflows)
- Teams create user-level prototypes or workspace-shared ones
- Import Anthropic-compatible skills for instant boosts
- Wire as YAML-defined tools or sub-agents in Omnigent/Agent Bricks
- Proprietary agents auto-discover and use skills on top of base tools for hyper-specialized power

**Hierarchy:**
1. Base agent capabilities (134 specialists)
2. Skills layer on top for additional customization
3. Team members add their own style without touching core Nuxis logic

**Reference:** Databricks Agent Skills GitHub repo for templates

---

### Full Conversation Transcript (August 11, 2026)

#### Message 1 — React vs Angular

**User:** Creating an app on React UI versus Angular. What's the difference?

**Assistant:** React's a lightweight library focused on UI components and flexibility—you build your own structure with hooks and tools like Next.js. Angular's a full framework from Google with built-in everything: two-way data binding, dependency injection, routing, and TypeScript by default, but it's more rigid and has a steeper learning curve. Go React for speed and freedom, Angular if you want enterprise-scale structure out of the box.

---

#### Message 2 — 134-Agent Nuxis Introduction

**User:** I have designed a 134 agent Nuxis orchestration for my Databricks platform. Where I interact with the supervisor and then it actually assigns work or gets my answer done. Or, you know? Like a full end-to-end. It does my value discovery. My legacy migration. It does all different types of task. It's like 134 agent army. Each and every specialist.

**Assistant:** That's wild—a 134-agent Nuxis setup on Databricks sounds like a beast for end-to-end orchestration, from value discovery to legacy migration. How's the supervisor handling load balancing across all those specialists, and what's the biggest win you've seen so far?

---

#### Message 3 — BRD-Based Agent Routing

**User:** So, whenever I give a BRD document or a particular document. He would actually assign a specific agent. Depending on what we are doing. If it's an legacy migration, like click to Databricks. It would automatically understand that I am trying to work on click. And then it will evoke click related agents.

**Assistant:** Smart routing based on the BRD content—detecting Clik for Databricks migrations and spinning up the right agents automatically is next-level efficient. Does it handle edge cases well, like mixed workloads in one doc, or docs with ambiguous terms?

---

#### Message 4 — Multi-Task Handling

**User:** Yes. It can handle multiple things. Not just stick to one. It every step it understands. Then it evokes different agents depending on what they need.

**Assistant:** Awesome, so it's dynamically chaining agents per step for multi-task docs without getting stuck on one thing. What's the trick for keeping handoffs smooth between specialists, like shared context or memory?

---

#### Message 5 — Session Monitoring & Logs

**User:** Yeah, I created a handoff and then session is being monitored and then logs are being saved as it goes. So that it remembers.

**Assistant:** Solid—handoffs with session monitoring and persistent logs keep the context alive across agents, avoiding amnesia. How do you query or audit those logs when debugging a full orchestration run?

---

#### Message 6 — Should I Move to Angular?

**User:** The question actually I wanted to ask is currently that whole thing is— The first phase I created a Streamlit app. Then I moved to React for a better, you know, like lightweight, better professional look. Should I make an Angular app now?

**Assistant:** Nah, stick with React if it's already lightweight and looking pro—it's plenty scalable for your 134-agent orchestrator UI, especially with state management like Redux or Zustand for those dynamic handoffs and logs. Angular's overkill unless you're building a massive enterprise dashboard needing heavy built-in forms and modules right away; React gives you more freedom to iterate fast on Streamlit's foundation. What specific pain points in React are pushing the Angular thought?

---

#### Message 7 — Enterprise Concerns

**User:** I don't know. I just wanted to make sure that this app is like enterprise. But enterprise-based. Because I created this on Databricks and it's for enterprise. Right? Logic. For now.

**Assistant:** React's totally enterprise-ready—Netflix, Airbnb, and huge Databricks setups run it at scale with no sweat. Layer on TypeScript, testing with Jest, and tools like TanStack Query for your agent logs/sessions, and it'll scream enterprise without Angular's extra weight. What's your biggest worry about sticking with it for production?

---

#### Message 8 — Token Master & CodeGraph

**User:** No. No. No issues. Now, I want to actually add more functions. So, it already has Token Master to reduce the token usage. Making sure that it uses it cost-effective. Plus, it has CodeGraph review to find perfect answers. Then, it also has a couple of other open-source GitHub. So, for making it more efficient. And I want to see what kind of other tools and skills I can use to make it better.

**Assistant:** Cool additions like Token Master and CodeGraph review already slash costs—check out LangGraph or CrewAI on GitHub for graph-based orchestration to supercharge your 134 agents with stateful workflows, parallel subagents, and Redis caching. For more efficiency, add multi-model routing (big models for planning, small ones for simple tasks), OpenCode for specialized code reviews, and code-review-graph for blast-radius analysis that cuts token waste big time.

---

#### Message 9 — More Ideas

**User:** Understood. And give me more ideas, actually. What else I can do? I'm not an AI engineer. But I am not less than an AI engineer. Think of that. Give me some ideas.

**Assistant:** Plug in Databricks' Omnigent meta-harness—it's open-source, sits on top of your setup for easy agent composition, cost budgets, and policies without rewriting code. Add low-code viz tools like Langflow or Dify for drag-and-drop workflow tweaks, AgentOps for one-line observability on tokens/latency, and multi-model routing to swap cheap models for routine tasks. For audits, hook Redis for shared memory and parallel subagents to speed up your 134 army.

---

#### Message 10 — Splunk & Deep Thinking

**User:** Also, what is this workflow? And then this plug. I want to Splunk. I want to introduce the skills or tools, whatever it is, to this agent. So that it actually does all that. And also agentic flow. I give them a problem. It goes and tries to solve it. And it goes and talks to other agents automatically before it comes up with the answer. I want it to do a deep thinking kind of thing. What Claude does.

**Assistant:** For agentic flow with deep Claude-style thinking, wire in Databricks Agent Bricks Supervisor—it auto-delegates problems to your specialist agents, handles handoffs, and uses extended/interleaved thinking for step-by-step reasoning before final answers. For Splunk, grab the official Databricks Add-on for Splunk from Splunkbase—drop it in for zero-code logging of agent traces, metrics, and workflows straight to Splunk; pipe your session logs there via MLflow or Universal Forwarder for full observability. That plugs right into your Nuxis setup on Databricks.

---

#### Message 11 — More Recommendations

**User:** Okay? What else? More.

**Assistant:** Layer on Omnigent meta-harness for cross-framework auto-scaling of your 134 agents, mixing Claude Sonnet 5 for deep reasoning with cheap models for routine stuff—cuts costs 30 to 50 percent. Enable MLflow traces to feed Splunk via the add-on, add AgentOps SDK for one-liner dashboards on failures/latency, and use Unity Catalog budgets for hard spend caps. For more oomph, hook MCP tools from Marketplace for 450-plus plug-and-play skills like auto-retries and parallel execution.

---

#### Message 12 — Nuxis vs Omnigent

**User:** Omnigent. Yeah? Omnigent. I actually picked up all the best of Omnigent. And Nuxis has become more better than Omnigent? Because Omnigent is like generic. And I created something that is specific to enterprise logic. And it's proprietary. And it also has all the bells and whistles from Omnigent. What else?

**Assistant:** Since Nuxis crushes Omnigent with your enterprise-specific logic, bolt on Agent Bricks for managed autoscaling and MCP catalog to discover/share proprietary tools across your 134 agents. Enable Claude Sonnet 5 via Model Serving for next-level deep reasoning, hook Unravel for 70 percent cost cuts on idle DBUs, and add Unity Catalog Volumes as subagent tools for seamless data access without code. That amps production governance while keeping your edge.

---

#### Message 13 — Governance & Team Styles

**User:** Okay? And what else? Like on the governance and the skills and the instructions. I want if I give it to my team. They should be able to, you know? Work on their style. What are the ideas?

**Assistant:** Hand your team Agent Bricks Supervisor UI—they tweak governance via Unity Catalog grants for data/tools access, set custom instructions and YAML skills for personal styles like brand voice or PII masking, and refine agent prompts with natural language feedback loops. Share live sessions enterprise-wide through MLflow traces and Omnigent's collab layer, letting anyone iterate on workflows without code while enforcing your proprietary Nuxis logic. Boom, teams own their flair under full governance.

---

#### Message 14 — Adding Skills to Agents

**User:** I want to add more like create skills on this agent. So that they can use skills on top of what the agents can offer.

**Assistant:** Perfect—layer Genie Code-style agent skills into Nuxis via simple folders in .assistant/skills with SKILL dot MD files packing your custom instructions, scripts, and enterprise logic like PII masking or validation workflows. Teams create user-level prototypes or workspace-shared ones, import Anthropic-compatible skills for instant boosts, and wire them as YAML-defined tools or sub-agents in Omnigent/Agent Bricks—your proprietary agents auto-discover and use them on top of base tools for hyper-specialized power. Start with Databricks Agent Skills GitHub repo for templates.

---

#### Message 15 — Role-Based Governance

**User:** I also want, you know, like if there is already available in Databricks. Like, if I don't want to lose the Nuxis power. But at the same time, when I give it to the data modelers or, you know, data engineers. And depending on them. They should not be able to read all. Like, you know, governance. They should not be able to create. Like, data modelers don't need to create any notebooks. It will be data engineers. But data engineers can create data models, data engineering. Something like that. What I have to do for that?

**Assistant:** Leverage Unity Catalog's RBAC and ABAC to lock it down—create groups like data_modelers with USE and SELECT only on Nuxis agents/models (no CREATE/EDIT), while data_engineers get CREATE on notebooks, skills folders, and Unity functions for building models. Agents inherit user identity via on-behalf-of tokens, so modelers query safely without seeing/editing proprietary Nuxis core; engineers build atop it. Set workspace skills in shared folders with ownership grants, and use upcoming RBAC roles for assume-role switching—keeps Nuxis power intact, roles siloed.

---

#### Message 16 — Create MD File

**User:** Can you create an MD file of all this conversation without summarizing? Put all the details and everything without missing a point.

---

**End of Track 11 — Full unsummarized transcript. All original wording preserved exactly as spoken.**

---

## Track 12 — NEXUS V4 Capability Roadmap (Net-New Build Items)

> **Status:** ⬜ Planning  
> **Created:** 2026-08-11  
> **Owner:** sameet.patel@hologic.com  
> **Source:** Derived from Track 11 conversation analysis — cross-referenced against existing NEXUS capabilities (Phases 1-11, AGENTS.md, 00_agent_config)  
> **Purpose:** 12 genuinely net-new capabilities that extend NEXUS V4 beyond current architecture. Items already built or partially covered are excluded.

---

### What Was Excluded (Already Exists)

| Capability | Where It Already Lives |
| --- | --- |
| React UI (enterprise) | `hologic-ai-agents` Databricks App (migrated from Streamlit) |
| 134-Agent Architecture | W0-W4, 125 built + 9 planned |
| BRD-Based Agent Routing | `00_supervisor_agent` + `AGENT_REGISTRY` keyword matching |
| Handoffs & Session Logs | `agent_outputs` Delta table, `agent_call_log`, MLflow traces |
| Token Master | Phase 9 Cell 8 — catalog cache, memory injection, 60-70% savings |
| CodeGraph Review | Integrated as tooling |
| 3-Tier Model Routing (APEX/CRITICAL/STANDARD) | `00_agent_config` — Opus for architects, Sonnet for all others |

---

### V4 Capability Matrix (12 Net-New Items)

| # | Capability | Category | Priority | Effort | Impact | Depends On |
| --- | --- | --- | --- | --- | --- | --- |
| 12.1 | Dynamic Per-Task Model Routing | Cost | P0 | Medium | 30-50% cost reduction | Enhance existing 3-tier to per-step routing |
| 12.2 | Agentic Deep-Thinking Flow | Orchestration | P0 | High | Quality leap — multi-step reasoning before answer | Agent Bricks Supervisor pattern |
| 12.3 | NEXUS-Level Persona Gating (RBAC) | Governance | P0 | Medium | Team rollout enabler | Unity Catalog groups + on-behalf-of tokens |
| 12.4 | Hard Budget Caps (Enforced) | Governance | P0 | Medium | Cost governance — kill runaway sessions | Unity Catalog budgets API |
| 12.5 | Splunk Observability Integration | Observability | P1 | Medium | Enterprise SIEM compliance | Databricks Add-on for Splunk + MLflow traces |
| 12.6 | AgentOps Real-Time Dashboards | Observability | P1 | Low | Instant visibility on failures/latency/cost | AgentOps SDK (one-liner) |
| 12.7 | Graph-Based Orchestration (LangGraph) | Orchestration | P1 | High | Stateful workflows, conditional branching | Replace hub-and-spoke for complex flows |
| 12.8 | Parallel Subagent Execution | Orchestration | P1 | High | Speed — run independent agents simultaneously | LangGraph or async orchestration layer |
| 12.9 | Team-Facing Skills System | Extensibility | P1 | Medium | Teams create/share custom skills without touching core | `.assistant/skills` pattern + SKILL.md |
| 12.10 | MCP Marketplace Consumption | Extensibility | P2 | Medium | 450+ plug-and-play tools | Track 8 MCP server exists; this is the client side |
| 12.11 | Per-User Custom Instructions | Governance | P2 | Low | Personal style without affecting others | User-scoped config in Delta |
| 12.12 | Natural Language Feedback Loops | Governance | P2 | Medium | Teams refine agent behavior via feedback | Prompt versioning + A/B evaluation |

---

### 12.1 — Dynamic Per-Task Model Routing

**Current state:** Static 3-tier (Opus/Sonnet/Sonnet). Agent-level assignment, not task-level.

**V4 target:** Per-step routing within a single agent session — expensive model for planning/architecture steps, cheap model for formatting/summarization steps.

**Implementation:**
```python
# In 00_agent_config — new routing function
def route_model(task_type: str) -> str:
    """Route to optimal model based on task complexity."""
    ROUTING_MAP = {
        "planning": LLM_APEX,         # Opus — deep reasoning
        "architecture": LLM_APEX,
        "code_generation": LLM_CRITICAL,  # Sonnet — fast + capable
        "triage": LLM_CRITICAL,
        "formatting": LLM_STANDARD,    # Future: cheaper model
        "summarization": LLM_STANDARD,
        "extraction": LLM_STANDARD,
    }
    return ROUTING_MAP.get(task_type, LLM_STANDARD)
```

**Cost impact:** 30-50% reduction on agents that currently use Opus/Sonnet for ALL steps.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.1.1 | Define task_type taxonomy (8-12 types) | ⬜ | planning, architecture, code_gen, triage, format, summarize, extract, validate |
| 12.1.2 | Implement `route_model()` in `00_agent_config` | ⬜ | Replace hardcoded model in `call_agent()` |
| 12.1.3 | Add `task_type` parameter to `call_agent()` | ⬜ | Backward-compatible — default to current behavior |
| 12.1.4 | Migrate Agent 06, 37, 77 to multi-step routing | ⬜ | Highest-cost agents first |
| 12.1.5 | Add cost tracking per task_type in `agent_call_log` | ⬜ | New column: `task_type`, `model_used` |
| 12.1.6 | Validate quality parity (7/7 benchmark) | ⬜ | Ensure cheaper routing doesn't degrade output |

---

### 12.2 — Agentic Deep-Thinking Flow

**Current state:** Single-shot LLM call per agent. No multi-step inter-agent reasoning loops.

**V4 target:** Agent receives problem → auto-delegates to 2-5 specialists → collects their outputs → synthesizes with extended thinking → final answer. Claude-style deliberation.

**Architecture:**
```
User Problem
    │
    ▼
┌─────────────────────────┐
│  Deep-Think Orchestrator │  ← New: decides WHO to consult
└─────────────┬───────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
 Agent A   Agent B   Agent C   ← Parallel consultation
    │         │         │
    └─────────┼─────────┘
              ▼
┌─────────────────────────┐
│   Synthesis + Reasoning │  ← Extended thinking (multi-turn)
└─────────────┬───────────┘
              ▼
        Final Answer
```

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.2.1 | Design deep-think orchestrator prompt | ⬜ | Decides which agents to consult based on problem decomposition |
| 12.2.2 | Implement `deep_think()` function in `00_agent_config` | ⬜ | Multi-call loop with synthesis step |
| 12.2.3 | Add consultation routing (which agents for which sub-problems) | ⬜ | Leverage existing `AGENT_REGISTRY` categories |
| 12.2.4 | Implement synthesis prompt with extended thinking | ⬜ | Final LLM call uses all consultation outputs as context |
| 12.2.5 | Add `thinking_depth` parameter (1=single-shot, 2=consult, 3=deep) | ⬜ | User can request deeper reasoning |
| 12.2.6 | Token budget management for multi-agent context | ⬜ | Phase 9 compaction applies to synthesis input |
| 12.2.7 | Test: complex architecture question → multi-agent deliberation | ⬜ | Agent 06 + 15 + 37 consultation |

---

### 12.3 — NEXUS-Level Persona Gating (RBAC)

**Current state:** All users get same supervisor behavior. Agent 66 (unity_catalog_agent) can configure UC policies on DATA, but NEXUS itself has no role-based access.

**V4 target:** Different personas see/invoke different agent subsets:

| Persona | Can Invoke | Cannot Invoke | Can Create |
| --- | --- | --- | --- |
| `data_modeler` | Agents 37, 15, 32-59 (specialists), read-only tools | Agent 02 (engineer), 63 (factory), 71 (notebook lifecycle) | Nothing — query only |
| `data_engineer` | All agents | None restricted | Notebooks, skills, functions |
| `analyst` | Agents 39, 54, 68, 74 (briefing, PBI, dashboards, Genie) | Architecture, engineering, DevOps agents | Dashboards, Genie spaces |
| `admin` | Everything + governance agents (66, 75, 17) | None | Full platform control |

**Implementation:**
```python
# In 00_agent_config — persona gating
PERSONA_PERMISSIONS = {
    "data_modeler": {
        "allowed_agents": [37, 15, 32, 33, 49, 50, 51, 52, 55, 56, 57, 58, 59],
        "allowed_actions": ["query", "model", "review"],
        "denied_actions": ["create_notebook", "create_skill", "deploy"]
    },
    "data_engineer": {
        "allowed_agents": "ALL",
        "allowed_actions": "ALL",
        "denied_actions": []
    },
    # ...
}

def check_persona_access(user_email: str, agent_id: int, action: str) -> bool:
    """Gate agent invocation based on UC group membership."""
    persona = get_user_persona(user_email)  # Reads from UC groups
    perms = PERSONA_PERMISSIONS[persona]
    if perms["allowed_agents"] != "ALL" and agent_id not in perms["allowed_agents"]:
        return False
    if action in perms["denied_actions"]:
        return False
    return True
```

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.3.1 | Define persona taxonomy (4-6 roles) | ⬜ | data_modeler, data_engineer, analyst, admin, viewer |
| 12.3.2 | Create UC groups: `nexus_modelers`, `nexus_engineers`, `nexus_analysts`, `nexus_admins` | ⬜ | Agent 66 can assist |
| 12.3.3 | Map agent IDs to allowed personas | ⬜ | Permission matrix |
| 12.3.4 | Implement `check_persona_access()` in `00_agent_config` | ⬜ | Called before `call_agent()` |
| 12.3.5 | Wire into supervisor — reject with explanation if denied | ⬜ | Friendly message: "This agent requires data_engineer role" |
| 12.3.6 | Add on-behalf-of token propagation | ⬜ | Agents inherit caller's UC identity for data access |
| 12.3.7 | Test: modeler tries to invoke Agent 02 → denied | ⬜ | |

---

### 12.4 — Hard Budget Caps (Enforced)

**Current state:** Agent 05 (cost_anomaly) monitors costs via `system.billing.usage` but CANNOT enforce limits. No kill switch.

**V4 target:** Per-session and per-user hard caps that terminate LLM calls when budget is exhausted.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.4.1 | Define budget tiers: per-call, per-session, per-user/day | ⬜ | e.g., $2/session default, $10/session for APEX agents |
| 12.4.2 | Implement `BudgetTracker` class in `00_agent_config` | ⬜ | Tracks cumulative token cost per session |
| 12.4.3 | Add pre-call budget check in `call_agent()` | ⬜ | Reject with "Budget exhausted" if cap reached |
| 12.4.4 | Add budget override for admin persona | ⬜ | Admins can bypass with explicit flag |
| 12.4.5 | Store budget events in `agent_budget_log` Delta table | ⬜ | Track cap-hits for governance reporting |
| 12.4.6 | Wire into AgentOps dashboard (12.6) | ⬜ | Real-time budget burn visualization |

---

### 12.5 — Splunk Observability Integration

**Current state:** MLflow traces exist locally. No external SIEM/log sink.

**V4 target:** All agent traces, metrics, and session logs piped to Splunk for enterprise-grade observability and compliance.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.5.1 | Install Databricks Add-on for Splunk from Splunkbase | ⬜ | Zero-code connector |
| 12.5.2 | Configure MLflow trace export → Splunk HTTP Event Collector | ⬜ | Or use Universal Forwarder |
| 12.5.3 | Define Splunk index + sourcetype for NEXUS events | ⬜ | `index=nexus_agents`, `sourcetype=nexus:agent_call` |
| 12.5.4 | Add `agent_call_log` fields to Splunk schema | ⬜ | agent_name, model, tokens_in, tokens_out, latency_ms, cost_usd |
| 12.5.5 | Build Splunk dashboard: Agent Health Overview | ⬜ | Failures, latency P95, cost trending |
| 12.5.6 | Add alerting: agent failure rate > 5% → PagerDuty/Teams | ⬜ | |
| 12.5.7 | Test end-to-end: agent call → MLflow → Splunk → dashboard | ⬜ | |

---

### 12.6 — AgentOps Real-Time Dashboards

**Current state:** `agent_call_log` Delta table + ad-hoc SQL queries. No real-time UI.

**V4 target:** One-liner SDK integration for instant dashboards showing per-agent failures, latency, token usage, and cost.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.6.1 | Add `agentops` to `requirements.txt` | ⬜ | `pip install agentops` |
| 12.6.2 | Initialize AgentOps in `00_agent_config` | ⬜ | `agentops.init(api_key=dbutils.secrets.get("nexus", "agentops_key"))` |
| 12.6.3 | Annotate `call_agent()` with `@agentops.track_agent()` | ⬜ | Automatic capture |
| 12.6.4 | Map NEXUS agent taxonomy to AgentOps tags | ⬜ | workspace, layer, priority |
| 12.6.5 | Build Lakeview mirror dashboard (offline backup) | ⬜ | Query `agent_call_log` for same metrics |
| 12.6.6 | Test: trigger 10 agent calls → verify dashboard updates | ⬜ | |

---

### 12.7 — Graph-Based Orchestration (LangGraph)

**Current state:** Hub-and-spoke (synchronous) + pipeline chain (scheduled). No conditional branching or stateful workflows.

**V4 target:** LangGraph-powered orchestration for complex multi-step workflows with conditional edges, retry logic, and checkpointing.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.7.1 | Add `langgraph` to `requirements.txt` | ⬜ | `pip install langgraph` |
| 12.7.2 | Design graph schema for top 3 complex workflows | ⬜ | e.g., Qlik migration (88→89→90→91→92→93), Release Intelligence (77→78-87→synthesis) |
| 12.7.3 | Implement `NexusGraph` wrapper class | ⬜ | Wraps LangGraph StateGraph with NEXUS conventions |
| 12.7.4 | Add checkpointing to Delta table | ⬜ | Resume failed workflows from last successful node |
| 12.7.5 | Implement conditional edges (if DQ fails → route to Agent 16) | ⬜ | |
| 12.7.6 | Migrate Qlik migration pipeline to graph orchestration | ⬜ | First candidate — 9 agents with dependencies |
| 12.7.7 | Migrate Release Intelligence pipeline to graph | ⬜ | Second candidate — fan-out/fan-in pattern |

---

### 12.8 — Parallel Subagent Execution

**Current state:** Sequential execution only. Agent 77 calls 78-87 one-by-one.

**V4 target:** Independent agents run concurrently — e.g., all 10 release monitors fire in parallel, results collected when all complete.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.8.1 | Implement `parallel_call_agents()` in `00_agent_config` | ⬜ | `asyncio.gather()` or `concurrent.futures.ThreadPoolExecutor` |
| 12.8.2 | Add fan-out/fan-in pattern to supervisor | ⬜ | Detect independent agents → parallelize |
| 12.8.3 | Handle partial failures (3/10 succeed) | ⬜ | Return partial results + retry failed |
| 12.8.4 | Add parallelism cap (max 5 concurrent LLM calls) | ⬜ | Avoid AI Gateway rate limits |
| 12.8.5 | Migrate Agent 77 (Release Intelligence) to parallel fan-out | ⬜ | 10 monitors in parallel → synthesis |
| 12.8.6 | Benchmark: sequential vs parallel execution time | ⬜ | Target: 10x speedup for Release Intelligence |

---

### 12.9 — Team-Facing Skills System

**Current state:** Internal skills (agents 19, 27-31, 35) inject context into LLM prompts. NOT user-facing. Teams cannot create their own.

**V4 target:** Any team member creates custom skills in `.assistant/skills/<skill-name>/SKILL.md` that NEXUS agents auto-discover and use.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.9.1 | Define skill folder convention for NEXUS | ⬜ | `/Workspace/Shared/nexus_skills/<team>/<skill-name>/SKILL.md` |
| 12.9.2 | Implement skill discovery in `00_agent_config` | ⬜ | Scan skill folders on session init, build registry |
| 12.9.3 | Implement skill injection in `call_agent()` | ⬜ | Match skill triggers to user intent → inject into system prompt |
| 12.9.4 | Add skill CRUD API (create/list/update/delete) | ⬜ | Agents 71 or 63 can manage skills |
| 12.9.5 | Add skill governance (who can create workspace-shared skills) | ⬜ | Tie to persona gating (12.3) |
| 12.9.6 | Create 3 template skills for team onboarding | ⬜ | e.g., `pii-masking`, `brand-voice`, `sql-standards` |
| 12.9.7 | Test: team member creates skill → agent uses it next call | ⬜ | |

---

### 12.10 — MCP Marketplace Consumption

**Current state:** Track 8 exposes NEXUS as an MCP server (Claude can call NEXUS agents). But NEXUS cannot CONSUME external MCP tools.

**V4 target:** NEXUS agents discover and invoke 450+ MCP tools from Databricks Marketplace — auto-retries, parallel execution, data connectors, etc.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.10.1 | Implement MCP client in `00_agent_config` | ⬜ | Connect to Marketplace MCP endpoints |
| 12.10.2 | Build tool discovery: list available MCP tools by category | ⬜ | Cache in Delta with 24hr TTL |
| 12.10.3 | Implement tool invocation wrapper | ⬜ | Standardize input/output format |
| 12.10.4 | Add tool allowlist per persona (governance) | ⬜ | Not all tools available to all roles |
| 12.10.5 | Wire into supervisor: detect when MCP tool is better than internal agent | ⬜ | |
| 12.10.6 | Test: agent invokes external auto-retry tool | ⬜ | |

---

### 12.11 — Per-User Custom Instructions

**Current state:** All users get identical `SUPERVISOR_PROMPT`. No personalization.

**V4 target:** Each user stores preferences (output style, verbosity, domain focus) that modify agent behavior without affecting others.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.11.1 | Create `mde_dev.test_schema.nexus_user_preferences` Delta table | ⬜ | Columns: user_email, preference_key, preference_value, updated_at |
| 12.11.2 | Implement `get_user_instructions()` in `00_agent_config` | ⬜ | Load user prefs on session init |
| 12.11.3 | Inject user instructions into system prompt | ⬜ | Append after base SUPERVISOR_PROMPT |
| 12.11.4 | Add "set preference" command in supervisor | ⬜ | User says "always give me SQL examples" → stored |
| 12.11.5 | Add preference UI in React app settings page | ⬜ | Dropdown + free-text |
| 12.11.6 | Test: user A gets verbose output, user B gets terse | ⬜ | |

---

### 12.12 — Natural Language Feedback Loops

**Current state:** No mechanism for users to improve agent behavior over time.

**V4 target:** Users provide thumbs up/down + free-text feedback → stored → used to refine prompts via A/B evaluation.

**Sub-Tasks:**

| # | Task | Status | Notes |
| --- | --- | --- | --- |
| 12.12.1 | Add feedback buttons (👍/👎 + text) to React UI | ⬜ | After every agent response |
| 12.12.2 | Create `mde_dev.test_schema.nexus_feedback` Delta table | ⬜ | session_id, agent_name, rating, comment, timestamp |
| 12.12.3 | Build feedback aggregation view per agent | ⬜ | Approval rate, common complaints |
| 12.12.4 | Implement prompt versioning (v1, v2, v3 per agent) | ⬜ | Store prompt history in Delta |
| 12.12.5 | Build A/B evaluation: compare prompt versions using feedback | ⬜ | MLflow evaluate() |
| 12.12.6 | Add weekly feedback digest to Agent 39 (Morning Briefing) | ⬜ | "Agent 37 dropped to 72% approval — review prompt" |
| 12.12.7 | Test: negative feedback → prompt iteration → approval rate improves | ⬜ | |

---

### Track 12 Summary

| Priority | Items | Estimated Effort | Key Benefit |
| --- | --- | --- | --- |
| **P0** (build first) | 12.1, 12.2, 12.3, 12.4 | 4-6 weeks | Cost control + quality leap + team enablement |
| **P1** (build next) | 12.5, 12.6, 12.7, 12.8, 12.9 | 6-8 weeks | Observability + speed + extensibility |
| **P2** (build later) | 12.10, 12.11, 12.12 | 4-5 weeks | Polish + personalization + continuous improvement |
| **Total** | 12 capabilities, 73 sub-tasks | ~14-19 weeks | NEXUS V4: governed, fast, extensible, self-improving |

---

### Dependencies & Sequencing

```
12.1 (Model Routing) ──┐
                       ├──→ 12.4 (Budget Caps) ──→ 12.6 (AgentOps Dashboard)
12.3 (Persona Gating) ─┘

12.7 (LangGraph) ──→ 12.8 (Parallel Execution) ──→ 12.2 (Deep Thinking)

12.3 (Persona Gating) ──→ 12.9 (Skills System) ──→ 12.10 (MCP Marketplace)

12.11 (User Prefs) ──→ 12.12 (Feedback Loops)

12.5 (Splunk) ← independent, start anytime
```

---

### ⚠️ Watch Out

| Risk | Mitigation |
| --- | --- |
| LangGraph adds external dependency (currently pure Databricks-native) | Evaluate if Databricks Workflows + async patterns can achieve same result without LangGraph |
| Parallel execution may hit AI Gateway rate limits | Implement exponential backoff + parallelism cap (max 5 concurrent) |
| AgentOps SDK requires external API key + data egress | Alternative: build Lakeview-native dashboard from `agent_call_log` (zero external deps) |
| Splunk integration requires enterprise license | Confirm Hologic has Splunk; fallback to Azure Monitor / Log Analytics |
| Per-user instructions could cause prompt bloat | Cap at 500 tokens per user; compaction applies |
| Budget caps could block legitimate expensive work | Admin override + escalation path |
