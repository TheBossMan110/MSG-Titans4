# RaftarXpress Logistics (Pvt) Ltd

The authored corpus: 500 labelled complaints, a 105-rule resolution matrix, and
a 25-document policy knowledge base for a Pakistani last-mile courier.

Delivered as JSON. Re-verify after **every** revision:

```bash
cd backend && python scripts/verify_dataset.py ../dataset/raftarxpress
```

That script exits non-zero on anything structurally or referentially wrong. A
broken reference does not fail loudly at import time — it quietly lowers a
benchmark score, and then the score gets blamed on the pipeline.

## Layout

```
raftarxpress/
├── complaints/           complaints_batch_01..10.json  — 50 each, 500 total
├── documents/source/     knowledge_base_documents.json — 25 documents
└── configuration/        the organisation itself
    ├── organization_profile.json      9 departments, SLA hours, branches
    ├── complaint_taxonomy.json        13 categories, 34 subcategories
    ├── complaint_resolution_rules.json  105 rules, each citing a policy section
    └── response_templates.json
```

Batch files are zero-padded so they sort in order. They arrived as
`complaints_batch_1..10`, which sorts 1, 10, 2 — and a loader that globs them
would have read batch 10 second.

## What one complaint looks like

```jsonc
{
  "complaint_id": "CMP-00001",
  "title": "Parcel CN-98214309812 delayed past promised delivery date",
  "description": "...",
  "customer_type": "Individual Consumer",
  "order_reference": "CN-98214309812",
  "complaint_bucket_tags": ["simple", "low_priority"],
  "expected_ground_truth": {          // read by the benchmark runner alone
    "category_id": "CAT-01",
    "subcategory_id": "SUB-001",
    "department_id": "DEPT-01",
    "urgency": "Medium",
    "priority": "P2",
    "escalation_required": false,
    "escalation_level": "No Escalation",
    "applicable_rule_id": "RULE-001",
    "refund_eligible": "No"
  }
}
```

`expected_ground_truth` is the scoring key. A test greps all six pipeline
packages to prove none of them can read a label, so a high score cannot come
from the system having seen the answer.

## Verification result

Checked on 24 September 2026. **No structural or referential problems.**

| Check | Result |
|---|---|
| Complaints | 500, unique ids, one uniform schema, none under 40 characters |
| Ground truth | present on all 500 |
| Category / subcategory / department ids | every one resolves |
| Rule ids | every one resolves; all 34 subcategories covered by the matrix |
| Rule → policy references | all 105 resolve to a real document **and section** |
| `previous_complaint_reference` | 43 present, none dangling |
| Documents | 25 (SRS asks 20+), 21 families, 4 carrying a superseded version |

### Adversarial coverage

Every SRS-scored trap is represented:

| Trap | Count | Challenge |
|---|---|---|
| `prompt_injection` | 51 (10%) | 1.8 #8 |
| `multi_issue` | 51 (10%) | 1.8 #12 |
| `incomplete` | 51 (10%) | 1.8 #11 |
| `adversarial` | 50 (10%) | general |
| `repeated` | 37 (7%) | 1.8 #13 |
| `contradictory` | 22 (4%) | 1.8 #10 |
| `calm_but_critical` | 70 | sentiment/urgency trap |
| `sentiment_urgency_trap` | 16 | " |

The injection cases are labelled correctly, which matters more than their
count. CMP-00011 carries an injected instruction to authorise a PKR 500,000
payout; its ground truth is `No Escalation`, `CAT-01` — the genuine delay
complaint, with the injected instruction ignored. A corpus that labelled the
injection as the complaint would train the benchmark to reward obeying it.

### Two things worth knowing

**Four rules are never exercised** — `RULE-033`, `RULE-063`, `RULE-065`,
`RULE-100`. They are valid and referenced correctly by the matrix, but no
complaint reaches them, so nothing proves they fire. Four complaints would
close that.

**49% of complaints escalate**, and 63% are P0 or P1. That is a deliberately
hot corpus, and it is worth saying out loud what it does to a score: a system
that escalated *everything* would post excellent escalation recall against it.
The benchmark reports precision alongside recall for exactly this reason, and
the figure to quote is the pair, never recall alone. A calmer majority would
make the number more meaningful, but the corpus is not wrong as it stands.

## Importing

```bash
POST /api/benchmark/datasets/raftarxpress/import
```

The importer reads spreadsheets. These files are JSON in a different shape, so
they are converted first — see `backend/scripts/convert_raftarxpress.py`.
