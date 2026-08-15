"""
Financial engine — manual Expense entries and PPh Final UMKM accrual/deposit
(Epic E). Income Statement and Cash Flow used to be computed here directly
from OmniOrder/Expense (Fase 3); Epic F replaced both with account-balance
reporting from JournalEntry (see app/services/balance_sheet_service.py),
per Keputusan Scope 1 — the old engine doesn't run alongside the new one.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import Expense, JournalEntry, OmniOrder, TransactionMappingRule
from app.services.balance_sheet_service import get_account_balance
from app.services.chart_of_accounts_service import get_account
from app.services.journal_engine_service import post_expense_journal, post_journal


def add_expense(
    db: Session, owner_id: int, category: str, amount: float, note: str, expense_date: datetime,
    rule_no: int, outlet_id: str | None = None,
) -> Expense:
    rule = db.get(TransactionMappingRule, rule_no)
    kredit_account = get_account(db, owner_id, rule.kode_kredit)
    if kredit_account.is_outlet_scoped and not outlet_id:
        raise ValueError(
            f"Jenis beban '{rule.event_trigger}' membutuhkan outlet — pilih outlet sebelum menyimpan."
        )

    expense = Expense(
        owner_id=owner_id, category=category, amount=amount, note=note, expense_date=expense_date,
        rule_no=rule_no, outlet_id=outlet_id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    post_expense_journal(db, expense)
    return expense


def list_expenses(db: Session, owner_id: int, start: datetime, end: datetime) -> list[Expense]:
    return (
        db.query(Expense)
        .filter(Expense.owner_id == owner_id, Expense.expense_date >= start, Expense.expense_date <= end)
        .order_by(Expense.expense_date.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# PPh Final UMKM 0,5% (Epic E) — rules #28 (akrual bulanan) and #29
# (penyetoran) already exist in TransactionMappingRule (seeded from
# docs/transaction_mapping_matrix.csv by Epic B); this just wires them to
# two new owner actions. Real PPh Final UMKM is 0,5% of GROSS turnover, not
# net profit — matches rule #28's own wording ("0,5% x Omset Bruto").
# ---------------------------------------------------------------------------

def _month_range(period: str) -> tuple[datetime, datetime]:
    year, month = (int(p) for p in period.split("-"))
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _gross_omset_for_period(db: Session, owner_id: int, period: str) -> float:
    start, end = _month_range(period)
    orders = (
        db.query(OmniOrder)
        .filter(
            OmniOrder.owner_id == owner_id,
            OmniOrder.status == "Selesai", OmniOrder.order_time >= start, OmniOrder.order_time < end,
        )
        .all()
    )
    return sum(o.gross_amount for o in orders)


def _close_month_sumber_dokumen(period: str) -> str:
    return f"Tutup Buku PPh {period}"


def close_month_pph(db: Session, owner_id: int, period: str) -> JournalEntry:
    """period: 'YYYY-MM'. Rejects a period that's already been closed —
    reuses the free-text sumber_dokumen convention (same as 'Pesanan X'/
    'Nota X'/'Biaya #N') instead of a new tracking column/table."""
    sumber_dokumen = _close_month_sumber_dokumen(period)
    already_closed = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner_id, JournalEntry.sumber_dokumen == sumber_dokumen
    ).first()
    if already_closed is not None:
        raise ValueError(f"Periode {period} sudah ditutup buku (PPh sudah diakru)")

    gross_omset = _gross_omset_for_period(db, owner_id, period)
    nominal = round(gross_omset * 0.005, 2)

    entry = post_journal(
        db, owner_id=owner_id, kode_debet="5410", kode_kredit="2140", nominal=nominal,
        tanggal=datetime.utcnow(), sumber_dokumen=sumber_dokumen,
        keterangan=f"Akrual PPh Final 0,5% periode {period} (omset bruto Rp {gross_omset:,.0f})",
        rule_no=28,
    )
    if entry is None:
        raise ValueError(f"Tidak ada omset selesai pada periode {period}, tidak ada PPh untuk diakru")
    return entry


def record_pph_deposit(db: Session, owner_id: int, amount: float, deposit_date: datetime) -> JournalEntry:
    """Nominal setoran adalah angka yang dikonfirmasi owner (dari BPN/bukti
    setor asli), bukan dipaksa sama dengan estimasi/saldo utang — sama
    seperti add_expense tidak memvalidasi jumlah terhadap sumber lain."""
    entry = post_journal(
        db, owner_id=owner_id, kode_debet="2140", kode_kredit="1113", nominal=amount,
        tanggal=deposit_date, sumber_dokumen=f"Setor PPh {deposit_date:%Y-%m}",
        keterangan=f"Penyetoran PPh Final UMKM 0,5% - {deposit_date:%Y-%m}",
        rule_no=29,
    )
    if entry is None:
        raise ValueError("Jumlah setoran harus lebih dari 0")
    return entry


def get_pph_summary(db: Session, owner_id: int, period: str) -> dict:
    gross_omset = _gross_omset_for_period(db, owner_id, period)
    estimated_pph = round(gross_omset * 0.005, 2)

    is_accrued = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner_id,
        JournalEntry.sumber_dokumen == _close_month_sumber_dokumen(period),
    ).first() is not None

    outstanding_utang = get_account_balance(db, get_account(db, owner_id, "2140"))
    if not is_accrued:
        status = "Belum Ada Akrual"
    elif outstanding_utang > 0:
        status = "Belum Disetor"
    else:
        status = "Sudah Disetor"

    return {
        "period": period,
        "gross_omset": gross_omset,
        "estimated_pph": estimated_pph,
        "is_accrued": is_accrued,
        "outstanding_utang": outstanding_utang,
        "status": status,
    }
