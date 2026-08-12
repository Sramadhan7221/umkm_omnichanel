"""
PlatformAdapter — the contract every platform integration implements, whether
it's a mock (dummy data, used now) or a real adapter (added later once API
access is obtained).

Design intent (blueprint Section 3.0): downstream systems (Order Inbox,
Inventory Engine, Financial Engine, Reconciliation Engine) depend only on this
interface and on the canonical model — never on a specific platform's raw
payload shape. Swapping a mock adapter for a real one later should require
zero changes outside this adapters/ package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.canonical import CanonicalOrder, SettlementRecord


class AuthSession:
    """Placeholder auth/session object. Real adapters would hold OAuth2
    access_token / refresh_token / expiry here."""

    def __init__(self, store_id: str, access_token: str = "mock-token"):
        self.store_id = store_id
        self.access_token = access_token


class SyncResult:
    def __init__(self, success: bool, message: str = ""):
        self.success = success
        self.message = message

    def __repr__(self) -> str:
        return f"SyncResult(success={self.success}, message={self.message!r})"


class PlatformAdapter(ABC):
    """Abstract base every platform adapter (mock or real) must implement."""

    channel_name: str = "unknown"

    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> AuthSession:
        """Establish/refresh a session for a given store's credentials."""
        raise NotImplementedError

    @abstractmethod
    def fetch_orders(self, since: Any) -> list[dict[str, Any]]:
        """Pull raw orders since a given timestamp (polling fallback path)."""
        raise NotImplementedError

    @abstractmethod
    def normalize_order(self, raw_order: dict[str, Any]) -> CanonicalOrder:
        """Translate one raw platform order payload into a CanonicalOrder."""
        raise NotImplementedError

    @abstractmethod
    def push_stock_update(self, sku: str, quantity: int) -> SyncResult:
        """Push an internal stock level change out to the platform."""
        raise NotImplementedError

    @abstractmethod
    def push_price_update(self, sku: str, price: float, cogs_price: float) -> SyncResult:
        """Push a selling-price/HPP change from Master Barang (Epic D) out to
        the platform. Master Barang is the single source of truth for price;
        this is the outbound sync leg — never the other direction."""
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, payload: dict[str, Any]) -> CanonicalOrder:
        """Translate a raw inbound webhook payload into a CanonicalOrder."""
        raise NotImplementedError

    @abstractmethod
    def parse_settlement(self, report: dict[str, Any]) -> list[SettlementRecord]:
        """Translate a raw settlement/payout report into SettlementRecords."""
        raise NotImplementedError
