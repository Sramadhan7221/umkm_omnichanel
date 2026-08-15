"""
Auth routes (Fase 5, extended Customer Request 1 Epic I): login page +
login/logout API, role-based access control, and Owner-managed Admin
accounts. Two access-gating layers other routers use:
`is_logged_in`/`require_login_api` for "is anyone logged in" (unchanged from
Fase 5), and `require_role(*roles)` on top of it for "is this specific role
allowed here" — `is_logged_in` for page routes (checked inline, then
RedirectResponse to /login), `require_login_api`/`require_role` as Depends
targets for API routes (401/403, no redirect, since these are called via
fetch()).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import User
from app.services.auth_service import authenticate, hash_new_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("user_id"))


def require_login_api(request: Request):
    """Dependency for API routes: plain 401 if not authenticated (no redirect,
    since these are called via fetch())."""
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Belum login")
    return request.session["user_id"]


def _get_session_role(request: Request) -> str | None:
    """Split out from require_role so tests can override just this piece
    (see tests/conftest.py) — require_role nests this as a sub-dependency
    rather than reading the session directly, so every require_role(...)
    closure (one per router, created at import time) still resolves through
    this single shared function and can be overridden centrally in tests."""
    return request.session.get("role")


def require_role(*roles: str):
    """Dependency factory for API routes: 401 if not logged in (via the
    nested require_login_api), 403 if logged in but role not in `roles`.
    Usage: Depends(require_role("owner")), Depends(require_role("owner", "admin"))."""

    def _dependency(
        user_id: int = Depends(require_login_api),
        role: str | None = Depends(_get_session_role),
    ):
        if role not in roles:
            raise HTTPException(status_code=403, detail="Anda tidak memiliki akses")
        return user_id

    return _dependency


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateAdminRequest(BaseModel):
    email: str
    password: str


@router.get("/login")
async def login_page(request: Request):
    role = request.session.get("role")
    if role == "owner":
        return RedirectResponse(url="/order_inbox")
    if role == "admin":
        return RedirectResponse(url="/pos")
    if role == "superadmin":
        return RedirectResponse(url="/superadmin/dashboard")
    # Logged-out visitor just sees the login form.
    return templates.TemplateResponse(request, "login.html")


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")
    if user.status == "pending":
        raise HTTPException(status_code=401, detail="Akun Anda menunggu persetujuan Superadmin")
    if user.status == "rejected":
        raise HTTPException(status_code=401, detail="Registrasi Anda ditolak")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Akun Anda dinonaktifkan, hubungi Superadmin")

    tenant_id = user.id if user.role == "owner" else (user.owner_id if user.role == "admin" else None)
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    request.session["role"] = user.role
    request.session["tenant_id"] = tenant_id
    return {"ok": True, "role": user.role}


@router.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.post("/api/auth/create-admin")
def create_admin(
    body: CreateAdminRequest,
    request: Request,
    db: Session = Depends(get_db),
    owner_id: int = Depends(require_role("owner")),
):
    """Owner creates an Admin account scoped to themselves. Admin needs no
    separate Superadmin approval (only Owner registration does, Epic J)."""
    email = body.email.strip().lower()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    salt_hex, hash_hex = hash_new_password(body.password)
    admin_user = User(
        email=email,
        password_hash=hash_hex,
        password_salt=salt_hex,
        role="admin",
        owner_id=owner_id,
        status="approved",
        is_active=True,
    )
    db.add(admin_user)
    db.commit()
    return {"ok": True, "id": admin_user.id, "email": admin_user.email}


@router.get("/api/auth/admins")
def list_admins(db: Session = Depends(get_db), owner_id: int = Depends(require_role("owner"))):
    admins = db.query(User).filter(User.role == "admin", User.owner_id == owner_id).all()
    return [
        {"id": a.id, "email": a.email, "is_active": a.is_active, "created_time": a.created_time}
        for a in admins
    ]
