# Use Cases and User Stories

Status: consolidated use cases; acceptance conditions are specification drafts.

## UC-01 – Deploy an application with PostgreSQL

As a developer, I want to declare a web application with PostgreSQL for a project so that I can get started without manually administering Docker, Kubernetes, or a database.

Prerequisites: an authorized user, an existing environment, an accessible registry, available capacity, and a supported image.

1. Select a project and environment, or create them within the authorized scope.
2. Validate and submit an [ApplicationSpec](../02-architecture/application-spec.md).
3. Receive an operation ID and track progress.
4. The platform provisions the database/role, secret binding, workload, and route.
5. Check the URL, observed revision, and health status; write and read data through the application.

Acceptance: resubmitting the same revision does not create additional resources. A failed workload does not delete an already provisioned database. Missing capabilities are reported clearly before any changes.

## UC-02 – Update, observe, and roll back

As an operator, I want to deploy a new image/configuration revision and evaluate its state.

The platform displays desired and observed revisions, operations, logs, and metrics. A failed rollout is visible as a failure or degradation. Rollback uses a known revision; incompatible database migrations mean rollback is not automatically safe. See [Deployment](../05-operations/deployment.md).

## UC-03 – Human database access

As an authorized developer, I want to inspect project data with a database client. The platform authorizes access to the specific database, uses a separate human identity, and provides a controlled tunnel. Application credentials are not exposed by default.

Acceptance: a user from another project receives neither connection details nor access. Revoking a grant terminates access according to the defined session policy. Short-lived credentials are a later extension. See [ADR-003](../03-decisions/ADR-003-postgresql-provisioning.md).

## UC-04 – Remove resources

As a project administrator, I want to clean up an environment. The platform presents a deletion plan, distinguishes ephemeral workloads from persistent data, and records retained resources.

Acceptance: databases are retained by default; permanently deleting data requires a separate, explicitly authorized step. A retry resumes the recorded deletion operation.

## UC-05 – Compare technical alternatives

As an architect, I want to run the same workload on two compute providers or against two data stores. Input data, versions, configuration, measurement duration, and evaluation method are fixed. Evaluate latency, throughput, resource consumption, and operational effort. A lab result supports an ADR; it does not automatically enable a new default service.

## UC-06 – Support development and incident analysis with AI

As a developer, I want to understand why an application has become slower since its last deployment. The assistant correlates the deployment diff, logs, metrics, and dependencies, identifies observations, and formulates a testable hypothesis.

A proposed change includes a concrete diff. Only after approval and renewed authorization does the Platform API execute it. The same boundaries apply to a later development assistant using documentation, ADRs, and API contracts as context. See [Phase 4](../04-development/phase-4-ai-operations.md).
