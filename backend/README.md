# SupportNova — backend

**Theme:** ResponseX Intelligence · **Category:** Generative AI PowerPlay · **TechWiz 7**

> SupportNova turns a customer complaint into a routed, escalated, policy-grounded
> resolution — where a deterministic Python rule engine independently verifies and,
> where required, **overrides** the AI before anything reaches the customer.

The project has three folders — see the [root README](../README.md) for the map.
This one covers the backend. The corpus it reads lives in [`../dataset/`](../dataset/README.md).

---

## The architecture in one paragraph

Two pipelines run over the same inputs. **Pipeline 1** (`genai_pipeline/`) sends the
complaint plus retrieved policy text to a Generative AI API and gets back strictly
schema-validated JSON: category, department, urgency, priority, escalation, policy
references, resolution steps. **Pipeline 2** (`python_validation/`) reaches its *own*
conclusion from the Complaint Resolution Rule Matrix using deterministic signal
extraction and rule evaluation — **with no language model involved at all**. A
comparison engine diffs them field by field, and a decision layer gives Python veto
over department, urgency, priority, escalation, policy validity and prohibited
actions. Only then is customer-facing prose generated, and it is scanned again by a
response guard before any human sees it.

You can prove Pipeline 2's independence at any time:

```bash
# No API key configured — Pipeline 2 still produces a full ground-truth result.
python -m python_validation.cli --complaint-ref CMP-00421
```

---

## Status

| Layer | State |
|---|---|
| Database schema (53 tables) + migrations | ✅ Done |
| Configuration-as-data (taxonomy, policy, signals, 110 rules) | ✅ Done |
| Auth + RBAC + audit trail | ✅ Done |
| Health / provenance endpoints | ✅ Done |
| Document ingestion (PDF + DOCX) + hybrid retrieval | ✅ Done |
| Pipeline 2 — deterministic Python ground truth | ✅ Done |
| Prompt injection defence (4 layers) | ✅ Done |
| Pipeline 1 — providers, prompts, schema validation | ✅ Done |
| Comparison engine + verification decision | ✅ Done |
| Response generation + response guard | ✅ Done |
| Hallucination checks + source traceability | ✅ Done |
| Complaint intake, write-back + explainability API | ✅ Done |
| Review queue, reviewer overrides, SLA tracking | ✅ Done |
| Analytics, trends, reports + CSV/XLSX/PDF export | ✅ Done |
| Benchmark runner + dataset import (labelled & hidden) | ✅ Done |
| Test suite | ✅ 547 passing (SQLite + PostgreSQL in CI) |
| 500-complaint dataset + 17 policy documents | 🔜 In progress |
| Admin config endpoints (live rule editing) | 🔜 |

---

## 1. Installation

### Prerequisites
* Python 3.11+ (developed on 3.13)
* Git
* A Supabase project (free tier) — or nothing at all, SQLite works out of the box

### Steps

```bash
git clone <repo-url> supportnova
cd supportnova

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt

cp .env.example .env          # then edit it — see section 2
python -m alembic upgrade head
python -m src.db.seed.run
```

### Run it

```bash
uvicorn src.main:app --reload
```

| URL | What it is |
|---|---|
| http://127.0.0.1:8000/api/docs | Interactive OpenAPI docs (the frontend contract) |
| http://127.0.0.1:8000/api/health | Liveness + readiness |
| http://127.0.0.1:8000/api/version | Active prompt / model / ruleset / precedence |

### Run the tests

```bash
pytest -q                 # everything
pytest -m unit -q         # fast, no database round-trips beyond SQLite
pytest -k escalation -q   # narrow: useful when debugging an injected defect
```

---

## 2. Configuration

Copy `.env.example` to `.env`. **`.env` is git-ignored and must never be committed.**

### Database

Local development needs nothing — the default is a SQLite file:

```bash
DATABASE_URL=sqlite:///./var/supportnova.db
```

For Supabase: *Project Settings → Database → Connection string → **Session pooler***,
then change the scheme to the psycopg 3 driver:

```bash
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

> Use the **Session pooler** string. The transaction pooler (port 6543) does not
> support prepared statements and will produce confusing driver errors.

The same migrations run on both. Keeping SQLite working is not an accident — it is
the offline fallback if venue networking fails during evaluation, and the test suite
runs against it continuously so a Postgres-only construct can never creep in unnoticed.

### API keys (free tiers only)

| Variable | Where to get it | Role |
|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey | Primary generation **and** embeddings |
| `GROQ_API_KEY` | https://console.groq.com/keys | Fallback provider |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys | Optional third fallback |

The application starts and remains fully usable with **no** key configured — Pipeline 2,
the rule matrix, routing, escalation and the audit trail are all deterministic. The UI
shows a degraded-mode banner instead of silently inventing results.

### Secret hygiene
* `.env` is git-ignored; `.env.example` is the committed template.
* `detect-secrets` runs in CI on every push.
* `SUPABASE_SERVICE_ROLE_KEY` is backend-only and must never be sent to the frontend.

---

## 3. Seeded accounts

All seeded accounts share one password, published deliberately: this is a
demonstration system holding **synthetic data only**. Override with `SEED_PASSWORD`.

| Email | Role | Purpose |
|---|---|---|
| `evaluator@raftarxpress.com` | evaluator | **Competition evaluator — read access across the system** |
| `admin@raftarxpress.com` | admin | **Administrator — knowledge base, rules, configuration** |
| `manager@raftarxpress.com` | manager | Support manager dashboards |
| `reviewer@raftarxpress.com` | reviewer | Manual review queue and overrides |
| `agent.billing@raftarxpress.com` | agent | Billing queue |
| `agent.logistics@raftarxpress.com` | agent | Delivery & logistics queue |
| `agent.claims@raftarxpress.com` | agent | Warranty & claims queue |
| `agent.safety@raftarxpress.com` | agent | Product safety queue |
| `customer@raftarxpress.com` | customer | Customer portal |

**Password:** `SupportNova#2026`

No email is ever sent by this application. `raftarxpress.com` is a fictional organisation.

---

## 4. The fictional organisation

**Zenithra** — consumer electronics & appliances e-commerce with in-house logistics,
operating in IN / AE / UK.

| | Count | SRS minimum |
|---|---|---|
| Departments | 10 | 8 |
| Complaint categories | 11 | 10 |
| Subcategories | 37 | 20 |
| Priority levels | 4 | — |
| Escalation levels | 6 | — |

All of it lives in `config/taxonomy.yaml` and is loaded into database tables — not
compiled into Python. That is what makes *"add a new category / department /
escalation threshold, live, without a deploy"* a 30-second operation.

---

## 5. Backend layout

```
config/                  taxonomy.yaml · policy.yaml · signals.yaml   ← config-as-data
complaint_rules/         Complaint Resolution Rule Matrix (YAML, human-authored)
routing_rules/           department routing rule sheets
escalation_rules/        mandatory escalation conditions
prompt_templates/        versioned Jinja2 prompts (v1.0, v1.1, …)
schemas/                 Pydantic API + GenAI output schemas

document_processing/     PDF / DOCX parsing, sectioning, chunking
knowledge_base/          versioning, precedence, retrieval
complaint_processing/    intake, normalisation, entity extraction, dedupe
genai_pipeline/          PIPELINE 1 — provider abstraction, prompts, schema validation
python_validation/       PIPELINE 2 — signals, rule engine, escalation floor  (no LLM)
comparison_engine/       field-level diff, ladders, scores, verification decision
hallucination_checks/    citation validation, claim support, source traceability
security/                prompt-injection defence, response guard

src/
  core/                  config · logging · security · deps · errors · middleware
  db/                    models (53 tables) · enums · seeders
  api/v1/                routers
  services/              application services
alembic/                 migrations

tests/                   pytest suite
                         (the corpus lives in ../dataset/, not here)
hidden_test_ready/       drop-zone for the evaluators' hidden pack
database/                schema documentation and SQL helpers
documentation/           architecture, diagrams, reports
reports/                 generated CSV / PDF / XLSX exports
```

---

## 6. Design decisions worth knowing

**Why our own JWT auth instead of Supabase Auth.** Roles, the audit trail and reviewer
overrides all need a single source of truth in our own `users` table, and the whole
stack has to keep working against SQLite with no network on demo day. Supabase is used
as managed Postgres + object storage only.

**Why synchronous SQLAlchemy.** FastAPI runs `def` endpoints in a threadpool. Async
SQLAlchemy buys nothing at this scale and costs real debugging time. LLM concurrency
in the batch runner comes from a `ThreadPoolExecutor`.

**Why business taxonomy is data but system states are code.** Categories, departments,
priorities, escalation levels, SLAs and rules are rows — evaluators can add them live.
Complaint status, run status and verification outcome are `text` + `CHECK` constraints,
because changing those means changing code paths anyway.

**Why prompts are files, not strings in Python.** Every prompt lives in
`prompt_templates/<name>/v<major>.<minor>.j2` and is reachable only through
`genai_pipeline/prompts.py`. Each version is checksummed in `prompt_versions`, so a
template edited without a version bump is detectable rather than merely discouraged,
and `genai_runs.prompt_version` ties every result to the exact text that produced it.
Taxonomy values are injected from the database at render time, so adding a complaint
category never requires touching a prompt.

**Why validation does not stop at the JSON schema.** Gemini enforces a schema during
decoding, and a schema check still cannot see the two failures that matter: a
well-formed `"category": "URGENT"` that no taxonomy row defines, and a perfectly
plausible citation to a policy document that does not exist. So `genai_pipeline/
validator.py` adds a reference gate (every code resolved against the live tables) and
a citation gate (every `chunk_key` resolved against the knowledge base *and* against
what was actually retrieved for that complaint). A failure produces a field-specific
correction instruction and exactly one bounded repair attempt.

**Why ladder fields are compared by rank, not by equality.** `MANAGER` against
`CRITICAL_MGMT` is not simply "different" — one is *below* the other, and the direction
decides whether a disagreement is safe over-caution or a genuine under-escalation. The
priority table counts the opposite way to the escalation table (P0 is rank 0), so both
are normalised on load to "higher means more severe". Compared raw, every
under-prioritisation would have been reported as over-caution.

**Why the comparison engine does not check required or prohibited actions.** It did
once, by fuzzy-matching the rule matrix's prose obligations against the model's prose
steps, and it produced two false findings on the first real complaint: a CRITICAL
violation for proposing *"advise the customer to cease using the product"* against a
prohibition on *"advise the customer to repair or test the product"* — near-identical
token sets, opposite meanings — and an 18% compliance score on a result that had in
fact followed the safety procedure. No threshold fixes that; the distinguishing feature
is negation, which token overlap cannot see. Obligations are carried into the
reconciled record and enforced by the response guard against the actual generated
reply, which is where SRS Step 28 puts that check. A fabricated CRITICAL finding is
worse than an absent one.

**Why an unmeasured score is null, not zero.** `compliance_score` stays null until the
response guard exists, because it asks a question the comparison stage cannot answer.
Every score carries its own numerator and denominator, and a score with no denominator
renders as null rather than a flattering 100% or a punishing 0%.

**Why the response guard keeps the draft it rejected.** A promise is authorised only
by an `ELIGIBLE` eligibility decision from Pipeline 2 — `CONDITIONAL` and
`REQUIRES_VERIFICATION` deliberately do not count, because a condition nobody has
checked is not a basis for telling a customer the answer is yes. A blocked draft is
regenerated once with the offending phrase quoted back, and both drafts are stored with
their flagged spans. Keeping only the clean replacement would leave no evidence that
the model tried to promise a refund the policy did not support, and that evidence is
the entire point of the check.

**Why the hallucination checks never ask a model.** A check that asked a model whether
a model hallucinated would inherit the failure it exists to catch, and could not run
during the outage where it matters most. So both checks are deterministic, and a test
greps the package to prove no provider is reachable from it.

**Why lexical overlap is not the only claim check.** Overlap measures *grounding* —
whether a claim's vocabulary appears in the source — and reliably catches a sentence
invented from nothing. It cannot tell you a claim is *true*: "refunds are available
within 30 days" against a policy saying 14 reuses every word of the source and scores
near-perfectly. So every figure in a claim is checked against the cited text, and the
claim's polarity is compared with the source line it rests on. Only policy claims are
scored — process narration like "we have escalated your complaint" is skipped, because
no policy document describes what the company is currently doing and reporting those
would fill the review queue with findings for politeness.

**Why the complaint is stored before it is analysed.** A submission that is accepted
and then fails analysis must still be a complaint someone can find and work by hand.
Persisting only on success would lose exactly the submissions that most need a human,
so intake writes the row first and marks it `FAILED` if the pipelines throw.

**Why almost nothing is rejected.** Only an *empty* complaint is refused. Too short, an
unrecognised order reference, an unsupported attachment, a suspected prompt injection —
all are accepted, recorded as findings, and answered on their merits. A customer with a
badly-formed complaint still has a complaint. Even a refused attempt is written to
`complaint_validation_issues` against its `submitted_ref`, so it is visible in the audit
rather than vanishing.

**Why the repeat count ignores what the complaint says.** "I have called five times" is
a sentiment, not a fact. The count comes from stored records of prior *unresolved*
contacts, because the rule matrix escalates on it — and letting the text drive that
would put the customer in charge of their own priority.

**Why a reviewer can raise an escalation but never lower one.** The mandatory floor
holds regardless of what any later stage concludes — and a reviewer is a later stage.
The endpoint refuses explicitly and names the floor, because a reviewer who believes
they lowered an escalation and did not is in a worse position than one who was told no.
If the floor is genuinely wrong, the fix is a rule change, which is a different and
separately audited act.

**Why the review queue is derived, not populated.** An item exists because a stored
`verification_decisions` row says so, or because an intake finding was marked
`ROUTED_TO_REVIEW`. Deciding twice — once in the comparison engine and again in a
queueing rule — is exactly how a queue stops meaning what the verdict says.

**Why an empty dashboard says "nothing to measure", not "100%".** Every percentage
carries its own numerator and denominator, and a ratio with no denominator renders as
`null`. A system with no complaints in it would otherwise report perfect SLA compliance
and a flawless override rate — the most flattering possible reading of having done
nothing. The same rule runs one layer down in trend detection: a percentage change from
a zero baseline is `null`, not 600% and not infinity.

**Why the dashboard is one call, not eight.** Panels fetched at different instants can
show figures that do not add up, and "why does that total not match" is an expensive
question to field during a demo.

**Why no pipeline can read a ground-truth label.** The `expected_*` columns sit on the
complaint row, so nothing but discipline stops a rule or a prompt consulting them — and
a pipeline that could see the answer would be scoring its own homework, making every
accuracy figure after it worthless. A test greps `python_validation/`, `genai_pipeline/`,
`comparison_engine/`, `hallucination_checks/` and `security/` to prove none of them can,
the same way the GenAI restriction on Pipeline 2 is enforced.

**Why the benchmark reports `null` for a pipeline that did not run.** A rules-only run,
or one taken during a provider outage, must not report the model at 0% accurate — it was
never asked, and "0%" reads as "got everything wrong". The two pipelines have separate
denominators for exactly this.

**Why mandatory escalation recall is reported on its own.** `policy.yaml` sets its target
at 100% and calls it non-negotiable. Folded into per-field accuracy, one un-escalated
safety complaint in five hundred reads as "escalation accuracy 99.8%" — which sounds like
success. It gets its own line, and the complaints it missed are named by reference.

**Why a GenAI outage is a degraded result, not an error.** When every provider fails,
Pipeline 1 records the failure and returns `ok=False`; Pipeline 2 still classifies,
routes, escalates and SLA-tracks the complaint from rules alone. Nothing is ever
fabricated to fill the gap.

**Why every AI call and every rule decision gets its own row.** "No hard-coded outputs"
means every number on screen must be traceable to a stored run record — so
`genai_runs`, `validation_runs`, `rule_hits` and `comparisons` are separate tables
rather than JSON blobs hanging off a complaint.

See `database/README.md` for the full schema rationale.

---

## 7. Licence

MIT — see `LICENSE`.
