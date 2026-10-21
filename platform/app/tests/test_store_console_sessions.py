import hashlib
import os
from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import h11
import jwt
from app.stores.console import session_metadata
from app.stores.http_relay import access_key, console_user, identity
from app.stores.s3 import S3, console_secret


class ConsoleSessionTests(TestCase):
    def setUp(self):
        self.credential = {
            "credential_id": str(uuid4()),
            "kind": "human",
            "provider": "s3",
            "expires_at": datetime.now(UTC) + timedelta(hours=24),
        }
        self.token = jwt.encode(
            {
                "parent": console_user(self.credential["credential_id"]),
                "exp": int((datetime.now(UTC) + timedelta(hours=12)).timestamp()),
            },
            "synthetic-native-signing-key-00000",
            algorithm="HS256",
        )
        self.child = "A" * 20
        self.digest = hashlib.sha256(self.token.encode()).hexdigest()
        self.credential["s3_sessions"] = {
            self.child: {
                "token_sha256": self.digest,
                "expires_at": datetime.now(UTC) + timedelta(hours=12),
            }
        }

    def request(self, key=None, token=None):
        headers = [
            (b"host", b"console.fixture.invalid"),
            (
                b"authorization",
                (
                    f"AWS4-HMAC-SHA256 Credential={key or self.child}/20261017/us-east-1/s3/aws4_request, SignedHeaders=host;x-amz-security-token, Signature="
                    + "a" * 64
                ).encode(),
            ),
            (b"x-amz-security-token", (token or self.token).encode()),
        ]
        return h11.Request(method=b"GET", target=b"/", headers=headers)

    def test_child_requires_the_exact_registered_key_token_pair_and_current_human_lease(
        self,
    ):
        self.assertEqual(
            identity(self.request(), self.credential)["_session"],
            (self.child, self.digest),
        )
        for request in (
            self.request(key="B" * 20),
            self.request(token=self.token + "changed"),
        ):
            with self.assertRaises(ValueError):
                identity(request, self.credential)
        for change in (
            {"kind": "binding"},
            {"s3_sessions": {}},
            {
                "s3_sessions": {
                    self.child: {
                        "token_sha256": self.digest,
                        "expires_at": datetime.now(UTC) - timedelta(seconds=1),
                    }
                }
            },
        ):
            with self.assertRaises(ValueError):
                identity(self.request(), {**self.credential, **change})

    def test_console_parent_is_human_only_and_service_keys_keep_their_existing_contract(
        self,
    ):
        parent = self.request(key=console_user(self.credential["credential_id"]))
        self.assertTrue(identity(parent, self.credential)["_console_login"])
        with self.assertRaises(ValueError):
            identity(parent, {**self.credential, "kind": "binding"})
        ordinary = self.request(key=access_key(self.credential["credential_id"]))
        self.assertNotIn(
            "_console_login", identity(ordinary, {**self.credential, "kind": "binding"})
        )

    def test_transient_sts_response_yields_only_a_hash_and_public_key_bounded_by_the_original_lease(
        self,
    ):
        row = {
            **self.credential,
            "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        }
        xml = f"""<AssumeRoleResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/"><AssumeRoleResult><Credentials>
            <AccessKeyId>{self.child}</AccessKeyId><SecretAccessKey>synthetic-secret-not-stored</SecretAccessKey>
            <SessionToken>{self.token}</SessionToken><Expiration>{self.credential["expires_at"].isoformat()}</Expiration>
            </Credentials></AssumeRoleResult></AssumeRoleResponse>""".encode()
        key, digest, expiry = session_metadata(xml, row)
        self.assertEqual(
            (key, digest, expiry), (self.child, self.digest, row["expires_at"])
        )
        self.assertNotIn(self.token, str((key, digest, expiry)))
        with self.assertRaises(ValueError):
            session_metadata(xml, {**row, "credential_id": str(uuid4())})

    def test_only_personal_connection_output_contains_console_credentials(self):
        provider = S3.__new__(S3)
        provider.endpoint = "http://127.0.0.1:9000"
        with patch.dict(os.environ, {"DATABASE_KEY": "s" * 32}):
            private = provider.credentials(
                {"resource_id": str(uuid4())}, {**self.credential, "kind": "binding"}
            )
            personal = provider.credentials(
                {"resource_id": str(uuid4())}, self.credential
            )
            self.assertNotIn("RUSTFS_CONSOLE_SECRET_KEY", private)
            self.assertEqual(
                personal["RUSTFS_CONSOLE_ACCESS_KEY"],
                console_user(self.credential["credential_id"]),
            )
            self.assertEqual(
                personal["RUSTFS_CONSOLE_SECRET_KEY"], console_secret(self.credential)
            )
            self.assertNotEqual(
                personal["RUSTFS_CONSOLE_SECRET_KEY"], personal["AWS_SECRET_ACCESS_KEY"]
            )
