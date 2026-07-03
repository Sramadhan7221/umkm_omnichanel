"""
MockGrabFoodAdapter — generates dummy order/settlement payloads shaped like
the GrabFood Merchant API's `Order`, `OrderItem`, and `OrderPrice` models
(confirmed against the official grab/grabfood-api-sdk-python OpenAPI-generated
models), and normalizes them into CanonicalOrder.

IMPORTANT — provenance note: field names (order_id, short_order_number,
items[], price.subtotal/tax/merchant_charge_fee/delivery_fee/eater_payment,
etc.) are taken directly from Grab's published SDK model docs. The exact
`order_state` enum string values were not confirmed from public docs at
build time (no live API access — business-registration blocker), so the
state labels used here are illustrative placeholders following the
documented lifecycle (new -> accept -> prepare -> ready -> completed /
cancelled). Re-verify literal enum strings once real API access is obtained
(see blueprint Section 3.0, "future work" note).
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

# Illustrative order_state labels (see provenance note above) mapped to canonical status
_GRABFOOD_STATUS_MAP = {
    "NEW_ORDER": OrderStatus.NEW,
    "ACCEPTED": OrderStatus.ACCEPTED,
    "FOOD_PREPARING": OrderStatus.PREPARING,
    "FOOD_READY": OrderStatus.READY_FOR_PICKUP,
    "COMPLETED": OrderStatus.COMPLETED,
    "CANCELLED": OrderStatus.CANCELLED,
}

_SAMPLE_MENU_ITEMS = [
    ("MENU-NASI-01", "Nasi Goreng Spesial", 32_000),
    ("MENU-AYAM-02", "Ayam Geprek Sambal Bawang", 28_000),
    ("MENU-MIE-03", "Mie Ayam Bakso", 25_000),
    ("MENU-MIN-04", "Es Teh Manis", 8_000),
]


class MockGrabFoodAdapter(PlatformAdapter):
    channel_name = "grabfood"

    # Overridable in subclasses that reuse this food-delivery-style generator
    # for a different platform (see MockGoFoodAdapter).
    _channel_enum = Channel.GRABFOOD
    _order_prefix = "GF"

    def authenticate(self, credentials: dict[str, Any]) -> AuthSession:
        merchant_id = credentials.get("merchant_id", "demo-grabfood-merchant")
        return AuthSession(store_id=merchant_id, access_token=f"mock-grab-{uuid.uuid4().hex[:8]}")

    # ---- Dummy data generation -------------------------------------------------

    def generate_raw_order(
        self,
        order_state: str | None = None,
        products: list[tuple[str, str, float]] | None = None,
    ) -> dict[str, Any]:
        """Produce a raw payload shaped like GrabFood's Order model (minor-unit pricing).

        `products` is an optional list of (sku, name, price) tuples to pick
        menu items from — when given (e.g. the user's own mapped product
        catalog for this platform), it's used instead of the built-in menu.
        """
        order_state = order_state or random.choice(list(_GRABFOOD_STATUS_MAP.keys()))
        # Food delivery orders are minutes-scale, not days-scale
        order_time = datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 45))

        catalog = products if products else _SAMPLE_MENU_ITEMS
        num_items = min(random.randint(1, 3), len(catalog))
        chosen = random.sample(catalog, num_items)
        items = []
        subtotal_minor = 0  # minor unit = smallest currency unit; IDR has no decimals, so 1:1
        for menu_id, name, price in chosen:
            qty = random.randint(1, 2)
            items.append({
                "id": menu_id,
                "name": name,
                "grab_item_id": f"{menu_id}#0",
                "quantity": qty,
                "price": price,
                "tax": 0,
                "specifications": random.choice(["", "Tidak pedas", "Extra sambal"]),
                "modifiers": [],
            })
            subtotal_minor += price * qty

        delivery_fee = random.choice([10_000, 12_000, 15_000])
        merchant_charge_fee = random.choice([0, 2_000])  # e.g. packaging
        commission_rate = 0.20  # GrabFood commission is typically a flat % of subtotal
        commission_fee = round(subtotal_minor * commission_rate)
        merchant_fund_promo = random.choice([0, 5_000])
        eater_payment = subtotal_minor + merchant_charge_fee + delivery_fee - merchant_fund_promo
        total = subtotal_minor + merchant_charge_fee - merchant_fund_promo
        merchant_earning = total - commission_fee

        return {
            "order_id": f"{self._order_prefix}{uuid.uuid4().hex[:12].upper()}",
            "short_order_number": str(random.randint(100, 999)),
            "merchant_id": "demo-grabfood-merchant",
            "payment_type": random.choice(["CASHLESS", "CASH"]),
            "cutlery": random.choice([True, False]),
            "order_time": order_time.isoformat(),
            "order_state": order_state,
            "currency": "IDR",
            "items": items,
            "price": {
                "subtotal": subtotal_minor,
                "tax": 0,
                "merchant_charge_fee": merchant_charge_fee,
                "service_charge_fee": 0,
                "grab_fund_promo": 0,
                "merchant_fund_promo": merchant_fund_promo,
                "delivery_fee": delivery_fee,
                "eater_payment": eater_payment,
                "total": total,
                "merchant_earning": merchant_earning,
            },
            "commission_fee": commission_fee,  # not a native OrderPrice field; carried for demo reconciliation
        }

    def generate_raw_settlement(self, raw_order: dict[str, Any]) -> dict[str, Any]:
        """Produce a raw payload shaped like a GrabFood payout/statement line item."""
        return {
            "statement_id": f"STMT-{uuid.uuid4().hex[:8].upper()}",
            "order_id": raw_order["order_id"],
            "payout_amount": raw_order["price"]["merchant_earning"],
            "commission_fee": raw_order["commission_fee"],
            "delivery_fee": raw_order["price"]["delivery_fee"],
            "settlement_time": int(datetime.now(timezone.utc).timestamp()),
            "batch_no": f"GF-BATCH-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        }

    # ---- Adapter contract implementation ---------------------------------------

    def fetch_orders(self, since: Any) -> list[dict[str, Any]]:
        return [self.generate_raw_order() for _ in range(random.randint(2, 5))]

    def normalize_order(self, raw_order: dict[str, Any]) -> CanonicalOrder:
        price = raw_order["price"]
        items = [
            OrderItem(
                sku=i["id"],
                platform_item_id=i["grab_item_id"],
                name=i.get("name", i["id"]),
                quantity=i["quantity"],
                unit_price=Decimal(i["price"]),
                modifiers=[i["specifications"]] if i["specifications"] else [],
            )
            for i in raw_order["items"]
        ]
        fees = [
            Fee(FeeCategory.COMMISSION, Decimal(raw_order["commission_fee"]), "commission_fee"),
            Fee(FeeCategory.LOGISTICS, Decimal(price["delivery_fee"]), "delivery_fee"),
        ]
        if price.get("merchant_charge_fee"):
            fees.append(Fee(FeeCategory.SERVICE_FEE, Decimal(price["merchant_charge_fee"]), "merchant_charge_fee"))
        if price.get("merchant_fund_promo"):
            fees.append(Fee(FeeCategory.PROMO_SUBSIDY, Decimal(price["merchant_fund_promo"]), "merchant_fund_promo"))

        return CanonicalOrder(
            order_id=str(uuid.uuid4()),
            platform_order_id=raw_order["order_id"],
            channel=self._channel_enum,
            fulfillment_type=FulfillmentType.INSTANT_PICKUP,
            status=_GRABFOOD_STATUS_MAP.get(raw_order["order_state"], OrderStatus.NEW),
            items=items,
            fees=fees,
            gross_amount=Decimal(price["eater_payment"]),
            net_amount=Decimal(price["merchant_earning"]),
            order_time=datetime.fromisoformat(raw_order["order_time"]),
            updated_time=datetime.now(timezone.utc),
            customer_ref=raw_order["short_order_number"],
            raw_status=raw_order["order_state"],
        )

    def push_stock_update(self, sku: str, quantity: int) -> SyncResult:
        # Real adapter would call GrabFood's menu/out-of-stock instruction endpoint here.
        return SyncResult(success=True, message=f"[mock] grabfood availability for {sku} set to {quantity}")

    def parse_webhook(self, payload: dict[str, Any]) -> CanonicalOrder:
        # GrabFood's Push Order State Webhook wraps an Order object; for the
        # mock we accept the full raw_order shape directly for simplicity.
        return self.normalize_order(payload)

    def parse_settlement(self, report: dict[str, Any]) -> list[SettlementRecord]:
        return [
            SettlementRecord(
                settlement_id=report["statement_id"],
                platform_order_id=report["order_id"],
                channel=self._channel_enum,
                payout_amount=Decimal(report["payout_amount"]),
                fees=[
                    Fee(FeeCategory.COMMISSION, Decimal(report["commission_fee"]), "commission_fee"),
                    Fee(FeeCategory.LOGISTICS, Decimal(report["delivery_fee"]), "delivery_fee"),
                ],
                settlement_date=datetime.fromtimestamp(report["settlement_time"], tz=timezone.utc),
                batch_ref=report["batch_no"],
            )
        ]
