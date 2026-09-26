"""
The uploaded-complaint channel: a letter in a file becomes a draft, and the
draft is filed with channel UPLOAD through the ordinary intake.
"""

from __future__ import annotations

import io

import pytest
from docx import Document

LETTER = (
    "To the Customer Support Team,\n\n"
    "Subject: Parcel CN-88120045 delivered to the wrong address\n\n"
    "Dear Sir or Madam,\n\n"
    "My parcel CN-88120045 was marked delivered on 18 September, but it went to a house two streets away. "
    "The neighbour opened it and the phone inside is now missing. I would like the parcel traced and a refund "
    "if it cannot be found.\n\nRegards,\nHamid Ali"
)


def _upload(client, headers, name: str, data: bytes, mime: str = "application/octet-stream"):
    return client.post("/api/complaints/from-file", files={"file": (name, data, mime)}, headers=headers)


def _docx(text: str) -> bytes:
    doc = Document()
    for para in text.split("\n\n"):
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_a_text_letter_becomes_a_draft(client, auth_headers):
    out = _upload(client, auth_headers("customer"), "letter.txt", LETTER.encode(), "text/plain")
    assert out.status_code == 200, out.text
    draft = out.json()
    assert draft["title"] == "Parcel CN-88120045 delivered to the wrong address"
    assert draft["order_ref"] == "CN-88120045"
    assert "phone inside is now missing" in draft["description"]
    assert draft["file_format"] == "TXT"


def test_a_word_letter_becomes_a_draft(client, auth_headers):
    out = _upload(client, auth_headers("customer"), "complaint.docx", _docx(LETTER))
    assert out.status_code == 200, out.text
    assert out.json()["order_ref"] == "CN-88120045"
    assert out.json()["file_format"] == "DOCX"


def test_without_a_subject_the_first_real_sentence_is_the_title(client, auth_headers):
    body = "Dear team,\n\nThe rider was rude to my mother and threw the box at the door. It happened twice this week."
    out = _upload(client, auth_headers("customer"), "note.txt", body.encode(), "text/plain")
    assert out.json()["title"] == "The rider was rude to my mother and threw the box at the door"


@pytest.mark.parametrize("name,data", [
    ("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64),
    ("empty.txt", b""),
    ("tiny.txt", b"hi"),
])
def test_what_cannot_be_read_is_refused_plainly(client, auth_headers, name, data):
    out = _upload(client, auth_headers("customer"), name, data)
    assert out.status_code == 422, out.text


def test_signing_in_is_required(client):
    assert _upload(client, {}, "letter.txt", LETTER.encode()).status_code == 401


def test_the_draft_files_as_an_upload(client, auth_headers):
    headers = auth_headers("customer")
    draft = _upload(client, headers, "letter.txt", LETTER.encode(), "text/plain").json()
    created = client.post("/api/complaints", json={
        "title": draft["title"], "description": draft["description"], "order_ref": draft["order_ref"], "channel": "UPLOAD",
    }, headers=headers)
    assert created.status_code == 201, created.text
    ref = created.json()["public_ref"]
    staff = client.get("/api/complaints", params={"search": ref}, headers=auth_headers("admin")).json()["items"]
    assert staff and staff[0]["channel"] == "UPLOAD"


@pytest.mark.parametrize("channel", ["SOCIAL", "IN_PERSON", "FAX"])
def test_an_unknown_channel_is_a_clear_422(client, auth_headers, channel):
    out = client.post("/api/complaints", json={
        "title": "Parcel late", "description": "My parcel CN-1234567 is five days late and tracking has not moved at all.",
        "channel": channel,
    }, headers=auth_headers("customer"))
    assert out.status_code == 422, out.text
