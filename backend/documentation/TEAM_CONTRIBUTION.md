# Team Contribution Record

Required by the SRS final submission checklist ("Team contribution record") and by
the GitHub requirement that the repository include work from all team members.

**Sources.** The git history of `github.com/TheBossMan110/SupportNova` (branch
`main`, 8 commits up to 27 Sep 2026, 19:01 PKT), and the development transcript
summarised in [`PROMPT_LOG.md`](PROMPT_LOG.md). Anything not evidenced by those two
sources is marked _\<to be confirmed by the team\>_; the team must complete it before
submission. AI assistance is declared separately in [`AI_USAGE.md`](../../AI_USAGE.md).

---

## 1. Members

| Member | Role | Owned areas | Can explain | Commits |
|---|---|---|---|---|
| **TheBossMan110** (git identity; syedzakihaider2006@gmail.com) — full name _\<to be added by the team\>_ | Team lead; owner of the backend and database (as he states in `PROMPT_LOG.md` entry 2) | Directed the requirements and every development step with the AI assistant; obtained the Gemini, Groq, OpenRouter and Supabase keys and the support mailbox's Gmail app password and set them in `.env` himself; supplied the design briefs, workflow and five-role permission design; tested in the browser and reported defects; deployed the backend on Render and the frontend on Vercel. His commits carry the backend and frontend code written with the AI assistant (see `AI_USAGE.md` section B), plus the teammates' dataset and first frontend. | _\<to be confirmed by the team\>_ | 6 |
| **Hamza Akram** | _\<to be confirmed by the team\>_ | Git history: `frontend/package-lock.json` only | _\<to be confirmed by the team\>_ | 1 |
| **Muhammad Mudasir** | _\<to be confirmed by the team\>_ | Git history (commit 965052d): agent, manager and reviewer dashboards; complaint list, detail and new-complaint pages; analytics and knowledge-base search pages; tracking pages; `complaint-bits`, `live-analysis`, `user-admin` and `app-shell` components; backend analytics, complaints, organisation and people APIs; analytics, reports and trends services; related schemas and GenAI prompt/response changes | _\<to be confirmed by the team\>_ | 1 |
| _\<name\>_ | _\<to be confirmed by the team\>_ | _\<to be completed by the team\>_ | _\<to be completed by the team\>_ | 0 in git history |
| _\<name\>_ | _\<to be confirmed by the team\>_ | _\<to be completed by the team\>_ | _\<to be completed by the team\>_ | 0 in git history |

"Can explain" must name the modules each member can explain to the judges; the SRS
states that a member unable to explain submitted code may receive reduced or zero marks
for that module.

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
them. The team must record the names.

| Contribution | Evidence | Author |
|---|---|---|
| The first frontend (Next.js), later moved to `frontend/.legacy/` | `PROMPT_LOG.md` entries 24 and 28 ("my team has make the frontend", "I got a frontend now"); committed in `11eab4d` | _\<to be confirmed by the team\>_. Its declaration `frontend/AI_USAGE.md` links to files under a local user folder named `mudas`, which suggests, but does not establish, Muhammad Mudasir. |
| The RaftarXpress dataset: 500 labelled complaints, 25 policy documents, 105-rule resolution matrix, taxonomy and response templates (`dataset/raftarxpress/`) | `PROMPT_LOG.md` entries 17, 18, 26 and 28 (the team collecting and verifying data; "the dataset he send"); committed in `11eab4d` | _\<to be confirmed by the team\>_ |
| Review of `backend/reports/label_audit.csv` (232 disputed labels) | Requested of the team in `PROMPT_LOG.md` entry 50 | _\<to be completed by the team\>_ |
| Project report, technical blog, demonstration video | Listed as team tasks in `PROMPT_LOG.md` entry 49 | _\<to be completed by the team\>_ |
