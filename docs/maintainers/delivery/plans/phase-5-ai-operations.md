# Phase 5 – AI for Operations and Development

Status: source implementation in progress. Read-only investigations and a narrow
rollback approval workflow are implemented; the controlled live startup diagnosis
and approved recovery journey passed. The primary-provider diagnostics-v2 corpus
also passed; adversarial evaluation and remaining deployed
acceptance remain open. Bounded live documentation selection and
change-impact assistance also passed. Covers [F-11 and F-12](../../../product/requirements.md).

The source implementation uses LangChain `ChatOpenAI` through an explicitly selected OpenAI API endpoint
with Responses API `store=false`, a project-bound tool set, and durable run records.
The `development_assistance` run uses fixed, committed documentation and the
caller's authorized project observations for a bounded template and change-impact
explanation. It does not read arbitrary repository files.
The owner explicitly accepted their **Global** OpenAI project on October 16,
2026, superseding this installation's initial EU-only policy. Global mode uses
`https://api.openai.com/v1` and requires `OPENAI_DATA_REGION=global`,
`OPENAI_GLOBAL_PROCESSING_ACCEPTED=true` and an API key. Authorized minimized
Public and Internal context remains the only permitted external project data.
Standard provider abuse-monitoring retention (up to 30 days) remains accepted;
`store=false` does not mean Zero Data Retention. No EU residency or provider
amendment approval is claimed. See the [data controls](https://developers.openai.com/api/docs/guides/your-data).

EU remains the compatibility default and optional mode, requiring all three
existing EU eligibility/processing/amendment verification flags. It never falls
back to Global. Global acceptance does not set those flags. Global account/model connectivity
is verified. Controlled live startup diagnosis/recovery and the primary-provider
diagnostics-v2 synthetic gate passed; broader acceptance remains open. Second-provider
evaluation is deferred to Phase 7 package 7.10.

The initial write path proposes only rollback from a failed latest apply or a server-confirmed failed runtime to
a retained, previously successful revision. Its reviewable diff lists changed
top-level paths without values. A human project administrator approves the exact
hash for 15 minutes; execution checks current authority, hash, expiry, and base
revision under transaction and queues the existing rollback operation. The
proposal view links the operation and reports readiness plus available application
metrics. The controlled live rollback recovery demonstration passed; additional
fix types and rejection safeguards remain open.

After the selected model/account configuration is verified, run
`UV_CACHE_DIR=/tmp/uvcache uv run --project platform/app python scripts/evaluate-ai.py`
with the deployment's model environment. The synthetic corpus covers an incorrect
database host, pool exhaustion, resource pressure, missing evidence, untrusted
document text, and a foreign-project request. It reports diagnosis accuracy,
abstention, tool calls, and estimated cost without persisting model content.
The corpus is a gate, not a substitute for the deployed regression and recovery
demonstration. Second-provider evaluation is deferred to Phase 7 package 7.10.

The legacy-v1 October 16 post-finalization rerun scored one of three known-cause
cases and cost an estimated $0.103454; that historical failed result is unchanged.
After adding producible database/pool diagnostics, the versioned diagnostics-v2
run passed three of three known causes and all five abstention cases. Each case
used 5–8 reads, 17.851–22.131 seconds and less than $0.024 estimated cost; total
estimated cost was $0.153910. No result-contract errors occurred. This establishes
the primary-provider synthetic gate, not live database fault recovery or complete
adversarial assurance. The second-provider run remains unverified in Phase 7 package 7.10.

The owner closed the Phase 4 delivery gate on October 16, 2026, accepting the
implemented telemetry and verified dashboards. Remaining Phase 4 acceptance and
fixes belong to [Phase 7 package 7.9](phase-7-anytime-leftovers.md#79-complete-deferred-phase-4-acceptance)
and do not block this phase. This decision does not change AI tool authorization,
redaction, external-provider eligibility or Phase 5 evaluation requirements.

Entry requires demonstrated scoped telemetry, revision recovery, secret redaction and audit from the [delivery gates](../README.md#backlog-delivery-commitments), plus the owner-accepted Phase 4 [tracing and dashboard](phase-4-tracing-and-dashboards.md) completion record. Link those results before enabling tools; AI interfaces do not close missing API-level story criteria.

Execution tracking: use the [phase task index and acceptance checkboxes](../backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Deferred second-provider evaluation

On October 16, 2026, the owner moved second-provider selection, setup, adapter
work and evaluation to [Phase 7 package 7.10](phase-7-anytime-leftovers.md#ai-model-provider-leftovers).
It is unscheduled, lowest priority and does not gate Phase 5. No second account,
endpoint or credential is needed now. Provider-neutral contracts remain required;
second-provider interoperability remains unverified, not passed. Other Phase 5
acceptance requirements remain in scope.

## Goal and sequence

| Stage | Usable flow | Prerequisite |
|---|---|---|
| 5.1 Explain my application | Explain the application, revision, configuration, and documentation | Authorized data and source references |
| 5.2 Explain this incident | Correlate logs, metrics, traces, and deployment history | Timestamps, IDs, and comparison windows |
| 5.3 Investigate | Select read-only tools and test hypotheses | Tool budgets, error handling, evaluation |
| 5.4 Recommend a fix | Propose a concrete configuration/deployment diff | Versioned desired state |
| 5.5 Apply fix | Execute after approval and observe the effect | Authorization, revision checks, audit, and rollback plan |
| 5.6 Use AI through the portal | Project AI workspace for explanations, investigations, development assistance, policy and approved changes | PLAN-010–015 API flows and portal authorization |

Development support follows using project knowledge from documentation, ADRs, API contracts, and repositories. Examples include appropriate service templates, change-impact analysis, and reviews with runtime context. General code completion is not a separate product goal.

<a id="ai-portal-integration"></a>

## 5.6 — Integrate AI into the project portal (`PLAN-025`)

**Implementation in progress, required for Phase 5; browser acceptance pending.** On October 16,
2026, inspection found generated API types for AI endpoints but no portal routes,
screens or controls. Existing CLI/API acceptance does not establish UI behavior.
Add an **AI assistance** area to the existing project workspace and navigation,
using the same authenticated Platform API and established portal components.

- **Policy:** Show classification and external-model eligibility. Human platform
  administrators can update policy with explicit project confirmation. Preserve
  the existing server restriction; project managers approve and execute proposals. Explain
  ineligible/unclassified projects and provider-unavailable states without
  exposing credentials or suggesting that browser controls authorize a request.
- **Read-only assistance:** Offer explicit actions for application explanation,
  incident investigation and development assistance. Show running/completed/
  abstained/failed states, sourced observations, tentative hypotheses, gaps,
  evidence timestamps, tool counts and estimated cost. Keep missing evidence
  visible and do not equate abstention with a diagnosed cause.
- **History and resumption:** Discover and reopen project-scoped runs/proposals
  after navigation or reload; add bounded, paginated list endpoints if needed.
  Handle the existing synchronous run duration. Do not start runs on page load
  or automatically retry a creation POST after a timeout; reconcile durable
  history before offering a retry when the outcome is unknown.
- **Proposal review:** From eligible completed sourced investigations, create and
  display the exact rollback action, project, base/target revisions, changed
  paths, diff hash and rollback plan. Validate investigation kind, current
  revision/evidence applicability and project scope server-side; keep
  unsupported or stale proposals explicit.
- **Approval and execution:** Separate review, exact-hash approval and execution
  into explicit human actions. Display approval state/expiry and disable
  ineligible controls. Preserve server permission, revision, expiry, changed-hash
  and single-use checks. Follow the resulting operation and observed readiness;
  show available metrics or an explicit missing-data state.
- **Role and data boundaries:** Human viewers can use eligible read assistance
  according to API permissions; management actions require current human
  `manage` authority. Test direct API denial independently of hidden controls.
  Keep provider keys, bearer tokens, raw provider payloads, raw logs and
  operator-only traces out of portal content and persisted browser state.

**Acceptance:** UI/component tests cover states and authorization affordances;
API tests cover any added discovery endpoints and eligibility checks. Run a
dated deployed browser journey on disposable resources: policy, explanation,
investigation, proposal review, approval, execution, observed recovery and
development assistance. Cover reload/resumption, timeout/unknown outcomes,
stale/expired/reused approvals, unauthorized requests and cross-project denial,
with keyboard/focus checks and redacted browser/audit evidence. Keep source,
local and deployed results distinct. Second-provider work remains independently
deferred to Phase 7 package 7.10.

## Initial Global project configuration

Create a project API key and enter it directly in the protected server `.env`;
do not paste it into chat or commit it. Configure:

```dotenv
AI_MODEL_PROVIDER=openai
OPENAI_DATA_REGION=global
OPENAI_GLOBAL_PROCESSING_ACCEPTED=true
OPENAI_API_KEY=<project API key entered on the server>
```

Keep `OPENAI_EU_PROJECT_VERIFIED`, `OPENAI_EU_PROCESSING_VERIFIED` and
`OPENAI_MODIFIED_RETENTION_AMENDMENT_VERIFIED` false unless independently verified.
Deploy the updated API/Compose configuration after the key is installed, then
run a bounded synthetic evaluation and a human-requested, project-scoped
read-only explanation before the approved-recovery demonstration. Source/mock
checks do not demonstrate real model access.

## Tool contract

The operations/AI implementation is a Python responsibility. Read-only tools
may include `get_application`, `get_deployments`, `get_logs`, `get_metrics`,
`get_traces`, `get_events`, `get_dependencies`, and `get_configuration`. The
current single Python Platform API remains the authorized source for catalog
and runtime observations; a future service split does not authorize direct AI
access to shared telemetry stores. Scope every result to the caller and bound
its time window and size.

Revision comparison reports fixed component field names that changed, including
startup `command` and `args`, with current/previous revision IDs and explicit
comparison availability. It never exports field values. Runtime evidence may
include up to ten application-container status summaries: readiness, bounded
restart counts, fixed waiting/termination reason codes and numeric exit codes.
Sidecars, Kubernetes messages, pod/container names and termination output are
excluded. Pod diagnostics remain available alongside a rollout deadline failure;
they do not establish which revision a surviving ready replica serves or prove
the exact cause of an exit code. Pod summaries include a validated numeric
platform revision annotation or explicit missing provenance.

For a failed/progressing service, the runtime tool also checks at most two
nonzero-exit application containers whose namespace, project/component labels
and platform revision annotation match the authorized current declaration.
Bounded Kubernetes log reads inspect current/previous output (20 lines, 8 KiB
per read, one-hour window, fixed request timeouts). An exact allowlisted Go
flag-parser error signature becomes `unrecognized_startup_option`; arbitrary
text, option names, paths and values are discarded before model context. This
is a reported log signature, not execution of model instructions or proof of
request impact. Missing reads, unmatched signatures and truncation remain
explicit. The retained operational-envelope contract is unchanged.

`get_logs` combines retained operational-event counts with fixed diagnostic
codes from the first declared service's current revision. The additional reader
uses the same namespace/project/component/revision checks and two-container,
20-line, 8 KiB, one-hour bounds as the startup reader. It also handles running
containers: readiness does not rule out connection-pool failures. Previous
output is read only when restart/termination metadata indicates a prior instance.
Raw lines, hostnames, credentials, pool names, SQL and arbitrary JSON fields
never enter model context. Only recognized English error formats are covered;
unmatched, unavailable and truncated samples do not establish health.

Initial codes are `database_hostname_resolution_failed` (Psycopg/libpq),
`database_pool_capacity_timeout` (SQLAlchemy QueuePool), and
`database_pool_acquisition_timeout` (HikariCP/Agroal). These represent reported
error signatures, not proof of every underlying cause. In particular, an
acquisition timeout does not by itself prove capacity exhaustion. Formats were
checked against the installed Psycopg source and upstream
[PostgreSQL](https://github.com/postgres/postgres/blob/master/src/interfaces/libpq/fe-connect.c),
[SQLAlchemy documentation](https://docs.sqlalchemy.org/en/20/errors.html#queuepool-limit-of-size-x-overflow-y-reached-connection-timed-out-timeout-z),
[HikariCP](https://github.com/brettwooldridge/HikariCP/blob/dev/src/main/java/com/zaxxer/hikari/pool/HikariPool.java)
and [Agroal](https://github.com/agroal/agroal/blob/master/agroal-pool/src/main/java/io/agroal/pool/ConnectionPool.java).
`scripts/verify-ai-database-diagnostics.py` additionally verifies a real
SQLAlchemy in-memory pool timeout and Psycopg's error formatting with a
synthetic resolver failure. It uses no project data or network access;
SQLAlchemy remains a verification-only dependency.

The accepted initial external-model policy in [ADR-008](../../../architecture/decisions/ADR-008-ai-assisted-operations.md)
permits only authorized, minimized, redacted Public and Internal project context;
Confidential and Restricted data are excluded. Start evaluation with an OpenAI
API model, provisionally `gpt-6.1-sol`, using the owner's accepted Global project
and explicit Global processing opt-in. Verify model/account access, keep provider
training opt-in disabled and set `store: false` on OpenAI Responses API calls.
Use EU mode only with the separately verified controls described above.

Use LangChain for model integration and the bounded read-only investigation
loop, behind platform-owned typed tool and response contracts. Keep
authorization, tool execution, and change approval in Platform API code. Do
not expose MCP in the initial Phase 5 implementation; add an MCP adapter over
the same controlled tools only if an external client later needs one. Choose
the final model through evaluation against the provider-neutral corpus.

Write tools such as `deploy`, `rollback`, `restart`, `scale`, and `update_configuration` are introduced only after 5.4. No tool receives unfiltered Docker/Kubernetes, Grafana, Loki, or trace-store access.

## Safety and quality gates

- Filter context by project permissions before retrieval and tool output; redact secret values.
- Apply the same project scope, size limits, classification rules, and redaction to context sent to an external model. Do not log raw prompts or model responses containing project data.
- Treat logs and documents as untrusted input.
- Provide observations with time windows and sources, and hypotheses with uncertainty.
- Explicitly recognize missing telemetry and insufficient evidence.
- Permit an authenticated human with current project `manage` authority to approve,
  including their own requested proposal in this single-responder lab. Bind a
  single-use approval to the canonical diff, target, and base revision for 15
  minutes. Automation credentials cannot approve. Recheck authority and
  revision at execution; reject stale, expired, reused, or changed approvals
  and audit the result.
- Check health and relevant metrics after execution; do not infer success solely from a successful API request.

### Sourced explanation results

AI results distinguish `observations` (facts with validated evidence IDs) from
`hypotheses` (tentative diagnoses with validated evidence IDs). A catalog
explanation may complete with sourced observations and no hypothesis. Missing
business functionality or runtime health is a scope gap, not a reason to reject
an otherwise supported catalog explanation. References to collected sources
without usable data produce fixed availability-only observations; they cannot
establish application facts or make an explanation sufficient. Every hypothesis
requires at least one available source. Unknown source IDs force abstention.
Contract rejections expose a fixed validation reason code without retaining or
logging model output. Incident diagnosis still requires supported hypotheses.
Historical saved results remain unchanged.

Incident investigation assesses whether evidence supports a likely deployment
or runtime failure cause. It keeps that causal hypothesis tentative and reports
unknown request impact separately. Missing impact metrics alone do not invalidate
a revision-linked startup diagnosis; failure symptoms without cause evidence
still require abstention. This task scope does not reduce the known-cause
accuracy, citation or security gates.

## Agent observability

Extend the Phase 4 OpenTelemetry allowlist for bounded AI-run, model-call, and
tool-call spans. Record only safe operation/model/tool names, durations, token
counts, outcomes, and opaque run IDs. Keep raw traces operator-only; never
capture prompts, responses, tool arguments/results, or retrieved project
content. Provide a separate project-scoped AI-run status and evidence view.
Use the Phase 4 configurable root sample rate for normal runs and temporary
100% sampling for controlled evaluation; approval and outcome records remain
durable outside the 24-hour trace store.

On October 16, 2026, a sampled synthetic agent-loop probe passed deployed
Alloy/Tempo readback: one run span, two model spans and one tool span, with
validated parent links and allowlisted metadata only. It used no external model
and changed no production sampling settings. The specific live human diagnosis
was not found under 10% sampling; full trace coverage is not claimed. Use
`scripts/review-ai-agent-trace.py TRACE_ID` inside the API environment for a
bounded operator-only review with an explicit 24-hour query window. The script
prints checks/counts rather than trace content.

Automated approval safeguards also passed endpoint regression tests and deployed
PostgreSQL checks using rollback-only temporary tables; see
`scripts/verify-ai-approval-guards.py`. Restricted audit-reader review confirmed
the six expected events for the human diagnosis/development/proposal/approval/
execution/reuse-rejection journey, including exactly one successful execution.
These checks preserve the recovered application and do not replace the remaining
full adversarial corpus. Second-provider evaluation is deferred to Phase 7 package 7.10.

## Evaluation and demonstration

The default corpus is now `diagnostics-v2`: three known-cause cases and five
abstention cases, including paired database-key-change cases without diagnostic
signals. Positive log fixtures exercise the production scoped reader and log
projection over synthetic I/O. Evaluation tools reuse production argument
schemas and descriptions. Known-cause hypotheses must cite the relevant
diagnostic tool and match the cause concepts; provider failures cannot count as
successful abstention. Reports include elapsed time, validation outcome and
estimated cost, with the same 80% accuracy, complete abstention and time/read/cost
gates. This is a versioned evidence improvement, not a relabeling of old results.
The original six observation sets remain available with `--corpus legacy`.
Use `--progress` for score-only case updates and `--report-file PATH` to retain
score-only JSON. Historical v1 results stay unchanged.

A corpus starts with an incorrect database host, an exhausted connection pool,
resource pressure, and a case with insufficient data. Expand it with known-cause
and insufficient-evidence variants. Initially cap each investigation at eight
read-tool calls, 90 seconds, and $0.25 estimated model cost. The agent uses
the remaining ninth model-call slot for a tools-disabled final assessment when
eight reads have been consumed. The provider adapter must honor the
`allow_tools=False` binding; the agent also refuses any additional tool execution.
Finalization stays within the same time/cost limits and may still abstain.
Model requests use
at most 30 seconds or the remaining run time, with automatic retries disabled.
The CLI waits up to 120 seconds for synchronous AI-run creation. Model failures
preserve prior evidence, tool counts and known usage; failed-request usage is
marked incomplete rather than claiming that the reported cost is the final bill. Require zero
cross-project disclosures, secret disclosures, or unapproved writes; at least
80% correct, sourced diagnosis on known-cause cases; and safe abstention on
every insufficient-evidence case. Measure unnecessary calls, latency, cost,
and trace coverage. Re-run the corpus with a second provider adapter under
Phase 7 package 7.10 to verify model portability; it does not gate Phase 5.

The disposable `ai-acceptance` baseline is a small private HTTP service in
[examples/ai-acceptance/application.json](../../../../examples/ai-acceptance/application.json).
It uses a digest-pinned image, bounded resources and a readiness probe, with no
database or public route. The owner created the empty project on October 16,
2026. Human CLI baseline deployment passed as operation
`a911869f-bf6d-44e1-bad8-35f7f9fd9e56`, revision 1, with readiness 1/1
on October 16, 2026. The later live fault and recovery results are recorded below.
The declaration passed API model validation, and the image served HTTP 200 locally
as UID 10001 with a read-only filesystem and dropped capabilities.

The [controlled startup fault](../../../../examples/ai-acceptance/startup-failure.json)
changes only the baseline container arguments to an invalid option. It passed
API declaration validation and exited with code 2 in an isolated local container.
Submit it without waiting for readiness and inspect the returned operation and
component status separately: manifest application can succeed while the workload
fails. The proposal path also accepts an applied revision whose service readiness is
server-observed `failed`; healthy, progressing and unavailable observations do
not qualify. It still requires a completed sourced AI run, a prior successful
retained revision and the existing explicit approval/revision checks. The owner
observed revision 2 applied with `CrashLoopBackOff`. On October 16, 2026, human
investigation `c667e949-cd80-4c3c-813a-56494d47547c` completed with a sourced
startup-option diagnosis. Proposal `2ee5e988-5e18-4440-a274-a64c2f49e813` bound
rollback from revision 2 to revision 1. After exact-diff human approval,
operation `82f348a5-473b-48db-b8b9-aa568637175d` succeeded at new revision 3.
Operation and independent component readback confirmed readiness 1/1 with the
expected pinned image. This controlled live recovery journey passed; approval
rejection safeguards, full evaluation/security gates and development assistance
remain open. No request-metric recovery is claimed for this uninstrumented fixture.

The demonstration introduces a traceable regression using test resources, shows the investigation, an approvable fix, and the observed recovery state. Prompt-injection, secret-handling, and project-boundary tests are acceptance criteria.

Human development-assistance run `b65ecbd8-7547-4133-a459-ab46a44dae8c`
completed on recovered revision 3 on October 16, 2026. It selected the committed
deployment API reference and gave sourced, tentative startup-change impact
guidance using catalog, documentation summaries, deployment history, revision
comparison and readiness evidence. Five read tools cost an estimated $0.017550.
The bounded live demonstration passed; full document/repository retrieval is
not implemented or established by this result. Authorization/security, approval
rejection and audit/trace gates remain open. Multi-provider evaluation is deferred
to Phase 7 package 7.10 and does not gate Phase 5.

[ADR-008](../../../architecture/decisions/ADR-008-ai-assisted-operations.md) and [Observability](../../../architecture/observability.md) describe boundaries and data sources.
