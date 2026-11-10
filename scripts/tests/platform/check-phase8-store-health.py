#!/usr/bin/env python3
"""Check deployed Phase 8 store health without changing platform resources."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

STORE_VOLUMES = {
    "couchdb": {"/opt/couchdb/data"},
    "hugegraph": {
        "/data",
        "/hugegraph-server/rocksdb-data",
        "/hugegraph-server/conf/graphs",
    },
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def docker(installation, *arguments):
    result = subprocess.run(
        ["docker", *arguments],
        cwd=installation,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    require(result.returncode == 0, "Docker inspection failed")
    return result.stdout.strip()


def response(opener, url):
    with opener.open(url, timeout=10) as result:
        require(result.status == 200, "HTTP health endpoint failed")
        return result.read()


def check_store(installation, service):
    container_id = docker(installation, "compose", "ps", "-q", service)
    require(container_id and "\n" not in container_id, service + " is not running")
    containers = json.loads(docker(installation, "inspect", container_id))
    require(len(containers) == 1, service + " inspection is ambiguous")
    container = containers[0]
    state = container["State"]
    require(state["Running"], service + " is stopped")
    require(
        state.get("Health", {}).get("Status") == "healthy", service + " is unhealthy"
    )

    settings = container["HostConfig"]
    require(settings.get("Memory", 0) > 0, service + " has no memory limit")
    require(settings.get("NanoCpus", 0) > 0, service + " has no CPU limit")
    require(not settings.get("PortBindings"), service + " publishes a host port")
    require(
        "@sha256:" in container["Config"]["Image"],
        service + " image is not digest-pinned",
    )

    named_volumes = {
        mount["Destination"]
        for mount in container["Mounts"]
        if mount["Type"] == "volume"
        and not re.fullmatch(r"[0-9a-f]{64}", mount.get("Name", ""))
    }
    # HugeGraph's image also declares an anonymous parent volume at
    # /hugegraph-server. Check the explicitly named backup targets separately
    # and report any anonymous image volumes for operator review.
    require(
        named_volumes == STORE_VOLUMES[service],
        service + " named persistent volumes differ",
    )
    anonymous = [
        mount["Destination"]
        for mount in container["Mounts"]
        if mount["Type"] == "volume"
        and re.fullmatch(r"[0-9a-f]{64}", mount.get("Name", ""))
    ]
    if anonymous:
        print("INFO " + service + " anonymous image volumes: " + ", ".join(anonymous))
    print("PASS " + service + " container, limits, private ports and volumes")


def check_metrics(opener, service):
    metric = "platform_native_" + service + "_up"
    query = urlencode({"query": metric + '{provider="' + service + '"}'})
    payload = json.loads(
        response(opener, "http://127.0.0.1:9090/api/v1/query?" + query)
    )
    require(payload.get("status") == "success", service + " metrics query failed")
    values = payload["data"]["result"]
    require(
        len(values) == 1 and values[0]["value"][1] == "1", service + " metric is not up"
    )
    print("PASS " + service + " Prometheus metric")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--installation",
        type=Path,
        default=Path("/opt/developer-platform"),
        help="Existing platform installation directory",
    )
    arguments = parser.parse_args()
    require(arguments.installation.is_dir(), "Installation directory is missing")

    opener = build_opener(ProxyHandler({}))
    response(opener, "http://127.0.0.1:8000/readyz")
    print("PASS Platform API readiness")
    for service in STORE_VOLUMES:
        check_store(arguments.installation, service)
        check_metrics(opener, service)


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as error:
        print("FAIL " + str(error), file=sys.stderr)
        raise SystemExit(1)
