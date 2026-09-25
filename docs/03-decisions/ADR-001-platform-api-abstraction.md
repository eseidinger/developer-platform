# ADR-001 – Technology-Independent Platform API

Created: September 25, 2026. Status: **Accepted principle**; detailed design proposed.

## Context

The Platform API must operate independently of Docker or Kubernetes. In the hybrid installation, compute, persistence, and monitoring do not necessarily share a runtime.

## Decision

Public contracts use Applications, Environments, Resources, Endpoints, and Grants. Small provider ports translate domain operations into compute, database, secret, network, and observability operations. Desired state and observed status remain separate.

Each environment declares its verified capabilities. Unsupported mandatory features cause rejection before provisioning. Internal backend resources remain referenced through stable platform IDs.

Ports and adapters, persistent reconciliation, and the specific v1alpha1 contract are the proposed implementation of this accepted requirement.

## Alternatives

- Direct Kubernetes API wrapper: faster for one backend, but violates the required independence.
- One monolithic InfrastructureProvider: simple initially, but unnecessarily couples database, compute, and monitoring.
- Lowest common feature set only: portable, but prevents optional advanced capabilities.
- Arbitrary provider passthrough fields: flexible, but make the contract backend-dependent; excluded from the first profile.

## Consequences

The platform owns its state models, error classes, and workflows. This increases implementation effort but allows the API, CLI, UI, and AI to share one contract. Portability does not guarantee automatic data migration or equivalent availability.

## Validation

Run the same web/PostgreSQL use case on Kubernetes and directly on Docker. The schema and client remain unchanged; only the environment and capability offering differ. Explicitly test partial failures and unsupported autoscaling.

Implementation: [Software architecture](../02-architecture/software-architecture.md), [ApplicationSpec](../02-architecture/application-spec.md), [Phase 2](../04-development/phase-2-platform-api.md).
