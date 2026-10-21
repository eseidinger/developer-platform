"""Configuration validation and real offline Ansible rendering, without a target host."""

import ast
import base64
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml
from ansible.errors import AnsibleFilterError
from playbook_helpers import load_playbook

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "platform_inventory", ROOT / "ansible/filter_plugins/platform_inventory.py"
)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
render = plugin.platform_inventory_settings


class InventorySettingsTests(unittest.TestCase):
    def stores(self):
        return {
            "profiles": ["s3", "qdrant", "opensearch", "neo4j"],
            "capacity_bytes": {
                p: 2**32 for p in ["postgresql", "s3", "qdrant", "opensearch", "neo4j"]
            },
            "neo4j": {"max_instances": 4, "memory_bytes": 1610612736},
        }

    def test_omitted_options_preserve_existing_environment(self):
        self.assertEqual(render({}), {})
        self.assertEqual(
            render({"stores": None, "network": None, "bootstrap_subject": None}), {}
        )

    def test_profiles_and_capacity_render_as_compose_and_json(self):
        source = self.stores()
        result = render({"stores": source})
        self.assertEqual(result["COMPOSE_PROFILES"], "s3,qdrant,opensearch,neo4j")
        self.assertEqual(
            json.loads(result["STORE_CAPACITY_BYTES"]), source["capacity_bytes"]
        )
        self.assertEqual(result["NEO4J_INSTANCE_MEMORY_BYTES"], "1610612736")
        self.assertEqual(result["NEO4J_MAX_INSTANCES"], "4")
        self.assertEqual(
            render({"stores": {"profiles": [], "capacity_bytes": {"postgresql": 1}}})[
                "COMPOSE_PROFILES"
            ],
            "",
        )

    def test_invalid_or_incomplete_store_selection_is_rejected(self):
        for change in [
            {"profiles": "neo4j"},
            {"profiles": ["neo4j", "neo4j"]},
            {"profiles": ["unknown"]},
            {"capacity_bytes": {"postgresql": 1}},
            {"capacity_bytes": {"postgresql": True}},
            {"capacity_bytes": {"postgresql": 0}},
            {"capacity_bytes": {"postgresql": "123"}},
            {"neo4j": {"max_instances": 65}},
            {"neo4j": {"memory_bytes": 512}},
            {"neo4j": {"admin_key": "must-not-appear"}},
            {"secret": "must-not-appear"},
        ]:
            with (
                self.subTest(change=change),
                self.assertRaises(AnsibleFilterError) as error,
            ):
                render({"stores": {**self.stores(), **change}})
            self.assertNotIn("must-not-appear", str(error.exception))

    def test_custom_network_derives_every_service_address(self):
        result = render(
            {
                "network": {
                    "subnet": "10.55.8.0/24",
                    "addresses": {"postgres": "10.55.8.90"},
                },
                "search_console_network": {"subnet": "10.55.9.0/29"},
            }
        )
        self.assertEqual(result["POSTGRES_IP"], "10.55.8.90")
        self.assertEqual(result["STORE_RELAY_IP"], "10.55.8.15")
        self.assertEqual(result["NEO4J_CONTROLLER_IP"], "10.55.8.31")
        self.assertEqual(result["STORE_SEARCH_API_IP"], "10.55.9.2")
        self.assertEqual(len([k for k in result if k.endswith("_IP")]), 24)

    def test_inventory_address_defaults_match_the_runtime_validator(self):
        tree = ast.parse(
            (ROOT / "scripts/checks/check-network-addresses.py").read_text()
        )
        fixed = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "FIXED_SERVICES"
                for target in node.targets
            )
        )
        result = render({"network": {"subnet": "172.30.80.0/24"}})
        self.assertEqual(set(plugin.ADDRESSES), set(fixed))
        for key, default in fixed.values():
            self.assertEqual(result[key], default)

    def test_networks_reject_overlap_bad_addresses_and_typographical_keys(self):
        for options in [
            {
                "network": {"subnet": "10.55.8.0/24"},
                "search_console_network": {"subnet": "10.55.8.0/29"},
            },
            {"network": {"subnet": "10.55.8.0/25"}},
            {"network": {"subnet": "8.8.8.0/24"}},
            {"network": {"subnet": "10.55.8.1/24"}},
            *(
                {"network": {"subnet": "10.55.8.0/24", "addresses": override}}
                for override in [
                    {"postgres": "10.55.9.2"},
                    {"postgres": "10.55.8.15"},
                    {"postgres": "10.55.8.1"},
                    {"postgres": "10.55.8.255"},
                    {"unknown": "10.55.8.2"},
                ]
            ),
        ]:
            with self.subTest(options=options), self.assertRaises(AnsibleFilterError):
                render(options)

    def test_private_access_requires_deliberate_reachable_listener(self):
        options = {
            "store_ssh_host": "db.example.com",
            "bastion_bind_ip": "10.1.2.3",
            "bastion_port": 2223,
        }
        self.assertEqual(
            render(options),
            {"STORE_SSH_HOST": "db.example.com", "STORE_SSH_PORT": "2223"},
        )
        for change in [
            {"bastion_bind_ip": None},
            {"bastion_bind_ip": "127.0.0.1"},
            {"bastion_bind_ip": "0.0.0.0"},
            {"bastion_port": None},
            {"bastion_port": 22},
            {"store_ssh_host": "https://db.example.com"},
            {"store_ssh_host": "host\nKEY=value"},
        ]:
            with self.subTest(change=change), self.assertRaises(AnsibleFilterError):
                render({**options, **change})
        self.assertEqual(render({"store_ssh_host": ""}), {"STORE_SSH_HOST": ""})

    def test_tracing_defaults_and_overrides(self):
        self.assertEqual(
            plugin.platform_trace_settings({}),
            {"sample_rate": "1.0", "retention": "24h"},
        )
        self.assertEqual(
            plugin.platform_trace_settings({"sample_rate": 0.25, "retention": "168h"}),
            {"sample_rate": "0.25", "retention": "168h"},
        )
        self.assertEqual(
            plugin.platform_trace_settings({"sample_rate": 0})["sample_rate"], "0.0"
        )
        for value in [True, -1, 1.01, "NaN", float("inf"), "1.0\nKEY=value", None]:
            with self.subTest(sample=value), self.assertRaises(AnsibleFilterError):
                plugin.platform_trace_settings({"sample_rate": value})
        for value in ["0h", "-24h", "24d", "24h\nKEY=value", "1000000h", 24, None]:
            with self.subTest(retention=value), self.assertRaises(AnsibleFilterError):
                plugin.platform_trace_settings({"retention": value})

    def test_version_subject_and_timeout_validation(self):
        self.assertEqual(
            render(
                {
                    "k3s_image": "rancher/k3s:v1.36.4-k3s1",
                    "bootstrap_subject": "human-id",
                }
            )["PLATFORM_BOOTSTRAP_SUBJECT"],
            "human-id",
        )
        for options in [
            {"k3s_image": "rancher/k3s:latest"},
            {"k3s_image": "other:v1.36.4"},
            {"k3s_image": "rancher/k3s:v1.35.4-k3s1", "kubectl_version": "v1.37.1"},
            {"bootstrap_subject": "human\nKEY=value"},
            {"bootstrap_timeout_seconds": "300"},
            {"readiness_timeout_seconds": False},
            {"readiness_timeout_seconds": 4000},
        ]:
            with self.subTest(options=options), self.assertRaises(AnsibleFilterError):
                render(options)

    @unittest.skipUnless(
        shutil.which("ansible-playbook"),
        "ansible-playbook required for offline rendering",
    )
    def test_real_ansible_preflight_accepts_example_and_rejects_invalid_selection(self):
        deployment = load_playbook(ROOT / "ansible/deploy.yml")[0]
        example = yaml.safe_load((ROOT / "ansible/inventory.example.yml").read_text())[
            "all"
        ]["children"]["developer_platform"]["vars"]
        variables = {
            **example,
            "platform_source_dir": str(ROOT),
            "ansible_facts": {
                "distribution": "Ubuntu",
                "distribution_version": "24.04",
                "architecture": "x86_64",
            },
        }
        assertions = {
            "ansible.builtin.assert": {
                "that": [
                    "platform_managed_settings['COMPOSE_PROFILES'] == ''",
                    "platform_managed_settings['NEO4J_CONTROLLER_IP'] == '172.30.80.31'",
                    "platform_managed_settings['STORE_SSH_PORT'] == '2222'",
                    "platform_settings['PLATFORM_TRACE_SAMPLE_RATE'] == '1.0'",
                    "(platform_settings | combine(platform_managed_settings))['K3S_IMAGE'] == 'rancher/k3s:v1.36.4-k3s1'",
                ]
            }
        }
        with tempfile.TemporaryDirectory(prefix="inventory-offline-") as directory:
            path = Path(directory) / "play.yml"
            env = {
                **os.environ,
                "ANSIBLE_LOCAL_TEMP": directory,
                "ANSIBLE_FILTER_PLUGINS": str(ROOT / "ansible/filter_plugins"),
                "ANSIBLE_NOCOLOR": "1",
            }
            for mode in ["default", "all", "omitted", "tracing", "invalid"]:
                configured = copy.deepcopy(variables)
                expected = copy.deepcopy(assertions)
                if mode == "invalid":
                    configured["platform_stores"]["profiles"] = [
                        "neo4j"
                    ]  # missing capacity
                elif mode == "all":
                    configured["platform_stores"] = self.stores()
                    expected["ansible.builtin.assert"]["that"][0] = (
                        "platform_managed_settings['COMPOSE_PROFILES'] == 's3,qdrant,opensearch,neo4j'"
                    )
                    expected["ansible.builtin.assert"]["that"] += [
                        "platform_managed_settings['STORE_CAPACITY_BYTES'] is string",
                        "(platform_managed_settings['STORE_CAPACITY_BYTES'] | from_json)['neo4j'] == 4294967296",
                    ]
                elif mode == "tracing":
                    configured["platform_trace_sample_rate"] = 0.25
                    configured["platform_trace_retention"] = "168h"
                    expected["ansible.builtin.assert"]["that"][3] = (
                        "platform_settings['PLATFORM_TRACE_SAMPLE_RATE'] == '0.25'"
                    )
                elif mode == "omitted":
                    for key in [
                        "platform_stores",
                        "platform_network",
                        "platform_search_console_network",
                        "platform_k3s_image",
                        "platform_store_ssh_host",
                        "platform_database_bastion_bind_ip",
                        "platform_database_bastion_port",
                        "platform_trace_sample_rate",
                        "platform_trace_retention",
                    ]:
                        configured.pop(key, None)
                    expected = {
                        "ansible.builtin.assert": {
                            "that": ["platform_managed_settings == {}"]
                        }
                    }
                expected["ansible.builtin.assert"]["that"] += [
                    "platform_tracing_settings['retention'] == '"
                    + configured.get("platform_trace_retention", "24h")
                    + "'",
                    "platform_tempo_configuration['backend_worker']['compaction']['block_retention'] == platform_tracing_settings['retention']",
                    "platform_tempo_configuration['storage']['trace']['backend'] == 'local'",
                    "(platform_tempo_configuration | to_nice_yaml(indent=2) | from_yaml) == platform_tempo_configuration",
                ]
                play = [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {**deployment["vars"], **configured},
                        "tasks": deployment["pre_tasks"] + [expected],
                    }
                ]
                path.write_text(yaml.safe_dump(play, sort_keys=False))
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", str(path)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
                if mode == "invalid":
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Allocate capacity", result.stdout + result.stderr)
                else:
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )


class BastionInventoryTests(unittest.TestCase):
    @unittest.skipUnless(
        shutil.which("ansible-playbook"),
        "ansible-playbook required for offline rendering",
    )
    def test_installer_uses_deployed_relay_and_rejects_advertisement_mismatch(self):
        installer = load_playbook(ROOT / "ansible/install-human-database-access.yml")[0]
        selected = [
            task
            for task in installer["tasks"]
            if task["name"]
            in {
                "Validate the deliberately selected listener",
                "Validate advertised SSH settings against the selected listener",
                "Extract the bastion token and private database address",
                "Require generated token and fixed PostgreSQL address",
            }
        ]
        self.assertEqual(len(selected), 4)
        source = (
            "DATABASE_BASTION_TOKEN="
            + "a" * 64
            + "\nPOSTGRES_IP=10.55.8.10\nSTORE_RELAY_IP=10.55.8.15\nSTORE_SSH_PORT=2223\nSTORE_SSH_HOST=db.example.com\n"
        )
        with tempfile.TemporaryDirectory(prefix="bastion-offline-") as directory:
            path = Path(directory) / "play.yml"
            env = {
                **os.environ,
                "ANSIBLE_LOCAL_TEMP": directory,
                "ANSIBLE_FILTER_PLUGINS": str(ROOT / "ansible/filter_plugins"),
                "ANSIBLE_NOCOLOR": "1",
            }
            for port in [2223, 2222]:
                play = [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            **installer["vars"],
                            "platform_database_bastion_bind_ip": "10.1.2.3",
                            "platform_database_bastion_port": port,
                            "platform_store_ssh_host": "db.example.com",
                            "database_environment": {
                                "content": base64.b64encode(source.encode()).decode()
                            },
                        },
                        "tasks": selected
                        + [
                            {
                                "ansible.builtin.assert": {
                                    "that": ["database_store_relay_ip == '10.55.8.15'"]
                                }
                            }
                        ],
                    }
                ]
                path.write_text(yaml.safe_dump(play, sort_keys=False))
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", str(path)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
                self.assertEqual(
                    result.returncode == 0, port == 2223, result.stdout + result.stderr
                )


if __name__ == "__main__":
    unittest.main()
