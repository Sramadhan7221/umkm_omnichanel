"""
Auth service (Fase 5) — minimal email/password auth for a single default
admin account. Uses stdlib hashlib.pbkdf2_hmac for password hashing (no new
pip dependency), and a random per-user salt stored alongside the hash.

This is deliberately simple (one seeded admin account, no registration UI,
no password reset flow) — enough to gate the demo behind a login screen for
a presentation, not a full user-management system.
"""

from __future__ import annotations

import hashlib
import os
from sqlalchemy.orm import Session

from app.models.db_models import User

DEFAULT_ADMIN_EMAIL = "admin@umkmapp.com"
DEFAULT_ADMIN_PASSWORD = "Qwertyz!1"

_PBKDF2_ITERATIONS = 260_000


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS).hex()


def hash_new_password(password: str) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex) for storing a new/updated password."""
    salt = os.urandom(16)
    return salt.hex(), _hash_password(password, salt)


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    return _hash_password(password, salt) == hash_hex


def seed_admin_user(db: Session) -> None:
    """Create the default admin account if no users exist yet."""
    if db.query(User).count() > 0:
        return
    salt_hex, hash_hex = hash_new_password(DEFAULT_ADMIN_PASSWORD)
    db.add(User(email=DEFAULT_ADMIN_EMAIL, password_hash=hash_hex, password_salt=salt_hex))
    db.commit()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None:
        return None
    if not verify_password(password, user.password_salt, user.password_hash):
        return None
    return user
