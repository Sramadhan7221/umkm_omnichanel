"""
umkm_omni_web — FastAPI + SQLite + Jinja2 rebuild of the Order Inbox demo.

Migrated off Frappe specifically so this deploys as a single process with no
external services (no MariaDB, no Redis, no separate worker/scheduler) —
Railway's free tier (and most other free PaaS) only comfortably run one
lightweight process per app, which Frappe's architecture doesn't fit.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, run_lightweight_migrations
from app.models.db_models import OmniOrder  # noqa: F401 (ensures table is registered)
from app.routers import (
    api,
    auth,
    financial,
    inventory,
    outlets,
    pages,
    platforms,
    pos,
    reconciliation,
    registration,
    superadmin,
)
from app.routers.api import _sync_mock_orders
from app.services.auth_service import seed_admin_user
from app.services.chart_of_accounts_service import seed_accounts
from app.services.inventory_service import seed_products
from app.services.journal_engine_service import seed_mapping_rules, seed_pos_payment_extension
from app.services.outlet_service import seed_outlets
from app.services.platform_service import backfill_fee_rates, seed_platforms
from app.services.reconciliation_service import generate_settlements

# Demo-only fallback secret — set SESSION_SECRET_KEY in the environment for
# anything beyond a local/disposable demo (Railway: set it as a variable).
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "umkm-omnichannel-demo-secret-change-me")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()  # add any new columns to tables that already existed

    # Auto-seed so the demo always has data on a fresh deploy/container
    # restart (SQLite file may not persist across Railway redeploys unless a
    # volume is attached) — the "Sync Mock Orders" button in the UI still
    # works for pulling additional batches live during a presentation.
    db: Session = SessionLocal()
    try:
        seed_admin_user(db)
        seed_accounts(db)  # Chart of Accounts (Epic A) — no dependency on order data
        seed_mapping_rules(db)  # Transaction Mapping Matrix (Epic B) — must exist before any journal posting
        seed_pos_payment_extension(db)  # POS payment methods 33/34 (Epic C, PO-approved extension)
        seed_outlets(db)  # Outlets (Epic H) — no dependency on order data
        seed_platforms(db)  # platform on/off switches must exist before orders can check them
        backfill_fee_rates(db)  # fix fee_rate=0 for platforms created before this column existed
        seed_products(db)  # product catalog must exist before orders can deduct stock from it
        if db.query(OmniOrder).count() == 0:
            # +1-per-active-platform per call, so call it a few times to seed
            # a demo-able initial dataset instead of just 1 order/platform.
            for _ in range(5):
                _sync_mock_orders(db)
        generate_settlements(db)  # settle any order that doesn't have one yet
    finally:
        db.close()

    yield


app = FastAPI(title="UMKM Omnichannel", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(inventory.router)
app.include_router(financial.router)
app.include_router(reconciliation.router)
app.include_router(platforms.router)
app.include_router(outlets.router)
app.include_router(pos.router)
app.include_router(registration.router)
app.include_router(superadmin.router)
app.include_router(pages.router)
