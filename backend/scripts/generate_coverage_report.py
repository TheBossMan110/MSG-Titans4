"""
Render documentation/REQUIREMENTS_COVERAGE.md from config/requirements.yaml.

    python scripts/generate_coverage_report.py

The markdown is generated, never hand-edited, so it cannot drift away from the
registry that the test suite enforces.  Run it before every submission.
"""

from __future__ import annotations

import pathlib
import sys
from collections import Counter
from datetime import UTC, datetime

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "requirements.yaml"
OUTPUT = ROOT / "documentation" / "REQUIREMENTS_COVERAGE.md"

BADGE = {
    "done": "✅ Done",
    "partial": "🟡 Partial",
    "planned": "⬜ Planned",
    "frontend": "🖥️ Frontend",
}


def _cell(values: list[str] | None, limit: int = 4) -> str:
    if not values:
        return "—"
    shown = [f"`{v}`" for v in values[:limit]]
    if len(values) > limit:
        shown.append(f"+{len(values) - limit} more")
    return " ".join(shown)


def _summary(counter: Counter, total: int) -> str:
    parts = [
        f"{BADGE[status]} {counter.get(status, 0)}"
        for status in ("done", "partial", "planned", "frontend")
        if counter.get(status)
    ]
    return " · ".join(parts) + f" · **{total} total**"


def build(registry: dict) -> str:
    meta = registry["meta"]
    frs = registry["functional_requirements"]
    steps = registry["development_steps"]
    nfrs = registry["non_functional_requirements"]
    integrity = registry["integrity_requirements"]

    fr_counts = Counter(e["status"] for e in frs.values())
    step_counts = Counter(e["status"] for e in steps.values())

    out: list[str] = []
    w = out.append

    w("# SRS Requirement Coverage")
    w("")
    w(f"**{meta['project']}** · {meta['theme']} · {meta['category']}")
    w("")
    w(
        "> Generated from `config/requirements.yaml` by "
        "`scripts/generate_coverage_report.py`. Do not edit by hand."
    )
    w(f"> Last generated: {datetime.now(UTC):%Y-%m-%d %H:%M UTC}")
    w("")
    w("`tests/test_requirements_coverage.py` fails the build if any requirement is")
    w("missing from the registry, if anything marked **Done** names a table, column,")
    w("module or endpoint that does not exist, or if anything marked **Partial** does")
    w("not state its remaining gap.")
    w("")
    w("| Section | Coverage |")
    w("|---|---|")
    w(f"| Functional requirements (1.6) | {_summary(fr_counts, len(frs))} |")
    w(f"| Development steps (1.2) | {_summary(step_counts, len(steps))} |")
    w(f"| Non-functional requirements (1.7) | **{len(nfrs)} total** |")
    w(f"| Competition integrity (1.8) | **{len(integrity)} total** |")
    w("")

    # ── functional requirements ──
    w("---")
    w("")
    w("## 1.6 Functional Requirements")
    w("")
    w("| # | Requirement | Status | Tables | Modules | Notes / Gap |")
    w("|---|---|---|---|---|---|")
    for key, entry in frs.items():
        number = key.replace("FR-", "")
        note = entry.get("gap") or entry.get("notes") or ""
        note = " ".join(note.split())
        if len(note) > 150:
            note = note[:147] + "…"
        if entry.get("gap"):
            note = f"**Gap:** {note}"
        w(
            f"| {number} | {entry['name']} | {BADGE[entry['status']]} "
            f"| {_cell(entry.get('tables'), 3)} | {_cell(entry.get('modules'), 2)} "
            f"| {note or '—'} |"
        )
    w("")

    # ── development steps ──
    w("---")
    w("")
    w("## 1.2 Development Steps")
    w("")
    w("| Step | Name | Status | Artefacts |")
    w("|---|---|---|---|")
    for number, entry in sorted(steps.items()):
        w(
            f"| {number} | {entry['name']} | {BADGE[entry['status']]} "
            f"| {_cell(entry.get('artefacts'), 3)} |"
        )
    w("")

    # ── non-functional ──
    w("---")
    w("")
    w("## 1.7 Non-Functional Requirements")
    w("")
    for key, entry in nfrs.items():
        w(f"### {key} — {entry['name']}  {BADGE[entry['status']]}")
        w("")
        w(f"**Target:** {' '.join(str(entry['target']).split())}")
        w("")
        if entry.get("approach"):
            w(f"**Approach:** {' '.join(entry['approach'].split())}")
            w("")
        if entry.get("evidence"):
            w(f"**Evidence:** {_cell(entry['evidence'], 6)}")
            w("")

    # ── integrity ──
    w("---")
    w("")
    w("## 1.8 Competition Integrity and Anti-Shortcut Requirements")
    w("")
    w("| # | Item | Status | Evidence | Note |")
    w("|---|---|---|---|---|")
    for number, entry in sorted(integrity.items()):
        note = " ".join(entry.get("note", "").split())
        w(
            f"| {number} | {entry['name']} | {BADGE[entry['status']]} "
            f"| {_cell(entry.get('evidence'), 3)} | {note or '—'} |"
        )
    w("")

    return "\n".join(out) + "\n"


def main() -> int:
    if not REGISTRY.exists():
        print(f"Registry not found: {REGISTRY}", file=sys.stderr)
        return 1
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build(registry), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
