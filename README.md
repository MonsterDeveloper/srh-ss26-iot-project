# IoT & AI — Parkinson Movement/Voice Study

Tracking 3 parameters in Parkinson patients from a custom Raspberry Pi Zero rig
with 3 sensors. The patient wears the setup, walks ~10 m while making wide hand
movements and repeating the "BA" sound. **Hypothesis:** wide body movements
improve patient stability and voice.

| Sensor | Placement | Output | Features |
|---|---|---|---|
| Microphone | near the face | `.wav` | mean loudness, vocal activity ratio, loudness variability, loudness trend |
| Accelerometer | leg, close to foot | `.csv` | step count, cadence, gait regularity, activity ratio |
| Gyroscope | leg, close to foot | `.csv` (same file) | mean rotation, rotation variability |
| Camera | face | `.h264` | mean mouth opening, opening rate, opening variability, opening trend |

Tech stack: Python + [uv](https://docs.astral.sh/uv/), librosa, opencv + mediapipe,
pandas, numpy, matplotlib. `sample_data_exploration.py` is a Streamlit dashboard
for raw-data inspection only (no feature extraction).

---

## IMU feature extraction pipeline (accelerometer + gyroscope)

This section documents how we extract the four motion features — **step count,
cadence, gait regularity, activity ratio** — from the IMU `.csv` files, the
findings from our sample data that drove the design, and *why* we made each
choice. It is the reference for implementing `motion_features.py`.

### Data findings (from `collected_sample_data/`, 9 trials)

Measured across all 9 `motion_*.csv` files (3 categories × 3 trials:
`1_normal_walk`, `2_faster_walk`, `3_long_steps`):

- **Columns:** `time, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z`.
  `time` is float seconds; the 6 sensor channels are raw `int16` counts.
- **No missing values, no duplicate rows.**
- **Sampling rate ≈ 9.3 Hz** (median `dt` ≈ 107 ms, range 105–114 ms). Recordings
  are ~9–20 s long, i.e. only ~85–184 samples each.
- **Sampling is nearly-but-not-perfectly uniform** — `dt` wobbles by a few ms.
- **int16 saturation / clipping** at `|value| = 32767`. It scales with movement
  speed: worst in `2_faster_walk`, where gyro axes clip on **20–40% of samples**
  and `accel_x` on ~20 samples; mild (a handful of samples) in the slower trials.
  Gyro is almost certainly configured at ±250 °/s and the leg swings faster than
  that during the swing phase.
- **Signal quality:** both `accel_mag = √(ax²+ay²+az²)` and
  `gyro_mag = √(gx²+gy²+gz²)` are clearly periodic at the step rate. The **gyro
  magnitude is the cleaner, more sharply periodic signal** — leg angular velocity
  has a strong, well-separated mid-swing peak.

### The two constraints that shape every algorithm choice

**1. Low sampling rate: ~9.3 Hz → Nyquist 4.65 Hz.**
Adequate for what we need (walking step frequency is ~1–2 Hz, well below Nyquist),
but:
- Timing resolution is ±107 ms per sample. A step is ~500 ms, so individual
  step-to-step timing is quantized to ~±20%.
- Only ~5 samples per step — fine impact-shape features are impossible;
  periodicity features are fine.
- **Consequence:** prefer **frequency-domain / autocorrelation** methods over
  measuring individual peak-to-peak intervals.

**2. Clipping is not negligible** (up to ~20–40% of samples in fast trials).
Amplitude is corrupted during the fastest swings; timing/periodicity survive
better.
- **Consequence:** prefer **periodicity-based** methods over amplitude-threshold
  methods; use **adaptive** thresholds (MAD-based), never fixed heights; and
  report a per-trial `clip_fraction` as a quality flag.
- *Future capture fix:* raise the IMU full-scale range (esp. gyro) so the leg
  swing stops railing.

### Stage A — Preprocessing (shared by all 4 features)

1. Load, sort by `time`, drop duplicate timestamps.
2. **Flag clipping:** mark `|value| >= 32767`; compute per-trial `clip_fraction`.
   Linear-interpolate short (1–2 sample) clipped runs; keep the flag for
   reporting. *Why:* we can't recover railed amplitude, but we can stop it from
   poisoning thresholds, and a reviewer needs to know the confidence.
3. **Resample to a uniform 10 Hz grid** (linear interpolation on `time`).
   *Why:* `dt` wobbles 105–114 ms and both filtering and FFT assume uniform
   spacing.
4. **Magnitude signals** `a_mag`, `g_mag`. *Why:* orientation-invariant — we
   don't need to know the exact sensor mounting angle on the leg.
5. **Band-pass 0.5–3 Hz** (Butterworth, `scipy.signal.filtfilt`, zero-phase).
   *Why:* removes the gravity DC offset and drift (<0.5 Hz) and out-of-band
   noise; 0.5–3 Hz brackets human walking step frequency. Zero-phase filtering
   avoids shifting peak timing.

### Stage B — The four features

Primary periodicity signal is the **band-passed gyro magnitude** (cleaner);
accel magnitude is the cross-check.

**Step count**
- `scipy.signal.find_peaks` on the band-passed gyro magnitude, with
  `distance` = min stride time (~0.3 s → ~3 samples) and an **adaptive
  prominence** (e.g. k · MAD of the signal), *not* a fixed height.
- *Why adaptive:* clipping and speed changes break any fixed height threshold.
- **One-leg convention (confirmed):** the sensor is on **one leg near the foot**,
  so each detected peak ≈ one gait cycle of that leg = one **stride**. Total
  steps ≈ **2 × detected peaks**. This is stated explicitly and validated against
  video.

**Cadence**
- Two independent estimates, both reported:
  - (a) time-domain: `n_steps / duration × 60` (steps/min);
  - (b) frequency-domain: **dominant frequency** from a Welch PSD of the
    band-passed signal, × 60.
- *Why both:* agreement between them is the confidence signal; the spectral
  estimate is robust to the ±107 ms timing jitter and to a few missed/extra
  peaks.

**Gait regularity**
- Primary: **unbiased autocorrelation** of the band-passed signal
  (Moe-Nilssen & Helbostad method). Height of the first dominant peak = step
  regularity; second peak = stride regularity (0–1, higher = more regular).
- Secondary: **coefficient of variation** of inter-step intervals from the
  detected peaks (`std/mean`, lower = more regular).
- *Why this split:* autocorrelation is the estimate to trust at 9.3 Hz;
  interval-CV is interpretable and clinically standard for Parkinson's gait
  variability but noisy with only ~10–20 steps/trial — report it with that
  caveat.

**Activity ratio**
- Sliding window (~1 s) over the **high-passed (>0.5 Hz)** accel magnitude; per
  window compute energy/std; threshold vs a rest baseline →
  `active_windows / total_windows`.
- Set the threshold from a still segment, or use Otsu on the window-energy
  distribution so it isn't a magic number.
- *Why:* captures pauses/turns within the 10 m walk rather than assuming
  continuous motion.

### Stage C — Validation (external to `extract_step_features.py`)

`extract_step_features(path) -> dict` is a pure per-trial function (one file
in, one feature dict out, no printing) so it can be reused as a library call
or behind an API. Cross-trial validation is a separate, offline step — run it
over a batch of results, not inside the extraction function.

- **Ranking check:** across the 3 categories, cadence should rank
  `faster_walk > normal > long_steps`; **per-step amplitude** (mean band-passed
  accel magnitude at each detected stride — returned as `step_amplitude`)
  should rank the reverse. If the numbers don't rank this way, the pipeline is
  wrong.
- **Confirmed on our 9 sample trials:** spectral cadence and `step_amplitude`
  both ranked exactly as hypothesized. **Time-domain cadence did not** — it
  ranked `long_steps` highest instead of lowest. This is the low-sample-count
  timing noise called out earlier (only ~11–18 strides/trial), not a broken
  pipeline: trust the spectral/amplitude cross-check over time-domain cadence
  when they disagree.

### Quality flags reported with every trial

- `clip_fraction` — share of saturated samples (confidence in amplitude).
- effective `fs` — measured sampling rate (confidence in timing).
