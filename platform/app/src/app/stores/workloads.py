"""Component-only store secrets and network access; no implicit project database."""
import copy
import hashlib
import ipaddress
import json
from . import catalog, providers

MARKER = "platform.example/store-credentials"


def _pod(manifest):
    if manifest["kind"] == "Deployment":
        return manifest["spec"]["template"]
    if manifest["kind"] == "CronJob":
        return manifest["spec"]["jobTemplate"]["spec"]["template"]
    return None


def resolve(conn, project, components):
    result = {}
    for component in components:
        entries, names = [], set()
        for reference in component.get("bindings", []):
            grant = catalog.grant(conn, reference["bindingId"], lock=True)
            res = catalog.resource(conn, grant["resource_id"], lock=True)
            if (grant["kind"] != "binding" or grant["consumer_project"] != project
                    or grant["component"] != component["name"] or grant["state"] != "active"
                    or res["state"] != "active" or res["observed_state"] != "active"):
                raise catalog.Conflict("Component binding is not approved, provisioned or in scope")
            found = conn.execute("""SELECT row_to_json(c) FROM store_credentials c WHERE grant_id=%s
                AND grant_version=%s AND state='active' AND expires_at>now() ORDER BY issued_at DESC LIMIT 1""",
                (grant["grant_id"], grant["version"])).fetchone()
            if not found:
                raise catalog.Conflict("Component binding credentials are not ready")
            cred = found[0]
            provider = providers.get(res["provider"])
            host, port = provider.endpoint()
            ipaddress.ip_address(host)
            prefix = reference.get("envPrefix", "")
            values = {prefix + key: value for key, value in provider.credentials(res, cred).items()}
            if names & values.keys():
                raise catalog.Conflict("Binding environment names overlap; use distinct prefixes")
            names.update(values)
            entries.append({"grant": grant, "credential": cred, "values": values, "host": host, "port": port})
            conn.execute("UPDATE store_grants SET bound_once=true WHERE grant_id=%s", (grant["grant_id"],))
        result[component["name"]] = entries
    return result


def attach(conn, project, spec, manifests):
    """Called under the deployment lifecycle lock, before any namespace mutation."""
    components = spec.get("components") or [{"name": "app", "bindings": []}]
    bindings = resolve(conn, project, components)
    result = []
    namespace = "project-" + project
    for original in manifests:
        manifest = copy.deepcopy(original)
        if manifest["kind"] == "Secret" and manifest["metadata"]["name"] == "database":
            continue
        if manifest["kind"] == "NetworkPolicy":
            # Strip only the implicit database exception from generated policies.
            # Provider egress is added per component below, never project-wide.
            egress = manifest["spec"].get("egress", [])
            postgres_ip = str(ipaddress.ip_address(__import__('os').environ["POSTGRES_IP"]))
            manifest["spec"]["egress"] = [rule for rule in egress if not (
                rule.get("to") == [{"ipBlock": {"cidr": postgres_ip + "/32"}}]
                and rule.get("ports") == [{"protocol": "TCP", "port": 5432}])]
        pod = _pod(manifest)
        if pod:
            labels = pod["metadata"].get("labels", {})
            component = labels.get("platform.example/component", "app")
            entries = bindings.get(component, [])
            containers = pod["spec"].get("containers", [])
            # Only the application container receives resource credentials.
            application = containers[0]
            application["envFrom"] = [value for value in application.get("envFrom", [])
                                      if value.get("secretRef", {}).get("name") != "database"]
            names = {e["name"] for e in application.get("env", [])}
            secrets, generations = [], []
            for entry in entries:
                if names & entry["values"].keys():
                    raise catalog.Conflict("Configuration shadows binding environment names")
                names.update(entry["values"])
                secret_name = "store-" + entry["grant"]["grant_id"]
                application["envFrom"].append({"secretRef": {"name": secret_name}})
                secrets.append({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                    "metadata": {"name": secret_name, "namespace": namespace,
                        "labels": {"platform.example/managed": "true", "platform.example/component": component}},
                    "stringData": entry["values"]})
                generations.append(entry["credential"]["credential_id"])
            marker = hashlib.sha256(json.dumps(sorted(generations)).encode()).hexdigest()[:32]
            pod["metadata"].setdefault("annotations", {})[MARKER] = marker
            result.extend(secrets)
        result.append(manifest)
    # Namespace must exist before secrets; keep stable declaration order otherwise.
    result.sort(key=lambda item: 0 if item["kind"] == "Namespace" else 1)
    for component, entries in bindings.items():
        if not entries:
            continue
        rules = [{"to": [{"ipBlock": {"cidr": e["host"] + ("/128" if ":" in e["host"] else "/32")}}],
                  "ports": [{"protocol": "TCP", "port": e["port"]}]} for e in entries]
        result.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": "store-" + component, "namespace": namespace,
                         "labels": {"platform.example/managed": "true", "platform.example/component": component}},
            "spec": {"podSelector": {"matchLabels": {"platform.example/component": component}},
                     "policyTypes": ["Egress"], "egress": rules}})
    return result
