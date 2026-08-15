"""
Owner registration + Superadmin approval workflow (Customer Request 1 Epic
J). Flat functions taking `db: Session` first, matching this project's
service-layer convention.

Approving an Owner is supposed to also seed their Chart of Accounts (per
CLAUDE.md's Epic J task text), but `chart_of_accounts_service.seed_accounts`
is still a global, once-only seed keyed on `Account.kode_akun` as primary
key with no `owner_id` column — re-seeding the same 38 codes for a second
owner would collide today. That restructuring is Epic K's job; `approve_owner`
below leaves a stub instead of calling it (PO-confirmed deferral, matching
the precedent set at Epic H for the same kind of forward dependency).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import User
from app.services.auth_service import hash_new_password


def register_owner(db: Session, email: str, password: str, business_name: str) -> User:
    email = email.strip().lower()
    business_name = business_name.strip()
    if len(password) < 8:
        raise ValueError("Kata sandi minimal 8 karakter")
    if not business_name:
        raise ValueError("Nama bisnis wajib diisi")
    if db.query(User).filter(User.email == email).first() is not None:
        raise ValueError("Email sudah terdaftar")

    salt_hex, hash_hex = hash_new_password(password)
    user = User(
        email=email,
        password_hash=hash_hex,
        password_salt=salt_hex,
        role="owner",
        owner_id=None,
        status="pending",
        is_active=True,
        business_name=business_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_pending_owners(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.role == "owner", User.status == "pending")
        .order_by(User.created_time)
        .all()
    )


def _get_owner(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id, User.role == "owner").first()
    if user is None:
        raise ValueError("Akun Owner tidak ditemukan")
    return user


def approve_owner(db: Session, user_id: int) -> User:
    user = _get_owner(db, user_id)
    if user.status != "pending":
        raise ValueError("Registrasi ini sudah diproses")
    user.status = "approved"
    db.commit()
    db.refresh(user)
    # TODO(Epic K): seed_accounts(db, owner_id=user.id) once Account has an
    # owner_id column and a per-owner-safe primary key (see module docstring).
    return user


def reject_owner(db: Session, user_id: int) -> User:
    user = _get_owner(db, user_id)
    if user.status != "pending":
        raise ValueError("Registrasi ini sudah diproses")
    user.status = "rejected"
    db.commit()
    db.refresh(user)
    return user


def deactivate_owner(db: Session, user_id: int) -> User:
    user = _get_owner(db, user_id)
    if user.status != "approved" or not user.is_active:
        raise ValueError("Hanya Owner aktif yang bisa dinonaktifkan")
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


def reactivate_owner(db: Session, user_id: int) -> User:
    user = _get_owner(db, user_id)
    if user.is_active:
        raise ValueError("Owner ini sudah aktif")
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


def get_owner_stats(db: Session) -> dict:
    owners = db.query(User).filter(User.role == "owner").all()
    active_owner_count = sum(1 for o in owners if o.status == "approved" and o.is_active)

    counts: Counter[str] = Counter(
        (o.created_time or datetime.utcnow()).strftime("%Y-%m") for o in owners
    )
    monthly_new_owners = [{"month": month, "count": counts[month]} for month in sorted(counts)]

    return {"active_owner_count": active_owner_count, "monthly_new_owners": monthly_new_owners}
