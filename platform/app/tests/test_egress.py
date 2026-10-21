import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.egress import resolve, validate


class DnsEgressTests(unittest.TestCase):
    def setUp(self):
        self.environment = os.environ.copy()
        os.environ["ALLOWED_EGRESS_CIDRS"] = "203.0.113.0/24"
        os.environ["ALLOWED_EGRESS_PORTS"] = "443"
        self.addCleanup(self.restore_environment)

    def restore_environment(self):
        os.environ.clear()
        os.environ.update(self.environment)

    def test_resolves_dns_to_operator_approved_cidrs(self):
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.9", 443)),
        ]
        with patch("app.egress.socket.getaddrinfo", return_value=answers):
            resolved = resolve({"dns": "Api.Example.Test.", "port": 443})
        self.assertEqual(
            resolved,
            {
                "dns": "api.example.test",
                "port": 443,
                "resolved_cidrs": ["203.0.113.8/32", "203.0.113.9/32"],
            },
        )

    def test_platform_network_cannot_be_reached_with_a_general_egress_declaration(self):
        os.environ["ALLOWED_EGRESS_CIDRS"] = "0.0.0.0/0"
        os.environ["ALLOWED_EGRESS_PORTS"] = "4318"
        with self.assertRaisesRegex(ValueError, "private platform network"):
            validate({"cidr": "172.30.80.14/32", "port": 4318})

    def test_rejects_unapproved_dns_answer_or_unresolvable_name(self):
        with (
            patch(
                "app.egress.socket.getaddrinfo",
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.51.100.8", 443))
                ],
            ),
            self.assertRaisesRegex(ValueError, "not allowed"),
        ):
            resolve({"dns": "api.example.test", "port": 443})
        with (
            patch("app.egress.socket.getaddrinfo", side_effect=socket.gaierror),
            self.assertRaisesRegex(ValueError, "could not be resolved"),
        ):
            resolve({"dns": "api.example.test", "port": 443})

    def test_mixed_address_families_are_denied_cleanly_when_ipv6_is_not_allowed(self):
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.8", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::8", 443, 0, 0)),
        ]
        with (
            patch("app.egress.socket.getaddrinfo", return_value=answers),
            self.assertRaisesRegex(ValueError, "not allowed"),
        ):
            resolve({"dns": "api.example.test", "port": 443})
