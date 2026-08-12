"""
Acceptance criteria for Epic D (Master Barang & HPP): Product gains cogs_price
(HPP) + unit_label as required source-of-truth fields, and changing either the
selling price or HPP pushes an outbound sync to every mapped platform.
"""

import json

from app.models.db_models import Product, ProductAuditLog
from app.services.inventory_service import (
    _INITIAL_CATALOG,
    create_product,
    seed_products,
    update_product,
)


def _make_product(db, sku="SKU-TEST-001", price=100_000, cogs=60_000, channels=None):
    return create_product(
        db, sku=sku, name="Produk Uji", description="", stock_qty=10,
        reference_price=price, cogs_price=cogs, unit_label="Pcs", ppn_rate=11.0,
        channels=channels or [],
    )


def test_create_product_stores_cogs_price_and_unit_label(db):
    product = _make_product(db)
    assert product.cogs_price == 60_000
    assert product.unit_label == "Pcs"


def test_seed_products_all_have_cogs_price_and_unit_label(db):
    seed_products(db)
    products = db.query(Product).all()
    assert len(products) == len(_INITIAL_CATALOG)
    for product in products:
        assert product.cogs_price > 0
        assert product.unit_label


def test_update_product_tracks_cogs_price_change_in_audit_log(db):
    _make_product(db)
    update_product(db, "SKU-TEST-001", {"cogs_price": 65_000}, note="Bahan baku naik")

    product = db.get(Product, "SKU-TEST-001")
    assert product.cogs_price == 65_000

    logs = db.query(ProductAuditLog).filter(ProductAuditLog.sku == "SKU-TEST-001").all()
    assert len(logs) == 1
    changed = json.loads(logs[0].changed_fields)
    assert changed["HPP (Harga Pokok)"] == {"old": 60_000.0, "new": 65_000.0}


def test_price_or_hpp_change_pushes_to_mapped_platforms(db, monkeypatch):
    calls = []

    class FakeAdapter:
        def push_price_update(self, sku, price, cogs_price):
            calls.append((sku, price, cogs_price))

        def push_stock_update(self, sku, quantity):
            pass

    monkeypatch.setattr("app.services.inventory_service._get_adapter", lambda channel: FakeAdapter())

    product = _make_product(db, channels=["Shopee"])
    assert calls == [("SKU-TEST-001", 100_000, 60_000)]  # push on create

    calls.clear()
    update_product(db, "SKU-TEST-001", {"reference_price": 110_000})
    assert calls == [("SKU-TEST-001", 110_000, 60_000)]

    calls.clear()
    update_product(db, "SKU-TEST-001", {"description": "Deskripsi baru"})
    assert calls == []  # non-price edit shouldn't trigger a price push


def test_add_product_endpoint_requires_cogs_price_and_unit_label(client, db):
    response = client.post("/api/inventory/products", data={
        "sku": "SKU-TEST-002", "name": "Produk Tanpa HPP", "stock_qty": "5", "reference_price": "50000",
    })
    assert response.status_code == 422


def test_add_product_endpoint_accepts_cogs_price_and_unit_label(client, db):
    response = client.post("/api/inventory/products", data={
        "sku": "SKU-TEST-003", "name": "Produk Lengkap", "stock_qty": "5",
        "reference_price": "50000", "cogs_price": "30000", "unit_label": "Botol",
    })
    assert response.status_code == 200

    detail = client.get("/api/inventory/products/SKU-TEST-003/detail").json()
    assert detail["cogs_price"] == 30000
    assert detail["unit_label"] == "Botol"
