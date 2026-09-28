# AI Tool Usage Declaration

Required by SRS 1.8 #19 (AI Tool Usage Declaration) and Deliverable 18 (tool name,
purpose, type of assistance, files affected, modifications made, testing performed,
verifying team members). Every use of an AI tool during development is recorded
here. Note the distinction the SRS draws:

* Using a **Generative AI API inside the product** is a mandatory architectural
  requirement of this category.
* Using an **AI assistant to help write code** is permitted, but the code must be
  independently reviewed, modified where required, tested, debugged and understood
  by a named team member. Anyone unable to explain a module may receive zero for it.

The prompt-by-prompt record behind section B is
[`backend/documentation/PROMPT_LOG.md`](backend/documentation/PROMPT_LOG.md). The team
contribution record is
[`backend/documentation/TEAM_CONTRIBUTION.md`](backend/documentation/TEAM_CONTRIBUTION.md).

---

## A. Generative AI used *inside the application* (architectural requirement)

Current configuration, from `backend/.env.example` and `backend/src/core/config.py`.
Only free tiers are used.

| Item | Value |
|---|---|
| Primary provider | Google Gemini (AI Studio, free tier) |
| Gemini model chain | `gemini-3.5-flash-lite` → `gemini-2.5-flash-lite` → `gemini-3.1-flash-lite` (`GEMINI_MODEL`, tried left to right) |
| Embeddings | `gemini-embedding-001`, reduced to 768 dimensions and L2-normalised (`EMBEDDING_DIM=768`) |
| Fallback provider | Groq (free tier) — `openai/gpt-oss-120b` → `qwen/qwen3.8-27b` |
| Third provider | OpenRouter free models — `z-ai/glm-5.2:free` → `nvidia/nemotron-3-super-120b-a12b:free` → `dots-studio/dots-3-note-preview:free` |
| DeepSeek | **Removed from the chain** — its API is pay-per-use, not free. The provider class remains in the code, but `DEEPSEEK_API_KEY` is empty in `.env.example`, so the chain skips it. |
| Generation settings | `LLM_TIMEOUT_SECONDS=30`, `LLM_MAX_RETRIES=2`, temperature 0.1 for complaint intelligence and 0.4 for customer responses, low reasoning effort, configurable output-token limit |
| Prompt templates | `backend/prompt_templates/` — `complaint_intelligence` (v1.0, v1.1), `customer_response` (v1.0, v1.1), `escalation_note` (v1.0); versioned, checksummed and registered in `prompt_versions` |
| Where it is used | Pipeline 1: classification, entity extraction, resolution steps, customer response, clarification questions, escalation notes. Also the "Nova" chat assistant (`genai_pipeline/assistant.py`) and drafting of email auto-replies (`genai_pipeline/email_reply.py`). |
| Where it is **not** used | Pipeline 2 (ground-truth validation), business rules, policy precedence, escalation enforcement, schema validation, comparison logic, security controls, audit logic |
| Failure behaviour | Retries are bounded by `LLM_MAX_RETRIES`. Within a provider, a retired (404) or overloaded (503) model falls through to the next model in its chain; a bad key or account-level rate limit does not. Providers fail over Gemini → Groq → OpenRouter. If all fail, Pipeline 1 records the failure and Pipeline 2 decides alone. Nothing is fabricated. |
| Output checks on chat and email | Replies from the chat assistant and the email channel are checked in code before a customer sees them; a reply that approves, promises or reveals its instructions is replaced with a fixed policy refusal (`security/manipulation_guard.py`, `security/response_guard.py`). |
| Response cache | `llm_cache` stores **real** captured responses only, and only after they pass validation. It is never used to manufacture output a provider did not produce (SRS 1.8 #17). |

**Model history.** Earlier configurations named `gemini-2.0-flash` and
`text-embedding-004`; both returned 404 on the current API. `gemini-flash-latest`
returned 503 during testing, which is the argument against pinning a floating alias.
`gemini-2.5-flash` was later refused as "no longer available to new users", and Groq
stopped serving `llama-3.3-70b-versatile`. `gemini-3.6-flash` repeatedly returned 503
("high demand") on the free tier. The current Gemini chain was chosen on
25 September 2026 by timing each available model on the real complaint prompt. DeepSeek
was added on the same day at a teacher's suggestion and disabled the same evening when
the account showed a $0 balance, because the team uses free keys only.

---

## B. AI assistance during development

**Tool:** Claude Code (Anthropic), an AI coding assistant used from the VS Code
extension, in a single continuous session from 23 to 27 September 2026 driven by the
team lead. The session transcript records the model behind each reply: Claude Opus 5
(`claude-opus-5`) from 23 September to the evening of 24 September, `claude-fable-5-1`
for the frontend rebuild on the evening of 24 September, and Claude Opus 5.5
(`claude-opus-5-5`) from 25 September onward.

**Type of assistance:** planning and architecture advice; code generation across the
backend and frontend; debugging and root-cause diagnosis; writing tests; running tests,
live API calls and headless-browser checks; data conversion scripts; documentation and
deployment guidance. The assistant ran commands and edited files in the repository
directly.

"Modifications made by the team" records only what the development transcript and the
git history show the team did. Where nothing more specific is shown, the entry reads "Reviewed and
tested by the team". "Verified by" names the member responsible for that area.

| # | Date | Tool | Purpose and assistance | Files / areas affected | Testing performed | Modifications made by the team | Verified by |
|---|---|---|---|---|---|---|---|
| 1 | 23 Sep | Claude Code (Anthropic, Claude Opus 5) | Idea selection and architecture (log entries 1–2). Advice only: analysed both SRS PDFs, recommended SupportNova, proposed the stack, a schema outline and a build order. | None — advice in chat | Not applicable | Team lead chose SupportNova and the stack (Next.js/TypeScript, FastAPI, Supabase) and split the work: teammates on the frontend, team lead on backend and database. | Zaki Haider |
| 2 | 23 Sep | Claude Code (Anthropic, Claude Opus 5) | Backend foundation (entries 3–5). Code generation: scaffold, SQLAlchemy schema (45 → 53 tables), Alembic migrations, configuration-as-data with seeder, JWT/Argon2 authentication with roles, audit trail, health/version endpoints, requirement registry with coverage test, PDF/DOCX document processing, Docker and CI. | `backend/src/**` (core, db, api), `backend/alembic/**`, `backend/config/*.yaml`, `backend/schemas/**`, `backend/document_processing/**`, `backend/tests/**`, `backend/scripts/generate_coverage_report.py`, `.github/workflows/ci.yml` | pytest 18 → 34 → 81 passing; ruff clean; migration downgrade/upgrade round trip; 53/53 model-to-database parity on Supabase PostgreSQL 17.6; live smoke test of `/api/health`, `/api/version`, login, `/api/auth/me` and a 401 path; PDF/DOCX parity test | Team lead obtained the Gemini, Groq, OpenRouter and Supabase keys and credentials, entered them in `.env` himself and fixed the database URL; required that no SRS requirement be missed. Reviewed and verified by team. | Zaki Haider |
| 3 | 23 Sep | Claude Code (Anthropic, Claude Opus 5) | Knowledge base (entries 6–7): file storage, document version control, embeddings, ingestion, hybrid retrieval, documents API; diagnosed retired Gemini model names. | `backend/knowledge_base/**`, `backend/src/services/storage.py`, `backend/src/api/v1/documents.py`, `backend/src/db/base.py`, knowledge-base, documents-API and dialect-portability tests, CI workflow | 124 → 131 tests passing; embeddings 24/24 chunks at 768 dimensions, norm 1.0; live full-text and pgvector checks on Supabase (two PostgreSQL-only bugs found and fixed); CI job on PostgreSQL + pgvector | Tested embedding generation and vector search retrieval; verified against active policy documents. | Abdul Sami |
| 4 | 23–24 Sep | Claude Code (Anthropic, Claude Opus 5) | Dual pipelines and safeguards (entries 8–12): Pipeline 2 rule engine and rule matrix, Pipeline 1 (prompts, provider chain, validator, orchestrator), comparison engine, response guard, hallucination checks. | `backend/python_validation/**`, `backend/complaint_processing/entities.py`, `backend/complaint_rules/`, `routing_rules/`, `escalation_rules/`, `backend/genai_pipeline/**`, `backend/prompt_templates/**`, `backend/security/injection_defense.py`, `security/response_guard.py`, `backend/comparison_engine/**`, `backend/hallucination_checks/**`, tests | 157 → 214 → 260 → 320 → 375 tests passing; sentiment–urgency trap run through the CLI with no API key; live Gemini calls (classification, embedded injection not obeyed, repair loop succeeded); live reconciliation VERIFIED at 100% agreement; a refund-promising draft BLOCKED and regenerated | Reviewed rule precedence logic, tested reconciliation engine under disagreement scenarios, and verified that rules consistently override model outputs. | Zaki Haider |
| 5 | 24 Sep | Claude Code (Anthropic, Claude Opus 5) | Complaint workflow services (entries 13–15, 19–20, 23, 25, 27): intake API, review queue and SLA, analytics, trends and reports, dataset import and benchmark runner, completion pipeline and lifecycle, admin configuration API, integrity items 4, 10 and 15. | `backend/complaint_processing/**`, `backend/src/services/*` (sla, review, analytics, trends, reports, dataset, benchmark, lifecycle), `backend/src/api/v1/*` (complaints, review, analytics, benchmark, admin), `backend/security/deliberate_defect.py`, tests | 418 → 460 → 514 → 547 → 600 tests passing; live HTTP checks (a safety complaint became CMP-000012 with rule ESC-0002 on "burning smell"; a reviewer lowering the escalation floor was refused with 422); registry at 95.8% with 81 endpoints | Tested SLA calculation timers, verified intake schemas and escalation status transitions across multiple complaint types. | Hamza Akram |
| 6 | 24 Sep | Claude Code (Anthropic, Claude Opus 5) | Dataset planning, repository layout and hand-offs (entries 16–18, 21–22, 24, 26): data brief for a teammate, restructure into `backend/`, `frontend/`, `dataset/`, a frontend specification for the teammates, status report. | Repository layout, root and frontend READMEs, CI paths, `backend/src/api/v1/complaints.py` (`/mine`) | 547 tests passing after the move with 0 skipped (42 silent skips found and fixed); 605 after adding `/mine` | Team lead asked the team to collect about 100 complaints with a 15% adversarial share, and set the three-folder layout and the location of `.venv`. | Hamza Akram |
| 7 | 24 Sep | Claude Code (Anthropic, Claude Opus 5) | RaftarXpress dataset integration and tuning (entries 28–34): verification of the teammate's dataset, conversion into the backend's configuration, lexicon and bridge rules, test repair, provider diagnosis. | `dataset/raftarxpress/**` (organised, README), `backend/scripts/verify_dataset.py`, `backend/scripts/convert_raftarxpress.py`, `backend/config/taxonomy.yaml`, `signals.yaml`, rule YAML files, tests in 14 files, `backend/genai_pipeline/providers/*` | `verify_dataset.py`: no structural or referential problems, all 11 SRS minimums met; Pipeline 2 alone over 500 complaints (escalation 70.2%, category 23.6%); both pipelines on 40 complaints (GenAI category 78.9% on the 19 Gemini answered); 627/693 → 693 passing, 0 failures | Authored and delivered the RaftarXpress dataset (500 labelled complaints, 25 policy documents, 105 rules). Verified minimum thresholds and taxonomy mappings. Commit 11eab4d "Backend and Dataset ready". | Hamza Akram |
| 8 | 24–25 Sep | Claude Code (Anthropic; `claude-fable-5-1` for the rebuild in entry 35, Claude Opus 5 for entries 36–39, Claude Opus 5.5 for 40–42) | Frontend rebuild and integration (entries 35–42): design system, landing page, 3D hero, 33 application pages with a typed API client, session proxy, sign-up, Gemini model chain, customer replies and evidence upload, design refresh. | `frontend/**` (app, components, lib), `frontend/.legacy/` (the teammates' first version, moved), `backend/src/services/auth.py`, `backend/src/api/v1/auth.py`, `backend/complaint_processing/customer_actions.py`, `backend/genai_pipeline/providers/chain.py`, tests (`test_register.py`, `test_model_chain.py`, `test_customer_actions.py`) | `next build` clean (37 routes); headless-browser checks (reduced motion, JavaScript off, no horizontal overflow at 390/768/1440 px, WCAG AA contrast); end-to-end sign-up → complaint → classification; 28/28 required pages render; backend 789 → 791 tests; measured latency 17.1–34.2 s | Designed and tested user interfaces, responsive layouts, color contrast standards, and integrated frontend routes with backend authentication and complaint APIs. Commits: a01106d, ef092e4. | Muhammad Mudasir |
| 9 | 25 Sep | Claude Code (Anthropic, Claude Opus 5.5) | Speed, live progress, dataset in the database, account security, chatbot (entries 43–44). | `backend/src/core/progress.py`, `refcache.py`, `totp.py`, `backend/src/services/auth.py`, `backend/src/api/v1/assistant.py`, `backend/genai_pipeline/assistant.py`, `backend/alembic/versions/0003_account_security.py`, frontend profile, organisation, assistant and landing components | 863 tests passing; about 16 s per complaint (from 34–67 s); 500 dataset complaints analysed — AI 43.8%, rules 39.4%, mandatory-escalation recall 51.7% against the labels; the chatbot refused off-topic and injection requests | Tested MFA/TOTP two-step sign-in end-to-end, tested assistant boundaries against prompt leakage, and tuned response caching. | Zaki Haider |
| 10 | 25 Sep | Claude Code (Anthropic, Claude Opus 5.5) | Email channel, separate dashboards, free-only AI chain, jailbreak guard, users pages, reports (entries 45–50). | `backend/src/services/email_channel.py`, `email_template.py`, `backend/genai_pipeline/email_reply.py`, `backend/src/api/v1/email.py`, `backend/alembic/versions/0004_email_messages.py`, `backend/security/manipulation_guard.py`, `backend/config/signals.yaml`, `backend/src/api/v1/people.py`, `backend/src/services/role_views.py`, `backend/complaint_processing/file_intake.py`, `backend/scripts/generate_reports.py`, `backend/reports/**`, frontend dashboards and email pages | 885 → 938 → 945 tests; 21 browser checks; free-model benchmark (3 real complaints per model); 16 jailbreak styles with 0 successes; 51/51 attack complaints detected, 0 false alarms on 449, 14/14 live attacks held; accuracy against labels about 35–40%, with 232 disputed labels listed in `label_audit.csv` (labels not changed) | Executed adversarial jailbreak evaluations, verified manipulation guard blocks on 16 attack styles, and verified email intake sanitization. | Abdul Sami |
| 11 | 26 Sep | Claude Code (Anthropic, Claude Opus 5.5) | Requirement visibility audit and five-role access control (entries 51–53). | `backend/src/core/scope.py`, `backend/src/api/v1/*` (complaints, review, admin, audit, people), `backend/src/services/role_views.py`, `backend/schemas/people.py`, `backend/tests/test_rbac.py`, `frontend/lib/roles.ts`, manager and reviewer dashboards, users pages | 976 tests; 55 browser checks across the five roles | Tested 5 distinct role permissions (Customer, Agent, Reviewer, Manager, Admin). Commit 965052d (Muhammad Mudasir) delivered evaluator demo features, explainability panel, verification meter, and split race view. | Muhammad Mudasir |
| 12 | 27 Sep | Claude Code (Anthropic, Claude Opus 5.5) | Performance, logo, deployment preparation (entries 54–56). | `backend/src/core/response_cache.py`, `backend/src/services/warmup.py`, `backend/src/core/deps.py`, `ratelimit.py`, `frontend/lib/use-api.ts`, reports and customer dashboard pages, brand images in `frontend/public/`, `frontend/app/api/session/*`, `DEPLOYMENT.md`, `backend/constraints.txt`, tests (`test_production_guards.py`, `test_proxy_client_address.py`) | Page loads 0.05–0.6 s measured in a browser (from 20–72 s); 977 → 981 tests; logo placement checks | Tested agent account creation workflow, verified client session proxy and rate-limiting responses across frontend dashboard pages. | Zaki Haider |
| 13 | 27 Sep | Claude Code (Anthropic, Claude Opus 5.5) | Deployment on Render and Vercel (entries 57–61): deployment steps, CORS and build-variable diagnosis, trailing-slash tolerance, Gmail relay for Render. | `backend/src/core/config.py`, `backend/src/services/email_channel.py`, `backend/scripts/gmail-relay.gs`, `backend/tests/test_email_relay.py`, `frontend/app/login/page.tsx`, `frontend/components/layout/app-shell.tsx` | 984 tests; full suite passed including the new relay tests | Deployed backend on Render and frontend on Vercel; configured production environment variables, tested live health endpoints and live Gmail relay service. | Zaki Haider |
| 14 | 27 Sep | Claude Code (Anthropic, Claude Opus 5.5) | Documentation and submission packaging (entry 62; in progress). | `backend/documentation/**`, `backend/reports/**`, this file | Complete documentation and verification checks | Reviewed project report, technical blog, and verified SRS requirement compliance matrix. | Abdul Sami |

**Other AI tools.** `frontend/AI_USAGE.md` is a separate declaration written by the
authors of the first frontend (now in `frontend/.legacy/`); it lists "Antigravity AI
Engine" as the tool they used. The review report pasted in log entry 40 does not state
its source. Any other AI tool a team member used must be added to this file.



---

## C. Dataset generation

| Artefact | Method | Human review |
|---|---|---|
| RaftarXpress complaint dataset — 500 labelled complaints (`dataset/raftarxpress/complaints/`) | Authored by a teammate and delivered as JSON with ground-truth labels. The authoring method is to be stated by the team. The assistant organised, converted and imported the files; it did not write complaints or change their labels. | Checked by `backend/scripts/verify_dataset.py` (no structural or referential problems; all 11 SRS minimums met). 232 labels where both pipelines agree with each other but not with the label are listed in `backend/reports/label_audit.csv` for the team to review; no label was changed. Reviewed by Hamza Akram and Abdul Sami. |
| RaftarXpress knowledge base — 25 policy/SOP documents | Written by a teammate as structured JSON; rendered to 13 PDF and 12 DOCX files by scripts written with AI assistance. | Verified by `verify_dataset.py`; one document labelled Draft with a past effective date (DOC-025) was flagged for the team. Reviewed by Abdul Sami. |
| Complaint Resolution Rule Matrix | The 105 rules (conditions written as prose) came with the teammate's dataset. `backend/scripts/convert_raftarxpress.py`, written with AI assistance, converts them into evaluable YAML rules; the matching vocabulary was derived from the taxonomy and rule text, never from the complaints it is scored against. Cross-cutting signals (hazard, injury, legal threat, repeat contact, high value) and the rules that connect them were written with AI assistance. The matrix is configuration: SRS Step 8 forbids generating it at runtime with the model that resolves complaints, and it is not. | Reviewed and verified by Hamza Akram and Zaki Haider. |
| Early placeholder policies (`dataset/ecommerce/`, `dataset/logistics/`: DEL-POL-04, REF-POL-02, SAF-POL-02) | Written by the AI assistant as YAML sources for the placeholder organisation "Zenithra", used to test the PDF and DOCX parsers. Superseded by the RaftarXpress corpus. | — |

---

## D. Team contribution record: MSG-Titans4

Summary of
[`backend/documentation/TEAM_CONTRIBUTION.md`](backend/documentation/TEAM_CONTRIBUTION.md),
which lists every commit.

| Member | Role | Owned areas (evidence) | Can explain | Commits |
|---|---|---|---|---|
| **Zaki Haider** (TheBossMan110; syedzakihaider2006@gmail.com) | Team Leader: Architecture, Backend Foundation, Dual-Pipeline Verification, Progress & Security, Deployment | Directed requirements, supplied keys and designs, tested in the browser and reported defects, deployed on Render and Vercel. His six commits carry the code written with the AI assistant, plus the teammates' dataset and first frontend | Architecture, Dual-Pipeline Verification, Backend APIs, Database & Migrations, Deployment | 6 |
| **Muhammad Mudasir** (mudasirhanif5438@gmail.com) | Frontend Rebuild, 5-Role RBAC & UI Views, Dashboard & Rate Limiting | Commit 965052d: agent, manager and reviewer dashboards, complaint views, analytics, reports and trends services, people and organisation APIs | 5-Role Dashboards, RBAC Views, Explainability Panel, Verification Meter, Split Race View | 1 |
| **Hamza Akram** (hmzaakram295@gmail.com) | Complaint Workflow & SLAs, Dataset Planning, RaftarXpress Dataset Tuning | `frontend/package-lock.json`, RaftarXpress dataset delivery and verification (500 labelled complaints, 25 policies, 105 rules) | Dataset schema, ground-truth labelling, policy precedence, dependency configuration | 1 |
| **Abdul Sami** | Knowledge Base & Vector Retrieval, Jailbreak & Injection Defense, Documentation Compliance | Verification of adversarial test cases, prompt injection defense testing, synthetic complaint verification, and documentation compliance | Adversarial complaint testing, prompt injection guards, compliance verification | 0 in git history |
