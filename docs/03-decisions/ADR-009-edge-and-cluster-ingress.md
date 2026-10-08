# ADR-009 – Caddy Edge and Traefik Cluster Ingress

Created: September 26, 2026. Status: **Accepted** for the current hybrid starting profile. Operational acceptance remains open.

## Context

ADR-002 selected the hybrid topology without selecting an edge proxy. The infrastructure draft proposed Traefik at the edge, while the inspected implementation uses Caddy in Docker outside k3d and Traefik inside the cluster. The edge needs to route the platform API and dynamically provisioned application hostnames without requiring access to the Kubernetes or Docker API.

## Decision

Retain the implemented division of responsibility:

- **Caddy outside k3d:** terminate public TLS, route the platform hostname to the API, and forward application traffic to the k3d load balancer.
- **Traefik inside k3d:** route application HTTP traffic using Kubernetes Ingress resources created by the provisioner.
- **Platform API:** authorize on-demand application certificates through `/internal/tls`; only the exact legacy project hostname or a service hostname generated from an `applied` stored spec under `APPS_DOMAIN` is eligible. A component hostname is `<component>-<project>.<APPS_DOMAIN>` and must correspond to a declared public service.

The current [Caddyfile](../../infrastructure/proxy/Caddyfile) has two upstream destinations and requires neither Docker discovery nor Kubernetes credentials. Caddy owns public certificate management; the internal application hop uses HTTP. Local `*.apps.localhost` traffic has an explicit HTTP route. The API's `applied` state is certificate eligibility, not observed application health.

This decision refines ADR-002 and replaces the draft edge-proxy suggestion; it does not supersede the accepted hybrid topology. It does not accept the shared Docker network as the final security boundary.

## Alternatives

| Option | Benefit | Cost or limitation |
| --- | --- | --- |
| Retain Caddy edge and Traefik ingress | Existing simple edge configuration and application certificate authorization; cluster routing remains Kubernetes-native | Two proxy technologies and configuration surfaces to operate |
| Traefik at both layers | One proxy technology; potential reuse of operational knowledge | Requires edge routing/certificate design, migration, and validation; two instances and routing layers remain |
| Move the public edge into k3d | Could remove the external proxy layer | Couples public platform routing and certificate handling to the workload cluster; changes the selected failure boundary |

Standardizing on Traefik alone is insufficient reason to migrate an already coherent edge implementation. Revisit if discovery requirements, custom-domain support, certificate scale, or operational experience demonstrate a concrete benefit.

## Consequences and boundaries

The edge remains outside the workload cluster, although all local components still share the host failure domain. A cluster outage does not inherently stop the edge process or platform process; application traffic and API dependency readiness can still fail.

On-demand certificate authorization depends on the platform API and its PostgreSQL lookup. It is not a per-request authorization check for application traffic and does not replace application authentication. New certificate acquisition can add initial connection latency; test issuance and renewal behavior rather than inferring availability from placement.

The implementation currently shares the `developer-platform` Docker network. Network segmentation is separate outstanding work: define required edge/API/cluster/database/monitoring paths, design boundaries, and test allowed and denied connectivity before rollout. Proxy replacement would not itself establish those boundaries. PostgreSQL transport encryption also remains unconfigured.

## Validation and review triggers

Source inspection establishes the routing and certificate-eligibility paths, not public TLS or recovery acceptance. Under [ADR-010](ADR-010-single-environment-lab.md), use controlled checks on the existing lab; defer exercises that require a fresh isolated installation. Record:

1. Platform and application routing with real DNS and ACME issuance, including renewal behavior.
2. Rejection of unknown, wrong-domain, and non-applied project names by the certificate authorization path.
3. API/database unavailability during new certificate acquisition and behavior of existing certificate routes.
4. Cluster outage behavior: edge/platform process availability, application failures, and recovery.
5. Recovery of Caddy certificate state and configuration from protected storage, followed by routing/TLS verification.
6. Forwarded client/protocol headers across both proxies, and allowed/denied connectivity when network segmentation is implemented.

These exercises remain unverified. Record environment, revision, certificate state, timing, and outcomes beside DEV-009-T01 and OPS-007-T01 in the [delivery backlog](../04-development/delivery-backlog.md) before claiming acceptance.

Details: [Infrastructure](../02-architecture/infrastructure.md), [Topology](../02-architecture/diagrams/topology.md), [Deployment](../05-operations/deployment.md).
