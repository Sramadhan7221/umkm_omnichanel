"""
Acceptance criteria for Customer Request 1 Epic I (Fondasi User & Role:
Superadmin/Owner/Admin). See docs/CLAUDE.md's Keputusan Scope CR1 §5 for the
exact endpoint-by-endpoint permission mapping these tests check against.
"""

from app.main import app
from app.models.db_models import Outlet, Product, User
from app.routers.auth import _get_session_role
from app.services.auth_service import hash_new_password
from app.services.chart_of_accounts_service import seed_accounts
from app.services.inventory_service import create_product
from app.services.journal_engine_service import seed_mapping_rules, seed_pos_payment_extension


def _make_user(db, email, role, status="approved", is_active=True, owner_id=None):
    salt_hex, hash_hex = hash_new_password("Qwertyz!1")
    user = User(
        email=email, password_hash=hash_hex, password_salt=salt_hex,
        role=role, status=status, is_active=is_active, owner_id=owner_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _as_role(client, role):
    app.dependency_overrides[_get_session_role] = lambda: role


def test_superadmin_denied_business_endpoint(client, db):
    _as_role(client, "superadmin")
    response = client.get("/api/inventory")
    assert response.status_code == 403


def test_admin_denied_product_create(client, db):
    _as_role(client, "admin")
    response = client.post("/api/inventory/products", data={
        "sku": "SKU-1", "name": "Produk", "stock_qty": "1",
        "reference_price": "1000", "cogs_price": "500", "unit_label": "Pcs",
    })
    assert response.status_code == 403


def test_admin_allowed_stock_adjust(client, db):
    create_product(
        db, sku="SKU-1", name="Produk Uji", description="", stock_qty=10,
        reference_price=10_000, cogs_price=5_000, unit_label="Pcs", ppn_rate=11.0, channels=[],
    )
    _as_role(client, "admin")
    response = client.post("/api/inventory/SKU-1/adjust", json={"quantity": 15, "note": "opname"})
    assert response.status_code == 200
    assert response.json()["stock_qty"] == 15


def test_admin_allowed_pos_sales(client, db):
    seed_accounts(db)
    seed_mapping_rules(db)
    seed_pos_payment_extension(db)
    db.add(Outlet(kode_outlet="OUT-1", nama_outlet="Toko Utama"))
    db.add(Product(sku="SKU-1", name="Kopi Susu", reference_price=18_000, cogs_price=8_000, stock_qty=10))
    db.commit()

    _as_role(client, "admin")
    response = client.post("/api/pos/sales", json={
        "outlet_id": "OUT-1", "rule_no": 8, "items": [{"sku": "SKU-1", "qty": 1}],
    })
    assert response.status_code == 200


def test_owner_creates_admin_account(client, db):
    response = client.post("/api/auth/create-admin", json={
        "email": "admin1@example.com", "password": "Qwertyz!1",
    })
    assert response.status_code == 200

    created = db.query(User).filter(User.email == "admin1@example.com").first()
    assert created is not None
    assert created.role == "admin"
    assert created.owner_id == 1  # client fixture's require_login_api override returns user_id=1


def test_login_rejects_pending_owner(client, db):
    _make_user(db, "pending@example.com", "owner", status="pending")
    response = client.post("/api/auth/login", json={"email": "pending@example.com", "password": "Qwertyz!1"})
    assert response.status_code == 401
    assert "menunggu persetujuan" in response.json()["detail"]


def test_login_rejects_rejected_owner(client, db):
    _make_user(db, "rejected@example.com", "owner", status="rejected")
    response = client.post("/api/auth/login", json={"email": "rejected@example.com", "password": "Qwertyz!1"})
    assert response.status_code == 401
    assert "ditolak" in response.json()["detail"]


def test_login_rejects_inactive_user(client, db):
    _make_user(db, "inactive@example.com", "owner", is_active=False)
    response = client.post("/api/auth/login", json={"email": "inactive@example.com", "password": "Qwertyz!1"})
    assert response.status_code == 401
    assert "dinonaktifkan" in response.json()["detail"]


def test_login_succeeds_for_approved_active_owner(client, db):
    _make_user(db, "owner@example.com", "owner")
    response = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Qwertyz!1"})
    assert response.status_code == 200
    assert response.json()["role"] == "owner"
