# Phase 2A – Multi-service Application with a Scheduled Component (historical)

Status: **accepted on October 4, 2026.** The deployed `test-platform-components.yml` acceptance suite passed on node-01 (EV-38). Database-row preservation, backup-inventory, and representative-capacity checks are owner-accepted deferrals; they remain required before making production-like recovery or capacity claims. Covers [F-13](../../../product/requirements.md) and [UC-07](../../../product/use-cases.md).

Execution tracking: [DEV-001-T01 through DEV-001-T03, DEV-006-T02, and DEV-011-T02](../backlog.md#phase-task-index).

## Goal

Deploy one application as a set of named, cooperating components. At least two components run as long-lived services and one component is started by a recurring schedule. The components share the project boundary, can use stable internal service names, and can be updated and observed independently.

This gate is delivered on the selected Kubernetes provider. The public contract remains free of Kubernetes-specific client fields. Docker workload parity is not part of current acceptance and is available only as an optional Phase 5 expansion.

## Initial contract

The successor to `v1alpha1` introduces `spec.components` rather than changing the existing singular `spec.application` object in place. Existing single-component revisions migrate losslessly to one named `service` component. The migration must preserve revision history and provide a rollback path.

Each component has a stable name and declares:

- `type`: `service` for a long-running component or `scheduled` for a one-shot component;
- its own OCI image, command/arguments, and resource requests and limits;
- for a `service`, zero or more named internal HTTP ports and a replica count;
- for a `scheduled` component, a five-field cron schedule, `UTC` timezone in the initial profile, and `Forbid` concurrency so a slow run is not overlapped by a later trigger.

The initial profile makes the application's existing project-managed configuration, secrets, and database binding available consistently to all components. Per-component configuration/secret assignment remains a separately tracked extension.

Only long-running services receive stable internal DNS names. Scheduled components may call those names while a run is active. A scheduled component does not receive a public endpoint and must exit after each run; the platform scheduler starts it again at the next matching time. Invalid schedules, unsupported timezones, public exposure on a scheduled component, name collisions, and cyclic or missing references are rejected before infrastructure changes.

Illustrative target shape (the exact schema is finalized by DEV-001-T01):

```yaml
apiVersion: platform.example/v1alpha2
kind: Application
metadata:
  name: order-processing
  project: order-processing
  environment: default
spec:
  components:
    - name: api
      type: service
      runtime:
        type: container
        image: registry.example.com/order-api:1.0.0
      ports:
        - name: http
          protocol: http
          port: 8080
      replicas: 1
    - name: processor
      type: service
      runtime:
        type: container
        image: registry.example.com/order-processor:1.0.0
      ports:
        - name: http
          protocol: http
          port: 8090
      replicas: 1
    - name: reconciliation
      type: scheduled
      runtime:
        type: container
        image: registry.example.com/order-reconciliation:1.0.0
        command: ["/app/reconcile"]
      schedule:
        cron: "0 * * * *"
        timezone: UTC
        concurrencyPolicy: Forbid
```

Kubernetes object names and `Service`/`CronJob` fields are not part of the public contract.

## Status and operations

Application status reports each long-running service's desired/ready replicas, active image, and failure reason. For each scheduled component it reports the schedule, next eligible run, active run if any, and the last run's start time, completion time, result, and redacted failure reason. Logs and audit events carry the project, application, component, revision, and scheduled-run identity.

Changing one component creates an application revision but reconciles only the changed component and any application binding that actually changed. It must not restart unchanged services or cause an immediate run of an unchanged scheduled component. Schedule or image changes affect subsequent runs; an already active run is allowed to finish unless an explicitly authorized stop operation is added later.

Deletion and rollback operate on the entire declared component set. Removal previews list all long-running and scheduled Kubernetes resources. Persistent data remains governed by its own retention decision and is not removed as a side effect.

## Ordered implementation work

1. Finalize and publish the successor schema, compatibility rules, capability flag, status model, and single-component migration/rollback design. Measure the representative three-component profile against the lab reserve.
2. Implement named long-running services, stable project-internal discovery, per-component reconciliation, status, logs, and failure attribution.
3. Implement scheduled components with validation, non-overlap, run history, logs, and audit correlation.
4. Run the acceptance scenario below on the existing Kubernetes environment and record evidence in DEV-001. Phase 2B began under the documented owner exception, but this acceptance remains required before entering Phase 2C.

All new endpoints and persisted records reuse project authorization, audit, redaction, revision, backup, and recovery boundaries. The implementation must extend backup coverage before the gate closes.

## Acceptance scenario

Deploy the example profile, or an equivalent application, with two long-running services and one scheduled component.

Acceptance requires evidence that:

1. both long-running services become ready and communicate through documented stable internal names;
2. the scheduled component does not run continuously, starts from its declared schedule, reaches an internal service, and completes successfully;
3. a deliberately long run does not overlap its next trigger;
4. component and run status/logs identify their source, and a failed scheduled run has a useful redacted reason;
5. changing only one service leaves the other service unchanged, and changing only the scheduled component does not restart either service;
6. an invalid cron expression and an unsupported scheduled capability are rejected before side effects;
7. migration of an existing single-component application preserves its revision history, configuration, secrets, database data, and rollback path; and
8. retirement preview and backup inventory include every service and scheduled component without implicitly deleting persistent data.

## Out of scope for this gate

- event-triggered jobs, ad-hoc jobs, and workflow/DAG orchestration;
- second-level schedules, non-UTC timezones, overlapping scheduled runs, and catch-up of every missed run;
- automatic retries beyond the provider's explicitly documented initial policy;
- autoscaling, multi-cluster placement, and high availability; and
- Docker execution of scheduled components, which is optional Phase 5 portability work.
