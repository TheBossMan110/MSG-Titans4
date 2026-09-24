"""
Rate limiting.

A single shared limiter so route modules can decorate endpoints at import time
while ``main.py`` owns registration of the 429 handler and middleware.

Storage is in-process memory on purpose: one web instance, no Redis to fail on
demo day.  If the service is ever scaled horizontally, point ``storage_uri`` at
a shared backend.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    headers_enabled=True,
)

LOGIN_LIMIT = settings.rate_limit_login
