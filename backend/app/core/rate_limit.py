from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.services.cache import cache


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Keep docs and health-style endpoints unrestricted.
        if request.url.path in {"/", "/docs", "/redoc", "/openapi.json", "/metrics", "/healthz", "/readyz"}:
            return await call_next(request)

        client_ip = _extract_client_ip(request)
        bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        key = f"ratelimit:{client_ip}:{bucket}"
        hits = cache.increment_with_ttl(key, ttl_seconds=65)

        if hits and hits > settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Попробуйте позже."},
            )

        return await call_next(request)


def _extract_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    candidate = forwarded_for or (request.client.host if request.client else "0.0.0.0")
    try:
        return str(ip_address(candidate))
    except ValueError:
        return "0.0.0.0"

