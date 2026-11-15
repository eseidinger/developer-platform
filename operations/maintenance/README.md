# Project purge maintenance

The
[operator lifecycle guide](../../docs/operators/project-lifecycle.md)
describes the public workflow. This directory owns the private host
operations that require Docker, telemetry-volume access and managed
backup credentials.

`purge-project.py` runs as root via the Ansible-installed systemd
timer. It reads only signed requests under `.runtime/maintenance`,
checks them against the API's purge ledger using
`docker compose exec`, and derives targets from verified UUIDs. It
accepts no arbitrary deletion path through the API. The maintenance
bind mount belongs to API UID 10001 with mode 0700.

Processing occurs in two phases:

1. Retire workloads and provider access; erase project telemetry and
   verify it; sign the storage receipt.
1. After the API removes its owned catalog and audit rows, compact
   metrics again, verify a new backup, prune snapshots containing the
   UUID, check the repository and sign the final receipt.

A blocked operation is incomplete. The worker preserves a complete
retained-log export and old Loki volume across failed rebuilds;
Prometheus uses a durable clean snapshot copy. Do not remove these
private files while work is pending. Loki ingestion remains stopped
during a failed rebuild to avoid overwriting unexported records on a
later retry. The timer resumes the same operation.

The API's private `app.lifecycle.maintenance` command implements
ledger checks, log export/replay verification, Prometheus
administrative requests and signed receipts. None of these actions is
a public HTTP endpoint.

Run offline host tests with:

```bash
python3 -m unittest discover -s operations/maintenance/tests/unit
```

API tests include encrypted recovery, real-SQL lifecycle transitions
and count/hash verification of log rebuilds. Native backend checks use
disposable storage; never point exploratory erasure commands at an
installed platform.
