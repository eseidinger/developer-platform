# ADR-012 – Synchronous Administrator Provisioning Baseline

Recorded: September 27, 2026. Status: **Implemented baseline; owner acceptance of this record not recorded**. This documents existing code, not approval to replace the target contract in ADR-001.

## Context

The current lab has one FastAPI process outside k3d. Projects need a repeatable path to SQL and Kubernetes resources without installing infrastructure on each request. The richer project/environment/application model and durable worker have not been implemented.

## Implemented choice

A shared bearer token authorizes all project reads, PUTs and retirement acknowledgements. Project name is both application identity and scope. PUT stores the latest `name/image/port/probe_profile` spec and `provisioning` status, publishes discovery, ensures a SQL database/login, applies fixed Kubernetes resources, then records `applied` and returns 200. The database is mandatory.

A session-level PostgreSQL advisory lock (`731904`) serializes all provisioning, retirement and discovery publication across API processes. SQL uses autocommit; PostgreSQL and Kubernetes changes do not form one transaction. Kubernetes server-side apply uses field manager `developer-platform`. Retrying PUT repairs resources on request; no workload reconciler or persisted steps resume automatically.

The API holds PostgreSQL administrator credentials and a long-lived Kubernetes ServiceAccount token. The ClusterRole permits get/list/create/patch/update for selected kinds across the cluster; it does not limit resource names to project namespaces. The API has no Docker socket. Its only Kubernetes delete permission is for namespaces, used by confirmed project retirement; a ValidatingAdmissionPolicy (`provisioner-namespace-delete`) rejects any namespace deletion by the provisioner unless the namespace is named `project-*` and labelled `platform.example/managed=true`. These are trusted infrastructure credentials, not tenant credentials.

## Alternatives and consequences

A durable job/revision model offers resumable work and concurrency checks but requires the state model and worker still planned in Phase 1C. Per-project locking could permit parallel provisioning, but the current global lock also serializes shared SQL and discovery effects.

The baseline is simple to operate, but one slow request delays every project and discovery refresh. A later PUT can overwrite an earlier spec because there is no expected revision. Process termination can leave `provisioning`; `applied` does not establish rollout readiness. At the original assessment, unknown fields were ignored by the model; PLAN-001 now rejects them before catalog/provider side effects. Images are not resolved to digests. There are no scoped users, operation IDs or durable actor audit events in the original baseline.

## Evidence and evolution

Source: [API](../../../platform/app/main.py), [manifests](../../../platform/app/manifests.py), [controller RBAC](../../../infrastructure/kubernetes/controller.yaml). Local fixture tests do not prove interrupted live provisioning or authorization between users. PLAN-001/002/003, DEV-006/007 and OPS-001/004 retain their outstanding criteria in the [backlog](../../maintainers/delivery/backlog.md).

Revisit when enabling self-service, introducing multiple applications/environments, or replacing manual retry with durable reconciliation. Preserve catalog/data/credential compatibility through versioned changes. [ADR-006](ADR-006-python-quarkus-evolution.md) now selects the FastAPI application as the current architecture; any deployable service extraction is optional Phase 5 work with separate contract, migration, parity, and rollback gates.
