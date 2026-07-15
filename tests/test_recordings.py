from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.models import Recording, RecordingStatus
from tests.helpers import exercise, experiment


def _put_all(storage, manifest, body=b"fixture"):
    for item in manifest.values():
        storage.internal.put_object(Bucket=storage.bucket, Key=item["key"], Body=body, ContentType=item["contentType"])


def _start_and_upload(client, storage, headers, parent, item):
    response = client.post(f"/exercises/{item['id']}/recording/start", headers=headers)
    assert response.status_code == 200, response.text
    started = response.json()
    manifest = storage.manifest(parent["id"], item["id"], started["recordingId"])
    _put_all(storage, manifest)
    return started, manifest


def _recording(db_session, storage, parent, item, status):
    recording = Recording(id=uuid.uuid4(), exercise_id=item["id"], status=status)
    recording.object_manifest = storage.manifest(parent["id"], item["id"], str(recording.id))
    db_session.add(recording)
    db_session.commit()
    return recording


@pytest.mark.integration
def test_recording_start_duplicate_refresh_and_missing_upload(client, storage, auth_headers):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    started = client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers)
    assert started.status_code == 200 and started.json()["status"] == "recording"
    assert client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers).status_code == 409
    assert client.post(f"/exercises/{item['id']}/recording/uploads/refresh", headers=auth_headers).status_code == 200
    assert client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers).status_code == 422


@pytest.mark.integration
def test_stop_all_stream_failure_contract_is_422(client, storage, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers); item = exercise(client, auth_headers, parent["id"])
    response = client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers)
    assert response.status_code == 200, response.text
    start = response.json()
    _put_all(storage, {k: {"key": v["key"], "contentType": v["contentType"], "maxBytes": 1000} for k, v in storage.manifest(parent['id'], item['id'], start['recordingId']).items()})
    # The persisted manifest is authoritative; put under exactly those keys.
    from api import server
    monkeypatch.setattr(server, "process_recording", lambda *_: ({}, {"motion":"bad", "audio":"bad", "video":"bad"}))
    response = client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers)
    assert response.status_code == 422
    canonical = response.json()["detail"]
    assert canonical["status"] == "failed" and canonical["errors"] == {"motion":"bad", "audio":"bad", "video":"bad"}
    assert client.get(f"/exercises/{item['id']}/data", headers=auth_headers).json() == canonical


@pytest.mark.integration
def test_data_delete_and_retry_state_rejections(client, storage, auth_headers):
    parent = experiment(client, auth_headers); item = exercise(client, auth_headers, parent["id"])
    assert client.get(f"/exercises/{item['id']}/data", headers=auth_headers).status_code == 404
    assert client.delete(f"/exercises/{item['id']}/data", headers=auth_headers).status_code == 404
    assert client.post(f"/exercises/{item['id']}/recording/retry", headers=auth_headers).status_code == 409
    assert client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers).status_code == 409


@pytest.mark.integration
@pytest.mark.parametrize(
    "features,errors,expected_status",
    [
        ({"motion": {}, "audio": {}, "video": {}}, {}, "completed"),
        ({"motion": {}, "audio": {}}, {"video": "bad"}, "completed_with_errors"),
    ],
)
def test_stop_success_and_partial_results(client, storage, auth_headers, monkeypatch, features, errors, expected_status):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    _start_and_upload(client, storage, auth_headers, parent, item)
    from api import server
    monkeypatch.setattr(server, "process_recording", lambda *_: (features, errors))
    response = client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == expected_status


@pytest.mark.integration
def test_unexpected_download_failure_is_sanitized_and_persisted(client, storage, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    _start_and_upload(client, storage, auth_headers, parent, item)
    monkeypatch.setattr(storage, "download_all", lambda *_: (_ for _ in ()).throw(RuntimeError("secret infrastructure detail")))
    response = client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["errors"] == {"recording": "Recording objects could not be processed"}


@pytest.mark.integration
@pytest.mark.parametrize("status", [RecordingStatus.FAILED, RecordingStatus.COMPLETED_WITH_ERRORS, RecordingStatus.UPLOADED])
def test_retry_from_every_retryable_state(client, storage, db_session, auth_headers, monkeypatch, status):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    recording = _recording(db_session, storage, parent, item, status)
    _put_all(storage, recording.object_manifest)
    from api import server
    monkeypatch.setattr(server, "process_recording", lambda *_: ({"motion": {}, "audio": {}, "video": {}}, {}))
    response = client.post(f"/exercises/{item['id']}/recording/retry", headers=auth_headers)
    assert response.status_code == 200 and response.json()["status"] == "completed"


@pytest.mark.integration
def test_delete_data_retains_sources_and_allows_retry(client, storage, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    _, manifest = _start_and_upload(client, storage, auth_headers, parent, item)
    from api import server
    monkeypatch.setattr(server, "process_recording", lambda *_: ({"motion": {}, "audio": {}, "video": {}}, {}))
    assert client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers).status_code == 200
    assert client.delete(f"/exercises/{item['id']}/data", headers=auth_headers).status_code == 204
    assert set(storage.head_all(manifest)) == {"motion", "audio", "video"}
    assert client.get(f"/exercises/{item['id']}/data", headers=auth_headers).status_code == 404
    retried = client.post(f"/exercises/{item['id']}/recording/retry", headers=auth_headers)
    assert retried.status_code == 200 and retried.json()["status"] == "completed"


@pytest.mark.integration
@pytest.mark.parametrize("endpoint", ["uploads/refresh", "stop"])
@pytest.mark.parametrize("status", [None, *[value for value in RecordingStatus if value is not RecordingStatus.RECORDING]])
def test_refresh_and_stop_reject_every_invalid_state(client, storage, db_session, auth_headers, endpoint, status):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    if status is not None:
        _recording(db_session, storage, parent, item, status)
    response = client.post(f"/exercises/{item['id']}/recording/{endpoint}", headers=auth_headers)
    assert response.status_code == 409


@pytest.mark.integration
@pytest.mark.parametrize("status", [None, RecordingStatus.IDLE, RecordingStatus.RECORDING, RecordingStatus.PROCESSING, RecordingStatus.COMPLETED])
def test_retry_rejects_every_invalid_state(client, storage, db_session, auth_headers, status):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    if status is not None:
        _recording(db_session, storage, parent, item, status)
    assert client.post(f"/exercises/{item['id']}/recording/retry", headers=auth_headers).status_code == 409


@pytest.mark.integration
@pytest.mark.parametrize("invalid", ["missing", "content_type", "oversize"])
def test_stop_validates_uploaded_objects(client, storage, auth_headers, invalid):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    response = client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers)
    manifest = storage.manifest(parent["id"], item["id"], response.json()["recordingId"])
    if invalid != "missing":
        for stream, spec in manifest.items():
            content_type = "application/octet-stream" if invalid == "content_type" and stream == "motion" else spec["contentType"]
            body = b"x" * (spec["maxBytes"] + 1) if invalid == "oversize" and stream == "motion" else b"x"
            storage.internal.put_object(Bucket=storage.bucket, Key=spec["key"], Body=body, ContentType=content_type)
    stopped = client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers)
    assert stopped.status_code == 422
    assert client.post(f"/exercises/{item['id']}/recording/uploads/refresh", headers=auth_headers).status_code == 200


@pytest.mark.integration
def test_concurrent_starts_return_one_success_and_one_conflict(client, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409], [(response.status_code, response.text) for response in responses]


@pytest.mark.integration
def test_start_translates_uniqueness_error_and_rolls_back(client, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    original_flush = Session.flush
    raised = False

    def conflicting_flush(session, *args, **kwargs):
        nonlocal raised
        if not raised and any(isinstance(value, Recording) for value in session.new):
            raised = True
            raise IntegrityError("INSERT", {}, Exception("unique"))
        return original_flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", conflicting_flush)
    response = client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers)
    assert response.status_code == 409
    assert client.get(f"/exercises/{item['id']}", headers=auth_headers).status_code == 200


@pytest.mark.integration
def test_concurrent_stops_claim_once_and_extract_once(client, storage, auth_headers, monkeypatch):
    parent = experiment(client, auth_headers)
    item = exercise(client, auth_headers, parent["id"])
    _start_and_upload(client, storage, auth_headers, parent, item)
    barrier = threading.Barrier(2)
    original_head = storage.head_all
    calls = 0
    lock = threading.Lock()

    def synchronized_head(manifest):
        result = original_head(manifest)
        barrier.wait(timeout=10)
        return result

    def counted_process(*_):
        nonlocal calls
        with lock:
            calls += 1
        return {"motion": {}, "audio": {}, "video": {}}, {}

    from api import server
    monkeypatch.setattr(storage, "head_all", synchronized_head)
    monkeypatch.setattr(server, "process_recording", counted_process)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert calls == 1
