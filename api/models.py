from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class RecordingStatus(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Experiment(Timestamped, Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_number: Mapped[str | None] = mapped_column(String(255))
    height: Mapped[float | None] = mapped_column(Float)
    age: Mapped[int | None] = mapped_column(Integer)
    weight: Mapped[float | None] = mapped_column(Float)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    exercises: Mapped[list["Exercise"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")


class Exercise(Timestamped, Base):
    __tablename__ = "exercises"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    experiment: Mapped[Experiment] = relationship(back_populates="exercises")
    recording: Mapped["Recording | None"] = relationship(back_populates="exercise", cascade="all, delete-orphan", uselist=False)


class Recording(Timestamped, Base):
    __tablename__ = "recordings"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), unique=True, nullable=False)
    status: Mapped[RecordingStatus] = mapped_column(
        Enum(
            RecordingStatus,
            name="recording_status",
            values_callable=lambda enum: [member.value for member in enum],
            validate_strings=True,
        ),
        default=RecordingStatus.IDLE,
        nullable=False,
    )
    object_manifest: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    errors: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exercise: Mapped[Exercise] = relationship(back_populates="recording")
