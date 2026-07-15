# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM --platform=linux/amd64 python:3.14-slim AS runtime
ARG COMMIT_SHA=unknown
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 PATH=/app/.venv/bin:$PATH COMMIT_SHA=$COMMIT_SHA
COPY --from=uv /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgles2 libglib2.0-0 libgl1 libgomp1 libsndfile1 ffmpeg && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api ./api
COPY alembic ./alembic
COPY alembic.ini ./
COPY extract_step_features.py extract_audio_features.py extract_video_features.py ./
COPY models/face_landmarker.task ./models/face_landmarker.task
RUN chown -R app:app /app
USER app
RUN python -c 'from extract_video_features import _make_landmarker; landmarker = _make_landmarker(); landmarker.close()'
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers 1"]
