from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import RecordingStatus


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExperimentInput(RequestModel):
    patientNumber: str | None = None
    height: float | None = Field(default=None, gt=0, le=300, description="cm")
    age: int | None = Field(default=None, ge=0, le=130, description="years")
    weight: float | None = Field(default=None, gt=0, le=500, description="kg")
    properties: dict = Field(default_factory=dict)


class ExerciseInput(RequestModel):
    properties: dict = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    id: str
    patientNumber: str | None
    height: float | None
    age: int | None
    weight: float | None
    properties: dict
    createdAt: datetime


class ExerciseResponse(BaseModel):
    id: str
    experimentId: str
    recordingStatus: RecordingStatus
    recordingStartedAt: datetime | None
    recordingEndedAt: datetime | None
    hasData: bool
    properties: dict
    createdAt: datetime


class ExperimentPage(BaseModel):
    items: list[ExperimentResponse]
    page: int
    pageSize: int
    total: int


class ExercisePage(BaseModel):
    items: list[ExerciseResponse]
    page: int
    pageSize: int
    total: int


class UploadResponse(BaseModel):
    recordingId: str
    status: RecordingStatus
    uploads: dict[str, str]


class RecordingDataResponse(BaseModel):
    exerciseId: str
    recordingId: str
    status: RecordingStatus
    features: dict
    errors: dict


class ErrorResponse(BaseModel):
    detail: str | RecordingDataResponse | list[dict[str, Any]]
