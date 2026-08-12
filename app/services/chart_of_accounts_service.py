"""
Chart of Accounts service (Epic A) — seeds the `account` table from
docs/chart_of_accounts.csv (source of truth: the business owner's own SAK
EMKM account list) and exposes a read-only, kelompok_utama-grouped view for
the /api/financial/accounts endpoint. No create/update/delete here yet —
the account list is fixed for this epic.
"""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.db_models import Account

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "chart_of_accounts.csv"

_KELOMPOK_ORDER = ["Aset", "Kewajiban", "Ekuitas", "Pendapatan", "Beban"]


def seed_accounts(db: Session) -> None:
    if db.query(Account).count() > 0:
        return
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            db.add(Account(
                kode_akun=row["kode_akun"],
                nama_akun=row["nama_akun"],
                penjelasan_awam=row["penjelasan_awam"],
                kelompok_utama=row["kelompok_utama"],
                saldo_normal=row["saldo_normal"],
                parent_code=row["parent_code"] or None,
                is_header=row["is_header"] == "true",
                is_outlet_scoped=row["is_outlet_scoped"] == "true",
            ))
    db.commit()


def list_accounts_grouped(db: Session) -> dict[str, list[dict]]:
    accounts = db.query(Account).order_by(Account.kode_akun).all()
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
            "is_outlet_scoped": account.is_outlet_scoped,
        })
    return grouped
