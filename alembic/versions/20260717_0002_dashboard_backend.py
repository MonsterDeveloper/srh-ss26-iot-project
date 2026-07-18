"""add dashboard backend fields and audit history

Revision ID: 20260717_0002
Revises: 20260714_0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260717_0002"
down_revision = "20260714_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("experiments", sa.Column("archived_by", sa.String(255)))
    op.add_column("exercises", sa.Column("condition", sa.String(64)))
    op.add_column("exercises", sa.Column("repetition", sa.Integer()))
    op.add_column("exercises", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("exercises", sa.Column("archived_by", sa.String(255)))
    op.execute("UPDATE exercises SET condition = properties->>'condition' WHERE jsonb_typeof(properties->'condition') = 'string'")
    op.execute("""UPDATE exercises SET repetition = (properties->>'repetition')::integer
                WHERE properties ? 'repetition' AND properties->>'repetition' ~ '^[1-9][0-9]*$'""")
    op.create_index(
        "uq_exercises_active_condition_repetition", "exercises",
        ["experiment_id", "condition", "repetition"], unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND condition IS NOT NULL AND repetition IS NOT NULL"),
    )
    op.add_column("recordings", sa.Column("traces", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("recordings", sa.Column("artifacts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("experiment_id", sa.String(36)),
        sa.Column("exercise_id", sa.String(36)),
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("request_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_events_experiment_id", "audit_events", ["experiment_id"])
    op.create_index("ix_audit_events_exercise_id", "audit_events", ["exercise_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_column("recordings", "artifacts")
    op.drop_column("recordings", "traces")
    op.drop_index("uq_exercises_active_condition_repetition", table_name="exercises")
    for column in ("archived_by", "archived_at", "repetition", "condition"):
        op.drop_column("exercises", column)
    op.drop_column("experiments", "archived_by")
    op.drop_column("experiments", "archived_at")
