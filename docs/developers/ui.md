# UI guide

Status: implemented in source with capability-specific local/deployed evidence.
Reviewed October 18, 2026; full installed-platform journey acceptance remains open.

The Platform Control Plane portal is served at `/` on the Platform API
origin. It uses OIDC Authorization Code with PKCE and calls the same API as the
CLI. The project workspace has lifecycle, diagnostics, project grants and
deployment credentials, with separate pages for **Application access**,
**Data stores** and **AI assistance**. **My store access** lists the signed-in
human's explicit store grants and leases across projects.
Implementation and acceptance evidence
are tracked in the [delivery backlog](../maintainers/delivery/backlog.md).

The UI may explain or hide actions based on the current role, but the Platform API
is authoritative for authorization, validation, audit, and redaction. Access
tokens and one-time secrets must not enter URLs, logs, screenshots, or persistent
browser storage.

Until a workflow is available in the portal, use the [CLI](cli.md) or
[API](api.md). For UI source, commands, and tests, see the
[UI maintainer guide](../maintainers/ui.md).

## Manage named stores and human access

Open **Data stores** at `/projects/{name}/stores` to create independent resources,
request component bindings, review incoming requests, and manage explicit human
grants. The server supplies enabled providers and management permissions. Resource
and grant changes use their current versions. Retirement revokes access and
retains data; purge is a separate UUID-confirmed action that waits for verified
off-host backup intent.

Open **My store access** at `/store-access` to issue a 24-hour credential for your
own grant, inspect lease history, reveal connection values, or open an available
console. Inspect pending issuance using its existing credential ID. After an
uncertain response, inspect lease history before issuing another lease. Active
credentials can be revealed again until their original deadline; early renewal
creates an independent generation. Register an Ed25519 key before issuing an SSH
lease; replacing your key ends existing leases. Console-only access needs no key.

PostgreSQL uses pgAdmin SSO and the host `store-access` inside that console.
The separately labelled `PGHOST` is for private native clients. RustFS, Qdrant,
OpenSearch Dashboards and Neo4j Browser use lease-scoped launch sessions plus
native credentials. Neo4j Community grants full instance access and has
no read-only mode. Expiry, revocation and permission changes fence connections.
Credential values remain in dialog memory and are discarded on close or expiry.
See [human store access](database-access.md) and the
[operator store guide](../operators/data-stores.md) for provider-specific steps
and acceptance limits. The old implicit-project database grant and password
issuance endpoints return HTTP 410; their former workspace panel is not mounted.

## Use AI assistance

Open `/projects/{name}/ai` for explanations, incident investigations and curated
development guidance. Human viewers may run assistance for Public/Internal
projects when the external provider is configured and eligible. A human platform
administrator sets AI classification; Confidential, Restricted and unclassified
projects cannot start model runs.

Review observations, source references, hypotheses, gaps and usage completeness.
A completed sourced incident investigation bound to the current failed revision
can support a rollback proposal to a retained successful revision. An authorized
human reviews the exact diff, approves it and executes it as separate actions.
Approval expires after 15 minutes; changed authority or revision invalidates
execution. Follow the resulting deployment operation and readiness separately.

Runs and proposals have durable history. After an uncertain mutation, refresh
history before acting again. Navigation does not cancel a synchronous model run;
an interrupted server process can leave a running record. Automatic polling stops
after five minutes and can be resumed with **Refresh AI**. Model output requires
review, and incomplete usage is not reported as a complete cost estimate.

## Define and approve application access

The **PLAN-020** screens below are implemented in source, exercised with local
browser fixtures, and reported visible on the deployed portal with an active
policy. The owner accepted this increment for lab sequencing without deployed
first-login and service-access journey checks. Their behavior through the portal
remains unverified; the supported [API](api.md#hosted-application-access) remains
available. The exception and original acceptance criteria are recorded in
[UI increment 4a](../maintainers/delivery/plans/ui.md#4a-deliver-hosted-application-access-plan-020).

Open a project and select **Application access**. Keep this area separate from
**Project access** and **Deployment credentials**: permission to deploy or
administer the platform never grants membership in the hosted application.
Project administrators manage application access; an application-administrator
group permits application routes without granting control-plane authority.

### Define the application's access

1. Deploy a `v1alpha2` application with one public service through the existing
   deployment workflow. The access overview shows the application/project name,
   public component, URL, workload readiness, and access-policy state separately.
   Explain a missing policy as **Access not configured; public requests denied**.
   Private-only and legacy applications show the requirement for a public
   `v1alpha2` component before access configuration is available.
2. In **Governance**, record data and telemetry classification, whether personal
   data is stored, domain-retention owner and policy, purge authority, and recovery
   owner. Save this separately from the deployment declaration. Email release
   requires a governance record with personal-data handling enabled.
3. In **Groups**, create named application groups with display names, for example
   `readers`, `application-administrators`, and `machine-readers`. Group selection
   uses stable IDs; names are labels. Creating a group grants nobody membership.
4. In **Policy**, select the declared public component and add route rules. Each
   rule has a name, exact path or segment-aware path prefix, explicit HTTP methods,
   **Browser session** or **Bearer token** authentication, and one or more allowed
   groups. A caller needs any one of the selected groups. Include the application's
   entry page, assets, and browser API calls where needed; undeclared paths/methods
   remain denied. For example, use browser-session rules for `/app/` and bearer-token
   rules for `/api/` with the intended methods and groups.
5. Review the route/group summary and save the complete policy. The editor rejects
   overlapping path/method rules, empty group selections, invalid or reserved
   `/oauth2` paths, and browser policies without a `GET` entry route. `HEAD` follows
   `GET`; `OPTIONS` needs an explicit rule. Unmatched requests are denied. Display
   name and email release default to off. The platform derives identity clients
   and routing settings; the form requests no credentials or provider settings.
6. Follow policy provisioning until the server reports the policy active. Keep
   **Saved**, **Provisioning**, **Active**, and **Failed** distinct. Show safe
   failure details and authorized retry, revision history, and rollback actions.
   Only after activation should the administrator share the browser entry URL.

### Approve a person's access

1. The person opens the application's browser entry URL and signs in with an
   existing identity-provider account. First login creates a pending request and
   displays the platform's pending page; the person has no application group yet.
   Account creation and password recovery remain identity-administrator tasks.
2. The project administrator opens **Human requests**, filtered to **Pending**.
   Each request identifies the target application, stable principal, request ID,
   creation time, expiry, and state. Display only profile attributes returned by
   the API; verify the intended recipient before approving.
3. Open the request, select one or more application groups, review the routes
   those groups permit, and choose **Approve**. Alternatively, choose **Reject**.
   No group is preselected, including for the administrator's own request.
4. Show **Request approved; membership provisioning** until the membership records
   are active. Approval alone does not establish usable access. The person retries
   after the application's session claims refresh or signs in again; matching
   routes then become accessible. A caller without a matching group remains denied.
5. In **Memberships**, inspect grants, add groups to approved requests, or revoke
   individual memberships. Show revocation pending until provider cleanup finishes
   and explain the maximum five-minute authorization-staleness bound. Rejected
   requests require explicit reopening; pending requests expire after 30 days.

### Request and approve machine access

1. In the consumer project's **Service access**, choose **Request access**, enter
   the request name, provider project, and target application, and acknowledge that
   the managed credential is visible to all components in the consumer project.
   The consumer chooses no provider groups and receives no usable credential yet.
2. The provider project's administrator opens **Incoming service requests**, reviews
   the consumer and target, selects groups accepted by the target's bearer-token
   routes, and approves or rejects the request.
3. Both owners follow approval and provisioning to **Active**. The consumer sees
   the provider URL, audience, and managed secret variable names, plus instructions
   for `client_credentials` and HTTPS egress to the issuer and provider. The UI
   never displays the service client secret or token. CI deployment credentials
   remain separate.
4. Provide consumer actions to rotate the credential and confirm adoption, with
   emergency rotation clearly explaining immediate old-client revocation. Either
   owner can revoke service access within its own project scope. Show operation
   and cleanup state rather than treating a submitted action as completion.

Every save and approval uses the current server resource version. If another
administrator changes it, reload the current resource and review again before
resubmitting. Loading, empty, denied, stale, and unavailable states remain distinct;
an unavailable request list must never appear as “no requests.”
