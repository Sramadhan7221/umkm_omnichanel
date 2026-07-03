"""
Auth routes (Fase 5): login page + login/logout API, plus the two helpers
(`is_logged_in`, `require_login_api`) other routers use to gate access —
`is_logged_in` for page routes (checked inline, then RedirectResponse to
/login), `require_login_api` as a Depends target for API routes (plain 401).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import authenticate

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


class LoginRequest(BaseModel):
    email: str
    password: str


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/order_inbox")
    return templates.TemplateResponse(request, "login.html")


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    return {"ok": True}


@router.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}
