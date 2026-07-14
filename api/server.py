from __future__ import annotations

import asyncio
import csv
import io
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .auth import require_bearer
from .config import get_settings
from .database import get_db
from .models import Exercise, Experiment, Recording, RecordingStatus
from .pipeline import process_recording
from .schemas import ExerciseInput, ExperimentInput
from .storage import ObjectStorage

settings = get_settings()
storage = ObjectStorage(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(storage.ensure_bucket_cors, settings.cors_allowed_origins)
    yield


app = FastAPI(title="Experiment API (Parkinson's Gait)", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_allowed_origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
extraction_slots = asyncio.Semaphore(settings.extraction_concurrency)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _recording_status(exercise: Exercise) -> str:
    return exercise.recording.status.value if exercise.recording else RecordingStatus.IDLE.value


def _experiment_out(item: Experiment) -> dict:
    return {"id": item.id, "patientNumber": item.patient_number, "height": item.height, "age": item.age, "weight": item.weight, "properties": item.properties, "createdAt": item.created_at}


def _exercise_out(item: Exercise) -> dict:
    recording = item.recording
    return {"id": item.id, "experimentId": item.experiment_id, "recordingStatus": _recording_status(item), "recordingStartedAt": recording.started_at if recording else None, "recordingEndedAt": recording.ended_at if recording else None, "hasData": bool(recording and recording.features), "properties": item.properties, "createdAt": item.created_at}


def _get_exercise(db: Session, exercise_id: str, *, with_experiment: bool = False) -> Exercise:
    opts = [selectinload(Exercise.recording)]
    if with_experiment:
        opts.append(selectinload(Exercise.experiment))
    exercise = db.scalar(select(Exercise).where(Exercise.id == exercise_id).options(*opts))
    if exercise is None:
        raise HTTPException(404, "Exercise not found")
    return exercise


def _data_out(exercise: Exercise) -> dict:
    recording = exercise.recording
    if recording is None or not recording.features:
        raise HTTPException(404, "No derived data recorded for this exercise")
    return {"exerciseId": exercise.id, "recordingId": str(recording.id), "status": recording.status.value, "features": recording.features, "errors": recording.errors}


def _flatten(value: dict, prefix: str = "") -> dict:
    output = {}
    for key, item in value.items():
        name = f"{prefix}{key}"
        if isinstance(item, dict):
            output.update(_flatten(item, f"{name}."))
        elif not isinstance(item, list):
            output[name] = item
    return output


@app.get("/health/live", include_in_schema=False)
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def ready(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ready"}


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "Experiment API", "docs": "/docs"}


@app.post("/experiments", status_code=201, dependencies=[Depends(require_bearer)])
def create_experiment(body: ExperimentInput, db: Session = Depends(get_db)) -> dict:
    item = Experiment(patient_number=body.patientNumber, height=body.height, age=body.age, weight=body.weight, properties=body.properties)
    db.add(item); db.commit(); db.refresh(item)
    return _experiment_out(item)


@app.get("/experiments", dependencies=[Depends(require_bearer)])
def list_experiments(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Experiment)) or 0
    items = db.scalars(select(Experiment).order_by(Experiment.created_at.desc()).offset((page - 1) * pageSize).limit(pageSize)).all()
    return {"items": [_experiment_out(item) for item in items], "page": page, "pageSize": pageSize, "total": total}


@app.get("/experiments/{experiment_id}", dependencies=[Depends(require_bearer)])
def get_experiment(experiment_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(Experiment, experiment_id)
    if item is None: raise HTTPException(404, "Experiment not found")
    return _experiment_out(item)


@app.patch("/experiments/{experiment_id}", dependencies=[Depends(require_bearer)])
def update_experiment(experiment_id: str, body: ExperimentInput, db: Session = Depends(get_db)) -> dict:
    item = db.get(Experiment, experiment_id)
    if item is None: raise HTTPException(404, "Experiment not found")
    for api_name, model_name in {"patientNumber": "patient_number", "height": "height", "age": "age", "weight": "weight", "properties": "properties"}.items():
        if api_name in body.model_fields_set: setattr(item, model_name, getattr(body, api_name))
    db.commit(); db.refresh(item)
    return _experiment_out(item)


def _delete_recordings_or_503(records: list[Recording]) -> None:
    for recording in records:
        try:
            storage.delete_manifest(recording.object_manifest)
        except RuntimeError as exc:
            raise HTTPException(503, "Recording storage is unavailable; deletion was not performed") from exc


@app.delete("/experiments/{experiment_id}", status_code=204, dependencies=[Depends(require_bearer)])
def delete_experiment(experiment_id: str, db: Session = Depends(get_db)) -> None:
    item = db.scalar(select(Experiment).where(Experiment.id == experiment_id).options(selectinload(Experiment.exercises).selectinload(Exercise.recording)))
    if item is None: raise HTTPException(404, "Experiment not found")
    _delete_recordings_or_503([exercise.recording for exercise in item.exercises if exercise.recording])
    db.delete(item); db.commit()


@app.post("/experiments/{experiment_id}/exercises", status_code=201, dependencies=[Depends(require_bearer)])
def create_exercise(experiment_id: str, body: ExerciseInput, db: Session = Depends(get_db)) -> dict:
    if db.get(Experiment, experiment_id) is None: raise HTTPException(404, "Experiment not found")
    item = Exercise(experiment_id=experiment_id, properties=body.properties)
    db.add(item); db.commit(); db.refresh(item)
    return _exercise_out(item)


@app.get("/experiments/{experiment_id}/exercises", dependencies=[Depends(require_bearer)])
def list_experiment_exercises(experiment_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Experiment, experiment_id) is None: raise HTTPException(404, "Experiment not found")
    items = db.scalars(select(Exercise).where(Exercise.experiment_id == experiment_id).options(selectinload(Exercise.recording)).order_by(Exercise.created_at.desc())).all()
    return [_exercise_out(item) for item in items]


@app.get("/exercises", dependencies=[Depends(require_bearer)])
def list_exercises(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Exercise)) or 0
    items = db.scalars(select(Exercise).options(selectinload(Exercise.recording)).order_by(Exercise.created_at.desc()).offset((page - 1) * pageSize).limit(pageSize)).all()
    return {"items": [_exercise_out(item) for item in items], "page": page, "pageSize": pageSize, "total": total}


@app.get("/exercises/{exercise_id}", dependencies=[Depends(require_bearer)])
def get_exercise(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    return _exercise_out(_get_exercise(db, exercise_id))


@app.delete("/exercises/{exercise_id}", status_code=204, dependencies=[Depends(require_bearer)])
def delete_exercise(exercise_id: str, db: Session = Depends(get_db)) -> None:
    item = _get_exercise(db, exercise_id)
    if item.recording: _delete_recordings_or_503([item.recording])
    db.delete(item); db.commit()


def _urls(recording: Recording) -> dict:
    return {"recordingId": str(recording.id), "status": recording.status.value, "uploads": storage.presigned_put_urls(recording.object_manifest)}


@app.post("/exercises/{exercise_id}/recording/start", dependencies=[Depends(require_bearer)])
def start_recording(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    exercise = _get_exercise(db, exercise_id, with_experiment=True)
    if exercise.recording:
        raise HTTPException(409, "A recording already exists for this exercise")
    recording = Recording(exercise_id=exercise.id, status=RecordingStatus.RECORDING, started_at=_now())
    db.add(recording); db.flush()
    recording.object_manifest = storage.manifest(exercise.experiment_id, exercise.id, str(recording.id))
    db.commit(); db.refresh(recording)
    return _urls(recording)


@app.post("/exercises/{exercise_id}/recording/uploads/refresh", dependencies=[Depends(require_bearer)])
def refresh_uploads(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    recording = _get_exercise(db, exercise_id).recording
    if recording is None or recording.status is not RecordingStatus.RECORDING: raise HTTPException(409, "Recording is not accepting uploads")
    return _urls(recording)


async def _extract(recording: Recording) -> tuple[dict, dict]:
    temp_dir = tempfile.mkdtemp(prefix="srh-recording-")
    try:
        paths = await run_in_threadpool(storage.download_all, recording.object_manifest, Path(temp_dir))
        return await run_in_threadpool(process_recording, paths, settings.route_distance_m)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def _process(exercise: Exercise, db: Session) -> dict:
    recording = exercise.recording
    assert recording
    try:
        await run_in_threadpool(storage.head_all, recording.object_manifest)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    recording.status = RecordingStatus.PROCESSING; db.commit()
    try:
        async with extraction_slots:
            features, errors = await _extract(recording)
    except Exception:
        features, errors = {}, {"recording": "Recording objects could not be processed"}
    recording.features, recording.errors, recording.ended_at = features, errors, _now()
    recording.status = RecordingStatus.COMPLETED if len(features) == 3 else (RecordingStatus.COMPLETED_WITH_ERRORS if features else RecordingStatus.FAILED)
    db.commit(); db.refresh(recording)
    response = _data_out(exercise)
    if recording.status is RecordingStatus.FAILED: raise HTTPException(422, detail=response)
    return response


@app.post("/exercises/{exercise_id}/recording/stop", dependencies=[Depends(require_bearer)])
async def stop_recording(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    exercise = _get_exercise(db, exercise_id)
    if not exercise.recording or exercise.recording.status is not RecordingStatus.RECORDING: raise HTTPException(409, "Recording is not ready to stop")
    return await _process(exercise, db)


@app.post("/exercises/{exercise_id}/recording/retry", dependencies=[Depends(require_bearer)])
async def retry_recording(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    exercise = _get_exercise(db, exercise_id)
    if not exercise.recording or exercise.recording.status not in {RecordingStatus.FAILED, RecordingStatus.COMPLETED_WITH_ERRORS, RecordingStatus.UPLOADED}: raise HTTPException(409, "Recording cannot be retried in its current state")
    return await _process(exercise, db)


@app.get("/exercises/{exercise_id}/data", dependencies=[Depends(require_bearer)])
def get_data(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    return _data_out(_get_exercise(db, exercise_id))


@app.delete("/exercises/{exercise_id}/data", status_code=204, dependencies=[Depends(require_bearer)])
def delete_data(exercise_id: str, db: Session = Depends(get_db)) -> None:
    exercise = _get_exercise(db, exercise_id)
    if not exercise.recording or not exercise.recording.features: raise HTTPException(404, "No derived data recorded for this exercise")
    exercise.recording.features = {}; exercise.recording.errors = {}; exercise.recording.status = RecordingStatus.UPLOADED
    db.commit()


@app.get("/experiments/{experiment_id}/export", dependencies=[Depends(require_bearer)])
def export_experiment(experiment_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    experiment = db.scalar(select(Experiment).where(Experiment.id == experiment_id).options(selectinload(Experiment.exercises).selectinload(Exercise.recording)))
    if experiment is None: raise HTTPException(404, "Experiment not found")
    rows, columns = [], []
    for exercise in experiment.exercises:
        props, recording = exercise.properties, exercise.recording
        row = {"exerciseId": exercise.id, "condition": props.get("condition", ""), "repetition": props.get("repetition", ""), "createdAt": exercise.created_at, "hasData": bool(recording and recording.features)}
        if recording:
            flat = _flatten(recording.features)
            columns.extend(key for key in flat if key not in columns); row.update(flat)
        rows.append(row)
    buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=["exerciseId", "condition", "repetition", "createdAt", "hasData", *columns], extrasaction="ignore", lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="experiment_{experiment_id}.csv"'})
