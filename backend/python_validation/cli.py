"""
Pipeline 2 from the command line.

    python -m python_validation.cli --text "My kettle is making a burning smell."
    python -m python_validation.cli --complaint-ref CMP-00421
    python -m python_validation.cli --text "..." --json
    python -m python_validation.cli --explain --text "..."

This exists to make one claim checkable rather than merely stated.

SRS 1.8 #18 says the Generative AI API "must not replace Python business
rules, ground-truth validation, policy precedence, escalation enforcement,
audit logic, security logic".  A reader can verify that here in two ways:

    # 1. no provider client is reachable from this package
    grep -rE "google|groq|openai|anthropic" python_validation/

    # 2. it produces a complete answer with no API key configured
    GEMINI_API_KEY= GROQ_API_KEY= python -m python_validation.cli --text "..."

Both are asserted by the test suite as well, so the property cannot quietly
decay as the code grows.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from sqlalchemy import select

from python_validation.pipeline import ValidationResult, run_validation
from src.core.config import settings
from src.core.logging import configure_logging
from src.db.base import SessionLocal
from src.db.models import Complaint

# Plain ASCII markers: this output is read in terminals, CI logs and
# screenshots, and a box-drawing character that renders as a mojibake box in a
# Windows console helps nobody.
RULE = "-" * 74


def _print_header(title: str) -> None:
    print(f"\n{title}\n{RULE}")


def _print_field(label: str, value: Any, *, note: str = "") -> None:
    shown = value if value not in (None, "", [], {}) else "-"
    suffix = f"   <- {note}" if note else ""
    print(f"  {label:<24} {shown}{suffix}")


def _render(result: ValidationResult, *, explain: bool) -> None:
    outcome = result.outcome

    _print_header("PIPELINE 2 - PYTHON GROUND TRUTH")
    _print_field("ruleset version", result.ruleset_version)
    _print_field("rules evaluated", f"{len(outcome.applied_hits)} matched")
    _print_field("passes", result.passes)
    _print_field("latency", f"{result.latency_ms} ms")

    _print_header("DERIVED CLASSIFICATION")
    _print_field("category", outcome.category_code)
    _print_field("subcategory", outcome.subcategory_code)
    _print_field("department", outcome.department_code)
    _print_field("support department", outcome.support_department_code)
    _print_field("urgency", outcome.urgency)
    _print_field("priority", outcome.priority_code)

    floor_note = ""
    if outcome.escalation_floor_code:
        floor_note = f"mandatory floor: {outcome.escalation_floor_code}"
    _print_field("escalation", outcome.escalation_code, note=floor_note)

    if outcome.unmatched:
        print("\n  ** UNMATCHED - no rule recognised this complaint.")
        print("     Routed for manual review rather than assigned a plausible guess.")
    if outcome.conflict_detected:
        print("\n  ** RULE CONFLICT")
        for conflict in outcome.conflicts:
            print(
                f"     {conflict.field_name}: {conflict.values} "
                f"({', '.join(conflict.rule_refs)}) -> {conflict.resolved_to}"
            )
    if outcome.rule_errors:
        print("\n  ** RULE ERRORS")
        for error in outcome.rule_errors:
            print(f"     {error}")

    _print_header("SIGNALS DETECTED")
    visible = sorted(result.signals.for_rules())
    if visible:
        for key in visible:
            spans = result.signals.spans(key)
            evidence = ", ".join(f'"{s["text"]}"' for s in spans[:3])
            more = f" (+{len(spans) - 3})" if len(spans) > 3 else ""
            print(f"  {key:<24} {evidence}{more}")
    else:
        print("  (none)")

    hidden = sorted(result.signals.analytics_only & set(result.signals.detected))
    if hidden:
        print(f"\n  analytics-only (withheld from rules): {', '.join(hidden)}")
        print("  These are recorded for reporting but cannot influence urgency or")
        print("  priority - see SRS 1.8 #6, the Sentiment-Urgency Trap.")

    if outcome.required_actions:
        _print_header("REQUIRED ACTIONS")
        for action in outcome.required_actions:
            print(f"  + {action}")

    if outcome.prohibited_actions:
        _print_header("PROHIBITED ACTIONS")
        for action in outcome.prohibited_actions:
            print(f"  x {action}")

    if result.eligibility:
        _print_header("ELIGIBILITY FINDINGS")
        for finding in result.eligibility:
            approval = " (human approval required)" if finding["requires_human_approval"] else ""
            print(
                f"  {finding['eligibility_type']:<18} {finding['python_outcome']}"
                f"{approval}   [{finding['rule_ref']}]"
            )
            for condition in finding["conditions_evaluated"]:
                print(f"       - {condition}")

    if outcome.policy_refs:
        _print_header("POLICY REFERENCES")
        for ref in outcome.policy_refs:
            section = ref.get("section_ref")
            print(f"  {ref.get('doc_ref')}{' s' + section if section else ''}")

    if explain and outcome.hits:
        _print_header("WHY (rule trace, highest precedence first)")
        for entry in outcome.explain():
            marker = "*" if entry["mandatory_escalation"] else " "
            state = "" if entry["applied"] else "  [not applied]"
            print(f"\n {marker} {entry['rule_ref']}  (precedence {entry['precedence']}){state}")
            if entry["rationale"]:
                print(f"     {entry['rationale']}")
            if entry["signals"]:
                print(f"     signals: {', '.join(entry['signals'])}")
            for span in entry["spans"][:3]:
                print(f'     matched: "{span["text"]}" at {span["start"]}-{span["end"]}')
        print("\n  * = mandatory escalation rule (sets a floor nothing may lower)")

    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m python_validation.cli",
        description=(
            "Run the Python ground-truth validation pipeline. "
            "Uses no Generative AI API and needs no API key."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Complaint text to validate")
    source.add_argument("--complaint-ref", help="Public reference of a stored complaint")
    source.add_argument("--complaint-id", help="UUID of a stored complaint")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a report")
    parser.add_argument("--explain", action="store_true", help="Show the full rule trace")
    parser.add_argument("--persist", action="store_true", help="Store the validation run")
    parser.add_argument("--quiet", action="store_true", help="Suppress log output")
    args = parser.parse_args(argv)

    configure_logging("ERROR" if (args.quiet or args.json) else settings.log_level,
                      json_output=False)

    db = SessionLocal()
    try:
        complaint: Complaint | None = None

        if args.complaint_ref or args.complaint_id:
            query = select(Complaint)
            query = (
                query.where(Complaint.public_ref == args.complaint_ref)
                if args.complaint_ref
                else query.where(Complaint.id == args.complaint_id)
            )
            complaint = db.execute(query).scalars().first()
            if complaint is None:
                identifier = args.complaint_ref or args.complaint_id
                print(f"No complaint found: {identifier}", file=sys.stderr)
                return 1
            text = complaint.description_clean or complaint.description_raw or ""
        else:
            text = args.text or ""

        if not text.strip():
            print("Nothing to validate: the complaint text is empty.", file=sys.stderr)
            return 1

        result = run_validation(db, text=text, complaint=complaint)

        if args.persist and complaint is not None:
            from python_validation.pipeline import persist_validation

            persist_validation(db, complaint, result)
            db.commit()

        if args.json:
            print(json.dumps(result.summary(), indent=2, default=str))
        else:
            if complaint is not None:
                print(f"\nComplaint: {complaint.public_ref}")
            print(f'Text: "{text[:200]}{"..." if len(text) > 200 else ""}"')
            _render(result, explain=args.explain)

            if not settings.gemini_api_key and not settings.groq_api_key:
                print("No GenAI API key is configured, and this result did not need one.\n")

        # Exit 2 signals "needs a human", which makes the CLI usable in a
        # batch script without parsing its output.
        return 2 if result.requires_review else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
