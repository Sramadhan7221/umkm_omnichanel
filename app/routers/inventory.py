"""
API routes for the Inventory Sync page. Two families of routes:

- The original Fase 2 set (list/adjust/movements) — untouched, same shape,
  since the catalog DataTable must keep showing exactly what it already
  shows (per the Fase 6 request).
- A new "/products" set (Fase 6) for full product CRUD: create with photos
  and platform selection, a single-page detail view, and edit with an audit
  trail.
"""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import require_role
from app.services.inventory_service import (
    adjust_stock,
    create_product,
    get_audit_log,
    get_movements,
    get_product_detail,
    get_products,
    update_product,
)

# Owner + Admin baseline (Admin's granted "update stok" capability lives
# here: list, adjust, movements, and the read-only detail lookup that backs
# the product detail page). Create/edit/audit routes below add an extra
# owner-only Depends on top — see Customer Request 1 Epic I Keputusan Scope
# CR1 §5.
router = APIRouter(
    prefix="/api/inventory", tags=["inventory"], dependencies=[Depends(require_role("owner", "admin"))]
)


class StockAdjustRequest(BaseModel):
    quantity: int
    note: str = ""


def _serialize_product_summary(p) -> dict:
    return {
        "sku": p.sku,
        "name": p.name,
        "reference_price": p.reference_price,
        "stock_qty": p.stock_qty,
        "low_stock_threshold": p.low_stock_threshold,
        "is_low_stock": p.stock_qty <= p.low_stock_threshold,
        "updated_time": p.updated_time.isoformat(sep=" ") if p.updated_time else None,
        "mappings": [
            {"channel": m.channel, "platform_item_id": m.platform_item_id}
            for m in p.mappings
        ],
    }


@router.get("")
def list_products(db: Session = Depends(get_db)):
    """Product catalog with current stock + mapped platform listings.

    Deliberately unchanged shape (Fase 6 requirement: adding product detail
    /edit features must not alter what the catalog DataTable displays)."""
    return [_serialize_product_summary(p) for p in get_products(db)]


@router.post("/{sku}/adjust")
def adjust_product_stock(sku: str, body: StockAdjustRequest, db: Session = Depends(get_db)):
    """Manual stock override (e.g. after a physical stock count)."""
    try:
        product = adjust_stock(db, sku, body.quantity, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "sku": product.sku,
        "stock_qty": product.stock_qty,
    }


@router.get("/{sku}/movements")
def product_stock_movements(sku: str, db: Session = Depends(get_db)):
    """Stock movement history (audit trail) for one SKU."""
    movements = get_movements(db, sku)
    return [
        {
            "change_qty": m.change_qty,
            "resulting_qty": m.resulting_qty,
            "source": m.source,
            "note": m.note,
            "created_time": m.created_time.isoformat(sep=" ") if m.created_time else None,
        }
        for m in movements
    ]


# ---------------------------------------------------------------------------
# Tambah / Detail / Edit Produk (Fase 6)
# ---------------------------------------------------------------------------

def _serialize_product_full(p) -> dict:
    return {
        "sku": p.sku,
        "name": p.name,
        "description": p.description or "",
        "reference_price": p.reference_price,
        "cogs_price": p.cogs_price,
        "unit_label": p.unit_label,
        "ppn_rate": p.ppn_rate,
        "stock_qty": p.stock_qty,
        "low_stock_threshold": p.low_stock_threshold,
        "updated_time": p.updated_time.isoformat(sep=" ") if p.updated_time else None,
        "mappings": [
            {"channel": m.channel, "platform_item_id": m.platform_item_id}
            for m in p.mappings
        ],
        "images": [
            {
                "id": img.id,
                "url": img.file_path,
                "is_primary": img.is_primary,
                "sort_order": img.sort_order,
            }
            for img in p.images
        ],
    }


@router.post("/products", dependencies=[Depends(require_role("owner"))])
def add_product(
    sku: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    stock_qty: int = Form(...),
    reference_price: float = Form(...),
    cogs_price: float = Form(...),
    unit_label: str = Form(...),
    ppn_rate: float = Form(11.0),
    channels: list[str] = Form([]),
    primary_image: UploadFile | None = File(None),
    gallery_images: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    """Create a new product for the selected platform(s), with photos."""
    try:
        product = create_product(
            db,
            sku=sku,
            name=name,
            description=description,
            stock_qty=stock_qty,
            reference_price=reference_price,
            cogs_price=cogs_price,
            unit_label=unit_label,
            ppn_rate=ppn_rate,
            channels=channels,
            primary_image=primary_image,
            gallery_images=gallery_images,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"sku": product.sku}


@router.get("/products/{sku}/detail")
def product_detail(sku: str, db: Session = Depends(get_db)):
    """Full product detail for the marketplace-style single-page view."""
    product = get_product_detail(db, sku)
    if product is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return _serialize_product_full(product)


@router.put("/products/{sku}", dependencies=[Depends(require_role("owner"))])
def edit_product(
    sku: str,
    name: str | None = Form(None),
    description: str | None = Form(None),
    stock_qty: int | None = Form(None),
    reference_price: float | None = Form(None),
    cogs_price: float | None = Form(None),
    unit_label: str | None = Form(None),
    ppn_rate: float | None = Form(None),
    remove_image_ids: str = Form("[]"),  # JSON-encoded list[int], sent as a single form field
    note: str = Form(""),
    new_primary_image: UploadFile | None = File(None),
    new_gallery_images: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    """Edit name/stock/price/description/images — every change lands in the
    product's ProductAuditLog (Fase 6 requirement)."""
    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if stock_qty is not None:
        updates["stock_qty"] = stock_qty
    if reference_price is not None:
        updates["reference_price"] = reference_price
    if cogs_price is not None:
        updates["cogs_price"] = cogs_price
    if unit_label is not None:
        updates["unit_label"] = unit_label
    if ppn_rate is not None:
        updates["ppn_rate"] = ppn_rate

    try:
        remove_ids = [int(i) for i in json.loads(remove_image_ids or "[]")]
    except (ValueError, TypeError):
        remove_ids = []

    try:
        product = update_product(
            db,
            sku,
            updates,
            new_primary_image=new_primary_image,
            new_gallery_images=new_gallery_images,
            remove_image_ids=remove_ids,
            note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return _serialize_product_full(product)


@router.get("/products/{sku}/audit", dependencies=[Depends(require_role("owner"))])
def product_audit_trail(sku: str, db: Session = Depends(get_db)):
    """Edit history (name/price/description/image changes) for one SKU."""
    logs = get_audit_log(db, sku)
    return [
        {
            "changed_fields": json.loads(log.changed_fields),
            "note": log.note,
            "changed_time": log.changed_time.isoformat(sep=" ") if log.changed_time else None,
        }
        for log in logs
    ]
