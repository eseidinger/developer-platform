import hashlib
import unittest
from datetime import UTC
from uuid import uuid4

from app.stores import catalog
from app.stores.bolt_relay import Decoder, validate
from app.stores.neo4j import admission, require_mode


def pack(value):
    if isinstance(value, str):
        raw = value.encode()
        return (
            bytes([0x80 + len(raw)]) if len(raw) < 16 else b"\xd0" + bytes([len(raw)])
        ) + raw
    if isinstance(value, dict):
        return bytes([0xA0 + len(value)]) + b"".join(
            pack(k) + pack(v) for k, v in value.items()
        )
    if isinstance(value, list):
        return bytes([0x90 + len(value)]) + b"".join(pack(v) for v in value)
    if value is None:
        return b"\xc0"
    if isinstance(value, int) and 0 <= value < 128:
        return bytes([value])
    raise ValueError()


def frame(tag, *fields):
    return bytes([0xB0 + len(fields), tag]) + b"".join(pack(value) for value in fields)


class BoltFenceTests(unittest.TestCase):
    def setUp(self):
        self.cid = str(uuid4())
        self.password = "a" * 64
        self.lease = {
            "credential_id": self.cid,
            "admission_sha256": hashlib.sha256(self.password.encode()).hexdigest(),
        }
        self.state = {"hello": False, "auth": False}

    def login(self, **changes):
        return frame(
            0x6A,
            {
                "scheme": "basic",
                "principal": catalog.login(self.cid),
                "credentials": self.password,
                **changes,
            },
        )

    def ready(self):
        validate(frame(1, {"user_agent": "fixture"}), self.lease, self.state)
        validate(self.login(), self.lease, self.state)

    def test_native_data_and_schema_queries_are_unmodified_and_not_filtered(self):
        self.ready()
        for query in [
            "MATCH (n) RETURN n",
            "CREATE INDEX FOR (n:Fixture) ON (n.value)",
            "SHOW USERS",
        ]:
            validate(frame(0x10, query, {}, {"db": "neo4j"}), self.lease, self.state)

    def test_cross_generation_and_changed_native_password_fail_before_upstream(self):
        for auth in [
            {"principal": catalog.login(uuid4())},
            {"credentials": "b" * 64},
            {"scheme": "none"},
        ]:
            with self.subTest(auth=list(auth)), self.assertRaises(ValueError):
                self.state = {"hello": True, "auth": False}
                validate(self.login(**auth), self.lease, self.state)

    def test_reauthentication_cannot_switch_identity(self):
        self.ready()
        validate(frame(0x6B), self.lease, self.state)
        with self.assertRaises(ValueError):
            validate(self.login(principal="neo4j"), self.lease, self.state)

    def test_impersonation_and_other_database_rejected(self):
        self.ready()
        for extra in [{"imp_user": "neo4j"}, {"db": "foreign"}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate(frame(0x10, "RETURN 1", {}, extra), self.lease, self.state)

    def test_payload_before_logon_and_auth_in_hello_rejected(self):
        for packet in [
            frame(0x10, "RETURN 1", {}, {}),
            frame(1, {"principal": "neo4j"}),
        ]:
            with self.assertRaises(ValueError):
                validate(packet, self.lease, self.state)

    def test_duplicate_map_keys_trailing_bytes_and_truncated_values_rejected(self):
        for data in [b"\xa2\x81a\x01\x81a\x02", b"\xd2\xff\xff\xff\xff"]:
            with self.assertRaises(ValueError):
                Decoder(data).value()
        with self.assertRaises(ValueError):
            validate(frame(1, {}) + b"\x01", self.lease, self.state)

    def test_unreviewed_message_rejected(self):
        self.ready()
        with self.assertRaises(ValueError):
            validate(frame(0x7F), self.lease, self.state)

    def test_read_only_is_rejected_without_changing_other_providers(self):
        with self.assertRaises(catalog.Conflict):
            require_mode("neo4j", "read-only")
        require_mode("neo4j", "read-write")
        require_mode("postgresql", "read-only")

    def test_missing_platform_verifier_fails_closed(self):
        with self.assertRaises(ValueError):
            admission(self.password, {"admission_sha256": None})


if __name__ == "__main__":
    unittest.main()


class BoltBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_message_rejected_before_reading_its_next_body(self):
        import asyncio

        from app.stores.bolt_relay import message

        reader = asyncio.StreamReader()
        reader.feed_data((b"\xff\xff" + b"x" * 65535) * 16 + b"\xff\xff")
        with self.assertRaises(ValueError):
            await message(reader)

    async def test_bolt_memory_budget_rejects_before_opening_a_backend(self):
        import asyncio
        import time
        from datetime import datetime, timedelta
        from unittest.mock import Mock, patch

        from app.stores.relay import MAX_BOLT_CONNECTIONS, Relay

        relay = Relay(host="127.0.0.1")
        relay.bolt_connections = MAX_BOLT_CONNECTIONS
        relay.last_success = time.monotonic()
        relay.leases[20000] = {
            "provider": "neo4j",
            "credential_id": str(uuid4()),
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
        writer = Mock()
        with patch("asyncio.open_connection") as connection:
            await relay.handle(20000, asyncio.StreamReader(), writer)
        writer.close.assert_called_once()
        connection.assert_not_called()
        self.assertEqual(relay.connections, 0)
        self.assertEqual(relay.bolt_connections, MAX_BOLT_CONNECTIONS)
