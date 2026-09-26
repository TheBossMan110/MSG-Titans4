# SRS Requirement Coverage

**SupportNova** · ResponseX Intelligence · Generative AI PowerPlay

> Generated from `config/requirements.yaml` by `scripts/generate_coverage_report.py`. Do not edit by hand.
> Last generated: 2026-09-26 09:01 UTC

`tests/test_requirements_coverage.py` fails the build if any requirement is
missing from the registry, if anything marked **Done** names a table, column,
module or endpoint that does not exist, or if anything marked **Partial** does
not state its remaining gap.

| Section | Coverage |
|---|---|
| Functional requirements (1.6) | ✅ Done 74 · 🖥️ Frontend 1 · **75 total** |
| Development steps (1.2) | ✅ Done 67 · 🟡 Partial 1 · **68 total** |
| Non-functional requirements (1.7) | **5 total** |
| Competition integrity (1.8) | **19 total** |

---

## 1.6 Functional Requirements

| # | Requirement | Status | Tables | Modules | Notes / Gap |
|---|---|---|---|---|---|
| i | User Authentication | ✅ Done | `users` `refresh_tokens` | `src/core/security.py` `src/services/auth.py` +1 more | Self-service registration is open and rate-limited per IP like login, but it can only ever produce a CUSTOMER: the request body has no role field a… |
| ii | Role-Based Access Control | ✅ Done | `users` | `src/core/deps.py` `src/core/scope.py` +2 more | Five role experiences, each with its own dashboard and navigation, enforced by the API (tests/test_rbac.py): customers see their own complaints; ag… |
| iii | Complaint Submission | ✅ Done | `complaints` `customers` `complaint_validation_issues` +1 more | `complaint_processing/intake.py` `src/api/v1/complaints.py` +5 more | Accepted, recorded and analysed in one call. The complaint is persisted before analysis runs, so one that is accepted and then fails analysis is st… |
| iv | Complaint Validation | ✅ Done | `complaint_validation_issues` | `complaint_processing/validation.py` | Empty, too short, too long, duplicate, invalid reference, missing field, unsupported attachment and suspected injection are all detected and persis… |
| v | Complaint Pre-processing | ✅ Done | `complaints` | `complaint_processing/preprocess.py` | NFKC normalisation, invisible and control character stripping, whitespace collapse and a length cap. Both texts are kept: description_raw is the ev… |
| vi | Knowledge-Base Upload | ✅ Done | `documents` `document_versions` | `knowledge_base/ingest.py` `src/api/v1/documents.py` +1 more | PDF and DOCX both ingest end to end. Files are content-addressed in object storage, and a per-file result is returned so one bad file in a batch do… |
| vii | Document Validation | ✅ Done | `document_validation_issues` | `document_processing/validation.py` `knowledge_base/ingest.py` | File type is decided by magic bytes, not the extension. Every finding is persisted, including for refused uploads, so the checks are provable rathe… |
| viii | Document Parsing | ✅ Done | `document_sections` | `document_processing/pdf_parser.py` `document_processing/docx_parser.py` +2 more | PDF carries page numbers, DOCX carries paragraph indices, and both reach the chunk row. A parity test renders the same policy to both formats and a… |
| ix | Document Chunking | ✅ Done | `chunks` | `document_processing/chunker.py` `knowledge_base/embeddings.py` | A chunk never crosses a section boundary, so every chunk is honestly citable. Enforced by test. |
| x | Document Version Control | ✅ Done | `document_versions` | `src/db/models/knowledge.py` | Partial unique index ux_docver_one_active makes "at most one ACTIVE version per document" a database guarantee, not a convention. |
| xi | Complaint Resolution Rule Matrix | ✅ Done | `rules` | `src/db/models/rules.py` | — |
| xii | GenAI API Integration | ✅ Done | `genai_runs` `llm_cache` | `genai_pipeline/providers/base.py` `genai_pipeline/providers/gemini.py` +3 more | Gemini primary with Groq and OpenRouter fallback. Failures are sorted into retryable and terminal; retry is bounded by LLM_MAX_RETRIES and every at… |
| xiii | Complaint Issue Identification | ✅ Done | `complaints` | `genai_pipeline/intelligence.py` | Generated, schema-validated, reconciled against the rule engine and written onto the complaint at intake. complaints.primary_issue. |
| xiv | Secondary Issue Identification | ✅ Done | `complaints` | `genai_pipeline/intelligence.py` | Generated, schema-validated, reconciled against the rule engine and written onto the complaint at intake. complaints.secondary_issue. |
| xv | Complaint Classification | ✅ Done | `categories` `subcategories` `complaints` | `genai_pipeline/intelligence.py` `python_validation/rule_engine.py` | Both pipelines classify, the comparison engine reconciles, and the reconciled category and subcategory are written to the complaint. |
| xvi | Entity Extraction | ✅ Done | `complaint_entities` | `complaint_processing/entities.py` | Python's regex pass and the model's pass are stored separately and tagged with extracted_by, never merged. Merging them would destroy the compariso… |
| xvii | Sentiment Analysis | ✅ Done | `complaints` | `genai_pipeline/intelligence.py` | Generated, schema-validated, reconciled against the rule engine and written onto the complaint at intake. Sentiment is recorded for analytics and i… |
| xviii | Urgency Classification | ✅ Done | `complaints` `validation_runs` | `python_validation/rule_engine.py` `python_validation/signals.py` | Both pipelines derive urgency, compared by ladder rank so the direction of a disagreement is recorded, and the reconciled value is written to the c… |
| xix | Priority Assignment | ✅ Done | `priority_levels` `complaints` `comparisons` | `python_validation/rule_engine.py` `genai_pipeline/intelligence.py` +1 more | Both pipelines assign a priority and the comparison engine compares them by ladder rank, so a disagreement records its direction rather than a bare… |
| xx | Department Routing | ✅ Done | `departments` `complaints` `comparisons` | `python_validation/rule_engine.py` `genai_pipeline/intelligence.py` +1 more | Both pipelines route, the comparison engine compares the destination and the reconciled department is written to the complaint. The rules win on di… |
| xxi | Multi-Department Routing | ✅ Done | `departments` `complaints` `comparisons` | `python_validation/rule_engine.py` `routing_rules/departments.yaml` +1 more | A complaint that spans two teams carries a supporting department alongside the owning one, derived by the routing rules and compared field-by-field… |
| xxii | Policy Retrieval | ✅ Done | `chunks` `complaint_policy_refs` | `knowledge_base/retrieval.py` `knowledge_base/embeddings.py` | Hybrid lexical (PostgreSQL full-text) plus semantic (pgvector), fused with Reciprocal Rank Fusion, with an exact-reference retriever that dominates… |
| xxiii | Policy Applicability Validation | ✅ Done | `complaint_policy_refs` `document_versions` | `knowledge_base/versioning.py` `hallucination_checks/citation_validator.py` | Every citation the model makes is resolved, classified APPLICABLE / CONDITIONALLY_APPLICABLE / NOT_APPLICABLE / OUTDATED, and written to complaint_… |
| xxiv | Resolution Generation | ✅ Done | `resolution_steps` | `genai_pipeline/intelligence.py` | Rule obligations and generated steps are both stored, tagged by source and never merged. A rule obligation stays MISSING until an agent confirms it… |
| xxv | Resolution Validation | ✅ Done | `resolution_steps` | `python_validation/resolution.py` `python_validation/rule_engine.py` | A rule-required step stays MISSING until a person confirms it. Whether 'verify the shipment in the tracking system' actually happened is not readab… |
| xxvi | Refund Rule Validation | ✅ Done | `eligibility_decisions` `rules` | `python_validation/pipeline.py` `complaint_rules/eligibility.yaml` | Eligibility is Pipeline 2's alone, by design. The model is never asked for it and the response schema has no field for it, so there is nothing to r… |
| xxvii | Replacement Rule Validation | ✅ Done | `eligibility_decisions` `rules` | `python_validation/pipeline.py` `complaint_rules/eligibility.yaml` | Eligibility is Pipeline 2's alone, by design. The model is never asked for it and the response schema has no field for it, so there is nothing to r… |
| xxviii | Compensation Validation | ✅ Done | `eligibility_decisions` `response_flags` | `python_validation/pipeline.py` `complaint_rules/eligibility.yaml` +1 more | Compensation carries a ceiling as well as an outcome, and the guard enforces both. An amount above the cap is the expensive failure the outcome che… |
| xxix | Professional Response Generation | ✅ Done | `responses` `response_flags` `genai_runs` | `genai_pipeline/response.py` `prompt_templates/customer_response/` | Generated from the reconciled record and the retrieved policy, never from raw Pipeline 1 output, so a classification the rules overrode cannot reac… |
| xxx | Response Tone Management | ✅ Done | `responses` | `genai_pipeline/response.py` | Tone is chosen from the reconciled urgency, not by the model. A safety incident answered breezily is a complaint of its own, so that decision does … |
| xxxi | Unsupported Promise Detection | ✅ Done | `response_flags` `promise_patterns` `responses` | `security/response_guard.py` `genai_pipeline/response.py` | One deterministic rule: a promise of type T is unsupported unless Pipeline 2 derived an eligibility decision of type T with outcome ELIGIBLE. CONDI… |
| xxxii | Hallucination Detection | ✅ Done | `response_flags` `complaint_policy_refs` | `hallucination_checks/citation_validator.py` `hallucination_checks/claim_support.py` +1 more | Two questions, kept apart: does the source exist, and does the source say it. Citations resolve to a chunk and their version is classified, so an i… |
| xxxiii | Escalation Detection | ✅ Done | `escalations` `validation_runs` `comparisons` | `python_validation/rule_engine.py` `genai_pipeline/intelligence.py` +1 more | Both pipelines decide whether to escalate and the comparison engine records where they differ, but the rules are not outvoted: a mandatory escalati… |
| xxxiv | Escalation Level Assignment | ✅ Done | `escalation_levels` `escalations` `validation_runs` | `comparison_engine/ladders.py` `comparison_engine/decision.py` +1 more | The floor may be raised and never lowered, and it is enforced against the model, the comparison engine and a human reviewer alike -- an override th… |
| xxxv | Escalation Notes Generation | ✅ Done | `escalations` `genai_runs` | `genai_pipeline/escalation_notes.py` `prompt_templates/escalation_note/v1.0.j2` | Written from the reconciled record, like the customer reply and for the same reason: a classification the rules overrode must not reach a colleague… |
| xxxvi | Escalation Validation | ✅ Done | `validation_runs` | `python_validation/rule_engine.py` `python_validation/pipeline.py` | The floor is a rank the reconciler may raise but never lower. This is the answer to the Escalation Trap (SRS 1.8 #7). |
| xxxvii | Follow-Up Communication Generation | ✅ Done | `follow_ups` | `complaint_processing/followup.py` | Five trigger types, each naming why the system owes contact. The message is composed from the stored trigger -- the outstanding eligibility conditi… |
| xxxviii | Follow-Up Requirement Detection | ✅ Done | `follow_ups` `validation_runs` `sla_policies` | `complaint_processing/followup.py` `python_validation/rule_engine.py` | Every trigger is a stored fact, never the model saying a follow-up was needed -- follow_up_required reaches here through the reconciled record, whe… |
| xxxix | Missing Information Detection | ✅ Done | `complaints` | `schemas/genai.py` `genai_pipeline/intelligence.py` +1 more | Pipeline 1 reports what it needed and did not have, and intake writes it to complaints.missing_information. Declaring the gap is treated as a corre… |
| xl | Clarification Question Generation | ✅ Done | `clarification_questions` | `schemas/genai.py` `complaint_processing/intake.py` | Schema-enforced: a result claiming insufficient_information without asking a question is rejected outright. Half an answer -- declaring the gap and… |
| xli | Complaint Summary Generation | ✅ Done | `complaints` | `genai_pipeline/intelligence.py` | Generated, schema-validated, reconciled against the rule engine and written onto the complaint at intake. complaints.summary. |
| xlii | Agent Guidance | ✅ Done | `agent_guidance` | `genai_pipeline/intelligence.py` `python_validation/rule_engine.py` | Rule-derived prohibitions are written as MANDATORY caution items an agent cannot dismiss; model guidance is advisory. The difference is the point: … |
| xliii | Structured JSON Output | ✅ Done | `genai_runs` | `schemas/genai.py` `genai_pipeline/validator.py` | Gemini enforces the schema during decoding; the OpenAI-compatible fallbacks cannot, so the schema is restated in the prompt and Pydantic is the enf… |
| xliv | JSON Schema Validation | ✅ Done | `genai_runs` | `genai_pipeline/validator.py` | Four gates: JSON extraction, Pydantic shape, reference codes resolved against the live taxonomy, and every cited chunk_key resolved against the kno… |
| xlv | Python Ground-Truth Validation | ✅ Done | `validation_runs` `rule_hits` | `python_validation/pipeline.py` `python_validation/cli.py` +3 more | — |
| xlvi | Classification Comparison | ✅ Done | `comparisons` | `comparison_engine/diff.py` `comparison_engine/fields.py` +2 more | Category and subcategory compared field by field; every row stores an explanation of the disagreement, not merely its existence. |
| xlvii | Routing Comparison | ✅ Done | `comparisons` | `comparison_engine/diff.py` `comparison_engine/fields.py` +2 more | Department and support department. A disagreement is CRITICAL and the rule-derived destination stands. |
| xlviii | Urgency Comparison | ✅ Done | `comparisons` | `comparison_engine/diff.py` `comparison_engine/fields.py` +2 more | Urgency and priority compared by ladder rank, not string equality, so the direction of a disagreement is recorded. Priority ranks are inverted on l… |
| xlix | Escalation Comparison | ✅ Done | `comparisons` | `comparison_engine/diff.py` `comparison_engine/fields.py` +2 more | Compared against the mandatory floor. A GenAI level below the rule-derived one is recorded as GENAI_BELOW_RULE_DERIVED and raised to the floor in t… |
| l | Policy Traceability | ✅ Done | `complaint_policy_refs` `chunks` `document_versions` +1 more | `hallucination_checks/citation_validator.py` `comparison_engine/engine.py` | Every reference that touches a complaint -- cited by the model, required by a matched rule, or surfaced by retrieval -- is written to complaint_pol… |
| li | Verification Score | ✅ Done | `verification_decisions` | `comparison_engine/decision.py` `security/response_guard.py` | Three scores, each computed from stored rows and each carrying its own numerator and denominator. Agreement and traceability are settled at reconci… |
| lii | Prompt Template Management | ✅ Done | `prompt_versions` | `genai_pipeline/prompts.py` | Templates live only in prompt_templates/<name>/v<major>.<minor>.j2 and are reached only through this module. Each is checksummed, so an edit withou… |
| liii | Prompt Version Tracking | ✅ Done | `genai_runs` `prompt_versions` `validation_runs` | `src/db/models/pipelines.py` | Prompt version, provider, model, timestamp and policy version are all stored per analysis. |
| liv | Prompt Injection Protection | ✅ Done | `injection_patterns` `injection_events` | `security/injection_defense.py` `genai_pipeline/intelligence.py` | Four layers: structural fencing with forged-delimiter stripping, 28 configurable detection patterns, Unicode neutralisation, and the structural imm… |
| lv | Adversarial Complaint Detection | ✅ Done | `injection_events` `complaints` | `security/injection_defense.py` `security/manipulation_guard.py` +5 more | Four layers of defence, and a flagged complaint is never refused: it is recorded, analysed on its merits, and routed to a reviewer with reason SENS… |
| lvi | Duplicate Complaint Detection | ✅ Done | `complaint_links` `complaints` | `complaint_processing/dedupe.py` | Exact and near duplicates are linked, never refused: a customer who submits twice because the first attempt appeared to fail still needs an answer.… |
| lvii | Complaint History | ✅ Done | `complaints` `customers` `complaint_status_history` | `src/db/models/complaints.py` | — |
| lviii | Repeat Complaint Detection | ✅ Done | `complaint_links` `complaints` | `complaint_processing/dedupe.py` | Counted from stored records of prior UNRESOLVED contacts, never from the complaint claiming to be a repeat. 'I have called five times' is a sentime… |
| lix | SLA Tracking | ✅ Done | `sla_events` `sla_policies` `complaints` | `src/services/sla.py` `src/api/v1/review.py` | **Gap:** Policies are seeded; the clock service is not written. |
| lx | SLA Risk Detection | ✅ Done | `sla_events` | `src/services/sla.py` | At-risk is a warning while there is still time; a breach is a fact recorded afterwards. risk_threshold_pct decides how much of the window must elap… |
| lxi | Manual Review Queue | ✅ Done | `review_queue` `verification_decisions` | `src/services/review.py` `src/api/v1/review.py` | Derived from the stored verification decision plus any intake finding marked ROUTED_TO_REVIEW, never hand-populated. Deciding twice is how a queue … |
| lxii | Reviewer Decision | ✅ Done | `review_actions` `review_queue` | `src/services/review.py` `src/api/v1/review.py` | Approve, reject, modify, reclassify, reassign, escalate, regenerate or comment. Every action writes a row carrying the before and after values. An … |
| lxiii | Reviewer Override | ✅ Done | `review_actions` `escalations` `complaints` | `src/services/review.py` | A reviewer may raise an escalation and may not lower it below the mandatory floor. The refusal is explicit and names the floor, because a reviewer … |
| lxiv | Audit Trail | ✅ Done | `audit_log` | `src/services/audit.py` `src/api/v1/audit.py` | The trail is readable, not only written: managers, admins and evaluators page through it with entity/action/actor filters, and any entity's own his… |
| lxv | Complaint Status Tracking | ✅ Done | `complaint_status_history` `audit_log` | `src/services/lifecycle.py` | Permitted transitions are declared as a graph, and a move outside it is refused with 422 naming what is permitted instead. Without that, a complain… |
| lxvi | Customer Dashboard | ✅ Done | `complaints` `clarification_questions` `complaint_attachments` +1 more | `src/api/v1/complaints.py` `complaint_processing/customer_actions.py` | A list of the customer's own complaints and a tracking view of one, both built from a single customer-safe projection so they cannot drift. That pr… |
| lxvii | Agent Dashboard | ✅ Done | `complaints` | `src/api/v1/analytics.py` | An agent's own workload, scoped to the caller rather than taking a user id, so one agent cannot read another's queue by guessing an identifier. |
| lxviii | Administrator Dashboard | ✅ Done | `complaints` `review_queue` `injection_events` +1 more | `src/services/analytics.py` `src/api/v1/analytics.py` +1 more | The nine SRS items plus users and sign-ins, refreshed live: the page polls GET /api/live/pulse and re-reads when a complaint, account, email or sta… |
| lxix | Complaint Analytics | ✅ Done | `complaints` `escalations` `sla_events` | `src/services/analytics.py` | Volume, category distribution, department load with open backlog, escalation rate by level and trigger, and SLA compliance. Every figure is an aggr… |
| lxx | Trend Detection | ✅ Done | `trend_snapshots` | `src/services/trends.py` `src/api/v1/analytics.py` | A trend is a change between two periods, stored with its own previous value so it can be compared against history rather than recomputed per page l… |
| lxxi | Search and Filtering | ✅ Done | `complaints` | `src/api/v1/complaints.py` | Filter by status, category, department, urgency, priority, verification outcome, dataset tag and review state, with text search across title, body … |
| lxxii | Reports | ✅ Done | `report_exports` `comparisons` `sla_events` +1 more | `src/services/reports.py` `src/api/v1/analytics.py` | Six reports, each assembled from stored rows. COMPARISON is Deliverable 8: one row per compared field per complaint with both readings, which preva… |
| lxxiii | Export | ✅ Done | `report_exports` | `src/services/reports.py` | CSV (UTF-8 with a BOM so Excel on Windows does not mangle currency symbols), XLSX with a frozen styled header, and landscape PDF with a repeating h… |
| lxxiv | Error Handling | ✅ Done | — | `src/core/errors.py` `src/core/middleware.py` | Uniform error envelope with request_id on every failure; API, parsing, validation and database errors each have a dedicated handler. |
| lxxv | Responsive Web Interface | 🖥️ Frontend | — | `frontend/` | Next.js + TypeScript client, built against this OpenAPI schema. |

---

## 1.2 Development Steps

| Step | Name | Status | Artefacts |
|---|---|---|---|
| 1 | Fictional Organisation Creation | ✅ Done | `config/taxonomy.yaml` |
| 2 | Knowledge-Base Document Creation | ✅ Done | `../dataset/raftarxpress/documents/` |
| 3 | Mandatory Input Formats PDF and DOCX | ✅ Done | `document_processing/pdf_parser.py` `document_processing/docx_parser.py` |
| 4 | Document Validation | ✅ Done | `document_validation_issues` |
| 5 | Document Parsing | ✅ Done | `document_sections` |
| 6 | Document Chunking | ✅ Done | `chunks` |
| 7 | Policy Version Control | ✅ Done | `document_versions` |
| 8 | Complaint Resolution Rule Matrix | ✅ Done | `rules` `complaint_rules/` |
| 9 | Complaint Submission | ✅ Done | `complaints` |
| 10 | Complaint Validation | ✅ Done | `complaint_validation_issues` |
| 11 | Complaint Pre-processing | ✅ Done | `complaint_processing/preprocess.py` |
| 12 | Complaint Issue Identification | ✅ Done | `complaints.primary_issue` |
| 13 | Secondary Issue Identification | ✅ Done | `complaints.secondary_issue` |
| 14 | Complaint Category Classification | ✅ Done | `categories` |
| 15 | Subcategory Classification | ✅ Done | `subcategories` |
| 16 | Entity Extraction | ✅ Done | `complaint_entities` |
| 17 | Sentiment Analysis | ✅ Done | `complaints.sentiment` |
| 18 | Emotion and Tone Indicators | ✅ Done | `complaints.emotion_indicators` |
| 19 | Urgency Classification | ✅ Done | `validation_runs.derived_urgency` |
| 20 | Priority Assignment | ✅ Done | `priority_levels` |
| 21 | Tricky Priority Cases | 🟡 Partial | `complaint_rules/` `lexicon_terms` |
| 22 | Department Routing | ✅ Done | `departments` |
| 23 | Routing Validation | ✅ Done | `python_validation/rule_engine.py` |
| 24 | Multi-Department Complaint Detection | ✅ Done | `complaints.support_department_id` `routing_rules/departments.yaml` |
| 25 | Policy Retrieval | ✅ Done | `knowledge_base/retrieval.py` |
| 26 | Policy Applicability Validation | ✅ Done | `complaint_policy_refs.applicability` `knowledge_base/versioning.py` `hallucination_checks/citation_validator.py` |
| 27 | Resolution Step Generation | ✅ Done | `resolution_steps` |
| 28 | Resolution Validation | ✅ Done | `resolution_steps.status` `resolution_steps.explanation` `python_validation/resolution.py` +1 more |
| 29 | Refund Eligibility | ✅ Done | `eligibility_decisions` `eligibility_decisions.python_outcome` `complaint_rules/eligibility.yaml` |
| 30 | Replacement Eligibility | ✅ Done | `eligibility_decisions.conditions_evaluated` `complaint_rules/eligibility.yaml` |
| 31 | Compensation Validation | ✅ Done | `eligibility_decisions.max_amount` `eligibility_decisions.currency` `security/response_guard.py` +1 more |
| 32 | Customer Response Generation | ✅ Done | `responses` `genai_pipeline/response.py` `prompt_templates/customer_response/` |
| 33 | Response Tone | ✅ Done | `responses.tone` |
| 34 | Unsupported Promise Detection | ✅ Done | `promise_patterns` `response_flags` `security/response_guard.py` |
| 35 | Hallucination Detection | ✅ Done | `hallucination_checks/` `complaint_policy_refs` `response_flags` |
| 36 | Escalation Detection | ✅ Done | `escalations` |
| 37 | Escalation Level | ✅ Done | `escalation_levels` |
| 38 | Escalation Notes Generation | ✅ Done | `escalations.notes` `genai_pipeline/escalation_notes.py` `prompt_templates/escalation_note/v1.0.j2` |
| 39 | Escalation Validation | ✅ Done | `validation_runs.escalation_floor_code` |
| 40 | Follow-Up Communication | ✅ Done | `follow_ups` `follow_ups.message` `complaint_processing/followup.py` |
| 41 | Follow-Up Scheduling | ✅ Done | `follow_ups.due_at` `sla_policies.first_response_mins` `tests/test_completion.py` |
| 42 | Missing Information Detection | ✅ Done | `complaints.missing_information` |
| 43 | Clarification Question Generation | ✅ Done | `clarification_questions` |
| 44 | Complaint Summary Generation | ✅ Done | `complaints.summary` |
| 45 | Agent Guidance | ✅ Done | `agent_guidance` |
| 46 | GenAI JSON Schema Validation | ✅ Done | `genai_pipeline/validator.py` `genai_runs.schema_errors` |
| 47 | Invalid GenAI Response Handling | ✅ Done | `genai_runs.status` `genai_pipeline/intelligence.py` |
| 48 | Prompt Template Management | ✅ Done | `prompt_versions` `prompt_templates/` `genai_pipeline/prompts.py` |
| 49 | Prompt Version Logging | ✅ Done | `genai_runs.prompt_version` `genai_runs.knowledge_base_version` `genai_runs.policy_snapshot` |
| 50 | Prompt Injection Protection | ✅ Done | `injection_patterns` `injection_events` `security/injection_defense.py` |
| 51 | Adversarial Complaint Detection | ✅ Done | `injection_events` |
| 52 | Duplicate Complaint Detection | ✅ Done | `complaint_links` |
| 53 | Complaint History | ✅ Done | `complaints.previous_complaint_id` |
| 54 | Repeat Complaint Detection | ✅ Done | `complaints.repeat_count` |
| 55 | SLA Tracking | ✅ Done | `sla_policies` |
| 56 | SLA Risk Detection | ✅ Done | `sla_events.at_risk` |
| 57 | Manual Review Queue | ✅ Done | `review_queue` |
| 58 | Reviewer Actions | ✅ Done | `review_actions` |
| 59 | Reviewer Override | ✅ Done | `review_actions.original_value` |
| 60 | Complaint Status Management | ✅ Done | `complaint_status_history` `src/services/lifecycle.py` `tests/test_lifecycle.py` |
| 61 | Customer Dashboard | ✅ Done | `src/api/v1/complaints.py` |
| 62 | Agent Dashboard | ✅ Done | `src/api/v1/complaints.py` |
| 63 | Administrator Dashboard | ✅ Done | `src/api/v1/analytics.py` |
| 64 | Complaint Analytics | ✅ Done | `src/services/analytics.py` |
| 65 | Trend Detection | ✅ Done | `trend_snapshots` |
| 66 | Search and Filtering | ✅ Done | `src/api/v1/complaints.py` |
| 67 | Reports | ✅ Done | `report_exports` |
| 68 | Export | ✅ Done | `src/services/reports.py` |

---

## 1.7 Non-Functional Requirements

### NFR-1 — Performance  🟡 Partial

**Target:** Analyse, validate and generate an initial recommendation within 20 seconds.

**Approach:** Latency is recorded per pipeline run and surfaced in the benchmark console and the X-Response-Time-ms header, so the claim is measured rather than asserted.

**Evidence:** `genai_runs.latency_ms` `validation_runs.latency_ms`

### NFR-2 — Scalable  🟡 Partial

**Target:** 10000 complaints, 100 categories and subcategories, 1000 knowledge-base documents.

**Approach:** Indexed query paths, pagination on every list endpoint, batch job runner.

**Evidence:** `ix_comp_status_created` `ix_comp_queue` `ix_chunks_embedding` `ix_comp_fts`

### NFR-3 — Usable  🖥️ Frontend

**Target:** Intuitive interface for customers, agents, reviewers, managers and administrators.

### NFR-4 — Accuracy and Compliance  🟡 Partial

**Target:** All mandatory escalation conditions and critical routing rules enforced before final verification; policy-based recommendations carry valid source references.

**Approach:** Mandatory escalation recall is a headline benchmark metric with a target of 100 percent; prohibited-action violations target zero.

**Evidence:** `validation_runs.escalation_floor_code` `complaint_policy_refs.was_active` `benchmark_runs.metrics` `src/services/benchmark.py`

### NFR-5 — Available  🟡 Partial

**Target:** 99 percent uptime during evaluation, excluding external GenAI API outages.

**Approach:** Health endpoint plus an external uptime pinger to keep the free-tier instance warm. The application stays fully functional with the GenAI API unavailable, because Pipeline 2 is deterministic.

**Evidence:** `health_endpoint`

---

## 1.8 Competition Integrity and Anti-Shortcut Requirements

| # | Item | Status | Evidence | Note |
|---|---|---|---|---|
| 1 | Unique Organisation Scenario | ✅ Done | `config/taxonomy.yaml` | — |
| 2 | Unique Complaint Dataset | ✅ Done | `complaints.dataset_tag` `complaints.expected_category_code` `benchmark_runs` +2 more | — |
| 3 | Hidden Complaint Dataset | ✅ Done | `complaints.dataset_tag` `complaint_validation_issues` | — |
| 4 | Hidden Policy Update | ✅ Done | `document_versions.status` `document_versions.superseded_by_id` `document_versions.superseded_at` +4 more | A policy dropped in mid-evaluation is picked up with no redeployment: activating the new version demotes the old one to SUPERSEDED, retrieval stops returning it from that moment, and the next analysis is grounded in the new text. Proved end to end in tests/test_policy_update.py -- the corpus answers with the old figure, an admin activates v2 through the API, and the corpus answers with the new one, in a single test with no restart between the two. The old version is demoted, never deleted. Contradiction detection needs the superseded text to compare against, and every decision taken while it governed would otherwise become unexplainable. A citation to it now resolves but scores OUTDATED, which is the distinction that matters: a reply grounded in last year's policy looks perfectly well-cited, and the applicability verdict is the only thing that tells them apart. Activation also answers the question an administrator asks the moment they press the button -- what did I just invalidate? Every complaint that cited the superseded version is listed, read from stored citations rather than recomputed, with open ones counted separately because a closed complaint decided under the old policy is history and an open one is a decision somebody is still about to act on. Nothing is re-analysed automatically: re-running hundreds of complaints would spend the free-tier quota in one click, and silently rewriting a decision an agent has already acted on is worse than leaving it visibly stale. |
| 5 | Hidden Complaint Category | ✅ Done | `categories` | Categories are database rows, not code. A new one needs no deploy. |
| 6 | Sentiment-Urgency Trap | ✅ Done | `lexicon_terms` | Emotional signals are recorded but forbidden from urgency rules; enforced by test. |
| 7 | Escalation Trap | ✅ Done | `validation_runs.escalation_floor_code` `rules.is_mandatory_escalation` | — |
| 8 | Prompt Injection Challenge | ✅ Done | `injection_patterns` `injection_events` `complaints.injection_suspected` +1 more | — |
| 9 | Unsupported Promise Challenge | ✅ Done | `promise_patterns` `response_flags` `responses.guard_status` +1 more | — |
| 10 | Contradictory Policy Challenge | ✅ Done | `complaint_policy_refs.conflict_with_ref` `complaint_policy_refs.precedence_tier` `hallucination_checks/policy_conflict.py` +3 more | Two policies that disagree are detected, the documented precedence order is applied, and the resolution is recorded rather than taken silently. That last part is the whole requirement: retrieval and precedence already made the system follow the higher policy, but a system that quietly follows the right one looks identical to a system that never noticed the wrong one existed, and the second is worth nothing to anybody auditing it. What counts as a disagreement is the claim checker's own definition, imported rather than restated: two sentences, one from each document, that share most of their vocabulary in BOTH directions -- so they are about the same thing -- and then either negate one another or state different figures in the same unit. A one-way containment test matches a short sentence against a long one that merely contains its words, and a detector that fires on agreeing policies floods the trace view until an agent stops reading it; the mutual test and the 0.60 floor in policy.yaml are what keep it quiet enough to be believed. Comparison is over each document's whole active version, not the two chunks that happened to be retrieved: a planted contradiction rarely sits in the two passages retrieval picked. The overruled reference is marked, never deleted -- conflict_with_ref names what beat it and the reason names the governing precedence tier -- because removing it would leave no evidence the conflict was ever found. Surfaced on GET /api/complaints/{ref}/explain as policy_conflicts. |
| 11 | Missing Information Challenge | ✅ Done | `complaints.missing_information` `clarification_questions` `complaint_processing/followup.py` +1 more | — |
| 12 | Multi-Issue Complaint Challenge | ✅ Done | `complaints.primary_issue` `complaints.secondary_issue` `complaints.support_department_id` +1 more | — |
| 13 | Repeat Complaint Challenge | ✅ Done | `complaints.repeat_count` `complaints.previous_complaint_id` `complaint_links` +2 more | — |
| 14 | Live Modification Challenge | ✅ Done | `rules` `categories` `departments` +8 more | Taxonomy, rules, lexicons, thresholds, comparison weights, SLA targets and prompt versions are all database rows read at evaluation time, and all of them are editable through /api/admin with no redeployment. POST /api/admin/rules/test is what makes the demonstration legible: it runs Pipeline 2 alone over a piece of text and returns what the rules conclude right now, deterministically, with no provider call and nothing written -- so an evaluator can edit a rule, post the same text again and see the difference in two requests, as often as they like, without spending the free-tier quota or filling the register with test rows. POST /api/admin/rules/reload is the undo, restoring the committed matrix so the next demonstration starts from a known state. Three guards keep the surface from becoming a back door. A rule that sets a mandatory escalation may have its level raised but never lowered, and cannot be deactivated at all: the floor is already enforced against the model, the comparison engine and a human reviewer, and an admin API able to switch off the rule that sets it would be a fourth way through and the quietest of the four, because it leaves no override on any complaint to notice. A change is refused at save time rather than at evaluation time, with every problem named at once -- a malformed condition, a signal no active lexicon term raises, an outcome naming a code that does not exist -- because a rule that saves cleanly and then silently never fires looks exactly like the system ignoring the evaluator. And every rule change re-stamps the ruleset version, so a validation_run recorded before the edit stays attributable to the rules that actually produced it. |
| 15 | Deliberate Defect Challenge | ✅ Done | `security/deliberate_defect.py` `security/response_guard.py` `comparison_engine/decision.py` +1 more | Four documented defects, each run through the production detector that should catch it, all four caught: a reply promising a refund no ELIGIBLE decision authorises (response guard, CRITICAL); an authorised compensation for ten times its ceiling -- the expensive one, because eligibility genuinely says yes, every other gate passes and only the number is wrong; a citation to a policy that does not exist; and a model downgrading a mandatory safety escalation to NONE, which the floor raises back to CRITICAL_MGMT. The defect is never installed. There is no flag that makes SupportNova behave badly and no configuration row that degrades it: each demonstration builds its faulty artefact inside one request, checks it and discards it. A switch that could break the running system in exchange for a better demo can be left on, and then the defect is not deliberate any more. One test asserts that isolation directly -- a demonstration persists nothing -- and a second asserts that no file in any of the six pipeline packages so much as mentions the module, so there is no path by which a demonstration could reach a real complaint. The detectors are the real ones: scan_response is the same function that guards every customer reply and build_reconciled the same one that enforces the floor on every complaint. A simplified checker written here would demonstrate only that the demonstration works. Served at GET /api/admin/defects and POST /api/admin/defects/demonstrate. |
| 16 | GitHub Activity | ⬜ Planned | `.github/workflows/ci.yml` | — |
| 17 | No Hard-Coded Outputs | ✅ Done | `genai_runs` `validation_runs` `rule_hits` +1 more | Every displayed value traces to a stored run record or rule hit. |
| 18 | GenAI API Restriction | ✅ Done | `python_validation/` | Pipeline 2 imports no provider client; its CLI runs with no API key set. |
| 19 | AI Tool Usage Declaration | ✅ Done | `../AI_USAGE.md` | — |

