# SupportNova — Frontend Design & Build Plan

The plan the build follows. Written before the first component, as the brief
asks, and kept because the team and the judges both read it.

---

## 1. What this is

SupportNova is not a chatbot. The interface has one job: make the **dual
pipeline** legible at a glance — a generative model *proposes*, a deterministic
rule engine *verifies* against the company's own policies, and nothing reaches
a customer that the second did not confirm.

Every design decision below serves that sentence.

## 2. Visual metaphor

**The AI writes in pencil. The rules confirm in ink.**

That metaphor runs through the whole system, in place of the indigo-vs-cyan
"two engine" colouring of the old build:

| | AI recommendation (pencil) | Ground-truth validation (ink) |
|---|---|---|
| Fill | sand `#E7DCCB` | espresso `#2A1F17` |
| Border | dashed, taupe | solid, espresso |
| Type | serif italic | sans, medium |
| Reads as | a proposal | a decision |

A verified resolution is the moment pencil becomes ink. The landing page's
central section animates exactly that.

## 3. Colour

Light-first. Cream is the ground; espresso is spent deliberately on brand
moments and a few full-bleed dark sections. There is no theme toggle — the
product *is* cream and espresso, the way a printed document is.

```
--cream      #F5F0E8   page ground
--ivory      #FBF8F2   cards on cream
--sand       #E7DCCB   AI / pencil fills, subtle panels
--taupe      #A08B75   secondary text, dashed borders, muted marks
--espresso   #2A1F17   PRIMARY: buttons, headlines on cream, dark sections
--espresso-2 #3D2E22   hover, dark-section cards
--charcoal   #1C1917   near-black type
--ink-on-dark #F1EBE1  type on espresso
```

Semantic colours are earthy relatives of the palette, never neon, and they are
for **state only** — they do not count as accent:

```
--verified  #3F6B4A  moss      confirmed / ELIGIBLE / ACTIVE
--warning   #B8862B  ochre     at-risk / REQUIRES_VERIFICATION / HIGH
--critical  #A63D2F  oxblood   breach / P0 / CRITICAL_MGMT / blocked
```

Rule: P0 and an overdue follow-up must be findable by eye in a full table.

## 4. Typography

Three faces, each with one job, all self-hosted through `next/font`:

- **Fraunces** (variable, optical size) — display and section headlines. Big,
  editorial, with the SOFT axis for warmth. Italic for the "pencil" register.
- **Instrument Sans** — every UI surface and body paragraph.
- **JetBrains Mono** — references, codes, timestamps, figures in columns.
  `font-variant-numeric: tabular-nums` wherever digits stack.

Scale: a fluid `clamp()` ramp from 0.8rem to 6.5rem. Display headlines get
`text-wrap: balance`, tight leading (1.0–1.05), and negative tracking. Running
text stays near 65ch.

Headline register is short and declarative, in stacked lines:

```
UNDERSTAND
EVERY COMPLAINT.

VERIFY
EVERY DECISION.
```

## 5. Page map

Every one of the backend's **84 operations** is owned by exactly one route.
Routes in **bold** are new against the previous scaffold; routes struck through
are removed.

### Public
| Route | Purpose | Endpoints |
|---|---|---|
| `/` | the landing page, 16 sections | `GET /api/health` (degraded banner) |
| `/login` | sign in | `auth/login`, `auth/refresh` |
| `/register` | see §11 | — |
| `/track` · `/track/[ref]` | customer tracking | `complaints/{ref}/status` |
| ~~`/pricing` `/contact` `/features` `/how-it-works` `/about`~~ | folded into the landing story | |

### Application (`/dashboard/…`)
| Route | Purpose | Endpoints |
|---|---|---|
| `/dashboard` | command centre | `analytics/dashboard`, `analytics/my-queue`, `review/stats`, `audit/actions` |
| `/dashboard/complaints` | queue + filters | `GET complaints` |
| `/dashboard/complaints/new` | intake | `POST complaints` |
| `/dashboard/complaints/[id]` | 7-tab detail | `complaints/{ref}` + `explain` `checklist` `follow-ups` `escalation` `lifecycle` `status` `reanalyse`, `review/{ref}/history` `sla`, **`audit/complaint/{id}`** |
| `/dashboard/my-complaints` | customer list | `complaints/mine` |
| **`/dashboard/follow-ups`** | due across all complaints | `review/follow-ups/due` |
| `/dashboard/review` | queue | `review/queue`, `review/stats` |
| **`/dashboard/review/[ref]`** | claim + decide | `review/queue/{ref}/claim`, `review/{ref}/actions` |
| `/dashboard/escalations` | *rewired from mock* | `GET complaints?escalation=…`, `complaints/{ref}/escalation` |
| `/dashboard/knowledge-base` | documents + health + findings | `documents`, `coverage`, `validation-issues` |
| `/dashboard/knowledge-base/upload` | multi-file upload | `POST documents` |
| `/dashboard/knowledge-base/[id]` | version history | `documents/{id}` |
| **`/dashboard/knowledge-base/versions/[id]`** | sections, chunks, activate, **impact** | `versions/{id}`, `chunks`, `activate`, `deactivate`, **`impact`** |
| **`/dashboard/knowledge-base/search`** | search + **traceability** | `documents/search`, `trace/{chunk_key}`, `chunks/by-reference` |
| `/dashboard/rules` | *rewired from mock* — the matrix | `admin/rules`, `admin/taxonomy`, `admin/rules/reload` |
| **`/dashboard/rules/sandbox`** | the live-modification demo | `admin/rules/test` |
| **`/dashboard/rules/[ref]`** | one rule, editable | `GET/PATCH admin/rules/{ref}` |
| `/dashboard/analytics` | the story | `volume` `categories` `departments` `pipelines` |
| **`/dashboard/analytics/trends`** | rising + history + snapshot | `trends`, `trends/history`, `trends/snapshot` |
| `/dashboard/reports` | read + **download** | `reports`, `reports/{type}`, **`reports/{type}/export`** |
| **`/dashboard/exports`** | export audit | `analytics/exports` |
| `/dashboard/prompts` | *rewired from mock* | `admin/prompts`, `PATCH admin/prompts/{name}` |
| **`/dashboard/security`** | injection stats + **deliberate defects** | `admin/defects`, `defects/demonstrate` |
| **`/dashboard/audit`** | the organisation trail | **`audit`, `audit/actions`, `audit/{type}/{id}`** |
| `/dashboard/settings` | tabs: config · lexicon · SLA · account · system | `admin/config`, `admin/lexicon`, `admin/sla`, `auth/me`, `change-password`, `logout`, `health`, `version` |
| `/dashboard/benchmark` · `/[id]` · **`/datasets/[tag]`** | scoring | `benchmark/*` incl. **import**, **delete** |
| ~~`/dashboard/evaluation`~~ | was mock; becomes `/security` + `/benchmark` | |
| ~~`/dashboard/validation`~~ | folded into `/analytics` (pipelines) | |

## 6. The landing page (16 sections)

1. Navigation — minimal, sticky, cream→translucent on scroll
2. Hero + 3D intelligence engine
3. Trust statement — one sentence, no logos wall
4. "A complaint is more than text" — one complaint, nine dimensions unfold
5. Complaint understanding — entity extraction shown on real text
6. The pipeline — 8 stages, scroll-activated, one continuous line not 8 cards
7. **AI vs ground truth** — pencil becomes ink. The centrepiece.
8. Knowledge base — floating document cards with version and effective date
9. Routing + escalation — a command board, the ladder P3→P0
10. Security — the injection is shown, then BLOCKED, then the audit row
11. Interactive demo — a real complaint processed live against the API
12. Analytics — three real figures, honest nulls if unmeasured
13. Human review — the override that the floor refuses
14. Complete workflow — the whole chain, quietly
15. Final CTA on espresso
16. Footer

Copy rule: nothing on the page is a claim the backend cannot demonstrate.

## 7. The 3D engine

Not a decorative object. **Six thin slabs** — Complaint, AI, Knowledge, Rules,
Validation, Resolution — stacked in the hero, then separated by scroll into a
labelled sequence. Materials are honest: sand matte for the AI slab (pencil),
espresso solid for the Validation slab (ink), which *locks* into place last.
Warm key light, soft fill, contact shadow. No particles, no neon.

Engineering:
- React Three Fiber + drei, loaded with `next/dynamic({ ssr: false })` after
  first paint; a static SVG poster holds the space until it mounts
- `frameloop="demand"`, invalidated only by the scroll scrub
- DPR clamped to `[1, 1.75]`; geometry is six boxes
- `dispose()` on unmount; the canvas pauses when off-screen
- **Under 1024px: the static poster only.** No 3D on phones.

## 8. Motion

- **Lenis** for smooth scroll, driven by GSAP's ticker (not its own rAF), with
  `lenis.on('scroll', ScrollTrigger.update)` and `lagSmoothing(0)` — the sync
  the previous build was missing
- **GSAP + ScrollTrigger** for reveals, parallax, the pipeline scrub, the 3D
  scrub. One `gsap.context()` per section component, reverted on unmount
- **anime.js** for number counters and status pulses only
- Only `transform` and `opacity` animate. Nothing animates layout
- `prefers-reduced-motion`: scrubs and parallax off, reveals become fades
- Timing register: slow, eased, `power2.out` / `expo.out`; nothing under 400ms
  except hover

## 9. Performance rules

Performance beats effect. Concretely: at most one ScrollTrigger per section;
`will-change` set only for the duration of an animation; images through
`next/image`; heavy components code-split; charts are hand-drawn SVG (no
chart library — three chart types do not justify one); IntersectionObserver
pauses anything off-screen. If a section stutters on a mid-range laptop, the
effect goes, not the frame rate.

## 10. Components

```
components/
  ui/         Button Card Badge Status Input Select Tabs Table Modal Toast
              Empty Skeleton ErrorState Eyebrow Display Kbd Tooltip
  layout/     MarketingNav AppShell Sidebar Topbar Footer AuthGuard
  motion/     SmoothScroll Reveal useGsap useReducedMotion
  three/      Engine Slab Poster (dynamic)
  marketing/  one component per landing section
  complaints/ review/ knowledge/ rules/ analytics/ security/
  charts/     Bars Area Donut Sparkline  (SVG, token-coloured)
```

The old `components/ui.tsx`, `components/supportnova.tsx`, `lib/mock-data.ts`
and the previous pages are parked in `.legacy/` (excluded from the TypeScript
program). Every page was rewritten on the new primitives; nothing imports the
legacy code and the folder can be deleted.

## 11. Two honest gaps

- **`/register` has no backend endpoint.** Accounts are provisioned by an
  administrator and roles are assigned, not chosen. The page says so and lists
  the demo accounts. A customer self-signup endpoint is a small backend
  addition if wanted; it is not faked in the frontend.
- **`ignoreBuildErrors` is turned off.** The build is the gate.

## 12. Build order

1. Tokens, fonts, primitives · 2. Nav, AppShell, Footer · 3. Landing sections
· 4. 3D hero · 5. Scroll story · 6. Auth · 7. Command centre · 8. Complaints
· 9. Detail · 10. Knowledge base · 11. Rules + sandbox · 12. Review
· 13. Analytics · 14. Reports, audit, security, settings · 15. Responsive
· 16. Performance pass · 17. Polish
