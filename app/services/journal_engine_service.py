"""
Journal Engine (Epic B) — turns existing transaction events (order
completed/refunded, settlement payout, manual expense) into balanced
double-entry JournalEntry rows, driven by TransactionMappingRule (seeded from
docs/transaction_mapping_matrix.csv, the business owner's own 32-row
"Matriks Transaction Mapping" — never hardcoded from memory here).

Known gap in the source matrix, resolved per Product Owner's explicit choice:
the 32 rows only write a literal row for e-commerce fee/retur cases (#4, #6,
#19 name account 1121 / "Shopee/Tokopedia/TikTok" specifically) — GrabFood/
GoFood's Logistik/Biaya Layanan/Subsidi Promo fees and refunds have no
literal row. Per the PO's answer, these are posted anyway by generalizing
the rule's *pattern* (same debit account, credit account resolved via
CHANNEL_RECEIVABLE_ACCOUNT for that channel) rather than left unposted.
`rule_no` is still recorded for traceability even when the credit account
was computed rather than copied from that literal row.

Every post_journal() call writes exactly one debit leg + one credit leg of
the same nominal, so "total debet = total kredit" holds by construction for
any batch of entries this module produces — there's no separate multi-line
balance-reject path because the schema can't represent an unbalanced entry.
"""

from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.canonical import CHANNEL_RECEIVABLE_ACCOUNT, CHANNEL_REVENUE_ACCOUNT, Channel
from app.models.db_models import (
    Expense,
    JournalEntry,
    OmniOrder,
    Settlement,
    TransactionMappingRule,
)
from app.services.chart_of_accounts_service import get_account
from app.services.inventory_service import get_product
from app.services.order_service import CHANNEL_LABELS

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "transaction_mapping_matrix.csv"

_LABEL_TO_CHANNEL = {label: Channel(value) for value, label in CHANNEL_LABELS.items()}

# Channel label -> rule no, for the revenue leg posted at order completion.
_REVENUE_RULE_BY_CHANNEL_LABEL = {"Shopee": 1, "TikTok Shop": 3, "GrabFood": 12, "GoFood": 12}

# Channel label -> rule no, for the bank-receipt leg posted at settlement.
_SETTLEMENT_RULE_BY_CHANNEL_LABEL = {"Shopee": 7, "TikTok Shop": 7, "GrabFood": 14, "GoFood": 14}

# Channel label -> rule no, for the retur leg posted on a refunded order.
# Literal matrix row #19 only names e-commerce; generalized to food delivery
# per the PO's answer (see module docstring), same rule_no kept for both.
# Offline POS (Epic G) also uses rule #19 for traceability even though its
# credit account isn't looked up from this map — see
# post_order_refunded_journal's per-order payment-account resolution below.
_RETUR_RULE_BY_CHANNEL_LABEL = {"Shopee": 19, "TikTok Shop": 19, "GrabFood": 19, "GoFood": 19, "Offline POS": 19}

# OmniOrderFee.category label -> (debit account code, nearest rule no).
# Komisi/Biaya Pembayaran/Biaya Layanan all fall under the "biaya layanan/
# komisi admin platform" pattern (5212, rules #5 e-commerce / #13 food
# delivery); Logistik is the "ongkir" pattern (5213, rule #6, generalized to
# food delivery); Subsidi Promo is the "potongan penjualan" pattern (4211,
# rule #4, generalized to food delivery). Categories with no data source
# today (Iklan, Penalti, Lainnya) are intentionally absent — skipped, not
# guessed.
_FEE_DEBIT_ACCOUNT_AND_RULE = {
    "Komisi": ("5212", 5),
    "Biaya Pembayaran": ("5212", 5),
    "Biaya Layanan": ("5212", 13),
    "Logistik": ("5213", 6),
    "Subsidi Promo": ("4211", 4),
}

_COGS_RULE_NO = 24

# POS Kasir payment methods (Epic C). Rules 8 (Tunai) and 9 (QRIS) are
# literal rows from the 32-row Excel matrix. Rules 33/34 (Transfer,
# E-Wallet) do NOT exist in that matrix — the PDF's Epic C task text asks
# for 4 payment methods but the source sheet only ever wrote 2. Per the
# Product Owner's explicit choice this session, they were added using the
# same accounts the matrix already uses for exactly this purpose elsewhere
# (1113 Kas di Bank for #7/#14, 1112 Kas di E-Wallet for #18) — seeded by
# seed_pos_payment_extension() below, NOT from transaction_mapping_matrix.csv,
# so that CSV stays the untouched, literal 32-row Excel source.
POS_PAYMENT_RULE_NOS = [8, 9, 33, 34]

_POS_PAYMENT_EXTENSION_ROWS = [
    # (no, event_trigger, kode_debet, nama_akun_debet)
    (33, "Penjualan via Transfer Bank", "1113", "Kas di Bank"),
    (34, "Penjualan via E-Wallet", "1112", "Kas di E-Wallet"),
]


def seed_mapping_rules(db: Session) -> None:
    if db.query(TransactionMappingRule).count() > 0:
        return
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            db.add(TransactionMappingRule(
                no=int(row["no"]),
                kategori_transaksi=row["kategori_transaksi"],
                event_trigger=row["event_trigger"],
                platform=row["platform"],
                kode_debet=row["kode_debet"],
                nama_akun_debet=row["nama_akun_debet"],
                kode_kredit=row["kode_kredit"],
                nama_akun_kredit=row["nama_akun_kredit"],
                trigger_dokumen=row["trigger_dokumen"],
                aturan_keterangan=row["aturan_keterangan"],
            ))
    db.commit()


def seed_pos_payment_extension(db: Session) -> None:
    """Adds rules 33/34 (Transfer, E-Wallet — see POS_PAYMENT_RULE_NOS'
    docstring above) if not already present. Idempotent, and independent of
    seed_mapping_rules so it can be re-run safely regardless of ordering."""
    for no, event_trigger, kode_debet, nama_akun_debet in _POS_PAYMENT_EXTENSION_ROWS:
        if db.get(TransactionMappingRule, no) is not None:
            continue
        db.add(TransactionMappingRule(
            no=no,
            kategori_transaksi="Penjualan Offline & POS",
            event_trigger=event_trigger,
            platform="Kasir / POS",
            kode_debet=kode_debet,
            nama_akun_debet=nama_akun_debet,
            kode_kredit="4114",
            nama_akun_kredit="Pendapatan Usaha - Offline",
            trigger_dokumen="Struk Kasir / POS Daily Summary",
            aturan_keterangan=(
                "Ekstensi Epic C (bukan dari sheet Excel asli) — disetujui Product Owner "
                "untuk melengkapi rule #8/#9 yang hanya mencakup Tunai/QRIS."
            ),
        ))
    db.commit()


def post_journal(
    db: Session,
    *,
    owner_id: int,
    kode_debet: str,
    kode_kredit: str,
    nominal: float,
    tanggal: datetime,
    sumber_dokumen: str,
    keterangan: str,
    rule_no: int | None = None,
    status: str = "OTOMATIS",
    outlet_id: str | None = None,
    order_id: str | None = None,
    settlement_id: str | None = None,
    expense_id: int | None = None,
) -> JournalEntry | None:
    if nominal <= 0:
        return None

    akun_debet = get_account(db, owner_id, kode_debet)
    akun_kredit = get_account(db, owner_id, kode_kredit)

    entry = JournalEntry(
        no_jurnal=f"JE-{uuid.uuid4().hex[:10].upper()}",
        owner_id=owner_id,
        tanggal=tanggal,
        kode_debet=kode_debet,
        nama_akun_debet=akun_debet.nama_akun,
        kode_kredit=kode_kredit,
        nama_akun_kredit=akun_kredit.nama_akun,
        nominal=nominal,
        sumber_dokumen=sumber_dokumen,
        keterangan=keterangan,
        status=status,
        outlet_id=outlet_id,
        rule_no=rule_no,
        order_id=order_id,
        settlement_id=settlement_id,
        expense_id=expense_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _order_label(order: OmniOrder) -> str:
    return "Nota" if order.channel == "Offline POS" else "Pesanan"


def _compute_cogs_total(db: Session, owner_id: int, order: OmniOrder) -> float:
    """qty x cogs_price summed across an order's items — shared by the
    original COGS posting (rule #24, below) and Epic G's retur stock-recovery
    reversal (rule #20), so the two always agree on the same amount."""
    cogs_total = 0.0
    for item in order.items:
        product = get_product(db, owner_id, item.sku)
        if product is None:
            continue  # SKU not in catalog — same skip-if-missing behavior as deduct_stock_for_order
        cogs_total += item.quantity * product.cogs_price
    return cogs_total


def _post_cogs(db: Session, order: OmniOrder) -> JournalEntry | None:
    """Rule #24 — channel-agnostic, shared by every completed-sale path
    (online order completion and POS Kasir) so the qty x cogs_price logic
    isn't duplicated."""
    label = _order_label(order)
    cogs_total = _compute_cogs_total(db, order.owner_id, order)
    return post_journal(
        db, owner_id=order.owner_id, kode_debet="5110", kode_kredit="1131", nominal=cogs_total,
        tanggal=order.order_time, sumber_dokumen=f"{label} {order.platform_order_id}",
        keterangan=f"HPP {label.lower()} {order.platform_order_id}",
        rule_no=_COGS_RULE_NO, order_id=order.platform_order_id,
    )


def post_order_completed_journal(db: Session, order: OmniOrder) -> list[JournalEntry]:
    channel_enum = _LABEL_TO_CHANNEL[order.channel]
    receivable_account = CHANNEL_RECEIVABLE_ACCOUNT[channel_enum]
    revenue_account = CHANNEL_REVENUE_ACCOUNT[channel_enum]
    revenue_rule_no = _REVENUE_RULE_BY_CHANNEL_LABEL[order.channel]

    entries = []
    entries.append(post_journal(
        db, owner_id=order.owner_id, kode_debet=receivable_account, kode_kredit=revenue_account,
        nominal=order.gross_amount,
        tanggal=order.order_time, sumber_dokumen=f"Pesanan {order.platform_order_id}",
        keterangan=f"Penjualan bruto {order.channel} pesanan selesai",
        rule_no=revenue_rule_no, order_id=order.platform_order_id,
    ))

    for fee in order.fees:
        mapping = _FEE_DEBIT_ACCOUNT_AND_RULE.get(fee.category)
        if mapping is None:
            continue  # no matching pattern in the 32-row matrix for this fee category — documented gap
        debit_account, rule_no = mapping
        entries.append(post_journal(
            db, owner_id=order.owner_id, kode_debet=debit_account, kode_kredit=receivable_account,
            nominal=fee.amount,
            tanggal=order.order_time, sumber_dokumen=f"Pesanan {order.platform_order_id}",
            keterangan=f"{fee.category} ({fee.label}) - {order.channel}",
            rule_no=rule_no, order_id=order.platform_order_id,
        ))

    entries.append(_post_cogs(db, order))

    return [e for e in entries if e is not None]


def _pos_original_payment_account(db: Session, order: OmniOrder) -> str:
    """Offline POS (Epic G) has no single static receivable account per
    channel the way online orders do (CHANNEL_RECEIVABLE_ACCOUNT) — each
    nota's payment leg (1111/1122/1113/1112) was chosen per-sale. Reversing
    a POS retur means crediting whichever account that SPECIFIC nota's sale
    actually debited, found the same way pos_service.get_receipt resolves
    the payment method: the original JournalEntry for this order_id whose
    rule_no is one of the POS payment rules."""
    original = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.owner_id == order.owner_id,
            JournalEntry.order_id == order.platform_order_id,
            JournalEntry.rule_no.in_(POS_PAYMENT_RULE_NOS),
        )
        .one()
    )
    return original.kode_debet


def post_order_refunded_journal(db: Session, order: OmniOrder) -> list[JournalEntry]:
    rule_no = _RETUR_RULE_BY_CHANNEL_LABEL[order.channel]
    if order.channel == "Offline POS":
        receivable_account = _pos_original_payment_account(db, order)
    else:
        channel_enum = _LABEL_TO_CHANNEL[order.channel]
        receivable_account = CHANNEL_RECEIVABLE_ACCOUNT[channel_enum]

    label = _order_label(order)
    entry = post_journal(
        db, owner_id=order.owner_id, kode_debet="4212", kode_kredit=receivable_account,
        nominal=order.gross_amount,
        tanggal=order.updated_time, sumber_dokumen=f"{label} {order.platform_order_id}",
        keterangan=f"Retur/pembatalan {label.lower()} {order.channel}",
        rule_no=rule_no, order_id=order.platform_order_id,
    )
    return [entry] if entry is not None else []


def post_retur_stock_recovery_journal(db: Session, order: OmniOrder) -> JournalEntry | None:
    """Rule #20 — only posted when the returned goods came back in good,
    resellable condition (Epic G, caller's choice). Reverses exactly the
    amount rule #24 originally expensed via the shared
    _compute_cogs_total, so HPP/Persediaan net back to their pre-sale state."""
    label = _order_label(order)
    cogs_total = _compute_cogs_total(db, order.owner_id, order)
    return post_journal(
        db, owner_id=order.owner_id, kode_debet="1131", kode_kredit="5110", nominal=cogs_total,
        tanggal=order.updated_time, sumber_dokumen=f"{label} {order.platform_order_id}",
        keterangan=f"Pemulihan stok retur {label.lower()} {order.platform_order_id}",
        rule_no=20, order_id=order.platform_order_id,
    )


def post_pos_sale_journal(db: Session, order: OmniOrder, rule_no: int) -> list[JournalEntry]:
    """POS Kasir (Epic C) — unlike online orders, a nota has no intermediate
    receivable/fee step: the full nominal hits the payment account directly
    (rules #8/#9/#33/#34 all have this shape). outlet_id is resolved from
    the debit account's own is_outlet_scoped flag (data-driven — only rule
    8's 1111 Kas di Tangan is outlet-scoped) rather than a hardcoded "1111"
    check."""
    rule = db.get(TransactionMappingRule, rule_no)
    akun_debet = get_account(db, order.owner_id, rule.kode_debet)
    outlet_id = order.outlet_id if akun_debet.is_outlet_scoped else None

    entries = [post_journal(
        db, owner_id=order.owner_id, kode_debet=rule.kode_debet, kode_kredit=rule.kode_kredit,
        nominal=order.gross_amount,
        tanggal=order.order_time, sumber_dokumen=f"Nota {order.platform_order_id}",
        keterangan=f"{rule.event_trigger} - {order.platform_order_id}",
        rule_no=rule_no, outlet_id=outlet_id, order_id=order.platform_order_id,
    )]
    entries.append(_post_cogs(db, order))

    return [e for e in entries if e is not None]


def post_settlement_journal(db: Session, settlement: Settlement) -> JournalEntry | None:
    rule_no = _SETTLEMENT_RULE_BY_CHANNEL_LABEL.get(settlement.channel)
    if rule_no is None:
        return None
    rule = db.get(TransactionMappingRule, rule_no)

    return post_journal(
        db, owner_id=settlement.owner_id, kode_debet=rule.kode_debet, kode_kredit=rule.kode_kredit,
        nominal=settlement.payout_amount,
        tanggal=settlement.settlement_date, sumber_dokumen=f"Settlement {settlement.settlement_id}",
        keterangan=f"Pencairan dana {settlement.channel} ke bank",
        rule_no=rule_no, settlement_id=settlement.settlement_id,
    )


def post_expense_journal(db: Session, expense: Expense) -> JournalEntry | None:
    rule = db.get(TransactionMappingRule, expense.rule_no)
    return post_journal(
        db, owner_id=expense.owner_id, kode_debet=rule.kode_debet, kode_kredit=rule.kode_kredit,
        nominal=expense.amount,
        tanggal=expense.expense_date, sumber_dokumen=f"Biaya #{expense.id}",
        keterangan=expense.note or expense.category,
        rule_no=expense.rule_no, status="MANUAL", outlet_id=expense.outlet_id, expense_id=expense.id,
    )


def list_journal_entries(db: Session, owner_id: int, start: datetime, end: datetime) -> list[JournalEntry]:
    return (
        db.query(JournalEntry)
        .filter(JournalEntry.owner_id == owner_id, JournalEntry.tanggal >= start, JournalEntry.tanggal <= end)
        .order_by(JournalEntry.tanggal.desc())
        .all()
    )


# The rules an Expense can post through (see Expense.rule_no docstring in
# db_models.py) — used to populate the "Jenis Beban" dropdown from data
# instead of hardcoding labels/accounts in the template. Whether a rule
# requires an outlet is NOT hardcoded here — it's derived per-rule from the
# credit account's Account.is_outlet_scoped flag (see expense_rules() in
# app/routers/financial.py), so adding a future outlet-scoped rule to this
# list needs no other code change.
EXPENSE_RULE_NOS = [25, 26, 30, 31, 32]


def list_expense_rules(db: Session) -> list[TransactionMappingRule]:
    return (
        db.query(TransactionMappingRule)
        .filter(TransactionMappingRule.no.in_(EXPENSE_RULE_NOS))
        .order_by(TransactionMappingRule.no)
        .all()
    )


def list_pos_payment_rules(db: Session) -> list[TransactionMappingRule]:
    return (
        db.query(TransactionMappingRule)
        .filter(TransactionMappingRule.no.in_(POS_PAYMENT_RULE_NOS))
        .order_by(TransactionMappingRule.no)
        .all()
    )
