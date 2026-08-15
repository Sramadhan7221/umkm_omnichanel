"""
Acceptance criteria for Epic G (Retur & Pembatalan). Rule #19 already
existed from Epic B for orders that arrive already-refunded; this epic adds
the real "Proses Retur" transition (order_service.process_retur) plus rule
#20's optional stock/HPP recovery. See
docs/Analisis_Kebutuhan_Modul_Akuntansi_POS.pdf Bagian 4.
"""

from datetime import datetime

from app.models.db_models import JournalEntry, OmniOrder, OmniOrderItem, Outlet, Product
from app.services.chart_of_accounts_service import seed_accounts
from app.services.inventory_service import get_product
from app.services.journal_engine_service import (
    post_order_completed_journal,
    seed_mapping_rules,
    seed_pos_payment_extension,
)
from app.services.order_service import process_retur
from app.services.pos_service import create_pos_sale
from tests.conftest import as_tenant, make_owner


def _seed(db):
    owner = make_owner(db)
    seed_accounts(db, owner.id)
    seed_mapping_rules(db)
    seed_pos_payment_extension(db)
    return owner


def _make_completed_order(db, owner_id, order_id, channel, gross=100_000, sku="SKU-1", qty=2):
    db.add(Product(owner_id=owner_id, sku=sku, name="Produk Uji", reference_price=gross / qty, cogs_price=10_000, stock_qty=50))
    db.commit()

    order = OmniOrder(
        owner_id=owner_id,
        platform_order_id=order_id, channel=channel, fulfillment_type="Pengiriman",
        status="Selesai", order_time=datetime(2026, 8, 1), updated_time=datetime(2026, 8, 1),
        gross_amount=gross, net_amount=gross,
    )
    db.add(order)
    db.flush()  # supaya order.id tersedia untuk FK item di bawah
    db.add(OmniOrderItem(order_id=order.id, sku=sku, item_name="Produk Uji", quantity=qty, unit_price=gross / qty))
    db.commit()
    db.refresh(order)
    post_order_completed_journal(db, order)
    return order


def test_process_retur_rejects_non_completed_order(db):
    owner = _seed(db)
    order = OmniOrder(
        owner_id=owner.id,
        platform_order_id="SP-1", channel="Shopee", fulfillment_type="Pengiriman",
        status="Baru", order_time=datetime(2026, 8, 1),
    )
    db.add(order)
    db.commit()

    try:
        process_retur(db, owner.id, "SP-1", restore_stock=False)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_process_retur_rejects_double_retur(db):
    owner = _seed(db)
    _make_completed_order(db, owner.id, "SP-1", "Shopee")
    process_retur(db, owner.id, "SP-1", restore_stock=False)

    try:
        process_retur(db, owner.id, "SP-1", restore_stock=False)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_process_retur_rejects_unknown_order(db):
    owner = _seed(db)
    try:
        process_retur(db, owner.id, "DOES-NOT-EXIST", restore_stock=False)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_shopee_retur_credits_ecommerce_receivable(db):
    owner = _seed(db)
    _make_completed_order(db, owner.id, "SP-1", "Shopee", gross=100_000)
    order = process_retur(db, owner.id, "SP-1", restore_stock=False)

    assert order.status == "Dikembalikan"
    entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == "SP-1", JournalEntry.rule_no == 19,
    ).one()
    assert entry.kode_debet == "4212" and entry.kode_kredit == "1121"
    assert entry.nominal == 100_000


def test_grabfood_retur_credits_food_delivery_receivable(db):
    owner = _seed(db)
    _make_completed_order(db, owner.id, "GF-1", "GrabFood", gross=50_000)
    process_retur(db, owner.id, "GF-1", restore_stock=False)

    entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == "GF-1", JournalEntry.rule_no == 19,
    ).one()
    assert entry.kode_debet == "4212" and entry.kode_kredit == "1123"


def test_pos_retur_credits_the_original_nota_payment_account(db):
    owner = _seed(db)
    db.add(Outlet(kode_outlet="OUT-1", nama_outlet="Toko Utama"))
    db.add(Product(owner_id=owner.id, sku="SKU-1", name="Kopi", reference_price=20_000, cogs_price=8_000, stock_qty=50))
    db.commit()

    tunai_order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=8, items=[{"sku": "SKU-1", "qty": 1}])
    qris_order = create_pos_sale(db, owner.id, outlet_id="OUT-1", rule_no=9, items=[{"sku": "SKU-1", "qty": 1}])

    process_retur(db, owner.id, tunai_order.platform_order_id, restore_stock=False)
    process_retur(db, owner.id, qris_order.platform_order_id, restore_stock=False)

    tunai_retur = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id,
        JournalEntry.order_id == tunai_order.platform_order_id, JournalEntry.rule_no == 19,
    ).one()
    qris_retur = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id,
        JournalEntry.order_id == qris_order.platform_order_id, JournalEntry.rule_no == 19,
    ).one()

    assert tunai_retur.kode_debet == "4212" and tunai_retur.kode_kredit == "1111"
    assert qris_retur.kode_debet == "4212" and qris_retur.kode_kredit == "1122"


def test_restore_stock_true_posts_rule_20_and_increases_stock(db):
    owner = _seed(db)
    _make_completed_order(db, owner.id, "SP-1", "Shopee", gross=100_000, sku="SKU-1", qty=2)
    product_before = get_product(db, owner.id, "SKU-1")
    stock_before = product_before.stock_qty  # already deducted? No — completed-order journal doesn't touch stock,
    # only deduct_stock_for_order (called from api.py) does; here we only posted the journal directly.

    process_retur(db, owner.id, "SP-1", restore_stock=True)

    cogs_entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == "SP-1", JournalEntry.rule_no == 24,
    ).one()
    recovery_entry = db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == "SP-1", JournalEntry.rule_no == 20,
    ).one()

    assert recovery_entry.kode_debet == "1131" and recovery_entry.kode_kredit == "5110"
    assert recovery_entry.nominal == cogs_entry.nominal == 20_000  # 2 x cogs_price(10_000)

    product_after = get_product(db, owner.id, "SKU-1")
    assert product_after.stock_qty == stock_before + 2


def test_restore_stock_false_skips_rule_20_and_stock_change(db):
    owner = _seed(db)
    _make_completed_order(db, owner.id, "SP-1", "Shopee", sku="SKU-1", qty=2)
    stock_before = get_product(db, owner.id, "SKU-1").stock_qty

    process_retur(db, owner.id, "SP-1", restore_stock=False)

    assert db.query(JournalEntry).filter(
        JournalEntry.owner_id == owner.id, JournalEntry.order_id == "SP-1", JournalEntry.rule_no == 20,
    ).first() is None
    assert get_product(db, owner.id, "SKU-1").stock_qty == stock_before


def test_process_retur_endpoint(client, db):
    owner = _seed(db)
    as_tenant(owner.id)
    _make_completed_order(db, owner.id, "SP-1", "Shopee", sku="SKU-1", qty=1)

    response = client.post("/api/order/SP-1/process-retur", json={"restore_stock": True})
    assert response.status_code == 200
    assert response.json()["status"] == "Dikembalikan"

    double = client.post("/api/order/SP-1/process-retur", json={"restore_stock": False})
    assert double.status_code == 400
