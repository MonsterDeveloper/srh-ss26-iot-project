"""initial PostgreSQL persistence

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260714_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    recording_status = sa.Enum("idle", "recording", "uploaded", "processing", "completed", "completed_with_errors", "failed", name="recording_status")
    recording_status.create(op.get_bind(), checkfirst=True)
    op.create_table("experiments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("patient_number", sa.String(255)), sa.Column("height", sa.Float()), sa.Column("age", sa.Integer()), sa.Column("weight", sa.Float()), sa.Column("properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_table("exercises", sa.Column("id", sa.String(36), primary_key=True), sa.Column("experiment_id", sa.String(36), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False), sa.Column("properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_exercises_experiment_id", "exercises", ["experiment_id"])
    op.create_table("recordings", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("exercise_id", sa.String(36), sa.ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("status", recording_status, nullable=False, server_default="idle"), sa.Column("object_manifest", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("features", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("errors", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("ended_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))


def downgrade() -> None:
    op.drop_table("recordings")
    op.drop_index("ix_exercises_experiment_id", table_name="exercises")
    op.drop_table("exercises")
    op.drop_table("experiments")
    sa.Enum(name="recording_status").drop(op.get_bind(), checkfirst=True)
