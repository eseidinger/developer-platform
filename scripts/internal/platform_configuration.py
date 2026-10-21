"""Validate and apply non-secret settings through a shared local/remote contract."""

import json
import os
import re
import tempfile
from pathlib import Path

from scripts.internal.deployment_options import (
    ADDRESSES,
    ConfigurationError,
    mapping,
    platform_inventory_settings,
    platform_trace_settings,
)
from scripts.internal.env import parse_environment

# Inventory names map to .env names at the Ansible boundary. Values/defaults live
# in .env.example, which is also the source used by local secret initialization.
CORE_SETTINGS = {
    "PLATFORM_DOMAIN",
    "APPS_DOMAIN",
    "IDENTITY_DOMAIN",
    "TLS_EMAIL",
    "EDGE_BIND_IP",
    "LOCAL_APPLICATION_HTTPS_ENABLED",
    "IMAGE_REGISTRIES",
    "DRIFT_SCAN_INTERVAL_SECONDS",
    "REVISION_RETENTION",
    "PLATFORM_TRACE_SAMPLE_RATE",
    "CAPACITY_ADMISSION_ENABLED",
    "CAPACITY_RESERVE_CPU_MILLICORES",
    "CAPACITY_RESERVE_MEMORY_MIB",
    "CAPACITY_HOST_OVERHEAD_CPU_MILLICORES",
    "CAPACITY_HOST_OVERHEAD_MEMORY_MIB",
    "CAPACITY_KUBERNETES_OVERHEAD_MEMORY_MIB",
    "ALLOWED_EGRESS_CIDRS",
    "ALLOWED_EGRESS_PORTS",
}


def environment_settings(values):
    """Accept only documented, non-secret endpoint and policy settings."""
    mapping(values, CORE_SETTINGS, "Environment settings")
    result = {}
    for key, value in values.items():
        if not isinstance(value, str) or not (
            re.fullmatch(r"[A-Za-z0-9.@:,_-]+", value)
            or (key in {"ALLOWED_EGRESS_CIDRS", "ALLOWED_EGRESS_PORTS"} and value == "")
            or (
                key == "ALLOWED_EGRESS_CIDRS"
                and re.fullmatch(r"[0-9A-Fa-f:.,/]+", value)
            )
        ):
            raise ConfigurationError(
                "Environment settings must be documented single-line values"
            )
        if (
            key.startswith("CAPACITY_")
            and key != "CAPACITY_ADMISSION_ENABLED"
            and not re.fullmatch(r"[0-9]+", value)
        ):
            raise ConfigurationError("Capacity settings must be non-negative integers")
        if key in {"CAPACITY_ADMISSION_ENABLED", "LOCAL_APPLICATION_HTTPS_ENABLED"}:
            if value.lower() not in {"true", "false"}:
                raise ConfigurationError("Boolean settings must be true or false")
            value = value.lower()
        if key in {"ALLOWED_EGRESS_CIDRS", "ALLOWED_EGRESS_PORTS"}:
            pattern = (
                r"^$|^[0-9A-Fa-f:.]+/[0-9]{1,3}(?:,[0-9A-Fa-f:.]+/[0-9]{1,3})*$"
                if key.endswith("CIDRS")
                else r"^$|^[0-9]+(?:,[0-9]+)*$"
            )
            if not re.fullmatch(pattern, value):
                raise ConfigurationError("Invalid egress allowlist syntax")
        result[key] = value
    return result


def render_settings(specification):
    """Render only explicitly supplied settings; omissions retain host values."""
    mapping(specification, {"environment", "options", "tracing"}, "Configuration")
    result = environment_settings(specification.get("environment", {}))
    result.update(platform_inventory_settings(specification.get("options", {})))
    if "tracing" in specification:
        tracing = platform_trace_settings(specification["tracing"])
        result["PLATFORM_TRACE_SAMPLE_RATE"] = tracing["sample_rate"]
        result["PLATFORM_TRACE_RETENTION"] = tracing["retention"]
    return result


def trace_retention(source):
    """Read the owned Tempo template's single retention field, without PyYAML."""
    matches = re.findall(r"(?m)^    block_retention: ([1-9][0-9]{0,5}h)$", source)
    if len(matches) != 1:
        raise ConfigurationError(
            "Tempo must contain one supported block_retention field"
        )
    return matches[0]


def tempo_configuration(source, retention):
    """Update only the owned retention field and preserve comments/other settings."""
    platform_trace_settings({"retention": retention})
    trace_retention(source)
    return re.sub(
        r"(?m)^    block_retention: [1-9][0-9]{0,5}h$",
        "    block_retention: " + retention,
        source,
    )


def validate_effective_settings(config, tempo_source):
    """Use inventory validators on effective .env settings before any writes."""
    environment_settings({key: config[key] for key in CORE_SETTINGS if key in config})
    try:
        profiles = config.get("COMPOSE_PROFILES", "")
        options = {
            "stores": {
                "profiles": profiles.split(",") if profiles else [],
                "capacity_bytes": json.loads(config["STORE_CAPACITY_BYTES"]),
                "neo4j": {
                    "max_instances": int(config["NEO4J_MAX_INSTANCES"]),
                    "memory_bytes": int(config["NEO4J_INSTANCE_MEMORY_BYTES"]),
                },
            },
            "network": {
                "subnet": config["PLATFORM_SUBNET"],
                "addresses": {
                    service: config[key] for service, (key, _) in ADDRESSES.items()
                },
            },
            "search_console_network": {
                "subnet": config["STORE_SEARCH_CONSOLE_SUBNET"],
                "addresses": {
                    "platform-api": config["STORE_SEARCH_API_IP"],
                    "opensearch-dashboards": config["OPENSEARCH_DASHBOARDS_IP"],
                },
            },
            "k3s_image": config["K3S_IMAGE"],
            "bootstrap_subject": config.get("PLATFORM_BOOTSTRAP_SUBJECT", ""),
        }
    except (KeyError, ValueError, TypeError):
        raise ConfigurationError(
            "Invalid store, network, capacity or egress settings"
        ) from None
    platform_inventory_settings(options)
    if config.get("LOCAL_APPLICATION_HTTPS_ENABLED", "false") == "true" and not all(
        re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.localhost", config[key])
        for key in ("APPS_DOMAIN", "IDENTITY_DOMAIN")
    ):
        raise ConfigurationError("Local application HTTPS requires localhost domains")
    tracing = platform_trace_settings(
        {
            "sample_rate": config["PLATFORM_TRACE_SAMPLE_RATE"],
            "retention": config.get(
                "PLATFORM_TRACE_RETENTION", trace_retention(tempo_source)
            ),
        }
    )
    return tempo_configuration(tempo_source, tracing["retention"])


def update_environment(source, updates):
    """Retain comments, unknown settings and secrets; replace every managed duplicate."""
    remaining = dict(updates)
    lines = []
    for line in source.splitlines():
        key = line.partition("=")[0]
        if key in updates:
            line = key + "=" + updates[key]
            remaining.pop(key, None)
        lines.append(line)
    lines.extend(key + "=" + value for key, value in remaining.items())
    return "\n".join(lines) + "\n"


def replace_file(path, content, mode):
    """Keep configuration private even while an atomic replacement is staged."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), mode)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def configure(root, specification, *, check=False, runtime=False):
    """Validate the complete result before changing .env or Tempo configuration."""
    target = root / ".env"
    if not target.is_file():
        raise ConfigurationError("Run python3 scripts/init.py first")
    original = target.read_text()
    updates = render_settings(specification)
    config = parse_environment((root / ".env.example").read_text())
    config.update(parse_environment(original))
    config.update(updates)
    if runtime:
        # Match env.settings(), used by bootstrap helpers and Compose. Explicit
        # Ansible configuration ignores ambient variables to remain repeatable.
        config.update({key: os.environ[key] for key in config if key in os.environ})
        if "PLATFORM_TRACE_RETENTION" in os.environ:
            config["PLATFORM_TRACE_RETENTION"] = os.environ["PLATFORM_TRACE_RETENTION"]
    tempo_path = root / "infrastructure/monitoring/tempo.yaml"
    tempo_source = tempo_path.read_text()
    tempo_result = validate_effective_settings(config, tempo_source)
    environment = update_environment(original, updates) if updates else original
    private_mode_changed = target.stat().st_mode & 0o777 != 0o600
    changed = (
        environment != original or tempo_result != tempo_source or private_mode_changed
    )
    if not check:
        if environment != original:
            replace_file(target, environment, 0o600)
        elif private_mode_changed:
            target.chmod(0o600)
        if tempo_result != tempo_source:
            replace_file(tempo_path, tempo_result, 0o644)
    return changed
