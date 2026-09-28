# Team Contribution Record: MSG-Titans4

Required by the SRS final submission checklist ("Team contribution record") and by
the GitHub requirement that the repository include work from all team members.

**Sources.** The git history of `github.com/TheBossMan110/SupportNova` (branch
`main`, 8 commits up to 27 Sep 2026, 19:01 PKT), and the development transcript
summarised in [`PROMPT_LOG.md`](PROMPT_LOG.md). Roles are as stated by the team. AI assistance is declared separately in [`AI_USAGE.md`](../../AI_USAGE.md).

---

## 1. Members

| Member | Role | Owned areas | Can explain | Commits |
|---|---|---|---|---|
| **Zaki Haider** (TheBossMan110; syedzakihaider2006@gmail.com) | Team Leader: Architecture, Backend Foundation, Dual-Pipeline Verification, Progress & Security, Deployment | Directed the requirements and every development step with the AI assistant; obtained the Gemini, Groq, OpenRouter and Supabase keys and the support mailbox's Gmail app password and set them in `.env` himself; supplied the design briefs, workflow and five-role permission design; tested in the browser and reported defects; deployed the backend on Render and the frontend on Vercel. His commits carry the backend and frontend code written with the AI assistant (see `AI_USAGE.md` section B), plus the teammates' dataset and first frontend. | Architecture, Dual-Pipeline Verification, Backend APIs, Database & Migrations, Deployment | 6 |
| **Muhammad Mudasir** (mudasirhanif5438@gmail.com) | Frontend Rebuild, 5-Role RBAC & UI Views, Dashboard & Rate Limiting | Git history (commit 965052d): agent, manager and reviewer dashboards; complaint list, detail and new-complaint pages; analytics and knowledge-base search pages; tracking pages; `complaint-bits`, `live-analysis`, `user-admin` and `app-shell` components; backend analytics, complaints, organisation and people APIs; analytics, reports and trends services; related schemas and GenAI prompt/response changes | 5-Role Dashboards, RBAC Views, Explainability Panel, Verification Meter, Split Race View | 1 |
| **Hamza Akram** (hmzaakram295@gmail.com) | Complaint Workflow & SLAs, Dataset Planning, RaftarXpress Dataset Tuning | Git history (`frontend/package-lock.json`), authored and verified the RaftarXpress 500-complaint dataset, policy/SOP structured documents, rule matrix conversion validation, dependency management | Dataset schema, ground-truth labelling, policy precedence, dependency configuration | 1 |
| **Abdul Sami** (Samixlive09@gmail.com) | Knowledge Base & Vector Retrieval, Jailbreak & Injection Defense, Documentation Compliance | Verification of adversarial test cases, prompt injection defense testing, synthetic complaint verification, and documentation compliance | Adversarial complaint testing, prompt injection guards, compliance verification | 0 in git history |

Each member can explain the modules listed against their name.

---

## 2. Commit history

All times Pakistan Standard Time (UTC+5). File counts and line changes are from
`git log --stat`.

| Date | Commit | Author | Message | Files changed | Summary of changes |
|---|---|---|---|---|---|
| 24 Sep 2026, 21:20 | `11eab4d` | TheBossMan110 | Backend and Dataset ready | 339 files, +119,575 | First commit. The whole backend as built so far (`backend/src`, pipelines, rule matrix, prompt templates, knowledge base, security, Alembic, config, 24 test files, Dockerfile, CI workflow); the datasets (`dataset/raftarxpress/` 67 files, `dataset/ecommerce/`, `dataset/logistics/`); the teammates' first frontend (`frontend/app`, `components`, `lib`, `public`, with its own `frontend/AI_USAGE.md`); root README, `AI_USAGE.md`, LICENSE and the SRS PDF |
| 25 Sep 2026, 11:27 | `a01106d` | TheBossMan110 | Backend and Frotnend Connectivity Done | 178 files, +37,776 / −5,899 | Rebuilt frontend (`frontend/app` 40 files, `components` 23, `lib` 7) with the first version moved to `frontend/.legacy/`; backend registration, audit API, customer actions and provider model chain with tests; the 25 knowledge-base documents re-rendered |
| 25 Sep 2026, 12:29 | `ef092e4` | Hamza Akram | Update package-lock.json | 1 file, +3 / −1 | `frontend/package-lock.json` |
| 25 Sep 2026, 21:05 | `ce93fa5` | TheBossMan110 | Frontend Design | 121 files, +10,362 / −807 | Email channel and templates, chat assistant, account security (two-step sign-in), live progress, reference-data cache, organisation API, migrations 0003–0004, 10 test files; frontend dashboards, profile, email and assistant pages, landing hero and chat |
| 26 Sep 2026, 14:21 | `2aa6207` | TheBossMan110 | 5 roles and fully requirment complete | 85 files, +23,607 / −12,887 | Five-role access control (`scope.py`, people API, role views), manipulation/jailbreak guard, uploaded-complaint intake, report generator and `backend/reports/`, 12 test files; manager and reviewer dashboards, users pages, `roles.ts`; regenerated OpenAPI types |
| 26 Sep 2026, 19:02 | `965052d` | Muhammad Mudasir | feat: complete 10 evaluator demo features, explainability panel, verification meter, and split race view | 43 files, +4,500 / −592 | Backend analytics, complaints, organisation and people APIs; analytics, reports and trends services; schemas; GenAI prompt/response changes. Frontend agent, manager and reviewer dashboards, analytics, complaint, knowledge-base search and tracking pages, and shared components. Also changed account creation so that managers can create agent accounts for their own team |
| 27 Sep 2026, 14:21 | `d04252d` | TheBossMan110 | Finaly done overall | 58 files, +1,637 / −3,617 | Server-side response cache and start-up warm-up, proxy-aware rate limiting, production start-up guards with tests, email logo and brand images, `DEPLOYMENT.md`, `backend/constraints.txt`, removal of the stale pnpm lockfile, frontend session routes and caching |
| 27 Sep 2026, 19:01 | `dc1b2b8` | TheBossMan110 | Admin email page, Gmail relay for Render, login cleanup | 9 files, +166 / −12 | Gmail relay script (`backend/scripts/gmail-relay.gs`) and relay sender with tests, configuration, admin Email page link, login page clean-up |

**Commits per day:** 23 Sep — 0; 24 Sep — 1; 25 Sep — 3; 26 Sep — 2; 27 Sep — 2. The
SRS asks for meaningful commits across all five days from all members.

---

## 3. Contributions shown in the transcript but not attributable from git

These were produced by team members according to the development transcript, but
reached the repository through the team lead's commits, so git does not show who did
them.

| Contribution | Evidence | Author |
|---|---|---|
| The first frontend (Next.js), later moved to `frontend/.legacy/` | `PROMPT_LOG.md` entries 24 and 28 ("my team has make the frontend", "I got a frontend now"); committed in `11eab4d` | Muhammad Mudasir |
| The RaftarXpress dataset: 500 labelled complaints, 25 policy documents, 105-rule resolution matrix, taxonomy and response templates (`dataset/raftarxpress/`) | `PROMPT_LOG.md` entries 17, 18, 26 and 28 (the team collecting and verifying data; "the dataset he send"); committed in `11eab4d` | Hamza Akram & Abdul Sami |
| Review of `backend/reports/label_audit.csv` (232 disputed labels) | Requested of the team in `PROMPT_LOG.md` entry 50 | Abdul Sami & Hamza Akram |
| Project report, technical blog, demonstration video | Listed as team tasks in `PROMPT_LOG.md` entry 49 | Zaki Haider, Muhammad Mudasir, Hamza Akram, Abdul Sami |
