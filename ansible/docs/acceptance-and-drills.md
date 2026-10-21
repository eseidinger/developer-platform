# Acceptance and operational drills

Back to the [Ansible directory guide](../README.md). Run commands from the
repository root.

## Hosted access and human database access

Hosted-application acceptance has a separate
[`test-platform-hosted-access.yml`](../tests/platform/test-platform-hosted-access.yml)
wrapper.
It defaults to an offline plan, does not deploy the platform, and requires
explicit API-origin confirmation for live runs. Prepare the runner environment,
public digest-pinned neutral fixture, and protected operator session on the
target using the
[acceptance harness procedure](../../docs/operators/validation/access-and-authorization.md#neutral-hosted-application-acceptance-harness).
This suite needs a renewable human platform-administrator session on the target,
not the basic suite's controller-side test-runner JSON. Runner/fixture-only
updates can follow the
[non-deploying update procedure](../../docs/operators/validation/access-and-authorization.md#update-the-runner-without-redeploying-platform-services);
they do not require the Compose outage described below. EV-45 records a directly
invoked harness run, not execution of this Ansible wrapper or full gate closure.

Human PostgreSQL access has a separate
[`test-platform-human-database-access.yml`](../tests/platform/test-platform-human-database-access.yml)
acceptance wrapper. Its default `plan` is offline. A live `run` requires an
explicit API-origin confirmation, a renewable human platform-administrator
session, a verified bastion host key, and a public digest-pinned neutral
fixture. It creates two uniquely named fixture projects, tests the tunnel and
SQL authorization/revocation, then retains the projects for explicit review and
retirement. See the
[human database acceptance procedure](../../docs/operators/validation/access-and-authorization.md#human-postgresql-access-acceptance-playbook).

## Component acceptance

`test-platform-components.yml` is the Phase 2A acceptance suite. Run it with the
normal platform inventory and the protected test-runner output; it creates and
retires its own disposable project, so it needs no human token. It checks legacy
migration, two stable internal Services, a scheduled internal connectivity
probe, non-overlap, invalid-cron rejection, an isolated component update,
revision history, and component retirement scope. It deliberately does not
trigger or inspect backup storage: backup evidence remains a separate
operational track. It also checks the authorized component-log search and
polling-cursor contract; That endpoint's Kubernetes log retention remains best
effort. PLAN-017 adds a separate authorized retained-log endpoint for minimized
centralized operational events, configured for seven days. Its deployed and
elapsed-retention checks are separate from this component suite.

## Scoped operational drills

The following Phase 2C playbooks create and retire their own disposable
projects. They consume the protected test-runner file; no reusable human or
project token is accepted:

```bash
# Named-store rollback check; supply a published digest-pinned web/PostgreSQL image.
ansible-playbook -i ansible/inventory.yml \
  ansible/tests/platform/test-platform-rollback-data.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_rollback_drill_host=platform \
  -e platform_rollback_drill_image=REGISTRY/web-postgres@sha256:DIGEST

# Temporarily enable and exercise reserved-capacity admission, then restore policy.
ansible-playbook -i ansible/inventory.yml \
  ansible/tests/platform/test-platform-capacity-admission.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_capacity_drill=true \
  -e platform_capacity_drill_acknowledgement=I_ACCEPT_CAPACITY_DRILL

# Uses a temporary, exact 1.1.1.1/32:853 allow-list and restores the prior
# Platform API environment during cleanup.
ansible-playbook -i ansible/inventory.yml \
  ansible/tests/platform/test-platform-egress-policy.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_egress_drill=true \
  -e platform_egress_drill_acknowledgement=I_ACCEPT_EGRESS_DRILL

# Optional: override all three defaults with a reachable listener you control.
# This replacement is also temporary and is restored during cleanup.
ansible-playbook -i ansible/inventory.yml \
  ansible/tests/platform/test-platform-egress-policy.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_egress_drill=true \
  -e platform_egress_drill_acknowledgement=I_ACCEPT_EGRESS_DRILL \
  -e platform_egress_target_host=198.51.100.10 \
  -e platform_egress_target_cidr=198.51.100.10/32 \
  -e platform_egress_target_port=8443

# Controlled shared Keycloak outage; the always block restores the service.
ansible-playbook -i ansible/inventory.yml \
  ansible/tests/platform/test-platform-identity-provider-outage.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_identity_drill_host=platform \
  -e platform_allow_identity_outage_drill=true \
  -e platform_identity_outage_acknowledgement=I_ACCEPT_IDENTITY_OUTAGE

# Disposable application plus shared proxy/Prometheus failure and recovery signals.
ansible-playbook -i ansible/inventory.yml \
  ansible/tests/platform/test-platform-failure-signals.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_failure_drill_host=platform \
  -e platform_allow_failure_signal_drill=true \
  -e platform_failure_drill_acknowledgement=I_ACCEPT_FAILURE_SIGNAL_DRILL
```

The capacity drill reads the API's request-accounting snapshot, creates a
temporary restricted namespace containing one synthetic pod request, and
automatically leaves less than 100m CPU or 128Mi memory available. It proves the
fixed workload is rejected, removes the reservation, and then proves the
same-sized real workload is admitted. It preserves the exact host `.env`,
temporarily enables admission with a valid zero reserve, recreates only
`platform-api`, and restores the original `.env` and API container in an
`always` block. The reservation namespace is also always removed. Normal
deployments manage admission enablement and budgets through the
`platform_capacity_*` inventory variables above. The drill deliberately
overrides the minimum reserve only for its duration; shared-service allocations
and overhead allowances still apply. It restores the exact pre-drill environment
afterward. The egress drill defaults to
[Cloudflare's public DNS-over-TLS listener](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-tls/)
at `1.1.1.1:853`. It replaces the two Platform API allow-list variables and
temporarily disables capacity admission only for the drill, recreates only
`platform-api`, and restores the exact original `.env` and API container in its
`always` cleanup. Override all three target variables together when that
endpoint is not reachable from workload pods. Never retain or broaden a normal
production allow-list merely to pass the drill.

The PostgreSQL, Keycloak, capacity, and failure-signal drills intentionally
disrupt shared services and must not run in routine CI. The rollback-data helper
now creates a named PostgreSQL resource and checks persistence through its bound
workload; a live rerun is still required. `scripts/tests/platform/isolation.py`,
`scripts/tests/platform/data_preservation.py`, and
`scripts/tests/platform/interrupted_provisioning.py` now use run-scoped named
PostgreSQL resources and the web/PostgreSQL fixture, but await live runs. The
interruption drill pauses the shared k3d server and kills the Platform API; it
requires an otherwise idle lab and is not a routine acceptance check. The
historical passes do not validate the current binding contract. The human-access
harness now uses named resources and expiring credentials; its full live rerun
remains separate from the older implicit-database evidence. Egress alters only a
disposable workload but depends on operator policy and an external listener.
Keep these drills in an explicitly approved protected pipeline rather than
pull-request CI.

The failure-signal drill also temporarily disables capacity admission so its
disposable canary tests only application, ingress, and monitoring signals. It
restores the exact host `.env` and recreates `platform-api` in its `always`
cleanup.
