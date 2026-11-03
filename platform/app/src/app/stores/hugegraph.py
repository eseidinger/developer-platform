"""Named HugeGraph 1.7 RocksDB graphs with operator-managed native identities.

The service is reachable only by the API and relay. Native graph permissions
do not prevent cross-graph reads in the tested image, so the relay's strict
route policy is part of this provider's security boundary.
"""

import base64
import os
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request

from . import catalog
from .http_client import PrivateJSON
from .s3 import StoreError

AUTH = "/graphspaces/DEFAULT/auth"
PERMISSIONS = {
    "read-only": {"READ"},
    "read-write": {"READ", "WRITE", "DELETE"},
}


def graph_name(resource):
    return catalog.identifier(resource["resource_id"])


def basic(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return "Basic " + token


class HugeGraph:
    quota_enforcement = "advisory"

    def __init__(self, endpoint=None, password=None):
        self.endpoint = endpoint or "http://" + os.environ["HUGEGRAPH_IP"] + ":8080"
        self.password = password or os.environ["HUGEGRAPH_ADMIN_PASSWORD"]
        self.root = PrivateJSON(
            self.endpoint, {"Authorization": basic("admin", self.password)}
        )

    @staticmethod
    def _names(resource):
        suffix = graph_name(resource).removeprefix("resource_")
        return {
            "target": "target_" + suffix,
            "read-only": "reader_" + suffix,
            "read-write": "writer_" + suffix,
        }

    def _object(self, path, identifier, field):
        result = self.root.request(
            "GET", path + "/" + quote(identifier, safe=""), missing=True
        )
        if result is not None and result.get(field) != identifier.split(":", 1)[1]:
            raise StoreError("HugeGraph authorization object drift")
        return result

    def _accesses(self):
        records = self.root.request("GET", AUTH + "/accesses?limit=10000")["accesses"]
        if len(records) >= 10000:
            raise StoreError("HugeGraph authorization inventory is incomplete")
        return records

    def _belongs(self):
        records = self.root.request("GET", AUTH + "/belongs?limit=10000")["belongs"]
        if len(records) >= 10000:
            raise StoreError("HugeGraph membership inventory is incomplete")
        return records

    @staticmethod
    def _graph_configuration(name):
        return {
            "gremlin.graph": "org.apache.hugegraph.auth.HugeFactoryAuthProxy",
            "backend": "rocksdb",
            "serializer": "binary",
            "store": name,
            "rocksdb.data_path": "/data/" + name + "/data",
            "rocksdb.wal_path": "/data/" + name + "/wal",
        }

    def _validate_graph(self, name):
        graph = self.root.request("GET", "/graphs/" + name)
        if graph.get("name") != name or graph.get("backend") != "rocksdb":
            raise StoreError("HugeGraph graph configuration drift")
        # The graph details endpoint omits store and RocksDB paths. The operator
        # configuration endpoint exposes the persisted values as properties.
        request = Request(
            self.endpoint + "/graphs/" + name + "/conf",
            headers=self.root.headers,
        )
        try:
            with self.root.opener.open(request, timeout=5) as response:
                raw = response.read(65537)
        except HTTPError as error:
            raise StoreError(
                f"HugeGraph graph configuration unavailable ({error.code})"
            ) from None
        if len(raw) > 65536:
            raise StoreError("HugeGraph graph configuration exceeded its limit")
        config = {}
        for line in raw.decode().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in config:
                raise StoreError("HugeGraph graph configuration has duplicate keys")
            config[key] = value.strip()
        if any(
            config.get(key) != value
            for key, value in self._graph_configuration(name).items()
        ):
            raise StoreError("HugeGraph graph configuration drift")

    def _security(self, resource):
        names = self._names(resource)
        target_id = "-45:" + names["target"]
        target = self._object(AUTH + "/targets", target_id, "target_name")
        expected_resource = {"type": "ALL", "label": "*", "properties": None}
        if (
            target is None
            or target.get("target_graph") != graph_name(resource)
            or target.get("target_resources") != {"ALL": [expected_resource]}
        ):
            raise StoreError("HugeGraph target is not reconciled")
        groups = {}
        for mode in PERMISSIONS:
            group_id = "-37:" + names[mode]
            if self._object("/auth/groups", group_id, "group_name") is None:
                raise StoreError("HugeGraph grant group is missing")
            groups[mode] = group_id
        observed = {mode: set() for mode in PERMISSIONS}
        for access in self._accesses():
            if access.get("target") != target_id:
                continue
            for mode, group_id in groups.items():
                if access.get("group") == group_id:
                    observed[mode].add(access.get("access_permission"))
                    break
            else:
                raise StoreError("HugeGraph target has an unmanaged grant")
        if observed != PERMISSIONS:
            raise StoreError("HugeGraph grant permissions are not reconciled")
        return groups, target_id

    def provision(self, resource):
        name = graph_name(resource)
        existing = self.root.request("GET", "/graphs").get("graphs", [])
        if not isinstance(existing, list):
            raise StoreError("HugeGraph graph inventory is unavailable")
        if name not in existing:
            # Separate paths prevent two graphs from sharing RocksDB files.
            self.root.request(
                "POST",
                "/graphs/" + name,
                self._graph_configuration(name),
            )
        else:
            self._validate_graph(name)

        names = self._names(resource)
        target_id = "-45:" + names["target"]
        if self._object(AUTH + "/targets", target_id, "target_name") is None:
            self.root.request(
                "POST",
                AUTH + "/targets",
                {
                    "target_name": names["target"],
                    "target_graph": name,
                    "target_url": urlsplit(self.endpoint).netloc,
                    "target_resources": [{"type": "ALL"}],
                },
            )
        accesses = self._accesses()
        for mode, permissions in PERMISSIONS.items():
            group_id = "-37:" + names[mode]
            if self._object("/auth/groups", group_id, "group_name") is None:
                self.root.request("POST", "/auth/groups", {"group_name": names[mode]})
            for permission in permissions:
                if not any(
                    row.get("group") == group_id
                    and row.get("target") == target_id
                    and row.get("access_permission") == permission
                    for row in accesses
                ):
                    self.root.request(
                        "POST",
                        AUTH + "/accesses",
                        {
                            "group": group_id,
                            "target": target_id,
                            "access_permission": permission,
                        },
                    )
        self._security(resource)

    def issue(self, resource, credential):
        groups, _ = self._security(resource)
        name = catalog.login(credential["credential_id"])
        user_id = "-31:" + name
        if self._object(AUTH + "/users", user_id, "user_name") is None:
            self.root.request(
                "POST",
                AUTH + "/users",
                {
                    "user_name": name,
                    "user_password": catalog.secret_for(credential["credential_id"]),
                },
            )
        membership = [row for row in self._belongs() if row.get("user") == user_id]
        expected_group = groups[credential["mode"]]
        if any(row.get("group") != expected_group for row in membership):
            raise StoreError("HugeGraph credential has an unmanaged group")
        if not membership:
            self.root.request(
                "POST", AUTH + "/belongs", {"user": user_id, "group": expected_group}
            )
        self.probe(resource, credential)

    def revoke(self, resource, credential):
        user_id = "-31:" + catalog.login(credential["credential_id"])
        for membership in self._belongs():
            if membership.get("user") == user_id:
                self.root.request(
                    "DELETE",
                    AUTH + "/belongs/" + quote(membership["id"], safe=""),
                    missing=True,
                )
        self.root.request("DELETE", AUTH + "/users/" + quote(user_id), missing=True)

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
        self.scoped(credential).request(
            "GET", "/graphs/" + graph_name(resource) + "/schema/propertykeys"
        )

    def credentials(self, resource, credential):
        return {
            "HUGEGRAPH_REST_URI": self.endpoint,
            "HUGEGRAPH_GRAPH": graph_name(resource),
            "HUGEGRAPH_USERNAME": catalog.login(credential["credential_id"]),
            "HUGEGRAPH_PASSWORD": catalog.secret_for(credential["credential_id"]),
        }

    def usage(self, resource):
        metrics = self.root.request("GET", "/metrics/backend")
        graph = metrics.get("DEFAULT-" + graph_name(resource), {})
        servers = graph.get("servers", {})
        if not isinstance(servers, dict) or not servers:
            raise StoreError("HugeGraph graph usage is unavailable")
        total = 0
        for server in servers.values():
            if server.get("disk_unit") != "GB" or not isinstance(
                server.get("disk_usage"), (int, float)
            ):
                raise StoreError("HugeGraph graph usage is unavailable")
            total += max(0, int(server["disk_usage"] * 1024**3))
        return total

    def validate_recovery(self, resource):
        self._validate_graph(graph_name(resource))
        self._security(resource)

    def purge(self, resource):
        names = self._names(resource)
        groups = {"-37:" + names[mode] for mode in PERMISSIONS}
        target_id = "-45:" + names["target"]
        if any(row.get("group") in groups for row in self._belongs()):
            raise StoreError("HugeGraph graph still has active credentials")
        for access in self._accesses():
            if access.get("target") == target_id:
                self.root.request(
                    "DELETE", AUTH + "/accesses/" + quote(access["id"], safe="")
                )
        for group_id in groups:
            if self._object("/auth/groups", group_id, "group_name") is not None:
                self.root.request("DELETE", "/auth/groups/" + quote(group_id, safe=""))
        if self._object(AUTH + "/targets", target_id, "target_name") is not None:
            self.root.request("DELETE", AUTH + "/targets/" + quote(target_id, safe=""))
        if graph_name(resource) in self.root.request("GET", "/graphs")["graphs"]:
            self.root.request(
                "DELETE",
                "/graphs/"
                + graph_name(resource)
                + "?confirm_message=I%27m%20sure%20to%20drop%20the%20graph",
            )
