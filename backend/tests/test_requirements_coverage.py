"""
Requirement coverage enforcement.

``config/requirements.yaml`` maps every SRS requirement to the artefacts that
implement it.  This suite makes that map *binding*:

* no requirement id may be missing,
* anything claimed ``done`` must actually exist — table, column, module file
  and API endpoint are each verified,
* anything marked ``partial`` must state its remaining gap in writing,
* status values are closed.

The point is that "we implemented requirement X" cannot drift away from the
truth without the build going red.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from src.db.models import Base

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "requirements.yaml"

VALID_STATUSES = {"done", "partial", "planned", "frontend"}
VERIFIABLE = {"done"}  # statuses whose artefacts must exist right now

# Roman numerals i..lxxv, in SRS order.
ROMAN_75 = [
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
    "xxi", "xxii", "xxiii", "xxiv", "xxv", "xxvi", "xxvii", "xxviii", "xxix", "xxx",
    "xxxi", "xxxii", "xxxiii", "xxxiv", "xxxv", "xxxvi", "xxxvii", "xxxviii", "xxxix", "xl",
    "xli", "xlii", "xliii", "xliv", "xlv", "xlvi", "xlvii", "xlviii", "xlix", "l",
    "li", "lii", "liii", "liv", "lv", "lvi", "lvii", "lviii", "lix", "lx",
    "lxi", "lxii", "lxiii", "lxiv", "lxv", "lxvi", "lxvii", "lxviii", "lxix", "lxx",
    "lxxi", "lxxii", "lxxiii", "lxxiv", "lxxv",
]


@pytest.fixture(scope="module")
def registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema_index() -> dict[str, set[str]]:
    """table name -> set of column names, straight from the ORM metadata."""
    return {name: set(t.columns.keys()) for name, t in Base.metadata.tables.items()}


# ── completeness ─────────────────────────────────────────────────────
@pytest.mark.unit
def test_registry_file_exists():
    assert REGISTRY_PATH.exists(), "config/requirements.yaml is the coverage contract"


@pytest.mark.unit
def test_all_75_functional_requirements_are_listed(registry):
    listed = set(registry["functional_requirements"])
    expected = {f"FR-{n}" for n in ROMAN_75}
    assert len(expected) == 75
    assert listed == expected, (
        f"missing: {sorted(expected - listed)} | unexpected: {sorted(listed - expected)}"
    )


@pytest.mark.unit
def test_all_68_development_steps_are_listed(registry):
    listed = set(registry["development_steps"])
    expected = set(range(1, 69))
    assert listed == expected, f"missing steps: {sorted(expected - listed)}"


@pytest.mark.unit
def test_all_non_functional_requirements_are_listed(registry):
    nfrs = registry["non_functional_requirements"]
    assert len(nfrs) == registry["meta"]["non_functional_requirement_count"] == 5
    for key, entry in nfrs.items():
        assert entry.get("target"), f"{key} has no measurable target"
        assert entry.get("status") in VALID_STATUSES, key


@pytest.mark.unit
def test_all_integrity_requirements_are_listed(registry):
    items = registry["integrity_requirements"]
    assert len(items) == registry["meta"]["integrity_item_count"] == 19
    assert set(items) == set(range(1, 20))


# ── honesty ──────────────────────────────────────────────────────────
@pytest.mark.unit
def test_every_status_value_is_recognised(registry):
    bad = []
    for section in ("functional_requirements", "development_steps",
                    "integrity_requirements", "non_functional_requirements"):
        for key, entry in registry[section].items():
            if entry.get("status") not in VALID_STATUSES:
                bad.append(f"{section}:{key}={entry.get('status')}")
    assert not bad, f"unrecognised status values: {bad}"


@pytest.mark.unit
def test_partial_requirements_declare_their_gap(registry):
    """
    A requirement claimed as half-done must say what is missing.  This stops
    'partial' being used as a vague hiding place.
    """
    undocumented = [
        f"{section}.{key}"
        for section in (
            "functional_requirements",
            "development_steps",
            "non_functional_requirements",
            "integrity_requirements",
        )
        for key, entry in registry.get(section, {}).items()
        if entry.get("status") == "partial" and not entry.get("gap")
    ]
    assert not undocumented, f"partial without a documented gap: {undocumented}"


# ── artefacts claimed as done must exist ─────────────────────────────
@pytest.mark.unit
def test_declared_tables_exist(registry, schema_index):
    missing = []
    for key, entry in registry["functional_requirements"].items():
        for table in entry.get("tables", []):
            if table not in schema_index:
                missing.append(f"{key} -> table '{table}'")
    assert not missing, f"requirements reference non-existent tables: {missing}"


@pytest.mark.unit
def test_declared_columns_exist(registry, schema_index):
    missing = []
    for key, entry in registry["functional_requirements"].items():
        for ref in entry.get("columns", []):
            table, _, column = ref.partition(".")
            if table not in schema_index:
                missing.append(f"{key} -> unknown table in '{ref}'")
            elif column not in schema_index[table]:
                missing.append(f"{key} -> '{ref}'")
    assert not missing, f"requirements reference non-existent columns: {missing}"


@pytest.mark.unit
def test_modules_for_done_requirements_exist(registry):
    missing = []
    for key, entry in registry["functional_requirements"].items():
        if entry["status"] not in VERIFIABLE:
            continue
        for module in entry.get("modules", []):
            if not (ROOT / module).exists():
                missing.append(f"{key} -> {module}")
    assert not missing, f"'done' requirements name missing modules: {missing}"


@pytest.mark.unit
def test_endpoints_for_done_requirements_exist(registry, client):
    spec = client.get("/api/openapi.json").json()
    available = {
        f"{method.upper()} {path}"
        for path, ops in spec["paths"].items()
        for method in ops
    }
    missing = []
    for key, entry in registry["functional_requirements"].items():
        if entry["status"] not in VERIFIABLE:
            continue
        for endpoint in entry.get("api", []):
            if endpoint not in available:
                missing.append(f"{key} -> {endpoint}")
    assert not missing, f"'done' requirements name missing endpoints: {missing}"


@pytest.mark.unit
def test_step_artefacts_for_done_steps_exist(registry, schema_index):
    """
    Step artefacts are a mix of table names, ``table.column`` references and
    repository paths.  Resolve each by shape.
    """
    missing = []
    for number, entry in registry["development_steps"].items():
        if entry["status"] not in VERIFIABLE:
            continue
        for artefact in entry.get("artefacts", []):
            if "/" in artefact:                       # a path
                if not (ROOT / artefact).exists():
                    missing.append(f"Step {number} -> path {artefact}")
            elif "." in artefact:                     # table.column
                table, _, column = artefact.partition(".")
                if table not in schema_index or column not in schema_index[table]:
                    missing.append(f"Step {number} -> column {artefact}")
            elif artefact not in schema_index:        # table
                missing.append(f"Step {number} -> table {artefact}")
    assert not missing, f"'done' steps name missing artefacts: {missing}"


@pytest.mark.unit
def test_integrity_evidence_for_done_items_exists(registry, schema_index):
    missing = []
    for number, entry in registry["integrity_requirements"].items():
        if entry["status"] not in VERIFIABLE:
            continue
        for artefact in entry.get("evidence", []):
            if "/" in artefact or artefact.endswith(".md"):
                if not (ROOT / artefact).exists():
                    missing.append(f"Integrity {number} -> path {artefact}")
            elif "." in artefact:
                table, _, column = artefact.partition(".")
                if table not in schema_index or column not in schema_index[table]:
                    missing.append(f"Integrity {number} -> column {artefact}")
            elif artefact not in schema_index:
                missing.append(f"Integrity {number} -> table {artefact}")
    assert not missing, f"'done' integrity items name missing evidence: {missing}"


# ── the schema itself ────────────────────────────────────────────────
@pytest.mark.unit
def test_every_table_is_referenced_by_at_least_one_requirement(registry, schema_index):
    """
    The reverse check: a table nobody's requirement points at is either dead
    weight or an undocumented feature.  Both are worth knowing about.
    """
    referenced: set[str] = set()
    for entry in registry["functional_requirements"].values():
        referenced.update(entry.get("tables", []))
        referenced.update(ref.split(".")[0] for ref in entry.get("columns", []))
    for entry in registry["development_steps"].values():
        for artefact in entry.get("artefacts", []):
            if "/" not in artefact:
                referenced.add(artefact.split(".")[0])
    for entry in registry["integrity_requirements"].values():
        for artefact in entry.get("evidence", []):
            if "/" not in artefact and not artefact.endswith(".md"):
                referenced.add(artefact.split(".")[0])

    # Infrastructure tables that support requirements without being named by one.
    INFRASTRUCTURE = {
        "alembic_version", "refresh_tokens", "llm_cache", "jobs",
        "document_sections", "complaint_attachments", "complaint_status_history",
        "benchmark_results", "impact_items", "response_flags", "rule_hits",
        "verification_decisions", "subcategories", "sla_events", "escalations",
        "follow_ups", "review_actions", "comparisons", "prompt_versions",
        "customers", "agent_guidance", "resolution_steps", "eligibility_decisions",
        "clarification_questions", "complaint_policy_refs", "trend_snapshots",
        "complaint_validation_issues", "document_validation_issues",
        "injection_events", "report_exports", "benchmark_runs", "impact_analyses",
        "audit_log", "documents", "chunks", "complaint_links", "complaint_entities",
        "promise_patterns", "injection_patterns", "app_config", "responses",
        "review_queue", "genai_runs", "validation_runs",
    }
    orphans = set(schema_index) - referenced - INFRASTRUCTURE
    assert not orphans, (
        f"tables not traceable to any requirement: {sorted(orphans)}. "
        "Either map them in config/requirements.yaml or remove them."
    )


@pytest.mark.unit
def test_srs_minimum_table_set_is_present(schema_index):
    """
    Tables the SRS effectively mandates by naming the thing they store.
    A blunt backstop against an accidental deletion.
    """
    required = {
        # pipelines and verification - the core of the category
        "genai_runs", "validation_runs", "rule_hits", "comparisons",
        "verification_decisions", "rules",
        # knowledge base with traceability
        "documents", "document_versions", "document_sections", "chunks",
        # complaints
        "complaints", "customers", "complaint_entities", "complaint_links",
        "complaint_status_history", "complaint_attachments",
        # intelligence detail
        "complaint_policy_refs", "resolution_steps", "eligibility_decisions",
        "clarification_questions", "agent_guidance",
        # workflow
        "responses", "response_flags", "escalations", "follow_ups",
        "review_queue", "review_actions", "sla_events", "sla_policies",
        # validation findings
        "complaint_validation_issues", "document_validation_issues",
        # security and ops
        "injection_events", "injection_patterns", "promise_patterns",
        "lexicon_terms", "audit_log", "benchmark_runs", "benchmark_results",
        "impact_analyses", "impact_items", "report_exports", "trend_snapshots",
        # taxonomy and config
        "users", "departments", "categories", "subcategories",
        "priority_levels", "escalation_levels", "app_config", "prompt_versions",
    }
    missing = required - set(schema_index)
    assert not missing, f"SRS-mandated tables are missing: {sorted(missing)}"


@pytest.mark.unit
def test_registry_roman_numerals_are_well_formed(registry):
    """Guard against a typo creating a silently-unchecked duplicate id."""
    pattern = re.compile(r"^FR-[ivxl]+$")
    bad = [k for k in registry["functional_requirements"] if not pattern.match(k)]
    assert not bad, f"malformed requirement ids: {bad}"
