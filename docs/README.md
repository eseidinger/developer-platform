# Developer Platform documentation

Status: current documentation index. Last reviewed October 9, 2026.

Choose the path that matches what you are trying to do.

## Use the platform

For application developers who deploy and operate their own applications:

1. [Developer overview](developers/README.md)
2. [Deploy your first application](developers/getting-started.md)
3. [Use the UI](developers/ui.md) or [CLI](developers/cli.md)
4. [Declare an application](developers/application-spec.md)
5. [Use the API](developers/api.md) or [deploy from CI](developers/ci-deployment.md)

## Operate the platform

For administrators responsible for the shared installation:

1. [Operator overview](operators/README.md)
2. [Install locally](operators/install-local.md) or
   [install on a remote host](operators/install-remote.md)
3. [Bootstrap identity and access](operators/identity-and-access.md)
4. [Monitor](operators/monitoring.md),
   [back up and recover](operators/backup-and-recovery.md), or
   [respond to an incident](operators/runbooks/README.md)

## Change the platform

For contributors and maintainers changing platform code or delivery plans:

1. [Maintainer overview](maintainers/README.md)
2. [Platform API](maintainers/platform-api.md), [CLI](maintainers/cli.md),
   [UI](maintainers/ui.md), and [monitoring](maintainers/monitoring.md)
3. [Delivery status and plans](maintainers/delivery/README.md)
4. [Delivery backlog and evidence](maintainers/delivery/backlog.md)

## Understand the design

For architects and reviewers:

1. [Architecture overview](architecture/README.md)
2. [Platform application](architecture/platform-application.md) and
   [application lifecycle](architecture/application-lifecycle.md)
3. [Deployment topology](architecture/deployment-topology.md),
   [security and authorization](architecture/security-and-authorization.md), and
   [observability](architecture/observability.md)
4. [Application contract](architecture/application-contract.md),
   [architecture evolution](architecture/evolution.md), and
   [decision records](architecture/decisions/README.md)

## Product direction

- [Overview and vision](product/overview.md)
- [Use cases](product/use-cases.md)
- [Requirements](product/requirements.md)
- [Roadmap](product/roadmap.md)

## Document status

- **Current:** describes supported behavior or an executable procedure.
- **Planned:** approved or proposed work that is not yet supported.
- **Historical:** preserves completed plans and evidence; it is not a current
  operating guide.
- **Generated reference:** produced from source and not edited by hand.

Current guides must not rely on planned behavior. Architecture explains why the
system has its shape, operator guides explain how to run it, and maintainer guides
explain how to change and validate its implementation. Source-adjacent READMEs
cover only their component and link back to the canonical guide here.
