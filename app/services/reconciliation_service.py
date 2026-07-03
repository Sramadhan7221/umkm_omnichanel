"""
Reconciliation engine (Fase 4 dari roadmap) — mencocokkan payout platform
terhadap net_amount yang sudah dihitung sendiri lewat Order Inbox.

Catatan cakupan: generate_settlements() di sini men-simulasikan payout batch
langsung dari OmniOrder.net_amount (bukan lewat PlatformAdapter.parse_settlement,
yang butuh raw payload asli yang tidak kita simpan). Untuk demo, sebagian
kecil settlement sengaja dibuat sedikit berbeda dari net_amount — ini
merepresentasikan skenario nyata yang justru jadi alasan modul ini ada:
payout platform kadang tidak persis sama dengan perhitungan sendiri.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import OmniOrder, Settlement

# Peluang satu settlement punya potongan tak terjelaskan (2-8% dari
# net_amount) — merepresentasikan kasus nyata di blueprint Section 1.2.
_DISCREPANCY_PROBABILITY = 0.15
_DISCREPANCY_RANGE = (0.02, 0.08)


def generate_settlements(db: Session) -> int:
    """Generate a Settlement row for every order that doesn't have one yet
    (simulates importing a new platform payout batch)."""
    already_settled = {s.platform_order_id for s in db.query(Settlement.platform_order_id).all()}
    orders = db.query(OmniOrder).filter(~OmniOrder.platform_order_id.in_(already_settled)).all() \
        if already_settled else db.query(OmniOrder).all()

    batch_ref = f"BATCH-{datetime.utcnow():%Y%m%d%H%M%S}"
    created = 0
    for order in orders:
        expected = order.net_amount
        if random.random() < _DISCREPANCY_PROBABILITY:
            deduction_pct = random.uniform(*_DISCREPANCY_RANGE)
            payout = round(expected * (1 - deduction_pct), 2)
        else:
            payout = expected

        diff = round(payout - expected, 2)
        status = "Cocok" if abs(diff) < 1 else "Selisih"

        db.add(Settlement(
            settlement_id=f"SETL-{uuid.uuid4().hex[:10].upper()}",
            platform_order_id=order.platform_order_id,
            channel=order.channel,
            expected_amount=expected,
            payout_amount=payout,
            diff_amount=diff,
            status=status,
            batch_ref=batch_ref,
            settlement_date=datetime.utcnow(),
        ))
        created += 1

    db.commit()
    return created


def get_reconciliation_summary(db: Session, start: datetime, end: datetime) -> dict:
    settlements = (
        db.query(Settlement)
        .filter(Settlement.settlement_date >= start, Settlement.settlement_date <= end)
        .all()
    )

    total_expected = sum(s.expected_amount for s in settlements)
    total_payout = sum(s.payout_amount for s in settlements)
    matched = [s for s in settlements if s.status == "Cocok"]
    mismatched = [s for s in settlements if s.status == "Selisih"]

    by_channel: dict[str, dict] = {}
    for s in settlements:
        bucket = by_channel.setdefault(s.channel, {"total": 0, "matched": 0, "mismatched": 0, "diff": 0.0})
        bucket["total"] += 1
        bucket["diff"] += s.diff_amount
        if s.status == "Cocok":
            bucket["matched"] += 1
        else:
            bucket["mismatched"] += 1

    return {
        "total_settlements": len(settlements),
        "matched_count": len(matched),
        "mismatched_count": len(mismatched),
        "total_expected": total_expected,
        "total_payout": total_payout,
        "total_diff": total_payout - total_expected,
        "channel_breakdown": [
            {"channel": channel, **figures} for channel, figures in by_channel.items()
        ],
    }


def list_settlements(db: Session, start: datetime, end: datetime, status: str | None = None) -> list[Settlement]:
    query = (
        db.query(Settlement)
        .filter(Settlement.settlement_date >= start, Settlement.settlement_date <= end)
    )
    if status:
        query = query.filter(Settlement.status == status)
    return query.order_by(Settlement.settlement_date.desc()).all()
