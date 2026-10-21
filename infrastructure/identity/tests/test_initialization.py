"""Exercise identity initialization with local CLI stand-ins, never live services."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

IDENTITY = Path(__file__).resolve().parents[1]
MOCK_CLI = r"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ["FIXTURE_ROOT"])
with (root / "commands.jsonl").open("a") as log:
    log.write(json.dumps([name, args]) + "\n")
if name == "kcadm" and args[0] == "get":
    if args[1] == "clients":
        client = next(arg.split("=", 1)[1] for arg in args if arg.startswith("clientId="))
        if os.environ["EXISTING"] == "yes" or (root / client).exists():
            print(json.dumps({"id": client + "-id"}))
    else:
        print(json.dumps({"id": "service-user-id"}))
elif name == "kcadm" and args[0] == "create":
    client = next(arg.split("=", 1)[1] for arg in args if arg.startswith("clientId="))
    (root / client).touch()
elif name == "kcadm" and args[0] == "update" and os.environ.get("FAIL_UPDATE"):
    sys.exit(9)
elif name == "psql" and "-tAc" in args:
    if os.environ["EXISTING"] == "yes":
        print("1")
elif name in ("pg_isready", "kcadm") and (name == "pg_isready" or args[0] == "config"):
    # Readiness is retried once without a real sleep or any network traffic.
    marker = root / (name + "-ready")
    if not marker.exists():
        marker.touch()
        sys.exit(1)
"""


class InitializationTests(unittest.TestCase):
    def run_initializer(self, name, *, existing=False, fail_update=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for command in ("psql", "pg_isready", "kcadm", "sleep"):
                executable = root / command
                executable.write_text(MOCK_CLI)
                executable.chmod(0o755)
            script = (
                (IDENTITY / name)
                .read_text()
                .replace("/opt/keycloak/bin/kcadm.sh", str(root / "kcadm"))
            )
            result = subprocess.run(
                ["/bin/sh", "-c", script],
                check=False,
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "FIXTURE_ROOT": str(root),
                    "EXISTING": "yes" if existing else "no",
                    "FAIL_UPDATE": "yes" if fail_update else "",
                    "POSTGRES_PASSWORD": "fixture-postgres-secret",
                    "KEYCLOAK_DB_PASSWORD": "fixture-db-secret",
                    "KEYCLOAK_ADMIN_PASSWORD": "fixture-admin-secret",
                    "STORE_CONSOLE_OIDC_SECRET": "fixture-console-secret",
                    "KEYCLOAK_PROVISIONER_SECRET": "fixture-provisioner-secret",
                    "PLATFORM_DOMAIN": "fixture.example.com",
                },
                capture_output=True,
                text=True,
                timeout=10,
            )
            commands = [
                json.loads(line)
                for line in (root / "commands.jsonl").read_text().splitlines()
            ]
            return result, commands

    def test_fresh_database_uses_restricted_role_and_waits(self):
        result, commands = self.run_initializer("init-database.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(name == "pg_isready" for name, _ in commands), 2)
        sql = " ".join(" ".join(args) for name, args in commands if name == "psql")
        self.assertIn("CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB", sql)
        self.assertIn("NOCREATEROLE", sql)
        self.assertIn("NOREPLICATION", sql)
        self.assertIn("CREATE DATABASE keycloak OWNER keycloak", sql)

    def test_existing_database_is_retained_and_password_refreshed(self):
        result, commands = self.run_initializer("init-database.sh", existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        sql = " ".join(" ".join(args) for name, args in commands if name == "psql")
        self.assertIn("ALTER ROLE keycloak PASSWORD 'fixture-db-secret'", sql)
        self.assertNotIn("CREATE ROLE", sql)
        self.assertNotIn("CREATE DATABASE", sql)

    def test_new_realm_clients_preserve_authentication_contracts(self):
        result, commands = self.run_initializer("init-realm.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        cli = [args for name, args in commands if name == "kcadm"]
        self.assertEqual(sum(args[0] == "create" for args in cli), 3)
        portal = next(
            args for args in cli if args[:2] == ["update", "clients/platform-portal-id"]
        )
        settings = dict(arg.split("=", 1) for arg in portal if "=" in arg)
        self.assertEqual(
            json.loads(settings["redirectUris"]),
            [
                "https://fixture.example.com/*",
                "http://localhost/*",
                "http://localhost:8000/*",
                "http://127.0.0.1:8000/*",
                "https://platform.localhost/*",
            ],
        )
        self.assertEqual(
            json.loads(settings["attributes"]), {"pkce.code.challenge.method": "S256"}
        )
        mapper = json.loads(settings["protocolMappers"])[0]
        self.assertEqual(mapper["config"]["included.client.audience"], "platform-api")
        console = next(
            args
            for args in cli
            if args[:2] == ["update", "clients/platform-store-console-id"]
        )
        settings = dict(arg.split("=", 1) for arg in console if "=" in arg)
        self.assertEqual(settings["publicClient"], "false")
        self.assertEqual(settings["secret"], "fixture-console-secret")
        self.assertEqual(
            json.loads(settings["redirectUris"]),
            ["https://fixture.example.com/store-console/postgresql/oauth2/authorize"],
        )
        grants = next(args for args in cli if args[0] == "add-roles")
        self.assertEqual(
            grants,
            [
                "add-roles",
                "-r",
                "platform",
                "--uid",
                "service-user-id",
                "--cclientid",
                "realm-management",
                "--rolename",
                "manage-clients",
                "--rolename",
                "manage-users",
                "--rolename",
                "view-users",
            ],
        )

    def test_existing_realm_refreshes_secrets_without_creating_clients(self):
        result, commands = self.run_initializer("init-realm.sh", existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        cli = [args for name, args in commands if name == "kcadm"]
        self.assertFalse(any(args[0] == "create" for args in cli))
        provisioner = next(
            args
            for args in cli
            if args[:2] == ["update", "clients/platform-credential-provisioner-id"]
        )
        self.assertIn("secret=fixture-provisioner-secret", provisioner)
        self.assertIn("serviceAccountsEnabled=true", provisioner)

    def test_cli_failure_stops_before_granting_roles(self):
        result, commands = self.run_initializer("init-realm.sh", fail_update=True)
        self.assertEqual(result.returncode, 9)
        self.assertFalse(
            any(name == "kcadm" and args[0] == "add-roles" for name, args in commands)
        )


if __name__ == "__main__":
    unittest.main()
