"""Platform-managed browser proxies and the shared protected request path."""
import hashlib
import os

from .access_provider import derived_secret


ACCESS_NAMESPACE = "platform-access"
AUTHORIZER_LABELS = {"platform.example/access-role": "authorizer"}
PROXY_IMAGE = "quay.io/oauth2-proxy/oauth2-proxy:v7.15.1@sha256:39f08531587045a5443db43299bf8495696c99ed8d0e1fdcbe60534f7c02ce14"


def ingress_name(host):
    return "host-" + hashlib.sha256(host.encode()).hexdigest()[:24]


def protected_ingress(host, project=None):
    return {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
        "metadata": {"name": ingress_name(host), "namespace": ACCESS_NAMESPACE,
                     "labels": {"platform.example/managed": "true",
                                **({"platform.example/project": project} if project else {})}},
        "spec": {"ingressClassName": "traefik", "rules": [{"host": host,
            "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {
                "service": {"name": "authorizer", "port": {"number": 8080}}}}]}}]}}


def protect_components(manifests, project, components):
    """Remove every broad ingress allowance to the public backend, including same-project pods."""
    public = [c for c in components if c.get("exposure") == "public" and c["type"] == "service"]
    if not public:
        return manifests
    names = [c["name"] for c in public]
    for manifest in manifests:
        if manifest["kind"] == "NetworkPolicy" and manifest["metadata"]["name"] == "isolation":
            manifest["spec"]["podSelector"] = {"matchExpressions": [
                {"key": "platform.example/component", "operator": "NotIn", "values": names}]}
            manifest["spec"]["ingress"] = [{"from": [{"podSelector": {}}]}]
    for component in public:
        selector = {"app.kubernetes.io/name": project, "platform.example/component": component["name"]}
        # Egress belongs to this selector too: exclude the public pod from the broad isolation policy.
        base = next(m for m in manifests if m["kind"] == "NetworkPolicy" and m["metadata"]["name"] == "isolation")
        manifests.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": component["name"] + "-access", "namespace": "project-" + project,
                         "labels": {"platform.example/managed": "true"}},
            "spec": {"podSelector": {"matchLabels": selector}, "policyTypes": ["Ingress", "Egress"],
                "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": ACCESS_NAMESPACE}}, "podSelector": {"matchLabels": AUTHORIZER_LABELS}}],
                    "ports": [{"protocol": "TCP", "port": component["ports"][0]["port"]}]}],
                "egress": base["spec"]["egress"]}})
    return manifests


def browser_name(policy):
    return "oauth-" + policy["id"].removeprefix("pol_")


def browser_manifests(policy):
    name = browser_name(policy)
    host = policy["spec"]["host"]
    issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    keycloak = os.environ.get("APPLICATION_IDENTITY_INTERNAL_URL", "http://172.30.80.12:8080") + "/realms/platform/protocol/openid-connect"
    labels = {"platform.example/access-role": "browser-proxy", "platform.example/access-policy": policy["id"]}

    def obj(kind, api="v1", **fields):
        return {"apiVersion": api, "kind": kind, "metadata": {"name": name, "namespace": ACCESS_NAMESPACE,
                "labels": {**labels, "platform.example/managed": "true"}}, **fields}

    env = {"OAUTH2_PROXY_PROVIDER": "oidc", "OAUTH2_PROXY_CLIENT_ID": "browser-" + policy["id"],
        "OAUTH2_PROXY_OIDC_ISSUER_URL": issuer, "OAUTH2_PROXY_REDIRECT_URL": "https://" + host + "/oauth2/callback",
        "OAUTH2_PROXY_HTTP_ADDRESS": "0.0.0.0:4180", "OAUTH2_PROXY_UPSTREAMS": "static://202",
        "OAUTH2_PROXY_EMAIL_DOMAINS": "*", "OAUTH2_PROXY_OIDC_EMAIL_CLAIM": "sub",
        "OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL": "true",
        "OAUTH2_PROXY_SCOPE": "openid profile email", "OAUTH2_PROXY_OIDC_GROUPS_CLAIM": "groups",
        "OAUTH2_PROXY_CODE_CHALLENGE_METHOD": "S256", "OAUTH2_PROXY_INSECURE_OIDC_SKIP_NONCE": "false",
        "OAUTH2_PROXY_SKIP_OIDC_DISCOVERY": "true", "OAUTH2_PROXY_LOGIN_URL": issuer + "/protocol/openid-connect/auth",
        "OAUTH2_PROXY_REDEEM_URL": keycloak + "/token", "OAUTH2_PROXY_OIDC_JWKS_URL": keycloak + "/certs",
        "OAUTH2_PROXY_SKIP_CLAIMS_FROM_PROFILE_URL": "true", "OAUTH2_PROXY_REVERSE_PROXY": "true",
        "OAUTH2_PROXY_SET_XAUTHREQUEST": "true", "OAUTH2_PROXY_PASS_ACCESS_TOKEN": "true",
        "OAUTH2_PROXY_COOKIE_NAME": "__Host-platform-session", "OAUTH2_PROXY_COOKIE_SECURE": "true",
        "OAUTH2_PROXY_COOKIE_HTTPONLY": "true", "OAUTH2_PROXY_COOKIE_SAMESITE": "lax",
        "OAUTH2_PROXY_COOKIE_REFRESH": "4m", "OAUTH2_PROXY_COOKIE_EXPIRE": "8h",
        "OAUTH2_PROXY_WHITELIST_DOMAINS": host, "OAUTH2_PROXY_SKIP_PROVIDER_BUTTON": "true",
        "OAUTH2_PROXY_REQUEST_LOGGING": "false", "OAUTH2_PROXY_AUTH_LOGGING": "false",
        "OAUTH2_PROXY_STANDARD_LOGGING": "false"}
    return [obj("Secret", type="Opaque", stringData={
        "OAUTH2_PROXY_CLIENT_SECRET": derived_secret(policy["id"], "browser"),
        "OAUTH2_PROXY_COOKIE_SECRET": derived_secret(policy["spec"]["sessionEpoch"], "cookie")}),
        obj("Deployment", "apps/v1", spec={"replicas": 1, "selector": {"matchLabels": labels},
            "template": {"metadata": {"labels": labels, "annotations": {
                "platform.example/session-epoch": policy["spec"]["sessionEpoch"]}}, "spec": {
                "automountServiceAccountToken": False,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "oauth2-proxy", "image": os.environ.get("OAUTH2_PROXY_IMAGE", PROXY_IMAGE),
                    "ports": [{"containerPort": 4180}], "env": [{"name": k, "value": v} for k, v in env.items()],
                    "envFrom": [{"secretRef": {"name": name}}],
                    "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                        "capabilities": {"drop": ["ALL"]}},
                    "resources": {"requests": {"cpu": "25m", "memory": "32Mi"}, "limits": {"cpu": "250m", "memory": "128Mi"}},
                    "readinessProbe": {"httpGet": {"path": "/ready", "port": 4180}},
                    "livenessProbe": {"httpGet": {"path": "/ping", "port": 4180}}}]}}}),
        obj("Service", spec={"selector": labels, "ports": [{"port": 4180, "targetPort": 4180}]})]


def shared_manifests(image, api_ip, identity_ip, internal_key, session_key):
    namespace = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ACCESS_NAMESPACE,
        "labels": {"pod-security.kubernetes.io/enforce": "restricted"}}}
    def obj(kind, name, api="v1", **fields):
        return {"apiVersion": api, "kind": kind, "metadata": {"name": name, "namespace": ACCESS_NAMESPACE,
                "labels": {"platform.example/managed": "true"}}, **fields}
    return [namespace,
        obj("Secret", "authorizer", type="Opaque", stringData={"APPLICATION_ACCESS_KEY": internal_key,
            "APPLICATION_SESSION_KEY": session_key}),
        obj("Service", "authorizer", spec={"selector": AUTHORIZER_LABELS, "ports": [{"port": 8080, "targetPort": 8080}]}),
        obj("Deployment", "authorizer", "apps/v1", spec={"replicas": 2, "selector": {"matchLabels": AUTHORIZER_LABELS},
            "template": {"metadata": {"labels": AUTHORIZER_LABELS}, "spec": {
                "automountServiceAccountToken": False,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "authorizer", "image": image, "imagePullPolicy": "IfNotPresent",
                    "ports": [{"containerPort": 8080}],
                    "env": [{"name": "APPLICATION_ACCESS_API", "value": "http://" + api_ip + ":8000"},
                            {"name": "APPLICATION_ACCESS_REPLICA", "valueFrom": {"fieldRef": {"fieldPath": "metadata.uid"}}}],
                    "envFrom": [{"secretRef": {"name": "authorizer"}}],
                    "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                        "capabilities": {"drop": ["ALL"]}},
                    "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "1", "memory": "256Mi"}},
                    "readinessProbe": {"httpGet": {"path": "/internal/ready", "port": 8080}, "periodSeconds": 2},
                    "livenessProbe": {"httpGet": {"path": "/internal/live", "port": 8080}}}]}}}),
        obj("NetworkPolicy", "access-isolation", "networking.k8s.io/v1", spec={"podSelector": {},
            "policyTypes": ["Ingress", "Egress"], "ingress": [
                {"from": [{"podSelector": {"matchLabels": AUTHORIZER_LABELS}}], "ports": [{"port": 4180}]},
                {"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                    "podSelector": {"matchLabels": {"app.kubernetes.io/name": "traefik"}}}], "ports": [{"port": 8080}]}],
            "egress": [{"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}], "ports": [{"port": 53, "protocol": "UDP"}, {"port": 53, "protocol": "TCP"}]},
                {"to": [{"ipBlock": {"cidr": identity_ip + "/32"}}], "ports": [{"port": 8080}]}]}),
        obj("NetworkPolicy", "authorizer-egress", "networking.k8s.io/v1", spec={"podSelector": {"matchLabels": AUTHORIZER_LABELS},
            "policyTypes": ["Egress"], "egress": [{"to": [{"ipBlock": {"cidr": api_ip + "/32"}}], "ports": [{"port": 8000}]},
                {"to": [{"namespaceSelector": {"matchLabels": {"platform.example/managed": "true"}}}]},
                {"to": [{"podSelector": {"matchLabels": {"platform.example/access-role": "browser-proxy"}}}], "ports": [{"port": 4180}]}]})]
