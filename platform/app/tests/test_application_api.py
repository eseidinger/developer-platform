"""Export and preflight must not enqueue work or mutate bindings."""

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.identity import Principal
from app.spec import to_flat
from fastapi.testclient import TestClient

from app import main

BODY = {
    "apiVersion": "platform.eseidinger.de/v1",
    "kind": "Application",
    "metadata": {"name": "demo"},
    "spec": {
        "components": [
            {
                "name": "web",
                "type": "service",
                "runtime": {"type": "container", "image": "example:v1"},
            }
        ]
    },
}


class ApplicationReadTests(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_principal] = lambda: Principal(
            "issuer", "human"
        )
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client = TestClient(main.app)

    def test_export_is_read_only_and_provides_the_revision(self):
        execution = to_flat(BODY)
        execution["components"][0]["resolved_image"] = "digest-observation"
        with (
            patch.object(main, "require_permission"),
            patch.object(main, "current_spec", return_value=(7, execution, "applied")),
        ):
            response = self.client.get("/v1/projects/demo/application")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["etag"], '"7"')
        self.assertNotIn("digest-observation", response.text)
        self.assertEqual(to_flat(response.json()), to_flat(BODY))

    def test_preflight_checks_images_and_capacity_without_queueing(self):
        conn = Mock()
        with (
            patch.object(main, "require_permission"),
            patch.object(
                main, "current_spec", return_value=(7, to_flat(BODY), "applied")
            ),
            patch.object(main, "connect", return_value=nullcontext(conn)),
            patch.object(main, "resolve_image", return_value="resolved"),
            patch.object(main, "assess_capacity", return_value={"state": "accepted"}),
            patch.object(main, "queue_deploy") as queue,
        ):
            response = self.client.post(
                "/v1/projects/demo/application/validate",
                json=BODY,
                headers={"If-Match": '"7"'},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["valid"])
        queue.assert_not_called()
        conn.execute.assert_not_called()

    def test_retired_project_requires_explicit_restore(self):
        with (
            patch.object(main, "require_permission"),
            patch.object(
                main, "current_spec", return_value=(7, to_flat(BODY), "retired")
            ),
            patch.object(main, "resolve_image") as image,
        ):
            response = self.client.post(
                "/v1/projects/demo/application/validate", json=BODY
            )
        self.assertEqual(response.status_code, 409)
        image.assert_not_called()

    def test_public_api_does_not_register_old_or_duplicate_routes(self):
        routes = [
            (method, route.path)
            for route in main.app.routes
            if getattr(route, "include_in_schema", False)
            for method in route.methods
        ]
        self.assertEqual(len(routes), len(set(routes)))
        for _, path in routes:
            self.assertTrue(
                path.startswith("/v1/") or path in {"/healthz", "/readyz"}, path
            )
        self.assertNotIn(("PUT", "/v1/projects/{project}"), routes)
        self.assertNotIn(("GET", "/v1/access-operations/{operation_id}"), routes)
