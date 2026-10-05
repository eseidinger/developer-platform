import re
import unittest
from pathlib import Path


CONTROLLER_MANIFEST = (Path(__file__).resolve().parents[2]
                       / "infrastructure/kubernetes/controller.yaml")


class ProvisionerRbacManifestTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
