# Test-runner credentials

Back to the [Ansible directory guide](../README.md). Run commands from the
repository root.

The one-time `bootstrap-platform-test-runner.yml` playbook uses a human
platform-administrator token and writes the returned client credential to an
explicit mode-`0600` path on the controller. Create the protected parent
directory there first; the playbook checks that it is writable and that the
output file does not already exist before creating the one-time credential. The
repeatable `test-platform.yml` playbook consumes that protected file, creates
empty disposable projects and short-lived role personas, performs the first
deployment with a project CI credential, and cleans up without retaining the
human token. It also checks that deployment credentials cannot mutate secrets;
there is no separate CI-credential playbook.

## Local bootstrap without interactive login

After the local API is ready, an operator with Docker access can issue the same
protected credential format directly through the trusted API container:

```bash
python3 scripts/setup/bootstrap-test-runner.py \
  --confirm-environment http://127.0.0.1:8000
```

This defaults to a one-day credential in `.runtime/test-runner.json`. It refuses
existing output files and requires a private parent directory. The one-time
secret goes straight to a mode-`0600` file, never into command arguments or
terminal output. Select `--api` and the matching `--confirm-environment` when
using a different API origin. The platform records the bootstrap as a system
operator action, rather than a fabricated human login.

Docker access is privileged host administration. This command adds no public
bootstrap endpoint and is not available to a runner through the API. The
credential retains the existing platform-wide test-runner authority; use it in
the intended lab, not as a project-scoped production credential. It remains
subject to database-backed expiry and revocation on every API request.

Python runners accept this file through their existing `--operator-token-file`
option. They obtain and renew access tokens with client credentials and verify
that the file targets the selected API and configured issuer. Their preflight
uses `/platform/test-context`; root runner credential-management endpoints
remain restricted to human administrators. Project deployment credentials and
short-lived test personas keep their existing test-runner permissions.
Existing Ansible playbooks consume the same file.

Checks whose purpose is human authentication or human database access still
require a real human session. Machine personas are never treated as humans,
and this credential does not establish browser-login coverage.

## Revocation and expiry

`revoke-platform-test-runner.yml` removes exactly one active named runner.
Supply `platform_api_url` and a fresh human platform-administrator token; the
runner JSON and credential ID are not needed. It defaults to
`platform-acceptance-suite`; set `platform_test_runner_name` for another runner
and set `platform_confirm_test_runner_revocation` to that same name. The
playbook refuses no or ambiguous active matches, revokes Platform API access
before provider cleanup, and polls until cleanup is complete.

`verify-platform-test-runner-expiry.yml` tests a dedicated runner at its expiry
boundary. Set `platform_expiry_evidence_file` to an absolute, new path in a
private directory on the controller (directory mode `0700`). Use the same
protected runner configuration and evidence path in both phases:

1. Run `platform_expiry_drill_phase=active` shortly **before** the credential's
   recorded expiry. The returned JWT must remain valid beyond that expiry;
   running a day early fails this prerequisite. The check verifies actual API
   access and writes the held JWT and identity metadata to a mode-`0600` file.
1. Run `platform_expiry_drill_phase=expired` **after** credential expiry and
   **before** that JWT expires. The helper verifies matching credential
   identity, retries asynchronous provider cleanup within the JWT lifetime,
   requires token-endpoint rejection, and proves the held, unexpired JWT is
   denied by the Platform API with HTTP 403.

A wrong secret, an early expired-phase invocation, or an already expired JWT
cannot satisfy the test. Retain the private evidence only as long as needed;
it contains a bearer token. This is a timed lab check, not a routine CI test.
