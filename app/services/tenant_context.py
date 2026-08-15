"""
Tenant scoping (Customer Request 1 Epic K). `tenant_id` is already populated
in the session at login by Epic I's auth.py (Owner's own id, or the owning
Owner's id for an Admin). This mirrors that file's require_login_api ->
_get_session_role -> require_role pattern: a small overridable function plus
a composing dependency, so tests can override one shared function
(_get_session_tenant_id) and unblock every route that depends on it at once.
"""

from fastapi import Depends, HTTPException, Request

from app.routers.auth import require_login_api


def _get_session_tenant_id(request: Request) -> int | None:
    return request.session.get("tenant_id")


def get_tenant_id(
    user_id: int = Depends(require_login_api),
    tenant_id: int | None = Depends(_get_session_tenant_id),
) -> int:
    """Dependency for API routes that read/write tenant-owned data. Every
    route already gated by require_role("owner") or require_role("owner",
    "admin") always has a tenant_id (Superadmin never reaches these routes),
    but this guards defensively rather than assuming session shape."""
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Akun ini tidak terhubung ke data bisnis manapun")
    return tenant_id
