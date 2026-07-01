"""Streamlit dashboard for exploring extracted IMU trial features.

Runs the feature-extraction pipeline from extract_step_features.py over every
motion_*.csv trial in collected_sample_data/ once at server start (no
preprocessing/filtering here — extract_step_features.py owns that) and presents
a full explorer:

  * Overview & quality  — KPIs, per-trial table, data-quality panel.
  * Condition comparison — the hypothesis view: are wider-movement conditions
    more stable? Grouped bars with per-trial points + a radar "fingerprint".
  * Feature relationships — interactive scatter + correlation heatmap.
  * Trial deep-dive — re-runs preprocessing to connect each number back to the
    raw signal (stride peaks, Welch PSD, autocorrelation).

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
from scipy.signal import welch

sys.path.append(str(Path(__file__).parent.parent))

from extract_step_features import (
    BAND_HIGH,
    BAND_LOW,
    TARGET_FS,
    detect_strides,
    extract_step_features,
    preprocess,
    unbiased_autocorrelation,
)

DATA_ROOT = Path(__file__).parent.parent / "collected_sample_data"

# label, unit, group, higher_is_better (None = neutral/descriptive), desc
FEATURE_META = {
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
    "step_count": ("Step count", "steps", "Counts / quality", None, "Detected steps (2 x strides)."),
    "n_strides": ("Stride count", "strides", "Counts / quality", None, "Detected gyro-magnitude peaks."),
    "duration_s": ("Duration", "s", "Counts / quality", None, "Trial length after resampling."),
    "effective_fs": ("Effective fs", "Hz", "Counts / quality", None, "Median raw sampling rate."),
    "clip_fraction": ("Clip fraction", "0–1", "Counts / quality", False,
                      "Fraction of samples hitting int16 saturation."),
    "n_samples": ("Samples", "n", "Counts / quality", None, "Rows after uniform resampling."),
}

GROUP_ORDER = ["Cadence", "Gait stability", "Movement magnitude", "Activity", "Counts / quality"]

st.set_page_config(page_title="IMU Feature Explorer", layout="wide")


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


def feature_label(col: str) -> str:
    return FEATURE_META[col][0] if col in FEATURE_META else col


def trial_label(df: pd.DataFrame) -> pd.Series:
    return df["category"] + " / " + df["timestamp"]


step_features_df = compute_step_features(str(DATA_ROOT))

st.title("IMU Feature Explorer")

if step_features_df.empty:
    st.error(f"No motion_*.csv trials found under {DATA_ROOT}")
    st.stop()

st.caption(
    f"Step / cadence / gait / rotation features for all {len(step_features_df)} "
    f"IMU trials under `{DATA_ROOT.name}/`, computed once at server start via "
    "`extract_step_features.py`. Comparative study: 3 walking conditions x 3 trials "
    "— individual trials are always shown, no significance is claimed on n=3."
)

feature_cols = [c for c in FEATURE_META if c in step_features_df.columns]
compare_defaults = [
    c for c in feature_cols
    if FEATURE_META[c][2] in ("Gait stability", "Cadence")
]

tab_overview, tab_compare, tab_relate, tab_trial = st.tabs(
    ["Overview & quality", "Condition comparison", "Feature relationships", "Trial deep-dive"]
)


# ---------- Tab 1: Overview & quality ----------
with tab_overview:
    st.subheader("At a glance")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Trials", len(step_features_df))
    k2.metric("Conditions", step_features_df["category"].nunique())
    k3.metric("Mean cadence", f"{step_features_df['cadence_spectral'].mean():.0f} spm")
    k4.metric("Mean stride reg.", f"{step_features_df['stride_regularity'].mean():.2f}")
    k5.metric("Total walk time", f"{step_features_df['duration_s'].sum():.0f} s")

    st.markdown("**Per-trial features**")
    display_df = step_features_df.drop(columns=["motion_path"]).copy()
    display_df.index = trial_label(step_features_df)
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
        step_features_df.groupby("category")[feature_cols].mean().style.format(precision=3),
        width="stretch",
    )

    st.markdown("---")
    st.subheader("Data quality")
    qc_df = step_features_df.assign(trial=trial_label(step_features_df))
    for col in ["clip_fraction", "effective_fs", "duration_s"]:
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

    high_clip = step_features_df[step_features_df["clip_fraction"] > 0.1]
    if not high_clip.empty:
        st.warning(
            f"{len(high_clip)} trial(s) have >10% clipped IMU samples — amplitude-based "
            "features (step_amplitude, mean_rotation, rotation_variability) may be less "
            "reliable for these: "
            + ", ".join(trial_label(high_clip).tolist())
        )


# ---------- Tab 2: Condition comparison ----------
with tab_compare:
    st.subheader("Does wider movement change gait? (condition comparison)")
    st.caption(
        "Bars are per-condition means; dots are the 3 individual trials. With n=3 "
        "per condition, read the dots — a difference in means only matters if the "
        "trials don't overlap."
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
        long_df = step_features_df.melt(
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
            "regularity higher is better, for stride interval CV / clip fraction "
            "lower is better."
        )
        radar_feats = selected if len(selected) >= 3 else feature_cols[:6]
        means = step_features_df.groupby("category")[radar_feats].mean()
        norm = means.copy()
        for c in radar_feats:
            lo, hi = step_features_df[c].min(), step_features_df[c].max()
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
    default_y = "stride_regularity" if "stride_regularity" in feature_cols else feature_cols[-1]
    c1, c2 = st.columns(2)
    x_feat = c1.selectbox("X axis", feature_cols, index=feature_cols.index(default_x),
                          format_func=feature_label)
    y_feat = c2.selectbox("Y axis", feature_cols, index=feature_cols.index(default_y),
                          format_func=feature_label)

    scatter = (
        alt.Chart(step_features_df.assign(trial=trial_label(step_features_df)))
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
        "Default axes (step amplitude vs stride regularity) probe the core "
        "hypothesis: does a bigger per-step swing come with a more regular gait?"
    )

    st.markdown("---")
    st.markdown("**Correlation heatmap** (Pearson, across all 9 trials)")
    corr_feats = [c for c in feature_cols if FEATURE_META[c][2] != "Counts / quality"
                  or c in ("step_count", "activity_ratio")]
    corr = step_features_df[corr_feats].corr()
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
        .properties(height=420)
    )
    text = heat.mark_text(fontSize=9).encode(
        text=alt.Text("corr:Q", format=".2f"),
        color=alt.condition("abs(datum.corr) > 0.6", alt.value("white"), alt.value("black")),
    )
    st.altair_chart(heat + text, use_container_width=True)
    st.caption("Only 9 trials — treat correlations as exploratory, not conclusive.")


# ---------- Tab 4: Trial deep-dive ----------
with tab_trial:
    st.subheader("From signal to feature")
    c1, c2 = st.columns(2)
    category = c1.selectbox("Condition", sorted(step_features_df["category"].unique()))
    subset = step_features_df[step_features_df["category"] == category]
    timestamp = c2.selectbox("Trial", subset["timestamp"].tolist())
    row = subset[subset["timestamp"] == timestamp].iloc[0]

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
        from scipy.signal import find_peaks

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
