from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routers.auth import is_logged_in

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _user_context(request: Request) -> dict:
    return {"user_email": request.session.get("user_email", "Admin")}


@router.get("/")
def root():
    return RedirectResponse(url="/order_inbox")


@router.get("/order_inbox")
async def order_inbox(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "order_inbox.html", _user_context(request))


@router.get("/inventory")
async def inventory(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "inventory.html", _user_context(request))


@router.get("/inventory/new")
async def inventory_new_product(request: Request):
    """Tambah Produk form (Fase 6). Registered before /inventory/{sku} so
    'new' is never mistaken for a SKU."""
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    context = _user_context(request)
    context["sku"] = ""
    return templates.TemplateResponse(request, "product_form.html", context)


@router.get("/inventory/{sku}/edit")
async def inventory_edit_product(request: Request, sku: str):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    context = _user_context(request)
    context["sku"] = sku
    return templates.TemplateResponse(request, "product_form.html", context)


@router.get("/inventory/{sku}")
async def inventory_product_detail(request: Request, sku: str):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    context = _user_context(request)
    context["sku"] = sku
    return templates.TemplateResponse(request, "product_detail.html", context)


@router.get("/financial")
async def financial(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "financial.html", _user_context(request))


@router.get("/neraca")
async def neraca(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "balance_sheet.html", _user_context(request))


@router.get("/reconciliation")
async def reconciliation(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "reconciliation.html", _user_context(request))


@router.get("/platforms")
async def platforms(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "platforms.html", _user_context(request))


@router.get("/outlets")
async def outlets(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "outlets.html", _user_context(request))


@router.get("/pos")
async def pos(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "pos.html", _user_context(request))
