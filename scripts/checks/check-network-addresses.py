#!/usr/bin/env python3
"""Validate fixed Docker addresses without printing configuration secrets."""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import ipaddress
import json
import subprocess

from scripts.internal.env import settings


NETWORK = "developer-platform"
FIXED_SERVICES = {
    "neo4j-controller": ("NEO4J_CONTROLLER_IP", "172.30.80.31"),
    "postgres-exporter": ("POSTGRES_EXPORTER_IP", "172.30.80.30"),
    "postgres": ("POSTGRES_IP", "172.30.80.10"),
    "platform-api": ("PLATFORM_API_IP", "172.30.80.11"),
    "keycloak": ("KEYCLOAK_IP", "172.30.80.12"),
    "telemetry-gateway": ("TELEMETRY_GATEWAY_IP", "172.30.80.13"),
    "alloy": ("ALLOY_IP", "172.30.80.14"),
    "store-access": ("STORE_RELAY_IP", "172.30.80.15"),
    "rustfs": ("RUSTFS_IP", "172.30.80.16"),
    "opensearch": ("OPENSEARCH_IP", "172.30.80.17"),
    "qdrant": ("QDRANT_IP", "172.30.80.18"),
    "opensearch-init": ("OPENSEARCH_INIT_IP", "172.30.80.19"),
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
    search_subnet, _ = console_addresses(config)
    if subnet.overlaps(search_subnet):
        raise ValueError('The isolated search-console subnet must not overlap PLATFORM_SUBNET.')
    return subnet, result


def console_addresses(config):
    try:
        subnet = ipaddress.IPv4Network(config.get('STORE_SEARCH_CONSOLE_SUBNET', '172.30.81.0/29'))
        result = {'platform-api': ipaddress.IPv4Address(config.get('STORE_SEARCH_API_IP', '172.30.81.2')),
            'opensearch-dashboards': ipaddress.IPv4Address(config.get('OPENSEARCH_DASHBOARDS_IP', '172.30.81.3'))}
        if len(set(result.values())) != 2 or any(address not in subnet or address in
                (subnet.network_address, subnet.broadcast_address, subnet.network_address + 1) for address in result.values()):
            raise ValueError()
    except ValueError:
        raise ValueError('Search-console addresses must be distinct usable IPv4 addresses in their isolated subnet, excluding its gateway.') from None
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
    parser.add_argument("--validate-networks", action="store_true", help="Also refuse changes to existing network subnets, without checking container ownership")
    args = parser.parse_args()
    config = settings()
    subnet, fixed = addresses(config)
    if args.validate_only:
        print("Fixed Docker address settings are valid.")
        return
    existing = docker("network", "ls", "--format", "{{.Name}}").splitlines()

    def labels(container_id):
        return json.loads(docker("inspect", container_id, "--format", "{{json .Config.Labels}}")) or {}

    search_subnet, search_fixed = console_addresses(config)
    errors = []
    for name, selected_subnet, selected_fixed in ((NETWORK, subnet, fixed),
            ('developer-platform-search-consoles', search_subnet, search_fixed)):
        if name in existing:
            network = json.loads(docker('network', 'inspect', name))[0]
            if args.validate_networks:
                configured = network.get('IPAM', {}).get('Config', [])
                if not any(item.get('Subnet') == str(selected_subnet) for item in configured):
                    raise ValueError('Existing Docker network subnet differs from configuration; network changes require a separate migration before deployment.')
            else:
                errors.extend(conflicts(selected_subnet, selected_fixed, network, labels))
    if errors:
        raise ValueError("Fixed Docker address conflict: " + "; ".join(errors) + ". "
                         "For Compose-owned conflicts, redeploy with ansible/deploy.yml to stop and "
                         "remove Compose containers while preserving volumes and the k3d network. "
                         "Other owners require operator intervention; bootstrap never disconnects them.")
    print("Fixed settings and existing Docker network subnets are valid." if args.validate_networks else
          "Fixed Docker addresses are available or held by their intended services.")


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
