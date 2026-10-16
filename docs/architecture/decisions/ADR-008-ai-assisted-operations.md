# ADR-008 – AI Support for Development and Operations

Created: September 25, 2026. Phase 5 technical choices accepted October 15, 2026. OpenAI EU retention terms accepted October 16, 2026; superseded for this installation by explicit Global-project acceptance later that day.
Status: **Accepted design; implementation and acceptance evidence remain open**.

## Context

AI should support operations and development. The platform has relevant context: applications, deployments, telemetry, configuration, and architecture.

## Decision

Place the AI layer above the Platform API. It explains platform context, correlates incidents, and supports changes. A general-purpose model-hosting service is not a prerequisite for this roadmap.

An external model may receive selected project-scoped telemetry and documentation needed for an authorized AI request. The Platform API first enforces the caller's project permissions, limits the requested time window and result size, and minimizes and redacts the context. The accepted initial policy permits only redacted Public and Internal context; Confidential data requires a separate explicit project handling decision and provider controls before transmission. Restricted values, including credentials and tokens, must never be sent. Model output has no authority to retrieve additional projects or perform writes.

Start evaluation with an OpenAI API model, provisionally `gpt-6.1-sol`, through a provider-neutral model adapter. Keep prompts, tool definitions, and evaluation cases independent of OpenAI-specific SDK objects so another provider or a local model can be substituted and judged against the same acceptance corpus. Model availability and account access must be checked before implementation. Do not opt in to provider training on project content; use `store: false` for every OpenAI Responses API request. On October 16, 2026, the owner explicitly accepted use of their **Global** OpenAI project, superseding the initial EU-only deployment decision. Global storage/processing at `https://api.openai.com/v1` is permitted for the same minimized, redacted Public and Internal context. The earlier acceptance of default abuse-monitoring retention applies: standard provider abuse-monitoring logs may be retained for up to 30 days; `store=false` does not establish Zero Data Retention. See the [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data). No EU residency or Modified Retention approval is claimed for this project. Reassess provider terms before expanding data classes or changing providers.

Select Global explicitly with `OPENAI_DATA_REGION=global` and `OPENAI_GLOBAL_PROCESSING_ACCEPTED=true`; an API key is still required. EU remains an optional mode and the compatibility default: `OPENAI_DATA_REGION=eu` requires verified EU project/processing eligibility and an executed Modified Retention amendment. It never silently falls back to Global. The owner's Global acceptance does not set those EU verification flags or prove model/account access. The region maps to a fixed official endpoint; arbitrary endpoint URLs are not accepted. Global uses Standard model pricing; the EU cost estimate includes its regional uplift.

Use LangChain for the provider-neutral model interface and the bounded read-only investigation loop. Keep tool definitions typed and execution inside the authorized Platform API. Do not expose an MCP endpoint in the initial Phase 5 implementation; a future external client may use an MCP adapter over the same controlled tools. The model can propose a change but cannot execute it. Deterministic platform operations perform writes only after an explicit approval.

An authenticated human with current project `manage` authority may approve an AI proposal, including one they requested themselves in this single-responder lab. Automation credentials cannot approve. Approval is explicit, single-use, valid for 15 minutes, and bound to the canonical diff, target, and base revision. Recheck authority and revision immediately before execution, audit the decision and outcome, and reject stale, expired, reused, or changed approvals.

Instrument AI runs through the Phase 4 OpenTelemetry path with bounded agent, model-call, and tool-call spans. Allow only safe names, durations, token counts, outcomes, and opaque run IDs; do not capture prompts, responses, tool arguments/results, or retrieved project content. Raw traces remain operator-only. A separate project-scoped AI-run view shows safe status and evidence references. Durable approval and outcome records live outside the 24-hour trace store.

## Alternatives

A logs-only assistant lacks context. Direct infrastructure access bypasses authorization and domain boundaries. Fully automatic remediation increases the potential impact before evaluation and operational evidence are available.

## Consequences

Tool access, retrieval, and telemetry must respect project boundaries. Minimize and redact sensitive data. Hypotheses require evidence and explicit data gaps. A changed plan requires renewed approval. Enforce initial investigation limits of eight read-tool calls, 90 seconds, and $0.25 estimated model cost; tune them only through recorded evaluation and a design update.

## Validation

Expand the incident corpus beyond the initial four scenarios with known-cause and insufficient-evidence variants. Require zero cross-project disclosures, secret disclosures, and unapproved writes; at least 80% correct, sourced diagnosis on known-cause cases; and safe abstention on every insufficient-evidence case. Measure latency, tool use, model cost, and trace coverage. Re-run the same corpus against a second provider adapter to prove that the platform contracts are provider-neutral.


**Owner-directed scheduling update, October 16, 2026:** Second-provider setup,
adapter work and evaluation are deferred to [Phase 7 package 7.10](../../maintainers/delivery/plans/phase-7-anytime-leftovers.md#ai-model-provider-leftovers),
unscheduled and non-gating for Phase 5. The provider-neutral contract remains;
this deferral does not claim second-provider interoperability passed.

Details: [Phase 5](../../maintainers/delivery/plans/phase-5-ai-operations.md), [Security](../../maintainers/delivery/history/security-design.md).
