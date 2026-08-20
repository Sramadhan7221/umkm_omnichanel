"""
Customer Request 3 revisi — Epic O (revisi 2): error_log table + the global
Exception handler that writes to it. Uses a local `client` fixture (shadows
conftest.py's) built with raise_server_exceptions=False, since these tests
deliberately trigger real unhandled exceptions and need TestClient to hand
back the app's actual 500 response instead of re-raising.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routers.api as api_router
import app.routers.auth as auth_router
import app.routers.financial as financial_router
import app.services.error_log_service as error_log_service
from app.database import Base, get_db
from app.main import app
from app.models.db_models import ErrorLog
from app.routers.auth import _get_session_role, require_login_api
from app.services.tenant_context import _get_session_tenant_id


@pytest.fixture()
def db(monkeypatch):
    """Overrides conftest.py's `db` fixture for this module only. log_error()
    deliberately opens its own SessionLocal() rather than reusing the
    request's session (see error_log_service.py's docstring), so the plain
    conftest fixture isn't enough here: SessionLocal must be repointed at
    this same in-memory engine, or writes from log_error would silently land
    in a completely different (real) database that these tests never see."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(error_log_service, "SessionLocal", TestingSessionLocal)
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
    app.dependency_overrides[_get_session_tenant_id] = lambda: 1
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_unhandled_exception_in_api_router_is_logged(client, db, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom in process_retur")

    monkeypatch.setattr(api_router, "process_retur", _boom)

    response = client.post("/api/order/ORD-DOES-NOT-MATTER/process-retur", json={"restore_stock": False})

    assert response.status_code == 500
    assert response.json() == {"detail": "Terjadi kesalahan pada server"}
    assert "RuntimeError" not in response.text
    assert "kaboom" not in response.text

    rows = db.query(ErrorLog).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.created_at is not None
    assert "process-retur" in row.endpoint
    assert "RuntimeError: kaboom in process_retur" in row.exceptions
    assert "Traceback" in row.exceptions

    request_ctx = json.loads(row.request)
    assert request_ctx["method"] == "POST"
    assert request_ctx["path"] == "/api/order/ORD-DOES-NOT-MATTER/process-retur"
    assert request_ctx["body"] == {"restore_stock": False}


def test_unhandled_exception_in_financial_router_is_logged(client, db, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom in list_accounts_grouped")

    monkeypatch.setattr(financial_router, "list_accounts_grouped", _boom)

    response = client.get("/api/financial/accounts")

    assert response.status_code == 500
    assert response.json() == {"detail": "Terjadi kesalahan pada server"}

    rows = db.query(ErrorLog).all()
    assert len(rows) == 1
    assert "accounts" in rows[0].endpoint
    assert "RuntimeError: kaboom in list_accounts_grouped" in rows[0].exceptions


def test_password_field_is_redacted_in_error_log(client, db, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom in authenticate")

    monkeypatch.setattr(auth_router, "authenticate", _boom)

    response = client.post(
        "/api/auth/login",
        json={"email": "someone@example.com", "password": "SuperSecret123!"},
    )

    assert response.status_code == 500

    rows = db.query(ErrorLog).all()
    assert len(rows) == 1
    raw_request_column = rows[0].request
    assert "SuperSecret123!" not in raw_request_column

    request_ctx = json.loads(raw_request_column)
    assert request_ctx["body"]["password"] == "***REDACTED***"
    assert request_ctx["body"]["email"] == "someone@example.com"


def test_error_log_write_failure_does_not_break_error_response(client, db, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom in process_retur")

    monkeypatch.setattr(api_router, "process_retur", _boom)

    def _broken_session_local():
        raise RuntimeError("db connection is down")

    monkeypatch.setattr(error_log_service, "SessionLocal", _broken_session_local)

    response = client.post("/api/order/ORD-X/process-retur", json={"restore_stock": False})

    assert response.status_code == 500
    assert response.json() == {"detail": "Terjadi kesalahan pada server"}


def test_expected_value_error_is_not_written_to_error_log(client, db):
    """Business validation (404-turned-400 here: order not found) is caught
    locally by the router and must NOT count as a bug for error_log."""
    response = client.post("/api/order/NONEXISTENT-ORDER/process-retur", json={"restore_stock": False})

    assert response.status_code == 400
    assert db.query(ErrorLog).count() == 0
