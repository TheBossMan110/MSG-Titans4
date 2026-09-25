# SupportNova — frontend

Next.js 16 (App Router, Turbopack) · React 19 · Tailwind 4 · GSAP + ScrollTrigger · Lenis · React Three Fiber.

The AI writes in pencil; the rules confirm in ink. Every screen is built on that one
reading: sand, dashed, italic serif for what the model proposed; solid espresso for
what the deterministic rule engine confirmed. The design plan is in [`DESIGN.md`](./DESIGN.md).

## Run it

```bash
cp .env.example .env.local        # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                       # http://localhost:3000
npm run build && npm start        # production
```

The backend must be running (`uvicorn src.main:app` in `../backend`) with `CORS_ORIGINS`
including `http://localhost:3000`. Seeded accounts and the published demo password are in
the backend README; there is no self-registration by design (`/register` explains why).

## What is where

| Path | Purpose |
|---|---|
| `app/page.tsx` + `components/landing/*` | the 16-section landing page |
| `components/three/*` | the six-slab 3D engine (`engine.tsx`), its poster, and the loader that only mounts WebGL on large, motion-allowed screens |
| `components/motion/*` | Lenis driven by `gsap.ticker`, `useGsap` (one `gsap.context` per section, reverted on unmount), `useReveal` |
| `components/ui/*` | the design system: primitives, surfaces (`PencilInk`), forms, data (`Stat` with honest nulls, `Ratio` with its fraction), feedback |
| `components/layout/*` | marketing nav, footer, `AppShell` (role-filtered sidebar), `AuthGuard` |
| `components/app/*` | complaint panels shared by the detail page and the review desk; house charts |
| `app/dashboard/**` | every application route (see the page map in `DESIGN.md` §5) |
| `app/api/session/*` | the session proxy (below) |
| `lib/api.ts` | one typed client for all 84 backend operations, generated types in `lib/api-types.d.ts` |
| `lib/use-api.ts` | `useApi` / `useAction` and formatting helpers |

Regenerate the API types after a backend change:

```bash
curl -s http://localhost:8000/openapi.json > lib/openapi.json
npx openapi-typescript lib/openapi.json -o lib/api-types.d.ts
```

`next build` runs the TypeScript check with `ignoreBuildErrors: false`, so a backend
schema change that breaks a page fails the build rather than a demo.

## Security model

- **No keys in the frontend.** There is no Supabase client and no service-role key;
  the browser talks only to the FastAPI backend and to its own origin.
- **Access token in memory only.** Never in `localStorage`, never in a URL. Report
  downloads go through `fetch` with the bearer header, then a blob.
- **Refresh token never reaches JavaScript.** The backend issues it in the response
  body; the route handlers under `app/api/session/` keep it in an `httpOnly`,
  `SameSite=Lax` cookie scoped to `/api/session` and forward it on the browser's behalf
  (`login`, `refresh`, `logout`). Rotation is honoured; a rejected refresh clears the cookie.
- **Roles are the server's decision.** The sidebar and the guards hide what a role
  cannot use so the interface never offers an action the API will refuse, but every
  request is still authorised by the backend.
- **Refusals are shown, not swallowed.** A 422 from lowering an escalation floor is the
  explanation the reviewer needs; `ErrorState` renders the server's sentence.

## Three traps in this stack

All three of these fail **silently** — the build passes, nothing logs, the page
just looks wrong. Each cost real debugging time, so they are worth knowing.

1. **Base styles must live in `@layer base`.** Unlayered CSS outranks every
   layered rule, so a bare `a { color: inherit }` beats `.text-ink-on-dark`
   and every button label renders charcoal on espresso, i.e. invisible.

2. **Never write `text-[var(--text-hero)]`.** An arbitrary value beginning
   with `var()` is ambiguous, and Tailwind resolves it as a *colour* — so the
   font size never applies and the headline renders at body size. Use the
   named utilities (`text-hero`, `text-h1`, `text-h2`, `text-h3`, `text-lead`)
   registered in the `--text-*` namespace in `globals.css`.

3. **New theme values must be declared to `tailwind-merge`** in
   [`lib/utils.ts`](./lib/utils.ts). It only knows Tailwind's stock scales;
   given `text-h1 text-espresso` it assumes both are colours, calls them a
   conflict and drops the size. Add every new colour and font size to the
   `extend.theme` lists there.

A fourth, about motion: **never hide content with CSS that only JavaScript can
undo.** `useReveal` sets the hidden state in GSAP and observes with
IntersectionObserver, so a failed script, reduced motion or a reflow all leave
the page readable. It also observes the unclipped headline rather than the
line inside the `overflow-hidden` mask, because a fully clipped element never
reports as intersecting.

## Motion and performance rules

- Lenis is stepped by `gsap.ticker`; `ScrollTrigger.update` runs on every scroll event;
  `lagSmoothing(0)`. Scrubbed animations never run a frame behind.
- Animations are `transform` and `opacity` only. The pencil→ink centrepiece is an
  espresso layer scaling in from the left, not a background-colour tween.
- `prefers-reduced-motion`: Lenis does not mount, `[data-reveal]` is visible from
  first paint, the 3D engine shows its static poster.
- Three.js is `next/dynamic` (`ssr: false`), mounted after first paint on `requestIdleCallback`,
  `frameloop="demand"`, DPR clamped to `[1, 1.75]`, six rounded boxes, one contact shadow.
  Under 1024px only the SVG poster renders.
- **three is pinned to exactly `0.182.0`.** React Three Fiber (9.8.x, including the
  latest release) constructs a `THREE.Clock` for every canvas; three deprecated `Clock`
  in r183 and logs a warning each time. r182 is the newest release R3F runs on without
  deprecation warnings. Unpin once R3F moves to `THREE.Timer`. The canvas still uses
  `shadows="percentage"` (PCFShadowMap), which is correct on every version.
- Fonts are self-hosted through `next/font` (Fraunces, Instrument Sans, JetBrains Mono).

## Honesty rules for figures

`Stat` renders `null`/`undefined` as *Not measured*, never as 0 or a full bar. `Ratio`
prints `count/total · pct`. The analytics page calls pipeline agreement *agreement*, not
accuracy; accuracy is only on the benchmark pages, against labels.

## Legacy

The previous scaffold is parked in `.legacy/` (excluded from the TypeScript program)
for reference and can be deleted.
