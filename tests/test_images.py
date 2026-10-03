import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app import images

DIGEST = "sha256:" + "a" * 64


class ReferenceTests(unittest.TestCase):
    def test_parses_registry_repository_and_tag(self):
        self.assertEqual(images.parse_reference("nginx"), ("docker.io", "library/nginx", "latest", None))
        self.assertEqual(images.parse_reference("hashicorp/http-echo:1.0.0"),
                         ("docker.io", "hashicorp/http-echo", "1.0.0", None))
        self.assertEqual(images.parse_reference("ghcr.io/org/app:2"), ("ghcr.io", "org/app", "2", None))
        self.assertEqual(images.parse_reference("quay.io:443/a/b@" + DIGEST),
                         ("quay.io:443", "a/b", None, DIGEST))


class ResolveTests(unittest.TestCase):
    def resolve(self, image, responses):
        calls = []

        def fake(url, headers, method="GET"):
            calls.append((method, url, dict(headers)))
            return responses.pop(0)

        with mock.patch.object(images, "_request", side_effect=fake), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IMAGE_REGISTRIES", None)
            try:
                return images.resolve_image(image), calls
            except images.ImageResolutionError as exc:
                return exc.reason, calls

    def test_digest_reference_needs_no_network(self):
        result, calls = self.resolve("hashicorp/http-echo@" + DIGEST, [])
        self.assertEqual((result, calls), ("hashicorp/http-echo@" + DIGEST, []))

    def test_docker_hub_tag_uses_anonymous_token_and_returns_digest_reference(self):
        challenge = 'Bearer realm="https://auth.docker.io/token",service="registry.docker.io"'
        result, calls = self.resolve("hashicorp/http-echo:1.0.0", [
            (401, {"www-authenticate": challenge}, b""),
            (200, {}, b'{"token":"t"}'),
            (200, {"docker-content-digest": DIGEST}, b""),
        ])
        self.assertEqual(result, "hashicorp/http-echo@" + DIGEST)
        self.assertEqual(calls[0][:2], ("HEAD", "https://registry-1.docker.io/v2/hashicorp/http-echo/manifests/1.0.0"))
        self.assertIn("scope=repository%3Ahashicorp%2Fhttp-echo%3Apull", calls[1][1])
        self.assertEqual(calls[2][2]["Authorization"], "Bearer t")

    def test_registry_prefix_is_kept_in_the_resolved_reference(self):
        result, _ = self.resolve("ghcr.io/org/app:2", [(200, {"docker-content-digest": DIGEST}, b"")])
        self.assertEqual(result, "ghcr.io/org/app@" + DIGEST)

    def test_unlisted_registry_is_rejected_without_a_request(self):
        result, calls = self.resolve("10.0.0.5:5000/app:1", [])
        self.assertEqual((result, calls), ("unsupported_registry", []))

    def test_token_realm_outside_the_registry_is_not_contacted(self):
        challenge = 'Bearer realm="https://evil.example/token",service="x"'
        result, calls = self.resolve("hashicorp/http-echo:1", [(401, {"www-authenticate": challenge}, b"")])
        self.assertEqual((result, len(calls)), ("unavailable", 1))
        result, _ = self.resolve("hashicorp/http-echo:1", [
            (401, {"www-authenticate": 'Bearer realm="http://auth.docker.io/token"'}, b"")])
        self.assertEqual(result, "unavailable")

    def test_missing_tag_and_registry_failure_are_distinguished(self):
        self.assertEqual(self.resolve("a/b:nope", [(404, {}, b"")])[0], "not_found")
        self.assertEqual(self.resolve("ghcr.io/a/b:1", [(500, {}, b"")])[0], "unavailable")
        self.assertEqual(self.resolve("ghcr.io/a/b:1", [(200, {}, b"")])[0], "unavailable")


if __name__ == "__main__":
    unittest.main()
