"""
Chart of Accounts service (Epic A, made per-owner in Customer Request 1
Epic K) — seeds the `account` table from docs/chart_of_accounts.csv (source
of truth: the business owner's own SAK EMKM account list) and exposes a
read-only, kelompok_utama-grouped view for the /api/financial/accounts
endpoint. No create/update/delete here yet — the account list is fixed for
this epic.

seed_accounts is no longer called once at app startup — since Account.kode_akun
is now only unique per (owner_id, kode_akun), not globally, a global seed
would either no-op after the first owner or collide. It's called once per
Owner from user_admin_service.approve_owner instead.
"""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.db_models import Account

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "chart_of_accounts.csv"

_KELOMPOK_ORDER = ["Aset", "Kewajiban", "Ekuitas", "Pendapatan", "Beban"]


def seed_accounts(db: Session, owner_id: int) -> None:
    if db.query(Account).filter(Account.owner_id == owner_id).count() > 0:
        return
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            db.add(Account(
                owner_id=owner_id,
                kode_akun=row["kode_akun"],
                nama_akun=row["nama_akun"],
                penjelasan_awam=row["penjelasan_awam"],
                kelompok_utama=row["kelompok_utama"],
                saldo_normal=row["saldo_normal"],
                parent_code=row["parent_code"] or None,
                is_header=row["is_header"] == "true",
            ))
    db.commit()


def get_account(db: Session, owner_id: int, kode_akun: str) -> Account | None:
    """Resolves an Account by its business code within one owner's chart —
    replaces db.get(Account, kode_akun), which stopped working once kode_akun
    became non-unique across owners."""
    return db.query(Account).filter(Account.owner_id == owner_id, Account.kode_akun == kode_akun).first()


def list_accounts_grouped(db: Session, owner_id: int) -> dict[str, list[dict]]:
    accounts = db.query(Account).filter(Account.owner_id == owner_id).order_by(Account.kode_akun).all()
    grouped: dict[str, list[dict]] = {k: [] for k in _KELOMPOK_ORDER}
    for account in accounts:
        grouped.setdefault(account.kelompok_utama, []).append({
            "kode_akun": account.kode_akun,
            "nama_akun": account.nama_akun,
            "penjelasan_awam": account.penjelasan_awam,
            "kelompok_utama": account.kelompok_utama,
            "saldo_normal": account.saldo_normal,
            "parent_code": account.parent_code,
            "is_header": account.is_header,
        })
    return grouped
