# Documentation review — October 18, 2026

Status: dated source review of `390f5e92fe630926d20899a2a3eaa71485f87621`
and the documentation changes accompanying this report. This is not new deployed
acceptance evidence. Current guides describe supported source behavior; the
[delivery register](delivery/backlog.md#verification-register) retains the exact
scope of earlier local and deployed results.

## Coverage and review passes

The starting inventory contained 138 Markdown documentation files and an empty
`AGENTS.md`. The table includes current guides, indexes, proposals and dated
evidence; the report itself is an additional file.

| Area | Files | Implementation/evidence checked |
| --- | ---: | --- |
| Root, Ansible, platform, operational, monitoring and example READMEs | 20 | Compose/Dockerfiles, package manifests, bootstrap, workflows, component scripts and examples |
| Documentation and generated-reference indexes | 2 | Navigation and generated OpenAPI ownership |
| Architecture, diagrams and decisions | 33 | API, workers, grants, manifests, providers, telemetry, trust boundaries and ADR dates |
| Developer guides | 10 | Declaration models, public endpoints, CLI registry/parser, React routes and tests |
| Maintainer/delivery material | 33 | CI workflows, test boundaries, current checkpoints and historical evidence labels |
| Operator guides, runbooks and validation | 22 | Deployment/inventory filters, lifecycle scripts, backup/restore, private access and playbooks |
| Platform model | 8 | Catalog tables, request/worker flow, identity, resource binding and observation |
| Product documentation | 5 | Implemented capabilities versus requirements, roadmap and owner-recorded exceptions |
| Provider compatibility records | 5 | Release pins, fixture commands and dated local-evidence boundaries |

The passes covered inventory/status, implementation contracts, developer and
operator procedures, then links/commands and cross-document consistency.
Eleven history-directory files, thirteen plan-directory files and twenty-two
decision-directory files (including their indexes) were checked as historical or
planning material. Their original criteria and evidence remain intact. Dated
notes qualify obsolete current-implementation claims in ADRs 003, 012, 013, 019
and 021; no architectural decision or acceptance gate was approved by this review.

## Assumptions corrected

- **Persistence:** deployment no longer creates a project database or project-wide
  `database` Secret. Resources have independent lifecycles, explicit human grants
  and component bindings, expiring credentials, private relay ports and confirmed
  purge gated by verified off-host intent. PostgreSQL database ownership remains
  with the operator; data writers share resource schema authority.
- **Clients:** the React portal implements lifecycle, access, stores and AI
  workflows. Its old implicit-database panel is not mounted. The CLI has profiles,
  keyring-backed human sessions and commands mapped to 119 public operations;
  environment machine credentials remain in memory. Native lease secrets are
  revealable by their human owner until expiry, unlike one-time CI secrets.
- **Tracing/monitoring:** applications export OTLP to localhost. Only the forwarder
  reads the rotating bound token. Tempo, provisioned dashboards, private application
  metrics, kubelet CPU/memory scrapes, PostgreSQL/native-store collection and AI
  telemetry are implemented. Configured retention is not elapsed-time evidence.
- **Installation/lifecycle:** bootstrap requires `setfacl` and a mounted bounded
  Tempo filesystem. Initial identity setup precedes API bootstrap; smoke needs an
  authorized token. Compose environment changes require container recreation.
  Compose teardown does not remove the host trace filesystem or controller-owned
  Neo4j instances/volumes.
- **Recovery/evidence:** backups include identity, revisions/operations, audit,
  application Secrets, store volumes/configuration and purge intent. Restored
  access is quarantined and requires fresh store approval. Internal catalog specs
  are not public declaration exports. Latest recorded EV-67–72 outcomes are linked
  without turning outstanding purge, recovery, timer or domain checks into passes.

## Validation performed

| Check | Result |
| --- | --- |
| Local Markdown destinations and heading anchors | Passed; checker now includes `examples/` and `persistence/` |
| Current-document shell and JSON fences | 165 shell blocks passed `bash -n`; 11 complete JSON blocks parsed |
| CLI examples | 43 fenced invocations parsed/help-checked without invoking mutation callbacks |
| API and generated clients | OpenAPI export check, CLI contract generation/coverage and UI generated-type check passed; 119 mapped operations, five intentional exclusions, no missing/extra operations |
| Focused API contracts/examples | 17 declaration tests, two OpenAPI tests and three web/PostgreSQL template tests passed |
| CLI suite | 45 tests passed |
| Ansible tests and syntax | 23 offline tests and all 33 playbook syntax checks passed with Ansible 2.21.5 |
| Configuration | Compose configuration, dashboard reproducibility, bootstrap/teardown shell syntax and diff whitespace checks passed |
| Offline acceptance entry points | Hosted-access and human-database `plan` commands succeeded with synthetic inputs and `mutates: false` |
| Public external references | 38 distinct URLs checked with read-only HTTPS requests; two MySQL pages returned 403 and remain unverified. Replaced a cloud-init link redirecting to login with its current public documentation URL. The private source-roadmap conversation was excluded. |

The Ansible dependency was installed in a temporary environment. Its offline
execution tests required local IPC outside the sandbox; they used temporary
localhost playbooks and contacted no platform host. No deployment, live outage,
backup capture, model run, mail delivery, natural-expiry wait or restore was
performed. A syntax/parser check establishes command shape, not an operational
journey. Earlier fixture results in compatibility/backlog records were not rerun.

## Remaining implementation gaps and uncertainty

The following table records the October 18 review baseline. It is retained as
dated evidence; the [current disposition](#current-disposition-october-19-2026)
below accounts for subsequent source changes.

| Finding | Evidence and practical consequence |
| --- | --- |
| Legacy database diagnostics | [`main.py`](../../platform/app/src/app/main.py) still reports the implicit `project_<name>` database through `data-services`; use named-resource and binding/lease observations for current stores. |
| Legacy live helpers | [`isolation.py`](../../scripts/acceptance/isolation.py), [`data_preservation.py`](../../scripts/acceptance/data_preservation.py), [`interrupted_provisioning.py`](../../scripts/acceptance/interrupted_provisioning.py), the [rollback-data playbook](../../ansible/test-platform-rollback-data.yml) and [generic recovery helper](../../operations/backup/scripts/test-recovery.py) assume an implicit database/Secret. They need adaptation before current named-store acceptance. |
| Automatic application recovery | [`restore-recovery.py`](../../operations/backup/scripts/restore-recovery.py) handles native volumes/quarantine but refuses recovered bindings and submits internal catalog specs for selected-project replay. Public declaration reconstruction and fresh-binding replay are not an end-to-end automated workflow. |
| Interrupted AI runs | Synchronous model work can leave a durable `running` record after process interruption; history refresh does not resume or cancel that work. |
| Deployed telemetry guarantees | The recorded Tempo filesystem metric permission issue, collector failure/recovery, elapsed retention and sustained combined capacity remain open. This source review did not recheck the host. |
| Latest fixture cleanup | EV-71/72 last record seven resources awaiting verified scheduled-backup purge intent, with access revoked. This review did not observe the timer or claim data deletion. |
| Full installed acceptance | The API/CLI/UI disposable acceptance runner remains proposed. Testing requirements retain the unresolved relationship with ADR-010; fixture tests and existing live checks are not that new runner. |

These findings are documented limitations rather than implementation changes in
this review. Follow the current [store](../operators/data-stores.md),
[recovery](../operators/backup-and-recovery.md) and [testing](testing-requirements.md)
guides when planning their resolution.

Subsequent source update: the legacy `data-services` diagnostic has been replaced
with visible named-resource and binding-credential observations. Its deployed
readback and native application write/read remain unverified. The finding above
records the state at the dated review baseline.
AI history and detail reads now mark runs still `running` after ten minutes as
failed, with a safe interruption result. Process-kill and deployed readback remain
unverified; this source change does not resume model work.

Subsequent source updates replaced three legacy helpers with run-scoped named
PostgreSQL drills. Data preservation checks an application write across redeploy,
restart and rollback. Isolation checks own SQL access, cross-project and platform
database denial, peer-service isolation and public egress. Interrupted provisioning
checks recovery of a bound application's second revision and retained data; it no
longer covers the historical implicit database creation step. That outage drill
requires an otherwise idle k3d lab, disabled capacity admission and exact outage
confirmation, and attempts host restoration in all normal error paths. All three
have passing offline contract checks but still need live runs. The rollback-data
playbook now provisions a named PostgreSQL resource and binding, checks persistence
through the bound web fixture after rollback, and checks the current secret.
Its syntax and offline declaration checks pass; a live rerun remains open. The
generic recovery helper remains on the old implicit-database model.

Subsequent source update: the recovery helper now also supports explicit named
PostgreSQL marker seeding and a quarantined SQL readback against a selected
resource UUID. It checks ownership and backup timing, and records that no binding
or application reconnection was tested. The automated recovery playbook and its
legacy `check` path still use the implicit database, and live named-store restore
and application acceptance remain open.

Subsequent source update: a fixture-backed Playwright journey now covers portal
project creation, deployment, rollback, retirement, and an API-denied create.
This closes that narrow browser CI gap; it does not replace the proposed
installed API/CLI/UI runner or resolve its ADR-010 environment decision.

## Current disposition — October 19, 2026

This is a source-status reconciliation through `1a66838`, not a new live
acceptance result. The original findings above remain the dated review record.

| Baseline finding | Current source status | Still needed |
| --- | --- | --- |
| Legacy database diagnostics | Named resources and binding credentials are reported by `data-services`. | Deployed readback and native application write/read. |
| Legacy live helpers | The isolation, data-preservation, interrupted-provisioning and rollback-data drills use named PostgreSQL. The recovery helper can seed and check one named SQL marker while quarantine stays active. | Run the drills live. The automated recovery playbook still uses the implicit-database check, and the named marker check does not prove application reconnection. |
| Automatic application recovery | Restore keeps recovered access quarantined; no automatic binding replay was added. | Reconstruct reviewed public declarations, issue fresh grants and bindings, then verify an application transaction after restore. |
| Interrupted AI runs | History/detail reads mark runs still `running` after ten minutes as failed. | Process-kill and deployed readback; resumption is not implemented. |
| Deployed telemetry guarantees | No new host evidence in this source review. | Resolve the recorded Tempo filesystem metric issue and observe collector recovery, elapsed retention and sustained combined capacity. |
| Latest fixture cleanup | The last cited EV-71/72 state remains seven resources awaiting verified scheduled-backup purge intent, with access revoked. | Observe the timer, verified backup acknowledgement and final data deletion before claiming cleanup. |
| Full installed acceptance | A fixture-backed portal lifecycle browser journey now runs in CI. | Implement and run the installed API/CLI/UI acceptance stages; settle the disposable-environment approach against [ADR-010](../architecture/decisions/ADR-010-single-environment-lab.md). |
