"""Audio feature extraction (near-face microphone).

Parallel to extract_step_features.py, but for the `audio_*.wav` recordings.
The microphone sits near the patient's face while they repeat the "BA" sound
during the walk. Per the project brief it tracks four loudness features:

    * mean loudness        — overall vocal effort
    * vocal activity ratio — fraction of time the patient is voicing
    * loudness variability — spread of loudness while voicing
    * loudness trend       — does loudness fade or grow over the trial

Pipeline: load -> mono -> frame-wise RMS loudness in dBFS -> Otsu-thresholded
voice-activity mask -> the four features (computed over voiced frames only,
except the activity ratio itself).
"""

from pathlib import Path

import librosa
import numpy as np

FRAME_LENGTH = 2048  # samples per analysis frame (~46 ms at 44.1 kHz)
HOP_LENGTH = 512  # samples between frames (~12 ms at 44.1 kHz)
EPS = 1e-10  # floor to keep log finite on silent frames


# ---------- Stage A: preprocessing ----------


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load a wav as mono float32 at its native sample rate."""
    y, sr = librosa.load(path, sr=None, mono=True)
    return y, int(sr)


def frame_loudness_db(y: np.ndarray) -> np.ndarray:
    """Frame-wise RMS converted to dBFS (0 dB = full scale, quieter is negative)."""
    rms = librosa.feature.rms(y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    return 20.0 * np.log10(rms + EPS)


def frame_times(n_frames: int, sr: int) -> np.ndarray:
    return librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=HOP_LENGTH)


# ---------- Stage B: voice activity ----------


def otsu_threshold(values: np.ndarray, n_bins: int = 32) -> float:
    """Otsu's method: threshold maximizing between-class variance of the histogram.

    Same implementation as extract_step_features.otsu_threshold — kept local so
    the audio module has no dependency on the IMU one.
    """
    hist, edges = np.histogram(values, bins=n_bins)
    hist = hist.astype(float)
    centers = (edges[:-1] + edges[1:]) / 2
    best_thresh, best_variance = centers[0], -1.0
    for i in range(1, n_bins):
        w0, w1 = hist[:i].sum(), hist[i:].sum()
        if w0 == 0 or w1 == 0:
            continue
        m0 = np.sum(hist[:i] * centers[:i]) / w0
        m1 = np.sum(hist[i:] * centers[i:]) / w1
        between_variance = w0 * w1 * (m0 - m1) ** 2
        if between_variance > best_variance:
            best_variance, best_thresh = between_variance, centers[i]
    return float(best_thresh)


def voice_activity_mask(loudness_db: np.ndarray) -> np.ndarray:
    """Boolean mask of voiced frames — frames louder than the Otsu split."""
    threshold = otsu_threshold(loudness_db)
    return loudness_db > threshold


# ---------- Stage C: the four features ----------


def mean_loudness(loudness_db: np.ndarray, voiced: np.ndarray) -> float:
    """Mean loudness (dBFS) over voiced frames — overall vocal effort."""
    if not voiced.any():
        return float("nan")
    return float(np.mean(loudness_db[voiced]))


def vocal_activity_ratio(voiced: np.ndarray) -> float:
    """Fraction of frames classified as voiced."""
    if len(voiced) == 0:
        return float("nan")
    return float(np.mean(voiced))


def loudness_variability(loudness_db: np.ndarray, voiced: np.ndarray) -> float:
    """Std of loudness (dB) over voiced frames — steadiness of the voice."""
    if voiced.sum() < 2:
        return float("nan")
    return float(np.std(loudness_db[voiced]))


def loudness_trend(loudness_db: np.ndarray, times: np.ndarray, voiced: np.ndarray) -> float:
    """Slope of loudness over time (dB/s) across voiced frames.

    Negative = voice fades over the trial, positive = it grows.
    """
    if voiced.sum() < 2:
        return float("nan")
    slope, _ = np.polyfit(times[voiced], loudness_db[voiced], 1)
    return float(slope)


def extract_audio_features(path: str | Path) -> dict:
    y, sr = load_audio(Path(path))
    loudness_db = frame_loudness_db(y)
    times = frame_times(len(loudness_db), sr)
    voiced = voice_activity_mask(loudness_db)

    return {
        "n_frames": len(loudness_db),
        "duration_s": float(len(y) / sr) if sr else float("nan"),
        "sample_rate": sr,
        "mean_loudness": mean_loudness(loudness_db, voiced),
        "vocal_activity_ratio": vocal_activity_ratio(voiced),
        "loudness_variability": loudness_variability(loudness_db, voiced),
        "loudness_trend": loudness_trend(loudness_db, times, voiced),
    }


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(arg)
        for key, value in extract_audio_features(arg).items():
            print(f"  {key}: {value}")
