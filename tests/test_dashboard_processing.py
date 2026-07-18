from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from api import media, pipeline
from api import backfill
from api.backfill import backfill_recordings
from api.config import Settings, get_settings
from api.dashboard import conditions, metadata, quality_codes
from api.models import Exercise, Experiment, Recording, RecordingStatus


def test_peak_downsampling_alignment_and_validation():
    signal = np.zeros(5000); signal[2511] = 100
    result = pipeline.downsample_aligned({"time": np.arange(5000), "signal": signal})
    assert len(result["time"]) <= 2000 and 100 in result["signal"] and len(result["time"]) == len(result["signal"])
    with pytest.raises(ValueError, match="equal lengths"):
        pipeline.downsample_aligned({"time": [0, 1], "signal": [1]})
    assert pipeline.downsample_aligned({}) == {}


def test_feature_and_trace_extraction_in_one_pass(monkeypatch, tmp_path):
    length = 2100
    frame = pd.DataFrame({
        "time": np.arange(length) / 50,
        "accel_x": np.ones(length), "accel_y": np.ones(length), "accel_z": np.ones(length),
        "gyro_x": np.ones(length), "gyro_y": np.ones(length), "gyro_z": np.ones(length),
        "accel_mag": np.ones(length), "gyro_mag": np.ones(length), "gyro_mag_band": np.sin(np.arange(length) / 10),
        "accel_mag_hp": np.sin(np.arange(length) / 10), "accel_mag_band": np.sin(np.arange(length) / 10),
    })
    monkeypatch.setattr(pipeline, "preprocess", lambda _: (frame, 0.0, 50.0))
    monkeypatch.setattr(pipeline, "detect_strides", lambda *_: np.array([10, 20]))
    monkeypatch.setattr(pipeline, "load_audio", lambda _: (np.sin(np.arange(5000) / 10), 1000))
    monkeypatch.setattr(pipeline, "frame_loudness_db", lambda _: np.linspace(-40, -5, length))
    monkeypatch.setattr(pipeline, "frame_times", lambda count, _: np.arange(count) / 10)
    monkeypatch.setattr(pipeline, "voice_activity_mask", lambda values: values > -20)
    opening = np.sin(np.arange(length) / 20); opening[5] = np.nan
    monkeypatch.setattr(pipeline, "mouth_opening_series", lambda _: opening)
    features, errors, traces = pipeline.process_recording_with_traces({"motion": "m", "audio": "a", "video": "v"}, 14)
    assert errors == {} and features["motion"]["walking_speed_cms"] == pytest.approx(1400 / frame["time"].iloc[-1]) and features["motion"]["step_length_cm"] == 350
    assert traces["schemaVersion"] == 1
    for modality in ("motion", "audio", "video"):
        assert max(len(value) for value in traces[modality].values()) <= 2000
    assert None in traces["video"]["mouthOpening"]
    zero_frame = frame.iloc[:1].copy()
    monkeypatch.setattr(pipeline, "preprocess", lambda _: (zero_frame, 0.0, 50.0))
    monkeypatch.setattr(pipeline, "detect_strides", lambda *_: np.array([], dtype=int))
    zero_features, _ = pipeline._motion(Path("m"), 14)
    assert "walking_speed_cms" not in zero_features and "step_length_cm" not in zero_features


def test_trace_extraction_partial_failures_are_safe(monkeypatch):
    monkeypatch.setattr(pipeline, "_motion", lambda *_: (_ for _ in ()).throw(OSError("path secret")))
    monkeypatch.setattr(pipeline, "_audio", lambda *_: ({"ok": 1}, {"time": [0]}))
    monkeypatch.setattr(pipeline, "_video", lambda *_: (_ for _ in ()).throw(ValueError("bad")))
    features, errors, traces = pipeline.process_recording_with_traces({"motion": "m", "audio": "a", "video": "v"}, 1)
    assert features == {"audio": {"ok": 1}} and set(errors) == {"motion", "video"} and traces["audio"] == {"time": [0]}
    monkeypatch.setattr(pipeline, "_motion", lambda *_: ({"duration_s": 0, "step_count": 0}, {}))
    monkeypatch.setattr(pipeline, "_audio", lambda *_: (_ for _ in ()).throw(OSError("bad")))
    monkeypatch.setattr(pipeline, "_video", lambda *_: ({}, {}))
    features, errors, _ = pipeline.process_recording_with_traces({"motion": "m", "audio": "a", "video": "v"}, 1)
    assert errors == {"audio": "OSError: extraction could not process this stream"} and features["motion"] == {"duration_s": 0, "step_count": 0}


def test_mp4_remux_fallback_and_command_errors(monkeypatch, tmp_path):
    original_run = media._run
    original_valid = media._valid_mp4
    source, target = tmp_path / "source.h264", tmp_path / "video.mp4"
    source.write_bytes(b"source")
    calls = []
    monkeypatch.setattr(media, "_run", lambda command: calls.append(command))
    monkeypatch.setattr(media, "_valid_mp4", lambda _: True)
    assert media.create_mp4(source, target) == "remux" and "copy" in calls[0]
    validity = iter([False, True]); calls.clear()
    monkeypatch.setattr(media, "_valid_mp4", lambda _: next(validity))
    assert media.create_mp4(source, target) == "transcode" and "libx264" in calls[1]
    monkeypatch.setattr(media, "_valid_mp4", lambda _: False)
    with pytest.raises(media.DerivativeError, match="validated"):
        media.create_mp4(source, target)
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")))
    with pytest.raises(media.DerivativeError): original_run(["ffmpeg"])
    assert original_valid(tmp_path / "missing") is False
    target.write_bytes(b"long enough for probe")
    assert original_valid(target) is False
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: object())
    assert original_valid(target) is True


def test_condition_override_validation():
    settings = get_settings()
    override = '[{"id":"only","label":{"en":"Only","de":"Einzig"},"active":true,"order":0,"baseline":true}]'
    assert conditions(settings.model_copy(update={"exercise_conditions_json": override}))[0].id == "only"
    value = metadata(settings)
    assert value["traceSchemaVersion"] == 1 and len(value["features"]) >= 7
    invalid = '[{"id":"x","label":{"en":"X","de":"X"},"active":true,"order":0,"baseline":false}]'
    with pytest.raises(ValueError, match="exactly one"):
        conditions(settings.model_copy(update={"exercise_conditions_json": invalid}))
    duplicate = '[{"id":"x","label":{"en":"X","de":"X"},"order":0,"baseline":true},{"id":"x","label":{"en":"Y","de":"Y"},"order":1,"baseline":false}]'
    with pytest.raises(ValueError, match="IDs"):
        conditions(settings.model_copy(update={"exercise_conditions_json": duplicate}))
    duplicate_order = '[{"id":"x","label":{"en":"X","de":"X"},"order":0,"baseline":true},{"id":"y","label":{"en":"Y","de":"Y"},"order":0,"baseline":false}]'
    with pytest.raises(ValueError, match="ordering"):
        conditions(settings.model_copy(update={"exercise_conditions_json": duplicate_order}))
    values = settings.model_dump(); values["dashboard_api_bearer_token"] = values["api_bearer_token"]
    with pytest.raises(ValueError, match="must differ"): Settings(**values)


def test_all_quality_codes_without_relationship_loading():
    settings = get_settings(); exercise = Exercise()
    assert quality_codes(exercise, settings) == []
    exercise.recording = Recording(status=RecordingStatus.FAILED, features={"motion": {}}, traces={}, object_manifest={"video": {}}, artifacts={})
    assert set(quality_codes(exercise, settings)) == {"failed_recording", "missing_traces", "missing_mp4"}
    exercise.recording.status = RecordingStatus.UPLOADED; exercise.recording.features = {}
    assert "derived_data_cleared" in quality_codes(exercise, settings)


@pytest.mark.integration
def test_backfill_dry_run_update_idempotency_and_failure(db_session, storage, monkeypatch, tmp_path):
    storage.ensure_bucket_cors(["http://testserver"])
    parent = Experiment(); exercise = Exercise(experiment=parent)
    recording = Recording(id=uuid.uuid4(), exercise=exercise, status=RecordingStatus.COMPLETED, features={"motion": {"x": 1}})
    db_session.add_all([parent, exercise, recording]); db_session.commit()
    recording.object_manifest = storage.manifest(parent.id, exercise.id, str(recording.id)); db_session.commit()
    for item in recording.object_manifest.values():
        storage.internal.put_object(Bucket=storage.bucket, Key=item["key"], Body=b"source", ContentType=item["contentType"])
    assert backfill_recordings(db_session, storage, dry_run=True) == {"examined": 1, "updated": 1, "failed": 0}
    monkeypatch.setattr("api.backfill.process_recording_with_traces", lambda *_: ({}, {}, {"schemaVersion": 1}))
    def fake_mp4(_source: Path, target: Path): target.write_bytes(b"valid mp4"); return "remux"
    monkeypatch.setattr("api.backfill.create_mp4", fake_mp4)
    result = backfill_recordings(db_session, storage, recording_id=recording.id)
    assert result["updated"] == 1
    db_session.refresh(recording)
    assert recording.features == {"motion": {"x": 1}} and recording.traces["schemaVersion"] == 1 and "video_playback" in recording.artifacts
    assert backfill_recordings(db_session, storage, limit=1)["updated"] == 0
    recording.traces = {}; db_session.commit()
    assert backfill_recordings(db_session, storage)["updated"] == 1
    recording.artifacts = {}; db_session.commit()
    assert backfill_recordings(db_session, storage)["updated"] == 1
    recording.traces = {}; recording.artifacts = {}; db_session.commit()
    monkeypatch.setattr(storage, "download_all", lambda *_: (_ for _ in ()).throw(RuntimeError("nope")))
    assert backfill_recordings(db_session, storage)["failed"] == 1


def test_backfill_cli(monkeypatch, capsys):
    class Database:
        def __enter__(self): return self
        def __exit__(self, *_): return None
    monkeypatch.setattr(backfill, "SessionLocal", lambda: Database())
    monkeypatch.setattr(backfill, "ObjectStorage", lambda _: object())
    monkeypatch.setattr(backfill, "backfill_recordings", lambda *_args, **kwargs: kwargs)
    monkeypatch.setattr(sys, "argv", ["backfill", "--dry-run", "--limit", "2"])
    backfill.main()
    assert "dry_run" in capsys.readouterr().out
