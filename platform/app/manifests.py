"""Runtime-independent Kubernetes workload contract."""
import ipaddress
import re

from .config import env_list

def validate_name(value):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}[a-z0-9]|[a-z]", value):
        raise ValueError("Use 1-32 lowercase letters, digits or hyphens; start with a letter.")
    return value

# Holds user-supplied secret values; written only through the secrets API, never by a deploy.
SECRET_NAME = "app-secrets"
DEFAULT_RESOURCES = {"requests": {"cpu": "100m", "memory": "128Mi"},
                     "limits": {"cpu": "500m", "memory": "256Mi"}}
# Rolling updates briefly run two pods, so twice these maxima must fit the namespace quota.
MAX_RESOURCES = {"requests": {"cpu": 1000, "memory": 1024}, "limits": {"cpu": 2000, "memory": 2048}}


def _millicores(value):
    text = str(value)
    if re.fullmatch(r"[0-9]{1,5}m", text):
        return int(text[:-1])
    if re.fullmatch(r"[0-9]{1,2}(\.[0-9]{1,3})?", text):
        return round(float(text) * 1000)
    raise ValueError("CPU must look like 250m or 0.25")


def _mebibytes(value):
    match = re.fullmatch(r"([0-9]{1,5})(Mi|Gi)", str(value))
    if not match:
        raise ValueError("Memory must look like 256Mi or 1Gi")
    return int(match[1]) * (1024 if match[2] == "Gi" else 1)


def normalize_resources(value):
    """Merge requested CPU/memory with the defaults and return canonical, validated values."""
    if not isinstance(value, dict) or set(value) - {"requests", "limits"}:
        raise ValueError("resources accepts only requests and limits")
    parsed = {}
    for section, defaults in DEFAULT_RESOURCES.items():
        given = value.get(section) or {}
        if not isinstance(given, dict) or set(given) - {"cpu", "memory"}:
            raise ValueError(f"{section} accepts only cpu and memory")
        merged = {**defaults, **given}
        cpu, memory = _millicores(merged["cpu"]), _mebibytes(merged["memory"])
        if not 0 < cpu <= MAX_RESOURCES[section]["cpu"] or not 0 < memory <= MAX_RESOURCES[section]["memory"]:
            raise ValueError(f"{section} are outside the supported range")
        parsed[section] = {"cpu": cpu, "memory": memory}
    if any(parsed["requests"][k] > parsed["limits"][k] for k in ("cpu", "memory")):
        raise ValueError("requests must not exceed limits")
    return {section: {"cpu": f"{v['cpu']}m", "memory": f"{v['memory']}Mi"} for section, v in parsed.items()}


def resources(name, image, port, domain, database_ip, password, workload_resources=None, configuration=None):
    validate_name(name)
    ipaddress.IPv4Address(database_ip)
    namespace = "project-" + name
    labels = {"app.kubernetes.io/name": name, "platform.example/managed": "true"}
    def obj(api, kind, objname, **fields):
        return {"apiVersion": api, "kind": kind,
                "metadata": {"name": objname, "namespace": namespace, "labels": labels}, **fields}
    selector = {"app.kubernetes.io/name": name}
    dbname = "project_" + name.replace("-", "_")
    return [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {
            "name": namespace, "labels": {
                "platform.example/managed": "true",
                "pod-security.kubernetes.io/enforce": "restricted",
                "pod-security.kubernetes.io/enforce-version": "v1.36"}}},
        obj("v1", "ResourceQuota", "budget", spec={"hard": {
            "requests.cpu": "2", "requests.memory": "2Gi", "limits.cpu": "4",
            "limits.memory": "4Gi", "pods": "10", "services": "5",
            "services.loadbalancers": "0", "services.nodeports": "0",
            "persistentvolumeclaims": "0"}}),
        obj("v1", "LimitRange", "defaults", spec={"limits": [{
            "type": "Container", "default": {"cpu": "500m", "memory": "256Mi"},
            "defaultRequest": {"cpu": "100m", "memory": "128Mi"}}]}),
        obj("v1", "Secret", "database", type="Opaque", stringData={
            "PGHOST": database_ip, "PGPORT": "5432", "PGDATABASE": dbname,
            "PGUSER": dbname, "PGPASSWORD": password}),
        obj("networking.k8s.io/v1", "NetworkPolicy", "isolation", spec={
            "podSelector": {}, "policyTypes": ["Ingress", "Egress"],
            "ingress": [
                {"from": [{"podSelector": {}}]},
                {"from": [{"namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": "kube-system"}},
                    "podSelector": {"matchLabels": {"app.kubernetes.io/name": "traefik"}}}],
                 "ports": [{"protocol": "TCP", "port": port}]}],
            "egress": [
                {"to": [{"podSelector": {}}]},
                {"to": [{"namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": "kube-system"}},
                    "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}],
                 "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
                {"to": [{"ipBlock": {"cidr": database_ip + "/32"}}],
                 "ports": [{"protocol": "TCP", "port": 5432}]}]}),
        obj("apps/v1", "Deployment", name, spec={
            "replicas": 1, "progressDeadlineSeconds": 120,
            "selector": {"matchLabels": selector},
            "template": {"metadata": {"labels": selector}, "spec": {
                "automountServiceAccountToken": False,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
                                    "runAsGroup": 10001, "fsGroup": 10001,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "app", "image": image,
                    "ports": [{"containerPort": port}],
                    "envFrom": [{"secretRef": {"name": "database"}},
                                {"secretRef": {"name": SECRET_NAME, "optional": True}}],
                    **({"env": env_list(configuration)} if configuration else {}),
                    "securityContext": {"allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                    "resources": workload_resources or DEFAULT_RESOURCES,
                    "readinessProbe": {"tcpSocket": {"port": port}, "periodSeconds": 5},
                    "livenessProbe": {"tcpSocket": {"port": port}, "initialDelaySeconds": 30},
                    "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}],
                "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "64Mi"}}]}}}),
        obj("v1", "Service", name, spec={"selector": selector,
            "ports": [{"port": 80, "targetPort": port}]}),
        obj("networking.k8s.io/v1", "Ingress", name, spec={
            "ingressClassName": "traefik", "rules": [{"host": name + "." + domain,
            "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {
                "service": {"name": name, "port": {"number": 80}}}}]}}]})
    ]


def component_resources(name, components, database_ip, password, configuration=None):
    """Build internal service and scheduled-job resources for a v1alpha2 application.

    Component names are scoped by the application namespace, so they form the stable
    DNS names used for service-to-service communication (``<component>`` or
    ``<component>.<namespace>``).  This deliberately creates no public Ingress.
    """
    validate_name(name)
    ipaddress.IPv4Address(database_ip)
    namespace = "project-" + name
    labels = {"app.kubernetes.io/name": name, "platform.example/managed": "true"}

    def obj(api, kind, objname, **fields):
        return {"apiVersion": api, "kind": kind,
                "metadata": {"name": objname, "namespace": namespace, "labels": labels}, **fields}

    def pod_spec(component, restart_policy=None):
        container = {"name": component["name"], "image": component["resolved_image"],
                     "envFrom": [{"secretRef": {"name": "database"}},
                                 {"secretRef": {"name": SECRET_NAME, "optional": True}}],
                     **({"env": env_list(configuration)} if configuration else {}),
                     "securityContext": {"allowPrivilegeEscalation": False,
                         "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                     "resources": component.get("resources") or DEFAULT_RESOURCES,
                     "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}
        if component.get("command") is not None:
            container["command"] = component["command"]
        if component.get("args") is not None:
            container["args"] = component["args"]
        if component["type"] == "service":
            ports = component.get("ports") or []
            if ports:
                container["ports"] = [{"name": port["name"], "containerPort": port["port"]} for port in ports]
                probe_port = ports[0]["port"]
                container["readinessProbe"] = {"tcpSocket": {"port": probe_port}, "periodSeconds": 5}
                container["livenessProbe"] = {"tcpSocket": {"port": probe_port}, "initialDelaySeconds": 30}
        spec = {"automountServiceAccountToken": False,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
                    "runAsGroup": 10001, "fsGroup": 10001,
                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [container], "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "64Mi"}}]}
        if restart_policy:
            spec["restartPolicy"] = restart_policy
        return spec

    dbname = "project_" + name.replace("-", "_")
    manifests = [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace, "labels": {
            "platform.example/managed": "true", "pod-security.kubernetes.io/enforce": "restricted",
            "pod-security.kubernetes.io/enforce-version": "v1.36"}}},
        obj("v1", "ResourceQuota", "budget", spec={"hard": {
            "requests.cpu": "2", "requests.memory": "2Gi", "limits.cpu": "4", "limits.memory": "4Gi",
            "pods": "10", "services": "5", "services.loadbalancers": "0", "services.nodeports": "0",
            "persistentvolumeclaims": "0"}}),
        obj("v1", "LimitRange", "defaults", spec={"limits": [{"type": "Container",
            "default": {"cpu": "500m", "memory": "256Mi"},
            "defaultRequest": {"cpu": "100m", "memory": "128Mi"}}]}),
        obj("v1", "Secret", "database", type="Opaque", stringData={
            "PGHOST": database_ip, "PGPORT": "5432", "PGDATABASE": dbname, "PGUSER": dbname,
            "PGPASSWORD": password}),
        obj("networking.k8s.io/v1", "NetworkPolicy", "isolation", spec={
            "podSelector": {}, "policyTypes": ["Ingress", "Egress"],
            "ingress": [{"from": [{"podSelector": {}}]}],
            "egress": [{"to": [{"podSelector": {}}]},
                {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                          "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}],
                 "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
                {"to": [{"ipBlock": {"cidr": database_ip + "/32"}}],
                 "ports": [{"protocol": "TCP", "port": 5432}]}]})]
    for component in components:
        component_labels = {"app.kubernetes.io/name": name, "platform.example/component": component["name"]}
        if component["type"] == "service":
            manifests.append(obj("apps/v1", "Deployment", component["name"], spec={
                "replicas": component.get("replicas", 1), "progressDeadlineSeconds": 120,
                "selector": {"matchLabels": component_labels},
                "template": {"metadata": {"labels": component_labels}, "spec": pod_spec(component)}}))
            ports = component.get("ports") or []
            if ports:
                manifests.append(obj("v1", "Service", component["name"], spec={"selector": component_labels,
                    "ports": [{"name": port["name"], "port": port["port"], "targetPort": port["name"]}
                              for port in ports]}))
        else:
            manifests.append(obj("batch/v1", "CronJob", component["name"], spec={
                "schedule": component["schedule"], "timeZone": component.get("time_zone", "UTC"),
                "concurrencyPolicy": component.get("concurrency_policy", "Forbid"),
                "successfulJobsHistoryLimit": 3, "failedJobsHistoryLimit": 3,
                "jobTemplate": {"metadata": {"labels": component_labels}, "spec": {"backoffLimit": 1, "template": {"metadata": {"labels": component_labels},
                    "spec": pod_spec(component, "Never")}}}}))
    return manifests
