"""
Acceptance criteria for Epic F (Neraca & Laba Rugi dari Saldo Akun). See
docs/Analisis_Kebutuhan_Modul_Akuntansi_POS.pdf Bagian 4 and
app/services/balance_sheet_service.py's module docstring for the
"no Laba Ditahan account in the CoA" gap this engine works around.
"""

from datetime import datetime

from app.models.db_models import Outlet
from app.services.balance_sheet_service import get_balance_sheet, get_kas_per_outlet, get_profit_loss
from app.services.chart_of_accounts_service import seed_accounts
from app.services.journal_engine_service import post_journal


def _seed(db):
    seed_accounts(db)


def _post(db, kode_debet, kode_kredit, nominal, tanggal, **kwargs):
    return post_journal(
        db, kode_debet=kode_debet, kode_kredit=kode_kredit, nominal=nominal,
        tanggal=tanggal, sumber_dokumen="test", keterangan="test", **kwargs,
    )


def _standard_scenario(db, tanggal=datetime(2026, 8, 10)):
    """Revenue 100k, discount 2k (contra), commission fee 5k, COGS 40k —
    a self-contained, individually-balanced set of entries (each row is one
    debit leg + one credit leg of the same nominal, so the whole set nets
    to zero automatically)."""
    _post(db, "1121", "4111", 100_000, tanggal)  # revenue: debit piutang, credit pendapatan
    _post(db, "4211", "1121", 2_000, tanggal)     # discount: debit potongan (contra), credit piutang
    _post(db, "5212", "1121", 5_000, tanggal)     # commission: debit beban, credit piutang
    _post(db, "5110", "1131", 40_000, tanggal)    # COGS: debit HPP, credit persediaan


def test_profit_loss_nets_contra_revenue_and_splits_hpp(db):
    _seed(db)
    _standard_scenario(db)

    result = get_profit_loss(db, datetime(2026, 8, 1), datetime(2026, 8, 31))

    assert result["total_pendapatan"] == 98_000  # 100,000 - 2,000 discount
    assert result["hpp"] == 40_000
    assert result["laba_kotor"] == 58_000
    assert result["total_beban_operasional"] == 5_000
    assert result["laba_bersih"] == 53_000
    assert {"kode_akun": "5212", "nama_akun": "Beban Komisi Admin / Platform", "jumlah": 5_000} in result["beban_operasional_breakdown"]
    assert not any(item["kode_akun"] == "5110" for item in result["beban_operasional_breakdown"])


def test_profit_loss_is_period_bounded(db):
    _seed(db)
    _standard_scenario(db, tanggal=datetime(2026, 7, 15))

    august_result = get_profit_loss(db, datetime(2026, 8, 1), datetime(2026, 8, 31))
    july_result = get_profit_loss(db, datetime(2026, 7, 1), datetime(2026, 7, 31))

    assert august_result["total_pendapatan"] == 0
    assert july_result["total_pendapatan"] == 98_000


def test_balance_sheet_balances_with_computed_laba_ditahan(db):
    _seed(db)
    _standard_scenario(db)

    result = get_balance_sheet(db, datetime(2026, 8, 31))

    assert result["is_balanced"] is True
    assert result["total_aset"] == result["total_kewajiban_ekuitas"]

    ekuitas_labels = {row["nama_akun"]: row["saldo"] for row in result["ekuitas"]}
    assert ekuitas_labels["Laba Ditahan (Berjalan)"] == 53_000  # matches laba_bersih above
    laba_ditahan_row = next(r for r in result["ekuitas"] if r["nama_akun"] == "Laba Ditahan (Berjalan)")
    assert laba_ditahan_row["is_computed"] is True


def test_balance_sheet_cumulative_includes_prior_months(db):
    _seed(db)
    _standard_scenario(db, tanggal=datetime(2026, 6, 1))

    neraca_august = get_balance_sheet(db, datetime(2026, 8, 31))
    ekuitas = {row["nama_akun"]: row["saldo"] for row in neraca_august["ekuitas"]}
    assert ekuitas["Laba Ditahan (Berjalan)"] == 53_000  # June's activity still counted as of August


def test_balance_sheet_1111_shows_per_outlet_breakdown(db):
    _seed(db)
    db.add_all([
        Outlet(kode_outlet="OUT-1", nama_outlet="Toko A"),
        Outlet(kode_outlet="OUT-2", nama_outlet="Toko B"),
    ])
    db.commit()

    _post(db, "1111", "4114", 50_000, datetime(2026, 8, 1), outlet_id="OUT-1")
    _post(db, "1111", "4114", 30_000, datetime(2026, 8, 2), outlet_id="OUT-2")

    result = get_balance_sheet(db, datetime(2026, 8, 31))
    kas_row = next(r for r in result["aset"] if r["kode_akun"] == "1111")

    assert kas_row["saldo"] == 80_000
    breakdown = {b["kode_outlet"]: b["saldo"] for b in kas_row["breakdown_outlet"]}
    assert breakdown == {"OUT-1": 50_000, "OUT-2": 30_000}


def test_get_kas_per_outlet_matches_balance_sheet_breakdown(db):
    _seed(db)
    db.add(Outlet(kode_outlet="OUT-1", nama_outlet="Toko A"))
    db.commit()
    _post(db, "1111", "4114", 20_000, datetime(2026, 8, 1), outlet_id="OUT-1")

    breakdown = get_kas_per_outlet(db, datetime(2026, 8, 31))
    assert breakdown == [{"kode_outlet": "OUT-1", "nama_outlet": "Toko A", "saldo": 20_000}]


def test_balance_sheet_endpoint_and_profit_loss_endpoint(client, db):
    _seed(db)
    _standard_scenario(db)

    pl_resp = client.get("/api/financial/profit-loss?start=2026-08-01&end=2026-08-31")
    assert pl_resp.status_code == 200
    assert pl_resp.json()["laba_bersih"] == 53_000

    bs_resp = client.get("/api/financial/balance-sheet?as_of=2026-08-31")
    assert bs_resp.status_code == 200
    assert bs_resp.json()["is_balanced"] is True
