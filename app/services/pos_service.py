"""
POS Kasir service (Epic C) — manual cash-register sales for physical
outlets. Unlike the other 4 channels, a nota isn't synced from a platform
adapter: the cashier picks items straight from Master Barang (Epic D,
read-only pricing — Keputusan Scope 3) and the sale is completed
immediately, no multi-day/multi-minute state machine.

Reuses the exact same ingestion pipeline online orders go through
(upsert_from_canonical -> deduct_stock_for_order -> journal posting) by
building a CanonicalOrder for the nota, so Order Inbox / Inventory / Jurnal
Transaksi all show POS sales through the same code paths as every other
channel — see app/routers/api.py::_ingest_order for the online-order
equivalent of this same three-step sequence.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.canonical import CanonicalOrder, Channel, FulfillmentType, OrderItem, OrderStatus
from app.models.db_models import JournalEntry, OmniOrder, Outlet, TransactionMappingRule
from app.services.inventory_service import deduct_stock_for_order, get_product
from app.services.journal_engine_service import POS_PAYMENT_RULE_NOS, post_pos_sale_journal
from app.services.order_service import get_order, upsert_from_canonical


def generate_nota_number(db: Session, owner_id: int) -> str:
    prefix = f"NT-{datetime.utcnow():%Y%m}"
    existing = (
        db.query(OmniOrder)
        .filter(OmniOrder.owner_id == owner_id, OmniOrder.platform_order_id.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{existing + 1:03d}"


def create_pos_sale(
    db: Session,
    owner_id: int,
    outlet_id: str,
    rule_no: int,
    items: list[dict],
    customer_ref: str = "",
) -> OmniOrder:
    outlet = db.get(Outlet, outlet_id)
    if outlet is None or not outlet.is_active:
        raise ValueError("Pilih outlet aktif sebelum membuat nota")

    if rule_no not in POS_PAYMENT_RULE_NOS:
        raise ValueError(f"Metode pembayaran (rule_no={rule_no}) tidak dikenal")

    if not items:
        raise ValueError("Nota harus punya minimal 1 barang")

    order_items = []
    for line in items:
        product = get_product(db, owner_id, line["sku"])
        if product is None:
            raise ValueError(f"SKU '{line['sku']}' tidak ditemukan di Master Barang")
        qty = int(line["qty"])
        if qty <= 0:
            raise ValueError(f"Qty untuk '{product.name}' harus lebih dari 0")
        if product.stock_qty < qty:
            raise ValueError(f"Stok '{product.name}' tidak cukup (tersedia {product.stock_qty})")
        order_items.append(OrderItem(
            sku=product.sku, platform_item_id=product.sku, name=product.name,
            quantity=qty, unit_price=Decimal(str(product.reference_price)),
        ))

    gross_amount = sum(item.unit_price * item.quantity for item in order_items)
    now = datetime.utcnow()
    nota_no = generate_nota_number(db, owner_id)

    canonical_order = CanonicalOrder(
        order_id=str(uuid.uuid4()),
        platform_order_id=nota_no,
        channel=Channel.OFFLINE_POS,
        fulfillment_type=FulfillmentType.WALK_IN,
        status=OrderStatus.COMPLETED,
        items=order_items,
        fees=[],
        gross_amount=gross_amount,
        net_amount=gross_amount,
        order_time=now,
        updated_time=now,
        customer_ref=customer_ref or "Umum",
        raw_status="completed",
        outlet_id=outlet_id,
    )

    db_order = upsert_from_canonical(db, owner_id, canonical_order)
    deduct_stock_for_order(db, owner_id, canonical_order)
    post_pos_sale_journal(db, db_order, rule_no)
    return db_order


def get_receipt(db: Session, owner_id: int, platform_order_id: str) -> dict | None:
    order = get_order(db, owner_id, platform_order_id)
    if order is None or order.channel != "Offline POS":
        return None

    outlet = db.get(Outlet, order.outlet_id) if order.outlet_id else None
    payment_entry = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.owner_id == owner_id,
            JournalEntry.order_id == platform_order_id, JournalEntry.rule_no.in_(POS_PAYMENT_RULE_NOS),
        )
        .first()
    )
    payment_rule = db.get(TransactionMappingRule, payment_entry.rule_no) if payment_entry else None

    return {
        "no_nota": order.platform_order_id,
        "tanggal": order.order_time.isoformat(sep=" "),
        "nama_pelanggan": order.customer_ref,
        "metode_pembayaran": payment_rule.event_trigger if payment_rule else "-",
        "outlet_nama": outlet.nama_outlet if outlet else "-",
        "outlet_alamat": outlet.alamat if outlet else "",
        "items": [
            {
                "sku": i.sku, "nama_barang": i.item_name,
                "qty": i.quantity, "harga_satuan": i.unit_price,
                "total_harga": i.unit_price * i.quantity,
            }
            for i in order.items
        ],
        "total": order.gross_amount,
    }
