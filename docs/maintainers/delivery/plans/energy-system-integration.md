# Energy-System Integration Priority Plan

Status: priority Phase 3 delivery slice. Adopted October 10, 2026.

This plan makes Developer Platform support for the
[AI-assisted energy-system configuration scenario](https://github.com/eseidinger/energy-system-configuration)
the next delivery priority. It implements the Developer Platform work packages
`DP-01` through `DP-03` and supplies the platform evidence needed by integration
gates 4 and 5. ODIP publication behavior, the energy adapter, VEF simulation and
optimization, and the AI user journey remain owned by their respective projects.

Execution tracking is in the
[phase task index](../backlog.md#phase-task-index). Complete this slice before
starting new Phase 3 breadth beyond work already in progress.

## Outcome

Run ODIP and VEF as separately owned applications on the Developer Platform so
that VEF can retrieve an immutable ODIP publication over an authenticated,
encrypted, least-privilege connection. Both applications retain state across
restart and recovery, expose meaningful health and diagnostics, and produce
enough deployment and correlation evidence for the cross-project acceptance
suite.

The first release uses public HTTPS for VEF-to-ODIP connectivity:

```text
Consultant -> VEF public HTTPS
                  |
                  | ODIP audience token + HTTPS
                  v
             ODIP public HTTPS
```

Private cross-project routing is not part of this slice. Activating it requires
a separate capability contract and acceptance suite; Kubernetes service reachability
or an ad hoc NetworkPolicy change is not a platform contract.

## Priority order

### 1. Freeze platform decisions and deployment profiles

Record the following before implementation-dependent acceptance begins:

- Public HTTPS is the default ODIP route. Record DNS, TLS termination, token
  audience, claims/scopes, credential provisioning owner, and rotation process.
- Define the `odip` project as an API plus worker and optional adapter component,
  with one retained PostgreSQL database. Define the `vef` project as a public
  API/UI plus an optional worker, with its own retained PostgreSQL database.
- Require public OCI images pinned by digest for the first release. Private image
  support is a separate platform capability.
- Keep ODIP artifacts, VEF verified imports, and immutable optimization runs in
  PostgreSQL. If an implementation requires a filesystem, PVC, or object store,
  stop and add a durable storage capability before deployment.
- Resolve whether the integration contract's encrypted-channel rule includes
  application-to-PostgreSQL traffic. If it does, enable verified PostgreSQL TLS
  and deliver the trust material through a managed binding; otherwise record the
  narrower scope in the accepted integration contract.
- Set artifact sizes, application resource bounds, run timeout, retention, and
  customer-data classification within the platform's advertised limits.

The deployment declarations must use `platform.example/v1alpha2`, custom HTTP
readiness paths for public APIs, bounded resources, and explicit outbound access.
A worker that needs semantic readiness exposes a private health port rather than
being treated as healthy merely because its process is running.

### 2. Deliver hosted-application identity

Implement [PLAN-009](../backlog.md#additional-phase-tasks) before the deployed
connection gate. The capability must support:

- a VEF browser client for consultant authentication;
- a distinct confidential VEF service identity for the ODIP audience;
- controlled redirect URIs and audiences;
- delivery of the service credential to the VEF project without exposing it in
  desired state, logs, audit exports, or ordinary reads;
- rotation, revocation, retirement cleanup, and recovery coverage; and
- proof that platform roles and deployment credentials grant no ODIP or VEF
  business authority.

An explicitly accepted operator-managed client-provisioning runbook may unblock
the first demonstration, but it does not complete PLAN-009 or establish a
self-service platform capability.

### 3. Correct component monitoring and correlation

Monitoring discovery must understand the component application schema. For each
declared public component, publish the actual
`<component>-<project>.<apps-domain>` target and component health profile. Do not
publish a legacy project hostname for a component application or publish a
blackbox target for an application without public exposure.

Add legacy and `v1alpha2` regression tests, project/component labels, and a
deployed ODIP/VEF probe check. Define the safe correlation fields shared by the
applications and platform evidence: dataset ID, dataset version, optimization
run ID, deployment revision, and platform operation ID. Bearer tokens, customer
details, and secret values must not appear in logs or explanations.

Use the authorized project log, component status, resource, and operation APIs as
the minimum demonstration evidence. Select and implement central Kubernetes
workload-log retention if the kubelet's best-effort window cannot meet the
retention decision from step 1.

### 4. Prove the authenticated deployed connection

Create an automated acceptance playbook that:

1. deploys digest-pinned ODIP API/worker and VEF components as separate projects;
2. waits for application readiness and verifies their separate databases;
3. provisions and activates the VEF-to-ODIP credential through the platform
   secret mechanism;
4. applies the ODIP public route and component-scoped VEF DNS/443 egress rule;
5. verifies DNS, certificate validation, token audience and dataset-scoped access;
6. proves denial for an unauthenticated identity, an unauthorized identity, a
   prohibited dataset, and an unrelated egress destination; and
7. captures image digests, application revisions, routes, component status,
   resource bounds, and correlation-safe logs.

DNS-based egress is resolved to fixed IP rules at deployment time. The playbook
must show the approved resolved addresses and prove that a changed destination
requires an explicit reapply rather than silently widening access.

### 5. Prove durability and recovery

Extend the cross-project acceptance workflow to restart ODIP and VEF, reproduce a
completed result from the retained publication/import/run records, and verify
that an older result remains pinned after a corrected publication is introduced.

Take a verified platform backup, restore it through the supported isolated
recovery workflow, reapply both project declarations, reactivate required
application identity material, and reproduce the reference result. Record the
snapshot, image and contract versions, recovery duration, restored database
checks, route/TLS result, and any manual identity steps. Byte-level backup
readback or a generic SQL marker does not satisfy this application-level check.

## Exit criteria

This priority slice is complete only when:

- `DP-01`: ODIP and VEF are ready after restart with isolated retained databases,
  immutable images, managed secrets, readiness, and bounded resources;
- `DP-02`: the authenticated VEF-to-ODIP request succeeds over verified HTTPS and
  an unrelated destination is denied;
- `DP-03`: application identity and the selected public routing boundary are
  documented as explicit capabilities with isolation tests;
- component-aware monitoring observes the actual ODIP and VEF public endpoints;
- the Gate 4 platform playbook and Gate 5 cross-project suite pass in one
  environment; and
- recovery reproduces the recorded reference result from restored state.

Do not claim completion from local application tests, three independently healthy
deployments, source inspection, or generic platform recovery evidence.

## Follow-on work, not a blocker

- Private cross-project service bindings and paired namespace policies.
- Component-specific configuration and secret bindings.
- Private registry credentials.
- PVC or object-storage resources.
- General OpenTelemetry/trace storage beyond the accepted correlation evidence.

Foundations:
[Application declaration](../../../developers/application-spec.md),
[application contract](../../../architecture/application-contract.md),
[security boundary](../../../architecture/security-and-authorization.md),
[observability](../../../architecture/observability.md), and
[backup and recovery](../../../operators/backup-and-recovery.md).
