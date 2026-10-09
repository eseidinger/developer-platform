# ADR-014 – Catalog-Derived Availability Probes and Explicit Retirement

Recorded: September 27, 2026. Status: **Implemented design; owner acceptance of this record not recorded**. Local preparation exists; live application outage/recovery and retirement acceptance remain open.

## Context

Kubernetes apply success and TCP pod probes do not establish HTTP application availability. Monitoring should keep failed provisioning attempts visible and should not interpret accidental workload disappearance as deliberate removal.

## Implemented choice

The durable PostgreSQL catalog is the source of target membership. Every project except a `retired` entry receives a root-path probe. Bounded `status` and `hello-world` profiles select HTTP 200 and optional full-body content checks; specs cannot supply arbitrary URLs, headers or regexes.

The API publishes discovery before provisioning side effects and repeats publication every 30 seconds in a background thread. The existing lifecycle advisory lock serializes it with PUT/retirement. Files are atomically replaced on a shared volume; failed queries/publication leave the prior target file available. Prometheus file discovery and the blackbox exporter probe applications without a restart. A textfile timestamp exposes publication freshness through node-exporter.

Exact `APPS_DOMAIN=apps.localhost` uses `http://proxy/` with the application's hostname parameter, avoiding container-loopback resolution. Other domains use the public HTTPS URL and certificate validation. Both originate on the platform host, outside k3d but inside the same host/network failure domain.

`POST /projects/{name}/retire` requires an OIDC `project-admin` or `platform-admin` grant, matching name confirmation and an absent project namespace. It retains SQL data/login/spec and removes discovery membership. Manual namespace removal alone never removes the target. PUT explicitly reactivates a retired entry. Bulk recovery replay skips retired entries; deliberately selecting one for PUT reactivates it.

## Alternatives and consequences

Kubernetes-discovered membership could silently lose monitoring when resources disappear. Hand-maintained targets require synchronization with lifecycle changes. An independent external probe service would add a separate network vantage point and operational dependency; it is not implemented here.

The discovery volume is disposable derived state and contains no credentials; the catalog/profile/retired status remain in the SQL backup. The thread reconciles discovery only, not workloads. Long lock-holding requests can cause stale-discovery alerts. Target removal can resolve an alert without application recovery; retirement evidence must stay distinct from recovery evidence. The endpoint does not implement deletion planning, resumable cleanup or audit.

## Evidence and evolution

Source and local validation: [monitoring publisher](../../../platform/app/monitoring.py), [probe/rule configuration and procedures](../../../infrastructure/monitoring/README.md), [lifecycle fixtures](../../../platform/tests/test_monitoring_lifecycle.py). OPS-007-T01 and DEV-011-T01 remain open for live evidence and the full lifecycle.

Extend profiles deliberately when applications need different health paths; revisit identity labels when environments/components exist. An outside-network check is separate evidence. This creates no additional watchdog observer and preserves ADR-011's accepted monitoring boundary.
