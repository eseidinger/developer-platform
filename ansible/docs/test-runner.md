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
human token. `test-platform-ci-credential.yml` is the narrower compatibility
check for an already prepared project.

## Revocation and expiry

`revoke-platform-test-runner.yml` removes exactly one active named runner.
Supply `platform_api_url` and a fresh human platform-administrator token; the
runner JSON and credential ID are not needed. It defaults to
`platform-acceptance-suite`; set `platform_test_runner_name` for another runner
and set `platform_confirm_test_runner_revocation` to that same name. The
playbook refuses no or ambiguous active matches, revokes Platform API access
before provider cleanup, and polls until cleanup is complete.

`verify-platform-test-runner-expiry.yml` is a two-stage, scheduled-safe expiry
drill for a dedicated one-day test runner: run it once with
`platform_expiry_drill_phase=active`, then schedule the same protected
credential file after its recorded expiry with
`platform_expiry_drill_phase=expired`.
