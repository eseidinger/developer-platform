# Playbook component matrix

Status: current inventory and dependency classification. Last reviewed October 9,
2026.

This page classifies the deployment, administration, acceptance, recovery, and
failure-drill playbooks by the minimum components they need. It distinguishes a
playbook's executable assertions from optional notification evidence that an
operator must confirm separately.

All 30 playbooks listed here passed `ansible-playbook --syntax-check` with their
corresponding example inventories on October 9, 2026. Syntax validation does not
execute tasks, connect to remote hosts, or establish live acceptance.

Inventory files, variable files, and
`operations/watchdog/tests/compose.watchdog.yaml` are configuration or test
fixtures, not Ansible playbooks, and are not counted in the 30.

## Component definitions

| Code | Component | Included responsibility |
|---|---|---|
| **P** | Platform and infrastructure | Docker, Kubernetes/k3d, PostgreSQL, Keycloak, Caddy, Prometheus, Grafana, and the baseline local Alertmanager service |
| **A** | Alertmanager delivery | Optional authenticated SMTP configuration and external alert delivery |
| **B** | Backup | Optional restic/S3 configuration, scheduled encrypted backups, retention, and recovery tooling |
| **H** | Heartbeat | Optional readiness sender installed on the platform host |
| **W** | Watchdog | Optional external PHP/MySQL receiver for heartbeat and backup signals |

“Alertmanager optional” means configured external notification delivery. The
Alertmanager container and its default local-only receiver are part of the
baseline monitoring stack in **P**.

## Platform and infrastructure

These playbooks require only **P** for their executable assertions.

| Type | Playbook | Purpose |
|---|---|---|
| Deployment | [`deploy.yml`](../../../ansible/deploy.yml) | Install or update the single-host platform and record its non-secret installation inventory |
| Credential administration | [`bootstrap-platform-test-runner.yml`](../../../ansible/bootstrap-platform-test-runner.yml) | Create the reusable automation identity from authorized human bootstrap inputs |
| Credential administration | [`revoke-platform-test-runner.yml`](../../../ansible/revoke-platform-test-runner.yml) | Revoke the selected automation identity and complete provider cleanup |
| Project administration | [`retire-platform-project.yml`](../../../ansible/retire-platform-project.yml) | Preview and execute explicit project retirement with retained-data evidence |
| General acceptance | [`test-platform.yml`](../../../ansible/test-platform.yml) | Exercise the core authorized platform lifecycle with short-lived personas |
| Application contract | [`test-platform-components.yml`](../../../ansible/test-platform-components.yml) | Exercise multi-service, scheduled-component, migration, status, update, rollback, and retirement behavior |
| CI credentials | [`test-platform-ci-credential.yml`](../../../ansible/test-platform-ci-credential.yml) | Exercise project-scoped machine deployment, denial, revocation, and cleanup |
| CI credentials | [`verify-platform-test-runner-expiry.yml`](../../../ansible/verify-platform-test-runner-expiry.yml) | Verify the dedicated runner before or after its configured expiry |
| Capacity | [`test-platform-capacity-admission.yml`](../../../ansible/test-platform-capacity-admission.yml) | Temporarily enable and exercise request-based reserved-capacity admission |
| Connectivity policy | [`test-platform-egress-policy.yml`](../../../ansible/test-platform-egress-policy.yml) | Exercise deny-by-default and explicitly approved component egress |
| Failure signals | [`test-platform-failure-signals.yml`](../../../ansible/test-platform-failure-signals.yml) | Exercise application, ingress, proxy, and Prometheus failure/recovery state |
| Identity failure | [`test-platform-identity-provider-outage.yml`](../../../ansible/test-platform-identity-provider-outage.yml) | Prove local revocation fails closed during a controlled Keycloak outage |
| Database failure | [`test-platform-postgres-outage.yml`](../../../ansible/test-platform-postgres-outage.yml) | Exercise managed PostgreSQL failure, recovery requests, and restored readiness |
| Data-aware rollback | [`test-platform-rollback-data.yml`](../../../ansible/test-platform-rollback-data.yml) | Prove rollback retains database data and the current secret version |

`deploy.yml` refuses to overlap active backup or availability drills. That is a
safety interlock, not a requirement to install **B**, **H**, or **W**.

`test-platform-failure-signals.yml` verifies local Prometheus alert state and
platform recovery, but does not prove external notification receipt. Complete
notification evidence adds:

- **A** for application and ingress FIRING/RESOLVED email delivery;
- **H + W** for independent detection while Prometheus or the complete Docker
  boundary is unavailable.

## Alertmanager delivery

| Playbook | Required components | Purpose |
|---|---|---|
| [`deploy-alertmanager.yml`](../../../operations/alertmanager/ansible/deploy-alertmanager.yml) | **P + A** | Install protected SMTP configuration and recreate the baseline Alertmanager service |

There is no dedicated Alertmanager test playbook. Live delivery acceptance uses
the documented synthetic alert exercise and requires operator confirmation of
both FIRING and RESOLVED messages. The platform failure-signal playbook does not
prove SMTP delivery by itself.

## Backup and recovery

| Playbook | Required components | Purpose and boundary |
|---|---|---|
| [`setup-backup.yml`](../../../operations/backup/ansible/setup-backup.yml) | **B**, normally on the **P** host | Install restic and configure or verify encrypted S3 repository access; does not require W |
| [`deploy-backup.yml`](../../../operations/backup/ansible/deploy-backup.yml) | **P + B + W** | Deploy the scheduled backup, recovery, and notification units; requires the watchdog `backup.php` contract and dedicated token |
| [`prepare-recovery-test.yml`](../../../operations/backup/ansible/prepare-recovery-test.yml) | **P + B** | Seed an application database marker and create a newer verified source backup |
| [`restore-recovery.yml`](../../../operations/backup/ansible/restore-recovery.yml) | **P + B** on a fresh recovery VM | Retrieve an explicitly selected verified snapshot, restore the platform, and run project checks; does not require A, H, or a live W |
| [`check-recovery-failure-modes.yml`](../../../operations/backup/ansible/check-recovery-failure-modes.yml) | **B** and a disposable recovery VM | Prove unavailable storage, incorrect password, and missing-password failures without repository writes |
| [`drill-backup-failure.yml`](../../../operations/backup/ansible/drill-backup-failure.yml) | **P + B + W** | Inject a capture failure, require watchdog signal acceptance, and perform a verified recovery backup |
| [`drill-backup-freshness.yml`](../../../operations/backup/ansible/drill-backup-freshness.yml) | **P + B + W** | Shared real-time stalled/overdue implementation using watchdog thresholds |
| [`drill-backup-stalled.yml`](../../../operations/backup/ansible/drill-backup-stalled.yml) | **P + B + W** | Select stalled mode for the shared freshness drill |
| [`drill-backup-overdue.yml`](../../../operations/backup/ansible/drill-backup-overdue.yml) | **P + B + W** | Select overdue mode for the shared freshness drill |
| [`check-backup-drill.yml`](../../../operations/backup/ansible/check-backup-drill.yml) | **P + B + W** | Collect and assess the asynchronous freshness-drill report |

Backup repository setup and isolated recovery can operate without the watchdog.
Scheduled backup deployment and every notification-oriented backup drill require
**W**. They do not require **H** because backup uses a distinct watchdog endpoint
and token.

The recovery playbooks use the `recovery` inventory group and a deliberately
fresh VM. `restore-recovery.yml` refuses an existing platform installation or
production heartbeat/backup timer, rather than overwriting one.

## Heartbeat and availability

| Playbook | Required components | Purpose and boundary |
|---|---|---|
| [`deploy-heartbeat.yml`](../../../operations/heartbeat/ansible/deploy-heartbeat.yml) | **P + H + W** | Install the sender and timer; requires the external watchdog heartbeat URL and token |
| [`drill-cluster-availability.yml`](../../../operations/heartbeat/ansible/drill-cluster-availability.yml) | **P**; add **A** for email evidence | Stop the k3d server, require the Kubernetes target and Prometheus alert to change state, and restore the cluster |
| [`drill-docker-availability.yml`](../../../operations/heartbeat/ansible/drill-docker-availability.yml) | **P + H + W** | Stop Docker, rebuild the platform state, and require the heartbeat timer to recover; W supplies actual DOWN/UP observation |
| [`drill-platform-availability.yml`](../../../operations/heartbeat/ansible/drill-platform-availability.yml) | Depends on selected mode | Shared implementation: cluster mode is **P**; Docker mode is **P + H + W** |

Treat the cluster and Docker wrappers as the operator entry points. The shared
playbook defaults to cluster mode and exists primarily to implement both wrappers.

Cluster mode proves the local Prometheus alert transition. Confirming notification
email additionally requires **A**. Docker mode removes Prometheus with the rest of
the local stack, so independent outage evidence comes through **H + W**.

## External watchdog

| Playbook | Required components | Purpose |
|---|---|---|
| [`deploy-watchdog.yml`](../../../operations/watchdog/ansible/deploy-watchdog.yml) | **W** | Deploy the external PHP/MySQL watchdog through SCP and optionally manage its cron entry |

The watchdog can be deployed before the platform. End-to-end usefulness requires
at least one producer:

- **P + H + W** for platform readiness signals;
- **P + B + W** for backup signals.

There is no watchdog-specific Ansible test playbook. Its automated component
tests use PHP and Python plus the Docker Compose fixture under
`operations/watchdog/tests`; those tests validate the component but are not live
cross-host acceptance.

## Recommended execution layers

1. Deploy and accept the core platform with `deploy.yml` and the
   `ansible/test-platform*.yml` suite: **P**.
2. Configure external alert delivery with `deploy-alertmanager.yml`: **P + A**.
3. Deploy the independent receiver with `deploy-watchdog.yml`: **W**.
4. Deploy heartbeat and run the Docker-boundary drill: **P + H + W**.
5. Configure repository access with `setup-backup.yml`: **P + B**.
6. Deploy scheduled backup reporting and drills: **P + B + W**.
7. Prepare a source backup on **P + B**, then restore it into a fresh **P + B**
   recovery environment.

Run destructive or availability-affecting drills only with their explicit
acknowledgement variables, in the documented protected window, and after checking
that no backup, deployment, or other drill overlaps them.
