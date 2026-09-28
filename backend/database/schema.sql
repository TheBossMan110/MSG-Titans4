-- =====================================================================
-- SupportNova - PostgreSQL schema (DDL)
-- =====================================================================
--
-- GENERATED FILE - do not edit by hand.
--
-- Produced from the SQLAlchemy ORM metadata (backend/src/db/models, registered
-- on src.db.base.Base.metadata) by compiling sqlalchemy.schema.CreateTable and
-- CreateIndex against the postgresql dialect. No database was connected to.
--
-- SOURCE OF TRUTH: the Alembic migrations in backend/alembic/versions
--   0001_initial -> 0002_rule_flags -> 0003_account_security -> 0004_email_messages (head)
-- Use `python -m alembic upgrade head` to build a real database. This file is
-- a readable reference / review artefact; if it and Alembic ever disagree,
-- Alembic wins.
--
-- Tables: 54
-- Naming convention: pk_<table>, fk_<table>_<col>_<ref>, uq_<table>_<col>,
--   ck_<table>_<name>, ix_<col_label> (src/db/base.py NAMING_CONVENTION).
-- Status/outcome columns are text + CHECK constraints (src/db/enums.py), not
-- PostgreSQL ENUM types; business taxonomy lives in lookup tables.
-- UUID primary keys are generated application-side (uuid.uuid4).
--
-- Known difference from the migrations: Alembic 0004_email_messages also
-- gives email_messages.subject / body_text a server default of '' and
-- email_messages.status a server default of 'RECEIVED'; the ORM model sets
-- these as Python-side defaults, so they do not appear below.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Extensions (created first by Alembic 0001_initial)
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- trigram near-duplicate detection
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector: chunks.embedding VECTOR(768)

-- ---------------------------------------------------------------------
-- departments   (src/db/models/taxonomy.py)
-- ---------------------------------------------------------------------
CREATE TABLE departments (
	id UUID NOT NULL,
	code VARCHAR(64) NOT NULL,
	name VARCHAR(255) NOT NULL,
	description TEXT,
	email VARCHAR(320),
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_departments PRIMARY KEY (id),
	CONSTRAINT uq_departments_code UNIQUE (code)
);

-- ---------------------------------------------------------------------
-- escalation_levels   (src/db/models/taxonomy.py)
-- ---------------------------------------------------------------------
CREATE TABLE escalation_levels (
	code VARCHAR(64) NOT NULL,
	name VARCHAR(255) NOT NULL,
	rank INTEGER NOT NULL,
	description TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_escalation_levels PRIMARY KEY (code),
	CONSTRAINT uq_escalation_levels_rank UNIQUE (rank)
);

-- ---------------------------------------------------------------------
-- injection_patterns   (src/db/models/signals.py)
-- ---------------------------------------------------------------------
CREATE TABLE injection_patterns (
	id UUID NOT NULL,
	pattern VARCHAR(512) NOT NULL,
	label VARCHAR(64) NOT NULL,
	severity VARCHAR(16) NOT NULL,
	description TEXT,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_injection_patterns PRIMARY KEY (id),
	CONSTRAINT ck_injection_patterns_severity_valid CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'INFORMATIONAL'))
);

-- ---------------------------------------------------------------------
-- lexicon_terms   (src/db/models/signals.py)
-- ---------------------------------------------------------------------
CREATE TABLE lexicon_terms (
	id UUID NOT NULL,
	signal_key VARCHAR(64) NOT NULL,
	term VARCHAR(255) NOT NULL,
	match_type VARCHAR(16) NOT NULL,
	weight NUMERIC(4, 2) NOT NULL,
	description TEXT,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_lexicon_terms PRIMARY KEY (id),
	CONSTRAINT uq_lexicon_signal_term UNIQUE (signal_key, term),
	CONSTRAINT ck_lexicon_terms_match_type_valid CHECK (match_type IN ('PHRASE','REGEX','WORD'))
);

CREATE INDEX ix_lexicon_terms_signal_key ON lexicon_terms (signal_key);

-- ---------------------------------------------------------------------
-- llm_cache   (src/db/models/pipelines.py)
-- ---------------------------------------------------------------------
CREATE TABLE llm_cache (
	prompt_hash VARCHAR(64) NOT NULL,
	provider VARCHAR(64) NOT NULL,
	model VARCHAR(255) NOT NULL,
	response_raw TEXT NOT NULL,
	tokens_in INTEGER,
	tokens_out INTEGER,
	hit_count INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_llm_cache PRIMARY KEY (prompt_hash)
);

-- ---------------------------------------------------------------------
-- priority_levels   (src/db/models/taxonomy.py)
-- ---------------------------------------------------------------------
CREATE TABLE priority_levels (
	code VARCHAR(8) NOT NULL,
	name VARCHAR(255) NOT NULL,
	rank INTEGER NOT NULL,
	description TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_priority_levels PRIMARY KEY (code),
	CONSTRAINT uq_priority_levels_rank UNIQUE (rank)
);

-- ---------------------------------------------------------------------
-- promise_patterns   (src/db/models/signals.py)
-- ---------------------------------------------------------------------
CREATE TABLE promise_patterns (
	id UUID NOT NULL,
	pattern VARCHAR(512) NOT NULL,
	promise_type VARCHAR(64) NOT NULL,
	requires_action VARCHAR(64),
	description TEXT,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_promise_patterns PRIMARY KEY (id)
);

-- ---------------------------------------------------------------------
-- prompt_versions   (src/db/models/pipelines.py)
-- ---------------------------------------------------------------------
CREATE TABLE prompt_versions (
	id UUID NOT NULL,
	name VARCHAR(64) NOT NULL,
	version VARCHAR(16) NOT NULL,
	file_path VARCHAR(512) NOT NULL,
	checksum VARCHAR(64) NOT NULL,
	changelog TEXT,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_prompt_versions PRIMARY KEY (id),
	CONSTRAINT uq_prompt_name_version UNIQUE (name, version)
);

CREATE UNIQUE INDEX ux_prompt_one_active ON prompt_versions (name) WHERE is_active = true;

-- ---------------------------------------------------------------------
-- trend_snapshots   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE trend_snapshots (
	id UUID NOT NULL,
	period_type VARCHAR(16) NOT NULL,
	period_start TIMESTAMP WITH TIME ZONE NOT NULL,
	period_end TIMESTAMP WITH TIME ZONE NOT NULL,
	metric VARCHAR(64) NOT NULL,
	dimension VARCHAR(64) NOT NULL,
	dimension_value VARCHAR(255) NOT NULL,
	value NUMERIC(14, 4) NOT NULL,
	previous_value NUMERIC(14, 4),
	delta_pct NUMERIC(8, 2),
	direction VARCHAR(8) NOT NULL,
	is_anomaly BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_trend_snapshots PRIMARY KEY (id),
	CONSTRAINT uq_trend_period_metric_dim UNIQUE (period_type, period_start, metric, dimension, dimension_value),
	CONSTRAINT ck_trend_snapshots_direction_valid CHECK (direction IN ('UP', 'DOWN', 'FLAT'))
);

CREATE INDEX ix_trend_metric_period ON trend_snapshots (metric, period_start);

-- ---------------------------------------------------------------------
-- categories   (src/db/models/taxonomy.py)
-- ---------------------------------------------------------------------
CREATE TABLE categories (
	id UUID NOT NULL,
	code VARCHAR(64) NOT NULL,
	name VARCHAR(255) NOT NULL,
	description TEXT,
	default_department_id UUID,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_categories PRIMARY KEY (id),
	CONSTRAINT uq_categories_code UNIQUE (code),
	CONSTRAINT fk_categories_default_department_id_departments FOREIGN KEY(default_department_id) REFERENCES departments (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- users   (src/db/models/identity.py)
-- ---------------------------------------------------------------------
CREATE TABLE users (
	id UUID NOT NULL,
	email VARCHAR(320) NOT NULL,
	password_hash TEXT NOT NULL,
	full_name VARCHAR(255) NOT NULL,
	role VARCHAR(32) NOT NULL,
	department_id UUID,
	is_active BOOLEAN NOT NULL,
	last_login_at TIMESTAMP WITH TIME ZONE,
	mfa_secret TEXT,
	mfa_enabled_at TIMESTAMP WITH TIME ZONE,
	mfa_recovery_codes JSONB,
	failed_login_count INTEGER NOT NULL,
	locked_until TIMESTAMP WITH TIME ZONE,
	password_changed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_users PRIMARY KEY (id),
	CONSTRAINT ck_users_role_valid CHECK (role IN ('customer', 'agent', 'reviewer', 'manager', 'admin', 'evaluator')),
	CONSTRAINT fk_users_department_id_departments FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX ux_users_email_lower ON users (lower(email));

-- ---------------------------------------------------------------------
-- app_config   (src/db/models/taxonomy.py)
-- ---------------------------------------------------------------------
CREATE TABLE app_config (
	key VARCHAR(128) NOT NULL,
	value JSONB NOT NULL,
	description TEXT,
	version INTEGER NOT NULL,
	updated_by UUID,
	updated_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_app_config PRIMARY KEY (key),
	CONSTRAINT fk_app_config_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- audit_log   (src/db/models/identity.py)
-- ---------------------------------------------------------------------
CREATE TABLE audit_log (
	id BIGSERIAL NOT NULL,
	actor_id UUID,
	actor_role VARCHAR(32),
	entity_type VARCHAR(64) NOT NULL,
	entity_id VARCHAR(64) NOT NULL,
	action VARCHAR(48) NOT NULL,
	before JSONB,
	after JSONB,
	reason TEXT,
	request_id VARCHAR(64),
	ip_address VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_audit_log PRIMARY KEY (id),
	CONSTRAINT fk_audit_log_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_actor ON audit_log (actor_id, created_at);
CREATE INDEX ix_audit_entity ON audit_log (entity_type, entity_id, created_at);

-- ---------------------------------------------------------------------
-- customers   (src/db/models/complaints.py)
-- ---------------------------------------------------------------------
CREATE TABLE customers (
	id UUID NOT NULL,
	external_ref VARCHAR(64) NOT NULL,
	display_name VARCHAR(255) NOT NULL,
	email VARCHAR(320),
	phone VARCHAR(64),
	tier VARCHAR(16) NOT NULL,
	region VARCHAR(128),
	user_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_customers PRIMARY KEY (id),
	CONSTRAINT ck_customers_tier_valid CHECK (tier IN ('STANDARD', 'PREMIUM', 'VIP', 'BUSINESS')),
	CONSTRAINT uq_customers_external_ref UNIQUE (external_ref),
	CONSTRAINT fk_customers_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- documents   (src/db/models/knowledge.py)
-- ---------------------------------------------------------------------
CREATE TABLE documents (
	id UUID NOT NULL,
	family_key VARCHAR(64) NOT NULL,
	title VARCHAR(255) NOT NULL,
	doc_type VARCHAR(32) NOT NULL,
	department_id UUID,
	description TEXT,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_documents PRIMARY KEY (id),
	CONSTRAINT ck_documents_doc_type_valid CHECK (doc_type IN ('POLICY', 'SOP', 'FAQ', 'ROUTING_RULES', 'ESCALATION', 'SLA', 'COMPLIANCE', 'HANDBOOK', 'PROCESS', 'OTHER')),
	CONSTRAINT uq_documents_family_key UNIQUE (family_key),
	CONSTRAINT fk_documents_department_id_departments FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_documents_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- jobs   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE jobs (
	id UUID NOT NULL,
	job_type VARCHAR(64) NOT NULL,
	status VARCHAR(16) NOT NULL,
	payload JSONB NOT NULL,
	progress INTEGER NOT NULL,
	total INTEGER,
	result JSONB,
	error TEXT,
	created_by UUID,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_jobs PRIMARY KEY (id),
	CONSTRAINT ck_jobs_status_valid CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')),
	CONSTRAINT fk_jobs_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_jobs_status_created ON jobs (status, created_at);
CREATE INDEX ix_jobs_type ON jobs (job_type);

-- ---------------------------------------------------------------------
-- refresh_tokens   (src/db/models/identity.py)
-- ---------------------------------------------------------------------
CREATE TABLE refresh_tokens (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	user_agent VARCHAR(255),
	ip_address VARCHAR(64),
	session_started_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
	CONSTRAINT fk_refresh_tokens_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_refresh_tokens_token_hash ON refresh_tokens (token_hash);
CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);

-- ---------------------------------------------------------------------
-- report_exports   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE report_exports (
	id UUID NOT NULL,
	report_type VARCHAR(64) NOT NULL,
	format VARCHAR(8) NOT NULL,
	filters JSONB,
	file_path VARCHAR(1024),
	row_count INTEGER,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_report_exports PRIMARY KEY (id),
	CONSTRAINT ck_report_exports_format_valid CHECK (format IN ('CSV', 'PDF', 'XLSX', 'JSON')),
	CONSTRAINT fk_report_exports_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- sla_policies   (src/db/models/taxonomy.py)
-- ---------------------------------------------------------------------
CREATE TABLE sla_policies (
	id UUID NOT NULL,
	category_id UUID,
	priority_code VARCHAR(8) NOT NULL,
	first_response_mins INTEGER NOT NULL,
	resolution_mins INTEGER NOT NULL,
	risk_threshold_pct INTEGER NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_sla_policies PRIMARY KEY (id),
	CONSTRAINT uq_sla_category_priority UNIQUE (category_id, priority_code),
	CONSTRAINT fk_sla_policies_category_id_categories FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE CASCADE,
	CONSTRAINT fk_sla_policies_priority_code_priority_levels FOREIGN KEY(priority_code) REFERENCES priority_levels (code)
);

-- ---------------------------------------------------------------------
-- subcategories   (src/db/models/taxonomy.py)
-- ---------------------------------------------------------------------
CREATE TABLE subcategories (
	id UUID NOT NULL,
	category_id UUID NOT NULL,
	code VARCHAR(64) NOT NULL,
	name VARCHAR(255) NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_subcategories PRIMARY KEY (id),
	CONSTRAINT uq_subcat_category_code UNIQUE (category_id, code),
	CONSTRAINT fk_subcategories_category_id_categories FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- benchmark_runs   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE benchmark_runs (
	id UUID NOT NULL,
	label VARCHAR(255) NOT NULL,
	dataset_tag VARCHAR(64) NOT NULL,
	sample_size INTEGER NOT NULL,
	ruleset_version VARCHAR(64) NOT NULL,
	prompt_version VARCHAR(16) NOT NULL,
	provider VARCHAR(64) NOT NULL,
	model VARCHAR(255) NOT NULL,
	metrics JSONB NOT NULL,
	status VARCHAR(16) NOT NULL,
	job_id UUID,
	finished_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_benchmark_runs PRIMARY KEY (id),
	CONSTRAINT fk_benchmark_runs_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- complaints   (src/db/models/complaints.py)
-- ---------------------------------------------------------------------
CREATE TABLE complaints (
	id UUID NOT NULL,
	public_ref VARCHAR(64) NOT NULL,
	customer_id UUID,
	submitted_by_user_id UUID,
	title VARCHAR(255) NOT NULL,
	description_raw TEXT NOT NULL,
	description_clean TEXT NOT NULL,
	product VARCHAR(255),
	order_ref VARCHAR(64),
	transaction_ref VARCHAR(64),
	amount NUMERIC(12, 2),
	currency VARCHAR(8),
	channel VARCHAR(16) NOT NULL,
	customer_type VARCHAR(32),
	preferred_contact VARCHAR(32),
	requested_resolution TEXT,
	previous_complaint_id UUID,
	status VARCHAR(32) NOT NULL,
	category_id UUID,
	subcategory_id UUID,
	department_id UUID,
	support_department_id UUID,
	urgency VARCHAR(16),
	priority_code VARCHAR(8),
	escalation_code VARCHAR(64),
	sentiment VARCHAR(24),
	verification_outcome VARCHAR(32),
	primary_issue VARCHAR(255),
	secondary_issue VARCHAR(255),
	summary TEXT,
	emotion_indicators JSONB NOT NULL,
	injection_suspected BOOLEAN NOT NULL,
	is_duplicate BOOLEAN NOT NULL,
	repeat_count INTEGER NOT NULL,
	missing_information JSONB NOT NULL,
	assigned_to UUID,
	expected_category_code VARCHAR(64),
	expected_subcategory_code VARCHAR(64),
	expected_department_code VARCHAR(64),
	expected_urgency VARCHAR(16),
	expected_priority_code VARCHAR(8),
	expected_escalation_code VARCHAR(64),
	dataset_tag VARCHAR(64),
	analyzed_at TIMESTAMP WITH TIME ZONE,
	validated_at TIMESTAMP WITH TIME ZONE,
	first_response_at TIMESTAMP WITH TIME ZONE,
	resolved_at TIMESTAMP WITH TIME ZONE,
	closed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_complaints PRIMARY KEY (id),
	CONSTRAINT ck_complaints_no_self_reference CHECK (id <> previous_complaint_id),
	CONSTRAINT ck_complaints_status_valid CHECK (status IN ('NEW', 'ANALYZING', 'ANALYZED', 'VALIDATED', 'ASSIGNED', 'IN_PROGRESS', 'AWAITING_CUSTOMER', 'ESCALATED', 'MANUAL_REVIEW', 'RESOLVED', 'CLOSED', 'REOPENED', 'FAILED')),
	CONSTRAINT ck_complaints_channel_valid CHECK (channel IN ('WEB', 'EMAIL', 'CHAT', 'PHONE', 'UPLOAD', 'IMPORT')),
	CONSTRAINT ck_complaints_sentiment_valid CHECK (sentiment IN ('POSITIVE', 'NEUTRAL', 'NEGATIVE', 'STRONGLY_NEGATIVE')),
	CONSTRAINT ck_complaints_urgency_valid CHECK (urgency IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
	CONSTRAINT ck_complaints_verification_outcome_valid CHECK (verification_outcome IN ('VERIFIED', 'VERIFIED_WITH_WARNING', 'CORRECTED_BY_RULES', 'MANUAL_REVIEW_REQUIRED', 'BLOCKED', 'INCOMPLETE')),
	CONSTRAINT uq_complaints_public_ref UNIQUE (public_ref),
	CONSTRAINT fk_complaints_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_submitted_by_user_id_users FOREIGN KEY(submitted_by_user_id) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_previous_complaint_id_complaints FOREIGN KEY(previous_complaint_id) REFERENCES complaints (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_category_id_categories FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_subcategory_id_subcategories FOREIGN KEY(subcategory_id) REFERENCES subcategories (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_department_id_departments FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_support_department_id_departments FOREIGN KEY(support_department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_priority_code_priority_levels FOREIGN KEY(priority_code) REFERENCES priority_levels (code) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_escalation_code_escalation_levels FOREIGN KEY(escalation_code) REFERENCES escalation_levels (code) ON DELETE SET NULL,
	CONSTRAINT fk_complaints_assigned_to_users FOREIGN KEY(assigned_to) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_comp_assigned ON complaints (assigned_to, status);
CREATE INDEX ix_comp_customer ON complaints (customer_id, created_at);
CREATE INDEX ix_comp_dataset ON complaints (dataset_tag);
CREATE INDEX ix_comp_queue ON complaints (department_id, priority_code, created_at);
CREATE INDEX ix_comp_status_created ON complaints (status, created_at);
CREATE INDEX ix_complaints_order_ref ON complaints (order_ref);
CREATE INDEX ix_complaints_status ON complaints (status);
CREATE INDEX ix_complaints_verification_outcome ON complaints (verification_outcome);

-- ---------------------------------------------------------------------
-- document_versions   (src/db/models/knowledge.py)
-- ---------------------------------------------------------------------
CREATE TABLE document_versions (
	id UUID NOT NULL,
	document_id UUID NOT NULL,
	doc_ref VARCHAR(64) NOT NULL,
	version VARCHAR(32) NOT NULL,
	title VARCHAR(255),
	effective_date DATE,
	expiry_date DATE,
	status VARCHAR(32) NOT NULL,
	file_format VARCHAR(8) NOT NULL,
	file_name VARCHAR(512) NOT NULL,
	file_path VARCHAR(1024) NOT NULL,
	file_hash VARCHAR(64) NOT NULL,
	file_size_bytes BIGINT,
	page_count INTEGER,
	section_count INTEGER,
	chunk_count INTEGER,
	parse_status VARCHAR(32) NOT NULL,
	parse_error TEXT,
	metadata_json JSONB,
	metadata_complete BOOLEAN NOT NULL,
	uploaded_by UUID,
	activated_at TIMESTAMP WITH TIME ZONE,
	superseded_at TIMESTAMP WITH TIME ZONE,
	superseded_by_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_document_versions PRIMARY KEY (id),
	CONSTRAINT uq_docver_document_version UNIQUE (document_id, version),
	CONSTRAINT uq_docver_file_hash UNIQUE (file_hash),
	CONSTRAINT ck_document_versions_status_valid CHECK (status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'EXPIRED', 'METADATA_REVIEW')),
	CONSTRAINT ck_document_versions_file_format_valid CHECK (file_format IN ('PDF', 'DOCX', 'TXT', 'MD', 'CSV')),
	CONSTRAINT ck_document_versions_parse_status_valid CHECK (parse_status IN ('PENDING', 'PARSING', 'PARSED', 'FAILED', 'NO_TEXT_LAYER')),
	CONSTRAINT fk_document_versions_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE,
	CONSTRAINT fk_document_versions_uploaded_by_users FOREIGN KEY(uploaded_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_document_versions_superseded_by_id_document_versions FOREIGN KEY(superseded_by_id) REFERENCES document_versions (id) ON DELETE SET NULL
);

CREATE INDEX ix_document_versions_doc_ref ON document_versions (doc_ref);
CREATE INDEX ix_docver_ref_version ON document_versions (doc_ref, version);
CREATE UNIQUE INDEX ux_docver_one_active ON document_versions (document_id) WHERE status = 'ACTIVE';

-- ---------------------------------------------------------------------
-- rules   (src/db/models/rules.py)
-- ---------------------------------------------------------------------
CREATE TABLE rules (
	id UUID NOT NULL,
	rule_ref VARCHAR(64) NOT NULL,
	name VARCHAR(255) NOT NULL,
	rule_type VARCHAR(32) NOT NULL,
	category_id UUID,
	subcategory_id UUID,
	conditions JSONB NOT NULL,
	outcome_category_id UUID,
	outcome_subcategory_id UUID,
	outcome_department_id UUID,
	outcome_support_department_id UUID,
	outcome_urgency VARCHAR(16),
	outcome_priority_code VARCHAR(8),
	outcome_escalation_code VARCHAR(64),
	required_actions JSONB NOT NULL,
	prohibited_actions JSONB NOT NULL,
	policy_refs JSONB NOT NULL,
	follow_up_required BOOLEAN NOT NULL,
	precedence INTEGER NOT NULL,
	is_mandatory_escalation BOOLEAN NOT NULL,
	is_catch_all BOOLEAN NOT NULL,
	eligibility JSONB,
	rationale TEXT NOT NULL,
	source_ref VARCHAR(255),
	version INTEGER NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_rules PRIMARY KEY (id),
	CONSTRAINT ck_rules_rule_type_valid CHECK (rule_type IN ('ROUTING', 'CLASSIFICATION', 'URGENCY', 'ESCALATION', 'RESOLUTION', 'ELIGIBILITY', 'SLA')),
	CONSTRAINT ck_rules_outcome_urgency_valid CHECK (outcome_urgency IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
	CONSTRAINT uq_rules_rule_ref UNIQUE (rule_ref),
	CONSTRAINT fk_rules_category_id_categories FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE CASCADE,
	CONSTRAINT fk_rules_subcategory_id_subcategories FOREIGN KEY(subcategory_id) REFERENCES subcategories (id) ON DELETE CASCADE,
	CONSTRAINT fk_rules_outcome_category_id_categories FOREIGN KEY(outcome_category_id) REFERENCES categories (id) ON DELETE SET NULL,
	CONSTRAINT fk_rules_outcome_subcategory_id_subcategories FOREIGN KEY(outcome_subcategory_id) REFERENCES subcategories (id) ON DELETE SET NULL,
	CONSTRAINT fk_rules_outcome_department_id_departments FOREIGN KEY(outcome_department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_rules_outcome_support_department_id_departments FOREIGN KEY(outcome_support_department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_rules_outcome_priority_code_priority_levels FOREIGN KEY(outcome_priority_code) REFERENCES priority_levels (code) ON DELETE SET NULL,
	CONSTRAINT fk_rules_outcome_escalation_code_escalation_levels FOREIGN KEY(outcome_escalation_code) REFERENCES escalation_levels (code) ON DELETE SET NULL,
	CONSTRAINT fk_rules_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_rules_active_precedence ON rules (is_active, precedence);
CREATE INDEX ix_rules_mandatory ON rules (is_mandatory_escalation, is_active);

-- ---------------------------------------------------------------------
-- agent_guidance   (src/db/models/intelligence.py)
-- ---------------------------------------------------------------------
CREATE TABLE agent_guidance (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	ordinal INTEGER NOT NULL,
	text TEXT NOT NULL,
	kind VARCHAR(16) NOT NULL,
	source VARCHAR(16) NOT NULL,
	rule_ref VARCHAR(64),
	is_mandatory BOOLEAN NOT NULL,
	acknowledged_by UUID,
	acknowledged_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_agent_guidance PRIMARY KEY (id),
	CONSTRAINT ck_agent_guidance_source_valid CHECK (source IN ('GENAI', 'RULE')),
	CONSTRAINT ck_agent_guidance_kind_valid CHECK (kind IN ('ACTION', 'CAUTION', 'VERIFICATION', 'ESCALATION', 'INFORMATION')),
	CONSTRAINT fk_agent_guidance_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_agent_guidance_acknowledged_by_users FOREIGN KEY(acknowledged_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_guidance_complaint ON agent_guidance (complaint_id, ordinal);

-- ---------------------------------------------------------------------
-- benchmark_results   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE benchmark_results (
	id UUID NOT NULL,
	benchmark_run_id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	field VARCHAR(64) NOT NULL,
	expected_value VARCHAR(255),
	genai_value VARCHAR(255),
	python_value VARCHAR(255),
	genai_correct BOOLEAN,
	python_correct BOOLEAN,
	agreed BOOLEAN,
	explanation TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_benchmark_results PRIMARY KEY (id),
	CONSTRAINT fk_benchmark_results_benchmark_run_id_benchmark_runs FOREIGN KEY(benchmark_run_id) REFERENCES benchmark_runs (id) ON DELETE CASCADE,
	CONSTRAINT fk_benchmark_results_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE
);

CREATE INDEX ix_benchresults_complaint ON benchmark_results (complaint_id);
CREATE INDEX ix_benchresults_run_field ON benchmark_results (benchmark_run_id, field);

-- ---------------------------------------------------------------------
-- complaint_attachments   (src/db/models/complaints.py)
-- ---------------------------------------------------------------------
CREATE TABLE complaint_attachments (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	file_name VARCHAR(512) NOT NULL,
	file_path VARCHAR(1024) NOT NULL,
	mime_type VARCHAR(128) NOT NULL,
	size_bytes BIGINT NOT NULL,
	file_hash VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_complaint_attachments PRIMARY KEY (id),
	CONSTRAINT fk_complaint_attachments_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE
);

CREATE INDEX ix_complaint_attachments_complaint_id ON complaint_attachments (complaint_id);

-- ---------------------------------------------------------------------
-- complaint_entities   (src/db/models/complaints.py)
-- ---------------------------------------------------------------------
CREATE TABLE complaint_entities (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	entity_type VARCHAR(64) NOT NULL,
	value VARCHAR(512) NOT NULL,
	normalized VARCHAR(512),
	span_start INTEGER,
	span_end INTEGER,
	extracted_by VARCHAR(16) NOT NULL,
	confidence NUMERIC(4, 3),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_complaint_entities PRIMARY KEY (id),
	CONSTRAINT ck_complaint_entities_extracted_by_valid CHECK (extracted_by IN ('PYTHON', 'GENAI')),
	CONSTRAINT fk_complaint_entities_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE
);

CREATE INDEX ix_entities_complaint_type ON complaint_entities (complaint_id, entity_type);

-- ---------------------------------------------------------------------
-- complaint_links   (src/db/models/complaints.py)
-- ---------------------------------------------------------------------
CREATE TABLE complaint_links (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	related_id UUID NOT NULL,
	link_type VARCHAR(24) NOT NULL,
	similarity NUMERIC(5, 4),
	detected_by VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_complaint_links PRIMARY KEY (id),
	CONSTRAINT uq_link_pair_type UNIQUE (complaint_id, related_id, link_type),
	CONSTRAINT ck_complaint_links_no_self_link CHECK (complaint_id <> related_id),
	CONSTRAINT ck_complaint_links_link_type_valid CHECK (link_type IN ('EXACT_DUPLICATE', 'NEAR_DUPLICATE', 'REPEAT', 'RELATED', 'FOLLOW_UP')),
	CONSTRAINT fk_complaint_links_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_complaint_links_related_id_complaints FOREIGN KEY(related_id) REFERENCES complaints (id) ON DELETE CASCADE
);

CREATE INDEX ix_links_complaint ON complaint_links (complaint_id);

-- ---------------------------------------------------------------------
-- complaint_status_history   (src/db/models/complaints.py)
-- ---------------------------------------------------------------------
CREATE TABLE complaint_status_history (
	id BIGSERIAL NOT NULL,
	complaint_id UUID NOT NULL,
	from_status VARCHAR(32),
	to_status VARCHAR(32) NOT NULL,
	changed_by UUID,
	reason TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_complaint_status_history PRIMARY KEY (id),
	CONSTRAINT fk_complaint_status_history_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_complaint_status_history_changed_by_users FOREIGN KEY(changed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_statushist_complaint ON complaint_status_history (complaint_id, created_at);

-- ---------------------------------------------------------------------
-- complaint_validation_issues   (src/db/models/validation_issues.py)
-- ---------------------------------------------------------------------
CREATE TABLE complaint_validation_issues (
	id UUID NOT NULL,
	complaint_id UUID,
	submitted_ref VARCHAR(255),
	submitted_by_user_id UUID,
	issue_code VARCHAR(32) NOT NULL,
	severity VARCHAR(16) NOT NULL,
	outcome VARCHAR(24) NOT NULL,
	field VARCHAR(64),
	message TEXT NOT NULL,
	detail TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_complaint_validation_issues PRIMARY KEY (id),
	CONSTRAINT ck_complaint_validation_issues_issue_code_valid CHECK (issue_code IN ('EMPTY_COMPLAINT', 'TOO_SHORT', 'TOO_LONG', 'DUPLICATE_COMPLAINT', 'INVALID_REFERENCE_ID', 'MISSING_MANDATORY_FIELD', 'UNSUPPORTED_ATTACHMENT', 'SUSPECTED_INJECTION', 'UNSUPPORTED_FILE_TYPE', 'FILE_TOO_LARGE', 'EMPTY_FILE', 'DUPLICATE_DOCUMENT', 'MISSING_DOCUMENT_ID', 'MISSING_VERSION', 'MISSING_EFFECTIVE_DATE', 'EXPIRED_DOCUMENT', 'MISSING_CATEGORY', 'NO_TEXT_LAYER', 'PARSE_FAILED', 'METADATA_INCOMPLETE')),
	CONSTRAINT ck_complaint_validation_issues_severity_valid CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'INFORMATIONAL')),
	CONSTRAINT ck_complaint_validation_issues_outcome_valid CHECK (outcome IN ('REJECTED', 'ACCEPTED_WITH_WARNING', 'ROUTED_TO_REVIEW')),
	CONSTRAINT fk_complaint_validation_issues_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_complaint_validation_issues_submitted_by_user_id_users FOREIGN KEY(submitted_by_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_cvi_code ON complaint_validation_issues (issue_code, created_at);
CREATE INDEX ix_cvi_complaint ON complaint_validation_issues (complaint_id);

-- ---------------------------------------------------------------------
-- document_sections   (src/db/models/knowledge.py)
-- ---------------------------------------------------------------------
CREATE TABLE document_sections (
	id UUID NOT NULL,
	document_version_id UUID NOT NULL,
	section_ref VARCHAR(64) NOT NULL,
	heading VARCHAR(255),
	level INTEGER NOT NULL,
	page_no INTEGER,
	paragraph_index INTEGER,
	ordinal INTEGER NOT NULL,
	text TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_document_sections PRIMARY KEY (id),
	CONSTRAINT uq_section_docver_ref UNIQUE (document_version_id, section_ref),
	CONSTRAINT fk_document_sections_document_version_id_document_versions FOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_sections_document_version_id ON document_sections (document_version_id);

-- ---------------------------------------------------------------------
-- document_validation_issues   (src/db/models/validation_issues.py)
-- ---------------------------------------------------------------------
CREATE TABLE document_validation_issues (
	id UUID NOT NULL,
	document_version_id UUID,
	file_name VARCHAR(512) NOT NULL,
	file_hash VARCHAR(64),
	uploaded_by UUID,
	issue_code VARCHAR(32) NOT NULL,
	severity VARCHAR(16) NOT NULL,
	outcome VARCHAR(24) NOT NULL,
	field VARCHAR(64),
	message TEXT NOT NULL,
	detail TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_document_validation_issues PRIMARY KEY (id),
	CONSTRAINT ck_document_validation_issues_issue_code_valid CHECK (issue_code IN ('EMPTY_COMPLAINT', 'TOO_SHORT', 'TOO_LONG', 'DUPLICATE_COMPLAINT', 'INVALID_REFERENCE_ID', 'MISSING_MANDATORY_FIELD', 'UNSUPPORTED_ATTACHMENT', 'SUSPECTED_INJECTION', 'UNSUPPORTED_FILE_TYPE', 'FILE_TOO_LARGE', 'EMPTY_FILE', 'DUPLICATE_DOCUMENT', 'MISSING_DOCUMENT_ID', 'MISSING_VERSION', 'MISSING_EFFECTIVE_DATE', 'EXPIRED_DOCUMENT', 'MISSING_CATEGORY', 'NO_TEXT_LAYER', 'PARSE_FAILED', 'METADATA_INCOMPLETE')),
	CONSTRAINT ck_document_validation_issues_severity_valid CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'INFORMATIONAL')),
	CONSTRAINT ck_document_validation_issues_outcome_valid CHECK (outcome IN ('REJECTED', 'ACCEPTED_WITH_WARNING', 'ROUTED_TO_REVIEW')),
	CONSTRAINT fk_document_validation_issues_document_version_id_docum_e857 FOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE CASCADE,
	CONSTRAINT fk_document_validation_issues_uploaded_by_users FOREIGN KEY(uploaded_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_dvi_code ON document_validation_issues (issue_code, created_at);
CREATE INDEX ix_dvi_docver ON document_validation_issues (document_version_id);

-- ---------------------------------------------------------------------
-- eligibility_decisions   (src/db/models/intelligence.py)
-- ---------------------------------------------------------------------
CREATE TABLE eligibility_decisions (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	eligibility_type VARCHAR(24) NOT NULL,
	genai_outcome VARCHAR(24),
	python_outcome VARCHAR(24) NOT NULL,
	final_outcome VARCHAR(24) NOT NULL,
	overridden BOOLEAN NOT NULL,
	conditions_evaluated JSONB NOT NULL,
	rule_ref VARCHAR(64),
	policy_ref VARCHAR(64),
	section_ref VARCHAR(64),
	max_amount NUMERIC(12, 2),
	currency VARCHAR(8),
	reason TEXT NOT NULL,
	requires_human_approval BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_eligibility_decisions PRIMARY KEY (id),
	CONSTRAINT uq_elig_complaint_type UNIQUE (complaint_id, eligibility_type),
	CONSTRAINT ck_eligibility_decisions_eligibility_type_valid CHECK (eligibility_type IN ('REFUND', 'REPLACEMENT', 'COMPENSATION', 'REPAIR', 'POLICY_EXCEPTION')),
	CONSTRAINT ck_eligibility_decisions_genai_outcome_valid CHECK (genai_outcome IN ('ELIGIBLE', 'NOT_ELIGIBLE', 'CONDITIONAL', 'REQUIRES_VERIFICATION', 'NOT_APPLICABLE')),
	CONSTRAINT ck_eligibility_decisions_python_outcome_valid CHECK (python_outcome IN ('ELIGIBLE', 'NOT_ELIGIBLE', 'CONDITIONAL', 'REQUIRES_VERIFICATION', 'NOT_APPLICABLE')),
	CONSTRAINT ck_eligibility_decisions_final_outcome_valid CHECK (final_outcome IN ('ELIGIBLE', 'NOT_ELIGIBLE', 'CONDITIONAL', 'REQUIRES_VERIFICATION', 'NOT_APPLICABLE')),
	CONSTRAINT fk_eligibility_decisions_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE
);

CREATE INDEX ix_elig_type_outcome ON eligibility_decisions (eligibility_type, final_outcome);

-- ---------------------------------------------------------------------
-- email_messages   (src/db/models/email.py)
-- ---------------------------------------------------------------------
CREATE TABLE email_messages (
	id UUID NOT NULL,
	direction VARCHAR(3) NOT NULL,
	message_id VARCHAR(512),
	in_reply_to VARCHAR(512),
	from_address VARCHAR(320) NOT NULL,
	from_name VARCHAR(255),
	to_address VARCHAR(320) NOT NULL,
	subject VARCHAR(998) NOT NULL,
	body_text TEXT NOT NULL,
	body_html TEXT,
	intent VARCHAR(16),
	status VARCHAR(16) NOT NULL,
	complaint_id UUID,
	error TEXT,
	handled_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_email_messages PRIMARY KEY (id),
	CONSTRAINT fk_email_messages_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE SET NULL
);

CREATE INDEX ix_email_complaint ON email_messages (complaint_id);
CREATE INDEX ix_email_from ON email_messages (from_address);
CREATE INDEX ix_email_message_id ON email_messages (message_id);
CREATE INDEX ix_email_to ON email_messages (to_address);

-- ---------------------------------------------------------------------
-- escalations   (src/db/models/workflow.py)
-- ---------------------------------------------------------------------
CREATE TABLE escalations (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	escalation_code VARCHAR(64) NOT NULL,
	triggered_by VARCHAR(16) NOT NULL,
	rule_ref VARCHAR(64),
	reason TEXT NOT NULL,
	notes TEXT,
	to_department_id UUID,
	acknowledged_by UUID,
	acknowledged_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_escalations PRIMARY KEY (id),
	CONSTRAINT ck_escalations_triggered_by_valid CHECK (triggered_by IN ('PYTHON_RULE', 'GENAI', 'REVIEWER', 'SLA')),
	CONSTRAINT fk_escalations_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_escalations_escalation_code_escalation_levels FOREIGN KEY(escalation_code) REFERENCES escalation_levels (code),
	CONSTRAINT fk_escalations_to_department_id_departments FOREIGN KEY(to_department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_escalations_acknowledged_by_users FOREIGN KEY(acknowledged_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_escalations_complaint ON escalations (complaint_id, created_at);

-- ---------------------------------------------------------------------
-- follow_ups   (src/db/models/workflow.py)
-- ---------------------------------------------------------------------
CREATE TABLE follow_ups (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	follow_up_type VARCHAR(64) NOT NULL,
	message TEXT,
	due_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_follow_ups PRIMARY KEY (id),
	CONSTRAINT fk_follow_ups_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_follow_ups_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_follow_ups_complaint_id ON follow_ups (complaint_id);
CREATE INDEX ix_followups_due ON follow_ups (due_at, completed_at);

-- ---------------------------------------------------------------------
-- genai_runs   (src/db/models/pipelines.py)
-- ---------------------------------------------------------------------
CREATE TABLE genai_runs (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	pipeline VARCHAR(32) NOT NULL,
	prompt_name VARCHAR(64) NOT NULL,
	prompt_version VARCHAR(16) NOT NULL,
	provider VARCHAR(64) NOT NULL,
	model VARCHAR(255) NOT NULL,
	temperature NUMERIC(3, 2),
	attempt INTEGER NOT NULL,
	status VARCHAR(24) NOT NULL,
	request_payload JSONB,
	response_raw TEXT,
	parsed_json JSONB,
	schema_errors JSONB,
	retrieved_chunk_ids JSONB NOT NULL,
	knowledge_base_version VARCHAR(64),
	policy_snapshot JSONB,
	tokens_in INTEGER,
	tokens_out INTEGER,
	latency_ms INTEGER,
	cache_hit BOOLEAN NOT NULL,
	error_message TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_genai_runs PRIMARY KEY (id),
	CONSTRAINT ck_genai_runs_pipeline_valid CHECK (pipeline IN ('INTELLIGENCE', 'RESPONSE', 'CLARIFICATION', 'ESCALATION_NOTE')),
	CONSTRAINT ck_genai_runs_status_valid CHECK (status IN ('PENDING', 'SUCCESS', 'SCHEMA_INVALID', 'REPAIRED', 'API_ERROR', 'TIMEOUT', 'RATE_LIMITED', 'CACHED', 'FAILED')),
	CONSTRAINT fk_genai_runs_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE
);

CREATE INDEX ix_genai_complaint_created ON genai_runs (complaint_id, created_at);
CREATE INDEX ix_genai_status_created ON genai_runs (status, created_at);

-- ---------------------------------------------------------------------
-- impact_analyses   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE impact_analyses (
	id UUID NOT NULL,
	new_document_version_id UUID NOT NULL,
	old_document_version_id UUID,
	changed_sections JSONB NOT NULL,
	affected_rule_count INTEGER NOT NULL,
	affected_complaint_count INTEGER NOT NULL,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_impact_analyses PRIMARY KEY (id),
	CONSTRAINT fk_impact_analyses_new_document_version_id_document_versions FOREIGN KEY(new_document_version_id) REFERENCES document_versions (id) ON DELETE CASCADE,
	CONSTRAINT fk_impact_analyses_old_document_version_id_document_versions FOREIGN KEY(old_document_version_id) REFERENCES document_versions (id) ON DELETE SET NULL,
	CONSTRAINT fk_impact_analyses_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- injection_events   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE injection_events (
	id UUID NOT NULL,
	source_type VARCHAR(16) NOT NULL,
	complaint_id UUID,
	document_version_id UUID,
	pattern_label VARCHAR(64) NOT NULL,
	severity VARCHAR(16) NOT NULL,
	matched_spans JSONB NOT NULL,
	action_taken VARCHAR(24) NOT NULL,
	notes TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_injection_events PRIMARY KEY (id),
	CONSTRAINT ck_injection_events_action_taken_valid CHECK (action_taken IN ('FLAGGED', 'NEUTRALIZED', 'BLOCKED', 'REVIEW_ROUTED')),
	CONSTRAINT ck_injection_events_severity_valid CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'INFORMATIONAL')),
	CONSTRAINT fk_injection_events_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_injection_events_document_version_id_document_versions FOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE CASCADE
);

CREATE INDEX ix_injection_complaint ON injection_events (complaint_id);
CREATE INDEX ix_injection_created ON injection_events (created_at);

-- ---------------------------------------------------------------------
-- review_queue   (src/db/models/workflow.py)
-- ---------------------------------------------------------------------
CREATE TABLE review_queue (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	reasons JSONB NOT NULL,
	priority_code VARCHAR(8),
	status VARCHAR(16) NOT NULL,
	assigned_to UUID,
	closed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_review_queue PRIMARY KEY (id),
	CONSTRAINT ck_review_queue_status_valid CHECK (status IN ('OPEN', 'IN_REVIEW', 'RESOLVED', 'DISMISSED')),
	CONSTRAINT fk_review_queue_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_review_queue_priority_code_priority_levels FOREIGN KEY(priority_code) REFERENCES priority_levels (code) ON DELETE SET NULL,
	CONSTRAINT fk_review_queue_assigned_to_users FOREIGN KEY(assigned_to) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_review_assigned ON review_queue (assigned_to, status);
CREATE INDEX ix_review_queue_complaint_id ON review_queue (complaint_id);
CREATE INDEX ix_review_status_opened ON review_queue (status, created_at);

-- ---------------------------------------------------------------------
-- sla_events   (src/db/models/workflow.py)
-- ---------------------------------------------------------------------
CREATE TABLE sla_events (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	event_type VARCHAR(255) NOT NULL,
	due_at TIMESTAMP WITH TIME ZONE NOT NULL,
	met_at TIMESTAMP WITH TIME ZONE,
	breached BOOLEAN NOT NULL,
	at_risk BOOLEAN NOT NULL,
	sla_policy_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_sla_events PRIMARY KEY (id),
	CONSTRAINT fk_sla_events_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_sla_events_sla_policy_id_sla_policies FOREIGN KEY(sla_policy_id) REFERENCES sla_policies (id) ON DELETE SET NULL
);

CREATE INDEX ix_sla_complaint ON sla_events (complaint_id);
CREATE INDEX ix_sla_open_due ON sla_events (due_at, met_at);

-- ---------------------------------------------------------------------
-- validation_runs   (src/db/models/pipelines.py)
-- ---------------------------------------------------------------------
CREATE TABLE validation_runs (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	ruleset_version VARCHAR(64) NOT NULL,
	knowledge_base_version VARCHAR(64),
	signals JSONB NOT NULL,
	derived_category_id UUID,
	derived_subcategory_id UUID,
	derived_department_id UUID,
	derived_support_department_id UUID,
	derived_urgency VARCHAR(16),
	derived_priority_code VARCHAR(8),
	derived_escalation_code VARCHAR(64),
	escalation_floor_code VARCHAR(64),
	required_actions JSONB NOT NULL,
	prohibited_actions JSONB NOT NULL,
	policy_refs JSONB NOT NULL,
	follow_up_required BOOLEAN NOT NULL,
	reason_codes JSONB NOT NULL,
	unmatched BOOLEAN NOT NULL,
	conflict_detected BOOLEAN NOT NULL,
	latency_ms INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_validation_runs PRIMARY KEY (id),
	CONSTRAINT ck_validation_runs_derived_urgency_valid CHECK (derived_urgency IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
	CONSTRAINT fk_validation_runs_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_validation_runs_derived_category_id_categories FOREIGN KEY(derived_category_id) REFERENCES categories (id) ON DELETE SET NULL,
	CONSTRAINT fk_validation_runs_derived_subcategory_id_subcategories FOREIGN KEY(derived_subcategory_id) REFERENCES subcategories (id) ON DELETE SET NULL,
	CONSTRAINT fk_validation_runs_derived_department_id_departments FOREIGN KEY(derived_department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_validation_runs_derived_support_department_id_departments FOREIGN KEY(derived_support_department_id) REFERENCES departments (id) ON DELETE SET NULL,
	CONSTRAINT fk_validation_runs_derived_priority_code_priority_levels FOREIGN KEY(derived_priority_code) REFERENCES priority_levels (code) ON DELETE SET NULL,
	CONSTRAINT fk_validation_runs_derived_escalation_code_escalation_levels FOREIGN KEY(derived_escalation_code) REFERENCES escalation_levels (code) ON DELETE SET NULL,
	CONSTRAINT fk_validation_runs_escalation_floor_code_escalation_levels FOREIGN KEY(escalation_floor_code) REFERENCES escalation_levels (code) ON DELETE SET NULL
);

CREATE INDEX ix_valrun_complaint_created ON validation_runs (complaint_id, created_at);

-- ---------------------------------------------------------------------
-- chunks   (src/db/models/knowledge.py)
-- ---------------------------------------------------------------------
CREATE TABLE chunks (
	id UUID NOT NULL,
	document_version_id UUID NOT NULL,
	section_id UUID,
	chunk_key VARCHAR(255) NOT NULL,
	doc_ref VARCHAR(64) NOT NULL,
	doc_version VARCHAR(32) NOT NULL,
	section_ref VARCHAR(64),
	heading VARCHAR(255),
	page_no INTEGER,
	paragraph_index INTEGER,
	ordinal INTEGER NOT NULL,
	text TEXT NOT NULL,
	token_count INTEGER,
	embedding VECTOR(768),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_chunks PRIMARY KEY (id),
	CONSTRAINT uq_chunk_docver_key UNIQUE (document_version_id, chunk_key),
	CONSTRAINT fk_chunks_document_version_id_document_versions FOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE CASCADE,
	CONSTRAINT fk_chunks_section_id_document_sections FOREIGN KEY(section_id) REFERENCES document_sections (id) ON DELETE CASCADE
);

CREATE INDEX ix_chunks_chunk_key ON chunks (chunk_key);
CREATE INDEX ix_chunks_doc_ref ON chunks (doc_ref);
CREATE INDEX ix_chunks_docver_ordinal ON chunks (document_version_id, ordinal);

-- ---------------------------------------------------------------------
-- clarification_questions   (src/db/models/intelligence.py)
-- ---------------------------------------------------------------------
CREATE TABLE clarification_questions (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	genai_run_id UUID,
	ordinal INTEGER NOT NULL,
	question TEXT NOT NULL,
	missing_field VARCHAR(64),
	required_for VARCHAR(255),
	asked_at TIMESTAMP WITH TIME ZONE,
	answered_at TIMESTAMP WITH TIME ZONE,
	answer TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_clarification_questions PRIMARY KEY (id),
	CONSTRAINT fk_clarification_questions_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_clarification_questions_genai_run_id_genai_runs FOREIGN KEY(genai_run_id) REFERENCES genai_runs (id) ON DELETE SET NULL
);

CREATE INDEX ix_clarq_complaint ON clarification_questions (complaint_id, ordinal);

-- ---------------------------------------------------------------------
-- comparisons   (src/db/models/verification.py)
-- ---------------------------------------------------------------------
CREATE TABLE comparisons (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	genai_run_id UUID,
	validation_run_id UUID,
	field VARCHAR(64) NOT NULL,
	genai_value VARCHAR(512),
	python_value VARCHAR(512),
	final_value VARCHAR(512),
	status VARCHAR(24) NOT NULL,
	severity VARCHAR(16) NOT NULL,
	winner VARCHAR(16),
	reason_code VARCHAR(64),
	explanation TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_comparisons PRIMARY KEY (id),
	CONSTRAINT ck_comparisons_status_valid CHECK (status IN ('MATCH', 'MISMATCH', 'GENAI_MISSING', 'PYTHON_MISSING', 'UNSUPPORTED', 'CORRECTED')),
	CONSTRAINT ck_comparisons_severity_valid CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'INFORMATIONAL')),
	CONSTRAINT ck_comparisons_winner_valid CHECK (winner IN ('GENAI', 'PYTHON', 'AGREED', 'NONE')),
	CONSTRAINT fk_comparisons_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_comparisons_genai_run_id_genai_runs FOREIGN KEY(genai_run_id) REFERENCES genai_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_comparisons_validation_run_id_validation_runs FOREIGN KEY(validation_run_id) REFERENCES validation_runs (id) ON DELETE SET NULL
);

CREATE INDEX ix_comparisons_complaint ON comparisons (complaint_id);
CREATE INDEX ix_comparisons_field ON comparisons (field);
CREATE INDEX ix_comparisons_status_severity ON comparisons (status, severity);

-- ---------------------------------------------------------------------
-- complaint_policy_refs   (src/db/models/intelligence.py)
-- ---------------------------------------------------------------------
CREATE TABLE complaint_policy_refs (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	genai_run_id UUID,
	validation_run_id UUID,
	source VARCHAR(16) NOT NULL,
	doc_ref VARCHAR(64) NOT NULL,
	section_ref VARCHAR(64),
	doc_version VARCHAR(32),
	chunk_key VARCHAR(255),
	page_no INTEGER,
	paragraph_index INTEGER,
	document_version_id UUID,
	resolved BOOLEAN NOT NULL,
	was_active BOOLEAN NOT NULL,
	applicability VARCHAR(32) NOT NULL,
	precedence_tier VARCHAR(64),
	conflict_with_ref VARCHAR(64),
	reason TEXT,
	relevance_score NUMERIC(5, 4),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_complaint_policy_refs PRIMARY KEY (id),
	CONSTRAINT ck_complaint_policy_refs_source_valid CHECK (source IN ('GENAI', 'PYTHON', 'RETRIEVAL')),
	CONSTRAINT ck_complaint_policy_refs_applicability_valid CHECK (applicability IN ('APPLICABLE', 'CONDITIONALLY_APPLICABLE', 'NOT_APPLICABLE', 'OUTDATED')),
	CONSTRAINT fk_complaint_policy_refs_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_complaint_policy_refs_genai_run_id_genai_runs FOREIGN KEY(genai_run_id) REFERENCES genai_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaint_policy_refs_validation_run_id_validation_runs FOREIGN KEY(validation_run_id) REFERENCES validation_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_complaint_policy_refs_document_version_id_document_versions FOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE SET NULL
);

CREATE INDEX ix_cpr_applicability ON complaint_policy_refs (applicability);
CREATE INDEX ix_cpr_complaint ON complaint_policy_refs (complaint_id);
CREATE INDEX ix_cpr_docref ON complaint_policy_refs (doc_ref, section_ref);

-- ---------------------------------------------------------------------
-- impact_items   (src/db/models/ops.py)
-- ---------------------------------------------------------------------
CREATE TABLE impact_items (
	id UUID NOT NULL,
	impact_analysis_id UUID NOT NULL,
	item_type VARCHAR(16) NOT NULL,
	item_id UUID NOT NULL,
	item_ref VARCHAR(64),
	reason TEXT NOT NULL,
	regenerated BOOLEAN NOT NULL,
	regenerated_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_impact_items PRIMARY KEY (id),
	CONSTRAINT fk_impact_items_impact_analysis_id_impact_analyses FOREIGN KEY(impact_analysis_id) REFERENCES impact_analyses (id) ON DELETE CASCADE
);

CREATE INDEX ix_impactitems_analysis ON impact_items (impact_analysis_id, item_type);

-- ---------------------------------------------------------------------
-- resolution_steps   (src/db/models/intelligence.py)
-- ---------------------------------------------------------------------
CREATE TABLE resolution_steps (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	genai_run_id UUID,
	validation_run_id UUID,
	ordinal INTEGER NOT NULL,
	text TEXT NOT NULL,
	action_code VARCHAR(64),
	source VARCHAR(16) NOT NULL,
	status VARCHAR(16) NOT NULL,
	rule_ref VARCHAR(64),
	policy_ref VARCHAR(64),
	section_ref VARCHAR(64),
	chunk_key VARCHAR(255),
	support_score NUMERIC(5, 4),
	explanation TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_resolution_steps PRIMARY KEY (id),
	CONSTRAINT ck_resolution_steps_source_valid CHECK (source IN ('GENAI', 'RULE_REQUIRED')),
	CONSTRAINT ck_resolution_steps_status_valid CHECK (status IN ('SUPPORTED', 'REQUIRED_MET', 'MISSING', 'UNSUPPORTED', 'PROHIBITED', 'DUPLICATE')),
	CONSTRAINT fk_resolution_steps_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_resolution_steps_genai_run_id_genai_runs FOREIGN KEY(genai_run_id) REFERENCES genai_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_resolution_steps_validation_run_id_validation_runs FOREIGN KEY(validation_run_id) REFERENCES validation_runs (id) ON DELETE SET NULL
);

CREATE INDEX ix_resstep_complaint_order ON resolution_steps (complaint_id, ordinal);
CREATE INDEX ix_resstep_status ON resolution_steps (status);

-- ---------------------------------------------------------------------
-- responses   (src/db/models/workflow.py)
-- ---------------------------------------------------------------------
CREATE TABLE responses (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	genai_run_id UUID,
	version INTEGER NOT NULL,
	tone VARCHAR(24) NOT NULL,
	draft_text TEXT NOT NULL,
	final_text TEXT,
	citations JSONB NOT NULL,
	guard_status VARCHAR(24) NOT NULL,
	regeneration_count INTEGER NOT NULL,
	edited_by UUID,
	approved_by UUID,
	approved_at TIMESTAMP WITH TIME ZONE,
	sent_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_responses PRIMARY KEY (id),
	CONSTRAINT uq_response_complaint_version UNIQUE (complaint_id, version),
	CONSTRAINT ck_responses_tone_valid CHECK (tone IN ('PROFESSIONAL', 'EMPATHETIC', 'CONCISE', 'FORMAL')),
	CONSTRAINT ck_responses_guard_status_valid CHECK (guard_status IN ('PENDING', 'CLEAN', 'FLAGGED', 'BLOCKED', 'REGENERATED')),
	CONSTRAINT fk_responses_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_responses_genai_run_id_genai_runs FOREIGN KEY(genai_run_id) REFERENCES genai_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_responses_edited_by_users FOREIGN KEY(edited_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_responses_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_responses_complaint ON responses (complaint_id, version);

-- ---------------------------------------------------------------------
-- review_actions   (src/db/models/workflow.py)
-- ---------------------------------------------------------------------
CREATE TABLE review_actions (
	id UUID NOT NULL,
	review_queue_id UUID,
	complaint_id UUID NOT NULL,
	actor_id UUID,
	action VARCHAR(24) NOT NULL,
	is_override BOOLEAN NOT NULL,
	original_value JSONB,
	new_value JSONB,
	comment TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_review_actions PRIMARY KEY (id),
	CONSTRAINT ck_review_actions_action_valid CHECK (action IN ('APPROVE', 'REJECT', 'MODIFY', 'RECLASSIFY', 'REASSIGN', 'ESCALATE', 'REGENERATE', 'COMMENT', 'OVERRIDE')),
	CONSTRAINT fk_review_actions_review_queue_id_review_queue FOREIGN KEY(review_queue_id) REFERENCES review_queue (id) ON DELETE CASCADE,
	CONSTRAINT fk_review_actions_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_review_actions_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_reviewactions_complaint ON review_actions (complaint_id, created_at);

-- ---------------------------------------------------------------------
-- rule_hits   (src/db/models/pipelines.py)
-- ---------------------------------------------------------------------
CREATE TABLE rule_hits (
	id UUID NOT NULL,
	validation_run_id UUID NOT NULL,
	rule_id UUID NOT NULL,
	rule_ref VARCHAR(64) NOT NULL,
	precedence INTEGER NOT NULL,
	matched_signals JSONB NOT NULL,
	matched_spans JSONB NOT NULL,
	applied BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_rule_hits PRIMARY KEY (id),
	CONSTRAINT fk_rule_hits_validation_run_id_validation_runs FOREIGN KEY(validation_run_id) REFERENCES validation_runs (id) ON DELETE CASCADE,
	CONSTRAINT fk_rule_hits_rule_id_rules FOREIGN KEY(rule_id) REFERENCES rules (id) ON DELETE CASCADE
);

CREATE INDEX ix_rulehits_rule ON rule_hits (rule_id);
CREATE INDEX ix_rulehits_run ON rule_hits (validation_run_id);

-- ---------------------------------------------------------------------
-- verification_decisions   (src/db/models/verification.py)
-- ---------------------------------------------------------------------
CREATE TABLE verification_decisions (
	id UUID NOT NULL,
	complaint_id UUID NOT NULL,
	genai_run_id UUID,
	validation_run_id UUID,
	outcome VARCHAR(32) NOT NULL,
	critical_mismatches INTEGER NOT NULL,
	high_mismatches INTEGER NOT NULL,
	total_fields INTEGER NOT NULL,
	matched_fields INTEGER NOT NULL,
	agreement_score NUMERIC(5, 2),
	traceability_score NUMERIC(5, 2),
	compliance_score NUMERIC(5, 2),
	requires_review BOOLEAN NOT NULL,
	review_reasons JSONB NOT NULL,
	reconciled JSONB NOT NULL,
	genai_available BOOLEAN NOT NULL,
	decided_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_verification_decisions PRIMARY KEY (id),
	CONSTRAINT ck_verification_decisions_outcome_valid CHECK (outcome IN ('VERIFIED', 'VERIFIED_WITH_WARNING', 'CORRECTED_BY_RULES', 'MANUAL_REVIEW_REQUIRED', 'BLOCKED', 'INCOMPLETE')),
	CONSTRAINT fk_verification_decisions_complaint_id_complaints FOREIGN KEY(complaint_id) REFERENCES complaints (id) ON DELETE CASCADE,
	CONSTRAINT fk_verification_decisions_genai_run_id_genai_runs FOREIGN KEY(genai_run_id) REFERENCES genai_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_verification_decisions_validation_run_id_validation_runs FOREIGN KEY(validation_run_id) REFERENCES validation_runs (id) ON DELETE SET NULL
);

CREATE INDEX ix_verdict_complaint ON verification_decisions (complaint_id, created_at);
CREATE INDEX ix_verdict_outcome ON verification_decisions (outcome);

-- ---------------------------------------------------------------------
-- response_flags   (src/db/models/workflow.py)
-- ---------------------------------------------------------------------
CREATE TABLE response_flags (
	id UUID NOT NULL,
	response_id UUID NOT NULL,
	flag_type VARCHAR(32) NOT NULL,
	severity VARCHAR(16) NOT NULL,
	matched_text VARCHAR(1024),
	span_start INTEGER,
	span_end INTEGER,
	explanation TEXT NOT NULL,
	blocking_rule_ref VARCHAR(64),
	resolved BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_response_flags PRIMARY KEY (id),
	CONSTRAINT ck_response_flags_flag_type_valid CHECK (flag_type IN ('UNSUPPORTED_PROMISE', 'HALLUCINATION', 'INVALID_CITATION', 'OUTDATED_POLICY', 'PROHIBITED_ACTION', 'MISSING_ACTION')),
	CONSTRAINT ck_response_flags_severity_valid CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'INFORMATIONAL')),
	CONSTRAINT fk_response_flags_response_id_responses FOREIGN KEY(response_id) REFERENCES responses (id) ON DELETE CASCADE
);

CREATE INDEX ix_respflags_response ON response_flags (response_id);
CREATE INDEX ix_respflags_type ON response_flags (flag_type);

-- ---------------------------------------------------------------------
-- PostgreSQL-only search / similarity indexes
-- These are expression / operator-class indexes that SQLAlchemy metadata
-- cannot express portably. They are created by raw SQL in Alembic
-- 0001_initial (POSTGRES_INDEXES) and copied here verbatim.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_comp_desc_trgm ON complaints USING gin (description_clean gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_comp_fts ON complaints USING gin (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(description_clean,'')));
CREATE INDEX IF NOT EXISTS ix_chunks_fts ON chunks USING gin (to_tsvector('english', text));
CREATE INDEX IF NOT EXISTS ix_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- End of schema: 54 tables, 78 indexes (excluding PK/UNIQUE constraint indexes).
