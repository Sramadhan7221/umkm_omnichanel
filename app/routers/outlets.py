"""
API routes for the Outlet management page (Epic H): list outlets, add a new
one, and toggle active status.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import require_role
from app.services.outlet_service import create_outlet, list_outlets, set_active

router = APIRouter(prefix="/api/outlets", tags=["outlets"], dependencies=[Depends(require_role("owner"))])


class CreateRequest(BaseModel):
    nama_outlet: str
    alamat: str = ""


class ToggleRequest(BaseModel):
    is_active: bool


def _serialize(outlet):
    return {
        "kode_outlet": outlet.kode_outlet,
        "nama_outlet": outlet.nama_outlet,
        "alamat": outlet.alamat,
        "is_active": outlet.is_active,
    }


@router.get("")
def list_all(db: Session = Depends(get_db)):
    return [_serialize(o) for o in list_outlets(db)]


@router.post("")
def create(body: CreateRequest, db: Session = Depends(get_db)):
    outlet = create_outlet(db, body.nama_outlet, body.alamat)
    return _serialize(outlet)


@router.post("/{code}/toggle")
def toggle(code: str, body: ToggleRequest, db: Session = Depends(get_db)):
    try:
        outlet = set_active(db, code, body.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _serialize(outlet)
