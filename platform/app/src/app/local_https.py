"""Opt-in local HTTPS destinations and public trust for declared components.

Only the dedicated workload gateway may bypass the general private-subnet
egress prohibition. Raw CIDRs and other private service addresses remain denied.
"""

import hashlib
import ipaddress
import os
import re
import ssl
from pathlib import Path

CONFIG_MAP = "local-application-trust"
TRUST_PATH = "/var/run/platform-trust/ca-bundle.pem"
TRUST_ENVIRONMENT = {
    "SSL_CERT_FILE": TRUST_PATH,
    "REQUESTS_CA_BUNDLE": TRUST_PATH,
    "NODE_EXTRA_CA_CERTS": TRUST_PATH,
}


def destination(hostname, port):
    """Map only configured local HTTPS names to the isolated gateway address."""
    if os.environ.get("LOCAL_APPLICATION_HTTPS_ENABLED") != "true" or port != 443:
        return None
    apps = os.environ.get("APPS_DOMAIN", "apps.localhost").lower().rstrip(".")
    identity = (
        os.environ.get("IDENTITY_DOMAIN", "identity.localhost").lower().rstrip(".")
    )
    if not all(name.endswith(".localhost") for name in (apps, identity)):
        raise ValueError("Local HTTPS requires configured localhost domains")
    host = hostname.lower().rstrip(".")
    application = re.fullmatch(
        r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\." + re.escape(apps), host
    )
    if host != identity and (not application or application[1].startswith("console-")):
        return None
    address = ipaddress.IPv4Address(
        os.environ.get("LOCAL_APPLICATION_EDGE_IP", "172.30.80.32")
    )
    network = ipaddress.IPv4Network(os.environ.get("PLATFORM_SUBNET", "172.30.80.0/24"))
    if address not in network or address in (
        network.network_address,
        network.broadcast_address,
        network.network_address + 1,
    ):
        raise ValueError("Local HTTPS gateway must be a usable platform address")
    return str(address)


def attach(pod, component):
    """Give only a declaring application container name resolution and public CA trust."""
    hosts = {}
    for item in component.get("outbound", []):
        if item.get("dns") and (address := destination(item["dns"], item["port"])):
            hosts[item["dns"].lower().rstrip(".")] = address
    if not hosts:
        return None
    certificate = Path(
        os.environ.get(
            "LOCAL_APPLICATION_CA_BUNDLE",
            "/run/platform-trust/application-ca-bundle.pem",
        )
    ).read_text()
    ssl.create_default_context().load_verify_locations(cadata=certificate)
    container = pod["containers"][0]
    if {value["name"] for value in container.get("env", [])} & TRUST_ENVIRONMENT.keys():
        raise ValueError("Local HTTPS trust environment is platform managed")
    # Kubernetes server-side apply keys this list by IP, so both local names
    # must share one entry when they resolve to the same gateway.
    aliases = {}
    for host, address in sorted(hosts.items()):
        aliases.setdefault(address, []).append(host)
    pod["hostAliases"] = [
        {"ip": address, "hostnames": names} for address, names in aliases.items()
    ]
    pod["volumes"].append({"name": CONFIG_MAP, "configMap": {"name": CONFIG_MAP}})
    container["volumeMounts"].append(
        {"name": CONFIG_MAP, "mountPath": "/var/run/platform-trust", "readOnly": True}
    )
    container.setdefault("env", []).extend(
        {"name": key, "value": value} for key, value in TRUST_ENVIRONMENT.items()
    )
    return certificate


def apply(manifests, components, namespace):
    """Attach trust to declaring workloads; keep public certificates outside secrets."""
    selected = {component["name"]: component for component in components}
    certificate = None
    for manifest in manifests:
        if manifest["kind"] == "Deployment":
            template = manifest["spec"]["template"]
        elif manifest["kind"] == "CronJob":
            template = manifest["spec"]["jobTemplate"]["spec"]["template"]
        else:
            continue
        component = selected[
            template["metadata"]["labels"]["platform.example/component"]
        ]
        bundle = attach(template["spec"], component)
        if bundle:
            certificate = bundle
            # Replacing the public CA must also replace existing workload pods.
            template["metadata"].setdefault("annotations", {})[
                "platform.example/local-trust"
            ] = hashlib.sha256(bundle.encode()).hexdigest()
    if certificate:
        manifests.insert(
            1,
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": CONFIG_MAP,
                    "namespace": namespace,
                    "labels": {"platform.example/managed": "true"},
                },
                "data": {"ca-bundle.pem": certificate},
            },
        )
    return manifests
