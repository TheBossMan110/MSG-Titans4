# Complaint intelligence report

*Generated 2026-09-25 18:29 UTC by `scripts/generate_reports.py` from the live database:
548 complaints in the register.*

## Categories

| Category | Complaints | Share |
|---|---|---|
| Delivery | 92 | 16.8% |
| Billing | 78 | 14.2% |
| Safety | 57 | 10.4% |
| Technical Support | 52 | 9.5% |
| Product Defect | 43 | 7.8% |
| Refund | 42 | 7.7% |
| Lost Shipment | 39 | 7.1% |
| Staff Behavior | 28 | 5.1% |
| Service Quality | 27 | 4.9% |
| Account | 25 | 4.6% |
| Privacy | 24 | 4.4% |
| Not classified | 15 | 2.7% |
| Customs/Documentation | 14 | 2.5% |
| Warranty | 12 | 2.2% |

## Priority

| Priority | Complaints |
|---|---|
| P0 | 124 |
| P1 | 87 |
| P2 | 254 |
| P3 | 68 |
| UNSET | 15 |

## Sentiment

| Sentiment | Complaints | Share |
|---|---|---|
| NEGATIVE | 218 | 39.8% |
| NEUTRAL | 174 | 31.8% |
| STRONGLY_NEGATIVE | 113 | 20.6% |
| UNSET | 26 | 4.7% |
| POSITIVE | 17 | 3.1% |

Sentiment is recorded, never used to set urgency (SRS 1.8 #6): urgency comes from risk signals and the rule matrix.

## Department routing

| Department | Complaints | Open |
|---|---|---|
| Customer Relations | 175 | 175 |
| Billing & Accounts | 64 | 64 |
| Warranty & Claims | 59 | 59 |
| Delivery & Logistics Operations | 52 | 52 |
| Compliance & Legal Affairs | 45 | 45 |
| Safety & Risk Management | 41 | 41 |
| Account Security & Fraud Prevention | 38 | 38 |
| Returns & Refunds | 36 | 36 |
| Management Escalations | 23 | 23 |
| Not routed | 15 | 15 |

## Channels

| Channel | Complaints |
|---|---|
| WEB | 196 |
| EMAIL | 175 |
| CHAT | 122 |
| UPLOAD | 52 |
| IMPORT | 3 |

## Escalations

Escalated: **298 of 548** (54.4%).

| Level | Complaints |
|---|---|
| CRITICAL_MGMT | 122 |
| DEPT_MANAGER | 54 |
| SUPERVISOR | 47 |
| COMPLIANCE_REVIEW | 38 |
| SPECIALIST | 37 |

## Repeat and duplicate complaints

* Complaints with an earlier related complaint (repeat count > 0): **0**
* Complaints marked as duplicates: **6**

## SLA risk

Open complaints at risk of missing their target: **25**.

| Complaint | Title | Priority | Team | Due | Breached |
|---|---|---|---|---|---|
| CMP-000011 | Charger made a popping noise and smells burnt | P0 | Safety & Risk Management | 2026-09-24T05:01 | yes |
| CMP-000012 | Charger popped and smells burnt | P0 | Safety & Risk Management | 2026-09-24T05:09 | yes |
| CMP-000013 | Charger burning smell | P0 | Safety & Risk Management | 2026-09-24T05:43 | yes |
| CMP-000014 | Charger burning smell | P0 | Safety & Risk Management | 2026-09-24T05:49 | yes |
| CMP-000015 | Charger burning smell | P0 | Safety & Risk Management | 2026-09-24T07:52 | yes |
| CMP-000016 | Charger burning smell | P0 | Safety & Risk Management | 2026-09-24T08:26 | yes |
| CMP-000020 | Charger burning smell | P0 | Safety & Risk Management | 2026-09-24T09:46 | yes |
| CMP-000029 | Laptop arrived late and damaged | P0 | Warranty & Claims | 2026-09-25T05:01 | yes |

## Policy usage

| Document | Citations | Of which to a superseded version |
|---|---|---|
| DOC-007 | 170 | 0 |
| DOC-003 | 126 | 0 |
| DOC-005 | 108 | 0 |
| DEL-POL-04 | 87 | 0 |
| DOC-001 | 87 | 0 |
| DOC-015 | 81 | 0 |
| DOC-023 | 74 | 0 |
| DOC-019 | 63 | 0 |
| DOC-013 | 63 | 0 |
| DOC-009 | 59 | 0 |
| SAF-POL-02 | 55 | 0 |
| DOC-016 | 44 | 0 |
| DOC-024 | 41 | 0 |
| DOC-020 | 40 | 0 |
| DOC-010 | 38 | 0 |
| DOC-014 | 34 | 0 |
| REF-POL-02 | 33 | 0 |
| DOC-025 | 29 | 0 |
| DOC-021 | 26 | 0 |
| DOC-017 | 21 | 0 |

## GenAI / Python disagreements

Mean agreement across analysed complaints: **31.13%**. Rules corrected the
model on 391 of 546 decisions.

| Field | Complaints where they disagree |
|---|---|
| follow_up_required | 424 |
| urgency | 369 |
| priority | 358 |
| department | 351 |
| subcategory | 256 |
| category | 165 |
| support_department | 164 |
| escalation_level | 132 |
| required_actions | 1 |
| prohibited_actions | 1 |

The per-complaint detail, with the explanation of each disagreement, is in
[`genai_python_comparison.csv`](genai_python_comparison.csv).

## Manual-review cases

Open in the review queue: **522**.

| Reason | Open cases |
|---|---|
| GENAI_PYTHON_DISAGREEMENT | 512 |
| AMBIGUOUS_COMPLAINT | 144 |
| RULE_UNMATCHED | 139 |
| RULE_CONFLICT | 74 |
| GENAI_UNAVAILABLE | 23 |
| SENSITIVE_COMPLAINT | 1 |
