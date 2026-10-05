import unittest
from pathlib import Path

import yaml


ANSIBLE_DIR = Path(__file__).resolve().parents[1]


def mappings(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from mappings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from mappings(nested)


class PlaybookCommandTests(unittest.TestCase):
    def test_command_argv_never_contains_yaml_null(self):
        """An unquoted standalone dash is YAML null, not kubectl's stdin path."""
        for path in sorted(ANSIBLE_DIR.glob("*.yml")):
            with self.subTest(playbook=path.name):
                documents = yaml.safe_load_all(path.read_text(encoding="utf-8"))
                for document in documents:
                    for mapping in mappings(document):
                        command = mapping.get("ansible.builtin.command")
                        if isinstance(command, dict) and isinstance(command.get("argv"), list):
                            self.assertNotIn(None, command["argv"])


if __name__ == "__main__":
    unittest.main()
