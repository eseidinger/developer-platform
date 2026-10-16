#!/usr/bin/env python3
"""Record the pinned k3s control-plane flannel source used by service proxies."""
import ipaddress
import json
import os
from pathlib import Path
import sys
import tempfile


def proxy_sources(nodes):
    sources = set()
    for node in nodes["items"]:
        if "node-role.kubernetes.io/control-plane" not in node["metadata"].get("labels", {}):
            continue
        spec = node["spec"]
        for cidr in spec.get("podCIDRs", [spec.get("podCIDR")]):
            network = ipaddress.ip_network(cidr)
            sources.add(str(ipaddress.ip_network((network.network_address, network.max_prefixlen))))
    if not sources:
        raise ValueError("No control-plane PodCIDR found for metrics proxy access")
    return sorted(sources)


def main():
    sources = proxy_sources(json.load(sys.stdin))
    target = Path(".env")
    key = "PLATFORM_METRICS_PROXY_CIDRS"
    lines = [line for line in target.read_text().splitlines() if not line.startswith(key + "=")]
    lines.append(key + "=" + ",".join(sources))
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
        os.fchmod(output.fileno(), 0o600)
        output.write("\n".join(lines) + "\n")
    os.replace(temporary, target)
    print("Recorded metrics proxy sources: " + ", ".join(sources))


if __name__ == "__main__":
    main()
