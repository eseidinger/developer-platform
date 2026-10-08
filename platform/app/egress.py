"""Conservative operator-controlled outbound CIDR/port policy."""
import ipaddress
import os
import re
import socket


def _cidrs():
    try:
        return [ipaddress.ip_network(value.strip())
                for value in os.environ.get("ALLOWED_EGRESS_CIDRS", "").split(",") if value.strip()]
    except ValueError as exc:
        raise ValueError("operator egress policy is invalid") from exc


def _ports():
    try:
        ports = {int(value) for value in os.environ.get("ALLOWED_EGRESS_PORTS", "").split(",") if value.strip()}
    except ValueError as exc:
        raise ValueError("operator egress policy is invalid") from exc
    if any(port < 1 or port > 65535 for port in ports):
        raise ValueError("operator egress policy is invalid")
    return ports


def validate(destination: dict) -> dict:
    try:
        network = ipaddress.ip_network(destination["cidr"], strict=False)
    except ValueError as exc:
        raise ValueError("outbound cidr must be a valid CIDR") from exc
    port = destination["port"]
    if not any(network.subnet_of(allowed) for allowed in _cidrs()) or port not in _ports():
        raise ValueError("outbound destination is not allowed by operator policy")
    return {"cidr": str(network), "port": port}


def resolve(destination: dict) -> dict:
    """Resolve an operator-approved DNS egress destination to immutable CIDRs.

    NetworkPolicy has no DNS selector. Resolution is therefore deliberately done
    when the desired state is accepted/applied; a later DNS change requires a new
    deployment rather than silently widening egress.
    """
    hostname = destination["dns"].lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*", hostname):
        raise ValueError("outbound dns must be a valid hostname")
    try:
        answers = socket.getaddrinfo(hostname, destination["port"], type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("outbound dns could not be resolved") from exc
    addresses = sorted({answer[4][0] for answer in answers})
    if not addresses:
        raise ValueError("outbound dns could not be resolved")
    cidrs = []
    for address in addresses:
        ip = ipaddress.ip_address(address)
        cidr = str(ipaddress.ip_network(f"{ip}/{ip.max_prefixlen}", strict=False))
        validate({"cidr": cidr, "port": destination["port"]})
        cidrs.append(cidr)
    return {"dns": hostname, "port": destination["port"], "resolved_cidrs": cidrs}
