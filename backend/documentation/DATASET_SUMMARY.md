# Dataset Summary

**SupportNova** · RaftarXpress Logistics (Pvt) Ltd · SRS requirements #3 and #4

This page describes the complaint dataset and the knowledge-base dataset the
system is built and scored against. Every count below was computed on
27 September 2026 by reading the files in the repository (no database): the
ten complaint batch files, the benchmark CSV, the configuration JSON and the
document sources. `backend/scripts/verify_dataset.py ../dataset/raftarxpress`
re-checks structure and references at any time.

The active dataset domain is `raftarxpress` (`DATASET_DOMAINS=raftarxpress` in
the backend environment). The `dataset/ecommerce` and `dataset/logistics`
folders are the earlier Zenithra samples: three documents
(`REF-POL-02` v3.0, `SAF-POL-02` v2.0, `DEL-POL-04` v2.1) and no complaint
files. They are not counted below.

---

## Where each required item lives

### #3 Complaint dataset

| Required | Where | Count |
|---|---|---|
| Minimum 500 complaints | `dataset/raftarxpress/complaints/complaints_batch_01..10.json` (50 each); the same 500 as `raftarxpress_benchmark.csv` | **500** |
| Metadata | Per complaint: `complaint_id`, `title`, `description`, `customer_type`, `product_or_service`, `order_reference`, `complaint_channel`, `date`, `previous_complaint_reference`, `requested_resolution`, `complaint_bucket_tags` | 11 fields |
| Categories | `expected_ground_truth.category_id`; defined in `configuration/complaint_taxonomy.json` | 13, all used |
| Subcategories | `expected_ground_truth.subcategory_id` | 34, all used |
| Expected routing | `expected_ground_truth.department_id` and `supporting_department_id`; CSV `expected_department_code` | 9 departments |
| Expected urgency | `expected_ground_truth.urgency` and `priority`; CSV `expected_urgency`, `expected_priority_code` | 4 levels, P0–P3 |
| Expected escalation | `expected_ground_truth.escalation_required` and `escalation_level`; CSV `expected_escalation_code` | 247 required |
| Difficult cases | tag `contradictory` (plus the sentiment and policy traps in §1.8) | 22 |
| Prompt-injection cases | tag `prompt_injection` | 51 |
| Duplicate cases | tags `repeated`, `near_duplicate`; field `previous_complaint_reference` | 39 tagged, 43 linked |
| Incomplete cases | tag `incomplete` | 51 |
| Multi-issue cases | tag `multi_issue`; field `expected_ground_truth.secondary_issue` | 51 |

### #4 Knowledge-base dataset

| Required | Where | Count |
|---|---|---|
| Policies | `dataset/raftarxpress/documents/` — see §2.3 | 12 active, 4 superseded, 1 draft |
| SOPs | `DOC-010` Complaint Handling SOP, `DOC-024` Customs SOP | 2 |
| FAQs | `DOC-019` Customer Portal FAQ | 1 |
| Routing rules | `DOC-017` (document); `backend/routing_rules/departments.yaml` and the Department column of the rule matrix (machine form) | 1 document |
| Escalation rules | `DOC-016` (document); `backend/escalation_rules/mandatory.yaml` (74 mandatory floors) | 1 document |
| Resolution rules | `configuration/complaint_resolution_rules.json` (105 rules, each citing a document section) → `backend/complaint_rules/*.yaml`; exported to `backend/reports/rule_matrix.csv` / `.xlsx` | 105 authored, 619 loaded |
| Document metadata | `documents/source/knowledge_base_documents.json`; the metadata block of each `documents/source/DOC-nnn_vX.Y.yaml`; the front matter printed in every PDF/DOCX; the file name | 25 documents |
| Version history | Four document families with a superseded and an active version — §2.4 | 4 families |
| Conflict cases | Version conflicts, cross-document conflicts, rule citations of non-active documents, and a complaint built on a conflict — §2.5 | see §2.5 |

Also in the knowledge base: `DOC-018` SLA rules, `DOC-022` response templates
(with 14 templates in `configuration/response_templates.json`), `DOC-023`
product-support guidelines, and `configuration/organization_profile.json`
(9 departments with SLA hours).

---

## 1. Complaint dataset

### 1.1 Files

| File | Contents |
|---|---|
| `complaints/complaints_batch_01.json` … `_10.json` | 50 complaints each, 500 in total, ids `CMP-00001`–`CMP-00500`, all unique |
| `complaints/raftarxpress_benchmark.csv` | The same 500 complaints in the importer's column layout (16 columns: `external_ref`, `title`, `description`, `order_ref`, `product`, `channel`, `customer_type`, `requested_resolution`, `previous_ref`, `tags`, and six `expected_*` columns carrying taxonomy codes). Its ids match the JSON exactly. |

`expected_ground_truth` also records `primary_issue`, `secondary_issue`,
`sentiment`, `applicable_rule_id`, `refund_eligible` and
`notes_for_reviewer`. The labels are read by the benchmark runner only; a test
checks that no pipeline package can read them.

### 1.2 Metadata

| Field | Distribution |
|---|---|
| Channel | Email 171 · Web Form 156 · Chat 121 · Complaint Upload 52 |
| Customer type | Individual Consumer 251 · Business/Merchant Account 116 · Corporate Freight Client 87 · VIP/Premium Account 46 |
| Product or service | Parcel Courier 225 · Freight Forwarding 93 · Last-Mile Delivery 50 · E-commerce Fulfillment 40 (+16 spelt "E-Commerce Fulfillment") · Cash-on-Delivery 34 (+18 spelt "Cash on Delivery (COD)") · Warehousing 24 |
| Date | 2026-09-10 to 2026-09-24 |
| Description length | 47 to 678 characters, median 249 |
| Order reference | present on 433, absent on 67 |
| Previous complaint reference | present on 43, every one resolving to a complaint in the set |
| Requested resolution | present on all 500 |
| Bucket tags | 509 distinct tag values |

### 1.3 Categories

| Id | Code | Name | Subcategories | Complaints | Share |
|---|---|---|---:|---:|---:|
| CAT-01 | DELIVERY | Delivery | 4 | 110 | 22.0% |
| CAT-02 | LOST_SHIPMENT | Lost Shipment | 2 | 34 | 6.8% |
| CAT-03 | PRODUCT_DEFECT | Product Defect | 3 | 46 | 9.2% |
| CAT-04 | BILLING | Billing | 4 | 56 | 11.2% |
| CAT-05 | REFUND | Refund | 3 | 58 | 11.6% |
| CAT-06 | ACCOUNT | Account | 3 | 34 | 6.8% |
| CAT-07 | TECHNICAL_SUPPORT | Technical Support | 3 | 36 | 7.2% |
| CAT-08 | STAFF_BEHAVIOR | Staff Behavior | 2 | 49 | 9.8% |
| CAT-09 | WARRANTY | Warranty | 2 | 25 | 5.0% |
| CAT-10 | PRIVACY | Privacy | 2 | 16 | 3.2% |
| CAT-11 | SAFETY | Safety | 2 | 12 | 2.4% |
| CAT-12 | CUSTOMS | Customs/Documentation | 2 | 12 | 2.4% |
| CAT-13 | SERVICE_QUALITY | Service Quality | 2 | 12 | 2.4% |
| | | **Total** | **34** | **500** | |

### 1.4 Subcategories

| Id | Code | Name | Category | Complaints |
|---|---|---|---|---:|
| SUB-001 | DELAYED_DELIVERY | Delayed Delivery | DELIVERY | 58 |
| SUB-002 | MISSED_DELIVERY_ATTEMPT | Missed Delivery Attempt | DELIVERY | 18 |
| SUB-003 | PACKAGE_LEFT_UNATTENDED | Package Left Unattended | DELIVERY | 16 |
| SUB-004 | WRONG_ROUTE_DISPATCH | Wrong Route Dispatch | DELIVERY | 18 |
| SUB-005 | LOST_PARCEL | Lost Parcel | LOST_SHIPMENT | 10 |
| SUB-006 | PARTIAL_SHIPMENT_MISSING | Partial Shipment Missing | LOST_SHIPMENT | 24 |
| SUB-007 | DAMAGED_PARCEL | Damaged Parcel | PRODUCT_DEFECT | 26 |
| SUB-008 | WRONG_ITEM_DELIVERED | Wrong Item Delivered | PRODUCT_DEFECT | 13 |
| SUB-009 | TAMPERED_PACKAGING | Tampered Packaging | PRODUCT_DEFECT | 7 |
| SUB-010 | COD_AMOUNT_MISMATCH | COD Amount Mismatch | BILLING | 9 |
| SUB-011 | DUPLICATE_CHARGE | Duplicate Charge | BILLING | 8 |
| SUB-012 | INCORRECT_CHARGE | Incorrect Charge | BILLING | 31 |
| SUB-013 | COD_REMITTANCE_DELAY | COD Remittance Delay | BILLING | 8 |
| SUB-014 | REFUND_NOT_PROCESSED | Refund Not Processed | REFUND | 5 |
| SUB-015 | REFUND_DELAY | Refund Delay | REFUND | 7 |
| SUB-016 | RTO_PROCESSING_DELAY | RTO Processing Delay | REFUND | 46 |
| SUB-017 | ACCOUNT_LOCKED | Account Locked | ACCOUNT | 10 |
| SUB-018 | UNAUTHORIZED_ACCOUNT_ACCESS | Unauthorized Account Access | ACCOUNT | 5 |
| SUB-019 | MERCHANT_PROFILE_UPDATE | Merchant Profile Update | ACCOUNT | 19 |
| SUB-020 | TRACKING_NOT_UPDATING | Tracking Not Updating | TECHNICAL_SUPPORT | 8 |
| SUB-021 | APP_CRASH | App Crash | TECHNICAL_SUPPORT | 11 |
| SUB-022 | API_WEBHOOK_FAILURE | API Webhook Failure | TECHNICAL_SUPPORT | 17 |
| SUB-023 | RUDE_RIDER_DRIVER_BEHAVIOR | Rude Rider/Driver Behavior | STAFF_BEHAVIOR | 31 |
| SUB-024 | RIDER_DEMANDING_CASH_TIP | Rider Demanding Cash Tip | STAFF_BEHAVIOR | 18 |
| SUB-025 | WARRANTY_CLAIM_DENIED | Warranty Claim Denied | WARRANTY | 5 |
| SUB-026 | INSURANCE_PAYOUT_DELAY | Insurance Payout Delay | WARRANTY | 20 |
| SUB-027 | DATA_PRIVACY_BREACH | Data Privacy Breach | PRIVACY | 11 |
| SUB-028 | UNSOLICITED_MARKETING_SMS | Unsolicited Marketing SMS | PRIVACY | 5 |
| SUB-029 | RECKLESS_DRIVING_SAFETY_RISK | Reckless Driving/Safety Risk | SAFETY | 7 |
| SUB-030 | HAZARDOUS_MATERIAL_MISHANDLING | Hazardous Material Mishandling | SAFETY | 5 |
| SUB-031 | MISSING_CUSTOMS_DOCUMENTS | Missing Customs Documents | CUSTOMS | 6 |
| SUB-032 | REGULATORY_IMPOUNDMENT_HOLD | Regulatory Impoundment Hold | CUSTOMS | 6 |
| SUB-033 | SUBSCRIPTION_CONTRACT_RENEWAL | Subscription/Contract Renewal | SERVICE_QUALITY | 5 |
| SUB-034 | EXECUTIVE_SLA_BREACH | Executive SLA Breach | SERVICE_QUALITY | 7 |

### 1.5 Expected routing

| Id | Code | Department | Owning | Share | As supporting |
|---|---|---|---:|---:|---:|
| DEPT-01 | LOGISTICS_OPS | Delivery & Logistics Operations | 154 | 30.8% | 86 |
| DEPT-02 | BILLING | Billing & Accounts | 56 | 11.2% | 27 |
| DEPT-03 | RETURNS_REFUNDS | Returns & Refunds | 58 | 11.6% | 6 |
| DEPT-04 | WARRANTY_CLAIMS | Warranty & Claims | 85 | 17.0% | 8 |
| DEPT-05 | CUSTOMER_RELATIONS | Customer Relations | 66 | 13.2% | 44 |
| DEPT-06 | ACCOUNT_SECURITY | Account Security & Fraud Prevention | 45 | 9.0% | 33 |
| DEPT-07 | COMPLIANCE | Compliance & Legal Affairs | 17 | 3.4% | 21 |
| DEPT-08 | SAFETY | Safety & Risk Management | 12 | 2.4% | 23 |
| DEPT-09 | MGMT_ESCALATIONS | Management Escalations | 7 | 1.4% | 51 |
| | | **Total** | **500** | | **299** |

299 complaints expect a supporting department as well as an owner
(multi-department routing); 201 expect the owner alone.

### 1.6 Expected urgency and priority

| Urgency | Complaints | Share | | Priority | Complaints | Share |
|---|---:|---:|---|---|---:|---:|
| Critical | 173 | 34.6% | | P0 | 123 | 24.6% |
| High | 143 | 28.6% | | P1 | 193 | 38.6% |
| Medium | 95 | 19.0% | | P2 | 95 | 19.0% |
| Low | 89 | 17.8% | | P3 | 89 | 17.8% |

### 1.7 Expected escalation

| Code (CSV) | Level (JSON) | Complaints | Share | `escalation_required` true | false |
|---|---|---:|---:|---:|---:|
| NONE | No Escalation | 183 | 36.6% | 0 | 183 |
| SUPERVISOR | Supervisor Review | 112 | 22.4% | 77 | 35 |
| DEPT_MANAGER | Department Manager | 30 | 6.0% | 30 | 0 |
| SPECIALIST | Specialist Team | 53 | 10.6% | 24 | 29 |
| COMPLIANCE_REVIEW | Compliance Review | 6 | 1.2% | 0 | 6 |
| CRITICAL_MGMT | Critical Management Escalation | 116 | 23.2% | 116 | 0 |
| | **Total** | **500** | | **247** | **253** |

`escalation_required` is true for 247 complaints (49.4%). 317 carry a level
other than *No Escalation*: 70 of them (Supervisor Review 35, Specialist Team
29, Compliance Review 6) name a level with `escalation_required` false. The
benchmark CSV carries the level only.

Other labels: refund eligibility No 308 · Yes 117 · Conditional 75;
sentiment Strongly Negative 203 · Neutral 145 · Negative 114 · Positive 38.
`applicable_rule_id` names 101 of the 105 authored rules; `RULE-033`,
`RULE-063`, `RULE-065` and `RULE-100` are never the expected rule.

### 1.8 Special cases

Special cases are flagged in `complaint_bucket_tags`. The tag names are the
ones `backend/scripts/verify_dataset.py` counts against the SRS minimums.

| Case type | How it is flagged | Complaints | Ids | What the label expects |
|---|---|---:|---|---|
| Prompt injection | `prompt_injection` (sub-tags `adversarial` 50 and `jailbreak_attempt` 6 all fall inside these 51) | **51** | CMP-00011, CMP-00251–CMP-00300 | The genuine complaint, with the injected instruction ignored. 34 of the 51 expect *No Escalation*; e.g. CMP-00011's embedded order to authorise a PKR 500,000 payout is labelled a routine `DELAYED_DELIVERY`, P2. |
| Difficult / contradictory | `contradictory` | **22** | CMP-00016, 00117, 00139, 00162, 00163, 00201–00217 | Customer statements that contradict themselves or a policy (CMP-00016 cites the FAQ against the refund policy; the label follows DOC-001). |
| Duplicate / repeat | `repeated` 37, `near_duplicate` 2 | **39** | e.g. CMP-00302 → CMP-00301, CMP-00348 → CMP-00347 | 37 of the 39 carry `previous_complaint_reference`. |
| Incomplete | `incomplete` | **51** | CMP-00038, CMP-00051–CMP-00100 | 50 of the 51 have no order reference; median description 87 characters. The reviewer note states what is missing. |
| Multi-issue | `multi_issue` | **51** | CMP-00036, CMP-00101–CMP-00150 | 50 of the 51 have a `secondary_issue`; all 51 expect a supporting department. |

Linked and duplicate data beyond the tags:

* `previous_complaint_reference` is set on 43 complaints: the 37 above and six
  without a repeat tag (CMP-00116, 00130, 00135, 00139, 00167, 00200). In 25 of
  the 43 the linked complaint has the same order reference.
* 63 order references appear on more than one complaint (149 complaints in
  all).
* `secondary_issue` is set on 71 complaints, 50 of them tagged `multi_issue`.

Other difficult cases (sentiment and policy traps):

| Tag | Complaints |
|---|---:|
| `calm_but_critical` / `calm_critical` / `sentiment_urgency_trap` | 70 / 15 / 16 (100 distinct complaints) |
| `contextual_override` | 72 |
| `unsupported_refund` / `unsupported_refund_request` | 40 in total |
| `policy_exception` / `policy_exception_request` | 25 in total |
| `frivolous` | 23 |
| `angry_low_priority` | 15 |

Counted as distinct complaints, 222 carry `contradictory` or at least one of
the tags in this table.

Overlaps between the five core types: none of the 51 prompt-injection
complaints carries another core tag; `multi_issue` overlaps duplicate on 10
complaints and `contradictory` on 2; duplicate and `contradictory` overlap on
1; `incomplete` overlaps none. 202 complaints carry at least one of the five.

Against the SRS minimums as `verify_dataset.py` states them: multi-issue 51
(minimum 25), contradictory/difficult 22 (minimum 20), prompt-injection /
adversarial 51 distinct complaints (minimum 20), repeated / near-duplicate 39
(minimum 25).

### 1.9 Notes on the labels

* The corpus is deliberately hot: 49.4% of complaints expect escalation and
  63.2% (316) are P0 or P1. Escalation recall should be read together with
  precision against it.
* 30 descriptions are templated ("Customer statement regarding issue: …
  Consignment and transaction records attached for reference.").
* `backend/reports/label_audit.csv` lists 371 field-level cases, across 232
  complaints, where the GenAI pipeline and the rule engine agreed with each
  other and not with the label (escalation 138, category 87, department 77,
  urgency 69). The labels in the dataset are unchanged.

---

## 2. Knowledge-base dataset

### 2.1 Files

| Path | Contents |
|---|---|
| `dataset/raftarxpress/documents/DOC-nnn_vX.Y.pdf` / `.docx` | The 25 rendered documents: 13 PDF, 12 DOCX (each document is rendered in one format) |
| `dataset/raftarxpress/documents/source/DOC-nnn_vX.Y.yaml` | Source of each document with its metadata block; rendered by `backend/scripts/make_sample_documents.py` |
| `dataset/raftarxpress/documents/source/knowledge_base_documents.json` | All 25 documents: id, family, title, category, version, lifecycle status, effective and expiry dates, and 79 sections (`DOC-nnn-Sn`, heading, page, content) |

Each rendered file prints its metadata as front matter (`Document ID`,
`Title`, `Version`, `Document Type`, `Category`, `Effective Date`, and
`Expiry Date` where set); the ingest parser reads those labels and falls back
to the file name (`DOC-003_v2.1.pdf`).

### 2.2 Totals

25 documents in 21 families, 79 sections. Lifecycle status: Active 20,
Superseded 4, Draft 1. 19 of the 25 are cited by at least one rule in the
matrix.

### 2.3 Documents

| Id | Title | Type (category) | Version | Status | Effective | Expiry | Family | File | Sections | Cited by rules |
|---|---|---|---|---|---|---|---|---|---:|---:|
| DOC-001 | Customer Refund Policy | Refund Policy | v2.0 | Active | 2025-07-01 | – | FAM-REFUND-POLICY | DOC-001_v2.0.pdf | 4 | 5 |
| DOC-002 | Customer Refund Policy (Legacy) | Refund Policy | v1.0 | Superseded | 2023-01-01 | 2025-06-30 | FAM-REFUND-POLICY | DOC-002_v1.0.docx | 3 | 0 |
| DOC-003 | Standard Last-Mile Delivery Policy | Delivery Policy | v2.1 | Active | 2025-01-01 | – | FAM-DELIVERY-POLICY | DOC-003_v2.1.pdf | 4 | 7 |
| DOC-004 | Standard Last-Mile Delivery Policy (Legacy) | Delivery Policy | v1.0 | Superseded | 2023-01-01 | 2024-12-31 | FAM-DELIVERY-POLICY | DOC-004_v1.0.docx | 3 | 0 |
| DOC-005 | Cash-on-Delivery (COD) Operations Policy | Other | v2.0 | Active | 2025-01-16 | – | FAM-COD-POLICY | DOC-005_v2.0.pdf | 4 | 7 |
| DOC-006 | Cash-on-Delivery Handling Policy (Legacy) | Other | v1.0 | Superseded | 2023-01-01 | 2025-01-15 | FAM-COD-POLICY | DOC-006_v1.0.docx | 2 | 1 |
| DOC-007 | Lost and Damaged Shipment Claims Policy | Warranty Policy | v2.0 | Active | 2024-09-01 | – | FAM-CLAIMS-POLICY | DOC-007_v2.0.pdf | 4 | 10 |
| DOC-008 | Lost and Damaged Shipment Claims Policy (Legacy) | Warranty Policy | v1.0 | Superseded | 2023-01-01 | 2024-08-31 | FAM-CLAIMS-POLICY | DOC-008_v1.0.docx | 2 | 0 |
| DOC-009 | Enterprise Customer Complaint Policy | Complaint Policy | v1.5 | Active | 2024-03-01 | – | FAM-COMPLAINT-POLICY | DOC-009_v1.5.pdf | 4 | 2 |
| DOC-010 | Standard Operating Procedure for Complaint Handling | Complaint SOP | v2.0 | Active | 2024-06-01 | – | FAM-COMPLAINT-SOP | DOC-010_v2.0.docx | 4 | 2 |
| DOC-011 | Parcel Replacement and Re-Dispatch Policy | Replacement Policy | v1.2 | Active | 2024-04-15 | – | FAM-REPLACEMENT-POLICY | DOC-011_v1.2.pdf | 3 | 3 |
| DOC-012 | Shipment Booking Cancellation Policy | Cancellation Policy | v1.1 | Active | 2024-02-01 | – | FAM-CANCELLATION-POLICY | DOC-012_v1.1.docx | 3 | 0 |
| DOC-013 | Tariff, Billing and Invoicing Policy | Billing Policy | v1.3 | Active | 2024-05-10 | – | FAM-BILLING-POLICY | DOC-013_v1.3.pdf | 3 | 5 |
| DOC-014 | Logistics Service Warranty and Guarantee | Warranty Policy | v1.0 | Active | 2023-11-01 | – | FAM-WARRANTY-POLICY | DOC-014_v1.0.docx | 3 | 2 |
| DOC-015 | Customer Data Privacy and Protection Policy | Privacy Policy | v2.0 | Active | 2024-08-01 | – | FAM-PRIVACY-POLICY | DOC-015_v2.0.pdf | 3 | 9 |
| DOC-016 | Multi-Tier Incident Escalation Procedure | Escalation Procedure | v2.0 | Active | 2024-09-01 | – | FAM-ESCALATION-PROCEDURE | DOC-016_v2.0.docx | 3 | 19 |
| DOC-017 | Automated Department Routing and Assignment Rules | Department-Routing Rules | v1.4 | Active | 2024-07-01 | – | FAM-ROUTING-RULES | DOC-017_v1.4.pdf | 3 | 0 |
| DOC-018 | Service Level Agreement (SLA) Matrix and Response Rules | Service-Level Rules | v2.0 | Active | 2024-10-01 | – | FAM-SLA-RULES | DOC-018_v2.0.docx | 3 | 4 |
| DOC-019 | Frequently Asked Questions (Customer Portal FAQ) | FAQs | v2.2 | Active | 2025-02-01 | – | FAM-FAQS | DOC-019_v2.2.pdf | 4 | 1 |
| DOC-020 | General Customer Service Policy and Standards | Customer-Service Policy | v1.1 | Active | 2024-01-15 | – | FAM-CUSTOMER-SERVICE | DOC-020_v1.1.docx | 3 | 4 |
| DOC-021 | Regulatory Compliance and Trade Ethics Guidelines | Compliance Guidelines | v1.0 | Active | 2023-09-01 | – | FAM-COMPLIANCE-GUIDELINES | DOC-021_v1.0.pdf | 3 | 9 |
| DOC-022 | Standard Customer Response Templates | Response Templates | v1.2 | Active | 2024-06-15 | – | FAM-RESPONSE-TEMPLATES | DOC-022_v1.2.docx | 3 | 0 |
| DOC-023 | Merchant Portal and Technical Product Support Guidelines | Product-Support Guidelines | v1.0 | Active | 2024-02-15 | – | FAM-PRODUCT-SUPPORT | DOC-023_v1.0.pdf | 3 | 8 |
| DOC-024 | Customs and Inter-Provincial Documentation SOP | Other | v1.0 | Active | 2024-03-15 | – | FAM-CUSTOMS-SOP | DOC-024_v1.0.docx | 3 | 3 |
| DOC-025 | Hazardous Materials and Dangerous Goods Transit Policy | Other | v0.9 | Draft | 2026-01-01 | – | FAM-DANGEROUS-GOODS | DOC-025_v0.9.pdf | 2 | 4 |

"Cited by rules" counts the 105 authored rules whose policy reference names
the document. Every reference resolves to a real document and section.

### 2.4 Version history

Four families hold a superseded and an active version. Each legacy version's
expiry date is the day before its successor's effective date.

| Family | Superseded | In force | Changed at |
|---|---|---|---|
| FAM-REFUND-POLICY | DOC-002 v1.0, 2023-01-01 to 2025-06-30 | DOC-001 v2.0 from 2025-07-01 | 2025-07-01 |
| FAM-DELIVERY-POLICY | DOC-004 v1.0, 2023-01-01 to 2024-12-31 | DOC-003 v2.1 from 2025-01-01 | 2025-01-01 |
| FAM-COD-POLICY | DOC-006 v1.0, 2023-01-01 to 2025-01-15 | DOC-005 v2.0 from 2025-01-16 | 2025-01-16 |
| FAM-CLAIMS-POLICY | DOC-008 v1.0, 2023-01-01 to 2024-08-31 | DOC-007 v2.0 from 2024-09-01 | 2024-09-01 |

`DOC-025` v0.9 is a draft with an effective date of 2026-01-01.

In the application a document's family key is its document id
(`document_processing/metadata.py`), so the legacy and current versions above
are held as separate documents rather than as two versions of one. On upload
the status is set from the metadata and dates (`knowledge_base/versioning.py`):
incomplete metadata goes to `METADATA_REVIEW`, a file whose expiry date has
passed is filed as `EXPIRED`, one whose effective date is in the future as
`DRAFT`, otherwise `ACTIVE`. The rendered files carry no
lifecycle field, so check `DOC-025`'s status after upload: its effective date
has passed. Uploading a newer version under the **same** document id with
"Activate on success" supersedes the previous one.

### 2.5 Conflict cases

**A. Superseded versus active (version conflicts).** The figures that changed:

| Family | Legacy says | Current says |
|---|---|---|
| Refund (DOC-002 → DOC-001) | Claim within 3 calendar days of delivery (S1); paid in 10–14 banking days by cross-cheque or hub voucher (S2); 15% restocking deduction on every refund (S3) | Claim within 7 business days (S2); original packaging, labels and seals required (S3); paid in 5–7 banking days by IBFT or wallet, cash disbursement prohibited (S4) |
| Delivery (DOC-004 → DOC-003) | Exactly 2 attempts, then immediate RTO with no hub hold (S1); PKR 100 surcharge for the second attempt (S2); paper run-sheet signature as proof (S3) | Up to 3 attempts with GPS logging (S1); CNIC and OTP above PKR 25,000 (S2); no unattended delivery without recorded consent (S3); 48-hour hub hold before RTO (S4) |
| COD (DOC-006 → DOC-005) | PKR 50,000 per-parcel limit (S1); bi-monthly remittance by cheque on the 1st and 15th (S2) | PKR 100,000 limit (S1); weekly remittance every Wednesday above PKR 5,000 (S2) |
| Claims (DOC-008 → DOC-007) | 5 calendar days to claim (S1); PKR 5,000 uninsured cap (S2) | 14 calendar days to claim (S1); PKR 15,000 or declared value, whichever is lower (S2) |

**B. Active documents that contradict each other.** Found by reading the
section text:

| Conflict | One side | Other side |
|---|---|---|
| FAQ versus refund policy | `DOC-019-S3` (FAQ): refunds and replacements "unconditionally guaranteed within 24 hours without original packaging inspection or invoice verification" | `DOC-001-S2`, `-S3`, `-S4` (policy): 7-business-day window, original packaging and seals required, 5–7 banking days by IBFT or wallet |
| SOP versus complaint policy | `DOC-010-S4` (SOP): agents may issue immediate cash compensation up to PKR 2,500 without supervisor approval | `DOC-009-S4` (policy): zero cash settlements at agent level, compensation through Billing & Accounts by IBFT only; `DOC-001-S4` also prohibits cash disbursement |

**C. Rules citing documents that are not active.** `RULE-026` cites
`DOC-006-S1` (superseded); `RULE-085`, `RULE-086`, `RULE-088` and `RULE-089`
cite `DOC-025-S2` (draft). See `RULE_MATRIX.md` §7.4.

**D. A complaint built on a conflict.** CMP-00016 quotes `DOC-019-S3` against
an agent who applied `DOC-001-S3`; its reviewer note reads "Governing policy
DOC-001 takes precedence over promotional FAQ DOC-019", and the label is
`REFUND_NOT_PROCESSED`, P2, no escalation. The other 21 `contradictory`
complaints are listed in §1.8.

**How conflicts are resolved.** `backend/config/policy.yaml` states the
precedence the engine applies: active policy, then compliance, department
SOP, routing rules, SLA, FAQ, handbook; ties go to the later effective date. A
superseded or expired version is never the primary basis of a resolution and
is kept only for contradiction detection and version comparison. A conflict
is recorded even when it is resolved automatically. By that order DOC-001
prevails over DOC-019 and DOC-009 over DOC-010.

---

## 3. Samples

Representative extracts ready to try in the application:

* `backend/sample_complaints/` — 33 complaints from this dataset with their
  original ids and labels, as JSON and as an importable CSV.
* `backend/sample_documents/` — six of the documents above (three PDF, three
  DOCX) including the DOC-001/DOC-002 version pair and both cross-document
  conflicts in §2.5 B.
