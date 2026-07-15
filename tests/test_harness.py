from __future__ import annotations

import shutil

import pytest
from sqlalchemy import text


@pytest.mark.integration
def test_node_and_npm_are_available():
    assert shutil.which("node")
    assert shutil.which("npm")


@pytest.mark.integration
def test_pglite_and_migration_schema(db_engine):
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "20260714_0001"
        tables = set(conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'" )).scalars())
        assert {"experiments", "exercises", "recordings"} <= tables
        assert conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname='recording_status')")).scalar()


@pytest.mark.integration
def test_moto_bucket_and_cors(storage):
    storage.ensure_bucket_cors(["http://testserver"])
    cors = storage.internal.get_bucket_cors(Bucket=storage.bucket)
    assert cors["CORSRules"][0]["AllowedMethods"] == ["PUT"]


@pytest.mark.integration
def test_client_lifespan_and_live(client):
    assert client.get("/health/live").json() == {"status": "ok"}
