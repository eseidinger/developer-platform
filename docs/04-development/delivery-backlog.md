# Delivery Backlog and Acceptance Criteria

Status: open delivery requirements and authoritative task/evidence register. The [development plan](development-plan.md) assigns delivery gates. Story criteria were migrated from the former archive; implementation findings and verification records are consolidated below. No story or task is certified complete by these documentation migrations.

## Conventions and scope

- **Developer:** a user who deploys and manages applications within authorized projects.
- **Operator:** a user who administers the platform, its capacity, and its security.
- **Project:** the boundary for application resources, configuration, and access.
- **Application:** one or more cooperating components, such as a web service and a worker,
  each of which can have its own deployment.
- Story IDs are permanent references. `DEV` identifies developer stories and `OPS`
  identifies operator stories. New stories receive the next unused number in their
  category; reordering or removing stories must not renumber existing IDs.
- Acceptance criteria describe observable outcomes. They do not prescribe a portal,
  CLI, or API implementation.

The platform currently targets trusted workloads on a single host. These stories
do not imply high availability or isolation suitable for hostile tenants.

## Task tracking

Each task belongs to exactly one phase or sub-gate; story IDs remain the overall acceptance gates. `DEV/OPS-xxx-Tnn` tasks inherit the story owner role in the [plan](development-plan.md#backlog-delivery-commitments). `PLAN-nnn` tasks cover existing phase scope outside the original stories and take their owner from the phase work package. Assign named owners before work starts. IDs are permanent; moving a task changes its phase field, not its ID.

Top-level task checkboxes remain open where full acceptance is outstanding. Checked progress criteria below record narrower verified outcomes; they do not close the parent task or phase. Task evidence below distinguishes partial or absent source implementation, verified local checks, and operational acceptance. Close a task only after its listed outcome is verified and record date, revision, environment, results and limitations beside it. Link shared checks by evidence ID. Update implementation findings here when code changes; other documents link here rather than maintain a separate status assessment. Close a story only when every original acceptance criterion passes. A Phase 3 design decision does not close deferred implementation tasks.

Phase gates remain **1A → 1B → 1C → 2 → 3 → 4.1–4.5**. Dependencies below supplement these gates and identify ordering within a phase; they do not authorize skipping earlier gates. Deferred tasks have no scheduled phase and cannot block the single-image gates. Component attribution in initial diagnostics uses the single supported component; rerun those checks when the model expands.

**Gate status, October 2, 2026:** Phase 1A is complete. Its three scheduled tasks are checked complete; ADR-011, ADR-016, and ADR-017 record the accepted lab limitations. Phase 1B is complete under its recorded owner-directed alert-delivery exception. Phase 1C is the next open gate.

Phase 1A runs within the existing administrator-operated boundary; secrets and operational credentials remain protected. Phase 1B establishes individual authorization/audit before expanded self-service. From Phase 1B onward, every task introducing an endpoint, data surface or persisted state must include scoped authorization/revocation, secret redaction and audit checks and update backup coverage. Reassess the documented recovery procedure when recovery scope changes; [ADR-016](../03-decisions/ADR-016-phase-1a-recovery-scope.md) excludes isolated recovery exercises from the current Phase 1A gate. These are part of that task's completion, not an unbounded extra phase. Release OPS-004-T01 with OPS-001-T01; later endpoints reuse the same boundary.

## Accepted lab validation approach

**Owner decisions, October 1, 2026:** [ADR-016](../03-decisions/ADR-016-phase-1a-recovery-scope.md) omits new fresh-installation restore drills, backup/key failure exercises, and recurring full-restoration scheduling from Phase 1A. Previous isolated recovery results remain historical evidence. OPS-006-T03 is deferred and does not block the 1A gate. [ADR-017](../03-decisions/ADR-017-phase-1a-retention-evidence-scope.md) omits elapsed-time proof of the full 14/8/6 retention horizon; it does not change the configured policy or claim that its complete retention history has been demonstrated. The next failed-backup notification exercise should use the existing installation with a bounded fault and recovery steps, preserving real backup data and verified-success history.

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
| [API](../../platform/app/main.py) accepts `name/image/port/probe_profile`, ignores extras and returns synchronous 200; ApplicationSpec described a richer asynchronous contract | Added explicit current/target comparison, current provisioning diagram and ADR-012 | PLAN-001/002/003: versioned contract, reject unknown/unsupported input, durable revisions/jobs and concurrency |
| Same API uses one all-project token, PostgreSQL administrator and cluster-wide [controller RBAC](../../infrastructure/kubernetes/controller.yaml); scoped role descriptions were target-only | Security page now states actual credential/authorization boundaries | OPS-001/004 and ADR-004: individual access/audit; no tenant permission claim |
| [Database provisioning](../../platform/app/main.py) derives HMAC passwords but never changes existing SQL passwords; runtime login owns its database | ADR-013 records key recovery and coordinated rotation; future role separation remains proposed | DEV-003/010, PLAN-008 and ADR-003: rotation/adoption and separate identities |
| [Monitoring loop](../../platform/app/monitoring.py) rebuilds files only; PUT/retirement share its global lock | Software/observability pages distinguish monitoring reconciliation from workload recovery | DEV-006/007 and PLAN-003: observed health and resumable provisioning |
| [Probe/retirement paths](../../platform/app/main.py) now exist beyond the imported baseline; retirement acknowledges manual removal and retains SQL/spec | ADR-014 records durable catalog membership and disposable discovery; historical “deletion absent” evidence remains dated | DEV-011/OPS-008 remain open for actual deletion planning, audit and cleanup; OPS-007-T01 for live probes |
| [Prometheus](../../infrastructure/monitoring/prometheus.yaml) now has five jobs; [Alloy](../../infrastructure/monitoring/config.alloy) collects host logs, not attributed pod logs; Grafana has data sources only | Replaced mixed proposed/current observability table; corrected scrape inventory | DEV-004/005, OPS-003/007: logs, resource usage, PostgreSQL/app telemetry and scoped views |
| Backlog records selected backup RPO/RTO/retention and partial SMTP/backup receipt while summary pages still called all undefined/unverified | Requirements, infrastructure, topology and monitoring summaries now reference selected policy and current evidence | Full scenario acceptance and precise measurements remain open; historical checks are not promoted |
| [Backup runner](../../operations/backup/scripts/backup-platform.py) implements exact readback, verified-only retention, service-stop recovery and independent backup state without an ADR | ADR-015 records bundle scope, exclusions and integrity/restore distinction; removed reference to deleted manual SQL helper | OPS-006/007: remaining failure, restoration and delivery criteria |
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
| 2 | DEV-004-T02, DEV-005-T02, DEV-007-T02, DEV-008-T01, DEV-009-T01, DEV-010-T02, OPS-003-T02, OPS-005-T01, OPS-005-T02, OPS-007-T02, OPS-008-T01, OPS-008-T02, PLAN-002, PLAN-003, PLAN-004, PLAN-005 |
| 3 | DEV-001-T01, PLAN-006, PLAN-007, PLAN-008, PLAN-009 |
| 4.1 | PLAN-010 |
| 4.2 | PLAN-011 |
| 4.3 | PLAN-012 |
| 4.4 | PLAN-013 |
| 4.5 | PLAN-014 |
| 4 (after 4.5) | PLAN-015 |
| Deferred | DEV-001-T02, DEV-002-T02, DEV-003-T03, DEV-006-T02, DEV-008-T02, DEV-009-T02, DEV-011-T02 |

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
| DEV-002-T01 | Not started | Capabilities declare `configuration.values: false` | No configuration CRUD |
| DEV-003-T01 | Not started | Capabilities declare `secrets: false`; only generated database Secrets exist | No secret CRUD, binding or redaction proof |
| DEV-003-T02 | Not started | None | Needs DEV-003-T01 |

Smallest route to closing the data-path part of 1C: run and record the isolation script, add a live write/read-and-redeploy drill (DEV-010-T01), then the interrupt-after-database-creation drill (DEV-007-T01). Configuration, secrets and logs (DEV-002/003/004) are new features.

## Developer stories

### DEV-001 — Deploy applications with multiple components

As a developer, I want to deploy an application composed of multiple components,
so that I can run its services and workers together within one project.

Acceptance criteria:

- Each component can specify its own image, startup command, ports, and replica count.
- Components can communicate through stable internal service names within the project.
- Deployment results identify successful and failed components and explain failures.
- Updating one component does not require redeploying unchanged components.

Phase tasks:

- [ ] **DEV-001-T01 · 3** — Review a concrete multi-component use case and capacity; record contract/migration design, independent-update semantics, and an owner-approved scheduling decision or continued deferral with a review trigger. Prerequisites: Phase 2 gate.
- [ ] **DEV-001-T02 · Deferred** — Implement named components with separate images, commands, ports and replicas; prove stable internal discovery, component-specific success/failure and independent updates, and migrate existing specs without data loss. Prerequisites: DEV-001-T01; explicit scheduling decision.

**Task evidence (B-2026-09-26):** T01 — local/unverified decision work; no multi-component contract decision or scheduling acceptance recorded. T02 — source absent, local unverified. The [API model](../../platform/app/main.py) has only `name`, `image`, and `port`, with one workload/database per project; no separate environment/application/component identity. PLAN-001 covers the single-image foundation; the deferred task requires a versioned migration.


### DEV-002 — Configure application environments

As a developer, I want to manage non-secret environment variables for each component,
so that I can change application behavior without rebuilding its image.

Acceptance criteria:

- I can view, add, update, and remove variables for an authorized component.
- Invalid configuration is rejected with an actionable error before it is applied.
- Changes indicate whether a rollout is needed and when the new configuration is active.

Phase tasks:

- [ ] **DEV-002-T01 · 1C** — Implement authorized configuration view/add/update/remove with validation before apply; report rollout requirements and observed activation for the single component. Prerequisites: OPS-004-T01; OPS-001-T01; PLAN-001.
- [ ] **DEV-002-T02 · Deferred** — Extend CRUD and activation reporting to independently addressed components; changing one component leaves others unchanged. Prerequisites: DEV-001-T02; DEV-002-T01.

**Task evidence (B-2026-09-26):** T01 — source absent, local unverified for user configuration CRUD/activation. The [API](../../platform/app/main.py) accepts no ordinary environment settings; extra fields are ignored under the model default rather than rejected. EV-01 validates names/manifests, not configuration acceptance. T02 — deferred, source absent, local unverified.


### DEV-003 — Manage application secrets

As a developer, I want to manage secret environment variables separately from ordinary
configuration, so that applications can use credentials without exposing them.

Acceptance criteria:

- I can create, replace, and remove secrets and assign them to specific components.
- Stored values are not returned in ordinary configuration views, logs, or audit records.
- Unauthorized users cannot read or modify secrets.
- I can roll out a replacement secret and see which components have adopted it.

Phase tasks:

- [ ] **DEV-003-T01 · 1C** — Implement separate secret create/replace/remove and authorized binding; prove values stay out of configuration views, logs and audit, and deny foreign-project read/write. Prerequisites: OPS-004-T01; OPS-001-T01; PLAN-001.
- [ ] **DEV-003-T02 · 1C** — Version and rotate a secret; observe adoption and successful reconnection before revoking the old version; include the new secret state in backup coverage. Prerequisites: DEV-003-T01; DEV-006-T01; OPS-006-T02.
- [ ] **DEV-003-T03 · Deferred** — Assign and rotate secrets per component and report adoption for every affected component without disclosing values. Prerequisites: DEV-001-T02; DEV-003-T02.

**Task evidence (B-2026-09-26):** T01/T02 — source partial; generated [Secret bindings](../../platform/app/manifests.py), redacted normal API responses/generic errors, and [cluster secret encryption](../../scripts/cluster_config.py) exist. User secret objects/references, authorized CRUD, rotation/adoption and comprehensive redaction tests are absent; local acceptance unverified (EV-01/02 are limited foundations). Changing `DATABASE_KEY` changes derived passwords, but [database provisioning](../../platform/app/main.py) only creates missing roles and does not update existing passwords: rotation must coordinate roles and Secrets. T03 — deferred, source absent, local unverified.


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
- [ ] **DEV-004-T02 · 2** — Add search, follow and project/component/instance/time filters; retrieve terminated-instance logs, show retention, and prove direct backend access cannot bypass authorization. Prerequisites: DEV-004-T01.

**Task evidence (B-2026-09-26):** T01 — source partial through [Alloy](../../infrastructure/monitoring/config.alloy) host Docker JSON logs. Explicit Kubernetes application-log collection inside k3d and project/environment/revision attribution are absent, as are authorized log endpoints. T02 — source absent for the requested query/retention workflow. Local task acceptance is unverified for both; shared dashboards do not enforce project boundaries.


### DEV-005 — Inspect application resources

As a developer, I want to see my application's deployed resources and resource usage,
so that I can understand its topology and identify capacity problems.

Acceptance criteria:

- I can list deployments, instances, services, routes, and attached data services.
- I can compare CPU and memory usage with configured requests, limits, and project quotas.
- Unavailable metrics are identified explicitly, rather than displayed as zero usage.

Phase tasks:

- [x] **DEV-005-T01 · 1C** — Expose basic authorized resource and CPU/memory observations; explicitly label missing or stale metrics. Prerequisites: OPS-004-T01; PLAN-001.
- [ ] **DEV-005-T02 · 2** — List deployments, instances, services, routes and attached data services; compare actual CPU/memory with requests, limits and quotas, including missing-data tests. Prerequisites: DEV-005-T01; OPS-003-T02; OPS-005-T01.

**Task evidence (B-2026-09-26):** T01/T02 — source partial: infrastructure metrics and Kubernetes object-state collection exist, but authorized resource/metric endpoints, workload usage comparisons and missing-data behavior are absent. [Prometheus](../../infrastructure/monitoring/prometheus.yaml) has no container resource-usage scrape; Grafana has data sources but no provisioned dashboards. Local workflow acceptance unverified; EV-04 establishes configuration only.


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
- [ ] **DEV-006-T02 · Deferred** — Report readiness, counts, active image and failures independently for each component, including mixed healthy/failed deployments. Prerequisites: DEV-001-T02; DEV-006-T01.

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
- [ ] **DEV-007-T02 · 2** — Select/reapply retained revisions and observe recovery rollout; report missing old secrets/dependencies and prove application rollback does not revert database contents or migrations. Prerequisites: DEV-007-T01; DEV-003-T02; DEV-006-T01.
  **Progress (October 3, 2026):** `GET /projects/{name}/revisions` lists retained revisions and `POST /projects/{name}/rollback` re-applies one (its stored spec and image digest) as a new revision through the normal deploy path; application-only, databases and roles are untouched (unit tests; live check pending). Open: observed recovery rollout evidence, and reporting missing old secrets/dependencies (no user secrets exist yet).

**Task evidence (B-2026-09-26):** T01 — source partial: database/role existence checks, deterministic credentials, server-side Kubernetes apply and a global PostgreSQL advisory lock support manual repeat PUT without intended database deletion. No persisted steps, automatic recovery worker or interruption acceptance exists. T02 — source absent: only the latest spec is retained; no revision selection, rollback or missing-secret dependency workflow. Both local acceptance results are unverified; EV-01 does not test durable recovery. PLAN-003 covers stale writes and concurrency hardening.


### DEV-008 — Scale application components

As a developer, I want to adjust component replicas and resource allocations,
so that I can match application capacity to demand.

Acceptance criteria:

- I can change replica counts and CPU and memory requests and limits per component.
- Changes that exceed project quotas are rejected with a clear explanation.
- If host capacity prevents scheduling, the platform shows the affected components and reason.

Phase tasks:

- [ ] **DEV-008-T01 · 2** — Change fixed replicas and CPU/memory requests/limits for one component; test explained quota rejection and host-capacity scheduling diagnostics. Prerequisites: PLAN-002; OPS-005-T02; DEV-006-T01.
- [ ] **DEV-008-T02 · Deferred** — Scale and allocate resources independently per component, retaining quota and scheduling failure attribution. Prerequisites: DEV-001-T02; DEV-008-T01.

**Task evidence (B-2026-09-26):** T01 — source partial through fixed [manifest](../../platform/app/manifests.py) replica/resource settings and namespace quotas; configurable scaling/resource requests/limits and scheduling diagnostics are absent. EV-01 verifies selected fixed quota settings only, not scaling acceptance. T02 — deferred, source absent, local unverified.


### DEV-009 — Control application connectivity

As a developer, I want to configure public endpoints and request required outbound access,
so that users and components can reach the services they need.

Acceptance criteria:

- I can choose which components are public and see their assigned URLs and TLS status.
- Components without a public endpoint remain inaccessible through public ingress.
- Required external destinations can be declared and are subject to operator policy.
- Rejected connectivity changes explain which policy prevented them.

Phase tasks:

- [ ] **DEV-009-T01 · 2** — Implement declared public/private exposure and outbound destinations; show URLs/TLS state, explain policy denials, and verify public-to-private changes remove obsolete ingress. Prerequisites: OPS-005-T02; PLAN-001.
- [ ] **DEV-009-T02 · Deferred** — Control exposure and outbound policy per component; prove private components cannot be reached through public ingress. Prerequisites: DEV-001-T02; DEV-009-T01.

**Task evidence (B-2026-09-26):** T01 — source partial: all projects get a public Ingress, with [Caddy](../../infrastructure/proxy/Caddyfile) edge forwarding to Traefik. Certificate authorization uses domain suffix and stored `applied` status, not observed health. Public/private transitions, declared egress, policy-specific errors and developer TLS-state reporting are absent. Local/live acceptance for DNS/ACME issuance/renewal, rejected names, outage behavior, forwarded headers and certificate-state recovery remains unverified; [ADR-009](../03-decisions/ADR-009-edge-and-cluster-ingress.md) lists exercises. T02 — deferred, source absent, local unverified.


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
- [ ] **DEV-010-T02 · 2** — Expose data-service availability and a tracked recovery request; demonstrate operator review, a documented controlled recovery procedure, and a developer-visible outcome without exposing foreign-project data. Prerequisites: DEV-010-T01; DEV-006-T01.

**Task evidence (B-2026-09-26):** T01 — source partial: [API provisioning](../../platform/app/main.py) creates dedicated non-superuser logins/databases and bindings use `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`, not the draft configurable `DB_*` prefix. Each runtime login owns its database; runtime/migration/human role separation is absent. The provisioner uses PostgreSQL `postgres` and cluster-wide Kubernetes permissions. Database preservation and CONNECT restrictions exist in source, but application write/read and live isolation remain unverified; smoke uses `http-echo`, and isolation was inspected, not run. T02 — source absent and local unverified for developer availability/recovery requests. Resolve ADR-003 role separation when implementing the binding/recovery design.


### DEV-011 — Remove unused applications

As a developer, I want to remove applications I no longer need,
so that unused workloads stop consuming project resources.

Acceptance criteria:

- Before deletion, I can review the affected components, routes, and configuration.
- Deletion requires explicit confirmation and reports completion or partial failure.
- Persistent data is retained unless a separate, explicit data deletion is authorized.

Phase tasks:

- [x] **DEV-011-T01 · 1C** — Preview affected workload/routes/configuration and require explicit confirmation; invalidate changed scope, retain data by default, persist retained inventory, and expose retryable partial failure and audited completion. Prerequisites: DEV-007-T01; OPS-001-T01.
- [ ] **DEV-011-T02 · Deferred** — Extend deletion previews and retryable cleanup to all components; verify actual removals match confirmed scope and data deletion remains separately authorized. Prerequisites: DEV-001-T02; DEV-011-T01.

**Task evidence (B-2026-09-26):** T01 — source absent for application deletion, preview/confirmation, resumable cleanup and retained-resource inventory. Lab teardown is not a scoped application lifecycle. Local acceptance unverified; shell syntax in EV-03 does not test deletion safety. T02 — deferred, source absent, local unverified.


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
- [ ] **OPS-003-T02 · 2** — Deliver host/usage/request comparisons and project storage/usage breakdown including shared services; test stale/missing metrics, capacity alerts and unschedulable workload visibility. Prerequisites: OPS-003-T01.

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

**Task evidence (B-2026-09-26):** T01 — source absent for individual scoped identities, memberships, roles, grant revocation and audit. The [platform guide](../../platform/README.md) correctly describes a single administrator bearer token granting all-project access. Infrastructure database/network restrictions do not supply user authorization. Local end-user acceptance unverified; the inspected smoke script's unauthenticated rejection does not test scoped access.

**Decision update (October 2, 2026):** [ADR-004](../03-decisions/ADR-004-identity-and-access-management.md) accepts a provider-neutral OIDC boundary with Keycloak as the supported lab reference, platform-owned grants, immutable issuer/subject principal keys, and `viewer`, `developer`, `project-admin` and `platform-admin` roles. This resolves the prerequisite design choice but supplies no OPS-004 implementation or acceptance evidence.

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

- [ ] **OPS-005-T01 · 2** — Configure per-project quotas, resource defaults and allowed network/security policy; show impact on existing workloads and subsequent deployments. Prerequisites: PLAN-002; OPS-004-T01; OPS-003-T01.
- [ ] **OPS-005-T02 · 2** — Reject security/quota violations with specific reasons; admit against aggregate host allocations after system/shared-service reserve and test policy enforcement. Prerequisites: OPS-005-T01; OPS-003-T02.

**Task evidence (B-2026-09-26):** T01/T02 — source partial: fixed quotas/LimitRange, restricted Pod Security, non-root/read-only workloads, dropped capabilities, no mounted API token and NetworkPolicies exist in [manifests](../../platform/app/manifests.py). Configurable policy, impact previews and aggregate host admission are absent. EV-01 checks selected hardening/quota settings only. All Compose/k3d services share the `developer-platform` network; pods use a fixed PostgreSQL IP because Compose DNS is not Kubernetes DNS. PostgreSQL TLS and target edge/platform/persistence segmentation are unimplemented; policy convergence can briefly allow new-pod egress. Define/test the required boundaries as part of policy work without claiming hostile-tenant isolation. Local/live network acceptance unverified; the isolation script was not run.


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
- **T02 — Accepted limitation:** [ADR-017](../03-decisions/ADR-017-phase-1a-retention-evidence-scope.md) omits elapsed-time proof of the 14 daily, 8 weekly, and 6 monthly policy from Phase 1A. The configured policy and scoped retention implementation remain in operation; full-horizon behavior is not demonstrated.
- **T02 — Accepted limitation (September 28, 2026):** [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md) removes the missing-update/local-monitoring-outage backup exercise from lab acceptance. The lab has no live evidence that external backup notifications continue while local monitoring is down.
- [x] **T03 — Fresh isolated restore:** playbook restored SQL, source/configuration and service volumes from S3 into a fresh Ubuntu VM without reading the source host during restoration.
- [x] **T03 — Historical SQL marker:** an independent pre-backup receipt matched the restored record through a Kubernetes test pod using the project Secret.
- [x] **T03 — Recovered service checks:** API/catalog, selected project rollout, HTTP ingress, project database authentication/write/read, denied catalog CONNECT privilege, Prometheus targets and Grafana database health passed.
- **T03 — Deferred scope:** recovery notification receipt, precise RPO/RTO measurements, production DNS/TLS, application-level database transactions, and recurring fresh-VM restoration are outside Phase 1A under ADR-016.

**P-2026-09-28 — Historical recovery failure preflight and cadence:** [check-recovery-failure-modes.yml](../../operations/backup/ansible/check-recovery-failure-modes.yml) runs selected unavailable-endpoint, wrong-password, and missing-password checks on an explicitly provisioned WSL recovery VM. It uses `restic snapshots --no-lock`, expects each negative case to fail, writes no repository state, removes temporary credentials, and fetches a non-secret report. This tooling and its prior cadence are historical reference material; ADR-016 removes the exercises and recurring full restores from Phase 1A.

**E-2026-09-28 — Recovery failure preflight passed:** The operator ran the playbook on `recovery_vm` after entering S3 credentials and the existing repository password. All three selected negative cases (`unavailable-endpoint`, `wrong-password`, `missing-password`) produced the expected failure, the assertion passed, and the temporary credential directory was removed. The fetched non-secret report is timestamped `2026-09-28T20:27:19Z` and records `repository_write_mode: disabled (--no-lock)`. This establishes the selected storage and credential failure behavior, not corruption, a full restore, or recovery-notification receipt.

**T03 — Accepted limitation (September 28, 2026):** [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md) excludes deliberately corrupting, deleting, or altering data in the only live restic repository. Repository `check`, verified readback, and automated checksum-rejection evidence remain in place; there is no live injected-corruption evidence.

**P-2026-09-28 — Lab recovery access policy accepted:** The owner accepted the fresh-WSL-VM replacement-host procedure and off-node password-manager storage for the Hetzner S3 credentials and restic password. This completes OPS-006-T01 planning within the single-environment lab scope; see [ADR-015](../03-decisions/ADR-015-verified-backup-bundles.md).

**In-place failure drill tooling (September 27, 2026; OPS-006-T02/OPS-007-T01):**
Added [drill-backup-failure.yml](../../operations/backup/ansible/drill-backup-failure.yml)
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
Added [stalled](../../operations/backup/ansible/drill-backup-stalled.yml) and
[overdue](../../operations/backup/ansible/drill-backup-overdue.yml) launch
playbooks plus [status/evidence collection](../../operations/backup/ansible/check-backup-drill.yml).
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

**Failed-backup drill evidence F-2026-09-27 (operator supplied; OPS-006-T02/OPS-007-T01):** The operator reports that [drill-backup-failure.yml](../../operations/backup/ansible/drill-backup-failure.yml) executed correctly on the existing lab and both notification emails arrived. The referenced drill injects database-capture failure, verifies preservation of the prior successful capture/snapshot, waits for the DOWN notification window, then runs and verifies a normal recovery backup. This is operator-reported acceptance of the failed-capture/recovery path and its email pair. The fetched report, exact deployed revision, snapshot IDs and receipt times were not supplied for independent inspection. It does not establish upload-failure acceptance; notification-delivery-failure injection and the local-monitoring-outage exercise are accepted limitations under ADR-011. No separate test environment was used, in accordance with ADR-010.

**Repository inspection I-2026-09-28 (operator supplied; OPS-006-T02):** `platform-restic snapshots --host node-01 --tag developer-platform,verified` listed four verified snapshots: `c03a2bcc` (September 26 15:01:01 UTC), `5ea9753a` (September 26 19:39:06 UTC), `b056b558` (September 27 10:52:27 UTC), and `94eda65a` (September 28 12:00:47 UTC). `platform-restic check` opened repository `ef5d344f`, checked one index and all four snapshots, trees and blobs, and reported no errors. This establishes an inspectable verified-snapshot inventory and repository structural integrity at that time. Four snapshots cannot demonstrate the configured 14/8/6 long-horizon retention policy; command output establishing root-only credential paths was not supplied.

**Backup credential access evidence A-2026-09-28 (operator supplied; OPS-006-T02):** `stat` confirmed `/etc/developer-platform/backup` and `/usr/local/sbin/platform-restic` at mode `0700`; `/etc/developer-platform/backup/restic.env` and `restic-password` at mode `0600`; all paths owned by `root:root`. This establishes host-side access restrictions for configured backup credentials and the wrapper. It does not establish S3-provider IAM policy or long-horizon retention outcomes.

**Scheduled backup evidence S-2026-09-27 (operator supplied; OPS-006-T02):** `platform-backup.timer` reported its last trigger at 00:00:04 UTC and next at 12:00 UTC. The service journal records successful start/completion at 00:00:04/00:01:38 UTC. Durable status records run `60c70027e90644258716b3c3bfeb8c4b`, `running: false`, `result: success`, `stage: complete`, and verified snapshot `38f989c67a080a82970d796d1a3da1c79d6264005e131d116431a12333a0e1ed`. The journal explicitly reports verified backup and completed retention. This establishes one scheduled successful capture/readback/retention run, not full retention-policy/access-control acceptance, notification email receipt, or restoration of this snapshot. Exact deployed revision was not supplied.

**Operational evidence R-2026-09-26 (operator supplied):** Source `node-01`;
recovery target `platform-recovery`, Ubuntu 24.04 amd64 under QEMU/KVM in WSL 2.
[Marker preparation](../../operations/backup/ansible/prepare-recovery-test.yml)
completed with 13 successful tasks, zero failures and backup service exit code 0.
Verified snapshot: `5ea9753aa32f362e351223154589489cf32b9188098da1f9d270030c1d39ed19`.
Independent controller receipt:
`.runtime/recovery-evidence/platform/recovery-test-ksghhx8e/marker.json`.
The [restore playbook](../../operations/backup/ansible/restore-recovery.yml)
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
by the successful-path drill alone. Use the [playbook-first workflow](../../operations/backup/README.md#start-with-the-playbooks).

**Historical implementation and baseline evidence:** The dated notes below retain
what was known at each earlier step. Statements that deployment or restoration had
not run apply to those steps, not to current progress above.

**Operator decisions (September 26, 2026; OPS-006-T01):** The user reports no application data currently requiring preservation; platform configuration and secrets remain in recovery scope. Confirmed destination: Hetzner Object Storage, bucket `eseidinger`, endpoint `https://hel1.your-objectstorage.com`, prefix `developer-platform/`. Access credentials exist and remain outside this repository. Confirmed policy: backups every 12 hours; retain 14 daily, 8 weekly and 6 monthly recovery points; RPO at most 24 hours and RTO at most four hours. These are selected targets, not measured guarantees. At decision capture, storage/key access and restore execution were unverified. Current verified outcomes and remaining T01 planning are listed above.

**Repository setup progress (September 26, 2026; OPS-006-T02):** Added [operations/backup/ansible/setup-backup.yml](../../operations/backup/ansible/setup-backup.yml), a [backup inventory example](../../operations/backup/ansible/inventory.backup.example.yml), private configuration template and root-only restic wrapper. This installs restic/CA certificates, configures the confirmed S3 destination and prompts privately for credentials/password, optionally initializes a new repository, then verifies opening and snapshot listing. Existing local repository passwords cannot be implicitly replaced. Usage is in the [Ansible guide](../../operations/backup/README.md#encrypted-s3-backup-repository-setup). Syntax checks passed. A temporary local Ansible fixture (package installation omitted, paths redirected to a temporary directory, simulated restic backend) verified check-mode nonmutation, explicit initialization, unchanged reruns, rejected password replacement, inaccessible-repository failure without implicit initialization, shell-metacharacter credential quoting, and 0600 secret file permissions. This is local fixture evidence for the working-tree change based on `10ca8ef`, not a target-host/S3 test. No package installation, backup upload, scheduled job, pruning or restore was performed. At this setup-only milestone, capture automation and operational acceptance remained outstanding; see current progress above.

**Setup run correction (September 26, 2026; OPS-006-T02):** The user reported a target-host run stopping at the initialization guard: `-e backup_restic_initialize=true` supplied a string, whose extra-variable precedence bypassed the original `set_fact` conversion. Setup reported 14 successful tasks and five changes before this failure; repository initialization/access was not established. Both consuming conditions now apply `default(false) | bool` explicitly. The original local fixture supplied a JSON boolean and missed this case; regression validation now uses the documented key=value command-line form for both true and false. Rerun with the same repository password; do not disable Ansible's strict conditional checks.

**Operator-reported repository setup (September 26, 2026; OPS-006-T02):** The user reports a successful rerun of setup-backup.yml and repository config present in the S3 bucket. This establishes reported initialization/access, not a data backup or restoration.

**Scheduled backup implementation (September 26, 2026; OPS-006-T02, OPS-007-T01):** [deploy-backup.yml](../../operations/backup/ansible/deploy-backup.yml) and the [runner](../../operations/backup/scripts/backup-platform.py) now provide locked twelve-hour UTC capture, a two-hour timeout, encrypted upload, exact-snapshot restore/checksum comparison, verified-only installation-scoped 14/8/6 retention with pruning/check, private durable status, interrupted-service recovery and notification retry. Capture includes SQL/roles/catalog, source/config/secrets, Caddy/Grafana stopped-service volumes, installed backup helpers/units and version/image metadata. The separate authenticated backup watchdog table/endpoint detects failed, missing, overdue and stalled backups without using host heartbeat freshness. Service capture briefly interrupts Caddy/Grafana; staging/readback needs disk for two bundle copies. External watchdog state and historical telemetry are excluded; image artifacts must remain available. See [deployment and recovery details](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts).

Local validation on the working tree (based on `10ca8ef`) includes ten Python tests with a real local restic 0.16.4 encrypted repository, checksum mismatch and failed-upload behavior, pending-snapshot retention isolation, interrupted-service recovery, and notification retry; PHP state/freshness tests and a disposable PHP/MariaDB integration test establish separate tokens/state, replay rejection, overdue/stalled detection, failed mail-handoff retry, recovery and repeat schema import. Integration mail is simulated. These results are local evidence only: no deployment to node-01, Hetzner snapshot upload, live BACKUP email receipt or SQL/application restoration was performed by this implementation work. This local-test milestone preceded the operator-reported deployment and restore; remaining acceptance is listed above.

**Task evidence (B-2026-09-26):** T01/T02 — source partial: the former local SQL dump helper (since removed in favor of the scheduled backup runner) privately and atomically published a compressed local `pg_dumpall` through a temporary file, including databases/roles/platform catalog. Scheduling, encrypted upload, remote retention, recovery-key/config automation and backup-age alerts are absent. T03 — source partial through the [isolated restore/reapply guide](../05-operations/backup-recovery.md); no executable restore harness or measured recovery evidence. EV-03/06 establish script/example syntax only. Recovery must retain `DATABASE_KEY` and compatible credentials, handle SQL errors explicitly, restore catalog/data, reapply workloads and prove application write/read. No SQL dump/import, clean-host restoration or actual backup alert exercise ran in the baseline assessment.


### OPS-007 — Monitor service availability

As an operator, I want to monitor shared services and application availability,
so that I can detect outages and identify affected projects.

Acceptance criteria:

- Health checks cover the control plane, ingress, database, and monitoring services.
- Alerts identify the failing service and affected projects where that information is available.
- An external check can report a complete host outage when local monitoring is unavailable.
- Alert routing can be tested before relying on it for incident response.

Phase tasks:

- [x] **OPS-007-T01 · 1A** — Configure real Alertmanager/watchdog routing and response ownership; verify actual outage/recovery receipt, cluster/host expiry, and public canary. Independent watchdog cron/hosting detection and notification-delivery-failure injection are excluded under [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md); both are accepted lab limitations. Keep platform, pipeline and backup identities/timestamps isolated. Prerequisites: Installation inventory and notification recipients.
- [ ] **OPS-007-T02 · 2** — Exercise control-plane, ingress, database, monitoring and application failure checks; identify affected projects where known and verify external detection with host/local monitoring unavailable. Prerequisites: OPS-007-T01; DEV-006-T01.

#### Current monitoring progress

**Application probe preparation (September 27, 2026):** [Catalog-driven blackbox probes](../../infrastructure/monitoring/README.md) add root-path HTTP 200 and optional `hello-world` content profiles, shared availability/missing-result/discovery-freshness rules, and authenticated retirement acknowledgement after manual namespace removal. Failed/provisioning entries stay monitored; retired entries retain SQL data/specs and leave discovery. Public HTTPS probes run on the platform host; local probes use HTTP routing through Caddy. Outside-network reachability remains manual evidence. Source/local preparation does not establish deployment, real retirement, or notification receipt; OPS-007-T01 remains open. This is not the full planned deletion/audit workflow. Local verification: 16 platform tests passed; Prometheus configuration and six alert-rule scenarios passed; disposable exporter/Prometheus fixtures verified content/status/timeout/TLS rejection, recovery, target labels and removal without reload. API image build and UID 10001/shared-volume reader checks passed. Backup regression suite: 34 passed, one optional real-restic test skipped. No live platform deployment or real notification test was run.


**Availability drill tooling (September 28, 2026; OPS-007-T01):** Added [cluster](../../operations/heartbeat/ansible/drill-cluster-availability.yml) and [Docker-boundary](../../operations/heartbeat/ansible/drill-docker-availability.yml) exercises. Cluster mode stops only `k3d-workloads-server-0`, waits for the `kubernetes-state` scrape failure and `ScrapeTargetDown`, then restores the same container and verifies node, target and alert recovery. Docker mode stops Docker for a bounded interval so the external heartbeat can become overdue, then verifies Docker, Prometheus, Kubernetes nodes and the heartbeat timer after restoration. Both save a private report and require operator confirmation of email receipt. Local Ansible syntax and Python compilation passed. The operator subsequently reported both drills completed successfully; detailed reports, exact revision, alert labels, timings, and email receipt are not yet recorded.

**SMTP configuration tooling (September 27, 2026; OPS-007-T01):**
Added [inventory-based Alertmanager deployment](../../operations/alertmanager/README.md)
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
- [x] **T01 — Response ownership:** on September 27, 2026, the owner confirmed they are the sole responder, targeting initial response within 24 hours for this side project. No secondary responder or escalation coverage; see the [accepted lab response policy](../05-operations/monitoring.md#alert-process). This records ownership and a response target, not measured response performance.
- [x] **T01 — Cluster failure and recovery:** operator reported successful execution of the cluster availability drill on September 28, 2026. The drill completion requires a failed `kubernetes-state` target, firing `ScrapeTargetDown`, restoration of the k3d server, all nodes Ready, target recovery, and alert resolution. Exact report, revision, and alert times were not supplied. The operator subsequently confirmed both ScrapeTargetDown FIRING and RESOLVED emails.
- [x] **T01 — Docker failure boundary and recovery:** operator reported successful execution of the Docker availability drill on September 28, 2026. The drill stops Docker for a bounded interval, restores it, and requires Docker, Prometheus, all Kubernetes nodes, and the heartbeat timer to recover. This simulates the local Docker boundary, not a power-loss host outage; exact report, revision, and timings were not supplied. The operator subsequently confirmed external watchdog DOWN and UP emails.
- [x] **T01 — Availability-drill notification receipt:** operator confirmed ScrapeTargetDown FIRING/RESOLVED emails for the cluster drill and external watchdog DOWN/UP emails for the Docker drill (September 28, 2026).
- [x] **T01 — Public application canary:** operator confirmed the monitored `smoke` application was scaled to zero and back on September 28, 2026, producing both ApplicationUnavailable FIRING and RESOLVED emails. Exact project revision, replica count, probe/alert timing, and recovery output were not supplied.
- [x] **T01 — Current accepted scope complete:** Alertmanager and external-watchdog delivery, configured notification recovery, cluster/Docker-boundary drills, and the public application canary have live operator evidence. The accepted ADR-011 limitations remain recorded below. OPS-007-T02 retains later Phase 2 service coverage.
- **T01 — Accepted limitation (September 28, 2026):** [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md) excludes notification-delivery-failure injection from lab acceptance. The lab has no live evidence of alerting behaviour when email delivery fails.
- **T01 — Accepted limitation (September 28, 2026):** [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md) excludes a backup-missing-update exercise with local monitoring unavailable. This coverage gap remains an accepted lab risk.
- **T01 — Accepted limitation (September 27, 2026):** [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md) removes independent watchdog cron/hosting failure detection from lab acceptance at the owner’s request. Watchdog failure and incidents occurring while it is unavailable may go unnoticed. This is an accepted scope limit, not verified detection or deferred implementation.

**Operator-reported SMTP evidence (September 27, 2026; OPS-007-T01):** The operator reported that the SMTP deployment playbook completed without errors and confirmed both alert and recovery email receipt after submitting `PlatformEmailTest` directly to Alertmanager using amtool on `node-01`. This establishes Alertmanager-to-email delivery only; it bypasses Prometheus rule evaluation. Exact deployed revision, receipt times, delivery latency and named response owner were not captured. Notification-delivery-failure injection is an accepted limitation under ADR-011; the other T01 acceptance checks remain open. This live evidence follows the local-only tooling validation above.

**Operator-reported rule-path evidence (September 27, 2026; OPS-007-T01):** Following the guided `node-exporter` stop/start exercise, the operator confirmed receipt of both alert and recovery emails. This verifies the selected scrape-failure rule through Prometheus, Alertmanager and SMTP, including recovery. Exact deployed revision and receipt/detection timings were not captured. This does not establish complete host/cluster failure detection, other rule coverage, or notification-delivery-failure handling; the latter is an accepted limitation under ADR-011, and OPS-007-T01 remains open.

These are operator-reported live outcomes, distinct from the imported local tests.
Healthy recovery monitoring does not establish alert delivery; the recovery VM
intentionally suppresses production notifications. OPS-007-T01 remains open.

**Operator-reported live evidence (September 26, 2026; OPS-007-T01):** On `node-01` in `/opt/developer-platform`, supplied output shows Compose services running, API/Prometheus readiness passing, three Kubernetes nodes Ready, and an enabled heartbeat timer with successful service exits. The user confirmed fresh external watchdog status and receipt of both outage and recovery emails during a heartbeat pause/resume exercise. A manually duplicated send received HTTP 429 about 16 seconds after a successful send; future recovery should start only the timer. Deployed revision, exact notification latency and final post-test service result were not captured. This establishes the user-reported heartbeat notification path only; independent Alertmanager delivery, application canary and watchdog-failure acceptance remain open. Do not close T01 from this partial evidence. The historical watchdog-failure acceptance requirement is subsequently removed by ADR-011; other outstanding criteria remain open.

**Task evidence (B-2026-09-26):** T01/T02 — source partial. [Monitoring](../../infrastructure/monitoring/compose.yaml) runs outside k3d; [rules](../../infrastructure/monitoring/alerts.yaml) cover scrape failure, low disk and unavailable replicas, but [Alertmanager](../../infrastructure/monitoring/alertmanager.yaml) has a `local-only` receiver with no notification integration. PostgreSQL exporter, application request/error/latency, backup-age and job telemetry are missing.

The [host sender](../../operations/heartbeat/scripts/heartbeat.py) checks API dependency readiness and Prometheus, then sends a heartbeat; it neither sends local alerts nor checks Alertmanager delivery, Grafana, Loki, backups or an end-to-end application. The external watchdog implements authenticated POST, receipt-time freshness, throttling, a fixed optional HTTPS probe (HEAD at the imported baseline; subsequently corrected to GET as recorded above), deduplication and retry after failed mail handoff. [Mail](../../operations/watchdog/src/mail.php) supports PHP mail and TLS-verified STARTTLS/implicit SMTP; [cron](../../operations/watchdog/src/cron.php) reports failure stages without raw exceptions. Maintenance windows and token-rotation workflow are absent. A stale cron returns an unavailable status page, but has no independent notifier.

The [heartbeat playbook](../../operations/heartbeat/ansible/deploy-heartbeat.yml) installs Python/CA certificates, a dynamically readable sender, private systemd environment and timer. The [external playbook](../../operations/watchdog/ansible/deploy-watchdog.yml) uploads an explicit release over SSH/SCP, preserves host-key checking, suppresses credential output and optionally replaces config/installs minute cron. Check mode validates local inputs only. Database/user, document root, HTTPS, extensions and mail are operator prerequisites; the uploaded [schema importer](../../operations/watchdog/src/import-schema.php) must run separately. Neither playbook was deployed in the assessment. EV-07–10 verify local freshness/SMTP/syntax only; actual receipt, public probing, sender installation and independent-failure detection remain unverified.


### OPS-008 — Decommission projects safely

As an operator, I want to retire projects with an explicit data retention decision,
so that I can reclaim resources without accidentally deleting required data.

Acceptance criteria:

- A deletion preview lists workloads, routes, credentials, databases, and retained backups.
- Destructive data deletion requires explicit confirmation of the project and retention decision.
- Decommissioning revokes project access and credentials and removes the selected resources.
- Partial failures can be retried, and the result and retained resources are recorded in the audit trail.

Phase tasks:

- [ ] **OPS-008-T01 · 2** — Preview project workloads/routes/credentials/databases/backups; record explicit project-specific retention/deletion decisions and confirmation invalidated by scope changes. Prerequisites: DEV-011-T01; OPS-004-T01; OPS-006-T02.
- [ ] **OPS-008-T02 · 2** — Revoke project access/credentials and remove selected resources; inject partial failures, retry without affecting other projects, and audit all retained/deleted resources and outcomes. Prerequisites: OPS-008-T01; OPS-001-T01.

**Task evidence (B-2026-09-26):** T01/T02 — source absent for scoped project retirement, inventory/confirmation, credential revocation and audited retryable cleanup. Whole-lab teardown cannot satisfy these workflows. Local acceptance unverified; prerequisites include retained data inventory, individual access and tested recovery.


## Additional phase tasks

These tasks make the existing phase work executable without inventing new DEV/OPS stories or treating portability, interfaces or AI as acceptance criteria for unrelated stories. They are mandatory within their assigned phase. An unresolved ADR may block implementation choices; it does not waive a requirement or permit phase closure without its acceptance evidence. An explicit scope change must update the requirements and phase plan together. Deferred component implementation remains separate.

- [x] **PLAN-001 · 1C** — Implement stable project/environment/application identity and atomically persisted desired revisions/asynchronous jobs before side effects, returning an operation ID with authorized progress and worker-interruption recovery. Validate the supported single-image profile, reject unknown fields/unsupported capabilities before side effects, and use technology-independent public identities and minimal provider ports. Demonstrate an authorized application restart with unchanged desired spec, retained data and observed readiness; demonstrate minimal API/CLI deployment and record installation versions/parameters. Prerequisites: Phase 1B gate.

  **Task evidence (B-2026-09-26):** Source partial; local EV-01–04 cover foundations only. Stable project names and latest specs exist, but environments/ownership/application IDs, asynchronous jobs, operation IDs, observed health and restart are absent. PUT is synchronous; unknown fields are ignored and no capability checks exist. Bootstrap/Ansible/config generation and checksum-verified installation exist, but Ansible ends at process health, not full application/database acceptance; firewall/backups are separate. UC-01 remains an administrator-only partial flow.

  **Schema, API and worker progress (October 3, 2026; working tree based on `2a6d2f0`):** The catalog migration adds stable internal project, default-environment and single-application IDs while preserving public project slugs and slug-based grants. Existing projects are backfilled with a default environment/application and revision 1. Desired specs are stored as immutable revisions; identical specs reuse the latest revision. PUT persists a versioned queued operation with its desired revision in one transaction, deduplicates active operations for that revision, and returns `202 Accepted` with an operation ID/status URL. `GET /v1/operations/{id}` checks current project-view authorization, audits reads, redacts results, and appends a live readiness snapshot separate from the durable apply outcome. An in-process worker claims queued/running operations with PostgreSQL advisory locks, rechecks the submitter's current change grant and desired revision, applies idempotent provider steps, records sanitized results, and reclaims interrupted running work after restart. Retirement is blocked while operations are active. Current local verification is recorded as EV-11 and EV-12. The request model rejects unknown project fields before catalog/provider side effects. Unsupported capabilities, live readiness failure drills, live worker interruption/failure drills, and end-to-end deployment acceptance remain open.

  **Update (October 3, 2026):** live acceptance, worker-interruption (EV-13), readiness failure (EV-14, EV-15), authorized restart (EV-16) and installation record (EV-17) evidence now exist; the throwaway `badimage` project was removed (namespace deleted, then retired with data retained) and the API/CLI demo is documented in the runbook. Unsupported capabilities (scaling, object storage, messaging, cache, multiple components, resources, environment) are rejected with 422 and no catalog/provider side effect by the strict `Project` model, covered by a unit test. Installation record now includes image references (EV-17). Repeat-POST reuse and no-spurious-rollout were confirmed live (EV-18); only a `progressing` snapshot during a restart roll remains unobserved. Tests use doubles; no live PostgreSQL migration/API, Kubernetes execution or operational acceptance was run. PLAN-001 remains open.

- [x] **PLAN-002 · 2** — Complete ApplicationSpec/API fit-gap and schema reuse assessment, versioned OpenAPI contract, environment capabilities/profiles, explicit CPU/memory request/limit semantics and migration rules; reject unsupported requests before side effects and keep backend fields out of the public contract. Prerequisites: Phase 1 gate.

  **Task evidence (B-2026-09-26):** Source partial; local EV-01 validates names/manifests, not the draft contract. API output exposes `namespace` and implementation calls Kubernetes directly. Schema versioning, capabilities, configurable bindings/resource budgets and fit-gap evidence are absent. Tag-to-digest resolution is absent despite the ApplicationSpec target; include it when stabilizing deployment identity.

  **Progress (October 3, 2026):** Tag-to-digest resolution is implemented in the API at acceptance (anonymous, allow-listed registries; unknown tag/unsupported registry 422, outage 503, no side effects; `resolved_image` stored in the revision and used for deployment and readiness), with unit tests. Live-verified in EV-19. The field-level [fit-gap](../02-architecture/application-spec-fit-gap.md) is written. Resource requests/limits are decided and implemented in the flat body (explicit requests and limits, validated, stored per revision, applied to the container; unit tests only, no live evidence yet); The versioned `Application` envelope is accepted next to the flat body (unit tests only) and the OpenAPI contract is committed; the public API does not expose `namespace`, `GET /v1/capabilities` publishes the default-environment capabilities and PUT rejections carry stable codes (unit tests only; no live evidence). Live evidence for the capability endpoint and stable codes is EV-22. Decision: the flat body stays supported with no sunset date and the envelope is the preferred format. PLAN-002 is closed; the Phase 1 gate prerequisite was not separately verified.

- [x] **PLAN-003 · 2** — Harden worker interruption, concurrent writes, revision retention and drift recovery; prove no duplicated resources/lost revisions and redacted traceable provider failures. Prerequisites: PLAN-002; DEV-007-T02.

  **Progress (October 3, 2026):** Decision: concurrent writes use an optional `If-Match: <revision>` header on PUT; a stale value returns 409 `revision_conflict` with the current revision and no side effects, and omitting it keeps last-writer-wins (unit tests; live check in EV-23). Drift decision: report only, never auto-revert; `GET /projects/{name}/drift` reports image, replica and resource differences and audits `project.drift.detected` (unit tests; live replica drift in EV-24; a background scan audits drift transitions; live in EV-25). Provider failures now record a redacted trace (`step`, `error_type`, numeric `http_status`; never exception text) in the operation result, audit detail and log (unit tests only; live check pending). Revision retention: each new revision prunes all but the newest `REVISION_RETENTION` (default 25), skipping revisions with queued/running operations and the last successful restart (unit tests; live check pending). Idempotency keys are dropped from scope (If-Match and spec deduplication cover it) and persisted health transitions are deferred to observability. Retention and rollback are live-verified in EV-26. Closed with two accepted gaps: the failure trace is unit-tested only (it will surface on the next real deploy failure), and revision 2 stayed beyond the window in EV-26 with the restart-pinning explanation unconfirmed (bounded to one extra revision); DEV-007-T02 is partly built (rollback) with its open parts noted there.

  **Task evidence (B-2026-09-26):** Source partial; local workflow acceptance unverified. A global advisory lock serializes cooperating API requests but supplies no expected-revision conflict check. Updates overwrite the only spec; stale clients can replace intent. Persistent idempotency keys, revision history, per-step recovery and drift reconciliation are absent.

- [ ] **PLAN-004 · 2** — Add the Docker adapter and shared provider contract tests; deploy/update/observe/remove the same spec on Kubernetes and Docker, including partial failure and capability rejection; publish tested profile differences. Prerequisites: PLAN-002; PLAN-003; Phase 2 retained-backlog packages.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. Docker hosts shared services but is not a direct application compute provider. No portable provider contract or reproducible provider comparison harness exists (F-07/UC-05).

- [ ] **PLAN-005 · 2** — Implement the ADR-006 transition as separately gated packages: versioned catalog/control-plane/worker contracts; Kotlin catalog metadata/grant migration; Quarkus control-plane contract and state parity; Python durable worker separation; single-writer cutovers; backup/restore and rollback. Prove cross-service authorization, audit correlation, interruption/idempotency, and stable-ID reconciliation before retiring the corresponding FastAPI path. Prerequisites: PLAN-001; PLAN-002; code/effort analysis before contract stabilization.

  **Task evidence (B-2026-09-26):** At this baseline the decision was open and local implementation-language parity/migration acceptance was unverified. The existing Python vertical slice remains the implementation baseline. ADR-006 accepted the target roles on October 1, 2026; that documentation decision supplies no implementation, migration, or acceptance evidence.

- [ ] **PLAN-006 · 3** — Deliver portal and CLI using the versioned catalog and control-plane APIs for ownership/roles, applications, deployments, redacted config, logs and operations; diagnose an injected failure and prove bypassed UI checks still fail in the responsible service. Prerequisites: Phase 2 gate.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. REST/curl and interactive API docs are not a domain CLI or self-service portal; no UI/API compatibility journey exists.

- [ ] **PLAN-007 · 3** — Deliver the web/PostgreSQL template and reproducible create/deploy/diagnose journey; verify UI/API compatibility and document the role matrix. Prerequisites: PLAN-006.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. The sample project JSON/http-echo demonstrates provisioning only, not a combined UI/API template or application/database journey (ADR-007).

- [ ] **PLAN-008 · 3** — Deliver separate authorized/audited human database identity and controlled tunnel; test foreign-project denial, credentials distinct from application credentials, and revocation of new/existing sessions per policy. Prerequisites: Phase 2 gate; accepted IAM design.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. Runtime logins own their database; no separate human identity, controlled tunnel, grant audit or session revocation workflow exists (F-09/UC-03).

- [ ] **PLAN-009 · 3** — Automate hosted-application OIDC clients/redirect URIs against the accepted provider-neutral OIDC boundary; demonstrate platform/application role separation and no implicit platform-admin access. F-10 acceptance is required for Phase 3 completion. Prerequisites: Phase 2 gate; ADR-004 acceptance.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No OIDC provider/client automation or platform/application role-separation flow exists. ADR-004 was proposed at this baseline.

  **Decision update (October 2, 2026):** ADR-004 accepts a generic OIDC contract with Keycloak as the supported lab reference and platform-owned authorization. This resolves the blocking design choice but supplies no implementation or acceptance evidence for PLAN-009.

- [ ] **PLAN-010 · 4.1** — Expose bounded read-only Platform API tools and authorized/redacted application/revision/configuration/document context; produce sourced explanations and test project denial and untrusted-input handling. Prerequisites: Phase 3 gate; scoped data/audit evidence.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No AI layer or authorized context/tools; ADR-008 accepts product focus only, not its implementation.

- [ ] **PLAN-011 · 4.2** — Correlate incident logs, metrics and history with timestamps/comparison windows; distinguish observations/hypotheses and explicitly report missing evidence. Prerequisites: PLAN-010; DEV-004-T02; DEV-005-T02; DEV-007-T02.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No AI incident correlation; underlying scoped telemetry and deployment history are also incomplete (UC-06).

- [ ] **PLAN-012 · 4.3** — Implement read-only investigation with tool budgets/errors; evaluate bad database host, pool exhaustion, resource pressure and insufficient evidence for diagnosis, abstention, unnecessary calls and time/cost; test injection and secret/project boundaries. Prerequisites: PLAN-011.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No investigation tool loop, incident corpus evaluation or AI boundary tests.

- [ ] **PLAN-013 · 4.4** — Generate a reviewable configuration/deployment diff bound to target and revision, with supporting evidence and a rollback plan; do not execute it at this stage. Prerequisites: PLAN-012.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No evidence-linked AI diff/approval-plan flow.

- [ ] **PLAN-014 · 4.5** — Apply only an exactly approved diff through authorized Platform API calls; reject stale approvals, audit execution and verify observed health/metrics. Demonstrate regression, investigation, approval and recovery in test resources. Prerequisites: PLAN-013; DEV-007-T02; OPS-001-T01.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No revision-bound AI approvals, execution integration or observed-recovery demonstration (F-12).

- [ ] **PLAN-015 · 4 (after 4.5)** — Demonstrate development assistance grounded in authorized docs, ADRs, contracts and repository context: template selection, change impact or review with runtime evidence; retain source references and project/secret boundaries. Prerequisites: PLAN-014.

  **Task evidence (B-2026-09-26):** Source absent; local acceptance unverified. No development assistant using project docs/contracts/repository/runtime context.


## Shared implementation baseline

B-2026-09-26 describes an administrator-operated hybrid foundation, not an accepted Phase 1 release. [Compose](../../compose.yaml), [cluster configuration](../../scripts/cluster_config.py) and [bootstrap](../../scripts/up.sh) place shared services outside a one-server/two-agent k3d cluster; PostgreSQL has a persistent volume. All local components share the same host failure domain. Current target-host installation, capacity, TLS, failure recovery and actual notification receipt are unverified. Watchdog SMTP, deployment automation and schema import were additions since the preceding assessment; the platform API/workload implementation was unchanged at that baseline.

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

[CI](../../.github/workflows/validate.yaml) defines syntax/configuration/unit checks, including PHP freshness and local SMTP transport tests, but no live smoke, isolation, or recovery acceptance. Its definition is not evidence that a particular remote run passed.

The [smoke script](../../scripts/smoke.py) checks unauthenticated rejection, repeat provisioning, rollout, and HTTP routing. Its sample is `http-echo`; it does not write/read PostgreSQL through the application. The [isolation script](../../scripts/isolation.py) checks database connectivity, denied foreign database access, DNS, and selected blocked network connections after a convergence delay. Neither script was run during the baseline assessment, and neither tests scoped end-user permissions, durable interrupted operations, or restore.

The [watchdog integration script](../../operations/watchdog/scripts/test-watchdog.py) exercises temporary PHP/MariaDB services, but substitutes successful mail handoff and disables the optional HTTPS probe. It also checks schema import, repeated import preservation, and credential-safe authentication failures. It cannot establish real notification receipt. It was inspected, not executed; the separate PHP freshness and SMTP fixture tests above were executed.


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
| F-07 / UC-05 | PLAN-002/004; additional data-store labs remain unscheduled |
| F-08 | PLAN-001/002/004, OPS-005-T01/02 |
| F-09 / UC-03 | PLAN-008 |
| F-10 | PLAN-006/007/009 |
| F-11 / UC-06 | PLAN-010/011/012 |
| F-12 / UC-06 | PLAN-013/014 |
| N-01 | PLAN-001/002/004 |
| N-02 | DEV-007-T01/02, PLAN-003, DEV-011-T01, OPS-008-T02 |
| N-03 | OPS-004-T01 and authorization checks on every later data surface |
| N-04 | DEV-003-T01/02 and redaction checks on every later data surface |
| N-05 | OPS-006-T01/02; reassess the documented recovery procedure whenever persisted state grows |
| N-06 | OPS-007-T01/02 |
| N-07 | OPS-003-T01/02, OPS-005-T01/02 |
| N-08 | OPS-001-T01/02 and audit checks on every later mutation/access change |

The phase task index remains authoritative for scheduling, including deferred component-specific extensions. Requirement or story closure needs all applicable criteria, not just the foundation tasks listed here.
