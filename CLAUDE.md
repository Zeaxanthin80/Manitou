# CLAUDE.md

Guidance for Claude Code working in this repository. Keep this file short; the full
roadmap lives in `PROJECT_PLAN.md`.

## What this is
A multi-platform online store for a single vendor. Web first, mobile later. One shared
PostgreSQL database, accessed only through one backend API. Target ~1,000 concurrent users.
Payments via Stripe. Hosted on AWS.

## Golden rule
**Clients never touch the database directly.** The web app, vendor portal, iOS, and Android
apps all go through the backend API. Only the API connects to PostgreSQL.

## Tech stack
- Database: PostgreSQL (local via Docker; AWS RDS in production)
- Backend: Python + FastAPI, SQLAlchemy, Alembic, Pydantic
- Auth: JWT (bcrypt password hashing), roles: `customer` / `admin`
- Web: Next.js (React) — storefront + `/admin` vendor portal (role-gated)
- Mobile: Kotlin (Android), Swift (iOS) — added after web works
- Payments: Stripe (PaymentIntents + webhook)
- Infra: Docker, GitHub Actions, AWS (RDS, App Runner/ECS, S3, CloudFront, Route 53)

## Repo layout
- `backend/` — FastAPI app (`models/`, `schemas/`, `routers/`, `services/`, `db.py`)
- `backend/alembic/` — migrations
- `web/` — Next.js storefront + vendor portal
- `mobile-android/`, `mobile-ios/` — added in Phase 7
- `infra/` — deployment notes/scripts

## Conventions
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
Phase 0 — Foundations
