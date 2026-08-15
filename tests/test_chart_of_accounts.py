"""
Acceptance criteria for Epic A (Chart of Accounts), written before the
implementation existed. See docs/Analisis_Kebutuhan_Modul_Akuntansi_POS.pdf
Bagian 4 and docs/chart_of_accounts.csv (source of truth for account data).
"""

import csv

from app.models.db_models import Account
from app.services.chart_of_accounts_service import CSV_PATH, get_account, seed_accounts
from tests.conftest import as_tenant, make_owner


def _csv_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_seed_creates_exact_rows_from_csv(db):
    owner = make_owner(db)
    seed_accounts(db, owner.id)
    csv_rows = _csv_rows()

    accounts = db.query(Account).filter(Account.owner_id == owner.id).all()
    assert len(accounts) == len(csv_rows)

    by_code = {a.kode_akun: a for a in accounts}
    for row in csv_rows:
        account = by_code[row["kode_akun"]]
        assert account.nama_akun == row["nama_akun"]
        assert account.penjelasan_awam == row["penjelasan_awam"]
        assert account.kelompok_utama == row["kelompok_utama"]
        assert account.saldo_normal == row["saldo_normal"]
        assert account.parent_code == (row["parent_code"] or None)
        assert account.is_header == (row["is_header"] == "true")
        assert account.is_outlet_scoped == (row["is_outlet_scoped"] == "true")


def test_accounts_endpoint_grouped_by_kelompok_utama(client, db):
    owner = make_owner(db, email="owner1@example.com")
    seed_accounts(db, owner.id)
    as_tenant(owner.id)

    response = client.get("/api/financial/accounts")
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"Aset", "Kewajiban", "Ekuitas", "Pendapatan", "Beban"}

    csv_rows = _csv_rows()
    expected_group = {row["kode_akun"]: row["kelompok_utama"] for row in csv_rows}
    for kelompok, accounts in body.items():
        for account in accounts:
            assert expected_group[account["kode_akun"]] == kelompok

    total_returned = sum(len(v) for v in body.values())
    assert total_returned == len(csv_rows)


def test_kas_di_tangan_is_outlet_scoped(db):
    owner = make_owner(db)
    seed_accounts(db, owner.id)

    kas = get_account(db, owner.id, "1111")
    assert kas.is_outlet_scoped is True

    ewallet = get_account(db, owner.id, "1112")
    assert ewallet.is_outlet_scoped is False
