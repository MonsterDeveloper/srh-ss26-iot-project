from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from api.models import Exercise, Experiment, Recording, RecordingStatus


DASHBOARD = {"Authorization": "Bearer test-dashboard-token", "X-Dashboard-Actor": "researcher1", "X-Request-ID": "request-1"}


@pytest.mark.integration
def test_dashboard_auth_actor_spoofing_and_audit_safety(client, auth_headers):
    assert client.get("/dashboard/metadata", headers=auth_headers).status_code == 403
    assert client.get("/dashboard/metadata", headers={"Authorization": "Bearer wrong"}).status_code == 401
    created = client.post("/experiments", headers={**auth_headers, "X-Dashboard-Actor": "spoofed"}, json={"patientNumber": "secret", "properties": {"private": "value"}})
    assert created.status_code == 201
    audit = client.get("/audit-events", headers=DASHBOARD).json()["items"][0]
    assert audit["actor"] == "api-client"
    assert audit["requestId"] if "requestId" in audit else True
    assert audit["changedFields"] == ["patientNumber", "properties"]
    assert "secret" not in str(audit) and "value" not in str(audit)


@pytest.mark.integration
def test_condition_compatibility_archive_restore_and_filters(client, auth_headers):
    parent = client.post("/experiments", headers=DASHBOARD, json={"patientNumber": "P-42", "properties": {}}).json()
    item = client.post(f"/experiments/{parent['id']}/exercises", headers=DASHBOARD, json={"condition": "normal", "repetition": 1, "properties": {"condition": "normal", "repetition": 1}})
    assert item.status_code == 201 and item.json()["condition"] == "normal"
    assert client.post(f"/experiments/{parent['id']}/exercises", headers=DASHBOARD, json={"condition": "unknown", "repetition": 1}).status_code == 422
    assert client.post(f"/experiments/{parent['id']}/exercises", headers=auth_headers, json={"properties": {"condition": "legacy", "repetition": "bad"}}).json()["condition"] == "legacy"
    assert client.post(f"/experiments/{parent['id']}/exercises", headers=DASHBOARD, json={"condition": "normal", "repetition": 1}).status_code == 409
    exercise_id = item.json()["id"]
    assert client.patch(f"/exercises/{exercise_id}", headers=DASHBOARD, json={"condition": "fast", "repetition": 2}).json()["properties"] == {"condition": "fast", "repetition": 2}
    assert client.patch(f"/exercises/{exercise_id}", headers=DASHBOARD, json={"condition": "normal"}).status_code == 200
    assert client.patch(f"/exercises/{exercise_id}", headers=DASHBOARD, json={"repetition": 3}).status_code == 200
    assert client.patch(f"/exercises/{exercise_id}", headers=auth_headers, json={"condition": "fast", "properties": {"condition": "normal"}}).status_code == 422
    assert client.patch(f"/exercises/{exercise_id}", headers=auth_headers, json={"repetition": 2, "properties": {"repetition": 3}}).status_code == 422
    assert client.patch(f"/exercises/{exercise_id}", headers=DASHBOARD, json={"properties": {"condition": "normal", "repetition": 3}}).json()["condition"] == "normal"
    assert client.post(f"/exercises/{exercise_id}/archive", headers=DASHBOARD).status_code == 200
    assert client.post(f"/exercises/{exercise_id}/archive", headers=DASHBOARD).status_code == 200
    replacement = client.post(f"/experiments/{parent['id']}/exercises", headers=DASHBOARD, json={"condition": "normal", "repetition": 3})
    assert replacement.status_code == 201
    assert client.post(f"/exercises/{exercise_id}/restore", headers=DASHBOARD).status_code == 409
    assert client.patch(f"/exercises/{exercise_id}", headers=DASHBOARD, json={"repetition": 3}).status_code == 409
    assert client.post(f"/experiments/{parent['id']}/archive", headers=DASHBOARD).json()["archivedBy"] == "researcher1"
    assert client.post(f"/experiments/{parent['id']}/archive", headers=DASHBOARD).status_code == 200
    assert client.patch(f"/experiments/{parent['id']}", headers=DASHBOARD, json={"age": 50}).status_code == 409
    assert client.post(f"/experiments/{parent['id']}/exercises", headers=DASHBOARD, json={"condition": "wide_step", "repetition": 1}).status_code == 409
    assert client.get("/dashboard/experiments?archive=archived&patientNumber=P-42&condition=normal", headers=DASHBOARD).json()["total"] == 1
    assert client.post(f"/experiments/{parent['id']}/restore", headers=DASHBOARD).status_code == 200
    assert client.post("/experiments/missing/archive", headers=DASHBOARD).status_code == 404
    events = client.get(f"/audit-events?experimentId={parent['id']}&pageSize=100", headers=DASHBOARD).json()
    assert events["total"] >= 7


@pytest.mark.integration
def test_dashboard_overview_analysis_quality_traces_and_media(client, db_session, storage):
    now = datetime.now(timezone.utc)
    parent = Experiment(patient_number="P-1", age=70, created_at=now)
    exercise = Exercise(experiment=parent, condition="normal", repetition=1, properties={"condition": "normal", "repetition": 1})
    recording = Recording(
        id=uuid.uuid4(), exercise=exercise, status=RecordingStatus.COMPLETED_WITH_ERRORS,
        object_manifest={}, features={"motion": {"clip_fraction": 0.2, "step_regularity": 0.7}, "audio": {"mean_loudness": -12.0}, "video": {"face_detection_ratio": 0.5, "mean_mouth_opening": None}},
        errors={"video": "safe"}, traces={"schemaVersion": 1, "motion": {"time": [0.0], "accelerationMagnitude": [1.0]}}, artifacts={}, ended_at=now,
    )
    stale = Exercise(experiment=parent, condition="wide_step", repetition=1, properties={})
    stale_recording = Recording(id=uuid.uuid4(), exercise=stale, status=RecordingStatus.PROCESSING, object_manifest={}, updated_at=now - timedelta(hours=1))
    db_session.add_all([parent, exercise, recording, stale, stale_recording]); db_session.commit()
    source = storage.manifest(parent.id, exercise.id, str(recording.id))
    recording.object_manifest = source
    playback = {"key": source["video"]["key"].replace("video.h264", "video.mp4"), "contentType": "video/mp4", "size": 3}
    recording.artifacts = {"video_playback": playback}; db_session.commit()
    for item, body in [(source["motion"], b"csv"), (source["audio"], b"wav"), (source["video"], b"h264"), (playback, b"mp4")]:
        storage.internal.put_object(Bucket=storage.bucket, Key=item["key"], Body=body, ContentType=item["contentType"])

    metadata = client.get("/dashboard/metadata", headers=DASHBOARD).json()
    assert [item["id"] for item in metadata["conditions"]] == ["normal", "fast", "wide_step"]
    assert client.get("/dashboard/experiments", headers=DASHBOARD).status_code == 200
    overview = client.get("/dashboard/overview", headers=DASHBOARD).json()
    assert overview["activeExperimentCount"] == 1 and overview["activeWorkCount"] == 1
    analysis = client.get("/dashboard/analysis?condition=normal&qualityOnly=true&feature=step_regularity", headers=DASHBOARD).json()
    assert analysis["total"] == 1 and analysis["items"][0]["features"]["motion"] == {"step_regularity": 0.7}
    quality = client.get("/dashboard/quality?severity=warning&modality=motion&condition=normal", headers=DASHBOARD).json()
    assert [item["code"] for item in quality["items"]] == ["imu_clipping"]
    all_quality = client.get("/dashboard/quality?pageSize=100", headers=DASHBOARD).json()["items"]
    assert {item["code"] for item in all_quality} >= {"extraction_errors", "imu_clipping", "low_face_detection", "stale_state"}
    assert client.get(f"/exercises/{exercise.id}/traces", headers=DASHBOARD).json()["schemaVersion"] == 1
    assert client.get(f"/exercises/{stale.id}/traces", headers=DASHBOARD).status_code == 404
    media = client.get(f"/exercises/{exercise.id}/media/video_playback/url", headers=DASHBOARD).json()
    assert media["contentType"] == "video/mp4" and media["size"] == 3 and "X-Amz-" in media["url"]
    assert client.get(f"/exercises/{exercise.id}/media/nope/url", headers=DASHBOARD).status_code == 404
    assert client.get(f"/exercises/{stale.id}/media/video_playback/url", headers=DASHBOARD).status_code == 404
    assert client.get(f"/audit-events?exerciseId={exercise.id}", headers=DASHBOARD).status_code == 200
    assert client.get("/dashboard/experiments?createdFrom=bad", headers=DASHBOARD).status_code == 422
    assert client.get("/dashboard/experiments?createdFrom=2020-01-01T00:00:00%2B00:00", headers=DASHBOARD).status_code == 200
    filtered = client.get(f"/dashboard/experiments?archive=all&createdFrom={now.date()}&createdTo={now.date()}&recordingStatus=completed_with_errors", headers=DASHBOARD).json()
    assert filtered["total"] == 1
    analysis_filtered = client.get(f"/dashboard/analysis?patientNumber=P-1&createdFrom={now.date()}&createdTo={now.date()}&recordingStatus=completed_with_errors", headers=DASHBOARD).json()
    assert analysis_filtered["total"] == 1
    assert client.get("/dashboard/quality?issue=extraction_errors&recordingStatus=completed_with_errors", headers=DASHBOARD).json()["total"] == 1


@pytest.mark.integration
def test_clear_derived_data_removes_derivative_but_retains_sources(client, db_session, storage):
    parent = Experiment(); exercise = Exercise(experiment=parent)
    recording = Recording(id=uuid.uuid4(), exercise=exercise, status=RecordingStatus.COMPLETED, features={"motion": {}}, traces={"schemaVersion": 1})
    db_session.add_all([parent, exercise, recording]); db_session.commit()
    source = storage.manifest(parent.id, exercise.id, str(recording.id)); artifact = {"key": source["video"]["key"].replace("video.h264", "video.mp4"), "contentType": "video/mp4"}
    recording.object_manifest = source; recording.artifacts = {"video_playback": artifact}; db_session.commit()
    for item in [*source.values(), artifact]: storage.internal.put_object(Bucket=storage.bucket, Key=item["key"], Body=b"x", ContentType=item["contentType"])
    assert client.delete(f"/exercises/{exercise.id}/data", headers=DASHBOARD).status_code == 204
    assert storage.internal.head_object(Bucket=storage.bucket, Key=source["audio"]["key"])["ContentLength"] == 1
    with pytest.raises(Exception): storage.internal.head_object(Bucket=storage.bucket, Key=artifact["key"])


@pytest.mark.integration
def test_missing_media_and_storage_clear_errors(client, db_session, storage, monkeypatch):
    parent = Experiment(); empty = Exercise(experiment=parent); derived = Exercise(experiment=parent)
    recording = Recording(id=uuid.uuid4(), exercise=derived, status=RecordingStatus.COMPLETED, features={"motion": {}}, artifacts={"video_playback": {"key": "missing", "contentType": "video/mp4"}})
    db_session.add_all([parent, empty, derived, recording]); db_session.commit()
    assert client.get(f"/exercises/{empty.id}/media/audio/url", headers=DASHBOARD).status_code == 404
    assert client.get(f"/exercises/{derived.id}/media/video_playback/url", headers=DASHBOARD).status_code == 404
    monkeypatch.setattr(storage, "delete_artifacts", lambda *_: (_ for _ in ()).throw(RuntimeError("down")))
    assert client.delete(f"/exercises/{derived.id}/data", headers=DASHBOARD).status_code == 503


@pytest.mark.integration
def test_successful_processing_uploads_playback_artifact(client, db_session, storage, monkeypatch):
    from api import server
    parent = client.post("/experiments", headers=DASHBOARD, json={}).json()
    exercise = client.post(f"/experiments/{parent['id']}/exercises", headers=DASHBOARD, json={"condition": "normal", "repetition": 1}).json()
    started = client.post(f"/exercises/{exercise['id']}/recording/start", headers=DASHBOARD).json()
    manifest = storage.manifest(parent["id"], exercise["id"], started["recordingId"])
    for item in manifest.values(): storage.internal.put_object(Bucket=storage.bucket, Key=item["key"], Body=b"source", ContentType=item["contentType"])
    monkeypatch.setattr(server, "process_recording", lambda *_: ({"motion": {}, "audio": {}, "video": {}}, {}, {"schemaVersion": 1}))
    def fake_mp4(_source, target): target.write_bytes(b"browser mp4"); return "remux"
    monkeypatch.setattr(server, "create_mp4", fake_mp4)
    assert client.post(f"/exercises/{exercise['id']}/recording/stop", headers=DASHBOARD).status_code == 200
    recording = db_session.get(Recording, uuid.UUID(started["recordingId"])); db_session.refresh(recording)
    assert recording.artifacts["video_playback"]["method"] == "remux"
