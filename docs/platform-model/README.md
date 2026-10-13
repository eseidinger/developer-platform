# How the developer platform works

This documentation explains the platform as a system: the decisions behind its
boundaries, the state it owns, and how an application moves from declared intent
to a running workload. It describes the current implementation. It is not an
installation guide or a sequence of tasks for platform users.

Read from the broad model toward the mechanisms:

1. [System model](system-model.md) introduces the control plane, runtime, and
   external identity and data services.
2. [Design concepts](design-concepts.md) explains the rules that shape those
   boundaries: declarative intent, durable reconciliation, scoped authority, and
   fail-closed access.
3. [Platform API](platform-api.md) describes the domains the API controls and
   the difference between accepting a change and completing it.
4. [Platform database](platform-database.md) identifies the authoritative
   records, their relationships, and the state kept outside the platform DB.
5. [Identity and authorization](identity-and-authorization.md) follows human,
   automation, browser, and service identities through Keycloak and the platform.
6. [Deployment and Kubernetes](deployment-and-kubernetes.md) traces a validated
   application declaration to PostgreSQL and Kubernetes resources.
7. [Observability](observability.md) explains how runtime state, probes, metrics,
   logs, alerts, and audit evidence relate to the platform's desired state.

The distinction that connects the whole set is **intent versus realization**.
The API records what a project is allowed to request and what it wants to run.
Workers realize that intent in Keycloak, PostgreSQL, and Kubernetes. Readers can
inspect both the recorded intent and the observed result without treating a
successful API response as proof that every downstream step has finished.
