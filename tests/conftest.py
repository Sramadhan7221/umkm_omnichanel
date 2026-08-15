"""
Shared pytest fixtures. `db` gives each test an isolated in-memory SQLite
session (separate from the app's real `app/data/umkm_omni.db`); `client`
wires that session into a TestClient via dependency_overrides and bypasses
login, without ever running app.main's startup lifespan (no `with` block —
see app.main.lifespan, which seeds against the real DB and is irrelevant
to route-level tests).

`require_role(*roles)` (Customer Request 1 Epic I) nests Depends(require_login_api)
and Depends(_get_session_role) rather than reading the session directly, so
overriding those two shared functions here controls every require_role(...)-
gated route app-wide — even though each router creates its own outer closure
at import time and can't be overridden individually. Defaulting the role to
"owner" keeps every pre-Epic-I test exercising its original unrestricted
path unchanged; role-specific tests (tests/test_auth.py) override it per-test.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.routers.auth import _get_session_role, require_login_api


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
    app.dependency_overrides[_get_session_role] = lambda: "owner"
    yield TestClient(app)
    app.dependency_overrides.clear()
