# Playbook component matrix

Status: current inventory and dependency classification. Last reviewed October
18, 2026.

The October 18 documentation review syntax-checked all 33 current playbooks with
Ansible 2.21.5 and ran 23 offline Ansible tests. This includes the two
human-access playbooks added to the table below. These checks executed no remote
platform tasks.

This page classifies the deployment, administration, acceptance, recovery, and
failure-drill playbooks by the minimum components they need. It distinguishes a
playbook's executable assertions from optional notification evidence that an
operator must confirm separately.

The October 9, 2026 baseline of 30 playbooks passed
`ansible-playbook --syntax-check` with their corresponding example inventories.
The inventory now also includes the hosted-access wrapper below; it was not part
of that historical check. Syntax validation does not execute tasks, connect to
remote hosts, or establish live acceptance. The directly invoked hosted-access
harness has separately recorded live core evidence in EV-45; that is not
evidence of executing the Ansible wrapper or closing the full gate. The added
wrapper separately passed syntax checking with `ansible/inventory.example.yml`
during the October 11 documentation consistency update; no playbook tasks were
executed.

Inventory files, variable files, and
`operations/watchdog/tests/compose.watchdog.yaml` are configuration or test
fixtures, not Ansible playbooks, and are not counted as playbooks.

## Component definitions

- **Code:** **P**
  - **Component:** Platform and infrastructure
  - **Included responsibility:** Docker, Kubernetes/k3d, PostgreSQL, Keycloak,
    Caddy, Prometheus, Grafana, and the baseline local Alertmanager service
- **Code:** **A**
  - **Component:** Alertmanager delivery
  - **Included responsibility:** Optional authenticated SMTP configuration and
    external alert delivery
- **Code:** **B**
  - **Component:** Backup
  - **Included responsibility:** Optional restic/S3 configuration, scheduled
    encrypted backups, retention, and recovery tooling
- **Code:** **H**
  - **Component:** Heartbeat
  - **Included responsibility:** Optional readiness sender installed on the
    platform host
- **Code:** **W**
  - **Component:** Watchdog
  - **Included responsibility:** Optional external PHP/MySQL receiver for
    heartbeat and backup signals

“Alertmanager optional” means configured external notification delivery. The
Alertmanager container and its default local-only receiver are part of the
baseline monitoring stack in **P**.

## Platform and infrastructure

These playbooks require only **P** for their executable assertions.

- **Type:** Deployment
  - **Playbook:** [`deploy.yml`](../../../ansible/deploy.yml)
  - **Purpose:** Install or update the single-host platform and record its
    non-secret installation inventory
- **Type:** Credential administration
  - **Playbook:**
    [`bootstrap-platform-test-runner.yml`](../../../ansible/operations/bootstrap-platform-test-runner.yml)
  - **Purpose:** Create the reusable automation identity from authorized human
    bootstrap inputs
- **Type:** Credential administration
  - **Playbook:**
    [`revoke-platform-test-runner.yml`](../../../ansible/operations/revoke-platform-test-runner.yml)
  - **Purpose:** Revoke the selected automation identity and complete provider
    cleanup
- **Type:** Project administration
  - **Playbook:**
    [`retire-platform-project.yml`](../../../ansible/operations/retire-platform-project.yml)
  - **Purpose:** Preview and execute explicit project retirement with
    retained-data evidence
- **Type:** General acceptance
  - **Playbook:**
    [`test-platform.yml`](../../../ansible/tests/platform/test-platform.yml)
  - **Purpose:** Exercise the core authorized platform lifecycle with
    short-lived personas
- **Type:** Application contract
  - **Playbook:**
    [`test-platform-components.yml`](../../../ansible/tests/platform/test-platform-components.yml)
  - **Purpose:** Exercise multi-service, scheduled-component, migration, status,
    update, rollback, and retirement behavior
- **Type:** Hosted application access
  - **Playbook:**
    [`test-platform-hosted-access.yml`](../../../ansible/tests/platform/test-platform-hosted-access.yml)
  - **Purpose:** Plan or run the neutral identity/HTTPS/isolation/persistence
    suite; no platform deployment, explicit live confirmation, and a private
    target-host human administrator session
- **Type:** Human store access installation
  - **Playbook:**
    [`install-human-database-access.yml`](../../../ansible/operations/install-human-database-access.yml)
  - **Purpose:** Install the separately configured restricted SSH bastion for
    private store leases
- **Type:** Human store acceptance
  - **Playbook:**
    [`test-platform-human-database-access.yml`](../../../ansible/tests/platform/test-platform-human-database-access.yml)
  - **Purpose:** Offline plan or opt-in human named-resource tunnel/SQL checks;
    current named-resource and historical implicit-database evidence are
    distinct
- **Type:** CI credentials
  - **Playbook:**
    [`test-platform.yml`](../../../ansible/tests/platform/test-platform.yml)
  - **Purpose:** Exercise project-scoped machine deployment, denial, revocation,
    and cleanup
- **Type:** CI credentials
  - **Playbook:**
    [`verify-platform-test-runner-expiry.yml`](../../../ansible/tests/platform/verify-platform-test-runner-expiry.yml)
  - **Purpose:** Verify the dedicated runner before or after its configured
    expiry
- **Type:** Capacity
  - **Playbook:**
    [`test-platform-capacity-admission.yml`](../../../ansible/tests/platform/test-platform-capacity-admission.yml)
  - **Purpose:** Temporarily enable and exercise request-based reserved-capacity
    admission
- **Type:** Connectivity policy
  - **Playbook:**
    [`test-platform-egress-policy.yml`](../../../ansible/tests/platform/test-platform-egress-policy.yml)
  - **Purpose:** Exercise deny-by-default and explicitly approved component
    egress
- **Type:** Failure signals
  - **Playbook:**
    [`test-platform-failure-signals.yml`](../../../ansible/tests/platform/test-platform-failure-signals.yml)
  - **Purpose:** Exercise application, ingress, proxy, and Prometheus
    failure/recovery state
- **Type:** Identity failure
  - **Playbook:**
    [`test-platform-identity-provider-outage.yml`](../../../ansible/tests/platform/test-platform-identity-provider-outage.yml)
  - **Purpose:** Prove local revocation fails closed during a controlled
    Keycloak outage
- **Type:** Database failure
  - **Playbook:**
    [`test-platform-postgres-outage.yml`](../../../ansible/tests/platform/test-platform-postgres-outage.yml)
  - **Purpose:** Exercise managed PostgreSQL failure, recovery requests, and
    restored readiness
- **Type:** Data-aware rollback
  - **Playbook:**
    [`test-platform-rollback-data.yml`](../../../ansible/tests/platform/test-platform-rollback-data.yml)
  - **Purpose:** Named PostgreSQL resource/binding, bound-workload visit
    persistence, and current-secret checks; live rerun pending

`deploy.yml` refuses to overlap active backup or availability drills. That is a
safety interlock, not a requirement to install **B**, **H**, or **W**.

The hosted-access wrapper defaults to an offline `plan`. A live `run`
additionally requires a prepared acceptance virtual environment, a public
digest-pinned fixture, wildcard DNS/HTTPS, operator-approved component egress
and a private renewable human platform-administrator session on the target. It
does not use the basic suite's test-runner credential file and does not install
those inputs. `--timed` tests actual machine-token expiry. Optional global
recovery reconciliation requires a separately reserved lab with no other project
records, including retired records; it is not a backup restore. The core suite
requires only **P**. Real backup/restore needs separate **B** tooling and
acceptance. See the
[harness procedure](access-and-authorization.md#neutral-hosted-application-acceptance-harness)
and
[EV-45 run record](access-and-authorization.md#executed-hosted-access-core-acceptance-october-11-2026).

`test-platform-failure-signals.yml` verifies local Prometheus alert state and
platform recovery, but does not prove external notification receipt. Complete
notification evidence adds:

- **A** for application and ingress FIRING/RESOLVED email delivery;
- **H + W** for independent detection while Prometheus or the complete Docker
  boundary is unavailable.

## Alertmanager delivery

- **Playbook:**
  [`deploy-alertmanager.yml`](../../../operations/alertmanager/ansible/deploy-alertmanager.yml)
  - **Required components:** **P + A**
  - **Purpose:** Install protected SMTP configuration and recreate the baseline
    Alertmanager service

There is no dedicated Alertmanager test playbook. Live delivery acceptance uses
the documented synthetic alert exercise and requires operator confirmation of
both FIRING and RESOLVED messages. The platform failure-signal playbook does not
prove SMTP delivery by itself.

## Backup and recovery

- **Playbook:**
  [`setup-backup.yml`](../../../operations/backup/ansible/setup-backup.yml)
  - **Required components:** **B**, normally on the **P** host
  - **Purpose and boundary:** Install restic and configure or verify encrypted
    S3 repository access; does not require W
- **Playbook:**
  [`deploy-backup.yml`](../../../operations/backup/ansible/deploy-backup.yml)
  - **Required components:** **P + B + W**
  - **Purpose and boundary:** Deploy the scheduled backup, recovery, and
    notification units; requires the watchdog `backup.php` contract and
    dedicated token
- **Playbook:**
  [`prepare-recovery-test.yml`](../../../operations/backup/ansible/prepare-recovery-test.yml)
  - **Required components:** **P + B**
  - **Purpose and boundary:** Seed an application database marker and create a
    newer verified source backup
- **Playbook:**
  [`restore-recovery.yml`](../../../operations/backup/ansible/restore-recovery.yml)
  - **Required components:** **P + B** on a fresh recovery VM
  - **Purpose and boundary:** Retrieve an explicitly selected verified snapshot,
    restore the platform, and run project checks; does not require A, H, or a
    live W
- **Playbook:**
  [`check-recovery-failure-modes.yml`](../../../operations/backup/ansible/check-recovery-failure-modes.yml)
  - **Required components:** **B** and a disposable recovery VM
  - **Purpose and boundary:** Prove unavailable storage, incorrect password, and
    missing-password failures without repository writes
- **Playbook:**
  [`drill-backup-failure.yml`](../../../operations/backup/ansible/drill-backup-failure.yml)
  - **Required components:** **P + B + W**
  - **Purpose and boundary:** Inject a capture failure, require watchdog signal
    acceptance, and perform a verified recovery backup
- **Playbook:**
  [`drill-backup-freshness.yml`](../../../operations/backup/ansible/drill-backup-freshness.yml)
  - **Required components:** **P + B + W**
  - **Purpose and boundary:** Shared real-time stalled/overdue implementation
    using watchdog thresholds
- **Playbook:**
  [`drill-backup-stalled.yml`](../../../operations/backup/ansible/drill-backup-stalled.yml)
  - **Required components:** **P + B + W**
  - **Purpose and boundary:** Select stalled mode for the shared freshness drill
- **Playbook:**
  [`drill-backup-overdue.yml`](../../../operations/backup/ansible/drill-backup-overdue.yml)
  - **Required components:** **P + B + W**
  - **Purpose and boundary:** Select overdue mode for the shared freshness drill
- **Playbook:**
  [`check-backup-drill.yml`](../../../operations/backup/ansible/check-backup-drill.yml)
  - **Required components:** **P + B + W**
  - **Purpose and boundary:** Collect and assess the asynchronous
    freshness-drill report

Backup repository setup and isolated recovery can operate without the watchdog.
Scheduled backup deployment and every notification-oriented backup drill require
**W**. They do not require **H** because backup uses a distinct watchdog
endpoint and token.

The recovery playbooks use the `recovery` inventory group and a deliberately
fresh VM. `restore-recovery.yml` refuses an existing platform installation or
production heartbeat/backup timer, rather than overwriting one.

## Heartbeat and availability

- **Playbook:**
  [`deploy-heartbeat.yml`](../../../operations/heartbeat/ansible/deploy-heartbeat.yml)
  - **Required components:** **P + H + W**
  - **Purpose and boundary:** Install the sender and timer; requires the
    external watchdog heartbeat URL and token
- **Playbook:**
  [`drill-cluster-availability.yml`](../../../operations/heartbeat/ansible/drill-cluster-availability.yml)
  - **Required components:** **P**; add **A** for email evidence
  - **Purpose and boundary:** Stop the k3d server, require the Kubernetes target
    and Prometheus alert to change state, and restore the cluster
- **Playbook:**
  [`drill-docker-availability.yml`](../../../operations/heartbeat/ansible/drill-docker-availability.yml)
  - **Required components:** **P + H + W**
  - **Purpose and boundary:** Stop Docker, rebuild the platform state, and
    require the heartbeat timer to recover; W supplies actual DOWN/UP
    observation
- **Playbook:**
  [`drill-platform-availability.yml`](../../../operations/heartbeat/ansible/drill-platform-availability.yml)
  - **Required components:** Depends on selected mode
  - **Purpose and boundary:** Shared implementation: cluster mode is **P**;
    Docker mode is **P + H + W**

Treat the cluster and Docker wrappers as the operator entry points. The shared
playbook defaults to cluster mode and exists primarily to implement both
wrappers.

Cluster mode proves the local Prometheus alert transition. Confirming
notification email additionally requires **A**. Docker mode removes Prometheus
with the rest of the local stack, so independent outage evidence comes through
**H + W**.

## External watchdog

- **Playbook:**
  [`deploy-watchdog.yml`](../../../operations/watchdog/ansible/deploy-watchdog.yml)
  - **Required components:** **W**
  - **Purpose:** Deploy the external PHP/MySQL watchdog through SCP and
    optionally manage its cron entry

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
   `ansible/tests/platform/test-platform*.yml` suite: **P**.
1. Configure external alert delivery with `deploy-alertmanager.yml`: **P + A**.
1. Deploy the independent receiver with `deploy-watchdog.yml`: **W**.
1. Deploy heartbeat and run the Docker-boundary drill: **P + H + W**.
1. Configure repository access with `setup-backup.yml`: **P + B**.
1. Deploy scheduled backup reporting and drills: **P + B + W**.
1. For an explicitly selected recovery, prepare a source backup on **P + B**,
   then restore into a fresh **P + B** recovery environment. Generic
   marker/project checks retain legacy assumptions; use the current store
   quarantine and fresh binding procedure rather than claiming automatic
   store-backed application recovery.

Run destructive or availability-affecting drills only with their explicit
acknowledgement variables, in the documented protected window, and after
checking that no backup, deployment, or other drill overlaps them.
