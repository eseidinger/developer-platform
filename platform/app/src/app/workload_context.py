"""Keep pod attribution stable until that workload's desired state changes."""

import copy
import hashlib
import json

FINGERPRINT = "platform.example/workload-fingerprint"
CONTEXT = ("platform.example/revision", "platform.example/operation-id")


def pod_template(manifest):
    spec = manifest["spec"]
    if manifest["kind"] == "CronJob":
        spec = spec["jobTemplate"]["spec"]
    return spec["template"]


def stamp(manifest, revision, operation_id):
    if manifest["kind"] not in {"Deployment", "CronJob"}:
        return manifest
    marked = copy.deepcopy(manifest)
    # Hash the complete desired workload spec before adding derived context.
    # This includes bindings, configuration, schedules, CA changes and explicit
    # restart markers. Only the digest is stored, never an additional secret.
    digest = hashlib.sha256(
        json.dumps(marked["spec"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    marked.setdefault("metadata", {}).setdefault("annotations", {})[FINGERPRINT] = (
        digest
    )
    annotations = (
        pod_template(marked).setdefault("metadata", {}).setdefault("annotations", {})
    )
    annotations.update(
        dict(zip(CONTEXT, (str(revision), str(operation_id)), strict=True))
    )
    return marked


def preserve(desired, existing):
    """Apply drift repairs while retaining attribution for an unchanged spec.

    Kubernetes increments Deployment generation whenever its pod template
    changes. Updating only telemetry context would therefore restart a peer
    whose application configuration did not change. A first apply after an
    upgrade has no stored fingerprint and adopts the new context once.
    """
    digest = desired.get("metadata", {}).get("annotations", {}).get(FINGERPRINT)
    if (
        not digest
        or existing.get("metadata", {}).get("annotations", {}).get(FINGERPRINT)
        != digest
    ):
        return desired
    annotations = pod_template(existing).get("metadata", {}).get("annotations", {})
    if not all(annotations.get(key) for key in CONTEXT):
        return desired
    preserved = copy.deepcopy(desired)
    pod_template(preserved)["metadata"]["annotations"].update(
        {key: annotations[key] for key in CONTEXT}
    )
    return preserved
