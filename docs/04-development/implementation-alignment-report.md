# Implementation alignment report

Assessment date: September 26, 2026. Source revision: `bbd509dd4bf3e3dbcb2094cfdaf92a35ab3100f8`.

This is a dated source assessment, not the current delivery schedule. The backlog and phase gates were subsequently refined; use the [active plan](development-plan.md#backlog-delivery-commitments) for sequencing and the [delivery backlog](delivery-backlog.md) for acceptance tasks. The source findings and recorded test results below have not been rerun by documentation-only amendments. The former archive is available in Git history.

## Assessment

The repository implements an **administrator-operated hybrid lab foundation**. It substantially matches the selected infrastructure topology, but does **not yet satisfy the Phase 1 acceptance gate** or the documented self-service MVP. The largest gaps are scoped authorization, the application/environment domain model, persistent asynchronous operations, observed deployment health, controlled removal, and demonstrated recovery and alert delivery.

The documentation index, development plan, deployment guide, software architecture, ADR-003, and Phase 1 now cite the inspected implementation and distinguish local verification from live acceptance. The presence of implementation and test scripts does not establish a working public installation or completion of the target requirements.

The target documents generally label future interfaces and decisions appropriately. Missing proposed features below are planning gaps, not claims that the existing prototype violates an already implemented API contract. The accepted technology-independent API principle is only partially reflected in the prototype.

Since the September 25 assessment, watchdog deployment automation, authenticated SMTP delivery, a CLI schema importer, and additional tests have been added, and watchdog sources have been consolidated under `watchdog/`. The platform API and workload provisioning implementation are unchanged from the previous source baseline. These additions improve operational tooling but do not close a requirement or phase acceptance gate.

## Scope and evidence

Rechecked changes since source revision `25c80743dc23991baeb5444444bbd79571bd93c3`, including watchdog source, deployment playbooks, tests, CI, and guide updates; retained the unchanged implementation assessment below. The assessment covers the product requirements, use cases, architecture and diagrams, ADRs 001–008 and the subsequent edge decision ADR-009, development phases, operational drafts, root/component guides, source, infrastructure configuration, deployment scripts, watchdog, and tests. Archived material provides historical context; the current `docs/` requirements and phases are the assessment baseline. In particular, the archived multi-component backlog must not override the current single-image MVP scope.

Evidence levels used here:

- **Implemented in source:** a concrete code/configuration path exists; deployment is not implied.
- **Partial:** a relevant path exists but does not meet the complete requirement.
- **Absent:** no implementation of the requested capability was found.
- **Unverified operationally:** an installed system or acceptance exercise is needed to establish the outcome.

No deployment, live workload mutation, failure injection, or restore was performed. Existing runtime files and historical observations were not treated as fresh operational evidence. External release availability and dependency currency were outside this repository-alignment review.

## What already aligns

| Area | Evidence and alignment | Limitation |
| --- | --- | --- |
| Hybrid foundation | [Compose](../../compose.yaml), [cluster configuration](../../scripts/cluster_config.py), and [bootstrap](../../scripts/up.sh) place shared services outside a one-server/two-agent k3d cluster. PostgreSQL uses a persistent Docker volume. | One host remains one failure domain; target-host installation and capacity were not verified. |
| Basic provisioning | [API](../../platform/app/main.py) provisions a database/login and applies namespace, Secret, Deployment, Service, Ingress, quota, limits, and network policy. | One project maps to one workload/database; no environment or separate application identity. |
| Retry and retention foundations | Database/role existence checks, server-side Kubernetes apply, deterministic credentials, and a PostgreSQL advisory lock support repeated PUT requests. Provisioning does not delete databases. | Manual retry only; no persisted operation steps, revision checks, recovery worker, or deletion policy model. |
| Workload hardening | [Manifests](../../platform/app/manifests.py) configure non-root execution, restricted Pod Security, dropped capabilities, read-only roots, no API token, quotas, and NetworkPolicy. | Trusted workloads only; the root guide records a policy-convergence egress window. No end-user authorization follows from namespace isolation. |
| Edge routing | [Caddy](../../infrastructure/proxy/Caddyfile) fronts the API and k3d ingress, with project registration gating on-demand certificates. | [ADR-009](../03-decisions/ADR-009-edge-and-cluster-ingress.md) accepts Caddy at the edge and Traefik inside k3d. Public DNS/ACME, outage behavior, and certificate-state recovery remain unverified. |
| Monitoring placement | [Monitoring stack](../../infrastructure/monitoring/compose.yaml) places Prometheus, Grafana, Loki, Alloy, and Alertmanager outside k3d. | Placement aligns; full application telemetry and delivered alerts do not yet follow. |
| Independent watchdog | [Host sender](../../watchdog/scripts/heartbeat.py), [systemd timer](../../watchdog/systemd/platform-heartbeat.timer), and [PHP watchdog](../../watchdog/README.md) implement readiness-gated HTTPS heartbeats, expiry detection, and state-change email attempts through PHP mail or authenticated SMTP with verified TLS. | Deployment playbooks and a CLI schema importer now exist; installation, scheduler reliability, public probes, and actual email receipt remain unverified. |
| Reproducible setup | [Ansible](../../ansible/deploy.yml), bootstrap, configuration generation, checksum-verified tool installation, and separate [watchdog/heartbeat playbooks](../../watchdog/ansible/README.md) are concrete automation. | Platform Ansible ends with process health, not the complete application/database acceptance flow. Watchdog hosting, database setup/import, HTTPS, and mail configuration require separate steps; firewall and backups remain separate. |

## Requirements coverage

Statuses assess the entire requirement in [Requirements](../01-product/requirements.md), rather than the presence of an adjacent component. No requirement is marked accepted solely from configuration or static tests.

| ID | Status | Implementation versus remaining acceptance |
| --- | --- | --- |
| F-01 | Partial | Project name and latest spec are persisted and list/update routes exist. Environments, ownership, memberships, and cross-project user access tests are absent. |
| F-02 | Partial | Image, port, generated HTTP route, and TCP probes exist. User configuration, declared application-level health, and ApplicationSpec submission are absent. |
| F-03 | Partial | Dedicated database/login and Kubernetes Secret binding exist. The runtime login owns the database; separate migration identity and application write/read acceptance are missing. |
| F-04 | Partial | Latest desired spec and `provisioning/applied/failed` are persisted. Observed state, revisions, asynchronous jobs, operation IDs, and interruption recovery are absent. |
| F-05 | Partial | PUT updates/reapplies the workload and preserves database data. Restart, controlled removal, deletion plans, and recorded retained resources are absent. |
| F-06 | Partial | Infrastructure metrics, Docker logs, and Kubernetes TCP probes exist. API-scoped workload logs/metrics, revision correlation, and failed-rollout status are absent. |
| F-07 | Absent | No direct Docker workload provider or shared provider contract. Docker hosting the foundation is not a second application compute provider. |
| F-08 | Absent | Basic name/image/port validation exists, but no environment capabilities or rejection of unsupported declared features before side effects. |
| F-09 | Absent | No separate human database identity, scoped authorization, tunnel workflow, grant audit, or revocation policy. |
| F-10 | Absent | No portal, application OIDC integration, or complete template-to-healthy-application flow. The sample project JSON is only a provisioning example. |
| F-11 | Absent | No AI diagnostics or authorized read-only platform tools. |
| F-12 | Absent | No AI plan, revision-bound approval, or controlled execution integration. |
| N-01 | Partial | Input uses name/image/port rather than raw Kubernetes manifests, but output exposes `namespace`, implementation directly invokes Kubernetes, and portability has not been demonstrated. |
| N-02 | Partial | Existence checks and apply support manual retry; one global advisory lock serializes provisioning. No resumable job, persisted steps, automatic recovery, or partial-failure acceptance test. |
| N-03 | Partial | Database CONNECT restrictions, network policy, and quotas provide infrastructure boundaries. The shared admin token accesses every project; no project/environment permission checks exist. |
| N-04 | Partial | Generated database credentials use Secrets, normal responses omit them, errors are generic, and cluster configuration enables secret encryption. User secret references, rotation/reconnection workflow, and comprehensive redaction tests are absent. |
| N-05 | Partial | Bootstrap, Ansible, and local SQL backups exist. Encrypted external backup automation, complete recovery bundle, and isolated restore evidence are missing. |
| N-06 | Partial | Central monitoring is outside k3d; host and external watchdog code exists. Watchdog/heartbeat deployment playbooks and TLS SMTP transport exist. Separate cluster/host failure exercises and notification receipt are not established. |
| N-07 | Partial | Container/cluster memory limits, workload quotas, and some retention settings exist. Representative load, total capacity, disk/log growth, and reserve measurements are absent. |
| N-08 | Absent | No durable audit model recording actor, scope, action, revision, operation, result, or denied access. Latest project status and generic error logging are insufficient. |

## Significant design gaps

### Application contract and lifecycle

The [draft ApplicationSpec](../02-architecture/application-spec.md) is not accepted by the current API. The actual [Project model](../../platform/app/main.py) contains only `name`, `image`, and `port`. It has no schema version, environment, owner, optional resources, configuration, secret references, endpoint exposure, access grants, or configurable scaling/resources/health. Every project receives PostgreSQL and a public ingress. Bindings use `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`, rather than the draft's configurable `DB_*` prefix.

The model does not configure rejection of extra fields. Under the Pydantic default, additional fields on an otherwise valid project request are ignored, contrary to the draft's explicit unknown-field rejection rule. This is particularly relevant before adding capability declarations: unsupported requests must not appear successfully applied while their requested settings are discarded.

PUT executes SQL and Kubernetes calls synchronously and returns `200` after applying resources. It does not implement the proposed `202` plus operation ID flow. The stored `applied` status deliberately does not mean ready, and no observer updates it after a failed rollout or dependency failure. An abrupt process termination can leave `provisioning` indefinitely until a caller repeats the PUT.

The global advisory lock avoids simultaneous provisioning inside cooperating API processes, but does not provide expected-revision conflict detection. Updates overwrite the only stored spec; stale clients can replace newer intent. There is no revision history, rollback selection, persistent idempotency key, per-step recovery, or drift reconciliation. Tag-to-digest resolution is also absent.

### Identity, credentials, and boundaries

The API uses one shared administrator bearer token. This accurately matches the warning in the [platform guide](../../platform/README.md), but does not satisfy the documented self-service permission model. No OIDC provider, individual principal, role binding, environment scope, or audit attribution exists. Basic authorization is a Phase 1 prerequisite even though the richer IAM design remains proposed.

The provisioner connects as PostgreSQL `postgres` and uses a cluster-wide Kubernetes role. Workloads have a separate non-superuser PostgreSQL role, but that role owns the database. Runtime, migration, and human responsibilities are not separated as proposed in ADR-003. Changing `DATABASE_KEY` changes the derived Secret password, while `provision_database` only creates missing roles and does not change an existing role password: key changes therefore require the coordinated manual rotation already documented in the root guide.

All Compose services and k3d share the `developer-platform` Docker network, rather than the target's separate edge/platform/persistence networks. PostgreSQL uses an explicit IP for pod connectivity, appropriately avoiding the assumption that Compose DNS names resolve in Kubernetes. PostgreSQL TLS is not configured in the repository. Generated NetworkPolicies and revoked database PUBLIC access are useful safeguards, but do not establish hostile-tenant isolation or complete target network segmentation.

### Observability and alerting

[Prometheus](../../infrastructure/monitoring/prometheus.yaml) scrapes itself, node-exporter, and kube-state-metrics. There is no configured PostgreSQL exporter, application request/error/latency instrumentation, container resource-usage scrape, backup-age signal, or job telemetry. Grafana has provisioned data sources but no provisioned dashboards.

[Alloy](../../infrastructure/monitoring/config.alloy) tails host Docker JSON logs. There is no explicit collection of Kubernetes application logs inside k3d, nor project/environment/revision attribution. The API has no authorized logs or metrics endpoints; exposing shared dashboards would not fill that gap.

[Alert rules](../../infrastructure/monitoring/alerts.yaml) cover scrape-target failure, low disk, and unavailable workload replicas. [Alertmanager](../../infrastructure/monitoring/alertmanager.yaml) uses a `local-only` receiver without a notification integration. Rule evaluation therefore does not establish operational alert delivery.

The host heartbeat checks API dependency readiness and Prometheus readiness, and stops sending when either fails. It relies on the external watchdog for notification; it is not a separate local alert-delivery service and does not check the Alertmanager delivery path, Grafana, Loki, backups, or an end-to-end application. The external watchdog supports authenticated POST, receipt-time freshness, throttling, an optional fixed HTTPS HEAD probe, notification deduplication, and retry after failed mail handoff. The [mail transport](../../watchdog/src/mail.php) supports PHP `mail()` and authenticated SMTP using STARTTLS or implicit TLS with certificate verification; failed handoff leaves notification state retryable. The [cron entry point](../../watchdog/src/cron.php) reports failure stages without raw exception details. Expiring maintenance windows and an explicit token-rotation workflow are absent. A stale cron makes the status page unavailable, but no independent notifier monitors watchdog scheduler/hosting failure.

### Watchdog deployment and setup

The [heartbeat playbook](../../watchdog/ansible/deploy-heartbeat.yml) installs Python/CA certificates, the sender, a private systemd environment file, and the service/timer on the platform host. It places the sender where the dynamic service user can read it and enables the timer, but does not verify live heartbeat delivery.

The [external watchdog playbook](../../watchdog/ansible/deploy-watchdog.yml) uploads an explicit release file list over SSH/SCP, optionally replaces private configuration, and optionally installs a minute-by-minute cron entry. It preserves SSH host-key checking and suppresses credential-bearing task output. Its check mode validates local inputs only; it does not inspect the remote installation. Database/user creation, the public document root, HTTPS, PHP extensions, and mail settings remain operator prerequisites. The [CLI schema importer](../../watchdog/src/import-schema.php) is uploaded but must be run separately; the integration script includes repeat-import preservation and credential-safe authentication-error checks.

Neither playbook was deployed during this assessment. Their presence and successful syntax checks establish automation in source, not a functioning external failure detector.

### Backup and recovery

[backup.sh](../../scripts/backup.sh) writes a private, compressed local `pg_dumpall` through a temporary file before publication. This includes databases and role state, but a same-host dump is not the external recovery capability in N-05.

No backup scheduler, encrypted upload, remote retention, key/configuration backup automation, backup-age alert, or executable isolated restore exercise exists. The current [backup and recovery guide](../05-operations/backup-recovery.md) carries forward the archived SQL restore/reapply procedure, with isolated-host prerequisites, private import logs, explicit error review, catalog reapplication, and data-verification steps. These commands are reviewed against source and syntax-checked, but have not been executed as a recovery exercise. Recovery must preserve `DATABASE_KEY` and compatible credentials, restore platform metadata and project databases, and reapply workloads after cluster recreation. These steps require a demonstrated data write/read result, not just successful dump creation.

## Documentation discrepancies

| Priority | Finding | Required documentation action |
| --- | --- | --- |
| Resolved | [Documentation index](../README.md), [development plan](development-plan.md), and [deployment](../05-operations/deployment.md) now describe the inspected source baseline and link this report. | Keep source/local-check evidence separate from live acceptance when recording future progress. |
| Resolved | The nine broken links in root, platform, and Ansible guides now point to current operations/architecture pages. Current deployment, runbook, monitoring, and backup/recovery pages expose source-reviewed commands, including the adapted archived SQL restore and catalog reapply procedure. | Keep command validation labels current; isolated restore and live operational acceptance remain open. |
| Resolved (documentation) | [Infrastructure](../02-architecture/infrastructure.md) and the topology diagram now describe the selected Caddy edge / Traefik ingress split and current shared Docker network; [ADR-009](../03-decisions/ADR-009-edge-and-cluster-ingress.md) records the decision. | Network segmentation remains separate implementation work. Public TLS, certificate authorization failures, cluster outages, and certificate-state recovery still require live evidence. |
| Resolved | Software architecture, ADR-003, and Phase 1 now cite inspected Python/database-secret behavior and this report. | Retain proposed design status and unverified live acceptance labels until evidence changes. |
| Resolved | The runbook now uses stored project status, dependency/Kubernetes inspection, and repeat PUT for repair. Deployment, monitoring, and recovery pages distinguish current commands from future worker/revision/audit procedures. | Validate the current commands in a recorded installation; extend target procedures only as the corresponding capabilities become available. |
| Resolved | Current baseline documents distinguish implemented source, passing local checks, and unverified live acceptance. | Record future live results with environment, date, revision, and outcome. |

ADRs 002 and 006 fit the current direction: retain the hybrid topology and inspect/evolve Python before considering a rewrite. ADR-001 remains a valid accepted principle with substantial implementation work outstanding. ADRs 003–005 have partial foundations, but their detailed decisions remain proposed; code presence does not accept an ADR. ADR-007's single-image starting profile fits the workload shape, while the combined UI/API template remains absent. ADR-008 remains future product work. ADR-009 accepts the existing edge/ingress split without claiming operational acceptance or completion of network segmentation.

## Phase and use-case assessment

| Phase | Assessment | Gate still open |
| --- | --- | --- |
| 1 — Foundation | Substantial infrastructure and admin provisioning implemented; incomplete. | Authorized application/database write-read flow, partial-failure recovery, correct update/removal status, isolated restore, and verified independent alerts. |
| 2 — Platform API | Early ingredients only: persisted spec, validation, manual reapply, SQL lock. | Versioned portable contract, capabilities, durable operations/revisions, provider interfaces, direct Docker provider, concurrency/failure tests. |
| 3 — Developer experience | Not implemented as a user workflow. | Portal/CLI, usable template, scoped identity, human database access, and application OIDC. Shell/curl examples are not a domain CLI. |
| 4 — AI | Not implemented. | Authorized context, deployment history, read-only tools, evaluations, and later controlled writes. |

UC-01 is partially supported for an administrator, without ApplicationSpec, progress tracking, observed health, or an application database write/read demonstration. UC-02 permits image changes but lacks revision history and rollback. UC-03 and UC-04 have no corresponding access/removal workflow. UC-05 lacks the second provider and reproducible comparison harness. UC-06 has no AI implementation.

## Verification performed

| Check | Result | What it establishes |
| --- | --- | --- |
| `python3 -m unittest discover -s tests -v` | Passed: 3 tests. | Name validation, generated namespace/network structure, and selected workload hardening/quota settings. |
| `python3 -m compileall -q platform scripts watchdog/scripts` | Passed. | Python syntax compilation; not dependency import or service execution. |
| `bash -n scripts/up.sh scripts/down.sh scripts/backup.sh` | Passed. | Shell syntax. |
| `docker compose config --quiet` | Passed. | Compose configuration resolves using this checkout's configuration; no services started. |
| Local Markdown link scan after guidance update | Passed: no broken relative file targets across 38 root/component/current-docs/watchdog Markdown files; the nine earlier broken occurrences are fixed. | Relative file-target existence, excluding fenced code, external URLs, and fragment validation. |
| Current operations code examples | Passed: `bash -n` for 22 shell blocks; embedded catalog-reapply Python parsed successfully. | Syntax only. No startup, shutdown, SQL backup/import, catalog replay, or alert exercise was executed. |
| `php watchdog/tests/watchdog.php` | Passed. | Heartbeat and scheduler freshness boundary checks. |
| `php -d curl.cainfo=<unused temporary certificate path> -d sendmail_path=/bin/true watchdog/tests/watchdog-mail.php` | Passed: seven SMTP scenarios plus validation/legacy transport checks. | Local fixture verifies STARTTLS/implicit TLS, authentication/recipient/data failures, missing TLS, certificate mismatch, invalid settings, and simulated PHP mail handoff. No real email is sent. Expected failure cases emit diagnostic logs. |
| `php -l` on tracked watchdog PHP source and tests | Passed: 10 files. | PHP syntax; excludes private local configuration and does not establish database integration. |
| `ansible-playbook -i watchdog/ansible/inventory.<name>.example.yml watchdog/ansible/deploy-<name>.yml --syntax-check` for `watchdog` and `heartbeat` | Both passed. | Playbook syntax only; no remote connection, installation, or delivery verification. |

[CI](../../.github/workflows/validate.yaml) defines syntax/configuration/unit checks, including PHP freshness and local SMTP transport tests, but no live smoke, isolation, or recovery acceptance. Its definition is not evidence that a particular remote run passed.

The [smoke script](../../scripts/smoke.py) checks unauthenticated rejection, repeat provisioning, rollout, and HTTP routing. Its sample is `http-echo`; it does not write/read PostgreSQL through the application. The [isolation script](../../scripts/isolation.py) checks database connectivity, denied foreign database access, DNS, and selected blocked network connections after a convergence delay. Neither script was run during this review, and neither tests scoped end-user permissions, durable interrupted operations, or restore.

The [watchdog integration script](../../watchdog/scripts/test-watchdog.py) exercises temporary PHP/MariaDB services, but substitutes successful mail handoff and disables the optional HTTPS probe. It also checks schema import, repeated import preservation, and credential-safe authentication failures. It cannot establish real notification receipt. It was inspected, not executed; the separate PHP freshness and SMTP fixture tests above were executed.

## Recommended sequence at assessment time

The subsequent plan supersedes this ordering with Phase 1A protection, 1B accountable access and 1C lifecycle gates, followed by Phase 2 retained-backlog completion and portability. The historical recommendations below explain the assessment; they are not a competing execution plan.

1. **Validate the current operational guidance.** Workspace-absence statements and broken links are corrected; current commands and the archived restore sequence are now discoverable with validation labels. Execute the documented flow on an isolated installation and record outcomes. The proxy choice is resolved by ADR-009; prioritize defining and testing the remaining network boundaries independently. Preserve other proposed ADR statuses until explicitly decided.
2. **Complete the Phase 1 domain and security foundation.** Introduce project/environment/application identity, scoped authorization and audit, strict input validation, and explicit supported profile constraints. Preserve the existing hardened workload and PostgreSQL path.
3. **Make provisioning observable and resumable.** Persist revisions and operations, detect stale writes, reconcile observed readiness, and implement controlled removal with retained-data inventory. Test interruption after database creation and retry without resource duplication or data loss.
4. **Close operational acceptance.** Configure real alert delivery, collect application/database signals, automate encrypted off-host backups, and demonstrate an isolated restore. Record cluster-failure and host-heartbeat outage/recovery results separately.
5. **Record a complete vertical slice.** Use an application that writes and reads PostgreSQL, exercise updates/failure/removal and denied foreign-project access, and attach environment, revision, timing, and outcomes to the development plan. Measure capacity before setting operational targets.
6. **Then advance Phase 2–4 gates.** Stabilize ApplicationSpec/provider contracts, add direct Docker compute and parity tests, then build developer experience and AI on the authorized lifecycle. The review establishes no need for a language rewrite to close the immediate gaps.

The current implementation is a useful base for Phase 1. Completing and proving that phase is the next milestone; describing it as either an empty documentation workspace or a completed self-service MVP would be inaccurate.
