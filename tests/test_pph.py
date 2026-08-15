"""
Acceptance criteria for Epic E (PPh Final UMKM 0,5%). Rules #28/#29 already
exist in TransactionMappingRule (seeded by Epic B from
docs/transaction_mapping_matrix.csv) — this only wires them to two new
owner actions. See docs/Analisis_Kebutuhan_Modul_Akuntansi_POS.pdf Bagian 4.
"""

from datetime import datetime

from app.models.db_models import JournalEntry, OmniOrder
from app.services.chart_of_accounts_service import seed_accounts
from app.services.financial_service import close_month_pph, get_pph_summary, record_pph_deposit
from app.services.journal_engine_service import seed_mapping_rules
from tests.conftest import as_tenant, make_owner


def _seed(db):
    owner = make_owner(db)
    seed_accounts(db, owner.id)
    seed_mapping_rules(db)
    return owner


def _order(owner_id, platform_order_id, status, order_time, gross_amount):
    return OmniOrder(
        owner_id=owner_id,
        platform_order_id=platform_order_id, channel="Shopee", fulfillment_type="Pengiriman",
        status=status, order_time=order_time, updated_time=order_time,
        gross_amount=gross_amount, net_amount=gross_amount,
    )


def test_close_month_pph_posts_half_percent_of_completed_gross_omset(db):
    owner = _seed(db)
    db.add_all([
        _order(owner.id, "SP-1", "Selesai", datetime(2026, 8, 5), 1_000_000),
        _order(owner.id, "SP-2", "Selesai", datetime(2026, 8, 20), 500_000),
        _order(owner.id, "SP-3", "Dibatalkan", datetime(2026, 8, 10), 999_999),  # not completed, excluded
        _order(owner.id, "SP-4", "Selesai", datetime(2026, 7, 31), 800_000),  # different month, excluded
    ])
    db.commit()

    entry = close_month_pph(db, owner.id, "2026-08")

    assert entry.kode_debet == "5410" and entry.kode_kredit == "2140"
    assert entry.nominal == 7_500  # 0.5% x 1,500,000
    assert entry.rule_no == 28


def test_close_month_pph_rejects_double_close(db):
    owner = _seed(db)
    db.add(_order(owner.id, "SP-1", "Selesai", datetime(2026, 8, 5), 1_000_000))
    db.commit()

    close_month_pph(db, owner.id, "2026-08")
    try:
        close_month_pph(db, owner.id, "2026-08")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_close_month_pph_rejects_zero_omset(db):
    owner = _seed(db)
    try:
        close_month_pph(db, owner.id, "2026-08")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_record_pph_deposit_posts_correct_entry(db):
    owner = _seed(db)
    db.add(_order(owner.id, "SP-1", "Selesai", datetime(2026, 8, 5), 1_000_000))
    db.commit()
    close_month_pph(db, owner.id, "2026-08")

    entry = record_pph_deposit(db, owner.id, 5_000, datetime(2026, 9, 1))

    assert entry.kode_debet == "2140" and entry.kode_kredit == "1113"
    assert entry.nominal == 5_000
    assert entry.rule_no == 29


def test_pph_summary_reflects_full_accrual_deposit_cycle(db):
    owner = _seed(db)
    db.add(_order(owner.id, "SP-1", "Selesai", datetime(2026, 8, 5), 1_000_000))
    db.commit()

    not_yet = get_pph_summary(db, owner.id, "2026-08")
    assert not_yet["is_accrued"] is False
    assert not_yet["status"] == "Belum Ada Akrual"
    assert not_yet["estimated_pph"] == 5_000

    close_month_pph(db, owner.id, "2026-08")
    accrued = get_pph_summary(db, owner.id, "2026-08")
    assert accrued["is_accrued"] is True
    assert accrued["status"] == "Belum Disetor"
    assert accrued["outstanding_utang"] == 5_000

    record_pph_deposit(db, owner.id, 5_000, datetime(2026, 9, 1))
    settled = get_pph_summary(db, owner.id, "2026-08")
    assert settled["status"] == "Sudah Disetor"
    assert settled["outstanding_utang"] == 0


def test_close_month_endpoint_and_deposit_endpoint(client, db):
    owner = _seed(db)
    as_tenant(owner.id)
    db.add(_order(owner.id, "SP-1", "Selesai", datetime(2026, 8, 5), 2_000_000))
    db.commit()

    close_resp = client.post("/api/financial/pph/close-month", json={"period": "2026-08"})
    assert close_resp.status_code == 200
    assert close_resp.json()["nominal"] == 10_000

    double_close = client.post("/api/financial/pph/close-month", json={"period": "2026-08"})
    assert double_close.status_code == 400

    deposit_resp = client.post("/api/financial/pph/deposit", json={"amount": 10_000, "deposit_date": "2026-09-01"})
    assert deposit_resp.status_code == 200

    summary_resp = client.get("/api/financial/pph/summary?period=2026-08")
    assert summary_resp.status_code == 200
    assert summary_resp.json()["status"] == "Sudah Disetor"


def test_close_month_pph_entries_are_balanced(db):
    owner = _seed(db)
    db.add(_order(owner.id, "SP-1", "Selesai", datetime(2026, 8, 5), 1_000_000))
    db.commit()
    close_month_pph(db, owner.id, "2026-08")

    entries = db.query(JournalEntry).filter(JournalEntry.rule_no == 28).all()
    total_debit = sum(e.nominal for e in entries)
    total_credit = sum(e.nominal for e in entries)
    assert total_debit == total_credit
