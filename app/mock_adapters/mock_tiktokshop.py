"""
MockTikTokShopAdapter — reuses MockShopeeAdapter's e-commerce-style order/fee
generation (both platforms are shipment-based e-commerce marketplaces with a
broadly similar commission/payment-fee structure), just swapping the channel
and order-id prefix.

This is a pragmatic simplification for the demo (see blueprint Section 3.0's
"future work" note) rather than a payload shaped after TikTok Shop's actual
API — that would need its own provenance research once real API access is
obtained.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.mock_adapters.base import AuthSession, SyncResult
from app.mock_adapters.mock_shopee import MockShopeeAdapter
from app.models.canonical import Channel


class MockTikTokShopAdapter(MockShopeeAdapter):
    channel_name = "tiktok_shop"
    _channel_enum = Channel.TIKTOK_SHOP
    _order_prefix = "TT"

    def authenticate(self, credentials: dict[str, Any]) -> AuthSession:
        shop_id = credentials.get("store_id", "demo-tiktokshop-store")
        return AuthSession(store_id=shop_id, access_token=f"mock-tiktokshop-{uuid.uuid4().hex[:8]}")

    def push_stock_update(self, sku: str, quantity: int) -> SyncResult:
        return SyncResult(success=True, message=f"[mock] tiktok shop stock for {sku} set to {quantity}")

    def push_price_update(self, sku: str, price: float, cogs_price: float) -> SyncResult:
        return SyncResult(success=True, message=f"[mock] tiktok shop price for {sku} set to {price} (HPP {cogs_price})")
