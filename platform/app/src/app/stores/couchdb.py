"""Named CouchDB databases with platform-managed native users.

The access relay is the sole client path. CouchDB members can write ordinary
documents, so native membership alone never represents a read-only grant.
"""

import base64
import os
import re
from urllib.parse import quote

from . import catalog
from .http_client import PrivateJSON
from .s3 import StoreError


def database(resource):
    return catalog.identifier(resource["resource_id"])


def basic(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return "Basic " + token


class CouchDB:
    quota_enforcement = "advisory"

    def __init__(self, endpoint=None, admin=None, password=None):
        self.endpoint = endpoint or "http://" + os.environ["COUCHDB_IP"] + ":5984"
        self.admin = admin or os.environ.get("COUCHDB_ADMIN_USER", "platform_admin")
        self.password = password or os.environ["COUCHDB_ADMIN_PASSWORD"]
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.admin):
            raise ValueError("Invalid CouchDB administrator name")
        self.root = PrivateJSON(
            self.endpoint, {"Authorization": basic(self.admin, self.password)}
        )

    def security(self, resource):
        return self.root.request("GET", "/" + database(resource) + "/_security")

    def set_members(self, resource, names):
        self.root.request(
            "PUT",
            "/" + database(resource) + "/_security",
            {
                "admins": {"names": [], "roles": []},
                # An empty members list can make a database public. Keep a
                # nonexistent sentinel even when the last lease is revoked.
                "members": {
                    "names": sorted({"platform_reserved", *names}),
                    "roles": [],
                },
            },
        )

    def provision(self, resource):
        name = database(resource)
        if self.root.request("GET", "/" + name, missing=True) is None:
            self.root.request("PUT", "/" + name)
        security = self.security(resource)
        members = security.get("members", {})
        names = members.get("names", [])
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise StoreError("CouchDB membership requires operator review")
        if any(
            n != "platform_reserved" and not n.startswith("credential_") for n in names
        ):
            raise StoreError("CouchDB membership requires operator review")
        admins = security.get("admins", {})
        if admins.get("names") or set(admins.get("roles", [])) - {"_admin"}:
            raise StoreError("CouchDB resource administrator drift")
        self.set_members(resource, names)

    def issue(self, resource, credential):
        user = catalog.login(credential["credential_id"])
        path = "/_users/" + quote("org.couchdb.user:" + user, safe=":")
        current = self.root.request("GET", path, missing=True)
        body = {
            "_id": "org.couchdb.user:" + user,
            "name": user,
            "type": "user",
            "roles": [],
            "password": catalog.secret_for(credential["credential_id"]),
        }
        if current is not None:
            body["_rev"] = current["_rev"]
        self.root.request("PUT", path, body)
        security = self.security(resource)
        self.set_members(resource, [*security["members"]["names"], user])
        self.probe(resource, credential)

    def revoke(self, resource, credential):
        user = catalog.login(credential["credential_id"])
        if self.root.request("GET", "/" + database(resource), missing=True) is not None:
            security = self.security(resource)
            self.set_members(
                resource, [n for n in security["members"]["names"] if n != user]
            )
        path = "/_users/" + quote("org.couchdb.user:" + user, safe=":")
        current = self.root.request("GET", path, missing=True)
        if current is not None:
            self.root.request("DELETE", path + "?rev=" + quote(current["_rev"]))

    def scoped(self, credential):
        return PrivateJSON(
            self.endpoint,
            {
                "Authorization": basic(
                    catalog.login(credential["credential_id"]),
                    catalog.secret_for(credential["credential_id"]),
                )
            },
        )

    def probe(self, resource, credential):
        name = database(resource)
        self.scoped(credential).request("GET", "/" + name)
        security = self.security(resource)
        if (
            catalog.login(credential["credential_id"])
            not in security["members"]["names"]
        ):
            raise StoreError("CouchDB credential is outside resource membership")

    def credentials(self, resource, credential):
        return {
            "COUCHDB_URL": self.endpoint,
            "COUCHDB_DATABASE": database(resource),
            "COUCHDB_USERNAME": catalog.login(credential["credential_id"]),
            "COUCHDB_PASSWORD": catalog.secret_for(credential["credential_id"]),
        }

    def usage(self, resource):
        sizes = self.root.request("GET", "/" + database(resource))["sizes"]
        value = sizes["file"]
        if type(value) is not int or value < 0:
            raise StoreError("CouchDB database usage unavailable")
        return value

    def validate_recovery(self, resource):
        name = database(resource)
        self.root.request("GET", "/" + name)
        security = self.security(resource)
        members = security.get("members", {})
        names = members.get("names", [])
        admins = security.get("admins", {})
        if (
            not isinstance(names, list)
            or "platform_reserved" not in names
            or any(
                not isinstance(user, str)
                or (user != "platform_reserved" and not user.startswith("credential_"))
                for user in names
            )
            or members.get("roles")
            or admins.get("names")
            or set(admins.get("roles", [])) - {"_admin"}
        ):
            raise StoreError("CouchDB resource security is not reconciled")

    def purge(self, resource):
        name = database(resource)
        security = self.root.request("GET", "/" + name + "/_security", missing=True)
        if security is not None:
            for user in security.get("members", {}).get("names", []):
                if user.startswith("credential_"):
                    path = "/_users/" + quote("org.couchdb.user:" + user, safe=":")
                    current = self.root.request("GET", path, missing=True)
                    if current is not None:
                        self.root.request(
                            "DELETE", path + "?rev=" + quote(current["_rev"])
                        )
        self.root.request("DELETE", "/" + name, missing=True)
