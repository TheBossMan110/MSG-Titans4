# Sample documents

Six documents copied byte-for-byte from the RaftarXpress knowledge base
(`dataset/raftarxpress/documents/`), three PDF and three DOCX. Together they
show a version history, two contradictions between documents that are both
in force, and the escalation procedure the rule matrix cites most often.
Metadata is from `dataset/raftarxpress/documents/source/knowledge_base_documents.json`;
the same fields are printed as front matter at the top of each file.

| File | Id | Title | Type | Version | Status | Effective | Expiry | Family | Sections | Cited by rules |
|---|---|---|---|---|---|---|---|---|---:|---:|
| `DOC-001_v2.0.pdf` | DOC-001 | Customer Refund Policy | Refund Policy | 2.0 | Active | 2025-07-01 | – | FAM-REFUND-POLICY | 4 | 5 |
| `DOC-002_v1.0.docx` | DOC-002 | Customer Refund Policy (Legacy) | Refund Policy | 1.0 | Superseded | 2023-01-01 | 2025-06-30 | FAM-REFUND-POLICY | 3 | 0 |
| `DOC-009_v1.5.pdf` | DOC-009 | Enterprise Customer Complaint Policy | Complaint Policy | 1.5 | Active | 2024-03-01 | – | FAM-COMPLAINT-POLICY | 4 | 2 |
| `DOC-010_v2.0.docx` | DOC-010 | Standard Operating Procedure for Complaint Handling | Complaint SOP | 2.0 | Active | 2024-06-01 | – | FAM-COMPLAINT-SOP | 4 | 2 |
| `DOC-016_v2.0.docx` | DOC-016 | Multi-Tier Incident Escalation Procedure | Escalation Procedure | 2.0 | Active | 2024-09-01 | – | FAM-ESCALATION-PROCEDURE | 3 | 19 |
| `DOC-019_v2.2.pdf` | DOC-019 | Frequently Asked Questions (Customer Portal FAQ) | FAQs | 2.2 | Active | 2025-02-01 | – | FAM-FAQS | 4 | 1 |

"Cited by rules" is the number of the 105 authored rules in
`configuration/complaint_resolution_rules.json` whose policy reference names
the document.

## What each pair shows

**Version history — DOC-002 → DOC-001 (refund policy).** DOC-002 v1.0 was in
force from 2023-01-01 to 2025-06-30; DOC-001 v2.0 replaced it on 2025-07-01.
The figures changed:

| | DOC-002 v1.0 (superseded) | DOC-001 v2.0 (active) |
|---|---|---|
| Claim window | 3 calendar days from delivery (S1) | 7 business days (S2) |
| Payment | 10–14 banking days, cross-cheque or hub voucher (S2) | 5–7 banking days, IBFT or wallet; cash disbursement prohibited (S4) |
| Deduction | 15% restocking deduction on every refund (S3) | none stated; original packaging, labels and seals required (S3) |

A reply that quotes "3 days" or "15%" is quoting an outdated policy.

**Conflict — DOC-019 FAQ against DOC-001 policy.** `DOC-019-S3` says refunds
and replacements are "unconditionally guaranteed within 24 hours without
original packaging inspection or invoice verification". `DOC-001` requires a
claim within 7 business days, the original packaging and seals, and payment in
5–7 banking days. Complaint CMP-00016 (in `../sample_complaints/`) quotes the
FAQ against the policy.

**Conflict — DOC-010 SOP against DOC-009 policy.** `DOC-010-S4` lets agents
issue immediate cash compensation up to PKR 2,500 without supervisor approval.
`DOC-009-S4` permits zero cash settlements at agent level and routes all
compensation through Billing & Accounts by IBFT only.

Both conflicts resolve by the precedence in `backend/config/policy.yaml`:
active policy ranks above department SOP and FAQ, so DOC-001 and DOC-009
prevail. The conflict is still recorded when it is resolved.

**DOC-016** is the escalation procedure: Tier-1 to Tier-2 triggers (2 hours
unacknowledged, 24 hours unresolved), direct routing of VIP SLA breaches,
legal notices, regulatory inquiries and damages over PKR 100,000 to
Management Escalations, and a one-business-hour response for that team. It is
cited by 19 rules, more than any other document.

## How to upload them

**Admin → Policy Versions** (`/dashboard/knowledge-base/upload`), signed in as
an administrator:

1. Choose one or more of these files (PDF or DOCX; up to 25 per upload).
   Optionally pick the owning department. Document id, version and
   effective date are read from the front matter, so no other field needs
   filling in.
2. Leave **Activate on success (supersedes the previous version)** ticked to
   make each file the active version of its document, or untick it to stage
   the file for impact review first.
3. Upload. Each file is validated (type by content, not extension; size;
   duplicates), parsed into sections, chunked and versioned, and the result
   lists it as accepted, needing review or rejected, with its reference,
   version and status and an **Open version** link.

The same upload through the API:

```bash
curl -X POST "$API/api/documents?activate=true" \
     -H "Authorization: Bearer $TOKEN" \
     -F "files=@DOC-001_v2.0.pdf" -F "files=@DOC-002_v1.0.docx"
```

Then use **Admin → Knowledge Base** (`/dashboard/knowledge-base`) to see each
document, its versions and sections, and the search page
(`/dashboard/knowledge-base/search`) to find the section a citation points
to.

What to expect:

* The status is set from the metadata and dates: DOC-001, DOC-009, DOC-010,
  DOC-016 and DOC-019 are in force and become `ACTIVE`; DOC-002's expiry date
  (2025-06-30) has passed, so it is filed as `EXPIRED`. A citation of an
  expired or superseded version is classified `OUTDATED` and is never the
  basis of a resolution.
* The application keys a document family on the document id, so DOC-001 and
  DOC-002 are held as two documents rather than two versions of one. The
  in-app supersede step (old version demoted to `SUPERSEDED`, never deleted)
  happens when a newer file carries the **same** document id.
* If the knowledge base already holds these exact files (the RaftarXpress
  corpus is normally loaded), each is rejected as `DUPLICATE_DOCUMENT` —
  "This exact file has already been uploaded." That is the duplicate check
  working; to watch a full ingest, use an environment where they have not
  been loaded.
