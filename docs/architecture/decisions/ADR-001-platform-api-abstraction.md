# ADR-001 – Technology-Independent Platform API

Created: September 25, 2026. Status: **Accepted public-contract principle**; second-provider implementation is optional Phase 5.

## Context

The Platform API must operate independently of Docker or Kubernetes. In the hybrid installation, compute, persistence, and monitoring do not necessarily share a runtime.

## Decision

Public contracts use Applications, Environments, Resources, Endpoints, and Grants. Small provider ports translate domain operations into compute, database, secret, network, and observability operations. Desired state and observed status remain separate.

Each environment declares its verified capabilities. Unsupported mandatory features cause rejection before provisioning. Internal backend resources remain referenced through stable platform IDs.

The public contract must remain independent of Kubernetes resource shapes. Multiple runtime adapters are not required by the current scope. Provider ports and a second compute implementation remain an optional Phase 5 technique for validating portability if a concrete need emerges.

## Alternatives

- Direct Kubernetes API wrapper: faster for one backend, but violates the required independence.
- One monolithic InfrastructureProvider: simple initially, but unnecessarily couples database, compute, and monitoring.
- Lowest common feature set only: portable, but prevents optional advanced capabilities.
- Arbitrary provider passthrough fields: flexible, but make the contract backend-dependent; excluded from the first profile.

## Consequences

The platform owns its state models, error classes, and workflows. This increases implementation effort but allows the API, CLI, UI, and AI to share one contract. Portability does not guarantee automatic data migration or equivalent availability.

## Validation

For the current scope, review the contract for Kubernetes-specific client fields and test capability rejection before side effects. If optional Phase 5 adds Docker compute, run the same web/PostgreSQL use case on Kubernetes and directly on Docker; keep the schema and client unchanged and test partial failures and unsupported capabilities.

Implementation: [Software architecture](../application-lifecycle.md), [ApplicationSpec](../application-contract.md), [Phase 2C](../../maintainers/delivery/history/phase-2c-platform-capabilities.md), [optional Phase 5](../evolution.md).
