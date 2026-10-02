# Infrastructure Architecture

Status: the hybrid solution is the selected starting topology. [ADR-009](../03-decisions/ADR-009-edge-and-cluster-ingress.md) accepts the implemented Caddy edge / Traefik cluster ingress split. Source configuration has been inspected; public TLS and full target-host acceptance remain open. Operator-reported marker-based recovery and selected email delivery checks are recorded in the backlog; they do not establish complete acceptance. A larger topology remains an expansion option.

## Starting topology: existing Hetzner host

The available Ubuntu host has **16 vCPUs and 32 GB RAM**. The hybrid design runs platform services and PostgreSQL in Docker, with project workloads in Kubernetes inside Docker, using k3d/k3s in the current implementation. The table distinguishes implemented components from target extensions.

| Area | Placement | Responsibility |
|---|---|---|
| Edge | Caddy in Docker outside k3d; implemented and selected | Public TLS, platform routing, application forwarding, and API-gated on-demand certificates |
| Platform API | Docker; implemented | Synchronous admin provisioning and latest project spec/status; durable worker remains proposed |
| Target application catalog | Docker placement proposed; not implemented | Kotlin/Spring Boot service for application metadata, ownership, environments, dependencies, and grants |
| Target control plane | Docker placement proposed; not implemented | Quarkus service for deployment intent, policy, operations, runtime status, and events |
| Target automation workers | Docker placement proposed; not implemented | Python execution of approved provider operations with scoped credentials |
| Identity provider | Dedicated service; generic OIDC boundary with Keycloak selected for the supported lab profile; not implemented | Authentication and client identities; platform grants remain platform-owned |
| PostgreSQL | Docker outside k3d, persistent volume | Platform metadata and separate project databases |
| Workload compute | k3d with project namespaces; implemented | Applications, services, secrets, and Traefik ingress; environment model remains proposed |
| Observability | Docker outside k3d; implemented | Prometheus, Grafana, Loki, Alertmanager; data sources are provisioned, dashboards are not |
| Collectors/exporters | node-exporter, kube-state-metrics, blackbox exporter and Alloy; implemented | Host metrics, Kubernetes object state, application availability and host Docker logs; PostgreSQL and workload usage/log telemetry remain target work |
| Host heartbeat sender | systemd outside Docker; implemented | Check API dependency and Prometheus readiness; stop heartbeats on failure so the external watchdog can notify |
| External watchdog | Independent PHP/MySQL web hosting | Detect host/network failures using heartbeats and probes |

[Topology diagram](diagrams/topology.md).

## Networking and persistence

Only intended edge endpoints are normally public over HTTPS, with HTTP used for redirects or required certificate validation. Administrative access uses controlled SSH/VPN. PostgreSQL, the Docker API, the Kubernetes API, and internal monitoring backends are not exposed as general public services.

**Current implementation:** Compose services and k3d nodes share the `developer-platform` Docker network. Kubernetes NetworkPolicies restrict workload traffic; pods reach PostgreSQL through its fixed private IP because Compose DNS names do not automatically resolve in Kubernetes. PostgreSQL TLS is not configured. These controls do not establish the proposed network segmentation or hostile-tenant isolation.

**Outstanding target:** define separate edge/platform/persistence network boundaries and the explicit connections needed by the edge, API, cluster, and monitoring. Implement and test allowed/denied traffic and pod-to-PostgreSQL connectivity before claiming segmentation. This work is independent of the selected proxy software.

Caddy terminates public TLS and forwards application HTTP traffic through the k3d load balancer to Traefik, which resolves Kubernetes Ingress routes. Platform traffic goes directly from Caddy to the API. Caddy owns public certificates; Traefik does not manage a second public certificate for these routes. Local `*.apps.localhost` requests use the explicit HTTP development route.

For application certificates, Caddy asks the API at `/internal/tls`; the API requires the configured domain suffix and a stored project with status `applied`. New certificate authorization therefore depends on the API and PostgreSQL. This gate does not check every application request or prove workload health. Keep the edge independent of Kubernetes/Docker API credentials. See [ADR-009](../03-decisions/ADR-009-edge-and-cluster-ingress.md) for alternatives and required issuance, rejection, outage, header, and certificate-recovery tests.

PostgreSQL data, platform metadata, identity-provider state, and relevant configuration require persistent storage and external backups. Recreating k3d must not delete these data. Logs and metrics have separate retention and storage budgets.

## Capacity and failure domain

A possible **planning baseline**, not a measurement or capacity guarantee:

| Area | RAM budget |
|---|---:|
| Host, Docker, and base processes | 3 GiB |
| PostgreSQL | 5 GiB |
| Monitoring/logging | 4 GiB |
| Catalog, control plane, workers, and identity provider | 3 GiB |
| k3d system components | 3 GiB |
| Application workloads | 9 GiB |
| Reserve | 5 GiB |
| Total | 32 GiB |

The 3 GiB service allocation predates implementation of the three-service target and is only a placeholder. Measure idle, peak, and failure/retry behavior for each JVM service and Python worker before accepting it or reduce workload capacity/reserve explicitly. Measure actual usable memory on the host: “32 GB” and “32 GiB” are not equivalent. Also constrain and measure CPU, I/O, connections, and log growth.

All local components share one host failure domain. The host sender does not directly inspect the Docker daemon or deliver a local notification; failed API/Prometheus checks stop its heartbeat. The external watchdog detects expiry, including during host loss. Broader host checks remain target work. The operator has reported receipt for heartbeat, selected Alertmanager and backup scenarios; see [current monitoring evidence](../04-development/delivery-backlog.md#current-monitoring-progress).

## Expansion option

Three Kubernetes VMs running control-plane and worker roles, a separate PostgreSQL VM, and a `platform-01` VM for central observability. Collectors, kube-state-metrics, node-exporter, and proposed Trivy Operator/Kyverno components remain cluster-local.

The proposed infrastructure-as-code split uses OpenTofu for Hetzner resources, Ansible for host configuration, and Helm/manifests for cluster components. The five-VM topology is an option, not the current deployment scope. It still has database and monitoring single points of failure unless additional measures are introduced.

Decision: [ADR-002](../03-decisions/ADR-002-docker-vs-kubernetes.md). Installation sequence: [Deployment](../05-operations/deployment.md).
