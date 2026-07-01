"""IMU feature extraction (accelerometer + gyroscope).

Implements the pipeline documented in README.md: preprocessing (clip
flagging/repair, uniform resampling, magnitude signals, band-pass filtering)
followed by the four motion features (step count, cadence, gait regularity,
activity ratio) plus the two gyroscope features (mean rotation, rotation
variability) for a single `motion_*.csv` trial.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, find_peaks, welch

SENSOR_COLUMNS = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"]
INT16_SATURATION = 32767

TARGET_FS = 10.0  # Hz, uniform resampling grid
BAND_LOW, BAND_HIGH = 0.5, 3.0  # Hz, walking step-frequency band
MIN_STRIDE_TIME_S = 0.3  # ~3 samples at 10 Hz
ACTIVITY_WINDOW_S = 1.0


# ---------- Stage A: preprocessing ----------


def load_trial(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df.sort_values("time").drop_duplicates(subset="time").reset_index(drop=True)


def compute_clip_fraction(df: pd.DataFrame) -> float:
    clipped = (df[SENSOR_COLUMNS].abs() >= INT16_SATURATION).any(axis=1)
    return float(clipped.mean())


def effective_sampling_rate(df: pd.DataFrame) -> float:
    dt = np.diff(df["time"].to_numpy())
    return float(1.0 / np.median(dt))


def interpolate_short_clips(df: pd.DataFrame, max_run: int = 2) -> pd.DataFrame:
    """Linear-interpolate clipped runs of <= max_run samples; leave longer runs as-is."""
    df = df.copy()
    for col in SENSOR_COLUMNS:
        series = df[col].astype(float)
        mask = series.abs() >= INT16_SATURATION
        if not mask.any():
            continue
        run_id = (mask != mask.shift(fill_value=False)).cumsum()
        short_runs = series[mask].groupby(run_id[mask]).filter(lambda g: len(g) <= max_run)
        series.loc[short_runs.index] = np.nan
        df[col] = series.interpolate(method="linear").ffill().bfill()
    return df


def resample_uniform(df: pd.DataFrame, fs: float = TARGET_FS) -> pd.DataFrame:
    t0, t1 = df["time"].iloc[0], df["time"].iloc[-1]
    grid = t0 + np.arange(int((t1 - t0) * fs) + 1) / fs
    out = {"time": grid}
    for col in SENSOR_COLUMNS:
        out[col] = np.interp(grid, df["time"], df[col])
    return pd.DataFrame(out)


def add_magnitudes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["accel_mag"] = np.sqrt(df["accel_x"] ** 2 + df["accel_y"] ** 2 + df["accel_z"] ** 2)
    df["gyro_mag"] = np.sqrt(df["gyro_x"] ** 2 + df["gyro_y"] ** 2 + df["gyro_z"] ** 2)
    return df


def bandpass_filter(signal: np.ndarray, fs: float, low: float = BAND_LOW, high: float = BAND_HIGH, order: int = 4) -> np.ndarray:
    nyquist = fs / 2
    b, a = butter(order, [low / nyquist, high / nyquist], btype="band")
    return filtfilt(b, a, signal)


def highpass_filter(signal: np.ndarray, fs: float, cutoff: float = BAND_LOW, order: int = 4) -> np.ndarray:
    nyquist = fs / 2
    b, a = butter(order, cutoff / nyquist, btype="high")
    return filtfilt(b, a, signal)


def preprocess(path: Path) -> tuple[pd.DataFrame, float, float]:
    raw = load_trial(path)
    clip_fraction = compute_clip_fraction(raw)
    fs_effective = effective_sampling_rate(raw)
    cleaned = interpolate_short_clips(raw)
    uniform = add_magnitudes(resample_uniform(cleaned))
    uniform["gyro_mag_band"] = bandpass_filter(uniform["gyro_mag"].to_numpy(), TARGET_FS)
    uniform["accel_mag_band"] = bandpass_filter(uniform["accel_mag"].to_numpy(), TARGET_FS)
    uniform["accel_mag_hp"] = highpass_filter(uniform["accel_mag"].to_numpy(), TARGET_FS)
    return uniform, clip_fraction, fs_effective


# ---------- Stage B: the four features ----------


def mad(x: np.ndarray) -> float:
    return float(np.median(np.abs(x - np.median(x))))


def detect_strides(signal: np.ndarray, fs: float, k: float = 1.5) -> np.ndarray:
    """One peak in the (one-leg) gyro magnitude ~= one stride of that leg."""
    prominence = max(k * mad(signal), 1e-9)
    distance = max(int(MIN_STRIDE_TIME_S * fs), 1)
    peaks, _ = find_peaks(signal, distance=distance, prominence=prominence)
    return peaks


def cadence_time_domain(n_steps: int, duration_s: float) -> float:
    return n_steps / duration_s * 60.0 if duration_s > 0 else float("nan")


def cadence_spectral(signal: np.ndarray, fs: float) -> float:
    freqs, psd = welch(signal, fs=fs, nperseg=min(len(signal), 256))
    band = (freqs >= BAND_LOW) & (freqs <= BAND_HIGH)
    if not band.any():
        return float("nan")
    dominant_stride_freq = freqs[band][np.argmax(psd[band])]
    return dominant_stride_freq * 2 * 60.0  # stride Hz -> steps/min (one-leg convention)


def unbiased_autocorrelation(signal: np.ndarray) -> np.ndarray:
    """Moe-Nilssen & Helbostad unbiased, zero-lag-normalized autocorrelation."""
    x = signal - np.mean(signal)
    n = len(x)
    ac = np.correlate(x, x, mode="full")[n - 1 :]
    ac = ac / (n - np.arange(n))
    return ac / ac[0] if ac[0] != 0 else ac


def gait_regularity(signal: np.ndarray, fs: float) -> tuple[float, float]:
    ac = unbiased_autocorrelation(signal)
    min_lag = max(int(MIN_STRIDE_TIME_S * fs), 1)
    peaks, _ = find_peaks(ac)
    peaks = peaks[peaks >= min_lag]
    if len(peaks) == 0:
        return float("nan"), float("nan")
    step_regularity = float(ac[peaks[0]])
    stride_regularity = float(ac[peaks[1]]) if len(peaks) > 1 else float("nan")
    return step_regularity, stride_regularity


def interval_cv(peak_samples: np.ndarray, fs: float) -> float:
    if len(peak_samples) < 2:
        return float("nan")
    intervals = np.diff(peak_samples) / fs
    return float(np.std(intervals) / np.mean(intervals))


def otsu_threshold(values: np.ndarray, n_bins: int = 32) -> float:
    """Otsu's method: threshold maximizing between-class variance of the histogram."""
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


def step_amplitude(accel_band: np.ndarray, stride_peaks: np.ndarray) -> float:
    """Mean band-passed accel magnitude at each detected stride — per-step swing size."""
    if len(stride_peaks) == 0:
        return float("nan")
    return float(np.mean(np.abs(accel_band[stride_peaks])))


def mean_rotation(gyro_mag: np.ndarray) -> float:
    return float(np.mean(gyro_mag))


def rotation_variability(gyro_mag: np.ndarray) -> float:
    return float(np.std(gyro_mag))


def activity_ratio(signal: np.ndarray, fs: float, window_s: float = ACTIVITY_WINDOW_S) -> float:
    window = max(int(window_s * fs), 1)
    n_windows = len(signal) // window
    if n_windows == 0:
        return float("nan")
    window_energy = np.array([np.std(signal[i * window : (i + 1) * window]) for i in range(n_windows)])
    threshold = otsu_threshold(window_energy)
    return float(np.mean(window_energy > threshold))


def extract_step_features(path: str | Path) -> dict:
    uniform, clip_fraction, fs_effective = preprocess(Path(path))
    duration_s = float(uniform["time"].iloc[-1] - uniform["time"].iloc[0])
    gyro_band = uniform["gyro_mag_band"].to_numpy()

    stride_peaks = detect_strides(gyro_band, TARGET_FS)
    n_strides = len(stride_peaks)
    n_steps = 2 * n_strides
    step_regularity, stride_regularity = gait_regularity(gyro_band, TARGET_FS)

    return {
        "n_samples": len(uniform),
        "duration_s": duration_s,
        "effective_fs": fs_effective,
        "clip_fraction": clip_fraction,
        "step_count": n_steps,
        "n_strides": n_strides,
        "cadence_time_domain": cadence_time_domain(n_steps, duration_s),
        "cadence_spectral": cadence_spectral(gyro_band, TARGET_FS),
        "step_regularity": step_regularity,
        "stride_regularity": stride_regularity,
        "interval_cv": interval_cv(stride_peaks, TARGET_FS),
        "activity_ratio": activity_ratio(uniform["accel_mag_hp"].to_numpy(), TARGET_FS),
        "step_amplitude": step_amplitude(uniform["accel_mag_band"].to_numpy(), stride_peaks),
        "mean_rotation": mean_rotation(uniform["gyro_mag"].to_numpy()),
        "rotation_variability": rotation_variability(uniform["gyro_mag"].to_numpy()),
    }
