"""
Inventory Sync service (Fase 2 dari roadmap) — central stock ledger,
SKU-to-platform mapping, dan push stok ke adapter platform.

Alur nyata yang disimulasikan di sini: saat order baru masuk (lewat
sync_mock_orders), stok internal berkurang otomatis lalu di-push ke semua
platform yang terhubung ke SKU tersebut (blueprint Section 1.1 & 3.5 —
"outbound stock sync"). Penyesuaian manual (mis. koreksi stok opname) juga
lewat jalur yang sama supaya audit trail (StockMovement) selalu konsisten.
"""

from __future__ import annotations

import json
import shutil
import uuid as uuid_lib
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.mock_adapters.mock_gofood import MockGoFoodAdapter
from app.mock_adapters.mock_grabfood import MockGrabFoodAdapter
from app.mock_adapters.mock_shopee import MockShopeeAdapter
from app.mock_adapters.mock_tiktokshop import MockTikTokShopAdapter
from app.models.canonical import CanonicalOrder
from app.models.db_models import (
    Product,
    ProductAuditLog,
    ProductImage,
    ProductPlatformMapping,
    StockMovement,
)

UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "static" / "uploads" / "products"

# Fields the Edit Produk form can change, and their human-readable labels
# for the audit trail (Fase 6).
_TRACKED_FIELDS = {
    "name": "Nama Produk",
    "description": "Deskripsi",
    "reference_price": "Harga Dasar",
    "cogs_price": "HPP (Harga Pokok)",
    "unit_label": "Satuan",
    "ppn_rate": "PPN (%)",
    "stock_qty": "Stok",
}

# Fields whose change should trigger an outbound price sync (Epic D) to every
# mapped platform, distinct from stock-triggered sync.
_PRICE_FIELD_LABELS = {"Harga Dasar", "HPP (Harga Pokok)"}

# Katalog awal demo. Setiap produk dipetakan ke platform SEJENIS: fashion ke
# Shopee + TikTok Shop (sama-sama e-commerce/pengiriman), makanan ke
# GrabFood + GoFood (sama-sama food delivery/ambil instan) — mendemokan
# konsep "satu SKU bisa ke banyak platform" dari mapping table Fase 2, dan
# memastikan TikTok Shop/GoFood punya produk begitu diaktifkan di menu
# Platform. HPP (Epic D) dipatok kasar di sekitar 55-65% dari harga jual —
# angka demo, bukan hasil hitung biaya produksi riil.
_INITIAL_CATALOG = [
    # (sku, nama, harga_acuan, hpp, satuan, [channel, ...], stok_awal)
    ("SKU-BAJU-001", "Kaos Polos Katun Combed", 75_000, 42_000, "Pcs", ["Shopee", "TikTok Shop"], 50),
    ("SKU-TAS-014", "Tas Selempang Kanvas", 120_000, 68_000, "Pcs", ["Shopee", "TikTok Shop"], 50),
    ("SKU-SPT-007", "Sepatu Sneakers Casual", 210_000, 125_000, "Pcs", ["Shopee", "TikTok Shop"], 50),
    ("SKU-AKS-022", "Gelang Kulit Handmade", 45_000, 22_000, "Pcs", ["Shopee", "TikTok Shop"], 50),
    ("MENU-NASI-01", "Nasi Goreng Spesial", 32_000, 18_000, "Porsi", ["GrabFood", "GoFood"], 50),
    ("MENU-AYAM-02", "Ayam Geprek Sambal Bawang", 28_000, 16_000, "Porsi", ["GrabFood", "GoFood"], 50),
    ("MENU-MIE-03", "Mie Ayam Bakso", 25_000, 14_000, "Porsi", ["GrabFood", "GoFood"], 50),
    ("MENU-MIN-04", "Es Teh Manis", 8_000, 3_000, "Gelas", ["GrabFood", "GoFood"], 50),
]


def seed_products(db: Session) -> None:
    """Seed katalog produk awal sekali saja (kalau tabel masih kosong)."""
    if db.query(Product).count() > 0:
        return

    for sku, name, price, cogs_price, unit_label, channels, initial_stock in _INITIAL_CATALOG:
        product = Product(
            sku=sku,
            name=name,
            reference_price=price,
            cogs_price=cogs_price,
            unit_label=unit_label,
            stock_qty=initial_stock,
            low_stock_threshold=10,
        )
        db.add(product)
        db.flush()  # supaya FK product.sku tersedia untuk mapping di bawah
        for channel in channels:
            db.add(ProductPlatformMapping(sku=sku, channel=channel, platform_item_id=sku))
        db.add(StockMovement(
            sku=sku, change_qty=initial_stock, resulting_qty=initial_stock,
            source="manual", note="Stok awal (seed demo)",
        ))

    db.commit()


def _get_adapter(channel_label: str):
    """Mock adapter registry untuk keempat platform yang tersedia di menu
    Platform (blueprint Fase 5)."""
    return {
        "Shopee": MockShopeeAdapter,
        "TikTok Shop": MockTikTokShopAdapter,
        "GrabFood": MockGrabFoodAdapter,
        "GoFood": MockGoFoodAdapter,
    }.get(channel_label, lambda: None)()


def _push_stock_to_platforms(product: Product) -> None:
    for mapping in product.mappings:
        adapter = _get_adapter(mapping.channel)
        if adapter is None:
            continue
        # Mock push — dalam adapter asli ini akan memanggil endpoint update
        # stok resmi platform. Hasilnya (SyncResult) tidak diblokir di sini;
        # kegagalan push nyata sebaiknya masuk ke Sync Health Dashboard
        # (belum dibangun di iterasi ini).
        adapter.push_stock_update(mapping.platform_item_id, product.stock_qty)


def _push_price_to_platforms(product: Product) -> None:
    """Outbound price sync (Epic D) — Master Barang is the single source of
    truth for selling price + HPP, pushed out on every create/edit so no
    platform ever drifts to a different number. Same fire-and-forget
    treatment as _push_stock_to_platforms: failures aren't blocked on here."""
    for mapping in product.mappings:
        adapter = _get_adapter(mapping.channel)
        if adapter is None:
            continue
        adapter.push_price_update(mapping.platform_item_id, product.reference_price, product.cogs_price)


def deduct_stock_for_order(db: Session, order: CanonicalOrder) -> None:
    """Dipanggil hanya untuk order yang BENAR-BENAR baru (bukan re-sync order
    yang sudah ada), supaya stok tidak berkurang dua kali untuk order yang
    sama."""
    for item in order.items:
        product = db.get(Product, item.sku)
        if product is None:
            # SKU dari mock adapter tidak ada di katalog — seharusnya tidak
            # terjadi di demo ini, tapi jangan sampai proses sync gagal
            # gara-gara ini.
            continue

        change = -item.quantity
        product.stock_qty = max(product.stock_qty + change, 0)
        product.updated_time = datetime.utcnow()
        db.add(StockMovement(
            sku=product.sku, change_qty=change, resulting_qty=product.stock_qty,
            source="order", note=f"Pesanan {order.platform_order_id}",
        ))
        db.commit()
        db.refresh(product)
        _push_stock_to_platforms(product)


def restore_stock_for_order(db: Session, order) -> None:
    """Mirror of deduct_stock_for_order — Epic G's retur flow, called only
    when the returned goods came back in good, resellable condition. Takes
    the persisted OmniOrder (not a CanonicalOrder) since retur always acts
    on an order that already exists."""
    for item in order.items:
        product = db.get(Product, item.sku)
        if product is None:
            continue

        change = item.quantity
        product.stock_qty += change
        product.updated_time = datetime.utcnow()
        db.add(StockMovement(
            sku=product.sku, change_qty=change, resulting_qty=product.stock_qty,
            source="retur", note=f"Retur {order.platform_order_id}",
        ))
        db.commit()
        db.refresh(product)
        _push_stock_to_platforms(product)


def adjust_stock(db: Session, sku: str, new_qty: int, note: str = "") -> Product:
    """Override manual (mis. hasil stok opname)."""
    product = db.get(Product, sku)
    if product is None:
        raise ValueError(f"SKU '{sku}' tidak ditemukan")

    change = new_qty - product.stock_qty
    product.stock_qty = new_qty
    product.updated_time = datetime.utcnow()
    db.add(StockMovement(
        sku=sku, change_qty=change, resulting_qty=new_qty,
        source="manual", note=note or "Penyesuaian manual",
    ))
    db.commit()
    db.refresh(product)
    _push_stock_to_platforms(product)
    return product


def get_products(db: Session) -> list[Product]:
    return db.query(Product).order_by(Product.sku).all()


def get_movements(db: Session, sku: str, limit: int = 20) -> list[StockMovement]:
    return (
        db.query(StockMovement)
        .filter(StockMovement.sku == sku)
        .order_by(StockMovement.created_time.desc())
        .limit(limit)
        .all()
    )


def get_products_for_channel(db: Session, channel_label: str) -> list[tuple[str, str, float]]:
    """(sku, name, reference_price) tuples for every product mapped to this
    platform — used by the "+1 order per active platform" event so new mock
    orders only ever pick from products the user has actually mapped there,
    instead of an adapter's hardcoded internal catalog."""
    mappings = (
        db.query(ProductPlatformMapping)
        .filter(ProductPlatformMapping.channel == channel_label)
        .all()
    )
    products = []
    for mapping in mappings:
        product = db.get(Product, mapping.sku)
        if product is not None:
            products.append((product.sku, product.name, product.reference_price))
    return products


# ---------------------------------------------------------------------------
# Tambah / Detail / Edit Produk (Fase 6)
# ---------------------------------------------------------------------------

def _save_image(sku: str, upload_file) -> str:
    """Saves an uploaded file to static/uploads/products/<sku>/ and returns
    the URL path to store in ProductImage.file_path. Same ephemeral-storage
    caveat as SQLite applies here on Railway without a mounted volume."""
    folder = UPLOAD_ROOT / sku
    folder.mkdir(parents=True, exist_ok=True)
    original_name = getattr(upload_file, "filename", "") or "foto.jpg"
    ext = Path(original_name).suffix or ".jpg"
    filename = f"{uuid_lib.uuid4().hex}{ext}"
    dest = folder / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(upload_file.file, f)
    return f"/static/uploads/products/{sku}/{filename}"


def create_product(
    db: Session,
    sku: str,
    name: str,
    description: str,
    stock_qty: int,
    reference_price: float,
    cogs_price: float,
    unit_label: str,
    ppn_rate: float,
    channels: list[str],
    primary_image=None,
    gallery_images: list | None = None,
) -> Product:
    if db.get(Product, sku) is not None:
        raise ValueError(f"SKU '{sku}' sudah dipakai")

    product = Product(
        sku=sku,
        name=name,
        description=description,
        reference_price=reference_price,
        cogs_price=cogs_price,
        unit_label=unit_label,
        ppn_rate=ppn_rate,
        stock_qty=stock_qty,
        low_stock_threshold=10,
    )
    db.add(product)
    db.flush()

    for channel in channels:
        db.add(ProductPlatformMapping(sku=sku, channel=channel, platform_item_id=sku))

    db.add(StockMovement(
        sku=sku, change_qty=stock_qty, resulting_qty=stock_qty,
        source="manual", note="Produk baru ditambahkan",
    ))

    sort_order = 0
    if primary_image is not None and getattr(primary_image, "filename", None):
        path = _save_image(sku, primary_image)
        db.add(ProductImage(sku=sku, file_path=path, is_primary=True, sort_order=sort_order))
        sort_order += 1

    for img in (gallery_images or []):
        if img is None or not getattr(img, "filename", None):
            continue
        path = _save_image(sku, img)
        db.add(ProductImage(sku=sku, file_path=path, is_primary=False, sort_order=sort_order))
        sort_order += 1

    db.commit()
    db.refresh(product)
    _push_stock_to_platforms(product)
    _push_price_to_platforms(product)
    return product


def get_product_detail(db: Session, sku: str) -> Product | None:
    return db.get(Product, sku)


def update_product(
    db: Session,
    sku: str,
    updates: dict,
    new_primary_image=None,
    new_gallery_images: list | None = None,
    remove_image_ids: list[int] | None = None,
    note: str = "",
) -> Product:
    """Applies edits to name/description/price/ppn/stock and/or images, and
    writes ONE ProductAuditLog row summarizing everything that changed —
    this is the audit trail the Edit Produk screen is required to keep."""
    product = db.get(Product, sku)
    if product is None:
        raise ValueError(f"SKU '{sku}' tidak ditemukan")

    changed_fields: dict[str, dict] = {}

    for field, label in _TRACKED_FIELDS.items():
        if field not in updates:
            continue
        old_value = getattr(product, field)
        new_value = updates[field]
        if field in ("reference_price", "cogs_price", "ppn_rate"):
            new_value = float(new_value)
        elif field == "stock_qty":
            new_value = int(new_value)
        if str(old_value) != str(new_value):
            changed_fields[label] = {"old": old_value, "new": new_value}
            setattr(product, field, new_value)

    if "Stok" in changed_fields:
        old_qty = changed_fields["Stok"]["old"]
        new_qty = changed_fields["Stok"]["new"]
        db.add(StockMovement(
            sku=sku, change_qty=new_qty - old_qty, resulting_qty=new_qty,
            source="manual", note=note or "Diedit lewat form Edit Produk",
        ))

    if remove_image_ids:
        removed_any = False
        for image_id in remove_image_ids:
            image = db.get(ProductImage, image_id)
            if image is not None and image.sku == sku:
                db.delete(image)
                removed_any = True
        if removed_any:
            changed_fields["Foto"] = {"old": "sebelumnya", "new": "sebagian dihapus"}

    if new_primary_image is not None and getattr(new_primary_image, "filename", None):
        for img in product.images:
            if img.is_primary:
                img.is_primary = False
        path = _save_image(sku, new_primary_image)
        db.add(ProductImage(sku=sku, file_path=path, is_primary=True, sort_order=0))
        changed_fields["Foto Utama"] = {"old": "sebelumnya", "new": "diganti"}

    for img in (new_gallery_images or []):
        if img is None or not getattr(img, "filename", None):
            continue
        path = _save_image(sku, img)
        max_order = max([i.sort_order for i in product.images], default=0)
        db.add(ProductImage(sku=sku, file_path=path, is_primary=False, sort_order=max_order + 1))
        changed_fields["Foto Tambahan"] = {"old": "-", "new": "ditambahkan foto baru"}

    product.updated_time = datetime.utcnow()

    if changed_fields:
        db.add(ProductAuditLog(
            sku=sku,
            changed_fields=json.dumps(changed_fields, ensure_ascii=False, default=str),
            note=note,
        ))

    db.commit()
    db.refresh(product)

    if "Stok" in changed_fields:
        _push_stock_to_platforms(product)

    if _PRICE_FIELD_LABELS & changed_fields.keys():
        _push_price_to_platforms(product)

    return product


def get_audit_log(db: Session, sku: str, limit: int = 30) -> list[ProductAuditLog]:
    return (
        db.query(ProductAuditLog)
        .filter(ProductAuditLog.sku == sku)
        .order_by(ProductAuditLog.changed_time.desc())
        .limit(limit)
        .all()
    )
