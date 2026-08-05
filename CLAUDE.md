# CLAUDE.md

Guidance for Claude Code working in this repository. Keep this file short; the full
roadmap lives in `PROJECT_PLAN.md`.

**Read `PROJECT_PLAN.md` yourself (with the Read tool) at the start of any new phase, or whenever
a question touches schema, architecture, or phase scope.** It is deliberately NOT imported here
with `@` — at ~860 lines it would load into every session and crowd out these rules. Open it on
demand instead.

## What this is

**Manitou** — a reusable single-vendor online store platform. Web first, mobile later. One shared
PostgreSQL database, accessed only through one backend API. Concurrency target is sized per
`PROJECT_PLAN.md` Section 10.1 (early-launch tier), not assumed as a round number — don't propose
"~1,000 concurrent users" as a launch requirement; it's a documented later-stage milestone.
Payments via Stripe. Hosted on AWS. A learning project built from first principles rather than a
hosted solution like Shopify.

The repo should be cloneable and adaptable to different store types (T-shirts = the default build,
candles, single-product, grocery, broad catalog) by changing config and content — not architecture.

## Scope guardrails

- **Single vendor, always.** One seller, many customers. Admin area is a role-gated route.
- **Never propose marketplace features** — no multiple sellers, seller onboarding, split payouts,
  or Stripe Connect. A large catalog is a scale problem (indexing, search, pagination), not a
  multi-vendor one.
- **Build the T-shirt store concretely first.** Do not generalize ahead of need. The only
  pre-built reusability seams are the three in `PROJECT_PLAN.md` Section 1.1: store config,
  `products.unit_of_measure`, and `product_variants.attributes` (JSONB). Nothing beyond those.

## Golden rule

**Clients never touch the database directly.** The web app, vendor portal, iOS, and Android
apps all go through the backend API. Only the API connects to PostgreSQL.

## Tech stack

- Database: PostgreSQL (local via Docker; AWS RDS in production)
- Backend: Python + FastAPI, SQLAlchemy, Alembic, Pydantic
- Auth: JWT (bcrypt password hashing), roles: `customer` / `admin`
- Web: Next.js (React) + Tailwind CSS — storefront and `/admin` vendor portal in ONE app
- Mobile: Kotlin/Jetpack Compose (Android), Swift/SwiftUI (iOS) — added after web works
- Design: `design-tokens.json` at repo root is the single source of truth for color, type, spacing
- Payments: Stripe (PaymentIntents + webhook)
- Infra: Docker, GitHub Actions, AWS (RDS, ECS Express Mode, ECR, S3, CloudFront, Route 53)

## Repo layout

- `backend/` — FastAPI app (`models/`, `schemas/`, `routers/`, `services/`, `db.py`)
- `backend/alembic/` — migrations
- `web/` — Next.js storefront + vendor portal
- `mobile-android/`, `mobile-ios/` — added in Phase 7
- `infra/` — deployment notes/scripts

## Conventions

- **Python work always runs inside the project venv at `backend/.venv`.** Before suggesting any
  `pip`, `python`, `alembic`, `uvicorn`, or `pytest` command, assume the venv must be active and
  remind the owner if it may not be. Never suggest a global `pip install`.
- Every new dependency is added to `requirements.txt` and committed. `.venv/` is never committed.
- Local dev split: PostgreSQL runs in Docker; the API runs on the host in the venv. Phase 6
  containerizes the API for AWS. Both install from the same `requirements.txt`.
- Config comes from `.env` (git-ignored). Any new variable must also be added to `.env.example`
  with a placeholder.
- **Never hardcode a color, font size, or spacing value in any component on any platform.** All of
  them come from `design-tokens.json` (via Tailwind on web, via the theme file on Android/iOS).
- **Never hardcode a store-specific value** (store name, currency, tax rules, enabled features) in
  a component or endpoint — it belongs in the store configuration. A cloned store should only need
  to edit store config + `design-tokens.json` + content.
- Variant dimensions live in `product_variants.attributes` (JSONB). The API validates key
  consistency; the DB cannot. Use `variant_name` for display, `attributes` for logic/filtering.
- The vendor portal is the `/admin` route of the same Next.js app — never a separate project. It
  reuses the Phase 3 UI primitives.
- Keep interface wording identical across web, Android, and iOS (same button labels, same terms).
- Mobile apps match the brand (color, type, spacing, wording), not the website's layout — use
  native navigation and native controls on each platform.
- All schema changes go through an Alembic migration — never edit the DB by hand.
- Money columns use `numeric(10,2)`, never floats.
- `order_items` snapshot product name and price at purchase time.
- Wrap checkout (order + inventory decrement + payment) in a single DB transaction;
  guard inventory so stock can't go negative under concurrency.
- Secrets (DB password, Stripe keys) come from env vars / AWS Secrets Manager. Never commit them.
- Validate all input at the API boundary with Pydantic.
- Stripe handles card data; we store only Stripe reference IDs.

## Working style

- **This is a learning project. The owner drives; you guide. This is not agent mode.**
  Explain the concept, draft code together, and let the owner review and understand each change
  before it is saved. Do not batch-implement multiple files without walking through them.
- `PROJECT_PLAN.md` tags every task **[You]** (owner acts alone) or **[You + Claude Code]**
  (work together). Respect that split — don't do **[You]** tasks (accounts, installs, sign-ins,
  running commands, decisions) for them.
- Follow the phase order in `PROJECT_PLAN.md`. Don't start mobile before the web store works end to end.
- When unsure about schema or business rules, check `PROJECT_PLAN.md` Section 6 before improvising.
- Prefer clear, teachable code — the owner is learning databases and AWS.

## Current phase

<!-- Update this line as you progress, e.g. "Phase 1 — Database" -->

Phase 2 — Backend API
