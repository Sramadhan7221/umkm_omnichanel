"""
Error Logging (Customer Request 3 revisi — replaces the Prometheus/Grafana
plan). Persists unhandled exceptions (the ones that fall through to
app/main.py's catch-all Exception handler) into the error_log table, so
production bugs are traceable via SQL (`SELECT * FROM error_log WHERE
created_at BETWEEN ...`) without any extra service to run/maintain.

Deliberately NOT wired to the `except ValueError` blocks already present in
most routers — those already return a clean 400 for expected business
validation (insufficient stock, inactive outlet, etc.) and are not bugs.
log_error() is exported as a plain function (not a closure inside main.py)
so it can also be called manually from a local `except` block later, if a
specific case ever needs it — see docs/CLAUDE.md's Epic O revisi 2.
"""

import json
import traceback
from datetime import datetime

from fastapi import Request

from app.database import SessionLocal
from app.models.db_models import ErrorLog

_REDACTED = "***REDACTED***"
_SENSITIVE_SUBSTRINGS = ("password", "token", "secret")


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(substring in key_lower for substring in _SENSITIVE_SUBSTRINGS)


def _redact(value):
    if isinstance(value, dict):
        return {
            key: (_REDACTED if _is_sensitive_key(key) else _redact(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


async def _build_request_context(request: Request) -> dict:
    # NOT request.body(): the Exception handler in app/main.py receives a
    # Request rebuilt from the bare ASGI scope (Starlette's
    # ServerErrorMiddleware does this so it can catch errors from the
    # receive-channel machinery itself), which has no live receive callable
    # to read the body from. app/main.py's cache_request_body middleware
    # reads it once, early, into request.state (backed by the same scope
    # dict, so it survives that reconstruction) — this just reads it back.
    body_bytes = getattr(request.state, "raw_body", b"")
    try:
        body = json.loads(body_bytes) if body_bytes else None
    except ValueError:
        body = "<unparseable body>"
    if isinstance(body, (dict, list)):
        body = _redact(body)

    headers = {
        name: _REDACTED
        for name in ("authorization", "cookie")
        if name in request.headers
    }

    return {
        "method": request.method,
        "path": request.url.path,
        "query_params": dict(request.query_params),
        "body": body,
        "headers": headers or None,
        "role": request.session.get("role"),
        "tenant_id": request.session.get("tenant_id"),
        "client_ip": request.client.host if request.client else None,
    }


async def log_error(exc: Exception, request: Request) -> None:
    """Best-effort only: a failure writing this log must never raise on top
    of the exception already being handled, and must never stop the caller
    from still returning its generic 500 response to the client."""
    try:
        route = request.scope.get("route")
        endpoint = route.path if route is not None else request.url.path
        context = await _build_request_context(request)
        exceptions_text = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        db = SessionLocal()
        try:
            db.add(ErrorLog(
                created_at=datetime.utcnow(),
                endpoint=endpoint,
                request=json.dumps(context, default=str, ensure_ascii=False),
                exceptions=exceptions_text,
            ))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
