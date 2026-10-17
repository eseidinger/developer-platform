"""Component-only store secrets and network access; no implicit project database."""
import copy
import hashlib
import ipaddress
import json
import os
from . import catalog, providers

MARKER = "platform.example/store-credentials"


def _pod(manifest):
    if manifest["kind"] == "Deployment":
        return manifest["spec"]["template"]
    if manifest["kind"] == "CronJob":
        return manifest["spec"]["jobTemplate"]["spec"]["template"]
    return None


def resolve(conn, project, components, strict=True):
    result = {}
    for component in components:
        entries, names = [], set()
        for reference in component.get("bindings", []):
            grant = catalog.grant(conn, reference["bindingId"], lock=True)
            res = catalog.resource(conn, grant["resource_id"], lock=True)
            if (grant["kind"] != "binding" or grant["consumer_project"] != project
                    or grant["component"] != component["name"] or grant["state"] != "active"
                    or res["state"] != "active" or res["observed_state"] != "active"):
                if strict:
                    raise catalog.Conflict("Component binding is not approved, provisioned or in scope")
                continue
            found = conn.execute("""SELECT row_to_json(c) FROM store_credentials c WHERE grant_id=%s
                AND grant_version=%s AND state='active' AND expires_at>now() ORDER BY issued_at DESC LIMIT 1""",
                (grant["grant_id"], grant["version"])).fetchone()
            if not found:
                if strict:
                    raise catalog.Conflict("Component binding credentials are not ready")
                continue
            cred = found[0]
            host, port = str(ipaddress.ip_address(os.environ.get("STORE_RELAY_IP", "172.30.80.15"))), cred["relay_port"]
            ipaddress.ip_address(host)
            prefix = reference.get("envPrefix", "")
            values = {prefix + key: value for key, value in providers.connection(res, cred).items()}
            if names & values.keys():
                raise catalog.Conflict("Binding environment names overlap; use distinct prefixes")
            names.update(values)
            entries.append({"grant": grant, "credential": cred, "values": values, "host": host, "port": port})
            conn.execute("UPDATE store_grants SET bound_once=true WHERE grant_id=%s", (grant["grant_id"],))
        result[component["name"]] = entries
    return result


def attach(conn, project, spec, manifests, strict=True):
    """Called under the deployment lifecycle lock, before any namespace mutation."""
    components = spec.get("components") or [{"name": "app", "bindings": []}]
    bindings = resolve(conn, project, components, strict)
    if strict:
        selected = [str(ref["bindingId"]) for component in components for ref in component.get("bindings", [])]
        conn.execute("""UPDATE store_grants SET state='revoked',version=version+1,observed_state='pending',updated_at=now()
            WHERE consumer_project=%s AND kind='binding' AND state='active' AND bound_once
                AND NOT(grant_id=ANY(%s::uuid[]))""", (project, selected))
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
            postgres_ip = str(ipaddress.ip_address(os.environ["POSTGRES_IP"]))
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
        rules = [{"to": [{"ipBlock": {"cidr": e["host"] + ("/128" if ":" in e["host"] else "/32")}}],
                  "ports": [{"protocol": "TCP", "port": e["port"]}]} for e in entries]
        result.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": "store-" + component, "namespace": namespace,
                         "labels": {"platform.example/managed": "true", "platform.example/component": component}},
            "spec": {"podSelector": {"matchLabels": {"platform.example/component": component}},
                     "policyTypes": ["Egress"], "egress": rules}})
    return result


def reconcile_runtime(conn, control):
    """Refresh only managed store secrets/networks and consumer credential markers."""
    from ..manifests import component_resources
    from ..config import rollout_state
    from kubernetes.client.exceptions import ApiException
    projects = conn.execute("""SELECT DISTINCT p.name,p.spec FROM projects p JOIN store_grants g
        ON g.consumer_project=p.name WHERE g.kind='binding' AND g.bound_once AND p.status='applied'
        AND (g.observed_state<>g.state OR EXISTS(SELECT 1 FROM store_credentials c WHERE c.grant_id=g.grant_id
            AND (c.state='retiring' OR (c.state='active' AND c.credential_id IS DISTINCT FROM g.delivered_credential_id))))""").fetchall()
    ready = set()
    for project, spec in projects:
        components = (spec or {}).get("components") or []
        if not components:
            continue
        generated = component_resources(project, components, os.environ["POSTGRES_IP"], "unused",
            spec.get("configuration"), os.environ["APPS_DOMAIN"])
        manifests = attach(conn, project, spec, generated, strict=False)
        for manifest in manifests:
            if manifest["kind"] == "Secret" and manifest["metadata"]["name"].startswith("store-"):
                control.apply(manifest)
            if manifest["kind"] == "NetworkPolicy" and manifest["metadata"]["name"].startswith("store-"):
                control.apply(manifest)
        for manifest in manifests:
            pod = _pod(manifest)
            if not pod:
                continue
            component = pod["metadata"].get("labels", {}).get("platform.example/component", "app")
            kind = manifest["kind"]
            resource = control.runtime.resources.get(api_version=manifest["apiVersion"], kind=kind)
            try:
                found = resource.get(name=manifest["metadata"]["name"], namespace="project-" + project, _request_timeout=(3, 5))
                live = found.to_dict() if hasattr(found, "to_dict") else found
            except ApiException as exc:
                if exc.status == 404:
                    continue
                raise
            desired_pod = {"metadata": {"annotations": {MARKER: pod["metadata"]["annotations"][MARKER]}},
                "spec": {"containers": [{"name": pod["spec"]["containers"][0]["name"],
                    "envFrom": pod["spec"]["containers"][0]["envFrom"]}]}}
            held = _pod(live)
            marker_matches = held and held["metadata"].get("annotations", {}).get(MARKER) == pod["metadata"]["annotations"][MARKER]
            if not marker_matches:
                patch = {"spec": {"template": desired_pod}} if kind == "Deployment" else {
                    "spec": {"jobTemplate": {"spec": {"template": desired_pod}}}}
                resource.patch(name=manifest["metadata"]["name"], namespace="project-" + project,
                    body=patch, content_type="application/strategic-merge-patch+json", _request_timeout=(3, 5))
                continue
            if kind == "Deployment":
                observed = live.get("status", {}).get("observedGeneration", 0)
                if observed >= live.get("metadata", {}).get("generation", 1) and rollout_state(live)["state"] == "active":
                    ready.add((project, component))
            elif not live.get("status", {}).get("active"):
                ready.add((project, component))
    # Erase revoked binding secrets. Data and other consumers remain untouched.
    revoked = conn.execute("""SELECT grant_id,consumer_project FROM store_grants WHERE kind='binding'
        AND bound_once AND state IN ('revoked','rejected') AND observed_state<>state""").fetchall()
    for grant_id, project in revoked:
        try:
            control.runtime.resources.get(api_version="v1", kind="Secret").delete(
                name="store-" + str(grant_id), namespace="project-" + project, _request_timeout=(3, 5))
        except ApiException as exc:
            if exc.status != 404:
                raise
    return ready
