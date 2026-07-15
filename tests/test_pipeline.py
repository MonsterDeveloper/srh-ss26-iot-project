from __future__ import annotations

import math
import numpy as np

from api import pipeline


def test_safe_recursively_normalizes_json_values():
    assert pipeline._safe({1: (np.int64(2), float("nan"), float("inf"))}) == {"1": [2, None, None]}


def test_pipeline_success_formulas_and_stream_errors(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_step_features", lambda _: {"duration_s": 2.0, "step_count": 4})
    monkeypatch.setattr(pipeline, "extract_audio_features", lambda _: {"value": np.float64(1)})
    monkeypatch.setattr(pipeline, "mouth_opening_series", lambda _: np.array([1.0, np.nan]))
    features, errors = pipeline.process_recording({"motion":"m", "audio":"a", "video":"v"}, 14)
    assert errors == {} and features["motion"]["walking_speed_cms"] == 700
    assert features["motion"]["step_length_cm"] == 350 and features["video"]["n_frames"] == 2


def test_pipeline_error_is_sanitized(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_step_features", lambda _: (_ for _ in ()).throw(RuntimeError("/secret/input")))
    monkeypatch.setattr(pipeline, "extract_audio_features", lambda _: {})
    monkeypatch.setattr(pipeline, "mouth_opening_series", lambda _: np.array([]))
    _, errors = pipeline.process_recording({"motion":"m", "audio":"missing", "video":"missing"}, 14)
    assert "/secret" not in errors["motion"] and "RuntimeError" in errors["motion"]


def test_pipeline_zero_motion_values_and_video_failure(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_step_features", lambda _: {"duration_s": 0, "step_count": 0})
    monkeypatch.setattr(pipeline, "extract_audio_features", lambda _: {})
    monkeypatch.setattr(pipeline, "mouth_opening_series", lambda _: (_ for _ in ()).throw(ValueError("bad video")))
    features, errors = pipeline.process_recording({"motion": "m", "audio": "a", "video": "v"}, 14)
    assert features["motion"] == {"duration_s": 0, "step_count": 0}
    assert "walking_speed_cms" not in features["motion"] and "step_length_cm" not in features["motion"]
    assert errors == {"video": "ValueError: extraction could not process this stream"}


def test_pipeline_audio_failure_is_sanitized(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_step_features", lambda _: {})
    monkeypatch.setattr(pipeline, "extract_audio_features", lambda _: (_ for _ in ()).throw(OSError("/secret/audio")))
    monkeypatch.setattr(pipeline, "mouth_opening_series", lambda _: np.array([]))
    _, errors = pipeline.process_recording({"motion": "m", "audio": "a", "video": "v"}, 14)
    assert errors == {"audio": "OSError: extraction could not process this stream"}
