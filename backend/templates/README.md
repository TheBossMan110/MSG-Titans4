# templates/

SupportNova's backend is a JSON API (FastAPI). It renders **no server-side HTML pages**, so this folder is
intentionally empty apart from this signpost. The web pages are React components in the Next.js frontend
(`frontend/app/` and `frontend/components/`).

The project does use templates in four places. Each lives next to the code that owns it:

| Template | Where | Format | What it is for |
|---|---|---|---|
| GenAI prompts | [`backend/prompt_templates/`](../prompt_templates/) | Jinja2 (`.j2`) | The instructions sent to the model |
| Customer email | [`backend/src/services/email_template.py`](../src/services/email_template.py) | Python (table-based HTML with inline styles, plus a plain-text version) | The branded reply a customer receives by email |
| Organisation reply templates | [`dataset/raftarxpress/configuration/response_templates.json`](../../dataset/raftarxpress/configuration/response_templates.json) | JSON (14 templates) | RaftarXpress's own house-style replies, per scenario and tone |
| Report files | [`backend/src/services/reports.py`](../src/services/reports.py) | Generated in code (CSV, XLSX with openpyxl, PDF with ReportLab) | The downloadable reports |

## 1. Prompt templates (Jinja2)

```
backend/prompt_templates/
├── complaint_intelligence/   v1.0.j2  v1.1.j2   Pipeline 1: classify, extract, cite, propose resolution (JSON)
├── customer_response/        v1.0.j2  v1.1.j2   the suggested reply, from the reconciled (rule-checked) record
└── escalation_note/          v1.0.j2            the handover note for the team receiving an escalation
```

* They are reached **only** through `backend/genai_pipeline/prompts.py`, which renders them with
  `StrictUndefined` (a missing variable is an error, never a silent blank).
* **Versioned:** a change means a new file (`v1.2.j2`), never an edit in place. Every AI run stores the prompt
  version that produced it (`genai_runs.prompt_version`).
* **Checksummed:** each version's SHA-256 is registered in the `prompt_versions` table, so a template edited
  without a version bump is detected.
* **One active version per prompt,** switched by an administrator under **Prompt Templates** in the web
  application (`PATCH /api/admin/prompts/{name}`).
* Category, department, priority and escalation codes are injected from the database at render time, so adding a
  category never requires editing a prompt. The complaint and any document text are fenced as untrusted data,
  never as instructions.

Two short system prompts are not in this folder: the chat receptionist *Nova* (`SYSTEM` in
`backend/genai_pipeline/assistant.py`) and the email triage and reply prompts (`backend/genai_pipeline/email_reply.py`).
They are constants in their modules; both outputs still pass the manipulation guard before anyone sees them.

## 2. Customer email template

`backend/src/services/email_template.py` builds the reply that goes to a customer who emailed
`supportnova110@gmail.com`: `render_html()` for the HTML body and `render_text()` for the plain-text part. Email
clients are not browsers, so the layout is tables with inline styles only, in the site's colours and fonts with
safe fallbacks. The logo travels inside the email as an inline image from
`backend/src/assets/supportnova-mark-email.png`, so it shows even while the site runs on `localhost`.

Preview it filled with sample content: **Email → Email template preview** in the web application, or
`GET /api/email/preview` (staff only).

## 3. Organisation reply templates

`dataset/raftarxpress/configuration/response_templates.json` holds the company's 14 authored reply templates
(scenario, tone, text with placeholders). `backend/scripts/convert_raftarxpress.py taxonomy` copies them verbatim
into the `response_templates:` section of `backend/config/taxonomy.yaml`; the seeder stores them in the
`app_config` table, and staff read them under **Organisation → Reply templates** (`GET /api/organisation`).
They are the house-style reference for agents. Generated replies come from the `customer_response` prompt and are
checked by the response guard; the same scenarios are also available to retrieval through the knowledge-base
document *DOC-022 Standard Customer Response Templates*.

## 4. Report layouts

CSV, Excel and PDF exports are laid out in code in `backend/src/services/reports.py`, not from template files.
The CSV carries a byte-order mark so Excel on Windows opens it without garbling characters.
