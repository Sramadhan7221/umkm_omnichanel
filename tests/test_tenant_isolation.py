"""
Acceptance criteria for Customer Request 1 Epic K (Isolasi Data
Multi-Tenant). See docs/CLAUDE.md's Epic K acceptance criteria — this file
exercises them directly against two independent Owners, the core thing this
epic exists to guarantee (without it, Owner/Admin roles are theater — every
tenant would still read/write the exact same rows).
"""

from datetime import datetime

from app.main import app
from app.routers.auth import _get_session_role
from app.services.chart_of_accounts_service import seed_accounts
from app.services.inventory_service import create_product
from app.services.journal_engine_service import post_journal
from tests.conftest import as_tenant, make_owner


def _as_role(role):
    app.dependency_overrides[_get_session_role] = lambda: role


def _make_product(db, owner_id, sku, name, stock_qty=5, price=10_000, cogs=5_000):
    return create_product(
        db, owner_id, sku=sku, name=name, description="", stock_qty=stock_qty,
        reference_price=price, cogs_price=cogs, unit_label="Pcs", ppn_rate=11.0, channels=[],
    )


def test_inventory_never_leaks_across_owners(client, db):
    owner_a = make_owner(db, email="a@example.com")
    owner_b = make_owner(db, email="b@example.com")
    _make_product(db, owner_a.id, "SKU-A", "Produk A")
    _make_product(db, owner_b.id, "SKU-B", "Produk B")

    as_tenant(owner_a.id)
    skus_a = {p["sku"] for p in client.get("/api/inventory").json()}
    assert skus_a == {"SKU-A"}

    as_tenant(owner_b.id)
    skus_b = {p["sku"] for p in client.get("/api/inventory").json()}
    assert skus_b == {"SKU-B"}


def test_same_sku_can_exist_for_two_owners_independently(db):
    owner_a = make_owner(db, email="a@example.com")
    owner_b = make_owner(db, email="b@example.com")
    product_a = _make_product(db, owner_a.id, "SKU-1", "Produk A", stock_qty=5)
    product_b = _make_product(db, owner_b.id, "SKU-1", "Produk B", stock_qty=9)

    assert product_a.id != product_b.id
    assert product_a.stock_qty == 5
    assert product_b.stock_qty == 9


def test_balance_sheet_isolated_per_owner_even_with_same_account_code(client, db):
    owner_a = make_owner(db, email="a@example.com")
    owner_b = make_owner(db, email="b@example.com")
    seed_accounts(db, owner_a.id)
    seed_accounts(db, owner_b.id)

    post_journal(
        db, owner_id=owner_a.id, kode_debet="1121", kode_kredit="4111", nominal=100_000,
        tanggal=datetime(2026, 8, 1), sumber_dokumen="test", keterangan="test",
    )

    as_tenant(owner_a.id)
    balance_a_before = client.get("/api/financial/balance-sheet?as_of=2026-08-31").json()["total_aset"]

    # OwnerB posts a transaction on the SAME account code — must not move
    # OwnerA's numbers at all.
    post_journal(
        db, owner_id=owner_b.id, kode_debet="1121", kode_kredit="4111", nominal=999_000,
        tanggal=datetime(2026, 8, 1), sumber_dokumen="test", keterangan="test",
    )

    balance_a_after = client.get("/api/financial/balance-sheet?as_of=2026-08-31").json()["total_aset"]
    assert balance_a_before == balance_a_after == 100_000

    as_tenant(owner_b.id)
    balance_b = client.get("/api/financial/balance-sheet?as_of=2026-08-31").json()["total_aset"]
    assert balance_b == 999_000


def test_admin_cannot_reach_other_owners_sku_by_direct_id(client, db):
    owner_a = make_owner(db, email="a@example.com")
    owner_b = make_owner(db, email="b@example.com")
    _make_product(db, owner_b.id, "SKU-SECRET", "Punya Owner B")

    # An Admin created by OwnerA has tenant_id == owner_a.id at login (Epic I) —
    # mirrored here by pointing the tenant override at owner_a.id while acting
    # as role="admin".
    as_tenant(owner_a.id)
    _as_role("admin")

    response = client.post("/api/inventory/SKU-SECRET/adjust", json={"quantity": 1, "note": "coba akses"})
    assert response.status_code == 404
