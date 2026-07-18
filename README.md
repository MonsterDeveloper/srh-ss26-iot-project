# IoT & AI — Parkinson Movement/Voice Study

Tracking 3 parameters in Parkinson patients from a custom Raspberry Pi Zero rig
with 3 sensors. The patient wears the setup, walks ~10 m while making wide hand
movements and repeating the "BA" sound. **Hypothesis:** wide body movements
improve patient stability and voice.

## Table of Contents

- [Overview](#iot--ai--parkinson-movementvoice-study)
- [Project structure](#project-structure)
- [Architecture](#architecture)
- [API](#api)
- [Local development](#local-development)
- [Testing](#testing)
- [Production deployment](#production-deployment)
- [IMU feature extraction pipeline](#imu-feature-extraction-pipeline-accelerometer--gyroscope)

| Sensor | Placement | Output | Features |
|---|---|---|---|
| Microphone | near the face | `.wav` | mean loudness, vocal activity ratio, loudness variability, loudness trend |
| Accelerometer | leg, close to foot | `.csv` | step count, cadence, gait regularity, activity ratio |
| Gyroscope | leg, close to foot | `.csv` (same file) | mean rotation, rotation variability |
| Camera | face | `.h264` | mean mouth opening, opening rate, opening variability, opening trend |

Tech stack: Python + [uv](https://docs.astral.sh/uv/), librosa, opencv + mediapipe,
pandas, numpy, matplotlib. `dashboards/sample_data_exploration.py` is a Streamlit
dashboard for raw-data inspection only (no feature extraction).

The service layer uses FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, and
RustFS/S3. The production dashboard is a server-rendered React Router 8 BFF
built with TypeScript, React 19, Bun, Tailwind CSS, Base UI, and Zod.

## Project Structure

- `api/` — FastAPI routes, auth, persistence, S3 access, and processing orchestration.
- `extract_*_features.py` — reusable motion, audio, and video extractors.
- `alembic/` — PostgreSQL schema migrations.
- `dashboards/` — local Streamlit inspection and feature-exploration tools.
- `web-dashboard/` — the React Router BFF and production research dashboard.
- `collected_sample_data/` — nine reference sensor triplets used by sample tests.
- `tests/` — API contract, integration, harness, and real-media tests.
- `models/` — bundled MediaPipe model assets.
- `docker-compose.dev.yml` — local PostgreSQL and RustFS services.
- `config/`, `.kamal/`, and `.github/workflows/` — deployment and CI automation.

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

The dashboard uses a distinct service bearer token. Only that token can trust
`X-Dashboard-Actor`, access reporting, or request signed downloads; capture-token
requests are always audited as `api-client`. Archiving retains sources, traces,
derivatives, and immutable audit history.

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

Processing stores bounded diagnostic traces and creates a browser-compatible
`video.mp4` derivative while preserving the original H.264. Dashboard endpoints
serve metadata, overview metrics, filtered observations, quality issues, audit
history, traces, and short-lived signed media links.

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

Experiment measurements are validated as human ranges: height must be greater
than 0 and at most 300 cm, age must be between 0 and 130 years, and weight must
be greater than 0 and at most 500 kg. Unknown request fields are rejected so
client spelling mistakes cannot be silently discarded.

Motion includes `walking_speed_cms` and `step_length_cm`, calculated using the
fixed 14 m route. NaN and infinity values are converted to JSON `null`; errors
are sanitized and do not expose stack traces or server paths.

## Local development

Install Python 3.14 and [uv](https://docs.astral.sh/uv/). Set the required
environment variables, then run:

```bash
uv sync
docker compose -f docker-compose.dev.yml up -d
uv run alembic upgrade head
uv run uvicorn api.server:app --reload
uv run --group dashboard streamlit run dashboards/features_extraction.py
```

Run the production dashboard separately:

```bash
cd web-dashboard
bun install --frozen-lockfile
bun dev
```

Dashboard setup, environment variables, and validation commands are documented
in [`web-dashboard/README.md`](web-dashboard/README.md).

Required API settings:

| Setting | Purpose |
|---|---|
| `API_BEARER_TOKEN` | Bearer token for business routes |
| `DASHBOARD_API_BEARER_TOKEN` | Separate bearer token for the dashboard BFF |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection (the URL is assembled safely in code) |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_REGION` | RustFS S3 credentials and bucket |
| `S3_PUBLIC_ENDPOINT`, `S3_INTERNAL_ENDPOINT` | Browser-facing and API-internal RustFS endpoints |
| `CORS_ALLOWED_ORIGINS` | Comma-separated explicit browser-origin allowlist |
| `ROUTE_DISTANCE_M` | Route distance; defaults to `14` |
| `PRESIGNED_URL_TTL_SECONDS` | Upload URL lifetime; defaults to `900` |
| `PRESIGNED_GET_URL_TTL_SECONDS` | Signed download lifetime; defaults to `60` |
| `EXTRACTION_CONCURRENCY` | Process-wide extraction limit; defaults to `1` |
| `EXERCISE_CONDITIONS_JSON` | Optional validated bilingual condition definitions |
| `QUALITY_IMU_CLIP_FRACTION` | IMU clipping warning threshold; defaults to `0.10` |
| `QUALITY_FACE_DETECTION_RATIO` | Face coverage warning threshold; defaults to `0.80` |
| `QUALITY_STALE_MINUTES` | Active-state stale threshold; defaults to `30` |

Backfill existing recordings without replacing valid summary features:

```bash
uv run backfill-derivatives --dry-run
uv run backfill-derivatives --limit 25
uv run backfill-derivatives --recording-id 00000000-0000-0000-0000-000000000000
```

The default object limits are 10 MiB for motion, 64 MiB for audio, and 256 MiB
for video. RustFS bucket CORS permits PUT requests only from the same explicit
API CORS allowlist. Do not use wildcard origins or expose the bucket publicly.

## Testing

The API test suite runs without Docker or Testcontainers. It starts a local
[PGlite](https://pglite.dev/) PostgreSQL-compatible instance in TCP mode,
migrates it through Alembic, and uses [Moto](https://docs.getmoto.org/) as the
in-process S3 substitute. FastAPI requests use `TestClient`; no developer
database, RustFS service, or production environment variables are used.

Install Python 3.14, Node/npm (required by PGlite), and uv, then run:

```bash
uv sync --group test
uv run --group test pytest -q tests/test_harness.py
uv run --group test pytest -ra --tb=short -m "not sample" \
  --cov=api --cov-branch --cov-report=term-missing
uv run --group test pytest -ra --tb=short -m sample
```

The harness test is the infrastructure gate: it verifies Node/npm discovery,
PGlite startup, the Alembic head revision and schema, Moto bucket/CORS setup,
and FastAPI lifespan behavior. The sample-marked test catalogs the nine
read-only motion/audio/video triplets under `collected_sample_data/` and sends
each through the complete recording API flow. CI runs the same harness and full
suite in [`.github/workflows/test-pr.yml`](.github/workflows/test-pr.yml). Pull-request
CI also builds the AMD64 production image and initializes MediaPipe's face
landmarker inside it as the non-root application user. This image-level gate
covers the native runtime libraries and bundled landmarker model that host-level
tests cannot validate.

Tests deliberately assert the intended API contract. A red contract test is
not skipped, xfailed, or weakened merely because the current implementation
does not satisfy it. The SQLAlchemy enum binding uses the lowercase values
defined by the PostgreSQL `recording_status` type, keeping recording creation
and the recording/export flows aligned with the migration.

## Production deployment

Production runs two independent Kamal 2 applications on one AMD64 Linux server.
GitHub Actions validates both codebases, deploys the API first, and deploys the
dashboard only after the API deployment succeeds. The dashboard uses a normal
`kamal deploy`; that command also ensures Kamal Proxy is running, so its first
deployment does not require `kamal setup`.

| Application | Kamal working directory | Configuration | Image | Public host |
|---|---|---|---|---|
| API | repository root | [`config/deploy.yml`](config/deploy.yml) | `ghcr.io/monsterdeveloper/srh-ss26-iot-project` | `srh-iot-api.ctoofeverything.dev` |
| Dashboard | `web-dashboard` | [`web-dashboard/config/deploy.yml`](web-dashboard/config/deploy.yml) | `ghcr.io/monsterdeveloper/srh-iot-dashboard` | `srh-iot-dashboard.ctoofeverything.dev` |

The API image runs as a non-root user, applies Alembic migrations before
starting one Uvicorn worker, and exposes port 8000. Kamal Proxy terminates TLS,
routes readiness checks to `/health/ready`, and retains two previous API
containers. The dashboard production image runs as the non-root `node` user on
port 3000, is checked at `/health`, and also retains two previous containers.

The API configuration defines two private accessories:

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
uses the GitHub `production` environment:

- Every push to `main` first runs the complete API test suite and the dashboard
  format, lint, type generation, typecheck, and production-build checks.
- The API job runs from the repository root. A normal deployment uses
  `kamal deploy -v`.
- A manual dispatch with `bootstrap=true` prepares the host directories,
  verifies the certificate directory, and runs `kamal setup -v` for the API and
  its accessories.
- After the API job succeeds, the dashboard job runs `kamal deploy -v` from
  `web-dashboard`. An API test, migration, bootstrap, or deployment failure
  prevents the dashboard deployment.
- Ruby 3.4, exactly Kamal 2.12.0, strict SSH host verification, and Docker
  Buildx are configured in both deployment jobs. Cancellation handlers release
  the lock for the service whose working directory the job uses.

Configure this complete secret inventory in the GitHub `production`
environment:

| Secret | Used by |
|---|---|
| `DEPLOY_SSH_PRIVATE_KEY` | API and dashboard SSH agent |
| `DEPLOY_SSH_KNOWN_HOSTS` | Strict host-key verification for both deployments |
| `POSTGRES_PASSWORD` | API and PostgreSQL accessory |
| `RUSTFS_ACCESS_KEY` | API and RustFS accessory |
| `RUSTFS_SECRET_KEY` | API and RustFS accessory |
| `API_BEARER_TOKEN` | Capture/API clients; must be at least 32 characters |
| `DASHBOARD_API_BEARER_TOKEN` | Shared by the API and dashboard; must be at least 32 characters and differ from `API_BEARER_TOKEN` |
| `DASHBOARD_SESSION_SECRET` | Dashboard session signing; must be at least 32 characters |
| `DASHBOARD_USERS_JSON` | Exactly three dashboard login accounts |

`CORS_ALLOWED_ORIGINS` is the sole required configurable GitHub variable. The
production API, dashboard, and media hostnames are explicit in the Kamal
configurations. `API_HOST` and `S3_HOST` are not used. GHCR authentication uses
the workflow's automatic `GITHUB_TOKEN`; it does not need to be added manually.

### First dashboard deployment handoff

1. Add `DASHBOARD_API_BEARER_TOKEN`, `DASHBOARD_SESSION_SECRET`, and
   `DASHBOARD_USERS_JSON` to the GitHub `production` environment.
2. Generate the dashboard API token with at least 32 characters, preferably
   with `openssl rand -hex 32`.
3. Generate the dashboard session secret independently with
   `openssl rand -hex 32`.
4. Generate three Argon2 password hashes locally:

   ```bash
   cd web-dashboard
   bun auth:hash
   ```

5. Store `DASHBOARD_USERS_JSON` as raw, one-line JSON containing exactly three
   unique users. Each object must have `username`, `displayName`, and
   `passwordHash`. Usernames must be lowercase, 3–32 characters, start with a
   letter, and otherwise contain only lowercase letters, digits, `_`, or `-`.
6. Confirm `DASHBOARD_API_BEARER_TOKEN` is the same GitHub secret consumed by
   both deployment jobs and differs from `API_BEARER_TOKEN`.
7. Preserve the existing SSH, PostgreSQL, RustFS, and API bearer secrets.
8. Keep `CORS_ALLOWED_ORIGINS`. After this workflow change is merged, remove
   the unused `API_HOST` and `S3_HOST` GitHub variables.
9. Confirm dashboard DNS points to `161.35.211.185` and that ports 80 and 443
   are reachable before merging to `main`.
10. Merge to `main`. The workflow validates both applications, deploys the API,
    and then performs the dashboard's first deployment.

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
