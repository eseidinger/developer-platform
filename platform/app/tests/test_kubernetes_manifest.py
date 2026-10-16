import re
import unittest
from pathlib import Path


CONTROLLER_MANIFEST = (Path(__file__).resolve().parents[3]
                       / "infrastructure/kubernetes/controller.yaml")


class ProvisionerRbacManifestTests(unittest.TestCase):
    def test_workload_log_reader_is_separate_and_read_only(self):
        manifest = (CONTROLLER_MANIFEST.parent / "log-reader.yaml").read_text()
        self.assertIn("name: workload-log-reader", manifest)
        self.assertIn("resources: [pods/log]", manifest)
        self.assertIn("resources: [pods]", manifest)
        self.assertNotRegex(manifest, r"verbs:.*(create|update|patch|delete|\*)")
        self.assertNotIn("resources: [secrets]", manifest)
        self.assertNotIn("resources: [pods/exec]", manifest)

    def test_reconciliation_delete_permissions_cover_obsolete_workload_kinds(self):
        for resource in ("services", "deployments", "cronjobs", "networkpolicies", "ingresses"):
            with self.subTest(resource=resource):
                self.assertRegex(CONTROLLER_MANIFEST.read_text(),
                                 r"resources: \[[^\]]*" + resource + r"[^\]]*\]\s+verbs: \[[^\]]*delete")

    def test_capacity_metrics_access_is_limited_to_pods_and_nodes(self):
        """The capacity API needs NodeMetrics without granting wildcard metrics access."""
        manifest = CONTROLLER_MANIFEST.read_text()
        match = re.search(
            r"- apiGroups: \[metrics\.k8s\.io\]\s+"
            r"#.*\s+resources: \[([^]]+)\]\s+verbs: \[([^]]+)\]",
            manifest,
        )
        self.assertIsNotNone(match)
        self.assertEqual({item.strip() for item in match.group(1).split(",")}, {"pods", "nodes"})
        self.assertEqual({item.strip() for item in match.group(2).split(",")}, {"get", "list"})

    def test_capacity_admission_can_read_core_node_allocatable_values(self):
        """Request admission reads status.allocatable from core Node objects."""
        manifest = CONTROLLER_MANIFEST.read_text()
        self.assertRegex(
            manifest,
            r'- apiGroups: \[""\]\s+'
            r'resources: \[nodes\]\s+verbs: \[get, list\]',
        )

    def test_traced_metrics_workloads_can_be_reconciled(self):
        manifest = CONTROLLER_MANIFEST.read_text()
        self.assertRegex(manifest, r'resources: \[serviceaccounts\]\s+'
                         r'verbs: \[patch, delete\]')
        self.assertRegex(manifest, r'resources: \[services/proxy\]\s+verbs: \[get\]')
        self.assertRegex(manifest, r'resources: \[roles, rolebindings\]\s+'
                         r'verbs: \[patch, delete\]')


if __name__ == "__main__":
    unittest.main()
