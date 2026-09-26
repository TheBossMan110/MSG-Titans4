# GenAI and Python comparison report

*Generated 2026-09-25 18:28 UTC by `scripts/generate_reports.py` from the live database.*

**Cases compared:** 500 labelled complaints from the RaftarXpress dataset (the SRS asks for at least 100).
The full per-complaint table is in [`genai_python_comparison.csv`](genai_python_comparison.csv) (also `.xlsx`),
with every column deliverable 8 lists: complaint ID, expected category, GenAI and Python category, department,
urgency and escalation, policy reference, match/mismatch, verification status and the explanation of each
disagreement.

## Results by field

| Field | GenAI agrees with Python | GenAI vs label | Python vs label | Final decision vs label |
|---|---|---|---|---|
| Category | 41.3% | 52.3% | 26.6% | 40.0% |
| Department | 32.7% | 34.1% | 33.4% | 33.4% |
| Urgency | 28.7% | 40.9% | 34.8% | 34.8% |
| Escalation | 53.2% | 37.8% | 39.4% | 39.0% |

*GenAI vs label* counts only complaints the model answered; *Final decision* is what the system stored
after the comparison engine reconciled the two (rules prevail on disagreement).

## Verification outcomes

| Outcome | Complaints |
|---|---|
| CORRECTED_BY_RULES | 206 |
| BLOCKED | 139 |
| MANUAL_REVIEW_REQUIRED | 136 |
| INCOMPLETE | 11 |
| VERIFIED_WITH_WARNING | 7 |
| VERIFIED | 1 |

## Accuracy by scenario (final category vs label)

| Scenario tag | Complaints | Final category matches label |
|---|---|---|
| high_priority | 111 | 60.4% |
| low_priority | 79 | 54.4% |
| contextual_override | 72 | 13.9% |
| calm_but_critical | 70 | 65.7% |
| emotional | 57 | 57.9% |
| simple | 51 | 72.5% |
| prompt_injection | 51 | 35.3% |
| multi_issue | 51 | 62.7% |
| incomplete | 51 | 86.3% |
| adversarial | 50 | 34.0% |
| repeated | 37 | 35.1% |
| unsupported_refund | 35 | 25.7% |
| safety | 26 | 61.5% |
| security | 25 | 68.0% |
| first_contact | 25 | 20.0% |
| frivolous | 23 | 8.7% |
| contradictory | 22 | 36.4% |
| policy_exception | 19 | 26.3% |
| sentiment_urgency_trap | 16 | 12.5% |
| calm_critical | 15 | 6.7% |
| angry_low_priority | 15 | 13.3% |
| privacy | 14 | 78.6% |

Scenario tags with fewer than 10 complaints are in the CSV (`bucket_tags`) but not summarised here.

## Read this before judging the accuracy figures

The labels are part of the dataset the team wrote, and an audit of the disagreements shows many of them are
themselves questionable. [`label_audit.csv`](label_audit.csv) lists **371 disputed labels on
232 complaints** (escalation: 138, category: 87, department: 77, urgency: 69), each with the evidence:

* **Two independent methods agree against the label.** GenAI and the rule engine share no code and no
  result until comparison; when both reach the same answer and the label says something else, the label is
  the first suspect.
* **Safety wording labelled "no escalation".** SRS 1.8 #6 requires a calmly written safety complaint to be
  treated as critical. These labels say the opposite.

Examples:

| Complaint | Title | Label | System decided |
|---|---|---|---|
| CMP-000421 | Delivery rider smoking cigarette inside warehouse fulfillment dispatch | NONE | CRITICAL_MGMT |
| CMP-000504 | Courteous notification regarding warehouse fire alarm failure in Karac | NONE | CRITICAL_MGMT |
| CMP-000508 | Friendly reminder regarding electrical short circuit sparks in sorting | NONE | CRITICAL_MGMT |
| CMP-000118 | Corporate contract renewal inquiry | SERVICE_QUALITY | BILLING |
| CMP-000124 | Need refund for damaged package | REFUND | PRODUCT_DEFECT |
| CMP-000140 | Where is my parcel? Need tracking info | DELIVERY | TECHNICAL_SUPPORT |
| CMP-000146 | Consignment dispatched to Quetta instead of Rawalpindi plus carton pun | DELIVERY | PRODUCT_DEFECT |
| CMP-000160 | Corporate freight SLA breach across 45 consignments plus unauthorized  | SERVICE_QUALITY | BILLING |

The labels have **not** been changed. Ground truth has to be confirmed by people; rewriting it to agree with
the system would be fabricating it (SRS 1.8 #17). Once the team has reviewed the audit, re-import the dataset
and re-run this script: the figures above will then measure the system against labels the team stands behind.

## What the numbers say about the design

For **category**, GenAI matches the labels more often (52.3%) than the rule
engine (26.6%), and because the rules prevail on every
disagreement the final category (40.0%) is below GenAI's. The
rule-wins policy is deliberate for escalation, urgency and eligibility, where a model must not be the authority
(SRS 1.8 #7, #18); for category classification it costs accuracy, and letting a confident GenAI category stand
when the rules' category match is weak is the first change to evaluate.

The system also makes genuine mistakes that the audit does not excuse, among them over-escalating some routine
billing complaints and reading "COD" as a billing signal in complaints that are about staff behaviour. Those
are tracked for rule tuning; they are visible, per complaint, in the CSV.
