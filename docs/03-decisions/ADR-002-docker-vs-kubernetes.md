# ADR-002 – Hybrid Starting Topology

Created: September 25, 2026. Status: **Hybrid accepted**; no additional workload adapter in the current scope.

## Context

An initial design used three Kubernetes VMs plus PostgreSQL and monitoring VMs. The available infrastructure is a low-cost Ubuntu host with 16 vCPUs and 32 GB RAM. The hybrid solution was selected on September 21, 2026.

## Decision

Starting profile: platform services, PostgreSQL, and central observability run in Docker; project workloads run in Kubernetes inside Docker, with k3d proposed. PostgreSQL remains outside the workload cluster. An external watchdog complements local monitoring.

k3d is the selected workload-compute implementation. The platform services and PostgreSQL continue to run in Docker, but Docker is not an additional application workload adapter. A direct Docker compute adapter is an optional Phase 5 expansion only.

## Implementation note — September 27, 2026

[Cluster configuration](../../scripts/cluster_config.py) now implements k3d/k3s with one server and two agents. The earlier “k3d proposed” wording records the original decision scope, not current implementation status. No direct Docker workload adapter exists.

## Alternatives and evolution

| Option | Benefit | Limitation |
|---|---|---|
| Docker only | Low infrastructure overhead | Kubernetes behavior and isolation are not automatically available |
| Hybrid | Real Kubernetes API with simple shared-service installation | Additional routing/network complexity; one host |
| Multiple VMs | Separate failure domains and scaling | Cost and higher operational effort |

Docker-first remains an optional implementation alternative. It has not replaced the accepted hybrid topology and is not part of Phases 2 through 4. Existing hybrid/Kubernetes work remains the supported path unless the owner explicitly activates the Phase 5 provider package.

## Consequences

No HA guarantee: multiple k3d nodes share one physical failure domain. Monitoring outside k3d can detect cluster failures but also fails when the host is lost. Restore and an external alert channel are required MVP evidence.

## Validation and review triggers

Verify host capacity, pod-to-PostgreSQL connectivity, TLS routing, cluster recreation, backup restore, and host-failure alerting. Revisit the multi-VM option when capacity or availability requirements increase.

Details: [Infrastructure](../02-architecture/infrastructure.md), [Phase 1](../04-development/phase-1-foundation.md).
