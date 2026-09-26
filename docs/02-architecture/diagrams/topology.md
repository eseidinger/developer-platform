# Hybrid Topology

Status: current source topology, with Caddy edge and Traefik ingress selected in [ADR-009](../../03-decisions/ADR-009-edge-and-cluster-ingress.md). Live TLS and recovery acceptance remain open. [Infrastructure details](../infrastructure.md).

```mermaid
flowchart TB
    User["User"] --> Edge
    subgraph Host["Ubuntu Host - Shared Failure Domain"]
        subgraph Network["Shared developer-platform Docker Network"]
            Edge["Caddy Edge / Public TLS"] --> API["Platform API - Synchronous Provisioning"]
            Edge --> LB["k3d Load Balancer / HTTP"]
            Edge -. "Certificate eligibility lookup" .-> API
            subgraph Cluster["k3d Workload Cluster"]
                LB --> Ingress["Traefik / Kubernetes Ingress"]
                Ingress --> App["Project Workload"]
                Secret["Database Secret"] --> App
                Metrics["kube-state-metrics"]
            end
            API --> Cluster
            API --> PG[("PostgreSQL Outside k3d")]
            App --> PG
            Metrics --> Monitor["Prometheus / Loki / Grafana / Alertmanager"]
        end
        DockerLogs["Host Docker Logs"] --> Alloy["Alloy"]
        Alloy --> Monitor
        Heartbeat["systemd Heartbeat Sender"] -. "Readiness checks" .-> API
        Heartbeat -. "Readiness checks" .-> Monitor
    end
    Heartbeat --> External["External PHP/MySQL Watchdog"]
    External --> Alert["Mail / TLS SMTP - Receipt Unverified"]
```

Arrows show logical flows rather than firewall rules. Caddy and shared services remain outside k3d, but all local components share one host failure domain. Public application TLS terminates at Caddy; the ingress hop is HTTP.

Separate Docker networks, the identity provider, durable worker, PostgreSQL/application telemetry, and automated encrypted external backups remain target work and are not shown as implemented components. Local SQL dumps exist but are not off-host recovery. The watchdog is independently hosted; actual installation and notification receipt still require evidence.
