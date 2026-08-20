"""
umkm_omni_web — FastAPI + SQLite + Jinja2 rebuild of the Order Inbox demo.

Migrated off Frappe specifically so this deploys as a single process with no
external services (no MariaDB, no Redis, no separate worker/scheduler) —
Railway's free tier (and most other free PaaS) only comfortably run one
lightweight process per app, which Frappe's architecture doesn't fit.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.database import DATABASE_URL, Base, SessionLocal, engine, run_lightweight_migrations
from app.routers import (
    api,
    auth,
    financial,
    inventory,
    pages,
    platforms,
    pos,
    reconciliation,
    registration,
    superadmin,
)
from app.services.auth_service import seed_admin_user
from app.services.error_log_service import log_error
from app.services.journal_engine_service import seed_mapping_rules, seed_pos_payment_extension

# Demo-only fallback secret — set SESSION_SECRET_KEY in the environment for
# anything beyond a local/disposable demo (Railway: set it as a variable).
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "umkm-omnichannel-demo-secret-change-me")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Postgres (Customer Request 2 Epic N): schema is entirely Alembic's
    # responsibility, applied via `alembic upgrade head` before this
    # container's uvicorn process even starts (see Dockerfile's CMD) — the
    # app itself never creates/alters tables against Postgres. SQLite
    # dev-mode keeps the old auto-migrate-on-boot behavior for fast local
    # iteration without needing Alembic (see app/database.py's comment).
    if DATABASE_URL.startswith("sqlite"):
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
    finally:
        db.close()

    yield


app = FastAPI(title="UMKM Omnichannel", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)


@app.middleware("http")
async def cache_request_body(request: Request, call_next):
    """Reads the body once, early, into request.state (backed by the ASGI
    scope dict, so it survives Starlette reconstructing a bare Request for
    the catch-all Exception handler below — see error_log_service.py's
    _build_request_context). Safe to read here even for file uploads:
    Starlette's Request caches this and replays it for any later
    .form()/.json() call downstream, it doesn't consume the stream twice."""
    request.state.raw_body = await request.body()
    return await call_next(request)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(inventory.router)
app.include_router(financial.router)
app.include_router(reconciliation.router)
app.include_router(platforms.router)
app.include_router(pos.router)
app.include_router(registration.router)
app.include_router(superadmin.router)
app.include_router(pages.router)

_DASHBOARD_BY_ROLE = {
    "owner": "/order_inbox",
    "admin": "/pos",
    "superadmin": "/superadmin/dashboard",
}


@app.exception_handler(HTTPException)
async def forbidden_page_handler(request: Request, exc: HTTPException):
    """Page routes (app/routers/pages.py's _guard) raise a plain 403
    HTTPException for a logged-in user with the wrong role — by default that
    renders as a bare {"detail": ...} JSON body, which looks broken in a
    browser. /api/* routes keep the default JSON handling since fetch()
    callers (see app/static/js/notify.js error toasts) read exc.detail from
    the JSON body."""
    if exc.status_code == 403 and not request.url.path.startswith("/api/"):
        role = request.session.get("role")
        return pages.templates.TemplateResponse(
            request, "403.html",
            {"detail": exc.detail, "dashboard_url": _DASHBOARD_BY_ROLE.get(role, "/login")},
            status_code=403,
        )
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for anything that isn't an HTTPException (those are already
    handled above, or by FastAPI's default JSON handling) — i.e. actual bugs,
    not expected validation failures (routers already catch those locally and
    raise a 400/404 HTTPException, see app/services/error_log_service.py's
    docstring). Logs full context to the error_log table (Customer Request 3
    revisi) and always replies generically: this app has been multi-tenant
    since CR1, so a stack trace reaching the client could leak another
    tenant's internals."""
    await log_error(exc, request)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": "Terjadi kesalahan pada server"})
    return pages.templates.TemplateResponse(request, "500.html", {}, status_code=500)
