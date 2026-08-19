"""
SQLAlchemy ORM models — the persistence-layer equivalent of the earlier
Frappe DocTypes (Omni Order / Omni Order Item / Omni Order Fee). Field names
and shape are kept identical on purpose, so the mapping from CanonicalOrder
(app.models.canonical) is a straight port from the Frappe version.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Auth (Fase 5, extended Customer Request 1 Epic I) — Superadmin/Owner/Admin
# roles. Password is stored as a PBKDF2-HMAC hash (stdlib hashlib, no extra
# dependency) rather than plaintext or a lighter hash.
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    created_time = Column(DateTime, default=datetime.utcnow)
    role = Column(String, nullable=False)  # "superadmin" | "owner" | "admin"
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=True)  # set only for role="admin"
    status = Column(String, nullable=False, default="approved")  # "pending" | "approved" | "rejected"
    is_active = Column(Boolean, nullable=False, default=True)
    business_name = Column(String, nullable=True)  # Owner's business name (Epic J register form)


# ---------------------------------------------------------------------------
# Platform management (Fase 5) — lets the user turn individual channels on
# or off. Order generation (both the startup auto-seed and the manual "+1
# per platform" sync) only touches platforms where is_active is True.
# ---------------------------------------------------------------------------

class Platform(Base):
    __tablename__ = "platform"
    __table_args__ = (UniqueConstraint("owner_id", "code", name="uq_platform_owner_code"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    code = Column(String, nullable=False)             # matches Channel enum value, e.g. "shopee" — unique per owner, not globally (Epic K)
    name = Column(String, nullable=False)             # display label, e.g. "Shopee"
    fulfillment_type = Column(String, nullable=False)  # "Pengiriman" | "Ambil Instan"
    is_active = Column(Boolean, default=False, nullable=False)
    fee_rate = Column(Float, default=0)  # persen, mis. 10.0 = 10% — dipakai di form Tambah Produk
    created_time = Column(DateTime, default=datetime.utcnow)


class OmniOrder(Base):
    __tablename__ = "omni_order"
    __table_args__ = (UniqueConstraint("owner_id", "platform_order_id", name="uq_omni_order_owner_platform_order_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    # Unique per owner, not globally (Epic K) — e.g. POS nota numbers like
    # "NT-202608001" are generated per-owner and can repeat across tenants.
    platform_order_id = Column(String, nullable=False)
    channel = Column(String, nullable=False, index=True)
    fulfillment_type = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    raw_status = Column(String)
    order_time = Column(DateTime, nullable=False, index=True)
    updated_time = Column(DateTime, default=datetime.utcnow)
    customer_ref = Column(String)
    payout_batch_ref = Column(String, nullable=True)
    gross_amount = Column(Float, default=0)
    net_amount = Column(Float, default=0)

    items = relationship("OmniOrderItem", back_populates="order", cascade="all, delete-orphan")
    fees = relationship("OmniOrderFee", back_populates="order", cascade="all, delete-orphan")


class OmniOrderItem(Base):
    __tablename__ = "omni_order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to OmniOrder's surrogate id (not platform_order_id, which is only
    # unique per owner since Epic K and can't safely back a shared relationship
    # join across tenants — see OmniOrder's owner_id comment).
    order_id = Column(Integer, ForeignKey("omni_order.id"), nullable=False)
    sku = Column(String, nullable=False)
    platform_item_id = Column(String)
    item_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, default=0)
    modifiers = Column(Text, default="")

    order = relationship("OmniOrder", back_populates="items")


class OmniOrderFee(Base):
    __tablename__ = "omni_order_fee"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to OmniOrder's surrogate id — see OmniOrderItem.order_id's comment above.
    order_id = Column(Integer, ForeignKey("omni_order.id"), nullable=False)
    category = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    label = Column(String)

    order = relationship("OmniOrder", back_populates="fees")


# ---------------------------------------------------------------------------
# Inventory Sync (Fase 2) — central stock ledger + SKU-to-platform mapping.
# One internal Product can map to N platform listings (blueprint Section
# 1.1): in this demo each SKU happens to map 1:1 since Shopee (fashion) and
# GrabFood (food) are naturally different catalogs, but the mapping table
# is generic and ready for a real cross-channel SKU later.
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("owner_id", "sku", name="uq_product_owner_sku"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    sku = Column(String, nullable=False)  # unique per owner, not globally (Epic K)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    reference_price = Column(Float, default=0)  # harga dasar
    ppn_rate = Column(Float, default=11.0)       # persen PPN, default tarif standar 2026 (11%)
    # HPP (Epic D) — owner-set cost of goods, single source of truth synced
    # out to every platform and later consumed by Epic B's automatic COGS
    # journal posting (5110 HPP Produk). Required at creation, so nullable
    # is False; run_lightweight_migrations backfills existing rows to 0/"Pcs".
    cogs_price = Column(Float, nullable=False, default=0)
    unit_label = Column(String, nullable=False, default="Pcs")  # Satuan: Pcs/Botol/Cup/dst
    stock_qty = Column(Integer, default=0, nullable=False)
    low_stock_threshold = Column(Integer, default=10, nullable=False)
    updated_time = Column(DateTime, default=datetime.utcnow)

    mappings = relationship("ProductPlatformMapping", back_populates="product", cascade="all, delete-orphan")
    movements = relationship("StockMovement", back_populates="product", cascade="all, delete-orphan")
    images = relationship(
        "ProductImage", back_populates="product", cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )
    audit_logs = relationship(
        "ProductAuditLog", back_populates="product", cascade="all, delete-orphan",
        order_by="ProductAuditLog.changed_time.desc()",
    )


class ProductPlatformMapping(Base):
    __tablename__ = "product_platform_mapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to Product's surrogate id (not sku, which is only unique per owner
    # since Epic K and can't safely back a shared relationship join across
    # tenants — see Product's owner_id comment).
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    channel = Column(String, nullable=False)          # display label, e.g. "Shopee"
    platform_item_id = Column(String, nullable=False)  # the platform's own item/menu id

    product = relationship("Product", back_populates="mappings")


class ProductImage(Base):
    """Product photos (Fase 6 — Tambah/Edit Produk). `is_primary` marks the
    one used as the showcase image on the selected platform(s); the rest are
    the gallery. Files are stored under app/static/uploads/products/<sku>/ —
    same ephemeral-storage caveat as SQLite: attach a persistent volume on
    Railway if uploads need to survive redeploys."""
    __tablename__ = "product_image"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to Product's surrogate id — see ProductPlatformMapping.product_id's comment above.
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    file_path = Column(String, nullable=False)  # e.g. "/static/uploads/products/SKU-001/abc123.jpg"
    is_primary = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0)
    uploaded_time = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="images")


class ProductAuditLog(Base):
    """Edit history for products (Fase 6) — separate from StockMovement
    (which only tracks quantity changes): this covers name/price/description/
    image edits, so 'what changed and when' is answerable for the whole
    product record, not just its stock."""
    __tablename__ = "product_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to Product's surrogate id — see ProductPlatformMapping.product_id's comment above.
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    changed_fields = Column(Text, nullable=False)  # JSON: {"field": {"old": ..., "new": ...}}
    note = Column(String, default="")
    changed_time = Column(DateTime, default=datetime.utcnow, index=True)

    product = relationship("Product", back_populates="audit_logs")


class StockMovement(Base):
    """Audit trail for every stock change — order-driven deductions and
    manual overrides both land here, so 'why is stock at this number' is
    always answerable (blueprint's central stock ledger concept)."""
    __tablename__ = "stock_movement"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to Product's surrogate id — see ProductPlatformMapping.product_id's comment above.
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    change_qty = Column(Integer, nullable=False)   # negative = deduction, positive = addition
    resulting_qty = Column(Integer, nullable=False)
    source = Column(String, nullable=False)         # "order" | "manual"
    note = Column(String, default="")
    created_time = Column(DateTime, default=datetime.utcnow, index=True)

    product = relationship("Product", back_populates="movements")


# ---------------------------------------------------------------------------
# Financial & Accounting (Fase 3) — manual expense entries. Revenue and fee
# figures for the Income Statement / Cash Flow come straight from OmniOrder
# and OmniOrderFee (already populated by the Order Inbox module); this table
# only covers the side that has no platform data source: operating expenses.
# ---------------------------------------------------------------------------

class Expense(Base):
    __tablename__ = "expense"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    category = Column(String, nullable=False)   # free-text, e.g. "Sewa", "Gaji", "Kemasan"
    amount = Column(Float, nullable=False)
    note = Column(String, default="")
    expense_date = Column(DateTime, nullable=False, index=True)
    created_time = Column(DateTime, default=datetime.utcnow)

    # Journal Engine (Epic B) — which of the 4 Expense-triggered mapping
    # rules (#26/#30/#31/#32) this expense posts through. A closed set, not
    # free text, because those 4 rules are the only debit-account x
    # payment-source pairs the mapping matrix actually defines for manual
    # expenses — required so every Expense produces exactly one JournalEntry.
    rule_no = Column(Integer, ForeignKey("transaction_mapping_rule.no"), nullable=False, default=32)


# ---------------------------------------------------------------------------
# Reconciliation (Fase 4) — one Settlement row per order, comparing the
# amount the platform actually paid out against the net_amount our own
# records expected. This is the piece MSME owners struggle with most
# (blueprint Section 1.2): platform payout reports rarely line up perfectly
# with what the seller calculated, and this table is where that gap gets
# surfaced instead of silently absorbed.
# ---------------------------------------------------------------------------

class Settlement(Base):
    __tablename__ = "settlement"

    settlement_id = Column(String, primary_key=True)  # "SETL-<uuid10>" — globally unique, no owner-scoped restructuring needed
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    # Plain String business key, not a DB-enforced FK — omni_order.platform_order_id
    # is only unique per owner since Epic K. Always queried together with this
    # row's own owner_id, so no ambiguity (see reconciliation_service.py).
    platform_order_id = Column(String, nullable=False, index=True)
    channel = Column(String, nullable=False)
    expected_amount = Column(Float, nullable=False)   # our own net_amount at settlement time
    payout_amount = Column(Float, nullable=False)     # what the (simulated) platform payout report says
    diff_amount = Column(Float, nullable=False)       # payout_amount - expected_amount
    status = Column(String, nullable=False, index=True)  # "Cocok" | "Selisih"
    batch_ref = Column(String)
    settlement_date = Column(DateTime, nullable=False, index=True)
    created_time = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Chart of Accounts (Epic A) — the account table double-entry bookkeeping is
# built on. Seeded from docs/chart_of_accounts.csv (source of truth: the
# business owner's own SAK EMKM account list), not hardcoded here. Journal
# posting (Epic B) and the balance sheet (Epic F) both read this table;
# nothing else in Epic A writes to it besides the seed.
# ---------------------------------------------------------------------------

class Account(Base):
    __tablename__ = "account"
    __table_args__ = (UniqueConstraint("owner_id", "kode_akun", name="uq_account_owner_kode_akun"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    kode_akun = Column(String, nullable=False)  # unique per owner, not globally (Epic K)
    nama_akun = Column(String, nullable=False)
    penjelasan_awam = Column(Text, default="")
    kelompok_utama = Column(String, nullable=False)  # Aset|Kewajiban|Ekuitas|Pendapatan|Beban
    saldo_normal = Column(String, default="")          # "Debet" | "Kredit" | "" untuk header
    # Plain String, not a DB-enforced FK (self-referencing) — kode_akun is only
    # unique per owner since Epic K. Resolved in application code instead.
    parent_code = Column(String, nullable=True)
    is_header = Column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------------------
# Journal Engine (Epic B) — TransactionMappingRule is the 32-row "aturan
# jurnal per event x platform" seeded from docs/transaction_mapping_matrix.csv
# (source of truth: the business owner's own prototype, NOT hardcoded here —
# same principle as Epic A's Account seed). JournalEntry is the resulting
# double-entry ledger: one row per posted transaction, always exactly one
# debit leg + one credit leg of the same nominal (so "total debet = total
# kredit" holds by construction, not by a separate balance-check step).
# ---------------------------------------------------------------------------

class TransactionMappingRule(Base):
    __tablename__ = "transaction_mapping_rule"

    no = Column(Integer, primary_key=True)  # matches the sheet's own row numbering (1-32), not autoincrement
    kategori_transaksi = Column(String, nullable=False)
    event_trigger = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    # Plain String, not a DB-enforced FK — account.kode_akun is only unique per
    # owner since Epic K, but this table stays GLOBAL (shared config, not
    # owner-scoped), so it can't target one owner's Account rows via FK anyway.
    # Resolved in application code (chart_of_accounts_service.get_account).
    kode_debet = Column(String, nullable=False)
    nama_akun_debet = Column(String, nullable=False)
    kode_kredit = Column(String, nullable=False)
    nama_akun_kredit = Column(String, nullable=False)
    trigger_dokumen = Column(String, default="")
    aturan_keterangan = Column(Text, default="")


class JournalEntry(Base):
    __tablename__ = "journal_entry"

    no_jurnal = Column(String, primary_key=True)  # generated "JE-<uuid10>" — globally unique, no owner-scoped restructuring needed
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    tanggal = Column(DateTime, nullable=False, index=True)
    # Plain String, not DB-enforced FKs — account.kode_akun is only unique per
    # owner since Epic K. Resolved in application code instead (always the
    # same owner_id as this JournalEntry itself).
    kode_debet = Column(String, nullable=False)
    nama_akun_debet = Column(String, nullable=False)
    kode_kredit = Column(String, nullable=False)
    nama_akun_kredit = Column(String, nullable=False)
    nominal = Column(Float, nullable=False)
    sumber_dokumen = Column(String, default="")
    keterangan = Column(String, default="")
    status = Column(String, nullable=False, default="OTOMATIS")  # "OTOMATIS" | "MANUAL"

    # Nearest matching rule, kept for traceability even when the posted accounts
    # were generalized beyond that rule's literal row (see journal_engine_service).
    rule_no = Column(Integer, ForeignKey("transaction_mapping_rule.no"), nullable=True)

    # Plain String business key (platform_order_id), not a DB-enforced FK —
    # omni_order.platform_order_id is only unique per owner since Epic K.
    # Always queried together with this row's own owner_id (see
    # journal_engine_service._pos_original_payment_account), so no ambiguity.
    order_id = Column(String, nullable=True)
    settlement_id = Column(String, ForeignKey("settlement.settlement_id"), nullable=True)
    expense_id = Column(Integer, ForeignKey("expense.id"), nullable=True)

    created_time = Column(DateTime, default=datetime.utcnow, index=True)
