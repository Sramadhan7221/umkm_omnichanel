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
from app.services.auth_service import seed_admin_user
from app.services.journal_engine_service import seed_mapping_rules, seed_pos_payment_extension
from app.services.outlet_service import seed_outlets

# Demo-only fallback secret — set SESSION_SECRET_KEY in the environment for
# anything beyond a local/disposable demo (Railway: set it as a variable).
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "umkm-omnichannel-demo-secret-change-me")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()  # add any new columns to tables that already existed

    # Global, tenant-independent seeds only (Customer Request 1 Epic K).
    # Everything that used to auto-seed a shared demo dataset here (Chart of
    # Accounts, Platforms, Products, mock orders, settlements) now requires a
    # real owner_id to attach rows to — a fresh boot has no Owner yet (only
    # the seeded Superadmin), so those move to user_admin_service.approve_owner
    # and run once per newly-approved Owner instead. A freshly-reset demo DB
    # shows only the login page until someone registers and gets approved.
    db: Session = SessionLocal()
    try:
        seed_admin_user(db)
        seed_mapping_rules(db)  # Transaction Mapping Matrix (Epic B) — global, shared by every tenant
        seed_pos_payment_extension(db)  # POS payment methods 33/34 (Epic C, PO-approved extension) — global
        seed_outlets(db)  # Outlets (Epic H) — global, unaffected by Epic K (Epic L removes the model next)
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
