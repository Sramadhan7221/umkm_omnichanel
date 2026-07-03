"""
Financial engine (Fase 3 dari roadmap) — Income Statement dan Cash Flow
dihitung langsung dari OmniOrder/OmniOrderFee yang sudah ada (hasil sinkron
Order Inbox), digabung dengan pencatatan Expense manual untuk sisi biaya
operasional yang tidak datang dari platform manapun.

Catatan cakupan (lihat blueprint Section 2 "Out of Scope"): ini laporan
ringkas yang bisa langsung dipakai MSME, BUKAN pembukuan double-entry
lengkap/standar akuntansi formal — itu sengaja di luar cakupan MVP.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import Expense, OmniOrder


def get_income_statement(db: Session, start: datetime, end: datetime) -> dict:
    orders = (
        db.query(OmniOrder)
        .filter(OmniOrder.order_time >= start, OmniOrder.order_time <= end)
        .all()
    )

    gross_revenue = sum(o.gross_amount for o in orders)
    net_revenue = sum(o.net_amount for o in orders)
    total_fees = gross_revenue - net_revenue

    fees_by_category: dict[str, float] = {}
    channel_breakdown: dict[str, dict] = {}
    for o in orders:
        bucket = channel_breakdown.setdefault(o.channel, {"gross": 0.0, "net": 0.0, "count": 0})
        bucket["gross"] += o.gross_amount
        bucket["net"] += o.net_amount
        bucket["count"] += 1
        for fee in o.fees:
            fees_by_category[fee.category] = fees_by_category.get(fee.category, 0.0) + fee.amount

    expenses = (
        db.query(Expense)
        .filter(Expense.expense_date >= start, Expense.expense_date <= end)
        .all()
    )
    total_expenses = sum(e.amount for e in expenses)
    net_profit = net_revenue - total_expenses

    return {
        "period": {"start": start.isoformat(sep=" "), "end": end.isoformat(sep=" ")},
        "order_count": len(orders),
        "gross_revenue": gross_revenue,
        "total_fees": total_fees,
        "fees_by_category": fees_by_category,
        "net_revenue": net_revenue,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "channel_breakdown": [
            {"channel": channel, **figures} for channel, figures in channel_breakdown.items()
        ],
    }


def get_cash_flow(db: Session, start: datetime, end: datetime) -> list[dict]:
    """Simplified daily cash flow: cash-in = net_amount of orders placed that
    day (a rough proxy for payout — real settlement timing differs per
    platform, see Fase 4 Reconciliation), cash-out = expenses recorded that
    day."""
    orders = (
        db.query(OmniOrder)
        .filter(OmniOrder.order_time >= start, OmniOrder.order_time <= end)
        .all()
    )
    expenses = (
        db.query(Expense)
        .filter(Expense.expense_date >= start, Expense.expense_date <= end)
        .all()
    )

    by_day: dict[str, dict] = {}
    for o in orders:
        day = o.order_time.date().isoformat()
        by_day.setdefault(day, {"cash_in": 0.0, "cash_out": 0.0})
        by_day[day]["cash_in"] += o.net_amount
    for e in expenses:
        day = e.expense_date.date().isoformat()
        by_day.setdefault(day, {"cash_in": 0.0, "cash_out": 0.0})
        by_day[day]["cash_out"] += e.amount

    rows = []
    for day in sorted(by_day.keys()):
        cash_in = by_day[day]["cash_in"]
        cash_out = by_day[day]["cash_out"]
        rows.append({"date": day, "cash_in": cash_in, "cash_out": cash_out, "net": cash_in - cash_out})
    return rows


def add_expense(db: Session, category: str, amount: float, note: str, expense_date: datetime) -> Expense:
    expense = Expense(category=category, amount=amount, note=note, expense_date=expense_date)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def list_expenses(db: Session, start: datetime, end: datetime) -> list[Expense]:
    return (
        db.query(Expense)
        .filter(Expense.expense_date >= start, Expense.expense_date <= end)
        .order_by(Expense.expense_date.desc())
        .all()
    )
