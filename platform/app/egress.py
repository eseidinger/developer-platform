"""Conservative operator-controlled outbound CIDR/port policy."""
import ipaddress
import os


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
