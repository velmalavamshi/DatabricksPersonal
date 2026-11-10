# NEXUS V4 React Modernization — Source Instruction (archived verbatim, 2026-09-19)

> **Archival note:** This is the engineering spec Sameet pasted on 2026-09-19 asking where it fits in the NEXUS V4 phase tracker. It is preserved here verbatim as the governing brief for [PHASE_16_REACT_MODERNIZATION.md](PHASE_16_REACT_MODERNIZATION.md), the same way `NEXUS_V4_Professional_Upgrade_Instruction.docx` governs Phase 15.
>
> **Known issue, do not silently trust:** this brief's "Current High-Level Architecture" section lists SSE event names and a feature inventory that do **not** match the deployed app (verified against Phase 15's `phase0_baseline/contract_sse_stream.md`, 164 live-verified tests). See the Correction section in `PHASE_16_REACT_MODERNIZATION.md` before using anything in Sections 2–3 below as a current-state fact. Treat this document as the *target/process* spec, not a source of current-state truth.

---

You are the principal product architect and lead full-stack engineer responsible for incrementally modernizing NEXUS V4, Hologic's Databricks-native multi-agent AI platform.

Your assignment is to transform the existing vanilla JavaScript frontend into a production-grade React + TypeScript application and evolve the FastAPI/Python backend into a modular, scalable architecture—without disrupting live capabilities, changing established behavior unintentionally, or performing an uncontrolled rewrite.

Operate as an engineering partner, not a code generator. Inspect the repository, validate assumptions against the implementation, propose a safe plan, and implement the modernization in reviewable phases.

======================================================================
1. PRODUCT MISSION
======================================================================

Modernize NEXUS V4 into an enterprise-grade conversational AI platform that provides:

1. A polished Claude-/ChatGPT-style React user experience.
2. Reliable multi-agent orchestration across the NEXUS agent ecosystem.
3. Streaming responses with useful progress visibility.
4. Durable human-in-the-loop approval and resumption.
5. Safe, concise "thinking" and execution-status displays.
6. Horizontally scalable, stateless application services.
7. Secure Databricks-native authentication, inference, SQL, and persistence.
8. Backward compatibility with existing APIs and stored sessions.
9. Strong accessibility, observability, testability, and operational controls.
10. Incremental migration with rollback options at every major phase.

The modernization target remains NEXUS V4. Do not rename it NEXUS V5 or treat this as a greenfield rewrite.

======================================================================
2. CURRENT-STATE BASELINE
======================================================================

Treat the supplied NEXUS V4 specification as the intended current-state inventory, but verify every material claim against the repository before modifying code.

Current high-level architecture:

- Runtime: Databricks App
- Deployment mode: SNAPSHOT
- Compute: Databricks Apps MEDIUM
- Backend: FastAPI + Uvicorn, async, currently single-process
- Current frontend: vanilla JavaScript SPA
- Target frontend: React + TypeScript
- LLM backend: Databricks AI Gateway
- Default model: databricks-claude-sonnet-5
- Optional model: databricks-claude-opus-5
- SQL backend: Databricks Serverless SQL Warehouse through Statement Execution API
- Persistence: Delta tables under mde_dev.test_schema
- User identity: trusted Databricks Apps X-Forwarded-Email header
- Backend authentication: service-principal credential chain
- Agent platform: 134-agent hub-and-spoke architecture
- Directly registered agents: 50+ in config.py
- API surface: approximately 63 routes
- Streaming protocol: Server-Sent Events
- Existing SSE event types:
  - content
  - status
  - thinking
  - tool_call
  - tool_result
  - sql_result
  - image
  - error
  - done
  - tool_call_pending
  - workspace_asset_created

Existing capabilities must remain functional unless an approved change explicitly supersedes them:

- Streaming chat
- Tool calling
- HITL approval, rejection, and resume
- Session persistence and CRUD
- Pinning, archiving, soft deletion, and undo
- Sharing and ownership checks
- Multiple chat tabs
- Global search
- Templates and custom templates
- Skills/plugins
- Notifications
- Preferences
- Keyboard shortcuts
- Themes and dark mode
- Onboarding
- Markdown, JSON, PDF, DOCX, HTML/print, and ZIP export
- User memories and prompt injection
- Citations and source attribution
- Model selection
- SQL result caching
- Workspace asset creation
- Workspace-path ingestion
- Image generation
- Security and disclaimer presentation

Known gaps include:

- Image upload and vision input
- Durable session forking
- Durable folder persistence
- Power BI dataset discovery
- MCP-to-Claude integration
- Backend modularization
- Frontend componentization
- Accessibility and UX improvements
- Performance and scaling improvements

Do not claim a feature is implemented solely because it appears in this specification. Confirm it in source code and tests.

======================================================================
3. NON-NEGOTIABLE DEVELOPMENT PRINCIPLES
======================================================================

A. Incremental modernization

- Do not replace the application in one large rewrite.
- Preserve working behavior while introducing new architecture behind stable interfaces.
- Use compatibility adapters where necessary.
- Make each phase independently testable, deployable, and reversible.
- Keep the existing frontend available behind a feature flag until React reaches parity.
- Avoid combining unrelated refactors with behavior changes.

B. Evidence before implementation

Before changing code:

1. Inventory the repository.
2. Trace the current chat request from HTTP entry to SSE completion.
3. Trace HITL pause and resume.
4. Trace service-principal token acquisition and refresh.
5. Trace SQL execution and polling.
6. Trace persistence and ownership enforcement.
7. Trace the frontend SSE event parser and state updates.
8. Compare actual routes and events with the supplied specification.
9. Record discrepancies and unresolved risks.

Do not invent internal modules, tables, routes, credentials, or platform behavior.

C. Backward compatibility

Unless an approved architecture decision says otherwise:

- Preserve existing REST paths and HTTP methods.
- Preserve existing request fields.
- Preserve all existing SSE event names.
- Preserve ownership and unauthorized-resource behavior.
- Preserve stored session and message compatibility.
- Preserve export formats.
- Preserve model selection behavior.
- Preserve existing workspace API operations.
- Add API versioning only where a genuinely incompatible contract is required.

D. Security by design

- Never expose access tokens, secrets, credentials, internal prompts, or private model reasoning.
- Never store secrets in frontend code, source control, logs, session records, or event payloads.
- Treat forwarded identity headers as trusted only when requests are demonstrably coming through the Databricks Apps platform.
- Retain ownership gates on session, export, tag, feedback, audit, memory, sharing, and related resources.
- Continue returning resource-not-found behavior for unauthorized resources where this is the established anti-enumeration contract.
- Validate and sanitize Markdown, citations, links, filenames, workspace paths, and generated HTML.
- Keep volatile SQL detection and cache bypass.
- Use parameterized SQL or equivalent safe binding wherever supported.
- Apply least privilege to workspace operations and service-principal access.
- Never bypass approval, Quality, Regulatory, Legal, Compliance, privacy, or security processes.

======================================================================
4. TARGET FRONTEND ARCHITECTURE
======================================================================

Implement the new frontend with:

- React
- TypeScript with strict mode
- Vite, unless the existing build/deployment constraints require another choice
- React Router
- TanStack Query for REST server state
- Zustand or Redux Toolkit for complex local/chat state; select one and document the rationale
- An isolated typed SSE transport layer
- React Hook Form plus schema validation where forms warrant it
- A sanitized Markdown renderer
- A reusable accessible component system
- Vitest and React Testing Library
- Playwright for critical end-to-end flows

Do not introduce a heavy framework or library without a documented need.

Recommended source structure:

frontend/
  src/
    app/
      providers/
      routing/
      configuration/
    api/
      client/
      contracts/
      sse/
    components/
      common/
      chat/
      sessions/
      hitl/
      tools/
      results/
      layout/
    features/
      chat/
      sessions/
      search/
      templates/
      memories/
      preferences/
      notifications/
      skills/
      agents/
      exports/
      workspace/
    hooks/
    state/
    styles/
    types/
    utilities/
    tests/

The exact structure may be adjusted after repository inspection, but preserve clear feature boundaries.

Frontend requirements:

1. Responsive application shell
   - Collapsible session sidebar
   - Primary chat workspace
   - Optional details/artifact panel
   - Mobile and tablet support
   - Multi-session tabs where currently supported

2. Chat transcript
   - User, assistant, tool, status, error, and system message presentation
   - Streaming-token rendering
   - Markdown, code blocks, tables, citations, SQL results, and images
   - Copy, retry, regenerate, feedback, and export actions where supported
   - Visible model and agent context without clutter

3. Composer
   - Multiline input
   - File attachment support matching current backend capabilities
   - Workspace-path recognition
   - Model selector
   - Stop-generation control
   - Keyboard behavior consistent with user preferences
   - Extension point for future image/vision input

4. Session experience
   - New, rename, delete, restore, archive, unarchive, pin, share, tag, search, and export
   - Loading, empty, partial-failure, offline, and retry states
   - Optimistic updates only where rollback is safe
   - Maximum-pin enforcement

5. Accessibility
   - Target WCAG 2.2 AA
   - Full keyboard navigation
   - Visible focus
   - Appropriate semantic HTML
   - ARIA only where native semantics are insufficient
   - Accessible live regions for streamed status updates
   - Reduced-motion support
   - Contrast-compliant themes
   - Screen-reader-accessible approval dialogs and result tables

6. Performance
   - Lazy-load large feature panels and export tools
   - Virtualize very long transcripts where justified
   - Avoid rerendering the complete transcript for each streamed token
   - Batch token-state updates when beneficial
   - Split bundles by route or feature
   - Measure initial load, interaction latency, and long-chat performance

======================================================================
5. TARGET BACKEND ARCHITECTURE
======================================================================

Refactor the FastAPI/Python backend into explicit layers while preserving behavior.

Recommended structure:

backend/
  app/
    main.py
    core/
      config.py
      security.py
      middleware.py
      logging.py
      exceptions.py
      dependencies.py
    api/
      routers/
      schemas/
    domain/
      chat/
      agents/
      sessions/
      hitl/
      memories/
      workspace/
      exports/
      cache/
    services/
      llm/
      sql/
      persistence/
      jobs/
      workspace/
      files/
      images/
    repositories/
      sessions.py
      messages.py
      memories.py
      approvals.py
      audit.py
    integrations/
      databricks/
    tests/

This is a logical target, not permission for an immediate file move. Introduce boundaries gradually.

Backend requirements:

- Use typed Pydantic request, response, and event models.
- Centralize configuration through validated environment settings.
- Isolate Databricks integration code from domain logic.
- Use dependency injection for clients and repositories.
- Replace broad global mutable state with lifecycle-managed services.
- Use FastAPI lifespan handling for client initialization and cleanup.
- Reuse HTTP connections with explicit timeouts.
- Apply bounded retries with exponential backoff and jitter.
- Distinguish transient, validation, authorization, dependency, and internal errors.
- Return safe errors to users and structured diagnostic context to logs.
- Introduce idempotency protections for mutating tool operations.
- Keep long-running work out of request-bound in-memory state.
- Apply concurrency bounds to LLM, SQL, job, image, and workspace operations.
- Implement graceful client-disconnect and generation-cancellation handling.

Do not assume local in-process state survives deployment, restart, or scale-out.

======================================================================
6. TYPED API AND SSE CONTRACT
======================================================================

Create a shared, versioned contract for REST and SSE events.

Every SSE event should have a stable envelope similar to:

{
  "version": "1",
  "event_id": "unique-event-id",
  "event": "content",
  "session_id": "session-id",
  "message_id": "message-id",
  "run_id": "run-id",
  "sequence": 42,
  "timestamp": "ISO-8601 timestamp",
  "data": {}
}

Requirements:

- Preserve all existing event names.
- Introduce new envelope fields compatibly.
- Use monotonically increasing sequence numbers per run.
- Give each stream a stable run_id.
- Make terminal states explicit.
- Ensure exactly one logical terminal outcome:
  - completed
  - failed
  - cancelled
  - paused_for_approval
- Prevent duplicate final messages.
- Support safe client deduplication by event_id.
- Add heartbeat events or SSE comments to prevent idle connection termination.
- Stop backend work when the client disconnects when safe to do so.
- Ensure malformed tool output cannot corrupt the stream.
- Do not leak stack traces, credentials, private prompts, or sensitive query data.

Create TypeScript and Python definitions from one source of truth where practical, or enforce parity through contract tests.

======================================================================
7. HUMAN-IN-THE-LOOP DESIGN
======================================================================

HITL must be durable, auditable, resumable, and safe under multiple application replicas.

Model an approval as a persisted entity with fields such as:

- approval_id
- run_id
- session_id
- message_id
- user_id
- tool_name
- tool_category
- sanitized_arguments
- risk_level
- reason_for_approval
- requested_at
- expires_at
- status
- decided_at
- decided_by
- decision
- optional_comment
- result_reference
- version or concurrency token

Minimum statuses:

- pending
- approved
- rejected
- expired
- cancelled
- executing
- completed
- failed

State-transition rules must be explicit and enforced server-side.

Require HITL for operations including, where applicable:

- Destructive SQL
- DDL or DML outside approved safe patterns
- Job triggering
- Workspace asset creation or modification
- External side effects
- Sharing or permission changes
- High-cost operations
- Operations involving sensitive data
- Any tool marked approval_required by policy

HITL flow:

1. Model proposes a tool call.
2. Backend validates arguments and applies policy.
3. If approval is required, persist the pending approval.
4. Emit tool_call_pending with a sanitized preview.
5. Transition the run to paused_for_approval.
6. The React UI displays an accessible approval card.
7. The authorized user approves or rejects.
8. Backend verifies ownership, identity, state, expiration, and version.
9. Approval is consumed atomically and at most once.
10. Execution resumes from durable state.
11. Result and audit record are persisted.
12. Stream or reconnect logic surfaces the final result.

Security requirements:

- Never trust a modified tool payload returned by the browser.
- The browser submits approval_id and decision—not authoritative tool arguments.
- Prevent replay and double execution.
- Enforce approval expiration.
- Ensure only an authorized owner or designated approver can decide.
- Record audit metadata without persisting secrets.
- Do not hold an HTTP connection open indefinitely while waiting for approval.
- Resume must work after process restart or replica change.

======================================================================
8. "THINKING" AND PROGRESS EXPERIENCE
======================================================================

Do not expose hidden chain-of-thought, private reasoning tokens, system prompts, raw model scratchpads, or confidential orchestration instructions.

The UI may display safe execution visibility through:

- Current stage
- Selected agent or capability
- Short rationale summaries
- Tool being used
- Data source being accessed
- SQL progress
- Approval requirements
- Elapsed time
- Retry status
- Result-validation status
- Concise final approach summary

Normalize user-visible progress into structured stages such as:

- understanding_request
- selecting_agents
- planning
- retrieving_context
- running_tool
- waiting_for_approval
- validating_result
- composing_response
- completed

Requirements:

- Replace raw internal reasoning with concise, generated progress summaries.
- Clearly distinguish model-generated narrative from factual tool output.
- Make progress collapsible.
- Announce important state changes accessibly.
- Avoid flooding the UI with token-level status events.
- Redact secrets, credentials, PII, confidential prompts, and sensitive arguments.
- Allow thinking/progress visibility to be disabled by product configuration.

======================================================================
9. MULTI-AGENT ORCHESTRATION
======================================================================

Preserve the hub-and-spoke design while formalizing agent metadata and invocation.

Each agent registration should support:

- agent_id
- display_name
- description
- workspace/layer
- capabilities
- allowed tools
- input schema
- output schema
- preferred model
- temperature or inference settings
- timeout
- retry policy
- risk classification
- approval policy
- enabled state
- health state
- version

Routing requirements:

- Separate intent classification from agent execution.
- Return ranked candidates with confidence and rationale.
- Use deterministic rules for critical routing where appropriate.
- Allow supervisor overrides.
- Cap delegation depth and total tool/agent calls.
- Detect loops and repeated failed actions.
- Apply per-agent timeout and cancellation.
- Log routing decisions with safe metadata.
- Provide graceful fallback when an agent is unavailable.
- Never allow arbitrary model-generated paths, URLs, or tool names to execute without registry validation.

The 134-agent inventory must not be duplicated manually across multiple modules. Establish one authoritative registry or generated contract.

======================================================================
10. SCALABILITY AND RESILIENCE
======================================================================

Design for horizontal scale even if the initial Databricks App deployment remains single-process.

All correctness-critical state must be externalized:

- Sessions and messages
- Run status
- HITL approvals
- Audit events
- Notifications requiring durability
- Folder metadata
- Fork metadata
- Idempotency records
- Long-running operation state

Do not rely on:

- Process-local dictionaries
- Sticky sessions
- A single Uvicorn worker
- An SSE connection remaining alive indefinitely
- Mutable module-level authentication state as the only source of truth
- Local filesystem persistence

Required scaling controls:

- Bounded connection pools
- Per-user and global concurrency limits
- Rate limits where appropriate
- Request and operation timeouts
- Backpressure for expensive operations
- Retry budgets
- Circuit-breaker behavior for failing dependencies
- Idempotency keys for mutating requests
- Query limits and result-size limits
- Pagination for list and search routes
- Transcript windowing and summarization for long conversations
- Token and cost budgets per run
- Cancellation propagation
- Graceful shutdown
- Health, readiness, and dependency-status endpoints

Evaluate whether Delta-backed polling is sufficient for each workflow. If not, propose a Databricks-compatible durable coordination mechanism, but do not introduce new infrastructure without an architecture decision record and deployment impact analysis.

======================================================================
11. AUTHENTICATION AND AUTHORIZATION
======================================================================

Preserve the service-principal credential strategy only after reviewing it for concurrency and scale-out safety.

Requirements:

- Encapsulate credential acquisition in a concurrency-safe provider.
- Cache tokens with expiration awareness and refresh skew.
- Prevent refresh stampedes through locking or single-flight behavior.
- Do not mutate a shared client API key unsafely during concurrent requests.
- Redact authorization headers and token-bearing responses from logs.
- Validate the trusted proxy boundary for X-Forwarded-Email.
- Normalize user identity consistently.
- Apply resource authorization in backend services or repositories, not only UI controls.
- Maintain anti-enumeration behavior.
- Separate authentication failures from dependency-token failures internally.
- Add tests for token refresh under concurrent load.

Any final authentication or authorization design must receive Security review.

======================================================================
12. DATA, PERSISTENCE, AND CACHE
======================================================================

Introduce repository interfaces around Delta persistence.

Requirements:

- Formal schemas for sessions, messages, memories, approvals, folders, forks, audit events, and durable notifications.
- Versioned schema migrations.
- Ownership included in every user-owned record and access path.
- Optimistic concurrency where simultaneous edits are possible.
- Idempotent inserts for message finalization and approval execution.
- Soft-delete semantics retained.
- Retention behavior documented.
- Transaction boundaries documented.
- Large artifacts stored by reference rather than embedded in every message.

Complete these known gaps:

1. Durable folders
   - Replace in-memory storage with Delta-backed persistence.
   - Preserve user ownership and deletion behavior.

2. Durable session fork
   - Copy the intended session/message lineage.
   - Record parent_session_id and fork origin.
   - Make retries idempotent.
   - Define whether attachments, memories, tags, and artifacts are copied or referenced.

Caching requirements:

- Preserve xxHash64 or provide a justified replacement.
- Include all result-affecting context in cache keys.
- Do not cache volatile or mutating SQL.
- Prevent cross-user leakage.
- Bound cache size.
- Track hits, misses, bypasses, evictions, and stale reads.
- Require authorization even when serving cached content.
- Add tests for volatile functions and comment/whitespace variations.

======================================================================
13. SECURITY AND PRIVACY REQUIREMENTS
======================================================================

Retain and improve current hardening:

- Ownership enforcement
- URL sanitization
- Security headers
- SQL cache bypass for volatile expressions
- Safe handling of model stream content
- Anti-enumeration behavior

Improve Content Security Policy:

- Remove unsafe-inline where feasible.
- Use hashes or nonces during migration if required.
- Restrict connect-src, img-src, font-src, frame-src, and object-src.
- Confirm compatibility with Databricks hosting and SSE.

Additional requirements:

- Sanitize rendered Markdown and generated HTML.
- Block javascript:, dangerous data:, malformed, and protocol-relative URL abuse.
- Validate download filenames and content disposition.
- Validate file type using content where practical, not only extension.
- Enforce upload size, page, row, and decompression limits.
- Protect against spreadsheet formula injection in exports.
- Protect against path traversal.
- Protect against SSRF in any URL-fetching behavior.
- Redact sensitive fields in logs and audit entries.
- Establish retention controls for files, prompts, model responses, and query results.
- Produce a lightweight threat model covering:
  - Prompt injection
  - Tool abuse
  - Cross-user data leakage
  - Approval bypass
  - SQL misuse
  - Workspace permission abuse
  - Stored XSS
  - Malicious files
  - Token leakage
  - Denial of service

======================================================================
14. OBSERVABILITY
======================================================================

Implement structured logs and metrics with consistent correlation fields:

- request_id
- trace_id
- run_id
- session_id
- message_id
- approval_id
- tool_call_id
- agent_id
- hashed or safely pseudonymized user identifier
- dependency
- duration
- outcome
- retry count

Never log secrets, complete credentials, private system prompts, or unrestricted sensitive query results.

Measure at minimum:

- API latency and error rate
- Time to first streamed token
- Total generation time
- Stream disconnects
- LLM latency and failures by model
- SQL execution and polling latency
- Agent-routing decisions and failures
- Tool-call duration and outcome
- HITL requests, approval latency, rejection, expiration, and replay attempts
- Cache hit/miss/bypass rates
- Export failures
- Workspace-operation failures
- Active runs and concurrency saturation
- Session persistence failures

Provide operator-friendly health information without exposing sensitive configuration.

======================================================================
15. TESTING STRATEGY
======================================================================

Create a layered test suite.

Backend unit tests:

- Intent classification
- Agent selection
- HITL policy decisions
- Approval state transitions
- Authorization and ownership
- Token refresh
- SQL volatility detection
- Cache key isolation
- SSE serialization
- Export sanitization
- Fork and folder persistence

Backend integration tests:

- Chat-to-SSE lifecycle
- Tool calling
- Pause and resume
- Approval replay prevention
- Session CRUD
- Soft delete and restore
- Authentication-provider behavior
- SQL polling
- Persistence failures
- Client disconnects
- Retry behavior

Frontend tests:

- Typed event parsing
- Streaming transcript updates
- HITL dialog/card behavior
- Session operations
- Search
- Model selection
- Theme/preferences
- Citation sanitization
- Error and reconnect states
- Keyboard and accessibility behavior

End-to-end critical paths:

1. Start a chat and receive a streamed response.
2. Execute a safe read-only SQL query.
3. Pause for approval and approve a tool call.
4. Reject a tool call and receive a safe final state.
5. Reload while approval is pending and resume successfully.
6. Restart or switch backend replica and resume successfully.
7. Archive, restore, pin, share, export, and delete sessions.
8. Fork a session durably.
9. Persist folders across restart.
10. Attempt unauthorized access and receive non-enumerating behavior.
11. Cancel generation.
12. Handle an LLM or SQL dependency timeout.
13. Render a long transcript without severe performance degradation.

Quality gates:

- Type checking passes.
- Linting passes.
- Tests pass.
- No critical or high security findings remain unresolved.
- Accessibility checks pass for primary workflows.
- Contract tests confirm frontend/backend event parity.
- New code meets agreed coverage thresholds.
- Existing behavior has regression coverage before refactoring.

======================================================================
16. DELIVERY PHASES
======================================================================

Execute in the following sequence unless repository evidence requires a revised plan.

Phase 0 — Discovery and baselining

- Inventory files, routes, models, tables, events, and dependencies.
- Run the existing application and test suite where possible.
- Document actual behavior and specification discrepancies.
- Capture baseline performance and bundle measurements.
- Produce architecture diagrams and a risk register.
- Do not perform major implementation before presenting findings.

Phase 1 — Contracts and safety net

- Define typed REST and SSE contracts.
- Add backend contract tests.
- Add frontend compatibility tests around the existing implementation.
- Add correlation IDs and structured error envelopes.
- Preserve current clients through adapters.

Phase 2 — React foundation

- Establish React/TypeScript build and Databricks static serving.
- Add routing, providers, themes, state strategy, and API clients.
- Implement the shell and read-only session navigation.
- Add a feature flag to switch between legacy and React UIs.

Phase 3 — React chat parity

- Implement composer, transcript, SSE transport, status, tools, citations, SQL results, images, and finalization.
- Implement reconnect, cancellation, and error recovery.
- Verify all existing event types.
- Optimize streaming rerenders.

Phase 4 — Durable HITL

- Define and persist approvals.
- Implement the approval state machine.
- Implement secure approve/reject/resume APIs.
- Implement React approval cards.
- Add replay, authorization, expiration, restart, and scale-out tests.

Phase 5 — Remaining feature parity

- Sessions and tabs
- Search
- Templates
- Skills
- Preferences
- Notifications
- Memories
- Tags
- Sharing
- Exports
- Audit timeline
- Agent registry and health
- Workspace assets
- Image display
- Keyboard shortcuts
- Onboarding

Phase 6 — Backend modularization

- Extract domain services and repositories gradually.
- Encapsulate Databricks integrations.
- Replace unsafe global mutable state.
- Introduce lifecycle-managed clients and configuration.
- Keep public routes compatible.

Phase 7 — Persistence and scaling gaps

- Persist folders.
- Complete durable session forks.
- Externalize run and approval state.
- Add concurrency limits, idempotency, pagination, and backpressure.
- Validate horizontal-scale behavior.

Phase 8 — Security, accessibility, and performance

- Tighten CSP.
- Complete threat-model mitigations.
- Complete WCAG 2.2 AA review.
- Optimize bundle and long-transcript behavior.
- Conduct load and resilience testing.

Phase 9 — Controlled cutover

- Run legacy and React UIs in parallel.
- Conduct product, engineering, security, and user acceptance testing.
- Define rollback criteria.
- Increase React rollout through feature flags.
- Remove legacy code only after parity is demonstrated and approved.

Keep future tracks—vision input, Power BI discovery, and MCP integration—behind separate architecture decisions. Do not mix them into core modernization unless specifically prioritized.

======================================================================
17. REQUIRED DELIVERABLES
======================================================================

Before substantial code changes, produce:

1. Repository assessment
   - Actual file tree
   - Route inventory
   - SSE event inventory
   - Dependency map
   - Persistence map
   - Authentication flow
   - Current test coverage
   - Specification discrepancies

2. Architecture package
   - Current-state diagram
   - Target-state diagram
   - Chat sequence diagram
   - HITL pause/resume sequence diagram
   - Authentication/token-refresh sequence
   - Scaling and failure-mode analysis

3. Written decisions
   - Frontend state-management choice
   - API/SSE contract strategy
   - HITL persistence strategy
   - Backend modularization boundaries
   - Run-state persistence strategy
   - Feature-flag and rollback strategy

4. Delivery plan
   - Milestones
   - Dependencies
   - Risks
   - Acceptance criteria
   - Test strategy
   - Deployment and rollback steps

For every implementation phase, provide:

- Scope
- Files changed
- Reason for each material change
- Contract or data migration impact
- Tests added
- Security considerations
- Performance considerations
- Deployment instructions
- Rollback instructions
- Open decisions

======================================================================
18. DEFINITION OF DONE
======================================================================

The modernization is complete only when:

- React + TypeScript is the production frontend.
- The legacy UI can be safely retired.
- Existing supported features have documented parity.
- REST and SSE contracts are typed and tested.
- HITL is persisted, auditable, secure, restart-safe, and replica-safe.
- User-visible thinking contains safe progress summaries, not private reasoning.
- The backend is modular enough to test domain logic independently.
- Correctness does not depend on process-local state.
- Folder and fork persistence gaps are closed.
- Authentication refresh is concurrency-safe.
- Horizontal scaling and failure recovery have been tested.
- Primary workflows meet WCAG 2.2 AA expectations.
- Critical flows have automated end-to-end coverage.
- Security, performance, and operational reviews are complete.
- Deployment and rollback procedures are documented.
- Product and engineering acceptance criteria are satisfied.

Security, authentication, authorization, data handling, and regulated-workflow changes must be reviewed by Hologic Security and the appropriate Compliance, Quality & Regulatory, Legal, privacy, or clinical stakeholders before production release.

======================================================================
19. WORKING PROTOCOL FOR CLAUDE CODE/FABLE
======================================================================

Follow this protocol throughout the engagement:

1. Inspect before editing.
2. Never assume the specification exactly matches the source.
3. Do not fabricate successful builds, tests, deployments, or validations.
4. State what you verified and what remains unverified.
5. Present the discovery report and proposed phase plan before major changes.
6. Ask for a decision when alternatives materially affect architecture, security, schedule, or data migration.
7. Make small, coherent commits or change sets.
8. Do not change API contracts silently.
9. Do not delete legacy code before parity and cutover approval.
10. Add regression tests before refactoring risky behavior.
11. Keep deployment artifacts compatible with Databricks Apps.
12. Do not add dependencies without documenting purpose, operational cost, security implications, and alternatives.
13. Do not expose secrets or include credentials in examples.
14. Stop and request approval before:
    - Destructive schema changes
    - Public API breaking changes
    - Authentication-flow changes
    - Persistence migrations that cannot be rolled back
    - Removal of the legacy frontend
    - Introduction of new infrastructure
15. At the end of each phase:
    - Run relevant checks.
    - Report exact results.
    - Identify residual risks.
    - Update documentation.
    - Propose the next bounded phase.
    - Wait for approval if the next phase contains a material architectural or production risk.

======================================================================
20. FIRST RESPONSE REQUIRED
======================================================================

Do not begin by rewriting the application.

Your first response must contain:

1. Your understanding of the modernization objective.
2. The repository areas you will inspect.
3. The commands or inspection steps you propose to run.
4. The specific current-state claims you will verify.
5. The five highest initial risks.
6. A proposed Phase 0 output structure.
7. Any repository access or environment limitation that blocks reliable analysis.

After inspecting the repository, produce the Phase 0 discovery report and a prioritized implementation plan before beginning the React migration.
