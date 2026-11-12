"""Private bounded PostgreSQL statistics, isolated from lifecycle reconciliation.

Only reviewed numeric fields and stable catalog identities leave this process.
Failed samples retain last-good values with explicit health and freshness.
"""

import json
import logging
import math
import os
import time
from pathlib import Path

from . import catalog, providers

log = logging.getLogger(__name__)


def line(name, value, labels):
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
    ):
        raise ValueError("Numeric metric required")
    encoded = ",".join(
        key + "=" + json.dumps(str(value)) for key, value in sorted(labels.items())
    )
    return name + "{" + encoded + "} " + str(value)


PG_CACHE = {}
PG_ERRORS = {}
PG_OFFSET = 0


def postgres(provider, resources):
    import psycopg

    global PG_OFFSET
    active = [r for r in resources if r["state"] == "active"]
    known = {str(r["resource_id"]) for r in active}
    for rid in list(PG_CACHE):
        if rid not in known:
            del PG_CACHE[rid]
    for rid in list(PG_ERRORS):
        if rid not in known:
            del PG_ERRORS[rid]
    chosen = (active[PG_OFFSET:] + active[:PG_OFFSET])[:8]
    PG_OFFSET = (PG_OFFSET + 8) % max(1, len(active))
    for resource in chosen:
        labels = {
            "provider": "postgresql",
            "project": resource["owner_project"],
            "resource_id": str(resource["resource_id"]),
            "scope": "resource",
        }
        try:
            with psycopg.connect(
                host=os.environ["POSTGRES_HOST"],
                dbname=catalog.identifier(resource["resource_id"]),
                user="platform_monitor",
                password=os.environ["POSTGRES_MONITOR_PASSWORD"],
                connect_timeout=2,
                options="-c statement_timeout=2000 -c default_transaction_read_only=on",
                autocommit=True,
            ) as conn:
                row = conn.execute("""SELECT coalesce(sum(n_live_tup),0),coalesce(sum(n_dead_tup),0),
                    coalesce(sum(vacuum_count+autovacuum_count),0),coalesce(sum(analyze_count+autoanalyze_count),0)
                    FROM pg_stat_user_tables""").fetchone()
                readings = [
                    line("platform_native_postgresql_" + name, float(value), labels)
                    for name, value in zip(
                        (
                            "estimated_live_rows",
                            "estimated_dead_rows",
                            "vacuums_total",
                            "analyzes_total",
                        ),
                        row,
                    )
                ]
                installed = {
                    name for (name,) in conn.execute("SELECT extname FROM pg_extension")
                }
                readings.extend(
                    line(
                        "platform_native_postgresql_extension_installed",
                        int(extension in installed),
                        {**labels, "extension": extension},
                    )
                    for extension in resource["extensions"]
                )
                indexes = conn.execute("""SELECT a.amname,coalesce(sum(s.idx_scan),0),coalesce(sum(pg_relation_size(s.indexrelid)),0)
                    FROM pg_stat_user_indexes s JOIN pg_class c ON c.oid=s.indexrelid JOIN pg_am a ON a.oid=c.relam
                    WHERE a.amname IN ('hnsw','ivfflat') GROUP BY a.amname""").fetchall()
                for kind, scans, size in indexes:
                    readings.extend(
                        [
                            line(
                                "platform_native_pgvector_index_scans_total",
                                float(scans),
                                {**labels, "index_type": kind},
                            ),
                            line(
                                "platform_native_pgvector_index_bytes",
                                float(size),
                                {**labels, "index_type": kind},
                            ),
                        ]
                    )
                progress = conn.execute("""SELECT count(*),coalesce(sum(blocks_done),0),coalesce(sum(blocks_total),0)
                    FROM pg_stat_progress_create_index WHERE datid=(SELECT oid FROM pg_database WHERE datname=current_database())""").fetchone()
                readings.extend(
                    line(
                        "platform_native_postgresql_index_build_" + name,
                        float(value),
                        labels,
                    )
                    for name, value in zip(
                        ("active", "blocks_done", "blocks_total"), progress
                    )
                )
            readings.append(
                line(
                    "platform_native_resource_last_success_timestamp_seconds",
                    time.time(),
                    labels,
                )
            )
            PG_CACHE[str(resource["resource_id"])] = readings
            PG_ERRORS[str(resource["resource_id"])] = False
        except Exception:  # noqa: BLE001 - Preserve previous samples across any provider failure.
            # Keep old samples with their own original success time.
            PG_ERRORS[str(resource["resource_id"])] = True
    result = [item for readings in PG_CACHE.values() for item in readings]
    for resource in active:
        labels = {
            "provider": "postgresql",
            "project": resource["owner_project"],
            "resource_id": str(resource["resource_id"]),
            "scope": "resource",
        }
        result.append(
            line(
                "platform_native_resource_collection_up",
                int(not PG_ERRORS.get(str(resource["resource_id"]), True)),
                labels,
            )
        )
    return result


def loop(stop, control):
    from ..monitoring import atomic_write

    cache = {}
    while not stop.is_set():
        try:
            with control.connect() as conn:
                resources = [
                    row[0]
                    for row in conn.execute(
                        "SELECT row_to_json(r) FROM store_resources r WHERE state<>'purged' ORDER BY resource_id LIMIT 128"
                    ).fetchall()
                ]
            selected = set(os.environ.get("STORE_ENABLED_PROVIDERS", "").split(","))
            now, lines = time.time(), []
            for native in ("s3",):
                lines.append(
                    line(
                        "platform_native_selected",
                        int(native in selected),
                        {"provider": native},
                    )
                )
            for name, collect in [("postgresql", postgres)]:
                enabled = name == "postgresql" or name in selected
                lines.append(
                    line("platform_native_selected", int(enabled), {"provider": name})
                )
                if not enabled:
                    cache.pop(name, None)
                    continue
                up = 0
                try:
                    provider = providers.get(name)
                    readings = collect(
                        provider, [r for r in resources if r["provider"] == name]
                    )
                    cache[name] = (now, readings)
                    up = 1
                except Exception:  # noqa: BLE001 - Provider failures must not stop monitoring.
                    log.debug("Native provider collection failed")
                stamp, readings = cache.get(name, (0, []))
                lines.extend(readings)
                lines.append(
                    line("platform_native_collection_up", up, {"provider": name})
                )
                lines.append(
                    line(
                        "platform_native_last_success_timestamp_seconds",
                        stamp,
                        {"provider": name},
                    )
                )
            lines.append(
                line("platform_native_collector_timestamp_seconds", time.time(), {})
            )
            root = Path(
                os.environ.get(
                    "MONITORING_DISCOVERY_DIR", "/var/lib/platform-monitoring"
                )
            )
            atomic_write(root / "stores-native.prom", "\n".join(lines) + "\n")
        except Exception:  # noqa: BLE001 - Keep the previous heartbeat on any write failure.
            log.debug("Native metric output unavailable")
        stop.wait(30)
