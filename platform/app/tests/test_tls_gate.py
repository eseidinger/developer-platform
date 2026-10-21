import os
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import main


class Connection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, query):
        self.query = query
        return self

    def fetchall(self):
        return self.rows


class TlsGateTests(unittest.TestCase):
    def setUp(self):
        self.environment = os.environ.copy()
        os.environ["APPS_DOMAIN"] = "apps.example.test"
        self.addCleanup(self.restore_environment)

    def restore_environment(self):
        os.environ.clear()
        os.environ.update(self.environment)

    def allow(self, domain, rows):
        with patch.object(main, "connect", return_value=nullcontext(Connection(rows))):
            return main.allow_certificate(domain)

    def test_allows_legacy_project_hostname(self):
        self.assertEqual(
            self.allow("hello.apps.example.test", [("hello", {"image": "example:v1"})]),
            {"allowed": True},
        )

    def test_allows_only_declared_public_component_hostname(self):
        rows = [
            (
                "odip",
                {
                    "components": [
                        {"name": "web", "type": "service", "exposure": "public"},
                        {"name": "worker", "type": "service", "exposure": "private"},
                    ]
                },
            )
        ]
        self.assertEqual(
            self.allow("web-odip.apps.example.test", rows), {"allowed": True}
        )
        for domain in (
            "odip.apps.example.test",
            "worker-odip.apps.example.test",
            "other-odip.apps.example.test",
            "web-odip.other.example.test",
        ):
            with (
                self.subTest(domain=domain),
                self.assertRaises(main.HTTPException) as error,
            ):
                self.allow(domain, rows)
            self.assertEqual(error.exception.status_code, 403)

    def test_rejects_no_matching_applied_project(self):
        with self.assertRaises(main.HTTPException) as error:
            self.allow("web-odip.apps.example.test", [])
        self.assertEqual(error.exception.status_code, 403)

    def test_console_certificate_requires_an_active_human_lease_in_the_bounded_port_range(
        self,
    ):
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = ("credential-id",)
        with (
            patch.object(main, "connect", return_value=nullcontext(connection)),
            patch(
                "app.stores.console.lease", return_value={"provider": "s3"}
            ) as lookup,
            patch("app.stores.console.enabled", return_value=True),
        ):
            for port in (20000, 20099, 20100, 20499, 20500, 20511):
                self.assertEqual(
                    main.allow_certificate(f"console-{port}.apps.example.test"),
                    {"allowed": True},
                )
            for port in (19999, 20512, 20999):
                with self.assertRaises(main.HTTPException):
                    main.allow_certificate(f"console-{port}.apps.example.test")
            lookup.return_value = None
            with self.assertRaises(main.HTTPException):
                main.allow_certificate("console-20000.apps.example.test")

    def test_console_component_name_still_uses_normal_application_certificate_rules(
        self,
    ):
        self.assertEqual(
            self.allow(
                "console-project.apps.example.test",
                [
                    (
                        "project",
                        {
                            "components": [
                                {
                                    "name": "console",
                                    "type": "service",
                                    "exposure": "public",
                                }
                            ]
                        },
                    )
                ],
            ),
            {"allowed": True},
        )


if __name__ == "__main__":
    unittest.main()
