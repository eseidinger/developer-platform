"""Conservative opt-in aggregate Kubernetes request admission."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import os

from kubernetes.utils.quantity import parse_quantity

from .manifests import DEFAULT_RESOURCES, TELEMETRY_FORWARDER_RESOURCES
from .host_capacity import read_snapshot


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _items(runtime, api_version, kind):
    return _get(runtime.resources.get(api_version=api_version, kind=kind).get(namespace=""), "items", []) or []


def _cpu_millicores(value, rounding=ROUND_CEILING):
    quantity = parse_quantity(str(value)) * Decimal(1000)
    if quantity < 0:
        raise ValueError("negative CPU quantity")
    return int(quantity.to_integral_value(rounding=rounding))


def _memory_mib(value, rounding=ROUND_CEILING):
    quantity = parse_quantity(str(value)) / Decimal(1024 * 1024)
    if quantity < 0:
        raise ValueError("negative memory quantity")
    return int(quantity.to_integral_value(rounding=rounding))


def _request_total(containers):
    total = {"cpu": 0, "memory": 0}
    for container in containers:
        requests = _get(_get(container, "resources", {}), "requests", {}) or {}
        for key, parser in (("cpu", _cpu_millicores), ("memory", _memory_mib)):
            if _get(requests, key) is not None:
                total[key] += parser(_get(requests, key))
    return total


def _proposed(spec):
    components = spec.get("components") or [{"type": "service", "resources": spec.get("resources")}]
    total = {"cpu": 0, "memory": 0}
    for component in components:
        resources = component.get("resources") or DEFAULT_RESOURCES
        replicas = component.get("replicas", 1) if component["type"] == "service" else 1
        containers = [{"resources": resources}]
        if component.get("tracing", {}).get("enabled"):
            containers.append({"resources": TELEMETRY_FORWARDER_RESOURCES})
        values = _request_total(containers)
        for key in total:
            total[key] += values[key] * replicas
    return total


def _pod_requests(spec):
    """Account for restartable init sidecars throughout startup and steady state."""
    sidecars = {"cpu": 0, "memory": 0}
    startup_peak = {"cpu": 0, "memory": 0}
    for container in _get(spec, "initContainers", []) or []:
        values = _request_total([container])
        if _get(container, "restartPolicy") == "Always":
            sidecars = {key: sidecars[key] + values[key] for key in sidecars}
            values = sidecars
        else:
            values = {key: sidecars[key] + values[key] for key in sidecars}
        startup_peak = {key: max(startup_peak[key], values[key]) for key in sidecars}
    application = _request_total(_get(spec, "containers", []) or [])
    return {key: max(application[key] + sidecars[key], startup_peak[key]) for key in sidecars}


def snapshot(runtime, log):
    """Intersect host and scheduler budgets; infrastructure is charged once."""
    if os.environ.get("CAPACITY_ADMISSION_ENABLED", "false").lower() != "true":
        return {"state": "disabled", "enabled": False}
    if runtime is None:
        return {"state": "unavailable", "enabled": True, "reason": "KubernetesApiUnavailable"}
    host = read_snapshot()
    if host['state'] != 'ok':
        return {'state': 'unavailable', 'enabled': True, 'reason': host['reason']}
    try:
        nodes, pods = _items(runtime, "v1", "Node"), _items(runtime, "v1", "Pod")
    except Exception as exc:
        log.error("Capacity admission query failed error_type=%s", type(exc).__name__)
        return {"state": "unavailable", "enabled": True, "reason": "KubernetesApiUnavailable"}
    try:
        reported = {"cpu": 0, "memory": 0}
        allocatable = {"cpu": 0, "memory": 0}
        observed_names = set()
        for node in nodes:
            name = _get(_get(node, 'metadata', {}), 'name')
            observed_names.add(name)
            limit = host['nodes'][name]
            values = _get(_get(node, "status", {}), "allocatable", {}) or {}
            node_cpu = _cpu_millicores(_get(values, "cpu"), ROUND_FLOOR)
            node_memory = _memory_mib(_get(values, "memory"), ROUND_FLOOR)
            reported['cpu'] += node_cpu
            reported['memory'] += node_memory
            allocatable['cpu'] += min(node_cpu, limit['cpu_millicores'])
            allocatable['memory'] += min(node_memory, limit['memory_mib'])
        if observed_names != set(host['nodes']):
            raise KeyError('Node topology changed')
        allocatable['cpu'] = min(allocatable['cpu'], host['capacity']['cpu_millicores'])
        allocatable['memory'] = min(allocatable['memory'], host['capacity']['memory_mib'])
        requested = {"cpu": 0, "memory": 0}
        for pod in pods:
            if _get(_get(pod, "status", {}), "phase") not in {"Succeeded", "Failed"}:
                values = _pod_requests(_get(pod, "spec", {}))
                for key in requested:
                    requested[key] += values[key]
    except KeyError:
        return {'state': 'unavailable', 'enabled': True, 'reason': 'HostKubernetesTopologyMismatch'}
    except (ArithmeticError, TypeError, ValueError) as exc:
        log.error("Capacity admission data invalid error_type=%s", type(exc).__name__)
        return {"state": "unavailable", "enabled": True, "reason": "InvalidKubernetesCapacityData"}
    try:
        reserve = {"cpu": int(os.environ.get("CAPACITY_RESERVE_CPU_MILLICORES", "2000")),
                   "memory": int(os.environ.get("CAPACITY_RESERVE_MEMORY_MIB", "8192"))}
        overhead = {'cpu': int(os.environ.get('CAPACITY_HOST_OVERHEAD_CPU_MILLICORES', '2000')),
                    'memory': int(os.environ.get('CAPACITY_HOST_OVERHEAD_MEMORY_MIB', '1024'))}
        node_overhead = {'cpu': 0, 'memory': int(os.environ.get('CAPACITY_KUBERNETES_OVERHEAD_MEMORY_MIB', '4096'))}
        if any(value < 0 for value in [*reserve.values(), *overhead.values(), *node_overhead.values()]):
            raise ValueError
    except ValueError:
        return {"state": "unavailable", "enabled": True, "reason": "InvalidCapacityReserve"}
    def public(values):
        return {"cpu_millicores": values["cpu"], "memory_mib": values["memory"]}
    shared = {'cpu': sum(service['cpu_millicores'] for service in host['services']),
              'memory': sum(service['memory_mib'] for service in host['services'])}
    infrastructure = {key: max(reserve[key], shared[key] + overhead[key] + node_overhead[key])
                      for key in reserve}
    host_capacity = {'cpu': host['capacity']['cpu_millicores'], 'memory': host['capacity']['memory_mib']}
    host_available = {key: host_capacity[key] - infrastructure[key] - requested[key] for key in reserve}
    cluster_available = {key: allocatable[key] - node_overhead[key] - requested[key] for key in reserve}
    available = {key: min(host_available[key], cluster_available[key]) for key in reserve}
    limiting = {key: 'host' if host_available[key] < cluster_available[key] else 'kubernetes' for key in reserve}
    effective_reserve = {key: allocatable[key] - requested[key] - available[key] for key in reserve}
    return {"state": "ok", "enabled": True, "allocatable": public(allocatable),
            "requested": public(requested), "reserve": public(effective_reserve), "available": public(available),
            'limiting': limiting,
            'host': {'state': 'ok', 'captured_at': host['captured_at'], 'capacity': public(host_capacity),
                     'minimum_reserve': public(reserve), 'shared_services': public(shared),
                     'overhead': public(overhead), 'infrastructure_reserved': public(infrastructure),
                     'available': public(host_available),
                     'cpu_unbounded_services': [service['name'] for service in host['services'] if service['cpu_unbounded']]},
            'kubernetes': {'reported_allocatable': public(reported), 'allocatable': public(allocatable),
                           'runtime_overhead': public(node_overhead), 'requested': public(requested),
                           'available': public(cluster_available)}}


def assess(runtime, spec, log):
    """Return a safe decision; enabled admission never assumes missing capacity is free."""
    current = snapshot(runtime, log)
    if current["state"] == "disabled":
        return {"state": "disabled"}
    if current["state"] != "ok":
        return {"state": "unavailable", "reason": current["reason"]}
    proposed = _proposed(spec)
    available = {"cpu": current["available"]["cpu_millicores"],
                 "memory": current["available"]["memory_mib"]}
    if any(proposed[key] > available[key] for key in proposed):
        return {"state": "rejected", "reason": "InsufficientReservedCapacity", "available": available,
                "proposed": proposed, 'limiting': current['limiting']}
    return {"state": "accepted", "available": available, "proposed": proposed, 'limiting': current['limiting']}
