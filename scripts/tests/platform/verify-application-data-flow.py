#!/usr/bin/env python3
"""Disposable bound-application check for artifact metadata and search projection.

Run only in a short-lived pod with SOURCE_, ARTIFACT_ and SEARCH_ managed
binding variables. The project and all three resources must be disposable.
"""

import argparse
import base64
import hashlib
import json
import os
from contextlib import ExitStack
from uuid import uuid4

import boto3
import httpx
import psycopg
from botocore.config import Config
from psycopg import sql
from psycopg.types.json import Jsonb


def require(name):
    return os.environ[name]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-disposable-bindings",
        action="store_true",
        required=True,
        help="Confirm all SOURCE_, ARTIFACT_ and SEARCH_ bindings are disposable",
    )
    parser.parse_args()
    with ExitStack() as cleanup:
        verify(cleanup)
    print(
        "PASS bound application data flow; fixture schema, document and object versions removed"
    )


def verify(cleanup):
    parquet = base64.b64decode(require("FIXTURE_PARQUET_B64"), validate=True)
    assert parquet.startswith(b"PAR1") and parquet.endswith(b"PAR1")
    s3 = boto3.client(
        "s3",
        endpoint_url=require("ARTIFACT_AWS_ENDPOINT_URL_S3"),
        aws_access_key_id=require("ARTIFACT_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=require("ARTIFACT_AWS_SECRET_ACCESS_KEY"),
        region_name=require("ARTIFACT_AWS_DEFAULT_REGION"),
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 2},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    bucket = require("ARTIFACT_S3_BUCKET")
    prefix = "application-flow/" + uuid4().hex + "/"
    data_key = prefix + "data.parquet"
    checksum = hashlib.sha256(parquet).hexdigest()

    def put_version(key, body):
        version = s3.put_object(Bucket=bucket, Key=key, Body=body).get("VersionId")
        # Register cleanup before validating versioning, including an unversioned
        # bucket supplied by mistake. The random key belongs only to this run.
        arguments = {"Bucket": bucket, "Key": key}
        if version is not None:
            arguments["VersionId"] = version
        cleanup.callback(s3.delete_object, **arguments)
        assert version and version != "null", "Versioned disposable bucket required"
        return version

    data_version = put_version(data_key, parquet)
    reference = {
        "key": data_key,
        "version": data_version,
        "bytes": len(parquet),
        "sha256": checksum,
    }
    manifest = json.dumps(reference, sort_keys=True, separators=(",", ":")).encode()
    manifest_key = prefix + "manifest.json"
    manifest_version = put_version(manifest_key, manifest)
    assert (
        manifest_version
        and data_version
        and manifest_version != "null"
        and data_version != "null"
    )
    put_version(data_key, b"newer version")
    read = s3.get_object(Bucket=bucket, Key=data_key, VersionId=data_version)[
        "Body"
    ].read()
    assert (
        len(read) == reference["bytes"] and hashlib.sha256(read).hexdigest() == checksum
    )
    assert (
        json.loads(
            s3.get_object(Bucket=bucket, Key=manifest_key, VersionId=manifest_version)[
                "Body"
            ].read()
        )
        == reference
    )

    conn = psycopg.connect(
        host=require("SOURCE_PGHOST"),
        port=int(require("SOURCE_PGPORT")),
        dbname=require("SOURCE_PGDATABASE"),
        user=require("SOURCE_PGUSER"),
        password=require("SOURCE_PGPASSWORD"),
        sslmode="disable",
        connect_timeout=10,
        autocommit=True,
    )
    cleanup.callback(conn.close)
    schema = "application_flow_" + uuid4().hex
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    cleanup.callback(
        conn.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
    )
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    search = httpx.Client(
        base_url=require("SEARCH_OPENSEARCH_URL"),
        auth=(
            require("SEARCH_OPENSEARCH_USERNAME"),
            require("SEARCH_OPENSEARCH_PASSWORD"),
        ),
        timeout=15,
        trust_env=False,
    )
    cleanup.callback(search.close)
    index = require("SEARCH_OPENSEARCH_INDEX")
    doc_id = "dataset-" + uuid4().hex

    def delete_document():
        response = search.delete("/" + index + "/_doc/" + doc_id + "?refresh=true")
        if response.status_code != 404:
            response.raise_for_status()

    cleanup.callback(delete_document)

    def source():
        return conn.execute(
            "SELECT title, version, deleted FROM documents WHERE id=%s", (doc_id,)
        ).fetchone()

    def project():
        pending = conn.execute(
            "SELECT event_id, version FROM outbox "
            "WHERE doc_id=%s AND NOT processed ORDER BY event_id",
            (doc_id,),
        ).fetchall()
        for event_id, version in pending:
            title, current, deleted = source()
            assert current >= version
            path = "/" + index + "/_doc/" + doc_id + "?refresh=true"
            response = (
                search.delete(path)
                if deleted
                else search.put(
                    path,
                    json={"title": title, "version": current, "artifact": manifest_key},
                )
            )
            assert response.status_code in ({200, 404} if deleted else {200, 201})
            conn.execute(
                "UPDATE outbox SET processed=true WHERE event_id=%s", (event_id,)
            )

    with conn.transaction():
        conn.execute(
            "CREATE TABLE documents ("
            "id text PRIMARY KEY, title text NOT NULL, version integer NOT NULL, "
            "deleted boolean NOT NULL DEFAULT false, artifact jsonb NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE outbox ("
            "event_id bigserial PRIMARY KEY, doc_id text NOT NULL, version integer NOT NULL, "
            "processed boolean NOT NULL DEFAULT false, UNIQUE(doc_id,version))"
        )
    with conn.transaction():
        conn.execute(
            "INSERT INTO documents VALUES (%s,%s,1,false,%s)",
            (
                doc_id,
                "initial dataset",
                Jsonb({"key": manifest_key, "version": manifest_version}),
            ),
        )
        conn.execute("INSERT INTO outbox(doc_id,version) VALUES (%s,1)", (doc_id,))
    assert source() == ("initial dataset", 1, False)
    assert conn.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1
    project()
    assert (
        search.get("/" + index + "/_doc/" + doc_id).json()["_source"]["title"]
        == "initial dataset"
    )

    # A metadata transaction either commits the new source and event together
    # or leaves both unchanged; the S3 object alone never publishes a dataset.
    try:
        with conn.transaction():
            conn.execute(
                "UPDATE documents SET title=%s,version=2 WHERE id=%s",
                ("rolled back", doc_id),
            )
            conn.execute("INSERT INTO outbox(doc_id,version) VALUES (%s,2)", (doc_id,))
            raise RuntimeError("synthetic transaction failure")
    except RuntimeError:
        pass
    assert source() == ("initial dataset", 1, False)
    assert conn.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1

    with conn.transaction():
        conn.execute(
            "UPDATE documents SET title=%s,version=2 WHERE id=%s",
            ("updated dataset", doc_id),
        )
        conn.execute("INSERT INTO outbox(doc_id,version) VALUES (%s,2)", (doc_id,))
    assert source() == ("updated dataset", 2, False)
    assert (
        search.get("/" + index + "/_doc/" + doc_id).json()["_source"]["title"]
        == "initial dataset"
    )
    project()
    assert (
        search.get("/" + index + "/_doc/" + doc_id).json()["_source"]["title"]
        == "updated dataset"
    )
    with conn.transaction():
        conn.execute(
            "UPDATE documents SET deleted=true,version=3 WHERE id=%s", (doc_id,)
        )
        conn.execute("INSERT INTO outbox(doc_id,version) VALUES (%s,3)", (doc_id,))
    assert source() == ("updated dataset", 3, True)
    project()
    assert search.get("/" + index + "/_doc/" + doc_id).status_code == 404
    assert (
        conn.execute("SELECT count(*) FROM outbox WHERE processed").fetchone()[0] == 3
    )


if __name__ == "__main__":
    main()
