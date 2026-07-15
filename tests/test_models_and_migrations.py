from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.models import Exercise, Experiment, Recording, RecordingStatus


@pytest.mark.integration
def test_json_uuid_fk_unique_and_cascade(db_session):
    experiment = Experiment(properties={"nested": {"value": 1}})
    db_session.add(experiment); db_session.flush()
    exercise = Exercise(experiment_id=experiment.id, properties={"x": True})
    db_session.add(exercise); db_session.flush()
    record = Recording(exercise_id=exercise.id, status=RecordingStatus.IDLE)
    db_session.add(record); db_session.commit()
    assert isinstance(record.id, uuid.UUID) and record.features == {}
    db_session.delete(experiment); db_session.commit()
    assert db_session.get(Exercise, exercise.id) is None


@pytest.mark.integration
def test_orm_enum_labels_match_lowercase_migration_contract(db_session):
    assert [member.value for member in RecordingStatus] == ["idle", "recording", "uploaded", "processing", "completed", "completed_with_errors", "failed"]
    experiment = Experiment()
    db_session.add(experiment)
    db_session.flush()
    for status in RecordingStatus:
        exercise = Exercise(experiment_id=experiment.id)
        db_session.add(exercise)
        db_session.flush()
        recording = Recording(exercise_id=exercise.id, status=status)
        db_session.add(recording)
        db_session.commit()
        db_session.expire(recording)
        assert recording.status is status
        raw = db_session.execute(text("SELECT status::text FROM recordings WHERE id = :id"), {"id": recording.id}).scalar_one()
        assert raw == status.value
