"""Hermetic PostgreSQL/S3/FastAPI test harness."""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
from collections.abc import Generator

# These assignments deliberately precede every application import.
_ENV = {
    "API_BEARER_TOKEN": "test-token",
    "DASHBOARD_API_BEARER_TOKEN": "test-dashboard-token",
    "DB_PASSWORD": "test-password",
    "S3_ACCESS_KEY_ID": "testing",
    "S3_SECRET_ACCESS_KEY": "testing",
    # Moto intercepts the standard AWS S3 endpoint; no request leaves process.
    "S3_PUBLIC_ENDPOINT": "https://s3.amazonaws.com",
    "S3_INTERNAL_ENDPOINT": "https://s3.amazonaws.com",
    "CORS_ALLOWED_ORIGINS": "http://testserver, https://example.test",
    "AWS_EC2_METADATA_DISABLED": "true",
    "PGSSLMODE": "disable",
}
os.environ.update(_ENV)

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from moto import mock_aws
from py_pglite import PGliteConfig
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="session")
def pglite_config(tmp_path_factory: pytest.TempPathFactory) -> PGliteConfig:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return PGliteConfig(use_tcp=True, tcp_host="127.0.0.1", tcp_port=port,
                        work_dir=tmp_path_factory.mktemp("pglite"), timeout=60,
                        auto_install_deps=True, extensions=[])


@pytest.fixture(scope="session")
def db_engine(pglite_sqlalchemy_manager):
    """Migrate through PGlite's own shared engine, never an application engine."""
    engine = pglite_sqlalchemy_manager.get_engine()
    cfg = Config("alembic.ini")
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        connection.commit()
    yield engine


@pytest.fixture(autouse=True)
def clean_database(db_engine):
    with db_engine.begin() as connection:
        connection.execute(text("TRUNCATE audit_events, recordings, exercises, experiments RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def storage():
    """A fresh storage adapter created only after Moto is active."""
    from api.config import get_settings
    from api.storage import ObjectStorage
    with mock_aws():
        yield ObjectStorage(get_settings())


@pytest.fixture
def client(db_engine, storage) -> Generator[TestClient, None, None]:
    import api.server as server
    from api.database import get_db

    original_storage, original_slots = server.storage, server.extraction_slots
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()
    server.storage = storage
    server.extraction_slots = asyncio.Semaphore(server.settings.extraction_concurrency)
    server.app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(server.app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        server.app.dependency_overrides.clear()
        server.storage, server.extraction_slots = original_storage, original_slots


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}
