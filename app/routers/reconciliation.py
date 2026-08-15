"""
API routes for the Reconciliation page (Fase 4): generate settlements,
summary stats, and the settlement list with match/mismatch filtering.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import require_role
from app.services.reconciliation_service import (
    generate_settlements,
    get_reconciliation_summary,
    list_settlements,
)
from app.services.tenant_context import get_tenant_id

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"], dependencies=[Depends(require_role("owner"))])


def _resolve_period(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    end_dt = datetime.fromisoformat(end) + timedelta(days=1) if end else datetime.utcnow()
    start_dt = datetime.fromisoformat(start) if start else end_dt - timedelta(days=30)
    return start_dt, end_dt


@router.post("/generate")
def generate(db: Session = Depends(get_db), owner_id: int = Depends(get_tenant_id)):
    """Simulate importing a new platform payout batch for any order that
    doesn't have a settlement yet."""
    created = generate_settlements(db, owner_id)
    return {"created": created}


@router.get("/summary")
def summary(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    start_dt, end_dt = _resolve_period(start, end)
    return get_reconciliation_summary(db, owner_id, start_dt, end_dt)


@router.get("/settlements")
def settlements(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    owner_id: int = Depends(get_tenant_id),
):
    start_dt, end_dt = _resolve_period(start, end)
    items = list_settlements(db, owner_id, start_dt, end_dt, status)
    return [
        {
            "settlement_id": s.settlement_id,
            "platform_order_id": s.platform_order_id,
            "channel": s.channel,
            "expected_amount": s.expected_amount,
            "payout_amount": s.payout_amount,
            "diff_amount": s.diff_amount,
            "status": s.status,
            "batch_ref": s.batch_ref,
            "settlement_date": s.settlement_date.isoformat(sep=" "),
        }
        for s in items
    ]
