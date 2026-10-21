"""Load static task imports for offline playbook contract checks."""

from pathlib import Path

import yaml

ANSIBLE_DIR = Path(__file__).resolve().parents[1]


def expand_tasks(tasks, directory):
    """Expand imports while retaining block, rescue, and cleanup boundaries."""
    expanded = []
    for original in tasks:
        task = dict(original)
        imported = task.get("ansible.builtin.import_tasks")
        if imported:
            if set(task) != {"name", "ansible.builtin.import_tasks"}:
                raise ValueError("The test loader needs to handle import attributes")
            path = directory / imported
            expanded.extend(expand_tasks(yaml.safe_load(path.read_text()), path.parent))
            continue
        for section in ("block", "rescue", "always"):
            if section in task:
                task[section] = expand_tasks(task[section], directory)
        expanded.append(task)
    return expanded


def load_playbook(path):
    """Read the effective tasks without executing a playbook or contacting a host."""
    plays = yaml.safe_load(path.read_text())
    for play in plays:
        for section in ("pre_tasks", "tasks", "post_tasks", "handlers"):
            if section in play:
                play[section] = expand_tasks(play[section], path.parent)
    return plays
