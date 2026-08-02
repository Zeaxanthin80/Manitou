# Online Store — Master Plan

> The definitive build plan for a multi-platform online store with a single shared database.
> Every technology choice below is final — there are no open decisions. Work top to bottom;
> each phase assumes the previous one is complete.
>
> **This is a learning project. You drive; Claude Code guides.** You are not using agent mode.
> Claude Code explains concepts and drafts code with you, but you create the accounts, run the
> commands, and review and understand every change before accepting it.

---

## How to read the task lists

Every task in Section 5 is tagged so you always know who acts:

- **[You]** — You do this yourself: create accounts, sign in, install software, run commands,
  make decisions, and review results. Claude Code can explain _how_, but your hands are on it.
- **[You + Claude Code]** — You work together. Claude Code explains the concept and drafts the
  code; you read it, ask questions, adjust, and only then save it. You must understand each
  change before moving on. This is deliberately not "let the agent do it."

Work through tasks in order. Check each box as you finish.

---

## 1. Project Overview

**What we're building:** a **reusable single-vendor online store platform**, codenamed **Manitou**,
reachable from:

- A **website** (customer-facing storefront plus a vendor/admin portal), and
- **Native mobile apps** (Android in Kotlin, iOS in Swift), added after the website works.

**The goal behind the goal:** learn to build a modern e-commerce stack from first principles rather
than assembling a hosted solution (Wix, Shopify). The finished repository should be **cloneable
from GitHub and adaptable** to different store types — printed T-shirts (the default build),
candles, a single-product store, a grocery store, or a broad multi-category catalog — by changing
configuration and content, not by rewriting the architecture.

**Fixed requirements:**

- One shared database so products, users, inventory, and orders are managed once and reflected everywhere.
- Support ~1,000 concurrent users.
- Payments via **Stripe**.
- Host on **AWS** (this also supports your AWS Certified Cloud Practitioner goal).
- Build order: **database → backend API → website → payments → deploy → mobile apps.**

**Scope boundaries — read these before proposing any feature:**

- **Single vendor, always.** One seller (the store owner) and many customer accounts. The vendor
  portal is an admin area gated by an `admin` role.
- **Not a marketplace.** No multiple independent sellers, no seller onboarding, no split payouts,
  no Stripe Connect. A large catalog ("Walmart-sized inventory, one owner") is a _scale_ concern —
  handled with indexing, search, and pagination — not a structural one. It does **not** imply
  multi-vendor.
- **Build one store concretely first.** The default build is the T-shirt store, built end to end
  without generalizing as you go. Configurability is proven by _actually cloning it_ for a second
  store type, not by speculating up front. The only exceptions are the deliberate seams in
  Section 1.1, which are cheap now and expensive later.

**Definitions used throughout:**

- The website and mobile apps are separate clients that all use one backend (Section 2).

---

## 1.1 Reusability Seams (deliberate, minimal)

These three seams exist so the repo can be cloned and adapted without a rewrite. They cost almost
nothing in the default T-shirt build. **Nothing beyond this list should be generalized in advance.**

| Seam                               | What it is                                                                                                                              | Why now, not later                                                                                                       |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Store configuration**            | One config source for store name, currency, locale, tax behavior, and feature flags (e.g. `variants_enabled`, `weight_pricing_enabled`) | If these values scatter across API code and React components, cloning means hunting through files instead of editing one |
| **`unit_of_measure` on products**  | `each` (default), `lb`, `kg`, `oz`, `g`                                                                                                 | A grocery store sells by weight. Without this column, that store type is a rewrite rather than a clone                   |
| **`attributes` JSONB on variants** | Free-form key/value per variant: `{"size":"L","color":"red"}` or `{"scent":"cedar","wax":"soy"}`                                        | Lets each store type define its own variant dimensions with no schema change                                             |

Everything else — the catalog, cart, checkout, order, and payment model — is already store-type
agnostic as designed in Section 6.

---

## 2. Core Architecture: One API, One Database

Your requirement — manage products and users once, everywhere — is met by one rule: **clients
never touch the database directly. Every client goes through one backend API.**

```
     ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────┐
     │  Web store   │   │ Vendor portal│   │  iOS (Swift) │   │Android(Kotlin)│
     │  (browser)   │   │  (browser)   │   │              │   │               │
     └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬────────┘
            │                  │                  │                  │
            └────────────┬─────┴──────────────────┴──────────────────┘
                         │  HTTPS / JSON (REST API)
                  ┌──────▼────────┐
                  │  Backend API  │  ← the ONLY thing that talks to the DB
                  │  (FastAPI)    │     handles auth, validation, business rules
                  └──────┬────────┘
                         │  SQL (via SQLAlchemy)
                  ┌──────▼────────┐
                  │  PostgreSQL   │  ← single source of truth
                  │  (AWS RDS)    │
                  └───────────────┘
```

Why this is the rule:

- **One place for business rules.** Pricing, stock checks, and permissions live in the API,
  not copy-pasted into four clients.
- **Security.** Database credentials never leave the server. A phone app must never hold your DB password.
- **One-time changes.** Add a product once via the API; every client sees it.
- **Easier mobile phase.** The apps later reuse the same endpoints the website already uses.

**Project-wide rule:** if a client needs data, it calls the API. Only the backend connects to PostgreSQL.

---

## 3. Technology Stack (final)

These choices are settled. Do not substitute them.

| Layer                 | Technology                                                                                          | Reason it was chosen                                                             |
| --------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Database              | **PostgreSQL**                                                                                      | Strong transactions for orders/payments; good JSON support; open source          |
| Backend API           | **Python 3.12+ with FastAPI**                                                                       | You know Python; async serves ~1k concurrent well; auto-generated API docs       |
| Python isolation      | **`venv` (built-in) + `pip` + `requirements.txt`**                                                  | Per-project packages; standard tooling; matches what the Docker image installs   |
| DB access             | **SQLAlchemy + Alembic**                                                                            | Python-to-SQL mapping plus safe, versioned schema migrations                     |
| Validation            | **Pydantic**                                                                                        | Enforces request/response shapes; ships with FastAPI                             |
| Web frontend          | **Next.js (React)**                                                                                 | You know JS/HTML/CSS; server rendering helps store SEO                           |
| Web styling           | **Tailwind CSS**, configured from shared design tokens                                              | Consistent spacing/color scale; tokens make cross-platform matching possible     |
| Design tokens         | **`design-tokens.json`** at the repo root — the single source of truth for color, type, and spacing | One definition, manually mirrored into Tailwind, Kotlin, and Swift (Section 4.3) |
| Vendor portal         | **The same Next.js app**, at `/admin`, gated by an `admin` role                                     | One codebase, one API, one auth system, one design system                        |
| Android               | **Kotlin (native)**                                                                                 | You already know it                                                              |
| iOS                   | **Swift (native)**                                                                                  | You already know it                                                              |
| Payments              | **Stripe**                                                                                          | Strong web + mobile SDKs; handles the PCI burden                                 |
| Auth                  | **JWT tokens** issued by the API, passwords hashed with **bcrypt**                                  | Identical flow for web and mobile                                                |
| Containerization      | **Docker**                                                                                          | Same environment locally and on AWS                                              |
| CI/CD                 | **GitHub Actions**                                                                                  | You know Git; automate tests and deploys                                         |
| API hosting           | **AWS App Runner**                                                                                  | Simplest managed way to run the container (upgrade path defined in Section 7)    |
| Web hosting           | **AWS Amplify Hosting**                                                                             | Runs Next.js with built-in CI/CD from your Git repo                              |
| Database hosting      | **AWS RDS (PostgreSQL)**                                                                            | Managed Postgres with backups and failover                                       |
| Images / static files | **AWS S3 + CloudFront**                                                                             | Store product images; serve them via CDN                                         |
| DNS + HTTPS           | **AWS Route 53 + ACM**                                                                              | Domain and free TLS certificates                                                 |
| Secrets               | **AWS Secrets Manager**                                                                             | DB password and Stripe keys, kept out of Git                                     |
| Monitoring            | **AWS CloudWatch**                                                                                  | Logs, metrics, alarms                                                            |

---

## 4. Repository Structure and Project Conventions

One repository holds everything so the whole system is discoverable:

```
Manitou/
├── CLAUDE.md              # concise guidance for Claude Code
├── PROJECT_PLAN.md        # this file — the master plan
├── README.md              # human-facing setup and run instructions
├── design-tokens.json     # single source of truth for color, type, spacing (Section 4.3)
├── .gitignore             # excludes .venv/, __pycache__/, .env, node_modules/
├── docker-compose.yml     # local PostgreSQL for development
├── backend/               # FastAPI app
│   ├── .venv/             # virtual environment — NEVER committed to Git
│   ├── .env.example       # template of required env vars (safe to commit)
│   ├── .env               # real local secrets — NEVER committed to Git
│   ├── app/
│   │   ├── main.py
│   │   ├── models/        # SQLAlchemy tables
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── routers/       # API endpoints (products, orders, auth, ...)
│   │   ├── services/      # business logic (checkout, inventory, payments)
│   │   └── db.py          # engine, session, connection pool
│   ├── alembic/           # migrations
│   ├── tests/
│   └── requirements.txt
├── web/                   # Next.js storefront + vendor portal
│   ├── app/               # customer pages
│   ├── app/admin/         # vendor portal (role-gated)
│   └── ...
├── mobile-android/        # Kotlin app (Phase 7)
├── mobile-ios/            # Swift app (Phase 7)
└── infra/                 # AWS notes and deployment scripts
```

---

## 4.1 Local Python Environment (venv) and Its Relationship to Docker

Every Python dependency for this project lives in a **virtual environment**, never in your system
Python. Without one, `pip install` writes packages globally, projects with different version
requirements collide, and your dependency list can't be reproduced reliably.

**The venv and Docker are both used, and they do different jobs:**

|                | Virtual environment (`.venv`)                                                   | Docker                                                |
| -------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Isolates       | Python packages for this project                                                | The entire runtime (OS, Python, system libraries)     |
| Used for       | Writing code: editor autocomplete, `pytest`, `alembic`, running the API locally | Running PostgreSQL locally; packaging the API for AWS |
| Lives          | On your machine, in `backend/.venv/`                                            | In containers                                         |
| Shipped to AWS | No                                                                              | Yes                                                   |

**Day-to-day development setup:** PostgreSQL runs in Docker; the FastAPI app runs on your host
inside the venv. You get fast hot-reload and easy debugging while developing, and Phase 6 packages
the same app into a Docker image for deployment. Both the venv and the Docker image install from
the same `requirements.txt`, so they stay in sync.

Your editor also needs the venv to be selected as its interpreter — otherwise it can't see FastAPI
or SQLAlchemy and you lose autocomplete and type checking.

**Rules for this project:**

- Create the venv once, in `backend/.venv`, and **activate it in every terminal session** before
  running any `pip`, `python`, `alembic`, `uvicorn`, or `pytest` command.
- Never `pip install` without the venv active. If you're unsure whether it's active, check that
  your shell prompt shows the environment name.
- Every new package gets recorded in `requirements.txt` and committed. The venv folder itself is
  **never** committed.
- The Node/Next.js side needs no equivalent step — `node_modules/` is already per-project isolation.
  Just keep it out of Git.

**Python version managers (pyenv):** not part of this project's required tooling. `pyenv` manages
_which Python version_ is installed, a separate layer from the venv (_which packages_) and Docker
(_which whole runtime ships_). Decision rule: run `python3 --version` in Phase 0 step 2. If it
reports 3.12 or higher, skip pyenv entirely. If it reports lower, install pyenv (macOS/Linux) or
install 3.12 from python.org (Windows) rather than modifying your system Python — on macOS
especially, other OS tooling depends on the bundled version. Either way, the venv is still created
on top of whichever interpreter you end up with, and the Dockerfile pins the production version
independently in Phase 6.

---

## 4.2 Configuration and Secrets: `.env` vs `.env.example`

### The principle

Configuration lives **outside** the code. The same application code runs on your laptop, on a
teammate's laptop, and on AWS — what changes between them is only the configuration values fed in
at startup: which database to connect to, which Stripe keys to use, what the JWT signing secret is.

This is why credentials are never written into Python files. If a Stripe key is hardcoded in
`main.py`, it's in your Git history forever, visible to anyone with repo access, and you'd have to
change code to move between test and live payments.

The backend reads all of it through environment variables. In Python that means `os.environ`
(here, via Pydantic's settings support), and the code is **identical** in every environment. Only
the source of the values differs.

### The two files, and why both exist

|                   | `.env`                            | `.env.example`                         |
| ----------------- | --------------------------------- | -------------------------------------- |
| Contains          | Real working values               | Variable names with placeholder values |
| Committed to Git? | **Never**                         | **Always**                             |
| Purpose           | Makes the app run on your machine | Documents what the app requires        |
| Who has it        | Each developer creates their own  | Shared by everyone via the repo        |

`.env` holds live secrets, so it stays out of Git. But that creates a problem: someone cloning the
repo — including future-you on a new machine — has no way to know the app needs eight specific
variables. They'd start the app, get a cryptic connection error, and have to reverse-engineer the
requirements from the source code.

`.env.example` solves exactly that. It's the committed, safe-to-read **contract** stating what
configuration the application requires. It carries the variable _names_ and harmless placeholders,
never real secrets.

Example of the shape:

```
# .env.example  — committed, no real values
DATABASE_URL=postgresql://manitou:password@localhost:5432/manitou
JWT_SECRET=replace-with-a-long-random-string
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx
S3_BUCKET_NAME=your-bucket-name
```

### How a developer uses it

1. Clone the repo.
2. Copy the template: `cp backend/.env.example backend/.env`
3. Fill in real values — the local Docker database URL, their own Stripe test keys, a locally
   generated JWT secret.
4. Run the app. Because `.env` is git-ignored, their secrets never leave their machine.

Each developer's `.env` is personal and different. The `.env.example` they all share is identical.

### How the live server differs

**There is no `.env` file in production.** This is the part that surprises people.

On AWS, values are injected into the container's environment by the platform. You store the real
secrets in **AWS Secrets Manager**, and **App Runner** supplies them to the running container as
environment variables at startup. Your code calls `os.environ` exactly as it does locally and never
knows the difference — that's the whole point of the pattern.

| Environment         | Where values come from                    | Where secrets are stored          |
| ------------------- | ----------------------------------------- | --------------------------------- |
| Local development   | `.env` file, loaded at startup            | On your machine only, git-ignored |
| CI (GitHub Actions) | Repository secrets injected into the job  | GitHub encrypted secrets          |
| Production (AWS)    | Injected into the container by App Runner | **AWS Secrets Manager**           |

So `.env` is a **local development convenience**, not a deployment mechanism. Shipping a `.env`
file to a server — or baking one into a Docker image — is a mistake: the image is stored in a
registry, and anyone who can pull it can read the secrets inside.

### Values must differ per environment

Never reuse the same secret across environments. Concretely:

- **Stripe:** local and CI use **test** keys (`sk_test_…`); production uses **live** keys. Using
  live keys locally means real charges during development.
- **Database:** local points at the Docker container; production points at RDS.
- **JWT secret:** a different random string in each environment, so a leaked development secret
  can't be used to forge tokens against production.

### Rules for this project

- Never commit `.env`. Confirm it's in `.gitignore` before it's ever created (Phase 0 step 5).
- Never put a real secret in `.env.example` — placeholders only.
- **Whenever you add a new variable to `.env`, add it to `.env.example` in the same commit.** This
  is the rule most often forgotten, and when it slips, the next person's setup breaks with no
  explanation of what's missing.
- Never log or print environment variable values — they end up in CloudWatch in plain text.
- If a secret is ever committed by accident, treat it as compromised and rotate it. Deleting the
  file in a later commit does not remove it from Git history.

---

## 4.3 Design System and Cross-Platform UI Consistency

### Why this needs to be explicit

The website, the Android app, and the iOS app share **no UI code whatsoever**. Next.js renders
HTML/CSS, Android renders Jetpack Compose, iOS renders SwiftUI. They share the API and the
database — nothing visual. Visual consistency therefore does **not** happen by itself: unless the
same values are deliberately defined once and carried into each platform, the three clients will
drift into three different-looking products.

That's what `design-tokens.json` is for.

### Design tokens: the single source of truth

`design-tokens.json` at the repo root defines the brand's raw visual values. It is plain data, so
every platform can read or mirror it:

- **Color** — 4–6 named values: primary, secondary/accent, background, surface, text, plus
  semantic states (success, warning, error). Name them by role (`color.primary`), never by
  appearance (`color.blue`), so a rebrand changes one value instead of every reference.
- **Typography** — a display face and a body face, plus a fixed type scale (e.g., xs/sm/base/lg/
  xl/2xl) with defined weights.
- **Spacing** — one numeric scale (4, 8, 12, 16, 24, 32, 48…). Every margin and padding across all
  three platforms comes from this scale, never an arbitrary number.
- **Radii, borders, shadows** — the values that quietly define whether a product feels soft or sharp.

How each platform consumes it:

| Platform         | How tokens are applied                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------ |
| Web (Next.js)    | Imported into `tailwind.config.js` so Tailwind's palette, type scale, and spacing come from the tokens |
| Android (Kotlin) | Mirrored into a Compose `Theme.kt` — `MaterialTheme` colors, typography, and shapes                    |
| iOS (Swift)      | Mirrored into a SwiftUI theme file — `Color` and `Font` extensions                                     |

Mobile mirroring is manual — you copy the values into the native theme file. That's acceptable
because tokens change rarely, and it keeps the tooling simple. The rule is that `design-tokens.json`
is authoritative: **if a value changes, it changes there first, then propagates.** Never hardcode a
hex value or a font size inside a component on any platform.

### Storefront and vendor portal share everything

The vendor portal is **not a separate application**. It is the same Next.js project, served under
`/admin`, using the same components, the same Tailwind config, and the same tokens. What differs is
only the route and the role gate. This is the reason Phase 4 names no new framework — there is
nothing new to choose.

Practically, this means Phase 3 should build shared UI primitives (button, input, card, table,
modal, form field) that Phase 4 reuses. The portal's density and priorities differ — it's dashboards
and data tables rather than product photography — but it is recognizably the same product.

### Consistency across mobile means _brand_, not pixel-cloning

An important distinction, and a place where "make the apps look like the website" can be taken too
far: **do not reproduce the website's layout in the native apps.** Users expect platform
conventions, and an app that ignores them feels wrong and dated:

- iOS expects bottom tab bars, swipe-back navigation, and system share sheets.
- Android expects Material navigation patterns and hardware back-button behavior.
- The web expects a persistent top nav, hover states, and browser-native controls.

So the target is: **identical brand, native feel.**

| Keep identical across all platforms        | Let each platform follow its own conventions        |
| ------------------------------------------ | --------------------------------------------------- |
| Colors and their roles                     | Navigation structure and patterns                   |
| Typefaces, hierarchy, and relative scale   | Native controls (pickers, date selectors, switches) |
| Spacing rhythm and density                 | Gestures and transitions                            |
| Logo, iconography style, imagery treatment | Layout for the screen size and input method         |
| Terminology and button wording             | Platform-standard system components                 |
| Product photography treatment              | System share, permission, and payment sheets        |

Someone moving from your website to your iOS app should immediately recognize the same store —
without the app feeling like a website in a wrapper.

### Interface writing counts as design

Wording is part of the design system, not an afterthought. Keep one vocabulary across all clients:
if the web button says "Place order," the mobile button says "Place order," not "Buy now." Name
actions by what they do (`Save changes`, not `Submit`), and keep a term consistent through an entire
flow — a "Publish" button should produce a "Published" confirmation. Errors state what went wrong
and how to fix it. Empty states invite an action rather than just reporting emptiness.

### The quality floor (non-negotiable on every screen)

- Responsive down to mobile browser widths.
- Visible keyboard focus states, and all interactive elements reachable by keyboard.
- Sufficient color contrast for body text.
- Reduced-motion preferences respected.
- Images carry meaningful alt text (`product_images.alt_text` exists in the schema for this reason).

### When the design gets defined

Design tokens are decided at the **start of Phase 3**, before any page is built. Retrofitting a
design system after screens exist means rewriting them. The tokens then stay fixed through Phases 4
and 7 unless deliberately revised.

---

## 5. Build Phases (with tasks)

Do the phases in order. Do not start mobile (Phase 7) until the website works end to end.

### Phase 0 — Foundations

1. **[You]** Install **Git**. Sign in to (or create) your **GitHub** account. Create a new
   repository named `Manitou`, then clone it to your machine.
2. **[You]** Install the toolchain: **Python 3.12+**, **Node.js LTS**, **Docker Desktop**, a
   PostgreSQL client (e.g., **psql** or **TablePlus/pgAdmin**), your editor, and **Claude Code**.
   Verify each with its `--version` command.
3. **[You]** Place `PROJECT_PLAN.md` and `CLAUDE.md` in the repo root. Commit and push them.
4. **[You + Claude Code]** Create the folder structure from Section 4. Have Claude Code explain
   what each folder is for as you make it.
5. **[You + Claude Code]** Create `.gitignore` covering `.venv/`, `__pycache__/`, `.env`,
   `node_modules/`, and OS junk files. Do this **before creating the venv or installing any project
   dependencies** (steps 6–8), since those write files into the repo folder. The step 2 toolchain
   installs to system locations outside the repo, so it isn't affected by this ordering.
6. **[You]** Create the virtual environment in `backend/.venv` and activate it. Confirm it's active
   (your prompt shows the environment name) and that `python --version` reports 3.12+.
   Read Section 4.1 first so you understand what the venv is doing.
7. **[You]** Point your editor at the venv as its Python interpreter, so autocomplete and type
   hints work.
8. **[You + Claude Code]** With the venv active, install FastAPI, Uvicorn, SQLAlchemy, Alembic,
   Pydantic, and the Postgres driver. Record them in `requirements.txt` and commit it.
9. **[You + Claude Code]** Write `docker-compose.yml` to run local PostgreSQL. Start it, then
   confirm the database is running by connecting with your Postgres client.
10. **[You + Claude Code]** Create `.env.example` (committed) and your real `.env` (ignored) with
    the local database connection string.
11. **[You + Claude Code]** Initialize the FastAPI app with a single health-check endpoint. Run it
    with the venv active and open it in your browser to confirm it responds.
12. **[You + Claude Code]** Connect the API to the local database and confirm the connection succeeds.
13. **[You + Claude Code]** Write a short `README.md`: what the project is and how to set it up and
    run it locally (start Docker, activate the venv, run the API).
14. **[You]** Commit and push. From here on, commit after each working step to build the habit.

### Phase 1 — Database (details in Section 6)

1. **[You + Claude Code]** Sketch the ER diagram from Section 6.2 yourself; have Claude Code
   review it and explain any correction. This builds your data-modeling intuition.
2. **[You + Claude Code]** Write the SQLAlchemy models for every table in Section 6.3.
3. **[You + Claude Code]** Set up Alembic, generate the first migration, and apply it.
4. **[You]** Open your Postgres client and inspect the created tables so you see the real result.
5. **[You + Claude Code]** Add the constraints and indexes from Sections 6.5–6.6 in a new migration.
6. **[You + Claude Code]** Write the seed script from Section 6.9 (sample categories, products,
   and one `admin` user).
7. **[You]** Run the seed script, then write and run a few `SELECT` queries yourself to get
   comfortable with SQL.

### Phase 2 — Backend API

1. **[You + Claude Code]** Auth: register, login, JWT issuing, bcrypt password hashing, and a
   role check (`customer` vs `admin`).
2. **[You + Claude Code]** Product and category endpoints (list, detail, search/filter).
3. **[You + Claude Code]** Cart endpoints (add, update quantity, remove, view).
4. **[You + Claude Code]** Order endpoints (create order, order history, order detail).
5. **[You + Claude Code]** Implement checkout as a single database transaction that also
   decrements inventory safely under concurrency (Section 6.7). Flag this to Claude Code explicitly.
6. **[You + Claude Code]** Admin endpoints (create/update/delete products, manage inventory,
   view all orders), all gated to the `admin` role.
7. **[You]** Open the auto-generated API docs at `/docs` and exercise the endpoints by hand.
8. **[You + Claude Code]** Write tests for the critical paths: auth, checkout, inventory.

### Phase 3 — Web Storefront

**Framework: Next.js (React) with Tailwind CSS.**

1. **[You]** Decide the brand direction before writing UI: palette, the two typefaces, and the
   overall feel of the store. This is your call as the owner — Claude Code can present options and
   critique, but the aesthetic decision is yours.
2. **[You + Claude Code]** Create `design-tokens.json` (Section 4.3) with color, typography,
   spacing, radii, and shadows.
3. **[You + Claude Code]** Create the store configuration source (Section 1.1): store name,
   currency, locale, tax behavior, and feature flags such as `variants_enabled` and
   `weight_pricing_enabled`. Every store-specific value the UI needs comes from here — never
   hardcoded in a component. This file plus `design-tokens.json` should be the only things a
   cloned store must edit.
4. **[You + Claude Code]** Create the Next.js project and wire `tailwind.config.js` to read from
   `design-tokens.json` so nothing is hardcoded.
5. **[You + Claude Code]** Build the shared UI primitives Phase 4 will reuse: button, input, form
   field, card, table, modal, and toast.
6. **[You + Claude Code]** Build the pages: catalog/home, category, product detail, cart,
   checkout, account, and order history.
7. **[You + Claude Code]** Implement the auth flow (login/register) and store the JWT securely.
8. **[You]** Test the storefront in a browser on both a PC and a phone to confirm it's responsive.
9. **[You]** Check the quality floor from Section 4.3: keyboard focus visible, contrast adequate,
   alt text present.

### Phase 4 — Vendor Portal

**Framework: the same Next.js + Tailwind application built in Phase 3 — no new framework, no
separate project.** The portal lives at the `/admin` route inside `web/`, reuses the Phase 3 UI
primitives and `design-tokens.json`, and calls the same API with the same JWT auth.

1. **[You + Claude Code]** Build the `/admin` section, with access gated by the `admin` role in the JWT.
2. **[You + Claude Code]** Product management (create/edit/delete, upload images — wired to S3 in Phase 6).
3. **[You + Claude Code]** Inventory management (stock levels and reorder alerts).
4. **[You + Claude Code]** Order dashboard (view orders and advance status: paid → shipped → delivered).
5. **[You + Claude Code]** A simple sales/inventory summary view.
6. **[You + Claude Code]** Reuse the Phase 3 primitives throughout. Admin screens are denser and
   more table-heavy than the storefront, but must stay visibly the same product — if a new
   component is needed, build it from the tokens and add it to the shared set.

### Phase 5 — Payments (Stripe)

1. **[You]** Create a **Stripe** account. Copy your **test-mode** API keys. Store them as
   environment variables — never commit them to Git.
2. **[You + Claude Code]** Backend: create a Stripe PaymentIntent when an order is placed.
3. **[You + Claude Code]** Web checkout: collect payment with Stripe's SDK so card data goes
   straight to Stripe and never touches your server.
4. **[You + Claude Code]** Add a Stripe webhook endpoint that confirms payment and marks the order paid.
5. **[You + Claude Code]** Record payment references in the `payments` table (Section 6.3).
6. **[You]** Run the full checkout using Stripe's test cards and confirm the order is marked paid.

### Phase 6 — AWS Deployment

1. **[You]** Create an **AWS account** at aws.amazon.com. A payment method is required, but you'll
   stay in the free tier where possible.
2. **[You]** Immediately set a **billing budget with an alert** (start around $10) so any charge
   warns you. Ask Claude Code for the exact current console steps.
3. **[You]** Create an **IAM user** for your daily work and stop using the root account for
   everyday tasks. (This is a security best practice and appears on the Cloud Practitioner exam.)
4. **[You + Claude Code]** Provision **RDS PostgreSQL**. Keep it private so only the API reaches it.
5. **[You + Claude Code]** Point Alembic at RDS and apply your migrations there, producing the
   same schema you have locally.
6. **[You + Claude Code]** Containerize the API with Docker and deploy it to **App Runner**.
7. **[You + Claude Code]** Deploy the web app to **Amplify Hosting**, connected to your Git repo.
8. **[You + Claude Code]** Set up **S3 + CloudFront** for product images and switch uploads to use them.
9. **[You]** Register a domain in **Route 53** and issue an **ACM** certificate for HTTPS.
10. **[You + Claude Code]** Move secrets into **Secrets Manager** and set up **CloudWatch** logs and alarms.

### Phase 7 — Mobile Apps

**Frameworks: Kotlin with Jetpack Compose (Android), Swift with SwiftUI (iOS).** Both consume the
existing API and mirror `design-tokens.json` per Section 4.3.

1. **[You + Claude Code]** Android: translate `design-tokens.json` into a Compose `Theme.kt`
   (colors, typography, shapes) **before** building screens.
2. **[You + Claude Code]** Android (Kotlin): auth, catalog, product detail, cart, checkout with
   the Stripe Android SDK, and order history — all against the existing API.
3. **[You + Claude Code]** iOS: translate the same tokens into a SwiftUI theme file, then build the
   same feature set with the Stripe iOS SDK.
4. **[You + Claude Code]** Use each platform's native navigation and controls (Section 4.3) — match
   the brand, not the website's layout.
5. **[You]** Open the website and both apps side by side. Confirm they read as the same store:
   same colors, type hierarchy, spacing rhythm, and button wording.
6. **[You]** Test both apps end to end against your deployed backend.

### Phase 8 — Hardening and Launch

1. **[You + Claude Code]** Load test toward ~1,000 concurrent users. Adjust the RDS instance size
   and connection pool based on results.
2. **[You + Claude Code]** Add rate limiting, review input validation, and do a security pass.
3. **[You]** Verify backups by performing a test restore. An untested backup is not a backup.
4. **[You + Claude Code]** Confirm logging, alerts, and error tracking are in place, then launch.

---

## 6. Database Implementation (Detailed)

This section is deep because the database is the foundation and because you asked to go beyond
the basics here. Read it as a short tutorial plus a concrete schema.

### 6.1 Approach

Design in this order:

1. **List the real-world things** the store cares about (customers, products, orders…). These become **tables**.
2. **Describe how they relate** (an order _has many_ items; a product _belongs to_ a category).
3. **Turn that into a schema** — tables, columns, data types, keys.
4. **Refine** for correctness (normalization) and speed (indexes).
5. **Version it** with migrations so changes are safe and repeatable.

### 6.2 Entities and Relationships

- A **user** places many **orders** and has many **addresses**.
- A **category** contains many **products**; a product belongs to one category.
- A **product** has many **variants** (e.g., "Large / Red") and many **images**.
- Each **variant** has one **inventory** record.
- A **cart** belongs to a user and contains many **cart items**.
- An **order** contains many **order items** and has zero or more **payments**.

"Has many / belongs to" describes **cardinality** — one-to-one, one-to-many, or many-to-many.
Most relationships above are one-to-many. Cart items and order items are the classic pattern for
turning a many-to-many (products ↔ orders) into two one-to-many links through a join table.

**Why an order has many payments, not one.** The intuitive model is one payment per order, but that
assumes payment succeeds on the first attempt. A declined card followed by a successful retry is two
records; a refund is a third; SCA/3-D Secure flows can produce more than one PaymentIntent for a
single checkout. Financial records are **append-only** — you never overwrite or delete a payment
row, you add another one, so an order's payment history is a ledger rather than a single value.
This is why `payments.order_id` carries no unique constraint (contrast `inventory.variant_id`,
which does — Section 6.3). It also means split-tender payment (two cards, or a card plus a gift
card) could be added later as a *feature* with no schema change — but it is deliberately **not**
part of v1 (Section 12), because it pulls in partial-payment order states, proportional refunds,
and reconciliation rules.

### 6.3 Core Schema

Columns marked **PK** are primary keys (the unique row identifier); **FK** are foreign keys (a
reference to another table's PK).

**users**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| email | text | unique, not null |
| password_hash | text | bcrypt hash — never store raw passwords |
| full_name | text | |
| phone | text | nullable |
| role | text | `'customer'` or `'admin'` (the store owner is admin) |
| created_at | timestamptz | default now() |

**addresses**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| user_id | bigint | **FK** → users.id |
| line1, line2, city, state, postal_code, country | text | |
| type | text | `'shipping'` or `'billing'` |
| is_default | boolean | |

**categories**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| name | text | not null |
| slug | text | unique — URL-friendly name |
| parent_id | bigint | **FK** → categories.id, nullable (subcategories) |

**products**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| name | text | not null |
| slug | text | unique |
| description | text | |
| category_id | bigint | **FK** → categories.id |
| base_price | numeric(10,2) | use `numeric`, never `float`, for money |
| unit_of_measure | text | `'each'` (default), `'lb'`, `'kg'`, `'oz'`, `'g'` — see Section 1.1 |
| is_active | boolean | hide products without deleting them |
| created_at | timestamptz | |

**product_variants**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| product_id | bigint | **FK** → products.id |
| sku | text | unique — stock keeping unit |
| variant_name | text | display label, e.g., "Large / Red" |
| attributes | jsonb | structured variant dimensions, e.g. `{"size":"L","color":"red"}` — see Section 1.1 |
| price_override | numeric(10,2) | nullable; falls back to product.base_price |

**product_images**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| product_id | bigint | **FK** → products.id |
| url | text | points to an S3 object |
| alt_text | text | |
| is_primary | boolean | |

**inventory**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| variant_id | bigint | **FK** → product_variants.id, unique (one row per variant) |
| quantity_available | integer | |
| quantity_reserved | integer | held during checkout |
| reorder_level | integer | alert threshold for the vendor |

**carts** and **cart_items**
| carts | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| user_id | bigint | **FK** → users.id |

| cart_items | Type    | Notes                        |
| ---------- | ------- | ---------------------------- |
| id         | bigint  | **PK**                       |
| cart_id    | bigint  | **FK** → carts.id            |
| variant_id | bigint  | **FK** → product_variants.id |
| quantity   | integer |                              |

**orders**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| user_id | bigint | **FK** → users.id |
| status | text | `pending`, `paid`, `shipped`, `delivered`, `cancelled`, `refunded` |
| subtotal, tax, shipping_cost, total | numeric(10,2) | |
| shipping_address_id, billing_address_id | bigint | **FK** → addresses.id |
| created_at | timestamptz | |

**order_items**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| order_id | bigint | **FK** → orders.id |
| variant_id | bigint | **FK** → product_variants.id |
| product_name_snapshot | text | copy the name at purchase time |
| unit_price_snapshot | numeric(10,2) | copy the price at purchase time |
| quantity | integer | |

**payments**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| order_id | bigint | **FK** → orders.id |
| stripe_payment_intent_id | text | reference into Stripe |
| amount | numeric(10,2) | |
| currency | text | e.g., `'usd'` |
| status | text | mirrors Stripe's status |
| created_at | timestamptz | |

Important detail: **order_items snapshot the name and price** at purchase time. If you later
change a product's price, past orders must still show what the customer actually paid. Never rely
on the live product row for historical orders.

### 6.4 Normalization

Normalization means storing each fact once so it can't disagree with itself. Aim for **third
normal form (3NF)**: don't repeat data that belongs elsewhere (store `category_id` on a product,
not the category name on every product), and every column should depend on the table's primary
key and nothing else. The schema above is in 3NF. There are two deliberate exceptions, both standard:

1. **Price/name snapshots on `order_items`** — intentional denormalization for historical accuracy.
2. **`attributes` JSONB on `product_variants`** — see below.

**Why variant attributes are JSONB rather than columns.** A strictly normalized design would use an
`attribute` / `attribute_value` table pair, or hardcoded `size` and `color` columns. Hardcoded
columns break the moment a store sells candles (scent, wax type) instead of shirts. Full attribute
tables are correct but add three joins to every product query for a store that only ever has two
dimensions.

JSONB is the pragmatic middle: each variant carries its own dimensions as data, so a cloned store
defines new ones with no migration. PostgreSQL indexes JSONB well (GIN indexes) if you later need
to filter by attribute.

The tradeoff to accept knowingly: the database can't enforce that every variant of a product uses
the same keys, so `{"size":"L"}` and `{"Size":"Large"}` could coexist. **The API is responsible for
that consistency** — validate attribute keys in the service layer, and keep the canonical list of
dimensions per store in the store configuration (Section 1.1). Use `variant_name` for display and
`attributes` for logic and filtering.

### 6.5 Keys, Relationships, and Constraints

- A **primary key** (`id`) on every table.
- **Foreign keys** so references are always valid.
- **Unique constraints** on `users.email`, `categories.slug`, `products.slug`, `product_variants.sku`.
- **Not-null constraints** on anything required (email, prices, quantities).
- Let the database enforce these; constraints are your safety net even if the app has a bug.

### 6.6 Indexes

An index speeds up lookups at a small cost to writes. Add indexes on columns you filter or join by:

- `users.email` (unique — already indexed)
- `products.category_id`, `products.slug`
- `product_variants.product_id`, `product_variants.sku`
- `inventory.variant_id`
- `orders.user_id`, `orders.status`
- `order_items.order_id`
- `cart_items.cart_id`
- `payments.order_id`, `payments.stripe_payment_intent_id`

Rule of thumb: if a query filters with `WHERE something = ...` or joins `ON something`, that
column is a candidate for an index.

### 6.7 Transactions and Concurrency (checkout)

Placing an order touches several tables at once: create the order, create order items, decrement
inventory, record the payment. If any step fails, **none** should apply. Wrap the whole checkout
in a **database transaction** so all steps commit together or roll back together (the "atomicity"
in ACID).

Concurrency matters: with ~1,000 users, two people may buy the last item at the same moment.
Protect the inventory decrement so stock can't go negative — either a row lock
(`SELECT ... FOR UPDATE`) inside the transaction, or a conditional update that only succeeds when
enough stock remains. Implement this in `services/checkout` and call it out to Claude Code so it
is not overlooked.

### 6.8 Migrations

A migration is a versioned, repeatable schema change. Use **Alembic**: every change (new table,
column, or index) becomes a migration file committed to Git, applied identically to local and RDS,
and reversible if something goes wrong. Never edit the production database by hand — always through
a migration.

### 6.9 Seeding

Write a script that fills a fresh database with a few categories, sample products and variants
with stock, and one **admin** user (the store owner) so you can log into the vendor portal
immediately. This makes local development and testing repeatable.

Seed the **T-shirt store** (the default build): a couple of categories, products with
`unit_of_measure = 'each'`, and variants whose `attributes` carry `{"size": ..., "color": ...}`.
Include at least one product with no variants, so the "single item store" path is exercised from
day one rather than discovered later.

### 6.10 Backups and Recovery

Locally, know how to dump and restore with `pg_dump` / `pg_restore`. On RDS, enable **automated
backups** and **point-in-time recovery**, and take a manual snapshot before risky changes. Test a
restore at least once before launch — an untested backup isn't a backup.

### 6.11 Local vs. AWS RDS

Develop against local PostgreSQL via Docker, then point the same app at **RDS PostgreSQL** in
production by swapping the connection string. Because you use migrations, the schema is identical
in both places. For ~1,000 concurrent users, use **connection pooling** (SQLAlchemy's pool, plus
**RDS Proxy** in front of the database) so you don't exhaust connections.

---

## 7. AWS Hosting Details

| Need                  | Service              | Notes                                                        |
| --------------------- | -------------------- | ------------------------------------------------------------ |
| Database              | **RDS (PostgreSQL)** | Managed Postgres; enable backups; add Multi-AZ before launch |
| API hosting           | **App Runner**       | Runs your container with minimal setup                       |
| Web hosting           | **Amplify Hosting**  | Runs Next.js with CI/CD from your Git repo                   |
| Images / static files | **S3 + CloudFront**  | Store product images in S3, serve via the CDN                |
| DNS + HTTPS           | **Route 53 + ACM**   | Domain plus free TLS certificates                            |
| Secrets               | **Secrets Manager**  | DB password, Stripe keys — out of Git                        |
| Permissions           | **IAM**              | Least-privilege roles; a dedicated user for daily work       |
| Networking            | **VPC**              | Keep RDS private; only the API reaches it                    |
| Monitoring            | **CloudWatch**       | Logs, metrics, alarms                                        |

**Defined upgrade path:** deploy the API on **App Runner**. If the Phase 8 load test shows you
need finer control over scaling or networking, migrate the same Docker container to **ECS Fargate**.
Do not add this complexity earlier.

---

## 8. Authentication and Security

- Hash passwords with **bcrypt**; never store or log raw passwords.
- Issue **JWT** access tokens on login; clients send them on each request. This is identical for
  web and mobile.
- Include the user's **role** in the token so the vendor portal can require `admin`.
- Serve everything over **HTTPS**.
- Keep all secrets out of Git (environment variables locally, Secrets Manager on AWS).
- Validate every input at the API boundary with Pydantic.
- Let Stripe handle card data; your servers never see or store card numbers.

---

## 9. Payments (Stripe)

- Use Stripe's **PaymentIntents** flow: the backend creates an intent, the client confirms with
  Stripe's SDK, and a **webhook** tells your backend the payment succeeded.
- Store only Stripe **reference IDs** in the `payments` table, never card data.
- Start in **test mode** with Stripe's test cards; switch to live keys only near launch.
- The same model extends to Apple Pay / Google Pay later through Stripe's mobile SDKs.

---

## 10. Testing and QA

- Backend: unit tests for services (checkout, inventory) and integration tests for endpoints.
- Prioritize the money-and-stock paths — that's where bugs hurt most.
- Load test toward ~1,000 concurrent users before launch and tune RDS size and pool settings.

---

## 11. Support for Your AWS Cloud Practitioner Goal

The exam is broad and conceptual. Building on AWS gives you hands-on context for its topics:

- **RDS** → managed databases, backups, Multi-AZ.
- **S3 + CloudFront** → object storage and content delivery.
- **App Runner / ECS / EC2** → compute options and the shared-responsibility model.
- **IAM** → identity, roles, least privilege.
- **VPC** → basic networking and isolation.
- **CloudWatch** → monitoring.
- **Billing** → set a budget alert early and watch each service's cost.

Pair the build with the official exam guide; you'll recognize the core services from using them here.

---

## 12. First Launch Scope (v1)

Version 1 — the target for your first live store — is exactly this:

1. The database from Section 6 (users, products, variants, inventory, orders, order_items, payments).
2. API: auth, product listing/detail, cart, checkout, and admin CRUD.
3. Web storefront plus the vendor portal.
4. Stripe test-mode checkout.
5. Deployed on AWS.

After v1 launches, add reviews, richer search, sales reporting, and the mobile apps (Phase 7).

---

## 13. Glossary

- **API** — the backend service clients call to read/write data.
- **ORM** — library that maps database rows to code objects (SQLAlchemy).
- **Migration** — a versioned, repeatable schema change (Alembic).
- **Primary key (PK)** — column that uniquely identifies a row.
- **Foreign key (FK)** — column referencing another table's PK.
- **Index** — structure that speeds up lookups on a column.
- **Transaction** — a group of DB operations that all succeed or all fail together.
- **Normalization** — organizing data so each fact is stored once.
- **JWT** — a signed token proving who a user is on each request.
- **JOIN** — combining rows from related tables in a query.
- **SKU** — stock keeping unit; a unique code per sellable variant.
- **IAM** — AWS Identity and Access Management; controls who can do what.
- **VPC** — a private network in AWS that isolates your resources.
