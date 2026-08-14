"""
Balance Sheet & P&L engine (Epic F) — Neraca and Laba Rugi computed from
account balances accumulated in JournalEntry (Epic B's ledger), replacing
the old ad-hoc get_income_statement/get_cash_flow in financial_service.py
(Keputusan Scope 1: this REPLACES that engine, it doesn't run alongside it).

Gap in the source Chart of Accounts (docs/chart_of_accounts.csv, Epic A):
there is exactly one Ekuitas account (3110 Modal Pemilik) — no "Laba
Ditahan". Per the Product Owner's explicit choice this session, the Neraca
shows a COMPUTED "Laba Ditahan (Berjalan)" line (cumulative Pendapatan -
Beban since inception) as part of the Ekuitas total, rather than a new
persisted CoA account with a formal year-end closing-entry cycle — that
would be materially bigger scope (a whole tutup-buku-tahunan mechanism),
left as a documented future option, not built here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import Account, JournalEntry, Outlet

# Flips the credit-positive raw ledger balance into each kelompok_utama's
# own natural-increase direction. Applying the GROUP's sign to every member
# account (not each account's own saldo_normal) is what makes contra
# accounts (4211 Potongan Penjualan, 4212 Retur Penjualan — both
# saldo_normal="Debet" despite living in the Pendapatan group) net AGAINST
# revenue automatically: standard contra-account handling, not a hack
# specific to this dataset.
_GROUP_SIGN = {
    "Aset": -1,
    "Kewajiban": 1,
    "Ekuitas": 1,
    "Pendapatan": 1,
    "Beban": -1,
}

_HPP_ACCOUNT = "5110"  # HPP Produk — split out of Beban for its own Laba Kotor line


def _raw_balance(
    db: Session, kode_akun: str, start: datetime | None = None, end: datetime | None = None,
) -> float:
    """SUM(kredit) - SUM(debet) for one account, optionally bounded by
    JournalEntry.tanggal. Both None => all-time. Only `end` set => cumulative
    balance up to a cutoff (Neraca). Both set => period sum (Laba Rugi)."""
    debit_q = db.query(JournalEntry).filter(JournalEntry.kode_debet == kode_akun)
    credit_q = db.query(JournalEntry).filter(JournalEntry.kode_kredit == kode_akun)
    if start is not None:
        debit_q = debit_q.filter(JournalEntry.tanggal >= start)
        credit_q = credit_q.filter(JournalEntry.tanggal >= start)
    if end is not None:
        debit_q = debit_q.filter(JournalEntry.tanggal <= end)
        credit_q = credit_q.filter(JournalEntry.tanggal <= end)

    debit_total = sum(e.nominal for e in debit_q.all())
    credit_total = sum(e.nominal for e in credit_q.all())
    return credit_total - debit_total


def get_account_balance(
    db: Session, account: Account, start: datetime | None = None, end: datetime | None = None,
) -> float:
    """Signed balance in the account's own kelompok_utama direction."""
    return _GROUP_SIGN[account.kelompok_utama] * _raw_balance(db, account.kode_akun, start, end)


def _leaf_accounts(db: Session, kelompok_utama: list[str]) -> list[Account]:
    return (
        db.query(Account)
        .filter(Account.kelompok_utama.in_(kelompok_utama), Account.is_header.is_(False))
        .order_by(Account.kode_akun)
        .all()
    )


def _outlet_breakdown(db: Session, kode_akun: str, end: datetime) -> list[dict]:
    """Per-outlet split of an is_outlet_scoped account's balance — the
    computation outlet_service.py's docstring has been pointing to since
    Epic H ('wire that in once Epic B lands')."""
    outlets = db.query(Outlet).order_by(Outlet.nama_outlet).all()
    breakdown = []
    for outlet in outlets:
        debit_total = sum(
            e.nominal for e in db.query(JournalEntry).filter(
                JournalEntry.kode_debet == kode_akun, JournalEntry.outlet_id == outlet.kode_outlet,
                JournalEntry.tanggal <= end,
            ).all()
        )
        credit_total = sum(
            e.nominal for e in db.query(JournalEntry).filter(
                JournalEntry.kode_kredit == kode_akun, JournalEntry.outlet_id == outlet.kode_outlet,
                JournalEntry.tanggal <= end,
            ).all()
        )
        breakdown.append({
            "kode_outlet": outlet.kode_outlet,
            "nama_outlet": outlet.nama_outlet,
            "saldo": debit_total - credit_total,  # 1111 is Aset (Debet-normal)
        })
    return breakdown


def get_kas_per_outlet(db: Session, as_of: datetime | None = None) -> list[dict]:
    """Public entry point reused by /outlets ('Kas per Outlet' report)."""
    return _outlet_breakdown(db, "1111", as_of or datetime.utcnow())


def _net_profit(db: Session, start: datetime | None, end: datetime) -> float:
    """get_account_balance already returns a POSITIVE amount for both a
    Pendapatan account (revenue earned) and a Beban account (expense
    incurred) — each in its own group's natural-increase direction — so
    computing net profit means explicitly subtracting the two group totals,
    not summing every account's contribution across both groups."""
    total_pendapatan = sum(get_account_balance(db, a, start, end) for a in _leaf_accounts(db, ["Pendapatan"]))
    total_beban = sum(get_account_balance(db, a, start, end) for a in _leaf_accounts(db, ["Beban"]))
    return total_pendapatan - total_beban


def get_profit_loss(db: Session, start: datetime, end: datetime) -> dict:
    pendapatan_accounts = _leaf_accounts(db, ["Pendapatan"])
    beban_accounts = _leaf_accounts(db, ["Beban"])

    total_pendapatan = sum(get_account_balance(db, a, start, end) for a in pendapatan_accounts)
    hpp = next(
        (get_account_balance(db, a, start, end) for a in beban_accounts if a.kode_akun == _HPP_ACCOUNT), 0.0,
    )
    laba_kotor = total_pendapatan - hpp

    beban_operasional_breakdown = [
        {"kode_akun": a.kode_akun, "nama_akun": a.nama_akun, "jumlah": get_account_balance(db, a, start, end)}
        for a in beban_accounts if a.kode_akun != _HPP_ACCOUNT
    ]
    beban_operasional_breakdown = [item for item in beban_operasional_breakdown if item["jumlah"] != 0]
    total_beban_operasional = sum(item["jumlah"] for item in beban_operasional_breakdown)
    laba_bersih = laba_kotor - total_beban_operasional

    return {
        "period": {"start": start.isoformat(sep=" "), "end": end.isoformat(sep=" ")},
        "total_pendapatan": total_pendapatan,
        "hpp": hpp,
        "laba_kotor": laba_kotor,
        "beban_operasional_breakdown": beban_operasional_breakdown,
        "total_beban_operasional": total_beban_operasional,
        "laba_bersih": laba_bersih,
    }


def get_balance_sheet(db: Session, as_of: datetime) -> dict:
    def _section(kelompok: str) -> list[dict]:
        rows = []
        for account in _leaf_accounts(db, [kelompok]):
            saldo = get_account_balance(db, account, end=as_of)
            row = {"kode_akun": account.kode_akun, "nama_akun": account.nama_akun, "saldo": saldo}
            if account.is_outlet_scoped:
                row["breakdown_outlet"] = _outlet_breakdown(db, account.kode_akun, as_of)
            rows.append(row)
        return rows

    aset = _section("Aset")
    kewajiban = _section("Kewajiban")
    ekuitas = _section("Ekuitas")

    laba_ditahan_berjalan = _net_profit(db, start=None, end=as_of)
    ekuitas.append({
        "kode_akun": None,
        "nama_akun": "Laba Ditahan (Berjalan)",
        "saldo": laba_ditahan_berjalan,
        "is_computed": True,
    })

    total_aset = sum(r["saldo"] for r in aset)
    total_kewajiban = sum(r["saldo"] for r in kewajiban)
    total_ekuitas = sum(r["saldo"] for r in ekuitas)
    total_kewajiban_ekuitas = total_kewajiban + total_ekuitas

    return {
        "as_of": as_of.isoformat(sep=" "),
        "aset": aset,
        "total_aset": total_aset,
        "kewajiban": kewajiban,
        "total_kewajiban": total_kewajiban,
        "ekuitas": ekuitas,
        "total_ekuitas": total_ekuitas,
        "total_kewajiban_ekuitas": total_kewajiban_ekuitas,
        "is_balanced": abs(total_aset - total_kewajiban_ekuitas) < 0.01,
    }
