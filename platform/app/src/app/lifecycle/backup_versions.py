"""Erase noncurrent S3 backup objects after restic has produced a clean repository.

Restic pruning removes current objects. Versioned S3 buckets can retain previous
object versions; every such copy in the dedicated repository prefix must also
be removed. This command receives root-only credentials over stdin, never HTTP.
"""

import json
import re
import sys
from urllib.parse import urlsplit
from uuid import UUID

import boto3


def stale_versions(page):
    return [
        {"Key": row["Key"], "VersionId": row["VersionId"]}
        for row in page.get("Versions", [])
        if not row["IsLatest"]
    ] + [
        {"Key": row["Key"], "VersionId": row["VersionId"]}
        for row in page.get("DeleteMarkers", [])
    ]


def erase(client, bucket, prefix):
    paginator = client.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        targets = stale_versions(page)
        for start in range(0, len(targets), 1000):
            response = client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": targets[start : start + 1000], "Quiet": True},
            )
            if response.get("Errors"):
                raise ValueError("Backup object versions could not be erased")
    # Re-list after mutations: pagination alone cannot certify erasure, and an
    # object lock/retention policy may leave historical objects in the backend.
    if any(
        stale_versions(page)
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
    ):
        raise ValueError("Historical backup object versions remain")


def main():
    from .maintenance import inspect

    payload = json.load(sys.stdin)
    operation = inspect(str(UUID(payload["operation_id"])))
    if operation["step"] != "catalog_removed":
        raise ValueError("Live project catalog has not been erased")
    configuration = payload["configuration"]
    repository = configuration["RESTIC_REPOSITORY"]
    if not repository.startswith("s3:https://"):
        raise ValueError("Expected an HTTPS S3 backup repository")
    endpoint = urlsplit(repository.removeprefix("s3:"))
    parts = endpoint.path.strip("/").split("/", 1)
    if len(parts) != 2 or not all(
        re.fullmatch(r"[A-Za-z0-9_./-]+", part) for part in parts
    ):
        raise ValueError("A dedicated backup bucket prefix is required")
    bucket, prefix = parts
    client = boto3.client(
        "s3",
        endpoint_url="https://" + endpoint.netloc,
        region_name=configuration["AWS_DEFAULT_REGION"],
        aws_access_key_id=configuration["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=configuration["AWS_SECRET_ACCESS_KEY"],
    )
    erase(client, bucket, prefix.rstrip("/") + "/")


if __name__ == "__main__":
    main()
