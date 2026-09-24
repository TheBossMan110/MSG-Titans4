# Frontend

Next.js + TypeScript. Not built yet — this folder is the drop point.

## The backend is already running and documented

```bash
cd ../backend
uvicorn src.main:app --reload
```

| | |
|---|---|
| Interactive API docs | http://localhost:8000/api/docs |
| OpenAPI schema | http://localhost:8000/api/openapi.json |

**Generate the TypeScript types from the schema rather than hand-writing them.**
Every endpoint returns a declared Pydantic model, so the contract is exact and
stays correct when the backend changes:

```bash
npx openapi-typescript http://localhost:8000/api/openapi.json -o src/types/api.d.ts
```

## Signing in

Seeded accounts, all with password `SupportNova#2026`:

| Role | Email | Sees |
|---|---|---|
| customer | customer@zenithra.com | Their own complaint only |
| agent | agent.billing@zenithra.com | The complaint queue, their own workload |
| reviewer | reviewer@zenithra.com | The review queue, overrides |
| manager | manager@zenithra.com | Analytics, exports, SLA sweep |
| admin | admin@zenithra.com | Everything |
| evaluator | evaluator@zenithra.com | Read everything, run the benchmark |

`POST /api/auth/login` returns an access token and a refresh token.

## The four screens worth building first

1. **Submit + track** — `POST /api/complaints`, then
   `GET /api/complaints/{ref}/status`. The customer view is a separate, much
   smaller payload than the agent view; internal guidance and rule references
   are not fields of it.
2. **Agent queue** — `GET /api/complaints` with filters, then
   `GET /api/complaints/{ref}` for the working view. Mandatory guidance
   (`is_mandatory: true`) cannot be dismissed.
3. **Explainability** — `GET /api/complaints/{ref}/explain`. The most
   demo-worthy screen in the system: which rules fired and **on which words**
   (`rule_hits[].spans` carries character offsets into the complaint text), both
   pipelines' readings, every disagreement with its explanation, and every model
   attempt including the failed ones.
4. **Dashboard** — `GET /api/analytics/dashboard`. Ten panels in one call.

## Two contract details that will bite otherwise

**A percentage can be `null`, and that is not an error.** It means the control
was not measurable — no denominator. Render "—" or "not measured", never 0% and
never 100%. An empty system reporting perfect compliance is the exact failure
the backend goes out of its way to avoid.

**Some refusals are 404 by design.** Reading someone else's complaint returns
404, not 403, because a distinct 403 would confirm the reference exists and
public references are sequential.
