"""
Shared pytest fixtures. `db` gives each test an isolated in-memory SQLite
session (separate from the app's real `app/data/umkm_omni.db`); `client`
wires that session into a TestClient via dependency_overrides and bypasses
login, without ever running app.main's startup lifespan (no `with` block —
see app.main.lifespan, which seeds against the real DB and is irrelevant
to route-level tests).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.routers.auth import require_login_api


@pytest.fixture()
def db():
    # StaticPool: a bare sqlite:///:memory: engine hands out a fresh, empty
    # in-memory DB per connection checkout, which breaks as soon as the
    # TestClient serves a request on a worker thread (its own checkout sees
    # none of the tables create_all() just made). StaticPool pins everyone
    # to the single connection that created the schema.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_login_api] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()
