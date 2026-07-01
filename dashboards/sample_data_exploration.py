"""Streamlit dashboard for exploring raw sensor recordings.

Loads motion (.csv), audio (.wav) and video (.h264) files collected by the
Raspberry Pi Zero rig and surfaces standard pandas/numpy/librosa summaries
(.info(), .describe(), NaN checks, etc.) to scope out cleanup steps.

This is a data-loading/inspection tool only — no feature extraction
(gait metrics, loudness, mouth opening, ...) happens here.

Run with: uv run streamlit run dashboards/sample_data_exploration.py
"""

import io
from pathlib import Path

import cv2
import librosa
import numpy as np
import pandas as pd
import streamlit as st

DATA_ROOT = Path(__file__).parent.parent / "collected_sample_data"
MOTION_COLUMNS = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"]
INT16_SATURATION = 32767

st.set_page_config(page_title="IoT Sensor Data Explorer", layout="wide")


@st.cache_data(show_spinner=False)
def discover_trials(root: str) -> pd.DataFrame:
    root_path = Path(root)
    rows = []
    for category_dir in sorted(p for p in root_path.iterdir() if p.is_dir()):
        motion_files = {f.stem.split("_", 1)[1]: f for f in category_dir.glob("motion_*.csv")}
        audio_files = {f.stem.split("_", 1)[1]: f for f in category_dir.glob("audio_*.wav")}
        video_files = {f.stem.split("_", 1)[1]: f for f in category_dir.glob("video_*.h264")}
        timestamps = sorted(set(motion_files) | set(audio_files) | set(video_files))
        for ts in timestamps:
            rows.append(
                {
                    "category": category_dir.name,
                    "timestamp": ts,
                    "motion_path": str(motion_files[ts]) if ts in motion_files else "",
                    "audio_path": str(audio_files[ts]) if ts in audio_files else "",
                    "video_path": str(video_files[ts]) if ts in video_files else "",
                }
            )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def load_motion(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_audio(path: str):
    y, sr = librosa.load(path, sr=None, mono=True)
    return y, sr


@st.cache_data(show_spinner="Decoding video frames (counting)...")
def count_video_frames(path: str):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"opened": False}
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    reported_fps = cap.get(cv2.CAP_PROP_FPS)
    reported_frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    count = 0
    ok, _ = cap.read()
    while ok:
        count += 1
        ok, _ = cap.read()
    cap.release()
    return {
        "opened": True,
        "width": width,
        "height": height,
        "reported_fps": reported_fps,
        "reported_frame_count": reported_frame_count,
        "decoded_frame_count": count,
    }


@st.cache_data(show_spinner="Extracting preview frames...")
def extract_preview_frames(path: str, frame_count: int):
    cap = cv2.VideoCapture(path)
    targets = {0, frame_count // 2, max(frame_count - 1, 0)}
    frames = {}
    idx = 0
    ok, frame = cap.read()
    while ok and targets:
        if idx in targets:
            frames[idx] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            targets.discard(idx)
        idx += 1
        ok, frame = cap.read()
    cap.release()
    return frames


st.title("IoT Sensor Data Explorer")
st.caption(
    "Raw sensor data loader & summary dashboard — inspecting file format, "
    "NaNs and obvious errors only. No feature extraction yet."
)

data_root = st.sidebar.text_input("Data root folder", value=str(DATA_ROOT))
trials_df = discover_trials(data_root)

if trials_df.empty:
    st.error(f"No trials found under {data_root}")
    st.stop()

category = st.sidebar.selectbox("Category", trials_df["category"].unique().tolist())
subset = trials_df[trials_df["category"] == category]
timestamp = st.sidebar.selectbox("Trial (timestamp)", subset["timestamp"].tolist())
trial = subset[subset["timestamp"] == timestamp].iloc[0]

st.sidebar.markdown("---")
st.sidebar.write("Motion:", "present" if trial.motion_path else "missing")
st.sidebar.write("Audio:", "present" if trial.audio_path else "missing")
st.sidebar.write("Video:", "present" if trial.video_path else "missing")

overview_tab, motion_tab, audio_tab, video_tab = st.tabs(
    ["Overview (all trials)", "Motion (IMU)", "Audio", "Video"]
)

with overview_tab:
    st.subheader("All discovered trials")
    st.dataframe(trials_df, use_container_width=True)

    st.markdown("---")
    if st.button("Compute cross-trial motion & audio summary"):
        summary_rows = []
        for _, t in trials_df.iterrows():
            row = {"category": t.category, "timestamp": t.timestamp}
            if t.motion_path:
                mdf = load_motion(t.motion_path)
                sensor_cols = [c for c in MOTION_COLUMNS if c in mdf.columns]
                row["motion_rows"] = len(mdf)
                row["motion_nans"] = int(mdf.isna().sum().sum())
                row["motion_saturated"] = int((mdf[sensor_cols].abs() >= INT16_SATURATION).sum().sum())
                row["motion_span_s"] = round(mdf["time"].iloc[-1] - mdf["time"].iloc[0], 2)
            if t.audio_path:
                y, sr = load_audio(t.audio_path)
                row["audio_duration_s"] = round(len(y) / sr, 2)
                row["audio_sr"] = sr
                row["audio_nans"] = int(np.isnan(y).sum())
                row["audio_clipped"] = int((np.abs(y) >= 0.999).sum())
            if t.video_path:
                row["video_size_mb"] = round(Path(t.video_path).stat().st_size / (1024**2), 2)
            summary_rows.append(row)
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)
    else:
        st.caption(
            "Video frame counts are computed lazily per-trial in the Video tab "
            "(full decode is slow). Click above to summarize motion + audio "
            "across all trials."
        )

with motion_tab:
    if not trial.motion_path:
        st.warning("No motion file for this trial.")
    else:
        df = load_motion(trial.motion_path)
        st.subheader(f"Motion data — {trial.category} / {trial.timestamp}")
        st.write(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**.head()**")
            st.dataframe(df.head(10))
        with c2:
            st.markdown("**Missing values per column**")
            st.dataframe(df.isna().sum().rename("n_missing"))

        st.markdown("**.info()**")
        buf = io.StringIO()
        df.info(buf=buf)
        st.code(buf.getvalue())

        st.markdown("**.describe()**")
        st.dataframe(df.describe())

        st.write(f"**Duplicate rows:** {df.duplicated().sum()}")

        st.markdown("**Sensor saturation check** (`|value| >= 32767`, int16 clipping)")
        sensor_cols = [c for c in MOTION_COLUMNS if c in df.columns]
        sat_counts = (df[sensor_cols].abs() >= INT16_SATURATION).sum().rename("n_saturated")
        st.dataframe(sat_counts)
        if sat_counts.sum() > 0:
            st.warning(
                f"{int(sat_counts.sum())} saturated readings found — the IMU is "
                "clipping at the int16 range during fast movements."
            )

        st.markdown("**Sampling interval (`time` diff) — describe()**")
        dt = df["time"].diff().dropna()
        st.dataframe(dt.describe().rename("dt_seconds"))
        st.line_chart(dt.rename("dt (s)"))

        st.markdown("**Raw signals**")
        accel_cols = [c for c in ["accel_x", "accel_y", "accel_z"] if c in df.columns]
        gyro_cols = [c for c in ["gyro_x", "gyro_y", "gyro_z"] if c in df.columns]
        cols = st.columns(2)
        with cols[0]:
            st.caption("Accelerometer (raw units)")
            st.line_chart(df.set_index("time")[accel_cols])
        with cols[1]:
            st.caption("Gyroscope (raw units)")
            st.line_chart(df.set_index("time")[gyro_cols])

with audio_tab:
    if not trial.audio_path:
        st.warning("No audio file for this trial.")
    else:
        y, sr = load_audio(trial.audio_path)
        st.subheader(f"Audio data — {trial.category} / {trial.timestamp}")
        st.audio(trial.audio_path)

        n_samples = len(y)
        duration = n_samples / sr
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Sample rate", f"{sr} Hz")
        m2.metric("Duration", f"{duration:.2f} s")
        m3.metric("Samples", f"{n_samples:,}")
        m4.metric("Channels", "1 (mono)")

        st.markdown("**Waveform summary (`describe()`)**")
        st.dataframe(pd.Series(y, name="amplitude").describe())

        n_nan = int(np.isnan(y).sum())
        n_inf = int(np.isinf(y).sum())
        n_clipped = int((np.abs(y) >= 0.999).sum())
        c1, c2, c3 = st.columns(3)
        c1.metric("NaN samples", n_nan)
        c2.metric("Inf samples", n_inf)
        c3.metric("Clipped samples (|amp| >= 0.999)", n_clipped)
        if n_nan or n_inf:
            st.error("Non-finite samples present — clean before any feature extraction.")
        if n_clipped:
            st.warning("Clipped samples detected — waveform hit full scale.")

        st.markdown("**Waveform**")
        max_points = 5000
        step = max(1, n_samples // max_points)
        st.line_chart(pd.Series(y[::step], name="amplitude"))

with video_tab:
    if not trial.video_path:
        st.warning("No video file for this trial.")
    else:
        st.subheader(f"Video data — {trial.category} / {trial.timestamp}")
        st.info(
            "Raw `.h264` elementary streams carry no container metadata — "
            "OpenCV's reported FPS/frame-count are placeholder values, not "
            "ground truth. The decoded frame count below comes from reading "
            "the whole stream."
        )
        meta = count_video_frames(trial.video_path)
        if not meta["opened"]:
            st.error("OpenCV could not open this video file.")
        else:
            file_size_mb = Path(trial.video_path).stat().st_size / (1024**2)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Resolution", f"{meta['width']}x{meta['height']}")
            m2.metric("Decoded frame count", meta["decoded_frame_count"])
            m3.metric("File size", f"{file_size_mb:.2f} MB")
            m4.metric("cv2-reported FPS (unreliable)", f"{meta['reported_fps']:.1f}")
            st.caption(f"cv2 CAP_PROP_FRAME_COUNT (unreliable): {meta['reported_frame_count']}")

            st.markdown("**Preview frames (first / middle / last)**")
            frames = extract_preview_frames(trial.video_path, meta["decoded_frame_count"])
            cols = st.columns(len(frames))
            for col, (idx, frame) in zip(cols, sorted(frames.items())):
                col.image(frame, caption=f"frame #{idx}", use_container_width=True)
