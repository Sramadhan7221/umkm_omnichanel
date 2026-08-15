"""
Superadmin API routes (Customer Request 1 Epic J): registration approval +
dashboard data. Superadmin has zero business-data access (CR1 Keputusan
Scope §4) — this router is the entirety of their surface area.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import require_role
from app.services.user_admin_service import (
    approve_owner,
    deactivate_owner,
    get_owner_stats,
    list_pending_owners,
    reactivate_owner,
    reject_owner,
)

router = APIRouter(
    prefix="/api/superadmin", tags=["superadmin"], dependencies=[Depends(require_role("superadmin"))]
)


def _serialize(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "business_name": user.business_name,
        "created_time": user.created_time.isoformat(sep=" ") if user.created_time else None,
    }


@router.get("/owners/pending")
def owners_pending(db: Session = Depends(get_db)):
    return [_serialize(u) for u in list_pending_owners(db)]


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    return get_owner_stats(db)


@router.post("/users/{user_id}/approve")
def approve(user_id: int, db: Session = Depends(get_db)):
    try:
        user = approve_owner(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(user)


@router.post("/users/{user_id}/reject")
def reject(user_id: int, db: Session = Depends(get_db)):
    try:
        user = reject_owner(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(user)


@router.post("/users/{user_id}/deactivate")
def deactivate(user_id: int, db: Session = Depends(get_db)):
    try:
        user = deactivate_owner(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(user)


@router.post("/users/{user_id}/reactivate")
def reactivate(user_id: int, db: Session = Depends(get_db)):
    try:
        user = reactivate_owner(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(user)
