# SupportNova test cases

**Result: 989 automated tests in 41 files, all passing** (`989 passed`, Python 3.13 on Windows, SQLite test
database, 27 September 2026). Continuous integration (`.github/workflows/ci.yml`) runs the same suite on every
push twice: on SQLite, and on PostgreSQL 16 with pgvector.

This document lists, for each test category the brief requires, the real test files and representative test
functions, what they assert, how many tests are in scope, and the command that runs just that category. It ends
with the per-file inventory and a set of manual test cases for the web interface.

---

## How the suite runs

All commands run from the `backend` folder in PowerShell:

```powershell
cd backend
.venv\Scripts\python -m pytest -q                      # the whole suite: 989 passed
.venv\Scripts\python -m pytest -q tests/test_rbac.py   # one file
.venv\Scripts\python -m pytest -q -k "floor"           # every test whose name contains "floor"
```

* **Isolated database.** `tests/conftest.py` points the application at its own SQLite file,
  `backend/var/test_supportnova.db`, before anything is imported. The suite never touches the live or development
  database. Run **one pytest process at a time**: two concurrent runs share that file and corrupt each other.
* **Offline and free.** Every AI key is blanked, embeddings are disabled and providers are replaced by stubs that
  misbehave on purpose (invalid JSON, invented citations, 429s, outages, capitulating to an attack). No test needs
  a network connection or spends quota.
* **PostgreSQL run.** Set `SUPPORTNOVA_TEST_DATABASE_URL=postgresql+psycopg://...` to a throwaway database to run
  the same suite on Postgres. The suite drops and recreates every table there, so never point it at a database
  you care about.
* **Test IDs.** Each category below gives exact pytest node IDs (`file::Class::test`). Categories overlap: one test
  can serve two categories, so the category counts do not add up to 989. "Tests in scope" counts collected tests,
  including every parametrised case.

## Summary by category

| # | Category | Tests in scope | Main files |
|---|---|---|---|
| 1 | Functional | 108 | `test_system`, `test_lifecycle`, `test_dashboards`, `test_complaints_api`, `test_requirements_coverage` |
| 2 | Complaint submission | 52 | `test_complaints_api`, `test_live_progress`, `test_file_intake`, `test_email_channel` |
| 3 | Document upload | 44 | `test_documents_api`, `test_document_processing`, `test_knowledge_base`, `test_customer_actions` |
| 4 | Parsing | 70 | `test_document_processing`, `test_complaints_api`, `test_email_channel`, `test_benchmark` |
| 5 | GenAI API | 73 | `test_genai_pipeline`, `test_model_chain`, `test_live_progress` |
| 6 | JSON | 28 | `test_genai_pipeline`, `test_response_guard`, `test_assistant` |
| 7 | Classification | 21 | `test_python_validation`, `test_comparison_engine`, `test_genai_pipeline` |
| 8 | Routing | 10 | `test_python_validation`, `test_comparison_engine`, `test_rbac`, `test_customer_actions` |
| 9 | Urgency | 21 | `test_python_validation`, `test_system`, `test_comparison_engine`, `test_response_guard` |
| 10 | Escalation | 28 | `test_python_validation`, `test_comparison_engine`, `test_review_sla`, `test_admin_config`, `test_benchmark` |
| 11 | Resolution | 39 | `test_completion`, `test_response_guard`, `test_python_validation` |
| 12 | Policy | 44 | `test_knowledge_base`, `test_policy_conflict`, `test_policy_update` |
| 13 | Hallucination | 61 | `test_hallucination_checks`, `test_comparison_engine`, `test_response_guard` |
| 14 | Prompt injection | 69 | `test_jailbreak_guard`, `test_document_injection`, `test_deliberate_defect` |
| 15 | Duplicate | 15 | `test_complaints_api`, `test_documents_api`, `test_email_channel` |
| 16 | Missing information | 24 | `test_customer_actions`, `test_genai_pipeline`, `test_complaints_api` |
| 17 | Multi-issue | 9 | `test_python_validation`, `test_comparison_engine` |
| 18 | Hidden-data readiness | 44 | `test_benchmark`, `test_admin_config` |
| 19 | Boundary | 37 | spread across 11 files |
| 20 | Security | 109 | `test_auth`, `test_rbac`, `test_account_security`, `test_register`, `test_audit_api` |

---

## 1. Functional tests (108 in scope)

End-to-end API behaviour of the main workflow: submit, read back, move through the lifecycle, dashboards,
exports, audit, and the machine-checked requirement registry.

| Test | Asserts |
|---|---|
| `test_system.py::test_health_is_public_and_reports_ok` | `/api/health` answers without sign-in and reports `ok` |
| `test_system.py::test_version_exposes_provenance` | `/api/version` names the active prompt, model and ruleset |
| `test_complaints_api.py::TestEndpoints::test_submit_returns_the_stored_complaint` | `POST /api/complaints` returns the stored complaint and its reference |
| `test_complaints_api.py::TestEndpoints::test_reanalysis_reports_what_changed` | Re-analysis says which fields changed |
| `test_lifecycle.py::TestEndpoints::test_every_offered_action_is_one_the_api_accepts` | Every status move the interface offers is one the API accepts |
| `test_lifecycle.py::TestGraph::test_a_closed_complaint_can_only_be_reopened` | The status graph is enforced |
| `test_completion.py::TestEndpoints::test_confirming_a_step_moves_the_coverage` | Confirming a checklist step updates resolution coverage |
| `test_dashboards.py::test_the_admin_dashboard_has_every_listed_figure` | The administrator dashboard carries every figure the brief lists |
| `test_people.py::test_a_customers_complaint_and_its_history_reach_the_admin` | A customer's complaint and its history appear on the admin's user page |
| `test_analytics_reports.py::TestEndpoints::test_export_downloads_a_file` | A report downloads as a file |
| `test_email_relay.py::test_the_reply_goes_out_with_the_secret_and_the_inline_logo` | Email replies go through the Gmail relay with its secret and the inline logo |
| `test_requirements_coverage.py::test_endpoints_for_done_requirements_exist` | Every requirement marked done names endpoints, tables and modules that really exist |

```powershell
.venv\Scripts\python -m pytest -q tests/test_system.py tests/test_complaints_api.py::TestEndpoints tests/test_lifecycle.py tests/test_dashboards.py tests/test_completion.py::TestEndpoints tests/test_organisation.py tests/test_people.py tests/test_analytics_reports.py::TestEndpoints tests/test_audit_api.py::TestTrail tests/test_email_relay.py tests/test_requirements_coverage.py
```

## 2. Complaint-submission tests (52 in scope)

| Test | Asserts |
|---|---|
| `test_complaints_api.py::TestValidation::test_only_an_empty_complaint_is_rejected` | Only an empty complaint is refused |
| `test_complaints_api.py::TestValidation::test_a_rejected_attempt_is_still_recorded` | Even a refused attempt is written to the validation log |
| `test_complaints_api.py::TestValidation::test_an_unsupported_attachment_is_dropped_not_refused` | A bad attachment is dropped; the complaint is still accepted |
| `test_complaints_api.py::TestWriteBack::test_the_reconciled_decision_is_written_to_the_complaint` | The reconciled decision (rules winning where they must) is stored on the complaint |
| `test_complaints_api.py::TestWriteBack::test_the_complaint_survives_an_analysis_failure` | The complaint is stored before analysis and kept (marked failed) if analysis throws |
| `test_live_progress.py::TestStreamEndpoint::test_the_stream_narrates_every_step_and_ends_with_the_result` | The live submission stream reports each pipeline step, then the result |
| `test_live_progress.py::TestStreamEndpoint::test_a_customer_gets_the_customer_view_only` | A customer's stream never reveals internal detail |
| `test_file_intake.py::test_a_word_letter_becomes_a_draft` | An uploaded DOCX letter is read into a complaint draft |
| `test_email_channel.py::TestInbound::test_a_complaint_email_is_filed_and_answered` | An emailed complaint is registered, analysed and answered |
| `test_email_channel.py::TestInbound::test_automatic_mail_is_ignored_and_never_answered` | Auto-replies and bounces are never filed or answered |
| `test_assistant.py::TestDrafts::test_chatting_never_creates_a_complaint` | The chat assistant only drafts; the customer must confirm |
| `test_customer_actions.py::TestPreview::test_the_preview_writes_no_complaint` | The as-you-type preview stores nothing |

```powershell
.venv\Scripts\python -m pytest -q tests/test_complaints_api.py::TestValidation tests/test_complaints_api.py::TestWriteBack tests/test_live_progress.py::TestStreamEndpoint tests/test_file_intake.py tests/test_customer_actions.py::TestPreview tests/test_customer_actions.py::TestIntakeResponseShape tests/test_email_channel.py::TestInbound tests/test_assistant.py::TestDrafts
```

## 3. Document-upload tests (44 in scope)

| Test | Asserts |
|---|---|
| `test_documents_api.py::test_admin_can_upload_a_pdf` / `test_admin_can_upload_a_docx` | Both formats ingest end to end |
| `test_documents_api.py::test_unsupported_file_type_is_refused_with_a_reason` | Wrong type is refused with a stated reason |
| `test_documents_api.py::test_duplicate_upload_is_reported_per_file_not_as_an_error` | One duplicate in a batch does not fail the others |
| `test_documents_api.py::test_evaluator_can_read_but_not_upload` | Only administrators upload |
| `test_document_processing.py::test_format_is_detected_from_magic_bytes_not_extension` | File type comes from the bytes, not the name |
| `test_document_processing.py::test_extension_spoofing_is_recorded_but_content_is_trusted` | A renamed file is recorded as spoofed |
| `test_document_processing.py::test_oversized_file_is_rejected` | Size limit enforced |
| `test_document_processing.py::test_filenames_are_sanitised` | Path characters are stripped from names |
| `test_knowledge_base.py::test_unparseable_upload_is_rejected_and_recorded` | A corrupt file is rejected and the rejection kept |
| `test_knowledge_base.py::test_document_without_metadata_lands_in_review_not_rejected` | An unfamiliar document is kept for metadata review |
| `test_customer_actions.py::TestEvidence::test_the_type_comes_from_the_bytes_not_the_name` | Customer evidence photos are typed by content |

```powershell
.venv\Scripts\python -m pytest -q tests/test_documents_api.py tests/test_knowledge_base.py::test_corpus_ingests_into_rows tests/test_knowledge_base.py::test_reuploading_the_same_file_is_rejected_and_recorded tests/test_knowledge_base.py::test_unparseable_upload_is_rejected_and_recorded tests/test_knowledge_base.py::test_document_without_metadata_lands_in_review_not_rejected tests/test_customer_actions.py::TestEvidence tests/test_document_processing.py::test_format_is_detected_from_magic_bytes_not_extension tests/test_document_processing.py::test_extension_spoofing_is_recorded_but_content_is_trusted tests/test_document_processing.py::test_empty_file_is_rejected tests/test_document_processing.py::test_unsupported_file_type_is_rejected tests/test_document_processing.py::test_oversized_file_is_rejected tests/test_document_processing.py::test_filenames_are_sanitised tests/test_document_processing.py::test_duplicate_document_is_detected_by_hash
```

## 4. Parsing tests (70 in scope)

| Test | Asserts |
|---|---|
| `test_document_processing.py::test_pdf_sections_carry_page_numbers` | PDF sections keep their page numbers |
| `test_document_processing.py::test_docx_sections_carry_paragraph_indices` | DOCX sections keep paragraph positions |
| `test_document_processing.py::test_pdf_and_docx_of_the_same_document_agree` | Both parsers produce the same sections for the same policy |
| `test_document_processing.py::test_docx_tables_are_captured_without_losing_columns` | Tables survive parsing |
| `test_document_processing.py::test_chunks_never_cross_a_section_boundary` | Chunking respects sections |
| `test_document_processing.py::test_metadata_is_read_from_the_front_matter_block` | Document id, version and dates come from the metadata block |
| `test_complaints_api.py::TestPreprocess::test_the_original_is_kept_byte_for_byte` | The raw complaint is stored unchanged beside the cleaned text |
| `test_complaints_api.py::TestPreprocess::test_invisible_and_control_characters_are_stripped` | Hidden characters are removed from the cleaned text |
| `test_email_channel.py::TestParsing::test_html_is_read_and_the_quoted_reply_dropped` | HTML email is read and quoted history dropped |
| `test_benchmark.py::TestImport::test_headers_are_matched_loosely` | `Order Ref`, `order-ref` and `ORDER_REF` are one column |
| `test_benchmark.py::TestImport::test_a_currency_symbol_in_an_amount_is_tolerated` | `Rs. 42,500` is read as 42500 |

```powershell
.venv\Scripts\python -m pytest -q tests/test_document_processing.py tests/test_complaints_api.py::TestPreprocess tests/test_email_channel.py::TestParsing tests/test_file_intake.py tests/test_benchmark.py::TestImport::test_headers_are_matched_loosely tests/test_benchmark.py::TestImport::test_a_bom_does_not_corrupt_the_first_column tests/test_benchmark.py::TestImport::test_a_currency_symbol_in_an_amount_is_tolerated tests/test_benchmark.py::TestImport::test_an_xlsx_file_imports
```

## 5. GenAI API tests (73 in scope)

Provider behaviour is tested with stubs, so every failure mode is reproducible.

| Test | Asserts |
|---|---|
| `test_genai_pipeline.py::TestProviderChain::test_retryable_failure_fails_over_to_the_next_provider` | Gemini failing hands over to Groq, then OpenRouter |
| `test_genai_pipeline.py::TestProviderChain::test_retries_are_bounded` | Retries stop at `LLM_MAX_RETRIES` |
| `test_genai_pipeline.py::TestProviderChain::test_every_attempt_is_recorded_including_the_failures` | Every call, failed or not, is stored |
| `test_genai_pipeline.py::TestProviderChain::test_empty_chain_raises_rather_than_inventing_an_answer` | No provider means no answer, never a made-up one |
| `test_genai_pipeline.py::TestOrchestration::test_total_outage_degrades_instead_of_raising` | A total outage degrades to rules-only |
| `test_genai_pipeline.py::TestPromptRegistry::test_registry_status_detects_an_edit_without_a_version_bump` | Editing a prompt without a new version is detected |
| `test_genai_pipeline.py::TestPromptRegistry::test_enum_values_come_from_the_database_not_the_template` | Category codes in the prompt come from the live taxonomy |
| `test_model_chain.py::test_a_retired_model_falls_through_to_the_next` | A retired model is skipped automatically |
| `test_model_chain.py::test_a_rate_limited_model_hands_over_to_the_next` | A 429 moves to the next model |
| `test_model_chain.py::test_the_model_that_answered_is_tried_first_next_time` | The chain remembers the last working model |
| `test_live_progress.py::TestReasoningEffort::test_gemini_25_uses_a_budget` | Per-model reasoning settings are sent correctly |
| `test_dashboards.py::test_an_empty_prepaid_balance_is_not_retried` | A 402 "insufficient balance" is final, not retried |

```powershell
.venv\Scripts\python -m pytest -q tests/test_genai_pipeline.py::TestPromptRegistry tests/test_genai_pipeline.py::TestProviderChain tests/test_genai_pipeline.py::TestOrchestration tests/test_model_chain.py tests/test_live_progress.py::TestReasoningEffort tests/test_dashboards.py::test_an_empty_prepaid_balance_is_not_retried
```

## 6. JSON tests (28 in scope)

| Test | Asserts |
|---|---|
| `test_genai_pipeline.py::TestJSONExtraction::test_recovers_from_common_formatting_slips` (5 cases) | Code fences, prose before or after the JSON, and a wrapping array are all tolerated |
| `test_genai_pipeline.py::TestJSONExtraction::test_repairs_a_trailing_comma` | A trailing comma is repaired |
| `test_genai_pipeline.py::TestJSONExtraction::test_unrecoverable_input_reports_an_error` | Garbage is reported, not guessed |
| `test_genai_pipeline.py::TestValidation::test_invalid_enum_value_is_rejected` | Values outside the schema's enums fail |
| `test_genai_pipeline.py::TestValidation::test_unknown_field_is_rejected_not_silently_dropped` | Extra fields fail validation |
| `test_genai_pipeline.py::TestValidation::test_missing_required_field_is_rejected` | Missing fields fail validation |
| `test_genai_pipeline.py::TestValidation::test_escalation_without_a_level_is_rejected` | Cross-field rules are enforced |
| `test_genai_pipeline.py::TestValidation::test_correction_instruction_names_the_field_and_its_permitted_values` | The single repair request names the field and the allowed values |
| `test_genai_pipeline.py::TestProviderSchema::test_schema_has_no_construct_a_provider_rejects` | The output schema is accepted by the providers' structured-output modes |
| `test_response_guard.py::TestResponseGeneration::test_invalid_json_is_retried_then_reported` | A reply draft with invalid JSON is retried, then reported |
| `test_assistant.py::TestWithoutAModel::test_unparseable_model_output_degrades_instead_of_failing` | The chat assistant survives unparseable output |

See also `test_genai_pipeline.py::TestOrchestration::test_invalid_output_triggers_one_bounded_repair` and
`test_repair_is_not_attempted_forever` (counted under GenAI API).

```powershell
.venv\Scripts\python -m pytest -q tests/test_genai_pipeline.py::TestJSONExtraction tests/test_genai_pipeline.py::TestValidation tests/test_genai_pipeline.py::TestProviderSchema tests/test_response_guard.py::TestResponseGeneration::test_invalid_json_is_retried_then_reported tests/test_assistant.py::TestWithoutAModel::test_unparseable_model_output_degrades_instead_of_failing tests/test_system.py::test_openapi_schema_builds
```

## 7. Classification tests (21 in scope)

| Test | Asserts |
|---|---|
| `test_python_validation.py::test_unrecognised_complaint_is_flagged_not_guessed` | Text no rule recognises is flagged, never forced into a category |
| `test_python_validation.py::test_a_scoped_rule_does_not_fire_outside_its_category` | Category-scoped rules stay in scope |
| `test_python_validation.py::test_determinism` | The same text always gets the same classification |
| `test_python_validation.py::test_rule_matrix_meets_srs_minimums` | The matrix has the rule counts the brief requires |
| `test_comparison_engine.py::TestFieldComparison::test_category_disagreement_is_recorded_with_an_explanation` | An AI/rules category mismatch is stored with its explanation |
| `test_comparison_engine.py::TestFieldComparison::test_sentiment_is_unsupported_not_a_mismatch` | Fields the rules do not derive are not counted as disagreements |
| `test_genai_pipeline.py::TestValidation::test_invented_category_is_caught_by_the_reference_gate` | A well-formed but non-existent category is rejected |
| `test_genai_pipeline.py::TestValidation::test_subcategory_from_a_different_category_is_caught` | Subcategory must belong to the category |
| `test_system.py::test_taxonomy_meets_srs_minimums` | Categories, subcategories and departments meet the minimums |
| `test_review_sla.py::TestOverrides::test_a_reclassification_is_applied_and_recorded` | A reviewer's reclassification is applied and audited |

```powershell
.venv\Scripts\python -m pytest -q tests/test_python_validation.py::test_unrecognised_complaint_is_flagged_not_guessed tests/test_python_validation.py::test_a_scoped_rule_does_not_fire_outside_its_category tests/test_python_validation.py::test_catch_all_obligations_do_not_leak_onto_recognised_complaints tests/test_python_validation.py::test_rule_matrix_meets_srs_minimums tests/test_python_validation.py::test_determinism tests/test_comparison_engine.py::TestFieldComparison tests/test_genai_pipeline.py::TestValidation::test_invented_category_is_caught_by_the_reference_gate tests/test_genai_pipeline.py::TestValidation::test_subcategory_from_a_different_category_is_caught tests/test_system.py::test_taxonomy_meets_srs_minimums tests/test_review_sla.py::TestOverrides::test_a_reclassification_is_applied_and_recorded tests/test_analytics_reports.py::TestAnalytics::test_unclassified_complaints_are_shown_not_dropped
```

## 8. Routing tests (10 in scope)

| Test | Asserts |
|---|---|
| `test_python_validation.py::test_legal_threat_routes_to_compliance` | A legal threat goes to Compliance |
| `test_comparison_engine.py::TestFieldComparison::test_rules_win_a_department_disagreement` | The rules' department prevails over the model's |
| `test_complaints_api.py::TestWriteBack::test_the_safety_complaint_lands_where_the_rules_put_it` | End to end, a safety complaint is routed to Safety |
| `test_genai_pipeline.py::TestValidation::test_invented_department_is_caught` | A department that does not exist is rejected |
| `test_rbac.py::test_an_agent_sees_their_team_and_their_assignments_only` | Routed work reaches only the owning team |
| `test_rbac.py::test_who_may_assign_whom` | Assignment permissions by role |
| `test_dashboards.py::test_an_agent_sees_their_own_team_only` | The agent dashboard is scoped to the agent's team |
| `test_customer_actions.py::TestTimeline::test_the_customer_sees_which_team_has_it_and_how_to_reach_them` | The customer is told which team has the case |
| `test_customer_actions.py::TestTimeline::test_an_unrouted_complaint_says_a_specialist` | An unrouted case is described honestly |
| `test_analytics_reports.py::TestAnalytics::test_department_load_separates_volume_from_backlog` | Department load counts volume and open backlog separately |

```powershell
.venv\Scripts\python -m pytest -q tests/test_python_validation.py::test_legal_threat_routes_to_compliance tests/test_comparison_engine.py::TestFieldComparison::test_rules_win_a_department_disagreement tests/test_complaints_api.py::TestWriteBack::test_the_safety_complaint_lands_where_the_rules_put_it tests/test_genai_pipeline.py::TestValidation::test_invented_department_is_caught tests/test_rbac.py::test_an_agent_sees_their_team_and_their_assignments_only tests/test_rbac.py::test_who_may_assign_whom tests/test_dashboards.py::test_an_agent_sees_their_own_team_only tests/test_customer_actions.py::TestTimeline::test_the_customer_sees_which_team_has_it_and_how_to_reach_them tests/test_customer_actions.py::TestTimeline::test_an_unrouted_complaint_says_a_specialist tests/test_analytics_reports.py::TestAnalytics::test_department_load_separates_volume_from_backlog
```

## 9. Urgency tests (21 in scope)

| Test | Asserts |
|---|---|
| `test_python_validation.py::test_calm_safety_report_is_critical` | A politely worded burning smell is `SAFETY`, `CRITICAL`, `P0`, `CRITICAL_MGMT` |
| `test_python_validation.py::test_furious_delivery_delay_is_not_critical` | An angry message about a late parcel stays `MEDIUM`, `P2`, no escalation |
| `test_python_validation.py::test_tone_is_detected_but_withheld_from_the_rule_engine` | Tone is recorded for analytics but invisible to the rules |
| `test_python_validation.py::test_no_rule_in_the_matrix_references_an_analytics_only_signal` | No rule can make urgency depend on anger |
| `test_python_validation.py::test_high_value_is_measured_not_guessed` | High value comes from the parsed amount |
| `test_system.py::test_safety_lexicon_exists_for_the_sentiment_urgency_trap` | The safety vocabulary is configured |
| `test_comparison_engine.py::TestLadders::test_priority_ranks_are_inverted_on_load` | P0 is ranked most severe, so under-prioritisation is detected correctly |
| `test_response_guard.py::TestTone::test_tone_follows_urgency_not_the_model` | Reply tone is set by the verified urgency |
| `test_review_sla.py::TestSLA::test_raising_priority_tightens_the_deadline` | Higher priority means a shorter SLA |
| `test_complaints_api.py::TestPreprocess::test_shouting_is_detected_and_never_corrected` | Capitals are noted, never "fixed" |

```powershell
.venv\Scripts\python -m pytest -q tests/test_python_validation.py::test_calm_safety_report_is_critical tests/test_python_validation.py::test_furious_delivery_delay_is_not_critical tests/test_python_validation.py::test_tone_is_detected_but_withheld_from_the_rule_engine tests/test_python_validation.py::test_no_rule_in_the_matrix_references_an_analytics_only_signal tests/test_python_validation.py::test_high_value_is_measured_not_guessed tests/test_system.py::test_safety_lexicon_exists_for_the_sentiment_urgency_trap tests/test_system.py::test_emotional_signals_are_marked_analytics_only tests/test_system.py::test_priority_and_escalation_ladders_are_ordered tests/test_comparison_engine.py::TestLadders tests/test_response_guard.py::TestTone tests/test_review_sla.py::TestSLA::test_raising_priority_tightens_the_deadline tests/test_complaints_api.py::TestPreprocess::test_shouting_is_detected_and_never_corrected
```

## 10. Escalation tests (28 in scope)

| Test | Asserts |
|---|---|
| `test_python_validation.py::test_mandatory_escalation_sets_a_floor` | A mandatory rule sets a minimum escalation |
| `test_python_validation.py::test_the_floor_raises_a_lower_proposal_and_never_lowers_a_higher_one` | The floor only ever raises |
| `test_python_validation.py::test_repeat_contact_forces_supervisor_escalation` | Stored repeat contacts force supervisor escalation |
| `test_comparison_engine.py::TestEscalationFloor::test_floor_holds_even_when_configuration_lets_genai_win` | The floor holds whatever the comparison weights say |
| `test_comparison_engine.py::TestEscalationFloor::test_no_escalation_at_all_is_raised_to_the_floor` | "No escalation" from the model is raised to the floor |
| `test_review_sla.py::TestOverrideFloor::test_a_reviewer_cannot_lower_an_escalation_below_the_floor` | A reviewer cannot lower it either |
| `test_review_sla.py::TestOverrideFloor::test_a_reviewer_may_raise_an_escalation` | Raising is allowed and recorded |
| `test_admin_config.py::TestFloorGuard::test_a_mandatory_escalation_rule_cannot_be_switched_off` | Live rule editing cannot remove the floor |
| `test_benchmark.py::TestEscalationRecall::test_an_under_escalation_is_caught` | The benchmark reports every under-escalated complaint |
| `test_completion.py::TestEscalationNotes::test_an_outage_costs_the_note_not_the_escalation` | An AI outage loses the handover note, never the escalation |
| `test_complaints_api.py::TestCustomerStatus::test_escalation_is_a_fact_not_a_level` | Customers see that a case is escalated, not the internal level |

```powershell
.venv\Scripts\python -m pytest -q tests/test_python_validation.py::test_mandatory_escalation_sets_a_floor tests/test_python_validation.py::test_the_floor_raises_a_lower_proposal_and_never_lowers_a_higher_one tests/test_python_validation.py::test_repeat_contact_forces_supervisor_escalation tests/test_python_validation.py::test_every_mandatory_escalation_rule_declares_a_level tests/test_comparison_engine.py::TestEscalationFloor tests/test_review_sla.py::TestOverrideFloor tests/test_admin_config.py::TestFloorGuard tests/test_benchmark.py::TestEscalationRecall tests/test_completion.py::TestEscalationNotes tests/test_analytics_reports.py::TestAnalytics::test_a_rule_derived_escalation_is_attributed_to_python tests/test_analytics_reports.py::TestAnalytics::test_the_escalation_record_names_the_rules_that_forced_it tests/test_analytics_reports.py::TestAnalytics::test_re_analysis_does_not_stack_escalation_records tests/test_complaints_api.py::TestCustomerStatus::test_escalation_is_a_fact_not_a_level
```

## 11. Resolution tests (39 in scope)

| Test | Asserts |
|---|---|
| `test_completion.py::TestResolutionValidation::test_rule_obligations_become_a_checklist` | The rules' required actions become the agent's checklist |
| `test_completion.py::TestResolutionValidation::test_a_rule_obligation_is_never_satisfied_automatically` | Only a person can tick an obligation |
| `test_completion.py::TestResolutionValidation::test_an_unauthorised_promise_in_a_step_is_prohibited` | A resolution step promising an unauthorised outcome is marked prohibited |
| `test_completion.py::TestFollowUps::test_due_dates_come_from_the_sla_policy` | Follow-up dates come from the SLA policy |
| `test_response_guard.py::TestResponseGeneration::test_a_blocked_draft_triggers_exactly_one_regeneration` | A blocked reply is regenerated once |
| `test_response_guard.py::TestResponseGeneration::test_the_rejected_draft_survives_the_regeneration` | The rejected draft is kept as evidence |
| `test_response_guard.py::TestResponseGeneration::test_an_unverified_complaint_produces_no_reply` | No reply before verification |
| `test_response_guard.py::TestResponseGeneration::test_a_total_outage_fails_without_inventing_a_reply` | No provider, no invented reply |
| `test_python_validation.py::test_refund_request_is_never_approved_at_the_desk` | A refund request needs verification, never instant approval |
| `test_python_validation.py::test_replacement_is_withheld_pending_a_safety_assessment` | A hazardous product is not replaced before assessment |
| `test_complaints_api.py::TestWriteBack::test_eligibility_decisions_are_stored_from_python_only` | Eligibility comes from the rules alone |
| `test_lifecycle.py::TestGraph::test_a_complaint_cannot_be_closed_without_being_worked` | No closing straight from new |

```powershell
.venv\Scripts\python -m pytest -q tests/test_completion.py::TestResolutionValidation tests/test_completion.py::TestFollowUps tests/test_response_guard.py::TestResponseGeneration tests/test_python_validation.py::test_replacement_is_withheld_pending_a_safety_assessment tests/test_python_validation.py::test_refund_request_is_never_approved_at_the_desk tests/test_python_validation.py::test_the_most_restrictive_eligibility_finding_wins tests/test_complaints_api.py::TestWriteBack::test_rule_obligations_become_an_agent_checklist tests/test_complaints_api.py::TestWriteBack::test_rule_prohibitions_become_mandatory_guidance tests/test_complaints_api.py::TestWriteBack::test_eligibility_decisions_are_stored_from_python_only tests/test_customer_actions.py::TestAnswering::test_answering_the_last_question_returns_the_complaint_to_work tests/test_lifecycle.py::TestTransition::test_resolving_stamps_the_time tests/test_lifecycle.py::TestGraph::test_a_complaint_cannot_be_closed_without_being_worked
```

## 12. Policy tests (44 in scope)

| Test | Asserts |
|---|---|
| `test_knowledge_base.py::test_new_version_supersedes_the_previous_one` | A new version supersedes the old one |
| `test_knowledge_base.py::test_only_one_version_can_be_active` | One active version per document |
| `test_knowledge_base.py::test_precedence_order_is_configuration_not_code` | The precedence order is read from `config/policy.yaml` |
| `test_knowledge_base.py::test_conflict_resolution_prefers_policy_then_recency` | Higher tier wins, then the later effective date |
| `test_knowledge_base.py::test_retrieval_excludes_superseded_versions` | Superseded text cannot back a decision |
| `test_knowledge_base.py::test_retrieval_works_without_embeddings` | Keyword retrieval works with no AI key |
| `test_policy_conflict.py::TestDetection::test_a_contradiction_is_recorded_not_silently_resolved` | Two disagreeing policies are recorded as a conflict |
| `test_policy_conflict.py::TestContradiction::test_the_reason_names_both_policies_and_the_governing_tier` | The record names both documents and which one governs |
| `test_policy_conflict.py::TestDisagreement::test_different_figures_in_the_same_unit_are_a_figure_conflict` | "14 days" against "30 days" is a conflict |
| `test_policy_conflict.py::TestFalsePositives::test_two_policies_that_agree_are_not_a_conflict` | Agreement is not flagged |
| `test_policy_update.py::TestHiddenPolicyUpdate::test_the_new_version_governs_the_next_analysis` | A policy switched live governs the next complaint |
| `test_policy_update.py::TestImpact::test_nothing_is_re_analysed_automatically` | A switch reports its impact but does not rewrite history |

```powershell
.venv\Scripts\python -m pytest -q tests/test_knowledge_base.py::test_new_version_supersedes_the_previous_one tests/test_knowledge_base.py::test_only_one_version_can_be_active tests/test_knowledge_base.py::test_initial_status_rules tests/test_knowledge_base.py::test_precedence_order_is_configuration_not_code tests/test_knowledge_base.py::test_conflict_resolution_prefers_policy_then_recency tests/test_knowledge_base.py::test_retrieval_finds_the_relevant_policy tests/test_knowledge_base.py::test_retrieval_excludes_superseded_versions tests/test_knowledge_base.py::test_exact_reference_outranks_semantic_similarity tests/test_knowledge_base.py::test_retrieval_works_without_embeddings tests/test_policy_conflict.py tests/test_policy_update.py tests/test_documents_api.py::test_traceability_resolves_a_real_citation tests/test_documents_api.py::test_deactivate_withdraws_without_deleting tests/test_comparison_engine.py::TestScores::test_a_superseded_citation_is_not_traceable
```

## 13. Hallucination tests (61 in scope)

| Test | Asserts |
|---|---|
| `test_hallucination_checks.py::TestCitationValidation::test_an_invented_reference_is_unresolvable` | A citation to a non-existent policy is caught |
| `test_hallucination_checks.py::TestSupportScoring::test_a_fabricated_claim_is_flagged` | A sentence with no support in its source is flagged |
| `test_hallucination_checks.py::TestNumericGrounding::test_an_invented_figure_is_caught` | "30 days" against a source saying 14 is caught |
| `test_hallucination_checks.py::TestNegationMismatch::test_an_inverted_claim_is_caught` | "Refunds are available" against "are not available" is caught |
| `test_hallucination_checks.py::TestClaimScoping::test_a_realistic_reply_produces_no_noise` | Courtesy and process sentences are not false alarms |
| `test_hallucination_checks.py::test_hallucination_checks_never_call_a_provider` | The checks are deterministic: no model is reachable from them |
| `test_comparison_engine.py::TestCitations::test_a_citation_outside_the_retrieved_set_is_marked` | Citing a document that was not retrieved is marked |
| `test_response_guard.py::TestCitationChecks::test_an_invented_policy_reference_is_flagged` | The reply guard flags invented policy references |
| `test_response_guard.py::TestCitationChecks::test_an_uncited_policy_claim_is_flagged` | A policy claim without a citation is flagged |
| `test_genai_pipeline.py::TestValidation::test_fabricated_citation_is_caught` | The JSON validator rejects fabricated citations |
| `test_documents_api.py::test_traceability_reports_an_invented_citation_as_unresolved` | The trace endpoint reports invented citations |

```powershell
.venv\Scripts\python -m pytest -q tests/test_hallucination_checks.py tests/test_comparison_engine.py::TestCitations tests/test_response_guard.py::TestCitationChecks tests/test_genai_pipeline.py::TestValidation::test_fabricated_citation_is_caught tests/test_documents_api.py::test_traceability_reports_an_invented_citation_as_unresolved tests/test_knowledge_base.py::test_an_invented_citation_does_not_resolve
```

## 14. Prompt-injection tests (69 in scope)

| Test | Asserts |
|---|---|
| `test_jailbreak_guard.py::test_attacks_are_detected` (14 cases) | Instruction override, fake admin code, fake `SYSTEM:` notes, role-play ("FreeNova"), developer mode, a Base64-encoded instruction, a closing-tag break-out and SQL are all detected |
| `test_jailbreak_guard.py::test_genuine_complaints_are_not_flagged` (4 cases) | Ordinary complaints that mention "rules", "manager" or "admin" are not flagged |
| `test_jailbreak_guard.py::test_a_reply_that_gives_in_is_replaced` | A model reply that capitulates is replaced by the policy answer |
| `test_jailbreak_guard.py::test_asking_for_the_prompt_is_refused_without_leaking_it` | The system prompt is never revealed |
| `test_jailbreak_guard.py::test_a_multi_turn_pressure_attack_is_held` | Pressure over several chat turns fails |
| `test_document_injection.py::test_a_planted_instruction_is_flagged_and_recorded` | An instruction hidden in a policy document is flagged |
| `test_document_injection.py::test_policy_text_reaches_the_model_fenced_as_data` | Document text is fenced as data |
| `test_python_validation.py::test_embedded_instructions_are_treated_as_complaint_content` | The rules classify the real complaint and never approve the demanded refund |
| `test_genai_pipeline.py::TestOrchestration::test_the_prompt_sent_to_the_provider_fences_the_complaint` | The complaint reaches the model inside an untrusted-data fence |
| `test_review_sla.py::TestValidationRouting::test_a_suspected_injection_reaches_a_reviewer` | A suspected injection is queued for a person |
| `test_customer_actions.py::TestAnswering::test_an_injected_answer_is_stored_but_flagged` | Injection in a clarification answer is caught too |
| `test_deliberate_defect.py::TestIsolation::test_demonstrating_a_defect_changes_nothing` | The deliberate-defect demonstration changes no data |

```powershell
.venv\Scripts\python -m pytest -q tests/test_jailbreak_guard.py tests/test_document_injection.py tests/test_deliberate_defect.py tests/test_complaints_api.py::TestValidation::test_an_injection_attempt_is_flagged_and_processed tests/test_genai_pipeline.py::TestOrchestration::test_injection_attempt_is_flagged_and_still_processed tests/test_genai_pipeline.py::TestOrchestration::test_the_prompt_sent_to_the_provider_fences_the_complaint tests/test_python_validation.py::test_embedded_instructions_are_treated_as_complaint_content tests/test_python_validation.py::test_injection_flag_forces_review_when_set tests/test_review_sla.py::TestValidationRouting::test_a_suspected_injection_reaches_a_reviewer tests/test_customer_actions.py::TestAnswering::test_an_injected_answer_is_stored_but_flagged tests/test_customer_actions.py::TestPreview::test_injection_is_noticed_but_nothing_is_recorded tests/test_assistant.py::TestSafety tests/test_response_guard.py::TestResponseGeneration::test_the_prompt_fences_the_complaint
```

## 15. Duplicate tests (15 in scope)

| Test | Asserts |
|---|---|
| `test_complaints_api.py::TestDedupe::test_an_identical_resubmission_is_linked_not_refused` | A resubmission is linked to the original, not refused |
| `test_complaints_api.py::TestDedupe::test_a_different_complaint_is_not_a_duplicate` | Similar but different complaints stay separate |
| `test_complaints_api.py::TestDedupe::test_prior_unresolved_contacts_are_counted` | Earlier unresolved contacts are counted |
| `test_complaints_api.py::TestDedupe::test_a_resolved_complaint_is_not_a_repeat` | A resolved case does not count as a repeat |
| `test_complaints_api.py::TestDedupe::test_the_repeat_count_ignores_what_the_complaint_claims` | "I have called five times" does not raise the count; stored records do |
| `test_document_processing.py::test_duplicate_document_is_detected_by_hash` | Re-uploading the same file is detected by content hash |
| `test_email_channel.py::TestInbound::test_the_same_message_is_handled_once` | One email is filed once |
| `test_customer_actions.py::TestEvidence::test_the_same_file_twice_is_stored_once` | Duplicate evidence is stored once |
| `test_benchmark.py::TestImport::test_replace_does_not_double_the_dataset` | Re-importing with `replace` does not double a dataset |

```powershell
.venv\Scripts\python -m pytest -q tests/test_complaints_api.py::TestDedupe tests/test_document_processing.py::test_duplicate_document_is_detected_by_hash tests/test_knowledge_base.py::test_reuploading_the_same_file_is_rejected_and_recorded tests/test_documents_api.py::test_duplicate_upload_is_reported_per_file_not_as_an_error tests/test_email_channel.py::TestInbound::test_the_same_message_is_handled_once tests/test_email_channel.py::TestInbound::test_a_follow_up_joins_its_complaint tests/test_customer_actions.py::TestEvidence::test_the_same_file_twice_is_stored_once tests/test_review_sla.py::TestQueue::test_enqueueing_twice_does_not_stack_items tests/test_benchmark.py::TestImport::test_replace_does_not_double_the_dataset tests/test_completion.py::TestFollowUps::test_rescheduling_refreshes_rather_than_duplicates
```

## 16. Missing-information tests (24 in scope)

| Test | Asserts |
|---|---|
| `test_genai_pipeline.py::TestValidation::test_insufficient_information_requires_a_question` | If the model says information is missing, it must ask a clarifying question |
| `test_customer_actions.py::TestAnswering::test_an_answer_that_supplies_the_missing_reference_fills_it` | The customer's answer fills the missing reference |
| `test_customer_actions.py::TestAnswering::test_a_filled_reference_is_never_overwritten` | An existing reference is not overwritten |
| `test_customer_actions.py::TestAnswering::test_answering_the_last_question_returns_the_complaint_to_work` | The case returns to the team once all questions are answered |
| `test_customer_actions.py::TestPreview::test_a_missing_reference_is_hinted` | The form hints that a reference is missing |
| `test_complaints_api.py::TestValidation::test_a_short_complaint_is_accepted_with_a_finding` | A very short complaint is accepted with a finding |
| `test_complaints_api.py::TestValidation::test_an_unrecognised_reference_is_accepted_with_a_finding` | An unknown reference format is accepted with a finding |
| `test_completion.py::TestFollowUps::test_an_unverified_eligibility_schedules_verification` | An unverifiable claim schedules a verification follow-up |
| `test_knowledge_base.py::test_document_without_metadata_lands_in_review_not_rejected` | A document missing metadata is kept for review |
| `test_benchmark.py::TestImport::test_a_row_with_no_description_is_skipped_with_a_reason` | An import row without text is skipped with its row number |

```powershell
.venv\Scripts\python -m pytest -q tests/test_genai_pipeline.py::TestValidation::test_insufficient_information_requires_a_question tests/test_customer_actions.py::TestAnswering tests/test_customer_actions.py::TestPreview::test_a_missing_reference_is_hinted tests/test_complaints_api.py::TestValidation::test_a_short_complaint_is_accepted_with_a_finding tests/test_complaints_api.py::TestValidation::test_an_unrecognised_reference_is_accepted_with_a_finding tests/test_python_validation.py::test_unrecognised_complaint_is_flagged_not_guessed tests/test_document_processing.py::test_missing_metadata_produces_issues_but_is_never_fatal tests/test_document_processing.py::test_metadata_falls_back_to_the_filename tests/test_knowledge_base.py::test_document_without_metadata_lands_in_review_not_rejected tests/test_completion.py::TestFollowUps::test_an_unverified_eligibility_schedules_verification tests/test_file_intake.py::test_without_a_subject_the_first_real_sentence_is_the_title tests/test_benchmark.py::TestImport::test_a_row_with_no_description_is_skipped_with_a_reason
```

## 17. Multi-issue tests (9 in scope)

A multi-issue complaint is stored with a primary issue, a secondary issue (from Pipeline 1) and, where a rule sets
one, a supporting department; it has one owning department. There is **no dedicated multi-issue test file**. The
behaviour is covered by the tests below, and the 51 complaints tagged `multi_issue` in the corpus are exercised
by every benchmark run.

| Test | Asserts |
|---|---|
| `test_python_validation.py::test_the_most_restrictive_eligibility_finding_wins` | A safety defect plus a replacement demand: the safety finding governs and replacement is withheld |
| `test_python_validation.py::test_a_scoped_rule_does_not_fire_outside_its_category` | A rule for one issue does not leak onto another |
| `test_python_validation.py::test_catch_all_obligations_do_not_leak_onto_recognised_complaints` | Generic obligations do not pile onto recognised issues |
| `test_comparison_engine.py::TestDecision::test_a_rule_conflict_forces_review` | Rules pulling in different directions send the case to a person |
| `test_comparison_engine.py::TestDecision::test_review_reasons_are_deduplicated` | Several reasons produce one queue item |
| `test_comparison_engine.py::TestDecision::test_a_subcategory_disagreement_alone_is_only_a_warning` | A secondary-level disagreement does not block the case |
| `test_comparison_engine.py::TestReconciliation::test_obligations_are_carried_into_the_reconciled_record` | Every fired rule's obligations reach the checklist |
| `test_email_channel.py::TestInbound::test_a_follow_up_joins_its_complaint` | A follow-up email about the same case joins it |

```powershell
.venv\Scripts\python -m pytest -q tests/test_python_validation.py::test_the_most_restrictive_eligibility_finding_wins tests/test_python_validation.py::test_a_scoped_rule_does_not_fire_outside_its_category tests/test_python_validation.py::test_catch_all_obligations_do_not_leak_onto_recognised_complaints tests/test_comparison_engine.py::TestDecision::test_a_rule_conflict_forces_review tests/test_comparison_engine.py::TestDecision::test_review_reasons_are_deduplicated tests/test_comparison_engine.py::TestDecision::test_a_subcategory_disagreement_alone_is_only_a_warning tests/test_comparison_engine.py::TestReconciliation::test_obligations_are_carried_into_the_reconciled_record tests/test_benchmark.py::TestImport::test_customer_type_and_follow_ups_survive_the_import tests/test_email_channel.py::TestInbound::test_a_follow_up_joins_its_complaint
```

## 18. Hidden-data readiness tests (44 in scope)

| Test | Asserts |
|---|---|
| `test_benchmark.py::test_no_pipeline_can_read_a_ground_truth_label` | Greps every pipeline package: none can read an `expected_*` label |
| `test_benchmark.py::test_the_benchmark_is_the_only_reader` | Only the benchmark reads labels |
| `test_benchmark.py::TestImport::test_an_unlabelled_file_still_imports` | A hidden pack with no labels imports |
| `test_benchmark.py::TestImport::test_an_xlsx_file_imports` | XLSX works as well as CSV |
| `test_benchmark.py::TestImport::test_importing_never_analyses` | Import only stores rows |
| `test_benchmark.py::TestBenchmark::test_unlabelled_complaints_are_processed_but_not_scored` | Unlabelled rows are processed, and no accuracy is invented for them |
| `test_benchmark.py::TestBenchmark::test_a_pipeline_that_did_not_run_scores_null_not_zero` | A rules-only run reports GenAI accuracy as `null`, not 0% |
| `test_benchmark.py::TestBenchmark::test_a_run_resumes_rather_than_restarting` | An interrupted run continues |
| `test_benchmark.py::TestEndpoints::test_an_evaluator_can_import_a_hidden_dataset` | The evaluator account can import without admin rights |
| `test_complaints_api.py::test_benchmark_labels_are_not_exposed_by_the_api` | Labels never appear in complaint responses |
| `test_admin_config.py::TestLiveModification::test_a_new_lexicon_term_changes_the_next_decision` | Behaviour can be changed live, without code |

```powershell
.venv\Scripts\python -m pytest -q tests/test_benchmark.py tests/test_complaints_api.py::test_benchmark_labels_are_not_exposed_by_the_api tests/test_complaints_api.py::TestEndpoints::test_a_customer_cannot_tag_a_complaint_into_the_scored_dataset tests/test_knowledge_base.py::test_document_without_metadata_lands_in_review_not_rejected tests/test_admin_config.py::TestLiveModification
```

How to run a real hidden pack through the system: [backend/hidden_test_ready/README.md](../hidden_test_ready/README.md).

## 19. Boundary tests (37 in scope)

| Test | Asserts |
|---|---|
| `test_complaints_api.py::TestPreprocess::test_over_long_text_is_truncated_and_recorded` | Text over the maximum length is cut and the cut recorded |
| `test_complaints_api.py::TestEndpoints::test_an_empty_complaint_is_refused_with_its_findings` | Empty input is the one refusal |
| `test_document_processing.py::test_empty_file_is_rejected` / `test_oversized_file_is_rejected` | Zero bytes and over-limit files |
| `test_document_processing.py::test_a_corrupt_pdf_is_reported_not_raised` | A broken PDF is reported, not a crash |
| `test_customer_actions.py::TestAnswering::test_empty_or_oversized_answers_are_refused` | Answer length limits |
| `test_benchmark.py::TestBenchmark::test_an_empty_dataset_produces_no_run` | Nothing to score, no run |
| `test_benchmark.py::TestBenchmark::test_workers_are_clamped_to_what_the_database_can_serve` | Concurrency is capped by the connection pool |
| `test_analytics_reports.py::TestHonestNulls::test_an_empty_system_reports_nothing_not_perfection` | An empty system shows `null`, not 100% |
| `test_analytics_reports.py::TestTrends::test_a_percentage_change_from_zero_is_undefined` | Change from zero is `null`, not infinity |
| `test_review_sla.py::TestSLA::test_a_complaint_becomes_at_risk_before_it_breaches` | SLA at-risk threshold before the deadline |
| `test_comparison_engine.py::TestLadders::test_unknown_value_fails_closed_against_a_floor` | An unknown level never satisfies a floor |
| `test_response_guard.py::TestUnsupportedPromise::test_an_amount_above_the_ceiling_blocks_a_genuinely_eligible_promise` | Eligible, but above the policy ceiling, is still blocked |
| `test_account_security.py::TestLockout::test_five_wrong_passwords_lock_the_account` | The fifth wrong password locks the account |
| `test_register.py::test_a_weak_password_is_refused` | Minimum password strength |

```powershell
.venv\Scripts\python -m pytest -q tests/test_complaints_api.py::TestPreprocess::test_over_long_text_is_truncated_and_recorded tests/test_complaints_api.py::TestPreprocess::test_empty_input_is_handled tests/test_complaints_api.py::TestValidation::test_only_an_empty_complaint_is_rejected tests/test_complaints_api.py::TestEndpoints::test_an_empty_complaint_is_refused_with_its_findings tests/test_document_processing.py::test_empty_file_is_rejected tests/test_document_processing.py::test_oversized_file_is_rejected tests/test_document_processing.py::test_a_corrupt_pdf_is_reported_not_raised tests/test_document_processing.py::test_long_sections_are_split_and_short_ones_are_not tests/test_document_processing.py::test_bare_capital_letter_does_not_invent_a_section tests/test_customer_actions.py::TestEvidence::test_an_empty_file_is_refused tests/test_customer_actions.py::TestEvidence::test_an_oversized_file_is_refused tests/test_customer_actions.py::TestAnswering::test_empty_or_oversized_answers_are_refused tests/test_benchmark.py::TestEndpoints::test_an_empty_file_is_refused tests/test_benchmark.py::TestBenchmark::test_an_empty_dataset_produces_no_run tests/test_benchmark.py::TestBenchmark::test_workers_are_clamped_to_what_the_database_can_serve tests/test_analytics_reports.py::TestHonestNulls tests/test_analytics_reports.py::TestTrends::test_a_percentage_change_from_zero_is_undefined tests/test_analytics_reports.py::TestTrends::test_small_numbers_are_not_a_trend tests/test_dashboards.py::TestSearchAndFiltering::test_a_future_date_range_is_empty tests/test_review_sla.py::TestSLA::test_a_complaint_becomes_at_risk_before_it_breaches tests/test_review_sla.py::TestSLA::test_a_passed_deadline_is_a_breach tests/test_review_sla.py::TestSLA::test_a_fresh_complaint_is_neither tests/test_comparison_engine.py::TestLadders::test_unknown_value_fails_closed_against_a_floor tests/test_comparison_engine.py::TestFieldComparison::test_long_values_are_truncated_to_fit_the_column tests/test_comparison_engine.py::TestScores::test_a_score_with_no_denominator_is_none_not_a_hundred tests/test_response_guard.py::TestUnsupportedPromise::test_an_amount_above_the_ceiling_blocks_a_genuinely_eligible_promise tests/test_response_guard.py::TestUnsupportedPromise::test_an_amount_within_the_ceiling_passes tests/test_account_security.py::TestLockout::test_five_wrong_passwords_lock_the_account tests/test_account_security.py::TestTotp::test_one_step_of_clock_drift_is_tolerated tests/test_register.py::test_a_weak_password_is_refused
```

## 20. Security tests (109 in scope)

| Test | Asserts |
|---|---|
| `test_auth.py::test_login_does_not_enumerate_accounts` | Unknown account and wrong password give the same answer |
| `test_auth.py::test_refresh_rotates_the_token` | Refresh tokens rotate |
| `test_rbac.py::test_each_role_gets_what_the_matrix_says` | Each role gets exactly the status code the permission matrix expects on each protected route |
| `test_rbac.py::test_only_an_admin_changes_rules_policies_prompts_and_users` | Configuration is administrator-only |
| `test_rbac.py::test_a_customer_never_reaches_the_internal_view` | Customers never see internal reasoning |
| `test_rbac.py::test_an_admin_cannot_lock_themselves_out` | An administrator cannot demote or deactivate their own account |
| `test_account_security.py::TestTwoStep::test_a_recovery_code_works_exactly_once` | Two-step sign-in recovery codes are single-use |
| `test_account_security.py::TestSessions::test_changing_the_password_signs_out_other_sessions` | A password change ends other sessions |
| `test_register.py::test_the_body_cannot_ask_for_authority` | A sign-up cannot request a staff role |
| `test_register.py::test_a_seeded_staff_address_cannot_be_claimed` | Staff addresses cannot be registered by anyone else |
| `test_production_guards.py::test_the_public_default_jwt_secret_is_refused` | Production refuses the default JWT secret |
| `test_proxy_client_address.py::test_a_client_cannot_choose_its_own_bucket_without_the_secret` | The rate limit cannot be dodged by forging the proxy header |
| `test_audit_api.py::TestAccess::test_the_trail_cannot_be_written_through_this_router` | The audit trail is read-only |
| `test_documents_api.py::test_refused_access_is_written_to_the_audit_trail` | Refused access is audited |
| `test_customer_actions.py::TestEvidence::test_downloads_are_attachments_never_rendered_inline` | Uploaded files are never rendered in the browser |
| `test_complaints_api.py::TestCustomerStatus::test_another_customer_gets_a_404_not_a_403` | Another customer's complaint does not even appear to exist |
| `test_python_validation.py::test_pipeline_2_imports_no_ai_provider` | Greps Pipeline 2: no AI provider can be reached from it |

```powershell
.venv\Scripts\python -m pytest -q tests/test_auth.py tests/test_rbac.py tests/test_account_security.py tests/test_register.py tests/test_production_guards.py tests/test_proxy_client_address.py tests/test_audit_api.py tests/test_documents_api.py::test_upload_requires_authentication tests/test_documents_api.py::test_agent_cannot_upload_documents tests/test_documents_api.py::test_refused_access_is_written_to_the_audit_trail tests/test_documents_api.py::test_evaluator_can_read_but_not_upload tests/test_customer_actions.py::TestEvidence::test_a_path_in_the_file_name_is_stripped tests/test_customer_actions.py::TestEvidence::test_downloads_are_attachments_never_rendered_inline tests/test_customer_actions.py::TestEvidence::test_a_stranger_cannot_upload_to_or_read_someone_elses tests/test_complaints_api.py::TestCustomerStatus::test_another_customer_gets_a_404_not_a_403 tests/test_complaints_api.py::TestMyComplaints::test_a_customer_never_sees_somebody_elses tests/test_email_channel.py::TestAccess tests/test_python_validation.py::test_pipeline_2_imports_no_ai_provider
```

---

## Per-file inventory (989 tests in 41 files)

| File | Tests | Focus |
|---|---|---|
| `test_account_security.py` | 17 | Lockout, two-step sign-in (TOTP, recovery codes), sessions, activity |
| `test_admin_config.py` | 39 | Live rule, threshold, lexicon, SLA and prompt configuration; floor guard |
| `test_analytics_reports.py` | 49 | Honest nulls, analytics, trends, reports, CSV/XLSX/PDF exports |
| `test_assistant.py` | 14 | Chat assistant scope, drafts, status look-up, safety |
| `test_audit_api.py` | 17 | Audit trail content, ordering and access |
| `test_auth.py` | 9 | Sign-in, tokens, refresh, audit of sign-ins |
| `test_benchmark.py` | 35 | Dataset import (labelled and hidden), benchmark runs, escalation recall |
| `test_comparison_engine.py` | 46 | Ladders, field comparison, scores, floor, verification decision, citations |
| `test_complaints_api.py` | 53 | Pre-processing, intake validation, dedupe, write-back, explainability, customer views |
| `test_completion.py` | 27 | Resolution checklist, follow-ups, escalation notes |
| `test_customer_actions.py` | 36 | Clarification answers, evidence upload, live preview, customer timeline |
| `test_dashboards.py` | 10 | Role dashboards, search and filters |
| `test_deliberate_defect.py` | 17 | Deliberate-defect catalogue: detection and isolation |
| `test_dialect_portability.py` | 7 | Queries and column types compile correctly for PostgreSQL |
| `test_document_injection.py` | 3 | Instructions hidden inside policy documents |
| `test_document_processing.py` | 47 | File validation, metadata, sections, chunking |
| `test_documents_api.py` | 19 | Upload API, versions, search, traceability, access |
| `test_email_channel.py` | 12 | Inbound email, parsing, guarded replies, access |
| `test_email_relay.py` | 5 | Gmail Apps Script relay for outbound replies |
| `test_file_intake.py` | 11 | Complaint letters (text, DOCX, PDF) read into drafts |
| `test_genai_pipeline.py` | 58 | Prompt registry, provider chain, JSON extraction and validation, orchestration |
| `test_hallucination_checks.py` | 50 | Citation validation, claim support, figures, negation, scoping |
| `test_jailbreak_guard.py` | 38 | Attack detection and manipulation-resistant replies |
| `test_knowledge_base.py` | 24 | Ingestion, versioning, precedence, retrieval, citation resolution |
| `test_lifecycle.py` | 22 | Complaint status graph and transitions |
| `test_live_progress.py` | 20 | Streamed intake, reasoning settings, deferred notes |
| `test_model_chain.py` | 33 | Model fall-through inside each provider |
| `test_organisation.py` | 4 | Organisation, teams and templates endpoint |
| `test_people.py` | 8 | User directory and account detail |
| `test_policy_conflict.py` | 18 | Contradictory-policy detection and precedence |
| `test_policy_update.py` | 14 | Hidden policy update: switch, impact, stale citations |
| `test_production_guards.py` | 3 | Production start-up refuses unsafe settings |
| `test_proxy_client_address.py` | 4 | Session-proxy client address and rate-limit buckets |
| `test_python_validation.py` | 26 | Pipeline 2: independence, signals, rules, floor, eligibility, determinism |
| `test_rbac.py` | 28 | Role permissions and scoping |
| `test_refcache.py` | 11 | Reference-data cache correctness and invalidation |
| `test_register.py` | 19 | Customer self-registration |
| `test_requirements_coverage.py` | 16 | Requirement registry matches the real code |
| `test_response_guard.py` | 69 | Promise detection, eligibility, citations, reply generation, tone |
| `test_review_sla.py` | 42 | Review queue, overrides, override floor, SLA clocks, validation routing |
| `test_system.py` | 9 | Health, version, OpenAPI, taxonomy and signal configuration |
| **Total** | **989** | **all passing** |

---

## Manual test cases (web interface)

Run these on https://support-nova.vercel.app (or http://localhost:3000). Wake the backend first by opening
`https://supportnova.onrender.com/api/health` and waiting for `"status": "ok"`. Accounts are listed in the root
[README](../../README.md#credentials).

| ID | Scenario | Account | Steps | Expected result |
|---|---|---|---|---|
| M-01 | Role-based sign-in | `review@supportnova.com` | Sign in. | Lands on *Reviewer Dashboard*; the sidebar shows only reviewer items (Review Queue, AI vs Python Comparison, and so on). |
| M-02 | Customer sign-up and isolation | New account via `/register` | Register, open **Complaint Details**, enter another customer's reference (for example one seen in M-04). | Account is created as a customer; the other reference is reported as not found, with no detail shown. |
| M-03 | Empty and short complaints | Any | On the submit page, try to submit with an empty description; then submit title `Late parcel`, description `Parcel late.` | Empty: the form will not submit (it needs a 3-character title and a 10-character description; the API also refuses an empty complaint). Short: accepted with a reference and an intake finding that it is short. |
| M-04 | Prompt injection | `admin@supportnova.com` | Submit page → **Prompt Injection Override** → **Submit complaint**. | *Injection suspected* badge; no refund approved; case queued for review; it appears on **Security**. |
| M-05 | Calm but critical safety complaint | `admin@supportnova.com` | Submit page → **Safety Hazard (P0 Floor)** → submit. | Safety department, Critical urgency, P0, Critical Management escalation; listed under **Escalation Rules**. |
| M-06 | Contradictory policy complaint | `admin@supportnova.com` | Submit the CMP-00016 text from the README quick tour (FAQ versus Refund Policy). | Refund category, Returns & Refunds, P2, no escalation; refund not approved; the policy trace cites the Refund Policy, and any recorded conflict names the governing document. |
| M-07 | Duplicate submission | Customer account from M-02, then `admin@supportnova.com` | Submit the same complaint twice; then, as the administrator, open the second one from **Complaints**. | The second is accepted, not refused, and is linked to the first under *Related complaints*. |
| M-08 | Document upload | `admin@supportnova.com` | **Policy Versions** → upload one PDF from `dataset/raftarxpress/documents/`; upload it again; upload a `.txt` file renamed to `.pdf`. | First: accepted with sections and chunks (or reported as a duplicate if already present). Second: reported as a duplicate. Third: rejected with the reason. |
| M-09 | Reply generation and guard | `admin@supportnova.com` | Open the M-06 complaint → **Resolution** → **Draft reply**. | A draft appears with the guard verdict; it does not promise the refund; any blocked phrase is shown. |
| M-10 | Escalation cannot be lowered | `review@supportnova.com` | Open the M-05 complaint at `/dashboard/review/<reference>` (**Claim** it if it is queued) → *Decide* → Action **Escalate**, level *Supervisor* → **Record Escalate**. | *The action was refused*, naming the mandatory floor; the level is unchanged. |
| M-11 | Rule sandbox | `admin@supportnova.com` | **Validation Configuration** → paste `Hello, the toaster I bought last month has started giving off a burning smell when I use it. There is no rush. Order CN-4471882.` → **Run**. | The rules that fired, with their trigger words; outcome Safety, Critical, P0, Critical Management (the same text pattern as `test_calm_safety_report_is_critical`); nothing is saved. |
| M-12 | Report export | `admin@supportnova.com` | **Reports** → *Comparison* → tick *Mismatches only* → **Download Excel**. | An `.xlsx` file downloads; the download is listed at `/dashboard/exports`. |
