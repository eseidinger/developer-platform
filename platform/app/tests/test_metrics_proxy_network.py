import io
import json
import runpy
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

network_script = runpy.run_path(
    str(
        Path(__file__).resolve().parents[3]
        / "scripts/internal/metrics-proxy-network.py"
    )
)
proxy_sources = network_script["proxy_sources"]


class MetricsProxyNetworkTests(unittest.TestCase):
    def test_only_control_plane_flannel_host_is_allowed(self):
        nodes = {
            "items": [
                {
                    "metadata": {
                        "labels": {"node-role.kubernetes.io/control-plane": "true"}
                    },
                    "spec": {"podCIDRs": ["10.42.2.0/24", "fd00:42:2::/64"]},
                },
                {"metadata": {"labels": {}}, "spec": {"podCIDR": "10.42.1.0/24"}},
            ]
        }
        self.assertEqual(proxy_sources(nodes), ["10.42.2.0/32", "fd00:42:2::/128"])

    def test_missing_control_plane_fails_closed(self):
        with self.assertRaises(ValueError):
            proxy_sources({"items": []})

    def test_refresh_preserves_private_settings_and_file_permissions(self):
        nodes = {
            "items": [
                {
                    "metadata": {
                        "labels": {"node-role.kubernetes.io/control-plane": "true"}
                    },
                    "spec": {"podCIDR": "10.42.2.0/24"},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            target = Path(".env")
            target.write_text(
                "SECRET=private-value\nPLATFORM_METRICS_PROXY_CIDRS=10.42.0.0/32\n"
            )
            output = io.StringIO()
            with (
                patch("sys.stdin", io.StringIO(json.dumps(nodes))),
                redirect_stdout(output),
            ):
                network_script["main"]()
            self.assertEqual(
                target.read_text(),
                "SECRET=private-value\nPLATFORM_METRICS_PROXY_CIDRS=10.42.2.0/32\n",
            )
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("private-value", output.getvalue())


if __name__ == "__main__":
    unittest.main()
