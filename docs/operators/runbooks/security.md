# Security runbooks

Status: current administrator procedures reviewed against source.
Run commands from the repository root on the affected host. An Ansible
installation requires a privileged shell in `/opt/developer-platform`.

Use these procedures for grants, credentials, and other security-sensitive incidents. Preserve redacted audit evidence and coordinate identity-provider actions separately.

## Compromised credential or access revocation

Revoke a project or platform grant through the authorized API, then verify the affected principal's next request returns `403` and inspect the corresponding redacted audit event. Token expiry/revocation at the identity provider is a separate control; platform authorization does not wait for a token to expire after a grant is removed. The one-time `PLATFORM_BOOTSTRAP_SUBJECT` is host configuration, not an API credential; remove it after first startup.

Preserve `DATABASE_KEY` during recovery. Changing it changes derived Secrets but does not update existing PostgreSQL role passwords; rotation requires coordinated role-password and workload-Secret changes. Follow the [platform configuration notes](../../../platform/README.md#configuration). The [controller rotation procedure](../lifecycle.md#rotate-the-controller-credential) describes the infrastructure credential separately. Never include secret values in incident records.
