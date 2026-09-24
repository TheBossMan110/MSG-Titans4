"""
Section detection — turning a wall of text into citable, addressable units.

A policy citation is only useful if the section it names exists and can be
found again.  Two strategies, because the two mandatory formats carry different
signals:

* **DOCX** has real structure — paragraph styles say "this is Heading 2".
  We trust that, and read the numbering out of the heading text when present.
* **PDF** has no structure, only layout.  We detect headings from numbering
  patterns ("5.2 Delivery Windows"), short title-case lines followed by body
  text, and all-caps lines.

Either way, every section gets a ``section_ref``.  When the document numbers
its own headings we keep that numbering exactly, because that is what a human
reader would cite.  When it does not, we synthesise a hierarchical reference
(1, 1.1, 2) and mark it ``numbered_in_source=False`` so the UI can show the
citation honestly as derived rather than quoted.
"""

from __future__ import annotations

import re

from document_processing.contracts import ParsedSection

# "5.2", "5.2.1", "A.3", "A." followed by a title.
#
# A BARE capital letter is deliberately NOT accepted as a section number.
# Wrapped policy prose starts with one constantly - "A delivery complaint must
# be escalated..." - and treating that as heading 'A' silently invents a
# section, which then gets cited by generated text and cannot be found again.
# A lettered section must therefore either carry a sub-number (A.3) or a
# terminator (A. / A) ).
_NUMBERED_HEADING = re.compile(
    r"^\s*(?P<number>"
    r"\d+(?:\.\d+){0,4}"          # 5, 5.2, 5.2.1
    r"|[A-Z](?:\.\d+){1,4}"        # A.3, A.3.1
    r"|[A-Z](?=[.)])"               # A. or A)  - terminator required
    r")[.)]?\s+(?P<title>\S.{0,120})$"
)
# "Section 5.2 - Delivery Windows"
_SECTION_WORD_HEADING = re.compile(
    r"^\s*(?:section|clause|article|part)\s+(?P<number>(?:\d+|[A-Z])(?:\.\d+){0,4})"
    r"\s*[:\-–]?\s*(?P<title>.{0,120})$",
    re.IGNORECASE,
)
_ALL_CAPS_HEADING = re.compile(r"^\s*(?P<title>[A-Z][A-Z0-9 &/,'()\-]{3,70})\s*$")

# Lines that look like headings but are not.
_NOISE = re.compile(
    r"^\s*(page\s+\d+|\d+\s*/\s*\d+|confidential|internal use only|"
    r"©.*|copyright.*|zenithra.*limited)\s*$",
    re.IGNORECASE,
)

MAX_HEADING_WORDS = 14
MIN_SECTION_CHARS = 1


def looks_like_heading(line: str) -> tuple[bool, str | None, str | None, int]:
    """
    Classify a single line.

    Returns ``(is_heading, number, title, level)``.  ``number`` is None when the
    heading carries no numbering of its own.
    """
    stripped = line.strip()
    if not stripped or _NOISE.match(stripped):
        return False, None, None, 0
    if len(stripped.split()) > MAX_HEADING_WORDS:
        return False, None, None, 0
    if stripped.endswith((".", ";", ",")) and not _NUMBERED_HEADING.match(stripped):
        return False, None, None, 0

    match = _SECTION_WORD_HEADING.match(stripped) or _NUMBERED_HEADING.match(stripped)
    if match:
        number = match.group("number")
        title = (match.group("title") or "").strip(" .:-–")
        # "2026 was a busy year" is not a heading; require a real title.
        if not title:
            return False, None, None, 0
        level = number.count(".") + 1
        return True, number, title, level

    caps = _ALL_CAPS_HEADING.match(stripped)
    if caps and len(stripped) >= 4:
        return True, None, caps.group("title").strip(), 1

    return False, None, None, 0


class _SectionNumberer:
    """Synthesises hierarchical refs (1, 1.1, 1.2, 2) for unnumbered headings."""

    def __init__(self) -> None:
        self._counters: list[int] = []

    def next_ref(self, level: int) -> str:
        level = max(1, min(level, 6))
        if len(self._counters) < level:
            self._counters.extend([0] * (level - len(self._counters)))
        else:
            del self._counters[level:]
        self._counters[level - 1] += 1
        return ".".join(str(n) for n in self._counters)


def _finalise(
    sections: list[ParsedSection], buffer: list[str], current: ParsedSection | None
) -> None:
    if current is None:
        return
    current.text = "\n".join(buffer).strip()
    if len(current.text) >= MIN_SECTION_CHARS or current.heading:
        sections.append(current)


def build_sections_from_lines(
    lines: list[tuple[str, int | None, int | None]],
    *,
    preamble_heading: str = "Preamble",
) -> list[ParsedSection]:
    """
    Group ``(text, page_no, paragraph_index)`` lines into sections.

    Text appearing before the first heading is not discarded — front matter and
    metadata blocks live there — it becomes a "Preamble" section so it stays
    retrievable and citable.
    """
    sections: list[ParsedSection] = []
    numberer = _SectionNumberer()
    current: ParsedSection | None = None
    buffer: list[str] = []
    ordinal = 0

    for text, page_no, para_index in lines:
        if not text.strip():
            if buffer:
                buffer.append("")
            continue

        is_heading, number, title, level = looks_like_heading(text)

        if is_heading:
            _finalise(sections, buffer, current)
            buffer = []
            ordinal += 1
            if number:
                section_ref = number
                numbered = True
            else:
                section_ref = numberer.next_ref(level)
                numbered = False
            current = ParsedSection(
                section_ref=section_ref,
                heading=title,
                level=level,
                text="",
                ordinal=ordinal,
                page_no=page_no,
                paragraph_index=para_index,
                numbered_in_source=numbered,
            )
            continue

        if current is None:
            ordinal += 1
            current = ParsedSection(
                section_ref="0",
                heading=preamble_heading,
                level=1,
                text="",
                ordinal=ordinal,
                page_no=page_no,
                paragraph_index=para_index,
                numbered_in_source=False,
            )
        buffer.append(text)

    _finalise(sections, buffer, current)
    return _deduplicate_refs([s for s in sections if not s.is_empty or s.heading])


def _deduplicate_refs(sections: list[ParsedSection]) -> list[ParsedSection]:
    """
    A section_ref must be unique within a document version - the database
    enforces it, and a duplicate would make a citation ambiguous.  Repeats get
    a suffix rather than being dropped.
    """
    seen: dict[str, int] = {}
    for section in sections:
        ref = section.section_ref
        if ref in seen:
            seen[ref] += 1
            section.section_ref = f"{ref}({seen[ref]})"
        else:
            seen[ref] = 0
    return sections
