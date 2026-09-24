# Dataset

The complaint corpus and the policy knowledge base, split by business domain.
Authored by people who never open the backend code, which is why it lives
beside `backend/` rather than inside it.

```
dataset/
├── ecommerce/          product, billing, refunds, warranty, safety, account
│   ├── complaints/     CSV or XLSX — one row per complaint
│   └── documents/      rendered PDF + DOCX
│       └── source/     the YAML each document is written as
└── logistics/          delivery, shipment, last mile, returns transport
    ├── complaints/
    └── documents/
        └── source/
```

## Complaints

One spreadsheet per file, any filename. Required columns:

| Column | Required | Notes |
|---|---|---|
| `title` | yes | One line, as a customer would write a subject |
| `description` | yes | The complaint body, 40–2000 characters |
| `order_ref` | no | `ZN-` then **6–8 digits**. Five digits is rejected as malformed |
| `product` | no | e.g. *Zenithra PowerCore 65W charger* |
| `amount` | no | Number only — `42500`, not `₹42,500` |
| `currency` | no | `INR`, `AED` or `GBP` |
| `channel` | no | `WEB`, `EMAIL`, `CHAT`, `PHONE` |

**Do not add classification columns.** Category, urgency, priority,
department and escalation are what the system is being scored on. The only
exception is the benchmark set, where `expected_*` columns hold ground truth —
and those are read by the benchmark runner alone. A test greps every pipeline
package to prove none of them can see a label.

Import with:

```bash
POST /api/benchmark/datasets/{tag}/import      # multipart file upload
```

## Documents

Written as YAML in `<domain>/documents/source/`, rendered to PDF and DOCX by:

```bash
cd backend && python scripts/make_sample_documents.py
```

Nobody opens Word. Copy an existing source file as the template — it carries
the metadata block the parsers expect.

The SRS requires **20 documents minimum**. Firm, checkable rules with real
numbers make useful documents; "we aim to respond promptly" cannot be verified
against anything, and the system checks every figure in a generated reply
against the document it cites.

## Adding a domain

Create `dataset/<name>/{complaints,documents/source}/` and add `<name>` to
`DATASET_DOMAINS` in the backend's `.env`. No loader changes — the same
configuration-as-data stance the taxonomy takes.
