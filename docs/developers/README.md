# Application developer guide

Status: current. Last reviewed October 9, 2026.

Use this section when you are deploying an application to an existing Developer
Platform installation. Platform installation and shared-service administration
belong in the [operator guide](../operators/README.md).

## Supported journey

1. Ask the platform team for a project, API URL, and either a user grant or a
   project-scoped deployment credential.
2. Package the application as a public OCI image that satisfies the runtime
   restrictions.
3. Describe its services, scheduled components, PostgreSQL requirement, routes,
   resources, probes, and approved egress in an application declaration.
4. Apply the declaration with the CLI or API and wait for both operation success
   and workload readiness.
5. Use operations, logs, revisions, and runtime status to diagnose a rollout.

Start with [Deploy your first application](getting-started.md). Then use:

- [UI guide](ui.md)
- [CLI guide](cli.md)
- [Application declaration reference](application-spec.md)
- [API guide](api.md)
- [CI deployment](ci-deployment.md)
- [Troubleshooting](troubleshooting.md)

## Important boundaries

An operation that has `succeeded` confirms that provider resources were applied;
it does not by itself prove that the application is ready. PostgreSQL data is
retained by default. Application rollback does not roll back database migrations
or restore historical secret values. Authorization, validation, audit, and secret
redaction remain server-side responsibilities regardless of which client is used.
