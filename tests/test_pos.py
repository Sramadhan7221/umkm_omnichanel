"""
Acceptance criteria for Epic C (POS Offline — Form Nota Kasir). See
docs/Analisis_Kebutuhan_Modul_Akuntansi_POS.pdf Bagian 4. Payment methods
33 (Transfer) and 34 (E-Wallet) are a PO-approved extension beyond the
32-row Excel matrix — see journal_engine_service.py's POS_PAYMENT_RULE_NOS
docstring.
"""

from datetime import datetime

from app.models.db_models import JournalEntry, Outlet, Product, Settlement
from app.services.chart_of_accounts_service import seed_accounts
from app.services.inventory_service import get_product
from app.services.journal_engine_service import seed_mapping_rules, seed_pos_payment_extension
from app.services.order_service import get_order
from app.services.pos_service import create_pos_sale, generate_nota_number, get_receipt
from app.services.reconciliation_service import generate_settlements
from tests.conftest import as_tenant, make_owner


def _seed(db):
    owner = make_owner(db)
    seed_accounts(db, owner.id)
    seed_mapping_rules(db)
    seed_pos_payment_extension(db)
    db.add(Outlet(kode_outlet="OUT-1", nama_outlet="Toko Utama", alamat="Jl. Contoh No. 1"))
    db.add(Outlet(kode_outlet="OUT-2", nama_outlet="Toko Nonaktif", is_active=False))
    db.add(Product(owner_id=owner.id, sku="SKU-1", name="Kopi Susu", reference_price=18_000, cogs_price=8_000, stock_qty=10))
    db.commit()
    return owner


def test_create_pos_sale_rejects_missing_outlet(db):
    owner = _seed(db)
    try:
        create_pos_sale(db, owner.id, outlet_id="NOPE", rule_no=8, items=[{"sku": "SKU-1", "qty": 1}])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_create_pos_sale_rejects_inactive_outlet(db):
    owner = _seed(db)
    try:
        create_pos_sale(db, owner.id, outlet_id="OUT-2", rule_no=8, items=[{"sku": "SKU-1", "qty": 1}])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_create_pos_sale_rejects_insufficient_stock(db):
    owner = _seed(db)
    try:
        create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=8, items=[{"sku": "SKU-1", "qty": 999}])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_create_pos_sale_creates_order_and_deducts_stock(db):
    owner = _seed(db)
    order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=8, items=[{"sku": "SKU-1", "qty": 2}], customer_ref="Bpk. Hendra")

    assert order.channel == "Offline POS"
    assert order.status == "Selesai"
    assert order.outlet_id == "OUT-1"
    assert order.gross_amount == 36_000
    assert order.customer_ref == "Bpk. Hendra"

    product = get_product(db, owner.id, "SKU-1")
    assert product.stock_qty == 8


def test_nota_number_format_and_monthly_increment(db):
    owner = _seed(db)
    first = generate_nota_number(db, owner.id)
    assert first == f"NT-{datetime.utcnow():%Y%m}001"

    create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=8, items=[{"sku": "SKU-1", "qty": 1}])
    second = generate_nota_number(db, owner.id)
    assert second == f"NT-{datetime.utcnow():%Y%m}002"


def test_tunai_payment_posts_outlet_scoped_kas_entry(db):
    owner = _seed(db)
    order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=8, items=[{"sku": "SKU-1", "qty": 1}])

    entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == order.platform_order_id, JournalEntry.rule_no == 8,
    ).one()
    assert entry.kode_debet == "1111" and entry.kode_kredit == "4114"
    assert entry.outlet_id == "OUT-1"
    assert entry.nominal == 18_000


def test_qris_payment_posts_receivable_entry_without_outlet(db):
    owner = _seed(db)
    order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=9, items=[{"sku": "SKU-1", "qty": 1}])

    entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == order.platform_order_id, JournalEntry.rule_no == 9,
    ).one()
    assert entry.kode_debet == "1122" and entry.kode_kredit == "4114"
    assert entry.outlet_id is None


def test_transfer_and_ewallet_extension_rules_post_correct_accounts(db):
    owner = _seed(db)
    transfer_order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=33, items=[{"sku": "SKU-1", "qty": 1}])
    ewallet_order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=34, items=[{"sku": "SKU-1", "qty": 1}])

    transfer_entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == transfer_order.platform_order_id, JournalEntry.rule_no == 33,
    ).one()
    ewallet_entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == ewallet_order.platform_order_id, JournalEntry.rule_no == 34,
    ).one()

    assert transfer_entry.kode_debet == "1113" and transfer_entry.kode_kredit == "4114"
    assert ewallet_entry.kode_debet == "1112" and ewallet_entry.kode_kredit == "4114"


def test_pos_sale_posts_cogs_entry(db):
    owner = _seed(db)
    order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=8, items=[{"sku": "SKU-1", "qty": 2}])

    cogs = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == order.platform_order_id, JournalEntry.rule_no == 24,
    ).one()
    assert cogs.kode_debet == "5110" and cogs.kode_kredit == "1131"
    assert cogs.nominal == 16_000  # 2 x cogs_price(8000)


def test_generate_settlements_excludes_offline_pos_orders(db):
    owner = _seed(db)
    create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=8, items=[{"sku": "SKU-1", "qty": 1}])

    created = generate_settlements(db, owner.id)
    assert created == 0
    assert db.query(Settlement).count() == 0


def test_get_receipt_returns_nota_ready_payload(db):
    owner = _seed(db)
    order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=9, items=[{"sku": "SKU-1", "qty": 1}], customer_ref="Ibu Sari")

    receipt = get_receipt(db, owner.id, order.platform_order_id)
    assert receipt["no_nota"] == order.platform_order_id
    assert receipt["nama_pelanggan"] == "Ibu Sari"
    assert receipt["outlet_nama"] == "Toko Utama"
    assert receipt["metode_pembayaran"] == "Penjualan via QRIS"
    assert receipt["total"] == 18_000
    assert receipt["items"][0]["nama_barang"] == "Kopi Susu"


def test_payment_methods_endpoint_returns_four_rules(client, db):
    owner = _seed(db)
    as_tenant(owner.id)
    response = client.get("/api/pos/payment-methods")
    assert response.status_code == 200
    assert {r["no"] for r in response.json()} == {8, 9, 33, 34}


def test_sales_endpoint_creates_nota_end_to_end(client, db):
    owner = _seed(db)
    as_tenant(owner.id)
    response = client.post("/api/pos/sales", json={
        "outlet_id": "OUT-1", "rule_no": 8, "customer_ref": "Bpk. Hendra",
        "items": [{"sku": "SKU-1", "qty": 2}],
    })
    assert response.status_code == 200

    body = response.json()
    assert body["total"] == 36_000
    assert body["outlet_nama"] == "Toko Utama"

    order = get_order(db, owner.id, body["no_nota"])
    assert order is not None and order.channel == "Offline POS"


def test_sales_endpoint_rejects_inactive_outlet(client, db):
    owner = _seed(db)
    as_tenant(owner.id)
    response = client.post("/api/pos/sales", json={
        "outlet_id": "OUT-2", "rule_no": 8, "items": [{"sku": "SKU-1", "qty": 1}],
    })
    assert response.status_code == 400
