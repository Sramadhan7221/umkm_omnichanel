"""
Persistence-layer glue between CanonicalOrder (app.models.canonical) and the
OmniOrder ORM model. Direct port of the earlier Frappe omni_order.py
controller's upsert_from_canonical — same label maps, same logic, just
SQLAlchemy instead of frappe.get_doc/frappe.new_doc.
"""

from sqlalchemy.orm import Session

from app.models.canonical import CanonicalOrder
from app.models.db_models import OmniOrder, OmniOrderFee, OmniOrderItem

CHANNEL_LABELS = {
    # Nama platform/brand tetap dalam bahasa aslinya, tidak diterjemahkan.
    "shopee": "Shopee",
    "tiktok_shop": "TikTok Shop",
    "grabfood": "GrabFood",
    "gofood": "GoFood",
    "offline_pos": "Offline POS",
}

FULFILLMENT_LABELS = {
    "shipment": "Pengiriman",
    "instant_pickup": "Ambil Instan",
    "walk_in": "Transaksi Langsung",
}

STATUS_LABELS = {
    "new": "Baru",
    "accepted": "Diterima",
    "preparing": "Diproses",
    "ready_for_pickup": "Siap Diambil",
    "shipped": "Dikirim",
    "completed": "Selesai",
    "cancelled": "Dibatalkan",
    "refunded": "Dikembalikan",
}

FEE_CATEGORY_LABELS = {
    "commission": "Komisi",
    "payment_processing": "Biaya Pembayaran",
    "ads": "Iklan",
    "promo_subsidy": "Subsidi Promo",
    "logistics": "Logistik",
    "service_fee": "Biaya Layanan",
    "penalty": "Penalti",
    "other": "Lainnya",
}


def upsert_from_canonical(db: Session, order: CanonicalOrder) -> OmniOrder:
    """Create or update an OmniOrder row (+ its items/fees) from a
    CanonicalOrder instance. Mirrors what a real webhook handler would do
    once live platform adapters replace the mock ones."""

    db_order = db.get(OmniOrder, order.platform_order_id)
    if db_order is None:
        db_order = OmniOrder(platform_order_id=order.platform_order_id)
        db.add(db_order)

    db_order.channel = CHANNEL_LABELS[order.channel.value]
    db_order.fulfillment_type = FULFILLMENT_LABELS[order.fulfillment_type.value]
    db_order.status = STATUS_LABELS[order.status.value]
    db_order.raw_status = order.raw_status
    db_order.order_time = order.order_time.replace(tzinfo=None)
    db_order.updated_time = order.updated_time.replace(tzinfo=None)
    db_order.customer_ref = order.customer_ref
    db_order.payout_batch_ref = order.payout_batch_ref
    db_order.outlet_id = order.outlet_id
    db_order.gross_amount = float(order.gross_amount)
    db_order.net_amount = float(order.net_amount)

    db_order.items.clear()
    for item in order.items:
        db_order.items.append(OmniOrderItem(
            sku=item.sku,
            platform_item_id=item.platform_item_id,
            item_name=item.name,
            quantity=item.quantity,
            unit_price=float(item.unit_price),
            modifiers=", ".join(item.modifiers) if item.modifiers else "",
        ))

    db_order.fees.clear()
    for fee in order.fees:
        db_order.fees.append(OmniOrderFee(
            category=FEE_CATEGORY_LABELS[fee.category.value],
            amount=float(fee.amount),
            label=fee.label,
        ))

    db.commit()
    db.refresh(db_order)
    return db_order
