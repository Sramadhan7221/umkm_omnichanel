"""
MockGoFoodAdapter — reuses MockGrabFoodAdapter's food-delivery-style
order/fee generation (both are instant-pickup food delivery platforms with a
broadly similar commission/delivery-fee structure), just swapping the
channel and order-id prefix.

Pragmatic simplification for the demo, same rationale as
MockTikTokShopAdapter — see blueprint Section 3.0's "future work" note.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.mock_adapters.base import AuthSession, SyncResult
from app.mock_adapters.mock_grabfood import MockGrabFoodAdapter
from app.models.canonical import Channel


class MockGoFoodAdapter(MockGrabFoodAdapter):
    channel_name = "gofood"
    _channel_enum = Channel.GOFOOD
    _order_prefix = "GO"

    def authenticate(self, credentials: dict[str, Any]) -> AuthSession:
        merchant_id = credentials.get("merchant_id", "demo-gofood-merchant")
        return AuthSession(store_id=merchant_id, access_token=f"mock-gofood-{uuid.uuid4().hex[:8]}")

    def push_stock_update(self, sku: str, quantity: int) -> SyncResult:
        return SyncResult(success=True, message=f"[mock] gofood availability for {sku} set to {quantity}")
