"""
API routes for the POS Kasir page (Epic C): payment method list and nota
creation/reprint. Outlet and product pickers reuse the existing
/api/outlets and /api/inventory endpoints from the frontend directly —
no duplicate listing endpoints here.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import require_role
from app.services.journal_engine_service import list_pos_payment_rules
from app.services.pos_service import create_pos_sale, get_receipt

router = APIRouter(prefix="/api/pos", tags=["pos"], dependencies=[Depends(require_role("owner", "admin"))])


class SaleItem(BaseModel):
    sku: str
    qty: int


class SaleCreateRequest(BaseModel):
    outlet_id: str
    rule_no: int
    customer_ref: str = ""
    items: list[SaleItem]


@router.get("/payment-methods")
def payment_methods(db: Session = Depends(get_db)):
    return [
        {
            "no": r.no,
            "event_trigger": r.event_trigger,
            "kode_debet": r.kode_debet,
            "nama_akun_debet": r.nama_akun_debet,
        }
        for r in list_pos_payment_rules(db)
    ]


@router.post("/sales")
def create_sale(body: SaleCreateRequest, db: Session = Depends(get_db)):
    try:
        order = create_pos_sale(
            db, outlet_id=body.outlet_id, rule_no=body.rule_no,
            items=[item.model_dump() for item in body.items],
            customer_ref=body.customer_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return get_receipt(db, order.platform_order_id)


@router.get("/sales/{nota_no}")
def get_sale_receipt(nota_no: str, db: Session = Depends(get_db)):
    receipt = get_receipt(db, nota_no)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Nota tidak ditemukan")
    return receipt
