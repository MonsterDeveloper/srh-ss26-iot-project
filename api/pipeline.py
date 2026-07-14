from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from extract_audio_features import extract_audio_features
from extract_step_features import extract_step_features
from extract_video_features import DEFAULT_FPS, mean_mouth_opening, mouth_opening_series, opening_rate, opening_trend, opening_variability


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _error(exc: Exception) -> str:
    # Deliberately omit traceback, paths, and implementation details.
    return f"{type(exc).__name__}: extraction could not process this stream"


def process_recording(paths: dict[str, str], route_distance_m: float) -> tuple[dict, dict]:
    features: dict = {}
    errors: dict = {}
    try:
        motion = extract_step_features(Path(paths["motion"]))
        duration, steps = motion.get("duration_s"), motion.get("step_count")
        if duration and duration > 0:
            motion["walking_speed_cms"] = route_distance_m * 100 / duration
        if steps:
            motion["step_length_cm"] = route_distance_m * 100 / steps
        features["motion"] = motion
    except Exception as exc:  # extraction failures are persisted per stream
        errors["motion"] = _error(exc)
    try:
        features["audio"] = extract_audio_features(Path(paths["audio"]))
    except Exception as exc:
        errors["audio"] = _error(exc)
    try:
        opening = mouth_opening_series(Path(paths["video"]))  # one decoding pass
        features["video"] = {
            "n_frames": int(len(opening)), "n_face_detected": int(np.sum(~np.isnan(opening))),
            "face_detection_ratio": float(np.mean(~np.isnan(opening))) if len(opening) else 0.0,
            "fps_assumed": float(DEFAULT_FPS), "mean_mouth_opening": mean_mouth_opening(opening),
            "mouth_opening_rate": opening_rate(opening, DEFAULT_FPS),
            "opening_variability": opening_variability(opening), "opening_trend": opening_trend(opening, DEFAULT_FPS),
        }
    except Exception as exc:
        errors["video"] = _error(exc)
    return _safe(features), _safe(errors)
