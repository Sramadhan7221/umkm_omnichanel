"""
Canonical Order Model — the single internal shape every platform adapter
normalizes into. Nothing downstream (inventory, financial engine, UI) should
ever touch a raw platform payload; it only ever sees these types.

Reference: umkm-apps blueprint, Section 3.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class Channel(str, Enum):
    SHOPEE = "shopee"
    TIKTOK_SHOP = "tiktok_shop"
    GRABFOOD = "grabfood"
    GOFOOD = "gofood"


class FulfillmentType(str, Enum):
    """Drives which state machine / SLA timers apply downstream.
    This is a first-class field, not derived from `channel` — e-commerce
    orders live for days, food-delivery orders live for minutes."""
    SHIPMENT = "shipment"          # e-commerce: pack -> courier -> transit -> delivered
    INSTANT_PICKUP = "instant_pickup"  # food delivery: accept -> prep -> driver pickup


class OrderStatus(str, Enum):
    """Canonical state machine. Each adapter maps its own platform's raw
    status string onto one of these."""
    NEW = "new"
    ACCEPTED = "accepted"
    PREPARING = "preparing"          # food delivery: kitchen prep
    READY_FOR_PICKUP = "ready_for_pickup"   # food delivery: waiting for driver
    SHIPPED = "shipped"              # e-commerce: handed to courier
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class FeeCategory(str, Enum):
    """Canonical fee bucket. The per-platform Fee Mapping Table (config-driven
    in production) maps each platform's raw fee line label onto one of these."""
    COMMISSION = "commission"
    PAYMENT_PROCESSING = "payment_processing"
    ADS = "ads"
    PROMO_SUBSIDY = "promo_subsidy"
    LOGISTICS = "logistics"
    SERVICE_FEE = "service_fee"
    PENALTY = "penalty"
    OTHER = "other"


# Channel -> kode akun pendapatan (Bagian 4 PDF, Epic A). Dipakai Journal
# Engine (Epic B) untuk menentukan akun kredit saat posting pendapatan;
# belum dipakai oleh kode manapun di Epic A. Kode akun harus ada di
# docs/chart_of_accounts.csv. GrabFood dan GoFood sama-sama masuk 4115
# "Pendapatan Usaha - Food Delivery" karena keduanya food-delivery.
CHANNEL_REVENUE_ACCOUNT: dict[Channel, str] = {
    Channel.SHOPEE: "4111",
    Channel.TIKTOK_SHOP: "4113",
    Channel.GRABFOOD: "4115",
    Channel.GOFOOD: "4115",
}

# Channel -> kode akun piutang (Epic B). Same grouping as
# CHANNEL_REVENUE_ACCOUNT: e-commerce channels share 1121 Piutang Penjualan
# E-Commerce (matrix rules #1/#3/#7), food-delivery channels share 1123
# Piutang Aplikasi Food Delivery (rules #12/#14). Used by the Journal Engine
# to resolve which receivable account a fee deduction, settlement payout, or
# refund reduces — including for GrabFood/GoFood fee/retur cases the 32-row
# matrix only wrote a literal row for e-commerce (see journal_engine_service
# docstring for the generalization this covers).
CHANNEL_RECEIVABLE_ACCOUNT: dict[Channel, str] = {
    Channel.SHOPEE: "1121",
    Channel.TIKTOK_SHOP: "1121",
    Channel.GRABFOOD: "1123",
    Channel.GOFOOD: "1123",
}


@dataclass
class Fee:
    category: FeeCategory
    amount: Decimal
    label: str  # original raw label from the platform, kept for audit trail


@dataclass
class OrderItem:
    sku: str                 # internal SKU (post SKU-mapping-table resolution)
    platform_item_id: str    # raw item/menu id from the platform
    name: str
    quantity: int
    unit_price: Decimal
    modifiers: list[str] = field(default_factory=list)  # food-delivery modifiers/notes


@dataclass
class CanonicalOrder:
    order_id: str                     # internal generated id
    platform_order_id: str            # platform's native order id
    channel: Channel
    fulfillment_type: FulfillmentType
    status: OrderStatus
    items: list[OrderItem]
    fees: list[Fee]
    gross_amount: Decimal             # what the buyer paid, pre-fee-deduction
    net_amount: Decimal               # what the seller nets, post-fee-deduction
    order_time: datetime
    updated_time: datetime
    customer_ref: str                 # anonymized platform buyer id
    raw_status: str                   # original platform status string, for debugging/audit
    payout_batch_ref: Optional[str] = None


@dataclass
class SettlementRecord:
    """One line item from a platform's payout/settlement report, used by the
    Reconciliation Engine to match against CanonicalOrder.net_amount."""
    settlement_id: str
    platform_order_id: str
    channel: Channel
    payout_amount: Decimal
    fees: list[Fee]
    settlement_date: datetime
    batch_ref: str
