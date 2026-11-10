# Phase 17 — Standalone, Locally-Installable Multi-Agent Product (MCP-Connected)

> **Status:** 🔵 FUTURE — placeholder only, not scoped, no work started. Captured 2026-09-19 from Sameet's own stated direction.
> **Explicit sequencing (Sameet's words, 2026-09-19):** "that is next phase after upgrading databricks app" — this does **not** begin until [Phase 16](PHASE_16_REACT_MODERNIZATION.md) (React/TS frontend + backend modularization on the live Databricks App) ships. Do not pull any of this into Phase 16's scope.
> **Owner:** sameet.patel@hologic.com

## The vision, as stated

Turn NEXUS from a single-tenant Databricks App into the best product for running agentic AI — then, as a later step, package it as a **standalone product installable on a local machine**, similar in distribution model to Open WebUI, rather than only reachable as a hosted Databricks App. That local install would connect out to enterprise data sources via **MCP**: Databricks (SQL/Unity Catalog/workspace), ADO (Boards/Wiki/Git), and internal network shares — the same kind of source access this Claude Code session already has natively (see the MCP servers already wired into this environment as a working reference point for "connect via MCP" in practice).

## Why this is its own phase, not folded into Phase 16

Phase 16 is scoped to modernizing the *existing* app in place (React frontend, modular backend, durable HITL) while it keeps running as a Databricks App — same runtime, same single-tenant hosting, same trusted-header auth model. This vision is a **distribution and deployment-model change**: a different packaging target (local install), a different connectivity model (MCP clients reaching out to Databricks/ADO/network from outside Databricks' own trusted-app boundary), and likely a different auth story (no more free `X-Forwarded-Email` trusted header once it's not running inside Databricks Apps). Mixing the two would violate Phase 16's own "don't combine unrelated refactors" rule and risks turning a bounded modernization into an open-ended rewrite.

## Relevant prior work to reuse, not rediscover

- **Phase 14's Open WebUI research already happened** — the real `open-webui-main.zip` source was read, and its **LICENSE branding clause was confirmed to forbid removing/rebranding the "Open WebUI" name/logo** at scale without a written permission or enterprise license (see [[nexus-frontend-rewrite-scoping]]). That finding still applies here: this must be an independent product inspired by Open WebUI's *distribution model* (local install, connector architecture), not a rebrand of their codebase.
- **MCP-to-Claude integration** was already flagged as a known gap in the V4 capability backlog (CAPABILITIES_INDEX Phase 12 tracks) — this phase is that gap's full realization, not a new idea.
- This Claude Code session's own MCP setup (Databricks, Slack, M365, Lucid, etc., each with their own auth/connection model) is a live, working example of exactly the multi-source MCP-connector pattern this phase would need to replicate in-product.

## Open questions to resolve before this can be broken into real delivery phases

- **Packaging/runtime target:** Electron/Tauri desktop app? Local Python/Node server + browser UI (Open WebUI's actual architecture)? A CLI tool? This determines almost everything else.
- **Auth model without Databricks Apps' trusted header:** how does a local install authenticate to Databricks (OAuth device flow? PAT? SP credentials shipped how?), to ADO (PAT scopes), and to internal network shares (domain-joined assumption?) — this is a materially different security posture than today's app and needs its own review before any build starts.
- **Codebase relationship to Phase 16:** does this become a second deployment target of the same React/FastAPI stack Phase 16 produces, or a genuinely separate codebase that happens to share components?
- **Licensing/distribution:** if this is ever shared beyond Sameet's own machine, what's the internal distribution mechanism (an internal package registry, a signed installer, a git-based tool) and who owns support?

## Rule for future sessions

Do not begin scoping or building against this file until Sameet explicitly prioritizes it. When that happens, this doc should be expanded into a real sub-phase table (matching the style of Phase 15/16) before any code is written — per the standing "evidence before implementation" discipline, starting with a repository/tooling inspection of whatever local-MCP-client precedents exist by then, not assumptions carried over from this placeholder.
