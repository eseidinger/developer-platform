# Script tests

Tests are organized by execution environment. A filename prefix such as `check-`
or `verify-` describes an existing command; it does not define a separate kind
of test or promise that a command is read-only.

- **`unit/`**: offline configuration and deployment contracts using mocks and
  temporary checkouts. These run through unittest discovery.
- **`components/`**: focused integration checks for stores, observability, AI,
  and application bindings. Read the script prerequisites: some launch
  disposable Docker services; some use a configured database or model provider.
- **`platform/`**: smoke, access, isolation, data preservation, configuration,
  secret, log, and retirement scenarios against a running platform. Some
  commands offer a read-only `plan`; live execution must be explicitly selected.
  Other commands act immediately and require a disposable project or lab.
- **`support/`**: importable fixture implementation used by component tests,
  including disposable volumes, store consoles, analytics, and recovery. Import
  these modules; they are not independent operator commands.

The `platform/` directory includes disruptive drills. In particular,
`interrupted_provisioning.py` interrupts shared cluster/API services, and
`retirement_drill.py` retires its selected project. Never run the entire
platform directory as a batch. Consult the
[acceptance procedure](../../docs/operators/validation/acceptance.md) for scope,
credentials, cleanup, and retained evidence.

From the repository root, offline tests are:

```bash
python3 -m unittest discover -s scripts/tests/unit -v
```

Most individual component/platform commands should run with the API environment:

```bash
uv run --project platform/app python \
  scripts/tests/platform/check-hosted-access.py plan
```

API unit tests remain beside the API under `platform/app/tests`. Ansible unit
tests and live platform playbooks have the same environment distinction under
[`ansible/tests/`](../../ansible/tests/README.md).
