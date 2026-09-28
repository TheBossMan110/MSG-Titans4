# Python Validation Pipeline Evidence (Deliverable 7)

This document evidences Pipeline 2, the deterministic Python ground-truth pipeline, and the
checks that sit between the two pipelines: classification, routing, priority, escalation,
policy, resolution, source traceability, unsupported promises, contradictions and schema
validation. For each it gives the module and function that does the work, a short code
excerpt, a real example from the production database and the tests that cover it.

Sources:

* **the code** in `backend/python_validation/`, `backend/comparison_engine/`,
  `backend/hallucination_checks/`, `backend/security/`, `backend/schemas/` and
  `backend/complaint_processing/validation.py`;
* **read-only `SELECT` queries** on the production Supabase PostgreSQL database (Alembic
  head `0004_email_messages`), snapshot of **27 September 2026, 14:43 UTC**; validation
  runs span 23 Sep 18:22 to 27 Sep 13:21 UTC.

Nothing was re-run and nothing was written. The tests are listed, not executed. Customer
data is synthetic; examples come from the 500-complaint `RAFTARXPRESS` dataset unless
marked as a test or live-submission complaint, and personal data is redacted.

---

## 0. The pipeline at a glance

```text
complaint text
  -> signals.extract_signals()       lexicon terms, entities, facts   (no model involved)
  -> rule_engine.evaluate_rules()    pass 1: classification and routing
  -> rule_engine.evaluate_rules()    pass 2: category-scoped rules
  -> _apply_escalation_floor()       mandatory floor, can only raise
  -> eligibility findings            refund / replacement / compensation
  -> validation_runs + rule_hits + eligibility_decisions
       |
       +--> comparison_engine: compare_all() -> decide() -> comparisons + verification_decisions
       +--> hallucination_checks: citations, claim support, policy conflicts
       +--> resolution.classify(): resolution_steps verdicts
       +--> security.response_guard: the reply a customer would receive
```

Two structural guarantees make Pipeline 2 independent of Pipeline 1:

```python
# python_validation/pipeline.py
def run_validation(db, *, text, complaint=None, rules=None,
                   knowledge_base_version=None) -> ValidationResult:
    """
    Derive the ground truth for one complaint.

    Note the signature: there is no parameter for the GenAI result.  This
    function cannot be influenced by it, which is what makes the comparison
    downstream a genuine second opinion rather than a rubber stamp.
    """
```

and no module in `python_validation/` imports a provider client (asserted by
`test_pipeline_2_imports_no_ai_provider`; `python_validation/cli.py` runs with no API key).

### Production totals

| Table | Rows | Notes |
|---|---:|---|
| `rules` | 728 | CLASSIFICATION 131 (107 active), ELIGIBILITY 334 (322), ESCALATION 107, all mandatory (74 active), RESOLUTION 136 (115), ROUTING 20 (1 active catch-all) |
| `lexicon_terms` | 1,451 | 730 active PHRASE terms plus WORD / REGEX terms |
| `validation_runs` | 591 | 554 complaints; mean 528 ms; `unmatched` 150, `conflict_detected` 78, escalation floor set 213 |
| `rule_hits` | 3,405 | 461 distinct rules fired; 454 hits recorded with `applied = false` |
| `comparisons` | 5,542 | 554 complaints, one row per field |
| `verification_decisions` | 591 | CORRECTED_BY_RULES 248, BLOCKED 150, MANUAL_REVIEW_REQUIRED 149, INCOMPLETE 32, VERIFIED_WITH_WARNING 8, VERIFIED 4 |
| `escalations` | 300 | all `triggered_by = PYTHON_RULE` |
| `complaint_policy_refs` | 1,332 | 496 complaints; all resolved |
| `resolution_steps` | 2,228 | see section 6 |
| `eligibility_decisions` | 626 | see section 5 |
| `responses` / `response_flags` | 10 / 10 | see section 8 |
| `complaint_validation_issues` | 19 | see section 10 |

Comparison severity and winner per field, as recorded in `comparisons` (configured in
`app_config['comparison_weights']`):

| Field | Mismatch severity | Winner on mismatch |
|---|---|---|
| department, priority, escalation_level | CRITICAL | Python |
| category, urgency | HIGH | Python |
| subcategory, support_department, follow_up_required | MEDIUM | Python |
| sentiment, primary_issue | INFORMATIONAL (Python does not derive them) | GenAI value kept |

---

## 1. Complaint classification validation

**What.** Python derives category and subcategory from the complaint alone, then the
comparison engine checks the model's classification against it.

**Where.**
`python_validation/signals.py::extract_signals()` (lexicon, entities, facts),
`python_validation/conditions.py::evaluate()` (the JSON condition DSL, interpreted,
never `eval`-ed), `python_validation/rule_engine.py::evaluate_rules()`,
`python_validation/pipeline.py::run_validation()` (two passes),
`comparison_engine/fields.py::FIELD_SPECS` and `comparison_engine/diff.py::compare_field()`.
The model's category is also checked against the live taxonomy by
`genai_pipeline/validator.py::_check_references()`.

```python
# python_validation/pipeline.py::run_validation  (two fixed passes)
for pass_number in range(1, MAX_PASSES + 1):          # MAX_PASSES = 2
    fields = dict(base_fields)
    if outcome is not None:
        fields["category"] = outcome.category_code      # lets category-scoped rules fire
        fields["subcategory"] = outcome.subcategory_code
    outcome = evaluate_rules(rules, signals, fields=fields, ...)

# python_validation/rule_engine.py::evaluate_rules
if outcome.category_code is None:
    outcome.unmatched = True    # no category derived -> a human decides; never a guess
```

**Production example.** `CMP-000517`, "DISASTER! RIDER DID NOT SMILE WHILE HANDING ME THE
ENVELOPE IN GUJRANWALA! CN-2201948" (labelled category `REFUND`, department
`RETURNS_REFUNDS`). The model read the tone and classified it as a staff-behaviour
complaint; classification rule `RULE-040` fired on the span `"REFUND"` (characters
251-257, signal `refund_not_processed_terms`).

| Field | GenAI | Python | Final | Status | Severity | Winner |
|---|---|---|---|---|---|---|
| category | STAFF_BEHAVIOR | **REFUND** | REFUND | MISMATCH | HIGH | PYTHON |
| subcategory | RUDE_RIDER_DRIVER_BEHAVIOR | **REFUND_NOT_PROCESSED** | REFUND_NOT_PROCESSED | MISMATCH | MEDIUM | PYTHON |

Recorded explanation: *"GenAI derived STAFF_BEHAVIOR; rules derived REFUND."* Verdict:
`MANUAL_REVIEW_REQUIRED` (agreement 16.67 %, 2 critical and 2 high mismatches).

**Unrecognised complaints are not guessed.** 150 validation runs ended `unmatched`
(no substantive rule derived a category; the catch-all `RTE-0001` gives the complaint a
queue but does not count as recognition). There are 150 `BLOCKED` verdicts, each carrying
the review reasons `RULE_UNMATCHED` and `AMBIGUOUS_COMPLAINT`. Example: live test complaint
`CMP-000551`, whose description is 12 characters.

**Counts.** `category` comparisons: MATCH 229, MISMATCH 165, GENAI_MISSING 18,
PYTHON_MISSING 142 (the rules derived no category). `subcategory`: MATCH 122, MISMATCH
260, GENAI_MISSING 19, PYTHON_MISSING 129, UNSUPPORTED 24.

**Tests.** `tests/test_python_validation.py`: `test_pipeline_2_imports_no_ai_provider`,
`test_run_validation_cannot_receive_the_genai_result`,
`test_validation_produces_a_full_result_with_no_api_key`,
`test_a_scoped_rule_does_not_fire_outside_its_category`,
`test_catch_all_obligations_do_not_leak_onto_recognised_complaints`,
`test_unrecognised_complaint_is_flagged_not_guessed`, `test_determinism`,
`test_rule_matrix_meets_srs_minimums`, `test_rule_references_are_unique`.
`tests/test_comparison_engine.py`: `test_category_disagreement_is_recorded_with_an_explanation`,
`test_a_subcategory_disagreement_alone_is_only_a_warning`, `test_unmatched_rules_force_review`,
`test_an_unclassifiable_complaint_is_blocked`.
`tests/test_genai_pipeline.py`: `test_invented_category_is_caught_by_the_reference_gate`,
`test_subcategory_from_a_different_category_is_caught`.

---

## 2. Routing validation

**What.** The responsible and supporting departments come from the rule matrix
(`rules.outcome_department_id`, `outcome_support_department_id`); the model's routing is
compared against them and the rules win a disagreement.

**Where.** `rule_engine.py::evaluate_rules()` / `_resolve_scalar()` (highest precedence
wins; two rules at the same precedence that disagree are recorded as a conflict),
`comparison_engine/fields.py` (`department`, `support_department`),
`comparison_engine/decision.py::decide()`; the model's department codes are also checked by
the GenAI reference gate.

```python
# comparison_engine/fields.py
FieldSpec("department",
          lambda g: g.department,          # GenAI result
          lambda p: p.department_code,     # rule-derived outcome
          describe="Routing destination (SRS Step 53)."),
```

**Production example.** `CMP-000066`, "Courier used abusive profanity and threatened
violence at doorstep" (labelled `LOGISTICS_OPS`): GenAI `CUSTOMER_RELATIONS`, rules
**`LOGISTICS_OPS`**, final `LOGISTICS_OPS`, MISMATCH, CRITICAL, winner PYTHON. Also
`CMP-000536` and `CMP-000527` (merchant technical queries, labelled `CUSTOMER_RELATIONS`):
GenAI `TECH_SUPPORT`, rules `CUSTOMER_RELATIONS`, recorded as *"GenAI derived
TECH_SUPPORT; rules derived CUSTOMER_RELATIONS."*

**Counts.** `department` comparisons: MATCH 181, MISMATCH 355 (all CRITICAL, Python
wins), GENAI_MISSING 18. `support_department`: MATCH 25, MISMATCH 166. Same-precedence
rule conflicts: 78 validation runs, each adding the review reason `RULE_CONFLICT`.
Rule-derived departments across the 591 runs: CUSTOMER_RELATIONS 190, BILLING 73,
WARRANTY_CLAIMS 67, LOGISTICS_OPS 57, COMPLIANCE 49, SAFETY 48, ACCOUNT_SECURITY 43,
RETURNS_REFUNDS 38, MGMT_ESCALATIONS 24, LOGISTICS 2.

**Tests.** `test_python_validation.py::test_legal_threat_routes_to_compliance`;
`test_comparison_engine.py::test_rules_win_a_department_disagreement`,
`test_a_rule_conflict_forces_review`, `TestConfiguration` (weights come from the database;
retuning a weight changes the verdict); `test_genai_pipeline.py::test_invented_department_is_caught`.

---

## 3. Priority validation

**What.** Urgency and priority come from risk signals, not tone. Priority P0-P3 is an
ordered ladder (`priority_levels.rank`, 0 = most severe), so a disagreement has a direction,
and a model that rates a complaint *lower* than the rules is named separately.

**Where.** `rule_engine.py` (`SCALAR_FIELDS`: urgency and priority resolve to the more
severe value on a same-precedence conflict), `comparison_engine/diff.py::compare_field()`
and `_compare_ladder()`, `comparison_engine/ladders.py`, and the analytics-only rule in
`signals.py::SignalSet.for_rules()`.

```yaml
# config/signals.yaml
emotional_intensity:
  description: "How upset the writer sounds. ANALYTICS ONLY: recorded and shown, and
    structurally unable to reach the rule engine. SRS 1.8 #6 - a furious complaint about
    a late parcel must not outrank a calm one about a fire."
  analytics_only: true
```

```python
# comparison_engine/diff.py::compare_field
reason_code = "GENAI_PYTHON_DISAGREEMENT"
if direction == "GENAI_LOWER":
    # an under-escalation is the interesting one; review queue and report filter on it
    reason_code = "GENAI_BELOW_RULE_DERIVED"
```

**Production example: tone does not raise priority.** `CMP-000217`, "MY STAFF ENTERED PKR
2,500 INSTEAD OF 5,200 AND YOUR SYSTEM HASN'T UPDATED IT YET!" (all capitals, labelled
MEDIUM / P2). The model read `STRONGLY_NEGATIVE` and proposed HIGH / P1; the rules (only
`RULE-029`, a routine COD booking correction, and its companions fired) derived
**MEDIUM / P2**, which is final. Verdict `CORRECTED_BY_RULES`.

| Field | GenAI | Python | Final | Severity |
|---|---|---|---|---|
| urgency | HIGH | MEDIUM | MEDIUM | HIGH |
| priority | P1 | P2 | P2 | CRITICAL |

**Production example: severity raised.** `CMP-000066` (section 2): GenAI HIGH / P1, rules
**CRITICAL / P0** (labelled CRITICAL / P0), both `GENAI_BELOW_RULE_DERIVED`.

**Counts.** `priority` comparisons: MATCH 173, MISMATCH 363, GENAI_MISSING 18; `urgency`:
MATCH 161, MISMATCH 375, GENAI_MISSING 18. `GENAI_BELOW_RULE_DERIVED` rows: urgency 257,
priority 239. Of the 111 dataset complaints the model read as `STRONGLY_NEGATIVE`, it
proposed HIGH or CRITICAL urgency for 78; the rules kept 52 of the 111 at LOW or MEDIUM.

**Tests.** `test_python_validation.py`: `test_calm_safety_report_is_critical`,
`test_furious_delivery_delay_is_not_critical`,
`test_tone_is_detected_but_withheld_from_the_rule_engine`,
`test_no_rule_in_the_matrix_references_an_analytics_only_signal`,
`test_high_value_is_measured_not_guessed`. `test_comparison_engine.py`: `TestLadders`
(6 tests), `test_lower_priority_is_reported_as_lower`,
`test_agreement_falls_with_a_disagreement`.

---

## 4. Escalation validation

**What.** A rule marked `is_mandatory_escalation` sets a **floor**. Nothing downstream,
including the model, may lower the final escalation below it.

**Where.** `rule_engine.py::_apply_escalation_floor()`,
`comparison_engine/decision.py::build_reconciled()` (the floor is applied *after* every
field is resolved) and `floor_satisfied()`; the `escalations` row is written with
`triggered_by = PYTHON_RULE`.

```python
# python_validation/rule_engine.py::_apply_escalation_floor
mandatory = [rule for rule, _ in matched
             if rule.is_mandatory_escalation and rule.escalation_code]
floor_rule = max(mandatory, key=lambda r: escalation_ranks.get(str(r.escalation_code).upper(), 0))
outcome.escalation_floor_code = floor_rule.escalation_code
if current_rank < floor_rank:                      # can only ever raise
    outcome.escalation_code = floor_rule.escalation_code
    outcome.reason_codes.append(f"{floor_rule.rule_ref}:MANDATORY_ESCALATION_FLOOR")

# comparison_engine/decision.py::build_reconciled
if floor and not at_or_above(ladders, "escalation_level", current, floor):
    reconciled["escalation_level"] = floor         # a floor that could be outweighed would not be a floor
    reconciled["escalation_floor_applied"] = True
```

**Production example.** `CMP-000066` (labelled `CRITICAL_MGMT`):

* Validation run `833cc0f0-051c-4977-ace2-b2801a5fd5ad`: mandatory rule **`ESC-068`**
  (precedence 115, outcome `CRITICAL_MGMT`) matched the spans `"abusive"` (49-56) and
  `"threatened"` (71-81), signals `rude_rider_driver_behavior_terms` and
  `rule_068_evidence`. Rationale: *"RULE-068 makes this escalation mandatory. The floor may
  be raised above CRITICAL_MGMT, never lowered below it."* Classification rule `RULE-068`
  (*"Zero-tolerance safety and harassment violation mandates emergency P0 escalation"*)
  fired on the same spans; the catch-all `RTE-0001` is recorded with `applied = false`.
* Comparison: GenAI `SUPERVISOR`, Python **`CRITICAL_MGMT`**, final `CRITICAL_MGMT`,
  MISMATCH, CRITICAL, reason `GENAI_BELOW_RULE_DERIVED`, explanation *"GenAI proposed
  SUPERVISOR, which is BELOW the rule-derived CRITICAL_MGMT. The rule-derived value
  stands."*
* `escalations`: `CRITICAL_MGMT`, `triggered_by = PYTHON_RULE`, `rule_ref = ESC-068`,
  to department `LOGISTICS_OPS`, reason *"Mandatory escalation floor CRITICAL_MGMT derived
  by ESC-068."*
* Verdict: `CORRECTED_BY_RULES`, 3 critical and 1 high mismatch, agreement 12.5 %.

A fact-based (not lexicon) floor also occurs: rule `REP-0001` sets `SUPERVISOR` for a
repeat contact, e.g. live e-mail submission `CMP-000558` (two previous contacts), where
the model proposed no escalation.

**Counts.** Floors set on 213 validation runs: CRITICAL_MGMT 105, SUPERVISOR 36,
COMPLIANCE_REVIEW 28, SPECIALIST 27, DEPT_MANAGER 17. `escalation_level` comparisons with
`GENAI_BELOW_RULE_DERIVED`: 121. Escalation records: 300 (CRITICAL_MGMT 119,
DEPT_MANAGER 54, SUPERVISOR 52, COMPLIANCE_REVIEW 38, SPECIALIST 37). **Invariant check:**
of the 213 verification decisions whose reconciled record carries an
`escalation_floor`, the reconciled `escalation_level` is below the floor in **0**.

**Tests.** `test_python_validation.py`: `test_mandatory_escalation_sets_a_floor`,
`test_the_floor_raises_a_lower_proposal_and_never_lowers_a_higher_one`,
`test_repeat_contact_forces_supervisor_escalation`,
`test_every_mandatory_escalation_rule_declares_a_level`.
`test_comparison_engine.py::TestEscalationFloor` (`test_floor_raises_a_lower_genai_escalation`,
`test_floor_holds_even_when_configuration_lets_genai_win`,
`test_floor_never_lowers_a_higher_escalation`,
`test_no_escalation_at_all_is_raised_to_the_floor`), `test_lower_genai_escalation_records_its_direction`,
`test_the_floor_holds_end_to_end`. `test_completion.py::test_an_escalation_schedules_contact`.

---

## 5. Policy validation

**What.** Two questions: is a cited policy *in force*, and does policy (through the rules)
actually permit a refund, replacement or compensation?

**Where.** Applicability: `hallucination_checks/citation_validator.py::validate_citation()`
with `knowledge_base/versioning.py::applicability_for()`; the database guarantees at most
one ACTIVE version per document (partial unique index `ux_docver_one_active`). Eligibility:
`python_validation/pipeline.py::_collect_eligibility()` writes `eligibility_decisions`;
`security/response_guard.py::is_permitted()` decides what may be promised.

```python
# hallucination_checks/citation_validator.py::validate_citation
verdict.was_active = getattr(version, "status", None) == DocStatus.ACTIVE
verdict.applicability = versioning.applicability_for(version)
if verdict.applicability == PolicyApplicability.OUTDATED:
    verdict.reason = (f"{verdict.doc_ref} resolves to a version that is no longer in force "
                      f"({version.status}). It may be used to detect a contradiction, "
                      "but not as the basis of an answer.")

# security/response_guard.py::is_permitted
if finding.get("requires_human_approval"):
    return False
return str(finding.get("python_outcome", "")).upper() == EligibilityOutcome.ELIGIBLE
```

**Production example: outdated policy.** `CMP-000250` and `CMP-000216` (dataset): a rule
required `DOC-006` section 1, which resolves to version **1.0, status EXPIRED**. Stored
verdict: applicability `OUTDATED`, `was_active = false`, reason *"DOC-006 resolves to a
version that is no longer in force (EXPIRED). It may be used to detect a contradiction, but
not as the basis of an answer."*

**Production example: eligibility.** Test complaint `CMP-TC10B0E` (duplicate charge):
`REFUND`, rule `ELG-0001`, `python_outcome = final_outcome = REQUIRES_VERIFICATION`,
conditions evaluated `["Purchase date within the applicable refund window", "Item not on
the non-refundable list"]`, reason *"The default position for any refund request. Nothing
is approved at the desk until the purchase date has been checked against REF-POL-02 s2."*
Section 8 shows this finding blocking a reply.

**Counts.** Document versions: ACTIVE 24, EXPIRED 4, SUPERSEDED 1. Policy references:
1,332, of which APPLICABLE 1,329 (524 cited by GenAI, 805 required by rules) and OUTDATED
3 (rule-required). Eligibility decisions, final outcome:

| Type | ELIGIBLE | NOT_ELIGIBLE | REQUIRES_VERIFICATION |
|---|---:|---:|---:|
| REFUND | 32 | 110 | 102 (94 need human approval) |
| COMPENSATION | 40 | 122 | 18 (all need human approval) |
| REPLACEMENT | 9 | 193 | 0 |

`genai_outcome` is empty on all 626 rows: the final eligibility is always the rule-derived
one.

**Tests.** `test_python_validation.py`: `test_replacement_is_withheld_pending_a_safety_assessment`,
`test_refund_request_is_never_approved_at_the_desk`,
`test_the_most_restrictive_eligibility_finding_wins`. `test_hallucination_checks.py::test_a_real_active_policy_is_trustworthy`;
`test_comparison_engine.py::test_a_superseded_citation_is_not_traceable`;
`test_knowledge_base.py`: `test_only_one_version_can_be_active`,
`test_new_version_supersedes_the_previous_one`, `test_retrieval_excludes_superseded_versions`,
`test_precedence_order_is_configuration_not_code`; `test_policy_update.py` (14 tests, e.g.
`test_a_citation_to_the_old_version_is_now_outdated`,
`test_the_old_version_is_demoted_not_deleted`).

---

## 6. Resolution validation

**What.** Every recommended step gets a verdict. Rule obligations stay `MISSING` until a
person confirms them; model-proposed steps are `SUPPORTED`, `UNSUPPORTED` or
`PROHIBITED`.

**Where.** `python_validation/resolution.py::classify()` and `confirm()`.

```python
# python_validation/resolution.py::classify  (a generated step)
promises = detect_promises(step.text, patterns)        # same patterns as the response guard
offending = next((p for p in promises
                  if not is_permitted(index.get(str(p.get("requires_eligibility") or "").upper()))), None)
if offending is not None:
    status = ResolutionStepStatus.PROHIBITED           # "no eligibility decision authorises"
elif _cites_a_real_policy(db, step):
    status = ResolutionStepStatus.SUPPORTED
else:
    status = ResolutionStepStatus.UNSUPPORTED          # "not traceable, so an agent owns it"
# RULE_REQUIRED steps are never auto-satisfied; only confirm() moves one to REQUIRED_MET
```

**Production examples.**

| Complaint | Source | Status | Step (truncated) | Recorded explanation |
|---|---|---|---|---|
| CMP-000209 | GENAI | PROHIBITED | "Contact the customer to explain the RTO consolidation policy or offer an exception if applicable." | "Proposes a exception that no eligibility decision authorises. An agent must not carry this out." |
| CMP-000541 | GENAI | SUPPORTED | "Provide the customer with the approved company guidelines for specialized packaging and ground transit fleet requirements." (`policy_ref` DOC-025) | "Traceable to DOC-025." |
| CMP-000558 (live) | RULE_REQUIRED | MISSING | "Review sorter conveyor CCTV footage" | "Required by the rule matrix; an agent must confirm it." |
| CMP-000558 (live) | GENAI | UNSUPPORTED | "Initiate a return for a refund or replacement once photographic evidence is received and verified." | "Generated without a policy reference that resolves. It may still be sensible; it is simply not traceable, so an agent owns it." |

**Counts.** 2,228 steps: GENAI SUPPORTED 115, UNSUPPORTED 1,044, PROHIBITED 8;
RULE_REQUIRED MISSING 1,061, REQUIRED_MET 0 (no agent confirmations recorded yet). Of the
1,044 UNSUPPORTED steps, 652 carry no policy reference at all; the other 392 are discussed
in section 12.

**Tests.** `tests/test_completion.py::TestResolutionValidation` (9 tests:
`test_rule_obligations_become_a_checklist`,
`test_a_rule_obligation_is_never_satisfied_automatically`, `test_an_agent_can_confirm_one`,
`test_confirming_survives_a_re_run`, `test_a_generated_suggestion_cannot_be_confirmed`,
`test_an_unauthorised_promise_in_a_step_is_prohibited`,
`test_a_permitted_promise_is_not_prohibited`,
`test_an_uncited_suggestion_is_unsupported_not_wrong`,
`test_coverage_is_null_when_there_is_nothing_to_do`);
`test_complaints_api.py::test_rule_prohibitions_become_mandatory_guidance`;
`test_comparison_engine.py::test_obligations_are_carried_into_the_reconciled_record`.

---

## 7. Source traceability

**What.** Any statement's policy basis can be traced to document, version, section, page or
paragraph and the exact chunk, with who proposed it and whether that version was in force.

**Where.** `hallucination_checks/citation_validator.py`: `validate_citation()`,
`validate_all()`, `persist()` (writes `complaint_policy_refs`) and `trace()`; chunks carry
denormalised `doc_ref`, `doc_version`, `section_ref`, `page_no`, `paragraph_index`.
Upstream, `genai_pipeline/validator.py::_check_citations()` rejects a model answer that
cites an identifier which does not exist (*unresolved*) and logs one that exists but was not
retrieved for the complaint (*ungrounded*).

**Production example.** `CMP-000544` (dataset), GenAI citation `DOC-020::3::c1`:

| Column | Value |
|---|---|
| source | GENAI |
| doc_ref / doc_version / section_ref | DOC-020 / 1.1 / 3 |
| chunk_key | DOC-020::3::c1 |
| page_no / paragraph_index | — / 12 (DOCX, so located by paragraph) |
| resolved / was_active / applicability / precedence_tier | true / true / APPLICABLE / ACTIVE_POLICY |
| chunk heading | "Customer Feedback and Quality Audits" |
| document file / status / effective date | `DOC-020_v1.1.docx` / ACTIVE / 2024-01-15 |
| chunk text | "3 Customer Feedback and Quality Audits. Post-interaction CSAT surveys are automatically dispatched upon ticket resolution, with random monthly audits conducted by the Quality Assurance team. …" |

The step "Verify record status in SupportNova compliance vault." on the same complaint is
`SUPPORTED` with *"Traceable to DOC-020."*

**Fabricated citations are stopped before they are stored.** 39 GenAI answers were rejected
by the citation gate (`genai_runs.schema_errors`), for example `CMP-000504`, whose model
cited `"[SAF-POL-02::3::c1]"`, an identifier that matches no chunk. None of them reached
`complaint_policy_refs`.

**Counts.** 1,332 policy references over 496 complaints, all resolved (0 unresolvable);
524 GenAI-sourced, all ACTIVE and APPLICABLE. The stored traceability score is 100.0 on
all 447 verification decisions that had citations to score (the other 144 had none).

**Tests.** `tests/test_hallucination_checks.py`: `TestCitationValidation` (8 tests, e.g.
`test_an_invented_reference_is_unresolvable`,
`test_the_resolved_chunk_carries_its_location`, `test_sources_are_kept_apart`,
`test_traceability_measures_only_what_the_model_cited`), `TestCitationPersistence`,
`TestSourceScope`. `tests/test_knowledge_base.py::test_every_chunk_is_fully_traceable`,
`test_retrieval_returns_full_citations`. `tests/test_comparison_engine.py::TestCitations`
(`test_an_invented_citation_is_unresolvable`, `test_a_citation_outside_the_retrieved_set_is_marked`),
`test_traceability_counts_only_resolvable_active_citations`.

---

## 8. Unsupported promise detection

**What.** Before a reply can reach a customer, every promise-shaped phrase is checked against
Pipeline 2's eligibility. A promise of type T is unsupported unless the rules independently
derived eligibility T = `ELIGIBLE` without a human-approval requirement, and any stated
amount is within the rule's ceiling.

**Where.** `security/response_guard.py`: `load_promise_patterns()` (19 rows in
`promise_patterns`), `detect_promises()`, `is_permitted()`, `exceeds_ceiling()`,
`scan_response()`, `persist_flags()`; the regenerate-once loop is
`genai_pipeline/response.py`. The same rule marks resolution steps `PROHIBITED`
(section 6).

```python
# security/response_guard.py::detect_promises
for pattern, promise_type, requires in patterns:
    for match in _compile(pattern).finditer(text):
        found.append({"promise_type": promise_type, "requires_eligibility": requires,
                      "text": match.group(0), "start": match.start(), "end": match.end()})
```

**Production example: blocked, regenerated once, blocked again, kept.** Test complaint
`CMP-TC10B0E` (a duplicate charge of Rs. 42,500 on order ZN-77321). Refund eligibility
from rule `ELG-0001` was `REQUIRES_VERIFICATION` (section 5).

| Draft | Guard status | Flag | Span | Matched text | Explanation |
|---|---|---|---|---|---|
| v1 | BLOCKED | UNSUPPORTED_PROMISE, CRITICAL, rule `ELG-0001` | 543-554 | "full refund" | "The reply promises a refund, but ELG-0001 derived REQUIRES_VERIFICATION, not ELIGIBLE. Outstanding: Purchase date within the applicable refund window; Item not on the non-refundable list." |
| v2 (regeneration 1) | BLOCKED | UNSUPPORTED_PROMISE, CRITICAL, rule `ELG-0001` | 532-556 | "refund will be processed" | same |

Both drafts are stored (`responses.version` 1 and 2) with their flags; the second was not
regenerated again (`max_regenerations = 1`) and was not sent. Each draft also carries
MEDIUM `HALLUCINATION` flags from the claim checker (section 9).

**Production example: hedged promise flagged, not blocked.** Test complaint `CMP-FF873CF`,
reply v1: "full refund" (525-536) and "refund will be processed" (530-554), both
`UNSUPPORTED_PROMISE`, MEDIUM, guard status `FLAGGED`: *"… It is phrased conditionally,
so it is flagged for a reviewer rather than blocked."*

**Counts.** 10 reply drafts on 8 complaints: CLEAN 6, BLOCKED 3, FLAGGED 1; 2 drafts are
regenerations. Flags: UNSUPPORTED_PROMISE 6 (CRITICAL 3, HIGH 1, MEDIUM 2), HALLUCINATION 4.
Resolution steps marked PROHIBITED by the same rule: 8.

**Tests.** `tests/test_response_guard.py` (53 tests): `TestDetection` (e.g.
`test_refund_promises_are_detected`, `test_a_neutral_reply_promises_nothing`,
`test_spans_point_at_the_matched_phrase`), `TestUnsupportedPromise` (e.g.
`test_eligible_permits_the_promise`, `test_anything_short_of_eligible_blocks_it`,
`test_an_amount_above_the_ceiling_blocks_a_genuinely_eligible_promise`,
`test_eligible_but_needing_human_approval_blocks_it`,
`test_the_wrong_eligibility_type_does_not_authorise`, `test_a_hedged_promise_is_flagged_not_blocked`,
`test_a_timeline_without_a_citation_is_flagged`,
`test_an_exception_promise_needs_policy_exception_eligibility`), `TestGuardReport`,
`TestResponseGeneration` (e.g. `test_a_blocked_draft_triggers_exactly_one_regeneration`,
`test_a_still_blocked_draft_is_kept_not_discarded`).

---

## 9. Contradiction detection

Three kinds of contradiction are detected, each by deterministic code.

**(a) GenAI against Python.** Every disagreement between the pipelines becomes a
`comparisons` row with a direction and an explanation (sections 1-4): 1,637 rows
`GENAI_PYTHON_DISAGREEMENT` and 617 `GENAI_BELOW_RULE_DERIVED`, which drive the review
reason `GENAI_PYTHON_DISAGREEMENT` on 568 decisions.

**(b) A generated statement against the policy it cites.** `hallucination_checks/claim_support.py`
scores each claim against its cited source and then applies two checks that vocabulary
overlap cannot make: a **figure** in the same unit that differs from the cited line
(e.g. "30 days" against a policy saying 14), and **polarity**, where one sentence negates
what the other asserts.

```python
# hallucination_checks/claim_support.py::score_claim
if supporting:
    claim_negated = bool(_NEGATION.search(claim.text))
    source_negated = bool(_NEGATION.search(supporting))
    if claim_negated != source_negated:
        verdict.negation_mismatch = True   # "... so a human should read both."
```

Production example, test complaint `CMP-TC10B0E`, reply v1, `HALLUCINATION`, MEDIUM,
span 525-598: the claim *"Once confirmed, a full refund for the erroneous charge will be
processed."* against the cited `REF-POL-02` section 7 (*"A confirmed duplicate charge is
refunded in full without reference to the refund window in section 2 …"*). Recorded
explanation: *"This statement asserts what the closest line of the cited policy negates …
Overlap alone cannot tell these apart, so a human should read both."* The source sentence
contains "without", so this is a case the detector deliberately routes to a person rather
than deciding.

**(c) Policy against policy.** `hallucination_checks/policy_conflict.py::detect()`
compares every pair of resolved documents a complaint rests on, sentence by sentence. A
pair counts as a conflict only when the sentences share at least 60 % of their vocabulary
*in both directions* and then differ by negation or by a figure in the same unit; the
documented precedence order (`knowledge_base/versioning.py::resolve_conflict()`) picks the
winner, and `persist()` marks the loser with `conflict_with_ref` rather than deleting it.

```python
# hallucination_checks/policy_conflict.py::_disagreement
if is_negated(text_a) != is_negated(text_b):
    return (NEGATION, f'one asserts what the other negates: "{negates[:120]}" against "{asserts[:120]}"')
for unit, values_a in figures_by_unit(text_a).items():
    values_b = figures_by_unit(text_b).get(unit)
    if values_b and not values_a & values_b:
        return (FIGURE, ...)          # same unit, different figures
```

In production, `complaint_policy_refs.conflict_with_ref` is empty on all 1,332 rows: no two
documents cited for the same complaint met that test, so this mechanism is evidenced by its
tests rather than by a stored case. The related superseded-policy case is stored
(`OUTDATED`, section 5).

**Tests.** `tests/test_policy_conflict.py` (18 tests: `TestSubjectMatch`, `TestDisagreement`,
`TestContradiction`, `TestDetection` including `test_a_contradiction_is_recorded_not_silently_resolved`,
`test_the_overruled_reference_is_kept`, `test_running_twice_does_not_stack_the_reason`,
and `TestFalsePositives`); `tests/test_hallucination_checks.py::TestNegationMismatch`
(4 tests) and `TestNumericGrounding` (e.g. `test_an_invented_figure_is_caught`);
`tests/test_knowledge_base.py::test_conflict_resolution_prefers_policy_then_recency`.

---

## 10. Schema validation

**(a) The GenAI output contract.** `schemas/genai.py::ComplaintIntelligence` is a Pydantic
model with `extra="forbid"`, `Literal` enums for sentiment, urgency and priority, length and
list bounds, and cross-field validators; `genai_pipeline/validator.py` adds the extraction,
reference and citation gates (see `GENAI_PIPELINE_EVIDENCE.md`, section 9).

```python
# schemas/genai.py
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class ComplaintIntelligence(StrictModel):
    urgency: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    priority: Literal["P0", "P1", "P2", "P3"]
    policy_refs: Annotated[list[PolicyReferenceOut], Field(max_length=12)] = ...
    ...
    @model_validator(mode="after")
    def _escalation_consistency(self):
        if self.escalation_required and not self.escalation_level:
            raise ValueError("escalation_required is true but escalation_level is missing")
        return self
```

Production: 58 GenAI answers rejected (`status = SCHEMA_INVALID`) with 59 findings:
citation 39, schema 11 (`policy_refs[i].supports` over 400 characters), reference 8
(`support_department` 6, `subcategory` 1, `category` 1), extraction 1. Example (schema
gate), test complaint `CMP-000557`: `{"stage": "schema", "field": "policy_refs.2.supports",
"message": "has an invalid length (String should have at most 400 characters)."}`.

**(b) Intake validation.** `complaint_processing/validation.py::validate_submission()`
records a `complaint_validation_issues` row per finding; only an empty complaint is refused.
Document uploads are checked by `document_processing/validation.py`
(`document_validation_issues`).

| Issue code | Outcome | Severity | Rows | Recorded message (example) |
|---|---|---|---:|---|
| DUPLICATE_COMPLAINT | ROUTED_TO_REVIEW | MEDIUM | 8 | "This appears to duplicate complaint CMP-000556 (100% similar). It is accepted and linked to the original rather than refused." |
| INVALID_REFERENCE_ID | ROUTED_TO_REVIEW | MEDIUM | 7 | "'ORD-77142' is not a recognised order ref. The complaint is accepted; the reference will be confirmed with the customer rather than guessed." |
| SUSPECTED_INJECTION | ROUTED_TO_REVIEW | HIGH | 3 | "The complaint contains text shaped like an instruction to the system. It is processed as complaint content and routed for review; no instruction within it is followed." |
| TOO_SHORT | ROUTED_TO_REVIEW | MEDIUM | 1 | "The complaint is 12 characters, below the 20-character minimum. It is accepted, and a clarification question will be asked rather than details being invented." |

Documents: MISSING_EFFECTIVE_DATE, METADATA_INCOMPLETE and MISSING_VERSION, one each, all
ACCEPTED_WITH_WARNING.

**(c) Database constraints.** Status and outcome columns carry `CHECK` constraints
generated from `src/db/enums.py` (e.g. `ck_complaints_status_valid`,
`ck_genai_runs_status_valid`, `ck_comparisons_severity_valid`; see
`database/schema.sql`), so an invalid value is refused by PostgreSQL even if code slipped.

**Tests.** `tests/test_genai_pipeline.py::TestValidation` (12 tests, e.g.
`test_invalid_enum_value_is_rejected`, `test_unknown_field_is_rejected_not_silently_dropped`,
`test_missing_required_field_is_rejected`, `test_escalation_without_a_level_is_rejected`,
`test_insufficient_information_requires_a_question`, `test_errors_are_serialisable_for_storage`),
`TestJSONExtraction`, `TestProviderSchema`. `tests/test_complaints_api.py`:
`test_only_an_empty_complaint_is_rejected`, `test_a_rejected_attempt_is_still_recorded`,
`test_a_short_complaint_is_accepted_with_a_finding`,
`test_an_unrecognised_reference_is_accepted_with_a_finding`,
`test_an_injection_attempt_is_flagged_and_processed`,
`test_a_different_complaint_is_not_a_duplicate`. `tests/test_knowledge_base.py`:
`test_reuploading_the_same_file_is_rejected_and_recorded`,
`test_unparseable_upload_is_rejected_and_recorded`,
`test_document_without_metadata_lands_in_review_not_rejected`.
`tests/test_dialect_portability.py` (JSONB, `VECTOR`, BIGINT keys and timezone-aware
timestamps render correctly for PostgreSQL, so `schema.sql` and the migrations agree).

---

## 11. Measured accuracy against the labelled dataset

`benchmark_runs` row "RaftarXpress 500 - full dataset" (25 Sep 2026, ruleset
`2026.09.25-004880e5`, prompt `complaint_intelligence v1.1`, `gemini-3.5-flash-lite`; 500
complaints processed, 0 failed, GenAI available on 487). Accuracy is against the
`expected_*` labels, which neither pipeline reads.

| Field | Python accuracy | GenAI accuracy | Agreement |
|---|---:|---:|---:|
| category | 40.0 % (200/500) | 52.3 % (261/499) | 69.1 % |
| subcategory | 27.4 % | 36.6 % | 50.0 % |
| department | 33.4 % | 34.1 % | 32.7 % |
| urgency | 34.8 % | 40.9 % | 28.7 % |
| priority | 31.6 % | 37.9 % | 30.5 % |
| escalation_level | 69.4 % (347/500) | 61.1 % | 76.2 % |
| **overall** | **39.4 %** | **43.8 %** | **47.9 %** |

Mandatory escalation (the SRS target is 100 % recall): **164 of 317 recalled (51.7 %),
target not met**; 68 complaints over-escalated. End-to-end latency per complaint: mean
14.0 s, median 12.8 s, 95th percentile 22.7 s. These figures are reported as measured;
the comparison report (Deliverable 8) is the place for their analysis.

---

## 12. Limitations observed in the data

Found while assembling this evidence; each is stated with its size.

1. **Phrase terms match inside words.** `signals.py::_compile_term()` compiles `PHRASE`
   terms without word boundaries (`WORD` terms have them). Across the 500 dataset
   complaints this produces 32 in-word matches in 29 complaints. Most are harmless plurals
   ("phone number" in "phone numbers"), but two change outcomes: `CMP-000241`, a
   credential-stuffing report, matched the safety term "on fire" inside "applicati**on
   fire**walls" and fired `ESC-SAF-0001` (category SAFETY; the CRITICAL_MGMT floor was also
   required independently by `ESC-066`); `CMP-000217` matched "our company" inside
   "y**our company**" (signal `vip_or_corporate`). Adding `\b` to phrase patterns removes
   both.
2. **Steps citing a chunk key are never SUPPORTED.** The GenAI schema has only
   `policy_ref` on a resolution step, the model puts a chunk key there (e.g.
   `"DOC-001::3::c1"`), and `resolution.py::_cites_a_real_policy()` compares `policy_ref`
   with `chunks.doc_ref`. 392 of the 1,044 UNSUPPORTED steps cite a chunk key that exists
   (after stripping stray brackets), so the true SUPPORTED count is understated.
3. **A negated promise can be marked PROHIBITED.** `CMP-000292`: "Inform the customer that
   full refunds for inconvenience are not provided when delivery is successfully
   completed." was classified PROHIBITED ("Proposes a refund that no eligibility decision
   authorises"). The resolution classifier applies promise patterns without the hedge and
   negation handling the reply guard uses.
4. **Coverage.** 150 of 591 validation runs (25.4 %) matched no substantive rule. By design
   these are routed to a person rather than guessed, but they are gaps in the rule matrix,
   and together with the benchmark in section 11 they are where rule-matrix work should go.
5. **Policy-against-policy conflicts** have no stored production case (section 9c); the
   evidence is the test suite.
