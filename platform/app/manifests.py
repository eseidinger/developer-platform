"""Runtime-independent Kubernetes workload contract."""
import ipaddress
import re

def validate_name(value):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}[a-z0-9]|[a-z]", value):
        raise ValueError("Use 1-32 lowercase letters, digits or hyphens; start with a letter.")
    return value

def resources(name, image, port, domain, database_ip, password):
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
            "replicas": 1, "selector": {"matchLabels": selector},
            "template": {"metadata": {"labels": selector}, "spec": {
                "automountServiceAccountToken": False,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
                                    "runAsGroup": 10001, "fsGroup": 10001,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "app", "image": image,
                    "ports": [{"containerPort": port}],
                    "envFrom": [{"secretRef": {"name": "database"}}],
                    "securityContext": {"allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                    "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                                  "limits": {"cpu": "500m", "memory": "256Mi"}},
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
