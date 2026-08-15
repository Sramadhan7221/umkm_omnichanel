"""
Public self-service Owner registration (Customer Request 1 Epic J). No auth
required — mirrors app/routers/auth.py's GET /login shape (redirect away if
already logged in, otherwise render).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.user_admin_service import register_owner

router = APIRouter(tags=["registration"])
templates = Jinja2Templates(directory="app/templates")


class RegisterRequest(BaseModel):
    email: str
    password: str
    business_name: str


@router.get("/register")
async def register_page(request: Request):
    role = request.session.get("role")
    if role == "owner":
        return RedirectResponse(url="/order_inbox")
    if role == "admin":
        return RedirectResponse(url="/pos")
    if role == "superadmin":
        return RedirectResponse(url="/superadmin/dashboard")
    return templates.TemplateResponse(request, "register.html")


@router.post("/api/auth/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    try:
        register_owner(db, body.email, body.password, body.business_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
