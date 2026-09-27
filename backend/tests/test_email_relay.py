"""
Replies through the Gmail relay: an Apps Script web app reached over HTTPS,
for hosts (Render's free plan) that block outbound SMTP.
"""

from __future__ import annotations

import base64

import pytest

from src.core.config import settings
from src.services import email_channel, email_template


class _Response:
    def __init__(self, status: int, body: dict | None):
        self.status_code, self._body = status, body
        self.text = str(body)

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


@pytest.fixture()
def relay(monkeypatch):
    monkeypatch.setattr(settings, "email_relay_url", "https://script.google.com/macros/s/abc/exec")
    monkeypatch.setattr(settings, "email_relay_secret", "shared-secret")
    calls = []

    def fake_post(url, json=None, timeout=None, follow_redirects=False):
        calls.append({"url": url, "json": json, "follow_redirects": follow_redirects})
        return fake_post.response

    fake_post.response = _Response(200, {"ok": True, "remaining": 99})
    monkeypatch.setattr(email_channel.httpx, "post", fake_post)
    return calls, fake_post


def test_the_relay_is_preferred_when_configured(relay):
    assert email_channel.sending_method() == "relay"


def test_the_reply_goes_out_with_the_secret_and_the_inline_logo(relay):
    calls, _ = relay
    html = email_template.render_html(email_template.EmailContent(greeting="Dear Ayesha,", paragraphs=["We have your complaint."]))
    email_channel._send_relay("ayesha@example.com", "Ayesha Khan", "Re: parcel", html, "text body")

    sent = calls[0]
    assert sent["url"].endswith("/exec") and sent["follow_redirects"] is True
    body = sent["json"]
    assert body["secret"] == "shared-secret"
    assert body["to"] == "Ayesha Khan <ayesha@example.com>"
    assert body["subject"] == "Re: parcel"
    assert base64.b64decode(body["logo"]) == email_template.logo_png()
    assert body["logoCid"] == email_template.LOGO_CID
    assert f'src="{email_template.LOGO_SRC}"' in body["html"]


def test_a_refusal_from_the_script_is_a_failed_send(relay):
    _, fake_post = relay
    fake_post.response = _Response(200, {"ok": False, "error": "bad secret"})
    with pytest.raises(RuntimeError, match="bad secret"):
        email_channel._send_relay("a@example.com", None, "s", "<p>x</p>", "x")


def test_a_non_json_answer_is_a_failed_send(relay):
    _, fake_post = relay
    fake_post.response = _Response(401, None)
    with pytest.raises(RuntimeError, match="Gmail relay 401"):
        email_channel._send_relay("a@example.com", None, "s", "<p>x</p>", "x")


def test_without_the_secret_the_relay_is_not_used(monkeypatch):
    monkeypatch.setattr(settings, "email_relay_url", "https://script.google.com/macros/s/abc/exec")
    monkeypatch.setattr(settings, "email_relay_secret", "")
    assert email_channel.sending_method() != "relay"
