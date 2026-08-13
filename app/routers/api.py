"""
API routes backing the Order Inbox page.

sync_mock_orders now generates +1 new order for EACH currently active
platform (Fase 5 Platform management), picking random items from that
platform's own mapped product catalog (Fase 2 Inventory) rather than an
adapter's hardcoded sample list — so toggling a platform on/off in
/platforms directly changes what this button does.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.mock_adapters.mock_gofood import MockGoFoodAdapter
from app.mock_adapters.mock_grabfood import MockGrabFoodAdapter
from app.mock_adapters.mock_shopee import MockShopeeAdapter
from app.mock_adapters.mock_tiktokshop import MockTikTokShopAdapter
from app.models.db_models import OmniOrder
from app.routers.auth import require_login_api
from app.services.inventory_service import deduct_stock_for_order, get_products_for_channel
from app.services.journal_engine_service import post_order_completed_journal, post_order_refunded_journal
from app.services.order_service import upsert_from_canonical
from app.services.platform_service import list_active_platforms

router = APIRouter(prefix="/api", tags=["orders"], dependencies=[Depends(require_login_api)])

_ADAPTER_REGISTRY = {
    "shopee": MockShopeeAdapter,
    "tiktok_shop": MockTikTokShopAdapter,
    "grabfood": MockGrabFoodAdapter,
    "gofood": MockGoFoodAdapter,
}


def _ingest_order(db: Session, canonical_order) -> None:
    """Upsert an order, then deduct stock and post journal entries ONLY the
    first time this order is seen — otherwise re-syncing would decrement
    stock / double-post journals for an order that already existed
    (blueprint Section 3.5: outbound stock sync should fire once per real
    order event, not once per poll; same principle applies to the Journal
    Engine, Epic B)."""
    is_new = db.get(OmniOrder, canonical_order.platform_order_id) is None
    db_order = upsert_from_canonical(db, canonical_order)
    if is_new:
        deduct_stock_for_order(db, canonical_order)
        if db_order.status == "Selesai":
            post_order_completed_journal(db, db_order)
        elif db_order.status == "Dikembalikan":
            post_order_refunded_journal(db, db_order)


def _sync_mock_orders(db: Session, per_platform: int = 1) -> dict:
    """Generate `per_platform` new order(s) for every currently active
    platform, using that platform's own mapped products. Platforms with no
    adapter implemented, or no products mapped yet, are skipped (and
    reported as such) rather than erroring the whole sync."""
    results: dict[str, str] = {}

    for platform in list_active_platforms(db):
        adapter_cls = _ADAPTER_REGISTRY.get(platform.code)
        if adapter_cls is None:
            results[platform.name] = "adapter belum tersedia"
            continue

        products = get_products_for_channel(db, platform.name)
        if not products:
            results[platform.name] = "belum ada produk terpetakan ke platform ini"
            continue

        adapter = adapter_cls()
        adapter.authenticate({"store_id": f"demo-{platform.code}"})

        created = 0
        for _ in range(per_platform):
            raw = adapter.generate_raw_order(products=products)
            _ingest_order(db, adapter.normalize_order(raw))
            created += 1
        results[platform.name] = f"{created} pesanan baru"

    return results


@router.post("/sync-mock-orders")
def sync_mock_orders(db: Session = Depends(get_db)):
    """Add one new order per active platform, from that platform's mapped products."""
    return {"result": _sync_mock_orders(db)}


@router.get("/order-inbox")
def get_order_inbox(db: Session = Depends(get_db)):
    """Flat list of orders for the unified Order Inbox DataTable."""
    orders = db.query(OmniOrder).order_by(desc(OmniOrder.order_time)).all()
    return [
        {
            "name": o.platform_order_id,
            "platform_order_id": o.platform_order_id,
            "channel": o.channel,
            "fulfillment_type": o.fulfillment_type,
            "status": o.status,
            "order_time": o.order_time.isoformat(sep=" "),
            "customer_ref": o.customer_ref,
            "gross_amount": o.gross_amount,
            "net_amount": o.net_amount,
        }
        for o in orders
    ]


@router.get("/order/{platform_order_id}")
def get_order_detail(platform_order_id: str, db: Session = Depends(get_db)):
    """Full order detail (items + fees) for the inbox's detail modal."""
    o = db.get(OmniOrder, platform_order_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "platform_order_id": o.platform_order_id,
        "channel": o.channel,
        "fulfillment_type": o.fulfillment_type,
        "status": o.status,
        "raw_status": o.raw_status,
        "order_time": o.order_time.isoformat(sep=" "),
        "customer_ref": o.customer_ref,
        "gross_amount": o.gross_amount,
        "net_amount": o.net_amount,
        "items": [
            {
                "sku": i.sku,
                "item_name": i.item_name,
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "modifiers": i.modifiers,
            }
            for i in o.items
        ],
        "fees": [
            {"category": f.category, "amount": f.amount, "label": f.label}
            for f in o.fees
        ],
    }
