"""
Auth service (Fase 5, extended Customer Request 1 Epic I) — email/password
auth with 3 roles (superadmin/owner/admin). Uses stdlib hashlib.pbkdf2_hmac
for password hashing (no new pip dependency), and a random per-user salt
stored alongside the hash.

Only a single Superadmin account is seeded at startup. Owner accounts are
created via self-service registration (Epic J, not yet built) and require
Superadmin approval (`status`); Admin accounts are created by an Owner via
`POST /api/auth/create-admin` and need no separate approval.
"""

from __future__ import annotations

import hashlib
import os
from sqlalchemy.orm import Session

from app.models.db_models import User

DEFAULT_SUPERADMIN_EMAIL = "superadmin@umkmapp.com"
DEFAULT_SUPERADMIN_PASSWORD = "Qwertyz!1"

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
    """Create the default Superadmin account if no users exist yet."""
    if db.query(User).count() > 0:
        return
    salt_hex, hash_hex = hash_new_password(DEFAULT_SUPERADMIN_PASSWORD)
    db.add(User(
        email=DEFAULT_SUPERADMIN_EMAIL,
        password_hash=hash_hex,
        password_salt=salt_hex,
        role="superadmin",
        status="approved",
        is_active=True,
    ))
    db.commit()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None:
        return None
    if not verify_password(password, user.password_salt, user.password_hash):
        return None
    return user
