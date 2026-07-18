# IoT & AI Parkinson Study

This project tests whether wide body movements improve stability and voice in
people with Parkinson's disease. A Raspberry Pi Zero rig records:

- `motion.csv`: accelerometer and gyroscope near the foot
- `audio.wav`: microphone near the face
- `video.h264`: face camera

See `README.md` for architecture, setup, API flows, and deployment details.

## Project-specific guidance

- FastAPI in `api/` is the system of record. PostgreSQL stores experiment and
  derived data; private source media and derivatives live in RustFS/S3.
- The reusable extractors are `extract_step_features.py`,
  `extract_audio_features.py`, and `extract_video_features.py`.
- `dashboards/` contains local Streamlit inspection tools. The production
  dashboard is the separate `web-dashboard/` application.
- Read `web-dashboard/CLAUDE.md` before changing anything in `web-dashboard/`.
- Add an Alembic migration for database schema changes.
- API read/export routes return stored results; they must not run extraction.
- Clearing derived data keeps source objects for retry. Deleting an exercise or
  experiment also deletes its stored objects.
- Tests marked `sample` process the real media in `collected_sample_data/`.

Run Python tools through uv. The usual checks are:

```bash
uv run --group test pytest -ra --tb=short -m "not sample" \
  --cov=api --cov-branch --cov-report=term-missing
uv run --group test pytest -ra --tb=short -m sample
```
