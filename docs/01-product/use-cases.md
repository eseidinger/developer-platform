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

## UC-07 – Deploy cooperating services with a scheduled component

As a developer, I want to deploy one application containing multiple services and a scheduled component so that the services can work together internally and recurring work runs without an external scheduler.

1. Declare at least two named long-running services and one named scheduled component in one application revision.
2. Give each component its own image, command, and resource settings; apply the application's existing managed configuration, secrets, and database binding consistently.
3. Declare internal ports for the long-running services and a cron schedule for the scheduled component.
4. Submit the application and track component-specific deployment and run status.
5. Verify that services communicate through stable internal names and that the scheduled component runs at the declared time, reaches the required internal service, and exits.
6. Update one component without restarting or redeploying unchanged components.

Acceptance: an invalid schedule is rejected before side effects; a scheduled run never overlaps the next trigger under the initial concurrency policy; status and logs distinguish every service and scheduled run; a failed component does not hide the health of other components; and migration from the existing single-component shape preserves configuration, secrets, database data, revisions, and rollback. See [Phase 2A](../04-development/phase-2a-multi-service-scheduled-application.md).

## UC-08 – Deploy an application from CI

As a developer, I want a dedicated revocable machine credential for my CI pipeline so that it can deploy an application without storing my personal access token or receiving project-administration rights.

1. A project administrator creates a named deployment credential scoped to one project/environment and optionally one application, with an expiry.
2. The secret is shown once and stored in the CI system's protected secret store.
3. The pipeline exchanges the credential through the configured OIDC provider for a short-lived Platform API token.
4. It submits an application revision and follows the operation and observed deployment status to completion.
5. The administrator rotates the credential, moves the pipeline to the replacement, and revokes the predecessor.

Acceptance: the pipeline works without interactive login; audit records attribute the deployment to the machine credential; list/status/log/audit/backup surfaces do not disclose its secret or bearer tokens; cross-project, grant/credential administration, secret-value, retirement, data-deletion, and operator actions are denied; and revocation denies the next Platform API request even if an earlier OIDC token has not expired. See [Phase 2B](../04-development/phase-2b-ci-deployment-credentials.md).

## UC-09 – Run platform acceptance without a reusable human token

As a platform administrator, I want to bootstrap one revocable test-runner identity so that repeatable acceptance tests can create disposable projects and role personas, assign grants, exercise platform behavior, and clean up without storing my interactive access token.

1. A human platform administrator creates an expiring test-runner client and places its one-time returned secret in protected suite configuration.
2. A test run exchanges that reusable client secret for a short-lived bearer token and creates a uniquely named empty project before any application deployment.
3. The runner creates short-lived service-account personas for viewer, developer, project-administrator, deployment, and selected disposable platform-administrator checks.
4. Each persona obtains its own token and the suite exercises its allowed and denied actions, including cross-project denial.
5. A project deployment credential performs the first deployment, is rotated with bounded overlap, and is revoked while its access token is still otherwise valid.
6. The suite revokes temporary identities and retires its disposable projects even when a test fails.

Acceptance: only a human platform administrator can create or revoke the root test-runner credential; a test runner cannot mint another root runner; persona secrets and bearer tokens never appear in reports, logs, inventories, or audit details; expiry and revocation are checked against platform state on every request; and operational backup, watchdog, heartbeat, and Alertmanager drills remain separate. See the [Phase 2B automation plan](../04-development/phase-2b-automation-implementation-plan.md).
