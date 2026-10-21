# Local application HTTPS validation: October 21, 2026

Enabled `LOCAL_APPLICATION_HTTPS_ENABLED=true` in the local installation and
deployed the dedicated private gateway, scoped component hostname resolution,
public CA distribution, and TCP/443 egress. The main edge remains bound to host
loopback; the workload gateway publishes no host ports.

The existing hosted-access runner completed with `result=core-passed`, all 38
assertions passing, and `cleanup=completed-data-retained`. Its private evidence
is `.runtime/hosted-access/d2ea8ee3c1ac/report.json`. This run used the full core
scenario, including its workload egress declarations; no host-only subset was
substituted.

Two projects each deployed a public API and private worker, with explicit named
PostgreSQL bindings. The consumer API obtained its managed client-credentials
token and called the provider's public HTTPS identity endpoint from inside its
container. Certificate and hostname verification stayed enabled. Returned
identity and synthetic correlation matched the approved service principal.

The runner also verified human approval and bounded claim refresh, secure
cookies, CSRF, machine audience/group restrictions, forged-header replacement,
direct-backend isolation from both projects, unrelated egress denial, fixed
egress CIDRs, isolated PostgreSQL state and restart persistence, policy rollback,
normal/emergency credential rotation, and revocation with existing sessions and
tokens. Disposable projects were retired and test identities removed; retained
store data was not purged. No managed test namespaces remained afterward.

The isolated production gateway fixture passed verified TLS, issuer/application
routing, identity admin/master/account denial, console denial, and strict SNI/Host
matching. Its permissive synthetic upstreams ensure rejected requests test the
gateway itself. The fixture is included in repository validation CI.

Regression suites passed: 554 API tests with 14 declared skips, 53 script tests,
25 Ansible tests, and 92 platform-runner tests with two declared skips. Targeted
tests cover the shared-IP host-alias grouping discovered
by live server-side apply. Changed Python, YAML, shell, Markdown, Compose, and
Caddy configuration passed applicable repository checks. The trust preparation
entry point also ran successfully with Python site packages disabled.

This closes the workload-to-public HTTPS and network-isolation gap recorded in
the [earlier local validation](local-2026-10-21.md). The broader acceptance gate
remains open for its declared backup, outage, timed expiry/retention, recovery,
and external use-case checks. No live AI calls were made for this follow-up.

Configuration, trust rotation, disabling the mode, and its shared-gateway
network boundary are documented in the
[local HTTPS operator guide](../local-application-https.md).
