"""
Convert the authored RaftarXpress corpus into the configuration the backend loads.

    python scripts/convert_raftarxpress.py taxonomy
    python scripts/convert_raftarxpress.py all

The dataset arrives as JSON written by someone who never opens the backend.
This turns it into the YAML the seeders read, and the CSV the benchmark
importer reads. It is a script rather than a one-off edit because the author
will send revisions, and hand-porting 105 rules twice is how the configuration
and the corpus drift apart.

**Codes are derived from names, once.** The corpus identifies things as
``CAT-01`` and ``DEPT-07``; the backend identifies them as ``DELIVERY`` and
``COMPLIANCE``, because a rule that reads ``department: DEPT-07`` cannot be
reviewed by the person who wrote the policy. The mapping is emitted alongside
the config so a ground-truth label can still be traced back to the id it came
from.

**Nothing is invented.** Where the corpus states a value it is carried across
unchanged. Where it states nothing -- a lexicon, for instance, which the rule
engine needs and the corpus does not contain -- what is generated is derived
from the corpus's own words and marked as generated, so a human tuning it later
knows what was authored and what was inferred.
"""

from __future__ import annotations

import collections
import csv
import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATASET = ROOT.parent / "dataset" / "raftarxpress"
CONFIG = DATASET / "configuration"

BANNER = "=" * 74


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════
# codes
# ══════════════════════════════════════════════════════════════
# Names that would slugify into something unreadable or over-long. Everything
# else is derived mechanically, so this list stays short and reviewable.
CODE_OVERRIDES: dict[str, str] = {
    "Customs/Documentation": "CUSTOMS",
    "Delivery & Logistics Operations": "LOGISTICS_OPS",
    "Billing & Accounts": "BILLING",
    "Returns & Refunds": "RETURNS_REFUNDS",
    "Warranty & Claims": "WARRANTY_CLAIMS",
    "Customer Relations": "CUSTOMER_RELATIONS",
    "Account Security & Fraud Prevention": "ACCOUNT_SECURITY",
    "Compliance & Legal Affairs": "COMPLIANCE",
    "Safety & Risk Management": "SAFETY",
    "Management Escalations": "MGMT_ESCALATIONS",
}


def code_for(name: str, *, limit: int = 32) -> str:
    """A reviewable code from a human name."""
    if name in CODE_OVERRIDES:
        return CODE_OVERRIDES[name]

    text = name.upper()
    text = re.sub(r"\(([^)]*)\)", r" \1 ", text)     # keep "(COD)" as COD
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    text = re.sub(r"_+", "_", text)

    if len(text) <= limit:
        return text
    # Drop the least informative words rather than truncating mid-word, which
    # produces codes nobody can read back to a name.
    filler = {"AND", "OR", "THE", "OF", "FOR", "TO", "A", "AN", "ON", "IN"}
    parts = [p for p in text.split("_") if p not in filler]
    while len("_".join(parts)) > limit and len(parts) > 2:
        parts.pop()
    return "_".join(parts)[:limit].strip("_")


# The two ladders the corpus and the backend already agree on, name for name.
# Carried across rather than regenerated so the ranks -- which the mandatory
# escalation floor compares -- keep their meaning.
ESCALATION_BY_NAME = {
    "No Escalation": "NONE",
    "Supervisor Review": "SUPERVISOR",
    "Department Manager": "DEPT_MANAGER",
    "Specialist Team": "SPECIALIST",
    "Compliance Review": "COMPLIANCE_REVIEW",
    "Critical Management Escalation": "CRITICAL_MGMT",
}

URGENCY_BY_NAME = {
    "Critical": "CRITICAL",
    "High": "HIGH",
    "Medium": "MEDIUM",
    "Low": "LOW",
}


class Mapping:
    """Every corpus id and the code it became."""

    def __init__(self) -> None:
        self.categories: dict[str, str] = {}
        self.subcategories: dict[str, str] = {}
        self.departments: dict[str, str] = {}
        self.subcategory_parent: dict[str, str] = {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "categories": self.categories,
            "subcategories": self.subcategories,
            "departments": self.departments,
            "subcategory_parent": self.subcategory_parent,
        }


def build_mapping() -> Mapping:
    taxonomy = load(CONFIG / "complaint_taxonomy.json")
    organisation = load(CONFIG / "organization_profile.json")

    mapping = Mapping()
    for row in taxonomy["categories"]:
        mapping.categories[row["category_id"]] = code_for(row["category_name"])
    for row in organisation["departments"]:
        mapping.departments[row["department_id"]] = code_for(row["name"])
    for row in taxonomy["subcategories"]:
        mapping.subcategories[row["subcategory_id"]] = code_for(row["subcategory_name"])
        mapping.subcategory_parent[row["subcategory_id"]] = row["parent_category_id"]

    for label, table in (
        ("category", mapping.categories),
        ("department", mapping.departments),
        ("subcategory", mapping.subcategories),
    ):
        seen: dict[str, str] = {}
        for source, code in table.items():
            if code in seen:
                raise SystemExit(
                    f"two {label}s collide on code {code}: {seen[code]} and {source}"
                )
            seen[code] = source
    return mapping


# ══════════════════════════════════════════════════════════════
# stage 1 - taxonomy
# ══════════════════════════════════════════════════════════════
def _yaml_scalar(value: Any) -> str:
    """Quote only when YAML would otherwise misread the value."""
    text = str(value)
    if not text:
        return '""'
    if re.fullmatch(r"[A-Za-z0-9 ,.&/'\-()+]+", text) and not text.strip().startswith(
        ("-", "?", ":", "#", "*", "&", "!", "%", "@", "`")
    ):
        return text
    return json.dumps(text)


def stage_taxonomy(mapping: Mapping) -> pathlib.Path:
    taxonomy = load(CONFIG / "complaint_taxonomy.json")
    organisation = load(CONFIG / "organization_profile.json")
    company = organisation["company"]

    out: list[str] = []
    w = out.append

    w("# " + "=" * 72)
    w("# SupportNova - organisation taxonomy")
    w("#")
    w(f"# Fictional organisation: {company['name'].upper()}")
    w(f"# {company['industry']}, operating across Pakistan.")
    w("#")
    w("# GENERATED from dataset/raftarxpress by scripts/convert_raftarxpress.py.")
    w("# Edit the dataset and re-run rather than editing this file: the corpus and")
    w("# the configuration have to agree, and a hand-edit here is how they stop.")
    w("#")
    w("# SRS 1.8 #1 requires a unique fictional organisation per team. SRS Step 14")
    w("# requires categories to be CONFIGURABLE, and SRS 1.8 #5 requires a NEW")
    w("# category to be processable without hard-coded logic - which is why this")
    w("# file is loaded into database tables rather than compiled into Python.")
    w("#")
    w("# Minimums enforced by tests/test_taxonomy_minimums.py:")
    w("#   >= 10 categories, >= 20 subcategories, >= 8 departments")
    w("# " + "=" * 72)
    w("")
    w("organisation:")
    w(f"  name: {_yaml_scalar(company['name'])}")
    w(f"  legal_name: {_yaml_scalar(company['name'])}")
    w(f"  industry: {_yaml_scalar(company['industry'])}")
    w(f"  founded_year: {company.get('founded_year')}")
    w("  regions: [PK]")
    w(f"  branches: [{', '.join(_yaml_scalar(b) for b in company.get('branches', []))}]")
    w(f"  services: [{', '.join(_yaml_scalar(s) for s in company.get('services', []))}]")
    w(
        "  customer_types: ["
        + ", ".join(_yaml_scalar(c) for c in company.get("customer_types", []))
        + "]"
    )
    w('  support_hours: "09:00-21:00 PKT, Mon-Sat"')
    w("")

    # ── departments ──
    w(f"# -- departments ({len(organisation['departments'])}) " + "-" * 40)
    w("departments:")
    # The corpus names each team but gives no mailbox. Customers are shown who
    # is handling their complaint and how to reach that team, so each gets a
    # team address on the fictional organisation's domain, derived from its
    # code so a regenerated file is identical to the last one.
    for row in organisation["departments"]:
        code = mapping.departments[row['department_id']]
        w(f"  - code: {code}")
        w(f"    name: {_yaml_scalar(row['name'])}")
        w(f"    description: {_yaml_scalar(row['function_summary'])}")
        w(f"    email: {code.lower().replace('_', '-')}@raftarxpress.com")
        w(f"    escalation_contact: {_yaml_scalar(row.get('escalation_contact_role'))}")
        w(f"    source_id: {row['department_id']}")
    w("")

    # ── priority, carried across unchanged ──
    w("# -- priority ladder (rank 0 = most severe) " + "-" * 30)
    w("# The corpus and the backend already agree on these, name for name, so they")
    w("# are carried across rather than regenerated: rank is what the SLA matrix")
    w("# and the priority comparison are written against.")
    w("priority_levels:")
    for code, name, rank, description in (
        ("P0", "Critical", 0, "Safety, security or regulatory risk. Immediate action."),
        ("P1", "High", 1, "Major service failure or high-value dispute."),
        ("P2", "Medium", 2, "Standard service issue with customer impact."),
        ("P3", "Low", 3, "Minor issue, information request or cosmetic complaint."),
    ):
        w(f"  - code: {code}")
        w(f"    name: {name}")
        w(f"    rank: {rank}")
        w(f"    description: {_yaml_scalar(description)}")
    w("")

    # ── escalation, carried across unchanged ──
    w("# -- escalation ladder (rank 0 = no escalation) " + "-" * 26)
    w("# SRS Step 37. `rank` is what makes the mandatory escalation FLOOR a")
    w("# comparison instead of a hard-coded if-chain. The corpus names all six")
    w("# levels identically, so the ladder is unchanged by the organisation swap.")
    w("escalation_levels:")
    for code, name, rank, description in (
        ("NONE", "No Escalation", 0, "Handled by the assigned agent."),
        ("SUPERVISOR", "Supervisor Review", 1,
         "Team supervisor reviews before the reply is sent."),
        ("DEPT_MANAGER", "Department Manager", 2,
         "Department manager owns the resolution."),
        ("SPECIALIST", "Specialist Team", 3,
         "Routed to a specialist function (security, safety, technical)."),
        ("COMPLIANCE_REVIEW", "Compliance Review", 4,
         "Legal/regulatory review required before any commitment."),
        ("CRITICAL_MGMT", "Critical Management Escalation", 5,
         "Executive ownership. Regulatory, safety or reputational exposure."),
    ):
        w(f"  - code: {code}")
        w(f"    name: {_yaml_scalar(name)}")
        w(f"    rank: {rank}")
        w(f"    description: {_yaml_scalar(description)}")
    w("")

    # ── categories ──
    w(f"# -- categories ({len(taxonomy['categories'])}) " + "-" * 44)
    w("# `default_department` is the department most of the category's")
    w("# subcategories already route to. It is the fallback the rule engine uses")
    w("# when a complaint classifies to a category but no rule names a")
    w("# destination -- without it such a complaint routes nowhere.")
    w("categories:")
    subs_by_category: dict[str, list[dict[str, Any]]] = {}
    for row in taxonomy["subcategories"]:
        subs_by_category.setdefault(row["parent_category_id"], []).append(row)

    for row in taxonomy["categories"]:
        children = subs_by_category.get(row["category_id"], [])
        counts = collections.Counter(
            mapping.departments[child["default_department_id"]] for child in children
        )
        w(f"  - code: {mapping.categories[row['category_id']]}")
        w(f"    name: {_yaml_scalar(row['category_name'])}")
        if counts:
            w(f"    default_department: {counts.most_common(1)[0][0]}")
        w(f"    description: {_yaml_scalar(row['description'])}")
        w(f"    source_id: {row['category_id']}")
    w("")

    # ── subcategories, grouped by parent ──
    w(f"# -- subcategories ({len(taxonomy['subcategories'])}) " + "-" * 40)
    w("# Each carries the department, urgency and priority the corpus states as its")
    w("# default. The rule matrix may raise any of them; nothing may lower a")
    w("# mandatory escalation.")
    w("subcategories:")
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in taxonomy["subcategories"]:
        by_parent.setdefault(row["parent_category_id"], []).append(row)

    for category in taxonomy["categories"]:
        children = by_parent.get(category["category_id"], [])
        if not children:
            continue
        w(f"  {mapping.categories[category['category_id']]}:")
        for row in children:
            code = mapping.subcategories[row["subcategory_id"]]
            department = mapping.departments[row["default_department_id"]]
            urgency = URGENCY_BY_NAME[row["urgency_default"]]
            w(
                f"    - {{ code: {code}, name: {_yaml_scalar(row['subcategory_name'])}, "
                f"default_department: {department}, default_urgency: {urgency}, "
                f"default_priority: {row['priority_default']}, "
                f"source_id: {row['subcategory_id']} }}"
            )
    w("")

    # ── SLA, from the departments' own stated targets ──
    w("# -- SLA targets " + "-" * 56)
    w("# The defaults are the priority ladder's. The overrides are each")
    w("# department's own stated response and resolution hours, converted to")
    w("# minutes - authored numbers, not invented ones.")
    w("sla_policies:")
    w("  default:")
    for priority, first, resolution in (
        ("P0", 30, 240), ("P1", 120, 1440), ("P2", 480, 4320), ("P3", 1440, 10080)
    ):
        w(
            f"    - {{ priority: {priority}, first_response_mins: {first}, "
            f"resolution_mins: {resolution} }}"
        )
    w("  overrides:")
    # A department's stated SLA applies to the categories its subcategories
    # default to -- but only where it is TIGHTER than the priority default.
    #
    # Warranty & Claims answers in 6 hours and owns Lost Parcel, which defaults
    # to P0. Taking the department target verbatim would give a P0 a six-hour
    # first response: slower than the P0 default, and slower than a P3 handled
    # by Customer Relations. A priority ladder that a department can slow down
    # is not a ladder, so the tighter of the two wins.
    defaults = {
        "P0": (30, 240), "P1": (120, 1440), "P2": (480, 4320), "P3": (1440, 10080)
    }
    seen_pairs: set[tuple[str, str]] = set()
    for row in taxonomy["subcategories"]:
        department = next(
            d for d in organisation["departments"]
            if d["department_id"] == row["default_department_id"]
        )
        category_code = mapping.categories[row["parent_category_id"]]
        priority = row["priority_default"]
        if (category_code, priority) in seen_pairs:
            continue
        seen_pairs.add((category_code, priority))

        default_first, default_resolution = defaults[priority]
        first = min(department["sla_response_hours"] * 60, default_first)
        resolution = min(department["sla_resolution_hours"] * 60, default_resolution)
        if (first, resolution) == (default_first, default_resolution):
            continue        # nothing to override

        w(
            f"    - {{ category: {category_code}, priority: {priority}, "
            f"first_response_mins: {first}, resolution_mins: {resolution} }}"
            f"   # {department['name']}"
        )
    w("  risk_threshold_pct: 75   # flag as AT RISK once this % of the window elapsed")
    w("")

    path = ROOT / "config" / "taxonomy.yaml"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


# ==============================================================
# stage 2 - signals and lexicon
# ==============================================================
#
# The rule engine fires on SIGNALS raised by lexicon terms. The corpus has no
# lexicon -- it states each rule's condition as prose a person can read. So the
# lexicon is derived, and where it is derived FROM matters more than how good
# it is:
#
#   allowed    subcategory names, category descriptions, rule condition prose.
#              All of it authored as configuration.
#   forbidden  the complaint descriptions.
#
# Deriving terms from the complaints would be fitting the rule engine to the
# set it is scored against. Pipeline 2's accuracy would then measure how well
# the extractor memorised the corpus, the benchmark would report a number
# nobody should believe, and the dual-pipeline comparison would become one
# pipeline checking its own homework. This stage never opens the complaints.

# Signals about people rather than about this company. Hazard words and anger
# words do not change when the organisation does, so these are authored once
# and carried across any corpus.
#
# Their weights are deliberately high: a hazard term is worth more evidence
# than a topic term, because being wrong in the cautious direction costs a
# needless escalation and being wrong the other way costs a fire.
CORE_SIGNALS: dict[str, dict[str, Any]] = {
    "safety_lexicon_hit": {
        "description": (
            "Physical hazard indicators. Forces SAFETY routing and P0 regardless "
            "of tone - the Sentiment-Urgency trap (SRS 1.8 #6) turns on hazard "
            "being detectable from the words alone."
        ),
        "weight": 3.0,
        "terms": [
            "burning smell", "smells like burning", "smell of burning",
            "caught fire", "catching fire", "on fire", "fire hazard",
            "smoke", "smoking", "sparks", "sparking", "exploded", "explosion",
            "overheating", "overheated", "melted", "melting",
            "chemical leak", "chemical spill", "acid leak", "toxic fumes",
            "leaking liquid", "gas leak", "battery fire", "lithium battery",
            "hazardous", "hazmat", "biohazard", "radioactive",
            "dangerous goods", "flammable", "corrosive",
        ],
    },
    "injury_mention": {
        "description": (
            "Personal injury or property damage. Compounds with a hazard signal: "
            "a danger that has already hurt somebody is a different complaint "
            "from one that has not."
        ),
        "weight": 3.0,
        "terms": [
            "injured", "injury", "burnt my", "burned my", "burn on my",
            "hospital", "ambulance", "paramedic", "electric shock",
            "shocked me", "cut my", "bleeding", "hurt my", "went to a&e",
            "emergency room", "damaged my house", "damaged my property",
            "caught my hand", "broke my",
        ],
    },
    "emotional_intensity": {
        "description": (
            "How upset the writer sounds. ANALYTICS ONLY: recorded and shown, "
            "and structurally unable to reach the rule engine. SRS 1.8 #6 - a "
            "furious complaint about a late parcel must not outrank a calm one "
            "about a fire."
        ),
        "weight": 1.0,
        "analytics_only": True,
        "terms": [
            "furious", "outraged", "disgusted", "appalled", "livid",
            "unacceptable", "disgraceful", "shambles", "pathetic",
            "worst service", "never again", "fed up", "sick of",
            "ridiculous", "insulting", "how dare", "scam", "fraudsters",
            "will sue", "legal action", "social media", "trustpilot",
            "absolutely fuming",
        ],
    },
}


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "causing", "due",
    "during", "for", "from", "has", "have", "in", "into", "is", "it", "its",
    "no", "not", "of", "on", "or", "over", "than", "that", "the", "their",
    "this", "to", "under", "until", "up", "was", "were", "with", "within",
    "without", "after", "before", "any", "all", "more", "less", "per", "via",
    "when", "where", "which", "while", "who", "customer", "consignment",
    "parcel", "shipment", "merchant", "client", "account", "delivery", "hub",
}

# A phrase appearing across more subcategories than this says nothing about
# which one a complaint belongs to, so it is not worth a signal.
MAX_SUBCATEGORY_SPREAD = 2

# A phrase appearing in more rules than this is not evidence of any one of
# them. Two, not one, so a scenario genuinely described twice still qualifies.
MAX_RULE_SPREAD = 2

# Evidence is a severity discriminator, not a topic: a handful of rare phrases
# does the job, and a long list only widens what it fires on.
MAX_EVIDENCE_TERMS = 8
MAX_TERMS_PER_SIGNAL = 14
MIN_TERM_CHARS = 4


# Clause boundaries. An n-gram that spans one joins two separate ideas --
# "drugs temperature-sensitive" comes from "life-saving drugs or
# temperature-sensitive goods", and matches neither.
_CLAUSE = re.compile(
    r"[,;:/()]|\s+(?:and|or|with|without|but|including|causing|due to|"
    r"resulting in|leading to)\s+",
    re.IGNORECASE,
)

# Words that describe a rule rather than a complaint. A customer writes "my
# parcel is late", not "transit delay exceeding standard threshold".
RULE_JARGON = {
    "standard", "exceeding", "threshold", "quota", "maximum", "minimum",
    "repeated", "subsequently", "prior", "alleges", "identifies", "reports",
    "requires", "involving", "containing", "regarding", "case", "cases",
    "level", "tier", "instance", "scenario", "condition", "conditions",
}


def _clauses(text: str) -> list[list[str]]:
    """The text as word lists, split where one idea ends and another begins."""
    clauses: list[list[str]] = []
    for piece in _CLAUSE.split(text or ""):
        words = [w.strip("-") for w in re.findall(r"[a-z][a-z-]+", (piece or "").lower())]
        words = [w for w in words if len(w) >= 3]
        if words:
            clauses.append(words)
    return clauses


def _phrases(text: str) -> set[str]:
    """
    Unigrams and bigrams a customer might plausibly write.

    No trigrams. Across 105 authored conditions every trigram was a fragment of
    the author's own sentence, and a lexicon full of those matches nothing
    while looking thorough.
    """
    found: set[str] = set()
    for words in _clauses(text):
        for word in words:
            if word not in STOPWORDS and word not in RULE_JARGON and len(word) >= MIN_TERM_CHARS:
                found.add(word)
        for index in range(len(words) - 1):
            first, second = words[index], words[index + 1]
            if first in STOPWORDS or second in STOPWORDS:
                continue
            if first in RULE_JARGON and second in RULE_JARGON:
                continue
            found.add(f"{first} {second}")
    return found


def _pick(
    candidates: list[str],
    spread: collections.Counter | None = None,
    limit: int = MAX_TERMS_PER_SIGNAL,
) -> list[str]:
    """
    Most distinctive first, and among equals the shortest.

    Short beats long here, which is the opposite of the intuition. "perishable"
    matches a customer complaining about spoiled food; "perishable contents
    transit" matches the rule author. Bigrams still earn their place when they
    are the distinctive unit -- "medical supplies", "bank overdraft" -- so both
    lengths compete on distinctiveness and length only breaks the tie.
    """
    spread = spread if spread is not None else collections.Counter()
    ordered = sorted(
        candidates,
        key=lambda p: (spread.get(p, 1), len(p.split()), len(p), p),
    )

    picked: list[str] = []
    for phrase in ordered:
        if len(picked) >= limit:
            break
        # A bigram whose words are both already picked adds a second chance to
        # match the same sentence and nothing else.
        parts = phrase.split()
        if len(parts) == 2 and all(part in picked for part in parts):
            continue
        picked.append(phrase)
    return picked


def _signal_name(code: str) -> str:
    return f"{code.lower()}_terms"


def _rule_signal(rule_id: str) -> str:
    return f"{rule_id.lower().replace('-', '_')}_evidence"


AUTHORED = ROOT / "config" / "authored_lexicon.yaml"


def load_authored() -> dict[str, Any]:
    """
    The hand-written lexicon, or nothing if it has been removed.

    Kept in its own file rather than inside this script because it is content,
    not code: the person tuning it is reading the taxonomy, not the converter.
    """
    if not AUTHORED.exists():
        return {"cross_cutting": {}, "topics": {}}

    import yaml

    data = yaml.safe_load(AUTHORED.read_text(encoding="utf-8")) or {}
    return {
        "cross_cutting": data.get("cross_cutting") or {},
        "topics": data.get("topics") or {},
    }


def _term_entries(terms: list[Any]) -> list[dict[str, str]]:
    """Normalise both shapes: a bare string, or a {t, m} mapping."""
    entries: list[dict[str, str]] = []
    for term in terms:
        if isinstance(term, dict):
            text = str(term.get("t", "")).strip()
            kind = str(term.get("m", "")).strip().upper()
        else:
            text = str(term).strip()
            kind = ""
        if not text:
            continue
        if kind not in {"PHRASE", "REGEX", "WORD"}:
            kind = "PHRASE" if (" " in text or "-" in text) else "WORD"
        entries.append({"t": text, "m": kind})
    return entries


def build_lexicon(mapping: Mapping) -> dict[str, dict[str, Any]]:
    """
    One signal per subcategory, plus a discriminator per rule.

    Terms are scored by how concentrated they are: a phrase in the conditions
    of a single subcategory identifies that subcategory, a phrase in fifteen
    of them identifies nothing.
    """
    taxonomy = load(CONFIG / "complaint_taxonomy.json")
    rules = load(CONFIG / "complaint_resolution_rules.json")["rule_matrix"]

    conditions_by_sub: dict[str, list[str]] = collections.defaultdict(list)
    for rule in rules:
        conditions_by_sub[rule["subcategory_id"]].append(rule["conditions"])

    names = {
        row["subcategory_id"]: row["subcategory_name"]
        for row in taxonomy["subcategories"]
    }

    spread: collections.Counter = collections.Counter()
    phrases_by_sub: dict[str, set[str]] = {}
    for sub_id, name in names.items():
        phrases_by_sub[sub_id] = _phrases(
            " ".join([name, *conditions_by_sub.get(sub_id, [])])
        )
        for phrase in phrases_by_sub[sub_id]:
            spread[phrase] += 1

    lexicon: dict[str, dict[str, Any]] = {}

    for sub_id, name in names.items():
        code = mapping.subcategories[sub_id]
        distinctive = [
            p for p in phrases_by_sub[sub_id] if spread[p] <= MAX_SUBCATEGORY_SPREAD
        ]
        terms = _pick(distinctive, spread, MAX_TERMS_PER_SIGNAL - 1)
        if len(name) >= MIN_TERM_CHARS and name.lower() not in terms:
            terms.insert(0, name.lower())

        lexicon[_signal_name(code)] = {
            "description": f"{name}. Topic terms, generated from the rule conditions.",
            "weight": 1.5,
            "terms": terms,
            "source_id": sub_id,
        }

    # How many rules, anywhere in the matrix, each phrase appears in. A phrase
    # unique among its three siblings can still be one of the commonest words
    # in the corpus -- and as evidence it then fires on everything.
    rule_spread: collections.Counter = collections.Counter()
    for rule in rules:
        for phrase in _phrases(rule["conditions"]):
            rule_spread[phrase] += 1

    # Rules inside one subcategory differ by severity, not topic. Each needs its
    # own discriminator or the engine cannot tell "delay under 24 hours" from
    # "delay containing life-saving drugs" -- and the second is a P0.
    for rule in rules:
        sub_id = rule["subcategory_id"]
        siblings = [
            r["conditions"]
            for r in rules
            if r["subcategory_id"] == sub_id and r["rule_id"] != rule["rule_id"]
        ]
        shared: set[str] = set()
        for condition in siblings:
            shared |= _phrases(condition)

        # Globally rare AND unlike its siblings. Either test alone lets through
        # a term that fires on half the corpus.
        unique = {
            phrase
            for phrase in _phrases(rule["conditions"]) - shared
            if rule_spread[phrase] <= MAX_RULE_SPREAD
        }
        terms = _pick(list(unique), rule_spread, MAX_EVIDENCE_TERMS)
        if not terms:
            continue

        lexicon[_rule_signal(rule["rule_id"])] = {
            "description": (
                f"Separates {rule['rule_id']} from the other rules in "
                f"{mapping.subcategories[sub_id]}: {rule['conditions'][:88]}"
            ),
            "weight": 2.0,
            "terms": terms,
            "source_id": rule["rule_id"],
        }

    authored = load_authored()

    # Topic terms JOIN the generated signal rather than replacing it. The
    # generated terms discriminate between rules inside a subcategory; the
    # authored ones carry the topic itself. Dropping either loses something.
    for code, terms in authored["topics"].items():
        name = _signal_name(code)
        spec = lexicon.setdefault(
            name,
            {
                "description": f"{code}. Authored topic terms.",
                "weight": 1.5,
                "terms": [],
                "source_id": "authored",
            },
        )
        # Authored terms REPLACE the generated ones rather than joining them.
        #
        # Joining looked generous and was the opposite. A plain "my parcel is
        # late" complaint raised fourteen signals, among them "rude rider
        # behaviour" and "COD remittance", every one of them from a generated
        # term that happened to appear in the subcategory's rule prose. The
        # correct topic was in the list and lost on precedence.
        #
        # The generated terms still earn their place as the per-rule severity
        # discriminators below; they are simply not what a topic is.
        spec["terms"] = _term_entries(terms)
        spec["description"] = f"{code}. Authored topic terms."
        spec["source_id"] = "authored"

    for name, spec in authored["cross_cutting"].items():
        lexicon[name] = {
            "description": " ".join(str(spec.get("description", "")).split()),
            "weight": spec.get("weight", 2.0),
            "terms": _term_entries(spec.get("terms") or []),
            "source_id": "authored",
        }

    # Authored last so a generated signal can never shadow one of these: a
    # subcategory called "Safety" must not overwrite the hazard vocabulary the
    # Sentiment-Urgency trap depends on.
    for name, spec in CORE_SIGNALS.items():
        lexicon[name] = {**spec, "terms": _term_entries(spec["terms"]),
                         "source_id": "authored"}

    return lexicon


def stage_signals(mapping: Mapping) -> pathlib.Path:
    lexicon = build_lexicon(mapping)
    organisation = load(CONFIG / "organization_profile.json")

    # How this company's references are written. The old ZN- order pattern
    # matches nothing in this corpus, and an extractor that finds no reference
    # makes every rule keyed on one vacuous.
    # These KEYS are the engine's vocabulary, not ours. `signals.py` asks
    # `entities.has("ORDER_ID")` to set `has_order_ref`, and the first version
    # of this called the same pattern TRACKING_ID -- so has_order_ref was false
    # for every complaint in the corpus and missing_order_reference was true for
    # every one, which is the Missing Information Challenge exactly inverted.
    entity_patterns = {
        "ORDER_ID": r"\b(?:CN|FWD)-?\d{6,12}\b",
        "TRANSACTION_ID": r"\bMER-\d{3,5}-[A-Z]{2,8}\b",
        "INVOICE_ID": r"\bINV-?\d{5,10}\b",
        "COMPLAINT_REF": r"\bCMP-?\d{4,8}\b",
        "AMOUNT": r"(?:pkr|rs\.?|inr|usd|[$])\s?\d[\d,]*(?:\.\d{1,2})?",
        "DATE_ISO": r"\b\d{4}-\d{2}-\d{2}\b",
        "EMAIL": r"[\w.+-]+@[\w-]+\.[\w.]{2,}",
        "PHONE": r"\+?\d[\d\s-]{8,14}\d",
    }

    backup = ROOT / "config" / "signals.zenithra.yaml.bak"
    source = backup if backup.exists() else ROOT / "config" / "signals.yaml"
    carried = source.read_text(encoding="utf-8")

    def section(name: str) -> str:
        """Lift a top-level block out of the previous signals file, verbatim."""
        match = re.search(rf"^{name}:.*?(?=^\w|\Z)", carried, re.S | re.M)
        return match.group(0).rstrip() if match else f"{name}: []"

    out: list[str] = []
    w = out.append
    w("# " + "=" * 72)
    w("# SupportNova - signals, lexicon and patterns")
    w("#")
    w(f"# GENERATED for {organisation['company']['name']} by")
    w("# scripts/convert_raftarxpress.py. Edit the dataset and re-run.")
    w("#")
    w("# The lexicon is DERIVED, and only from authored configuration: the")
    w("# subcategory names and the rule condition prose. It is never derived from")
    w("# the complaint corpus. Fitting the rule engine to the complaints it is")
    w("# scored against would make Pipeline 2's accuracy a measure of how well the")
    w("# extractor memorised the test set.")
    w("#")
    w("# Generated terms are a starting point, not a finished lexicon. Tune them")
    w("# against the benchmark's per-field accuracy, or live through the admin API")
    w("# at /api/admin/lexicon, which needs no redeploy.")
    w("# " + "=" * 72)
    w("")
    w("lexicon:")
    for name, spec in lexicon.items():
        w(f"  {name}:")
        w(f"    description: {_yaml_scalar(spec['description'])}")
        w(f"    weight: {spec['weight']}")
        w(f"    source_id: {spec['source_id']}")
        if spec.get("analytics_only"):
            # The seeder collects these into app_config.analytics_only_signals,
            # and a rule-engine test fails the build if any rule names one.
            w("    analytics_only: true")
        w("    terms:")
        for entry in _term_entries(spec["terms"]):
            w(f"      - {{ t: {_yaml_scalar(entry['t'])}, m: {entry['m']} }}")
        w("")

    w("# -- injection patterns " + "-" * 50)
    w("# Carried across unchanged. These describe how a support system is")
    w("# attacked, which does not vary with the company behind it.")
    w(section("injection_patterns"))
    w("")
    w("# -- promise patterns " + "-" * 52)
    w("# Also unchanged: a promise of a refund is the same commitment whoever")
    w("# makes it, and requires_eligibility still names a real EligibilityType.")
    w(section("promise_patterns"))
    w("")
    w("# -- entity patterns " + "-" * 53)
    w("# RaftarXpress references: CN- tracking, FWD- freight, MER- merchant.")
    w("entity_patterns:")
    for name, pattern in entity_patterns.items():
        w(f"  {name}: {json.dumps(pattern)}")
    w("")

    path = ROOT / "config" / "signals.yaml"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


# ==============================================================
# stage 3 - the rule matrix
# ==============================================================
#
# One authored rule carries everything at once: category, subcategory,
# department, urgency, priority, escalation, required and prohibited actions,
# and three eligibility verdicts. The engine splits those across three files,
# and the split is not cosmetic.
#
# A mandatory escalation becomes its OWN rule at a higher precedence band. If
# the floor lived on the classification rule, then editing that rule -- to fix
# a department, say -- would be able to move the floor as a side effect. The
# floor may be raised and never lowered, and keeping it in a separate rule is
# what makes that reviewable: escalation_rules/mandatory.yaml is the only file
# that can set one.
#
# Precedence bands
#   100-115  mandatory escalation, by severity
#    60-75   classification, by severity, so the worse rule wins its subcategory
#    60      eligibility
#     5      catch-all -> routes somewhere without suppressing `unmatched`

# Authored rules that bridge the hazard signals to an outcome. Every generated
# rule keys on a subcategory signal taken from the rule matrix, so without
# these the hazard vocabulary is raised and then ignored -- which is the
# Sentiment-Urgency trap failing silently.
#
# Precedence 130+ puts them above every generated rule, including the
# generated escalations at 100-115. A burning parcel is not a delivery
# complaint that happens to mention fire, and precedence is what says so.
#
# `safety_subcategory` and `safety_department` are looked up rather than
# hardcoded, so the bridge survives the taxonomy being re-authored.
# Cross-cutting escalations. None sets a category: a legal threat about a
# refund is still a refund complaint, and overwriting the category would lose
# what the customer is actually asking for. They raise the floor, the urgency
# and the owning department, and leave classification to the topic rule.
#
# `department` here is a code that must exist in the taxonomy; the converter
# checks each one and refuses to emit a rule naming a department that does not.
# Wherever a customer asks for money back. Not a classification -- the
# complaint is still about whatever went wrong -- but a standing verdict that
# no refund is approved without a person checking the conditions first.
REFUND_STANCE = {
    "ref": "ELG-STANCE-0001",
    "name": "A refund is never approved at the desk",
    "precedence": 90,
    "topics": ("REFUND_NOT_PROCESSED", "REFUND_DELAY", "RTO_PROCESSING_DELAY"),
    "rationale": (
        "SRS 1.8 #9. The rule engine may derive REQUIRES_VERIFICATION; turning "
        "that into a yes is a person's act, after they have checked the "
        "conditions. Wrongly withholding a refund is recoverable by a human; "
        "wrongly promising one is not."
    ),
    "eligibility": [("REFUND", "REQUIRES_VERIFICATION", True)],
    "prohibited_actions": [
        "Confirm a refund before eligibility is verified",
        "Give the customer a date for a refund that has not been approved",
    ],
}

CROSS_CUTTING_BRIDGE = [
    {
        "ref": "LEG-0001",
        "name": "Legal or regulatory exposure raised by the customer",
        "precedence": 120,
        "when": ["      signal: legal_threat"],
        "department": "COMPLIANCE",
        "urgency": "HIGH",
        "priority": "P1",
        "escalation": "COMPLIANCE_REVIEW",
        "rationale": (
            "Once a customer has mentioned a lawyer, a court or a regulator, a "
            "reply that commits the company to anything is a liability. "
            "Compliance owns it and the floor is raised before any promise can "
            "be drafted."
        ),
        "required_actions": [
            "Record the exact wording of the legal reference",
            "Route to Compliance and Legal Affairs before replying",
        ],
        "prohibited_actions": [
            "Admit liability or fault",
            "Offer any settlement, refund or compensation without legal sign-off",
        ],
    },
    {
        "ref": "REG-0001",
        "name": "A regulator or enforcement agency is already involved",
        "precedence": 125,
        "when": ["      signal: regulatory_body"],
        "department": "COMPLIANCE",
        "urgency": "CRITICAL",
        "priority": "P0",
        "escalation": "COMPLIANCE_REVIEW",
        "rationale": (
            "A seizure or an agency notice is not the customer being angry: a "
            "third party with statutory power is already involved, and the "
            "company's answer is on a record it does not control."
        ),
        "required_actions": [
            "Record the agency and any reference number quoted",
            "Notify Compliance and Legal Affairs immediately",
        ],
        "prohibited_actions": [
            "Contact the agency on the customer's behalf without legal sign-off",
            "Promise a release date for goods held by a third party",
        ],
    },
    {
        "ref": "URG-0001",
        "name": "Time-critical contents make the delay dangerous",
        "precedence": 128,
        "when": ["      signal: time_critical_contents"],
        "department": "MGMT_ESCALATIONS",
        "urgency": "CRITICAL",
        "priority": "P0",
        "escalation": "SPECIALIST",
        "rationale": (
            "What is inside changes what the delay costs. A late parcel is an "
            "inconvenience; late insulin is not, and the difference is legible "
            "in the complaint text without any judgement about tone."
        ),
        "required_actions": [
            "Locate the consignment and confirm its current hub immediately",
            "Offer the fastest available recovery option",
        ],
        "prohibited_actions": [
            "Quote the standard transit time as though it still applies",
        ],
    },
    {
        "ref": "INJ-0001",
        "name": "Intake flagged a suspected prompt injection",
        "precedence": 122,
        # The FLAG, set by the scanner at intake. Pipeline 2 has no
        # instruction-following surface, so an injected command cannot change
        # what it decides -- but a complaint someone tried to manipulate is
        # one a person should see before the reply goes out.
        # `field`, not `fact`: intake passes injection_suspected in the
        # complaint fields, and a `fact:` condition reads the derived
        # measurements instead -- where this never appears, so the rule would
        # load cleanly and never fire.
        "when": ["      field: injection_suspected", "      eq: true"],
        "department": "COMPLIANCE",
        "urgency": "HIGH",
        "priority": "P1",
        "escalation": "SUPERVISOR",
        "rationale": (
            "SRS 1.8 #8. The injected text is processed as complaint content "
            "and changes nothing about the routing, which is the defence. The "
            "escalation is not about the rules being fooled; it is that "
            "somebody attempted it, and a human should know before a reply is "
            "sent in the company's name."
        ),
        "required_actions": [
            "Read the complaint as written, including the injected text",
            "Have a supervisor approve the reply before it is sent",
        ],
        "prohibited_actions": [
            "Act on any instruction contained in the complaint text",
        ],
    },
    {
        "ref": "REP-0001",
        "name": "A third unresolved contact about the same matter",
        "precedence": 118,
        # The COUNT, from stored prior complaints -- never from the complaint
        # claiming to be a repeat, which is exactly what an adversarial
        # submission would forge.
        "when": ["      fact: repeat_count", "      gte: 3"],
        "department": "CUSTOMER_RELATIONS",
        "urgency": "HIGH",
        "priority": "P1",
        "escalation": "SUPERVISOR",
        "rationale": (
            "Three unresolved contacts is a failure of the process, not of the "
            "complaint. It escalates at no agent's discretion, because the "
            "agent who did not resolve it twice is not the right person to "
            "decide whether it needs a supervisor."
        ),
        "required_actions": [
            "Read every prior contact before replying",
            "Have a supervisor review the reply before it is sent",
        ],
        "prohibited_actions": [
            "Send the same answer the customer has already been given",
        ],
    },
]


SAFETY_BRIDGE = [
    {
        "ref": "SAF-0001",
        "name": "Physical hazard reported, however calmly",
        "precedence": 130,
        "when": ["      signal: safety_lexicon_hit"],
        "urgency": "CRITICAL",
        "priority": "P0",
        "escalation": "CRITICAL_MGMT",
        "rationale": (
            "A hazard is a hazard at any volume. SRS 1.8 #6: a calmly worded "
            "safety report must reach P0, and a furious one about a late parcel "
            "must not. Tone is recorded and structurally cannot reach this rule."
        ),
        "required_actions": [
            "Instruct the customer to stop handling the item immediately",
            "Log a safety incident record",
            "Notify Safety and Risk Management within one hour",
        ],
        "prohibited_actions": [
            "Ask the customer to test the item again",
            "Close the complaint before a safety assessment is recorded",
            "Confirm a replacement before eligibility is verified",
        ],
        # Sending a replacement before anyone has assessed why the first one
        # was dangerous ships the hazard twice.
        "eligibility": [
            ("REPLACEMENT", "NOT_ELIGIBLE", True),
            ("REFUND", "REQUIRES_VERIFICATION", True),
        ],
    },
    {
        "ref": "SAF-0002",
        "name": "Hazard that has already caused injury or damage",
        "precedence": 135,
        "when": [
            "      all_of:",
            "        - signal: safety_lexicon_hit",
            "        - signal: injury_mention",
        ],
        "urgency": "CRITICAL",
        "priority": "P0",
        "escalation": "CRITICAL_MGMT",
        "rationale": (
            "A danger that has already hurt somebody is not the same complaint "
            "as one that has not. Ranked above SAF-0001 so the more serious "
            "reading wins when both match."
        ),
        "required_actions": [
            "Record the injury or damage reported, verbatim",
            "Escalate to Safety and Risk Management immediately",
            "Preserve the item and all packaging as evidence",
        ],
        "prohibited_actions": [
            "Offer any settlement before a safety assessment is recorded",
            "Ask the customer to return the item by ordinary courier",
            "Confirm a replacement before eligibility is verified",
        ],
        "eligibility": [
            ("REPLACEMENT", "NOT_ELIGIBLE", True),
            ("COMPENSATION", "REQUIRES_VERIFICATION", True),
        ],
    },
]


ESCALATION_RANK = {
    "NONE": 0, "SUPERVISOR": 1, "DEPT_MANAGER": 2,
    "SPECIALIST": 3, "COMPLIANCE_REVIEW": 4, "CRITICAL_MGMT": 5,
}

ELIGIBILITY_FIELDS = (
    ("refund_eligible", "REFUND"),
    ("replacement_eligible", "REPLACEMENT"),
    ("compensation_permitted", "COMPENSATION"),
)

# The corpus states eligibility as Yes / No / Conditional. Only an explicit Yes
# authorises a promise; Conditional means a person has to check something first,
# which is REQUIRES_VERIFICATION and not a basis for telling a customer yes.
ELIGIBILITY_OUTCOME = {
    "yes": "ELIGIBLE",
    "no": "NOT_ELIGIBLE",
    "conditional": "REQUIRES_VERIFICATION",
}


def _when(
    mapping: Mapping,
    rule: dict[str, Any],
    lexicon: dict[str, Any],
    *,
    is_baseline: bool = False,
) -> list[str]:
    """
    The condition tree, as YAML lines.

    **Evidence escalates; it does not gate.** Every subcategory has one
    baseline rule -- its least severe reading -- and that one fires on the
    topic alone. The rest require the topic AND their own discriminator.

    Requiring evidence on all of them was worse than useless: a complaint
    whose topic matched but whose severity phrase did not matched nothing at
    all, went to `unmatched`, and scored as wrong on every field. Tightening
    the evidence then made accuracy fall, which reads as "being more precise
    hurt" and is really "the routine case stopped having a rule".
    """
    sub_code = mapping.subcategories[rule["subcategory_id"]]
    topic = _signal_name(sub_code)
    evidence = _rule_signal(rule["rule_id"])

    lines = ["    when:"]
    if is_baseline or evidence not in lexicon:
        lines.append(f"      signal: {topic}")
    else:
        lines.append("      all_of:")
        lines.append(f"        - signal: {topic}")
        lines.append(f"        - signal: {evidence}")
    return lines


def _actions(label: str, items: list[str]) -> list[str]:
    if not items:
        return []
    lines = [f"      {label}:"]
    lines += [f"        - {_yaml_scalar(item)}" for item in items]
    return lines


def stage_rules(mapping: Mapping) -> pathlib.Path:
    rules = load(CONFIG / "complaint_resolution_rules.json")["rule_matrix"]
    lexicon = build_lexicon(mapping)
    documents = load(DATASET / "documents" / "source" / "knowledge_base_documents.json")
    doc_refs = {d["document_id"]: d["document_id"] for d in documents["documents"]}

    # The least severe rule in each subcategory is its baseline reading: what
    # the complaint is, absent any evidence that it is worse than that.
    baseline_of: dict[str, str] = {}
    for rule in rules:
        sub_id = rule["subcategory_id"]
        rank = ESCALATION_RANK[ESCALATION_BY_NAME[rule["escalation_level"]]]
        current = baseline_of.get(sub_id)
        if current is None or rank < ESCALATION_RANK[
            ESCALATION_BY_NAME[
                next(r["escalation_level"] for r in rules if r["rule_id"] == current)
            ]
        ]:
            baseline_of[sub_id] = rule["rule_id"]

    classification: list[str] = []
    escalation: list[str] = []
    eligibility: list[str] = []
    resolution: list[str] = []

    for rule in rules:
        source_id = rule["rule_id"]
        sub_code = mapping.subcategories[rule["subcategory_id"]]
        category_code = mapping.categories[rule["category_id"]]
        department = mapping.departments[rule["department_id"]]
        support = rule.get("supporting_department_id")
        escalation_code = ESCALATION_BY_NAME[rule["escalation_level"]]
        rank = ESCALATION_RANK[escalation_code]
        reference = rule.get("policy_reference") or {}
        doc_ref = doc_refs.get(reference.get("document_id"))

        # -- classification --
        w = classification.append
        w("")
        w(f"  - rule_ref: {source_id}")
        w(f"    name: {_yaml_scalar(rule['conditions'][:110])}")
        w("    rule_type: CLASSIFICATION")
        w(f"    precedence: {60 + rank * 3}")
        w(f"    rationale: {_yaml_scalar(rule.get('priority_logic_note') or rule['conditions'])}")
        classification.extend(
            _when(
                mapping, rule, lexicon,
                is_baseline=baseline_of.get(rule["subcategory_id"]) == source_id,
            )
        )
        w("    then:")
        w(f"      category: {category_code}")
        w(f"      subcategory: {sub_code}")
        w(f"      department: {department}")
        if support:
            w(f"      support_department: {mapping.departments[support]}")
        w(f"      urgency: {URGENCY_BY_NAME[rule['urgency']]}")
        w(f"      priority: {rule['priority']}")
        if rule.get("follow_up_required"):
            w("      follow_up_required: true")
        if doc_ref:
            w("      policy_refs:")
            w(
                f"        - {{ doc_ref: {doc_ref}, "
                # Always quoted. A ref of 1 emitted bare is read back by YAML
                    # as the integer 1, and every consumer calling .strip()
                    # on it raises -- which crashed 466 of 500 complaints.
                    f"section_ref: {json.dumps(section_ref(reference.get('section_id')))} }}"
            )

        # -- obligations, as their own rule --
        #
        # Separate from classification so a reviewer has one file to read to
        # see what a case requires and forbids. The engine aggregates
        # required_actions across every rule that fired, so both rules
        # contributing to the same complaint is the intended shape.
        if rule.get("required_actions") or rule.get("prohibited_actions"):
            w = resolution.append
            w("")
            w(f"  - rule_ref: RES-{source_id.split('-')[1]}")
            w(f"    name: {_yaml_scalar('Obligations for ' + rule['conditions'][:92])}")
            w("    rule_type: RESOLUTION")
            w("    precedence: 60")
            w(
                "    rationale: "
                + _yaml_scalar(
                    f"{source_id} states what this case requires and forbids. A "
                    "required step stays outstanding until a person confirms it."
                )
            )
            resolution.extend(_when(mapping, rule, lexicon))
            w("    then:")
            resolution.extend(
                _actions("required_actions", rule.get("required_actions") or [])
            )
            resolution.extend(
                _actions("prohibited_actions", rule.get("prohibited_actions") or [])
            )
            if doc_ref:
                w("      policy_refs:")
                w(
                    f"        - {{ doc_ref: {doc_ref}, "
                    # Always quoted. A ref of 1 emitted bare is read back by YAML
                    # as the integer 1, and every consumer calling .strip()
                    # on it raises -- which crashed 466 of 500 complaints.
                    f"section_ref: {json.dumps(section_ref(reference.get('section_id')))} }}"
                )

        # -- mandatory escalation, as its own rule --
        if rule.get("is_mandatory_escalation") and escalation_code != "NONE":
            w = escalation.append
            w("")
            w(f"  - rule_ref: ESC-{source_id.split('-')[1]}")
            w(f"    name: {_yaml_scalar(rule['conditions'][:110])}")
            w("    rule_type: ESCALATION")
            w(f"    precedence: {100 + rank * 3}")
            # The loader reads `mandatory_escalation`. Spelling it
            # `is_mandatory_escalation` loads the rule with no floor at all,
            # which is the safety property failing silently.
            w("    mandatory_escalation: true")
            w(
                "    rationale: "
                + _yaml_scalar(
                    f"{source_id} makes this escalation mandatory. The floor may be "
                    f"raised above {escalation_code}, never lowered below it."
                )
            )
            escalation.extend(_when(mapping, rule, lexicon))
            w("    then:")
            w(f"      escalation: {escalation_code}")
            w(f"      department: {department}")
            w(f"      urgency: {URGENCY_BY_NAME[rule['urgency']]}")
            w(f"      priority: {rule['priority']}")
            if doc_ref:
                w("      policy_refs:")
                w(
                    f"        - {{ doc_ref: {doc_ref}, "
                    # Always quoted. A ref of 1 emitted bare is read back by YAML
                    # as the integer 1, and every consumer calling .strip()
                    # on it raises -- which crashed 466 of 500 complaints.
                    f"section_ref: {json.dumps(section_ref(reference.get('section_id')))} }}"
                )

        # -- eligibility --
        verdicts = [
            (kind, ELIGIBILITY_OUTCOME[str(rule.get(field, "No")).strip().lower()])
            for field, kind in ELIGIBILITY_FIELDS
            if str(rule.get(field, "No")).strip().lower() in ELIGIBILITY_OUTCOME
        ]
        # Every verdict, including NOT_ELIGIBLE. "We considered a refund and
        # the answer is no" is information an agent needs and a customer is
        # owed; silence is indistinguishable from nobody having looked.
        stated = verdicts
        # One rule per entitlement: the loader reads `eligibility` from the
        # rule's top level as a single mapping, not a list under `then`.
        number = source_id.split("-")[1]
        for kind, outcome in stated:
            requires_human = outcome == "REQUIRES_VERIFICATION"
            w = eligibility.append
            w("")
            w(f"  - rule_ref: ELG-{number}-{kind[:4]}")
            w(
                f"    name: {_yaml_scalar(kind.title() + ' for ' + rule['conditions'][:80])}"
            )
            w("    rule_type: ELIGIBILITY")
            w("    precedence: 60")
            w(
                "    rationale: "
                + _yaml_scalar(
                    f"{source_id} states what this case entitles the customer to. "
                    "Only an explicit ELIGIBLE authorises a promise."
                )
            )
            eligibility.extend(_when(mapping, rule, lexicon))
            w("    eligibility:")
            w(f"      type: {kind}")
            w(f"      outcome: {outcome}")
            w(f"      requires_human_approval: {str(requires_human).lower()}")
            if doc_ref:
                # A MAPPING, not a bare reference: persist_validation reads
                # policy_ref.get("doc_ref") and .get("section_ref"), so a
                # string here crashes the whole analysis on any complaint the
                # rule fires for.
                w(
                    f"      policy_ref: {{ doc_ref: {doc_ref}, "
                    f"section_ref: {json.dumps(section_ref(reference.get('section_id')))} }}"
                )
            if rule.get("conditions"):
                w("      conditions:")
                w(f"        - {_yaml_scalar(rule['conditions'][:150])}")

    # -- the authored hazard bridge --
    safety_category = next(
        (code for code in mapping.categories.values() if code == "SAFETY"), None
    )
    safety_subcategory = next(
        (
            mapping.subcategories[sub_id]
            for sub_id, parent in mapping.subcategory_parent.items()
            if mapping.categories.get(parent) == "SAFETY"
        ),
        None,
    )
    safety_department = next(
        (code for code in mapping.departments.values() if code == "SAFETY"), None
    )

    if safety_category and safety_subcategory and safety_department:
        for spec in SAFETY_BRIDGE:
            w = classification.append
            w("")
            w(f"  - rule_ref: {spec['ref']}")
            w(f"    name: {_yaml_scalar(spec['name'])}")
            w("    rule_type: CLASSIFICATION")
            w(f"    precedence: {spec['precedence']}")
            w(f"    rationale: {_yaml_scalar(spec['rationale'])}")
            w("    when:")
            classification.extend(spec["when"])
            w("    then:")
            w(f"      category: {safety_category}")
            w(f"      subcategory: {safety_subcategory}")
            w(f"      department: {safety_department}")
            w(f"      urgency: {spec['urgency']}")
            w(f"      priority: {spec['priority']}")
            w("      follow_up_required: true")

            w = escalation.append
            w("")
            w(f"  - rule_ref: ESC-{spec['ref']}")
            w(f"    name: {_yaml_scalar(spec['name'])}")
            w("    rule_type: ESCALATION")
            w(f"    precedence: {spec['precedence'] + 10}")
            w("    mandatory_escalation: true")
            w(f"    rationale: {_yaml_scalar(spec['rationale'])}")
            w("    when:")
            escalation.extend(spec["when"])
            w("    then:")
            w(f"      escalation: {spec['escalation']}")
            w(f"      department: {safety_department}")
            w(f"      urgency: {spec['urgency']}")
            w(f"      priority: {spec['priority']}")

            w = resolution.append
            w("")
            w(f"  - rule_ref: RES-{spec['ref']}")
            w(f"    name: {_yaml_scalar('Obligations for ' + spec['name'])}")
            w("    rule_type: RESOLUTION")
            w(f"    precedence: {spec['precedence']}")
            w(f"    rationale: {_yaml_scalar(spec['rationale'])}")
            w("    when:")
            resolution.extend(spec["when"])
            w("    then:")
            resolution.extend(_actions("required_actions", spec["required_actions"]))
            resolution.extend(_actions("prohibited_actions", spec["prohibited_actions"]))

            for kind, verdict, needs_human in spec.get("eligibility") or []:
                w = eligibility.append
                w("")
                w(f"  - rule_ref: ELG-{spec['ref']}-{kind[:4]}")
                w(f"    name: {_yaml_scalar(kind.title() + ' for ' + spec['name'])}")
                w("    rule_type: ELIGIBILITY")
                w(f"    precedence: {spec['precedence']}")
                w(f"    rationale: {_yaml_scalar(spec['rationale'])}")
                w("    when:")
                eligibility.extend(spec["when"])
                w("    eligibility:")
                w(f"      type: {kind}")
                w(f"      outcome: {verdict}")
                w(f"      requires_human_approval: {str(needs_human).lower()}")
    else:
        raise SystemExit(
            "the taxonomy has no SAFETY category, subcategory or department, so "
            "the hazard bridge cannot be built -- check config/taxonomy.yaml"
        )

    for topic_code in REFUND_STANCE["topics"]:
        if topic_code not in mapping.subcategories.values():
            continue
        signal = _signal_name(topic_code)
        suffix = topic_code.lower()

        for kind, verdict, needs_human in REFUND_STANCE["eligibility"]:
            w = eligibility.append
            w("")
            w(f"  - rule_ref: ELG-STANCE-{suffix[:14]}-{kind[:4]}")
            w(f"    name: {_yaml_scalar(REFUND_STANCE['name'])}")
            w("    rule_type: ELIGIBILITY")
            w(f"    precedence: {REFUND_STANCE['precedence']}")
            w(f"    rationale: {_yaml_scalar(REFUND_STANCE['rationale'])}")
            w("    when:")
            w(f"      signal: {signal}")
            w("    eligibility:")
            w(f"      type: {kind}")
            w(f"      outcome: {verdict}")
            w(f"      requires_human_approval: {str(needs_human).lower()}")

        w = resolution.append
        w("")
        w(f"  - rule_ref: RES-STANCE-{suffix[:18]}")
        w(f"    name: {_yaml_scalar('Obligations for ' + REFUND_STANCE['name'])}")
        w("    rule_type: RESOLUTION")
        w(f"    precedence: {REFUND_STANCE['precedence']}")
        w(f"    rationale: {_yaml_scalar(REFUND_STANCE['rationale'])}")
        w("    when:")
        w(f"      signal: {signal}")
        w("    then:")
        resolution.extend(
            _actions("prohibited_actions", REFUND_STANCE["prohibited_actions"])
        )

    known_departments = set(mapping.departments.values())
    for spec in CROSS_CUTTING_BRIDGE:
        if spec["department"] not in known_departments:
            raise SystemExit(
                f"{spec['ref']} routes to {spec['department']}, which is not a "
                "department in this taxonomy"
            )

        w = escalation.append
        w("")
        w(f"  - rule_ref: {spec['ref']}")
        w(f"    name: {_yaml_scalar(spec['name'])}")
        w("    rule_type: ESCALATION")
        w(f"    precedence: {spec['precedence']}")
        w("    mandatory_escalation: true")
        w(f"    rationale: {_yaml_scalar(spec['rationale'])}")
        w("    when:")
        escalation.extend(spec["when"])
        w("    then:")
        w(f"      escalation: {spec['escalation']}")
        w(f"      department: {spec['department']}")
        w(f"      urgency: {spec['urgency']}")
        w(f"      priority: {spec['priority']}")

        w = resolution.append
        w("")
        w(f"  - rule_ref: RES-{spec['ref']}")
        w(f"    name: {_yaml_scalar('Obligations for ' + spec['name'])}")
        w("    rule_type: RESOLUTION")
        w(f"    precedence: {spec['precedence']}")
        w(f"    rationale: {_yaml_scalar(spec['rationale'])}")
        w("    when:")
        resolution.extend(spec["when"])
        w("    then:")
        resolution.extend(_actions("required_actions", spec["required_actions"]))
        resolution.extend(_actions("prohibited_actions", spec["prohibited_actions"]))

    def render(title: str, ruleset: str, body: list[str], notes: list[str]) -> str:
        head = ["# " + "=" * 72, f"# RaftarXpress - {title}", "#"]
        head += [f"# {line}" for line in notes]
        head += [
            "#",
            "# GENERATED from dataset/raftarxpress by scripts/convert_raftarxpress.py.",
            "# Edit the dataset and re-run. Tune live at /api/admin/rules, which",
            "# refuses a condition naming a signal no lexicon term raises.",
            "# " + "=" * 72,
            "",
            'version: "1.0"',
            f"ruleset: {ruleset}",
            "",
            "rules:",
        ]
        return "\n".join(head + body) + "\n"

    (ROOT / "complaint_rules" / "classification.yaml").write_text(
        render(
            "CLASSIFICATION RULES",
            "classification",
            classification,
            [
                "What a complaint is about, decided without the model. Precedence",
                "rises with severity, so inside one subcategory the worse rule wins:",
                "a delayed parcel carrying life-saving drugs is not a routine delay.",
            ],
        ),
        encoding="utf-8",
    )
    (ROOT / "escalation_rules" / "mandatory.yaml").write_text(
        render(
            "MANDATORY ESCALATION RULES",
            "escalation",
            escalation,
            [
                "The floor. Separate from classification on purpose: if the floor",
                "lived on the classification rule, editing that rule to fix a",
                "department could move the floor as a side effect. This is the only",
                "file that may set is_mandatory_escalation.",
            ],
        ),
        encoding="utf-8",
    )
    (ROOT / "complaint_rules" / "resolution.yaml").write_text(
        render(
            "RESOLUTION RULES",
            "resolution",
            resolution,
            [
                "What each case requires and forbids, straight from the authored",
                "matrix. A required step is stored against the complaint as MISSING",
                "and stays that way until an agent confirms it: whether 'check hub",
                "GPS scan history' actually happened is not readable from any text",
                "the system holds, and a checklist that ticked itself would be",
                "decorative.",
            ],
        ),
        encoding="utf-8",
    )
    (ROOT / "complaint_rules" / "eligibility.yaml").write_text(
        render(
            "ELIGIBILITY RULES",
            "eligibility",
            eligibility,
            [
                "What a case entitles the customer to. The corpus says Yes, No or",
                "Conditional; Conditional becomes REQUIRES_VERIFICATION, because a",
                "condition nobody has checked is not a basis for telling a customer",
                "yes -- and the response guard refuses to promise on it.",
            ],
        ),
        encoding="utf-8",
    )

    # A single catch-all so an unrecognised complaint still reaches a person.
    # It must not suppress `unmatched`: the flag is how a gap in the matrix
    # becomes visible instead of being quietly absorbed.
    (ROOT / "routing_rules" / "departments.yaml").write_text(
        render(
            "ROUTING FALLBACK",
            "routing",
            [
                "",
                "  - rule_ref: RTE-0001",
                "    name: Unrecognised complaint",
                "    rule_type: ROUTING",
                "    precedence: 5",
                "    catch_all: true",
                "    rationale: >-",
                "      Nothing in the matrix matched. The complaint still needs an owner,",
                "      so it goes to Customer Relations -- but `unmatched` stays set, and",
                "      the verification outcome routes it to a human. A catch-all that",
                "      cleared the flag would turn every gap in the matrix into a",
                "      confident wrong answer.",
                "    when:",
                "      always: true",
                "    then:",
                "      department: CUSTOMER_RELATIONS",
                "      urgency: MEDIUM",
                "      priority: P2",
            ],
            [
                "Destination of last resort. Every other routing decision is made by",
                "the classification rule that matched, which carries its own",
                "department straight from the authored matrix.",
            ],
        ),
        encoding="utf-8",
    )

    return ROOT / "complaint_rules" / "classification.yaml"


# ==============================================================
# stage 4 - the knowledge base
# ==============================================================
#
# 25 authored documents, each with numbered sections, become the YAML the
# renderer turns into PDF and DOCX. The parsers read those files, not the
# JSON, because the SRS asks the system to ingest real documents and a
# pipeline fed structured JSON would never exercise the parser at all.
#
# Lifecycle is carried across exactly. Four families ship a superseded v1.0
# beside their active v2.0, and one document is a draft -- those are what the
# Hidden Policy Update and Contradictory Policy challenges are demonstrated
# with, so flattening them all to ACTIVE would quietly delete two challenges.

LIFECYCLE = {
    "Active": "ACTIVE",
    "Superseded": "SUPERSEDED",
    "Draft": "DRAFT",
    "Expired": "EXPIRED",
}

# Alternate so both parsers are exercised by the corpus rather than by a test
# fixture. A DOCX-only corpus leaves the PDF parser unproven on real content.
FORMAT_CYCLE = ("pdf", "docx")


def section_ref(section_id: str | None) -> str:
    """
    ``DOC-003-S12`` -> ``12``.

    Numeric because the section parser finds headings by their number. The
    renderer writes "<ref> <heading>", so a ref of "S1" produced the line
    "S1 Scope and Applicability", which matches no heading pattern -- and every
    document collapsed into a single unsectioned chunk. Twenty-five documents
    became twenty-five blobs, retrieval had nothing to rank, and no citation
    could resolve to a section.
    """
    if not section_id:
        return ""
    tail = str(section_id).rsplit("-", 1)[-1]
    digits = "".join(ch for ch in tail if ch.isdigit())
    return digits or tail


def _wrap(text: str, width: int = 74, indent: str = "        ") -> list[str]:
    """A YAML block scalar, wrapped so the file stays readable in review."""
    words = str(text or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(indent + current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(indent + current)
    return lines


def stage_documents(mapping: Mapping) -> pathlib.Path:
    payload = load(DATASET / "documents" / "source" / "knowledge_base_documents.json")
    organisation = load(CONFIG / "organization_profile.json")
    company = organisation["company"]["name"]

    source_dir = DATASET / "documents" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    for stale in source_dir.glob("*.yaml"):
        stale.unlink()

    written = 0
    for index, document in enumerate(payload["documents"]):
        doc_id = document["document_id"]
        version = str(document["version"]).lstrip("vV")
        status = LIFECYCLE.get(document["lifecycle_status"], "ACTIVE")
        fmt = FORMAT_CYCLE[index % len(FORMAT_CYCLE)]

        out: list[str] = []
        w = out.append
        w(f"# {company} - {document['title']}, version {version} ({status})")
        w("#")
        w("# GENERATED from knowledge_base_documents.json by")
        w("# scripts/convert_raftarxpress.py. Edit the JSON and re-run, then")
        w("# re-render with scripts/make_sample_documents.py.")
        w(f"formats: [{fmt}]")
        w("")
        w("metadata:")
        w(f"  doc_ref: {doc_id}")
        w(f"  title: {_yaml_scalar(document['title'])}")
        w(f'  version: "{version}"')
        w("  doc_type: POLICY")
        w(f"  category: {_yaml_scalar(document.get('category'))}")
        w(f"  family: {document['document_family_id']}")
        w(f"  status: {status}")
        if document.get("effective_date"):
            w(f'  effective_date: "{document["effective_date"]}"')
        if document.get("expiry_date"):
            w(f'  expiry_date: "{document["expiry_date"]}"')
        w("")
        w(f"header_text: {_yaml_scalar(company + ' - Internal Policy')}")
        w(f"footer_text: {_yaml_scalar(f'{doc_id} v{version} - {status}')}")
        w("")
        w("sections:")
        for section in document["sections"]:
            w(f'  - ref: "{section_ref(section["section_id"])}"')
            w(f"    source_id: {section['section_id']}")
            w(f"    heading: {_yaml_scalar(section['heading'])}")
            if section.get("page"):
                w(f"    page: {section['page']}")
            w("    body:")
            w("      - >-")
            out.extend(_wrap(section["content"]))
            w("")

        path = source_dir / f"{doc_id}_v{version}.yaml"
        path.write_text("\n".join(out), encoding="utf-8")
        written += 1

    print(f"             {written} document sources")
    return source_dir


# ==============================================================
# stage 5 - the complaints
# ==============================================================
#
# 500 complaints become the CSV the benchmark importer reads. The ground truth
# travels as `expected_*` columns, which the importer writes to columns only
# the benchmark may read -- a test greps all six pipeline packages to prove
# none of them can see a label.
#
# The corpus's own ids travel too. Without them a scored failure can be read
# back to a row in the CSV but not to the complaint the author wrote, and the
# person who has to fix it works in the JSON.

CSV_COLUMNS = [
    "external_ref", "title", "description", "order_ref", "product", "channel",
    "customer_type", "requested_resolution", "previous_ref", "tags",
    "expected_category_code", "expected_subcategory_code",
    "expected_department_code", "expected_urgency", "expected_priority_code",
    "expected_escalation_code",
]

CHANNELS = {
    "web form": "WEB", "web": "WEB", "email": "EMAIL", "phone": "PHONE",
    "call": "PHONE", "chat": "CHAT", "mobile app": "WEB", "app": "WEB",
    "social media": "SOCIAL", "whatsapp": "CHAT", "portal": "WEB",
}


def stage_complaints(mapping: Mapping) -> pathlib.Path:
    rows: list[dict[str, Any]] = []
    for path in sorted((DATASET / "complaints").glob("complaints_batch_*.json")):
        payload = load(path)
        rows.extend(payload["complaints"] if isinstance(payload, dict) else payload)

    out_dir = DATASET / "complaints"
    target = out_dir / "raftarxpress_benchmark.csv"

    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            truth = row["expected_ground_truth"]
            channel = CHANNELS.get(str(row.get("complaint_channel", "")).strip().lower(), "WEB")
            escalation = ESCALATION_BY_NAME.get(truth.get("escalation_level") or "", "NONE")

            writer.writerow(
                {
                    "external_ref": row["complaint_id"],
                    "title": row["title"],
                    "description": row["description"],
                    "order_ref": row.get("order_reference") or "",
                    "product": row.get("product_or_service") or "",
                    "channel": channel,
                    "customer_type": row.get("customer_type") or "",
                    "requested_resolution": row.get("requested_resolution") or "",
                    "previous_ref": row.get("previous_complaint_reference") or "",
                    "tags": ";".join(row.get("complaint_bucket_tags") or []),
                    "expected_category_code": mapping.categories[truth["category_id"]],
                    "expected_subcategory_code": mapping.subcategories[truth["subcategory_id"]],
                    "expected_department_code": mapping.departments[truth["department_id"]],
                    "expected_urgency": URGENCY_BY_NAME[truth["urgency"]],
                    "expected_priority_code": truth["priority"],
                    "expected_escalation_code": escalation,
                }
            )

    print(f"             {len(rows)} complaints")
    return target


# ══════════════════════════════════════════════════════════════
# entry point
# ══════════════════════════════════════════════════════════════
STAGES = {
    "taxonomy": stage_taxonomy,
    "signals": stage_signals,
    "rules": stage_rules,
    "documents": stage_documents,
    "complaints": stage_complaints,
}


def main() -> int:
    if len(sys.argv) != 2 or (sys.argv[1] not in STAGES and sys.argv[1] != "all"):
        print(__doc__)
        print("stages:", ", ".join(STAGES), "| all")
        return 2

    if not CONFIG.exists():
        print(f"No corpus at {CONFIG}")
        return 2

    mapping = build_mapping()
    (ROOT / "config" / "raftarxpress_codes.json").write_text(
        json.dumps(mapping.as_dict(), indent=2), encoding="utf-8"
    )

    wanted = list(STAGES) if sys.argv[1] == "all" else [sys.argv[1]]
    for name in wanted:
        path = STAGES[name](mapping)
        # Some stages write into the dataset, which is a sibling of the
        # backend, so a path relative to ROOT is not always possible.
        try:
            shown = path.relative_to(ROOT)
        except ValueError:
            shown = path.relative_to(ROOT.parent)
        print(f"{name:12} -> {shown}")

    print(BANNER)
    print(f"categories    {len(mapping.categories)}")
    print(f"subcategories {len(mapping.subcategories)}")
    print(f"departments   {len(mapping.departments)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
