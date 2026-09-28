"""
Render the Zenithra knowledge base to PDF and DOCX.

    python scripts/make_sample_documents.py

Source content lives in ``sample_documents/source/*.yaml`` as structured data;
this script renders each one to the format(s) it declares.  Keeping the content
as data and the rendering as code means:

* the same policy can be emitted as PDF *and* DOCX to prove both parsers work
  on identical content (SRS Step 3 makes both formats mandatory),
* a v1 and v2 of the same policy differ only in the fields that changed, which
  is what the Policy Update Challenge (SRS 1.8 #4) needs,
* adversarial documents carrying hidden instructions are authored the same way
  as ordinary ones, so nothing about them is special-cased in the pipeline.

Output goes to ``sample_documents/`` and is committed as part of the required
Knowledge-Base Dataset deliverable.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402

# The corpus lives outside the backend, split by business domain, and is
# authored by people who never open this code. Each domain renders in
# place: dataset/<domain>/documents/source/*.yaml -> ../*.pdf|docx
SOURCE_DIRS = settings.document_source_dirs
OUTPUT_DIRS = settings.document_dirs

METADATA_ORDER = [
    ("doc_ref", "Document ID"),
    ("title", "Title"),
    ("version", "Version"),
    ("doc_type", "Document Type"),
    ("department", "Department"),
    ("category", "Category"),
    ("effective_date", "Effective Date"),
    ("expiry_date", "Expiry Date"),
    ("owner", "Document Owner"),
    # Rendered so the file itself says it is a draft. Without it DOC-025 v0.9
    # reached ingest with only its dates, and a passed effective date made an
    # unapproved draft ACTIVE.
    ("status", "Status"),
]


def _metadata_lines(spec: dict) -> list[str]:
    meta = spec.get("metadata", {})
    return [f"{label}: {meta[key]}" for key, label in METADATA_ORDER if meta.get(key)]


# ── PDF rendering ────────────────────────────────────────────────────
def render_pdf(spec: dict, path: pathlib.Path) -> None:
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ZBody", parent=styles["BodyText"], fontSize=10, leading=14,
        spaceAfter=6, alignment=TA_LEFT,
    )
    heading = ParagraphStyle(
        "ZHeading", parent=styles["Heading2"], fontSize=12, leading=16,
        spaceBefore=12, spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "ZMeta", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=2,
    )

    story: list = [Paragraph(spec["metadata"]["title"], styles["Title"]), Spacer(1, 6 * mm)]
    story.extend(Paragraph(line, meta_style) for line in _metadata_lines(spec))
    story.append(Spacer(1, 8 * mm))

    for index, section in enumerate(spec["sections"]):
        if section.get("page_break") and index:
            story.append(PageBreak())
        story.append(Paragraph(f"{section['ref']} {section['heading']}", heading))
        for paragraph in section["body"]:
            story.append(Paragraph(paragraph, body))

    path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=spec["metadata"]["title"],
    ).build(story)


# ── DOCX rendering ───────────────────────────────────────────────────
def render_docx(spec: dict, path: pathlib.Path) -> None:
    import docx
    from docx.shared import Pt

    document = docx.Document()
    document.add_heading(spec["metadata"]["title"], level=0)

    for line in _metadata_lines(spec):
        paragraph = document.add_paragraph(line)
        paragraph.runs[0].font.size = Pt(9)

    for section in spec["sections"]:
        document.add_heading(f"{section['ref']} {section['heading']}", level=1)
        for paragraph in section["body"]:
            document.add_paragraph(paragraph)
        for table_spec in section.get("tables", []):
            rows = table_spec["rows"]
            table = document.add_table(rows=len(rows), cols=len(rows[0]))
            table.style = "Table Grid"
            for r, row in enumerate(rows):
                for c, cell in enumerate(row):
                    table.cell(r, c).text = str(cell)

    # Hidden-text runs, used only by the adversarial fixtures. The parser must
    # surface these so the injection scanner can see them (SRS 1.8 #8).
    for hidden in spec.get("hidden_text", []):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(hidden)
        run.font.hidden = True

    if spec.get("header_text"):
        document.sections[0].header.paragraphs[0].text = spec["header_text"]
    if spec.get("footer_text"):
        document.sections[0].footer.paragraphs[0].text = spec["footer_text"]

    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))


RENDERERS = {"pdf": render_pdf, "docx": render_docx}


def main() -> int:
    """
    Render every domain in place.

    Each domain owns its own source folder and output folder, so a document
    lands beside the others in its business area. Adding a domain is a folder
    and a line in DATASET_DOMAINS -- this script needs no change.
    """
    project = settings.dataset_dir.parent
    written: list[str] = []
    total_specs = 0

    for source_dir, output_dir in zip(SOURCE_DIRS, OUTPUT_DIRS, strict=True):
        if not source_dir.exists():
            print(f"  (no source folder: {source_dir}, skipping)", file=sys.stderr)
            continue

        specs = sorted(source_dir.glob("*.yaml"))
        total_specs += len(specs)
        for spec_path in specs:
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            meta = spec["metadata"]
            stem = f"{meta['doc_ref']}_v{meta['version']}"
            for fmt in spec.get("formats", ["pdf"]):
                renderer = RENDERERS.get(fmt)
                if renderer is None:
                    print(
                        f"  ! unknown format {fmt} in {spec_path.name}", file=sys.stderr
                    )
                    continue
                out_path = output_dir / f"{stem}.{fmt}"
                renderer(spec, out_path)
                written.append(
                    f"{out_path.relative_to(project)}  "
                    f"({out_path.stat().st_size:,} bytes)"
                )

    if not total_specs:
        print(
            f"No document sources found under {settings.dataset_dir}", file=sys.stderr
        )
        return 1

    print(f"Rendered {len(written)} file(s) from {total_specs} source document(s):")
    for line in written:
        print("  ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
