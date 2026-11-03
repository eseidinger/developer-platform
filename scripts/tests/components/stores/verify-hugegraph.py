#!/usr/bin/env python3
"""Run a disposable HugeGraph lifecycle and access-boundary fixture.

This fixture starts an isolated container with three temporary named volumes.
It never connects to or changes a deployed platform. Docker access is required.
"""

import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "platform/app/src"))

from app.stores.hugegraph import HugeGraph, graph_name
from app.stores.hugegraph_access import authorize
from app.stores.s3 import StoreError

IMAGE = "hugegraph/hugegraph:1.7.0@sha256:077b89e1f2d5e228d99598bdb537161fb2e8a7b5abedf4724d97cf4de11529ba"


def docker(*arguments):
    completed = subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return completed.stdout.strip()


def wait_ready(endpoint):
    for _ in range(90):
        try:
            with urlopen(endpoint + "/versions", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError, TimeoutError):
            pass
        time.sleep(2)
    raise RuntimeError("HugeGraph fixture did not become ready")


def fixture(endpoint, password):
    provider = HugeGraph(endpoint=endpoint, password=password)
    resource = {"resource_id": str(uuid4())}
    other = {"resource_id": str(uuid4())}
    reader = {"credential_id": str(uuid4()), "mode": "read-only"}
    writer = {"credential_id": str(uuid4()), "mode": "read-write"}
    path = "/graphs/" + graph_name(resource)

    provider.provision(resource)
    provider.provision(resource)
    provider.provision(other)
    provider.issue(resource, reader)
    provider.issue(resource, writer)

    # Native READ still reaches another graph in 1.7. The relay must reject it.
    provider.scoped(reader).request(
        "GET", "/graphs/" + graph_name(other) + "/graph/vertices"
    )
    lease = {"resource_id": resource["resource_id"], "mode": "read-only"}
    for method, target in [
        (b"GET", "/graphs"),
        (b"GET", "/graphs/" + graph_name(other) + "/graph/vertices"),
        (b"POST", path + "/schema/propertykeys"),
        (b"GET", path + "/gremlin"),
    ]:
        try:
            authorize(method, target.encode(), lease)
        except ValueError:
            pass
        else:
            raise AssertionError("HugeGraph relay accepted an unsafe request")

    writer_client = provider.scoped(writer)
    writer_client.request(
        "POST",
        path + "/schema/propertykeys",
        {"name": "name", "data_type": "TEXT", "cardinality": "SINGLE"},
    )
    writer_client.request(
        "POST",
        path + "/schema/vertexlabels",
        {
            "name": "person",
            "id_strategy": "PRIMARY_KEY",
            "properties": ["name"],
            "primary_keys": ["name"],
            "nullable_keys": [],
            "enable_label_index": True,
        },
    )
    writer_client.request(
        "POST",
        path + "/schema/edgelabels",
        {
            "name": "knows",
            "source_label": "person",
            "target_label": "person",
            "frequency": "SINGLE",
            "properties": [],
            "sort_keys": [],
            "nullable_keys": [],
            "enable_label_index": True,
        },
    )
    vertex = writer_client.request(
        "POST",
        path + "/graph/vertices",
        {"label": "person", "properties": {"name": "Ada"}},
    )
    assert vertex["id"]
    peer = writer_client.request(
        "POST",
        path + "/graph/vertices",
        {"label": "person", "properties": {"name": "Bob"}},
    )
    edge = writer_client.request(
        "POST",
        path + "/graph/edges",
        {
            "label": "knows",
            "outV": vertex["id"],
            "inV": peer["id"],
            "outVLabel": "person",
            "inVLabel": "person",
            "properties": {},
        },
    )
    assert edge["id"]
    assert isinstance(provider.usage(resource), int)
    assert provider.scoped(reader).request("GET", path + "/graph/vertices")["vertices"]
    assert provider.scoped(reader).request("GET", path + "/graph/edges")["edges"]
    try:
        provider.scoped(reader).request(
            "POST", path + "/schema/propertykeys", {"name": "blocked"}
        )
    except StoreError:
        pass
    else:
        raise AssertionError("HugeGraph reader created schema")

    return provider, resource, other, reader, writer, edge["id"]


def main():
    suffix = uuid4().hex[:12]
    container = "hugegraph-fixture-" + suffix
    volumes = {
        purpose: container + "-" + purpose for purpose in ("data", "system", "config")
    }
    password = secrets.token_hex(32)
    os.environ["DATABASE_KEY"] = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="hugegraph-fixture-") as directory:
        env_file = Path(directory) / "container.env"
        env_file.write_text("PASSWORD=" + password + "\n")
        env_file.chmod(0o600)
        try:
            for volume in volumes.values():
                docker("volume", "create", volume)
            run_args = [
                "run",
                "--rm",
                "-d",
                "--name",
                container,
                "--env-file",
                str(env_file),
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--memory",
                "1536m",
                "--cpus",
                "1",
                "-p",
                "127.0.0.1::8080",
                "--mount",
                f"type=volume,source={volumes['data']},target=/data",
                "--mount",
                f"type=volume,source={volumes['system']},target=/hugegraph-server/rocksdb-data",
                "--mount",
                f"type=volume,source={volumes['config']},target=/hugegraph-server/conf/graphs",
                IMAGE,
            ]
            docker(*run_args)
            endpoint = "http://" + docker("port", container, "8080/tcp").splitlines()[0]
            wait_ready(endpoint)
            provider, resource, other, reader, writer, edge_id = fixture(
                endpoint, password
            )
            docker("restart", container)
            # Docker may reassign a dynamically published port on restart.
            endpoint = "http://" + docker("port", container, "8080/tcp").splitlines()[0]
            wait_ready(endpoint)
            provider = HugeGraph(endpoint=endpoint, password=password)
            provider.validate_recovery(resource)
            assert provider.scoped(reader).request(
                "GET", "/graphs/" + graph_name(resource) + "/graph/vertices"
            )["vertices"]
            # A new container must recover graph definitions and identities
            # from the same volumes, as happens during a Compose recreation.
            docker("stop", container)
            for _ in range(30):
                removed = subprocess.run(
                    ["docker", "container", "inspect", container],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
                if removed.returncode != 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Stopped HugeGraph fixture was not removed")
            docker(*run_args)
            endpoint = "http://" + docker("port", container, "8080/tcp").splitlines()[0]
            wait_ready(endpoint)
            provider = HugeGraph(endpoint=endpoint, password=password)
            provider.validate_recovery(resource)
            assert provider.scoped(reader).request(
                "GET", "/graphs/" + graph_name(resource) + "/graph/vertices"
            )["vertices"]
            assert provider.scoped(reader).request(
                "GET", "/graphs/" + graph_name(resource) + "/graph/edges"
            )["edges"]
            provider.scoped(writer).request(
                "DELETE",
                "/graphs/"
                + graph_name(resource)
                + "/graph/edges/"
                + quote(edge_id, safe=""),
            )
            assert not provider.scoped(reader).request(
                "GET", "/graphs/" + graph_name(resource) + "/graph/edges"
            )["edges"]
            provider.revoke(resource, reader)
            try:
                provider.scoped(reader).request(
                    "GET", "/graphs/" + graph_name(resource) + "/schema/propertykeys"
                )
            except StoreError:
                pass
            else:
                raise AssertionError("Revoked HugeGraph user can still read")
            provider.revoke(resource, writer)
            provider.purge(resource)
            provider.purge(other)
            print("HugeGraph fixture lifecycle and isolation checks passed")
        finally:
            subprocess.run(
                ["docker", "stop", container],
                check=False,
                capture_output=True,
                timeout=90,
            )
            for volume in volumes.values():
                subprocess.run(
                    ["docker", "volume", "rm", volume],
                    check=False,
                    capture_output=True,
                    timeout=90,
                )


if __name__ == "__main__":
    main()
