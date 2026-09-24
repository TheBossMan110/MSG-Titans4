"""
Verify an authored dataset before it is imported.

    python scripts/verify_dataset.py ../dataset/raftarxpress

Run this on every revision the dataset author sends. A corpus is only worth as
much as its labels: a broken reference or a duplicate id does not fail loudly
at import time, it quietly lowers a benchmark score, and then the score gets
blamed on the pipeline.

Checks, in the order a problem would bite:

1. **Structural** -- files present, parseable, uniform schema, no duplicate ids.
2. **Referential** -- every category, subcategory, department, rule and policy
   reference the ground truth names actually exists.
3. **Coverage** -- every complaint's (category, subcategory) pair has a rule,
   every rule is exercised, both halves of each escalation ladder are used.
4. **Adversarial** -- the share of cases that carry the traps the SRS scores.

Exit code is 1 when anything in 1 or 2 fails, because those are wrong rather
than merely thin. Coverage and adversarial findings are reported as warnings:
they are judgements about the corpus, not defects in it.
"""

from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import sys
from typing import Any

# Cases the SRS scores directly. A corpus with none of one of these cannot
# demonstrate the matching challenge, however many complaints it holds.
SCORED_TRAPS = {
    "prompt_injection": "Prompt Injection Challenge (1.8 #8)",
    "multi_issue": "Multi-Issue Complaint Challenge (1.8 #12)",
    "incomplete": "Missing Information Challenge (1.8 #11)",
    "repeated": "Repeat Complaint Challenge (1.8 #13)",
    "contradictory": "Contradictory Policy Challenge (1.8 #10)",
    "adversarial": "general adversarial set",
}

MIN_DESCRIPTION = 40

# The SRS dataset table, verbatim. Checked rather than remembered: these are
# the numbers a judge counts, and "we think we have enough" is not an answer.
# Each entry is (label, minimum, the bucket tags that count toward it).
SRS_MINIMUMS: list[tuple[str, int, tuple[str, ...]]] = [
    ("Ambiguous / multi-issue complaints", 25, ("multi_issue",)),
    ("Contradictory / difficult policy cases", 20, ("contradictory",)),
    (
        "Prompt-injection / adversarial complaints",
        20,
        ("prompt_injection", "adversarial", "jailbreak_attempt"),
    ),
    ("Repeated / near-duplicate complaints", 25, ("repeated", "near_duplicate")),
]

# The suggested 500-complaint mix. Below one of these is not a failure -- the
# minimum above is the requirement -- but it is worth saying, because a corpus
# that is mostly traps measures something different from one that is mostly
# routine work.
SUGGESTED_MIX: list[tuple[str, int, tuple[str, ...]]] = [
    ("Ambiguous / multi-issue", 50, ("multi_issue",)),
    ("Contradictory / difficult policy", 40, ("contradictory",)),
    (
        "Prompt-injection / adversarial",
        35,
        ("prompt_injection", "adversarial", "jailbreak_attempt"),
    ),
    ("Repeated / near-duplicate", 30, ("repeated", "near_duplicate")),
    (
        "Calm but critical / sentiment traps",
        25,
        ("calm_but_critical", "calm_critical", "sentiment_urgency_trap"),
    ),
    ("Missing-information", 20, ("incomplete",)),
]

MIN_DOCUMENTS = 20
MIN_COMPLAINTS = 500
MIN_CATEGORIES = 10
MIN_SUBCATEGORIES = 20
MIN_DEPARTMENTS = 8
MIN_RULES = 100
MIN_MANDATORY_ESCALATIONS = 30


class Report:
    """Findings, separated by whether they make the corpus wrong or thin."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.facts: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def fact(self, message: str) -> None:
        self.facts.append(message)

    def render(self) -> int:
        print("\n-- what is in the corpus " + "-" * 46)
        for line in self.facts:
            print(f"   {line}")

        if self.warnings:
            print("\n-- worth a look " + "-" * 55)
            for line in self.warnings:
                print(f"   ! {line}")

        if self.errors:
            print("\n-- wrong " + "-" * 62)
            for line in self.errors:
                print(f"   x {line}")
            print(f"\n{len(self.errors)} problem(s) must be fixed before import.\n")
            return 1

        print("\n   No structural or referential problems.\n")
        return 0


def _load(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path.name} is not valid JSON: {exc}") from exc


def verify(root: pathlib.Path) -> int:
    report = Report()

    config = root / "configuration"
    complaints_dir = root / "complaints"
    documents = root / "documents" / "source" / "knowledge_base_documents.json"

    for required in (config, complaints_dir, documents):
        if not required.exists():
            report.error(f"missing: {required.relative_to(root)}")
    if report.errors:
        return report.render()

    taxonomy = _load(config / "complaint_taxonomy.json")
    organisation = _load(config / "organization_profile.json")
    rule_matrix = _load(config / "complaint_resolution_rules.json")["rule_matrix"]
    kb = _load(documents)["documents"]

    rows: list[dict[str, Any]] = []
    for path in sorted(complaints_dir.glob("complaints_batch_*.json")):
        payload = _load(path)
        rows.extend(payload["complaints"] if isinstance(payload, dict) else payload)

    categories = {c["category_id"] for c in taxonomy["categories"]}
    subcategories = {s["subcategory_id"] for s in taxonomy["subcategories"]}
    departments = {d["department_id"] for d in organisation["departments"]}
    rule_ids = {r["rule_id"] for r in rule_matrix}
    doc_ids = {d["document_id"] for d in kb}
    section_ids = {s["section_id"] for d in kb for s in d["sections"]}

    report.fact(
        f"{len(rows)} complaints | {len(rule_matrix)} rules | {len(kb)} documents"
    )
    report.fact(
        f"{len(categories)} categories | {len(subcategories)} subcategories | "
        f"{len(departments)} departments"
    )

    mandatory = sum(1 for r in rule_matrix if r.get("is_mandatory_escalation"))
    for label, actual, minimum in (
        ("complaints", len(rows), MIN_COMPLAINTS),
        ("categories", len(categories), MIN_CATEGORIES),
        ("subcategories", len(subcategories), MIN_SUBCATEGORIES),
        ("departments", len(departments), MIN_DEPARTMENTS),
        ("policy documents", len(kb), MIN_DOCUMENTS),
        ("resolution rules", len(rule_matrix), MIN_RULES),
        ("mandatory escalation rules", mandatory, MIN_MANDATORY_ESCALATIONS),
    ):
        if actual < minimum:
            report.error(f"{actual} {label}; the SRS requires at least {minimum}")
        else:
            report.fact(f"{label}: {actual} (SRS minimum {minimum})")

    # -- 1. structural --
    ids = [r.get("complaint_id") for r in rows]
    duplicates = [k for k, n in collections.Counter(ids).items() if n > 1]
    if duplicates:
        report.error(f"duplicate complaint ids: {duplicates[:8]}")

    schemas = {tuple(sorted(r)) for r in rows}
    if len(schemas) > 1:
        report.error(
            f"{len(schemas)} different field sets across complaints; "
            "every row must carry the same keys"
        )

    for row in rows:
        cid = row.get("complaint_id", "?")
        if not (row.get("title") or "").strip():
            report.error(f"{cid}: empty title")
        body = (row.get("description") or "").strip()
        if not body:
            report.error(f"{cid}: empty description")
        elif len(body) < MIN_DESCRIPTION:
            report.warn(f"{cid}: description is {len(body)} characters")
        if "expected_ground_truth" not in row:
            report.error(f"{cid}: no expected_ground_truth, so it cannot be scored")

    # -- 2. referential --
    broken: dict[str, list[str]] = collections.defaultdict(list)
    for row in rows:
        truth = row.get("expected_ground_truth") or {}
        cid = row.get("complaint_id", "?")
        checks = (
            ("category_id", truth.get("category_id"), categories, True),
            ("subcategory_id", truth.get("subcategory_id"), subcategories, True),
            ("department_id", truth.get("department_id"), departments, True),
            ("supporting_department_id", truth.get("supporting_department_id"),
             departments, False),
            ("applicable_rule_id", truth.get("applicable_rule_id"), rule_ids, False),
        )
        for field, value, vocabulary, required in checks:
            if value is None:
                if required:
                    broken[field].append(f"{cid}: missing")
            elif value not in vocabulary:
                broken[field].append(f"{cid}: {value}")

    for field, problems in broken.items():
        report.error(
            f"{len(problems)} complaint(s) name an unknown {field}: {problems[:4]}"
        )

    for rule in rule_matrix:
        reference = rule.get("policy_reference") or {}
        if reference.get("document_id") not in doc_ids:
            report.error(
                f"{rule['rule_id']} cites document "
                f"{reference.get('document_id')}, which does not exist"
            )
        elif reference.get("section_id") not in section_ids:
            report.error(
                f"{rule['rule_id']} cites section "
                f"{reference.get('section_id')}, which does not exist"
            )

    known_ids = set(ids)
    dangling = sorted(
        {
            row["previous_complaint_reference"]
            for row in rows
            if row.get("previous_complaint_reference")
            and row["previous_complaint_reference"] not in known_ids
        }
    )
    if dangling:
        report.error(f"previous_complaint_reference points nowhere: {dangling[:6]}")

    # -- 3. coverage --
    truths = [r.get("expected_ground_truth") or {} for r in rows]
    rule_pairs = {(r["category_id"], r["subcategory_id"]) for r in rule_matrix}
    uncovered = sorted(
        {(t.get("category_id"), t.get("subcategory_id")) for t in truths} - rule_pairs
    )
    if uncovered:
        report.error(
            f"{len(uncovered)} complaint category/subcategory pair(s) have no rule: "
            f"{uncovered[:4]}"
        )

    exercised = {t.get("applicable_rule_id") for t in truths}
    idle = sorted(rule_ids - exercised)
    if idle:
        report.warn(
            f"{len(idle)} rule(s) no complaint exercises, so nothing proves they "
            f"fire: {idle[:6]}"
        )

    for field in ("urgency", "priority", "escalation_level", "sentiment"):
        spread = collections.Counter(t.get(field) for t in truths)
        report.fact(f"{field}: {dict(spread.most_common())}")

    escalated = sum(1 for t in truths if t.get("escalation_required"))
    share = escalated / len(rows) if rows else 0
    report.fact(f"escalation_required on {escalated}/{len(rows)} ({share:.0%})")
    if share > 0.4:
        report.warn(
            f"{share:.0%} of complaints escalate. A corpus this hot inflates "
            "escalation recall -- a system that escalated everything would score "
            "well on it. Worth a calmer majority."
        )

    # -- 4. adversarial --
    tags = collections.Counter(
        tag for row in rows for tag in (row.get("complaint_bucket_tags") or [])
    )

    def counted(names: tuple[str, ...]) -> int:
        return sum(tags.get(name, 0) for name in names)

    for label, minimum, names in SRS_MINIMUMS:
        actual = counted(names)
        if actual < minimum:
            report.error(
                f"{actual} {label}; the SRS requires at least {minimum} "
                f"(tags: {', '.join(names)})"
            )
        else:
            report.fact(f"{label}: {actual} (SRS minimum {minimum})")

    special = 0
    for label, suggested, names in SUGGESTED_MIX:
        actual = counted(names)
        special += actual
        if actual < suggested:
            report.warn(
                f"{label}: {actual}, below the suggested {suggested}. Above the "
                "SRS minimum, so this is a judgement about the mix rather than "
                "a shortfall."
            )

    routine = len(rows) - special
    report.fact(f"routine complaints: about {routine} (suggested 300)")
    if routine < 200:
        report.warn(
            f"only about {routine} routine complaints against {special} carrying "
            "a trap. A corpus that is mostly traps measures how the system "
            "handles traps, which is not the same as how it handles the work."
        )

    for tag, why in SCORED_TRAPS.items():
        if not tags.get(tag):
            report.warn(f"no complaint tagged '{tag}' -- cannot demonstrate {why}")

    lifecycle = collections.Counter(d.get("lifecycle_status") for d in kb)
    report.fact(f"document lifecycle: {dict(lifecycle)}")
    if not lifecycle.get("Superseded"):
        report.warn(
            "no superseded document version -- the Hidden Policy Update and "
            "Contradictory Policy challenges both need one"
        )

    # The stated lifecycle and the dates have to agree. Ingestion derives
    # status from the dates, so a document labelled Draft with an effective
    # date in the past ingests as ACTIVE -- and the label silently loses.
    today = datetime.date.today().isoformat()
    for document in kb:
        status = document.get("lifecycle_status")
        effective = document.get("effective_date")
        expiry = document.get("expiry_date")
        doc_id = document.get("document_id")

        if status == "Draft" and effective and effective <= today:
            report.warn(
                f"{doc_id} is labelled Draft but takes effect {effective}, which "
                "has passed. Ingestion reads the dates, so it will load as ACTIVE."
            )
        if status == "Active" and expiry and expiry <= today:
            report.warn(
                f"{doc_id} is labelled Active but expired {expiry}; it will load "
                "as EXPIRED and stop being retrievable."
            )
        if status == "Superseded" and not expiry:
            report.warn(
                f"{doc_id} is labelled Superseded but states no expiry date, so "
                "nothing in the dates marks it out of force."
            )

    families = collections.Counter(d.get("document_family_id") for d in kb)
    versioned = sum(1 for n in families.values() if n > 1)
    report.fact(f"{len(families)} document families, {versioned} with 2+ versions")

    rendered = root / "documents"
    pdfs = len(list(rendered.glob("*.pdf")))
    docx = len(list(rendered.glob("*.docx")))
    report.fact(f"rendered: {pdfs} PDF + {docx} DOCX")
    if not pdfs or not docx:
        report.error(
            "the SRS requires the knowledge base to support PDF and DOCX; the "
            f"corpus renders {pdfs} PDF and {docx} DOCX. Run "
            "scripts/make_sample_documents.py."
        )

    references = [r.get("order_reference") for r in rows if r.get("order_reference")]
    shapes = collections.Counter(
        re.sub(r"\d", "#", str(value)) for value in references
    )
    report.fact(
        f"order references on {len(references)}/{len(rows)}; "
        f"{len(shapes)} distinct shapes"
    )

    return report.render()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = pathlib.Path(sys.argv[1]).resolve()
    if not root.exists():
        print(f"No such dataset: {root}")
        return 2
    print(f"\nVerifying {root.name}")
    return verify(root)


if __name__ == "__main__":
    raise SystemExit(main())
