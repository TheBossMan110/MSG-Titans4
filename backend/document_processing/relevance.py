"""
Is this file about what the system is for? The content-relevance gate.

A file can pass every check SRS Step 4 lists -- a real PDF or DOCX, under the
size limit, not empty, not a duplicate -- and still be the wrong thing: a
picture and a song pasted into a Word document, a recipe, a CV. Before this
gate such a file was ingested as a policy awaiting metadata review, chunked,
embedded and offered to the model as something it could cite; read as a
complaint letter, it filled the form with lyrics.

The test is deterministic and explainable, like Pipeline 2. It measures how
much of the text is the vocabulary of complaint handling:

* the lexicon Pipeline 2 classifies complaints with (topic and risk signals,
  ``lexicon_terms``, editable at runtime), minus the analytics-only tone words
  -- "furious" is not evidence that a text is about deliveries;
* business nouns: parcel, order, refund, invoice, account, customer...;
* for a policy, the language policies are written in: scope, procedure,
  "shall", "within 3 working days", approval, eligibility.

No model is asked. The gate works with every AI provider down, and it cannot be
talked round: a song that calls itself "the refund policy" still reads like a
song.

Thresholds were measured, not guessed (``content_relevance`` in
config/policy.yaml, editable at runtime). On the corpus the 30 policy
documents score at least 9.3 matched terms per 100 words; the few complaints
that name no business noun at all still score at least 10 with 4 different
terms. Song lyrics, a recipe, a match report, a CV and lorem ipsum score under
5 with at most 3 different terms, and the song also repeats its lines, which no
policy or complaint in the corpus does. tests/test_content_relevance.py holds
the gate to exactly that: no corpus file refused, every off-topic one refused.

A CV is the exception vocabulary cannot catch: a support agent's CV is full of
"complaints", "refunds" and "SLA". It is caught by its shape instead -- the
Education / Experience / Skills / References headings that no policy or
complaint letter has.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field, fields
from typing import Any, Literal

Purpose = Literal["policy", "complaint"]
Lexicon = list[tuple[str, str, str, float]]

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# What a customer-service text is about, whatever the company: the things that
# are bought, sent, paid for and complained about.
_ANCHORS = re.compile(
    r"\b(?:parcels?|packages?|packets?|shipments?|consignments?|couriers?|deliver(?:y|ies|ed|ing)?|riders?|"
    r"orders?|ordered|tracking|refunds?|refunded|returns?|exchange|replacement|charged?|charges|payments?|paid|"
    r"invoices?|bill(?:s|ing|ed)?|cod|cash on delivery|amount|pkr|rs\.?|accounts?|app|website|customers?|"
    r"complaints?|complain(?:ed|ing)?|services?|support|warranty|claims?|insurance|compensation|policy|policies|"
    r"procedures?|branch|office|staff|address|booking|merchant|seller|products?|items?|receipt|transaction|card|"
    r"bank|money|agent|helpline|hub|warehouse|dispatch(?:ed)?)\b",
    re.IGNORECASE,
)
_REFERENCE = re.compile(r"\b(?:CN|ORD|RX|TRK|AWB|ORDER|FWD|MER)[-\s#]?\d{4,}\b", re.IGNORECASE)

# How policies, procedures and SLAs are written, as opposed to what they are about.
_GOVERNANCE = re.compile(
    r"\b(?:document (?:id|type)|version|effective(?: date)?|expiry|scope|purpose|overview|procedures?|"
    r"guidelines?|guidance|policy|policies|applies to|shall|must|responsib\w*|complian\w*|approv\w*|"
    r"eligib\w*|entitle\w*|escalat\w*|supervisor|sla|service level|section|clause|"
    r"within (?:\w+ )?(?:business |working )?(?:hours?|days?|minutes?))\b",
    re.IGNORECASE,
)

# Song structure: section labels, repeat marks, music notes.
_SONG_MARKER = re.compile(
    r"^\s*[\[(](?:verse|chorus|pre-chorus|bridge|hook|intro|outro|refrain)\b[^\])\n]*[\])]|\(x\s?\d+\)|[♪♫]",
    re.IGNORECASE | re.MULTILINE,
)

# CV structure. Vocabulary cannot catch a CV: a developer's says "app",
# "website" and "customers", a support agent's says "complaints", "refunds" and
# "SLA". Its shape can: section headings no policy or complaint letter has,
# each on a line of its own or opening one ("Skills: Python, SQL").
_CV_SECTION = re.compile(
    r"^\s*(?:[-•*\d.)]+\s*)?"
    r"(education|academic qualifications?|educational background|qualifications?|work experience|"
    r"professional experience|employment history|experience|internships?|skills|technical skills|"
    r"computer skills|key skills|core competencies|projects|certifications?|career objective|objective|"
    r"professional summary|profile summary|languages|hobbies|interests|references|personal information|"
    r"personal details|achievements|awards)\s*(?::|$)",
    re.IGNORECASE | re.MULTILINE,
)
_CV_MARKER = re.compile(
    r"curriculum\s+vitae|^\s*r[eé]sum[eé]\s*$|references\s+(?:are\s+)?available\s+(?:up)?on\s+request|"
    r"references\s+will\s+be\s+(?:furnished|provided)|linkedin\.com/in/|father'?s\s+name\s*:",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class RelevanceConfig:
    """Thresholds; overridden by the ``content_relevance`` row of ``app_config``."""

    enabled: bool = True
    # A policy needs this many matched terms per 100 words, and this much variety.
    policy_min_density: float = 6.0
    policy_min_distinct: int = 6
    # A complaint letter naming nothing that is bought, sent or paid for needs
    # this density, and this many different terms: one word repeated ("never,
    # never, never") is not variety.
    complaint_min_density_without_anchor: float = 4.5
    complaint_min_distinct_without_anchor: int = 4
    # Song-shaped text is refused below this density.
    song_max_density: float = 10.0
    song_repeat_share: float = 0.25
    song_min_lines: int = 8
    # A CV is refused whatever its vocabulary: this many CV section headings,
    # or this many beside an explicit marker ("Curriculum Vitae", "References
    # available on request").
    cv_min_sections: int = 4
    cv_min_sections_with_marker: int = 2

    @classmethod
    def from_mapping(cls, values: Any) -> RelevanceConfig:
        if not isinstance(values, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in known})


@dataclass(slots=True)
class RelevanceVerdict:
    """Whether the text belongs here, why, and the evidence counted."""

    relevant: bool
    purpose: Purpose
    words: int
    hits: int
    distinct: int
    anchors: int
    density: float
    song_like: bool
    repeat_share: float
    images: int = 0
    cv_sections: list[str] = field(default_factory=list)
    cv_like: bool = False
    reason: str | None = None
    recognised: list[str] = field(default_factory=list)

    def detail(self) -> str:
        """One line for ``document_validation_issues.detail``: the numbers behind the decision."""
        parts = [
            f"{self.hits} of {self.words} words matched ({self.density:.1f} per 100)",
            f"{self.distinct} distinct terms",
            f"{self.anchors} business nouns",
        ]
        if self.song_like:
            parts.append(f"song-like ({round(self.repeat_share * 100)}% of lines repeated)")
        if self.cv_like:
            parts.append("CV-like (sections: " + ", ".join(self.cv_sections[:6]) + ")")
        if self.images:
            parts.append(f"{self.images} picture(s) not read")
        if self.recognised:
            parts.append("recognised: " + ", ".join(self.recognised[:8]))
        return "; ".join(parts)


def _repeat_share(text: str) -> tuple[float, int]:
    lines = [re.sub(r"\W+", " ", line).strip().lower() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return 0.0, 0
    return 1 - len(set(lines)) / len(lines), len(lines)


def embedded_images(data: bytes) -> int:
    """Pictures inside a DOCX. They are never read, and the refusal says so."""
    if data[:4] != b"PK\x03\x04":
        return 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return sum(1 for name in archive.namelist() if name.startswith("word/media/"))
    except zipfile.BadZipFile:
        return 0


def assess(
    text: str,
    lexicon: Lexicon,
    *,
    purpose: Purpose,
    config: RelevanceConfig | None = None,
    images: int = 0,
) -> RelevanceVerdict:
    """Decide from the text alone. ``lexicon`` is ``(signal_key, term, match_type, weight)`` rows."""
    from python_validation.signals import match_lexicon

    config = config or RelevanceConfig()
    words = max(len(_WORD.findall(text)), 1)

    spans: dict[tuple[int, int], str] = {}
    for hit in match_lexicon(text, lexicon):
        spans[(hit.start, hit.end)] = hit.text.lower()
    anchors = 0
    for pattern in (_ANCHORS, _REFERENCE):
        for match in pattern.finditer(text):
            spans[(match.start(), match.end())] = match.group(0).lower()
            anchors += 1
    if purpose == "policy":
        for match in _GOVERNANCE.finditer(text):
            spans[(match.start(), match.end())] = match.group(0).lower()

    hits = len(spans)
    recognised = [term for term, _ in Counter(spans.values()).most_common()]
    density = round(hits / words * 100, 2)
    repeat, line_count = _repeat_share(text)
    song_like = bool(_SONG_MARKER.search(text)) or (
        line_count >= config.song_min_lines and repeat >= config.song_repeat_share
    )

    sections = list(dict.fromkeys(m.group(1).lower() for m in _CV_SECTION.finditer(text)))
    marked = bool(_CV_MARKER.search(text))
    cv_like = len(sections) >= config.cv_min_sections or (
        marked and len(sections) >= config.cv_min_sections_with_marker
    )

    verdict = RelevanceVerdict(
        relevant=True, purpose=purpose, words=words, hits=hits, distinct=len(recognised),
        anchors=anchors, density=density, song_like=song_like, repeat_share=round(repeat, 2),
        images=images, recognised=recognised[:12], cv_sections=sections, cv_like=cv_like,
    )
    if not config.enabled:
        return verdict

    pictures = (
        f" Pictures are not read: the {images} in this file {'was' if images == 1 else 'were'} ignored."
        if images else ""
    )
    looks_like = " It reads like song lyrics: its lines repeat." if song_like else ""
    headings = ", ".join(s.title() for s in sections[:3])

    if cv_like:
        verdict.relevant = False
        verdict.reason = (
            f"This file looks like a CV or résumé (it has sections such as {headings}), "
            + ("not a customer-service policy, so it was not added to the knowledge base."
               " Upload the company's policy, procedure, SLA or FAQ document instead."
               if purpose == "policy" else
               "not a complaint. Nothing was filled in. Upload the letter that describes the problem, or type it below.")
        )
        return verdict

    if purpose == "policy":
        if density < config.policy_min_density or verdict.distinct < config.policy_min_distinct:
            verdict.relevant = False
            verdict.reason = (
                "This file is not a customer-service policy, so it was not added to the knowledge base."
                f"{looks_like} Only {hits} of its {words} words are the vocabulary of complaint handling "
                f"({density:.1f} in every 100; a policy needs at least {config.policy_min_density:g})."
                f"{pictures} Upload the company's policy, procedure, SLA or FAQ document instead."
            )
        return verdict

    if song_like and density < config.song_max_density:
        verdict.relevant = False
        verdict.reason = (
            "This file doesn't read like a complaint: it looks like song lyrics, with lines that repeat."
            f"{pictures} Nothing was filled in. Upload the letter that describes the problem, or type it below."
        )
    elif anchors == 0 and (
        density < config.complaint_min_density_without_anchor
        or verdict.distinct < config.complaint_min_distinct_without_anchor
    ):
        verdict.relevant = False
        verdict.reason = (
            "This file doesn't read like a complaint: it never mentions an order, a parcel, a payment, "
            f"an account or anything else we handle.{pictures} Nothing was filled in. "
            "Upload the letter that describes the problem, or type it below."
        )
    return verdict


def load_config(db) -> RelevanceConfig:
    """The thresholds in force: ``app_config.content_relevance`` over the defaults."""
    from src.db.models import AppConfig

    row = db.get(AppConfig, "content_relevance")
    return RelevanceConfig.from_mapping(row.value if row is not None else None)


def check(db, text: str, *, purpose: Purpose, images: int = 0) -> RelevanceVerdict:
    """:func:`assess` with the live lexicon (analytics-only tone words left out) and thresholds."""
    from python_validation.signals import load_analytics_only, load_lexicon

    excluded = load_analytics_only(db)
    lexicon = [row for row in load_lexicon(db) if row[0] not in excluded]
    return assess(text, lexicon, purpose=purpose, config=load_config(db), images=images)


__all__ = ["RelevanceConfig", "RelevanceVerdict", "assess", "check", "embedded_images", "load_config"]
