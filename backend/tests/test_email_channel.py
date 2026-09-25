"""
The email channel. The model is stubbed and SMTP is faked, so these tests
check the code around them: what is filed, what is answered, what is never
revealed, and what is never sent.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from genai_pipeline import email_reply
from src.core.config import settings
from src.db.models import Complaint, EmailMessage
from src.services import email_channel
from src.services.email_template import EmailContent, render_html, render_text

BODY = "My parcel CN-5566778 arrived today in Lahore with the box crushed and the lamp inside broken. I paid Rs 4,500 and I want a replacement."


@pytest.fixture(autouse=True)
def _stub_model(monkeypatch):
    """Deterministic model answers: triage by keyword, compose echoes the facts."""
    def ask(system, prompt, schema, model):
        if model is email_reply.Triage:
            return email_reply.Triage(intent="complaint" if "broken" in prompt or "late" in prompt else "other", title="Broken lamp in crushed box")
        return email_reply.Composed(greeting="Dear Test,", paragraphs=["We understand the lamp arrived broken.", "The team will check it against company policy."])
    monkeypatch.setattr(email_reply, "_ask", ask)


def _sender() -> str:
    return f"mail-{uuid.uuid4().hex[:8]}@example.com"


def _simulate(client, headers, frm, subject, body, **extra):
    r = client.post("/api/email/simulate", headers=headers, json={"from_address": frm, "from_name": "Test Person", "subject": subject, "body": body, **extra})
    assert r.status_code == 200, r.text
    return r.json()


class TestInbound:
    def test_a_complaint_email_is_filed_and_answered(self, client, auth_headers, db):
        admin = auth_headers("admin")
        frm = _sender()
        out = _simulate(client, admin, frm, "Broken lamp", BODY)
        assert out["intent"] == "COMPLAINT"
        assert out["complaint_ref"].startswith("CMP-")
        complaint = db.execute(select(Complaint).where(Complaint.public_ref == out["complaint_ref"])).scalars().one()
        assert complaint.channel == "EMAIL"
        assert complaint.customer.email == frm

        reply = next(m for m in out["thread"] if m["direction"] == "OUT")
        assert reply["to_address"] == frm
        assert reply["status"] == "NOT_SENT"           # a simulation never sends
        assert out["complaint_ref"] in reply["subject"]
        full = client.get(f"/api/email/messages/{reply['id']}", headers=admin).json()
        assert "lamp arrived broken" in full["body_text"]
        assert f"/track/{out['complaint_ref']}" in full["body_html"]

    def test_a_follow_up_joins_its_complaint(self, client, auth_headers):
        admin = auth_headers("admin")
        frm = _sender()
        ref = _simulate(client, admin, frm, "Broken lamp", BODY)["complaint_ref"]
        follow = _simulate(client, admin, frm, f"Re: [{ref}]", f"Any update on {ref}? I have photos.")
        assert follow["intent"] == "FOLLOW_UP"
        assert follow["complaint_ref"] == ref

    def test_someone_elses_reference_reveals_nothing(self, client, auth_headers):
        admin = auth_headers("admin")
        ref = _simulate(client, admin, _sender(), "Broken lamp", BODY)["complaint_ref"]
        stranger = _simulate(client, admin, _sender(), f"Status of {ref}", f"What is happening with {ref}?")
        assert stranger["intent"] == "STATUS"
        assert stranger["complaint_ref"] is None
        reply = next(m for m in stranger["thread"] if m["direction"] == "OUT") if stranger["thread"] else None
        detail = client.get(f"/api/email/messages/{stranger['id']}", headers=admin).json()
        assert reply is None or "could not find" in client.get(f"/api/email/messages/{reply['id']}", headers=admin).json()["body_text"]
        assert detail["complaint_ref"] is None

    def test_a_thank_you_is_not_a_complaint(self, client, auth_headers, db):
        before = db.execute(select(Complaint)).scalars().all()
        out = _simulate(client, auth_headers("admin"), _sender(), "Thanks", "Thank you so much!")
        assert out["intent"] == "OTHER" and out["complaint_ref"] is None
        db.expire_all()
        assert len(db.execute(select(Complaint)).scalars().all()) == len(before)

    def test_automatic_mail_is_ignored_and_never_answered(self, db):
        raw = (b"From: Mail Delivery <mailer-daemon@googlemail.com>\r\nTo: support@x.com\r\nSubject: Undeliverable\r\n"
               b"Auto-Submitted: auto-replied\r\nMessage-ID: <auto-1@x>\r\n\r\nYour message could not be delivered.")
        row = email_channel.handle(db, email_channel.parse(raw), dry_run=True)
        assert row.status == "IGNORED"
        assert not db.execute(select(EmailMessage).where(EmailMessage.in_reply_to == "<auto-1@x>")).scalars().all()

    def test_the_same_message_is_handled_once(self, db):
        raw = (b"From: A <a-dup@example.com>\r\nTo: s@x.com\r\nSubject: Hi\r\nMessage-ID: <dup-1@x>\r\n\r\nThank you")
        first = email_channel.handle(db, email_channel.parse(raw), dry_run=True)
        again = email_channel.handle(db, email_channel.parse(raw), dry_run=True)
        assert first.id == again.id


class TestParsing:
    def test_html_is_read_and_the_quoted_reply_dropped(self):
        raw = (
            b"From: Ali Khan <ali@example.com>\r\nTo: support@x.com\r\nSubject: Late parcel\r\nMessage-ID: <p1@x>\r\n"
            b"In-Reply-To: <ours@x>\r\nMIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            b"<p>My parcel is late.</p><p>On Mon, 1 Sep 2026 Support wrote:</p><blockquote>&gt; old text</blockquote>"
        )
        parsed = email_channel.parse(raw)
        assert parsed.from_address == "ali@example.com" and parsed.from_name == "Ali Khan"
        assert parsed.in_reply_to == "<ours@x>"
        assert "My parcel is late." in parsed.text
        assert "old text" not in parsed.text
        assert parsed.automatic is False


class TestReplies:
    def test_a_reply_that_promises_is_replaced(self, db, monkeypatch):
        monkeypatch.setattr(email_reply, "_ask", lambda *a: email_reply.Composed(greeting="Hi,", paragraphs=["We will refund you in full today."]))
        composed = email_reply.compose(db, first_name="Ali", subject="x", body="y", facts={}, fallback=["Plain acknowledgement."])
        assert composed.ai_written is False
        assert composed.paragraphs == ["Plain acknowledgement."]

    def test_the_template_carries_the_brand_and_the_link(self):
        content = EmailContent(greeting="Dear Ali,", paragraphs=["Hello."], reference="CMP-000001", facts=[("Handled by", "Billing")],
                               steps=["One."], cta_label="Track your complaint", cta_url="http://x/track/CMP-000001")
        html = render_html(content, support_hours="9-5")
        assert "Support<i>Nova</i>" in html and "CMP-000001" in html and "http://x/track/CMP-000001" in html
        assert "#2a1f17" in html and "#6e56cf" not in html.lower()   # espresso, and no purple
        text = render_text(content)
        assert "CMP-000001" in text and "http://x/track/CMP-000001" in text

    def test_a_real_send_goes_through_smtp(self, db, monkeypatch):
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None): sent["host"] = host
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): sent["tls"] = True
            def login(self, user, password): sent["login"] = user
            def send_message(self, msg): sent["to"] = msg["To"]; sent["auto"] = msg["Auto-Submitted"]

        monkeypatch.setattr(settings, "email_address", "supportnova@gmail.com")
        monkeypatch.setattr(settings, "email_app_password", "app-password")
        monkeypatch.setattr(settings, "resend_from", "")
        monkeypatch.setattr(email_channel.smtplib, "SMTP", FakeSMTP)
        row = email_channel.send(db, to="ali@example.com", name="Ali", subject="Re: x", content=EmailContent(greeting="Hi", paragraphs=["x"]))
        assert row.status == "SENT"
        assert sent == {"host": "smtp.gmail.com", "tls": True, "login": "supportnova@gmail.com", "to": "Ali <ali@example.com>", "auto": "auto-replied"}


class TestAccess:
    def test_a_customer_sees_only_their_own_emails(self, client, auth_headers):
        _simulate(client, auth_headers("admin"), _sender(), "Broken lamp", BODY)
        mine = client.get("/api/email/messages", headers=auth_headers("customer")).json()
        assert all("customer@raftarxpress.com" in (m["from_address"], m["to_address"]) for m in mine["items"])

    def test_customers_cannot_simulate_or_see_status(self, client, auth_headers):
        h = auth_headers("customer")
        assert client.get("/api/email/status", headers=h).status_code == 403
        assert client.post("/api/email/simulate", headers=h, json={"from_address": "a@b.com", "body": "x"}).status_code == 403
