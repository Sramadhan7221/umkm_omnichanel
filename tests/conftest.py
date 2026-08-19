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

Epic K adds the same treatment for tenant scoping: `get_tenant_id`
(app/services/tenant_context.py) nests Depends(_get_session_tenant_id), so
overriding that one function here (default tenant_id=1, matching
require_login_api's fixed user_id=1) unblocks every owner_id-scoped route at
once. `make_owner` creates a real `User` row so tests that need an actual
owner_id (most direct-service-call tests, post-Epic-K) don't have to
construct one by hand every time — pass its returned `.id` as `owner_id` to
service calls, or override `_get_session_tenant_id` to match it for
`client`-based tests exercising a specific tenant.

Customer Request 2 Epic N's acceptance criteria require running this whole
suite once against a real Postgres instance as a dialect smoke test (SQLite
and Postgres don't always behave identically for constraints/types). The
`db` fixture below honors DATABASE_URL when it's set to do this — point it
at a throwaway Postgres (e.g. `docker run -p 5432:5432 postgres:18`, NOT the
docker-compose.yml `db` service, which deliberately has no exposed port) and
run `pytest` with that env var set. Default local/CI runs are unaffected:
no DATABASE_URL means the in-memory SQLite engine below, exactly as before.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.db_models import User
from app.routers.auth import _get_session_role, require_login_api
from app.services.auth_service import hash_new_password
from app.services.tenant_context import _get_session_tenant_id


_POSTGRES_TEST_URL = os.environ.get("DATABASE_URL")


@pytest.fixture()
def db():
    if _POSTGRES_TEST_URL:
        # Postgres smoke-test mode (see module docstring). Unlike the
        # in-memory SQLite engine below, this server persists between
        # tests, so drop_all() both before (in case a previous run crashed
        # mid-test) and after each test keeps every test isolated.
        engine = create_engine(_POSTGRES_TEST_URL)
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    else:
        # StaticPool: a bare sqlite:///:memory: engine hands out a fresh,
        # empty in-memory DB per connection checkout, which breaks as soon
        # as the TestClient serves a request on a worker thread (its own
        # checkout sees none of the tables create_all() just made).
        # StaticPool pins everyone to the single connection that created
        # the schema.
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        if _POSTGRES_TEST_URL:
            Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_login_api] = lambda: 1
    app.dependency_overrides[_get_session_role] = lambda: "owner"
    app.dependency_overrides[_get_session_tenant_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def as_tenant(owner_id: int) -> None:
    """Points the `client` fixture's tenant dependency at a specific owner_id
    — use when a test creates its own Owner via make_owner() and needs
    `client` HTTP calls to act as that tenant instead of the fixture's
    default (owner_id=1)."""
    app.dependency_overrides[_get_session_tenant_id] = lambda: owner_id


def make_owner(db, email: str = "owner@example.com") -> User:
    """Creates a real, approved Owner row — used by tests that need an
    actual owner_id (Customer Request 1 Epic K made owner_id required
    everywhere data is tenant-scoped)."""
    salt_hex, hash_hex = hash_new_password("Qwertyz!1")
    user = User(
        email=email, password_hash=hash_hex, password_salt=salt_hex,
        role="owner", status="approved", is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
