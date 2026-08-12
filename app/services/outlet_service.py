"""
Outlet management service (Epic H) — lets the owner manage the list of
physical stores that POS Kasir (Epic C) will sell from and that account 1111
Kas di Tangan is scoped by. This is the foundation half of Epic H only:
listing/creating/toggling outlets. The other half — a real "Kas per Outlet"
balance report (SUM debit/credit on account 1111 grouped by outlet_id) and
the consolidated cash line in the Neraca — needs JournalEntry, which doesn't
exist until Epic B (Journal Engine). Wire that in once Epic B lands.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.db_models import Outlet

_INITIAL_OUTLETS = [
    # (kode_outlet, nama_outlet, alamat)
    ("OUT-PST", "Toko Pusat", "Jl. Merdeka No. 1, Jakarta"),
    ("OUT-CB1", "Cabang Bandung", "Jl. Asia Afrika No. 10, Bandung"),
]


def seed_outlets(db: Session) -> None:
    if db.query(Outlet).count() > 0:
        return
    for kode_outlet, nama_outlet, alamat in _INITIAL_OUTLETS:
        db.add(Outlet(kode_outlet=kode_outlet, nama_outlet=nama_outlet, alamat=alamat))
    db.commit()


def list_outlets(db: Session) -> list[Outlet]:
    return db.query(Outlet).order_by(Outlet.nama_outlet).all()


def _slugify(nama_outlet: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", nama_outlet.upper()).strip("-")
    return slug or "OUTLET"


def create_outlet(db: Session, nama_outlet: str, alamat: str = "") -> Outlet:
    base_code = _slugify(nama_outlet)
    kode_outlet = base_code
    suffix = 2
    while db.get(Outlet, kode_outlet) is not None:
        kode_outlet = f"{base_code}-{suffix}"
        suffix += 1

    outlet = Outlet(kode_outlet=kode_outlet, nama_outlet=nama_outlet, alamat=alamat)
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    return outlet


def set_active(db: Session, code: str, is_active: bool) -> Outlet:
    outlet = db.get(Outlet, code)
    if outlet is None:
        raise ValueError(f"Outlet '{code}' tidak ditemukan")
    outlet.is_active = is_active
    db.commit()
    db.refresh(outlet)
    return outlet
