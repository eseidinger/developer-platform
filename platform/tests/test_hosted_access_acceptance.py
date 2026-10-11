"""Harness safety and fixture checks. No test contacts or mutates the live lab."""
import contextlib
import io
import json
import os
import socket
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx2 as httpx
import jwt
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acceptance import fixture, harness as h
from app.access_contract import Governance, PolicyCreate
from app.spec import ApplicationEnvelopeV1Alpha2


RUN = "0123456789ab"
IMAGE = "ghcr.io/example/fixture@sha256:" + "a" * 64
API = "http://127.0.0.1:8000"
ISSUER = "https://identity.example.invalid/realms/platform"


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "run"

    def journal(self):
        return h.Journal(self.directory, API, RUN)

    def args(self, *extra):
        return h.parser().parse_args(["--fixture-image", IMAGE, "--run-id", RUN, *extra])

    def test_plan_is_offline_and_has_no_file_side_effects(self):
        with patch.object(h, "Keycloak") as provider, patch.object(h, "API") as api, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(h.main(["plan", "--fixture-image", IMAGE, "--run-id", RUN, "--output", str(self.directory)]), 0)
        plan = json.loads(output.getvalue())
        self.assertFalse(plan["mutates"])
        self.assertFalse(plan["gateClosed"])
        self.assertFalse(self.directory.exists())
        api.assert_not_called()
        provider.assert_not_called()

    def test_live_run_requires_exact_origin_confirmation_before_access(self):
        for confirmation in (None, "https://elsewhere.example", API + "/"):
            with self.subTest(confirmation=confirmation), patch.object(h, "settings") as config:
                args = self.args("run", "--operator-token-file", "/unused")
                args.confirm_environment = confirmation
                with self.assertRaisesRegex(h.DrillError, "explicit_environment_confirmation_required"):
                    h.validate(args)
                config.assert_not_called()

    def test_requires_digest_and_scoped_names(self):
        for image in ("example/fixture:latest", "example/fixture@sha256:abc", "secret\nvalue"):
            args = self.args()
            args.fixture_image = image
            with self.assertRaisesRegex(h.DrillError, "digest_pinned"):
                h.validate(args)
        for name in ("../../project", "", "ABCDEF012345", "0123456789abcdef"):
            with self.assertRaises(h.DrillError):
                h.project_names(name)

    def test_cleanup_requires_explicit_existing_run_id(self):
        args = h.parser().parse_args(["cleanup"])
        with self.assertRaisesRegex(h.DrillError, "cleanup_requires_run_id"):
            h.validate(args)

    def test_untrusted_origins_and_token_endpoints_rejected(self):
        for url in ("http://api.example", "https://name:password@api.example", "https://api.example/path", "https://api.example?token=secret"):
            with self.assertRaises(h.DrillError):
                h.origin(url)
        for url in ("http://identity.example/token", "https://u:p@identity.example/token"):
            with self.assertRaisesRegex(h.DrillError, "unsafe_token_endpoint"):
                h.MachineTokens({"TOKEN_URL": url})

    def test_fixture_declarations_match_current_contract(self):
        for role, project in h.project_names(RUN).items():
            body = h.declaration(project, role, IMAGE, RUN, "https://provider.example", ISSUER)
            with patch("app.spec.resolve_egress_dns"):
                envelope = ApplicationEnvelopeV1Alpha2.model_validate(body)
            self.assertEqual(len(envelope.spec.components), 2)
            self.assertEqual(sum(c.exposure == "public" for c in envelope.spec.components), 1)
            self.assertEqual(envelope.spec.components[1].outbound, [])
            self.assertEqual(envelope.spec.resources[0].deletionPolicy, "retain")
            self.assertNotIn("identity", body["spec"])

    def test_policy_matches_contract_without_application_special_cases(self):
        policy = PolicyCreate.model_validate(h.access_policy("readers", "humans", "administrators"))
        self.assertEqual(policy.defaultDecision, "deny")
        self.assertEqual({r.authentication.mode for r in policy.routes}, {"bearer-token", "browser-session"})
        self.assertFalse(policy.identityAttributes.email)

    def test_journal_private_whitelisted_evidence_and_resume(self):
        journal = self.journal()
        with contextlib.redirect_stdout(io.StringIO()):
            journal.check("safe-check", True, httpStatus=200, seconds=0.2)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        for name in ("state.json", "report.json"):
            self.assertEqual(stat.S_IMODE((self.directory / name).stat().st_mode), 0o600)
        resumed = h.Journal(self.directory, API, RUN, resume=True)
        self.assertFalse(resumed.report["gateClosed"])
        for values in ({"token": "private-secret"}, {"responseBody": {"secret": "private-secret"}}, {"not-safe": 1}):
            with self.assertRaisesRegex(h.DrillError, "unsafe_evidence"):
                journal.check("unsafe", True, **values)
        self.assertNotIn("private-secret", (self.directory / "report.json").read_text())
        with self.assertRaisesRegex(h.DrillError, "journal_scope_mismatch"):
            h.Journal(self.directory, "https://other.example", RUN, resume=True)

    def test_journal_rejects_existing_run_and_symlink(self):
        self.journal()
        with self.assertRaisesRegex(h.DrillError, "run_directory_exists"):
            self.journal()
        target = self.directory / "report.json"
        target.unlink()
        target.symlink_to(self.directory / "state.json")
        with self.assertRaisesRegex(h.DrillError, "unsafe_output_file"):
            self.journal_for_existing().save()

    def journal_for_existing(self):
        value = object.__new__(h.Journal)
        value.directory = self.directory
        value.state, value.report = {}, {}
        return value

    def test_private_inputs_require_owner_only_permissions(self):
        path = Path(self.temporary.name) / "input"
        path.write_text("private-secret")
        path.chmod(0o644)
        with self.assertRaisesRegex(h.DrillError, "private_file_permissions"):
            h.private_text(path)
        path.chmod(0o600)
        self.assertEqual(h.private_text(path), "private-secret")

    def test_wait_has_real_bound_and_no_sleep_beyond_poll_interval(self):
        clock = [0.0]
        sleeps = []
        def sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds
        with self.assertRaisesRegex(h.DrillError, "not_ready"):
            h.wait_for(lambda: False, "not_ready", 5, clock=lambda: clock[0], sleep=sleep)
        self.assertEqual(clock[0], 5)
        self.assertLessEqual(max(sleeps), 2)

    def test_operation_cannot_exfiltrate_operator_token(self):
        api = h.API(API, h.Tokens("private-secret"))
        self.addCleanup(api.http.close)
        with self.assertRaisesRegex(h.DrillError, "invalid_operation_url"):
            api.operation({"status_url": "https://attacker.example/collect"})

    def test_api_optimistic_concurrency_and_safe_errors(self):
        api = h.API(API, h.Tokens("private-secret"))
        self.addCleanup(api.http.close)
        seen = []
        def respond(request):
            seen.append(request)
            return httpx.Response(409, json={"detail": "private-secret"})
        api.http.close()
        api.http = httpx.Client(transport=httpx.MockTransport(respond))
        with self.assertRaisesRegex(h.DrillError, "^control_api_http_409$"):
            api.request("PUT", "/v1/resource", {}, etag=7, key="idempotent")
        self.assertEqual(seen[0].headers["If-Match"], '"7"')
        self.assertEqual(seen[0].headers["Idempotency-Key"], "idempotent")

    def test_login_password_never_sent_to_untrusted_form(self):
        page = httpx.Response(200, text='<form id="kc-form-login" action="https://attacker.example/login-actions/x"></form>')
        http = Mock()
        with self.assertRaisesRegex(h.DrillError, "untrusted_login_destination"):
            h.submit_login(http, page, ISSUER, "synthetic", "private-secret")
        http.post.assert_not_called()

    def test_refresh_renewal_stays_in_memory(self):
        expired = jwt.encode({"exp": time.time() - 1}, "test-only-" * 4, algorithm="HS256")
        client = Mock()
        client.refresh.return_value = ("renewed-secret", "new-refresh-secret")
        tokens = h.Tokens(expired, client, "old-refresh-secret")
        self.assertEqual(tokens.get(), "renewed-secret")
        client.refresh.assert_called_once_with("old-refresh-secret")

    def test_cleanup_rejects_foreign_project_before_mutation(self):
        journal = self.journal()
        journal.state["createdProjects"] = ["real-project"]
        api, keycloak = Mock(), Mock()
        with self.assertRaisesRegex(h.DrillError, "cleanup_scope_mismatch"):
            h.cleanup(journal, api, keycloak)
        api.request.assert_not_called()
        keycloak.admin.assert_not_called()

    def test_cleanup_refuses_changed_fixture_configuration(self):
        journal = self.journal()
        project = journal.state["projects"]["provider"]
        journal.state.update(createdProjects=[project], image=IMAGE)
        api = Mock()
        api.request.return_value = [{"name": project, "status": "active", "spec": {"configuration": {"ACCEPTANCE_RUN_ID": "different"}}}]
        with self.assertRaisesRegex(h.DrillError, "cleanup_project_changed"):
            h.cleanup(journal, api, Mock())
        self.assertEqual(api.request.call_count, 1)

    def test_cleanup_only_retires_and_never_purges_database(self):
        journal = self.journal()
        project = journal.state["projects"]["provider"]
        journal.state.update(createdProjects=[project], image=IMAGE)
        calls = []
        def request(method, path, body=None, **kwargs):
            calls.append((method, path, body))
            if path == "/projects":
                return [{"name": project, "status": "active", "spec": {"configuration": {"ACCEPTANCE_RUN_ID": RUN}, "components": [{"image": IMAGE}]}}]
            if path.endswith("retirement-preview"):
                return {"blockers": [], "scope_token": "scope"}
            if path.endswith("/retire"):
                return {"status": "retired"}
            return {"credentials": []}
        h.cleanup(journal, Mock(request=request), Mock())
        self.assertEqual(journal.report["cleanup"], "completed-data-retained")
        self.assertFalse(any("purge" in path for _, path, _ in calls))
        self.assertEqual(calls[2][2], {"confirm_name": project, "scope_token": "scope"})

    def test_global_recovery_rejects_even_foreign_retired_project(self):
        journal = self.journal()
        api = Mock()
        api.request.return_value = [{"name": "other-project", "status": "retired"}]
        drill = h.Drill(self.args(), journal, api, Mock(), Mock())
        self.addCleanup(drill.public.close)
        self.addCleanup(drill.browser.close)
        with self.assertRaisesRegex(h.DrillError, "recovery_requires_empty_lab"):
            drill.isolated_lab()
        self.assertEqual(api.request.call_count, 1)

    def run_mocked_main(self, *, fail=False, cleanup_fail=False):
        argv = ["run", "--fixture-image", IMAGE, "--run-id", RUN, "--output", str(self.directory),
                "--confirm-environment", API, "--operator-token-file", "/private/session"]
        with patch.object(h, "settings", return_value={"APPS_DOMAIN": "apps.example.invalid"}), \
             patch.object(h, "Keycloak"), patch.object(h, "operator_tokens"), patch.object(h, "API"), \
             patch.object(h, "Drill") as drill, patch.object(h, "cleanup") as cleanup, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            if fail:
                drill.return_value.run.side_effect = ValueError("private-secret")
            if cleanup_fail:
                cleanup.side_effect = ValueError("another-secret")
            result = h.main(argv)
            cleanup.assert_called_once()
        return result, output.getvalue(), json.loads((self.directory / "report.json").read_text())

    def test_failure_always_attempts_cleanup_and_redacts_exception(self):
        result, output, report = self.run_mocked_main(fail=True)
        self.assertEqual(result, 1)
        self.assertEqual(report["errorCode"], "dependency_failure")
        self.assertNotIn("private-secret", output + json.dumps(report))
        self.assertFalse(report["gateClosed"])

    def test_cleanup_failure_is_not_success(self):
        result, output, report = self.run_mocked_main(cleanup_fail=True)
        self.assertEqual(result, 1)
        self.assertEqual(report["cleanup"], "incomplete-retry-required")
        self.assertNotIn("another-secret", output + json.dumps(report))

    def test_core_pass_does_not_close_full_acceptance_gate(self):
        result, _, report = self.run_mocked_main()
        self.assertEqual(result, 0)
        self.assertEqual(report["result"], "core-passed")
        self.assertFalse(report["gateClosed"])
        self.assertIn("real-backup-restore", report["deferred"])

    def test_core_orchestration_skips_optional_mutations_and_preserves_deferrals(self):
        journal = self.journal()
        drill = h.Drill(self.args(), journal, Mock(), Mock(), Mock())
        self.addCleanup(drill.public.close)
        self.addCleanup(drill.browser.close)
        names = ("setup", "service", "human_checks", "machine_checks", "network_checks", "persistence",
                 "policy_checks", "rotate", "expiry", "recovery", "revocations")
        for name in names:
            setattr(drill, name, Mock())
        human = {"id": "synthetic"}
        drill.setup.return_value = human, "private-secret"
        drill.service.side_effect = [("service", Mock()), ("reverse-service", Mock())]
        drill.human_checks.return_value = "stable-human"
        drill.rotate.side_effect = [("rotated", "replacement"), ("emergency", "emergency-replacement")]
        drill.public_call = Mock(return_value=Mock(status_code=200))
        with patch.object(h, "wait_for", side_effect=lambda check, *args: check()):
            drill.run()
        self.assertEqual(drill.service.call_args_list[0].args, ("consumer", "provider"))
        self.assertEqual(drill.rotate.call_count, 2)
        drill.expiry.assert_not_called()
        drill.recovery.assert_not_called()
        drill.revocations.assert_called_once_with("emergency", "emergency-replacement", "stable-human")
        self.assertIn("held-machine-token-expiry", journal.report["deferred"])
        self.assertIn("recovery-reconciliation-rehearsal", journal.report["deferred"])

    def test_setup_payloads_validate_against_real_platform_contracts(self):
        journal = self.journal()
        args = self.args()
        api = Mock(url=API)
        api.request.side_effect = lambda method, path, *a, **k: ({"hostedApplicationAccess": {
            "modes": ["browser-session", "bearer-token"]}} if path == "/v1/capabilities" else
            {"credential_id": str(uuid4()), "client_id": "synthetic-client", "client_secret": "private-secret",
             "token_endpoint": ISSUER + "/protocol/openid-connect/token"})
        owner = Mock()
        owner.operation.return_value = {"revision": 1}
        declarations = []
        def owned_request(method, path, body=None, **kwargs):
            if path.endswith("/governance"):
                Governance.model_validate(body)
                return {}
            if path.endswith("/application-groups"):
                return {"id": "grp_" + uuid4().hex}
            if path.endswith("/access-policy"):
                if method == "PUT":
                    PolicyCreate.model_validate(body)
                    return {"operation_id": str(uuid4())}
                return {"spec": {}}
            with patch("app.spec.resolve_egress_dns"):
                ApplicationEnvelopeV1Alpha2.model_validate(body)
            declarations.append(body)
            return {"operation_id": str(uuid4()), "status_url": "/v1/operations/" + str(uuid4())}
        owner.request.side_effect = owned_request
        kube = Mock()
        kube.obj.return_value = {"spec": {"template": {"spec": {"containers": [{"image": IMAGE,
            "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "250m", "memory": "128Mi"}}}]}}}}
        provider = Mock(issuer=ISSUER)
        drill = h.Drill(args, journal, api, provider, kube)
        self.addCleanup(drill.public.close)
        self.addCleanup(drill.browser.close)
        drill.bootstrap = Mock(return_value=({"id": "synthetic"}, "private-secret"))
        with patch.object(h, "API", return_value=owner), contextlib.redirect_stdout(io.StringIO()):
            drill.setup()
        self.assertEqual(len(declarations), 2)
        self.assertEqual(journal.report["fixture"]["revisions"], {"provider": 1, "consumer": 1})
        self.assertNotIn("private-secret", json.dumps(journal.state) + json.dumps(journal.report))

    def test_expiry_holds_original_token_instead_of_renewing(self):
        journal = self.journal()
        drill = h.Drill(self.args(), journal, Mock(), Mock(), Mock())
        self.addCleanup(drill.public.close)
        self.addCleanup(drill.browser.close)
        token = jwt.encode({"exp": time.time() + 120}, "synthetic-key-" * 3, algorithm="HS256")
        machines = Mock()
        machines.get.return_value = token
        drill.public_call = Mock(return_value=Mock(status_code=401))
        with patch.object(h, "wait_for", side_effect=lambda check, *args: check()), contextlib.redirect_stdout(io.StringIO()):
            drill.expiry(machines)
        machines.get.assert_called_once()
        drill.public_call.assert_called_once_with("/api/identity", token)

    def network_result(self, **changes):
        return {"resolved": True, "addresses": ["192.0.2.1"], "connected": 0,
                "refused": 0, "timedOut": 0, "unexpectedErrors": 0,
                "dnsError": False, "addressMismatch": False, **changes}

    def controlled_network_check(self, result, *, before=None, after=None):
        journal = h.Journal(self.directory / uuid4().hex, API, RUN)
        drill = h.Drill(self.args(), journal, Mock(), Mock(), Mock())
        self.addCleanup(drill.public.close)
        self.addCleanup(drill.browser.close)
        control = Mock(side_effect=[before if before is not None else self.network_result(connected=1),
                                    after if after is not None else self.network_result(connected=1)])
        probe = Mock(return_value=result)
        error = None
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                drill.controlled_network_check("controlled-denial", "example.invalid", 443,
                                               probe, control, ip_versions=[4])
            except h.DrillError as exc:
                error = str(exc)
        return journal.report["checks"][-1], error, probe, control

    def test_refusal_and_timeout_need_healthy_same_address_controls(self):
        for outcome in ("refused", "timedOut"):
            with self.subTest(outcome=outcome):
                result = self.network_result(**{outcome: 1})
                self.assertFalse(h.network_control_ready(result))  # Alone, not proof of enforcement.
                check, error, probe, control = self.controlled_network_check(result)
                self.assertIsNone(error)
                self.assertEqual(check["result"], "passed")
                self.assertEqual(check[outcome], 1)
                self.assertTrue(check["controlBefore"] and check["controlAfter"])
                self.assertEqual(check["controlBeforeConnected"], 1)
                self.assertEqual(check["controlAfterConnected"], 1)
                self.assertTrue(check["ipvFour"])
                self.assertFalse(check["ipvSix"])
                pinned = {"host": "example.invalid", "port": 443, "ipVersions": [4], "expectedAddresses": ["192.0.2.1"]}
                probe.assert_called_once_with(pinned)
                self.assertEqual(control.call_args_list[1].args, (pinned,))
                self.assertNotIn("192.0.2.1", json.dumps(check))

    def test_unavailable_control_or_changed_dns_cannot_pass_isolation(self):
        for failure in (self.network_result(refused=1), self.network_result(timedOut=1),
                        self.network_result(resolved=False, addresses=[], dnsError=True),
                        self.network_result(connected=1, addresses=["192.0.2.2"]),
                        self.network_result(addressMismatch=True)):
            with self.subTest(failure=failure):
                check, error, probe, _ = self.controlled_network_check(self.network_result(refused=1), after=failure)
                self.assertEqual(error, "controlled-denial")
                self.assertEqual(check["result"], "failed")
                self.assertFalse(check["controlAfter"])
                probe.assert_called_once()
        check, error, probe, control = self.controlled_network_check(
            self.network_result(refused=1), before=self.network_result(refused=1))
        self.assertEqual(error, "controlled-denial")
        self.assertFalse(check["controlBefore"])
        self.assertEqual(check["controlBeforeRefused"], 1)
        probe.assert_not_called()
        self.assertEqual(control.call_count, 1)

    def test_success_dns_error_unexpected_error_or_partial_denial_cannot_pass(self):
        for result in (self.network_result(connected=1), self.network_result(unexpectedErrors=1),
                       self.network_result(resolved=False, addresses=[], dnsError=True),
                       self.network_result(addressMismatch=True), self.network_result(),
                       self.network_result(refused=1, connected=1),
                       self.network_result(refused=1, addresses=["192.0.2.2"])):
            with self.subTest(result=result):
                check, error, _, _ = self.controlled_network_check(result)
                self.assertEqual(error, "controlled-denial")
                self.assertEqual(check["result"], "failed")

    def test_every_controlled_address_must_be_denied(self):
        addresses = ["192.0.2.1", "192.0.2.2"]
        positive = self.network_result(addresses=addresses, connected=2)
        for counts, passes in (({"refused": 2}, True), ({"refused": 1, "timedOut": 1}, True),
                               ({"refused": 1, "connected": 1}, False), ({"refused": 1}, False)):
            with self.subTest(counts=counts):
                check, error, _, _ = self.controlled_network_check(
                    self.network_result(addresses=addresses, **counts), before=positive, after=positive)
                self.assertEqual(check["result"], "passed" if passes else "failed")
                self.assertEqual(error, None if passes else "controlled-denial")

    def probe_result(self, failures, *, answers=None, body=None, dns_failure=None):
        answers = answers if answers is not None else [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))]
        sockets = [Mock() for _ in failures]
        for sock, failure in zip(sockets, failures):
            sock.connect.side_effect = failure
        with patch("socket.getaddrinfo", return_value=answers, side_effect=dns_failure), \
             patch("socket.socket", side_effect=sockets) as create_socket, \
             patch("sys.stdin", io.StringIO(json.dumps(body or {"host": "example.invalid", "port": 443, "ipVersions": [4]}))), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            try:
                exec(h.NETWORK_PROBE, {})
            except SystemExit:
                pass
        self.assertNotIn("private-secret", output.getvalue())
        for sock in sockets:
            sock.close.assert_called_once()
        return json.loads(output.getvalue()), create_socket

    def test_probe_classifies_connect_timeout_refusal_and_other_errors(self):
        for failure, field in ((None, "connected"), (TimeoutError(), "timedOut"),
                               (ConnectionRefusedError(), "refused"), (OSError("private-secret"), "unexpectedErrors")):
            with self.subTest(field=field):
                result, _ = self.probe_result([failure])
                self.assertEqual(result, self.network_result(**{field: 1}))

    def test_probe_dns_failure_and_address_change_do_not_attempt_connect(self):
        result, create = self.probe_result([], dns_failure=socket.gaierror("private-secret"))
        self.assertFalse(result["resolved"])
        self.assertTrue(result["dnsError"])
        create.assert_not_called()
        result, create = self.probe_result([], body={"host": "example.invalid", "port": 443,
                                                   "ipVersions": [4], "expectedAddresses": ["192.0.2.2"]})
        self.assertTrue(result["addressMismatch"])
        create.assert_not_called()

    def test_probe_deduplicates_answers_and_checks_all_supported_families(self):
        ipv_four = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))
        ipv_six = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 443, 0, 0))
        for versions in ([4], [4, 6]):
            result, create = self.probe_result([ConnectionRefusedError()] * len(versions),
                answers=[ipv_four, ipv_four, ipv_six], body={"host": "example.invalid", "port": 443, "ipVersions": versions})
            self.assertEqual(create.call_count, len(versions))
            self.assertEqual(result["refused"], len(versions))
            self.assertEqual(result["addresses"], ["192.0.2.1"] + (["2001:db8::1"] if 6 in versions else []))

    def test_probe_records_mixed_address_outcomes_without_hiding_connect(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("192.0.2.1", "192.0.2.2")]
        result, _ = self.probe_result([ConnectionRefusedError(), None], answers=answers)
        self.assertEqual(result["connected"], 1)
        self.assertEqual(result["refused"], 1)
        check, error, _, _ = self.controlled_network_check(result)
        self.assertEqual(error, "controlled-denial")
        self.assertEqual(check["connected"], 1)

    def test_host_control_uses_real_disposable_loopback_listener(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(4)
            body = {"host": "127.0.0.1", "port": listener.getsockname()[1], "ipVersions": [4]}
            result = h.host_network_probe(body)
            self.assertTrue(h.network_control_ready(result))
            self.assertEqual(result["addresses"], ["127.0.0.1"])
        # Bind but don't listen: the same probe must not call refusal a healthy control.
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            result = h.host_network_probe({**body, "port": unavailable.getsockname()[1]})
            self.assertEqual(result["refused"], 1)
            self.assertFalse(h.network_control_ready(result))

    def test_kubernetes_controls_use_authorizer_and_ready_fixture_pod_families(self):
        kube = h.Kube("kubectl")
        body = {"host": "fixture.invalid", "port": 8080, "ipVersions": [4]}
        with patch.object(kube, "call", return_value=json.dumps(self.network_result(connected=1))) as call:
            self.assertTrue(h.network_control_ready(kube.authorizer_probe(body)))
        call.assert_called_once_with("-n", "platform-access", "exec", "-i", "deploy/authorizer",
            "--", "python", "-c", h.NETWORK_PROBE, data=json.dumps(body), timeout=45)
        ready = {"metadata": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}],
                                             "podIPs": [{"ip": "192.0.2.1"}, {"ip": "2001:db8::1"}]}}
        deleting = {"metadata": {"deletionTimestamp": "now"}, "status": ready["status"]}
        with patch.object(kube, "call", return_value=json.dumps({"items": [ready, deleting]})) as call:
            self.assertEqual(kube.pod_ip_versions(h.project_names(RUN)["consumer"], "api"), [4, 6])
        call.assert_called_once_with("-n", "project-" + h.project_names(RUN)["consumer"], "get", "pods",
                                    "-l", "platform.example/component=api", "-o", "json")
        with patch.object(kube, "call", return_value=json.dumps({"items": [deleting]})), \
             self.assertRaisesRegex(h.DrillError, "fixture_network_families_unavailable"):
            kube.pod_ip_versions(h.project_names(RUN)["consumer"], "api")

    def test_network_checks_wire_backend_controls_to_authorizer_and_egress_to_host(self):
        journal = self.journal()
        kube = Mock()
        kube.pod_ip_versions.return_value = [4]
        kube.authorizer_probe.return_value = self.network_result(connected=1)
        kube.exec_json.return_value = self.network_result(refused=1)
        kube.obj.return_value = {"spec": {"egress": [{"to": [{"ipBlock": {"cidr": "192.0.2.10/32"}}]}]}}
        drill = h.Drill(self.args(), journal, Mock(), Mock(), kube)
        self.addCleanup(drill.public.close)
        self.addCleanup(drill.browser.close)
        with patch.object(h, "host_network_probe", return_value=self.network_result(connected=1)) as host, \
             contextlib.redirect_stdout(io.StringIO()):
            drill.network_checks()
        self.assertEqual(kube.authorizer_probe.call_count, 4)
        self.assertEqual(host.call_count, 2)
        self.assertEqual([(c.args[0], c.args[1]) for c in kube.exec_json.call_args_list],
                         [(drill.projects["provider"], "worker"), (drill.projects["consumer"], "worker"),
                          (drill.projects["consumer"], "api")])
        self.assertTrue(all(check["result"] == "passed" for check in journal.report["checks"]))
        self.assertNotIn("192.0.2.1", json.dumps(journal.report["checks"]))

    def test_operator_session_supports_only_existing_public_clients(self):
        for client_id in ("platform-cli", "platform-portal"):
            self.assertEqual(h.OperatorRefresh(Mock(), client_id).client_id, client_id)
        with self.assertRaisesRegex(h.DrillError, "unsupported_operator_client"):
            h.OperatorRefresh(Mock(), "unexpected-client")

    def test_missing_confirmation_stops_main_before_any_environment_read(self):
        with patch.object(h, "settings") as config, contextlib.redirect_stdout(io.StringIO()) as output:
            code = h.main(["run", "--fixture-image", IMAGE])
        self.assertEqual(code, 1)
        self.assertIn("explicit_environment_confirmation_required", output.getvalue())
        config.assert_not_called()


class FixtureTests(unittest.TestCase):
    def test_identity_reports_presence_never_credential_values(self):
        result = fixture.identity({"Authorization": "Bearer private-secret", "Cookie": "__Host-platform-session=private-cookie",
            "X-Platform-Principal-Id": "synthetic-principal", "X-Platform-Principal-Kind": "service"})
        self.assertTrue(result["authorizationPresent"])
        self.assertTrue(result["platformCookiePresent"])
        self.assertNotIn("private-secret", json.dumps(result))
        self.assertNotIn("private-cookie", json.dumps(result))

    def test_probe_requires_exactly_one_managed_binding(self):
        with patch.dict(os.environ, {"ACCEPTANCE_RUN_ID": RUN}, clear=True), self.assertRaises(ValueError):
            fixture.probe()

    def test_probe_refuses_unencrypted_endpoints_before_sending_secrets(self):
        with patch.dict(os.environ, {"ACCEPTANCE_RUN_ID": RUN, "ACCESS_ABC_CLIENT_ID": "fixture", "PROVIDER_URL": "http://provider.example",
            "ACCESS_ABC_TOKEN_URL": "https://identity.example/token"}, clear=True), patch.object(fixture, "urlopen") as open_url:
            with self.assertRaises(ValueError):
                fixture.probe()
            open_url.assert_not_called()

    def test_fixture_http_contract_and_safe_dependency_failure(self):
        with patch.dict(os.environ, {"ACCEPTANCE_RUN_ID": RUN}), patch.object(fixture, "state", return_value="synthetic") as state:
            server = fixture.ThreadingHTTPServer(("127.0.0.1", 0), fixture.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with httpx.Client(base_url="http://127.0.0.1:" + str(server.server_port), trust_env=False) as client:
                    self.assertEqual(client.get("/health/ready").json()["runId"], RUN)
                    identity = client.get("/api/identity", headers={"X-Platform-Principal-Kind": "service"})
                    self.assertEqual(identity.json()["principal"]["Kind"], "service")
                    self.assertEqual(client.post("/api/state", json={"marker": "x" * 101}).status_code, 400)
                    state.side_effect = ValueError("private-secret")
                    failed = client.get("/api/state")
                    self.assertEqual(failed.status_code, 503)
                    self.assertNotIn("private-secret", failed.text)
                    self.assertEqual(client.head("/api/identity").content, b"")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

    @unittest.skipUnless(os.environ.get("ACCESS_FIXTURE_TEST_DSN"), "Set ACCESS_FIXTURE_TEST_DSN to disposable PostgreSQL")
    def test_real_fixture_postgresql_state_is_durable(self):
        dsn = os.environ["ACCESS_FIXTURE_TEST_DSN"]
        schema = "acceptance_fixture_" + uuid4().hex
        connect = psycopg.connect
        with connect(dsn, autocommit=True) as admin:
            admin.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
            try:
                with patch.dict(os.environ, {"FIXTURE_ROLE": "provider", "ACCEPTANCE_RUN_ID": RUN}), \
                     patch.object(fixture.psycopg, "connect", side_effect=lambda **kwargs: connect(dsn, options="-c search_path=" + schema, **kwargs)):
                    self.assertEqual(fixture.state(), "provider-" + RUN)
                    self.assertEqual(fixture.state("durable-marker"), "durable-marker")
                    self.assertEqual(fixture.state(), "durable-marker")
            finally:
                admin.execute(psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(psycopg.sql.Identifier(schema)))
