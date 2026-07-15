from __future__ import annotations

from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from api.storage import STREAMS


def test_manifest_urls_and_metadata_validation(storage, tmp_path):
    storage.ensure_bucket_cors(["http://testserver"])
    manifest = storage.manifest("e", "x", "r")
    assert set(manifest) == set(STREAMS)
    assert all("X-Amz-" in url for url in storage.presigned_put_urls(manifest).values())
    for stream, spec in manifest.items():
        storage.internal.put_object(Bucket=storage.bucket, Key=spec["key"], Body=b"x", ContentType=spec["contentType"] + "; charset=utf-8")
    assert set(storage.head_all(manifest)) == set(STREAMS)
    paths = storage.download_all(manifest, tmp_path)
    assert {Path(path).read_bytes() for path in paths.values()} == {b"x"}
    storage.delete_manifest(manifest)
    with pytest.raises(ValueError, match="Missing uploaded"):
        storage.head_all(manifest)


def test_storage_rejects_wrong_type_oversize_and_empty_delete(storage):
    storage.ensure_bucket_cors(["http://testserver"])
    manifest = storage.manifest("e", "x", "r")
    motion = manifest["motion"]
    storage.internal.put_object(Bucket=storage.bucket, Key=motion["key"], Body=b"x", ContentType="application/json")
    with pytest.raises(ValueError, match="Invalid motion"):
        storage.head_all({"motion": motion})
    storage.delete_manifest({})


def test_storage_rejects_oversize_object(storage):
    storage.ensure_bucket_cors(["http://testserver"])
    motion = storage.manifest("e", "x", "r")["motion"]
    motion["maxBytes"] = 0
    storage.internal.put_object(Bucket=storage.bucket, Key=motion["key"], Body=b"x", ContentType=motion["contentType"])
    with pytest.raises(ValueError, match="Invalid motion"):
        storage.head_all({"motion": motion})


def test_storage_delete_translates_client_and_per_object_errors(storage, monkeypatch):
    manifest = storage.manifest("e", "x", "r")
    error = ClientError({"Error": {"Code": "InternalError", "Message": "down"}}, "DeleteObjects")
    monkeypatch.setattr(storage.internal, "delete_objects", lambda **_: (_ for _ in ()).throw(error))
    with pytest.raises(RuntimeError, match="Could not delete"):
        storage.delete_manifest(manifest)
    monkeypatch.setattr(storage.internal, "delete_objects", lambda **_: {"Errors": [{"Key": "bad"}]})
    with pytest.raises(RuntimeError, match="Could not delete"):
        storage.delete_manifest(manifest)
