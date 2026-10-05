# Architecture Diagrams

[Back to architecture overview](../overview.md)

Diagrams are maintained directly in the repository as Markdown files containing Mermaid blocks.

- [Hybrid topology and failure boundaries](topology.md)
- [Kubernetes infrastructure](../kubernetes-infrastructure.md)
- [Platform application](../platform-application.md)
- [Keycloak and Kubernetes authorization](../authorization-keycloak-kubernetes.md)
- [Keycloak and Kubernetes authorization principles](../keycloak-kubernetes-authorization-principles.md)
- [Provisioning and partial failures](provisioning.md)
- [Component overview](../overview.md)
- [Lifecycle state machine](../software-architecture.md)

Each diagram declares its evidence level: topology shows inspected source configuration; provisioning distinguishes the current in-process worker from the target worker service; the component overview and lifecycle state machine are target states. None establishes live operational acceptance. Changes to topology or lifecycle must be accompanied by specification and ADR updates.
