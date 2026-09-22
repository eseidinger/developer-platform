# Architecture decisions

## Docker-based Developer Platform Lab

Shared services run in Docker, with application workloads in Kubernetes-in-Docker
on the existing Hetzner host.

Infrastructure as code lives in `infrastructure/`, and the application control
plane lives in `platform/`. The existing host is not recreated using OpenTofu.
Docker and k3d handle resource provisioning.

## Boundaries and data flow

Caddy is the public entry point. The API uses PostgreSQL to store project state
and the Kubernetes API to manage declarative resources. The provisioning
ServiceAccount can manage the required resource types, but cannot manage
ClusterRoles, RoleBindings, Nodes, or perform arbitrary cluster administration.
Because namespaces are created dynamically, its resource permissions apply
cluster-wide. Workloads cannot access this token.

All Compose services and k3d nodes share a dedicated Docker network.
Workload pods are restricted by k3s NetworkPolicies; PostgreSQL is reached through
a fixed private IPv4 address. This keeps pod-to-database access independent of
Docker DNS inside Kubernetes. PostgreSQL, Loki, Alertmanager, and Kubernetes
NodePorts are not exposed through host ports.

In local live testing, internet egress was briefly possible immediately after
pods started; it was blocked once kube-router activated its rules asynchronously.
The isolation test therefore waits 15 seconds before checking the settled state.
This delay is not a security guarantee and is not enforced as a startup barrier
for workloads. Before opening the platform to hostile tenants, a CNI with suitable
isolation from startup and a separate security review are required.

The API requires a strong admin bearer token. OIDC and tenant-specific
authorization are planned extensions. Project images are set only by trusted
administrators. The platform offers no guarantees for hostile tenants on a shared
host; in particular, k3d nodes are privileged.

## Persistence and repeatability

Each project has its own database and login role without CREATE ROLE, CREATE DB,
or SUPERUSER privileges. PUBLIC has no access to project databases.
Database administrator access remains exclusively in the control plane.
Project passwords are generated deterministically using HMAC with a secret master
key; repeated API requests do not change existing credentials.

A PostgreSQL advisory lock serializes provisioning. DDL and Kubernetes operations
do not share a transaction: after partial failures, existing resources are
preserved, the state is marked as `failed`, and another PUT reconciles the resources.
A process crash may leave the state as `provisioning`; repeating the PUT repairs
this state too. There is no background reconciler yet.

## Resources and availability

PostgreSQL: 6 GiB; k3d: 2 GiB for the server + 2×4 GiB for agents;
API: 512 MiB; monitoring/proxy: approximately 3 GiB.
Container limits are upper bounds, not capacity reservations.
Namespace quotas do not replace global admission control. With too many projects,
pods remain Pending; check capacity before accepting more projects.

All components share the same failure domain. Multiple k3d nodes do not provide
host high availability. The PHP watchdog therefore runs on independent web
hosting. It detects missing heartbeats even during a complete Docker or host outage.

## Monitoring limitations

Prometheus monitors the host and Kubernetes object states; Grafana connects to
Prometheus and Loki. Alloy reads JSON file logs from Docker's default data
directory. For rootless Docker, other logging drivers, or a different data-root,
the mount must be adjusted. WSL does not require recursively propagated host mounts.

PostgreSQL query metrics, container resource metrics through cAdvisor,
Kubernetes application metrics, and dashboards are areas for future extension.
Alertmanager includes a local receiver; SMTP/webhook configuration must be added
for the deployment. The external watchdog already provides email notifications
when status changes.
