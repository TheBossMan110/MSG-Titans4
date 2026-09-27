"""
Rate limiting.

A single shared limiter so route modules can decorate endpoints at import time
while ``main.py`` owns registration of the 429 handler and middleware.

Storage is in-process memory on purpose: one web instance, no Redis to fail on
demo day.  If the service is ever scaled horizontally, point ``storage_uri`` at
a shared backend.
"""

from __future__ import annotations

import hmac

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from src.core.config import settings


def client_address(request: Request) -> str:
    """
    Who to count a request against.

    Sign-in, sign-up and refresh arrive through the frontend's session proxy,
    so on a hosted frontend they all come from its handful of server IPs. The
    proxy names the browser's address in ``X-SN-Client-IP``; that header is
    believed only alongside the shared secret, so a client cannot pick its
    own bucket. Everything else is keyed on the connecting address.
    """
    secret = settings.session_proxy_secret
    if secret:
        sent = request.headers.get("x-sn-proxy-secret", "")
        if sent and hmac.compare_digest(sent.encode(), secret.encode()):
            vouched = request.headers.get("x-sn-client-ip", "").split(",")[0].strip()
            if vouched:
                return vouched
    return get_remote_address(request)


limiter = Limiter(
    key_func=client_address,
    default_limits=[settings.rate_limit_default],
    headers_enabled=True,
)

LOGIN_LIMIT = settings.rate_limit_login
