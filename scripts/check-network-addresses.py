#!/usr/bin/env python3
"""Validate fixed Docker addresses without printing configuration secrets."""
import argparse
import ipaddress
import json
import subprocess
import sys

from env import settings


NETWORK = "developer-platform"
FIXED_SERVICES = {
    "postgres": ("POSTGRES_IP", "172.30.80.10"),
    "platform-api": ("PLATFORM_API_IP", "172.30.80.11"),
    "keycloak": ("KEYCLOAK_IP", "172.30.80.12"),
    "telemetry-gateway": ("TELEMETRY_GATEWAY_IP", "172.30.80.13"),
    "alloy": ("ALLOY_IP", "172.30.80.14"),
    "proxy": ("PROXY_IP", "172.30.80.20"),
    "blackbox-exporter": ("BLACKBOX_EXPORTER_IP", "172.30.80.21"),
    "prometheus": ("PROMETHEUS_IP", "172.30.80.22"),
    "grafana": ("GRAFANA_IP", "172.30.80.23"),
    "tempo": ("TEMPO_IP", "172.30.80.24"),
    "loki": ("LOKI_IP", "172.30.80.25"),
    "alertmanager": ("ALERTMANAGER_IP", "172.30.80.26"),
    "node-exporter": ("NODE_EXPORTER_IP", "172.30.80.27"),
    "keycloak-db-init": ("KEYCLOAK_DB_INIT_IP", "172.30.80.28"),
    "keycloak-realm-init": ("KEYCLOAK_REALM_INIT_IP", "172.30.80.29"),
}


def addresses(config):
    try:
        subnet = ipaddress.IPv4Network(config.get("PLATFORM_SUBNET", "172.30.80.0/24"))
        result = {service: ipaddress.IPv4Address(config.get(key, default))
                  for service, (key, default) in FIXED_SERVICES.items()}
    except ValueError:
        raise ValueError("PLATFORM_SUBNET and fixed service addresses must be valid IPv4 values.") from None
    if len(set(result.values())) != len(result):
        raise ValueError("Fixed service IP addresses must be distinct.")
    for service, address in result.items():
        if address not in subnet or address in (subnet.network_address, subnet.broadcast_address):
            raise ValueError(f"The fixed address for {service} must be a usable address in PLATFORM_SUBNET.")
    return subnet, result


def conflicts(subnet, fixed, network, labels):
    configured = network.get("IPAM", {}).get("Config", [])
    if not any(item.get("Subnet") == str(subnet) for item in configured):
        raise ValueError("Existing developer-platform network does not match PLATFORM_SUBNET; "
                         "do not remove the network while k3d is attached.")
    gateways = {item.get("Gateway") for item in configured}
    errors = []
    for service, address in fixed.items():
        if str(address) in gateways:
            errors.append(f"{service}: {address} is the Docker network gateway")
        for container_id, endpoint in network.get("Containers", {}).items():
            assigned = endpoint.get("IPv4Address", "").split("/", 1)[0]
            if assigned != str(address):
                continue
            owner = labels(container_id)
            if (owner.get("com.docker.compose.project") != NETWORK
                    or owner.get("com.docker.compose.service") != service):
                errors.append(f"{service}: {address} is occupied by {endpoint.get('Name', container_id)}")
    return errors


def docker(*arguments):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
    if result.returncode:
        # Do not forward arbitrary daemon diagnostics or full inspection data.
        raise ValueError("Docker network inspection failed; check Docker availability and permissions.")
    return result.stdout


def check():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate settings without Docker inspection")
    args = parser.parse_args()
    subnet, fixed = addresses(settings())
    if args.validate_only:
        print("Fixed Docker address settings are valid.")
        return
    existing = docker("network", "ls", "--filter", f"name=^{NETWORK}$", "--format", "{{.Name}}").splitlines()
    if NETWORK not in existing:
        print("Platform Docker network will be created during bootstrap.")
        return
    network = json.loads(docker("network", "inspect", NETWORK))[0]

    def labels(container_id):
        return json.loads(docker("inspect", container_id, "--format", "{{json .Config.Labels}}")) or {}

    errors = conflicts(subnet, fixed, network, labels)
    if errors:
        raise ValueError("Fixed Docker address conflict: " + "; ".join(errors) + ". "
                         "For Compose-owned conflicts, redeploy with ansible/deploy.yml to stop and "
                         "remove Compose containers while preserving volumes and the k3d network. "
                         "Other owners require operator intervention; bootstrap never disconnects them.")
    print("Fixed Docker addresses are available or held by their intended services.")


if __name__ == "__main__":
    try:
        check()
    except (ValueError, OSError, KeyError):
        # ValueErrors here are deliberately sanitized above; other errors may
        # include private environment-file contents and must not be displayed.
        error = sys.exc_info()[1]
        if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError):
            print(str(error), file=sys.stderr)
        else:
            print("Unable to validate platform Docker addresses; inspect configuration privately.", file=sys.stderr)
        sys.exit(1)
