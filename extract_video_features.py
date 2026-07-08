"""Video feature extraction (face camera).

Parallel to extract_step_features.py / extract_audio_features.py, but for the
`video_*.h264` face recordings. As the patient repeats the "BA" sound the mouth
opens and closes; MediaPipe FaceMesh gives per-frame lip landmarks from which we
derive the four mouth features in the project brief:

    * mean mouth opening   — average how-far-open the mouth is
    * mouth opening rate    — open/close cycles per second (the "BA BA" rate)
    * opening variability   — spread of mouth opening across the trial
    * opening trend         — does the mouth open more/less over the trial

The mouth opening is the vertical inner-lip gap **normalized by inter-ocular
distance**, so it is invariant to how close the face is to the camera.

Raw `.h264` elementary streams carry no container metadata, so OpenCV's reported
FPS is a placeholder. We take `fps` as an argument (default 30, the Pi camera
capture rate) — every time-based feature (rate, trend, duration) depends on it.

MediaPipe 0.10.x ships only the Tasks API, so this uses `FaceLandmarker` with a
downloaded model bundle (`models/face_landmarker.task`); the landmark topology
(478 points) is the same as the legacy FaceMesh, so the lip/eye indices below
are unchanged.
"""

from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from scipy.signal import find_peaks

DEFAULT_FPS = 30.0  # Pi camera capture rate; raw .h264 has no reliable metadata
MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"

# MediaPipe FaceMesh landmark indices (same topology in the Tasks API).
UPPER_INNER_LIP = 13
LOWER_INNER_LIP = 14
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263

MIN_CYCLE_TIME_S = 0.15  # ~3.3 "BA"/s ceiling — min spacing between open peaks


# ---------- Stage A: per-frame mouth opening ----------


def _landmark_xy(landmarks, index: int, w: int, h: int) -> np.ndarray:
    lm = landmarks[index]
    return np.array([lm.x * w, lm.y * h])


def _make_landmarker() -> vision.FaceLandmarker:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"FaceLandmarker model not found at {MODEL_PATH}. Download it from "
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
            "face_landmarker/float16/1/face_landmarker.task"
        )
    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
    )
    return vision.FaceLandmarker.create_from_options(options)


def mouth_opening_series(path: Path, fps: float = DEFAULT_FPS) -> np.ndarray:
    """Per-frame normalized mouth opening; NaN for frames with no detected face."""
    landmarker = _make_landmarker()
    cap = cv2.VideoCapture(str(path))
    openings = []
    frame_idx = 0
    try:
        ok, frame = cap.read()
        while ok:
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(frame_idx / fps * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
            if result.face_landmarks:
                lm = result.face_landmarks[0]
                top = _landmark_xy(lm, UPPER_INNER_LIP, w, h)
                bottom = _landmark_xy(lm, LOWER_INNER_LIP, w, h)
                left_eye = _landmark_xy(lm, LEFT_EYE_OUTER, w, h)
                right_eye = _landmark_xy(lm, RIGHT_EYE_OUTER, w, h)
                interocular = np.linalg.norm(left_eye - right_eye)
                gap = np.linalg.norm(top - bottom)
                openings.append(gap / interocular if interocular > 0 else np.nan)
            else:
                openings.append(np.nan)
            frame_idx += 1
            ok, frame = cap.read()
    finally:
        cap.release()
        landmarker.close()
    return np.array(openings, dtype=float)


# ---------- Stage B: the four features ----------


def mean_mouth_opening(opening: np.ndarray) -> float:
    """Mean normalized mouth opening over frames with a detected face."""
    valid = opening[~np.isnan(opening)]
    return float(np.mean(valid)) if valid.size else float("nan")


def opening_rate(opening: np.ndarray, fps: float) -> float:
    """Open/close cycles per second — peaks in the opening signal over duration."""
    valid = opening[~np.isnan(opening)]
    if valid.size < 2:
        return float("nan")
    prominence = max(0.5 * float(np.std(valid)), 1e-6)
    distance = max(int(MIN_CYCLE_TIME_S * fps), 1)
    peaks, _ = find_peaks(valid, distance=distance, prominence=prominence)
    duration_s = valid.size / fps
    return float(len(peaks) / duration_s) if duration_s > 0 else float("nan")


def opening_variability(opening: np.ndarray) -> float:
    """Std of mouth opening over detected frames."""
    valid = opening[~np.isnan(opening)]
    return float(np.std(valid)) if valid.size >= 2 else float("nan")


def opening_trend(opening: np.ndarray, fps: float) -> float:
    """Slope of mouth opening over time (opening units/s).

    Negative = mouth opens less as the trial goes on, positive = more.
    """
    idx = np.arange(len(opening))
    mask = ~np.isnan(opening)
    if mask.sum() < 2:
        return float("nan")
    times = idx[mask] / fps
    slope, _ = np.polyfit(times, opening[mask], 1)
    return float(slope)


def extract_video_features(path: str | Path, fps: float = DEFAULT_FPS) -> dict:
    opening = mouth_opening_series(Path(path), fps)
    n_frames = len(opening)
    n_detected = int(np.sum(~np.isnan(opening)))

    return {
        "n_frames": n_frames,
        "n_face_detected": n_detected,
        "face_detection_ratio": float(n_detected / n_frames) if n_frames else float("nan"),
        "duration_s": float(n_frames / fps) if fps else float("nan"),
        "fps_assumed": fps,
        "mean_mouth_opening": mean_mouth_opening(opening),
        "mouth_opening_rate": opening_rate(opening, fps),
        "opening_variability": opening_variability(opening),
        "opening_trend": opening_trend(opening, fps),
    }


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(arg)
        for key, value in extract_video_features(arg).items():
            print(f"  {key}: {value}")
