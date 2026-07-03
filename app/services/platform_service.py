"""
Platform management service (Fase 5) — lets the user turn individual sales
channels on/off. Everything that generates orders (startup auto-seed, the
"+1 per platform" manual sync) reads this table first and only touches
channels where is_active is True.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.db_models import Platform

# code must match the Channel enum values in app.models.canonical, and the
# channel labels already used throughout OmniOrder/ProductPlatformMapping.
# fee_rate = representative flat commission % (see chat for sourcing/date —
# real platforms use tiered, category-based schedules; these are simplified
# single figures for the demo's auto-fill-on-platform-select field).
_INITIAL_PLATFORMS = [
    # (code, name, fulfillment_type, default_active, fee_rate_percent)
    ("shopee", "Shopee", "Pengiriman", True, 10.0),
    ("tiktok_shop", "TikTok Shop", "Pengiriman", False, 8.0),
    ("grabfood", "GrabFood", "Ambil Instan", True, 20.0),
    ("gofood", "GoFood", "Ambil Instan", False, 20.0),
]


def seed_platforms(db: Session) -> None:
    if db.query(Platform).count() > 0:
        return
    for code, name, fulfillment_type, is_active, fee_rate in _INITIAL_PLATFORMS:
        db.add(Platform(
            code=code, name=name, fulfillment_type=fulfillment_type,
            is_active=is_active, fee_rate=fee_rate,
        ))
    db.commit()


def backfill_fee_rates(db: Session) -> None:
    """One-time fix for platforms created before `fee_rate` existed: the
    lightweight migration in app.database adds the column with a plain 0
    default, so this fills in the real per-platform figures afterward."""
    known_rates = {code: fee_rate for code, _, _, _, fee_rate in _INITIAL_PLATFORMS}
    changed = False
    for platform in db.query(Platform).filter((Platform.fee_rate == 0) | (Platform.fee_rate.is_(None))).all():
        if platform.code in known_rates:
            platform.fee_rate = known_rates[platform.code]
            changed = True
    if changed:
        db.commit()


def list_platforms(db: Session) -> list[Platform]:
    return db.query(Platform).order_by(Platform.name).all()


def list_active_platforms(db: Session) -> list[Platform]:
    return db.query(Platform).filter(Platform.is_active.is_(True)).order_by(Platform.name).all()


def set_active(db: Session, code: str, is_active: bool) -> Platform:
    platform = db.get(Platform, code)
    if platform is None:
        raise ValueError(f"Platform '{code}' tidak ditemukan")
    platform.is_active = is_active
    db.commit()
    db.refresh(platform)
    return platform
