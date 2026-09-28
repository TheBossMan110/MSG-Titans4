# Complaint Resolution Rule Matrix

**SupportNova** · RaftarXpress Logistics (Pvt) Ltd · SRS requirement #5

The rule matrix is the approved complaint-handling logic that Pipeline 2 (the
deterministic Python validator) applies to every complaint. It is authored as
data, loaded into the `rules` table, and never generated at runtime by the
model it checks.

| Deliverable | Path |
|---|---|
| Full matrix, one row per loaded rule (619 rows, 16 columns) | [`backend/reports/rule_matrix.csv`](../reports/rule_matrix.csv) |
| Same rows, plus a per-case view and a summary sheet | [`backend/reports/rule_matrix.xlsx`](../reports/rule_matrix.xlsx) |
| Reproducible exporter (reads YAML only, no database) | [`backend/scripts/export_rule_matrix.py`](../scripts/export_rule_matrix.py) |
| Rule sources the engine loads | `backend/complaint_rules/*.yaml`, `backend/routing_rules/*.yaml`, `backend/escalation_rules/*.yaml` |
| Authored source of the 105 case rules | `dataset/raftarxpress/configuration/complaint_resolution_rules.json` |

Regenerate the export at any time:

```bash
cd backend
.venv\Scripts\python.exe scripts\export_rule_matrix.py          # writes reports/rule_matrix.csv and .xlsx
.venv\Scripts\python.exe scripts\export_rule_matrix.py --out DIR
```

The script prints the counts below and exits non-zero if it finds a problem the
loader would reject (a missing or duplicate `rule_ref`). The export shown here
was produced on 27 September 2026 with ruleset checksum
`004880e57af6…` (first eight characters `004880e5`).

---

## 1. Columns

The CSV and the "Rule Matrix" sheet carry exactly the twelve columns the SRS
lists, in its order, followed by four that the YAML also provides.

| Column | Taken from | Notes |
|---|---|---|
| Rule ID | `rule_ref` | Unique across all files (the loader rejects duplicates). |
| Category | `then.category` | Taxonomy code, e.g. `DELIVERY`. |
| Subcategory | `then.subcategory` | Taxonomy code, e.g. `DELAYED_DELIVERY`. |
| Conditions | `when` (+ `scope`) | The condition tree rendered as a boolean expression, then `--` and the authored prose the rule is named after. |
| Department | `then.department`, `then.support_department` | Owning department; a supporting department appears as `support: CODE`. |
| Urgency | `then.urgency` | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL`. |
| Priority | `then.priority` | `P0`–`P3`. |
| Policy | `then.policy_refs`, `eligibility` | Cited sections as `DOC-nnn-Sn`. For ELIGIBILITY rules, also the entitlement verdict (`REFUND: REQUIRES_VERIFICATION`, and whether human approval is required). |
| Escalation | `then.escalation`, `mandatory_escalation` | `(mandatory floor)` marks a level the engine may raise but never lower. |
| Required actions | `then.required_actions` | Separated by ` \| ` in the CSV, by line breaks in the XLSX. |
| Prohibited actions | `then.prohibited_actions` | As above. |
| Follow-up | `then.follow_up_required` | `Yes` where the YAML sets it; blank otherwise (see §7.1). |
| Rule type | `rule_type` | CLASSIFICATION, ESCALATION, RESOLUTION, ELIGIBILITY or ROUTING. |
| Precedence | `precedence` | Higher wins. File default 50 if absent (none is absent). |
| Version | file-level `version` | `1.0` for all five files. The integer `rules.version` in the database increments on every reseed and is not in the files. |
| Active | `active` (default true) | All 619 are active. |

**Blank means the rule does not set that field.** Nothing is copied from
another rule on the "Rule Matrix" sheet. A RESOLUTION rule, for instance, has
no category of its own: it carries obligations, and the category comes from
the CLASSIFICATION rule that fires with it.

### The "By Case" sheet

Because one authored case is split across several rules (§3), the XLSX adds a
**By Case** sheet with one row per case (116 rows). Each row merges the rules
of one lineage — for example `RULE-002`, `ESC-002`, `RES-002` and
`ELG-002-{COMP,REFU,REPL}` — using the engine's own merge semantics (§5):
scalar fields from the highest-precedence rule that sets them, actions and
policy references unioned, escalation raised to the mandatory floor. It shows
what a case's own rules produce when they fire together; at runtime other
rules (safety, legal, repeat-contact) may fire alongside and change the
outcome. The "Rule ID" cell lists every rule the row was built from.

---

## 2. How many rules, and why 619

The five YAML files hold **619 rules, all active**, which is the figure the
live system reports, so there is no difference to explain. Equal counts mean
no rule was rejected at load time (the exporter itself checks only what needs
no database: every `rule_ref` present and unique), and the loader deactivates
any database rule whose `rule_ref` is no longer in the files, so after a seed
the active set is exactly the file set. A rule added or deactivated live
through the admin API after seeding would make the two differ; the files
alone cannot show that. The `*.zenithra.bak` backups beside the YAML do not
match the loader's `*.yaml` glob and are not loaded.

| File | Rule type | Rules |
|---|---|---:|
| `complaint_rules/classification.yaml` | CLASSIFICATION | 107 |
| `complaint_rules/eligibility.yaml` | ELIGIBILITY | 322 |
| `complaint_rules/resolution.yaml` | RESOLUTION | 115 |
| `routing_rules/departments.yaml` | ROUTING | 1 |
| `escalation_rules/mandatory.yaml` | ESCALATION | 74 |
| **Total** | | **619** |

The 619 are generated variants of 105 authored cases plus a small set of
cross-cutting rules:

| Origin | CLASSIFICATION | ESCALATION | RESOLUTION | ELIGIBILITY | ROUTING | Total |
|---|---:|---:|---:|---:|---:|---:|
| 105 authored cases `RULE-001`…`RULE-105` | 105 | 67 | 105 | 315 | – | 592 |
| Safety bridge `SAF-0001`, `SAF-0002` | 2 | 2 | 2 | 4 | – | 10 |
| Cross-cutting `LEG`, `REG`, `URG`, `INJ`, `REP` (`-0001`) | – | 5 | 5 | – | – | 10 |
| Refund stance (`*-STANCE-*`, 3 refund topics) | – | – | 3 | 3 | – | 6 |
| Catch-all `RTE-0001` | – | – | – | – | 1 | 1 |
| **Total** | **107** | **74** | **115** | **322** | **1** | **619** |

* **67 escalation floors** from the authored cases: one `ESC-nnn` for every
  case marked `is_mandatory_escalation` with a level other than *No
  Escalation* (32 Critical Management, 19 Supervisor, 10 Department Manager,
  6 Specialist).
* **315 eligibility rules** = 105 cases × 3 entitlements (refund,
  replacement, compensation). "No" becomes `NOT_ELIGIBLE`, "Yes" `ELIGIBLE`,
  and "Conditional" `REQUIRES_VERIFICATION` with human approval required.
* **74 mandatory escalation floors in total** (67 + 2 safety + 5
  cross-cutting): 34 at `CRITICAL_MGMT`, 21 at `SUPERVISOR`, 10 at
  `DEPT_MANAGER`, 7 at `SPECIALIST`, 2 at `COMPLIANCE_REVIEW`.
* **1 catch-all** (`RTE-0001`), 81 rules with Follow-up = Yes, 144 distinct
  signals referenced, 19 knowledge-base documents cited.

---

## 3. How rules are authored

1. **The case matrix** is written in
   `dataset/raftarxpress/configuration/complaint_resolution_rules.json`:
   105 rules, each with its conditions (prose), category, subcategory,
   department and supporting department, urgency, priority, escalation level,
   `is_mandatory_escalation`, required and prohibited actions,
   `follow_up_required`, refund / replacement / compensation eligibility and a
   policy reference (`DOC-nnn-Sn`). All 34 subcategories are covered.
2. **`backend/scripts/convert_raftarxpress.py`** turns each case into
   separate rules, one concern per file, so a reviewer can read one file to
   see all escalation floors or all obligations:
   * `RULE-nnn` (classification) — precedence `60 + 3 × escalation rank`, so
     inside a subcategory the more severe reading wins (60 for no escalation,
     up to 75 for Critical Management).
   * `RES-nnn` (resolution obligations) — precedence 60.
   * `ESC-nnn` (mandatory floor) — only for mandatory cases; precedence
     `100 + 3 × rank` (103–115), and the only file allowed to set
     `mandatory_escalation: true`.
   * `ELG-nnn-REFU/REPL/COMP` (eligibility) — precedence 60.
3. **Conditions are signals**, not free text. Each subcategory has a topic
   signal (`delayed_delivery_terms`) and each case an evidence signal
   (`rule_002_evidence`) that separates it from its siblings. The least severe
   case in each subcategory (34 "baseline" rules) fires on the topic alone;
   the others need topic **and** evidence. Signal vocabularies live in
   `config/signals.yaml` (derived from the taxonomy and the rule prose) and
   `config/authored_lexicon.yaml` (hand-written). Neither is derived from the
   complaint corpus, so the rules are not fitted to the set they are scored
   against.
4. **Cross-cutting rules** are written in the converter itself rather than in
   the case matrix, because they cut across subcategories:
   * `SAF-0001` / `SAF-0002` — a physical hazard is `SAFETY`/`P0` with a
     `CRITICAL_MGMT` floor however calmly it is reported (SRS 1.8 #6); the
     injury variant ranks above it.
   * `LEG-0001` (legal threat → `COMPLIANCE_REVIEW`), `REG-0001` (regulator
     involved → `COMPLIANCE_REVIEW`), `URG-0001` (time-critical contents →
     `SPECIALIST`), `INJ-0001` (intake flagged a prompt injection →
     `SUPERVISOR`), `REP-0001` (third unresolved contact → `SUPERVISOR`).
   * `RES-STANCE-*` / `ELG-STANCE-*` — on any refund topic a refund is
     `REQUIRES_VERIFICATION` and may not be confirmed at the desk (SRS 1.8 #9).
   * `RTE-0001` — the catch-all.

The generated YAML carries a header saying so: edit the dataset and re-run the
converter rather than hand-editing. Administrators can also tune rules live at
**Admin → Resolution Rules / Routing Rules / Escalation Rules**
(`/api/admin/rules`), which refuses a condition naming a signal no lexicon
term raises. Such live edits change the database, not the YAML; this export
shows the files.

---

## 4. How rules are loaded

`src/db/seed/rules.py` (run by `python -m src.db.seed.run`) is the only path
from the files into the `rules` table:

* Files are read in a fixed order: `complaint_rules/`, `routing_rules/`,
  `escalation_rules/`, each directory's `*.yaml` sorted by name. The exporter
  uses the same order.
* Each rule is **validated before it is stored**: the condition tree is
  structurally checked; every signal it names must exist as a lexicon term;
  every category, subcategory, department, priority and escalation code must
  resolve; `rule_ref` must be unique across files; a mandatory rule must name
  an escalation level ("a floor with no height cannot be enforced"). A rule
  that fails is **not loaded** and the failure is reported, rather than
  loading a rule that would silently never fire.
* Loading is idempotent: an existing rule is updated and its integer version
  incremented; a database rule absent from the files is **deactivated, not
  deleted**, so a live admin edit is never silently destroyed.
* A new `ruleset_version` is stamped as `YYYY.MM.DD-<first 8 of sha256>`,
  where the checksum is taken over the raw file text in load order. Every
  validation run records it, so a past result can be tied to the exact rules
  that produced it. The exporter computes the same checksum
  (`004880e5` for these files); a database seeded from these files should
  carry that suffix.

---

## 5. How rules are applied

`python_validation/pipeline.py` loads the active rules (ordered by precedence,
highest first) and `python_validation/rule_engine.py` evaluates them against
the complaint's signals. The GenAI result is not an input: the engine reaches
its conclusion from the complaint alone.

1. **Matching.** Each rule's condition is evaluated against the rule-visible
   signals (sentiment and tone are recorded but cannot reach a rule), derived
   facts such as `repeat_count`, and complaint fields such as
   `injection_suspected`. Conditions are interpreted, never `eval()`-ed; a
   malformed rule evaluates to false and is reported. The pipeline runs up to
   two passes so that category-scoped rules can see the category found in the
   first (no current rule is scoped).
2. **Precedence.** For each scalar field (category, subcategory, department,
   supporting department, urgency, priority, escalation) the
   highest-precedence matching rule that sets the field wins.

   | Band | Rules |
   |---:|---|
   | 5 | `RTE-0001` catch-all |
   | 60 | classification of cases with no escalation level, all `RES-nnn` and `ELG-nnn-*` |
   | 63–75 | classification of cases with an escalation level (`60 + 3 × rank`) |
   | 90 | refund stance |
   | 103–115 | case escalation floors (`100 + 3 × rank`) |
   | 118–128 | cross-cutting: REP 118, LEG 120, INJ 122, REG 125, URG 128 |
   | 130 / 135 | `SAF-0001` / `SAF-0002` (and their RES/ELG) |
   | 140 / 145 | `ESC-SAF-0001` / `ESC-SAF-0002` |

3. **Conflicts.** Two matching rules at the *same* precedence that disagree on
   a field are recorded as a conflict. Urgency, priority and escalation
   resolve to the more severe value; other fields resolve deterministically
   by `rule_ref`; either way the complaint is routed for human review
   (`RULE_CONFLICT`). Nothing is resolved silently.
4. **Obligations are unioned.** Required actions, prohibited actions and
   policy references are the union over every matching rule, so a
   prohibition from a lower-precedence rule cannot be cancelled by a
   higher-precedence rule that is silent on it. A required action is stored
   against the complaint as outstanding until an agent confirms it.
   Follow-up is required if any matching rule requires it.
5. **Catch-all.** `RTE-0001` (`always: true`, precedence 5) gives an
   unrecognised complaint an owner (Customer Relations, MEDIUM, P2), but if it
   is the only rule that matched the complaint stays `unmatched` and goes to
   manual review (`RULE_UNMATCHED`). When any substantive rule matches, the
   catch-all's hit is kept in the trace but its outcome is withdrawn. A
   complaint for which no rule derives a category is also `unmatched`.
6. **Mandatory escalation floors.** After merging, the engine takes the
   highest-ranked level demanded by any matching mandatory rule and raises
   the outcome to it (SRS 1.8 #7). The ladder, from `config/taxonomy.yaml`,
   is `NONE` 0 · `SUPERVISOR` 1 · `DEPT_MANAGER` 2 · `SPECIALIST` 3 ·
   `COMPLIANCE_REVIEW` 4 · `CRITICAL_MGMT` 5. Reconciliation with the GenAI
   pipeline, the reviewer UI and the response guard may raise the final
   level but can never lower it below the floor.
7. **Eligibility.** ELIGIBILITY rules record `ELIGIBLE`, `NOT_ELIGIBLE` or
   `REQUIRES_VERIFICATION` per entitlement. Only an explicit `ELIGIBLE`
   authorises a promise: the response guard treats a refund, replacement or
   compensation promise in the reply as unsupported unless Pipeline 2 derived
   that verdict (`config/policy.yaml`: regenerate once, then human review).

Every matched rule is kept with the signals and text spans that made it
match, together with its rationale. That trace is what the explainability
panel renders: the rule, why it exists, and the words in the complaint that
triggered it.

---

## 6. Representative excerpt

### 6.1 By case (33 of 116 cases)

27 authored cases covering all 13 categories, the safety bridge, three
cross-cutting rules, a refund-stance rule and the catch-all, taken from the
"By Case" sheet.
Required and prohibited actions are separated by `;` here.

| Rule ID | Category | Subcategory | Conditions | Department | Urgency | Priority | Policy | Escalation | Required actions | Prohibited actions | Follow-up |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RULE-001, RES-001, ELG-001-{COMP,REFU,REPL} | DELIVERY | DELAYED_DELIVERY | RULE-001: delayed_delivery_terms; RES-001, ELG-001-COMP, ELG-001-REFU, ELG-001-REPL: delayed_delivery_terms AND rule_001_evidence<br>Standard domestic transit delay under 24 hours without perishable contents | LOGISTICS_OPS | MEDIUM | P2 | DOC-003-S1<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Check hub GPS scan history; Notify destination delivery hub; Send SMS update to consignee | Guarantee delivery time before hub dispatch confirmation; Cancel consignment unilaterally | Yes |
| RULE-002, ESC-002, RES-002, ELG-002-{COMP,REFU,REPL} | DELIVERY | DELAYED_DELIVERY | delayed_delivery_terms AND rule_002_evidence<br>Transit delay exceeding 72 hours with repeated customer inquiries (>2 times) | LOGISTICS_OPS | HIGH | P1 | DOC-016-S1<br>Eligibility: Compensation: REQUIRES_VERIFICATION (human approval); Refund: REQUIRES_VERIFICATION (human approval); Replacement: NOT_ELIGIBLE | SUPERVISOR (mandatory floor) | Flag consignment as priority linehaul search; Issue intermediate tracking SMS to consignee; Request hub physical shelf audit | Promise compensation before verification; Mark ticket resolved while parcel remains in transit | Yes |
| RULE-003, ESC-003, RES-003, ELG-003-{COMP,REFU,REPL} | DELIVERY | DELAYED_DELIVERY | delayed_delivery_terms AND rule_003_evidence<br>Delayed delivery containing urgent medical supplies, life-saving drugs or temperature-sensitive goods | LOGISTICS_OPS | CRITICAL | P0 | DOC-018-S1<br>Eligibility: Compensation: ELIGIBLE; Refund: REQUIRES_VERIFICATION (human approval); Replacement: ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Initiate emergency same-day dedicated vehicle dispatch; Alert Regional Operations Director; Coordinate direct telephone line with receiving hospital/patient | Route through standard overnight batch queue; Dismiss as routine delay | Yes |
| RULE-005, ESC-005, RES-005, ELG-005-{COMP,REFU,REPL} | DELIVERY | MISSED_DELIVERY_ATTEMPT | missed_delivery_attempt_terms AND rule_005_evidence<br>Consignee alleges fake delivery attempt / rider marked delivered or attempted without visiting | LOGISTICS_OPS | HIGH | P1 | DOC-020-S1<br>Eligibility: Compensation: REQUIRES_VERIFICATION (human approval); Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE | DEPT_MANAGER (mandatory floor) | Cross-reference rider GPS breadcrumb logs with delivery address; Interview route courier; Reschedule priority morning delivery window | Dismiss customer claim without reviewing GPS audit; Blame consignee for missed call without call log review | Yes |
| RULE-006, RES-006, ELG-006-{COMP,REFU,REPL} | DELIVERY | MISSED_DELIVERY_ATTEMPT | missed_delivery_attempt_terms AND rule_006_evidence<br>Third consecutive missed delivery attempt reaching maximum quota threshold | LOGISTICS_OPS; support: RETURNS_REFUNDS | MEDIUM | P2 | DOC-003-S4<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: REQUIRES_VERIFICATION (human approval); Replacement: NOT_ELIGIBLE |  | Move parcel to 48-hour hub retention bay; Call consignee directly from customer support desk; Notify merchant of impending RTO status | Dispose of shipment; Return to origin before mandatory 48h holding period | Yes |
| RULE-013, RES-013, ELG-013-{COMP,REFU,REPL} | LOST_SHIPMENT | LOST_PARCEL | lost_parcel_terms AND rule_013_evidence<br>Standard parcel missing scan for >5 days, declared value under PKR 15,000 | WARRANTY_CLAIMS; support: LOGISTICS_OPS | HIGH | P1 | DOC-007-S1<br>Eligibility: Compensation: ELIGIBLE; Refund: ELIGIBLE; Replacement: ELIGIBLE |  | Trigger 48-hour all-hub physical inventory search; Request merchant commercial invoice and packing list; Initiate standard indemnity processing upon search expiry | Promise instant cash payout before completing 48h search; Refuse claim filed within 14-day window | Yes |
| RULE-019, RES-019, ELG-019-{COMP,REFU,REPL} | PRODUCT_DEFECT | DAMAGED_PARCEL | RULE-019: damaged_parcel_terms; RES-019, ELG-019-COMP, ELG-019-REFU, ELG-019-REPL: damaged_parcel_terms AND rule_019_evidence<br>Minor outer carton denting with internal goods completely undamaged | WARRANTY_CLAIMS | LOW | P3 | DOC-007-S4<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Inspect customer unboxing photographic evidence; Log delivery feedback for packing improvement; Close inquiry with polite reassurance | Authorize product replacement when contents are 100% intact |  |
| RULE-026, ESC-026, RES-026, ELG-026-{COMP,REFU,REPL} | PRODUCT_DEFECT | TAMPERED_PACKAGING | tampered_packaging_terms AND rule_026_evidence<br>Parcel cut open and high-value item replaced with dummy weight / counterfeit goods | ACCOUNT_SECURITY | CRITICAL | P0 | DOC-006-S1<br>Eligibility: Compensation: ELIGIBLE; Refund: ELIGIBLE; Replacement: ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Quarantine parcel packaging for forensic inspection; Conduct immediate audit of linehaul drivers and hub handlers; File formal internal anti-fraud incident report | Return tampered box to shipper without photographing evidence; Accuse customer of self-tampering without proof | Yes |
| RULE-031, RES-031, ELG-031-{COMP,REFU,REPL} | BILLING | DUPLICATE_CHARGE | RULE-031: duplicate_charge_terms; RES-031, ELG-031-COMP, ELG-031-REFU, ELG-031-REPL: duplicate_charge_terms AND rule_031_evidence<br>Customer online portal shows two identical invoice charges for a single consignment booking | BILLING | MEDIUM | P2 | DOC-013-S3<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Verify payment gateway transaction logs against CN number; Confirm second charge is a duplicate capture; Trigger automated gateway refund reversal within 48 hours | Force customer to dispute charge through external bank chargeback; Deny duplicate charge when transaction IDs match | Yes |
| RULE-039, ESC-039, RES-039, ELG-039-{COMP,REFU,REPL} | BILLING | COD_REMITTANCE_DELAY | cod_remittance_delay_terms AND rule_039_evidence<br>Unresolved COD remittance withheld exceeding PKR 100,000 with legal threat from merchant | BILLING | CRITICAL | P0 | DOC-016-S2<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: ELIGIBLE; Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Conduct emergency financial audit with Finance Director; Engage Legal Counsel (DEPT-07) for merchant dialogue; Execute verified funds transfer within 12 hours | Engage in informal arguments with merchant legal counsel; Freeze merchant account out of retaliation | Yes |
| RULE-040, RES-040, ELG-040-{COMP,REFU,REPL} | REFUND | REFUND_NOT_PROCESSED | RULE-040: refund_not_processed_terms; RES-040, ELG-040-COMP, ELG-040-REFU, ELG-040-REPL: refund_not_processed_terms AND rule_040_evidence<br>Customer refund requested within 7-day policy window, all documentation verified | RETURNS_REFUNDS; support: BILLING | MEDIUM | P2 | DOC-001-S2<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Verify CN delivery status and original payment mode; Submit IBFT payment voucher to Finance queue; Notify customer of 5-7 banking days disbursement timeline | Promise same-day cash payout; Require unnecessary in-person hub visits | Yes |
| RULE-041, ESC-041, RES-041, ELG-041-{COMP,REFU,REPL} | REFUND | REFUND_NOT_PROCESSED | refund_not_processed_terms AND rule_041_evidence<br>Refund request submitted on day 8 (past 7-day window) citing genuine medical emergency | RETURNS_REFUNDS | MEDIUM | P2 | DOC-001-S2<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: REQUIRES_VERIFICATION (human approval); Replacement: NOT_ELIGIBLE | SUPERVISOR (mandatory floor) | Review customer exemption rationale and supporting documents; Submit one-time policy exception request to Customer Experience Director; Process refund if authorized under discretionary allowance | Grant policy exception without documented supervisor approval; Rudely reject without evaluating circumstances | Yes |
| RULE-053, ESC-053, RES-053, ELG-053-{COMP,REFU,REPL} | ACCOUNT | UNAUTHORIZED_ACCOUNT_ACCESS | unauthorized_account_access_terms AND rule_053_evidence<br>Merchant portal compromised and bank disbursement details altered to fraudulent account | ACCOUNT_SECURITY | CRITICAL | P0 | DOC-015-S1<br>Eligibility: Compensation: ELIGIBLE; Refund: ELIGIBLE; Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Freeze all outgoing COD remittances instantly; Lock merchant profile and restore verified banking records; Alert Head of Information Security and Banking Operations | Allow pending IBFT payouts to proceed while bank details are contested; Blame merchant before securing financial assets | Yes |
| RULE-056, RES-056, ELG-056-{COMP,REFU,REPL} | ACCOUNT | MERCHANT_PROFILE_UPDATE | merchant_profile_update_terms AND rule_056_evidence<br>Merchant requests legal company title change and NTN/Sales Tax registration update | CUSTOMER_RELATIONS; support: COMPLIANCE | MEDIUM | P2 | DOC-021-S1<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Collect updated FBR NTN certificate and SECP incorporation form; Submit legal documents to Compliance (DEPT-07) for validation; Update ERP billing ledger title upon compliance sign-off | Update tax entity details without verified FBR documentation | Yes |
| RULE-058, RES-058, ELG-058-{COMP,REFU,REPL} | TECHNICAL_SUPPORT | TRACKING_NOT_UPDATING | RULE-058: tracking_not_updating_terms; RES-058, ELG-058-COMP, ELG-058-REFU, ELG-058-REPL: tracking_not_updating_terms AND rule_058_evidence<br>Consignment tracking scan stationary for 12 hours during overnight inter-city linehaul | CUSTOMER_RELATIONS | LOW | P3 | DOC-019-S1<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Verify linehaul truck departure and estimated hub arrival time; Explain linehaul transit scan cycle to customer; Provide estimated timestamp for next destination scan | Declare parcel lost prematurely during routine linehaul transit |  |
| RULE-066, ESC-066, RES-066, ELG-066-{COMP,REFU,REPL} | TECHNICAL_SUPPORT | API_WEBHOOK_FAILURE | api_webhook_failure_terms AND rule_066_evidence<br>Enterprise corporate client API gateway completely down, blocking all nationwide bookings | CUSTOMER_RELATIONS | CRITICAL | P0 | DOC-016-S2<br>Eligibility: Compensation: ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Activate enterprise failover API endpoint and bypass proxy; Convene emergency bridge with Enterprise Client CTO; Execute automated retroactive sync once gateway is restored | Leave enterprise bookings queued without executive alert | Yes |
| RULE-067, RES-067, ELG-067-{COMP,REFU,REPL} | STAFF_BEHAVIOR | RUDE_RIDER_DRIVER_BEHAVIOR | RULE-067: rude_rider_driver_behavior_terms; RES-067, ELG-067-COMP, ELG-067-REFU, ELG-067-REPL: rude_rider_driver_behavior_terms AND rule_067_evidence<br>Customer reports rider spoke discourteously or showed impatient attitude during delivery | LOGISTICS_OPS; support: CUSTOMER_RELATIONS | MEDIUM | P2 | DOC-020-S1<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Call customer to convey formal company apology; Counsel courier regarding professional service standards; Log behavioral warning in rider performance scorecard | Confront customer aggressively to defend rider; Share customer contact with rider for private argument | Yes |
| RULE-071, ESC-071, RES-071, ELG-071-{COMP,REFU,REPL} | STAFF_BEHAVIOR | RIDER_DEMANDING_CASH_TIP | rider_demanding_cash_tip_terms AND rule_071_evidence<br>Rider refuses to release prepaid parcel unless customer pays unauthorized cash fee | ACCOUNT_SECURITY | CRITICAL | P0 | DOC-021-S2<br>Eligibility: Compensation: ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Dispatch supervisor to customer address for immediate parcel handover; Offboard courier and confiscate company device and cash bag; Initiate recovery of illicitly collected funds | Force customer to negotiate cash with rogue courier; Delay parcel release pending courier interview | Yes |
| RULE-077, ESC-077, RES-077, ELG-077-{COMP,REFU,REPL} | WARRANTY | INSURANCE_PAYOUT_DELAY | insurance_payout_delay_terms AND rule_077_evidence<br>Insured payout delayed past 30 days due to missing underwriter surveyor sign-off | WARRANTY_CLAIMS | HIGH | P1 | DOC-007-S3<br>Eligibility: Compensation: REQUIRES_VERIFICATION (human approval); Refund: ELIGIBLE; Replacement: NOT_ELIGIBLE | SPECIALIST (mandatory floor) | Issue urgent demand letter to third-party insurance underwriter; Release 50% advance compensation from company reserve if underwriter is stalled; Update customer weekly with claims tracking log | Leave customer waiting without tracking or insurance updates | Yes |
| RULE-080, ESC-080, RES-080, ELG-080-{COMP,REFU,REPL} | PRIVACY | DATA_PRIVACY_BREACH | data_privacy_breach_terms AND rule_080_evidence<br>Merchant manifests containing 500+ customer names and phone numbers leaked online or sent to wrong client | ACCOUNT_SECURITY | CRITICAL | P0 | DOC-015-S1<br>Eligibility: Compensation: ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Execute emergency containment and take down exposed URL / file links; Notify Chief Information Security Officer and Legal Counsel within 1 hour; Issue formal statutory breach disclosure and notify affected data subjects | Conceal data breach from impacted customers and regulators; Delete audit logs to obscure breach origin | Yes |
| RULE-082, RES-082, ELG-082-{COMP,REFU,REPL} | PRIVACY | UNSOLICITED_MARKETING_SMS | RULE-082: unsolicited_marketing_sms_terms; RES-082, ELG-082-COMP, ELG-082-REFU, ELG-082-REPL: unsolicited_marketing_sms_terms AND rule_082_evidence<br>Customer requests opt-out from promotional broadcast SMS marketing campaigns | COMPLIANCE | LOW | P3 | DOC-015-S2<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Add phone number to nationwide Do-Not-Call / Do-Not-SMS suppression list; Send automated opt-out confirmation message within 24 hours | Continue sending promotional SMS to opted-out numbers |  |
| RULE-085, ESC-085, RES-085, ELG-085-{COMP,REFU,REPL} | SAFETY | RECKLESS_DRIVING_SAFETY_RISK | RULE-085: reckless_driving_safety_risk_terms; ESC-085, RES-085, ELG-085-COMP, ELG-085-REFU, ELG-085-REPL: reckless_driving_safety_risk_terms AND rule_085_evidence<br>Citizen reports courier van driving recklessly / speeding in residential neighborhood | SAFETY | HIGH | P1 | DOC-025-S2<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE | SUPERVISOR (mandatory floor) | Retrieve vehicle GPS telematics and speed-monitoring logs; Identify driver and issue formal safety warning and speeding deduction; Send acknowledgement and appreciation note to reporting citizen | Ignore reckless driving report if no physical damage was done |  |
| RULE-089, ESC-089, RES-089, ELG-089-{COMP,REFU,REPL} | SAFETY | HAZARDOUS_MATERIAL_MISHANDLING | hazardous_material_mishandling_terms AND rule_089_evidence<br>Consignment of undeclared lithium batteries catches fire / emits smoke in regional sortation center | SAFETY | CRITICAL | P0 | DOC-025-S2<br>Eligibility: Compensation: ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Evacuate sorting floor and deploy specialized chemical fire extinguishers; Isolate affected cargo container in outdoor fire-safe zone; Notify fire department and initiate emergency investigation against shipper | Attempt to handle smoking lithium batteries with bare hands; Resume sortation before safety clearance | Yes |
| RULE-091, RES-091, ELG-091-{COMP,REFU,REPL} | CUSTOMS | MISSING_CUSTOMS_DOCUMENTS | RULE-091: missing_customs_documents_terms; RES-091, ELG-091-COMP, ELG-091-REFU, ELG-091-REPL: missing_customs_documents_terms AND rule_091_evidence<br>Inter-provincial consignment missing commercial invoice copy in outer pouch; digital copy on file | COMPLIANCE | MEDIUM | P2 | DOC-024-S1<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Print digital invoice copy from SupportNova booking database; Attach reprint to parcel documentation pouch at transit hub; Authorize shipment release for next linehaul departure | Hold shipment indefinitely when digital invoice is verified on file |  |
| RULE-096, ESC-096, RES-096, ELG-096-{COMP,REFU,REPL} | CUSTOMS | REGULATORY_IMPOUNDMENT_HOLD | regulatory_impoundment_hold_terms AND rule_096_evidence<br>Mass regulatory seizure of entire linehaul container valued at > PKR 5,000,000 | COMPLIANCE | CRITICAL | P0 | DOC-016-S2<br>Eligibility: Compensation: ELIGIBLE; Refund: REQUIRES_VERIFICATION (human approval); Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Assemble executive crisis team with General Legal Counsel; File urgent petition for release of legitimate third-party commercial cargo; Engage directly with Federal Board of Revenue high commission | Conceal mass seizure from affected corporate clients | Yes |
| RULE-097, RES-097, ELG-097-{COMP,REFU,REPL} | SERVICE_QUALITY | SUBSCRIPTION_CONTRACT_RENEWAL | RULE-097: subscription_contract_renewal_terms; RES-097, ELG-097-COMP, ELG-097-REFU, ELG-097-REPL: subscription_contract_renewal_terms AND rule_097_evidence<br>Corporate freight client requests routine annual rate review and SLA contract renewal | CUSTOMER_RELATIONS | LOW | P3 | DOC-020-S2<br>Eligibility: Compensation: NOT_ELIGIBLE; Refund: NOT_ELIGIBLE; Replacement: NOT_ELIGIBLE |  | Generate annual shipping volume and revenue summary report; Schedule contract review meeting with corporate account manager; Draft revised corporate tariff addendum based on standard pricing matrix | Unilaterally alter contracted rates without signed contract addendum |  |
| RULE-102, ESC-102, RES-102, ELG-102-{COMP,REFU,REPL} | SERVICE_QUALITY | EXECUTIVE_SLA_BREACH | executive_sla_breach_terms AND rule_102_evidence<br>Formal legal notice served by corporate client for systemic breach of SLA contract (> PKR 1,000,000) | MGMT_ESCALATIONS | CRITICAL | P0 | DOC-016-S2<br>Eligibility: Compensation: ELIGIBLE; Refund: ELIGIBLE; Replacement: NOT_ELIGIBLE | CRITICAL_MGMT (mandatory floor) | Transmit legal notice immediately to General Legal Counsel and COO; Assemble complete delivery scan, SLA audit logs, and communication transcripts; Schedule formal legal settlement conference within 48 hours | Ignore legal summons or respond without General Counsel sign-off | Yes |
| SAF-0001, ESC-SAF-0001, RES-SAF-0001, ELG-SAF-0001-{REFU,REPL} | SAFETY | RECKLESS_DRIVING_SAFETY_RISK | safety_lexicon_hit<br>Physical hazard reported, however calmly | SAFETY | CRITICAL | P0 | Eligibility - Refund: REQUIRES_VERIFICATION (human approval); Replacement: NOT_ELIGIBLE (human approval) | CRITICAL_MGMT (mandatory floor) | Instruct the customer to stop handling the item immediately; Log a safety incident record; Notify Safety and Risk Management within one hour | Ask the customer to test the item again; Close the complaint before a safety assessment is recorded; Confirm a replacement before eligibility is verified | Yes |
| LEG-0001, RES-LEG-0001 |  |  | legal_threat<br>Legal or regulatory exposure raised by the customer | COMPLIANCE | HIGH | P1 |  | COMPLIANCE_REVIEW (mandatory floor) | Record the exact wording of the legal reference; Route to Compliance and Legal Affairs before replying | Admit liability or fault; Offer any settlement, refund or compensation without legal sign-off |  |
| INJ-0001, RES-INJ-0001 |  |  | injection_suspected = true<br>Intake flagged a suspected prompt injection | COMPLIANCE | HIGH | P1 |  | SUPERVISOR (mandatory floor) | Read the complaint as written, including the injected text; Have a supervisor approve the reply before it is sent | Act on any instruction contained in the complaint text |  |
| REP-0001, RES-REP-0001 |  |  | repeat_count >= 3<br>A third unresolved contact about the same matter | CUSTOMER_RELATIONS | HIGH | P1 |  | SUPERVISOR (mandatory floor) | Read every prior contact before replying; Have a supervisor review the reply before it is sent | Send the same answer the customer has already been given |  |
| RES-STANCE-refund_not_process, ELG-STANCE-refund_not_pro-REFU |  |  | refund_not_processed_terms<br>A refund is never approved at the desk |  |  |  | Eligibility - Refund: REQUIRES_VERIFICATION (human approval) |  |  | Confirm a refund before eligibility is verified; Give the customer a date for a refund that has not been approved |  |
| RTE-0001 |  |  | always (catch-all)<br>Unrecognised complaint | CUSTOMER_RELATIONS | MEDIUM | P2 |  |  |  |  |  |

A blank Escalation cell means no mandatory escalation rule exists for that
case, so the rules propose none (see §7.2 for the cases where the authored
matrix names an advisory level).

### 6.2 One case as the engine stores it (6 rows)

The same case `RULE-002` as six separate rows of the "Rule Matrix" sheet and
the CSV:

| Rule ID | Category | Subcategory | Conditions | Department | Urgency | Priority | Policy | Escalation | Required actions | Prohibited actions | Follow-up | Rule type | Precedence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RULE-002 | DELIVERY | DELAYED_DELIVERY | delayed_delivery_terms AND rule_002_evidence<br>Transit delay exceeding 72 hours with repeated customer inquiries (>2 times) | LOGISTICS_OPS; support: CUSTOMER_RELATIONS | HIGH | P1 | DOC-016-S1 |  |  |  | Yes | CLASSIFICATION | 63 |
| ESC-002 |  |  | delayed_delivery_terms AND rule_002_evidence<br>Transit delay exceeding 72 hours with repeated customer inquiries (>2 times) | LOGISTICS_OPS | HIGH | P1 | DOC-016-S1 | SUPERVISOR (mandatory floor) |  |  |  | ESCALATION | 103 |
| RES-002 |  |  | delayed_delivery_terms AND rule_002_evidence<br>Transit delay exceeding 72 hours with repeated customer inquiries (>2 times) |  |  |  | DOC-016-S1 |  | Flag consignment as priority linehaul search; Issue intermediate tracking SMS to consignee; Request hub physical shelf audit | Promise compensation before verification; Mark ticket resolved while parcel remains in transit |  | RESOLUTION | 60 |
| ELG-002-COMP |  |  | delayed_delivery_terms AND rule_002_evidence<br>Transit delay exceeding 72 hours with repeated customer inquiries (>2 times) |  |  |  | DOC-016-S1 - Eligibility COMPENSATION: REQUIRES_VERIFICATION (human approval required) |  |  |  |  | ELIGIBILITY | 60 |
| ELG-002-REFU |  |  | delayed_delivery_terms AND rule_002_evidence<br>Transit delay exceeding 72 hours with repeated customer inquiries (>2 times) |  |  |  | DOC-016-S1 - Eligibility REFUND: REQUIRES_VERIFICATION (human approval required) |  |  |  |  | ELIGIBILITY | 60 |
| ELG-002-REPL |  |  | delayed_delivery_terms AND rule_002_evidence<br>Transit delay exceeding 72 hours with repeated customer inquiries (>2 times) |  |  |  | DOC-016-S1 - Eligibility REPLACEMENT: NOT_ELIGIBLE |  |  |  |  | ELIGIBILITY | 60 |

---

## 7. Observations from the export

Found while building the export. No existing file was changed; each is stated
so it can be decided on.

### 7.1 Follow-up flag is not read by the loader

The YAML writes the flag as `then.follow_up_required: true` (81 rules), but
`src/db/seed/rules.py` reads `then.get("follow_up", False)`. As seeded, the
`rules.follow_up_required` column is therefore false for every rule, and the
rule engine's `follow_up_required` output (`any(...)` over matched rules) is
false whatever matched. The export's Follow-up column shows the authored
value. Reading either key in the loader would align the two.

### 7.2 Advisory escalation levels are not carried into the rules

13 authored cases name an escalation level but are not marked mandatory:
`RULE-006`, `008`, `025`, `067`, `070` (Supervisor Review); `RULE-013`, `016`,
`020`, `063`, `065`, `088` (Specialist Team); `RULE-056`, `081` (Compliance
Review). The converter only writes an escalation for mandatory cases, so the
rules propose no escalation for these 13 unless another rule fires (their
classification precedence still reflects the level). 73 of the 500 complaints
name one of these cases as their expected rule.

### 7.3 Baseline cases: obligations need the evidence signal

For the 34 baseline cases the classification rule fires on the topic signal
alone, but the case's `RES-nnn` and `ELG-nnn-*` rules — and, for the six
baseline cases that have a floor (`RULE-014`, `017`, `052`, `079`, `085`,
`100`), the `ESC-nnn` rule — also require the case's evidence signal. A
complaint recognised by topic only is classified and routed by the baseline
rule without that case's obligations, eligibility verdicts or floor. The
"By Case" sheet shows both expressions for these cases.

### 7.4 Citations of documents that are not active

Five cases cite a knowledge-base document whose lifecycle status in
`knowledge_base_documents.json` is not *Active*: `RULE-026` cites
`DOC-006-S1` (Superseded legacy COD policy); `RULE-085`, `086`, `088` and
`089` cite `DOC-025-S2` (Draft dangerous-goods policy, v0.9).
`knowledge_base/versioning.py` classifies a citation of a superseded or
expired version as `OUTDATED` and of a draft as `NOT_APPLICABLE`, so these
citations will not count as applicable support if the knowledge base holds
the documents in those states.

### 7.5 Cases the corpus never exercises

As the dataset README records, no complaint names `RULE-033`, `RULE-063`,
`RULE-065` or `RULE-100` as its expected rule, so the corpus alone does not
demonstrate that they fire. The other 101 cases are each the expected rule
of at least one complaint.
