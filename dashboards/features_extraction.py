"""Streamlit dashboard for extracted trial features.

Runs the feature-extraction pipeline from extract_step_features.py over every
motion_*.csv trial in collected_sample_data/ once at server start (no
preprocessing/filtering here — extract_step_features.py owns that) and
presents the results per section, one sensor/feature-group at a time.

Run with: uv run streamlit run dashboards/features_extraction.py
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from extract_step_features import extract_step_features

DATA_ROOT = Path(__file__).parent.parent / "collected_sample_data"

st.set_page_config(page_title="Features Extraction", layout="wide")


@st.cache_data(show_spinner="Extracting step features from all trials...")
def compute_step_features(root: str) -> pd.DataFrame:
    root_path = Path(root)
    rows = []
    for category_dir in sorted(p for p in root_path.iterdir() if p.is_dir()):
        for motion_path in sorted(category_dir.glob("motion_*.csv")):
            timestamp = motion_path.stem.split("_", 1)[1]
            features = extract_step_features(motion_path)
            rows.append({"category": category_dir.name, "timestamp": timestamp, **features})
    return pd.DataFrame(rows)


step_features_df = compute_step_features(str(DATA_ROOT))

st.title("Features Extraction")

st.header("Step features")

if step_features_df.empty:
    st.error(f"No motion_*.csv trials found under {DATA_ROOT}")
    st.stop()

st.caption(
    f"IMU-derived step/cadence/gait/rotation features for all {len(step_features_df)} "
    f"trials under `{DATA_ROOT.name}/`, computed once at server start via "
    "`extract_step_features.py`."
)

st.markdown("**Per-trial features**")
st.dataframe(step_features_df, width="stretch")

st.markdown("**Mean by category**")
feature_cols = [c for c in step_features_df.columns if c not in ("category", "timestamp")]
st.dataframe(step_features_df.groupby("category")[feature_cols].mean(), width="stretch")

st.markdown("**Cadence by trial**")
label = step_features_df["category"] + " / " + step_features_df["timestamp"]
cadence_df = step_features_df[["cadence_time_domain", "cadence_spectral"]].set_index(label)
st.bar_chart(cadence_df)

high_clip = step_features_df[step_features_df["clip_fraction"] > 0.1]
if not high_clip.empty:
    st.warning(
        f"{len(high_clip)} trial(s) have >10% clipped IMU samples — amplitude-based "
        "features (e.g. step_amplitude) may be less reliable for these."
    )
