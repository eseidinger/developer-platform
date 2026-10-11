import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hosted_access_release", ROOT / "scripts/hosted-access-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class HostedAccessWorkflowTests(unittest.TestCase):
    def configuration(self, **changes):
        return {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "hosted-access-v0.1.0",
                "DOCKERHUB_USERNAME": "eseidinger", **changes}

    def test_release_tag_maps_to_docker_hub_version(self):
        self.assertEqual(release.metadata(self.configuration()), {
            "version": "0.1.0", "image": "docker.io/eseidinger/developer-platform-acceptance-fixture"})

    def test_explicit_organization_namespace(self):
        self.assertEqual(release.metadata(self.configuration(DOCKERHUB_NAMESPACE="platform-team"))["image"],
                         "docker.io/platform-team/developer-platform-acceptance-fixture")

    def test_unrelated_or_malformed_release_tags_are_rejected(self):
        for tag in ("v0.1.0", "cli-v0.1.0", "hosted-access-v", "hosted-access-v0.1", "hosted-access-v01.2.3",
                    "hosted-access-v0.1.0-rc.1", "hosted-access-v0.1.0\nimage=attacker", "hosted-access-v0.1.0;evil"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.metadata(self.configuration(GITHUB_REF_NAME=tag))
        with self.assertRaises(ValueError):
            release.metadata(self.configuration(GITHUB_REF_TYPE="branch"))

    def test_invalid_registry_names_never_reach_outputs(self):
        for name in ("", "UPPERCASE", "name/repository", "name\nimage=attacker", "name:tag"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.metadata(self.configuration(DOCKERHUB_USERNAME=name))
        with self.assertRaises(ValueError):
            release.metadata(self.configuration(DOCKERHUB_NAMESPACE="bad/namespace"))

    def test_publishing_is_tag_only_and_test_gated(self):
        source = (ROOT / ".github/workflows/hosted-access-fixture.yaml").read_text()
        workflow = yaml.safe_load(source)
        triggers = workflow.get("on", workflow.get(True))  # PyYAML's YAML 1.1 spelling of `on`.
        self.assertEqual(triggers["push"], {"tags": ["hosted-access-v*"]})
        self.assertNotIn("pull_request_target", triggers)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        publish = workflow["jobs"]["publish"]
        self.assertEqual(publish["needs"], "test")
        self.assertIn("github.event_name == 'push'", publish["if"])
        self.assertIn("refs/tags/hosted-access-v", publish["if"])
        self.assertEqual(publish["environment"], "dockerhub")
        self.assertNotIn("secrets.", str(workflow["jobs"]["test"]))
        steps = publish["steps"]
        build = next(step for step in steps if step.get("id") == "build")
        self.assertEqual(build["with"]["context"], "platform/acceptance")
        self.assertEqual(build["with"]["file"], "platform/acceptance/Dockerfile.fixture")
        self.assertEqual(build["with"]["platforms"], "linux/amd64,linux/arm64")
        self.assertTrue(build["with"]["push"])
        self.assertNotIn("latest", build["with"]["tags"])
        self.assertIn("--config", source)
        self.assertIn("$IMAGE@$DIGEST", source)
        self.assertNotIn("--allow-recovery-reconcile", source)
        self.assertNotIn("scripts/up.sh", source)


if __name__ == "__main__":
    unittest.main()
