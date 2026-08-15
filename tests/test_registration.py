"""
Acceptance criteria for Customer Request 1 Epic J (Registrasi Owner
Self-Service + Dashboard Approval Superadmin). Approving an Owner now also
provisions their full demo sandbox (Epic K wired this up for real — see
app/services/user_admin_service.py's module docstring) — the approve tests
below exercise that path too, just don't assert on its contents (that's
tests/test_tenant_isolation.py's job).
"""

from app.main import app
from app.models.db_models import User
from app.routers.auth import _get_session_role
from app.services.journal_engine_service import seed_mapping_rules, seed_pos_payment_extension


def _as_role(client, role):
    app.dependency_overrides[_get_session_role] = lambda: role


def _register(client, email="owner@example.com", password="Qwertyz!1", business_name="Toko Uji"):
    return client.post("/api/auth/register", json={
        "email": email, "password": password, "business_name": business_name,
    })


def test_register_creates_pending_owner_that_cannot_login(client, db):
    response = _register(client)
    assert response.status_code == 200

    user = db.query(User).filter(User.email == "owner@example.com").first()
    assert user is not None
    assert user.role == "owner" and user.status == "pending"

    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Qwertyz!1"})
    assert login.status_code == 401
    assert "menunggu persetujuan" in login.json()["detail"]


def test_register_rejects_duplicate_email(client, db):
    _register(client)
    response = _register(client)
    assert response.status_code == 400


def test_register_rejects_short_password(client, db):
    response = _register(client, password="short")
    assert response.status_code == 400


def test_superadmin_stats_reflect_new_registration(client, db):
    _as_role(client, "superadmin")
    before = client.get("/api/superadmin/stats").json()

    _register(client)
    after = client.get("/api/superadmin/stats").json()

    before_total = sum(m["count"] for m in before["monthly_new_owners"])
    after_total = sum(m["count"] for m in after["monthly_new_owners"])
    assert after_total == before_total + 1


def test_approve_then_login_succeeds_and_double_approve_rejected(client, db):
    # approve_owner()'s demo-sandbox provisioning needs the GLOBAL mapping
    # rules to already exist (same as app.main's lifespan seeds them once at
    # cold boot, before any registration happens) — the client/db fixtures
    # don't run that lifespan, so seed them explicitly here.
    seed_mapping_rules(db)
    seed_pos_payment_extension(db)

    _register(client)
    user = db.query(User).filter(User.email == "owner@example.com").first()

    _as_role(client, "superadmin")
    response = client.post(f"/api/superadmin/users/{user.id}/approve")
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"

    again = client.post(f"/api/superadmin/users/{user.id}/approve")
    assert again.status_code == 400

    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Qwertyz!1"})
    assert login.status_code == 200
    assert login.json()["role"] == "owner"


def test_reject_blocks_login_permanently_but_keeps_row(client, db):
    _register(client)
    user = db.query(User).filter(User.email == "owner@example.com").first()

    _as_role(client, "superadmin")
    response = client.post(f"/api/superadmin/users/{user.id}/reject")
    assert response.status_code == 200

    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Qwertyz!1"})
    assert login.status_code == 401
    assert "ditolak" in login.json()["detail"]

    assert db.query(User).filter(User.email == "owner@example.com").first() is not None


def test_deactivate_then_reactivate_owner(client, db):
    seed_mapping_rules(db)  # see test_approve_then_login_succeeds_and_double_approve_rejected
    seed_pos_payment_extension(db)

    _register(client)
    user = db.query(User).filter(User.email == "owner@example.com").first()

    _as_role(client, "superadmin")
    client.post(f"/api/superadmin/users/{user.id}/approve")

    deactivate = client.post(f"/api/superadmin/users/{user.id}/deactivate")
    assert deactivate.status_code == 200

    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Qwertyz!1"})
    assert login.status_code == 401
    assert "dinonaktifkan" in login.json()["detail"]

    reactivate = client.post(f"/api/superadmin/users/{user.id}/reactivate")
    assert reactivate.status_code == 200

    login_again = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Qwertyz!1"})
    assert login_again.status_code == 200


def test_non_superadmin_denied_superadmin_routes(client, db):
    _as_role(client, "owner")
    assert client.get("/api/superadmin/stats").status_code == 403
    assert client.get("/api/superadmin/owners/pending").status_code == 403

    _as_role(client, "admin")
    assert client.get("/api/superadmin/stats").status_code == 403
