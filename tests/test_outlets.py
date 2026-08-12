"""
Acceptance criteria for Epic H's foundation half (Outlet entity + management
UI). The "Kas per Outlet" balance report is deferred to Epic B (see
app/services/outlet_service.py docstring) and has no tests here yet.
"""

from datetime import datetime

from app.models.db_models import OmniOrder, Outlet
from app.services.outlet_service import (
    _INITIAL_OUTLETS,
    create_outlet,
    seed_outlets,
    set_active,
)


def test_seed_creates_initial_outlets(db):
    seed_outlets(db)
    outlets = db.query(Outlet).all()
    assert len(outlets) == len(_INITIAL_OUTLETS)

    by_code = {o.kode_outlet: o for o in outlets}
    for kode_outlet, nama_outlet, alamat in _INITIAL_OUTLETS:
        outlet = by_code[kode_outlet]
        assert outlet.nama_outlet == nama_outlet
        assert outlet.alamat == alamat
        assert outlet.is_active is True


def test_seed_is_idempotent(db):
    seed_outlets(db)
    seed_outlets(db)
    assert db.query(Outlet).count() == len(_INITIAL_OUTLETS)


def test_outlets_endpoint_lists_seeded_outlets(client, db):
    seed_outlets(db)

    response = client.get("/api/outlets")
    assert response.status_code == 200

    codes = {o["kode_outlet"] for o in response.json()}
    assert codes == {kode for kode, _, _ in _INITIAL_OUTLETS}


def test_create_outlet_endpoint_adds_new_outlet(client, db):
    response = client.post("/api/outlets", json={"nama_outlet": "Cabang Surabaya", "alamat": "Jl. Pemuda No. 5"})
    assert response.status_code == 200

    body = response.json()
    assert body["nama_outlet"] == "Cabang Surabaya"
    assert body["alamat"] == "Jl. Pemuda No. 5"
    assert body["is_active"] is True
    assert db.get(Outlet, body["kode_outlet"]) is not None


def test_create_outlet_dedupes_code_on_name_collision(db):
    first = create_outlet(db, "Cabang Baru", "Alamat 1")
    second = create_outlet(db, "Cabang Baru", "Alamat 2")
    assert first.kode_outlet != second.kode_outlet


def test_toggle_endpoint_flips_active_status(client, db):
    seed_outlets(db)
    kode_outlet = _INITIAL_OUTLETS[0][0]

    response = client.post(f"/api/outlets/{kode_outlet}/toggle", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    db.refresh(db.get(Outlet, kode_outlet))
    assert db.get(Outlet, kode_outlet).is_active is False


def test_toggle_unknown_outlet_returns_404(client, db):
    response = client.post("/api/outlets/DOES-NOT-EXIST/toggle", json={"is_active": True})
    assert response.status_code == 404


def test_set_active_raises_for_unknown_code(db):
    try:
        set_active(db, "DOES-NOT-EXIST", True)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_omni_order_outlet_id_is_optional_and_accepts_a_real_outlet(db):
    seed_outlets(db)
    kode_outlet = _INITIAL_OUTLETS[0][0]

    online_order = OmniOrder(
        platform_order_id="ORD-ONLINE-1", channel="shopee", fulfillment_type="shipment",
        status="new", order_time=datetime.utcnow(),
    )
    offline_order = OmniOrder(
        platform_order_id="ORD-POS-1", channel="offline_pos", fulfillment_type="shipment",
        status="new", order_time=datetime.utcnow(), outlet_id=kode_outlet,
    )
    db.add_all([online_order, offline_order])
    db.commit()

    assert db.get(OmniOrder, "ORD-ONLINE-1").outlet_id is None
    assert db.get(OmniOrder, "ORD-POS-1").outlet_id == kode_outlet
