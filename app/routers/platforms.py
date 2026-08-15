"""
API routes for the Platform management page (Fase 5): list platforms and
toggle their active/inactive status.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import require_role
from app.services.platform_service import list_platforms, set_active

router = APIRouter(prefix="/api/platforms", tags=["platforms"], dependencies=[Depends(require_role("owner"))])


class ToggleRequest(BaseModel):
    is_active: bool


@router.get("")
def list_all(db: Session = Depends(get_db)):
    platforms = list_platforms(db)
    return [
        {
            "code": p.code,
            "name": p.name,
            "fulfillment_type": p.fulfillment_type,
            "is_active": p.is_active,
            "fee_rate": p.fee_rate,
        }
        for p in platforms
    ]


@router.post("/{code}/toggle")
def toggle(code: str, body: ToggleRequest, db: Session = Depends(get_db)):
    try:
        platform = set_active(db, code, body.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"code": platform.code, "is_active": platform.is_active}
