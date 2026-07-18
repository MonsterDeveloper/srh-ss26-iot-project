from __future__ import annotations

import asyncio
import csv
import io
import shutil
import tempfile
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .auth import AuthContext, require_bearer, require_dashboard
from .config import get_settings
from .dashboard import conditions, metadata, quality_codes, quality_issue
from .database import get_db
from .media import DerivativeError, create_mp4
from .models import AuditEvent, Exercise, Experiment, Recording, RecordingStatus
from .pipeline import process_recording
from .schemas import (
    ErrorResponse,
    ExerciseInput,
    ExercisePatch,
    ExercisePage,
    ExerciseResponse,
    ExperimentInput,
    ExperimentPage,
    ExperimentResponse,
    RecordingDataResponse,
    MediaLinkResponse,
    UploadResponse,
)
from .storage import ObjectStorage

settings = get_settings()
storage = ObjectStorage(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    conditions(settings)
    await run_in_threadpool(storage.ensure_bucket_cors, settings.cors_allowed_origins)
    yield


app = FastAPI(title="Experiment API (Parkinson's Gait)", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_allowed_origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
extraction_slots = asyncio.Semaphore(settings.extraction_concurrency)
recording_start_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _recording_status(exercise: Exercise) -> str:
    return exercise.recording.status.value if exercise.recording else RecordingStatus.IDLE.value


def _experiment_out(item: Experiment) -> dict:
    exercises = item.exercises if "exercises" in item.__dict__ else []
    status_counts: dict[str, int] = {}
    issue_count = 0
    for exercise in exercises:
        status = _recording_status(exercise)
        status_counts[status] = status_counts.get(status, 0) + 1
        issue_count += len(quality_codes(exercise, settings))
    return {"id": item.id, "patientNumber": item.patient_number, "height": item.height, "age": item.age, "weight": item.weight, "properties": item.properties, "createdAt": item.created_at, "archivedAt": item.archived_at, "archivedBy": item.archived_by, "exerciseCount": len(exercises), "qualityIssueCount": issue_count, "statusCounts": status_counts}


def _exercise_out(item: Exercise) -> dict:
    recording = item.recording
    return {"id": item.id, "experimentId": item.experiment_id, "recordingStatus": _recording_status(item), "recordingStartedAt": recording.started_at if recording else None, "recordingEndedAt": recording.ended_at if recording else None, "hasData": bool(recording and recording.features), "properties": item.properties, "createdAt": item.created_at, "condition": item.condition, "repetition": item.repetition, "archivedAt": item.archived_at, "archivedBy": item.archived_by, "qualityIssueCount": len(quality_codes(item, settings))}


def _audit(db: Session, context: AuthContext, action: str, target_type: str, target_id: str, *, experiment_id: str | None = None, exercise_id: str | None = None, changed_fields: list[str] | None = None) -> None:
    db.add(AuditEvent(actor=context.actor, action=action, target_type=target_type, target_id=target_id, experiment_id=experiment_id, exercise_id=exercise_id, changed_fields=sorted(set(changed_fields or [])), request_id=context.request_id))


def _ensure_mutable(item: Experiment | Exercise) -> None:
    if item.archived_at is not None:
        raise HTTPException(409, f"Archived {item.__class__.__name__.lower()} must be restored before mutation")


def _exercise_metadata(body: ExerciseInput | ExercisePatch, *, current_properties: dict | None = None, dashboard: bool = False) -> tuple[dict, str | None, int | None]:
    properties = dict(body.properties if body.properties is not None else (current_properties or {}))
    submitted_properties = body.properties if "properties" in body.model_fields_set and body.properties is not None else {}
    property_condition = submitted_properties.get("condition")
    property_repetition = submitted_properties.get("repetition")
    top_condition = body.condition if "condition" in body.model_fields_set else None
    top_repetition = body.repetition if "repetition" in body.model_fields_set else None
    if top_condition is not None and property_condition is not None and top_condition != property_condition:
        raise HTTPException(422, "Conflicting top-level and properties condition values")
    if top_repetition is not None and property_repetition is not None and top_repetition != property_repetition:
        raise HTTPException(422, "Conflicting top-level and properties repetition values")
    fallback_condition = properties.get("condition")
    fallback_repetition = properties.get("repetition")
    condition_value = top_condition if top_condition is not None else (property_condition if property_condition is not None else fallback_condition)
    repetition_value = top_repetition if top_repetition is not None else (property_repetition if property_repetition is not None else fallback_repetition)
    condition = condition_value if isinstance(condition_value, str) and condition_value else None
    repetition = repetition_value if isinstance(repetition_value, int) and not isinstance(repetition_value, bool) and repetition_value > 0 else None
    if dashboard and condition not in {item.id for item in conditions(settings) if item.active}:
        raise HTTPException(422, "Dashboard writes require an active configured condition")
    if condition is not None:
        properties["condition"] = condition
    if repetition is not None:
        properties["repetition"] = repetition
    return properties, condition, repetition


def _commit_integrity(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, message) from exc


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
    if recording is None or (not recording.features and not recording.errors):
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


@app.post("/experiments", status_code=201, response_model=ExperimentResponse, responses={401: {"model": ErrorResponse}})
def create_experiment(body: ExperimentInput, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    item = Experiment(patient_number=body.patientNumber, height=body.height, age=body.age, weight=body.weight, properties=body.properties)
    db.add(item); db.flush()
    _audit(db, context, "create", "experiment", item.id, experiment_id=item.id, changed_fields=list(body.model_fields_set))
    db.commit(); db.refresh(item)
    return _experiment_out(item)


@app.get("/experiments", response_model=ExperimentPage, responses={401: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def list_experiments(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Experiment)) or 0
    items = db.scalars(select(Experiment).order_by(Experiment.created_at.desc()).offset((page - 1) * pageSize).limit(pageSize)).all()
    return {"items": [_experiment_out(item) for item in items], "page": page, "pageSize": pageSize, "total": total}


@app.get("/experiments/{experiment_id}", response_model=ExperimentResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def get_experiment(experiment_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(Experiment, experiment_id)
    if item is None:
        raise HTTPException(404, "Experiment not found")
    return _experiment_out(item)


@app.patch("/experiments/{experiment_id}", response_model=ExperimentResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def update_experiment(experiment_id: str, body: ExperimentInput, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    item = db.get(Experiment, experiment_id)
    if item is None:
        raise HTTPException(404, "Experiment not found")
    _ensure_mutable(item)
    for api_name, model_name in {"patientNumber": "patient_number", "height": "height", "age": "age", "weight": "weight", "properties": "properties"}.items():
        if api_name in body.model_fields_set:
            setattr(item, model_name, getattr(body, api_name))
    _audit(db, context, "edit", "experiment", item.id, experiment_id=item.id, changed_fields=list(body.model_fields_set))
    db.commit(); db.refresh(item)
    return _experiment_out(item)


def _delete_recordings_or_503(records: list[Recording]) -> None:
    for recording in records:
        try:
            storage.delete_manifest(recording.object_manifest)
            storage.delete_artifacts(recording.artifacts)
        except RuntimeError as exc:
            raise HTTPException(503, "Recording storage is unavailable; deletion was not performed") from exc


@app.delete("/experiments/{experiment_id}", status_code=204, dependencies=[Depends(require_bearer)])
def delete_experiment(experiment_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> None:
    item = db.scalar(select(Experiment).where(Experiment.id == experiment_id).options(selectinload(Experiment.exercises).selectinload(Exercise.recording)))
    if item is None:
        raise HTTPException(404, "Experiment not found")
    _delete_recordings_or_503([exercise.recording for exercise in item.exercises if exercise.recording])
    _audit(db, context, "permanent_delete", "experiment", item.id, experiment_id=item.id)
    db.delete(item); db.commit()


@app.post("/experiments/{experiment_id}/exercises", status_code=201, response_model=ExerciseResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
def create_exercise(experiment_id: str, body: ExerciseInput, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    _ensure_mutable(experiment)
    properties, condition, repetition = _exercise_metadata(body, dashboard=context.dashboard)
    item = Exercise(experiment_id=experiment_id, properties=properties, condition=condition, repetition=repetition)
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "An active exercise already uses this condition and repetition") from exc
    _audit(db, context, "create", "exercise", item.id, experiment_id=experiment_id, exercise_id=item.id, changed_fields=list(body.model_fields_set))
    _commit_integrity(db, "An active exercise already uses this condition and repetition")
    db.refresh(item)
    return _exercise_out(item)


@app.get("/experiments/{experiment_id}/exercises", response_model=list[ExerciseResponse], responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def list_experiment_exercises(experiment_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Experiment, experiment_id) is None:
        raise HTTPException(404, "Experiment not found")
    items = db.scalars(select(Exercise).where(Exercise.experiment_id == experiment_id).options(selectinload(Exercise.recording)).order_by(Exercise.created_at.desc())).all()
    return [_exercise_out(item) for item in items]


@app.get("/exercises", response_model=ExercisePage, responses={401: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def list_exercises(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Exercise)) or 0
    items = db.scalars(select(Exercise).options(selectinload(Exercise.recording)).order_by(Exercise.created_at.desc()).offset((page - 1) * pageSize).limit(pageSize)).all()
    return {"items": [_exercise_out(item) for item in items], "page": page, "pageSize": pageSize, "total": total}


@app.get("/exercises/{exercise_id}", response_model=ExerciseResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def get_exercise(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    return _exercise_out(_get_exercise(db, exercise_id))


@app.delete("/exercises/{exercise_id}", status_code=204, dependencies=[Depends(require_bearer)])
def delete_exercise(exercise_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> None:
    item = _get_exercise(db, exercise_id)
    if item.recording:
        _delete_recordings_or_503([item.recording])
    _audit(db, context, "permanent_delete", "exercise", item.id, experiment_id=item.experiment_id, exercise_id=item.id)
    db.delete(item); db.commit()


@app.patch("/exercises/{exercise_id}", response_model=ExerciseResponse, dependencies=[Depends(require_bearer)])
def update_exercise(exercise_id: str, body: ExercisePatch, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    item = _get_exercise(db, exercise_id)
    _ensure_mutable(item)
    properties, condition, repetition = _exercise_metadata(body, current_properties=item.properties, dashboard=context.dashboard)
    if "properties" in body.model_fields_set:
        item.properties = properties
    else:
        updated = dict(item.properties)
        if "condition" in body.model_fields_set:
            updated["condition"] = condition
        if "repetition" in body.model_fields_set:
            updated["repetition"] = repetition
        item.properties = updated
    if "condition" in body.model_fields_set or "properties" in body.model_fields_set:
        item.condition = condition
    if "repetition" in body.model_fields_set or "properties" in body.model_fields_set:
        item.repetition = repetition
    _audit(db, context, "edit", "exercise", item.id, experiment_id=item.experiment_id, exercise_id=item.id, changed_fields=list(body.model_fields_set))
    _commit_integrity(db, "An active exercise already uses this condition and repetition")
    db.refresh(item)
    return _exercise_out(item)


def _archive_experiment(experiment_id: str, restore: bool, db: Session, context: AuthContext) -> dict:
    item = db.get(Experiment, experiment_id)
    if item is None:
        raise HTTPException(404, "Experiment not found")
    if restore:
        item.archived_at = None; item.archived_by = None
    else:
        if item.archived_at is not None:
            return _experiment_out(item)
        item.archived_at = _now(); item.archived_by = context.actor
    _audit(db, context, "restore" if restore else "archive", "experiment", item.id, experiment_id=item.id, changed_fields=["archivedAt", "archivedBy"])
    db.commit(); db.refresh(item)
    return _experiment_out(item)


@app.post("/experiments/{experiment_id}/archive", response_model=ExperimentResponse, dependencies=[Depends(require_bearer)])
def archive_experiment(experiment_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    return _archive_experiment(experiment_id, False, db, context)


@app.post("/experiments/{experiment_id}/restore", response_model=ExperimentResponse, dependencies=[Depends(require_bearer)])
def restore_experiment(experiment_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    return _archive_experiment(experiment_id, True, db, context)


def _archive_exercise(exercise_id: str, restore: bool, db: Session, context: AuthContext) -> dict:
    item = _get_exercise(db, exercise_id)
    if restore:
        item.archived_at = None; item.archived_by = None
    else:
        if item.archived_at is not None:
            return _exercise_out(item)
        item.archived_at = _now(); item.archived_by = context.actor
    _audit(db, context, "restore" if restore else "archive", "exercise", item.id, experiment_id=item.experiment_id, exercise_id=item.id, changed_fields=["archivedAt", "archivedBy"])
    _commit_integrity(db, "Restore conflicts with an active exercise using this condition and repetition")
    db.refresh(item)
    return _exercise_out(item)


@app.post("/exercises/{exercise_id}/archive", response_model=ExerciseResponse, dependencies=[Depends(require_bearer)])
def archive_exercise(exercise_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    return _archive_exercise(exercise_id, False, db, context)


@app.post("/exercises/{exercise_id}/restore", response_model=ExerciseResponse, dependencies=[Depends(require_bearer)])
def restore_exercise(exercise_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    return _archive_exercise(exercise_id, True, db, context)


def _urls(recording: Recording) -> dict:
    return {"recordingId": str(recording.id), "status": recording.status.value, "uploads": storage.presigned_put_urls(recording.object_manifest)}


@app.post("/exercises/{exercise_id}/recording/start", response_model=UploadResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def start_recording(exercise_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    with recording_start_lock:
        exercise = _get_exercise(db, exercise_id, with_experiment=True)
        _ensure_mutable(exercise)
        _ensure_mutable(exercise.experiment)
        if exercise.recording:
            raise HTTPException(409, "A recording already exists for this exercise")
        recording = Recording(exercise_id=exercise.id, status=RecordingStatus.RECORDING, started_at=_now())
        db.add(recording)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "A recording already exists for this exercise") from exc
        recording.object_manifest = storage.manifest(exercise.experiment_id, exercise.id, str(recording.id))
        _audit(db, context, "start_recording", "recording", str(recording.id), experiment_id=exercise.experiment_id, exercise_id=exercise.id, changed_fields=["status", "objectManifest", "startedAt"])
        db.commit(); db.refresh(recording)
    return _urls(recording)


@app.post("/exercises/{exercise_id}/recording/uploads/refresh", response_model=UploadResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def refresh_uploads(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    exercise = _get_exercise(db, exercise_id)
    _ensure_mutable(exercise)
    recording = exercise.recording
    if recording is None or recording.status is not RecordingStatus.RECORDING:
        raise HTTPException(409, "Recording is not accepting uploads")
    return _urls(recording)


async def _extract(recording: Recording) -> tuple[dict, dict, dict, dict]:
    temp_dir = tempfile.mkdtemp(prefix="srh-recording-")
    try:
        paths = await run_in_threadpool(storage.download_all, recording.object_manifest, Path(temp_dir))
        result = await run_in_threadpool(process_recording, paths, settings.route_distance_m, True)
        features, errors = result[:2]
        traces = result[2] if len(result) > 2 else {}
        artifacts: dict = {}
        try:
            target = Path(temp_dir) / "video.mp4"
            method = await run_in_threadpool(create_mp4, Path(paths["video"]), target)
            key = str(Path(recording.object_manifest["video"]["key"]).with_name("video.mp4"))
            artifact = await run_in_threadpool(storage.upload_artifact, key, target, "video/mp4")
            artifact["method"] = method
            artifacts["video_playback"] = artifact
        except (DerivativeError, RuntimeError, ValueError):
            pass
        return features, errors, traces, artifacts
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def _process(exercise: Exercise, db: Session, allowed_statuses: set[RecordingStatus], context: AuthContext) -> dict:
    recording = exercise.recording
    assert recording
    try:
        await run_in_threadpool(storage.head_all, recording.object_manifest)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    claimed = db.execute(
        update(Recording)
        .where(Recording.id == recording.id, Recording.status.in_(allowed_statuses))
        .values(status=RecordingStatus.PROCESSING)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Recording state changed before processing could start")
    db.commit()
    db.refresh(recording)
    try:
        async with extraction_slots:
            features, errors, traces, artifacts = await _extract(recording)
    except Exception:
        features, errors, traces, artifacts = {}, {"recording": "Recording objects could not be processed"}, {}, {}
    recording.features, recording.errors, recording.traces, recording.artifacts, recording.ended_at = features, errors, traces, artifacts, _now()
    recording.status = RecordingStatus.COMPLETED if len(features) == 3 else (RecordingStatus.COMPLETED_WITH_ERRORS if features else RecordingStatus.FAILED)
    _audit(db, context, "retry_processing" if RecordingStatus.RECORDING not in allowed_statuses else "stop_recording", "recording", str(recording.id), experiment_id=exercise.experiment_id, exercise_id=exercise.id, changed_fields=["status", "features", "errors", "traces", "artifacts"])
    db.commit(); db.refresh(recording)
    response = _data_out(exercise)
    if recording.status is RecordingStatus.FAILED:
        raise HTTPException(422, detail=response)
    return response


@app.post("/exercises/{exercise_id}/recording/stop", response_model=RecordingDataResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
async def stop_recording(exercise_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    exercise = _get_exercise(db, exercise_id)
    _ensure_mutable(exercise)
    if not exercise.recording or exercise.recording.status is not RecordingStatus.RECORDING:
        raise HTTPException(409, "Recording is not ready to stop")
    return await _process(exercise, db, {RecordingStatus.RECORDING}, context)


@app.post("/exercises/{exercise_id}/recording/retry", response_model=RecordingDataResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
async def retry_recording(exercise_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> dict:
    exercise = _get_exercise(db, exercise_id)
    _ensure_mutable(exercise)
    retryable = {RecordingStatus.FAILED, RecordingStatus.COMPLETED_WITH_ERRORS, RecordingStatus.UPLOADED}
    if not exercise.recording or exercise.recording.status not in retryable:
        raise HTTPException(409, "Recording cannot be retried in its current state")
    return await _process(exercise, db, retryable, context)


@app.get("/exercises/{exercise_id}/data", response_model=RecordingDataResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}, dependencies=[Depends(require_bearer)])
def get_data(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    return _data_out(_get_exercise(db, exercise_id))


@app.get("/exercises/{exercise_id}/traces", dependencies=[Depends(require_dashboard)])
def get_traces(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    recording = _get_exercise(db, exercise_id).recording
    if recording is None or not recording.traces:
        raise HTTPException(404, "No diagnostic traces recorded for this exercise")
    return recording.traces


MEDIA_ASSETS = {
    "motion": ("source", "motion", "motion.csv"),
    "audio": ("source", "audio", "audio.wav"),
    "video_source": ("source", "video", "video.h264"),
    "video_playback": ("artifact", "video_playback", "video.mp4"),
}


@app.get("/exercises/{exercise_id}/media/{asset}/url", response_model=MediaLinkResponse, dependencies=[Depends(require_dashboard)])
def get_media_url(exercise_id: str, asset: str, db: Session = Depends(get_db)) -> dict:
    if asset not in MEDIA_ASSETS:
        raise HTTPException(404, "Media asset not found")
    recording = _get_exercise(db, exercise_id).recording
    if recording is None:
        raise HTTPException(404, "Media asset not found")
    kind, name, filename = MEDIA_ASSETS[asset]
    collection = recording.object_manifest if kind == "source" else recording.artifacts
    item = collection.get(name)
    if not isinstance(item, dict) or not item.get("key"):
        raise HTTPException(404, "Media asset not found")
    try:
        return storage.media_link(item, filename)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/exercises/{exercise_id}/data", status_code=204, dependencies=[Depends(require_bearer)])
def delete_data(exercise_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(require_bearer)) -> None:
    exercise = _get_exercise(db, exercise_id)
    _ensure_mutable(exercise)
    if not exercise.recording or not exercise.recording.features:
        raise HTTPException(404, "No derived data recorded for this exercise")
    try:
        storage.delete_artifacts(exercise.recording.artifacts)
    except RuntimeError as exc:
        raise HTTPException(503, "Recording storage is unavailable; derived data was not cleared") from exc
    exercise.recording.features = {}
    exercise.recording.errors = {}
    exercise.recording.traces = {}
    exercise.recording.artifacts = {}
    exercise.recording.status = RecordingStatus.UPLOADED
    _audit(db, context, "clear_derived_data", "recording", str(exercise.recording.id), experiment_id=exercise.experiment_id, exercise_id=exercise.id, changed_fields=["features", "errors", "traces", "artifacts", "status"])
    db.commit()


@app.get("/experiments/{experiment_id}/export", dependencies=[Depends(require_bearer)])
def export_experiment(experiment_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    experiment = db.scalar(select(Experiment).where(Experiment.id == experiment_id).options(selectinload(Experiment.exercises).selectinload(Exercise.recording)))
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
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


def _audit_out(item: AuditEvent) -> dict:
    return {"id": str(item.id), "actor": item.actor, "action": item.action, "targetType": item.target_type, "targetId": item.target_id, "experimentId": item.experiment_id, "exerciseId": item.exercise_id, "changedFields": item.changed_fields, "createdAt": item.created_at}


@app.get("/audit-events", dependencies=[Depends(require_dashboard)])
def list_audit_events(experimentId: str | None = None, exerciseId: str | None = None, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    query = select(AuditEvent)
    if experimentId:
        query = query.where(AuditEvent.experiment_id == experimentId)
    if exerciseId:
        query = query.where(AuditEvent.exercise_id == exerciseId)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(AuditEvent.created_at.desc()).offset((page - 1) * pageSize).limit(pageSize)).all()
    return {"items": [_audit_out(item) for item in items], "page": page, "pageSize": pageSize, "total": total}


@app.get("/dashboard/metadata", dependencies=[Depends(require_dashboard)])
def dashboard_metadata() -> dict:
    return metadata(settings)


def _parse_boundary(value: str | None, *, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "Invalid date filter") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if end and len(value) == 10:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _exercise_query():
    return select(Exercise).options(selectinload(Exercise.recording), selectinload(Exercise.experiment))


@app.get("/dashboard/experiments", dependencies=[Depends(require_dashboard)])
def dashboard_experiments(
    patientNumber: str | None = None, createdFrom: str | None = None, createdTo: str | None = None,
    recordingStatus: RecordingStatus | None = None, condition: str | None = None,
    archive: str = Query("active", pattern="^(active|archived|all)$"), page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
) -> dict:
    query = select(Experiment).options(selectinload(Experiment.exercises).selectinload(Exercise.recording))
    if patientNumber:
        query = query.where(Experiment.patient_number.ilike(f"%{patientNumber}%"))
    if start := _parse_boundary(createdFrom):
        query = query.where(Experiment.created_at >= start)
    if end := _parse_boundary(createdTo, end=True):
        query = query.where(Experiment.created_at <= end)
    if archive == "active": query = query.where(Experiment.archived_at.is_(None))
    elif archive == "archived": query = query.where(Experiment.archived_at.is_not(None))
    if condition or recordingStatus:
        query = query.join(Experiment.exercises)
        if condition: query = query.where(Exercise.condition == condition)
        if recordingStatus:
            query = query.join(Exercise.recording).where(Recording.status == recordingStatus)
        query = query.distinct()
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    items = db.scalars(query.order_by(Experiment.created_at.desc()).offset((page - 1) * pageSize).limit(pageSize)).unique().all()
    return {"items": [_experiment_out(item) for item in items], "page": page, "pageSize": pageSize, "total": total}


def _observation(item: Exercise) -> dict:
    recording = item.recording
    raw_features = recording.features if recording else {}
    clean_features: dict[str, dict] = {}
    for modality in ("motion", "audio", "video"):
        source = raw_features.get(modality, {})
        clean_features[modality] = {key: value for key, value in source.items() if value is None or isinstance(value, (int, float)) and not isinstance(value, bool)}
    return {"experimentId": item.experiment_id, "patientNumber": item.experiment.patient_number, "experimentCreatedAt": item.experiment.created_at, "age": item.experiment.age, "height": item.experiment.height, "weight": item.experiment.weight, "exerciseId": item.id, "condition": item.condition, "repetition": item.repetition, "status": recording.status.value if recording else "idle", "archivedAt": item.archived_at, "features": clean_features, "extractionErrors": recording.errors if recording else {}, "qualityIssueCodes": quality_codes(item, settings)}


@app.get("/dashboard/analysis", dependencies=[Depends(require_dashboard)])
def dashboard_analysis(
    condition: list[str] = Query(default=[]), patientNumber: str | None = None, createdFrom: str | None = None, createdTo: str | None = None,
    recordingStatus: RecordingStatus | None = None, qualityOnly: bool = False, feature: list[str] = Query(default=[]),
    page: int = Query(1, ge=1), pageSize: int = Query(1000, ge=1, le=1000), db: Session = Depends(get_db),
) -> dict:
    query = _exercise_query().where(Exercise.archived_at.is_(None), Exercise.experiment.has(Experiment.archived_at.is_(None)))
    if condition: query = query.where(Exercise.condition.in_(condition))
    if patientNumber: query = query.where(Exercise.experiment.has(Experiment.patient_number.ilike(f"%{patientNumber}%")))
    if start := _parse_boundary(createdFrom): query = query.where(Exercise.created_at >= start)
    if end := _parse_boundary(createdTo, end=True): query = query.where(Exercise.created_at <= end)
    if recordingStatus: query = query.where(Exercise.recording.has(Recording.status == recordingStatus))
    all_items = db.scalars(query.order_by(Exercise.created_at.desc())).all()
    observations = [_observation(item) for item in all_items]
    if qualityOnly: observations = [item for item in observations if item["qualityIssueCodes"]]
    if feature:
        allowed = set(feature)
        for observation in observations:
            observation["features"] = {modality: {key: value for key, value in values.items() if key in allowed} for modality, values in observation["features"].items()}
    total = len(observations); start_index = (page - 1) * pageSize
    return {"items": observations[start_index:start_index + pageSize], "page": page, "pageSize": pageSize, "total": total}


@app.get("/dashboard/quality", dependencies=[Depends(require_dashboard)])
def dashboard_quality(
    severity: str | None = None, issue: str | None = None, modality: str | None = None, condition: str | None = None,
    recordingStatus: RecordingStatus | None = None, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
) -> dict:
    exercises = db.scalars(_exercise_query().where(Exercise.archived_at.is_(None), Exercise.experiment.has(Experiment.archived_at.is_(None))).order_by(Exercise.created_at.desc())).all()
    issues = [quality_issue(code, exercise) for exercise in exercises for code in quality_codes(exercise, settings)]
    if severity: issues = [item for item in issues if item["severity"] == severity]
    if issue: issues = [item for item in issues if item["code"] == issue]
    if modality: issues = [item for item in issues if item["modality"] == modality]
    if condition: issues = [item for item in issues if item["condition"] == condition]
    if recordingStatus: issues = [item for item in issues if item["status"] == recordingStatus.value]
    total = len(issues); start_index = (page - 1) * pageSize
    return {"items": issues[start_index:start_index + pageSize], "page": page, "pageSize": pageSize, "total": total}


@app.get("/dashboard/overview", dependencies=[Depends(require_dashboard)])
def dashboard_overview(db: Session = Depends(get_db)) -> dict:
    experiments = db.scalars(select(Experiment).where(Experiment.archived_at.is_(None)).options(selectinload(Experiment.exercises).selectinload(Exercise.recording)).order_by(Experiment.created_at.desc())).all()
    exercises = [exercise for experiment in experiments for exercise in experiment.exercises if exercise.archived_at is None]
    recordings = [exercise.recording for exercise in exercises if exercise.recording]
    status_counts: dict[str, int] = {}
    for recording in recordings: status_counts[recording.status.value] = status_counts.get(recording.status.value, 0) + 1
    audits = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(10)).all()
    return {"activeExperimentCount": len(experiments), "exerciseCount": len(exercises), "completedRecordingCount": sum(recording.status in {RecordingStatus.COMPLETED, RecordingStatus.COMPLETED_WITH_ERRORS} for recording in recordings), "totalRecordingCount": len(recordings), "activeWorkCount": sum(recording.status in {RecordingStatus.RECORDING, RecordingStatus.PROCESSING} for recording in recordings), "qualityIssueCount": sum(len(quality_codes(exercise, settings)) for exercise in exercises), "statusCounts": status_counts, "recentExperiments": [_experiment_out(item) for item in experiments[:10]], "recentAuditEvents": [_audit_out(item) for item in audits]}
