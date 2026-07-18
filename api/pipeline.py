from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from extract_audio_features import (
    extract_audio_features, frame_loudness_db, frame_times, load_audio,
    loudness_trend, loudness_variability, mean_loudness, vocal_activity_ratio,
    voice_activity_mask,
)
from extract_step_features import (
    TARGET_FS, activity_ratio, cadence_spectral, cadence_time_domain,
    detect_strides, extract_step_features, gait_regularity, interval_cv,
    mean_rotation, preprocess, rotation_variability, step_amplitude,
    unbiased_autocorrelation,
)
from extract_video_features import DEFAULT_FPS, mean_mouth_opening, mouth_opening_series, opening_rate, opening_trend, opening_variability

TRACE_SCHEMA_VERSION = 1
# Well below the contract ceiling to keep each JSON document compact while
# preserving peaks in the short pilot recordings.
MAX_TRACE_POINTS = 100


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


def _indices(length: int, maximum: int = MAX_TRACE_POINTS) -> np.ndarray:
    """Deterministic endpoint-preserving indices for aligned trace groups."""
    if length <= maximum:
        return np.arange(length, dtype=int)
    return np.unique(np.linspace(0, length - 1, maximum, dtype=int))


def _peak_indices(values: Any, maximum: int = MAX_TRACE_POINTS) -> np.ndarray:
    """Keep local minima/maxima in deterministic buckets, including endpoints."""
    array = np.asarray(values, dtype=float)
    if len(array) <= maximum:
        return np.arange(len(array), dtype=int)
    bucket_count = max(1, (maximum - 2) // 2)
    selected = {0, len(array) - 1}
    for bucket in np.array_split(np.arange(1, len(array) - 1), bucket_count):
        finite = np.nan_to_num(array[bucket], nan=0.0, posinf=0.0, neginf=0.0)
        selected.add(int(bucket[int(np.argmin(finite))])); selected.add(int(bucket[int(np.argmax(finite))]))
    return np.asarray(sorted(selected)[:maximum], dtype=int)


def downsample_aligned(series: dict[str, Any], maximum: int = MAX_TRACE_POINTS) -> dict[str, list]:
    """Peak-preserving downsampling for an aligned series group."""
    if not series:
        return {}
    lengths = {len(np.asarray(value)) for value in series.values()}
    if len(lengths) != 1:
        raise ValueError("aligned trace series must have equal lengths")
    reference = next((value for key, value in series.items() if key.lower() not in {"time", "frametimes"}), next(iter(series.values())))
    indexes = _peak_indices(reference, maximum)
    return {key: _series(value, indexes) for key, value in series.items()}


def _series(values: Any, indices: np.ndarray | None = None) -> list:
    array = np.asarray(values)
    if indices is None:
        indices = _indices(len(array))
    return _safe(array[indices].tolist())


def _motion(path: Path, route_distance_m: float) -> tuple[dict, dict]:
    frame, clip_fraction, effective_fs = preprocess(path)
    duration = float(frame["time"].iloc[-1] - frame["time"].iloc[0])
    gyro_band = frame["gyro_mag_band"].to_numpy()
    peaks = detect_strides(gyro_band, TARGET_FS)
    steps = 2 * len(peaks)
    step_regularity, stride_regularity = gait_regularity(gyro_band, TARGET_FS)
    features = {
        "n_samples": len(frame), "duration_s": duration, "effective_fs": effective_fs,
        "clip_fraction": clip_fraction, "step_count": steps, "n_strides": len(peaks),
        "cadence_time_domain": cadence_time_domain(steps, duration), "cadence_spectral": cadence_spectral(gyro_band, TARGET_FS),
        "step_regularity": step_regularity, "stride_regularity": stride_regularity,
        "interval_cv": interval_cv(peaks, TARGET_FS), "activity_ratio": activity_ratio(frame["accel_mag_hp"].to_numpy(), TARGET_FS),
        "step_amplitude": step_amplitude(frame["accel_mag_band"].to_numpy(), peaks),
        "mean_rotation": mean_rotation(frame["gyro_mag"].to_numpy()), "rotation_variability": rotation_variability(frame["gyro_mag"].to_numpy()),
    }
    if duration and duration > 0:
        features["walking_speed_cms"] = route_distance_m * 100 / duration
    if steps:
        features["step_length_cm"] = route_distance_m * 100 / steps
    indexes = _peak_indices(gyro_band)
    marker = np.full(len(frame), np.nan)
    marker[peaks] = gyro_band[peaks]
    freqs, psd = __import__("scipy.signal", fromlist=["welch"]).welch(gyro_band, fs=TARGET_FS, nperseg=min(len(gyro_band), 256))
    autocorrelation = unbiased_autocorrelation(gyro_band)
    ac_indexes = _indices(len(autocorrelation))
    trace = {
        "time": _series(frame["time"].to_numpy() - frame["time"].iloc[0], indexes),
        "accelX": _series(frame["accel_x"], indexes), "accelY": _series(frame["accel_y"], indexes), "accelZ": _series(frame["accel_z"], indexes),
        "gyroX": _series(frame["gyro_x"], indexes), "gyroY": _series(frame["gyro_y"], indexes), "gyroZ": _series(frame["gyro_z"], indexes),
        "accelerationMagnitude": _series(frame["accel_mag"], indexes), "gyroscopeMagnitude": _series(frame["gyro_mag"], indexes),
        "strideSignal": _series(gyro_band, indexes), "strideMarkers": _series(marker, indexes),
        "psdFrequency": _series(freqs), "psd": _series(psd),
        "autocorrelationLag": _series(np.arange(len(autocorrelation)) / TARGET_FS, ac_indexes),
        "autocorrelation": _series(autocorrelation, ac_indexes),
    }
    return features, trace


def _audio(path: Path) -> tuple[dict, dict]:
    samples, sample_rate = load_audio(path)
    loudness = frame_loudness_db(samples)
    times = frame_times(len(loudness), sample_rate)
    voiced = voice_activity_mask(loudness)
    features = {
        "n_frames": len(loudness), "duration_s": float(len(samples) / sample_rate) if sample_rate else float("nan"), "sample_rate": sample_rate,
        "mean_loudness": mean_loudness(loudness, voiced), "vocal_activity_ratio": vocal_activity_ratio(voiced),
        "loudness_variability": loudness_variability(loudness, voiced), "loudness_trend": loudness_trend(loudness, times, voiced),
    }
    frame_indexes = _peak_indices(loudness)
    # Min/max envelope is calculated over deterministic equal-width bins.
    edges = np.linspace(0, len(samples), min(MAX_TRACE_POINTS, max(1, len(samples))) + 1, dtype=int)
    mins, maxes = [], []
    for left, right in zip(edges[:-1], edges[1:], strict=True):
        window = samples[left:max(right, left + 1)]
        mins.append(float(np.min(window))); maxes.append(float(np.max(window)))
    slope = features.get("loudness_trend")
    intercept = float(np.mean(loudness[voiced]) - slope * np.mean(times[voiced])) if voiced.any() and slope is not None and math.isfinite(slope) else None
    return features, {
        "time": _safe((edges[:-1] / sample_rate).tolist()), "waveformMin": _safe(mins), "waveformMax": _safe(maxes),
        "frameTimes": _series(times, frame_indexes), "loudness": _series(loudness, frame_indexes),
        "voiced": _series(voiced.astype(float), frame_indexes), "trendCoefficients": _safe([intercept, slope]),
    }


def _video(path: Path) -> tuple[dict, dict]:
    opening = mouth_opening_series(path)
    detected = ~np.isnan(opening)
    features = {
        "n_frames": int(len(opening)), "n_face_detected": int(np.sum(detected)),
        "face_detection_ratio": float(np.mean(detected)) if len(opening) else 0.0,
        "fps_assumed": float(DEFAULT_FPS), "duration_s": float(len(opening) / DEFAULT_FPS),
        "mean_mouth_opening": mean_mouth_opening(opening), "mouth_opening_rate": opening_rate(opening, DEFAULT_FPS),
        "opening_variability": opening_variability(opening), "opening_trend": opening_trend(opening, DEFAULT_FPS),
    }
    valid = opening[detected]
    prominence = max(0.5 * float(np.std(valid)), 1e-6) if len(valid) else 1e-6
    event_indices = __import__("scipy.signal", fromlist=["find_peaks"]).find_peaks(np.nan_to_num(opening, nan=-np.inf), distance=max(int(0.25 * DEFAULT_FPS), 1), prominence=prominence)[0]
    indexes = _peak_indices(opening)
    events = np.full(len(opening), np.nan); events[event_indices] = opening[event_indices]
    return features, {
        "frameTimes": _series(np.arange(len(opening)) / DEFAULT_FPS, indexes),
        "mouthOpening": _series(opening, indexes), "openingEvents": _series(events, indexes),
        "assumedFps": [float(DEFAULT_FPS)],
    }


def process_recording(paths: dict[str, str], route_distance_m: float, include_traces: bool = False):
    features: dict = {}
    errors: dict = {}
    traces: dict = {"schemaVersion": TRACE_SCHEMA_VERSION}
    if not include_traces:
        try:
            motion = extract_step_features(Path(paths["motion"]))
            duration, steps = motion.get("duration_s"), motion.get("step_count")
            if duration and duration > 0:
                motion["walking_speed_cms"] = route_distance_m * 100 / duration
            if steps:
                motion["step_length_cm"] = route_distance_m * 100 / steps
            features["motion"] = motion
        except Exception as exc:
            errors["motion"] = _error(exc)
        try:
            features["audio"] = extract_audio_features(Path(paths["audio"]))
        except Exception as exc:
            errors["audio"] = _error(exc)
        try:
            features["video"], _ = _video(Path(paths["video"]))
        except Exception as exc:
            errors["video"] = _error(exc)
        return _safe(features), _safe(errors)
    try:
        features["motion"], traces["motion"] = _motion(Path(paths["motion"]), route_distance_m)
    except Exception as exc:  # extraction failures are persisted per stream
        errors["motion"] = _error(exc)
    try:
        features["audio"], traces["audio"] = _audio(Path(paths["audio"]))
    except Exception as exc:
        errors["audio"] = _error(exc)
    try:
        features["video"], traces["video"] = _video(Path(paths["video"]))
    except Exception as exc:
        errors["video"] = _error(exc)
    result = (_safe(features), _safe(errors), _safe(traces))
    return result if include_traces else result[:2]


def process_recording_with_traces(paths: dict[str, str], route_distance_m: float) -> tuple[dict, dict, dict]:
    return process_recording(paths, route_distance_m, include_traces=True)
