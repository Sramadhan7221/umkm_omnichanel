"""
Acceptance criteria for Epic B (Journal Engine). See
docs/Analisis_Kebutuhan_Modul_Akuntansi_POS.pdf Bagian 4 and
docs/transaction_mapping_matrix.csv (source of truth for the 32 mapping
rules, transcribed verbatim from the business owner's Excel prototype).
"""

import csv
from datetime import datetime

import pytest

from app.models.db_models import (
    JournalEntry,
    OmniOrder,
    OmniOrderFee,
    OmniOrderItem,
    Outlet,
    Product,
    Settlement,
    TransactionMappingRule,
)
from app.services.chart_of_accounts_service import seed_accounts
from app.services.financial_service import add_expense
from app.services.journal_engine_service import (
    CSV_PATH,
    post_order_completed_journal,
    post_order_refunded_journal,
    post_settlement_journal,
    seed_mapping_rules,
)


def _seed(db):
    seed_accounts(db)
    seed_mapping_rules(db)


def _csv_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _make_order(db, order_id, channel, status, gross, fees, items=None):
    order = OmniOrder(
        platform_order_id=order_id, channel=channel, fulfillment_type="Pengiriman",
        status=status, order_time=datetime(2026, 8, 1, 10, 0), updated_time=datetime(2026, 8, 1, 10, 0),
        gross_amount=gross, net_amount=gross,
    )
    db.add(order)
    for category, amount, label in fees:
        db.add(OmniOrderFee(order_id=order_id, category=category, amount=amount, label=label))
    for sku, qty, price in (items or []):
        db.add(OmniOrderItem(order_id=order_id, sku=sku, item_name=sku, quantity=qty, unit_price=price))
    db.commit()
    db.refresh(order)
    return order


def test_seed_creates_exact_32_rows_from_csv(db):
    seed_mapping_rules(db)
    csv_rows = _csv_rows()

    rules = db.query(TransactionMappingRule).all()
    assert len(rules) == 32 == len(csv_rows)

    by_no = {r.no: r for r in rules}
    for row in csv_rows:
        rule = by_no[int(row["no"])]
        assert rule.kode_debet == row["kode_debet"]
        assert rule.kode_kredit == row["kode_kredit"]


def test_seed_mapping_rules_is_idempotent(db):
    seed_mapping_rules(db)
    seed_mapping_rules(db)
    assert db.query(TransactionMappingRule).count() == 32


def test_shopee_order_completed_posts_revenue_fee_and_cogs_entries(db):
    _seed(db)
    db.add(Product(sku="SKU-1", name="Produk 1", cogs_price=10_000, stock_qty=100))
    db.commit()

    order = _make_order(
        db, "SP-001", "Shopee", "Selesai", gross=100_000,
        fees=[("Komisi", 2_000, "commission_fee"), ("Biaya Pembayaran", 2_800, "service_fee")],
        items=[("SKU-1", 2, 50_000)],
    )
    entries = post_order_completed_journal(db, order)

    assert len(entries) >= 3
    revenue = next(e for e in entries if e.kode_kredit == "4111")
    assert revenue.kode_debet == "1121" and revenue.nominal == 100_000

    fee_entries = [e for e in entries if e.kode_debet == "5212"]
    assert len(fee_entries) == 2
    assert all(e.kode_kredit == "1121" for e in fee_entries)

    cogs = next(e for e in entries if e.rule_no == 24)
    assert cogs.kode_debet == "5110" and cogs.kode_kredit == "1131" and cogs.nominal == 20_000

    total_debit = sum(e.nominal for e in entries)
    total_credit = sum(e.nominal for e in entries)
    assert total_debit == total_credit  # balanced by construction, one leg each side per row


def test_grabfood_logistics_fee_generalizes_to_food_delivery_receivable(db):
    _seed(db)
    order = _make_order(
        db, "GF-001", "GrabFood", "Selesai", gross=50_000,
        fees=[("Komisi", 10_000, "commission_fee"), ("Logistik", 5_000, "delivery_fee")],
    )
    entries = post_order_completed_journal(db, order)

    logistics = next(e for e in entries if e.kode_debet == "5213")
    assert logistics.kode_kredit == "1123"
    assert logistics.nominal == 5_000

    commission = next(e for e in entries if e.kode_debet == "5212")
    assert commission.kode_kredit == "1123"


def test_refunded_order_posts_retur_entry_for_ecommerce_and_food_delivery(db):
    _seed(db)
    shopee_refund = _make_order(db, "SP-REF-1", "Shopee", "Dikembalikan", gross=75_000, fees=[])
    grabfood_refund = _make_order(db, "GF-REF-1", "GrabFood", "Dikembalikan", gross=40_000, fees=[])

    shopee_entries = post_order_refunded_journal(db, shopee_refund)
    grabfood_entries = post_order_refunded_journal(db, grabfood_refund)

    assert len(shopee_entries) == 1
    assert shopee_entries[0].kode_debet == "4212" and shopee_entries[0].kode_kredit == "1121"

    assert len(grabfood_entries) == 1
    assert grabfood_entries[0].kode_debet == "4212" and grabfood_entries[0].kode_kredit == "1123"


def test_settlement_posts_bank_receipt_entry(db):
    _seed(db)
    order = _make_order(db, "SP-002", "Shopee", "Selesai", gross=100_000, fees=[])
    settlement = Settlement(
        settlement_id="SETL-TEST01", platform_order_id=order.platform_order_id, channel="Shopee",
        expected_amount=95_000, payout_amount=95_000, diff_amount=0, status="Cocok",
        batch_ref="BATCH-TEST", settlement_date=datetime(2026, 8, 2, 9, 0),
    )
    db.add(settlement)
    db.commit()

    entry = post_settlement_journal(db, settlement)

    assert entry.kode_debet == "1113"
    assert entry.kode_kredit == "1121"
    assert entry.nominal == 95_000
    assert entry.settlement_id == "SETL-TEST01"


def test_expense_rule_variants_post_correct_account_pairs(db):
    _seed(db)
    db.add(Outlet(kode_outlet="OUT-1", nama_outlet="Toko Utama"))
    db.commit()

    kemasan = add_expense(db, "Bubble Wrap", 75_000, "", datetime(2026, 8, 1), rule_no=25, outlet_id="OUT-1")
    saas = add_expense(db, "Langganan POS", 150_000, "", datetime(2026, 8, 1), rule_no=26)
    gaji_bank = add_expense(db, "Gaji", 3_000_000, "", datetime(2026, 8, 1), rule_no=30)
    gaji_tunai = add_expense(db, "Gaji Harian", 200_000, "", datetime(2026, 8, 1), rule_no=31, outlet_id="OUT-1")
    operasional = add_expense(db, "Listrik", 500_000, "", datetime(2026, 8, 1), rule_no=32)

    entries = {e.expense_id: e for e in db.query(JournalEntry).filter(JournalEntry.expense_id.isnot(None)).all()}

    assert entries[kemasan.id].kode_debet == "5120" and entries[kemasan.id].kode_kredit == "1111"
    assert entries[kemasan.id].outlet_id == "OUT-1"
    assert entries[saas.id].kode_debet == "5214" and entries[saas.id].kode_kredit == "1113"
    assert entries[gaji_bank.id].kode_debet == "5310" and entries[gaji_bank.id].kode_kredit == "1113"
    assert entries[gaji_tunai.id].kode_debet == "5310" and entries[gaji_tunai.id].kode_kredit == "1111"
    assert entries[gaji_tunai.id].outlet_id == "OUT-1"
    assert entries[operasional.id].kode_debet == "5320" and entries[operasional.id].kode_kredit == "1113"


@pytest.mark.parametrize("rule_no", [25, 31])
def test_add_expense_rejects_outlet_scoped_rule_without_outlet(db, rule_no):
    _seed(db)
    with pytest.raises(ValueError):
        add_expense(db, "Biaya Tunai", 50_000, "", datetime(2026, 8, 1), rule_no=rule_no, outlet_id=None)

    assert db.query(JournalEntry).filter(JournalEntry.rule_no == rule_no).count() == 0


def test_add_expense_allows_non_outlet_scoped_rule_without_outlet(db):
    _seed(db)
    expense = add_expense(db, "Listrik", 500_000, "", datetime(2026, 8, 1), rule_no=32, outlet_id=None)
    assert expense.id is not None


def test_journal_endpoint_returns_posted_entries(client, db):
    _seed(db)
    order = _make_order(db, "SP-003", "Shopee", "Selesai", gross=60_000, fees=[("Komisi", 1_200, "commission_fee")])
    post_order_completed_journal(db, order)

    response = client.get("/api/financial/journal?start=2026-07-01&end=2026-08-31")
    assert response.status_code == 200

    body = response.json()
    assert any(row["sumber_dokumen"] == "Pesanan SP-003" for row in body)


def test_expense_rules_endpoint_returns_five_rules_with_outlet_flag(client, db):
    _seed(db)
    response = client.get("/api/financial/expense-rules")
    assert response.status_code == 200

    rules = {r["no"]: r for r in response.json()}
    assert set(rules) == {25, 26, 30, 31, 32}
    assert rules[25]["outlet_required"] is True
    assert rules[31]["outlet_required"] is True
    assert rules[26]["outlet_required"] is False
    assert rules[30]["outlet_required"] is False
    assert rules[32]["outlet_required"] is False


def test_create_expense_endpoint_rejects_missing_outlet_for_outlet_scoped_rule(client, db):
    _seed(db)
    response = client.post("/api/financial/expenses", json={
        "category": "Bubble Wrap", "amount": 50_000, "expense_date": "2026-08-01", "rule_no": 25,
    })
    assert response.status_code == 400
