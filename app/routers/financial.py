"""
API routes for the Financial Reports page: Laba Rugi and Neraca (from
account balances, Epic F), PPh Final accrual/deposit (Epic E), and manual
Expense entries — filtered by a start/end date range or as_of cutoff.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Account
from app.routers.auth import require_role
from app.services.balance_sheet_service import get_balance_sheet, get_kas_per_outlet, get_profit_loss
from app.services.chart_of_accounts_service import list_accounts_grouped
from app.services.export_service import export_balance_sheet, export_journal, export_profit_loss
from app.services.financial_service import (
    add_expense,
    close_month_pph,
    get_pph_summary,
    list_expenses,
    record_pph_deposit,
)
from app.services.journal_engine_service import list_expense_rules, list_journal_entries
from app.services.tenant_context import get_tenant_id

router = APIRouter(prefix="/api/financial", tags=["financial"], dependencies=[Depends(require_role("owner"))])


def _resolve_period(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    """Default to the last 30 days if no range is given."""
    end_dt = datetime.fromisoformat(end) + timedelta(days=1) if end else datetime.utcnow()
    start_dt = datetime.fromisoformat(start) if start else end_dt - timedelta(days=30)
    return start_dt, end_dt


class ExpenseCreateRequest(BaseModel):
    category: str
    amount: float
    note: str = ""
    expense_date: str  # "YYYY-MM-DD"
    rule_no: int
    outlet_id: str | None = None


@router.get("/accounts")
def accounts(db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id)):
    return list_accounts_grouped(db, owner_id)


@router.get("/expenses")
def expenses(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    start_dt, end_dt = _resolve_period(start, end)
    items = list_expenses(db, owner_id, start_dt, end_dt)
    return [
        {
            "id": e.id,
            "category": e.category,
            "amount": e.amount,
            "note": e.note,
            "expense_date": e.expense_date.date().isoformat(),
        }
        for e in items
    ]


@router.post("/expenses")
def create_expense(
    body: ExpenseCreateRequest, db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id),
):
    expense_date = datetime.fromisoformat(body.expense_date)
    try:
        expense = add_expense(
            db, owner_id, body.category, body.amount, body.note, expense_date,
            rule_no=body.rule_no, outlet_id=body.outlet_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": expense.id}


@router.get("/expense-rules")
def expense_rules(db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id)):
    rules = list_expense_rules(db)
    kredit_accounts = {a.kode_akun: a for a in db.query(Account).filter(
        Account.owner_id == owner_id, Account.kode_akun.in_({r.kode_kredit for r in rules})
    ).all()}
    return [
        {
            "no": r.no,
            "event_trigger": r.event_trigger,
            "kode_debet": r.kode_debet,
            "nama_akun_debet": r.nama_akun_debet,
            "kode_kredit": r.kode_kredit,
            "nama_akun_kredit": r.nama_akun_kredit,
            # Data-driven: whether picking this rule must also require an
            # outlet, derived from the credit account's is_outlet_scoped
            # flag (e.g. 1111 Kas di Tangan) instead of a hardcoded rule no.
            "outlet_required": kredit_accounts[r.kode_kredit].is_outlet_scoped,
        }
        for r in rules
    ]


class CloseMonthRequest(BaseModel):
    period: str  # "YYYY-MM"


class PphDepositRequest(BaseModel):
    amount: float
    deposit_date: str  # "YYYY-MM-DD"


@router.get("/pph/summary")
def pph_summary(
    period: str | None = Query(default=None), db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id),
):
    period = period or f"{datetime.utcnow():%Y-%m}"
    return get_pph_summary(db, owner_id, period)


@router.post("/pph/close-month")
def pph_close_month(
    body: CloseMonthRequest, db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id),
):
    try:
        entry = close_month_pph(db, owner_id, body.period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"no_jurnal": entry.no_jurnal, "nominal": entry.nominal}


@router.post("/pph/deposit")
def pph_deposit(
    body: PphDepositRequest, db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id),
):
    deposit_date = datetime.fromisoformat(body.deposit_date)
    try:
        entry = record_pph_deposit(db, owner_id, body.amount, deposit_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"no_jurnal": entry.no_jurnal, "nominal": entry.nominal}


@router.get("/profit-loss")
def profit_loss(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    start_dt, end_dt = _resolve_period(start, end)
    return get_profit_loss(db, owner_id, start_dt, end_dt)


@router.get("/profit-loss/export")
def profit_loss_export(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    format: str = Query(default="pdf"),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    start_dt, end_dt = _resolve_period(start, end)
    data = get_profit_loss(db, owner_id, start_dt, end_dt)
    try:
        content, media_type, ext = export_profit_loss(data, format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    filename = f"laba_rugi_{start_dt.date()}_{end_dt.date()}.{ext}"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/balance-sheet")
def balance_sheet(
    as_of: str | None = Query(default=None),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    # Same "whole day inclusive" convention as _resolve_period's `end` handling.
    as_of_dt = datetime.fromisoformat(as_of) + timedelta(days=1) if as_of else datetime.utcnow()
    return get_balance_sheet(db, owner_id, as_of_dt)


@router.get("/balance-sheet/export")
def balance_sheet_export(
    as_of: str | None = Query(default=None),
    format: str = Query(default="pdf"),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    as_of_dt = datetime.fromisoformat(as_of) + timedelta(days=1) if as_of else datetime.utcnow()
    data = get_balance_sheet(db, owner_id, as_of_dt)
    try:
        content, media_type, ext = export_balance_sheet(data, format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    filename = f"neraca_{as_of_dt.date()}.{ext}"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/kas-per-outlet")
def kas_per_outlet(db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id)):
    """Backs the /outlets page's real cash-per-outlet report — see
    balance_sheet_service.get_kas_per_outlet."""
    return get_kas_per_outlet(db, owner_id)


@router.get("/journal")
def journal(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    start_dt, end_dt = _resolve_period(start, end)
    entries = list_journal_entries(db, owner_id, start_dt, end_dt)
    return [
        {
            "no_jurnal": e.no_jurnal,
            "tanggal": e.tanggal.isoformat(sep=" "),
            "sumber_dokumen": e.sumber_dokumen,
            "kode_debet": e.kode_debet,
            "nama_akun_debet": e.nama_akun_debet,
            "kode_kredit": e.kode_kredit,
            "nama_akun_kredit": e.nama_akun_kredit,
            "nominal": e.nominal,
            "keterangan": e.keterangan,
            "status": e.status,
        }
        for e in entries
    ]


@router.get("/journal/export")
def journal_export(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    format: str = Query(default="pdf"),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    start_dt, end_dt = _resolve_period(start, end)
    entries = list_journal_entries(db, owner_id, start_dt, end_dt)
    try:
        content, media_type, ext = export_journal(entries, start_dt, end_dt, format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    filename = f"jurnal_transaksi_{start_dt.date()}_{end_dt.date()}.{ext}"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
