from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routers.auth import is_logged_in

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _user_context(request: Request) -> dict:
    return {
        "user_email": request.session.get("user_email", "Admin"),
        "role": request.session.get("role"),
    }


def _guard(request: Request, *roles: str) -> RedirectResponse | None:
    """Not-logged-in -> redirect to /login (existing convention). Logged in
    but wrong role -> 403 (Customer Request 1 Epic I Keputusan Scope CR1 §5)."""
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    if request.session.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Anda tidak memiliki akses ke halaman ini")
    return None


@router.get("/")
def root():
    """Halaman default saat membuka aplikasi adalah Login — GET /login sendiri
    yang menangani redirect role-aware untuk sesi yang sudah login (Owner ->
    /order_inbox, Admin -> /pos, Superadmin -> /superadmin/dashboard), jadi
    tidak perlu duplikasi logic role di sini. Sebelumnya redirect ke
    /order_inbox langsung menyebabkan Admin/Superadmin dapat 403 alih-alih
    diarahkan ke halaman yang benar."""
    return RedirectResponse(url="/login")


@router.get("/order_inbox")
async def order_inbox(request: Request):
    guard = _guard(request, "owner")
    if guard:
        return guard
    return templates.TemplateResponse(request, "order_inbox.html", _user_context(request))


@router.get("/inventory")
async def inventory(request: Request):
    guard = _guard(request, "owner", "admin")
    if guard:
        return guard
    return templates.TemplateResponse(request, "inventory.html", _user_context(request))


@router.get("/inventory/new")
async def inventory_new_product(request: Request):
    """Tambah Produk form (Fase 6). Registered before /inventory/{sku} so
    'new' is never mistaken for a SKU."""
    guard = _guard(request, "owner")
    if guard:
        return guard
    context = _user_context(request)
    context["sku"] = ""
    return templates.TemplateResponse(request, "product_form.html", context)


@router.get("/inventory/{sku}/edit")
async def inventory_edit_product(request: Request, sku: str):
    guard = _guard(request, "owner")
    if guard:
        return guard
    context = _user_context(request)
    context["sku"] = sku
    return templates.TemplateResponse(request, "product_form.html", context)


@router.get("/inventory/{sku}")
async def inventory_product_detail(request: Request, sku: str):
    guard = _guard(request, "owner", "admin")
    if guard:
        return guard
    context = _user_context(request)
    context["sku"] = sku
    return templates.TemplateResponse(request, "product_detail.html", context)


@router.get("/financial")
async def financial(request: Request):
    guard = _guard(request, "owner")
    if guard:
        return guard
    return templates.TemplateResponse(request, "financial.html", _user_context(request))


@router.get("/neraca")
async def neraca(request: Request):
    guard = _guard(request, "owner")
    if guard:
        return guard
    return templates.TemplateResponse(request, "balance_sheet.html", _user_context(request))


@router.get("/reconciliation")
async def reconciliation(request: Request):
    guard = _guard(request, "owner")
    if guard:
        return guard
    return templates.TemplateResponse(request, "reconciliation.html", _user_context(request))


@router.get("/platforms")
async def platforms(request: Request):
    guard = _guard(request, "owner", "admin")
    if guard:
        return guard
    return templates.TemplateResponse(request, "platforms.html", _user_context(request))


@router.get("/pos")
async def pos(request: Request):
    guard = _guard(request, "owner", "admin")
    if guard:
        return guard
    return templates.TemplateResponse(request, "pos.html", _user_context(request))


@router.get("/team")
async def team(request: Request):
    guard = _guard(request, "owner")
    if guard:
        return guard
    return templates.TemplateResponse(request, "team.html", _user_context(request))


@router.get("/superadmin/dashboard")
async def superadmin_dashboard(request: Request):
    guard = _guard(request, "superadmin")
    if guard:
        return guard
    return templates.TemplateResponse(request, "superadmin_dashboard.html", _user_context(request))
