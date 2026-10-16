# Delivery backlog and acceptance criteria

Status: open delivery requirements and authoritative task/evidence register. The [development plan](README.md) assigns delivery gates. Story criteria were migrated from the former archive; implementation findings and verification records are consolidated below. No story or task is certified complete by these documentation migrations.

## Conventions and scope

- **Developer:** a user who deploys and manages applications within authorized projects.
- **Operator:** a user who administers the platform, its capacity, and its security.
- **Project:** the boundary for application resources, configuration, and access.
- **Application:** one or more cooperating components, such as a web service and a worker,
  each of which can have its own deployment.
- **Scheduled component:** a one-shot application component started by the platform from
  a declared recurring cron schedule; it is not a continuously running service.
- **Deployment credential:** a revocable OIDC machine identity and platform grant used
  by CI; it is distinct from a person's token and from infrastructure credentials.
- Story IDs are permanent references. `DEV` identifies developer stories and `OPS`
  identifies operator stories. New stories receive the next unused number in their
  category; reordering or removing stories must not renumber existing IDs.
- Acceptance criteria describe observable outcomes. They do not prescribe a portal,
  CLI, or API implementation.

The platform currently targets trusted workloads on a single host. These stories
do not imply high availability or isolation suitable for hostile tenants.

## Task tracking

Each task belongs to exactly one phase or sub-gate; story IDs remain the overall acceptance gates. `DEV/OPS-xxx-Tnn` tasks inherit the story owner role in the [plan](README.md#backlog-delivery-commitments). `PLAN-nnn` tasks cover existing phase scope outside the original stories and take their owner from the phase work package. Assign named owners before work starts. IDs are permanent; moving a task changes its phase field, not its ID.

Top-level task checkboxes remain open where full acceptance is outstanding. Checked progress criteria below record narrower verified outcomes; they do not close the parent task or phase. Task evidence below distinguishes partial or absent source implementation, verified local checks, and operational acceptance. Close a task only after its listed outcome is verified, or record an explicit owner-directed acceptance exception that names every unverified outcome; record date, revision, environment, results and limitations beside it. Link shared checks by evidence ID. Update implementation findings here when code changes; other documents link here rather than maintain a separate status assessment. Close a story only when every original acceptance criterion passes. A Phase 3 design decision does not close deferred implementation tasks.

Scheduled phase gates are **1A → 1B → 1C → 2A → 2B → 2C → 3 → 4.1–4.4 → 5.1–5.6**. Dependencies below identify ordering within a phase. Phase 2A adds multi-service and scheduled components; Phase 2B adds CI deployment credentials; Phase 2C covers the current-platform capabilities. Phase 3 delivers general developer experience, Phase 4 adds tracing and Grafana dashboards, and Phase 5 adds AI operations. Optional Phase 6 architecture expansion is unscheduled. [Phase 7 anytime leftovers](plans/phase-7-anytime-leftovers.md) is displayed last, has the lowest priority, and may be worked on independently when capacity allows; it does not gate Phases 3–5 or optional 6. Its unfinished task outcomes remain open. Concrete energy-system declarations and domain acceptance remain externally owned. Component attribution in initial diagnostics uses the single implemented component; rerun those checks when the model expands.

**Gate status, October 16, 2026:** Phase 1A is complete. Its three scheduled tasks are checked complete; ADR-011, ADR-016, and ADR-017 record the accepted lab limitations. Phase 1B is complete under its recorded owner-directed alert-delivery exception. Phase 1C is complete as of October 3, 2026: all ten tasks are checked with live evidence (EV-30 to EV-37), and the unit-tested-only items and the not-yet-run access/audit drill are recorded owner-accepted limits in the Phase 1C audit below. Phase 2A passed its deployed component acceptance suite on node-01 (EV-38 and EV-39); database-row preservation, backup-inventory, and representative capacity measurements are owner-accepted deferred checks. Phase 2B is accepted under its owner-directed acceptance exception: its basic deployed automation suite passed, while the expiry, controlled identity-provider-outage, and deployed backup-coverage checks are deferred. **Phase 2C is complete:** protected live drills passed for components, retirement, PostgreSQL recovery, data-aware rollback, capacity admission, egress policy, and failure signals; the owner confirmed notification receipt (EV-39 to EV-44). Remaining single-lab constraints are accepted limitations. **Phase 3 is complete by owner-directed source/local scope decision** at checkout `f7a8aff`; the unverified deployed journeys are named in the [completion record](history/phase-3-developer-experience.md#completion-record-october-15-2026). **Phase 4 is complete by owner direction** at baseline `4681e56`: implemented telemetry and owner-verified dashboards are accepted for delivery sequencing; remaining PLAN-021–024 checks and resulting fixes move to [Phase 7 package 7.9](plans/phase-7-anytime-leftovers.md#79-complete-deferred-phase-4-acceptance), unverified and non-gating. **Phase 7 is open and unscheduled:** it collects those acceptance leftovers in the [anytime plan](plans/phase-7-anytime-leftovers.md) and does not block Phases 4–5.

Phase 1A runs within the existing administrator-operated boundary; secrets and operational credentials remain protected. Phase 1B establishes individual authorization/audit before expanded self-service. From Phase 1B onward, every task introducing an endpoint, data surface or persisted state must include scoped authorization/revocation, secret redaction and audit checks and update backup coverage. Reassess the documented recovery procedure when recovery scope changes; [ADR-016](../../architecture/decisions/ADR-016-phase-1a-recovery-scope.md) excludes isolated recovery exercises from the current Phase 1A gate. These are part of that task's completion, not an unbounded extra phase. Release OPS-004-T01 with OPS-001-T01; later endpoints reuse the same boundary.

**Portal increment, October 13, 2026:** Owner-requested **PLAN-020** is accepted
for lab sequencing under the owner-directed exception recorded in its task note.
The owner observed the deployed application-access screens and an active policy,
but waived the deployed browser, approval, service-access, denial, and audit
journeys. This does not establish their behavior or close the remaining
PLAN-009/017/018/019 acceptance.

## Accepted lab validation approach

**Owner decisions, October 1, 2026:** [ADR-016](../../architecture/decisions/ADR-016-phase-1a-recovery-scope.md) omits new fresh-installation restore drills, backup/key failure exercises, and recurring full-restoration scheduling from Phase 1A. Previous isolated recovery results remain historical evidence. OPS-006-T03 is deferred and does not block the 1A gate. [ADR-017](../../architecture/decisions/ADR-017-phase-1a-retention-evidence-scope.md) omits elapsed-time proof of the full 14/8/6 retention horizon; it does not change the configured policy or claim that its complete retention history has been demonstrated. The next failed-backup notification exercise should use the existing installation with a bounded fault and recovery steps, preserving real backup data and verified-success history.

## Evidence conventions

The task notes below inherit **baseline B-2026-09-26**, inspected source revision `bbd509dd4bf3e3dbcb2094cfdaf92a35ab3100f8`. Findings were imported from the former alignment assessment, including its review of changes since `25c80743dc23991baeb5444444bbd79571bd93c3`. They are dated evidence, not a fresh assessment of HEAD. Documentation consolidation did not rerun implementation checks or live acceptance. The historical report and resolved documentation findings remain in Git history.

- **Source — partial:** a relevant implementation exists, but task behavior is incomplete. **Source — absent:** the requested workflow was not found. **Source — implemented** may be used only with concrete evidence for the full task behavior; it does not prove deployment.
- **Local — verified:** the linked check passed in the recorded environment, within its stated limits. A syntax check is not workflow acceptance. **Local — unverified:** no executed check establishes that task outcome.
- **Operational — accepted:** criterion-level evidence from a named environment demonstrates the required outcome. **Operational — unverified:** that evidence is missing. Every task is operationally unverified at the imported baseline; decision-only tasks need a recorded decision rather than a deployment.

“Open” is delivery status, distinct from implementation and verification. Where a task note names multiple IDs, the findings apply to each as specified; deferred extensions have no source implementation or local acceptance evidence. Local evidence IDs refer to the [verification register](#verification-register). As evidence changes, update the relevant task note, checkbox and record together; never silently turn an old test result into a current one.


## Documentation review September 27, 2026

Read-only implementation assessment of source revision `39ae809259ed4d9d7611af31dc2372cb2357639b`, followed by documentation changes. This supplements B-2026-09-26; it does not rewrite historical evidence or close task checkboxes. No live deployment, fault injection, mail delivery or recovery was performed in this review.

| Finding and source evidence | Documentation disposition | Remaining task/decision |
|---|---|---|
| [API](../../../platform/app/src/app/main.py) accepts `name/image/port/probe_profile`, ignores extras and returns synchronous 200; ApplicationSpec described a richer asynchronous contract | Added explicit current/target comparison, current provisioning diagram and ADR-012 | PLAN-001/002/003: versioned contract, reject unknown/unsupported input, durable revisions/jobs and concurrency |
| Same API uses one all-project token, PostgreSQL administrator and cluster-wide [controller RBAC](../../../infrastructure/kubernetes/controller.yaml); scoped role descriptions were target-only | Security page now states actual credential/authorization boundaries | OPS-001/004 and ADR-004: individual access/audit; no tenant permission claim |
| [Database provisioning](../../../platform/app/src/app/main.py) derives HMAC passwords but never changes existing SQL passwords; runtime login owns its database | ADR-013 records key recovery and coordinated rotation; future role separation remains proposed | DEV-003/010, PLAN-008 and ADR-003: rotation/adoption and separate identities |
| [Monitoring loop](../../../platform/app/src/app/monitoring.py) rebuilds files only; PUT/retirement share its global lock | Software/observability pages distinguish monitoring reconciliation from workload recovery | DEV-006/007 and PLAN-003: observed health and resumable provisioning |
| [Probe/retirement paths](../../../platform/app/src/app/main.py) now exist beyond the imported baseline; retirement acknowledges manual removal and retains SQL/spec | ADR-014 records durable catalog membership and disposable discovery; historical “deletion absent” evidence remains dated | DEV-011/OPS-008 remain open for actual deletion planning, audit and cleanup; OPS-007-T01 for live probes |
| [Prometheus](../../../infrastructure/monitoring/prometheus.yaml) now has five jobs; [Alloy](../../../infrastructure/monitoring/config.alloy) collects host logs, not attributed pod logs; Grafana has data sources only | Replaced mixed proposed/current observability table; corrected scrape inventory | DEV-004/005, OPS-003/007: logs, resource usage, PostgreSQL/app telemetry and scoped views |
| Backlog records selected backup RPO/RTO/retention and partial SMTP/backup receipt while summary pages still called all undefined/unverified | Requirements, infrastructure, topology and monitoring summaries now reference selected policy and current evidence | Full scenario acceptance and precise measurements remain open; historical checks are not promoted |
| [Backup runner](../../../operations/backup/scripts/backup-platform.py) implements exact readback, verified-only retention, service-stop recovery and independent backup state without an ADR | ADR-015 records bundle scope, exclusions and integrity/restore distinction; removed reference to deleted manual SQL helper | OPS-006/007: remaining failure, restoration and delivery criteria |
| Generic deployment/recovery text required new isolated environments and additional watchdog monitoring after owner decisions excluded them | Added ADR-010 scope to recovery/upgrade guidance and replaced stale watchdog-observer requirement with ADR-011 limitation | ADR-016 omits fresh-restore exercises from Phase 1A; independent watchdog observer is excluded, not an unfinished task |
| ADR-002 still called k3d proposed, ADR-005 suggested direct Docker checks, and ADR index rows 010/011 fell outside its table | Added dated implementation notes without rewriting accepted decisions; repaired index and added records 012–015 | New source-derived records require owner acceptance; language/provider/IAM choices retain existing status |

These ADR additions document implemented tradeoffs rather than infer owner approval. Existing accepted ADRs are preserved. Validation for this review (local checkout, Python 3.14.7):

- All 410 relative Markdown links, including heading fragments, passed across 50 documentation files.
- Shell syntax passed for 67 fenced examples in modified documents; the embedded catalog-reapply Python parsed successfully.
- Eleven existing manifest/discovery unit tests passed (`test_manifests.py` and `test_monitoring.py`), establishing the selected resource/discovery behavior only.
- `git diff --check` passed. Application source and deployment configuration were unchanged. API lifecycle tests were not rerun because FastAPI/Kubernetes/psycopg dependencies are absent from this interpreter; no live/integration tests were run.

## Phase task index

This index lists execution tasks, not story completion promises. Task details and checkboxes below are authoritative.

| Gate | Tasks |
|---|---|
| 1A | OPS-006-T01, OPS-006-T02, OPS-007-T01 |
| 1B | OPS-001-T01, OPS-001-T02, OPS-002-T01, OPS-004-T01 |
| 1C | DEV-002-T01, DEV-003-T01, DEV-003-T02, DEV-004-T01, DEV-005-T01, DEV-006-T01, DEV-007-T01, DEV-010-T01, DEV-011-T01, OPS-003-T01, PLAN-001 |
| 2A | DEV-001-T01, DEV-001-T02, DEV-001-T03, DEV-006-T02, DEV-011-T02 |
| 2B | DEV-012-T01, DEV-012-T02, DEV-012-T03 |
| 2C | DEV-004-T02, DEV-005-T02, DEV-007-T02, DEV-008-T01, DEV-009-T01, DEV-010-T02, OPS-003-T02, OPS-005-T01, OPS-005-T02, OPS-007-T02, OPS-008-T01, OPS-008-T02, PLAN-002, PLAN-003 |
| 3, complete | Owner-accepted developer-experience source/local milestones; open PLAN-006/007/008 outcomes remain in Phase 7 |
| 4.1, complete by owner exception | PLAN-021: tracing |
| 4.2, complete by owner exception | PLAN-022: Grafana dashboards |
| 4.3, complete by owner exception | PLAN-023: opt-in hosted-application metrics and framework dashboard templates |
| 4.4, complete by owner exception | PLAN-024: opt-in hosted-application tracing and scoped readback |
| 5.1 | PLAN-010 |
| 5.2 | PLAN-011 |
| 5.3 | PLAN-012 |
| 5.4 | PLAN-013 |
| 5.5 | PLAN-014 |
| 5 (after 5.5) | PLAN-015 |
| 5.6 | PLAN-025: AI portal integration and deployed browser acceptance |
| Optional 6 | PLAN-004, PLAN-005 |
| 7, anytime | PLAN-016, PLAN-009, PLAN-017, PLAN-018, PLAN-019, PLAN-006, PLAN-007, PLAN-008, the deferred deployed PLAN-020 portal journeys, and deferred PLAN-021–024 acceptance/fixes (7.9) in the [anytime leftovers plan](plans/phase-7-anytime-leftovers.md) |
| Deferred | DEV-002-T02, DEV-003-T03, DEV-008-T02, DEV-009-T02 |

### Phase 1C story-task audit (October 3, 2026)

Read-only review of the 1C tasks still open after PLAN-001 to PLAN-003, against the source at the audit commit and the evidence rows above. "Accepted" requires named live evidence for every criterion; nothing was run for this audit.

| Task | Verdict | What exists | Gap |
|---|---|---|---|
| DEV-006-T01 | Accepted (ticked) | Readiness snapshot, bad-image, stalled and unschedulable reasons | None for T01 |
| DEV-007-T01 | Done | Persisted operations with outcomes, safe repeat PUT, interrupted-worker reclaim (EV-13) | Closed: interrupted after database creation, repeat request, no duplicates, data and credentials intact (EV-29) |
| DEV-010-T01 | Done | Generated Secret with `PGHOST`/`PGUSER`/`PGPASSWORD`; `scripts/isolation.py` checks denied foreign and platform database access | Closed: isolation passed live (EV-27); write/read and data preservation across redeploy and restart passed live (EV-28) |
| DEV-011-T01 | Done | `GET /projects/{name}/retirement-preview` (removed objects, route, retained data, blockers, `scope_token`); `POST .../retire` with the token deletes the namespace, answers 202 while it terminates, rejects a stale token (409 `scope_changed`), persists a retained inventory (`project_retirements`) and audits request and completion (unit tests) | Closed live (EV-30); configuration is not in the preview (not yet a feature) |
| DEV-005-T01 | Done | `GET /projects/{name}/resource-usage` (`view` grant, audited): per-pod and total CPU/memory from the metrics API, state `ok`/`stale`/`missing`/`unavailable` with reason; live on node-01 (EV-31) | Stale, missing and unavailable states are unit-tested only, not provoked live |
| OPS-003-T01 | Done | Idle baseline measured and recorded (EV-32); system reserve confirmed: at least 8 GiB RAM, 2 CPUs and 50 GB disk kept free of projects | Owner decision October 3, 2026: no load run; the idle baseline stands as the baseline and no workload capacity is promised. Re-measure under load before sizing project quotas (OPS-005-T01, OPS-003-T02) |
| DEV-004-T01 | Done | `GET /projects/{name}/logs` (`view` grant, audited): timestamped lines with pod/container attribution, `tail` and `since_seconds` bounds, previous-run fallback, best-effort redaction, `ok`/`no_pods`/`no_output`/`unavailable` states; `scripts/log_drill.py`; live (EV-33) | Cross-project denial rests on the shared `view` grant check (unit tests); not shown live with a second scoped user. Redaction is best effort. Search, follow and terminated-instance retention are DEV-004-T02 |
| DEV-002-T01 | Done | `GET`/`PUT /projects/{name}/configuration` (`view`/`change` grants, audited with names only): validated values stored in the application spec so each change is a revision with `If-Match`, rollback and drift; 202 reports `rollout_required`; `activation` is observed from the Deployment (EV-34) | Single component only; secrets stay out (DEV-003) |
| DEV-003-T01 | Done | `GET`/`PUT`/`DELETE /projects/{name}/secrets` (`view`/`change` grants): write-only values held only in the project `app-secrets` Secret, injected as env vars, restart on change, names-only audit (EV-35) | Audit and foreign-project denial are unit-tested, not shown live |
| DEV-003-T02 | Done | Versioned rotation: previous value held unmounted until `confirm` after pod adoption, or `revert` (EV-37); secrets in the verified backup bundle (EV-36) | Client reconnection is not observable (adoption plus explicit confirm); restore of secrets is unit-tested only; previous values are not backed up |

**Gate audit, October 3, 2026 (documentation bullet):** the minimal API flow, deployment versions, installation parameters (EV-17), operational commands and failure responses are documented in the [runbook day-2 flow](../../operators/runbooks/application.md#day-2-application-flow) and the [platform README](../../../platform/README.md#api-reference); each flow has a live drill (EV-30, EV-33 to EV-37). Left for later by owner decision: live proof of denial for a user without grants and of the audit rows (`scripts/access_audit_drill.py`, written, not run), live stale/missing/unavailable telemetry states, `not_adopted`, fail-closed backup, and secret restore into a rebuilt cluster (unit-tested only; isolated recovery drills deferred under ADR-016).

Smallest route to closing the data-path part of 1C: run and record the isolation script, add a live write/read-and-redeploy drill (DEV-010-T01), then the interrupt-after-database-creation drill (DEV-007-T01). Configuration, secrets and logs (DEV-002/003/004) are new features.

## Developer stories

### DEV-001 — Deploy applications with multiple and scheduled components

As a developer, I want to deploy an application composed of multiple services and a cron-triggered component,
so that its services can cooperate internally and recurring work runs within one project.

Acceptance criteria:

- Each component can specify its own image, startup command, and resources; long-running services can also specify ports and replica count.
- Components can communicate through stable internal service names within the project.
- A scheduled component declares a validated cron schedule, runs to completion rather than continuously, and does not overlap a later trigger.
- Deployment results identify successful and failed components and explain failures.
- Updating one component does not require redeploying unchanged components.
- Status and logs distinguish long-running components and individual scheduled runs.

Phase tasks:

- [x] **DEV-001-T01 · 2A** — Finalize and publish the successor component schema, capability flags, migration/rollback rules, independent-update semantics, scheduled-run status, and the representative three-component capacity result. Prerequisites: Phase 1 gate. The capacity measurement is owner-accepted as deferred.
- [x] **DEV-001-T02 · 2A** — Implement named long-running services with separate images, commands, internal ports, resources and replicas; prove stable internal discovery, component-specific success/failure, independent updates, and lossless migration of existing specs/revisions. Prerequisites: DEV-001-T01. Database-row preservation is owner-accepted as deferred.
- [x] **DEV-001-T03 · 2A** — Implement a scheduled component with validated five-field cron/UTC scheduling, non-overlap, component/run status, logs and audit correlation; prove it reaches an internal service, exits, reports failure safely, and is included in backup and retirement inventories. Prerequisites: DEV-001-T02. Backup-inventory evidence is owner-accepted as deferred.

**Operational evidence EV-38 (October 4, 2026):** On node-01, `ansible-playbook -i ansible/inventory.yml ansible/test-platform-components.yml -e @/home/eseidinger/.local/state/developer-platform/platform-test-runner.json` passed for disposable run `components-1791143495`. The deployed controller checkout was based on `3f155e6` with the then-uncommitted configuration-preservation and expanded acceptance changes; the exact installation record revision was not retained. The suite migrated a legacy application to two ready internal services and two scheduled components, proved one scheduled internal-connectivity run succeeded without overlap, proved the other safely reported a failed run, verified component-scoped logs/status, invalid-cron rejection, API-only and scheduled-only update isolation, configuration and write-only-secret preservation, rollback, revision history, and retirement scope. Its cleanup retired the project and revoked its temporary administrator persona. The owner accepts deferral of database-row preservation across migration/rollback, backup-inventory evidence, and a representative capacity measurement. These limitations do not invalidate EV-38 but must be reconsidered before production-like capacity or recovery claims.


### DEV-002 — Configure application environments

As a developer, I want to manage non-secret environment variables for each component,
so that I can change application behavior without rebuilding its image.

Acceptance criteria:

- I can view, add, update, and remove variables for an authorized component.
- Invalid configuration is rejected with an actionable error before it is applied.
- Changes indicate whether a rollout is needed and when the new configuration is active.

Phase tasks:

- [x] **DEV-002-T01 · 1C** — Implement authorized configuration view/add/update/remove with validation before apply; report rollout requirements and observed activation for the single component. Prerequisites: OPS-004-T01; OPS-001-T01; PLAN-001.
- [ ] **DEV-002-T02 · Deferred** — Extend CRUD and activation reporting to independently addressed components; changing one component leaves others unchanged. Prerequisites: DEV-001-T02; DEV-002-T01.

**Task evidence (B-2026-09-26):** T01 — source absent, local unverified for user configuration CRUD/activation. The [API](../../../platform/app/src/app/main.py) accepts no ordinary environment settings; extra fields are ignored under the model default rather than rejected. EV-01 validates names/manifests, not configuration acceptance. T02 — deferred, source absent, local unverified.


### DEV-003 — Manage application secrets

As a developer, I want to manage secret environment variables separately from ordinary
configuration, so that applications can use credentials without exposing them.

Acceptance criteria:

- I can create, replace, and remove secrets and assign them to specific components.
- Stored values are not returned in ordinary configuration views, logs, or audit records.
- Unauthorized users cannot read or modify secrets.
- I can roll out a replacement secret and see which components have adopted it.

Phase tasks:

- [x] **DEV-003-T01 · 1C** — Implement separate secret create/replace/remove and authorized binding; prove values stay out of configuration views, logs and audit, and deny foreign-project read/write. Prerequisites: OPS-004-T01; OPS-001-T01; PLAN-001.
- [x] **DEV-003-T02 · 1C** — Version and rotate a secret; observe adoption and successful reconnection before revoking the old version; include the new secret state in backup coverage. Prerequisites: DEV-003-T01; DEV-006-T01; OPS-006-T02.
- [ ] **DEV-003-T03 · Deferred** — Assign and rotate secrets per component and report adoption for every affected component without disclosing values. Prerequisites: DEV-001-T02; DEV-003-T02.

**Task evidence (B-2026-09-26):** T01/T02 — source partial; generated [Secret bindings](../../../platform/app/src/app/manifests.py), redacted normal API responses/generic errors, and [cluster secret encryption](../../../scripts/cluster_config.py) exist. User secret objects/references, authorized CRUD, rotation/adoption and comprehensive redaction tests are absent; local acceptance unverified (EV-01/02 are limited foundations). Changing `DATABASE_KEY` changes derived passwords, but [database provisioning](../../../platform/app/src/app/main.py) only creates missing roles and does not update existing passwords: rotation must coordinate roles and Secrets. T03 — deferred, source absent, local unverified.


### DEV-004 — Inspect application logs

As a developer, I want to search and follow logs from my application components,
so that I can diagnose failures and understand their behavior.

Acceptance criteria:

- I can filter logs by project, component, instance, and time range.
- Log entries include timestamps and identify their source component and instance.
- I can follow new entries and access retained logs from terminated instances.
- Access is limited to authorized projects, and the available retention window is visible.

Phase tasks:

- [x] **DEV-004-T01 · 1C** — Collect timestamped single-component logs with project/component/instance attribution; demonstrate authorized failure diagnosis and cross-project denial. Prerequisites: OPS-004-T01; PLAN-001.
- [x] **DEV-004-T02 · 2C** — Add search, follow and project/component/instance/time filters; retrieve terminated-instance logs, show retention, and prove direct backend access cannot bypass authorization. Prerequisites: DEV-004-T01.

  **Accepted (October 5, 2026):** The authorized log endpoint supports bounded case-insensitive text search, exact pod-instance selection, component selection, and `after`/`before` timestamp filters. `next_cursor` supports client polling for new entries. Lines from listed `Succeeded`/`Failed` pods are marked `terminated`; the response makes kubelet retention explicitly `best_effort` and reports its terminal-instance count. Unit tests cover filters, cursor, terminal attribution, redaction and Kubernetes-query bounds. The owner accepts the existing provider-access boundary as the direct-backend control for this single-lab phase.

**Task evidence (B-2026-09-26):** T01 — source partial through [Alloy](../../../infrastructure/monitoring/config.alloy) host Docker JSON logs. Explicit Kubernetes application-log collection inside k3d and project/environment/revision attribution are absent, as are authorized log endpoints. T02 — source absent for the requested query/retention workflow. Local task acceptance is unverified for both; shared dashboards do not enforce project boundaries.


### DEV-005 — Inspect application resources

As a developer, I want to see my application's deployed resources and resource usage,
so that I can understand its topology and identify capacity problems.

Acceptance criteria:

- I can list deployments, instances, services, routes, and attached data services.
- I can compare CPU and memory usage with configured requests, limits, and project quotas.
- Unavailable metrics are identified explicitly, rather than displayed as zero usage.

Phase tasks:

- [x] **DEV-005-T01 · 1C** — Expose basic authorized resource and CPU/memory observations; explicitly label missing or stale metrics. Prerequisites: OPS-004-T01; PLAN-001.
- [x] **DEV-005-T02 · 2C** — List deployments, instances, services, routes and attached data services; compare actual CPU/memory with requests, limits and quotas, including missing-data tests. Prerequisites: DEV-005-T01; OPS-003-T02; OPS-005-T01.

  **Accepted (October 5, 2026):** `GET /projects/{name}/resources` returns an authorized safe topology inventory (deployments, instances, Services, routes, quotas, limit ranges, and the managed PostgreSQL attachment), declared container requests/limits, aggregate declarations across desired replicas, labelled live usage, and each applicable namespace quota's declared/hard/remaining comparison. Provider-unavailable state is explicit. Unit tests cover successful/unavailable inventory, aggregate math, quota comparison and usage wiring. EV-31 verifies live usage against Kubernetes metrics; EV-39 verifies the deployed multi-component topology, declared request and quota comparison. No additional manual acceptance is required for this task. Broader host/shared-service/storage capacity remains in OPS-003-T02.

**Task evidence (B-2026-09-26):** T01/T02 — source partial: infrastructure metrics and Kubernetes object-state collection exist, but authorized resource/metric endpoints, workload usage comparisons and missing-data behavior are absent. [Prometheus](../../../infrastructure/monitoring/prometheus.yaml) has no container resource-usage scrape; Grafana has data sources but no provisioned dashboards. Local workflow acceptance unverified; EV-04 establishes configuration only.


### DEV-006 — Track deployment health

As a developer, I want to see rollout progress and component health,
so that I know whether my application is ready to serve traffic.

Acceptance criteria:

- The platform distinguishes accepted configuration from a completed, healthy rollout.
- I can see desired and ready replica counts and the active image version for each component.
- Failed or stalled rollouts show diagnostic reasons, such as image pull or scheduling failures.

Phase tasks:

- [x] **DEV-006-T01 · 1C** — Separate accepted desired state from observed readiness; show desired/ready counts and active image; exercise bad-image, unready, stalled and unschedulable rollout reasons. Prerequisites: PLAN-001; OPS-004-T01.
  **Audit (October 3, 2026):** Accepted on live evidence: desired state is separate from observed readiness with desired/ready counts and active image (EV-13); bad-image `ErrImagePull`/`ImagePullBackOff` (EV-14); stalled rollout and unschedulable pods (EV-15); restart and repeat rollouts (EV-16, EV-18).
- [x] **DEV-006-T02 · 2A** — Report readiness, counts, active image and failures independently for each long-running component and report active/last-run state for each scheduled component, including mixed healthy/failed results. Prerequisites: DEV-001-T02; DEV-006-T01. Verified by EV-38.

**Task evidence (B-2026-09-26):** T01 — source partial: TCP probes and stored `provisioning/applied/failed` status exist. Synchronous PUT returns `200` after apply; `applied` does not mean ready, no observer updates it after rollout/dependency failure, and termination can leave `provisioning` until a repeated PUT. Local health acceptance unverified; the inspected smoke script waits for rollout but was not run in the baseline assessment. T02 — deferred, source absent, local unverified.

**Current progress (October 3, 2026):** Authorized operation status includes an on-demand Kubernetes readiness snapshot with desired/ready replicas, desired/Deployment images, active image references and IDs, and diagnostic reasons for image-pull, scheduling, and stalled rollouts. Readiness is separate from the durable operation apply outcome and is not persisted as ongoing project health. Local fixture tests cover the observation cases (EV-12); live bad-image, unready, stalled and unschedulable acceptance remains open.


### DEV-007 — Recover from failed changes

As a developer, I want to retry failed deployments and restore a previous configuration,
so that I can recover from unsuccessful changes.

Acceptance criteria:

- Repeating an unchanged deployment request does not duplicate resources or delete data.
- I can select and reapply a retained application configuration revision.
- Recovery reports its rollout status and any unavailable dependencies, including old secrets.
- Restoring application configuration does not implicitly revert database contents or migrations.

Phase tasks:

- [x] **DEV-007-T01 · 1C** — Persist operation outcomes and safe retries; interrupt after database creation, repeat the same request and prove no duplicated resources or lost data. Prerequisites: PLAN-001; DEV-010-T01.
- [x] **DEV-007-T02 · 2C** — Select/reapply retained revisions and observe recovery rollout; report missing old secrets/dependencies and prove application rollback does not revert database contents or migrations. Prerequisites: DEV-007-T01; DEV-003-T02; DEV-006-T01.
  **Accepted (October 5, 2026):** `GET /projects/{name}/revisions` lists retained revisions and `POST /projects/{name}/rollback` re-applies one (its stored spec and image digest) as a new revision through the normal deploy path. Each revision reports safe dependency state: database is retained/not rolled back, configuration is re-applied when stored, and application secrets are explicitly `current_only` because values are never revisioned. Unit tests cover the no-secret-disclosure report. EV-42 records the protected self-contained rollback drill: revision one was restored while a unique SQL marker and active write-only secret version 2 remained.

**Task evidence (B-2026-09-26):** T01 — source partial: database/role existence checks, deterministic credentials, server-side Kubernetes apply and a global PostgreSQL advisory lock support manual repeat PUT without intended database deletion. No persisted steps, automatic recovery worker or interruption acceptance exists. T02 — source absent: only the latest spec is retained; no revision selection, rollback or missing-secret dependency workflow. Both local acceptance results are unverified; EV-01 does not test durable recovery. PLAN-003 covers stale writes and concurrency hardening.


### DEV-008 — Scale application components

As a developer, I want to adjust component replicas and resource allocations,
so that I can match application capacity to demand.

Acceptance criteria:

- I can change replica counts and CPU and memory requests and limits per component.
- Changes that exceed project quotas are rejected with a clear explanation.
- If host capacity prevents scheduling, the platform shows the affected components and reason.

Phase tasks:

- [x] **DEV-008-T01 · 2C** — Change fixed replicas and CPU/memory requests/limits for one component; test explained quota rejection and host-capacity scheduling diagnostics. Prerequisites: PLAN-002; OPS-005-T02; DEV-006-T01.

  **Accepted (October 5, 2026):** Versioned component specifications support per-service replicas and CPU/memory requests/limits; the inventory reports their declared totals and quota comparison. Validation rejects a component rollout that exceeds the namespace pod/resource quota including rolling-update headroom before provider side effects. EV-39 verifies a two-replica API with explicit resources and an explained quota rejection. `GET /operator/capacity` exposes redacted request-admission accounting with explicit units; EV-43 proves an oversized rollout is rejected before side effects and the identical workload is admitted after capacity recovers. EV-15 supplies the retained unschedulable-workload diagnostic evidence. This closes developer-facing scaling/admission behavior, not physical-host capacity planning: k3d node allocatable values overlap on the single host and must not be treated as a measured workload promise.
- [ ] **DEV-008-T02 · Deferred** — Scale and allocate resources independently per component, retaining quota and scheduling failure attribution. Prerequisites: DEV-001-T02; DEV-008-T01.

**Task evidence (B-2026-09-26):** T01 — source partial through fixed [manifest](../../../platform/app/src/app/manifests.py) replica/resource settings and namespace quotas; configurable scaling/resource requests/limits and scheduling diagnostics are absent. EV-01 verifies selected fixed quota settings only, not scaling acceptance. T02 — deferred, source absent, local unverified.


### DEV-009 — Control application connectivity

As a developer, I want to configure public endpoints and request required outbound access,
so that users and components can reach the services they need.

Acceptance criteria:

- I can choose which components are public and see their assigned URLs and TLS status.
- Components without a public endpoint remain inaccessible through public ingress.
- Required external destinations can be declared and are subject to operator policy.
- Rejected connectivity changes explain which policy prevented them.

Phase tasks:

- [x] **DEV-009-T01 · 2C** — Implement declared public/private exposure and outbound destinations; show URLs/TLS state, explain policy denials, and verify public-to-private changes remove obsolete ingress. Prerequisites: OPS-005-T02; PLAN-001.

  **Accepted (October 5, 2026):** v1alpha2 service components are private by default and may declare one public HTTP service. The platform creates only that component's Traefik Ingress and matching NetworkPolicy allowance; removing the declaration deletes the stale Ingress during reconciliation. Unit tests cover private/public manifests and schema limits; `ansible/test-platform-components.yml` verifies both public-route creation and public-to-private route removal in authorized inventory. The owner accepts independently observed public TLS as outside this single-lab delivery gate; the API reports its intentionally non-authoritative TLS state as `unknown`.

  **Accepted (October 5, 2026):** Service components may declare up to five CIDR/TCP-port destinations. The Platform API validates every request against operator `ALLOWED_EGRESS_CIDRS` and `ALLOWED_EGRESS_PORTS`; default-empty or malformed policy fails closed, rejects requests before side effects, and approved destinations receive component-scoped NetworkPolicy egress rules. EV-44 records the self-contained egress drill passing with a denied destination and approved `1.1.1.1/32:853` connectivity, restoring the original policy afterward. `GET /projects/{name}/resources` exposes declared HTTPS URLs and deliberately labels TLS as `unknown` until independently observed. The existing component drill verifies public-to-private ingress removal; the owner accepts unobserved external TLS as outside this lab gate.
- [ ] **DEV-009-T02 · Deferred** — Control exposure and outbound policy per component; prove private components cannot be reached through public ingress. Prerequisites: DEV-001-T02; DEV-009-T01.

**Task evidence (B-2026-09-26):** T01 — source partial: all projects get a public Ingress, with [Caddy](../../../infrastructure/proxy/Caddyfile) edge forwarding to Traefik. Certificate authorization uses domain suffix and stored `applied` status, not observed health. Public/private transitions, declared egress, policy-specific errors and developer TLS-state reporting are absent. Local/live acceptance for DNS/ACME issuance/renewal, rejected names, outage behavior, forwarded headers and certificate-state recovery remains unverified; [ADR-009](../../architecture/decisions/ADR-009-edge-and-cluster-ingress.md) lists exercises. T02 — deferred, source absent, local unverified.


### DEV-010 — Use project data services

As a developer, I want to connect my application to a project database,
so that it can persist data without requiring database administration access.

Acceptance criteria:

- Authorized components receive connection settings through managed configuration and secrets.
- Project credentials cannot access another project's database.
- Redeploying application components preserves database contents.
- I can see data service availability and request recovery through the operator workflow.

Phase tasks:

- [x] **DEV-010-T01 · 1C** — Bind managed database settings/secrets; demonstrate application write/read, denied cross-project database access and data preservation across redeployment. Prerequisites: PLAN-001; OPS-004-T01; OPS-001-T01.
- [x] **DEV-010-T02 · 2C** — Expose data-service availability and a tracked recovery request; demonstrate operator review, a documented controlled recovery procedure, and a developer-visible outcome without exposing foreign-project data. Prerequisites: DEV-010-T01; DEV-006-T01.

  **Progress (October 5, 2026):** Authorized developers can inspect a safe PostgreSQL availability result and latest recovery outcome, and submit a bounded recovery category; platform administrators list and acknowledge/resolve durable requests. Unit tests cover availability, request creation and operator review. The protected `ansible/test-platform.yml` drill creates a request as a developer, acknowledges it as platform administrator, then verifies the viewer-visible outcome is credential-free. `ansible/test-platform-postgres-outage.yml` creates and retires its own disposable project/persona/workload, automates a guarded Compose PostgreSQL stop/start, accepts either safe authenticated `503` (authorization cannot reach PostgreSQL) or `DatabaseUnavailable`, verifies Platform API readiness failure/recovery, and checks the resolved redacted outcome; it always restores PostgreSQL. **Operational evidence (October 5, 2026):** the self-contained drill passed for `pg-drill-1791220461-48144`: PostgreSQL stopped, the protected API returned the safe outage response and `/readyz` failed, PostgreSQL was restored, the API and managed database recovered, the recovery request was resolved, and the project/persona cleanup completed. **Manual test need:** explicitly approve the protected service interruption. Application-specific database write/read still needs a data-capable disposable workload before it can be automated.

**Task evidence (B-2026-09-26):** T01 — source partial: [API provisioning](../../../platform/app/src/app/main.py) creates dedicated non-superuser logins/databases and bindings use `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`, not the draft configurable `DB_*` prefix. Each runtime login owns its database; runtime/migration/human role separation is absent. The provisioner uses PostgreSQL `postgres` and cluster-wide Kubernetes permissions. Database preservation and CONNECT restrictions exist in source, but application write/read and live isolation remain unverified; smoke uses `http-echo`, and isolation was inspected, not run. T02 — source absent and local unverified for developer availability/recovery requests. Resolve ADR-003 role separation when implementing the binding/recovery design.


### DEV-011 — Remove unused applications

As a developer, I want to remove applications I no longer need,
so that unused workloads stop consuming project resources.

Acceptance criteria:

- Before deletion, I can review the affected components, routes, and configuration.
- Deletion requires explicit confirmation and reports completion or partial failure.
- Persistent data is retained unless a separate, explicit data deletion is authorized.

Phase tasks:

- [x] **DEV-011-T01 · 1C** — Preview affected workload/routes/configuration and require explicit confirmation; invalidate changed scope, retain data by default, persist retained inventory, and expose retryable partial failure and audited completion. Prerequisites: DEV-007-T01; OPS-001-T01.
- [x] **DEV-011-T02 · 2A** — Extend retirement previews and retryable cleanup to every long-running and scheduled component; verify actual removals match confirmed scope, run resources are included, and data deletion remains separately authorized. Prerequisites: DEV-001-T03; DEV-011-T01. Verified by EV-38.

**Task evidence (B-2026-09-26):** T01 — source absent for application deletion, preview/confirmation, resumable cleanup and retained-resource inventory. Lab teardown is not a scoped application lifecycle. Local acceptance unverified; shell syntax in EV-03 does not test deletion safety. T02 — deferred, source absent, local unverified.


### DEV-012 — Deploy applications from CI with revocable credentials

As a developer, I want a dedicated machine credential for my CI pipeline,
so that it can deploy an application without storing my personal token or receiving project-administration privileges.

Acceptance criteria:

- A project administrator can create a named, expiring credential scoped to one project/environment and optionally one application; its secret is returned exactly once.
- CI exchanges the credential through the configured OIDC provider for a short-lived token, deploys a revision non-interactively, and observes the operation result.
- The credential can be rotated with bounded overlap and revoked without changing a person's access or another pipeline's credential.
- Revocation or expiry denies the next Platform API request, including a request made with a previously issued but still-unexpired access token.
- Cross-project access, credential/grant administration, secret-value reads, retirement, data deletion, and operator endpoints are denied.
- Credential creation, use, rotation, denial, expiry, and revocation are attributable in audit without exposing client secrets, bearer tokens, or authorization headers.

Phase tasks:

- [x] **DEV-012-T01 · 2B** — Finalize the provider-neutral deployment/test-automation credential API, empty-project lifecycle, OIDC administration adapter, machine-principal/grant model, permission matrix, expiry/rotation policy, one-time-secret and redaction rules, and failure states. Prerequisites: accepted Phase 2A gate; ADR-004; ADR-018.
- [x] **DEV-012-T02 · 2B** — Implement empty-project creation; authorized deployment/test-runner/test-persona lifecycle; Keycloak confidential-client integration; short-lived client-credentials authentication; immediate platform-grant denial; provider cleanup retry state; and audit coverage. Prerequisites: DEV-012-T01; OPS-001-T01; OPS-004-T01.
- [x] **DEV-012-T03 · 2B** — Run the portable machine-driven platform suite and prove empty-project first deployment, one-time disclosure, role and cross-project permissions, deploy/observe success, rotation, expiry, immediate revocation with an unexpired token, provider-failure recovery, cleanup, and complete redaction. Prerequisites: DEV-012-T02; DEV-006-T02. Expiry, controlled provider outage, and deployed backup-coverage checks are owner-accepted as deferred.

**Task evidence (October 4, 2026):** Source now includes empty-project creation; deployment, test-runner, and test-persona credential profiles; Keycloak confidential-client provisioning; one-time secret responses; per-request expiry/revocation checks; bounded rotation; fail-closed provider cleanup with automatic retry; and bootstrap plus repeatable Ansible playbooks. The deployed `test-platform.yml` suite passed against node-01: it created empty projects and personas, completed a first CI deployment, checked authorization boundaries, configuration/restart/rollback, bounded rotation, immediate revocation, and cleanup. `verify-platform-test-runner-expiry.yml` and `test-platform-identity-provider-outage.yml` automate the explicit expiry and provider-failure drills. **Owner-directed acceptance exception (October 4, 2026):** expiry, controlled identity-provider outage, and deployed backup-coverage validation are deferred for the current lab. The first requires a real one-day wait, the second deliberately stops Keycloak, and the third needs protected backup credentials. This closes DEV-012-T03 and Phase 2B for sequencing; it is not evidence that any deferred drill ran, and all three must be reconsidered before production-like credential-recovery claims.


## Operator stories

### OPS-001 — Perform security audits

As an operator, I want to review security configuration and privileged activity,
so that I can identify policy violations and investigate changes.

Acceptance criteria:

- I can inspect project permissions, workload security settings, and network policies.
- Audit records identify the actor, timestamp, action, target, and outcome of changes.
- I can filter and export records for a selected time range without exposing secret values.
- Audit retention and access restrictions are defined, and developers cannot alter audit records.

Phase tasks:

- [x] **OPS-001-T01 · 1B** — Implement durable redacted audit records for mutations, failures and grant changes; include actor/time/action/target/result and scope/revision/operation when available; define retention/tamper protection and enforce restricted access. Prerequisites: OPS-007-T01; OPS-006-T02.
- [x] **OPS-001-T02 · 1B** — Inspect project permissions, workload security and network policies; filter/export audit by time; prove developers cannot alter records and exports contain no secrets. Prerequisites: OPS-001-T01; OPS-004-T01.

**Task evidence (B-2026-09-26):** T01/T02 — source absent for durable actor-attributed audit, restricted inspection/export and retention/tamper controls; latest project status and generic logs are insufficient. Local acceptance unverified. Record authentication/denial/grant changes with mutations, and release the access boundary together with OPS-004-T01.

**Source update (October 2, 2026):** The Python baseline now defines an append-only `platform_audit.events` table, redaction, restricted writer/reader roles, a security-definer append function, and mutation/provisioning-failure/authentication-denial/grant-change hooks attributed to immutable OIDC principals. Restricted inspection/export, deployed backup coverage, and controlled live permission checks remain open. This update does not close OPS-001-T01 or T02.

**Local verification (October 2, 2026):** The fresh local lab successfully appended a controlled event through the restricted writer after the audit policy migration; a direct `INSERT` by that writer was denied. This verifies the live append/access boundary only. Actor-attributed endpoint outcomes, deployed backup coverage, and the remaining T02 controlled operator checks remain open.

**Source update (October 2, 2026):** Platform-admin-only `/operator/*` endpoints now inspect platform-owned project grants and the managed workload/network-security contract, and export a bounded, offset-bearing audit time window as JSON or CSV through the restricted audit-reader login. Exports are redacted again at read time and are capped at 31 days/10,000 events. `scripts/check-phase-1b-security.py` automates non-mutating administrator access, export-redaction, workload-policy, and optional developer-denial checks.

**Controlled lab acceptance (October 2, 2026):** Separate individual users completed the scoped role/cross-project matrix through the Keycloak PKCE portal. A platform administrator inspected project grants, managed workload security and network policy, and time-filtered redacted audit export; a developer was denied the operator surfaces. The prior restricted-writer check confirms direct audit-table insertion is denied. No token, password, subject ID, or audit-secret value was retained in shared evidence.


### OPS-002 — Receive security event notifications

As an operator, I want notifications about security-relevant events,
so that I can investigate and respond promptly.

Acceptance criteria:

- I can configure alert rules for authentication failures, access denials, and privileged changes.
- Notifications include severity, time, affected resources, and a reference to supporting events.
- I can configure and test a notification destination and see delivery failures.
- Repeated events are grouped to reduce duplicate notifications without hiding ongoing incidents.

Phase tasks:

- [x] **OPS-002-T01 · 1B** — Configure authentication-failure, denial and privileged-change rules; link severity/time/resources to supporting events; test destinations, delivery-failure visibility and grouping that preserves ongoing incidents. Prerequisites: OPS-001-T01; OPS-007-T01.

**Task evidence (B-2026-09-26):** T01 — source absent for security-event rules and evidence-linked notification workflow; no audit event model feeds it. Local acceptance unverified. General alert-rule files and watchdog mail fixtures (EV-07–10) are supporting infrastructure, not security-alert acceptance.

**Source update (October 2, 2026):** A restricted audit-reader collector publishes bounded, redacted Prometheus metrics for authentication failures, authorization denials, and successful membership changes. Rules preserve resource labels/severity, point operators to the latest durable audit-event ID, detect a stale collector and Alertmanager delivery failures; Alertmanager groups repeated events by stable resource rather than event ID. The SMTP playbook supplies destination configuration and a FIRING/RESOLVED test procedure. Real destination configuration, receipt, grouping, controlled delivery-failure observation and deployed audit correlation remain required before closing OPS-002-T01.

**Controlled lab progress (October 2, 2026):** The configured SMTP synthetic delivery test succeeded. After repairing the audit collector's PostgreSQL placeholder parsing, controlled authentication-failure, authorization-denial, and privileged-change events fired their corresponding security rules.

**Owner-directed closure (October 2, 2026):** Real notifications for the authentication-failure, authorization-denial, and privileged-change rules were received successfully, and repeated events remained one grouped ongoing incident. The owner does not require separate retained evidence for these confirmations. The controlled notification-delivery-failure exercise is omitted from this Phase 1B task by owner direction; Alertmanager's failure counter/rule remains implemented for operational use.


### OPS-003 — Monitor platform capacity

As an operator, I want an overview of platform resource usage and allocation,
so that I can identify bottlenecks and plan capacity.

Acceptance criteria:

- I can compare host capacity, actual CPU and memory usage, and workload resource requests.
- I can inspect storage usage and break down workload usage by project.
- Shared services are included in the overview, and missing or stale metrics are identified.
- Capacity thresholds can trigger alerts, and unschedulable workloads are visible.

Phase tasks:

- [x] **OPS-003-T01 · 1C** — Measure host, shared-service, workload and storage consumption; record system reserve and representative load baseline without promising unmeasured capacity. Prerequisites: PLAN-001.
- [x] **OPS-003-T02 · 2C** — Deliver host/usage/request comparisons and project storage/usage breakdown including shared services; test stale/missing metrics, capacity alerts and unschedulable workload visibility. Prerequisites: OPS-003-T01.

  **Accepted (October 5, 2026):** `GET /operator/capacity` supplies audited platform-admin Kubernetes node capacity, allocatable values and NodeMetrics usage with explicit provider-unavailable/missing-metrics state. The provisioner is limited to read/list `metrics.k8s.io` pod and node metrics; unit tests cover successful and unavailable provider responses plus the RBAC manifest contract. EV-43 validates deployed request accounting and bounded admission. The owner accepts existing host/shared-service/storage baselines and the documented single-host k3d capacity limitation in lieu of a destructive representative-load run.

**Task evidence (B-2026-09-26):** T01/T02 — source partial: node-exporter, kube-state-metrics, Compose memory limits, fixed workload quotas and some retention settings exist. Representative load/reserve measurements, project/shared-service usage breakdown, storage/capacity comparisons, CPU/memory alerts and dashboards are missing. EV-01/04 verify selected config only; task measurement/alert acceptance remains unverified.


### OPS-004 — Manage identities and project access

As an operator, I want to assign and revoke project permissions,
so that users can manage only the resources they are authorized to access.

Acceptance criteria:

- Developers authenticate with individual identities without using the platform admin token.
- Permissions distinguish viewing resources, changing applications, and administering the platform.
- Authorization is enforced for every project operation, including logs, metrics, and secrets.
- Revoking access blocks subsequent requests and creates an audit record.

Phase tasks:

- [x] **OPS-004-T01 · 1B** — Implement individual identities and scoped view/change/admin roles; deny unauthorized operations, revoke a platform grant and prove the next request is denied and audited. Release with audit, never with a developer admin-token fallback. Prerequisites: OPS-001-T01.

**Task evidence (B-2026-09-26):** T01 — source absent for individual scoped identities, memberships, roles, grant revocation and audit. The [platform guide](../../../platform/README.md) correctly describes a single administrator bearer token granting all-project access. Infrastructure database/network restrictions do not supply user authorization. Local end-user acceptance unverified; the inspected smoke script's unauthenticated rejection does not test scoped access.

**Decision update (October 2, 2026):** [ADR-004](../../architecture/decisions/ADR-004-identity-and-access-management.md) accepts a provider-neutral OIDC boundary with Keycloak as the supported lab reference, platform-owned grants, immutable issuer/subject principal keys, and `viewer`, `developer`, `project-admin` and `platform-admin` roles. This resolves the prerequisite design choice but supplies no OPS-004 implementation or acceptance evidence.

**Source update (October 2, 2026):** The Python baseline now validates configured OIDC JWT issuer/signature/audience/lifetime through a generic JWKS verifier, stores principals and project/platform grants in PostgreSQL, and checks those grants on every request. It provides audited grant/revocation endpoints, filters project lists by grants, and records authorization denials; revocation is effective on the next request because no permission cache exists. A Keycloak 26.4.1 Compose reference profile supplies the lab issuer without becoming the authorization source. Deployment, real Keycloak login/JWKS rotation, operator bootstrap, restricted user acceptance, and backup verification remain open. This update does not close OPS-004-T01.

**Local verification (October 2, 2026):** A fresh Keycloak reference realm issued a PKCE Device Authorization token to an individual bootstrap platform administrator; `GET /projects` succeeded. Disposable project A received distinct viewer, developer, and project-admin grants. The individual-role denial/cross-project matrix, platform-grant revocation with an unchanged token, audit correlation, JWKS rotation, and backup verification remain open; OPS-004-T01 stays unchecked.


### OPS-005 — Enforce project policies and quotas

As an operator, I want to define resource and security constraints per project,
so that workloads operate within the platform's agreed boundaries.

Acceptance criteria:

- I can configure project quotas, default resource limits, and allowed network access.
- Workloads that violate required security settings are rejected with a specific reason.
- Policy changes show their effect on existing workloads and subsequent deployments.
- Project quotas are considered alongside host capacity when admitting new workloads.

Phase tasks:

- [x] **OPS-005-T01 · 2C** — Configure per-project quotas, resource defaults and allowed network/security policy; show impact on existing workloads and subsequent deployments. Prerequisites: PLAN-002; OPS-004-T01; OPS-003-T01.
- [x] **OPS-005-T02 · 2C** — Reject security/quota violations with specific reasons; admit against aggregate host allocations after system/shared-service reserve and test policy enforcement. Prerequisites: OPS-005-T01; OPS-003-T02.

**Accepted (October 5, 2026):** `PROJECT_QUOTAS_JSON` supplies an operator-owned default quota plus bounded per-project overrides for pods and CPU/memory requests/limits. The same resolver drives ResourceQuota manifests and pre-operation application admission, including rolling-update headroom; malformed policy fails closed. The platform-admin security-configuration endpoint shows the effective safe manifest policy. EV-39 proves deployed quota rejection, EV-43 proves aggregate request rejection/recovery, and EV-44 proves approved egress connectivity and restoration. The owner accepts the documented lack of physical-host calibration for overlapping k3d allocatable values as a lab limitation.

**Task evidence (B-2026-09-26):** Fixed quotas/LimitRange, restricted Pod Security, non-root/read-only workloads, dropped capabilities, no mounted API token and NetworkPolicies exist in [manifests](../../../platform/app/src/app/manifests.py). All Compose/k3d services share the `developer-platform` network; pods use a fixed PostgreSQL IP because Compose DNS is not Kubernetes DNS. PostgreSQL TLS and target edge/platform/persistence segmentation are unimplemented; policy convergence can briefly allow new-pod egress. Define/test the required boundaries as part of policy work without claiming hostile-tenant isolation. Local/live network acceptance remains unverified; the isolation script was not run.


### OPS-006 — Back up and restore platform data

As an operator, I want scheduled backups and a verified restoration procedure,
so that I can recover project data and platform configuration after a failure.

Acceptance criteria:

- Backup scope includes project databases, platform state, and configuration and secrets needed for recovery.
- Backup schedules, retention, access controls, and storage outside the host are configured.
- Failed or overdue backups trigger notifications.
- A restoration exercise verifies data and application access against documented recovery time and data loss targets.

Phase tasks:

- [x] **OPS-006-T01 · 1A** — Inventory databases, roles, state, config, secrets and service-state recovery needs; record storage, encryption/key recovery, schedule, retention/access, RPO/RTO and replacement-host decisions. Prerequisites: Installation inventory and operator-selected storage/targets.
- [x] **OPS-006-T02 · 1A** — Automate bounded non-overlapping scheduled capture, encryption, off-host transfer and verified readback; test failure/overdue/stalled/missing signals independently of heartbeat, and verify scoped retention/access controls; failed uploads never advance success time. Full 14/8/6 elapsed-time retention evidence is omitted from Phase 1A by ADR-017. Prerequisites: OPS-006-T01; OPS-007-T01.
- [ ] **OPS-006-T03 · Deferred** — Exercise recovery onto an empty isolated installation without the original host; verify data/permissions/workloads/ingress/monitoring and actual alert receipt against RPO/RTO; exercise unavailable/corrupt backup and key failures. Schedule only through a later explicit scope decision or an actual recovery event. Prerequisites: OPS-006-T02; ADR-016 revision or recovery event.

#### Current backup and recovery progress

As of September 27, 2026, the following criterion-level progress supersedes older
baseline/implementation-only notes below. Parent task IDs and prerequisites are
unchanged; OPS-006-T01/T02 are complete within the accepted single-environment lab scope. OPS-006-T03 is deferred by ADR-016.

- [x] **T01 — Policy and scope:** documented SQL/roles/catalog, original configuration/secrets, Caddy/Grafana state, exclusions, S3 destination, encryption, twelve-hour schedule, 14/8/6 retention, 24-hour RPO and four-hour RTO targets.
- [x] **T01 — Independent recovery access:** existing S3 credentials and repository password successfully opened the repository from the fresh recovery VM.
- [x] **T01 — Replacement-host and credential policy:** accepted September 28, 2026. A fresh Ubuntu VM in WSL is provisioned when recovery is required; Hetzner S3 credentials and the restic password are retained in the operator password manager outside `node-01` and this repository; the operator selects an explicit verified snapshot and runs the recovery playbook. No recovery VM is maintained continuously for this lab.
- [x] **T02 — Source backup exercised:** managed capture, encrypted S3 upload and verified readback completed on `node-01`; marker preparation playbook reported service exit code 0 and capture after marker commit.
- [x] **T02 — Automation safeguards locally tested:** failed-upload behavior, checksum rejection, scoped retention, interrupted-service recovery and independent watchdog state transitions have local tests (not live failure-delivery acceptance).
- [x] **T02 — Scheduled execution:** operator-supplied timer, status and journal output confirms the September 27, 2026 midnight run on `node-01`, from 00:00:04 to 00:01:38 UTC (94 seconds), with verified snapshot and retention completion.
- [x] **T02 — No-backup notification and recovery:** operator confirmed both BACKUP DOWN and BACKUP UP emails on September 27, 2026 and supplied DOWN reason `no-backup`. Source defines this as no recorded successful capture (`last_capture` is null). This establishes initial no-backup detection and recovery email receipt; actual receipt times were not supplied. This initial check does not establish failed, overdue or stalled scenarios; later drill evidence is recorded separately below.
- [x] **T02 — Failed capture notification and recovery:** operator confirmed successful execution of the failure-drill playbook on the existing lab and receipt of both drill emails (September 27, 2026). This covers injected database-capture failure and subsequent verified backup recovery; see F-2026-09-27 below.
- [x] **T02 — Stalled backup notification and recovery:** the operator supplied a passed drill/recovery report and confirmed both BACKUP DOWN (stalled) and subsequent BACKUP UP emails on September 27, 2026. See stalled drill completion evidence below.
- [x] **T02 — Overdue backup notification and recovery:** the operator supplied a passed drill/recovery report and confirmed both BACKUP DOWN (`overdue`) and subsequent BACKUP UP emails on September 28, 2026. See overdue drill completion evidence below.
- [x] **T02 — Repository integrity and snapshot inventory:** operator listed four `developer-platform,verified` snapshots for `node-01` and ran `platform-restic check` successfully on September 28, 2026.
- [x] **T02 — Repository access controls:** operator confirmed root-only modes on September 28, 2026: backup directory and configured restic wrapper `0700`; S3 credential and repository-password files `0600`; all owned by `root:root`.
- **T02 — Accepted limitation:** [ADR-017](../../architecture/decisions/ADR-017-phase-1a-retention-evidence-scope.md) omits elapsed-time proof of the 14 daily, 8 weekly, and 6 monthly policy from Phase 1A. The configured policy and scoped retention implementation remain in operation; full-horizon behavior is not demonstrated.
- **T02 — Accepted limitation (September 28, 2026):** [ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md) removes the missing-update/local-monitoring-outage backup exercise from lab acceptance. The lab has no live evidence that external backup notifications continue while local monitoring is down.
- [x] **T03 — Fresh isolated restore:** playbook restored SQL, source/configuration and service volumes from S3 into a fresh Ubuntu VM without reading the source host during restoration.
- [x] **T03 — Historical SQL marker:** an independent pre-backup receipt matched the restored record through a Kubernetes test pod using the project Secret.
- [x] **T03 — Recovered service checks:** API/catalog, selected project rollout, HTTP ingress, project database authentication/write/read, denied catalog CONNECT privilege, Prometheus targets and Grafana database health passed.
- **T03 — Deferred scope:** recovery notification receipt, precise RPO/RTO measurements, production DNS/TLS, application-level database transactions, and recurring fresh-VM restoration are outside Phase 1A under ADR-016.

**P-2026-09-28 — Historical recovery failure preflight and cadence:** [check-recovery-failure-modes.yml](../../../operations/backup/ansible/check-recovery-failure-modes.yml) runs selected unavailable-endpoint, wrong-password, and missing-password checks on an explicitly provisioned WSL recovery VM. It uses `restic snapshots --no-lock`, expects each negative case to fail, writes no repository state, removes temporary credentials, and fetches a non-secret report. This tooling and its prior cadence are historical reference material; ADR-016 removes the exercises and recurring full restores from Phase 1A.

**E-2026-09-28 — Recovery failure preflight passed:** The operator ran the playbook on `recovery_vm` after entering S3 credentials and the existing repository password. All three selected negative cases (`unavailable-endpoint`, `wrong-password`, `missing-password`) produced the expected failure, the assertion passed, and the temporary credential directory was removed. The fetched non-secret report is timestamped `2026-09-28T20:27:19Z` and records `repository_write_mode: disabled (--no-lock)`. This establishes the selected storage and credential failure behavior, not corruption, a full restore, or recovery-notification receipt.

**T03 — Accepted limitation (September 28, 2026):** [ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md) excludes deliberately corrupting, deleting, or altering data in the only live restic repository. Repository `check`, verified readback, and automated checksum-rejection evidence remain in place; there is no live injected-corruption evidence.

**P-2026-09-28 — Lab recovery access policy accepted:** The owner accepted the fresh-WSL-VM replacement-host procedure and off-node password-manager storage for the Hetzner S3 credentials and restic password. This completes OPS-006-T01 planning within the single-environment lab scope; see [ADR-015](../../architecture/decisions/ADR-015-verified-backup-bundles.md).

**In-place failure drill tooling (September 27, 2026; OPS-006-T02/OPS-007-T01):**
Added [drill-backup-failure.yml](../../../operations/backup/ansible/drill-backup-failure.yml)
and a supervised helper using the installed backup runner and its lock. It injects
a database-capture failure with an in-memory Docker override, checks preservation
of the last verified capture, waits for the notification window, and attempts a
normal verified recovery backup in a finally block. A transient systemd service
continues independently of the controller. Reports retain before/failure/recovery
status without credentials; mailbox receipt requires operator confirmation.
Local playbook syntax passed; 26 backup/recovery tests ran with 25 passing and
one optional real-restic check skipped, including six new drill control-flow
checks. These are local fixture results, not execution on node-01. Subsequent
operator-reported live execution is recorded as F-2026-09-27 below.

**Freshness drill tooling (September 27, 2026; OPS-006-T02/OPS-007-T01):**
Added [stalled](../../../operations/backup/ansible/drill-backup-stalled.yml) and
[overdue](../../../operations/backup/ansible/drill-backup-overdue.yml) launch
playbooks plus [status/evidence collection](../../../operations/backup/ansible/check-backup-drill.yml).
They use the existing lab and installed runner, real two-hour/24-hour thresholds,
an independent transient systemd service and the backup lock. The stalled attempt
delays capture; the overdue exercise lets the previous verified capture age without
sending fabricated events. Scheduled attempts cannot acquire the lock during
these exercises. A normal verified capture follows the wait; interruption also
attempts recovery. Reports keep prior/current evidence; actual email receipt
remains an operator check. Local syntax validation and nine simulated-clock/control-flow
tests passed; full backup suite: 34 passed, one optional real-restic test skipped.
No live freshness exercise was run during implementation. Subsequent operator
output confirms launch and waiting state below; overdue/stalled acceptance
remains open.

**Stalled drill launch (September 27, 2026; operator-supplied output):**
The launch playbook completed with 13 successful tasks and zero failures on
inventory host platform. The status playbook showed the transient service active
and the report in running/waiting-for-stalled state. Run
bfe5d4443417454ba8b73cd00b9fc3df started at 08:46:40 UTC; the real stalled threshold
is crossed after 10:46:40 UTC, with recovery scheduled no earlier than 10:51:41 UTC.
Remote report: /var/lib/developer-platform-backup-drill/freshness-_5w2hvpe/report.json.
The report retained the previous verified capture/snapshot while waiting.
This records initial launch/progress; completion evidence follows below. Exact
deployed revision was not supplied.

**Stalled drill completion (September 27, 2026; operator-supplied report):**
The status playbook completed with six successful tasks and zero failures. The
transient service was inactive with exit code 0; the report recorded result
passed, stage complete and recovery exit code 0. The threshold/notification
window ended at 10:51:41 UTC; recovery finished at 10:52:38 UTC. Recovery run
bfe5d4443417454ba8b73cd00b9fc3df produced verified snapshot
b056b5582daad0c73b974a60caba37ed960fac5e5838a1287a7493c8c4c0c23d.
The runner retains the attempt start, 08:46:40 UTC, as last_verified_capture;
this is not the completion time. The report establishes elapsed-threshold and
verified-recovery behavior. The operator subsequently confirmed receipt of both BACKUP DOWN with stalled
reason and subsequent BACKUP UP emails on September 27, 2026. This completes
the stalled notification/recovery check. Exact receipt times were not supplied;
overdue and other remaining operational criteria stay open.

**Overdue drill progress (September 27, 2026; operator-supplied report):**
The status playbook completed with six successful tasks and zero failures. The
transient service was active and the report recorded mode overdue, result running,
and stage waiting-for-overdue. The exercise started at 11:25:57 UTC on September 27.
Its baseline is the stalled-drill verified snapshot
b056b5582daad0c73b974a60caba37ed960fac5e5838a1287a7493c8c4c0c23d,
with last_verified_capture at September 27 08:46:40 UTC (the attempt start, not
its 10:52:38 UTC completion). The 24-hour threshold is exceeded at September 28
08:46:41 UTC; recovery is scheduled no earlier than 08:51:41 UTC after the
five-minute notification window (10:46:41/10:51:41 Berlin time, CEST).
This records the initial waiting state; completion evidence follows below. Exact
deployed revision was not supplied.

**Overdue drill completion (September 28, 2026; operator-supplied report):**
The status playbook recorded the transient service inactive with exit code 0 and
the report recorded result `passed`, stage `complete`, and recovery exit code 0.
The notification window ended at 08:51:41 UTC; recovery finished at 08:52:49 UTC.
Recovery run `0a0976b20ef24474981b7438e04a71f8` produced verified snapshot
`87346cb4eead6a2e5dd981a241aea749af3d79f3aedb981ee7e51b9d4b36fcb4`.
The operator confirmed the overdue BACKUP DOWN and subsequent BACKUP UP emails.
This completes the overdue notification/recovery check. Exact receipt times and
the deployed revision were not supplied; other T02 criteria remain open.

**Failed-backup drill evidence F-2026-09-27 (operator supplied; OPS-006-T02/OPS-007-T01):** The operator reports that [drill-backup-failure.yml](../../../operations/backup/ansible/drill-backup-failure.yml) executed correctly on the existing lab and both notification emails arrived. The referenced drill injects database-capture failure, verifies preservation of the prior successful capture/snapshot, waits for the DOWN notification window, then runs and verifies a normal recovery backup. This is operator-reported acceptance of the failed-capture/recovery path and its email pair. The fetched report, exact deployed revision, snapshot IDs and receipt times were not supplied for independent inspection. It does not establish upload-failure acceptance; notification-delivery-failure injection and the local-monitoring-outage exercise are accepted limitations under ADR-011. No separate test environment was used, in accordance with ADR-010.

**Repository inspection I-2026-09-28 (operator supplied; OPS-006-T02):** `platform-restic snapshots --host node-01 --tag developer-platform,verified` listed four verified snapshots: `c03a2bcc` (September 26 15:01:01 UTC), `5ea9753a` (September 26 19:39:06 UTC), `b056b558` (September 27 10:52:27 UTC), and `94eda65a` (September 28 12:00:47 UTC). `platform-restic check` opened repository `ef5d344f`, checked one index and all four snapshots, trees and blobs, and reported no errors. This establishes an inspectable verified-snapshot inventory and repository structural integrity at that time. Four snapshots cannot demonstrate the configured 14/8/6 long-horizon retention policy; command output establishing root-only credential paths was not supplied.

**Backup credential access evidence A-2026-09-28 (operator supplied; OPS-006-T02):** `stat` confirmed `/etc/developer-platform/backup` and `/usr/local/sbin/platform-restic` at mode `0700`; `/etc/developer-platform/backup/restic.env` and `restic-password` at mode `0600`; all paths owned by `root:root`. This establishes host-side access restrictions for configured backup credentials and the wrapper. It does not establish S3-provider IAM policy or long-horizon retention outcomes.

**Scheduled backup evidence S-2026-09-27 (operator supplied; OPS-006-T02):** `platform-backup.timer` reported its last trigger at 00:00:04 UTC and next at 12:00 UTC. The service journal records successful start/completion at 00:00:04/00:01:38 UTC. Durable status records run `60c70027e90644258716b3c3bfeb8c4b`, `running: false`, `result: success`, `stage: complete`, and verified snapshot `38f989c67a080a82970d796d1a3da1c79d6264005e131d116431a12333a0e1ed`. The journal explicitly reports verified backup and completed retention. This establishes one scheduled successful capture/readback/retention run, not full retention-policy/access-control acceptance, notification email receipt, or restoration of this snapshot. Exact deployed revision was not supplied.

**Operational evidence R-2026-09-26 (operator supplied):** Source `node-01`;
recovery target `platform-recovery`, Ubuntu 24.04 amd64 under QEMU/KVM in WSL 2.
[Marker preparation](../../../operations/backup/ansible/prepare-recovery-test.yml)
completed with 13 successful tasks, zero failures and backup service exit code 0.
Verified snapshot: `5ea9753aa32f362e351223154589489cf32b9188098da1f9d270030c1d39ed19`.
Independent controller receipt:
`.runtime/recovery-evidence/platform/recovery-test-ksghhx8e/marker.json`.
The [restore playbook](../../../operations/backup/ansible/restore-recovery.yml)
then passed the marker-enabled acceptance suite for `smoke`, exit code 0, ending
at `2026-09-26 19:49:55` in Ansible's reported remote time. The suite ran for
36.35 seconds; this is not total recovery duration. Report on the VM:
`/root/platform-recovery/checks-smoke.json`; fetched controller copies live under
`.runtime/recovery-evidence/recovery_vm/<run-timestamp>/`. Receipts/reports remain
private and ignored by Git. Tooling was committed as `0ce015d` after these runs;
exact deployed checkout revisions were not captured, so the commit identifies the
resulting tooling, not proof that the source host ran that revision.

The earlier manual drill restored snapshot `c03a2bcc`, completed verification at
18:10:06 UTC, and took an operator-estimated 30–60 minutes including preparation.
That is within the selected four-hour target but is not a precise RTO benchmark.
The marker drill proves SQL data survival and the pod-to-database path; `http-echo`
is not a database-backed application's transaction test. Production alert senders
were deliberately disabled on the recovery VM. No task or Phase 1A gate is closed
by the successful-path drill alone. Use the [playbook-first workflow](../../../operations/backup/README.md#start-with-the-playbooks).

**Historical implementation and baseline evidence:** The dated notes below retain
what was known at each earlier step. Statements that deployment or restoration had
not run apply to those steps, not to current progress above.

**Operator decisions (September 26, 2026; OPS-006-T01):** The user reports no application data currently requiring preservation; platform configuration and secrets remain in recovery scope. Confirmed destination: Hetzner Object Storage, bucket `eseidinger`, endpoint `https://hel1.your-objectstorage.com`, prefix `developer-platform/`. Access credentials exist and remain outside this repository. Confirmed policy: backups every 12 hours; retain 14 daily, 8 weekly and 6 monthly recovery points; RPO at most 24 hours and RTO at most four hours. These are selected targets, not measured guarantees. At decision capture, storage/key access and restore execution were unverified. Current verified outcomes and remaining T01 planning are listed above.

**Repository setup progress (September 26, 2026; OPS-006-T02):** Added [operations/backup/ansible/setup-backup.yml](../../../operations/backup/ansible/setup-backup.yml), a [backup inventory example](../../../operations/backup/ansible/inventory.backup.example.yml), private configuration template and root-only restic wrapper. This installs restic/CA certificates, configures the confirmed S3 destination and prompts privately for credentials/password, optionally initializes a new repository, then verifies opening and snapshot listing. Existing local repository passwords cannot be implicitly replaced. Usage is in the [Ansible guide](../../../operations/backup/README.md#encrypted-s3-backup-repository-setup). Syntax checks passed. A temporary local Ansible fixture (package installation omitted, paths redirected to a temporary directory, simulated restic backend) verified check-mode nonmutation, explicit initialization, unchanged reruns, rejected password replacement, inaccessible-repository failure without implicit initialization, shell-metacharacter credential quoting, and 0600 secret file permissions. This is local fixture evidence for the working-tree change based on `10ca8ef`, not a target-host/S3 test. No package installation, backup upload, scheduled job, pruning or restore was performed. At this setup-only milestone, capture automation and operational acceptance remained outstanding; see current progress above.

**Setup run correction (September 26, 2026; OPS-006-T02):** The user reported a target-host run stopping at the initialization guard: `-e backup_restic_initialize=true` supplied a string, whose extra-variable precedence bypassed the original `set_fact` conversion. Setup reported 14 successful tasks and five changes before this failure; repository initialization/access was not established. Both consuming conditions now apply `default(false) | bool` explicitly. The original local fixture supplied a JSON boolean and missed this case; regression validation now uses the documented key=value command-line form for both true and false. Rerun with the same repository password; do not disable Ansible's strict conditional checks.

**Operator-reported repository setup (September 26, 2026; OPS-006-T02):** The user reports a successful rerun of setup-backup.yml and repository config present in the S3 bucket. This establishes reported initialization/access, not a data backup or restoration.

**Scheduled backup implementation (September 26, 2026; OPS-006-T02, OPS-007-T01):** [deploy-backup.yml](../../../operations/backup/ansible/deploy-backup.yml) and the [runner](../../../operations/backup/scripts/backup-platform.py) now provide locked twelve-hour UTC capture, a two-hour timeout, encrypted upload, exact-snapshot restore/checksum comparison, verified-only installation-scoped 14/8/6 retention with pruning/check, private durable status, interrupted-service recovery and notification retry. Capture includes SQL/roles/catalog, source/config/secrets, Caddy/Grafana stopped-service volumes, installed backup helpers/units and version/image metadata. The separate authenticated backup watchdog table/endpoint detects failed, missing, overdue and stalled backups without using host heartbeat freshness. Service capture briefly interrupts Caddy/Grafana; staging/readback needs disk for two bundle copies. External watchdog state and historical telemetry are excluded; image artifacts must remain available. See [deployment and recovery details](../../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts).

Local validation on the working tree (based on `10ca8ef`) includes ten Python tests with a real local restic 0.16.4 encrypted repository, checksum mismatch and failed-upload behavior, pending-snapshot retention isolation, interrupted-service recovery, and notification retry; PHP state/freshness tests and a disposable PHP/MariaDB integration test establish separate tokens/state, replay rejection, overdue/stalled detection, failed mail-handoff retry, recovery and repeat schema import. Integration mail is simulated. These results are local evidence only: no deployment to node-01, Hetzner snapshot upload, live BACKUP email receipt or SQL/application restoration was performed by this implementation work. This local-test milestone preceded the operator-reported deployment and restore; remaining acceptance is listed above.

**Task evidence (B-2026-09-26):** T01/T02 — source partial: the former local SQL dump helper (since removed in favor of the scheduled backup runner) privately and atomically published a compressed local `pg_dumpall` through a temporary file, including databases/roles/platform catalog. Scheduling, encrypted upload, remote retention, recovery-key/config automation and backup-age alerts are absent. T03 — source partial through the [isolated restore/reapply guide](../../operators/backup-and-recovery.md); no executable restore harness or measured recovery evidence. EV-03/06 establish script/example syntax only. Recovery must retain `DATABASE_KEY` and compatible credentials, handle SQL errors explicitly, restore catalog/data, reapply workloads and prove application write/read. No SQL dump/import, clean-host restoration or actual backup alert exercise ran in the baseline assessment.


### OPS-007 — Monitor service availability

As an operator, I want to monitor shared services and application availability,
so that I can detect outages and identify affected projects.

Acceptance criteria:

- Health checks cover the control plane, ingress, database, and monitoring services.
- Alerts identify the failing service and affected projects where that information is available.
- An external check can report a complete host outage when local monitoring is unavailable.
- Alert routing can be tested before relying on it for incident response.

Phase tasks:

- [x] **OPS-007-T01 · 1A** — Configure real Alertmanager/watchdog routing and response ownership; verify actual outage/recovery receipt, cluster/host expiry, and public canary. Independent watchdog cron/hosting detection and notification-delivery-failure injection are excluded under [ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md); both are accepted lab limitations. Keep platform, pipeline and backup identities/timestamps isolated. Prerequisites: Installation inventory and notification recipients.
- [x] **OPS-007-T02 · 2C** — Exercise control-plane, ingress, database, monitoring and application failure checks; identify affected projects where known and verify external detection with host/local monitoring unavailable. Prerequisites: OPS-007-T01; DEV-006-T01.

  **Accepted (October 5, 2026):** EV-41 covers the controlled PostgreSQL/API readiness boundary. EV-44 covers a disposable public canary, project-labelled application and ingress alerts through firing and resolution, and a controlled Prometheus outage/recovery; all services and policy were restored. The owner confirmed notification receipt. Existing accepted cluster/watchdog evidence supplies the control-plane and external-detection boundary for this lab.

#### Current monitoring progress

**Deployed component/log evidence (October 11, 2026; EV-46):** Operator-provided
node-01 run `60c3ca1647b9` passed all 45 core-plus-monitoring assertions after
the Alloy state-permission repair and confirmed healthy collector startup.
Provider/consumer public-boundary probes, independent Kubernetes readiness and
project-authorized central synthetic correlation reads passed. Cleanup completed
with data retained. Seven-day retention, post-retirement/restart log readback and
the full integration gate remain open; this does not retroactively change EV-45
or earlier monitoring evidence. See the [run record](../../operators/validation/access-and-authorization.md#executed-hosted-access-monitoring-acceptance-october-11-2026).

**Application probe preparation (September 27, 2026):** [Catalog-driven blackbox probes](../../../infrastructure/monitoring/README.md) add root-path HTTP 200 and optional `hello-world` content profiles, shared availability/missing-result/discovery-freshness rules, and authenticated retirement acknowledgement after manual namespace removal. Failed/provisioning entries stay monitored; retired entries retain SQL data/specs and leave discovery. Public HTTPS probes run on the platform host; local probes use HTTP routing through Caddy. Outside-network reachability remains manual evidence. Source/local preparation does not establish deployment, real retirement, or notification receipt; OPS-007-T01 remains open. This is not the full planned deletion/audit workflow. Local verification: 16 platform tests passed; Prometheus configuration and six alert-rule scenarios passed; disposable exporter/Prometheus fixtures verified content/status/timeout/TLS rejection, recovery, target labels and removal without reload. API image build and UID 10001/shared-volume reader checks passed. Backup regression suite: 34 passed, one optional real-restic test skipped. No live platform deployment or real notification test was run.


**Availability drill tooling (September 28, 2026; OPS-007-T01):** Added [cluster](../../../operations/heartbeat/ansible/drill-cluster-availability.yml) and [Docker-boundary](../../../operations/heartbeat/ansible/drill-docker-availability.yml) exercises. Cluster mode stops only `k3d-workloads-server-0`, waits for the `kubernetes-state` scrape failure and `ScrapeTargetDown`, then restores the same container and verifies node, target and alert recovery. Docker mode stops Docker for a bounded interval so the external heartbeat can become overdue, then verifies Docker, Prometheus, Kubernetes nodes and the heartbeat timer after restoration. Both save a private report and require operator confirmation of email receipt. Local Ansible syntax and Python compilation passed. The operator subsequently reported both drills completed successfully; detailed reports, exact revision, alert labels, timings, and email receipt are not yet recorded.

**SMTP configuration tooling (September 27, 2026; OPS-007-T01):**
Added [inventory-based Alertmanager deployment](../../../operations/alertmanager/README.md)
with STARTTLS/implicit TLS, a private password prompt or Vault input, a separate
0600 password file, pre-installation amtool validation, and Alertmanager-only
recreation/readiness checks. Private configuration is included in existing
infrastructure backup capture and preserved across bootstrap; isolated recovery
explicitly selects the notification-free default. Local validation on the working
tree based on `0756ef8`: Ansible syntax/check-mode checks passed (check mode made
zero changes); default/private Compose resolution passed; both TLS modes passed
amtool validation using `prom/alertmanager:v0.34.1`; backup/recovery suite passed
19 tests with one optional real-restic test skipped. No target deployment, real
SMTP connection, notification receipt or new restore drill was performed.
OPS-007-T01 remains open.


- [x] **T01 — External heartbeat delivery:** operator confirmed both outage and recovery emails during the pause/resume exercise.
- [x] **T01 — HTTPS probe correction:** diagnosed HTTP 405 from HEAD on the GET-only health endpoint, changed the watchdog to GET, and operator confirmed status UP plus recovery email.
- [x] **Recovery monitoring health:** recovered Prometheus ready, Grafana database `ok`, and `host`, `kubernetes-state`, and `prometheus` scrape targets UP; automated restore suite also passed monitoring.
- [x] **T01 — Alertmanager SMTP delivery:** operator confirmed successful playbook execution on `node-01` and receipt of both FIRING and RESOLVED emails for the synthetic `PlatformEmailTest` alert on September 27, 2026.
- [x] **T01 — Prometheus-to-email delivery:** operator confirmed both FIRING and RESOLVED emails during the `node-exporter` stop/start exercise for `ScrapeTargetDown` on `node-01` (September 27, 2026).
- [x] **T01 — Backup channel email receipt:** operator confirmed BACKUP DOWN/UP for `no-backup`, failed capture, stalled, and overdue conditions (September 27–28, 2026); see OPS-006-T02 for scope limits.
- [x] **T01 — Response ownership:** on September 27, 2026, the owner confirmed they are the sole responder, targeting initial response within 24 hours for this side project. No secondary responder or escalation coverage; see the [accepted lab response policy](../../operators/monitoring.md#alert-process). This records ownership and a response target, not measured response performance.
- [x] **T01 — Cluster failure and recovery:** operator reported successful execution of the cluster availability drill on September 28, 2026. The drill completion requires a failed `kubernetes-state` target, firing `ScrapeTargetDown`, restoration of the k3d server, all nodes Ready, target recovery, and alert resolution. Exact report, revision, and alert times were not supplied. The operator subsequently confirmed both ScrapeTargetDown FIRING and RESOLVED emails.
- [x] **T01 — Docker failure boundary and recovery:** operator reported successful execution of the Docker availability drill on September 28, 2026. The drill stops Docker for a bounded interval, restores it, and requires Docker, Prometheus, all Kubernetes nodes, and the heartbeat timer to recover. This simulates the local Docker boundary, not a power-loss host outage; exact report, revision, and timings were not supplied. The operator subsequently confirmed external watchdog DOWN and UP emails.
- [x] **T01 — Availability-drill notification receipt:** operator confirmed ScrapeTargetDown FIRING/RESOLVED emails for the cluster drill and external watchdog DOWN/UP emails for the Docker drill (September 28, 2026).
- [x] **T01 — Public application canary:** operator confirmed the monitored `smoke` application was scaled to zero and back on September 28, 2026, producing both ApplicationUnavailable FIRING and RESOLVED emails. Exact project revision, replica count, probe/alert timing, and recovery output were not supplied.
- [x] **T01 — Current accepted scope complete:** Alertmanager and external-watchdog delivery, configured notification recovery, cluster/Docker-boundary drills, and the public application canary have live operator evidence. The accepted ADR-011 limitations remain recorded below. OPS-007-T02 retains later Phase 2 service coverage.
- **T01 — Accepted limitation (September 28, 2026):** [ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md) excludes notification-delivery-failure injection from lab acceptance. The lab has no live evidence of alerting behaviour when email delivery fails.
- **T01 — Accepted limitation (September 28, 2026):** [ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md) excludes a backup-missing-update exercise with local monitoring unavailable. This coverage gap remains an accepted lab risk.
- **T01 — Accepted limitation (September 27, 2026):** [ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md) removes independent watchdog cron/hosting failure detection from lab acceptance at the owner’s request. Watchdog failure and incidents occurring while it is unavailable may go unnoticed. This is an accepted scope limit, not verified detection or deferred implementation.

**Operator-reported SMTP evidence (September 27, 2026; OPS-007-T01):** The operator reported that the SMTP deployment playbook completed without errors and confirmed both alert and recovery email receipt after submitting `PlatformEmailTest` directly to Alertmanager using amtool on `node-01`. This establishes Alertmanager-to-email delivery only; it bypasses Prometheus rule evaluation. Exact deployed revision, receipt times, delivery latency and named response owner were not captured. Notification-delivery-failure injection is an accepted limitation under ADR-011; the other T01 acceptance checks remain open. This live evidence follows the local-only tooling validation above.

**Operator-reported rule-path evidence (September 27, 2026; OPS-007-T01):** Following the guided `node-exporter` stop/start exercise, the operator confirmed receipt of both alert and recovery emails. This verifies the selected scrape-failure rule through Prometheus, Alertmanager and SMTP, including recovery. Exact deployed revision and receipt/detection timings were not captured. This does not establish complete host/cluster failure detection, other rule coverage, or notification-delivery-failure handling; the latter is an accepted limitation under ADR-011, and OPS-007-T01 remains open.

These are operator-reported live outcomes, distinct from the imported local tests.
Healthy recovery monitoring does not establish alert delivery; the recovery VM
intentionally suppresses production notifications. OPS-007-T01 remains open.

**Operator-reported live evidence (September 26, 2026; OPS-007-T01):** On `node-01` in `/opt/developer-platform`, supplied output shows Compose services running, API/Prometheus readiness passing, three Kubernetes nodes Ready, and an enabled heartbeat timer with successful service exits. The user confirmed fresh external watchdog status and receipt of both outage and recovery emails during a heartbeat pause/resume exercise. A manually duplicated send received HTTP 429 about 16 seconds after a successful send; future recovery should start only the timer. Deployed revision, exact notification latency and final post-test service result were not captured. This establishes the user-reported heartbeat notification path only; independent Alertmanager delivery, application canary and watchdog-failure acceptance remain open. Do not close T01 from this partial evidence. The historical watchdog-failure acceptance requirement is subsequently removed by ADR-011; other outstanding criteria remain open.

**Task evidence (B-2026-09-26):** T01/T02 — source partial. [Monitoring](../../../infrastructure/monitoring/compose.yaml) runs outside k3d; [rules](../../../infrastructure/monitoring/alerts.yaml) cover scrape failure, low disk and unavailable replicas, but [Alertmanager](../../../infrastructure/monitoring/alertmanager.yaml) has a `local-only` receiver with no notification integration. PostgreSQL exporter, application request/error/latency, backup-age and job telemetry are missing.

The [host sender](../../../operations/heartbeat/scripts/heartbeat.py) checks API dependency readiness and Prometheus, then sends a heartbeat; it neither sends local alerts nor checks Alertmanager delivery, Grafana, Loki, backups or an end-to-end application. The external watchdog implements authenticated POST, receipt-time freshness, throttling, a fixed optional HTTPS probe (HEAD at the imported baseline; subsequently corrected to GET as recorded above), deduplication and retry after failed mail handoff. [Mail](../../../operations/watchdog/src/mail.php) supports PHP mail and TLS-verified STARTTLS/implicit SMTP; [cron](../../../operations/watchdog/src/cron.php) reports failure stages without raw exceptions. Maintenance windows and token-rotation workflow are absent. A stale cron returns an unavailable status page, but has no independent notifier.

The [heartbeat playbook](../../../operations/heartbeat/ansible/deploy-heartbeat.yml) installs Python/CA certificates, a dynamically readable sender, private systemd environment and timer. The [external playbook](../../../operations/watchdog/ansible/deploy-watchdog.yml) uploads an explicit release over SSH/SCP, preserves host-key checking, suppresses credential output and optionally replaces config/installs minute cron. Check mode validates local inputs only. Database/user, document root, HTTPS, extensions and mail are operator prerequisites; the uploaded [schema importer](../../../operations/watchdog/src/import-schema.php) must run separately. Neither playbook was deployed in the assessment. EV-07–10 verify local freshness/SMTP/syntax only; actual receipt, public probing, sender installation and independent-failure detection remain unverified.


### OPS-008 — Decommission projects safely

As an operator, I want to retire projects with an explicit data retention decision,
so that I can reclaim resources without accidentally deleting required data.

Acceptance criteria:

- A deletion preview lists workloads, routes, credentials, databases, and retained backups.
- Destructive data deletion requires explicit confirmation of the project and retention decision.
- Decommissioning revokes project access and credentials and removes the selected resources.
- Partial failures can be retried, and the result and retained resources are recorded in the audit trail.

Phase tasks:

- [x] **OPS-008-T01 · 2C** — Preview project workloads/routes/credentials/databases/backups; record explicit project-specific retention/deletion decisions and confirmation invalidated by scope changes. Prerequisites: DEV-011-T01; OPS-004-T01; OPS-006-T02.

  **Accepted (October 5, 2026):** Retirement preview enumerates managed Ingress hostnames, workload removal and retained database/role/catalog scope, plus redacted project-grant and deployment-credential counts. Its confirmation token is bound to that access inventory and revision. On completed namespace retirement, project grants are removed immediately and project deployment credentials enter fail-closed provider cleanup; database and catalog remain retained. EV-40 passed with a generated public workload, bound scope, immediate credential denial, completed provider cleanup, and namespace retirement. The owner accepts retained data as the explicit Phase 2C retention decision; destructive data deletion, project-addressable backup inventory, and injected provider-cleanup failure remain later hardening work rather than closure blockers.
- [x] **OPS-008-T02 · 2C** — Revoke project access/credentials and remove selected resources; inject partial failures, retry without affecting other projects, and audit all retained/deleted resources and outcomes. Prerequisites: OPS-008-T01; OPS-001-T01.

**Task evidence (B-2026-09-26):** T01/T02 — source absent for scoped project retirement, inventory/confirmation, credential revocation and audited retryable cleanup. Whole-lab teardown cannot satisfy these workflows. Local acceptance unverified; prerequisites include retained data inventory, individual access and tested recovery.


## Additional phase tasks

These tasks make the existing phase work executable without inventing new DEV/OPS stories or treating portability, interfaces or AI as acceptance criteria for unrelated stories. They are mandatory within their assigned phase. An unresolved ADR may block implementation choices; it does not waive a requirement or permit phase closure without its acceptance evidence. An explicit scope change must update the requirements and phase plan together. Deferred component implementation remains separate.

- [x] **PLAN-001 · 1C** — Implement stable project/environment/application identity and atomically persisted desired revisions/asynchronous jobs before side effects, returning an operation ID with authorized progress and worker-interruption recovery. Validate the supported single-image profile, reject unknown fields/unsupported capabilities before side effects, and use technology-independent public identities and minimal provider ports. Demonstrate an authorized application restart with unchanged desired spec, retained data and observed readiness; demonstrate minimal API/CLI deployment and record installation versions/parameters. Prerequisites: Phase 1B gate.

  **Task evidence (B-2026-09-26):** Source partial; local EV-01–04 cover foundations only. Stable project names and latest specs exist, but environments/ownership/application IDs, asynchronous jobs, operation IDs, observed health and restart are absent. PUT is synchronous; unknown fields are ignored and no capability checks exist. Bootstrap/Ansible/config generation and checksum-verified installation exist, but Ansible ends at process health, not full application/database acceptance; firewall/backups are separate. UC-01 remains an administrator-only partial flow.

  **Schema, API and worker progress (October 3, 2026; working tree based on `2a6d2f0`):** The catalog migration adds stable internal project, default-environment and single-application IDs while preserving public project slugs and slug-based grants. Existing projects are backfilled with a default environment/application and revision 1. Desired specs are stored as immutable revisions; identical specs reuse the latest revision. PUT persists a versioned queued operation with its desired revision in one transaction, deduplicates active operations for that revision, and returns `202 Accepted` with an operation ID/status URL. `GET /v1/operations/{id}` checks current project-view authorization, audits reads, redacts results, and appends a live readiness snapshot separate from the durable apply outcome. An in-process worker claims queued/running operations with PostgreSQL advisory locks, rechecks the submitter's current change grant and desired revision, applies idempotent provider steps, records sanitized results, and reclaims interrupted running work after restart. Retirement is blocked while operations are active. Current local verification is recorded as EV-11 and EV-12. The request model rejects unknown project fields before catalog/provider side effects. Unsupported capabilities, live readiness failure drills, live worker interruption/failure drills, and end-to-end deployment acceptance remain open.

  **Update (October 3, 2026):** live acceptance, worker-interruption (EV-13), readiness failure (EV-14, EV-15), authorized restart (EV-16) and installation record (EV-17) evidence now exist; the throwaway `badimage` project was removed (namespace deleted, then retired with data retained) and the API/CLI demo is documented in the runbook. Unsupported capabilities (scaling, object storage, messaging, cache, multiple components, resources, environment) are rejected with 422 and no catalog/provider side effect by the strict `Project` model, covered by a unit test. Installation record now includes image references (EV-17). Repeat-POST reuse and no-spurious-rollout were confirmed live (EV-18); only a `progressing` snapshot during a restart roll remains unobserved. Tests use doubles; no live PostgreSQL migration/API, Kubernetes execution or operational acceptance was run. PLAN-001 remains open.

- [x] **PLAN-002 · 2C** — Complete ApplicationSpec/API fit-gap and schema reuse assessment, versioned OpenAPI contract, environment capabilities/profiles, explicit CPU/memory request/limit semantics and migration rules; reject unsupported requests before side effects and keep backend fields out of the public contract. Prerequisites: Phase 1 gate.

  **Task evidence (B-2026-09-26):** Source partial; local EV-01 validates names/manifests, not the draft contract. API output exposes `namespace` and implementation calls Kubernetes directly. Schema versioning, capabilities, configurable bindings/resource budgets and fit-gap evidence are absent. Tag-to-digest resolution is absent despite the ApplicationSpec target; include it when stabilizing deployment identity.

  **Progress (October 3, 2026):** Tag-to-digest resolution is implemented in the API at acceptance (anonymous, allow-listed registries; unknown tag/unsupported registry 422, outage 503, no side effects; `resolved_image` stored in the revision and used for deployment and readiness), with unit tests. Live-verified in EV-19. The field-level [fit-gap](history/application-spec-fit-gap.md) is written. Resource requests/limits are decided and implemented in the flat body (explicit requests and limits, validated, stored per revision, applied to the container; unit tests only, no live evidence yet); The versioned `Application` envelope is accepted next to the flat body (unit tests only) and the OpenAPI contract is committed; the public API does not expose `namespace`, `GET /v1/capabilities` publishes the default-environment capabilities and PUT rejections carry stable codes (unit tests only; no live evidence). Live evidence for the capability endpoint and stable codes is EV-22. Decision: the flat body stays supported with no sunset date and the envelope is the preferred format. PLAN-002 is closed; the Phase 1 gate prerequisite was not separately verified.

- [x] **PLAN-003 · 2C** — Harden worker interruption, concurrent writes, revision retention and drift recovery; prove no duplicated resources/lost revisions and redacted traceable provider failures. Prerequisites: PLAN-002; DEV-007-T02.

  **Progress (updated October 5, 2026):** Decision: concurrent writes use an optional `If-Match: <revision>` header on PUT; a stale value returns 409 `revision_conflict` with the current revision and no side effects, and omitting it keeps last-writer-wins (unit tests; live check in EV-23). Drift decision: report only, never auto-revert; `GET /projects/{name}/drift` reports image, replica and resource differences and audits `project.drift.detected` (unit tests; live replica drift in EV-24; a background scan audits drift transitions; live in EV-25). Provider failures record a redacted trace (`step`, `error_type`, numeric `http_status`; never exception text) in the operation result, audit detail and log. Revision retention keeps the newest `REVISION_RETENTION` revisions while protecting in-flight and restart dependencies; retention and rollback are live-verified in EV-26. PLAN-003 remains closed with its recorded unit-tested failure-trace and bounded extra-revision gaps. DEV-007-T02 subsequently passed its data-aware rollback acceptance in EV-42.

  **Task evidence (B-2026-09-26):** Source partial; local workflow acceptance unverified. A global advisory lock serializes cooperating API requests but supplies no expected-revision conflict check. Updates overwrite the only spec; stale clients can replace intent. Persistent idempotency keys, revision history, per-step recovery and drift reconciliation are absent.

- [ ] **PLAN-004 · Optional 6** — If a recorded need activates the package, add the Docker adapter and shared provider contract tests; deploy/update/observe/remove the same spec on Kubernetes and Docker, including partial failure and capability rejection; publish tested profile differences. Prerequisites: completed current-platform lifecycle; explicit owner scope decision.

  **Task evidence (B-2026-09-26; moved October 4, 2026):** Source absent; local acceptance unverified. Docker hosts shared services but is not a direct application compute provider. No portable provider contract or reproducible provider comparison harness exists (F-07/UC-05). This is expected while the package remains optional and inactive.

- [ ] **PLAN-005 · Optional 6** — If a recorded need activates the package, extract only the justified deployable responsibilities using versioned contracts, state reconciliation, single-writer cutovers, backup/restore, parity, and rollback. The candidate split remains Kotlin catalog, Quarkus control plane, and Python workers. Prove cross-service authorization, audit correlation, interruption/idempotency, and stable-ID reconciliation before retiring any FastAPI path. Prerequisites: completed current-platform lifecycle; explicit owner scope decision; code/effort analysis before contract stabilization.

  **Task evidence (B-2026-09-26; moved October 4, 2026):** At this baseline the decision was open and local implementation-language parity/migration acceptance was unverified. The Python application remains the selected architecture through the current delivery phases. ADR-006 retains the former target roles only as an optional expansion candidate; that documentation decision supplies no implementation, migration, or acceptance evidence. The candidate is now scheduled as optional Phase 6.

- [ ] **PLAN-006 · 7 (anytime)** — Deliver portal and CLI using the versioned Python Platform API for ownership/roles, applications, deployments, redacted config, logs and operations; extend the CLI to every public project administration operation, including hosted application access and governance; diagnose an injected failure and prove bypassed client checks still fail server-side. Prerequisites: Phase 2C gate; hosted-access commands require the PLAN-009 public API.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. REST/curl and interactive API docs are not a domain CLI or self-service portal; no UI/API compatibility journey exists.

  **Progress (October 6, 2026):** [ADR-019](../../architecture/decisions/ADR-019-react-ui-technology-stack.md) selects the React UI stack, and the [UI implementation plan](plans/ui.md) defines gated foundation, authentication, read-only diagnosis, lifecycle, administration and operator increments. Foundation increment 0 is implemented in source under `platform/ui`: the Vite demonstration is replaced by a routed shell and query provider; shadcn source is under `src`; strict type-aware linting, OpenAPI type generation, a typed API-client boundary, Vitest, and a Playwright smoke configuration are present. The first authentication source increment selects `oidc-client-ts` and wires provider-neutral OIDC Authorization Code with PKCE from `/portal/config`, in-memory user/token state, callback handling, local session clearing, and API bearer injection. An initial authenticated project list uses the typed client, validates the currently `unknown` `/projects` response at the UI boundary, and renders project name/status with loading, empty, error, and refresh states. `npm run check` and the self-contained Playwright browser smoke test pass locally. No live Keycloak login, deployed API feature view, or portal acceptance journey has run. This is partial PLAN-006 source and local-check evidence only; CLI work remains separate within this task.

  **CLI scope update (October 13, 2026):** The package under `platform/cli` already
  implements environment authentication, `auth status`, and `deploy apply` with
  optimistic revision updates and bounded operation/readiness watching. The
  [expanded CLI plan](plans/cli.md#project-administration-coverage) maps every
  current public project API family to commands and defines a checked coverage
  registry. Human login and shared command infrastructure precede the first
  administration slice: application groups/policies, human requests/memberships,
  governance, access operations, and full consumer/provider service lifecycle,
  including a same-project worker calling its application's public service.
  Remaining increments cover diagnosis, configuration/secrets, recovery requests,
  lifecycle, grants, CI credentials, and explicitly privileged operator actions.
  Require exact ETags, idempotent creates, distinct deployment/access operation
  watching, project-wide managed-secret semantics, explicit credential adoption,
  and a role/denial acceptance matrix. This is a planning update; administration
  commands and their deployed acceptance remain open under PLAN-006.

  **CLI source progress (October 13, 2026):** The CLI now implements named
  non-secret profiles, OIDC device login with keyring-backed refresh, preserved
  environment deployment authentication, and domain commands for all 81
  non-health public API methods. The packaged contract check reports 81 covered,
  two health endpoints excluded, and no missing or extra commands. Local CLI
  tests cover the existing deployment invocation, profile/session boundaries,
  a same-project service request and approval with durable operation watching,
  stale ETag denial, and unauthorized administration. The Python test suite and
  wheel build pass locally. No live Keycloak login, deployed CLI administration,
  role/denial matrix, or injected-failure journey ran; PLAN-006 stays open.

  **Source update (October 14, 2026):** The CLI registry and packaged contract
  now cover all 87 public non-health methods, including human database grant,
  key, and credential operations; two health methods remain intentionally
  excluded. The CLI test suite and portal `npm run check` pass locally. No
  deployed browser, CLI, direct-API denial, or injected-failure acceptance is
  claimed; those checks are Phase 7.7 work.

- [ ] **PLAN-007 · 7 (anytime)** — Deliver the web/PostgreSQL template and reproducible create/deploy/diagnose journey; verify UI/API compatibility and document the role matrix. Prerequisites: PLAN-006.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. The sample project JSON/http-echo demonstrates provisioning only, not a combined UI/API template or application/database journey (ADR-007).

  **Source update (October 14, 2026):** `examples/web-postgres` now includes a
  public OCI image source, digest-pinned `v1alpha2` declaration renderer, managed
  PostgreSQL counter and readiness path, separate browser access-policy example,
  role matrix, and reproducible create/deploy/diagnose/recover instructions.
  Local tests validate the rendered declaration and policy against the current
  schemas; no image was published or deployed, and the Phase 7.7 UI/API journey
  and injected-failure acceptance remain open.

- [ ] **PLAN-008 · 7 (anytime)** — Deliver separate authorized/audited human database identity and controlled tunnel; test foreign-project denial, credentials distinct from application credentials, and revocation of new/existing sessions per policy. Prerequisites: Phase 2C gate; accepted IAM design.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. Runtime logins own their database; no separate human identity, controlled tunnel, grant audit or session revocation workflow exists (F-09/UC-03).

  **Source update (October 14, 2026):** A named `(issuer, subject)` grant now
  creates a distinct read-only SQL role, authenticated self-service key and
  one-time password rotation, audited admin grant/revocation, active-backend
  termination, retirement/purge cleanup, and a restricted OpenSSH forwarding
  service with fail-closed dynamic key lookup. Unit tests cover key validation,
  role separation, machine denial, and revocation calls; Ansible syntax passes.
  This does not establish deployed tunnel reachability, foreign-project SQL
  denial, credential distinctness in a live database, audit export, or existing
  session termination; all remain Phase 7.7 acceptance work.

  **Portal source update (October 14, 2026):** The project workspace now has
  administrator grant/list/revoke controls and a named-human panel for SSH key
  replacement and one-time SQL password rotation. The password is held only in
  the open dialog, not a query cache; local UI tests cover permission/empty
  states, grant/revoke actions, key replacement, and password dismissal. This
  adds no deployed acceptance evidence.

  **Acceptance automation source (October 14, 2026):** The opt-in
  `ansible/test-platform-human-database-access.yml` wrapper defaults to an
  offline plan. Its live runner is designed to exercise a pinned neutral
  fixture, two isolated PostgreSQL databases, restricted SSH tunneling,
  machine-grant denial, named human read-only SQL, foreign-project denial,
  revocation of existing/new sessions and key access, and redacted audit
  events. Local tests and playbook syntax are the only evidence so far; no
  deployed run, browser inspection, remote firewall test, or full Phase 7.7
  acceptance is claimed.

  **Deployed partial acceptance (October 15, 2026; EV-47):** Node-01 run
  `5f39d4862423` returned `core-passed` with all 14 automated checks passed.
  The owner also verified the portal grant and one-time credential journey,
  project A read-only SQL, project B and write denial, SSH key replacement,
  and SQL/SSH denial after portal revocation. Two portal defects found during
  the journey were fixed, regression-tested, deployed, and rechecked. The
  runner cleaned up its grant and persona but retained the two fixture
  projects. A later clean deployment recorded revision
  `9826de70829b47f18b8c8018c9348fc81dcb8c43`; API readiness passed, and
  both fixture projects were subsequently retired with their databases retained.
  The access checks were not repeated after that deployment. `gateClosed: false`:
  remote firewall, browser storage, and independent redaction review remain.
  The original tested deployment was
  recorded as `b3acaef1e413e698d772c218dc336da8d55684b0+dirty`, not an
  attested commit. [Detailed evidence and limits](../../operators/validation/access-and-authorization.md#executed-human-postgresql-access-acceptance-october-15-2026).

  **Owner acceptance (October 15, 2026):** The owner accepts EV-47's 14
  automated checks and completed manual portal, tunnel, SQL, key-rotation,
  and revocation checks as passed; a repeat run solely for the later clean
  deployment is not required. This accepts the performed core tests, not the
  deferred firewall, browser-storage, or independent redaction reviews.
  The owner moved those three reviews to the lowest-priority, final
  [Phase 7 work package](plans/phase-7-anytime-leftovers.md#78-complete-the-lowest-priority-human-database-leftovers-plan-008).
  PLAN-008 and the full Phase 7 gate remain open for those outcomes.

- [ ] **PLAN-009 · 7 (anytime package 7.2)** — Automate generic hosted-application authentication and coarse route authorization against the accepted provider-neutral OIDC boundary; demonstrate platform/application role separation and no implicit platform-admin access. The first accepted modes are `browser-session` and `bearer-token` on explicit non-overlapping route/method rules protected by project-scoped application groups. The platform derives browser clients and callbacks from public-component routing and derives confidential service clients and audiences from stable service-access targets. Applications do not supply redirect URIs, audiences, OAuth scopes, session settings, identity-provider group paths, or proxy flags in the initial profile. Humans use first-login requests with no default group; machines require provider approval and group assignment before credential activation. Include controlled project-wide secret binding, audited group/membership lifecycle, rotation, revocation, retirement cleanup, and recovery coverage. F-10 acceptance remains required for its own story; it is scheduled in Phase 7 and does not gate Phase 3 completion. Prerequisites: Phase 2C gate; ADR-004 acceptance; PLAN-016 identity decision.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No OIDC provider/client automation or platform/application role-separation flow exists. ADR-004 was proposed at this baseline.

  **Decision update (October 2, 2026):** ADR-004 accepts a generic OIDC contract with Keycloak as the supported lab reference and platform-owned authorization. This resolves the blocking design choice but supplies no implementation or acceptance evidence for PLAN-009.

  **Implementation progress (October 11, 2026; current working tree):** Generic hosted-access API and PostgreSQL resources, durable provider operations, first-login approval, provider-approved service clients, immutable policy revisions, group-scoped normalized identity headers, private-backend network policy, replicated authorizer/per-policy OAuth2 Proxy, credential rotation and fail-closed revocation, governance metadata, retirement/purge cleanup, and recovery quarantine are implemented. CI enables isolated PostgreSQL lifecycle tests and real disposable Keycloak PKCE/machine-client plus pinned proxy configuration tests. OpenAPI and UI API types are regenerated. Source and local/provider tests are evidence only: no running-platform deployment occurred, and F-10, timed five-minute dependency-outage/revocation, actual Kubernetes/DNS/TLS isolation, and restored-access acceptance remain open. No energy-specific platform branches or external contract edits were introduced. Implement the platform first and reconcile the external energy contract afterward.

  **Deployed core evidence (October 11, 2026; EV-45):** The later operator-provided report for node-01 run `c927adee1d50` supersedes the no-deployment status of the implementation-stage note above. All 39 core assertions passed, including human approval/group/cookie/CSRF checks, machine audience and pre-approval enforcement, forged-header stripping, private-backend isolation with healthy controls, project-wide credential binding, policy lifecycle, normal/emergency rotation, five-minute held-token expiry, and denial of existing human sessions and issued machine tokens after revocation (2.357/2.310 seconds). Cleanup completed while retaining databases. This supplies deployed criterion-level evidence, not PLAN-009/F-10 closure: dependency-outage behavior, restored access, long browser/rotation timers, retention, monitoring and other full-gate checks remain unverified. Audit lifecycle and backup coverage are not certified by the core result. See the [detailed run record](../../operators/validation/access-and-authorization.md#executed-hosted-access-core-acceptance-october-11-2026).

  **Flow decision (October 11, 2026):** The public contract uses generic application groups and access policies; Keycloak and OAuth2 Proxy remain reference implementation details. The reference deployment has one realm per platform environment, separate clients/audiences per application purpose, and client-scoped group claims. `browser-session` uses Authorization Code with PKCE, a platform-derived callback/client, a secure cookie, and CSRF protection. First login records a pending human request with no authority; a provider project administrator assigns groups. `bearer-token` uses a platform-derived target audience, distinct confidential client, and `client_credentials`, never redirects, and is activated only after provider approval and machine-group assignment. Explicit non-overlapping path/method rules may combine the modes and group policies on one public component; overlaps, unmatched routes, and ambiguous `session-or-bearer` routing fail closed. The access boundary enforces coarse authorization and forwards stable principal/group IDs; applications retain only finer object/domain authorization when required. Acceptance must deny forged headers and direct-backend bypass, distinguish `401` authentication failures from `403` group denials, prove pending/unapproved human and service denial, and record that a project-wide service credential identifies the project client rather than an individual component. The accepted authorization-staleness bound is five minutes; token lifetime, browser-session claim refresh, and timed revocation acceptance must enforce it. See the [energy-system use-case plan](plans/energy-system-integration.md#2-deliver-hosted-application-identity).

  **Platform design decisions (October 11, 2026):** Use one platform-managed OAuth2 Proxy configuration per public application and a shared replicated authorizer. Map stable application-group IDs to Keycloak application-client roles and a client-scoped `groups` claim. PostgreSQL is authoritative: grants activate only after reconciliation, while `revocation-pending` denies immediately and cleanup retries. Automatic idempotent first login returns a platform pending response. Policies support authenticated exact/segment-prefix routes, explicit methods and non-empty `anyOfGroups` only; reject overlaps, ambiguous paths, anonymous routes and unmatched routes. Groups, policies, requests, memberships and approvals are first-class versioned/audited Platform API resources managed initially by project administrators. Pending requests expire after 30 days; terminal requests and revoked memberships retain 90-day records. Authorizer snapshots expire after five minutes and then fail closed. Machine tokens last five minutes; browser claims refresh in five minutes with a 30-minute idle/eight-hour absolute session. Machine rotation uses a replacement client, explicit adoption and at most 24 hours overlap. Policy revisions activate atomically with deny-first/grant-last ordering. Identity administration owns realm accounts. Display name is opt-in and email additionally requires classified personal-data opt-in. Recovery invalidates browser sessions and reconciles the restored platform catalog outward to Keycloak, rotating uncertain service credentials.

- [ ] **PLAN-016 · 7 (anytime package 7.1)** — Freeze the generic Developer Platform contracts needed by the energy-system use case: public HTTPS application-to-application communication, application identity ownership, digest-pinned public images, per-project PostgreSQL persistence, encrypted-channel scope, resource/run limits, retention, and data-classification responsibilities. Specify how application-owned `v1alpha2` declarations compose public services, private workers, optional scheduled components, readiness, bounded resources, configuration, secrets, and explicit egress. Platform source and fixtures must use neutral applications and must not contain ODIP/VEF profiles, defaults, or branches; the application repositories own their concrete declarations and domain limits. Prerequisites: Phase 2C gate; accepted cross-project contract baseline.

  **Assessment (October 10, 2026; `27a45e1`):** Source already supports the required generic component types, separate project databases, write-only project secrets, digest resolution for public images, custom readiness, bounded resources, public ingress, and operator-approved DNS/port egress. It does not provide private image credentials, durable PVC/object storage, private cross-project bindings, or PostgreSQL TLS. The first release therefore uses public images and public authenticated HTTPS, advertises PostgreSQL as its durable application-state capability, and records whether database transport is inside or outside the integration contract's encrypted-channel rule. Generic decision records are absent; concrete deployable declarations remain an application-repository responsibility, and operational acceptance is unverified.

  **Decision update (October 11, 2026):** [ADR-020](../../architecture/decisions/ADR-020-generic-hosted-application-integration.md) accepts one public component per project, public HTTPS as the cross-project encrypted boundary, unencrypted application-to-PostgreSQL transport as a bounded lab limitation, and project-wide service-credential visibility. It assigns domain-row retention to applications and infrastructure retention to the platform; retains the latest verified backup plus 14 daily/8 weekly/6 monthly points, targets seven days for centralized workload logs, keeps the existing metric/revision/audit policies, and defines Public, Internal, Confidential, and Restricted handling. Ordinary application data is limited to Confidential; Restricted values use managed secret mechanisms. Decisions are frozen, but neutral fixtures, classification records, implementation checks, and operational acceptance remain open, so PLAN-016 is not complete.

  **Application-owner confirmation (October 11, 2026):** The prioritized applications fit the platform's current resource and execution limits, require PostgreSQL as their only durable-storage capability, and can supply the required project classification and domain-retention governance records. These three capability questions are closed. Concrete declaration and record validation, neutral fixtures, implementation checks, and operational acceptance remain open, so this confirmation does not by itself complete PLAN-016.

- [ ] **PLAN-017 · 7 (anytime package 7.3)** — Make monitoring discovery component-aware and define the generic correlation evidence boundary. Discover the actual `<component>-<project>.<apps-domain>` URL and declared health profile for each public `v1alpha2` service, retain legacy compatibility, omit private-only applications, and add unit plus deployed neutral-fixture probe tests. Support application-supplied correlation keys alongside deployment revision and operation ID without interpreting domain identifiers or exposing customer details, tokens, secret values, or sensitive correlation values. Implement the ADR-020 seven-day centralized workload-log target because kubelet best-effort logs do not meet it. The external suite owns energy-domain correlation assertions. Prerequisites: PLAN-016.

  **Assessment (October 10, 2026; `27a45e1`):** Component ingress correctly uses `<component>-<project>`, but monitoring discovery still produces the legacy `<project>` hostname and reads only the flat `probe_profile`. Existing discovery tests cover only legacy specifications. Authorized pod-log reads, component status, inventory, and resource views exist; Loki does not collect k3d workload logs and no trace backend is installed. Source is partial; the component target is incorrect and deployed evidence is absent.

  **Source implementation (October 11, 2026):** Component-aware public target/path/profile discovery, private-only exclusion, legacy compatibility and bounded project/component/environment labels are implemented. Protected public probes expect credential-free login/denial; separate Kubernetes readiness metrics/rules establish semantic workload health without a public bypass or implicit membership. A dedicated read-only Kubernetes collector ships minimized operational envelopes to configured seven-day persistent Loki; pod-derived revision/operation identifiers remain non-indexed metadata. Project-authorized retained-log reads fix scope server-side and revalidate safe entries. Local blackbox/Prometheus and actual Alloy/Loki fixtures plus API/RBAC/regression tests cover source behavior; the neutral harness gains optional `--monitoring` checks. No live deployment or elapsed retention drill was executed during the implementation step; later deployed evidence is recorded below. EV-45 is unchanged, and no energy-specific source behavior is introduced.

  **Deployed partial acceptance (October 11, 2026; EV-46):** After correcting the collector identity to `0:473` and adding readiness-gated bootstrap, the operator confirmed healthy Alloy and run `60c3ca1647b9` returned `core-passed` with all 45 checks passed. The six new provider/consumer boundary-probe, semantic-readiness and central-correlation assertions establish deployed monitoring/ingestion criteria. The fixture remained `hosted-access-v0.2.0`; the report pins its digest and runner hash, not the exact deployed control-plane revision. Cleanup completed while retaining data. `sevenDayRetention: not-time-verified`, post-retirement/restart log readback and the combined monitoring/retention deferral remain open, so PLAN-017 is not checked complete. [Detailed evidence and limits](../../operators/validation/access-and-authorization.md#executed-hosted-access-monitoring-acceptance-october-11-2026).

- [ ] **PLAN-018 · 7 (anytime package 7.4)** — Automate the deployed generic integration gate. With neutral digest-pinned provider and consumer fixtures, activate a consumer-to-provider credential through the platform secret mechanism, apply and verify provider DNS/TLS plus component-scoped consumer port-443 egress, and capture safe image/revision/route/health/resource/correlation evidence. Prove browser-session first login is pending and denied until an allowed group is assigned; prove successful pre-authorized service access with the platform-derived target audience and denial for missing, expired, wrong-audience, forged-header, direct-backend, and valid-but-unapproved or wrong-group identities plus an unrelated egress destination. Separately record the versioned external energy-system suite result for dataset-level business authorization; do not duplicate its applications or assertions in platform source. Prerequisites: PLAN-009, PLAN-016, PLAN-017; application projects publish their image, configuration, readiness, access-policy/group intent, service-access target, and any fine-grained domain-authorization inputs.

  **Assessment (October 10, 2026):** Generic multi-component and egress acceptance exists, but no generic application-identity acceptance, real cross-project request, public TLS observation, or combined allowed/denied identity-and-network suite exists. Concrete application declarations are intentionally outside the platform repository. DNS rules are pinned to apply-time addresses; acceptance must record those addresses and prove that changes require reapply.

  **Automation progress (October 11, 2026):** `scripts/check-hosted-access.py` and neutral provider/consumer fixtures implement the core hosted-identity/HTTPS/network/persistence/rotation/revocation checks with an offline plan, explicit live scope confirmation, private credential-free evidence, and resumable retirement cleanup that preserves databases. Optional real-token expiry and isolated global recovery reconciliation are separate choices. Local tests, fixture image build, and disposable PostgreSQL/container checks pass; no deployed run had been performed at this source-automation stage. Reports explicitly defer the real backup restore, outage/long-timer/retention/monitoring checks and externally owned energy suite. This is source automation progress, not PLAN-018 or F-10 closure. See the [operator harness procedure](../../operators/validation/access-and-authorization.md#neutral-hosted-application-acceptance-harness).

  **Deployed core evidence (October 11, 2026; EV-45):** Node-01 run `c927adee1d50` returned `core-passed` with all 39 assertions passed, timed token expiry enabled, and `completed-data-retained` cleanup. Runner/fixture source `e8f74fd` (`hosted-access-v0.1.2`), harness SHA-256 and immutable image digest are recorded in the [detailed evidence](../../operators/validation/access-and-authorization.md#executed-hosted-access-core-acceptance-october-11-2026); the report does not attest the deployed control-plane revision. Establishes neutral two-project/four-component readiness, authenticated public HTTPS and correlation, managed project-wide binding, identity denial matrix, IPv4 backend/egress denial with healthy same-address controls, DNS-address pinning, project-isolated PostgreSQL state/restart persistence, policy activation/rollback, rotation, expiry and live revocation. IPv6 isolation, changed-DNS reapply, component monitoring/central log retention and the externally owned versioned energy suite are not demonstrated; nine checks remain explicitly deferred and `gateClosed: false`. PLAN-018 remains open.

- [ ] **PLAN-019 · 7 (anytime package 7.5)** — Prove generic platform durability and recovery, then consume externally owned energy-workflow evidence. Restart neutral multi-component fixtures, verify retained database state and version isolation, restore a verified platform backup through the supported isolated workflow, and verify recovered application resources, principals, groups, memberships, access policies, routes, and TLS. The external cross-project suite owns reapplication of its declarations, access-policy/group intent, service-access targets, and any fine-grained domain grants plus reproduction of its immutable reference result. Record both versioned results together, including snapshot, image/contract versions, recovery duration, database checks, route/TLS result, and manual identity steps. Prerequisites: PLAN-018; the external deterministic fixture and expected result are immutable and accepted.

  **Assessment (October 10, 2026):** The platform has encrypted whole-instance backups and a fresh-VM recovery workflow, but byte readback and generic SQL-marker evidence do not prove recovery of application resources or identity bindings, and platform-owned tests cannot prove domain-result recovery. Neither the generic platform recovery gate nor the external energy-system restart/restore evidence exists.

  **Partial durability evidence (October 11, 2026; EV-45):** The neutral provider's durable marker survived rolling restart, its revision stayed at 1, and the consumer retained separate PostgreSQL state; write/read statuses were `200`. This is application-path restart persistence, not backup restoration or recovered access bindings. Real backup restore, recovery reconciliation and the versioned external energy restart/restore result remain deferred; PLAN-019 remains open.

- [x] **PLAN-020 · 3 (owner-accepted exception; deployed journeys unverified)** — Deliver project-scoped hosted-application
  access definition and approval through the portal. Include governance, group
  creation, structured browser/bearer route policies and activation/revisions,
  first-login request review/approval/rejection/reopening, membership changes and
  revocation, consumer service requests, provider group approval, managed-secret
  metadata, credential rotation/adoption, and owner-scoped service revocation.
  Follow [UI increment 4a](plans/ui.md#4a-deliver-hosted-application-access-plan-020)
  and the [user journey](../../developers/ui.md#define-and-approve-application-access).
  Prerequisites: Phase 2C; existing portal authentication/project workspace;
  implemented PLAN-009 APIs and generated OpenAPI contract. Full PLAN-009
  acceptance is not a prerequisite for this UI increment. Owner: UI/API work
  package; assign a named delivery owner before implementation.

  **Acceptance:** Configure and activate the policy in the portal; observe human
  pending denial, approve explicit groups, prove admitted access after membership
  activation/session refresh, and revoke within the five-minute bound. Request
  machine access as the consumer, approve target bearer groups as the provider,
  observe active managed binding and successful allowed calls, and exercise
  rotation/adoption/revocation. Prove wrong-group, unauthorized and cross-project
  denial with direct API attempts, version-conflict handling, safe failure/pending
  states, accessible controls, and no secret/token exposure. Record dated local
  and deployed browser/audit evidence; broader PLAN-009 acceptance remains separate.

  **Definition (October 12, 2026):** Workflow and delivery scope documented at the
  owner's request. Source absent for hosted-access screens: current portal project
  and platform grants manage control-plane permissions, not application membership.
  Hosted-access API/types exist. Local and operational UI acceptance are unverified;
  this planning update supplies no implementation or acceptance evidence.

  **Source and local progress (October 12, 2026; working tree after `cf3697d`):**
  Project-scoped portal screens now cover governance, groups, structured policy
  review/save/history/rollback, human requests and memberships, provider/consumer
  service access and credential lifecycle metadata. The API adds scoped context
  and bounded operation-list reads; its PostgreSQL authorization/redaction tests
  pass. UI validation covers generated contract parity, lint, types, 31 unit
  tests, production build, and 10 fixture-backed Chromium browser journeys.
  Browser fixtures use simulated API/OIDC state and do not prove deployed identity,
  policy enforcement, managed-secret delivery, or application calls.

  **Owner-directed acceptance exception (October 13, 2026):** The owner asked to
  accept this portal increment without running every journey. The owner reports
  that the deployed Application access screens, project overview information,
  and an active policy are visible. The installation record reports source
  revision `cf3697de4418f57eb8fdd0118341582fbfcd1b18+dirty`; the committed
  base predates the PLAN-020 implementation commit `08533f6`, and the dirty
  source changes were not captured, so the exact deployed portal tree is not
  attested. No deployed browser/audit report was supplied. Policy creation and
  activation through the portal; first-login pending denial, approval, admitted
  access and revocation; consumer/provider service approval, binding, calls,
  rotation and revocation; role/cross-project denials; conflict/failure handling;
  accessibility; and secret-artifact checks remain unverified through this UI.
  The task is closed for lab sequencing by owner direction, not by a passed
  deployed acceptance journey. Revisit these checks before making a
  production-like portal claim. PLAN-009/017/018/019, F-10, PLAN-006, and the
  Phase 7 acceptance checks remain open; EV-45/46 establish API and neutral-fixture behavior,
  not this portal journey.

**Phase 5 planning decision (October 15, 2026):** The owner accepted the
EU-resident initial OpenAI boundary, LangChain with internal typed tools,
15-minute single-use project-manager approval including self-approval, bounded
investigation/evaluation gates, and content-free agent tracing. [ADR-008](../../architecture/decisions/ADR-008-ai-assisted-operations.md)
and the [Phase 5 plan](plans/phase-5-ai-operations.md) contain the exact
choices. This is a design decision; PLAN-010 through PLAN-015 remain unchecked
pending implementation and evidence. The dated task-evidence notes below are
historical snapshots.

**OpenAI EU policy update (October 16, 2026):** The owner accepted the additional
abuse-monitoring controls and Modified Retention amendment required for EU data
residency, superseding the earlier default-retention decision. OpenAI approval,
an executed amendment, and EU project/model/endpoint eligibility have not been
verified. Keep external model calls disabled until those checks are recorded;
the policy decision alone is not provider account activation. See [ADR-008](../../architecture/decisions/ADR-008-ai-assisted-operations.md).

**Global OpenAI project policy update (October 16, 2026):** The owner explicitly
accepted their Global project, superseding the preceding EU-only installation
policy. Explicit Global mode now selects the official global endpoint and requires
`OPENAI_GLOBAL_PROCESSING_ACCEPTED=true` plus a key. The previously accepted
standard abuse-monitoring retention applies; no EU residency, Zero Data Retention
or executed regional amendment is claimed. Scoped minimized Public/Internal
context, redaction, `store=false`, tool budgets and human change approval remain
in force. EU mode retains its independent verification gates and never silently
falls back. Sixteen AI tests passed, including explicit Global acceptance, missing
key/acceptance rejection, unchanged EU gating, fixed endpoint selection and
regional cost estimates. Deployment and real model evaluation remain pending.
See [ADR-008](../../architecture/decisions/ADR-008-ai-assisted-operations.md).

- [ ] **PLAN-010 · 5.1** — Expose bounded read-only Platform API tools and authorized/redacted application/revision/configuration/document context; produce sourced explanations and test project denial and untrusted-input handling. Prerequisites: Phase 4 gate; scoped data/audit evidence.

  **Source progress (October 15, 2026; `77d3c1d`–`2f3fa82`):** Added classified, human-requested AI runs, project-bound read tools, safe documentation references, sourced result validation and fail-closed regional model configuration. Targeted unit and OpenAPI tests pass. Deployed project-denial and real-model explanation evidence remains open.

  **Owner-executed ODIP explanation passed (October 16, 2026; deployment through `b61c32a`):** Human CLI run `cda304f2-94f4-499f-bb60-4de2a5e434b5` returned `completed` for ODIP revision 17. Three observations cite the authorized project-catalog evidence `E1`: applied revision, metrics/tracing-enabled web service, and tracing-enabled scheduled ingestion worker. The result contains no diagnostic hypothesis, reports absent business/runtime-health evidence as gaps, and sets `insufficient_evidence=false`. It used one read-tool call with estimated cost **$0.004388**. Record this live human explanation journey as **passed**. PLAN-010 remains open for its other boundary checks; incident diagnosis, second-provider scoring, proposals and approved recovery are not established by this run.

  **Explanation-result correction (October 16, 2026; `b61c32a`):** The owner retrieved the saved ODIP run: it accurately described revision 17, the web service and scheduled worker, but was marked `abstained` because the shared result contract required diagnostic hypotheses. Results now separate validated sourced observations from hypotheses. Catalog explanations can complete with observations and optional scope gaps; incident diagnoses still require supported hypotheses, and missing/unavailable/foreign citations still force abstention. Twenty-one AI tests passed. The targeted API deployment became healthy, and a real-model synthetic catalog explanation completed with three sourced observations, zero hypotheses, one tool call and estimated cost $0.003686. The original ODIP run was preserved; a new human CLI explanation remains to be checked. This narrow correction does not change or close the failed incident-diagnosis evaluation gate.

  **Human ODIP run and audit repair (October 16, 2026; `7f41c32`):** The owner used human CLI authentication to classify ODIP Internal and request `explain_application`. Run `d41f44f7-58e7-4fd4-94c0-573abb85d9ac` was saved as `abstained` after one read-tool call (estimated cost $0.003148), but the API returned 503 because it sent that domain state to the audit table's restricted result field. Source now maps completed/abstained runs to audit `succeeded`, failed runs to `failed`, and retains the domain state in event details. Eighteen AI tests passed, including all three run states and audit-unavailability enforcement. A targeted API rebuild/recreation became healthy. The missing audit event was appended as ID 4797 using the saved original requester/outcome, explicitly marked as recovered after audit failure; the model was not rerun. The existing run can be retrieved through its project-scoped GET. This repairs delivery/audit behavior; the abstention is not a passed application explanation.

  **Global activation and first real-model evaluation (October 16, 2026; `0a07c26`):** After the owner installed a project key in node-01's protected `.env`, only the Platform API was rebuilt/recreated. Health returned HTTP 200; the adapter selected `openai:gpt-6.1-sol` at `https://api.openai.com/v1`, Global processing acceptance was true, all three EU verification flags remained false, and response storage was false. Six synthetic cases used the real model without real project context or write tools. All stayed within budgets (eight tool calls each); insufficient-evidence, untrusted-document and foreign-project-request cases passed their abstention checks. All three known-cause diagnosis cases failed: **0/3 accuracy**, below the 80% gate. Estimated total cost was **$0.087504**. Private score-only evidence: `/opt/developer-platform/.runtime/ai-evaluation/global-initial-20261016.jsonl`. Model connectivity/configuration is verified; diagnosis quality, live human project-scoped runs and the second-provider evaluation remain open. This does not close PLAN-010–015 or establish deployed project-isolation security acceptance. Preserve these results while investigating evidence sufficiency and tool-budget behavior.

  **Deployed gate check (October 16, 2026; `4508274`):** Node-01 Ansible deployment passed 37 tasks with no failures. The API is healthy and its OpenAI EU project, processing, and amendment verification flags remain false. This establishes fail-closed deployment configuration, not account eligibility or model evaluation.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No AI layer or authorized context/tools; ADR-008 accepts product focus only, not its implementation.

  **Investigation timeout repair (October 16, 2026; `9b4d6b7`):** Human ODIP investigation `1474f682-25e1-48ef-92e6-ab8ac4b2a976` returned `failed`; the API's safe log identified `OpenAITimeoutError`. The adapter previously allowed ten seconds per call, and an outer failure handler discarded prior progress. Model calls now receive up to 30 seconds, capped by remaining run time; automatic retries remain disabled. Model failures preserve collected evidence, read-call counts and successful-response costs, marking failed-request usage incomplete. CLI AI-run creation now waits up to 120 seconds for the existing 90-second server budget, without retrying POST. Twenty-three AI tests and three CLI client tests passed, including deadline handling, partial-progress retention and no duplicate POST on timeout. The targeted API deployment became healthy; a bounded real-model synthetic explanation completed with three sourced observations, one tool call and estimated cost $0.003636. The original failed run remains unchanged and is not acceptance evidence; the human investigation retry and diagnosis-quality gate remain open.

- [ ] **PLAN-011 · 5.2** — Correlate incident logs, metrics, authorized traces and history with timestamps/comparison windows; distinguish observations/hypotheses and explicitly report missing evidence. Prerequisites: PLAN-010; PLAN-021; DEV-004-T02; DEV-005-T02; DEV-007-T02.

  **Owner-executed known startup diagnosis passed (October 16, 2026; `4409bb1`):** Human disposable-project run `c667e949-cd80-4c3c-813a-56494d47547c` completed with `insufficient_evidence=false`, five sourced observations and one tentative causal hypothesis. It linked revision 2's changed startup arguments to the revision-specific `unrecognized_startup_option` signature, exit code 2, ten restarts and failed rollout, while identifying the surviving ready container as revision 1. It correctly left the exact offending argument and user impact unresolved. Four scoped tools and estimated cost $0.014140 stayed within budget. Record this controlled live known-cause investigation as passed. It does not establish the full corpus accuracy/security gate, proposal review, approval, execution or recovery; those remain open. This completed sourced run is available for the human recovery-proposal journey.

  **Revision-linked startup cause evidence (October 16, 2026; `0ad8849`, scope clarification `4409bb1`):** Runtime summaries now include validated numeric pod revision annotations. The new bounded reader checks namespace/project/component/current-revision identity and nonzero application-container exit status before reading up to two containers' current/previous Kubernetes logs. Only an exact allowlisted Go flag-parser signature becomes the fixed code `unrecognized_startup_option`; raw text, flag names and values never reach model context or logs. Read errors and truncation are explicit; the retained operational-envelope contract is unchanged. All 39 AI tests and nine readiness tests passed, including cross-project/stale-pod rejection, sidecar exclusion, hostile text, response limits and unavailable reads. A read-only deployed check identified the healthy container as revision 1 and the crashing container as revision 2, and matched the startup-option signature for revision 2 with API health 200. The initial seven-tool synthetic check still abstained ($0.018078). Investigation task wording was then clarified to assess a supported likely deployment/runtime failure cause separately from unknown request impact. With that candidate wording, the bounded known-cause synthetic check completed with a sourced startup hypothesis (five tools, $0.014036); its paired variant without cause evidence abstained with no hypotheses (seven tools, $0.018456). Neither response failed citation validation. The targeted API deployment of the clarified scope became healthy; a post-deployment check verified the new wording was loaded and health returned 200. These focused checks establish the evidence/scope repair, not the full corpus gate or human recovery acceptance. No proposal, approval or rollback was performed.

  **Owner-executed enriched investigation (October 16, 2026):** Run `ecebe5c6-91c0-4b7e-895a-32179d073aa5` consumed the new revision and container diagnostics successfully: four sourced observations, two tentative hypotheses, eight tools and estimated cost $0.024930. It identified changed startup arguments as a plausible lead alongside CrashLoopBackOff and exit code 2, while correctly retaining uncertainty about argument validity, pod/revision identity, timing and impact. Record evidence integration and safe abstention as passed; known-cause diagnosis and recovery are still open. Repeating the same request without new evidence is not the next acceptance step. Inspection confirms retained logs accept only the operational-envelope event/level/correlation fields; this fixture's unstructured CLI startup error is unavailable through that path. Next work needs explicit pod/revision provenance and bounded startup failure evidence, with privacy-contract changes reviewed and tested; weakening sufficiency or using an explanation run to bypass proposal eligibility is not justified. No proposal, approval or execution occurred.

  **Bounded startup evidence deployed (October 16, 2026; `a77d77a`):** Revision comparison now reports current/previous revision IDs, explicit comparison availability and fixed changed component field names without values. Optional readiness diagnostics report application-container readiness, bounded restarts, allowlisted reason codes and numeric exit codes, excluding sidecars and Kubernetes messages. Thirty-two AI tests and nine readiness tests passed. After the targeted API deployment became healthy, read-only live checks confirmed revision 2 versus 1 changed only `args`, alongside an old ready container and a restarting container (`CrashLoopBackOff`, prior `Error`, exit code 2); API health returned 200. One bounded real-model synthetic check with these evidence categories returned five observations and two hypotheses without contract errors, seven calls and estimated cost $0.017820, but still abstained. This establishes richer evidence collection and contract handling, not exact known-cause diagnosis or recovery. Human investigation retry remains open; no proposal or rollback was executed.

  **Owner-executed fault investigation retry (October 16, 2026; validator `f56fa88`):** Disposable-project run `48a726b6-a6cb-460a-87cf-beb809d66982` passed the sourced result contract with four observations, two tentative hypotheses, seven tool calls and estimated cost $0.020518. It correctly distinguished revision 2's successful apply operations from runtime `failed / ProgressDeadlineExceeded`, did not equate one ready replica with a healthy new rollout, and identified absent logs, metrics, traces and pod-level evidence. Its `abstained` / `insufficient_evidence=true` outcome is justified. Record the live contract repair and evidence-limited abstention as passed; known-cause diagnosis and recovery remain open. Inspection confirms `get_configuration` compares configuration key/value changes only and does not expose the changed startup arguments; runtime evidence exposes aggregate readiness only. A richer bounded, value-free revision comparison and safe pod failure details are the next implementation steps. This abstained run does not satisfy the completed-run requirement for proposal creation; no proposal, approval or recovery has occurred.

  **Owner-executed no-injected-fault investigation passed (October 16, 2026; `9b4d6b7`):** Human ODIP run `e458ddb6-6434-415b-8e70-09c125d7a0a7` returned `abstained` after collecting eight project-scoped sources (catalog, deployments, HTTP metrics, readiness, log counts, events, configuration-key changes and declared dependencies). It reported applied revision 17 and readiness 1/1, distinguished missing server-error metrics from zero, identified truncated logs and absent trace/incident details, and kept the relationship to historical deployment failures explicitly tentative. `insufficient_evidence=true` is appropriate because no incident was injected or specified. The run stayed within eight tools and estimated cost **$0.035662**, with no application writes. Record this bounded live no-fault investigation/abstention journey as **passed**; it does not establish known-cause accuracy, fault recovery, cross-project denial or all PLAN-011 criteria. The failed synthetic diagnosis gate remains open.

  **Source progress (October 15, 2026):** Bounded read tools expose operation history, five-minute metrics, one-hour safe log counts, scoped trace summaries, readiness reasons and configuration key changes. Run results carry evidence references and abstention. Live correlation quality is unverified.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No AI incident correlation; underlying scoped telemetry and deployment history are also incomplete (UC-06).

- [ ] **PLAN-012 · 5.3** — Implement read-only investigation with tool budgets/errors; evaluate bad database host, pool exhaustion, resource pressure and insufficient evidence for diagnosis, abstention, unnecessary calls and time/cost; test injection and secret/project boundaries. Prerequisites: PLAN-011.

  **Owner-directed second-provider deferral (October 16, 2026):** Move second-provider selection, setup, any required adapter implementation and corpus evaluation to [Phase 7 package 7.10](plans/phase-7-anytime-leftovers.md#ai-model-provider-leftovers), unscheduled and lowest priority. It no longer gates Phase 5 and requires no provider/account decision now. Preserve the provider-neutral interface and the accepted primary-provider results; second-provider interoperability remains unverified, not passed. This disposition overrides earlier notes describing that evaluation as a Phase 5 prerequisite. Broader adversarial and other remaining Phase 5 acceptance criteria are unchanged.

  **Deployed diagnostic readback and empty-history repair passed (October 16, 2026; `74847d8`):** A live healthy-service read exposed a Kubernetes dynamic-client edge case: empty `lastState` objects are truthy, so the reader unnecessarily requested unavailable previous logs. The source now checks explicit prior termination/restart metadata, with a regression using actual dynamic `ResourceInstance` objects; all 64 AI tests passed. The targeted API deployment became healthy. Readback then confirmed current revision 3, exactly one scoped running-container read, zero unavailable reads, explicit `no_match`, output below 2 KiB and no raw log fields. Independent runtime readback confirmed all service components still ready at unchanged revision 3. This verifies deployed read integration, not a live injected database fault. The second-provider portability test awaits an available provider/account or local endpoint; broader adversarial evaluation remains open.

  **Primary-provider diagnostics-v2 evaluation passed (October 16, 2026; `9e589a9`, `c895ca7`):** Added current-revision, project/component-scoped fixed database hostname-resolution, pool-capacity-timeout and pool-acquisition-timeout signatures. Running containers are eligible because readiness does not establish pool health. Raw log text, hostnames, pool names, credentials and SQL are not exported; unmatched/unavailable/truncated sampling remains explicit. All 64 AI tests passed. An installed Psycopg error-format check and a real exhausted SQLAlchemy QueuePool over in-memory SQLite verified both diagnostic families with no network or project data; SQLAlchemy is verification-only. Versioned diagnostics-v2 fixtures exercise the production reader/projection with synthetic I/O and reuse live typed tool contracts/descriptions. They add two key-change-only abstention variants and strengthen scoring to require matching cause concepts and a citation to the discriminating tool; provider failures cannot count as abstention. The deployed real-model run passed **3/3 known causes and 5/5 abstention cases**, with 5–8 reads, 17.851–22.131 seconds per case, no contract errors and **$0.153910** total estimated cost. All time/read/cost gates passed, without lowering the 80% diagnosis threshold. Score-only evidence is retained at node-01 `.runtime/ai-evaluation/global-diagnostics-v2-20261016.json`. Original v1 observations and failed results remain available and unchanged. This closes the primary-provider synthetic diagnosis/abstention gate; live database fault-specific acceptance, broader adversarial testing and second-provider evaluation remain distinct open work.

  **Post-finalization corpus result (October 16, 2026; `a3d20c1`):** The targeted API deployment became healthy. The unchanged six-case real-model corpus then scored **1/3 known-cause accuracy**: resource pressure passed; database-host and pool cases still abstained. All three missing-evidence/untrusted-document/foreign-project cases passed abstention, all read/cost checks passed, no result-contract errors occurred and no case used the generic limit fallback. Every case consumed eight reads; total estimated cost was $0.103454. Score-only reports were retained on node-01 under `.runtime/ai-evaluation/global-before-budget-finalization-20261016.json` and `global-after-budget-finalization-20261016.json`. This demonstrates improved final assessment, but remains below the 80% quality threshold and does not close the gate. The database cases expose changed configuration keys and aggregate symptoms rather than discriminating database/pool diagnostics; next work is bounded diagnostic evidence and a stronger, production-contract-aligned corpus. Do not relabel the failed cases as passes or lower the threshold. Second-provider and broader adversarial evaluation remain open.

  **External-model eligibility and run isolation checks passed (October 16, 2026):** Added endpoint regressions verify that unclassified, Confidential and Restricted projects, and automation callers, are rejected with 403 before model configuration or invocation. All 51 AI tests passed. The deployed rollback-only PostgreSQL verification now also checks AI-run lookup: the owning synthetic project can retrieve its record, while another project cannot retrieve the same run UUID. All nine isolated database checks passed and both temporary tables were rolled back. These are source/isolated database checks, not additional live human policy-change journeys or a complete adversarial data-leakage assessment.

  **Full corpus rerun before budget-finalization repair (October 16, 2026):** The current six-case synthetic corpus still scored 0/3 known-cause accuracy, while missing-evidence, untrusted-document and foreign-project cases all passed abstention. All cases consumed eight reads, remained within cost limits and had no result-contract errors; total estimated cost was $0.094202. Preserve this failed gate independently of the passed live startup journey. Inspection and regression tests identified a loop weakness: at the read limit the model could request another tool and fall through to a generic limit result rather than produce a final assessment. The adapter contract now permits a tools-disabled binding; the agent requests final JSON from collected evidence after eight reads, with unchanged nine-call/90-second/$0.25 limits. A provider ignoring disabled tools still cannot execute a ninth read. All 49 AI tests pass. This repair is not itself a passing diagnosis gate; a real-model rerun is required.

  **Result-contract repair (October 16, 2026; `f56fa88`):** Owner-run disposable-project investigation `d137f751-9234-46eb-9da6-d2ce6b076126` collected seven sources, including failed runtime readiness and an empty log result, but its final result failed the sourced contract (estimated cost $0.020074). The original raw response was not retained, so its precise rejection reason cannot be established. Regression tests reproduced a defect where an observation referencing an empty source discarded an otherwise supported result. Such references now become fixed availability-only observations; hypotheses still require an available source, and unknown references are rejected. Fixed validation reason codes expose future rejection causes without logging model output. All 31 AI tests passed and the targeted API deployment became healthy. One bounded real-model synthetic failure investigation returned four observations and one hypothesis with no contract error, seven tool calls and estimated cost $0.015588; it correctly retained `insufficient_evidence=true` and abstained. This verifies contract handling, not known-cause accuracy. The original owner run remains failed acceptance evidence; human retry and diagnosis/recovery acceptance remain open.

  **Source progress (October 15, 2026):** The LangChain loop limits tools, duration, estimated cost and output size; unknown tools and project arguments are rejected. A synthetic six-case corpus and runner are committed. Actual model scoring, second-provider scoring and deployed security evidence remain open.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No investigation tool loop, incident corpus evaluation or AI boundary tests.

- [ ] **PLAN-013 · 5.4** — Generate a reviewable configuration/deployment diff bound to target and revision, with supporting evidence and a rollback plan; do not execute it at this stage. Prerequisites: PLAN-012.

  **Owner-created rollback proposal passed (October 16, 2026):** Human proposal `2ee5e988-5e18-4440-a274-a64c2f49e813`, requested using completed investigation `c667e949-cd80-4c3c-813a-56494d47547c`, proposes rollback of `ai-acceptance` from base revision 2 to retained target revision 1. Its reviewable structural diff lists only `/components`, with SHA-256 `974adbd6f1498b851c1d54814717e9f33cfee5ccca3578a105a921a80e777563` and an explicit recovery-failure plan. Record the controlled live proposal-creation step as passed. The diff exposes structural paths rather than startup argument values; the earlier fixture comparison established the argument-only change. No approval, execution or recovery is established by this result; the complete task and remaining gates stay open.

  **Runtime-failure proposal support (October 16, 2026; `f98a431`):** The owner classified `ai-acceptance` Internal and applied the controlled invalid-startup-option fixture at revision 2 (operation `ff395e57-66f8-4b03-9b5c-97412cfe17b6`). Apply succeeded, while readiness reported `CrashLoopBackOff` with an old ready replica. This exposed a proposal eligibility gap: only failed apply operations qualified. Source now also accepts a succeeded apply when the server confirms service runtime state `failed`; healthy/progressing/unknown states, stale revisions and in-flight operations remain rejected. Completed sourced runs, prior retained success, human approval and execution checks remain required. Twenty-eight AI tests passed. The targeted API deployment became healthy, and a read-only live check observed revision 2 `failed / ProgressDeadlineExceeded` and selected retained revision 1 as the candidate. No proposal was created, approved or executed by this check; human diagnosis/proposal/recovery acceptance remains open.

  **Source progress (October 15, 2026):** A narrow rollback proposal selects a retained successful revision after a failed latest deployment, binds it to a completed sourced run, and records a canonical value-free path diff, hash, target and base revision. Other fix types and deployed review remain open.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No evidence-linked AI diff/approval-plan flow.

- [ ] **PLAN-014 · 5.5** — Apply only an exactly approved diff through authorized Platform API calls; reject stale approvals, audit execution and verify observed health/metrics. Demonstrate regression, investigation, approval and recovery in test resources. Prerequisites: PLAN-013; DEV-007-T02; OPS-001-T01.

  **Automated guard and audit verification passed (October 16, 2026; `c7b836f`):** Seven added endpoint/queue regression tests verify initial permission denial, automation denial for approval/execution, permission recheck inside the transaction, rejected approval handling/audit, stale-base rejection without consuming approval, and the real queue's stale-revision check before mutation. All 46 AI tests passed. The deployed `verify-ai-approval-guards.py` exercised actual PostgreSQL approval SQL with eight passing checks: unapproved execution, changed-hash approval, exact-hash approval, foreign-project execution, changed-hash execution, expiry, reuse and reapproval after execution. All fixture writes were confined to a temporary shadow table in a forced-rollback transaction; cleanup was verified and no live proposal/project/operation was modified. A separate audit-reader-role review found all six expected human-journey events (investigation, development assistance, proposal creation, approval, successful execution and rejected reuse), verified project scope and allowlisted detail keys, and confirmed exactly one successful execution referencing revision 3 and the original operation. These establish automated endpoint/database safeguards and durable live audit evidence; isolated database fixtures do not claim additional human HTTP expiry/staleness journeys or full adversarial evaluation.

  **Agent trace readback passed with controlled synthetic run (October 16, 2026):** A separate diagnostic process sampled its synthetic LangChain-loop run at 100%, without external model calls or changes to production's 10% sampling. Trace `8c8a26520b2a6ec2895b4aa7f72e3b7a` was retrieved from deployed Tempo using the existing explicit time-window lookup pattern. Review verified one AI-run span, two model spans, one tool span, correct parent-child links, nonnegative durations, allowlisted resource/span attributes and empty span events/status messages. The initial recent-data lookup/search did not return the trace; explicit-window readback later succeeded. Aggregate Alloy and Tempo counters showed accepted/exported/received spans with zero refused spans. No trace was found for the specific human investigation under normal sampling; this check establishes controlled instrumentation/export/readback and metadata privacy, not complete sampling coverage or real-provider latency/cost tracing. The reusable operator review script prints verification metadata only. Two tracing boundary tests also passed. Full corpus/security and second-provider evaluation remain open.

  **Owner-verified state after rejected reuse passed (October 16, 2026):** Proposal readback at 15:01:48 UTC retained state `executed`, original operation `82f348a5-473b-48db-b8b9-aa568637175d` and resulting revision 3, with succeeded operation and ready runtime. Independent component readback at 15:01:57 UTC confirmed project revision 3 and `web` ready 1/1 with the expected pinned image. Together with the preceding 409, record the live single-use execution check and unchanged project revision as passed. Expiry, changed-hash, stale-revision and unauthorized-execution checks remain separate open criteria; this result does not close the full task.

  **Owner-tested repeated execution rejected (October 16, 2026):** Re-executing already-used proposal `2ee5e988-5e18-4440-a274-a64c2f49e813` with the originally approved hash returned HTTP 409, `Approval expired, changed, used or revision is stale`, and `retryable=false`. Record the live rejection of a reused proposal as passed; the generic error does not independently establish expiry, changed-hash or stale-revision rejection. Proposal/operation and revision readback should confirm no additional deployment was created. Other rejection safeguards and audit/trace review remain open.

  **Owner-verified approved recovery passed (October 16, 2026):** Operation `82f348a5-473b-48db-b8b9-aa568637175d` succeeded at revision 3, with runtime readiness `ready`, desired/ready replicas 1/1, no failure reason and the expected pinned `hashicorp/http-echo` digest active. Independent human component readback confirmed project revision 3 and `web` ready at 14:59:37 UTC. An intervening 401 on component readback was resolved by renewing authentication; it was not a workload failure. Record the controlled startup regression → sourced diagnosis → exact-diff proposal → human approval → execution → readiness recovery journey as passed. The private fixture has no request metrics/traces, so no metric recovery or external endpoint check is claimed. Live rejection safeguards, audit/agent-trace review, full corpus/security evaluation and development assistance remain open. No credential values are retained in this evidence record.

  **Owner-triggered approved execution queued (October 16, 2026):** Human execution of exact-diff-approved proposal `2ee5e988-5e18-4440-a274-a64c2f49e813` queued operation `82f348a5-473b-48db-b8b9-aa568637175d` at new revision 3. Record successful submission through the approved execution path; operation success, rollout readiness and recovery are not established by the queued response. Await operation/component readback before claiming the recovery journey passed.

  **Owner-approved exact rollback diff passed (October 16, 2026):** Human CLI approval of proposal `2ee5e988-5e18-4440-a274-a64c2f49e813` returned state `approved`, binding project `ai-acceptance`, investigation `c667e949-cd80-4c3c-813a-56494d47547c`, base revision 2, target revision 1 and SHA-256 `974adbd6f1498b851c1d54814717e9f33cfee5ccca3578a105a921a80e777563`. Approval was granted at 14:57:22.078301 UTC and expires at 15:12:22.078301 UTC, demonstrating the configured 15-minute window. Operation ID and resulting revision remained null. Record the live exact-diff approval step as passed; execution, recovery and rejection safeguards remain unverified.

  **Disposable baseline passed (October 16, 2026; fixture `77bf91e`):** The owner created project `ai-acceptance` and deployed its digest-pinned private HTTP baseline through the human CLI. Operation `a911869f-bf6d-44e1-bad8-35f7f9fd9e56` succeeded at revision 1, with desired/ready replicas 1/1 and the expected `hashicorp/http-echo` digest active. Record this as the retained successful rollback baseline. No fault injection, AI proposal, approval, execution or recovery is established yet.

  **Source progress (October 15, 2026):** Human project-manager approval binds the diff hash for 15 minutes and one execution. Execution rechecks authority and revision and queues the existing rollback operation; proposal reads expose operation readiness and available metrics. The deployed regression/recovery proof remains open.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No revision-bound AI approvals, execution integration or observed-recovery demonstration (F-12).

- [ ] **PLAN-015 · 5 (after 5.5)** — Demonstrate development assistance grounded in authorized docs, ADRs, contracts and repository context: template selection, change impact or review with runtime evidence; retain source references and project/secret boundaries. Prerequisites: PLAN-014.

  **Owner-executed bounded development assistance passed (October 16, 2026):** Human run `b65ecbd8-7547-4133-a459-ab46a44dae8c` completed on `ai-acceptance` revision 3 with five sourced observations, two tentative change-impact hypotheses, five read tools and estimated cost $0.017550. It selected the committed deployment API reference, correlated the revision 2-to-3 startup-argument field change with deployment history and current ready runtime, and explicitly distinguished startup/readiness from functional correctness, performance and sustained health. It acknowledged that documentation tools expose committed reference summaries rather than full schemas/example contents. Record this bounded live documentation-selection/change-impact demonstration as passed. It does not establish arbitrary repository retrieval, full documentation analysis, adversarial project/secret boundaries or completion of the prerequisite PLAN-014 safeguards; those broader gates remain open.

  **Source progress (October 15, 2026):** A bounded `development_assistance` run can cite curated committed template, API and ADR references alongside project-scoped observations. The later owner-executed demonstration above supplies live evidence for this bounded flow; broader task criteria remain open.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No development assistant using project docs/contracts/repository/runtime context.

- [x] **PLAN-025 · 5.6 (owner-accepted)** — Add project-scoped AI assistance to the portal: classification/eligibility settings, explicit explanation/investigation/development actions, durable run/proposal discovery and resumption, sourced results and gaps, exact-diff review, separate human approval/execution and observed recovery. Add bounded list endpoints and strengthen server eligibility checks where required. Verify role/project boundaries, timeout/unknown-outcome handling without duplicate model requests, stale/expired/reused approvals, accessible controls and redacted browser/audit evidence. Prerequisites: PLAN-010–015 API capabilities and existing portal authorization. See the [AI portal integration plan](plans/phase-5-ai-operations.md#ai-portal-integration).

  **Owner-added Phase 5 scope (October 16, 2026):** Inspection found AI endpoints in generated UI types but no AI routes, screens or controls. The owner requested this integration in the plan. It is required Phase 5 work, not an anytime leftover. At that planning checkpoint, source implementation and UI/browser acceptance were unverified; existing CLI/API results did not count as UI evidence. Second-provider work stays independently deferred to Phase 7 package 7.10.

  **Implementation and local verification (October 16, 2026):** Added the project AI route, classification/eligibility display, explicit assistance actions, durable paginated history, sourced results, exact-hash human confirmations and recovery observations. The API now binds new investigations to trusted revisions and rejects non-investigation, unbound, stale or duplicate proposal sources. Policy changes preserve the existing human platform-administrator restriction; project management permission covers proposal actions. 70 AI backend tests and the full UI check (40 unit tests, API types, lint, typecheck and build) passed. The complete browser suite passed 25 tests, followed by all 16 final AI browser cases including two additional keyboard/resumption checks. These use synthetic browser fixtures. At that checkpoint, authenticated deployed browser acceptance remained open; these automated results alone did not close PLAN-025 or Phase 5. See the linked plan for implementation and migration details.

  **Targeted deployment verification (October 16, 2026; `4b20f11`):** API/portal rebuilt and healthy. Seven rollback-only PostgreSQL history/revision guards and nine existing approval guards passed; no live proposal writes. `ai-acceptance` remained healthy at revision 3. A missing server deep-link route was found and fixed, with four portal backend tests passing. Final anonymous Chromium direct load/reload passed (HTTP 200, zero browser errors, zero AI mutations); unauthenticated AI context and both histories returned 401. At that checkpoint, authenticated human UI acceptance remained open.

  **Owner-tested UI acceptance (October 16, 2026; deployed source `4b20f11`):** The owner reported “i have tested the ui and it is accepted”. Mark PLAN-025 / Phase 5.6 complete and accepted. No individual scenario transcript or additional run/proposal IDs were supplied; retain the scope of previously recorded automated, database, browser and CLI evidence. This acceptance closes the AI portal task; other Phase 5 gates retain their existing status.

- [x] **PLAN-021 · 4.1 (owner-accepted exception; follow-up in 7.9)** — Instrument the current API and durable worker with bounded OpenTelemetry traces and operator-only collection/storage. Correlate requests, authorization outcomes, operations, retries and provider calls without secret or personal values; prove scoped access, collection failure isolation, resource limits, and deployed trace readback. Prerequisites: usable scoped metrics/logs and a recorded backend, sampling, retention and recovery decision. Full PLAN-017 acceptance remains in Phase 7 and does not gate this task. See the [Phase 4 plan](plans/phase-4-tracing-and-dashboards.md).

  **Owner-directed completion (October 16, 2026; baseline `4681e56`):** Complete for the Phase 4 delivery gate under the owner's explicit instruction. All remaining acceptance and any fixes it reveals are deferred to [Phase 7 package 7.9](plans/phase-7-anytime-leftovers.md#79-complete-deferred-phase-4-acceptance), at the lowest priority with no Phase 5 dependency. The package names the unverified outcomes; earlier open-evidence notes below remain historical and do not override this disposition. Only checks explicitly recorded as passed are passing evidence.

  **Source progress (October 15, 2026; `f0aa876`):** Added bounded platform tracing, private Alloy/Tempo source, sampling configuration, fixed trace storage budget and local configuration checks. Deployed trace readback and failure isolation remain unverified.

  **Deployed infrastructure check (October 16, 2026; `4508274`):** After the operator prepared the four GiB Tempo mount, the Ansible deployment completed with 37 successful tasks and no failures. PostgreSQL and Platform API were healthy; Alloy and the telemetry gateway were healthy; the API container received HTTP 200 from Tempo `/ready`; and the fixed-address check passed. Scoped Kubernetes credential files were mode 0640 with UID-specific ACLs. No representative trace readback, retention elapsed check, application framework fixture, collector-failure drill, or dashboard panel acceptance is established by this startup check.

  **Planning baseline (October 14, 2026):** Prometheus, Loki, Alloy and Grafana exist, but there is no trace backend or instrumented end-to-end operation path. No source, local or deployed tracing acceptance is claimed.

  **Design decision (October 15, 2026):** [ADR-021](../../architecture/decisions/ADR-021-phase-4-tracing-boundary.md) selects Tempo 3 single-process/local storage, Compose Alloy, 10% head sampling, 24-hour retention, a hard 4 GiB trace filesystem, bounded ingestion and disposable trace recovery. These are accepted implementation choices, not acceptance evidence.

- [x] **PLAN-022 · 4.2 (owner-accepted exception; follow-up in 7.9)** — Provision versioned, operator-only Grafana dashboards for platform health/delivery, workloads/capacity, and telemetry/security. Validate panel queries, meaningful missing-data states, safe trace/log links, restart/reconciliation, failure diagnosis, redaction and deployed evidence. Prerequisites: PLAN-021 and existing scoped metrics/logs. See the [Phase 4 plan](plans/phase-4-tracing-and-dashboards.md).

  **Owner-directed completion (October 16, 2026; baseline `4681e56`):** Complete for the Phase 4 delivery gate under the owner's explicit instruction. All remaining acceptance and any fixes it reveals are deferred to [Phase 7 package 7.9](plans/phase-7-anytime-leftovers.md#79-complete-deferred-phase-4-acceptance), at the lowest priority with no Phase 5 dependency. The package names the unverified outcomes; earlier open-evidence notes below remain historical and do not override this disposition. Only checks explicitly recorded as passed are passing evidence.

  **Owner-verified dashboard acceptance (October 16, 2026):** The owner confirmed that the dashboards were already verified using VEF (the Quarkus application deployed as `vareng`) and ODIP (Spring Boot). Record the performed live dashboard checks as **passed** for PLAN-022 and the dashboard portion of PLAN-023. This supplements the automated live query, provisioning, JVM and workload-capacity evidence below; repeating functional dashboard verification with disposable JVM applications is not an outstanding requirement. This confirmation does not claim FastAPI runtime coverage, injected collector/backend failures, trace/log-link verification, or retention/security checks; those unperformed acceptance items remain tracked separately.

  **PostgreSQL and host storage extension (October 16, 2026; `f1b4cfc`):** Added a private pinned PostgreSQL exporter with a dedicated `pg_monitor` login, bounded collection and reviewed aggregate metrics, plus a 15-panel **PostgreSQL** dashboard with a database selector. Connection state, lock waits and transaction age are aggregated before export; SQL text, session identities and table labels are excluded. The disposable PostgreSQL 18/exporter/Prometheus fixture passed repeatable role setup, denied application-table reads/writes, metric privacy, database selection and dashboard query checks; the monitoring configuration/rule suite and ten network-bootstrap tests passed. Live node-01 collection reported `up=1`, `pg_up=1`, scrape error zero and 283 retained samples. Panel queries returned the expected signals for `platform`, `project_odip` and `project_vareng`; unlimited database limits and inactive cache ratios correctly returned no series. **Workloads and capacity** gained host storage utilization, total/available bytes and inode usage; live readback covered `/` and `/boot/efi` space and root inode usage. The exporter has no published port and uses a restricted password file. Deployment started only the new exporter and reloaded Prometheus/Grafana; PostgreSQL and applications were not restarted. Per-table maintenance metrics are not included, and no new failure-injection or elapsed-retention acceptance is claimed.

  **Owner-verified PostgreSQL and storage panels (October 16, 2026):** After deployment through `b347e92`, the owner confirmed that the PostgreSQL dashboard and new host storage panels are working. Record their live functional dashboard checks as **passed** for PLAN-022, supplementing the automated readback above. These performed checks do not need repeating; unperformed failure/recovery, trace/log-link and retention checks remain separate.

  **Source progress (October 15, 2026; `c7aed4e`):** Added three generated operator dashboards and provisioning source. Live panels, restart and failure drills remain unverified.

  **Planning baseline (October 14, 2026):** Grafana data sources are provisioned but dashboards are not. No dashboard implementation or deployed acceptance is claimed.

- [x] **PLAN-023 · 4.3 (owner-accepted exception; follow-up in 7.9)** — Add a versioned, opt-in application metrics declaration and private scrape discovery for deployed service components; expose bounded project-scoped reads and provision one shared HTTP application dashboard plus a Micrometer JVM dashboard. Prove metric/label limits, missing-data behavior, cross-project denial, retirement cleanup, resource cost, and deployed readback with instrumented neutral fixtures. Prerequisites: PLAN-022's operator dashboard provisioning path and the existing authorized Platform API observation boundary. See the [Phase 4 plan](plans/phase-4-tracing-and-dashboards.md#43-collect-hosted-application-metrics-plan-023) and [N-10](../../product/requirements.md).

  **Owner-directed completion (October 16, 2026; baseline `4681e56`):** Complete for the Phase 4 delivery gate under the owner's explicit instruction. All remaining acceptance and any fixes it reveals are deferred to [Phase 7 package 7.9](plans/phase-7-anytime-leftovers.md#79-complete-deferred-phase-4-acceptance), at the lowest priority with no Phase 5 dependency. The package names the unverified outcomes; earlier open-evidence notes below remain historical and do not override this disposition. Only checks explicitly recorded as passed are passing evidence.

  **Accepted dashboard scope (October 16, 2026):** Live dashboard verification with VEF/vareng and ODIP is owner-confirmed **passed**, as recorded under PLAN-022. Remaining framework-runtime coverage concerns FastAPI; the already performed JVM dashboard checks do not need a repeat acceptance run. Project authorization, target retirement and collection-failure acceptance remain separate from dashboard functionality.

  **Source progress (October 15, 2026; `4c170d5`):** Added an opt-in `v1alpha2` metrics declaration, private discovery/proxy, scoped fixed reads, and generated Spring, Quarkus and FastAPI dashboards. Framework fixture readback remains unverified.

  **Live repair evidence (October 16, 2026):** ODIP revision 16 initially failed with Kubernetes HTTP 403 at `apply:ServiceAccount`. Provisioner RBAC was corrected to allow creation/reconciliation of telemetry ServiceAccounts and metrics Roles/RoleBindings (`9c8b072`, `295b4d8`). Retrying the saved revision under its original authorized actor succeeded as operation `8b25afe0-003f-4540-ab65-cd22ab0cfc0a`; the replacement web Pod reached 2/2 ready. The deployed API still generated the old proxy Role name, so the live ODIP Role was corrected to `http:web:http`. A cross-node scrape also required an ingress policy from the observed control-plane flannel host `10.42.2.0/32` to the declared metrics port 8080. After that narrow live policy, Prometheus reported the ODIP target `up` with no scrape error (08:08:15 UTC), and Tempo search found retained `odip.web` traces. Source now derives the trusted host from the control-plane PodCIDR during bootstrap and generates the port-specific policy.

  **Deployed repair verification (October 16, 2026; `b81b9fc`):** The operator approved the full platform deployment and shared-service restart. Ansible completed 37 tasks with zero failures; API, Tempo and Grafana readiness returned HTTP 200, and Alloy and the telemetry gateway were healthy. The restarted API received `PLATFORM_METRICS_PROXY_CIDRS=10.42.2.0/32` and contained the named-port proxy and network-policy fixes. Reapplying saved ODIP revision 16 under its original authorized actor succeeded as operation `d27100f5-59e9-4369-9b03-6ceb3dff449f`; the web rollout completed. Reconciliation retained Role resource name `http:web:http` and the single-source, port-8080 metrics ingress policy. Prometheus reported both ODIP and vareng targets `up` with no scrape errors, and Tempo returned retained `odip.web` traces after restart. The repair's 37 focused local tests passed. These observations do not establish complete dashboard or neutral-fixture acceptance.

  **Planning baseline (October 15, 2026):** Current application discovery feeds only blackbox availability probes; Prometheus does not scrape application `/metrics` endpoints. No framework dashboard templates or application metric reads are implemented.

  **Dashboard consolidation and JVM readback (October 16, 2026):** Replaced the three equivalent framework dashboards with **Application metrics** and added **Micrometer JVM** with 19 panels. The reviewed scrape allowlist now retains bounded JVM/process metrics and runtime dimensions; existing sample, body and label limits remain in force. A disposable Prometheus fixture passed both supported HTTP conventions, Micrometer precedence, every JVM panel query, project scoping and label filtering. The existing monitoring fixture and dashboard freshness checks passed. Node-01 received a validated Prometheus configuration reload and Grafana provisioning reload without shared-service restarts. Both ODIP and vareng remained scrape-up, retaining 91 and 75 samples respectively, with live JVM memory, CPU, thread, class, buffer and file-descriptor readback. Rate panels need multiple scrapes; HTTP mean duration needs requests. Legacy framework dashboards were removed. Kubernetes pod/deployment legends now use namespace and workload names: live queries returned both projects separately even though their metrics share one kube-state-metrics exporter address. Per-container CPU/memory collection remains outside this change; full neutral-framework and failure-drill acceptance remains open.

  **Workload capacity extension (October 16, 2026; `cc3ed69`):** Added pod and deployment CPU usage, memory working set, configured requests and configured limits to **Workloads and capacity**, with project-namespace selection and node scrape health. Private TLS-verified kubelet discovery/scraping uses a separate service account with node list/watch and `nodes/metrics` get. Live permission checks allowed collection and denied node proxy, secrets and pod exec. All three node targets were up; recording-rule evaluation failures were zero. Both ODIP and vareng returned all three CPU and memory comparisons at pod and deployment level after the second scrape. ODIP web requests included its sidecar (0.275 cores / 320 MiB); vareng web requests were 0.125 cores / 192 MiB. Deployment ownership joins distinguish namespaces and combine rolling ReplicaSets. The disposable monitoring fixture and 21 resource-rule assertions passed, including native-sidecar accounting, ordinary init exclusion, completed-job exclusion, project separation and omission of incomplete limits. Only Prometheus was recreated for new read-only mounts. These steady-state totals exclude startup init peaks and pod overhead and do not replace scheduler admission accounting.

- [x] **PLAN-024 · 4.4 (owner-accepted exception; follow-up in 7.9)** — Add opt-in OpenTelemetry tracing for hosted service and scheduled components. Carry safe W3C context through the authenticated platform boundary, accept OTLP only from verified workload identities, derive provenance server-side, bound and redact spans, and provide fixed project-scoped readback while keeping raw trace search operator-only. Prove Spring Boot, Quarkus and FastAPI flows, internal propagation, forged-origin/cross-project denial, sampling gaps, retirement and collector-failure isolation. Prerequisites: PLAN-021 private trace collector and PLAN-022 operator trace links; PLAN-023 application selectors may be reused. See the [Phase 4 plan](plans/phase-4-tracing-and-dashboards.md#44-let-hosted-applications-participate-in-tracing-plan-024) and [N-11](../../product/requirements.md).

  **Owner-directed completion (October 16, 2026; baseline `4681e56`):** Complete for the Phase 4 delivery gate under the owner's explicit instruction. All remaining acceptance and any fixes it reveals are deferred to [Phase 7 package 7.9](plans/phase-7-anytime-leftovers.md#79-complete-deferred-phase-4-acceptance), at the lowest priority with no Phase 5 dependency. The package names the unverified outcomes; earlier open-evidence notes below remain historical and do not override this disposition. Only checks explicitly recorded as passed are passing evidence.

  **Source progress (October 15, 2026; `5709217`):** Added versioned trace opt-in, Pod-bound token projection, authenticated OTLP gateway with catalog checks, bounded span redaction and fixed project-scoped reads. End-to-end framework fixtures and live denial checks remain open.

  **Forwarder check (October 15, 2026; `02761b0`):** Added a Pod-local OTLP forwarder that rereads the projected token per batch, with token inaccessible to the app container and sidecar resource requests included in quota/admission. The image built locally, the Alloy configuration validated in its pinned image, and targeted manifest/forwarder/capacity tests passed. The local Compose API, Alloy and Keycloak containers are restarting, `.env` lacks new required values, and the dedicated Tempo mount is absent; no live acceptance is inferred from these source checks.

  **Scheduled-job lifecycle repair (October 16, 2026; `8edc917`):** A regular tracing sidecar kept ODIP's scheduled Pods running after the main worker exited, causing readiness alerts and eventual deadline failures. One inspected worker had also exited with an identity-provider network error; identity discovery subsequently returned HTTP 200 from the same Pod network, and a later worker exited 0. Scheduled forwarders now use native restartable init sidecars, with their requests included in observed capacity accounting. The platform unit suite ran 386 tests successfully (16 skipped), and all four GitHub workflows passed for the fix. The live ODIP CronJob template was corrected, and the two changed API source modules were installed with a targeted API rebuild/recreation. Rendering the saved application through the restarted API produced the native sidecar. Jobs `ingestion-worker-29869212`, `ingestion-worker-29869213`, and `ingestion-worker-29869214` then completed successfully in 39–41 seconds; Prometheus reported no pending or firing readiness alert for the worker. Public platform/identity endpoints returned HTTP 200, the external watchdog showed UP, and recent heartbeat deliveries succeeded; these checks do not establish the cause of the earlier reported watchdog outage.

  **Planning baseline (October 15, 2026):** No hosted application trace declaration, OTLP ingestion path, platform-to-application trace propagation, verified application-span provenance or scoped trace read exists. Existing workload-log `correlationId` values are not verified trace IDs.

  **Design decision (October 15, 2026):** [ADR-021](../../architecture/decisions/ADR-021-phase-4-tracing-boundary.md) fixes the additive `v1alpha2` opt-in field, private gateway address and Pod-bound telemetry token/`TokenReview` path, server-derived provenance, fixed 24-hour project read, and fail-closed ingestion behavior. Implementation and deployed proof remain open.


## Shared implementation baseline

B-2026-09-26 describes an administrator-operated hybrid foundation, not an accepted Phase 1 release. [Compose](../../../compose.yaml), [cluster configuration](../../../scripts/cluster_config.py) and [bootstrap](../../../scripts/up.sh) place shared services outside a one-server/two-agent k3d cluster; PostgreSQL has a persistent volume. All local components share the same host failure domain. Current target-host installation, capacity, TLS, failure recovery and actual notification receipt are unverified. Watchdog SMTP, deployment automation and schema import were additions since the preceding assessment; the platform API/workload implementation was unchanged at that baseline.

Source inspection covers requirements, use cases, architecture, ADRs, guides, scripts, infrastructure and tests. It does not verify current external releases or dependency currency. Resolved historical documentation corrections and their former recommended ordering are not open delivery tasks; the active phase plan controls sequencing. ADR acceptance remains in the ADR index, not inferred from source presence.

## Verification register

These are **imported results**, executed during the September 26 assessment at the source revision above in a local checkout/fixture environment. No target-host deployment, live mutation, failure injection, or restore was performed. No remote CI run was verified. Record subsequent runs as new evidence with their own date, revision and environment; preserve these result limits.

| Evidence ID / tasks | Check | Result | What it establishes |
|---|---|---|---|
| EV-01 · PLAN-001/002, DEV-008-T01, OPS-005-T01/02 | `python3 -m unittest discover -s tests -v` | Passed: 3 tests. | Name validation, generated namespace/network structure, and selected workload hardening/quota settings. |
| EV-02 · PLAN-001, DEV-003-T01 | `python3 -m compileall -q platform scripts operations/watchdog/scripts` | Passed. | Python syntax compilation; not dependency import or service execution. |
| EV-03 · PLAN-001, OPS-006-T02 | `bash -n scripts/up.sh scripts/down.sh` | Passed. | Shell syntax. |
| EV-04 · PLAN-001, DEV-005-T01, OPS-003-T01 | `docker compose config --quiet` | Passed. | Compose configuration resolves using the assessed checkout's configuration; no services started. |
| EV-05 · Documentation maintenance | Local Markdown link scan after guidance update | Passed: no broken relative file targets across 38 root/component/current-docs/watchdog Markdown files; the nine earlier broken occurrences are fixed. | Relative file-target existence, excluding fenced code, external URLs, and fragment validation. |
| EV-06 · OPS-006-T02, PLAN-001 | Current operations code examples | Passed: `bash -n` for 22 shell blocks; embedded catalog-reapply Python parsed successfully. | Syntax only. No startup, shutdown, SQL backup/import, catalog replay, or alert exercise was executed. |
| EV-07 · OPS-007-T01 | `php operations/watchdog/tests/watchdog.php` | Passed. | Heartbeat and scheduler freshness boundary checks. |
| EV-08 · OPS-007-T01 | `php -d curl.cainfo=<unused temporary certificate path> -d sendmail_path=/bin/true operations/watchdog/tests/watchdog-mail.php` | Passed: seven SMTP scenarios plus validation/legacy transport checks. | Local fixture verifies STARTTLS/implicit TLS, authentication/recipient/data failures, missing TLS, certificate mismatch, invalid settings, and simulated PHP mail handoff. No real email is sent. Expected failure cases emit diagnostic logs. |
| EV-09 · OPS-007-T01 | `php -l` on tracked watchdog PHP source and tests | Passed: 10 files. | PHP syntax; excludes private local configuration and does not establish database integration. |
| EV-10 · OPS-007-T01 | `ansible-playbook -i operations/<name>/ansible/inventory.<name>.example.yml operations/<name>/ansible/deploy-<name>.yml --syntax-check` for `watchdog` and `heartbeat` | Both passed. | Playbook syntax only; no remote connection, installation, or delivery verification. |
| EV-11 · PLAN-001 | Local working tree based on `2a6d2f0`: `python -m unittest discover -s tests -v`; `python -m unittest discover -s operations/backup/tests -v`; `python -m compileall -q platform scripts operations tests`; `bash -n scripts/up.sh scripts/down.sh`; `git diff --check` | Passed: 41 platform tests; 35 backup tests with one optional real-Restic test skipped; Python compilation, shell syntax, and diff checks passed. The API regression test confirms unknown fields return 422 before catalog/provider side effects. | Local tests exercise API/worker logic with doubles; compilation and syntax checks do not establish live PostgreSQL migration, Kubernetes execution, process-interruption recovery, or operational acceptance. |
| EV-12 · PLAN-001, DEV-006-T01 | Local working tree based on `2a6d2f0`: platform/backup unittest discovery; Python compileall; shell syntax; `git diff --check` | Passed: 48 platform tests; 35 backup tests with one optional real-Restic test skipped; compilation, shell syntax and diff checks passed. Readiness fixtures cover ready counts/images, image pull, unschedulable pods, progress deadline, missing Deployment, observer failure, and stale rollout mismatch; API test confirms authorized status adds the snapshot and revoked access does not query Kubernetes. | Readiness classification and API wiring are locally verified with fixtures/doubles only. No live Kubernetes observer, rollout failure drill, PostgreSQL migration/API, or end-to-end acceptance was run. |
| EV-13 · PLAN-001, DEV-006-T01 | Live node-01 lab, commit `81ef62e` deployed with `ansible/deploy.yml` (no pre-deploy backup; lab holds no data of value, user decision, October 3, 2026), then RBAC fix `813deeb`; `scripts/smoke.py` run on the node with a short-lived OIDC token; worker-interruption drill: `docker pause` of `k3d-workloads-server-0`, PUT, API restart while the operation was `running`, `docker unpause`. | Passed: migration backfilled `smoke` with revision 1 and an empty operations table; PUT returned 202 and a repeated PUT reused the operation; operation reached `succeeded` with live readiness `ready` (1/1, image and image ID reported) and ingress routed. Initial run returned readiness `unknown` because the provisioner role could not read pods (`ForbiddenError`); granting pod `get/list` fixed it. Interruption drill: operation observed `running` with `attempt_count=1`, reclaimed after the API restart, ended `succeeded` with `attempt_count=2`; no queued/running operations remained; one Deployment, pod and ingress. | One project, one pod, one worker process, spec unchanged in the drill (idempotent re-apply), so no data-retention or changed-spec rollout was exercised. Bad-image, unschedulable and stalled-rollout readiness drills, authorized restart, expected-revision conflicts and installation parameter records are not done. PLAN-001 stays open. |
| EV-14 · PLAN-001, DEV-006-T01 | Live node-01 lab, October 3, 2026, API at `81ef62e` with RBAC fix `813deeb`: throwaway project `badimage` deployed with image tag `hashicorp/http-echo:no-such-tag`, then corrected to `hashicorp/http-echo:1.0.0`; operation status polled every 5 s. | Passed: bad image operation `succeeded` (apply outcome) while readiness stayed `progressing` with reasons `ErrImagePull`/`ImagePullBackOff`, 0 ready replicas, never `ready` (about 60 s observed). Corrected spec created a new operation; first poll reported `DeploymentImageMismatch`, then `ready` with 1/1 replicas and the 1.0.0 image; one running pod. First changed-spec rollout observed live. | Bad-image case is `progressing`, not `failed`: the manifest sets no `progressDeadlineSeconds` (Kubernetes default 600 s), so `failed` and the `smoke.py` 300 s timeout are not reconciled and `smoke.py` does not print the readiness reason on timeout. Unschedulable and stalled-rollout drills, authorized restart with data retention and installation parameter records remain open. `badimage` is still deployed on the lab. |
| EV-15 · PLAN-001, DEV-006-T01 | Live node-01 lab, October 3, 2026, API at `52e286f` (`progressDeadlineSeconds: 120`, stalled-rollout readiness fix) redeployed with `ansible/deploy.yml`; `badimage` project: nonexistent tag PUT and polled every 10 s; then all three k3d nodes cordoned and the project's pods deleted while polling the same operation. Before the fix (`1f7b5e4`) the same drill reported `ready` for about 2 minutes. | Passed: after the fix the bad-tag rollout stayed `progressing` (`ErrImagePull`/`ImagePullBackOff`) and never `ready`, then `failed` with `ProgressDeadlineExceeded` at about 2 minutes. With nodes cordoned the replacement pods reported `progressing` with `Unschedulable` and 0 ready replicas; nodes were uncordoned afterwards. Local regression test covers an old ready pod plus a stalled new pod. | The unschedulable drill ran against the failed bad-tag deployment, not a healthy one, and used cordon plus pod deletion rather than an oversized request (the public spec has no resource fields). A stalled rollout that is not an image pull problem and an authorized application restart with data retention are not exercised. Installation parameter records remain open. PLAN-001 stays open. `badimage` is still deployed on the lab. |
| EV-16 · PLAN-001, DEV-006-T01 | Live node-01 lab, October 3, 2026, API at `b65252b`: authenticated `POST /projects/smoke/restart` returned an operation; the `smoke` pod `smoke-587bf9d6bb-nwm62` was replaced by `smoke-7dd9ccdffd-8rfdl`, the operation reached `succeeded` and readiness stayed/returned `ready` with 1 replica, and `scripts/smoke.py` passed afterwards. Not observed: a `progressing` snapshot during the roll (polling began while queued and the roll completed within one poll), a repeat-POST reuse and an unchanged-spec PUT after restart; covered by unit tests only. | Restart operation works end to end; PLAN-001 stays open for the installation record and API/CLI demo. |
| EV-17 · PLAN-001, DEV-006-T01 | Live node-01 lab, October 3, 2026, `ansible/deploy.yml` at `a088fa0` wrote `/opt/developer-platform/.runtime/installation-record.json` with source revision `a088fa0` (clean), Ubuntu 24.04 x86_64, Docker 29.8.1, Compose 5.5.1, k3d v5.9.0, kubectl v1.36.4 and the non-secret domain/bind/kubectl parameters. A redeploy at `5679408` (clean revision) wrote a record including 13 running Compose images as `repository:tag@sha256` (e.g. `postgres:18.6-trixie`, `caddy:2.11.4-alpine`, `keycloak:26.4.1`); the earlier record had no images because `docker compose images --format` accepts only `table`/`json` and the failure was masked, and the first redeploy failed on `pipefail` under dash before the fixes. The locally built `platform-api` image is recorded as `:latest` with its image ID only. | Installation versions/parameters and image IDs recorded. |
| EV-18 · PLAN-001, DEV-006-T01 | Live node-01 lab, October 3, 2026, API at `5679408`: two consecutive `POST /projects/smoke/restart` calls returned the same operation `197e0930-1fee-4836-bfbb-1c0f098d9489`; the pod was replaced (`smoke-7dd9ccdffd-8rfdl` to `smoke-67b97fd4d8-sphzv`) and readiness stayed `ready` with 1 replica at every 2 s poll (first poll `queued`). A following PUT of the unchanged spec returned a new operation at the same revision 2, and the pod name/age were unchanged 20 s later, so the retained restart marker caused no second rollout. Not observed: a `progressing` snapshot during the restart roll (the new pod became ready within one poll interval); covered only by unit tests and the bad-image drills in EV-14/EV-15. | Restart idempotence and no spurious rollout confirmed live. |
| EV-19 · PLAN-002 | Live node-01 lab, October 3, 2026, API at `42d5a78`, smoke script at `1f97df8`: `smoke.py`, then Deployment image query and a PUT with `hashicorp/http-echo:no-such-tag`. | Passed: `smoke.py` reached readiness `ready` and edge routing over local HTTPS; the Deployment image is `hashicorp/http-echo@sha256:fcb75f69…a186` (resolved from `1.0.0`); the nonexistent tag was rejected with HTTP 422 at PUT time. | Registry resolution from the API container works against Docker Hub. Not yet exercised live: unsupported registry (422), registry outage (503), moved-tag revision. The smoke script's edge check and operation-identity assertion were corrected during this run (`5e30efb`, `1f97df8`). |
| EV-20 · PLAN-002 | Live node-01 lab, October 3, 2026, API at `062445e`: PUT `smoke` with `resources.limits` of 1 CPU and 512Mi (revision 4), then Deployment, pod and operation status. | Passed: PUT accepted (202, revision 4); Deployment container shows limits `1`/`512Mi` with requests unchanged at `100m`/`128Mi`; one new pod `1/1 Running`; operation `succeeded`, readiness `ready`. | Not yet exercised live: the idempotent re-PUT with the equivalent spelling (`1000m`), and 422 for invalid resources (unit-tested only). |
| EV-21 · PLAN-002 | Live node-01 lab, October 3, 2026, API at `0470109` (rebuilt with `docker compose up -d --build platform-api` from the repo root): PUT of a versioned `Application` envelope for `smoke`, a second envelope with `maxInstances: 3`, pod listing and `/openapi.json`. | Passed: the envelope was accepted as revision 4, the same revision as the equivalent flat PUT, with no new rollout (pod unchanged, age 10 min); autoscaling envelope rejected with 422; `/openapi.json` lists `Application` and `ApplicationEnvelope`. | Compose commands for a single service must run from the repo root, not `platform/compose.yaml`. Not yet exercised live: the other rejected capabilities (unit-tested). Public `namespace` removal and capability profiles remain open. |
| EV-22 · PLAN-002 | Live node-01 lab, October 3, 2026, API at `b166034`: `GET /v1/capabilities` and an envelope PUT with `scaling.maxInstances: 3`. | Passed: capabilities returned the `default` profile (container, one public http endpoint, fixed 1/1 scaling, resource ranges); the autoscaling PUT returned 422 with `code` `unsupported_capability`. | Profile is static in code. Flat-body sunset decision remains. |
| EV-23 · PLAN-003 | Live node-01 lab, October 3, 2026, API at `1da5a5e`: PUT of `smoke` with `If-Match: 1`, then `If-Match: 4`, current revision 4. | Passed: the stale value returned 409 `revision_conflict` with `current_revision: 4`; the matching value returned 202 on revision 4 (unchanged spec, no new revision). | A stale PUT that would have changed the spec, and two truly concurrent PUTs, are unit-tested only. |
| EV-24 · PLAN-003 | Live node-01 lab, October 3, 2026, API at `4f4e236`: `GET /projects/smoke/drift` before, after `kubectl scale --replicas=2`, and after scaling back to 1. | Passed: `in_sync` at revision 4; `drifted` with `replicas` desired 1, observed 2; `in_sync` again. The platform did not revert the manual scale. | Image and resource drift are unit-tested only. No periodic scan yet. |
| EV-25 · PLAN-003 | Live node-01 lab, October 3, 2026, API at `78f0e93` with `DRIFT_SCAN_INTERVAL_SECONDS=20`: `smoke` scaled to 2 replicas and back to 1 twice (about 45 s each); platform-admin audit export for the window. | Passed: each manual scale produced one `project.drift.detected` (`fields: [replicas]`, revision 4) at 14:50:29 and 14:57:10 UTC and one `project.drift.resolved` at 14:51:30 and 14:57:30, actor `system`/`drift-scan`; no repeated events while drift persisted; the cluster was not changed by the platform. | Image and resource drift in the scan, and the 300 s default interval, are not exercised live. State resets on API restart. Revision retention and redacted provider-failure traces remain open. |
| EV-26 · PLAN-003, DEV-007-T02 | Live node-01 lab, October 3, 2026, API at `1583f51` with `REVISION_RETENTION=3`: four PUTs changing the CPU limit (revisions 5 to 8), rollback to revision 6 with `If-Match: 8`, rollback to a pruned revision, a stale `If-Match`, then restore (revision 10 at 1 CPU, retention back to 25). | Passed: pruning ran (rollback to revision 5 returned 404 `Unknown project or revision`); the rollback returned 202 as revision 9, the Deployment went from `400m` to `300m`, rolled out successfully and the app answered HTTP 200; stale `If-Match: 3` returned 409 `revision_conflict` with `current_revision: 9`; `/revisions` listed 9, 8, 7 and 2. | Revision 2 (`resources: null`, created before resource defaults) stayed beyond the window; the expected cause is the kept last-successful-restart operation pinning it, but its operations were not queried. Provider-failure trace is unit-tested only. Rollback to a pre-resources revision was not exercised. |
| EV-27 · DEV-010-T01 | Live node-01 lab, October 3, 2026: `scripts/isolation.py` (updated for asynchronous deployments, `4335df6`) deployed project `isolation`, then ran a check pod in `project-smoke` with the smoke project's database Secret. | Passed: own PostgreSQL reachable; denied access to `project_isolation` and `platform` databases; DNS allowed; TCP to another project's service and to the internet blocked. | Application write/read and data preservation across redeploy not yet exercised. |
| EV-28 · DEV-010-T01 | Live node-01 lab, October 3, 2026: `scripts/data_preservation.py` (`90a95da`) wrote a marker row to the smoke project's managed database, deployed a new revision (changed CPU limit), read the row, ran a rolling restart, and read it again. | Passed: the marker was read back after the redeploy and after the restart; both operations reached ready. | Covers redeploy and restart only, not retire/recreate. The check pods use the project's database Secret rather than an application workload. |
| EV-29 · DEV-007-T01 | Live node-01 lab, October 3, 2026: `scripts/interrupted_provisioning.py` (`5f15bcf`) paused the k3d API, PUT a new project so the worker stalled after creating its database, killed the API with the operation `running`, wrote a marker row, restarted the API, and repeated the same PUT. | Passed: the repeat reused revision 1; every operation on it succeeded; exactly one database and one role existed; the marker row survived; a pod using the project's generated Secret read the marker. | The interruption is deterministic only because the cluster API is paused; earlier attempts without it (kill after database creation) always landed after completion. A repeat PUT after reclaim gets its own operation (sharing is only while active); apply is idempotent. |
| EV-30 · DEV-011-T01 | Live node-01 lab, October 3, 2026: `scripts/retirement_drill.py crashdrill51427` (`908752b`, API fix `bf6774f`) against a project created by the interrupted-provisioning drill, with the provisioner namespace-delete RBAC and `provisioner-namespace-delete` admission policy applied. | Passed: a server-side dry-run delete of `platform-system` with the controller credentials was denied by the admission policy; the preview listed removed objects and retained data; a stale `scope_token` returned 409 `scope_changed` and left the namespace untouched; the confirmed retire answered 202 `retiring` while the namespace terminated, then 200 `retired`; the database, role and `project_retirements` inventory (revision 1) remained. An earlier run exposed that repeating the delete after completion returned 503 (404 treated as an error), fixed in `bf6774f`. | Retirement preview, confirmation, namespace removal and retained inventory verified live. |
| EV-31 · DEV-005-T01 | Live node-01 lab, October 3, 2026: `GET /projects/smoke/resource-usage` (`f67d03a`) with the provisioner granted `metrics.k8s.io` pod read, compared with `kubectl top pods -n project-smoke`. | Passed: `state: ok`, one pod, memory 3,227,648 bytes and CPU 0.18 millicores, matching `kubectl top` (3Mi, 1m rounded up). | Metrics-server is available on the lab k3s. CPU is now rounded to 3 decimals. |
| EV-32 · OPS-003-T01 | Live node-01 lab, October 3, 2026, idle (up 6 days, load average 1.14/1.54/0.89): `free`, `df`, `docker stats --no-stream`, `kubectl top nodes/pods -A`, `docker system df` and per-database sizes. | Host: 16 CPUs, 31,337 MiB RAM (3,217 used, 28,119 available, no swap), `/` 301 GB with 12 GB used (5%). Shared Compose services (11 containers): about 1,045 MiB in total, mostly Keycloak 444, Grafana 230, platform-api 97, Loki 75; combined CPU under 8% of one core. k3d cluster containers: about 1,164 MiB (server 613, agents 291 and 244); node CPU 54-116m each. Kubernetes system pods: about 91 MiB; the nine project pods: 2-4 MiB and 1m CPU each. Storage: Docker images 5.8 GB, volumes 3.0 GB (48), build cache 0.5 GB (reclaimable); the largest database is Keycloak at 13 MB, every project database about 7.6-7.8 MB. | Baseline is idle: the workloads are tiny test containers, so it shows overhead, not capacity. Host memory used exceeds the sum of containers by about 1 GiB (operating system and other processes). **System reserve (confirmed by the owner, October 3, 2026):** keep at least 8 GiB RAM, 2 CPUs and 50 GB disk unallocated to projects. The owner declined a load run, so only the idle baseline exists and no workload capacity figure is claimed. |
| EV-33 · DEV-004-T01 | Live node-01 lab, October 3, 2026: `scripts/log_drill.py` (`5f88ef4`) against the `smoke` project, with provisioner `pods/log` read applied. | Passed on the second run: unauthenticated read denied, unknown project 404, `tail=0` 422; `smoke` returned 20 attributed, time-ordered lines; a failed pod labelled as part of `smoke` was diagnosed from two separate lines (`failure-marker password=[REDACTED] <marker>` and `second-line <marker>`) and deleted afterwards. | The first run passed but showed a literal `\n'` at the end of the failure line: the client mangled the body. Fixed by reading raw bytes (`5f88ef4`) and the drill now asserts separate, clean lines. |
| EV-34 · DEV-002-T01 | Live node-01 lab, October 3, 2026: `scripts/config_drill.py smoke` (`f9d5583`). | Passed: unauthenticated read denied; reserved (`PGHOST`), secret-like (`DB_PASSWORD`) and oversized values rejected with 422 `invalid_configuration`; a stale `If-Match` gave 409; add (revision 12), update/remove (13) and clear (14) each reached `active` after the pods rolled, and drift was `in_sync` at the end. | Activation showed `pending` before `active`, as expected during a rollout. Cross-project denial rests on the shared `view`/`change` check and is unit-tested only. |
| EV-35 · DEV-003-T01 | Live node-01 lab, October 3, 2026: `scripts/secret_drill.py smoke` (`bb66535`). | Passed: unauthenticated read denied; reserved name rejected; created secret was stored only in the project `app-secrets` Secret, the pods restarted and became `active`; rotation restarted the pods again; the listing showed the name and change time only; delete worked and a second delete gave 404; neither value appeared in any API response (secrets, revisions, configuration, drift) or in the `platform-api` logs. | The image has no `printenv`, so the pod environment was not inspected directly. The audit table was not queried live (unit test only). Foreign-project denial is unit-tested only. Versioned rotation with reconnection checks and backup coverage (DEV-003-T02) are not done. |
| EV-36 · DEV-003-T02 | Live node-01 lab, October 3, 2026: `platform-backup.service` with the secrets export (`59239ec`), after setting a probe secret `BACKUP_PROBE` in `smoke`. | Passed: the new verified snapshot `1e9ea25e` (19:34) contains `bundle/project-secrets.json`; it lists `{smoke: [BACKUP_PROBE]}` and the decoded value matched the value set; the probe was then deleted. | Not shown: fail-closed behaviour with the cluster unreachable (unit-tested only) and restoring secrets into a rebuilt cluster (unit-tested only; isolated recovery drills deferred under ADR-010/016). |
| EV-37 · DEV-003-T02 | Live node-01 lab, October 3, 2026: `scripts/secret_drill.py smoke` (`6d631da`). | Passed: rotation held the previous value (version 1) in the unmounted `app-secrets-previous` Secret and the listing showed version 2 `rotating`; revert restored it as version 3; a new rotation followed by `confirm` after adoption revoked the previous value and a second confirm returned 409; no value in responses or logs. | Not shown: `not_adopted` refusal and cross-project denial (unit-tested only). The platform cannot observe a client reconnection; the signal is pod adoption plus the explicit confirm. The previous Secret is not in the backup bundle. |
| EV-39 · DEV-004-T02, DEV-005-T02, DEV-008-T01, DEV-009-T01, OPS-005-T01/T02 | Live node-01 lab, October 5, 2026: `ansible/test-platform-components.yml` passed 76 tasks for disposable project `components-1791215912`; a subsequent administrator query confirmed its namespace was absent. | Passed: two ready long-running services, scheduled success and safe failure/non-overlap, stable internal names, component log filtering and cursor polling, topology/resource/quota inventory, two API replicas, explained quota and default-deny egress rejection, public-to-private Ingress removal, isolated service/scheduled updates, retained configuration/write-only secret metadata, rollback and cleanup. | This evidence closes the portions attributed above only when combined with their task-specific unit/live evidence. It does not prove direct Loki access denial, externally observed public TLS, approved external egress, per-project quota-policy mutation, physical-host reserve calibration, or alert delivery. |
| EV-40 · OPS-008-T01/T02 | Live node-01 lab, October 5, 2026: `ansible/retire-platform-project.yml` passed 17 tasks for generated project `retire-drill-1791218627-13425` with credential-revocation verification enabled. | Passed: created and readied a public workload, required its Deployment and Ingress in the bound retirement scope, retired the namespace, immediately denied the project credential, observed provider cleanup reach `revoked`, and retained data according to the current policy. | Backup inventory, an explicit project-specific destructive-data decision, provider-deletion failure injection/retry, unaffected-neighbour proof and audit inspection remain open, so OPS-008-T01/T02 are not closed. |
| EV-41 · DEV-010-T02, OPS-007-T02 | Live node-01 lab, October 5, 2026: guarded `ansible/test-platform-postgres-outage.yml` passed 26 tasks for `pg-drill-1791220461-48144`. | Passed: created a disposable project/persona/workload and recovery request, stopped PostgreSQL, observed a safe API outage response plus failed readiness, restored PostgreSQL, observed API/database recovery, resolved the request and verified the redacted developer-visible result, then retired the project and revoked the persona. | Establishes the database boundary and recovery workflow. It does not by itself complete all control-plane, ingress, application, monitoring, external-detection or notification criteria in OPS-007-T02. |
| EV-42 · DEV-007-T02 | Live node-01 lab, October 5, 2026: `ansible/test-platform-rollback-data.yml` passed 29 tasks for `rollback-1791225853-1852`. | Passed: deployed two revisions, inserted a unique SQL marker, created and rotated a write-only secret, rolled back to revision one, verified the database marker survived and active secret version 2 remained without value disclosure, verified dependency semantics, and retired the project. | Application rollback deliberately retains the current database and secret state; it is not a database migration rollback. |
| EV-43 · DEV-008-T01, OPS-005-T02 | Live node-01 lab, October 5, 2026: `ansible/test-platform-capacity-admission.yml` passed 31 tasks for `capacity-1791232590-427` against the API containing the `fe49dcd` admission/RBAC/quantity fix and the controller-side quoted-stdin correction. | Passed: enabled admission temporarily, read a valid Node/Pod request snapshot, created a 43,600m CPU/4,969Mi synthetic reservation, rejected a 100m/128Mi rollout before side effects, removed the reservation, observed capacity recovery, admitted and readied the same workload, restored the exact original environment/API policy, and retired the project. | This is mechanism evidence, not a physical load test. The zero-reserve drill and overlapping allocatable values reported by three k3d nodes on one host do not validate permanent reserve sizing or a 43.6-core host-capacity claim; OPS-005-T02 remains open for calibrated policy acceptance. |
| EV-44 · DEV-009-T01, OPS-005-T01/T02, OPS-007-T02 | Live node-01 lab, October 5, 2026: `ansible/test-platform-egress-policy.yml` passed for `egress-1791234145-367`; `ansible/test-platform-failure-signals.yml` passed for `failure-1791234467-33`; the owner confirmed notification receipt. | Passed: egress drill rejected an undeclared destination, connected to `1.1.1.1:853` only through its temporary `1.1.1.1/32` policy, and restored the exact original API environment. Failure-signal drill observed and resolved project-labelled application and ingress alerts, controlled Prometheus unavailability/recovery, restored proxy, Prometheus, and API policy, and retired the disposable project. | Completes protected lab acceptance. Egress and failure drills intentionally disable capacity admission only while running and restore it from the exact pre-drill environment. Notification receipt is owner-confirmed; this is lab acceptance, not a production availability guarantee. |
| EV-45 · PLAN-009, PLAN-018, PLAN-019 (partial) | Operator-provided live node-01 report, October 11, 2026: `scripts/check-hosted-access.py run --timed`, run `c927adee1d50`, UTC 16:34:39–16:47:23. Runner/fixture release `hosted-access-v0.1.2`, source `e8f74fdd522ab18bd06ffed06073525494a90345`; the report pins the runner hash/image digest, not the deployed control-plane revision. Private report: `/opt/developer-platform/.runtime/hosted-access/c927adee1d50/report.json`. | `core-passed`: all 39 named assertions passed; held-token expiry enabled; cleanup `completed-data-retained`; `gateClosed: false`. PostgreSQL write/read statuses `200`, marker comparisons passed, state retained after restart; human/machine revocation observed in 2.357/2.310 seconds. | Deployed core criterion-level evidence for human/service access, managed HTTPS binding, IPv4 network denial with positive controls, synthetic correlation, policy lifecycle, rotation, expiry and restart persistence. Nine checks remain deferred; no IPv6 isolation, backup restore, outage-bound, long-timer/retention/monitoring or external energy-suite acceptance is claimed. PLAN-009/018/019 and F-10 remain open. [Detailed evidence and limits](../../operators/validation/access-and-authorization.md#executed-hosted-access-core-acceptance-october-11-2026). |
| EV-46 · PLAN-017, PLAN-009/018/019 (partial) | Operator-provided live node-01 report, October 11, 2026: `scripts/check-hosted-access.py run --timed --monitoring`, run `60c3ca1647b9`, UTC 19:02:34–19:14:55. Runner/fixture release `hosted-access-v0.2.0`, source `b360ddee34444748c95705c597aa7b17491cd05b`; operator-confirmed redeployment of the subsequent Alloy permission/readiness fix. The report pins runner hash/image digest, not the exact deployed control-plane tree. Private report: `/opt/developer-platform/.runtime/hosted-access/60c3ca1647b9/report.json`. | `core-passed`: all 45 assertions passed, including six new provider/consumer public-boundary, semantic-readiness and central-correlation checks. `componentProbes`/`centralIngestion: passed`, `sevenDayRetention: not-time-verified`; cleanup `completed-data-retained`; `gateClosed: false`. Human/machine revocation observed in 2.338/2.240 seconds. | Deployed component monitoring and immediate safe-envelope ingestion/API retrieval plus repeated core criterion-level evidence. Nine deferrals remain; no elapsed retention, post-retirement/restart log readback, alert delivery, IPv6 isolation, recovery/outage or external energy-suite acceptance is claimed. PLAN-017 and the full gate remain open. [Detailed evidence and limits](../../operators/validation/access-and-authorization.md#executed-hosted-access-monitoring-acceptance-october-11-2026). |
| EV-47 · PLAN-008 (partial) | Live node-01 report and owner-confirmed portal/SQL checks, October 15, 2026: human database run `5f39d4862423`, UTC 17:43:50–17:44:13; private report `/opt/developer-platform/.runtime/human-database-access/5f39d4862423/report.json`. Fixture digest and deployment revisions are in the detailed record. | Owner-accepted passed core tests: `core-passed`, 14/14 automated checks; `cleanup: complete`; `projectsRetained: true` at run completion; `gateClosed: false`. Manual portal grant, credential display, SSH key rotation, read-only/foreign-project SQL, and revocation checks passed after two deployed UI fixes. A later clean deployment was ready, and both fixture projects were retired with SQL data retained. | Establishes the deployed core human database boundary and owner-observed portal journey. The owner accepts these performed checks without a repeat run on the clean deployment. Remote firewall, browser storage, and independent redaction review remain unverified in final work package 7.8; PLAN-008 and Phase 7 stay open. [Detailed evidence and limits](../../operators/validation/access-and-authorization.md#executed-human-postgresql-access-acceptance-october-15-2026). |

[CI](../../../.github/workflows/validate.yaml) defines syntax/configuration/unit checks, including PHP freshness and local SMTP transport tests, but no live smoke, isolation, or recovery acceptance. Its definition is not evidence that a particular remote run passed.

The [smoke script](../../../scripts/smoke.py) checks unauthenticated rejection, repeat provisioning, rollout, and HTTP routing. Its sample is `http-echo`; it does not write/read PostgreSQL through the application. The [isolation script](../../../scripts/isolation.py) checks database connectivity, denied foreign database access, DNS, and selected blocked network connections after a convergence delay. Neither script was run during the baseline assessment, and neither tests scoped end-user permissions, durable interrupted operations, or restore.

The [watchdog integration script](../../../operations/watchdog/scripts/test-watchdog.py) exercises temporary PHP/MariaDB services, but substitutes successful mail handoff and disables the optional HTTPS probe. It also checks schema import, repeated import preservation, and credential-safe authentication failures. It cannot establish real notification receipt. It was inspected, not executed; the separate PHP freshness and SMTP fixture tests above were executed.


## Requirement and use-case traceability

Requirement outcomes inherit task evidence; this table is a navigation map, not a second status register. No requirement is accepted solely because a configuration file or local fixture exists.

| Requirement / use case | Tasks supplying acceptance evidence |
|---|---|
| F-01 / UC-01 | PLAN-001, OPS-004-T01 |
| F-02 / UC-01 | PLAN-001, DEV-002-T01, DEV-006-T01 |
| F-03 / UC-01 | DEV-010-T01, DEV-003-T01/02 |
| F-04 | PLAN-001/003, DEV-006-T01, DEV-007-T01/02 |
| F-05 / UC-02 / UC-04 | PLAN-001, DEV-007-T02, DEV-011-T01, OPS-008-T01/02 |
| F-06 / UC-02 | DEV-004-T01/02, DEV-005-T01/02, DEV-006-T01, DEV-007-T02 |
| F-07 / UC-05 (optional Phase 6) | PLAN-002/004; additional data-store labs remain unscheduled |
| F-08 | PLAN-001/002, OPS-005-T01/02; PLAN-004 only if optional provider work is activated |
| F-09 / UC-03 | PLAN-008 |
| F-10 | PLAN-006/007/009/020 |
| F-11 / UC-06 | PLAN-010/011/012 |
| F-12 / UC-06 | PLAN-013/014 |
| F-13 / UC-07 | DEV-001-T01/02/03, DEV-006-T02, DEV-011-T02 |
| F-14 / UC-08; F-15 / UC-09 | DEV-012-T01/02/03 |
| N-01 | PLAN-001/002/004 |
| N-02 | DEV-007-T01/02, PLAN-003, DEV-011-T01, OPS-008-T02 |
| N-03 | OPS-004-T01, DEV-012-T02/03, and authorization checks on every later data surface |
| N-04 | DEV-003-T01/02, DEV-012-T01/02/03, and redaction checks on every later data surface |
| N-05 | OPS-006-T01/02; reassess the documented recovery procedure whenever persisted state grows |
| N-06 | OPS-007-T01/02 |
| N-07 | OPS-003-T01/02, OPS-005-T01/02 |
| N-08 | OPS-001-T01/02, DEV-012-T02/03, and audit checks on every later mutation/access change |
| N-09 | PLAN-021/022 |
| N-10 | PLAN-023 |
| N-11 | PLAN-024 |

The phase task index remains authoritative for scheduling, including deferred component-specific extensions. Requirement or story closure needs all applicable criteria, not just the foundation tasks listed here.
