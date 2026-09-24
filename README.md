# SupportNova

**Theme:** ResponseX Intelligence · **Category:** Generative AI PowerPlay · **TechWiz 7**

> SupportNova turns a customer complaint into a routed, escalated, policy-grounded
> resolution — where a deterministic Python rule engine independently verifies and,
> where required, **overrides** the AI before anything reaches the customer.

---

## Three folders

```
.
├── backend/     FastAPI + PostgreSQL. Both pipelines, the rule engine, the API.
│             Self-contained: its own .venv, requirements, tests and tooling.
├── frontend/    Next.js + TypeScript. Built against the OpenAPI schema.
└── dataset/     The complaint corpus and policy knowledge base, split by domain.
```

They are separate because the people are. The dataset is authored by whoever knows
the business, not by whoever wrote the parser, and it has no reason to live inside a
Python package. The frontend consumes a published schema rather than reaching into
the backend's internals.

| Folder | Start here |
|---|---|
| [backend/](backend/README.md) | Installation, configuration, architecture, design decisions |
| [frontend/](frontend/README.md) | The four screens worth building first, and two contract details that bite |
| [dataset/](dataset/README.md) | Column contracts, the document template, how to add a domain |

## The architecture in one paragraph

Two pipelines run over the same complaint. **Pipeline 1** sends it plus retrieved
policy text to a Generative AI API and gets back strictly-schema'd JSON. **Pipeline 2**
derives the same conclusions from a deterministic rule matrix and never calls a model
— a test greps the package to prove it cannot. A comparison engine reconciles them
field by field, and where they disagree on anything that matters, **the rules win**.
Every stage writes its own rows, so no figure the system displays is unsourced.

## Running it

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                                # add your keys
python -m alembic upgrade head
python -m src.db.seed.run
uvicorn src.main:app --reload
```

Then <http://localhost:8000/api/docs>.

Full instructions, including the offline SQLite fallback, are in
[backend/README.md](backend/README.md).

## Status

| Layer | State |
|---|---|
| Database schema (53 tables) + migrations | ✅ Done |
| Configuration-as-data (taxonomy, policy, signals, 110 rules) | ✅ Done |
| Auth + RBAC + audit trail | ✅ Done |
| Document ingestion (PDF + DOCX) + hybrid retrieval | ✅ Done |
| Pipeline 2 — deterministic Python ground truth | ✅ Done |
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
| Frontend | 🔜 In progress |
| Admin config endpoints (live rule editing) | 🔜 |

Requirement coverage is machine-checked: `backend/config/requirements.yaml` maps every
SRS clause to the tables, modules, endpoints and tests that satisfy it, and
`tests/test_requirements_coverage.py` fails the build if anything marked **done**
names something that does not exist, or if anything marked **partial** does not state
its remaining gap in writing. The rendered map is
[backend/documentation/REQUIREMENTS_COVERAGE.md](backend/documentation/REQUIREMENTS_COVERAGE.md).

## Licence

See [LICENSE](LICENSE). AI tool usage is declared in [AI_USAGE.md](AI_USAGE.md).
