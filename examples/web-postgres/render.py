#!/usr/bin/env python3
"""Render a digest-pinned platform declaration for the web/PostgreSQL sample."""
import argparse
import json
import re
from uuid import UUID


PROJECT = re.compile(r"^[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?$")
IMAGE = re.compile(r"^[^\s]+@sha256:[0-9a-f]{64}$")


def declaration(project: str, image: str, *, fail_ready: bool = False, binding_id: str | None = None) -> dict:
    if not PROJECT.fullmatch(project):
        raise ValueError("project must be a lowercase platform slug of at most 32 characters")
    if not IMAGE.fullmatch(image):
        raise ValueError("image must be a public OCI reference pinned with @sha256:<64 lowercase hex>")
    bindings = [{"bindingId": str(UUID(binding_id)), "envPrefix": ""}] if binding_id else []
    return {
        "apiVersion": "platform.example/v1alpha2", "kind": "Application",
        "metadata": {"name": project, "project": project, "environment": "default"},
        "spec": {
            "components": [{
                "name": "web", "type": "service", "runtime": {"type": "container", "image": image},
                "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                "replicas": 1, "exposure": "public", "bindings": bindings,
                "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                              "limits": {"cpu": "500m", "memory": "256Mi"}},
                "health": {"readiness": {"path": "/health/ready"}},
            }],
            "configuration": {"values": {"DEMO_FAIL_READY": "true" if fail_ready else "false"}},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--binding-id", required=True, help="approved named PostgreSQL binding for the web component")
    parser.add_argument("--fail-ready", action="store_true", help="inject a readiness failure for diagnosis")
    args = parser.parse_args()
    try:
        print(json.dumps(declaration(args.project, args.image, fail_ready=args.fail_ready, binding_id=args.binding_id), indent=2))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
