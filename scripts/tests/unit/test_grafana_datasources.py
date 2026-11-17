"""Offline checks for project data-source rendering and reconciliation."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/operations/reconcile-grafana-datasources.py"
SPEC = importlib.util.spec_from_file_location("grafana_datasources", SCRIPT)
RECONCILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONCILER)


class GrafanaDataSourcesTests(unittest.TestCase):
    def test_render_keeps_shared_sources_and_uses_immutable_project_id(self):
        identifier = "755613cc-5691-4ab0-b69a-15db2814f4a5"
        base = (ROOT / "infrastructure/monitoring/datasources.yaml").read_text()
        rendered = RECONCILER.render(base, [["vareng", identifier]])

        self.assertIn("uid: loki-755613cc56914ab0b69a15db2814f4a5", rendered)
        self.assertIn("uid: tempo-755613cc56914ab0b69a15db2814f4a5", rendered)
        self.assertEqual(rendered.count("httpHeaderValue1: " + identifier), 2)
        self.assertIn("uid: prometheus", rendered)
        self.assertEqual(RECONCILER.render(base, []), base)
        self.assertNotIn("project vareng", RECONCILER.render(base, []))

        replacement = RECONCILER.render(
            base, [["vareng", "14a14636-e8bc-4644-981c-09e8715b7d53"]]
        )
        self.assertNotIn("loki-755613cc56914ab0b69a15db2814f4a5", replacement)
        self.assertIn("loki-14a14636e8bc4644981c09e8715b7d53", replacement)

    def test_invalid_catalog_names_and_ids_cannot_enter_provisioning(self):
        for project in [
            ["bad\nname", "755613cc-5691-4ab0-b69a-15db2814f4a5"],
            ["valid", "not-a-uuid"],
        ]:
            with self.subTest(project=project), self.assertRaises(ValueError):
                RECONCILER.project_sources([project])

    def test_reconcile_restarts_only_when_file_changes_and_grafana_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "datasources/default.yaml"
            with (
                patch.object(RECONCILER, "TARGET", target),
                patch.object(RECONCILER, "catalog_projects", return_value=[]),
                patch.object(RECONCILER, "grafana_running", return_value=True),
                patch.object(RECONCILER, "docker") as docker,
                patch.object(RECONCILER, "wait_for_grafana") as ready,
            ):
                self.assertTrue(RECONCILER.reconcile())
                docker.assert_called_once_with("restart", "grafana")
                ready.assert_called_once()

                docker.reset_mock()
                ready.reset_mock()
                self.assertFalse(RECONCILER.reconcile())
                docker.assert_not_called()
                ready.assert_not_called()
