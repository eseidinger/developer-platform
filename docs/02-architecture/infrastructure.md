# Infrastructure Architecture

Status: the hybrid solution is the selected starting topology; installation has not been verified here. A larger topology remains an expansion option.

## Starting topology: existing Hetzner host

The available Ubuntu host has **16 vCPUs and 32 GB RAM**. The hybrid design runs platform services and PostgreSQL in Docker, with project workloads in Kubernetes inside Docker, using k3d/k3s as the proposed implementation.

| Area | Placement | Responsibility |
|---|---|---|
| Edge | Docker; Traefik proposed | Public HTTP(S) routes and TLS |
| Platform API / worker | Dedicated Docker stack | Control plane and provisioning |
| Identity provider | Dedicated service; Keycloak proposed | Authentication and client identities |
| PostgreSQL | Docker outside k3d, persistent volume | Platform metadata and separate project databases |
| Workload compute | k3d with project/environment namespaces | Applications, services, secrets, internal ingress routes |
| Observability | Docker outside k3d | Prometheus, Grafana, Loki, Alertmanager |
| Collectors/exporters | Alongside monitored systems | Host, database, container, and Kubernetes signals |
| Host watchdog | systemd outside Docker | Detect Docker/monitoring failures |
| External watchdog | Independent PHP/MySQL web hosting | Detect host/network failures using heartbeats and probes |

[Topology diagram](diagrams/topology.md).

## Networking and persistence

Only intended edge endpoints are normally public over HTTPS, with HTTP used for redirects or required certificate validation. Administrative access uses controlled SSH/VPN. PostgreSQL, the Docker API, the Kubernetes API, and internal monitoring backends are not exposed as general public services.

Separate networks bound edge, platform, persistence, and project workloads. The pod-to-PostgreSQL path must be tested for DNS, routing, firewall rules, and TLS. A Compose DNS name is not automatically resolvable inside the cluster.

The edge proxy forwards application traffic to the k3d entry point and its ingress. Each route has exactly one designated TLS termination point. The installation profile prevents duplicate or conflicting certificate management.

PostgreSQL data, platform metadata, identity-provider state, and relevant configuration require persistent storage and external backups. Recreating k3d must not delete these data. Logs and metrics have separate retention and storage budgets.

## Capacity and failure domain

A possible **planning baseline**, not a measurement or capacity guarantee:

| Area | RAM budget |
|---|---:|
| Host, Docker, and base processes | 3 GiB |
| PostgreSQL | 5 GiB |
| Monitoring/logging | 4 GiB |
| Platform API, worker, and identity provider | 3 GiB |
| k3d system components | 3 GiB |
| Application workloads | 9 GiB |
| Reserve | 5 GiB |
| Total | 32 GiB |

Measure actual usable memory on the host: “32 GB” and “32 GiB” are not equivalent. Reduce budgets accordingly. Also constrain and measure CPU, I/O, connections, and log growth.

All local components share one host failure domain. The host watchdog helps during Docker failures but cannot detect a complete host failure independently. The external watchdog remains necessary.

## Expansion option

Three Kubernetes VMs running control-plane and worker roles, a separate PostgreSQL VM, and a `platform-01` VM for central observability. Collectors, kube-state-metrics, node-exporter, and proposed Trivy Operator/Kyverno components remain cluster-local.

The proposed infrastructure-as-code split uses OpenTofu for Hetzner resources, Ansible for host configuration, and Helm/manifests for cluster components. The five-VM topology is an option, not the current deployment scope. It still has database and monitoring single points of failure unless additional measures are introduced.

Decision: [ADR-002](../03-decisions/ADR-002-docker-vs-kubernetes.md). Installation sequence: [Deployment](../05-operations/deployment.md).
