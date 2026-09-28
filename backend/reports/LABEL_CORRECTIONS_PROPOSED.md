# Label corrections — CMP-00301 … CMP-00500

Proposed ground-truth rule assignments for the last 200 SupportNova / RaftarXpress complaints.
Companion file: `backend/var/label_corrections_proposed.csv` (200 rows, one per complaint).

- **Inputs:**
  - `dataset/raftarxpress/complaints/complaints_batch_07..10.json` (records 301–500)
  - `dataset/raftarxpress/configuration/complaint_resolution_rules.json` (`rule_matrix`, RULE-001…RULE-105)
  - `dataset/raftarxpress/configuration/complaint_taxonomy.json`
  - `backend/config/raftarxpress_codes.json`
- **Method:** I read every record (title, description, primary_issue, requested_resolution, tags, customer_type, previous_complaint_reference) in batches of 25. For each one I chose the single rule whose conditions best describe it. Every label in the CSV comes from that proposed rule and is converted to code form.
- **No repository file was modified.** Only the two output files above were written.

## 1. Counts

| Measure | Count |
|---|---|
| Rows | 200 |
| Original rule **kept** (`changed = no`) | **18** |
| Rule **changed** (`changed = yes`) | **182** |
| Confidence **high** | 41 |
| Confidence **medium** | 75 |
| Confidence **low** | 84 |
| `no_genuine_complaint = yes` | **54** |
| `no_genuine_complaint = no` | 146 |

Confidence split by no_genuine_complaint:

| no_genuine_complaint | high | medium | low | total |
|---|---|---|---|---|
| no | 38 | 57 | 51 | 146 |
| yes | 3 | 18 | 33 | 54 |

**Kept rows:** CMP-00301, 00302, 00329, 00330, 00339, 00340, 00362, 00419, 00426, 00432, 00444, 00445, 00446, 00466, 00493, 00495, 00498, 00500.

Rule assignments are spread across **53 distinct rules**. The most used are:

| Rule | Uses |
|---|---|
| RULE-001 | 21 |
| RULE-019 | 11 |
| RULE-003 | 10 |
| RULE-067 | 10 |
| RULE-034 | 9 |
| RULE-090 | 9 |
| RULE-100 | 9 |
| RULE-085 | 8 |

Distribution of the resulting labels:

- **Escalation:** NONE 66, SUPERVISOR 58, CRITICAL_MGMT 47, SPECIALIST 17, DEPT_MANAGER 11, COMPLIANCE_REVIEW 1.
- **Urgency:** HIGH 59, CRITICAL 49, MEDIUM 47, LOW 45.

**Meaning of `low` confidence.** Low means no rule in the matrix describes the situation. Examples:

- missed merchant pickups
- warehouse facility hazards (structural, fire systems)
- ransomware
- security-vulnerability reports
- routine information or service requests

In these cases the row names the closest rule, and the reason column says which conditions are unmet. Most of the 33 low-confidence no-genuine rows are "closest rule for a non-complaint", which is inherently weak.

## 2. Mapping tables used

### 2.1 Escalation (`escalation_level` string → code)

The rule matrix uses exactly **six** escalation strings; all six are mapped. The code ladder is `backend/config/taxonomy.yaml` → `escalation_levels`.

| Rule-matrix string | Code | Ladder rank |
|---|---|---|
| No Escalation | NONE | 0 |
| Supervisor Review | SUPERVISOR | 1 |
| Department Manager | DEPT_MANAGER | 2 |
| Specialist Team | SPECIALIST | 3 |
| Compliance Review | COMPLIANCE_REVIEW | 4 |
| Critical Management Escalation | CRITICAL_MGMT | 5 |

The brief mentioned a `"Legal…" → LEGAL` mapping. **No rule in the matrix uses a Legal escalation string**, and LEGAL is not on the backend ladder, so it is never emitted.

The brief's list also omitted "Compliance Review". It is used by RULE-056 and RULE-081 and is mapped to the ladder code **COMPLIANCE_REVIEW**. Only CMP-00472 (RULE-081) ends up with it.

### 2.2 Urgency and priority

- **Urgency:** Low → LOW, Medium → MEDIUM, High → HIGH, Critical → CRITICAL (uppercased).
- **Priority:** copied as-is (P0, P1, P2, P3).

### 2.3 Category (`raftarxpress_codes.json`)

| ID | Code | ID | Code |
|---|---|---|---|
| CAT-01 | DELIVERY | CAT-08 | STAFF_BEHAVIOR |
| CAT-02 | LOST_SHIPMENT | CAT-09 | WARRANTY |
| CAT-03 | PRODUCT_DEFECT | CAT-10 | PRIVACY |
| CAT-04 | BILLING | CAT-11 | SAFETY |
| CAT-05 | REFUND | CAT-12 | CUSTOMS |
| CAT-06 | ACCOUNT | CAT-13 | SERVICE_QUALITY |
| CAT-07 | TECHNICAL_SUPPORT | | |

### 2.4 Subcategory (with parent category)

| ID | Code | Parent | ID | Code | Parent |
|---|---|---|---|---|---|
| SUB-001 | DELAYED_DELIVERY | CAT-01 | SUB-018 | UNAUTHORIZED_ACCOUNT_ACCESS | CAT-06 |
| SUB-002 | MISSED_DELIVERY_ATTEMPT | CAT-01 | SUB-019 | MERCHANT_PROFILE_UPDATE | CAT-06 |
| SUB-003 | PACKAGE_LEFT_UNATTENDED | CAT-01 | SUB-020 | TRACKING_NOT_UPDATING | CAT-07 |
| SUB-004 | WRONG_ROUTE_DISPATCH | CAT-01 | SUB-021 | APP_CRASH | CAT-07 |
| SUB-005 | LOST_PARCEL | CAT-02 | SUB-022 | API_WEBHOOK_FAILURE | CAT-07 |
| SUB-006 | PARTIAL_SHIPMENT_MISSING | CAT-02 | SUB-023 | RUDE_RIDER_DRIVER_BEHAVIOR | CAT-08 |
| SUB-007 | DAMAGED_PARCEL | CAT-03 | SUB-024 | RIDER_DEMANDING_CASH_TIP | CAT-08 |
| SUB-008 | WRONG_ITEM_DELIVERED | CAT-03 | SUB-025 | WARRANTY_CLAIM_DENIED | CAT-09 |
| SUB-009 | TAMPERED_PACKAGING | CAT-03 | SUB-026 | INSURANCE_PAYOUT_DELAY | CAT-09 |
| SUB-010 | COD_AMOUNT_MISMATCH | CAT-04 | SUB-027 | DATA_PRIVACY_BREACH | CAT-10 |
| SUB-011 | DUPLICATE_CHARGE | CAT-04 | SUB-028 | UNSOLICITED_MARKETING_SMS | CAT-10 |
| SUB-012 | INCORRECT_CHARGE | CAT-04 | SUB-029 | RECKLESS_DRIVING_SAFETY_RISK | CAT-11 |
| SUB-013 | COD_REMITTANCE_DELAY | CAT-04 | SUB-030 | HAZARDOUS_MATERIAL_MISHANDLING | CAT-11 |
| SUB-014 | REFUND_NOT_PROCESSED | CAT-05 | SUB-031 | MISSING_CUSTOMS_DOCUMENTS | CAT-12 |
| SUB-015 | REFUND_DELAY | CAT-05 | SUB-032 | REGULATORY_IMPOUNDMENT_HOLD | CAT-12 |
| SUB-016 | RTO_PROCESSING_DELAY | CAT-05 | SUB-033 | SUBSCRIPTION_CONTRACT_RENEWAL | CAT-13 |
| SUB-017 | ACCOUNT_LOCKED | CAT-06 | SUB-034 | EXECUTIVE_SLA_BREACH | CAT-13 |

### 2.5 Department

| ID | Code | ID | Code |
|---|---|---|---|
| DEPT-01 | LOGISTICS_OPS | DEPT-06 | ACCOUNT_SECURITY |
| DEPT-02 | BILLING | DEPT-07 | COMPLIANCE |
| DEPT-03 | RETURNS_REFUNDS | DEPT-08 | SAFETY |
| DEPT-04 | WARRANTY_CLAIMS | DEPT-09 | MGMT_ESCALATIONS |
| DEPT-05 | CUSTOMER_RELATIONS | | |

## 3. Conventions applied (for consistency across similar records)

1. **Thresholds are respected.** If a severe rule's numeric or conditional trigger is not met, the lower sibling in the same subcategory is used. Triggers include days overdue, hours, PKR value band, >2 inquiries, a legal threat, and >3 complaints.
   - RTO at 9 days → RULE-046, not RULE-047 (>10 days). At >10 days → RULE-047.
   - COD remittance not overdue >7 days and with no legal threat → RULE-037, even at PKR 145,000 or PKR 18.5M.
   - A repeat on the same rude-rider incident stays RULE-067, because RULE-069 needs >3 complaints in 30 days.
2. **Follow-ups keep the base issue's rule unless the facts cross a threshold.** CMP-00343 → 00344: 96 hours with no scan (RULE-059) becomes a lost-parcel claim of PKR 20,000 (RULE-014).
3. **Delays by customer type:**
   - VIP/Premium delays or at-risk deadlines → RULE-100 (executive SLA breach).
   - Corporate-freight and consumer delays under 24 hours → RULE-001. Production or financial impact is context, not a different rule.
   - Life-saving or temperature-sensitive medical cargo, and perishables → RULE-003.
4. **Marked delivered but never received** → RULE-005 (same convention as CMP-00052 in the first 300).
5. **Transit damage by value:** contents damaged in transit under PKR 15,000 → RULE-020. Commercial freight over PKR 100,000 → RULE-021. Outer packaging only, goods intact → RULE-019.
6. **Privacy:**
   - A courier's single-customer privacy breach (WhatsApp, TikTok video, disclosure, exposed CNIC, VIP address) → RULE-079.
   - Mass or online PII exposure → RULE-080.
7. **Security:**
   - Vulnerabilities or credential exposure with no compromise yet → RULE-052.
   - Portal takeover targeting payout bank details → RULE-053.
8. **Rider conduct:**
   - Discourtesy or unprofessional behaviour → RULE-067.
   - Threats, profanity, violence, intimidation, stalking → RULE-068.
   - Withholding service for cash → RULE-071.
9. **Safety:**
   - Unsafe riding or driving → RULE-085.
   - Company-vehicle property damage → RULE-086.
   - Undeclared or toxic chemicals and other critical hazmat → RULE-090.
   - Lithium fire → RULE-089.
   - Small odour or leak → RULE-088.
   - Facility fire hazards → RULE-089 (low confidence).
10. **No-genuine-complaint rows** get the lowest-severity rule in the closest domain:
    - packaging cosmetics → RULE-019
    - rider-manner trivia → RULE-067
    - tracking or app trivia → RULE-058 / RULE-061
    - billing admin → RULE-034
    - merchant routine requests → RULE-055
    - on-time or early deliveries and pure ETA questions → RULE-001, as the first 300 do for "delivered on time"
11. **Frivolous rage.** Rows tagged `angry_low_priority` / `frivolous` are marked no-genuine, whatever the threats or amounts demanded. One exception: **CMP-00472**. It contains an explicit data-deletion request, which is a genuine, actionable RULE-081 erasure request.
12. **Prompt injection.** No record in 301–500 contains prompt-injection text; the injection-style records are all in CMP-00251…00300. The calm-critical and sentiment traps were labelled on substance, not tone.

## 4. Caveats you should know before applying these labels

- **Contextual overrides are not carried over.** 72 of the original 200 records (all tagged `contextual_override`) had urgency and/or priority deliberately set above their rule's default. The CSV's urgency, priority and escalation are **pure rule-derived values**, as requested. If the dataset keeps its override convention, re-apply those overrides on top of the new rule.
- **`primary_issue` is itself wrong in many records.** Many records carry an unrelated template sentence, so decisions were driven by title and description. Examples:
  - CMP-00323 is an API 500 error, but primary_issue says "MFA waiver".
  - CMP-00325 is a fake delivery attempt, but primary_issue says "assembly service".
  - CMP-00333 is pilferage, but primary_issue says "prohibited currency".
  - CMP-00356 is phishing SMS, but primary_issue says "customs seizure".
  - CMP-00371–00400 are safety and harassment incidents, but primary_issue says "rider impolite communication".
  - CMP-00394 is an armed robbery, but primary_issue says "untracked >72 hours".
- **The first 300 are not fully clean.** 56 records in **CMP-00202…CMP-00299** carry the same template → wrong-rule pairs that were corrected here. For example, "Rider lacks exact currency change" is labelled RULE-046 (RTO consolidation), and "Merchant requesting security policy waiver" is labelled RULE-067 (rude rider). The affected IDs are:
  - 202, 204, 205, 207, 208, 210, 211, 213, 214, 217, 220, 221, 223, 225
  - 227, 228, 231, 232, 233, 236, 237, 239, 240, 245, 248, 249, 250, 253
  - 256, 257, 258, 259, 261, 262, 265, 266, 269, 270, 272, 273, 275, 276
  - 278, 279, 281, 282, 284, 285, 287, 290, 291, 293, 294, 295, 298, 299

  These were not relabelled (out of scope), but they are worth a separate pass.
- **Some matrix gaps forced low-confidence picks.** There are no rules for:
  - missed merchant pickups
  - warehouse inventory variance
  - facility, structural or electrical hazards
  - ransomware
  - robbery
  - informational inquiries

## 5. Ten worked examples

**1. CMP-00303 — "Microwave oven arrived with dented side panel in Karachi"** (primary_issue: parcel damaged in transit by carrier handling)
- Original: RULE-015 "High-value consignment lost in transit (>PKR 100,000 or corporate freight)" → LOST_SHIPMENT / LOST_PARCEL / CRITICAL / P0 / CRITICAL_MGMT.
- Proposed: **RULE-020** "Total breakage of fragile contents due to rough transit handling (value < PKR 15,000)" → PRODUCT_DEFECT / DAMAGED_PARCEL / WARRANTY_CLAIMS / HIGH / P1 / SPECIALIST. Confidence medium.
- Why: nothing is lost. The appliance itself was dented, so this is contents damage, not RULE-019's "carton dented, goods undamaged". The follow-up (CMP-00304) puts the claim at PKR 8,000, inside RULE-020's value band.

**2. CMP-00309 — "Parcel marked delivered to wrong address in PECHS Karachi"**
- Original: RULE-049 "Consumer portal account locked after 5 incorrect password attempts" → ACCOUNT / LOW / P3 / NONE.
- Proposed: **RULE-005** "Consignee alleges fake delivery attempt / rider marked delivered … without visiting" → DELIVERY / MISSED_DELIVERY_ATTEMPT / LOGISTICS_OPS / HIGH / P1 / DEPT_MANAGER. Confidence medium.
- Why: the status says delivered but the consignee never received it. This matches the first 300's handling of "status says delivered, not received" (CMP-00052).
- Alternative considered: RULE-022 (wrong parcel via label swap). Rejected because nobody received a wrong item; the right item went to the wrong gate.

**3. CMP-00323 — "VIP Merchant API integration throwing 500 server error"** (primary_issue wrongly says MFA waiver)
- Original: RULE-067 (discourteous rider) → STAFF_BEHAVIOR / MEDIUM / P2 / SUPERVISOR.
- Proposed: **RULE-066** "Enterprise corporate client API gateway completely down, blocking all nationwide bookings" → TECHNICAL_SUPPORT / API_WEBHOOK_FAILURE / CUSTOMER_RELATIONS / CRITICAL / P0 / CRITICAL_MGMT. Confidence medium.
- Why: an enterprise client's order-creation API is failing and its bookings are queued. The follow-up (CMP-00324) confirms 2.5 hours of downtime with 400+ orders stalled, and is rated high confidence.

**4. CMP-00327 — "Customer refused COD parcel not returned to merchant"** (9 days)
- Original: RULE-030 "COD cash discrepancy, customer overpayment >PKR 10,000" → BILLING / HIGH / P1 / DEPT_MANAGER.
- Proposed: **RULE-046** "Failed delivery consignment held in hub awaiting scheduled weekly RTO consolidation" → REFUND / RTO_PROCESSING_DELAY / RETURNS_REFUNDS / LOW / P3 / NONE. Confidence medium.
- Why: this is an RTO delay, not a billing issue. At 9 days it is under RULE-047's ">10 days" trigger. The follow-up CMP-00328 ("exceeded 10 days, tracking dark") crosses the threshold and becomes **RULE-047** (high confidence).

**5. CMP-00344 — "SECOND NOTICE: Untracked parcel still missing"**
- Original: RULE-011 "Parcel dispatched to incorrect province/city" → DELIVERY / WRONG_ROUTE_DISPATCH.
- Proposed: **RULE-014** "Insured shipment lost in transit with declared value PKR 15,000–100,000" → LOST_SHIPMENT / LOST_PARCEL / WARRANTY_CLAIMS / HIGH / P1 / DEPT_MANAGER. Confidence medium.
- Why: there is no misrouting evidence. The parcel has had no scan for 5 full days, and the customer asks for a lost declaration and an insurance claim of PKR 20,000, which falls in RULE-014's band. RULE-013 (<PKR 15,000) is out on value.
- The first contact, CMP-00343 (96 hours), was below the lost-parcel threshold and was labelled RULE-059 (frozen tracking >48h).

**6. CMP-00349 — "VIP Board executive express document consignment delayed"**
- Original: RULE-001 (standard delay) → MEDIUM / P2 / NONE, with a manual override to HIGH / P1.
- Proposed: **RULE-100** "VIP consumer shipment misses guaranteed overnight delivery commitment by 4 hours" → SERVICE_QUALITY / EXECUTIVE_SLA_BREACH / MGMT_ESCALATIONS / HIGH / P1 / SUPERVISOR. Confidence medium.
- Why: the matrix has a dedicated VIP guaranteed-delivery rule, and it yields the HIGH / P1 the author had to force by override.
- The chairman's contract-termination threat in CMP-00350 is not a formal 30-day notice from an account with >PKR 10M annual freight, so RULE-099 does not apply.

**7. CMP-00408 — "VIP Merchant COD Remittance PKR 18.5 Million Blocked in Banking Switch"** (low confidence)
- Original: RULE-024 "Misdelivered parcel contains confidential data / restricted goods" → PRODUCT_DEFECT.
- Proposed: **RULE-037** "Merchant COD remittance delayed past standard Wednesday cycle due to bank holiday" → BILLING / COD_REMITTANCE_DELAY / BILLING / LOW / P3 / NONE.
- Why: this is a bank-side remittance failure in the current cycle. RULE-038 needs >7 days overdue, and RULE-039 needs >PKR 100,000 **with a legal threat**; neither is met.
- Flagged low because the rule's LOW / P3 clearly understates an 18.5M VIP failure. A reviewer may prefer to add a contextual override here.

**8. CMP-00451 — "Courteous notification regarding oncology medication thermal excursion"** (calm-critical trap)
- Original: RULE-020 (fragile breakage) → PRODUCT_DEFECT / HIGH / P1 / SPECIALIST.
- Proposed: **RULE-003** "Delayed delivery containing urgent medical supplies, life-saving drugs or temperature-sensitive goods" → DELIVERY / DELAYED_DELIVERY / LOGISTICS_OPS / CRITICAL / P0 / CRITICAL_MGMT. Confidence high.
- Why: chemotherapy drugs have sat 18 hours in a non-refrigerated bay and denature above 8°C. The polite tone is irrelevant to severity.

**9. CMP-00466 — "BLOOD-BOILING RAGE! RIDER ARRIVED 7 MINUTES AFTER 2:00 PM!"** (angry-low-priority trap)
- Original and proposed: **RULE-001** (kept) → DELIVERY / DELAYED_DELIVERY / LOGISTICS_OPS / MEDIUM / P2 / NONE. **no_genuine_complaint = yes**.
- Why: a 7-minute variance on an intact delivery is immaterial. The legal threats and PKR 1M demand do not change the underlying issue, and RULE-001 is the closest rule.

**10. CMP-00472 — "TREACHERY! DELIVERY SMS USED LOWERCASE 'r' … CANCEL MY ACCOUNT!"**
- Original: RULE-068 (rider profanity / threats) → STAFF_BEHAVIOR / CRITICAL / P0 / CRITICAL_MGMT.
- Proposed: **RULE-081** "Customer requests permanent deletion / erasure of shipping history under privacy rights" → PRIVACY / DATA_PRIVACY_BREACH / ACCOUNT_SECURITY / LOW / P3 / COMPLIANCE_REVIEW. Confidence medium. **no_genuine_complaint = no.**
- Why: the capitalisation grievance is frivolous. But the customer explicitly demands "delete all my data" and account deletion, which is an actionable erasure request. The first 300 label the same kind of request RULE-081 (CMP-00168).

## 6. Validation performed

- 200 rows, IDs CMP-00301…CMP-00500 in order, no duplicates, header exactly as specified.
- Every `proposed_rule_id` (and `original_rule_id`) exists in the 105-rule matrix.
- Every category, subcategory and department code is a value in `raftarxpress_codes.json`. Each subcategory's parent matches its category (`subcategory_parent`).
- Every urgency is in {LOW, MEDIUM, HIGH, CRITICAL}, every priority in {P0, P1, P2, P3}, and every escalation code is on the 6-level ladder. All six matrix escalation strings are mapped; none is unmapped.
- The CSV was re-read after writing and re-checked (row count, header, rule IDs).
