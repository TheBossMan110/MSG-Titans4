"""
Chunking (SRS Step 6 — every chunk must retain Chunk ID, Document ID, Section,
Heading, Page reference and Version).

One rule governs everything here: **a chunk never crosses a section boundary.**

It would be easy to get better retrieval recall by sliding a fixed window over
the whole document, and it would quietly destroy the thing this project is
judged on.  A chunk spanning sections 5.2 and 5.3 cannot be cited honestly —
whichever section it claims, half its text comes from somewhere else, and a
judge picking a generated sentence during the Source-Traceability Challenge
would find the cited section does not contain it.

So sections are the hard boundary.  Long sections are split on sentence
boundaries with a configurable overlap; short sections stay whole.  Overlap is
applied *within* a section only, for the same reason.
"""

from __future__ import annotations

import re

from document_processing.contracts import ChunkCandidate, ParsedSection
from src.core.config import settings

# Sentence-ish boundary: terminator + whitespace + capital / digit / bullet.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(•\-])")
_PARAGRAPH_BOUNDARY = re.compile(r"\n{2,}")
_WHITESPACE = re.compile(r"[ \t]+")

# ~4 characters per token is close enough for budgeting and costs nothing.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _normalise(text: str) -> str:
    text = _WHITESPACE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _split_units(text: str) -> list[str]:
    """
    Break a section into the smallest pieces we are willing to split on.

    Paragraphs first, then sentences inside an over-long paragraph.  A single
    sentence longer than the budget is never cut mid-sentence: it is emitted
    whole and allowed to exceed the target, because a truncated clause in a
    policy document can invert its meaning.
    """
    units: list[str] = []
    for paragraph in _PARAGRAPH_BOUNDARY.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(
            sentence.strip()
            for sentence in _SENTENCE_BOUNDARY.split(paragraph)
            if sentence.strip()
        )
    return units


def _pack(units: list[str], max_tokens: int, overlap_tokens: int) -> list[str]:
    """Greedily pack units into chunks, carrying an overlap tail forward."""
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = estimate_tokens(unit)

        if current and current_tokens + unit_tokens > max_tokens:
            chunks.append(" ".join(current))
            # Carry the tail of the finished chunk into the next one so a fact
            # split across the boundary is still retrievable from both sides.
            tail: list[str] = []
            tail_tokens = 0
            for previous in reversed(current):
                previous_tokens = estimate_tokens(previous)
                if tail_tokens + previous_tokens > overlap_tokens:
                    break
                tail.insert(0, previous)
                tail_tokens += previous_tokens
            current = tail
            current_tokens = tail_tokens

        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_section(
    section: ParsedSection,
    *,
    doc_ref: str,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[ChunkCandidate]:
    """
    Chunk a single section.

    The heading is prepended to every chunk of the section.  Retrieval quality
    depends on it: a chunk reading "within 48 hours of delivery" is ambiguous
    on its own, and useful under the heading "5.2 Refund Windows".
    """
    max_tokens = max_tokens or settings.chunk_tokens
    overlap_tokens = overlap_tokens or settings.chunk_overlap

    body = _normalise(section.text)
    if not body and not section.heading:
        return []

    heading_prefix = f"{section.section_ref} {section.heading}".strip() if section.heading else ""
    units = _split_units(body) or ([heading_prefix] if heading_prefix else [])
    if not units:
        return []

    # Budget for the heading we prepend to each chunk.
    budget = max(64, max_tokens - estimate_tokens(heading_prefix))
    pieces = _pack(units, budget, min(overlap_tokens, budget // 2))

    candidates: list[ChunkCandidate] = []
    for index, piece in enumerate(pieces, start=1):
        text = f"{heading_prefix}\n{piece}".strip() if heading_prefix else piece
        candidates.append(
            ChunkCandidate(
                chunk_key=f"{doc_ref}::{section.section_ref}::c{index}",
                text=text,
                ordinal=0,  # assigned document-wide by chunk_document
                section_ref=section.section_ref,
                heading=section.heading,
                page_no=section.page_no,
                paragraph_index=section.paragraph_index,
                token_count=estimate_tokens(text),
            )
        )
    return candidates


def chunk_document(
    sections: list[ParsedSection],
    *,
    doc_ref: str,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[ChunkCandidate]:
    """Chunk every section, assigning a stable document-wide ordinal."""
    chunks: list[ChunkCandidate] = []
    for section in sections:
        chunks.extend(
            chunk_section(
                section,
                doc_ref=doc_ref,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
        )

    for ordinal, chunk in enumerate(chunks, start=1):
        chunk.ordinal = ordinal

    return [c for c in chunks if not c.is_empty]
