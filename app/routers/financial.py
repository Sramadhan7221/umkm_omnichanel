"""
API routes for the Financial Reports page (Fase 3): Income Statement, Cash
Flow, and manual Expense entries — all filtered by a start/end date range.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import require_login_api
from app.services.chart_of_accounts_service import list_accounts_grouped
from app.services.financial_service import (
    add_expense,
    get_cash_flow,
    get_income_statement,
    list_expenses,
)

router = APIRouter(prefix="/api/financial", tags=["financial"], dependencies=[Depends(require_login_api)])


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


@router.get("/income-statement")
def income_statement(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    start_dt, end_dt = _resolve_period(start, end)
    return get_income_statement(db, start_dt, end_dt)


@router.get("/cash-flow")
def cash_flow(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    start_dt, end_dt = _resolve_period(start, end)
    return get_cash_flow(db, start_dt, end_dt)


@router.get("/accounts")
def accounts(db: Session = Depends(get_db)):
    return list_accounts_grouped(db)


@router.get("/expenses")
def expenses(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    start_dt, end_dt = _resolve_period(start, end)
    items = list_expenses(db, start_dt, end_dt)
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
def create_expense(body: ExpenseCreateRequest, db: Session = Depends(get_db)):
    expense_date = datetime.fromisoformat(body.expense_date)
    expense = add_expense(db, body.category, body.amount, body.note, expense_date)
    return {"id": expense.id}
