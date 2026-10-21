"""Adapt shared configuration validation to Ansible's filter interface."""

import sys
from pathlib import Path

from ansible.errors import AnsibleFilterError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.internal import deployment_options
from scripts.internal.env import parse_environment
from scripts.internal.platform_configuration import (
    environment_settings,
    tempo_configuration,
)

# Retain the public filter names and address table used by inventory consumers.
ADDRESSES = deployment_options.ADDRESSES


def apply_filter(function, *arguments):
    try:
        return function(*arguments)
    except ValueError as error:
        raise AnsibleFilterError(str(error)) from error


def platform_inventory_settings(options):
    return apply_filter(deployment_options.platform_inventory_settings, options)


def platform_trace_settings(settings):
    return apply_filter(deployment_options.platform_trace_settings, settings)


def platform_environment_settings(values):
    # Native Jinja preserves booleans/numbers; .env settings use strings.
    # Normalize only scalars, keeping invalid structures rejected.
    normalized = {
        key: str(value).lower()
        if isinstance(value, bool)
        else str(value)
        if isinstance(value, (int, float))
        else value
        for key, value in values.items()
    }
    return apply_filter(environment_settings, normalized)


class FilterModule:
    def filters(self):
        return {
            "platform_inventory_settings": platform_inventory_settings,
            "platform_trace_settings": platform_trace_settings,
            "platform_environment_defaults": lambda source: apply_filter(
                parse_environment, source
            ),
            "platform_environment_settings": platform_environment_settings,
            "platform_tempo_configuration": lambda source, retention: apply_filter(
                tempo_configuration, source, retention
            ),
        }
