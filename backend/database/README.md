# Database design

53 tables. PostgreSQL (Supabase) in production, SQLite for local work and as the
offline demo fallback — the same Alembic migrations run on both.

---

## Two rules that shape everything

### 1. Business taxonomy is DATA. System states are CODE.

SRS 1.8 #5 says a *new complaint category* must be processable through configuration,
and #14 says evaluators may ask us to add a department, change an escalation threshold
or modify an SLA **live**. So the split is:

| Concept | Storage | Why |
|---|---|---|
| Departments, categories, subcategories, priority levels, escalation levels, SLA policies, rules, lexicons, injection patterns, promise patterns | **Lookup tables** | Must be addable at runtime |
| Complaint status, GenAI run status, verification outcome, user role, comparison status | **`text` + `CHECK` constraint** (`src/db/enums.py`) | Coupled to code paths; changing them means changing logic anyway |

`CHECK` constraints are used rather than PostgreSQL `ENUM` types because altering an
enum in Alembic is needlessly painful and a `CHECK` is a one-line migration.

### 2. Every AI decision and every rule decision gets its own row.

"No hard-coded outputs / no fabricated verification values" (SRS 1.8 #17) means every
number the UI displays must be traceable to a stored record. That is why
`genai_runs`, `validation_runs`, `rule_hits`, `comparisons` and
`verification_decisions` are separate tables rather than JSON columns on `complaints`.

Four SRS deliverables are satisfied by simply querying these tables:

| Deliverable | Query source |
|---|---|
| 6 — GenAI Pipeline Evidence (requests, responses, invalid responses, retry evidence) | `genai_runs` (one row **per attempt**) |
| 7 — Python Validation Pipeline Evidence | `validation_runs` + `rule_hits` |
| 8 — GenAI / Python Comparison Report | `comparisons` + `benchmark_results` |
| 10 — Security & Adversarial Testing Report | `injection_events` + `audit_log` + `response_flags` |

---

## Table groups

### A · Identity, access, audit (3)
`users` · `refresh_tokens` · `audit_log`

* A **user** logs in. A **customer** is a record about someone who complained.
  They are different tables and `customers.user_id` is nullable — most complaints
  arrive by phone/email/import from people with no account.
* `audit_log` is append-only. Grant no `UPDATE`/`DELETE` to the application role in
  production (`database/grants.sql`).
* Refresh tokens are stored as a SHA-256 hash and rotated on use; the presented token
  is revoked, so a replayed refresh fails.

### B · Taxonomy & runtime configuration (7)
`departments` · `categories` · `subcategories` · `priority_levels` ·
`escalation_levels` · `sla_policies` · `app_config`

`priority_levels.rank` and `escalation_levels.rank` are ordered ladders (0 = most
severe / no escalation). This is what makes the **mandatory escalation floor** a rank
comparison instead of a hard-coded `if` chain:

```python
final_rank = max(genai_rank, python_floor_rank)   # Python can raise, never lower
```

`app_config` holds the documented policy precedence order, comparison severity
weights, decision thresholds and the current ruleset version.

### C · Deterministic signal configuration (3)
`lexicon_terms` · `injection_patterns` · `promise_patterns`

Pipeline 2's entire sensory apparatus. Rows, not Python constants, so an evaluator
can add a safety keyword or an injection pattern on stage.

`lexicon_terms.signal_key` groups terms into named signals (`safety_lexicon_hit`,
`legal_threat`, `privacy_breach`, …) that rule conditions test. Signals marked
`analytics_only` in `config/signals.yaml` — currently `emotional_intensity` — are
recorded but **must never** influence urgency or priority. That is the
Sentiment-Urgency Trap (SRS 1.8 #6), and the rule-engine test suite enforces it.

### D · Knowledge base (4)
`documents` · `document_versions` · `document_sections` · `chunks`

```
documents (policy family, e.g. DEL-POL)
   └── document_versions (DEL-POL-04 v2.1, ACTIVE | SUPERSEDED | EXPIRED | DRAFT | METADATA_REVIEW)
          └── document_sections (5.2, page 7 / paragraph 41)
                 └── chunks (DEL-POL-04::5.2::c1  + embedding + FTS)
```

Two things worth calling out:

* **`ux_docver_one_active`** is a partial unique index on `document_id WHERE status = 'ACTIVE'`.
  "At most one active version per policy" is therefore a *database guarantee*, not a
  code convention — that is the answer when a judge asks how an outdated policy is
  prevented from being used.
* **`METADATA_REVIEW`** exists because the hidden evaluation pack will not follow our
  metadata block convention. An unrecognised document degrades into this state, stays
  parseable and retrievable at reduced traceability, and an admin completes the
  metadata in the UI. It never crashes the parser.

Chunks denormalise `doc_ref`, `doc_version`, `section_ref`, `page_no` and
`paragraph_index` so a retrieval result answers the Source-Traceability Challenge
without three joins.

### E · Rule matrix (1)
`rules`

`conditions` is a small declarative DSL stored as JSON and **interpreted, never
`eval()`-ed**:

```json
{"any_of": [
  {"signal": "safety_lexicon_hit"},
  {"all_of": [{"field": "category", "eq": "PRODUCT_DEFECT"},
              {"signal": "injury_mention"}]}
]}
```

Source of truth is YAML in `complaint_rules/` (a required deliverable), loaded here by
a seeder and editable at runtime through the admin API.

`precedence` (higher wins), `is_mandatory_escalation` (sets the floor) and `rationale`
(shown verbatim in the explainability panel) are the three control columns that matter.

### F · Customers & complaints (6)
`customers` · `complaints` · `complaint_entities` · `complaint_links` ·
`complaint_status_history` · `complaint_attachments`

`complaints` holds the **reconciled** classification — what the system finally
decided — not raw model output.

The `expected_*` columns hold the labelled ground truth for the 500-complaint
benchmark dataset. **Neither pipeline ever reads them**; only the benchmark comparator
does, and a test asserts that.

`complaint_links` records `EXACT_DUPLICATE` / `NEAR_DUPLICATE` / `REPEAT` relationships
with the similarity score and which detector found it (`TRIGRAM`, `EMBEDDING`,
`REFERENCE`).

### G · Pipelines (5)
`prompt_versions` · `llm_cache` · `genai_runs` · `validation_runs` · `rule_hits`

* `genai_runs` gets **one row per attempt**, so retries are evidence rather than
  overwritten history.
* `validation_runs.escalation_floor_code` is the value nothing downstream may lower.
* `rule_hits.matched_spans` holds `[{start, end, text, signal}]` — this is what
  highlights *"burning smell"* inside the complaint as the reason escalation fired.
* `rule_hits.applied = false` records rules that matched but lost on precedence.
* `llm_cache` stores **real captured responses** for development cost control and as a
  network-outage fallback. It must never be written by anything other than an actual
  provider call; fabricated responses are prohibited by SRS 1.8 #17.

### H · Verification (2)
`comparisons` · `verification_decisions`

One `comparisons` row per compared field, each carrying `severity`, `winner` and a
plain-English `explanation` — which is exactly the shape Deliverable 8 asks for, so
the report is generated rather than hand-written.

### I · Workflow (7)
`responses` · `response_flags` · `escalations` · `follow_ups` · `review_queue` ·
`review_actions` · `sla_events`

`review_actions.original_value` + `is_override` is the literal implementation of
SRS Step 59: *"the original recommendation and reviewer decision must both remain in
the audit trail."*

`response_flags.span_start/span_end` drive the inline red highlight in the reply
editor; `blocking_rule_ref` is the hover text.

### J · Security & operations (7)
`injection_events` · `jobs` · `benchmark_runs` · `benchmark_results` ·
`impact_analyses` · `impact_items` · `report_exports`

`jobs` is a database-backed queue on purpose: no Redis, no Celery, nothing extra to
fail on demo day, and the progress bar reads straight from the row.

`impact_analyses` answers the Hidden Policy Update challenge. It is only answerable
because every resolution stores the policy references it relied on — so "which
complaints are affected by this changed clause?" is a join, not a guess.

---

## Cross-dialect notes

Two column types are dialect-aware (`src/db/base.py`):

| Type | PostgreSQL | SQLite |
|---|---|---|
| `Vector(768)` | `pgvector` | JSON array of floats |
| `JSONType` | `JSONB` | `JSON` |
| `BigIntPK` | `BIGINT` | `INTEGER` |

`BigIntPK` exists because SQLite only auto-increments an `INTEGER PRIMARY KEY` — a
`BIGINT` primary key silently loses autoincrement and every insert fails. The test
suite runs on SQLite specifically so mistakes like that surface immediately instead of
on demo day.

### Migrations

`alembic/versions/0001_baseline_schema.py` is a **baseline** revision: it creates the
PostgreSQL extensions, calls `metadata.create_all()` (which compiles against the live
connection's dialect, so the variant types above render correctly on both), then adds
the PostgreSQL-only search indexes. Every revision **after** the baseline is a normal
explicit autogenerated Alembic migration.

PostgreSQL-only indexes created by the baseline:

| Index | Purpose |
|---|---|
| `ix_comp_desc_trgm` (GIN trigram) | Near-duplicate complaint detection |
| `ix_comp_fts` (GIN tsvector) | Complaint free-text search |
| `ix_chunks_fts` (GIN tsvector) | Lexical half of hybrid retrieval |
| `ix_chunks_embedding` (ivfflat) | Semantic half of hybrid retrieval |

### Storage footprint

~600 chunks × 768-dim vectors ≈ 2 MB, 500 complaints ≈ 1 MB, `genai_runs` raw
responses ≈ 3 MB. Comfortably inside Supabase's 500 MB free tier.

---

## Commands

```bash
python -m alembic upgrade head            # apply migrations
python -m alembic revision --autogenerate -m "add x"
python -m alembic downgrade -1

python -m src.db.seed.run                 # idempotent — safe to re-run
python -m src.db.seed.run --only users
python -m src.db.seed.run --reset         # drops everything first (blocked in production)
```

---

## Files in this folder

| File | What it is |
|---|---|
| `README.md` | This design note. |
| `schema.sql` | PostgreSQL DDL for all **54** tables (the 53 described above plus `email_messages`, added by migration `0004_email_messages`), with every index, the `CHECK` constraints and the four PostgreSQL-only search indexes. **Generated** from the SQLAlchemy metadata (`src/db/models`, via `src.db.base.Base.metadata`) by compiling `CreateTable` / `CreateIndex` for the `postgresql` dialect. The extensions it needs (`pgcrypto`, `pg_trgm`, `vector`) are listed at the top. |
| `ER_DIAGRAM.md` | Mermaid entity-relationship diagrams, one per domain (A-M) plus an overview of the dual-pipeline core, with real columns, keys and foreign keys, followed by a table-by-table description with row counts from a read-only production snapshot. Generated from the same metadata. |
| `__init__.py` | Package marker. |

**Source of truth.** Alembic (`backend/alembic/versions`, head `0004_email_messages`)
builds the real database; `schema.sql` and `ER_DIAGRAM.md` are review artefacts derived
from the same ORM metadata. If either ever disagrees with the migrations, the
migrations win. The one known difference is recorded in the header of `schema.sql`
(server defaults that migration 0004 sets on three `email_messages` columns).

Non-sensitive reference and business tables (taxonomy, rules, SLA policies, document
metadata, complaints, comparisons and verification decisions) are exported as CSV
outside the repository, in the submission folder `DATABASE\data\`, with their own
`README.md` listing each file, its row count and its source table.
