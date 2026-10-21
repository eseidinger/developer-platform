"""Retirement scope confirmation, controller confinement, and retained SQL data."""

import json

from ..harness import require


def check_retirement(fixture):
    host = fixture.kubectl(
        "config",
        "view",
        "--minify",
        "-o",
        "jsonpath={.clusters[0].cluster.server}",
        namespace=False,
    ).stdout
    denied = fixture.command(
        [
            str(fixture.args.kubectl),
            "--kubeconfig",
            str(fixture.args.controller_kubeconfig),
            "--server",
            host,
            "--tls-server-name",
            "kubernetes",
            "delete",
            "namespace",
            "platform-system",
            "--dry-run=server",
        ],
        check=False,
    )
    require(
        denied.returncode != 0 and "provisioner-namespace-delete" in denied.stderr,
        "controller_namespace_delete_not_confined",
    )
    preview = fixture.request("GET", "/retirement-preview")
    require(not preview["blockers"], "retirement_blocked")
    rejected = fixture.request(
        "POST",
        "/retire",
        {"confirm_name": fixture.project, "scope_token": "0" * 32},
        statuses=(409,),
    )
    require(rejected["code"] == "scope_changed", "stale_retirement_scope_accepted")
    fixture.kubectl("get", "namespace", "project-" + fixture.project, namespace=False)
    # New applications receive database access through explicit named bindings.
    # Preserve any historical implicit database and role that actually exist;
    # do not require creating either merely to exercise project retirement.
    database = "project_" + fixture.project.replace("-", "_")
    query = (
        "SELECT (SELECT count(*) FROM pg_database WHERE datname='" + database + "'),"
        "(SELECT count(*) FROM pg_roles WHERE rolname='" + database + "')"
    )
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-X",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-tAc",
        query,
    ]
    before = fixture.command(command).stdout.strip()
    require(before in {"0|0", "1|1"}, "legacy_database_role_inconsistent")
    fixture.retire()
    # A failed kubectl call alone is not evidence of deletion: require a successful
    # get with --ignore-not-found and an empty result.
    require(
        not fixture.kubectl(
            "get",
            "namespace",
            "project-" + fixture.project,
            "--ignore-not-found",
            "-o",
            "name",
            namespace=False,
        ).stdout.strip(),
        "retired_namespace_present",
    )
    inventory = fixture.api.request(
        "GET", "/operator/projects/" + fixture.project + "/retirement"
    )
    require(
        inventory["status"] == "retired"
        and inventory["retained"]["database"] == preview["retains"]["database"],
        "retirement_inventory_missing",
    )
    require(
        preview["retains"]["database"] == database, "retained_database_scope_mismatch"
    )
    result = fixture.command(command)
    require(result.stdout.strip() == before, "retirement_sql_data_not_retained")
    require(
        database in json.dumps(inventory["retained"]), "retained_inventory_mismatch"
    )
    fixture.check("retirement-controller-confinement-stale-scope-and-retained-data")
