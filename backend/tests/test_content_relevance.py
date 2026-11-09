"""
The content-relevance gate: a valid file about something else is refused.

Found by hand: a Word document holding a picture and a song was accepted into
the knowledge base, because every SRS Step 4 check (type, size, empty,
duplicate) passed. The thresholds in config/policy.yaml were measured on the
corpus; these tests hold them to what was measured -- no corpus policy or
complaint refused, every off-topic sample refused.
"""

from __future__ import annotations

import io
import json
import struct
import zlib
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import delete, select

from document_processing import relevance
from document_processing.parser import parse_document
from document_processing.validation import detect_format
from src.core.config import settings
from src.db.models import AppConfig, DocumentValidationIssue

# Written for these tests; no real lyrics. The second verse deliberately uses
# words the delivery lexicon knows ("deliver", "late", "still waiting").
SONG = """[Verse 1]
I waited all night by the window, baby
You said you'd deliver your love to me
The clock is late, the stars are fading
Still waiting for you to set me free

[Chorus]
Oh oh, come back home tonight
Oh oh, hold me till the light
Oh oh, come back home tonight
Oh oh, hold me till the light

[Verse 2]
The rain keeps falling on my shoulder
Every message left unread
I'm growing colder, getting older
Dancing with the words you said

[Chorus]
Oh oh, come back home tonight
Oh oh, hold me till the light
Oh oh, come back home tonight
Oh oh, hold me till the light (x2)"""

SONG_WITHOUT_LABELS = "\n".join(
    line for line in SONG.splitlines() if not line.startswith("[") and "(x2)" not in line
)

ROMAN_URDU_SONG = "\n".join([
    "Dil ki baat kahun kaise", "Tum bin jeena mushkil hai", "Chanda ki chandni mein", "Tera chehra yaad aaye",
] * 3)

OFF_TOPIC = {
    "song": SONG,
    "song without section labels": SONG_WITHOUT_LABELS,
    "roman urdu song": ROMAN_URDU_SONG,
    "recipe": (
        "Chicken Biryani. Ingredients: 1 kg basmati rice, 1 kg chicken, 4 onions sliced, 2 cups yogurt, ginger "
        "garlic paste, green chillies, mint, coriander, saffron soaked in warm milk, whole spices. Method: wash and "
        "soak the rice for thirty minutes. Fry the onions until golden brown and set half aside. Add the chicken "
        "and cook until it changes colour. Add yogurt, chillies and spices and simmer for twenty minutes. Boil the "
        "rice with salt until seventy percent done. Layer the rice over the chicken, sprinkle fried onions, mint "
        "and saffron milk. Cover tightly and cook on low heat for twenty five minutes. Serve hot with raita."
    ),
    "match report": (
        "Pakistan beat Australia by six wickets in the second one-day international at the Gaddafi Stadium on "
        "Sunday. Chasing 287, the hosts were steadied by a century from the captain, who struck eleven fours and "
        "three sixes. Earlier, the fast bowlers shared seven wickets as Australia lost their last five wickets "
        "for 31 runs. The series is now level, with the decider in Rawalpindi on Wednesday."
    ),
    "cv": (
        "Curriculum Vitae. Name: Ali Raza. Objective: To obtain a challenging position in software engineering. "
        "Education: BS Computer Science, 2024. Skills: Python, JavaScript, React, SQL, teamwork. Experience: "
        "Intern at a software house, built web pages and fixed bugs. Hobbies: reading, football, travelling."
    ),
    "lorem ipsum": (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et "
        "dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip. "
    ) * 3,
}

# Another company's policies must still be accepted: the gate asks "is this
# about customer service?", not "is this RaftarXpress?".
OTHER_INDUSTRY_POLICIES = {
    "hotel": (
        "Guest Complaints and Refund Policy. Purpose: this policy sets out how the hotel handles guest complaints "
        "and refund requests. Scope: applies to all front desk staff and duty managers. 1. Every complaint must "
        "be logged within one hour. 2. Refunds for cancelled bookings are processed within seven working days to "
        "the original payment method. 3. A guest who reports a safety hazard must be moved immediately and the "
        "incident escalated to the duty manager. 4. Compensation above PKR 20,000 requires approval from the "
        "general manager. 5. Staff must not promise a refund before eligibility is confirmed."
    ),
    "telecom": (
        "Billing Dispute Procedure. Customers who believe they were charged incorrectly may raise a billing "
        "dispute within 30 days of the invoice date. The agent shall verify the charge against the usage records. "
        "Where a duplicate charge is confirmed the amount is credited to the account within two billing cycles. "
        "Disputes above the threshold are escalated to the Billing team lead."
    ),
    # Headings a CV also uses (References, Scope, Definitions): one policy heading
    # in common with a CV must not make a policy look like one.
    "with references section": (
        "Refund Policy\nPurpose\nThis policy explains when a customer is entitled to a refund.\n"
        "Scope\nApplies to all agents handling refund complaints.\nDefinitions\nA refund returns the amount paid "
        "to the original payment method.\nProcedure\nRefunds are processed within seven working days after the "
        "returned item is inspected at the hub. Refunds above PKR 50,000 require supervisor approval.\n"
        "References\nDOC-002 Returns SOP; DOC-019 Customer FAQ."
    ),
}

# Written for these tests. Vocabulary alone lets all three through: the first
# says "app", "website" and "customers"; the second is full of complaints,
# refunds and SLAs. Their headings give them away.
CVS = {
    "developer": (
        "Muhammad Ahmed\nSoftware Engineer | Lahore | ahmed.dev@example.com | linkedin.com/in/ahmeddev\n\n"
        "Career Objective\nMotivated engineer seeking a role building reliable web applications.\n\n"
        "Education\nBS Computer Science, University of the Punjab, 2021 - 2025, CGPA 3.4\n\n"
        "Experience\nSoftware Engineering Intern, TechNest Solutions, 2024\n"
        "- Built a React web app for an online store, including checkout and order history.\n"
        "- Fixed bugs reported by customers and deployed the website on Vercel.\n\n"
        "Projects\nFood Delivery App: users place orders and track delivery.\n\n"
        "Skills\nJavaScript, React, Node.js, Python, SQL\n\nHobbies\nCricket, reading\n\n"
        "References\nAvailable on request"
    ),
    "support agent": (
        "RESUME\nAyesha Khan\nKarachi | ayesha.khan@example.com\n\nProfessional Summary\n"
        "Customer service professional with three years in courier support, handling complaints, refunds and "
        "escalations.\n\nWork Experience\nCustomer Support Executive, FastTrack Couriers, 2022 - present\n"
        "- Handled customer calls about late deliveries, lost parcels and damaged packages.\n"
        "- Processed refund and replacement requests according to company policy.\n"
        "- Escalated unresolved complaints to supervisors within the SLA.\n\n"
        "Education\nBachelor of Commerce, University of Karachi, 2021\n\n"
        "Skills\nComplaint handling, CRM software, communication\n\nReferences\nAvailable on request"
    ),
    "pakistani format": (
        "CURRICULUM VITAE\n\nPersonal Information\nName: Hamza Ali\nFather's Name: Ali Raza\n"
        "Date of Birth: 14-03-2001\nAddress: House 12, Street 4, Gulberg, Lahore\n\n"
        "Objective\nTo work in a challenging environment for the growth of the organisation.\n\n"
        "Academic Qualification\nMatric, BISE Lahore, 2017\nBS Information Technology, COMSATS, 2023\n\n"
        "Experience\nData Entry Operator, Al-Noor Traders, 2023 - 2024\n\n"
        "Computer Skills\nMS Word, MS Excel\n\nLanguages\nUrdu, English\n\n"
        "References will be furnished on demand"
    ),
}


def _corpus_documents() -> list[Path]:
    found = []
    for folder in settings.document_dirs:
        found += sorted(p for p in Path(folder).glob("*") if p.suffix.lower() in {".pdf", ".docx"})
    return found


def _corpus_complaints() -> list[str]:
    texts = []
    for path in sorted(Path(settings.dataset_dir).glob("*/complaints/*.json")):
        for complaint in json.loads(path.read_text(encoding="utf-8"))["complaints"]:
            texts.append(f"{complaint['title']}\n{complaint['description']}")
    return texts


def _png() -> bytes:
    """A valid 1x1 PNG, so python-docx will embed it."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"")


def _docx(text: str, *, picture: bool = False) -> bytes:
    doc = Document()
    if picture:
        doc.add_picture(io.BytesIO(_png()))
    for line in text.split("\n"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════
# the measured thresholds
# ══════════════════════════════════════════════════════════════
def test_no_corpus_policy_is_refused(db):
    documents = _corpus_documents()
    assert documents, "the corpus documents are missing"
    refused = []
    for path in documents:
        data = path.read_bytes()
        fmt, _ = detect_format(data, path.name)
        parsed = parse_document(data, file_name=path.name, file_format=fmt)
        verdict = relevance.check(db, parsed.raw_text or "\n".join(s.text for s in parsed.sections), purpose="policy")
        if not verdict.relevant:
            refused.append((path.name, verdict.detail()))
    assert not refused, refused


def test_no_corpus_complaint_is_refused(db):
    complaints = _corpus_complaints()
    assert len(complaints) >= 500
    refused = [text[:80] for text in complaints if not relevance.check(db, text, purpose="complaint").relevant]
    assert not refused, refused


@pytest.mark.parametrize("name", list(OFF_TOPIC))
@pytest.mark.parametrize("purpose", ["policy", "complaint"])
def test_off_topic_text_is_refused(db, name, purpose):
    verdict = relevance.check(db, OFF_TOPIC[name], purpose=purpose)
    assert not verdict.relevant, verdict.detail()
    assert verdict.reason


@pytest.mark.parametrize("name", list(OTHER_INDUSTRY_POLICIES))
def test_another_industrys_policy_is_accepted(db, name):
    verdict = relevance.check(db, OTHER_INDUSTRY_POLICIES[name], purpose="policy")
    assert verdict.relevant, verdict.detail()


def test_a_song_is_named_as_one(db):
    verdict = relevance.check(db, SONG, purpose="policy")
    assert verdict.song_like
    assert "song lyrics" in verdict.reason


@pytest.mark.parametrize("name", list(CVS))
@pytest.mark.parametrize("purpose", ["policy", "complaint"])
def test_a_cv_is_refused_however_relevant_its_words(db, name, purpose):
    verdict = relevance.check(db, CVS[name], purpose=purpose)
    assert verdict.cv_like, verdict.detail()
    assert not verdict.relevant
    assert "CV or résumé" in verdict.reason


def test_no_corpus_file_looks_like_a_cv(db):
    texts = _corpus_complaints()
    for path in _corpus_documents():
        data = path.read_bytes()
        fmt, _ = detect_format(data, path.name)
        parsed = parse_document(data, file_name=path.name, file_format=fmt)
        texts.append(parsed.raw_text or "\n".join(s.text for s in parsed.sections))
    flagged = [t[:60] for t in texts if relevance.check(db, t, purpose="policy").cv_like]
    assert not flagged, flagged


def test_tone_words_are_not_evidence(db):
    """Analytics-only signals ("furious", "pathetic") say how a writer feels, not what the text is about."""
    angry = "Furious! Pathetic! Ridiculous! Disgraceful! Never again, absolutely fuming, fed up and sick of it. " * 3
    assert not relevance.check(db, angry, purpose="complaint").relevant


def test_the_gate_can_be_switched_off(db):
    row = db.get(AppConfig, "content_relevance")
    original = dict(row.value)
    row.value = {**original, "enabled": False}
    db.flush()
    try:
        assert relevance.check(db, SONG, purpose="policy").relevant
    finally:
        row.value = original
        db.flush()


# ══════════════════════════════════════════════════════════════
# through the API: exactly what was tried by hand
# ══════════════════════════════════════════════════════════════
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_a_word_file_with_a_picture_and_a_song_is_refused_by_the_knowledge_base(client, auth_headers, db):
    data = _docx(SONG, picture=True)
    out = client.post(
        "/api/documents", headers=auth_headers("admin"),
        files={"files": ("my_song.docx", data, DOCX_MIME)},
    )
    assert out.status_code == 201, out.text
    body = out.json()
    assert body["accepted"] == 0 and body["rejected"] == 1
    result = body["results"][0]
    assert result["accepted"] is False
    assert "song lyrics" in result["message"]
    assert "picture" in result["message"].lower()
    assert any(i["code"] == "OFF_TOPIC_CONTENT" and i["fatal"] for i in result["issues"])

    recorded = db.execute(
        select(DocumentValidationIssue).where(
            DocumentValidationIssue.file_name == "my_song.docx",
            DocumentValidationIssue.issue_code == "OFF_TOPIC_CONTENT",
        )
    ).scalars().all()
    assert recorded and recorded[0].outcome == "REJECTED", "a refusal must leave evidence"
    assert "1 picture(s) not read" in recorded[0].detail
    db.execute(delete(DocumentValidationIssue).where(DocumentValidationIssue.file_name == "my_song.docx"))
    db.commit()


def test_a_cv_is_refused_by_the_knowledge_base(client, auth_headers, db):
    out = client.post(
        "/api/documents", headers=auth_headers("admin"),
        files={"files": ("my_cv.docx", _docx(CVS["support agent"]), DOCX_MIME)},
    )
    assert out.status_code == 201, out.text
    result = out.json()["results"][0]
    assert result["accepted"] is False
    assert "CV or résumé" in result["message"]
    assert any(i["code"] == "OFF_TOPIC_CONTENT" for i in result["issues"])
    db.execute(delete(DocumentValidationIssue).where(DocumentValidationIssue.file_name == "my_cv.docx"))
    db.commit()


def test_a_word_file_with_a_song_is_not_read_into_a_complaint(client, auth_headers):
    out = client.post(
        "/api/complaints/from-file", headers=auth_headers("customer"),
        files={"file": ("letter.docx", _docx(SONG, picture=True), DOCX_MIME)},
    )
    assert out.status_code == 422, out.text
    error = out.json()["error"]
    assert "doesn't read like a complaint" in error["message"]
    assert error["details"]["code"] == "OFF_TOPIC_CONTENT"


def test_a_real_complaint_letter_with_a_photo_is_still_read(client, auth_headers):
    letter = (
        "Subject: Parcel CN-88120045 arrived damaged\n"
        "The box was crushed and the phone inside has a cracked screen. I attached a photo. "
        "Please arrange a replacement or a refund."
    )
    out = client.post(
        "/api/complaints/from-file", headers=auth_headers("customer"),
        files={"file": ("letter.docx", _docx(letter, picture=True), DOCX_MIME)},
    )
    assert out.status_code == 200, out.text
    assert out.json()["order_ref"] == "CN-88120045"
