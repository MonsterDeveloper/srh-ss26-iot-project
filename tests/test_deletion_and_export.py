from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import text
from api.models import Recording, RecordingStatus
from tests.helpers import exercise, experiment


@pytest.mark.integration
def test_export_empty_and_flattened_features(client, db_engine, auth_headers):
    parent = experiment(client, auth_headers); item = exercise(client, auth_headers, parent["id"], properties={"condition":"a", "repetition":1})
    empty = client.get(f"/experiments/{parent['id']}/export", headers=auth_headers)
    assert empty.status_code == 200 and len(list(csv.DictReader(io.StringIO(empty.text)))) == 1
    # Use a lowercase literal to build this export fixture: this test is about
    # export, while the separate enum contract test owns the ORM mismatch.
    with db_engine.begin() as connection:
        connection.execute(text("INSERT INTO recordings (id, exercise_id, status, features) VALUES (gen_random_uuid(), :exercise, 'completed', CAST(:features AS jsonb))"), {"exercise": item["id"], "features": '{"motion":{"cadence":1},"list":[1]}'})
    exported = client.get(f"/experiments/{parent['id']}/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    row = next(csv.DictReader(io.StringIO(exported.text)))
    assert row["motion.cadence"] == "1" and "list" not in row


@pytest.mark.integration
def test_delete_storage_failure_preserves_metadata(client, storage, db_engine, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers); item = exercise(client, auth_headers, parent["id"])
    with db_engine.begin() as connection:
        connection.execute(text("INSERT INTO recordings (id, exercise_id, status) VALUES (gen_random_uuid(), :exercise, 'idle')"), {"exercise": item["id"]})
    monkeypatch.setattr(storage, "delete_manifest", lambda _: (_ for _ in ()).throw(RuntimeError("down")))
    response = client.delete(f"/exercises/{item['id']}", headers=auth_headers)
    assert response.status_code == 503, response.text
    assert client.get(f"/exercises/{item['id']}", headers=auth_headers).status_code == 200


@pytest.mark.integration
def test_delete_exercise_removes_source_objects(client, storage, auth_headers):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    started = client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers).json()
    manifest = storage.manifest(parent["id"], item["id"], started["recordingId"])
    for spec in manifest.values():
        storage.internal.put_object(Bucket=storage.bucket, Key=spec["key"], Body=b"x", ContentType=spec["contentType"])
    assert client.delete(f"/exercises/{item['id']}", headers=auth_headers).status_code == 204
    with pytest.raises(ValueError, match="Missing uploaded"):
        storage.head_all(manifest)


@pytest.mark.integration
def test_delete_experiment_removes_all_sources(client, storage, auth_headers):
    parent = experiment(client, auth_headers)
    manifests = []
    for _ in range(2):
        item = exercise(client, auth_headers, parent["id"])
        started = client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers).json()
        manifest = storage.manifest(parent["id"], item["id"], started["recordingId"])
        manifests.append(manifest)
        for spec in manifest.values():
            storage.internal.put_object(Bucket=storage.bucket, Key=spec["key"], Body=b"x", ContentType=spec["contentType"])
    assert client.delete(f"/experiments/{parent['id']}", headers=auth_headers).status_code == 204
    for manifest in manifests:
        with pytest.raises(ValueError, match="Missing uploaded"):
            storage.head_all(manifest)


@pytest.mark.integration
def test_delete_experiment_storage_failure_preserves_metadata(client, storage, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    assert client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers).status_code == 200
    monkeypatch.setattr(storage, "delete_manifest", lambda _: (_ for _ in ()).throw(RuntimeError("down")))
    response = client.delete(f"/experiments/{parent['id']}", headers=auth_headers)
    assert response.status_code == 503
    assert client.get(f"/experiments/{parent['id']}", headers=auth_headers).status_code == 200
