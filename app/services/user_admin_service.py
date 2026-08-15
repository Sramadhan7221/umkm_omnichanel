"""
Owner registration + Superadmin approval workflow (Customer Request 1,
Epic J extended by Epic K). Flat functions taking `db: Session` first,
matching this project's service-layer convention.

Approving an Owner provisions their entire independent demo sandbox — Chart
of Accounts, Platform toggles, product catalog, a handful of mock orders,
and their settlements — mirroring what used to auto-seed once, globally, at
app startup before Epic K made all of this owner-scoped (see
app/main.py's lifespan, which now only seeds global/tenant-independent
data). Epic J shipped this as a `# TODO(Epic K)` stub because
`chart_of_accounts_service.seed_accounts` was still a global, once-only seed
with no `owner_id` column on `Account` — Epic K's schema change (surrogate
`id` PK + `owner_id` + `unique(owner_id, kode_akun)`) is what makes the real
call below safe.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import User
from app.services.auth_service import hash_new_password
from app.services.chart_of_accounts_service import seed_accounts
from app.services.inventory_service import seed_products
from app.services.platform_service import seed_platforms
from app.services.reconciliation_service import generate_settlements


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
    # Imported here (not at module top) to avoid a service->router layering
    # oddity being visible at import time for every caller of this module —
    # _sync_mock_orders lives in app/routers/api.py (Fase 5 placement, never
    # moved), and this is its only cross-layer caller.
    from app.routers.api import _sync_mock_orders

    user = _get_owner(db, user_id)
    if user.status != "pending":
        raise ValueError("Registrasi ini sudah diproses")
    user.status = "approved"
    db.commit()
    db.refresh(user)

    # Provision a full, independent demo sandbox for this Owner — see module
    # docstring.
    seed_accounts(db, user.id)
    seed_platforms(db, user.id)
    seed_products(db, user.id)
    for _ in range(5):
        _sync_mock_orders(db, user.id)
    generate_settlements(db, user.id)

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
