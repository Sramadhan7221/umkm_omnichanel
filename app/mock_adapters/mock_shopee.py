"""
MockShopeeAdapter — generates dummy order/settlement payloads shaped like
Shopee Open Platform v2's `get_order_detail` + `get_escrow_detail` responses,
and normalizes them into CanonicalOrder.

IMPORTANT — provenance note: field names below (order_sn, order_status,
item_list, escrow_amount, commission_fee, buyer_paid_shipping_fee, etc.) are
taken from Shopee Open Platform v2 public API documentation and community SDK
references. They represent the real response shape closely, but since this
project currently has no live API access (business-registration blocker),
treat these as "best-effort realistic" rather than byte-exact — re-verify
against the live docs once real API access is obtained (see blueprint
Section 3.0, "future work" note).
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.mock_adapters.base import AuthSession, PlatformAdapter, SyncResult
from app.models.canonical import (
    CanonicalOrder,
    Channel,
    Fee,
    FeeCategory,
    FulfillmentType,
    OrderItem,
    OrderStatus,
    SettlementRecord,
)

# Real Shopee order_status values (subset relevant to a normal happy-path + cancel flow)
_SHOPEE_STATUS_MAP = {
    "UNPAID": OrderStatus.NEW,
    "READY_TO_SHIP": OrderStatus.ACCEPTED,
    "PROCESSED": OrderStatus.ACCEPTED,
    "SHIPPED": OrderStatus.SHIPPED,
    "COMPLETED": OrderStatus.COMPLETED,
    "CANCELLED": OrderStatus.CANCELLED,
    "TO_RETURN": OrderStatus.REFUNDED,
}

_SAMPLE_PRODUCTS = [
    ("SKU-BAJU-001", "Kaos Polos Katun Combed", 75_000),
    ("SKU-TAS-014", "Tas Selempang Kanvas", 120_000),
    ("SKU-SPT-007", "Sepatu Sneakers Casual", 210_000),
    ("SKU-AKS-022", "Gelang Kulit Handmade", 45_000),
]


class MockShopeeAdapter(PlatformAdapter):
    channel_name = "shopee"

    # Overridable in subclasses that reuse this e-commerce-style generator
    # for a different platform (see MockTikTokShopAdapter).
    _channel_enum = Channel.SHOPEE
    _order_prefix = "SP"

    def authenticate(self, credentials: dict[str, Any]) -> AuthSession:
        store_id = credentials.get("store_id", "demo-shopee-store")
        return AuthSession(store_id=store_id, access_token=f"mock-shopee-{uuid.uuid4().hex[:8]}")

    # ---- Dummy data generation -------------------------------------------------

    def generate_raw_order(
        self,
        status: str | None = None,
        products: list[tuple[str, str, float]] | None = None,
    ) -> dict[str, Any]:
        """Produce a raw payload shaped like Shopee's get_order_detail response.

        `products` is an optional list of (sku, name, price) tuples to pick
        items from — when given (e.g. the user's own mapped product catalog
        for this platform), it's used instead of the built-in sample catalog.
        """
        status = status or random.choice(list(_SHOPEE_STATUS_MAP.keys()))
        order_time = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 3))

        catalog = products if products else _SAMPLE_PRODUCTS
        num_items = min(random.randint(1, 3), len(catalog))
        chosen = random.sample(catalog, num_items)
        item_list = []
        subtotal = 0
        for sku, name, price in chosen:
            qty = random.randint(1, 2)
            item_list.append({
                "item_id": random.randint(10_000_000, 99_999_999),
                "item_name": name,
                "item_sku": sku,
                "model_id": random.randint(1_000_000, 9_999_999),
                "model_name": "Default",
                "model_sku": sku,
                "model_quantity_purchased": qty,
                "model_discounted_price": price,
                "model_original_price": price,
            })
            subtotal += price * qty

        buyer_paid_shipping_fee = random.choice([0, 9_000, 15_000])
        commission_fee = round(subtotal * 0.02)          # ~2% Shopee commission
        service_fee = round(subtotal * 0.028)            # ~2.8% payment/service fee
        seller_discount = random.choice([0, 5_000])
        escrow_amount = subtotal - commission_fee - service_fee - seller_discount

        return {
            "order_sn": f"{self._order_prefix}{uuid.uuid4().hex[:10].upper()}",
            "region": "ID",
            "currency": "IDR",
            "cod": False,
            "order_status": status,
            "shipping_carrier": random.choice(["JNE", "SiCepat", "J&T Express"]),
            "payment_method": "ShopeePay",
            "total_amount": subtotal + buyer_paid_shipping_fee,
            "buyer_user_id": random.randint(1_000_000, 9_999_999),
            "buyer_username": f"buyer_{uuid.uuid4().hex[:6]}",
            "create_time": int(order_time.timestamp()),
            "pay_time": int(order_time.timestamp()) + 60,
            "item_list": item_list,
            # escrow-detail-shaped fee breakdown, normally a separate API call
            # (get_escrow_detail) but inlined here for demo simplicity
            "escrow_detail": {
                "order_income": {
                    "escrow_amount": escrow_amount,
                    "buyer_total_amount": subtotal + buyer_paid_shipping_fee,
                    "original_price": subtotal,
                    "seller_discount": seller_discount,
                    "commission_fee": commission_fee,
                    "service_fee": service_fee,
                    "buyer_paid_shipping_fee": buyer_paid_shipping_fee,
                }
            },
        }

    def generate_raw_settlement(self, raw_order: dict[str, Any]) -> dict[str, Any]:
        """Produce a raw payload shaped like a Shopee payout/settlement line item."""
        income = raw_order["escrow_detail"]["order_income"]
        return {
            "settlement_id": f"SETL-{uuid.uuid4().hex[:8].upper()}",
            "order_sn": raw_order["order_sn"],
            "payout_amount": income["escrow_amount"],
            "commission_fee": income["commission_fee"],
            "service_fee": income["service_fee"],
            "settlement_time": int(datetime.now(timezone.utc).timestamp()),
            "batch_no": f"BATCH-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        }

    # ---- Adapter contract implementation ---------------------------------------

    def fetch_orders(self, since: Any) -> list[dict[str, Any]]:
        return [self.generate_raw_order() for _ in range(random.randint(2, 5))]

    def normalize_order(self, raw_order: dict[str, Any]) -> CanonicalOrder:
        income = raw_order["escrow_detail"]["order_income"]
        items = [
            OrderItem(
                sku=i["item_sku"],
                platform_item_id=str(i["item_id"]),
                name=i["item_name"],
                quantity=i["model_quantity_purchased"],
                unit_price=Decimal(i["model_discounted_price"]),
            )
            for i in raw_order["item_list"]
        ]
        fees = [
            Fee(FeeCategory.COMMISSION, Decimal(income["commission_fee"]), "commission_fee"),
            Fee(FeeCategory.PAYMENT_PROCESSING, Decimal(income["service_fee"]), "service_fee"),
        ]
        if income.get("seller_discount"):
            fees.append(Fee(FeeCategory.PROMO_SUBSIDY, Decimal(income["seller_discount"]), "seller_discount"))

        order_time = datetime.fromtimestamp(raw_order["create_time"], tz=timezone.utc)
        return CanonicalOrder(
            order_id=str(uuid.uuid4()),
            platform_order_id=raw_order["order_sn"],
            channel=self._channel_enum,
            fulfillment_type=FulfillmentType.SHIPMENT,
            status=_SHOPEE_STATUS_MAP.get(raw_order["order_status"], OrderStatus.NEW),
            items=items,
            fees=fees,
            gross_amount=Decimal(raw_order["total_amount"]),
            net_amount=Decimal(income["escrow_amount"]),
            order_time=order_time,
            updated_time=datetime.now(timezone.utc),
            customer_ref=str(raw_order["buyer_user_id"]),
            raw_status=raw_order["order_status"],
        )

    def push_stock_update(self, sku: str, quantity: int) -> SyncResult:
        # Real adapter would call Shopee's update_stock endpoint here.
        return SyncResult(success=True, message=f"[mock] shopee stock for {sku} set to {quantity}")

    def parse_webhook(self, payload: dict[str, Any]) -> CanonicalOrder:
        # Shopee webhook payloads wrap order_sn + status; for the mock we accept
        # a full raw_order shape directly for simplicity.
        return self.normalize_order(payload)

    def parse_settlement(self, report: dict[str, Any]) -> list[SettlementRecord]:
        return [
            SettlementRecord(
                settlement_id=report["settlement_id"],
                platform_order_id=report["order_sn"],
                channel=self._channel_enum,
                payout_amount=Decimal(report["payout_amount"]),
                fees=[
                    Fee(FeeCategory.COMMISSION, Decimal(report["commission_fee"]), "commission_fee"),
                    Fee(FeeCategory.PAYMENT_PROCESSING, Decimal(report["service_fee"]), "service_fee"),
                ],
                settlement_date=datetime.fromtimestamp(report["settlement_time"], tz=timezone.utc),
                batch_ref=report["batch_no"],
            )
        ]
