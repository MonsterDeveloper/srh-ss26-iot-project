from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .config import Settings
from .models import Exercise, RecordingStatus


class Translation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str = Field(min_length=1)
    de: str = Field(min_length=1)


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: Translation
    description: Translation | None = None
    active: bool = True
    order: int = Field(ge=0)
    baseline: bool = False


class Conditions(BaseModel):
    items: list[Condition]

    @model_validator(mode="after")
    def validate_set(self) -> "Conditions":
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("condition IDs must be unique")
        if len({item.order for item in self.items}) != len(self.items):
            raise ValueError("condition ordering must be unique")
        if sum(item.baseline for item in self.items) != 1:
            raise ValueError("exactly one condition must be the baseline")
        return self


DEFAULT_CONDITIONS = [
    {"id": "normal", "label": {"en": "Normal walk", "de": "Normales Gehen"}, "active": True, "order": 0, "baseline": True},
    {"id": "fast", "label": {"en": "Fast walk", "de": "Schnelles Gehen"}, "active": True, "order": 1, "baseline": False},
    {"id": "wide_step", "label": {"en": "Wide-step walk", "de": "Gehen mit weiten Schritten"}, "active": True, "order": 2, "baseline": False},
]


FEATURES = [
    ("step_regularity", "Step regularity", "Schrittregelmäßigkeit", "Consistency between successive steps", "Konsistenz aufeinanderfolgender Schritte", "motion", None, "higher", "decimal", True),
    ("stride_regularity", "Stride regularity", "Gangzyklusregelmäßigkeit", "Consistency between successive strides", "Konsistenz aufeinanderfolgender Gangzyklen", "motion", None, "higher", "decimal", True),
    ("step_amplitude", "Step amplitude", "Schrittamplitude", "Mean acceleration swing at stride peaks", "Mittlere Beschleunigung an Gangspitzen", "motion", "g", "neutral", "decimal", True),
    ("step_count", "Step count", "Schrittzahl", "Estimated number of steps", "Geschätzte Anzahl der Schritte", "motion", "steps", "neutral", "integer", False),
    ("cadence_time_domain", "Cadence", "Kadenz", "Estimated steps per minute", "Geschätzte Schritte pro Minute", "motion", "steps/min", "neutral", "decimal", False),
    ("activity_ratio", "Activity ratio", "Aktivitätsanteil", "Fraction of active motion windows", "Anteil aktiver Bewegungsfenster", "motion", "%", "higher", "percent", False),
    ("mean_rotation", "Mean rotation", "Mittlere Rotation", "Mean gyroscope magnitude", "Mittlere Gyroskop-Magnitude", "motion", "deg/s", "neutral", "decimal", False),
    ("rotation_variability", "Rotation variability", "Rotationsvariabilität", "Variability of gyroscope magnitude", "Variabilität der Gyroskop-Magnitude", "motion", "deg/s", "neutral", "decimal", False),
    ("mean_loudness", "Mean loudness", "Mittlere Lautstärke", "Mean loudness of voiced frames", "Mittlere Lautstärke stimmhafter Abschnitte", "audio", "dBFS", "higher", "decimal", True),
    ("vocal_activity_ratio", "Vocal activity ratio", "Stimmaktivitätsanteil", "Fraction of frames classified as voiced", "Anteil als stimmhaft erkannter Abschnitte", "audio", "%", "higher", "percent", True),
    ("loudness_variability", "Loudness variability", "Lautstärkevariabilität", "Variation in voiced loudness", "Variation der stimmhaften Lautstärke", "audio", "dB", "lower", "decimal", False),
    ("loudness_trend", "Loudness trend", "Lautstärketrend", "Change in loudness over time", "Änderung der Lautstärke über die Zeit", "audio", "dB/s", "higher", "decimal", False),
    ("mean_mouth_opening", "Mean mouth opening", "Mittlere Mundöffnung", "Mean normalized mouth opening", "Mittlere normalisierte Mundöffnung", "video", None, "higher", "decimal", True),
    ("mouth_opening_rate", "Mouth-opening rate", "Mundöffnungsrate", "Detected opening cycles per second", "Erkannte Öffnungszyklen pro Sekunde", "video", "1/s", "higher", "decimal", True),
    ("opening_variability", "Opening variability", "Öffnungsvariabilität", "Variation in mouth opening", "Variation der Mundöffnung", "video", None, "neutral", "decimal", False),
    ("opening_trend", "Opening trend", "Öffnungstrend", "Change in mouth opening over time", "Änderung der Mundöffnung über die Zeit", "video", "1/s", "higher", "decimal", False),
]


def conditions(settings: Settings) -> list[Condition]:
    raw: Any = DEFAULT_CONDITIONS if not settings.exercise_conditions_json else json.loads(settings.exercise_conditions_json)
    return Conditions(items=TypeAdapter(list[Condition]).validate_python(raw)).items


def metadata(settings: Settings) -> dict:
    definitions = [{"id": row[0], "label": {"en": row[1], "de": row[2]}, "description": {"en": row[3], "de": row[4]}, "modality": row[5], "unit": row[6], "direction": row[7], "format": row[8], "defaultSelected": row[9]} for row in FEATURES]
    return {"conditions": [item.model_dump() for item in sorted(conditions(settings), key=lambda item: item.order)], "features": definitions, "qualityThresholds": {"imuClipFraction": settings.quality_imu_clip_fraction, "faceDetectionRatio": settings.quality_face_detection_ratio, "staleMinutes": settings.quality_stale_minutes}, "traceSchemaVersion": 1}


ISSUE_TEXT = {
    "failed_recording": ("Failed recording", "Fehlgeschlagene Aufnahme", "error", "recording"),
    "extraction_errors": ("Completed with extraction errors", "Mit Extraktionsfehlern abgeschlossen", "error", "recording"),
    "derived_data_cleared": ("Derived data cleared and awaiting retry", "Abgeleitete Daten gelöscht; Wiederholung ausstehend", "warning", "recording"),
    "stale_state": ("Recording or processing state is stale", "Aufnahme oder Verarbeitung ist veraltet", "warning", "recording"),
    "imu_clipping": ("IMU clipping exceeds threshold", "IMU-Clipping überschreitet den Grenzwert", "warning", "motion"),
    "low_face_detection": ("Face detection is below threshold", "Gesichtserkennung liegt unter dem Grenzwert", "warning", "video"),
    "missing_traces": ("Diagnostic traces are missing", "Diagnosespuren fehlen", "warning", "recording"),
    "missing_mp4": ("MP4 playback derivative is missing", "MP4-Wiedergabedatei fehlt", "warning", "video"),
}


def quality_codes(exercise: Exercise, settings: Settings, now: datetime | None = None) -> list[str]:
    recording = exercise.recording
    if recording is None:
        return []
    codes: list[str] = []
    if recording.status is RecordingStatus.FAILED:
        codes.append("failed_recording")
    if recording.status is RecordingStatus.COMPLETED_WITH_ERRORS:
        codes.append("extraction_errors")
    if recording.status is RecordingStatus.UPLOADED and not recording.features:
        codes.append("derived_data_cleared")
    if recording.status in {RecordingStatus.RECORDING, RecordingStatus.PROCESSING} and recording.updated_at < (now or datetime.now(timezone.utc)) - timedelta(minutes=settings.quality_stale_minutes):
        codes.append("stale_state")
    motion = recording.features.get("motion", {})
    if isinstance(motion.get("clip_fraction"), (int, float)) and motion["clip_fraction"] > settings.quality_imu_clip_fraction:
        codes.append("imu_clipping")
    video = recording.features.get("video", {})
    if isinstance(video.get("face_detection_ratio"), (int, float)) and video["face_detection_ratio"] < settings.quality_face_detection_ratio:
        codes.append("low_face_detection")
    if recording.features and not recording.traces:
        codes.append("missing_traces")
    if "video" in recording.object_manifest and "video_playback" not in recording.artifacts:
        codes.append("missing_mp4")
    return codes


def quality_issue(code: str, exercise: Exercise) -> dict:
    en, de, severity, modality = ISSUE_TEXT[code]
    recording = exercise.recording
    return {"code": code, "severity": severity, "issue": {"en": en, "de": de}, "modality": modality, "experimentId": exercise.experiment_id, "exerciseId": exercise.id, "patientNumber": exercise.experiment.patient_number, "condition": exercise.condition, "status": recording.status.value if recording else "idle", "createdAt": exercise.created_at}
