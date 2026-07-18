from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, func, text
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
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[str | None] = mapped_column(String(255))
    exercises: Mapped[list["Exercise"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")


class Exercise(Timestamped, Base):
    __tablename__ = "exercises"
    __table_args__ = (
        Index(
            "uq_exercises_active_condition_repetition",
            "experiment_id", "condition", "repetition",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND condition IS NOT NULL AND repetition IS NOT NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    condition: Mapped[str | None] = mapped_column(String(64))
    repetition: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[str | None] = mapped_column(String(255))
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
    traces: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    artifacts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exercise: Mapped[Exercise] = relationship(back_populates="recording")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    experiment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    exercise_id: Mapped[str | None] = mapped_column(String(36), index=True)
    changed_fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
