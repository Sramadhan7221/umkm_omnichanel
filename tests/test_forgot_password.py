"""
Acceptance criteria for Customer Request 1 Epic M (Forgot Password via
Email, SMTP Mailtrap). email_service.send_email is monkeypatched in every
test here — these tests must never touch a real network/SMTP server.
"""

from datetime import datetime, timedelta

import pytest

from app.models.db_models import PasswordResetToken, User
from app.services import email_service
from tests.conftest import make_owner


@pytest.fixture()
def sent_emails(monkeypatch):
    calls = []

    def _fake_send_email(to, subject, body):
        calls.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(email_service, "send_email", _fake_send_email)
    return calls


def test_forgot_password_for_registered_active_owner_sends_one_email_with_token_link(client, db, sent_emails):
    owner = make_owner(db, email="owner@example.com")

    response = client.post("/api/auth/forgot-password", json={"email": "owner@example.com"})
    assert response.status_code == 200

    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "owner@example.com"

    token_row = db.query(PasswordResetToken).filter(PasswordResetToken.user_id == owner.id).one()
    assert token_row.token in sent_emails[0]["body"]
    assert token_row.used_at is None


def test_forgot_password_response_is_identical_for_unknown_and_known_email(client, db, sent_emails):
    make_owner(db, email="owner@example.com")

    known = client.post("/api/auth/forgot-password", json={"email": "owner@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # Only the registered address actually triggers an email — enumeration
    # is prevented at the response level, not by skipping the send.
    assert len(sent_emails) == 1


def test_forgot_password_skips_pending_or_inactive_owner_but_response_is_unchanged(client, db, sent_emails):
    pending = make_owner(db, email="pending@example.com")
    pending.status = "pending"
    inactive = make_owner(db, email="inactive@example.com")
    inactive.is_active = False
    db.commit()

    pending_resp = client.post("/api/auth/forgot-password", json={"email": "pending@example.com"})
    inactive_resp = client.post("/api/auth/forgot-password", json={"email": "inactive@example.com"})

    assert pending_resp.status_code == inactive_resp.status_code == 200
    assert pending_resp.json() == inactive_resp.json()
    assert len(sent_emails) == 0


def test_reset_password_with_valid_token_changes_password_and_old_password_stops_working(client, db, sent_emails):
    make_owner(db, email="owner@example.com")
    client.post("/api/auth/forgot-password", json={"email": "owner@example.com"})
    token = db.query(PasswordResetToken).one().token

    reset_resp = client.post("/api/auth/reset-password", json={"token": token, "password_baru": "NewPass123"})
    assert reset_resp.status_code == 200

    old_login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Qwertyz!1"})
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "NewPass123"})
    assert new_login.status_code == 200


def test_reset_password_rejects_reusing_the_same_token(client, db, sent_emails):
    make_owner(db, email="owner@example.com")
    client.post("/api/auth/forgot-password", json={"email": "owner@example.com"})
    token = db.query(PasswordResetToken).one().token

    first = client.post("/api/auth/reset-password", json={"token": token, "password_baru": "NewPass123"})
    assert first.status_code == 200

    second = client.post("/api/auth/reset-password", json={"token": token, "password_baru": "AnotherPass123"})
    assert second.status_code == 400


def test_reset_password_rejects_expired_token(client, db):
    owner = make_owner(db, email="owner@example.com")
    expired = PasswordResetToken(
        token="expired-token-123", user_id=owner.id,
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(expired)
    db.commit()

    response = client.post("/api/auth/reset-password", json={"token": "expired-token-123", "password_baru": "NewPass123"})
    assert response.status_code == 400


def test_reset_password_rejects_unknown_token(client, db):
    response = client.post("/api/auth/reset-password", json={"token": "does-not-exist", "password_baru": "NewPass123"})
    assert response.status_code == 400


def test_forgot_password_page_and_reset_password_page_render(client, db):
    forgot_page = client.get("/forgot-password")
    assert forgot_page.status_code == 200

    reset_page = client.get("/reset-password?token=whatever")
    assert reset_page.status_code == 200
