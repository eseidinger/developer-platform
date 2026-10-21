# Monitoring verification history

These dated observations describe specific deployed revisions and environments.
They do not replace the [current validation procedures](VALIDATION.md) or prove
elapsed retention and sustained capacity. Private evidence paths are retained as
references for operators with access to the corresponding host.

## Scheduled trace export — October 19, 2026

Live scheduled-job verification on October 19, 2026 found two failures in the
`odip` and `odip-test` ingestion workers: the forwarder took 6.3 seconds to
listen under its 100m CPU limit, and the gateway rejected Python's valid OTLP
flag encoding. After adding the native-sidecar startup gate and accepting that
encoding, both next natural runs waited 12 seconds before application startup,
exited successfully and logged zero export errors. Tempo contained a fresh
three-span worker trace for each project, also readable through the project
trace reader. Private deployment/rollback records are under
`.runtime/forwarder-startup-update-66be6e4b4bab/` and
`.runtime/gateway-flags-update-1557b7bae0ba/` on the installed host.

## AI metadata readback — October 19, 2026

Live verification on October 19, 2026 sent two synthetic service/model spans
from an opted-in `vareng-test` Pod through its real forwarder and authenticated
gateway. Tempo model/framework searches and the scoped trace reader returned
both spans; forged resource provenance and private-content markers were absent.
The focused gateway/API/Alloy patch and private verification record are retained
under `/opt/developer-platform/.runtime/ai-trace-update-a731205cedba/`. This
verifies the new path, not metadata recovery for old traces or elapsed
retention/load capacity.

## Structured log readback — October 19, 2026

Live verification on October 19, 2026 confirmed normal framework JSON records in
Loki for `odip`, `odip-test`, `vareng`, and `vareng-test`, with successful
scoped reads. Existing operational events and the project AI trace remained
readable; collector write retry/drop counters were zero. The update only
recreated Alloy and the Platform API; applications did not need redeployment.
Private backup and source-hash deployment evidence is recorded under
`.runtime/json-log-update-178011bed720/` on the installed host. Previously
dropped logs are not guaranteed to be recoverable; quiet applications may
require a wider Grafana time range. The production Alloy/Loki fixture verifies
both framework schemas, escaping, redaction, malformed/scalar rejection, size
limits after redaction, and persisted readback after restart.

## Hosted-access monitoring

Deployed evidence now exists for component boundary probes, independent
Kubernetes readiness and immediate provider/consumer central correlation reads:
operator-provided node-01 run `60c3ca1647b9` passed all 45 assertions with
`--timed --monitoring` after the collector state-permission repair. See
[EV-46](../../docs/operators/validation/access-and-authorization.md#executed-hosted-access-monitoring-acceptance-october-11-2026).
The report says `sevenDayRetention: not-time-verified`; neither post-retirement
log readback nor elapsed retention/compactor deletion was exercised.
