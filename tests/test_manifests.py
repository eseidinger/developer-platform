import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.manifests import component_resources, normalize_resources, resources, validate_name

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

    def test_configuration_becomes_plain_env_alongside_database_secret(self):
        docs = resources("a", "example:v1", 8080, "apps.localhost", "172.30.80.10", "secret",
                         None, {"B": "2", "A": "1"})
        container = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["env"], [{"name": "A", "value": "1"}, {"name": "B", "value": "2"}])
        self.assertEqual(container["envFrom"], [{"secretRef": {"name": "database"}},
                                                {"secretRef": {"name": "app-secrets", "optional": True}}])
        plain = resources("a", "example:v1", 8080, "apps.localhost", "172.30.80.10", "secret")
        self.assertNotIn("env", next(d for d in plain if d["kind"] == "Deployment")
                         ["spec"]["template"]["spec"]["containers"][0])

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

    def test_default_resources_are_unchanged(self):
        docs = resources("a", "example:v1", 8080, "apps.localhost", "172.30.80.10", "secret")
        container = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["resources"], {"requests": {"cpu": "100m", "memory": "128Mi"},
                                                  "limits": {"cpu": "500m", "memory": "256Mi"}})

    def test_requested_resources_reach_the_container(self):
        wanted = normalize_resources({"requests": {"cpu": "0.25"}, "limits": {"cpu": "1", "memory": "1Gi"}})
        self.assertEqual(wanted, {"requests": {"cpu": "250m", "memory": "128Mi"},
                                  "limits": {"cpu": "1000m", "memory": "1024Mi"}})
        docs = resources("a", "example:v1", 8080, "apps.localhost", "172.30.80.10", "secret", wanted)
        container = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["resources"], wanted)

    def test_invalid_resources_are_rejected(self):
        bad = [{"requests": {"cpu": "600m"}, "limits": {"cpu": "500m"}},
               {"requests": {"memory": "512Mi"}},
               {"requests": {"cpu": "0"}},
               {"requests": {"cpu": "1100m"}, "limits": {"cpu": "1500m"}},
               {"limits": {"cpu": "2100m"}},
               {"limits": {"memory": "3Gi"}},
               {"limits": {"memory": "256MB"}},
               {"limits": {"cpu": "fast"}},
               {"limits": {"gpu": "1"}},
               {"surprise": {}}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_resources(value)

    def test_component_resources_create_internal_services_and_a_non_overlapping_cronjob(self):
        docs = component_resources("shop", [
            {"name": "api", "type": "service", "resolved_image": "registry/api@sha256:one", "replicas": 2,
             "ports": [{"name": "http", "port": 8080}]},
            {"name": "worker", "type": "scheduled", "resolved_image": "registry/worker@sha256:two",
             "schedule": "*/15 * * * *", "time_zone": "UTC", "concurrency_policy": "Forbid"},
        ], "172.30.80.10", "secret", {"MODE": "batch"})
        self.assertEqual([d["kind"] for d in docs].count("Deployment"), 1)
        self.assertEqual([d["kind"] for d in docs].count("Service"), 1)
        self.assertFalse(any(d["kind"] == "Ingress" for d in docs))
        service = next(d for d in docs if d["kind"] == "Service")
        self.assertEqual(service["metadata"]["name"], "api")
        self.assertEqual(service["spec"]["selector"]["platform.example/component"], "api")
        cronjob = next(d for d in docs if d["kind"] == "CronJob")["spec"]
        self.assertEqual(cronjob["schedule"], "*/15 * * * *")
        self.assertEqual(cronjob["timeZone"], "UTC")
        self.assertEqual(cronjob["concurrencyPolicy"], "Forbid")
        pod = cronjob["jobTemplate"]["spec"]["template"]["spec"]
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertEqual(pod["containers"][0]["env"], [{"name": "MODE", "value": "batch"}])

    def test_updating_one_component_leaves_other_service_pod_template_unchanged(self):
        shared = [{"name": "api", "type": "service", "resolved_image": "registry/api@sha256:one",
                   "ports": [{"name": "http", "port": 8080}]},
                  {"name": "web", "type": "service", "resolved_image": "registry/web@sha256:one",
                   "ports": [{"name": "http", "port": 8081}]}]
        before = component_resources("shop", shared, "172.30.80.10", "secret")
        changed = [{**component, **({"resolved_image": "registry/api@sha256:two"} if component["name"] == "api" else {})}
                   for component in shared]
        after = component_resources("shop", changed, "172.30.80.10", "secret")
        template = lambda docs, component: next(d for d in docs if d["kind"] == "Deployment" and
                                                 d["metadata"]["name"] == component)["spec"]["template"]
        self.assertEqual(template(before, "web"), template(after, "web"))
        self.assertNotEqual(template(before, "api"), template(after, "api"))

if __name__ == "__main__":
    unittest.main()
