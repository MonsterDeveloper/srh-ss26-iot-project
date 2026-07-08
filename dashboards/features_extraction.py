"""Streamlit dashboard for exploring extracted trial features (IMU · voice · mouth).

Runs all three feature-extraction pipelines over every trial in
collected_sample_data/ once at server start and merges them per trial:

  * extract_step_features.py  — motion_*.csv  → cadence / gait / rotation
  * extract_audio_features.py — audio_*.wav   → loudness / vocal activity
  * extract_video_features.py — video_*.h264  → mouth opening / rate

(no preprocessing/filtering here — each extractor owns that) and presents a full
explorer:

  * Overview & quality  — KPIs, per-trial table, data-quality panel.
  * Condition comparison — the hypothesis view: are wider-movement conditions
    more stable / louder / more articulate? Grouped bars with per-trial points
    plus a radar "fingerprint".
  * Feature relationships — interactive scatter + correlation heatmap across all
    modalities (does a bigger step come with a louder, steadier voice?).
  * Trial deep-dive — re-runs each pipeline to connect the numbers back to the
    raw signals (stride peaks / PSD / autocorrelation, loudness-over-time,
    mouth-opening-over-time).

The study is comparative: 3 walking conditions x 3 trials = 9 recordings, so
individual trial points are always shown alongside any mean — no significance
claims are made on n=3.

Run with: uv run streamlit run dashboards/features_extraction.py
"""

import sys
from pathlib import Path

import altair as alt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from scipy.signal import find_peaks, welch

sys.path.append(str(Path(__file__).parent.parent))

from extract_audio_features import (
    extract_audio_features,
    frame_loudness_db,
    frame_times,
    load_audio,
    voice_activity_mask,
)
from extract_step_features import (
    BAND_HIGH,
    BAND_LOW,
    TARGET_FS,
    detect_strides,
    extract_step_features,
    preprocess,
    unbiased_autocorrelation,
)
from extract_video_features import (
    DEFAULT_FPS,
    MIN_CYCLE_TIME_S,
    extract_video_features,
    mouth_opening_series,
)

DATA_ROOT = Path(__file__).parent.parent / "collected_sample_data"

# label, unit, group, higher_is_better (None = neutral/descriptive), desc
FEATURE_META = {
    # ----- IMU (motion_*.csv) -----
    "cadence_time_domain": ("Cadence (time-domain)", "steps/min", "Cadence", None,
                            "Steps per minute from stride count / duration."),
    "cadence_spectral": ("Cadence (spectral)", "steps/min", "Cadence", None,
                         "Steps per minute from the dominant gait frequency (Welch PSD)."),
    "step_regularity": ("Step regularity", "0–1", "Gait stability", True,
                        "Autocorrelation at the step lag — higher = more repeatable steps."),
    "stride_regularity": ("Stride regularity", "0–1", "Gait stability", True,
                          "Autocorrelation at the stride lag — higher = more repeatable strides."),
    "interval_cv": ("Stride interval CV", "ratio", "Gait stability", False,
                    "Variability of stride timing — lower = more consistent (more stable)."),
    "step_amplitude": ("Step amplitude", "accel band a.u.", "Movement magnitude", None,
                       "Band-passed accel magnitude at each stride — per-step swing size."),
    "mean_rotation": ("Mean rotation", "gyro a.u.", "Movement magnitude", None,
                      "Mean gyroscope magnitude — overall angular activity of the leg."),
    "rotation_variability": ("Rotation variability", "gyro a.u.", "Movement magnitude", None,
                             "Std of gyroscope magnitude — spread of angular velocity."),
    "activity_ratio": ("Activity ratio", "0–1", "Activity", None,
                       "Fraction of time the leg is actively moving (Otsu-thresholded energy)."),
    # ----- Voice (audio_*.wav) -----
    "mean_loudness": ("Mean loudness", "dBFS", "Voice (audio)", True,
                      "Mean RMS loudness over voiced frames — overall vocal effort (louder = higher)."),
    "vocal_activity_ratio": ("Vocal activity ratio", "0–1", "Voice (audio)", True,
                             "Fraction of frames classified as voiced — how much of the trial is voiced."),
    "loudness_variability": ("Loudness variability", "dB", "Voice (audio)", None,
                             "Std of loudness over voiced frames — steadiness of the voice."),
    "loudness_trend": ("Loudness trend", "dB/s", "Voice (audio)", None,
                       "Slope of loudness over time — negative = the voice fades over the trial."),
    # ----- Mouth (video_*.h264) -----
    "mean_mouth_opening": ("Mean mouth opening", "ratio", "Mouth (video)", None,
                           "Mean inner-lip gap normalized by inter-ocular distance."),
    "mouth_opening_rate": ("Mouth opening rate", "cycles/s", "Mouth (video)", None,
                           "Open/close cycles per second — the 'BA BA' articulation rate."),
    "opening_variability": ("Opening variability", "ratio", "Mouth (video)", None,
                            "Std of mouth opening across the trial."),
    "opening_trend": ("Opening trend", "1/s", "Mouth (video)", None,
                      "Slope of mouth opening over time — negative = mouth opens less over the trial."),
    # ----- Counts / quality (all modalities) -----
    "step_count": ("Step count", "steps", "Counts / quality", None, "Detected steps (2 x strides)."),
    "n_strides": ("Stride count", "strides", "Counts / quality", None, "Detected gyro-magnitude peaks."),
    "duration_s": ("Duration", "s", "Counts / quality", None, "Trial length after resampling."),
    "effective_fs": ("Effective fs", "Hz", "Counts / quality", None, "Median raw sampling rate."),
    "clip_fraction": ("Clip fraction", "0–1", "Counts / quality", False,
                      "Fraction of samples hitting int16 saturation."),
    "n_samples": ("Samples", "n", "Counts / quality", None, "Rows after uniform resampling."),
    "face_detection_ratio": ("Face detection ratio", "0–1", "Counts / quality", None,
                             "Fraction of video frames with a detected face — video coverage/quality."),
}

GROUP_ORDER = ["Cadence", "Gait stability", "Movement magnitude", "Activity",
               "Voice (audio)", "Mouth (video)", "Counts / quality"]

# Which extracted keys to keep from the audio / video extractors (the rest are
# per-modality bookkeeping like n_frames/sample_rate that would collide on merge).
AUDIO_FEATURES = ["mean_loudness", "vocal_activity_ratio", "loudness_variability", "loudness_trend"]
VIDEO_FEATURES = ["mean_mouth_opening", "mouth_opening_rate", "opening_variability",
                  "opening_trend", "face_detection_ratio"]

st.set_page_config(page_title="Trial Feature Explorer", layout="wide")


# ---------- Feature extraction (once per server, cached) ----------


@st.cache_data(show_spinner="Extracting step features from all trials...")
def compute_step_features(root: str) -> pd.DataFrame:
    root_path = Path(root)
    rows = []
    for category_dir in sorted(p for p in root_path.iterdir() if p.is_dir()):
        for motion_path in sorted(category_dir.glob("motion_*.csv")):
            timestamp = motion_path.stem.split("_", 1)[1]
            features = extract_step_features(motion_path)
            rows.append(
                {
                    "category": category_dir.name,
                    "timestamp": timestamp,
                    "motion_path": str(motion_path),
                    **features,
                }
            )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Extracting voice features from all trials...")
def compute_audio_features(root: str) -> pd.DataFrame:
    root_path = Path(root)
    rows = []
    for category_dir in sorted(p for p in root_path.iterdir() if p.is_dir()):
        for audio_path in sorted(category_dir.glob("audio_*.wav")):
            timestamp = audio_path.stem.split("_", 1)[1]
            features = extract_audio_features(audio_path)
            rows.append(
                {
                    "category": category_dir.name,
                    "timestamp": timestamp,
                    "audio_path": str(audio_path),
                    **{k: features[k] for k in AUDIO_FEATURES},
                }
            )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Extracting mouth features from all trials (decoding video)...")
def compute_video_features(root: str) -> pd.DataFrame:
    root_path = Path(root)
    rows = []
    for category_dir in sorted(p for p in root_path.iterdir() if p.is_dir()):
        for video_path in sorted(category_dir.glob("video_*.h264")):
            timestamp = video_path.stem.split("_", 1)[1]
            features = extract_video_features(video_path)
            rows.append(
                {
                    "category": category_dir.name,
                    "timestamp": timestamp,
                    "video_path": str(video_path),
                    **{k: features[k] for k in VIDEO_FEATURES},
                }
            )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Re-running preprocessing for this trial...")
def compute_trial_signals(motion_path: str) -> dict:
    """Mirror extract_step_features internals so plots match the numbers."""
    uniform, clip_fraction, fs_effective = preprocess(Path(motion_path))
    gyro_band = uniform["gyro_mag_band"].to_numpy()
    peaks = detect_strides(gyro_band, TARGET_FS)
    freqs, psd = welch(gyro_band, fs=TARGET_FS, nperseg=min(len(gyro_band), 256))
    autocorr = unbiased_autocorrelation(gyro_band)
    return {
        "time": uniform["time"].to_numpy(),
        "gyro_mag": uniform["gyro_mag"].to_numpy(),
        "gyro_band": gyro_band,
        "peaks": peaks,
        "freqs": freqs,
        "psd": psd,
        "autocorr": autocorr,
    }


@st.cache_data(show_spinner="Re-computing loudness for this trial...")
def compute_audio_signal(audio_path: str) -> dict:
    """Mirror extract_audio_features internals: frame-wise loudness + voicing."""
    y, sr = load_audio(Path(audio_path))
    loudness_db = frame_loudness_db(y)
    times = frame_times(len(loudness_db), sr)
    voiced = voice_activity_mask(loudness_db)
    return {"times": times, "loudness_db": loudness_db, "voiced": voiced}


@st.cache_data(show_spinner="Re-decoding mouth opening for this trial...")
def compute_video_signal(video_path: str, fps: float = DEFAULT_FPS) -> dict:
    """Mirror extract_video_features internals: per-frame mouth opening."""
    opening = mouth_opening_series(Path(video_path), fps)
    return {"opening": opening, "fps": fps}


def feature_label(col: str) -> str:
    return FEATURE_META[col][0] if col in FEATURE_META else col


def trial_label(df: pd.DataFrame) -> pd.Series:
    return df["category"] + " / " + df["timestamp"]


def has_path(row: pd.Series, col: str) -> bool:
    return col in row and pd.notna(row[col]) and bool(row[col])


# ---------- Build the merged per-trial feature table ----------

features_df = compute_step_features(str(DATA_ROOT))
audio_df = compute_audio_features(str(DATA_ROOT))
video_df = compute_video_features(str(DATA_ROOT))

if not audio_df.empty:
    features_df = features_df.merge(audio_df, on=["category", "timestamp"], how="outer")
if not video_df.empty:
    features_df = features_df.merge(video_df, on=["category", "timestamp"], how="outer")

PATH_COLS = [c for c in ("motion_path", "audio_path", "video_path") if c in features_df.columns]

st.title("Trial Feature Explorer — IMU · Voice · Mouth")

if features_df.empty:
    st.error(f"No trials found under {DATA_ROOT}")
    st.stop()

st.caption(
    f"Motion, voice and mouth features for all {len(features_df)} trials under "
    f"`{DATA_ROOT.name}/`, computed once at server start via `extract_step_features.py`, "
    "`extract_audio_features.py` and `extract_video_features.py`. Comparative study: "
    "3 walking conditions x 3 trials — individual trials are always shown, no significance "
    "is claimed on n=3."
)

feature_cols = [c for c in FEATURE_META if c in features_df.columns]
compare_defaults = [
    c for c in feature_cols
    if FEATURE_META[c][2] in ("Gait stability", "Voice (audio)", "Mouth (video)")
]

tab_overview, tab_compare, tab_relate, tab_trial = st.tabs(
    ["Overview & quality", "Condition comparison", "Feature relationships", "Trial deep-dive"]
)


# ---------- Tab 1: Overview & quality ----------
with tab_overview:
    st.subheader("At a glance")
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.metric("Trials", len(features_df))
    k2.metric("Conditions", features_df["category"].nunique())
    k3.metric("Mean cadence", f"{features_df['cadence_spectral'].mean():.0f} spm")
    k4.metric("Mean stride reg.", f"{features_df['stride_regularity'].mean():.2f}")
    if "mean_loudness" in features_df:
        k5.metric("Mean loudness", f"{features_df['mean_loudness'].mean():.1f} dB")
    if "mouth_opening_rate" in features_df:
        k6.metric("Mean mouth rate", f"{features_df['mouth_opening_rate'].mean():.2f} /s")
    k7.metric("Total walk time", f"{features_df['duration_s'].sum():.0f} s")

    st.markdown("**Per-trial features**")
    display_df = features_df.drop(columns=PATH_COLS).copy()
    display_df.index = trial_label(features_df)
    st.dataframe(
        display_df.drop(columns=["category", "timestamp"]).style.format(precision=3),
        width="stretch",
    )

    with st.expander("Feature glossary"):
        glossary = pd.DataFrame(
            [
                {"feature": feature_label(c), "group": FEATURE_META[c][2],
                 "unit": FEATURE_META[c][1], "what it means": FEATURE_META[c][4]}
                for c in feature_cols
            ]
        )
        st.dataframe(glossary, width="stretch", hide_index=True)

    st.markdown("**Mean by condition**")
    st.dataframe(
        features_df.groupby("category")[feature_cols].mean().style.format(precision=3),
        width="stretch",
    )

    st.markdown("---")
    st.subheader("Data quality")
    qc_df = features_df.assign(trial=trial_label(features_df))
    qc_cols = [c for c in ["clip_fraction", "face_detection_ratio", "effective_fs", "duration_s"]
               if c in features_df.columns]
    for col in qc_cols:
        chart = (
            alt.Chart(qc_df)
            .mark_bar()
            .encode(
                x=alt.X("trial:N", sort=None, title=None, axis=alt.Axis(labelAngle=-40)),
                y=alt.Y(f"{col}:Q", title=f"{feature_label(col)} ({FEATURE_META[col][1]})"),
                color=alt.Color("category:N", title="Condition"),
                tooltip=["trial", alt.Tooltip(f"{col}:Q", format=".3f")],
            )
            .properties(height=200)
        )
        st.altair_chart(chart, use_container_width=True)

    high_clip = features_df[features_df["clip_fraction"] > 0.1]
    if not high_clip.empty:
        st.warning(
            f"{len(high_clip)} trial(s) have >10% clipped IMU samples — amplitude-based "
            "features (step_amplitude, mean_rotation, rotation_variability) may be less "
            "reliable for these: "
            + ", ".join(trial_label(high_clip).tolist())
        )
    if "face_detection_ratio" in features_df.columns:
        low_face = features_df[features_df["face_detection_ratio"] < 0.8]
        if not low_face.empty:
            st.warning(
                f"{len(low_face)} trial(s) have a face detected in <80% of video frames — "
                "mouth features may be less reliable for these: "
                + ", ".join(trial_label(low_face).tolist())
            )


# ---------- Tab 2: Condition comparison ----------
with tab_compare:
    st.subheader("Does wider movement change gait, voice & articulation?")
    st.caption(
        "Bars are per-condition means; dots are the 3 individual trials. With n=3 "
        "per condition, read the dots — a difference in means only matters if the "
        "trials don't overlap. Defaults span gait stability, voice and mouth."
    )
    selected = st.multiselect(
        "Features to compare",
        options=feature_cols,
        default=compare_defaults,
        format_func=feature_label,
    )

    if not selected:
        st.info("Select at least one feature to compare.")
    else:
        long_df = features_df.melt(
            id_vars=["category", "timestamp"],
            value_vars=selected,
            var_name="feature",
            value_name="value",
        )
        long_df["feature_label"] = long_df["feature"].map(feature_label)

        base = alt.Chart(long_df).encode(
            x=alt.X("category:N", title=None, axis=alt.Axis(labelAngle=-30)),
        )
        bars = base.mark_bar(opacity=0.55).encode(
            y=alt.Y("mean(value):Q", title="value"),
            color=alt.Color("category:N", title="Condition", legend=None),
        )
        points = base.mark_circle(size=70, color="black", opacity=0.8).encode(
            y=alt.Y("value:Q"),
            tooltip=["category", "timestamp", alt.Tooltip("value:Q", format=".3f")],
        )
        chart = (
            (bars + points)
            .properties(width=180, height=200)
            .facet(facet=alt.Facet("feature_label:N", title=None), columns=3)
            .resolve_scale(y="independent")
        )
        st.altair_chart(chart, use_container_width=True)

        st.markdown("**Condition fingerprint (normalized radar)**")
        st.caption(
            "Each feature is min–max normalized across all trials to 0–1, so the "
            "shapes are comparable. Note direction differs per feature: for "
            "regularity / loudness higher is better, for stride interval CV / clip "
            "fraction lower is better."
        )
        radar_feats = selected if len(selected) >= 3 else feature_cols[:6]
        means = features_df.groupby("category")[radar_feats].mean()
        norm = means.copy()
        for c in radar_feats:
            lo, hi = features_df[c].min(), features_df[c].max()
            norm[c] = (means[c] - lo) / (hi - lo) if hi > lo else 0.5

        angles = np.linspace(0, 2 * np.pi, len(radar_feats), endpoint=False)
        angles = np.concatenate([angles, angles[:1]])
        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})
        for category, row in norm.iterrows():
            vals = np.concatenate([row.values, row.values[:1]])
            ax.plot(angles, vals, label=category, linewidth=2)
            ax.fill(angles, vals, alpha=0.1)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels([feature_label(c) for c in radar_feats], fontsize=8)
        ax.set_yticklabels([])
        ax.set_ylim(0, 1)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)
        st.pyplot(fig)


# ---------- Tab 3: Feature relationships ----------
with tab_relate:
    st.subheader("How do features relate?")
    default_x = "step_amplitude" if "step_amplitude" in feature_cols else feature_cols[0]
    default_y = "mean_loudness" if "mean_loudness" in feature_cols else feature_cols[-1]
    c1, c2 = st.columns(2)
    x_feat = c1.selectbox("X axis", feature_cols, index=feature_cols.index(default_x),
                          format_func=feature_label)
    y_feat = c2.selectbox("Y axis", feature_cols, index=feature_cols.index(default_y),
                          format_func=feature_label)

    scatter = (
        alt.Chart(features_df.assign(trial=trial_label(features_df)))
        .mark_circle(size=140, opacity=0.8)
        .encode(
            x=alt.X(f"{x_feat}:Q", title=f"{feature_label(x_feat)} ({FEATURE_META[x_feat][1]})",
                    scale=alt.Scale(zero=False)),
            y=alt.Y(f"{y_feat}:Q", title=f"{feature_label(y_feat)} ({FEATURE_META[y_feat][1]})",
                    scale=alt.Scale(zero=False)),
            color=alt.Color("category:N", title="Condition"),
            tooltip=["trial", alt.Tooltip(f"{x_feat}:Q", format=".3f"),
                     alt.Tooltip(f"{y_feat}:Q", format=".3f")],
        )
        .properties(height=420)
        .interactive()
    )
    st.altair_chart(scatter, use_container_width=True)
    st.caption(
        "Default axes (step amplitude vs mean loudness) probe the core hypothesis: "
        "does a bigger per-step swing come with a louder, stronger voice?"
    )

    st.markdown("---")
    st.markdown(f"**Correlation heatmap** (Pearson, across all {len(features_df)} trials)")
    corr_feats = [c for c in feature_cols if FEATURE_META[c][2] != "Counts / quality"
                  or c in ("step_count", "activity_ratio")]
    corr = features_df[corr_feats].corr()
    corr_long = corr.stack().reset_index()
    corr_long.columns = ["f1", "f2", "corr"]
    corr_long["l1"] = corr_long["f1"].map(feature_label)
    corr_long["l2"] = corr_long["f2"].map(feature_label)
    order = [feature_label(c) for c in corr_feats]
    heat = (
        alt.Chart(corr_long)
        .mark_rect()
        .encode(
            x=alt.X("l1:N", sort=order, title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("l2:N", sort=order, title=None),
            color=alt.Color("corr:Q", scale=alt.Scale(scheme="redblue", domain=[-1, 1]),
                            title="Pearson r"),
            tooltip=["l1", "l2", alt.Tooltip("corr:Q", format=".2f")],
        )
        .properties(height=520)
    )
    text = heat.mark_text(fontSize=8).encode(
        text=alt.Text("corr:Q", format=".2f"),
        color=alt.condition("abs(datum.corr) > 0.6", alt.value("white"), alt.value("black")),
    )
    st.altair_chart(heat + text, use_container_width=True)
    st.caption(f"Only {len(features_df)} trials — treat correlations as exploratory, not conclusive.")


# ---------- Tab 4: Trial deep-dive ----------
with tab_trial:
    st.subheader("From signal to feature")
    c1, c2 = st.columns(2)
    category = c1.selectbox("Condition", sorted(features_df["category"].unique()))
    subset = features_df[features_df["category"] == category]
    timestamp = c2.selectbox("Trial", subset["timestamp"].tolist())
    row = subset[subset["timestamp"] == timestamp].iloc[0]

    # ----- IMU -----
    st.markdown("### Motion (IMU)")
    if not has_path(row, "motion_path"):
        st.warning("No motion file for this trial.")
    else:
        signals = compute_trial_signals(row["motion_path"])
        peaks = signals["peaks"]

        left, right = st.columns([3, 1])
        with right:
            st.markdown("**This trial**")
            st.metric("Steps", int(row["step_count"]))
            st.metric("Cadence (spectral)", f"{row['cadence_spectral']:.0f} spm")
            st.metric("Step regularity", f"{row['step_regularity']:.2f}")
            st.metric("Stride regularity", f"{row['stride_regularity']:.2f}")
            st.metric("Stride interval CV", f"{row['interval_cv']:.2f}")
            st.metric("Clip fraction", f"{row['clip_fraction']:.1%}")

        with left:
            # 1. Band-passed gyro magnitude with detected stride peaks.
            fig1, ax1 = plt.subplots(figsize=(9, 3))
            ax1.plot(signals["time"], signals["gyro_band"], color="#1f77b4", lw=1.2)
            ax1.plot(signals["time"][peaks], signals["gyro_band"][peaks], "x",
                     color="red", markersize=9, label=f"{len(peaks)} strides")
            ax1.set(xlabel="time (s)", ylabel="gyro mag (band 0.5–3 Hz)",
                    title="Stride detection — one peak ≈ one stride")
            ax1.legend(loc="upper right")
            st.pyplot(fig1)

            # 2. Welch PSD with walking band shaded + dominant peak.
            freqs, psd = signals["freqs"], signals["psd"]
            band = (freqs >= BAND_LOW) & (freqs <= BAND_HIGH)
            fig2, ax2 = plt.subplots(figsize=(9, 3))
            ax2.plot(freqs, psd, color="#2ca02c")
            ax2.axvspan(BAND_LOW, BAND_HIGH, color="orange", alpha=0.15,
                        label=f"walking band {BAND_LOW}–{BAND_HIGH} Hz")
            if band.any():
                dom = freqs[band][np.argmax(psd[band])]
                ax2.axvline(dom, color="red", ls="--",
                            label=f"dominant {dom:.2f} Hz → {dom * 120:.0f} spm")
            ax2.set(xlabel="frequency (Hz)", ylabel="power",
                    title="Welch PSD — drives spectral cadence")
            ax2.legend(loc="upper right")
            st.pyplot(fig2)

            # 3. Autocorrelation with first two lag peaks (step / stride regularity).
            autocorr = signals["autocorr"]
            lags = np.arange(len(autocorr)) / TARGET_FS
            min_lag = max(int(0.3 * TARGET_FS), 1)
            ac_peaks, _ = find_peaks(autocorr)
            ac_peaks = ac_peaks[ac_peaks >= min_lag]
            fig3, ax3 = plt.subplots(figsize=(9, 3))
            ax3.plot(lags, autocorr, color="#9467bd")
            ax3.axhline(0, color="gray", lw=0.6)
            for i, label in zip(ac_peaks[:2], ["step regularity", "stride regularity"]):
                ax3.plot(lags[i], autocorr[i], "o", color="red")
                ax3.annotate(f"{label}\n{autocorr[i]:.2f}", (lags[i], autocorr[i]),
                             textcoords="offset points", xytext=(5, 5), fontsize=8)
            ax3.set(xlabel="lag (s)", ylabel="autocorrelation",
                    title="Unbiased autocorrelation — drives gait regularity")
            st.pyplot(fig3)

    # ----- Voice -----
    st.markdown("---")
    st.markdown("### Voice (audio)")
    if not has_path(row, "audio_path"):
        st.warning("No audio file for this trial.")
    else:
        audio = compute_audio_signal(row["audio_path"])
        times, loudness_db, voiced = audio["times"], audio["loudness_db"], audio["voiced"]

        left, right = st.columns([3, 1])
        with right:
            st.markdown("**This trial**")
            st.metric("Mean loudness", f"{row['mean_loudness']:.1f} dB")
            st.metric("Vocal activity ratio", f"{row['vocal_activity_ratio']:.1%}")
            st.metric("Loudness variability", f"{row['loudness_variability']:.2f} dB")
            st.metric("Loudness trend", f"{row['loudness_trend']:+.2f} dB/s")
            st.audio(row["audio_path"])

        with left:
            fig4, ax4 = plt.subplots(figsize=(9, 3))
            ax4.plot(times, loudness_db, color="#8c8c8c", lw=0.8, label="loudness")
            ax4.plot(times[voiced], loudness_db[voiced], ".", color="#d62728",
                     markersize=4, label=f"voiced ({voiced.mean():.0%})")
            if voiced.sum() >= 2:
                slope, intercept = np.polyfit(times[voiced], loudness_db[voiced], 1)
                ax4.plot(times, slope * times + intercept, "--", color="black", lw=1.2,
                         label=f"trend {slope:+.2f} dB/s")
            ax4.set(xlabel="time (s)", ylabel="loudness (dBFS)",
                    title="Frame loudness — voiced frames drive the voice features")
            ax4.legend(loc="upper right", fontsize=8)
            st.pyplot(fig4)

    # ----- Mouth -----
    st.markdown("---")
    st.markdown("### Mouth (video)")
    if not has_path(row, "video_path"):
        st.warning("No video file for this trial.")
    else:
        video = compute_video_signal(row["video_path"])
        opening, fps = video["opening"], video["fps"]
        frame_t = np.arange(len(opening)) / fps
        valid = ~np.isnan(opening)

        left, right = st.columns([3, 1])
        with right:
            st.markdown("**This trial**")
            st.metric("Mean opening", f"{row['mean_mouth_opening']:.3f}")
            st.metric("Opening rate", f"{row['mouth_opening_rate']:.2f} /s")
            st.metric("Opening variability", f"{row['opening_variability']:.3f}")
            st.metric("Opening trend", f"{row['opening_trend']:+.4f} /s")
            st.metric("Face detected", f"{row['face_detection_ratio']:.1%}")

        with left:
            fig5, ax5 = plt.subplots(figsize=(9, 3))
            ax5.plot(frame_t[valid], opening[valid], color="#1f77b4", lw=1.0, label="mouth opening")
            # Peaks = open events, mirroring extract_video_features.opening_rate.
            if valid.sum() >= 2:
                vals = opening[valid]
                prominence = max(0.5 * float(np.std(vals)), 1e-6)
                distance = max(int(MIN_CYCLE_TIME_S * fps), 1)
                peaks, _ = find_peaks(vals, distance=distance, prominence=prominence)
                ax5.plot(frame_t[valid][peaks], vals[peaks], "x", color="red",
                         markersize=8, label=f"{len(peaks)} open events")
                slope, intercept = np.polyfit(frame_t[valid], vals, 1)
                ax5.plot(frame_t[valid], slope * frame_t[valid] + intercept, "--",
                         color="black", lw=1.2, label=f"trend {slope:+.4f}/s")
            ax5.set(xlabel="time (s)", ylabel="mouth opening (norm.)",
                    title="Mouth opening per frame — peaks drive the 'BA' rate")
            ax5.legend(loc="upper right", fontsize=8)
            st.pyplot(fig5)
