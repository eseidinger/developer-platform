import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.manifests import resources, validate_name

class WorkloadContract(unittest.TestCase):
    def test_rejects_namespace_and_identifier_injection(self):
        for name in ("kube-system/", "../admin", "UPPER", "a_b", "a" * 33, "ends-", "1abc", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_name(name)

    def test_namespace_isolation(self):
        docs = resources("hello", "example:v1", 8080, "apps.localhost", "172.30.80.10", "secret")
        self.assertEqual(docs[0]["metadata"]["name"], "project-hello")
        self.assertTrue(all(d["metadata"]["namespace"] == "project-hello" for d in docs[1:]))
        policy = next(d for d in docs if d["kind"] == "NetworkPolicy")["spec"]
        self.assertEqual(policy["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(policy["egress"][-1]["to"], [{"ipBlock": {"cidr": "172.30.80.10/32"}}])
        ingress = policy["ingress"][1]["from"][0]
        self.assertIn("namespaceSelector", ingress)
        self.assertIn("podSelector", ingress)

    def test_restricted_workload_and_no_api_credentials(self):
        docs = resources("a", "example:v1", 8080, "apps.localhost", "172.30.80.10", "secret")
        spec = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]
        self.assertFalse(spec["automountServiceAccountToken"])
        self.assertTrue(spec["securityContext"]["runAsNonRoot"])
        self.assertEqual(spec["containers"][0]["securityContext"]["capabilities"]["drop"], ["ALL"])
        quota = next(d for d in docs if d["kind"] == "ResourceQuota")["spec"]["hard"]
        self.assertEqual(quota["services.nodeports"], "0")
        self.assertEqual(quota["services.loadbalancers"], "0")

    def test_rollout_fails_visibly_within_smoke_timeout(self):
        docs = resources("a", "example:v1", 8080, "apps.localhost", "172.30.80.10", "secret")
        deployment = next(d for d in docs if d["kind"] == "Deployment")["spec"]
        self.assertEqual(deployment["progressDeadlineSeconds"], 120)

if __name__ == "__main__":
    unittest.main()
