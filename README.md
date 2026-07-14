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
pandas, numpy, matplotlib. `dashboards/sample_data_exploration.py` is a Streamlit
dashboard for raw-data inspection only (no feature extraction).

## Architecture

The FastAPI application in `api/` is the system of record for experiments and
derived features. PostgreSQL stores metadata and JSONB results; RustFS stores
the original private media objects. The root extraction modules remain shared
with the Streamlit dashboards and are imported directly by the API.

```text
Raspberry Pi / browser
        │  1. start → presigned PUT URLs
        ▼
 FastAPI ────────────────► PostgreSQL
    │                         experiments, exercises, recordings,
    │                         manifests, features, errors
    │  2. direct PUT
    ▼
 RustFS (private bucket) ──► temporary worker files ──► root extractors
        motion.csv / audio.wav / video.h264                │
                                                          ▼
                                                canonical JSONB features
```

Each exercise has at most one recording. A recording owns its status, RustFS
object manifest, feature JSON, and extractor-error JSON. Deleting derived data
keeps the source objects so extraction can be retried; deleting an exercise or
experiment removes its RustFS objects before its database row is deleted.

## API

Interactive OpenAPI documentation is available at `/docs`. All business routes
require `Authorization: Bearer <API_BEARER_TOKEN>`; only `/`, `/docs`,
`/openapi.json`, `/health/live`, and `/health/ready` are public.

The primary recording flow is:

1. Create an experiment and an exercise.
2. `POST /exercises/{id}/recording/start` creates the manifest and returns
   three 15-minute presigned PUT URLs.
3. Upload `motion.csv`, `audio.wav`, and `video.h264` directly to RustFS with
   the returned content types.
4. `POST /exercises/{id}/recording/stop` verifies object size/type, downloads
   temporary copies, and runs extraction once outside FastAPI's event loop.
5. `GET /exercises/{id}/data` and `GET /experiments/{id}/export` read the
   stored result only; they never re-run extraction.

`/recording/uploads/refresh` refreshes expired PUT URLs without moving the
objects. `/recording/retry` uses retained source objects for failed or cleared
results. A successful recording is `completed`, a partial result is
`completed_with_errors`, and an all-stream failure is `failed`. Invalid state
transitions return HTTP 409.

The canonical data response contains only stored derived data:

```json
{
  "exerciseId": "…",
  "recordingId": "…",
  "status": "completed",
  "features": { "motion": {}, "audio": {}, "video": {} },
  "errors": {}
}
```

Motion includes `walking_speed_cms` and `step_length_cm`, calculated using the
fixed 14 m route. NaN and infinity values are converted to JSON `null`; errors
are sanitized and do not expose stack traces or server paths.

## Local development

Install Python 3.14 and [uv](https://docs.astral.sh/uv/). Set the required
environment variables, then run:

```bash
uv sync
docker compose -f compose.dev.yml up -d
uv run alembic upgrade head
uv run uvicorn api.server:app --reload
uv run --group dashboard streamlit run dashboards/features_extraction.py
```

Required API settings:

| Setting | Purpose |
|---|---|
| `API_BEARER_TOKEN` | Bearer token for business routes |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection (the URL is assembled safely in code) |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_REGION` | RustFS S3 credentials and bucket |
| `S3_PUBLIC_ENDPOINT`, `S3_INTERNAL_ENDPOINT` | Browser-facing and API-internal RustFS endpoints |
| `CORS_ALLOWED_ORIGINS` | Comma-separated explicit browser-origin allowlist |
| `ROUTE_DISTANCE_M` | Route distance; defaults to `14` |
| `PRESIGNED_URL_TTL_SECONDS` | Upload URL lifetime; defaults to `900` |
| `EXTRACTION_CONCURRENCY` | Process-wide extraction limit; defaults to `1` |

The default object limits are 10 MiB for motion, 64 MiB for audio, and 256 MiB
for video. RustFS bucket CORS permits PUT requests only from the same explicit
API CORS allowlist. Do not use wildcard origins or expose the bucket publicly.

## Production deployment

Production is a single AMD64 Linux server deployed exclusively through GitHub
Actions and Kamal 2. The image runs as a non-root user, applies Alembic
migrations before starting one Uvicorn worker, and exposes port 8000. Kamal
Proxy automatically obtains and terminates TLS for
`srh-iot-api.ctoofeverything.dev`, routes readiness checks to `/health/ready`,
and retains two previous application containers for zero-downtime overlap.

[`config/deploy.yml`](config/deploy.yml) defines the application plus two
private accessories:

| Service | Image | Persistent host path | Notes |
|---|---|---|---|
| PostgreSQL | `postgres:17-alpine` | `/srv/srh-iot/postgres` | Private port 5432; alias `srh-iot-postgres` |
| RustFS | `rustfs/rustfs:1.0.0-beta.8` | `/srv/srh-iot/rustfs` | Native TLS, port 9000 only, console disabled |

RustFS is served publicly at `https://srh-iot-media.ctoofeverything.dev`.
Cloudflare forwards that HTTPS hostname to RustFS on origin port 9000; the API
uses the private Docker-network endpoint on port 9000. Its certificate files
are mounted from `/srv/srh-iot/rustfs-tls` as
`rustfs_cert.pem` and `rustfs_key.pem`; Certbot renewals copy fresh files to
that directory and restart the RustFS container. Keep the media DNS record
**proxied** in Cloudflare and configure its Origin Rule to use destination port
9000. The API host may remain proxied.

The workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)
uses the GitHub `production` environment and has one deployment job only:

- Pushes to `main` run `kamal deploy -v`.
- A manual dispatch with `bootstrap=true` prepares the host directories,
  verifies the certificate directory, then runs `kamal setup -v`.
- Ruby 3.4, exactly Kamal 2.12.0, strict SSH host verification, and Docker
  Buildx are configured in the job.

Configure these GitHub secrets: `DEPLOY_SSH_PRIVATE_KEY`,
`DEPLOY_SSH_KNOWN_HOSTS`, `POSTGRES_PASSWORD`, `RUSTFS_ACCESS_KEY`,
`RUSTFS_SECRET_KEY`, and `API_BEARER_TOKEN`. Configure these repository
variables: `API_HOST`, `S3_HOST`, and `CORS_ALLOWED_ORIGINS`. GHCR
authentication uses the workflow `GITHUB_TOKEN`.

The RustFS TLS certificate directory, DNS, firewall ports (80, 443, 9000), and
backups are infrastructure responsibilities outside this repository.

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
