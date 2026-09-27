"""
Sign-ins reach the backend through the frontend's session proxy. The rate
limit must count them per browser, and only the proxy may say which browser.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from src.core import ratelimit
from src.core.config import settings


def _request(headers: dict[str, str], peer: str = "76.76.21.21") -> Request:
    return Request({
        "type": "http", "method": "POST", "path": "/api/auth/login", "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 44321),
    })


@pytest.fixture()
def proxy_secret(monkeypatch):
    monkeypatch.setattr(settings, "session_proxy_secret", "s3cret-shared-with-the-frontend")
    return "s3cret-shared-with-the-frontend"


def test_the_proxy_vouches_for_the_browser_address(proxy_secret):
    req = _request({"X-SN-Proxy-Secret": proxy_secret, "X-SN-Client-IP": "39.40.41.42"})
    assert ratelimit.client_address(req) == "39.40.41.42"


def test_a_client_cannot_choose_its_own_bucket_without_the_secret(proxy_secret):
    assert ratelimit.client_address(_request({"X-SN-Client-IP": "1.2.3.4"})) == "76.76.21.21"
    wrong = _request({"X-SN-Proxy-Secret": "guess", "X-SN-Client-IP": "1.2.3.4"})
    assert ratelimit.client_address(wrong) == "76.76.21.21"


def test_without_a_configured_secret_the_header_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "session_proxy_secret", "")
    req = _request({"X-SN-Proxy-Secret": "", "X-SN-Client-IP": "1.2.3.4"})
    assert ratelimit.client_address(req) == "76.76.21.21"


def test_only_the_first_address_of_a_list_counts(proxy_secret):
    req = _request({"X-SN-Proxy-Secret": proxy_secret, "X-SN-Client-IP": "39.40.41.42, 10.0.0.1"})
    assert ratelimit.client_address(req) == "39.40.41.42"
