# Hybrid Topology

Status: selected installation model, shown as an architectural draft. [Details](../infrastructure.md).

```mermaid
flowchart TB
    User["User"] --> Edge
    subgraph Host["Hetzner Ubuntu Host - Shared Failure Domain"]
        Edge["Docker Edge / TLS"] --> API["Platform API / Worker"]
        IdP["OIDC Provider"] --> API
        Edge --> Ingress
        subgraph Cluster["k3d - Workload Cluster"]
            Ingress["Ingress"] --> App["Project Workload"]
            App --> Secret["Secret Binding"]
            Collect["Collector / Exporter"]
        end
        API --> Cluster
        API --> PG[("PostgreSQL Outside k3d")]
        App --> PG
        Collect --> Monitor["Prometheus / Loki / Grafana / Alertmanager"]
        PG --> Monitor
        Watch["systemd Host Watchdog"] --> Monitor
        Watch --> Heartbeat["Heartbeat Sender"]
    end
    Heartbeat --> External["External PHP/MySQL Web Hosting"]
    External --> Alert["Independent Alert Channel"]
    PG --> Backup["External Backup Target"]
    API --> Backup
```

Arrows to observability and backup represent logical data flows, not a complete firewall rule set. The external watchdog must run outside the monitored host. Verify network, credential, and storage separation during installation.
