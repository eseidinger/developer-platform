# Security runbooks

Status: current administrator procedures reviewed against source.
Run commands from the repository root on the affected host. An Ansible
installation requires a privileged shell in `/opt/developer-platform`.

Use these procedures for grants, credentials, and other security-sensitive incidents. Preserve redacted audit evidence and coordinate identity-provider actions separately.

## Compromised credential or access revocation

For access to the Platform API, revoke a project or platform grant through the
authorized API, then verify the affected principal's next request returns `403`
and inspect the corresponding redacted audit event. This does not revoke hosted
application-group memberships or service access; those are separate resources
below. Token expiry/revocation at the identity provider is a separate control;
platform authorization does not wait for a token to expire after a grant is
removed. The one-time `PLATFORM_BOOTSTRAP_SUBJECT` is host configuration, not an
API credential; remove it after first startup.

Preserve `DATABASE_KEY` during recovery. Changing it changes derived Secrets but does not update existing PostgreSQL role passwords; rotation requires coordinated role-password and workload-Secret changes. Follow the [platform configuration notes](../../../platform/README.md#configuration). The [controller rotation procedure](../lifecycle.md#rotate-the-controller-credential) describes the infrastructure credential separately. Never include secret values in incident records.

## Hosted application revocation and rotation

Use an authorized Platform API principal, not the hosted application's service
token. Read the resource first and use its current quoted version `ETag` as
`If-Match`; poll asynchronous work through its returned `status_url`. See the
[hosted API guide](../../developers/api.md#hosted-application-access) for bodies,
permissions and concurrency errors.

- Human authority: remove every affected application membership using
  `DELETE /v1/projects/{provider}/application-group-memberships/{id}` as the
  provider project administrator. Verify denial using an already open browser
  session; removing a platform grant alone is insufficient.
- Machine authority: revoke the service-access request using
  `DELETE /v1/projects/{owner}/service-access-requests/{id}`. The provider's
  project administrator or authorized consumer owner can revoke it in their own
  scope. Verify denial with an already issued token and inspect provider cleanup;
  do not wait for token expiry or expose the managed secret.
- Compromised consumer credential with continuing access intended: the consumer
  owner invokes `POST /{id}/rotate` on its service-access request with
  `{"emergency":true}`. Old-client authority has no overlap; wait for the
  replacement operation and confirm application adoption before declaring
  recovery. For routine rotation use `{"emergency":false}` and explicitly
  confirm adoption using `POST /{id}/confirm`; normal overlap is at most 24 hours.

Local pending revocation excludes authority from the next compiled snapshot
while provider cleanup retries durably. The accepted authorization-staleness
maximum is five minutes; dependency failure must not extend snapshot expiry.
EV-45 observed human and machine denial with existing sessions/tokens in
2.357/2.310 seconds under healthy dependencies, not an outage-bound guarantee.
See the [dated evidence and deferrals](../validation/access-and-authorization.md#executed-hosted-access-core-acceptance-october-11-2026).

For restored catalogs or uncertain identity-provider state, keep public
application traffic quarantined and follow the
[hosted-access recovery procedure](../identity-and-access.md#hosted-application-access-installation-and-recovery).
Do not infer successful restore or reconciliation from the core acceptance run.
