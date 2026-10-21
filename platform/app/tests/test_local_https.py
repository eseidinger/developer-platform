"""Local access remains opt-in, component-scoped, and isolated from operator services."""

import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.manifests import component_resources

from app import egress, local_https


class LocalHttpsTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "LOCAL_APPLICATION_HTTPS_ENABLED": "true",
                "LOCAL_APPLICATION_EDGE_IP": "172.30.80.32",
                "PLATFORM_SUBNET": "172.30.80.0/24",
                "APPS_DOMAIN": "apps.localhost",
                "IDENTITY_DOMAIN": "identity.localhost",
                "ALLOWED_EGRESS_CIDRS": "",
                "ALLOWED_EGRESS_PORTS": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_configured_https_names_resolve_without_widening_general_allowlists(self):
        for host in ("identity.localhost", "api-provider.apps.localhost"):
            with patch.object(
                egress.socket, "getaddrinfo", side_effect=AssertionError("external DNS")
            ):
                self.assertEqual(
                    egress.resolve({"dns": host, "port": 443})["resolved_cidrs"],
                    ["172.30.80.32/32"],
                )
        with self.assertRaisesRegex(ValueError, "private platform network"):
            egress.validate({"cidr": "172.30.80.32/32", "port": 443})

    def test_other_hosts_ports_and_private_addresses_receive_no_exception(self):
        for host, port in (
            ("platform.localhost", 443),
            ("console-20000.apps.localhost", 443),
            ("api-provider.apps.localhost.attacker.example", 443),
            ("nested.api.apps.localhost", 443),
            ("identity.localhost", 8080),
            ("api-provider.apps.localhost", 80),
            ("172.30.80.10", 443),
        ):
            with self.subTest(host=host, port=port):
                self.assertIsNone(local_https.destination(host, port))
        os.environ["LOCAL_APPLICATION_HTTPS_ENABLED"] = "false"
        self.assertIsNone(local_https.destination("identity.localhost", 443))

    def test_gateway_configuration_must_remain_local_and_inside_private_network(self):
        for key, value in (
            ("APPS_DOMAIN", "apps.example.com"),
            ("LOCAL_APPLICATION_EDGE_IP", "8.8.8.8"),
        ):
            with patch.dict(os.environ, {key: value}), self.assertRaises(ValueError):
                local_https.destination("identity.localhost", 443)

    def component(self, name, kind="service", outbound=None):
        return {
            "name": name,
            "type": kind,
            "resolved_image": "example/fixture@sha256:" + "a" * 64,
            "outbound": outbound or [],
            **({"schedule": "0 * * * *"} if kind == "scheduled" else {}),
        }

    def test_only_declaring_services_and_jobs_mount_public_trust(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "ca.pem"
            public_ca = ssl.create_default_context().get_ca_certs(binary_form=True)[0]
            bundle.write_text(ssl.DER_cert_to_PEM_cert(public_ca))
            outbound = [
                {"dns": "identity.localhost", "port": 443},
                {"dns": "api-provider.apps.localhost", "port": 443},
            ]
            with patch.dict(os.environ, {"LOCAL_APPLICATION_CA_BUNDLE": str(bundle)}):
                manifests = component_resources(
                    "test",
                    [
                        self.component("caller", outbound=outbound),
                        self.component("worker"),
                        self.component("job", "scheduled", outbound),
                    ],
                    "172.30.80.10",
                    "synthetic",
                )
            config = next(item for item in manifests if item["kind"] == "ConfigMap")
            self.assertEqual(config["data"]["ca-bundle.pem"], bundle.read_text())
            for item in manifests:
                if item["kind"] == "Deployment":
                    template = item["spec"]["template"]
                elif item["kind"] == "CronJob":
                    template = item["spec"]["jobTemplate"]["spec"]["template"]
                else:
                    continue
                pod = template["spec"]
                if item["metadata"]["name"] == "worker":
                    self.assertNotIn("hostAliases", pod)
                    self.assertFalse(
                        any(v["name"] == local_https.CONFIG_MAP for v in pod["volumes"])
                    )
                    continue
                self.assertEqual(
                    pod["hostAliases"],
                    [
                        {
                            "ip": "172.30.80.32",
                            "hostnames": [
                                "api-provider.apps.localhost",
                                "identity.localhost",
                            ],
                        }
                    ],
                )
                self.assertIn(
                    "platform.example/local-trust", template["metadata"]["annotations"]
                )
                environment = {
                    v["name"]: v["value"] for v in pod["containers"][0]["env"]
                }
                self.assertEqual(environment["SSL_CERT_FILE"], local_https.TRUST_PATH)
                self.assertTrue(pod["containers"][0]["volumeMounts"][-1]["readOnly"])

    def test_missing_bundle_prevents_deployment_instead_of_disabling_tls(self):
        with (
            patch.dict(
                os.environ, {"LOCAL_APPLICATION_CA_BUNDLE": "/missing-local-ca.pem"}
            ),
            self.assertRaises(FileNotFoundError),
        ):
            component_resources(
                "test",
                [
                    self.component(
                        "caller", outbound=[{"dns": "identity.localhost", "port": 443}]
                    )
                ],
                "172.30.80.10",
                "synthetic",
            )


if __name__ == "__main__":
    unittest.main()
