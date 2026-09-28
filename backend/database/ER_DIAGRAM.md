# SupportNova - Entity-Relationship Diagram

**54 tables**, PostgreSQL (Supabase) in production. Generated from the SQLAlchemy
metadata in `backend/src/db/models` (the same metadata `schema.sql` is compiled from);
Alembic (`backend/alembic`, head `0004_email_messages`) remains the source of truth.

How to read the diagrams

* One Mermaid `erDiagram` per domain; every column of the domain's tables is listed
  with its PostgreSQL type (`varchar64` = `VARCHAR(64)`, `vector768` = pgvector
  `VECTOR(768)`), and `PK` / `FK` / `UK` (single-column unique) markers.
  `"not null"` marks mandatory columns.
* Tables from another domain appear with their primary key only, so each diagram
  shows how its domain attaches to the rest.
* `||--o{` = mandatory parent, `|o--o{` = optional parent (nullable foreign key).
  The label is the foreign-key column.
* Foreign keys to `users` (`created_by`, `uploaded_by`, `actor_id`, `assigned_to` ...)
  are marked `FK` in the column lists but only drawn in diagram A, to keep the other
  diagrams legible.
* Status and outcome columns are `text` + `CHECK` constraints (values in
  `src/db/enums.py`); business taxonomy lives in lookup tables (domain B).

## Contents

| Domain | Tables |
|---|---|
| A - Identity, access and audit | `users`, `refresh_tokens`, `audit_log` |
| B - Taxonomy and runtime configuration | `departments`, `categories`, `subcategories`, `priority_levels`, `escalation_levels`, `sla_policies`, `app_config` |
| C - Deterministic signal configuration | `lexicon_terms`, `injection_patterns`, `promise_patterns` |
| D - Knowledge base | `documents`, `document_versions`, `document_sections`, `chunks` |
| E - Rule matrix | `rules` |
| F - Customers and complaints | `customers`, `complaints`, `complaint_entities`, `complaint_links`, `complaint_status_history`, `complaint_attachments` |
| G - Complaint-intelligence detail | `complaint_policy_refs`, `resolution_steps`, `eligibility_decisions`, `clarification_questions`, `agent_guidance` |
| H - Intake validation findings | `complaint_validation_issues`, `document_validation_issues` |
| I - Pipelines (GenAI and Python) | `prompt_versions`, `llm_cache`, `genai_runs`, `validation_runs`, `rule_hits` |
| J - Verification | `comparisons`, `verification_decisions` |
| K - Workflow | `responses`, `response_flags`, `escalations`, `follow_ups`, `review_queue`, `review_actions`, `sla_events` |
| L - Security, operations and reporting | `injection_events`, `jobs`, `benchmark_runs`, `benchmark_results`, `impact_analyses`, `impact_items`, `report_exports`, `trend_snapshots` |
| M - E-mail channel | `email_messages` |

## Overview - the dual-pipeline core

Relationships only. A complaint is analysed independently by Pipeline 1
(`genai_runs`, one row per attempt) and Pipeline 2 (`validation_runs` + `rule_hits`);
`comparisons` and `verification_decisions` reconcile the two; every policy reference
resolves through `complaint_policy_refs` to a `chunks` row of a `document_versions` row.
`prompt_versions` is linked to `genai_runs` by name + version (no foreign key).

```mermaid
erDiagram
    document_versions ||--o{ chunks : "document_version_id"
    complaints ||--o{ comparisons : "complaint_id"
    genai_runs |o--o{ comparisons : "genai_run_id"
    validation_runs |o--o{ comparisons : "validation_run_id"
    complaints ||--o{ complaint_policy_refs : "complaint_id"
    document_versions |o--o{ complaint_policy_refs : "document_version_id"
    genai_runs |o--o{ complaint_policy_refs : "genai_run_id"
    validation_runs |o--o{ complaint_policy_refs : "validation_run_id"
    escalation_levels |o--o{ complaints : "escalation_code"
    complaints |o--o{ complaints : "previous_complaint_id"
    documents ||--o{ document_versions : "document_id"
    document_versions |o--o{ document_versions : "superseded_by_id"
    complaints ||--o{ eligibility_decisions : "complaint_id"
    complaints ||--o{ escalations : "complaint_id"
    escalation_levels ||--o{ escalations : "escalation_code"
    complaints ||--o{ genai_runs : "complaint_id"
    complaints ||--o{ resolution_steps : "complaint_id"
    genai_runs |o--o{ resolution_steps : "genai_run_id"
    validation_runs |o--o{ resolution_steps : "validation_run_id"
    responses ||--o{ response_flags : "response_id"
    complaints ||--o{ responses : "complaint_id"
    genai_runs |o--o{ responses : "genai_run_id"
    complaints ||--o{ review_queue : "complaint_id"
    rules ||--o{ rule_hits : "rule_id"
    validation_runs ||--o{ rule_hits : "validation_run_id"
    escalation_levels |o--o{ rules : "outcome_escalation_code"
    complaints ||--o{ validation_runs : "complaint_id"
    escalation_levels |o--o{ validation_runs : "derived_escalation_code"
    escalation_levels |o--o{ validation_runs : "escalation_floor_code"
    complaints ||--o{ verification_decisions : "complaint_id"
    genai_runs |o--o{ verification_decisions : "genai_run_id"
    validation_runs |o--o{ verification_decisions : "validation_run_id"
    prompt_versions ||..o{ genai_runs : "name + version (logical)"
```

## A - Identity, access and audit

```mermaid
erDiagram
    users {
        uuid id PK
        varchar320 email "not null"
        text password_hash "not null"
        varchar255 full_name "not null"
        varchar32 role "not null"
        uuid department_id FK
        bool is_active "not null"
        timestamptz last_login_at
        text mfa_secret
        timestamptz mfa_enabled_at
        jsonb mfa_recovery_codes
        int failed_login_count "not null"
        timestamptz locked_until
        timestamptz password_changed_at
        timestamptz created_at "not null"
    }
    refresh_tokens {
        uuid id PK
        uuid user_id FK "not null"
        varchar64 token_hash "not null"
        timestamptz expires_at "not null"
        timestamptz revoked_at
        varchar255 user_agent
        varchar64 ip_address
        timestamptz session_started_at
        timestamptz created_at "not null"
    }
    audit_log {
        bigint id PK
        uuid actor_id FK
        varchar32 actor_role
        varchar64 entity_type "not null"
        varchar64 entity_id "not null"
        varchar48 action "not null"
        jsonb before
        jsonb after
        text reason
        varchar64 request_id
        varchar64 ip_address
        timestamptz created_at "not null"
    }
    departments {
        uuid id PK
    }
    users |o--o{ audit_log : "actor_id"
    users ||--o{ refresh_tokens : "user_id"
    departments |o--o{ users : "department_id"
    %% 18 further tables reference users.id: agent_guidance, app_config, complaint_status_history, complaint_validation_issues, complaints, customers, document_validation_issues, document_versions, documents, escalations, follow_ups, impact_analyses, jobs, report_exports, responses, review_actions, review_queue, rules
```

## B - Taxonomy and runtime configuration

```mermaid
erDiagram
    departments {
        uuid id PK
        varchar64 code UK "not null"
        varchar255 name "not null"
        text description
        varchar320 email
        bool is_active "not null"
        timestamptz created_at "not null"
    }
    categories {
        uuid id PK
        varchar64 code UK "not null"
        varchar255 name "not null"
        text description
        uuid default_department_id FK
        bool is_active "not null"
        timestamptz created_at "not null"
    }
    subcategories {
        uuid id PK
        uuid category_id FK "not null"
        varchar64 code "not null"
        varchar255 name "not null"
        bool is_active "not null"
        timestamptz created_at "not null"
    }
    priority_levels {
        varchar8 code PK
        varchar255 name "not null"
        int rank UK "not null"
        text description
        timestamptz created_at "not null"
    }
    escalation_levels {
        varchar64 code PK
        varchar255 name "not null"
        int rank UK "not null"
        text description
        timestamptz created_at "not null"
    }
    sla_policies {
        uuid id PK
        uuid category_id FK
        varchar8 priority_code FK "not null"
        int first_response_mins "not null"
        int resolution_mins "not null"
        int risk_threshold_pct "not null"
        bool is_active "not null"
        timestamptz created_at "not null"
        timestamptz updated_at "not null"
    }
    app_config {
        varchar128 key PK
        jsonb value "not null"
        text description
        int version "not null"
        uuid updated_by FK
        timestamptz updated_at
    }
    departments |o--o{ categories : "default_department_id"
    categories |o--o{ sla_policies : "category_id"
    priority_levels ||--o{ sla_policies : "priority_code"
    categories ||--o{ subcategories : "category_id"
```

## C - Deterministic signal configuration

```mermaid
erDiagram
    lexicon_terms {
        uuid id PK
        varchar64 signal_key "not null"
        varchar255 term "not null"
        varchar16 match_type "not null"
        numeric weight "not null"
        text description
        bool is_active "not null"
        timestamptz created_at "not null"
    }
    injection_patterns {
        uuid id PK
        varchar512 pattern "not null"
        varchar64 label "not null"
        varchar16 severity "not null"
        text description
        bool is_active "not null"
        timestamptz created_at "not null"
    }
    promise_patterns {
        uuid id PK
        varchar512 pattern "not null"
        varchar64 promise_type "not null"
        varchar64 requires_action
        text description
        bool is_active "not null"
        timestamptz created_at "not null"
    }
```

## D - Knowledge base

```mermaid
erDiagram
    documents {
        uuid id PK
        varchar64 family_key UK "not null"
        varchar255 title "not null"
        varchar32 doc_type "not null"
        uuid department_id FK
        text description
        uuid created_by FK
        timestamptz created_at "not null"
    }
    document_versions {
        uuid id PK
        uuid document_id FK "not null"
        varchar64 doc_ref "not null"
        varchar32 version "not null"
        varchar255 title
        date effective_date
        date expiry_date
        varchar32 status "not null"
        varchar8 file_format "not null"
        varchar512 file_name "not null"
        varchar1024 file_path "not null"
        varchar64 file_hash UK "not null"
        bigint file_size_bytes
        int page_count
        int section_count
        int chunk_count
        varchar32 parse_status "not null"
        text parse_error
        jsonb metadata_json
        bool metadata_complete "not null"
        uuid uploaded_by FK
        timestamptz activated_at
        timestamptz superseded_at
        uuid superseded_by_id FK
        timestamptz created_at "not null"
    }
    document_sections {
        uuid id PK
        uuid document_version_id FK "not null"
        varchar64 section_ref "not null"
        varchar255 heading
        int level "not null"
        int page_no
        int paragraph_index
        int ordinal "not null"
        text text "not null"
        timestamptz created_at "not null"
    }
    chunks {
        uuid id PK
        uuid document_version_id FK "not null"
        uuid section_id FK
        varchar255 chunk_key "not null"
        varchar64 doc_ref "not null"
        varchar32 doc_version "not null"
        varchar64 section_ref
        varchar255 heading
        int page_no
        int paragraph_index
        int ordinal "not null"
        text text "not null"
        int token_count
        vector768 embedding
        timestamptz created_at "not null"
    }
    departments {
        uuid id PK
    }
    document_versions ||--o{ chunks : "document_version_id"
    document_sections |o--o{ chunks : "section_id"
    document_versions ||--o{ document_sections : "document_version_id"
    documents ||--o{ document_versions : "document_id"
    document_versions |o--o{ document_versions : "superseded_by_id"
    departments |o--o{ documents : "department_id"
```

## E - Rule matrix

```mermaid
erDiagram
    rules {
        uuid id PK
        varchar64 rule_ref UK "not null"
        varchar255 name "not null"
        varchar32 rule_type "not null"
        uuid category_id FK
        uuid subcategory_id FK
        jsonb conditions "not null"
        uuid outcome_category_id FK
        uuid outcome_subcategory_id FK
        uuid outcome_department_id FK
        uuid outcome_support_department_id FK
        varchar16 outcome_urgency
        varchar8 outcome_priority_code FK
        varchar64 outcome_escalation_code FK
        jsonb required_actions "not null"
        jsonb prohibited_actions "not null"
        jsonb policy_refs "not null"
        bool follow_up_required "not null"
        int precedence "not null"
        bool is_mandatory_escalation "not null"
        bool is_catch_all "not null"
        jsonb eligibility
        text rationale "not null"
        varchar255 source_ref
        int version "not null"
        bool is_active "not null"
        uuid created_by FK
        timestamptz created_at "not null"
        timestamptz updated_at "not null"
    }
    categories {
        uuid id PK
    }
    departments {
        uuid id PK
    }
    escalation_levels {
        varchar64 code PK
    }
    priority_levels {
        varchar8 code PK
    }
    subcategories {
        uuid id PK
    }
    categories |o--o{ rules : "category_id"
    categories |o--o{ rules : "outcome_category_id"
    departments |o--o{ rules : "outcome_department_id"
    escalation_levels |o--o{ rules : "outcome_escalation_code"
    priority_levels |o--o{ rules : "outcome_priority_code"
    subcategories |o--o{ rules : "outcome_subcategory_id"
    departments |o--o{ rules : "outcome_support_department_id"
    subcategories |o--o{ rules : "subcategory_id"
```

## F - Customers and complaints

```mermaid
erDiagram
    customers {
        uuid id PK
        varchar64 external_ref UK "not null"
        varchar255 display_name "not null"
        varchar320 email
        varchar64 phone
        varchar16 tier "not null"
        varchar128 region
        uuid user_id FK
        timestamptz created_at "not null"
    }
    complaints {
        uuid id PK
        varchar64 public_ref UK "not null"
        uuid customer_id FK
        uuid submitted_by_user_id FK
        varchar255 title "not null"
        text description_raw "not null"
        text description_clean "not null"
        varchar255 product
        varchar64 order_ref
        varchar64 transaction_ref
        numeric amount
        varchar8 currency
        varchar16 channel "not null"
        varchar32 customer_type
        varchar32 preferred_contact
        text requested_resolution
        uuid previous_complaint_id FK
        varchar32 status "not null"
        uuid category_id FK
        uuid subcategory_id FK
        uuid department_id FK
        uuid support_department_id FK
        varchar16 urgency
        varchar8 priority_code FK
        varchar64 escalation_code FK
        varchar24 sentiment
        varchar32 verification_outcome
        varchar255 primary_issue
        varchar255 secondary_issue
        text summary
        jsonb emotion_indicators "not null"
        bool injection_suspected "not null"
        bool is_duplicate "not null"
        int repeat_count "not null"
        jsonb missing_information "not null"
        uuid assigned_to FK
        varchar64 expected_category_code
        varchar64 expected_subcategory_code
        varchar64 expected_department_code
        varchar16 expected_urgency
        varchar8 expected_priority_code
        varchar64 expected_escalation_code
        varchar64 dataset_tag
        timestamptz analyzed_at
        timestamptz validated_at
        timestamptz first_response_at
        timestamptz resolved_at
        timestamptz closed_at
        timestamptz created_at "not null"
    }
    complaint_entities {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar64 entity_type "not null"
        varchar512 value "not null"
        varchar512 normalized
        int span_start
        int span_end
        varchar16 extracted_by "not null"
        numeric confidence
        timestamptz created_at "not null"
    }
    complaint_links {
        uuid id PK
        uuid complaint_id FK "not null"
        uuid related_id FK "not null"
        varchar24 link_type "not null"
        numeric similarity
        varchar64 detected_by "not null"
        timestamptz created_at "not null"
    }
    complaint_status_history {
        bigint id PK
        uuid complaint_id FK "not null"
        varchar32 from_status
        varchar32 to_status "not null"
        uuid changed_by FK
        text reason
        timestamptz created_at "not null"
    }
    complaint_attachments {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar512 file_name "not null"
        varchar1024 file_path "not null"
        varchar128 mime_type "not null"
        bigint size_bytes "not null"
        varchar64 file_hash "not null"
        timestamptz created_at "not null"
    }
    categories {
        uuid id PK
    }
    departments {
        uuid id PK
    }
    escalation_levels {
        varchar64 code PK
    }
    priority_levels {
        varchar8 code PK
    }
    subcategories {
        uuid id PK
    }
    complaints ||--o{ complaint_attachments : "complaint_id"
    complaints ||--o{ complaint_entities : "complaint_id"
    complaints ||--o{ complaint_links : "complaint_id"
    complaints ||--o{ complaint_links : "related_id"
    complaints ||--o{ complaint_status_history : "complaint_id"
    categories |o--o{ complaints : "category_id"
    customers |o--o{ complaints : "customer_id"
    departments |o--o{ complaints : "department_id"
    escalation_levels |o--o{ complaints : "escalation_code"
    complaints |o--o{ complaints : "previous_complaint_id"
    priority_levels |o--o{ complaints : "priority_code"
    subcategories |o--o{ complaints : "subcategory_id"
    departments |o--o{ complaints : "support_department_id"
```

## G - Complaint-intelligence detail

```mermaid
erDiagram
    complaint_policy_refs {
        uuid id PK
        uuid complaint_id FK "not null"
        uuid genai_run_id FK
        uuid validation_run_id FK
        varchar16 source "not null"
        varchar64 doc_ref "not null"
        varchar64 section_ref
        varchar32 doc_version
        varchar255 chunk_key
        int page_no
        int paragraph_index
        uuid document_version_id FK
        bool resolved "not null"
        bool was_active "not null"
        varchar32 applicability "not null"
        varchar64 precedence_tier
        varchar64 conflict_with_ref
        text reason
        numeric relevance_score
        timestamptz created_at "not null"
    }
    resolution_steps {
        uuid id PK
        uuid complaint_id FK "not null"
        uuid genai_run_id FK
        uuid validation_run_id FK
        int ordinal "not null"
        text text "not null"
        varchar64 action_code
        varchar16 source "not null"
        varchar16 status "not null"
        varchar64 rule_ref
        varchar64 policy_ref
        varchar64 section_ref
        varchar255 chunk_key
        numeric support_score
        text explanation
        timestamptz created_at "not null"
    }
    eligibility_decisions {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar24 eligibility_type "not null"
        varchar24 genai_outcome
        varchar24 python_outcome "not null"
        varchar24 final_outcome "not null"
        bool overridden "not null"
        jsonb conditions_evaluated "not null"
        varchar64 rule_ref
        varchar64 policy_ref
        varchar64 section_ref
        numeric max_amount
        varchar8 currency
        text reason "not null"
        bool requires_human_approval "not null"
        timestamptz created_at "not null"
    }
    clarification_questions {
        uuid id PK
        uuid complaint_id FK "not null"
        uuid genai_run_id FK
        int ordinal "not null"
        text question "not null"
        varchar64 missing_field
        varchar255 required_for
        timestamptz asked_at
        timestamptz answered_at
        text answer
        timestamptz created_at "not null"
    }
    agent_guidance {
        uuid id PK
        uuid complaint_id FK "not null"
        int ordinal "not null"
        text text "not null"
        varchar16 kind "not null"
        varchar16 source "not null"
        varchar64 rule_ref
        bool is_mandatory "not null"
        uuid acknowledged_by FK
        timestamptz acknowledged_at
        timestamptz created_at "not null"
    }
    complaints {
        uuid id PK
    }
    document_versions {
        uuid id PK
    }
    genai_runs {
        uuid id PK
    }
    validation_runs {
        uuid id PK
    }
    complaints ||--o{ agent_guidance : "complaint_id"
    complaints ||--o{ clarification_questions : "complaint_id"
    genai_runs |o--o{ clarification_questions : "genai_run_id"
    complaints ||--o{ complaint_policy_refs : "complaint_id"
    document_versions |o--o{ complaint_policy_refs : "document_version_id"
    genai_runs |o--o{ complaint_policy_refs : "genai_run_id"
    validation_runs |o--o{ complaint_policy_refs : "validation_run_id"
    complaints ||--o{ eligibility_decisions : "complaint_id"
    complaints ||--o{ resolution_steps : "complaint_id"
    genai_runs |o--o{ resolution_steps : "genai_run_id"
    validation_runs |o--o{ resolution_steps : "validation_run_id"
```

## H - Intake validation findings

```mermaid
erDiagram
    complaint_validation_issues {
        uuid id PK
        uuid complaint_id FK
        varchar255 submitted_ref
        uuid submitted_by_user_id FK
        varchar32 issue_code "not null"
        varchar16 severity "not null"
        varchar24 outcome "not null"
        varchar64 field
        text message "not null"
        text detail
        timestamptz created_at "not null"
    }
    document_validation_issues {
        uuid id PK
        uuid document_version_id FK
        varchar512 file_name "not null"
        varchar64 file_hash
        uuid uploaded_by FK
        varchar32 issue_code "not null"
        varchar16 severity "not null"
        varchar24 outcome "not null"
        varchar64 field
        text message "not null"
        text detail
        timestamptz created_at "not null"
    }
    complaints {
        uuid id PK
    }
    document_versions {
        uuid id PK
    }
    complaints |o--o{ complaint_validation_issues : "complaint_id"
    document_versions |o--o{ document_validation_issues : "document_version_id"
```

## I - Pipelines (GenAI and Python)

```mermaid
erDiagram
    prompt_versions {
        uuid id PK
        varchar64 name "not null"
        varchar16 version "not null"
        varchar512 file_path "not null"
        varchar64 checksum "not null"
        text changelog
        bool is_active "not null"
        timestamptz created_at "not null"
    }
    llm_cache {
        varchar64 prompt_hash PK
        varchar64 provider "not null"
        varchar255 model "not null"
        text response_raw "not null"
        int tokens_in
        int tokens_out
        int hit_count "not null"
        timestamptz created_at "not null"
    }
    genai_runs {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar32 pipeline "not null"
        varchar64 prompt_name "not null"
        varchar16 prompt_version "not null"
        varchar64 provider "not null"
        varchar255 model "not null"
        numeric temperature
        int attempt "not null"
        varchar24 status "not null"
        jsonb request_payload
        text response_raw
        jsonb parsed_json
        jsonb schema_errors
        jsonb retrieved_chunk_ids "not null"
        varchar64 knowledge_base_version
        jsonb policy_snapshot
        int tokens_in
        int tokens_out
        int latency_ms
        bool cache_hit "not null"
        text error_message
        timestamptz created_at "not null"
    }
    validation_runs {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar64 ruleset_version "not null"
        varchar64 knowledge_base_version
        jsonb signals "not null"
        uuid derived_category_id FK
        uuid derived_subcategory_id FK
        uuid derived_department_id FK
        uuid derived_support_department_id FK
        varchar16 derived_urgency
        varchar8 derived_priority_code FK
        varchar64 derived_escalation_code FK
        varchar64 escalation_floor_code FK
        jsonb required_actions "not null"
        jsonb prohibited_actions "not null"
        jsonb policy_refs "not null"
        bool follow_up_required "not null"
        jsonb reason_codes "not null"
        bool unmatched "not null"
        bool conflict_detected "not null"
        int latency_ms
        timestamptz created_at "not null"
    }
    rule_hits {
        uuid id PK
        uuid validation_run_id FK "not null"
        uuid rule_id FK "not null"
        varchar64 rule_ref "not null"
        int precedence "not null"
        jsonb matched_signals "not null"
        jsonb matched_spans "not null"
        bool applied "not null"
        timestamptz created_at "not null"
    }
    categories {
        uuid id PK
    }
    complaints {
        uuid id PK
    }
    departments {
        uuid id PK
    }
    escalation_levels {
        varchar64 code PK
    }
    priority_levels {
        varchar8 code PK
    }
    rules {
        uuid id PK
    }
    subcategories {
        uuid id PK
    }
    complaints ||--o{ genai_runs : "complaint_id"
    rules ||--o{ rule_hits : "rule_id"
    validation_runs ||--o{ rule_hits : "validation_run_id"
    complaints ||--o{ validation_runs : "complaint_id"
    categories |o--o{ validation_runs : "derived_category_id"
    departments |o--o{ validation_runs : "derived_department_id"
    escalation_levels |o--o{ validation_runs : "derived_escalation_code"
    priority_levels |o--o{ validation_runs : "derived_priority_code"
    subcategories |o--o{ validation_runs : "derived_subcategory_id"
    departments |o--o{ validation_runs : "derived_support_department_id"
    escalation_levels |o--o{ validation_runs : "escalation_floor_code"
```

## J - Verification

```mermaid
erDiagram
    comparisons {
        uuid id PK
        uuid complaint_id FK "not null"
        uuid genai_run_id FK
        uuid validation_run_id FK
        varchar64 field "not null"
        varchar512 genai_value
        varchar512 python_value
        varchar512 final_value
        varchar24 status "not null"
        varchar16 severity "not null"
        varchar16 winner
        varchar64 reason_code
        text explanation
        timestamptz created_at "not null"
    }
    verification_decisions {
        uuid id PK
        uuid complaint_id FK "not null"
        uuid genai_run_id FK
        uuid validation_run_id FK
        varchar32 outcome "not null"
        int critical_mismatches "not null"
        int high_mismatches "not null"
        int total_fields "not null"
        int matched_fields "not null"
        numeric agreement_score
        numeric traceability_score
        numeric compliance_score
        bool requires_review "not null"
        jsonb review_reasons "not null"
        jsonb reconciled "not null"
        bool genai_available "not null"
        timestamptz decided_at
        timestamptz created_at "not null"
    }
    complaints {
        uuid id PK
    }
    genai_runs {
        uuid id PK
    }
    validation_runs {
        uuid id PK
    }
    complaints ||--o{ comparisons : "complaint_id"
    genai_runs |o--o{ comparisons : "genai_run_id"
    validation_runs |o--o{ comparisons : "validation_run_id"
    complaints ||--o{ verification_decisions : "complaint_id"
    genai_runs |o--o{ verification_decisions : "genai_run_id"
    validation_runs |o--o{ verification_decisions : "validation_run_id"
```

## K - Workflow

```mermaid
erDiagram
    responses {
        uuid id PK
        uuid complaint_id FK "not null"
        uuid genai_run_id FK
        int version "not null"
        varchar24 tone "not null"
        text draft_text "not null"
        text final_text
        jsonb citations "not null"
        varchar24 guard_status "not null"
        int regeneration_count "not null"
        uuid edited_by FK
        uuid approved_by FK
        timestamptz approved_at
        timestamptz sent_at
        timestamptz created_at "not null"
    }
    response_flags {
        uuid id PK
        uuid response_id FK "not null"
        varchar32 flag_type "not null"
        varchar16 severity "not null"
        varchar1024 matched_text
        int span_start
        int span_end
        text explanation "not null"
        varchar64 blocking_rule_ref
        bool resolved "not null"
        timestamptz created_at "not null"
    }
    escalations {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar64 escalation_code FK "not null"
        varchar16 triggered_by "not null"
        varchar64 rule_ref
        text reason "not null"
        text notes
        uuid to_department_id FK
        uuid acknowledged_by FK
        timestamptz acknowledged_at
        timestamptz created_at "not null"
    }
    follow_ups {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar64 follow_up_type "not null"
        text message
        timestamptz due_at
        timestamptz completed_at
        uuid created_by FK
        timestamptz created_at "not null"
    }
    review_queue {
        uuid id PK
        uuid complaint_id FK "not null"
        jsonb reasons "not null"
        varchar8 priority_code FK
        varchar16 status "not null"
        uuid assigned_to FK
        timestamptz closed_at
        timestamptz created_at "not null"
    }
    review_actions {
        uuid id PK
        uuid review_queue_id FK
        uuid complaint_id FK "not null"
        uuid actor_id FK
        varchar24 action "not null"
        bool is_override "not null"
        jsonb original_value
        jsonb new_value
        text comment
        timestamptz created_at "not null"
    }
    sla_events {
        uuid id PK
        uuid complaint_id FK "not null"
        varchar255 event_type "not null"
        timestamptz due_at "not null"
        timestamptz met_at
        bool breached "not null"
        bool at_risk "not null"
        uuid sla_policy_id FK
        timestamptz created_at "not null"
    }
    complaints {
        uuid id PK
    }
    departments {
        uuid id PK
    }
    escalation_levels {
        varchar64 code PK
    }
    genai_runs {
        uuid id PK
    }
    priority_levels {
        varchar8 code PK
    }
    sla_policies {
        uuid id PK
    }
    complaints ||--o{ escalations : "complaint_id"
    escalation_levels ||--o{ escalations : "escalation_code"
    departments |o--o{ escalations : "to_department_id"
    complaints ||--o{ follow_ups : "complaint_id"
    responses ||--o{ response_flags : "response_id"
    complaints ||--o{ responses : "complaint_id"
    genai_runs |o--o{ responses : "genai_run_id"
    complaints ||--o{ review_actions : "complaint_id"
    review_queue |o--o{ review_actions : "review_queue_id"
    complaints ||--o{ review_queue : "complaint_id"
    priority_levels |o--o{ review_queue : "priority_code"
    complaints ||--o{ sla_events : "complaint_id"
    sla_policies |o--o{ sla_events : "sla_policy_id"
```

## L - Security, operations and reporting

```mermaid
erDiagram
    injection_events {
        uuid id PK
        varchar16 source_type "not null"
        uuid complaint_id FK
        uuid document_version_id FK
        varchar64 pattern_label "not null"
        varchar16 severity "not null"
        jsonb matched_spans "not null"
        varchar24 action_taken "not null"
        text notes
        timestamptz created_at "not null"
    }
    jobs {
        uuid id PK
        varchar64 job_type "not null"
        varchar16 status "not null"
        jsonb payload "not null"
        int progress "not null"
        int total
        jsonb result
        text error
        uuid created_by FK
        timestamptz started_at
        timestamptz finished_at
        timestamptz created_at "not null"
    }
    benchmark_runs {
        uuid id PK
        varchar255 label "not null"
        varchar64 dataset_tag "not null"
        int sample_size "not null"
        varchar64 ruleset_version "not null"
        varchar16 prompt_version "not null"
        varchar64 provider "not null"
        varchar255 model "not null"
        jsonb metrics "not null"
        varchar16 status "not null"
        uuid job_id FK
        timestamptz finished_at
        timestamptz created_at "not null"
    }
    benchmark_results {
        uuid id PK
        uuid benchmark_run_id FK "not null"
        uuid complaint_id FK "not null"
        varchar64 field "not null"
        varchar255 expected_value
        varchar255 genai_value
        varchar255 python_value
        bool genai_correct
        bool python_correct
        bool agreed
        text explanation
        timestamptz created_at "not null"
    }
    impact_analyses {
        uuid id PK
        uuid new_document_version_id FK "not null"
        uuid old_document_version_id FK
        jsonb changed_sections "not null"
        int affected_rule_count "not null"
        int affected_complaint_count "not null"
        uuid created_by FK
        timestamptz created_at "not null"
    }
    impact_items {
        uuid id PK
        uuid impact_analysis_id FK "not null"
        varchar16 item_type "not null"
        uuid item_id "not null"
        varchar64 item_ref
        text reason "not null"
        bool regenerated "not null"
        timestamptz regenerated_at
        timestamptz created_at "not null"
    }
    report_exports {
        uuid id PK
        varchar64 report_type "not null"
        varchar8 format "not null"
        jsonb filters
        varchar1024 file_path
        int row_count
        uuid created_by FK
        timestamptz created_at "not null"
    }
    trend_snapshots {
        uuid id PK
        varchar16 period_type "not null"
        timestamptz period_start "not null"
        timestamptz period_end "not null"
        varchar64 metric "not null"
        varchar64 dimension "not null"
        varchar255 dimension_value "not null"
        numeric value "not null"
        numeric previous_value
        numeric delta_pct
        varchar8 direction "not null"
        bool is_anomaly "not null"
        timestamptz created_at "not null"
    }
    complaints {
        uuid id PK
    }
    document_versions {
        uuid id PK
    }
    benchmark_runs ||--o{ benchmark_results : "benchmark_run_id"
    complaints ||--o{ benchmark_results : "complaint_id"
    jobs |o--o{ benchmark_runs : "job_id"
    document_versions ||--o{ impact_analyses : "new_document_version_id"
    document_versions |o--o{ impact_analyses : "old_document_version_id"
    impact_analyses ||--o{ impact_items : "impact_analysis_id"
    complaints |o--o{ injection_events : "complaint_id"
    document_versions |o--o{ injection_events : "document_version_id"
```

## M - E-mail channel

```mermaid
erDiagram
    email_messages {
        uuid id PK
        varchar3 direction "not null"
        varchar512 message_id
        varchar512 in_reply_to
        varchar320 from_address "not null"
        varchar255 from_name
        varchar320 to_address "not null"
        varchar998 subject "not null"
        text body_text "not null"
        text body_html
        varchar16 intent
        varchar16 status "not null"
        uuid complaint_id FK
        text error
        timestamptz handled_at
        timestamptz created_at "not null"
    }
    complaints {
        uuid id PK
    }
    complaints |o--o{ email_messages : "complaint_id"
```

## Table-by-table description

Row counts are a read-only snapshot of the production database taken on 27 September 2026;
they change as the system is used.

### A - Identity, access and audit

- **`users`** (15 columns, PK `id`, 40 rows). Login accounts for staff and customers: e-mail (unique, case-insensitive via `ux_users_email_lower`), password hash, role (`customer`, `agent`, `reviewer`, `manager`, `admin`, `evaluator`), optional department, and the two-step sign-in / lockout columns added by migration 0003.
  Foreign keys: `department_id -> departments`.
- **`refresh_tokens`** (9 columns, PK `id`, 842 rows). Refresh tokens stored only as SHA-256 hashes and rotated on every use, so a replayed token fails. Carries the session start time across rotations.
  Foreign keys: `user_id -> users`.
- **`audit_log`** (12 columns, PK `id`, 301 rows). Append-only audit trail: actor, entity, action, `before`/`after` JSON, reason and request id. The application role is not granted UPDATE/DELETE on it in production.
  Foreign keys: `actor_id -> users`.

### B - Taxonomy and runtime configuration

- **`departments`** (7 columns, PK `id`, 14 rows). Responsible departments, i.e. routing targets. Stored as data so a department can be added at runtime.
- **`categories`** (7 columns, PK `id`, 13 rows). Configurable complaint categories, each with an optional default department.
  Foreign keys: `default_department_id -> departments`.
- **`subcategories`** (6 columns, PK `id`, 68 rows). Subcategories scoped to a category (`uq_subcat_category_code`).
  Foreign keys: `category_id -> categories`.
- **`priority_levels`** (5 columns, PK `code`, 4 rows). Ordered priority ladder P0-P3 keyed by `code`. `rank` 0 is the most severe, which turns "Python may raise but never lower" into a rank comparison.
- **`escalation_levels`** (5 columns, PK `code`, 6 rows). Ordered escalation ladder (NONE up to CRITICAL_MGMT) keyed by `code`. `rank` is what the mandatory escalation floor is compared on.
- **`sla_policies`** (9 columns, PK `id`, 17 rows). First-response and resolution targets per category x priority, with an at-risk percentage threshold.
  Foreign keys: `category_id -> categories`; `priority_code -> priority_levels`.
- **`app_config`** (6 columns, PK `key`, 12 rows). Key -> JSON runtime configuration: policy precedence order, comparison severity weights, thresholds, ruleset version, organisation profile.
  Foreign keys: `updated_by -> users`.

### C - Deterministic signal configuration

- **`lexicon_terms`** (8 columns, PK `id`, 1,451 rows). Phrases, words and regular expressions mapped to named signals (`signal_key`) that rule conditions test. Signals marked analytics-only (e.g. `emotional_intensity`) are recorded but never reach the rule engine.
- **`injection_patterns`** (7 columns, PK `id`, 76 rows). Prompt-injection detection patterns with a label (INSTRUCTION_OVERRIDE, ROLE_HIJACK, ...) and severity.
- **`promise_patterns`** (7 columns, PK `id`, 19 rows). Phrases that amount to a promise (refund, compensation, timeline, exception ...) and the eligibility type each one requires before it may reach a customer.

### D - Knowledge base

- **`documents`** (8 columns, PK `id`, 29 rows). A policy family: the logical document across all of its versions, with type and owning department.
  Foreign keys: `created_by -> users`; `department_id -> departments`.
- **`document_versions`** (25 columns, PK `id`, 29 rows). One uploaded file per version with status (ACTIVE, SUPERSEDED, EXPIRED, DRAFT, METADATA_REVIEW), effective/expiry dates, file metadata and parse status. The partial unique index `ux_docver_one_active` guarantees at most one ACTIVE version per document.
  Foreign keys: `document_id -> documents`; `superseded_by_id -> document_versions`; `uploaded_by -> users`.
- **`document_sections`** (10 columns, PK `id`, 129 rows). Numbered or headed sections of a version, located by page (PDF) or paragraph index (DOCX).
  Foreign keys: `document_version_id -> document_versions`.
- **`chunks`** (15 columns, PK `id`, 129 rows). Retrieval units. `chunk_key` (e.g. `DEL-POL-04::6::c1`) is the token the model must cite; doc_ref, version, section, page and paragraph are denormalised for traceability. Holds the 768-dimension embedding and a full-text index.
  Foreign keys: `document_version_id -> document_versions`; `section_id -> document_sections`.

### E - Rule matrix

- **`rules`** (29 columns, PK `id`, 728 rows). The Complaint Resolution Rule Matrix: a JSON condition DSL (interpreted, never eval-ed), outcome columns (category, department, urgency, priority, escalation), required and prohibited actions, policy references, precedence, and the `is_mandatory_escalation`, `is_catch_all` and `eligibility` control columns.
  Foreign keys: `category_id -> categories`; `created_by -> users`; `outcome_category_id -> categories`; `outcome_department_id -> departments`; `outcome_escalation_code -> escalation_levels`; `outcome_priority_code -> priority_levels`; `outcome_subcategory_id -> subcategories`; `outcome_support_department_id -> departments`; `subcategory_id -> subcategories`.

### F - Customers and complaints

- **`customers`** (9 columns, PK `id`, 10 rows). Records about the person who complained (synthetic data only). Separate from `users`; `user_id` is optional.
  Foreign keys: `user_id -> users`.
- **`complaints`** (49 columns, PK `id`, 558 rows). The central record: raw and cleaned text, order/transaction references, the reconciled classification (category, department, urgency, priority, escalation, verification outcome), flags, the `expected_*` benchmark labels (never read by either pipeline) and lifecycle timestamps.
  Foreign keys: `assigned_to -> users`; `category_id -> categories`; `customer_id -> customers`; `department_id -> departments`; `escalation_code -> escalation_levels`; `previous_complaint_id -> complaints`; `priority_code -> priority_levels`; `subcategory_id -> subcategories`; `submitted_by_user_id -> users`; `support_department_id -> departments`.
- **`complaint_entities`** (10 columns, PK `id`, 921 rows). Extracted entities (order id, amount, date ...) with character spans and which pipeline extracted them.
  Foreign keys: `complaint_id -> complaints`.
- **`complaint_links`** (7 columns, PK `id`, 26 rows). Exact-duplicate, near-duplicate and repeat relationships with similarity score and detector (TRIGRAM, EMBEDDING, REFERENCE).
  Foreign keys: `complaint_id -> complaints`; `related_id -> complaints`.
- **`complaint_status_history`** (7 columns, PK `id`, 1,385 rows). Every lifecycle transition: from/to status, who changed it and why.
  Foreign keys: `changed_by -> users`; `complaint_id -> complaints`.
- **`complaint_attachments`** (8 columns, PK `id`, 4 rows). Attachment metadata: file name, path, MIME type, size and hash.
  Foreign keys: `complaint_id -> complaints`.

### G - Complaint-intelligence detail

- **`complaint_policy_refs`** (20 columns, PK `id`, 1,332 rows). Every policy reference that touches a complaint (cited by GenAI, required by a rule, or surfaced by retrieval) with its verdict: resolved, was_active, applicability, precedence tier and `conflict_with_ref`. The table the Source-Traceability Challenge is answered from.
  Foreign keys: `complaint_id -> complaints`; `document_version_id -> document_versions`; `genai_run_id -> genai_runs`; `validation_run_id -> validation_runs`.
- **`resolution_steps`** (16 columns, PK `id`, 2,228 rows). Recommended resolution steps from either pipeline with a Python verdict: SUPPORTED, UNSUPPORTED, PROHIBITED, MISSING or REQUIRED_MET.
  Foreign keys: `complaint_id -> complaints`; `genai_run_id -> genai_runs`; `validation_run_id -> validation_runs`.
- **`eligibility_decisions`** (16 columns, PK `id`, 626 rows). Refund / replacement / compensation eligibility: GenAI opinion, Python outcome and the final (deterministic) outcome, conditions evaluated and any amount ceiling.
  Foreign keys: `complaint_id -> complaints`.
- **`clarification_questions`** (11 columns, PK `id`, 105 rows). Focused questions asked when information is missing, instead of inventing facts.
  Foreign keys: `complaint_id -> complaints`; `genai_run_id -> genai_runs`.
- **`agent_guidance`** (11 columns, PK `id`, 1,802 rows). Internal guidance for the agent, from GenAI and from the rules; rule-sourced CAUTION items are mandatory.
  Foreign keys: `acknowledged_by -> users`; `complaint_id -> complaints`.

### H - Intake validation findings

- **`complaint_validation_issues`** (11 columns, PK `id`, 19 rows). Intake findings for submitted complaints (TOO_SHORT, DUPLICATE_COMPLAINT, INVALID_REFERENCE_ID, SUSPECTED_INJECTION ...) with severity and outcome.
  Foreign keys: `complaint_id -> complaints`; `submitted_by_user_id -> users`.
- **`document_validation_issues`** (12 columns, PK `id`, 3 rows). Intake findings for uploaded documents (unsupported type, oversized, missing version or effective date ...).
  Foreign keys: `document_version_id -> document_versions`; `uploaded_by -> users`.

### I - Pipelines (GenAI and Python)

- **`prompt_versions`** (8 columns, PK `id`, 5 rows). Registry of versioned prompt templates (`prompt_templates/<name>/vX.Y.j2`) with a SHA-256 checksum; `ux_prompt_one_active` allows one active version per prompt name.
- **`llm_cache`** (8 columns, PK `prompt_hash`, 506 rows). Prompt hash -> real captured provider response, used for development cost control and as an outage replay. Never written by anything but a real provider call.
- **`genai_runs`** (23 columns, PK `id`, 704 rows). One row per GenAI attempt (retries are extra rows): pipeline, prompt name and version, provider, model, temperature, status, request payload, raw response, parsed JSON, schema errors, retrieved chunk keys, policy snapshot, tokens, latency, cache flag and error message.
  Foreign keys: `complaint_id -> complaints`.
- **`validation_runs`** (22 columns, PK `id`, 591 rows). Pipeline 2 output, produced without the GenAI result: deterministic signals, derived category/department/urgency/priority/escalation, the escalation floor, required and prohibited actions, reason codes, and the `unmatched` / `conflict_detected` flags.
  Foreign keys: `complaint_id -> complaints`; `derived_category_id -> categories`; `derived_department_id -> departments`; `derived_escalation_code -> escalation_levels`; `derived_priority_code -> priority_levels`; `derived_subcategory_id -> subcategories`; `derived_support_department_id -> departments`; `escalation_floor_code -> escalation_levels`.
- **`rule_hits`** (9 columns, PK `id`, 3,405 rows). Which rules fired in a validation run, with the matched signals and text spans; `applied = false` for a rule that matched but lost on precedence.
  Foreign keys: `rule_id -> rules`; `validation_run_id -> validation_runs`.

### J - Verification

- **`comparisons`** (14 columns, PK `id`, 5,542 rows). One row per compared field per complaint: GenAI value, Python value, final value, status, severity, winner, reason code and a plain-English explanation.
  Foreign keys: `complaint_id -> complaints`; `genai_run_id -> genai_runs`; `validation_run_id -> validation_runs`.
- **`verification_decisions`** (18 columns, PK `id`, 591 rows). The reconciled verdict per complaint: outcome, critical/high mismatch counts, agreement, traceability and compliance scores, review reasons and the reconciled record.
  Foreign keys: `complaint_id -> complaints`; `genai_run_id -> genai_runs`; `validation_run_id -> validation_runs`.

### K - Workflow

- **`responses`** (15 columns, PK `id`, 10 rows). Versioned customer-reply drafts with tone, citations, guard status and regeneration count.
  Foreign keys: `approved_by -> users`; `complaint_id -> complaints`; `edited_by -> users`; `genai_run_id -> genai_runs`.
- **`response_flags`** (11 columns, PK `id`, 10 rows). Response-guard findings (UNSUPPORTED_PROMISE, HALLUCINATION, INVALID_CITATION ...) with character span, explanation and blocking rule.
  Foreign keys: `response_id -> responses`.
- **`escalations`** (11 columns, PK `id`, 300 rows). Escalation records: level, trigger (PYTHON_RULE, GENAI, REVIEWER, SLA), rule, reason and the generated handover note.
  Foreign keys: `acknowledged_by -> users`; `complaint_id -> complaints`; `escalation_code -> escalation_levels`; `to_department_id -> departments`.
- **`follow_ups`** (8 columns, PK `id`, 491 rows). Scheduled follow-up actions with due and completion times.
  Foreign keys: `complaint_id -> complaints`; `created_by -> users`.
- **`review_queue`** (8 columns, PK `id`, 532 rows). Manual review queue items with entry reasons, priority, status and assignee.
  Foreign keys: `assigned_to -> users`; `complaint_id -> complaints`; `priority_code -> priority_levels`.
- **`review_actions`** (10 columns, PK `id`, 3 rows). Reviewer decisions, keeping both `original_value` and `new_value` (`is_override`).
  Foreign keys: `actor_id -> users`; `complaint_id -> complaints`; `review_queue_id -> review_queue`.
- **`sla_events`** (9 columns, PK `id`, 1,086 rows). SLA clocks (first response, resolution) with due, met, breached and at-risk flags.
  Foreign keys: `complaint_id -> complaints`; `sla_policy_id -> sla_policies`.

### L - Security, operations and reporting

- **`injection_events`** (10 columns, PK `id`, 82 rows). Every prompt-injection detection on complaints and documents, with matched spans and the action taken.
  Foreign keys: `complaint_id -> complaints`; `document_version_id -> document_versions`.
- **`jobs`** (12 columns, PK `id`, 0 rows). Database-backed background job queue with progress; no external broker.
  Foreign keys: `created_by -> users`.
- **`benchmark_runs`** (13 columns, PK `id`, 4 rows). Batch evaluation runs over the labelled dataset with headline metrics (including mandatory escalation recall).
  Foreign keys: `job_id -> jobs`.
- **`benchmark_results`** (12 columns, PK `id`, 3,030 rows). One field of one complaint in one benchmark run: expected, GenAI and Python values and whether each was correct.
  Foreign keys: `benchmark_run_id -> benchmark_runs`; `complaint_id -> complaints`.
- **`impact_analyses`** (8 columns, PK `id`, 0 rows). Impact analysis when a policy version is replaced (changed sections, affected rules and complaints).
  Foreign keys: `created_by -> users`; `new_document_version_id -> document_versions`; `old_document_version_id -> document_versions`.
- **`impact_items`** (9 columns, PK `id`, 0 rows). Complaints, rules or responses affected by a policy change, and whether each was regenerated.
  Foreign keys: `impact_analysis_id -> impact_analyses`.
- **`report_exports`** (8 columns, PK `id`, 1 rows). Record of every report export: type, format, filters, row count and who exported it.
  Foreign keys: `created_by -> users`.
- **`trend_snapshots`** (13 columns, PK `id`, 0 rows). Rolling period aggregates per metric and dimension with delta, direction and anomaly flag.

### M - E-mail channel

- **`email_messages`** (16 columns, PK `id`, 25 rows). Every message received at or sent from the support mailbox (both directions), linked to a complaint where one exists. Added by migration 0004.
  Foreign keys: `complaint_id -> complaints`.

