# Requirements

Status: consolidated requirements; prioritization and evidence are drafts.
Required rows describe target acceptance, while explicitly optional rows require
a separate scope decision.

## Delivery terminology

**MVP (minimum viable product) means Phase 1**, including all three ordered
gates: 1A operational protection, 1B accountable access, and 1C durable
single-application lifecycle. It is not a separate stage before the numbered
phases. See the
[Phase 1 gates](../maintainers/delivery/history/phase-1-foundation.md#ordered-work-packages-and-acceptance-gates).

The delivery phase identifies when the listed acceptance evidence is first
required. Requirements continue to apply in later phases and to new
endpoints/providers. “Confirmed requirement” describes decision status, not a
delivery phase. N-01 keeps the public contract free of backend-specific fields;
a second-provider proof is an optional Phase 6 expansion rather than a current
delivery gate.

Phase 1 acceptance must pass before advancing to Phase 2. Later hardening or
extensions do not postpone the Phase 1 minimum:

- **Requirement:** F-04 / N-02
  - **Phase 1 (MVP) minimum:** Persist desired state and traceable operations;
    observe readiness and resume interrupted provisioning without duplicates or
    data loss
  - **Phase 2 extension:** Harden concurrency and drift recovery; add
    retained-revision recovery
- **Requirement:** F-06
  - **Phase 1 (MVP) minimum:** Diagnose a failed rollout through authorized
    basic logs, metrics, health and revision context
  - **Phase 2 extension:** Add full log search/follow and retention, resource
    comparisons and capacity views
- **Requirement:** F-08
  - **Phase 1 (MVP) minimum:** Validate the supported single-image profile and
    reject unsupported capabilities before side effects
  - **Phase 2 extension:** Publish the selected environment capability profile
    and extend policy enforcement

Phase 3 adds developer experience and access extensions; Phase 4 adds platform
and opted-in application telemetry with Grafana dashboards; Phase 5 adds AI
assistance and controlled actions. The full delivery backlog spans these phases
and includes explicitly deferred work, so completing the MVP does not mean
completing every backlog story.

- **ID:** F-01
  - **Requirement:** Manage projects and environments with stable identity and
    ownership
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Create/read/update and cross-project access tests
- **ID:** F-02
  - **Requirement:** Declaratively deploy an OCI image, HTTP endpoint,
    configuration, and health check
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** UC-01 without manually creating backend artifacts
- **ID:** F-03
  - **Requirement:** Provision a PostgreSQL database and dedicated workload
    role; bind a secret
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Write/read data; no secrets in API status or logs
- **ID:** F-04
  - **Requirement:** Expose desired and observed state and asynchronous
    operations
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Restart a worker during provisioning and retain a
    traceable state
- **ID:** F-05
  - **Requirement:** Support updates, restarts, and controlled removal
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Repeatable operations; persistent data is retained
- **ID:** F-06
  - **Requirement:** Associate logs, basic metrics, health, and deployment
    revisions
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Locate a failed rollout through the API and
    monitoring
- **ID:** F-07
  - **Requirement:** Optionally support a shared contract across Kubernetes and
    Docker providers
  - **Delivery phase:** Optional Phase 6
  - **Acceptance evidence:** If activated, run the same spec on both providers
    with no backend fields in the core contract
- **ID:** F-08
  - **Requirement:** Check environment capabilities and reject unsupported
    requirements
  - **Delivery phase:** Phase 1 (MVP) core; Phase 2 extension
  - **Acceptance evidence:** Reject autoscaling on an unsuitable environment
    without side effects
- **ID:** F-09
  - **Requirement:** Authorize and audit separate human database access
  - **Delivery phase:** Phase 3
  - **Acceptance evidence:** Tunnel/database login distinct from application
    login; revocation test
- **ID:** F-10
  - **Requirement:** Offer a portal, templates, and OIDC integration for hosted
    applications
  - **Delivery phase:** Phase 3
  - **Acceptance evidence:** Template-to-healthy-application flow with separate
    platform/application permissions
- **ID:** F-11
  - **Requirement:** Generate AI diagnoses through read-only platform tools
  - **Delivery phase:** Phase 5
  - **Acceptance evidence:** Incident diagnosis with evidence; deny access to
    another project's context
- **ID:** F-12
  - **Requirement:** Execute AI changes through the Platform API using an
    approved plan
  - **Delivery phase:** Phase 5
  - **Acceptance evidence:** No mutation without valid approval for the exact
    revision and target
- **ID:** F-13
  - **Requirement:** Deploy one application as multiple cooperating services,
    including a component triggered by a cron schedule
  - **Delivery phase:** Phase 2A
  - **Acceptance evidence:** UC-07: two long-running services communicate
    internally; one scheduled component runs without overlap; component updates,
    status, logs, and failures are independently attributable
- **ID:** F-14
  - **Requirement:** Create scoped, expiring, rotatable, and revocable machine
    credentials for CI application deployments
  - **Delivery phase:** Phase 2B
  - **Acceptance evidence:** UC-08: a non-interactive pipeline deploys and
    observes one scoped application; revocation denies the next request;
    cross-project and privileged actions remain denied; the secret is returned
    once and never exposed by later platform surfaces
- **ID:** F-15
  - **Requirement:** Bootstrap an empty project and run the platform acceptance
    suite through an expiring, revocable automation identity
  - **Delivery phase:** Phase 2B
  - **Acceptance evidence:** UC-09: a human administrator creates one
    test-runner client; later suites create disposable projects and role
    personas without a reusable human token, test grants and platform features,
    and clean up their identities
- **ID:** N-01
  - **Requirement:** Keep the public Platform API technology-independent
  - **Delivery phase:** All phases; second-provider proof optional in Phase 6
  - **Acceptance evidence:** Contract review; F-07 only if Phase 6 is activated
- **ID:** N-02
  - **Requirement:** Make provisioning idempotent and resumable after partial
    failures
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Database creation succeeds, deployment fails, retry
    creates no duplicates
- **ID:** N-03
  - **Requirement:** Enforce project/environment boundaries server-side
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Negative tests for resources, logs, secrets, jobs,
    and database access
- **ID:** N-04
  - **Requirement:** Reference, protect, and redact secrets
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Spec/audit/log inspection; rotation followed by
    reconnection
- **ID:** N-05
  - **Requirement:** Make infrastructure and recovery reproducible
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Encrypted off-host capture, verified readback,
    independently recoverable credentials, and a documented replacement-host
    procedure; isolated recovery exercises are deferred by ADR-016
- **ID:** N-06
  - **Requirement:** Keep monitoring available during workload-cluster failure;
    detect host failure externally
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** k3d failure and separate host/heartbeat failure
    tests
- **ID:** N-07
  - **Requirement:** Keep single-host operation within available resources
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Load measurement including log growth, database,
    and reserve; no swap/disk exhaustion
- **ID:** N-08
  - **Requirement:** Audit changes, role assignments, and provider operations
  - **Delivery phase:** Phase 1 (MVP)
  - **Acceptance evidence:** Correlate actor, target, revision, timestamp,
    result, and operation ID
- **ID:** N-09
  - **Requirement:** Correlate platform operations with bounded traces and
    provision useful operator dashboards
  - **Delivery phase:** Phase 4
  - **Acceptance evidence:** Follow a sampled request through an asynchronous
    operation without sensitive span data; dashboards diagnose a deployment
    failure and telemetry gap while denying unscoped project access
- **ID:** N-10
  - **Requirement:** Collect opted-in hosted-application metrics through a
    private, bounded platform path and provide shared HTTP and Micrometer JVM
    dashboards
  - **Delivery phase:** Phase 4
  - **Acceptance evidence:** Declared Spring Boot, Quarkus, and FastAPI fixtures
    yield scoped request/error/latency signals in one
    application/component-selectable dashboard; JVM fixtures additionally expose
    reviewed memory, GC, CPU, thread, class and buffer signals in a Micrometer
    dashboard; undeclared or cross-project targets and unscoped reads are
    denied; missing metrics are not shown as healthy
- **ID:** N-11
  - **Requirement:** Correlate opted-in hosted-application spans with platform
    traces through a private, authenticated collector
  - **Delivery phase:** Phase 4
  - **Acceptance evidence:** Sampled Spring Boot, Quarkus and FastAPI flows
    cross the platform boundary and permitted component calls; forged origins
    and foreign reads fail; collection outages do not interrupt application
    requests

F-03's original implicit project database has been replaced by independent named
resources and explicit component bindings. Current declarations do not create a
project database automatically. Store provider scope and remaining acceptance
are recorded in the [data-store roadmap](data-store-roadmap.md).

## Delivery acceptance

The [delivery backlog](../maintainers/delivery/backlog.md) retains detailed
DEV/OPS acceptance criteria. The
[development plan crosswalk](../maintainers/delivery/README.md#backlog-delivery-commitments)
assigns them to phases, including security-event notifications and project
retirement as explicit extensions of these broad requirements. F-13 and F-14
have accepted Phase 2 evidence under the recorded lab limitations; the roadmap
and backlog identify outstanding checks. Single-image or interactive-user
evidence does not close their multi-service, scheduled-run, or CI-credential
criteria.

## Boundaries and open operational targets

The hybrid installation is a single-host lab with a shared failure domain.
Multiple Kubernetes nodes in Docker do not provide host-level high availability.
Namespaces and Docker networks alone do not guarantee strong tenant isolation.

Availability, p95 provisioning time, API latency and concurrent application
count remain to be defined. The owner selected a 24-hour RPO and four-hour RTO,
twelve-hour backups and 14 daily / 8 weekly / 6 monthly retention points; these
are targets, not measured guarantees.
[ADR-020](../architecture/decisions/ADR-020-generic-hosted-application-integration.md)
accepts a seven-day centralized workload-log target and Public, Internal,
Confidential, and Restricted classification rules for the Phase 3 integration
profile. Minimized Kubernetes operational-envelope collection and authorized
retained-log reads are implemented; ordinary free-text logs remain kubelet best
effort. Seven elapsed days and compactor deletion remain unverified. The lab
initial response target is 24 hours with one responder. See
[backup policy evidence](../maintainers/delivery/backlog.md#current-backup-and-recovery-progress)
and [alert ownership](../operators/monitoring.md#alert-process). Measure
representative baselines before promising SLAs.

Multi-cluster operation, automatic multi-node HA, a broad data-service catalog,
complex autoscaling, and unattended AI remediation are outside Phase 1 (MVP).
See the [development plan](../maintainers/delivery/README.md) for phases and
dependencies.
