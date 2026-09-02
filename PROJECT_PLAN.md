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
- Support the concurrency the business actually warrants — **sized via the methodology in Section
  10.1**, not assumed. Design and Phase 7 load-test against the early-launch tier for whatever
  store this becomes; treat higher figures (including the commonly-assumed "~1,000 concurrent") as
  earned scale milestones, not day-one requirements.
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

These four seams exist so the repo can be cloned and adapted without a rewrite. They cost almost
nothing in the default T-shirt build. **Nothing beyond this list should be generalized in advance.**

The fourth was added deliberately, after the first three, when planning Phase 5.5 — recorded here
rather than smuggled in. It passes the same test as the others: a `method` column costs nothing in
a store that ships by carrier, while retrofitting a second delivery-confirmation path onto a schema
with no shipment table is a migration plus a rewrite of every fulfilment code path. It is the same
argument `unit_of_measure` already won, for the same clone.

| Seam                                                 | What it is                                                                                                                                           | Why now, not later                                                                                                                                                                                                          |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Store configuration**                              | One config source for store name, currency, locale, tax behavior, and feature flags (e.g. `variants_enabled`, `weight_pricing_enabled`)              | If these values scatter across API code and React components, cloning means hunting through files instead of editing one                                                                                                    |
| **`unit_of_measure` on products**                    | `each` (default), `lb`, `kg`, `oz`, `g`                                                                                                              | A grocery store sells by weight. Without this column, that store type is a rewrite rather than a clone                                                                                                                      |
| **`attributes` JSONB on variants**                   | Free-form key/value per variant: `{"size":"L","color":"red"}` or `{"scent":"cedar","wax":"soy"}`                                                     | Lets each store type define its own variant dimensions with no schema change                                                                                                                                                |
| **`fulfilment.method` + event `source`** (Phase 5.5) | `carrier` (default), `courier`, `pickup` in store config; every delivery event records what confirmed it — `admin`, `carrier`, `courier`, `customer` | A store running its own delivery staff confirms from an app, not a carrier's API. Without these columns that store is a rewrite rather than a clone, and the evidence quality of a delivery is unrecoverable after the fact |

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
                         ▼
                  ┌───────────────┐
                  │  Backend API  │  ← the ONLY thing that talks to the DB
                  │  (FastAPI)    │     handles auth, validation, business rules
                  └──────┬────────┘
                         │  SQL (via SQLAlchemy)
                         ▼
                  ┌───────────────┐
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

| Layer                 | Technology                                                                                          | Reason it was chosen                                                                                                                                 |
| --------------------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Database              | **PostgreSQL**                                                                                      | Strong transactions for orders/payments; good JSON support; open source                                                                              |
| Backend API           | **Python 3.12+ with FastAPI**                                                                       | You know Python; async serves ~1k concurrent well; auto-generated API docs                                                                           |
| Python isolation      | **`venv` (built-in) + `pip` + `requirements.txt`**                                                  | Per-project packages; standard tooling; matches what the Docker image installs                                                                       |
| DB access             | **SQLAlchemy + Alembic**                                                                            | Python-to-SQL mapping plus safe, versioned schema migrations                                                                                         |
| Validation            | **Pydantic**                                                                                        | Enforces request/response shapes; ships with FastAPI                                                                                                 |
| Web frontend          | **Next.js (React)**                                                                                 | You know JS/HTML/CSS; server rendering helps store SEO                                                                                               |
| Web styling           | **Tailwind CSS**, configured from shared design tokens                                              | Consistent spacing/color scale; tokens make cross-platform matching possible                                                                         |
| Design tokens         | **`design-tokens.json`** at the repo root — the single source of truth for color, type, and spacing | One definition, manually mirrored into Tailwind, Kotlin, and Swift (Section 4.3)                                                                     |
| Vendor portal         | **The same Next.js app**, at `/admin`, gated by an `admin` role                                     | One codebase, one API, one auth system, one design system                                                                                            |
| Android               | **Kotlin (native)**                                                                                 | You already know it                                                                                                                                  |
| iOS                   | **Swift (native)**                                                                                  | You already know it                                                                                                                                  |
| Payments              | **Stripe**                                                                                          | Strong web + mobile SDKs; handles the PCI burden                                                                                                     |
| Auth                  | **JWT tokens** issued by the API, passwords hashed with **bcrypt**                                  | Identical flow for web and mobile                                                                                                                    |
| Containerization      | **Docker**                                                                                          | Same environment locally and on AWS                                                                                                                  |
| CI/CD                 | **GitHub Actions**                                                                                  | You know Git; automate tests and deploys                                                                                                             |
| API hosting           | **Amazon ECS (Express Mode)**                                                                       | AWS App Runner closed to new customers April 30, 2026; Express Mode is AWS's official successor — same App Runner-like simplicity, on top of Fargate |
| Container registry    | **Amazon ECR**                                                                                      | Express Mode deploys pre-built images only (no source builds), so the Docker image is pushed here first                                              |
| Web hosting           | **Amazon ECS (Express Mode)**                                                                             | Runs the Next.js container, sharing the API's load balancer. Not Amplify: it supports Next.js 12-15, this app is on 16 (Section 7)                                                                                                  |
| Database hosting      | **AWS RDS (PostgreSQL)**                                                                            | Managed Postgres with backups and failover                                                                                                           |
| Images / static files | **AWS S3 + CloudFront**                                                                             | Store product images; serve them via CDN                                                                                                             |
| DNS + HTTPS           | **AWS Route 53 + ACM**                                                                              | Domain and free TLS certificates                                                                                                                     |
| Secrets               | **AWS Secrets Manager**                                                                             | DB password and Stripe keys, kept out of Git                                                                                                         |
| Monitoring            | **AWS CloudWatch**                                                                                  | Logs, metrics, alarms                                                                                                                                |

---

## 4. Repository Structure and Project Conventions

One repository holds everything so the whole system is discoverable:

```
Manitou/
├── CLAUDE.md              # concise guidance for Claude Code
├── PROJECT_PLAN.md        # this file — the master plan
├── README.md              # human-facing setup and run instructions
├── design-tokens.json     # single source of truth for color, type, spacing (Section 4.3)
├── store-config.json      # store identity: name, currency, locale, tax, shipping, feature flags
│                          #   (Section 1.1). Together with design-tokens.json, the only two files
│                          #   a cloned store must edit. NOT .env — committed, and identical across
│                          #   environments. Read by the backend (app/store.py) and the web app.
├── .gitignore             # excludes .venv/, __pycache__/, .env, node_modules/
├── docker-compose.yml     # local PostgreSQL for development
├── docs/                  # project artifacts — ER diagram, per-phase build journals
│   └── reference/         # HTML concept references and exercises, named p<phase>-<task>-
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
│   │   ├── db.py          # engine, session, connection pool
│   │   ├── config.py      # settings from .env — secrets, per-environment values
│   │   ├── store.py       # settings from store-config.json — store identity, per-clone values
│   │   ├── security.py    # password hashing and JWT encode/decode (no FastAPI imports)
│   │   └── dependencies.py # FastAPI auth dependencies: get_current_user, require_admin
│   ├── alembic/           # migrations
│   ├── tests/             # pytest suite + conftest.py fixtures
│   ├── pytest.ini         # testpaths, and pythonpath so `app` imports resolve
│   ├── requirements.txt   # runtime only — this is what the Docker image installs
│   └── requirements-dev.txt  # -r requirements.txt, plus pytest and the test client
├── web/                   # Next.js storefront + vendor portal
│   ├── app/layout.tsx     # document shell only — html/body/fonts
│   ├── app/(store)/       # customer pages. Route group: parentheses keep it out of the
│   │                      #   URL, so /cart is still /cart. Carries SiteHeader + SiteFooter
│   ├── app/admin/         # vendor portal (role-gated). Its own nav, deliberately no footer
│   ├── components/        # shared UI — ui/ holds the primitives Phase 4 reuses
│   └── ...
├── mobile-android/        # Kotlin app (Phase 8)
├── mobile-ios/            # Swift app (Phase 8)
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
- Every new package gets recorded and committed, in **one of two files**. The venv folder itself is
  **never** committed.

| File                   | Holds                                                                            | Installed by                                          |
| ---------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `requirements.txt`     | Everything the app needs to **run**                                              | The Docker image (Phase 6), and developers indirectly |
| `requirements-dev.txt` | Test tooling only — `pytest`, the test client. Begins with `-r requirements.txt` | Developers: `pip install -r requirements-dev.txt`     |

The split exists so the production container never ships test code. It also means `pip freeze >
requirements.txt` is **no longer safe** — it would sweep the dev packages into the runtime file.
Add new entries deliberately, and check for drift afterwards:

```bash
comm -23 <(pip freeze | cut -d= -f1 | sort) <(cat requirements*.txt | cut -d= -f1 | sort)
```

Anything it prints is installed but undeclared — which is how `PyJWT` and `email-validator` went
missing from `requirements.txt` for four tasks, leaving a fresh clone unable to start the app.

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

Phase 4.5 adds two more: `EMAIL_SENDER` (which delivery implementation to use — `console` locally,
`ses` in Phase 6) and `APP_BASE_URL` (the origin password-reset links point at, which differs
between a laptop and production and therefore belongs here rather than in `store-config.json`).

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
secrets in **AWS Secrets Manager**, and **ECS** supplies them to the running container as
environment variables at startup. Your code calls `os.environ` exactly as it does locally and never
knows the difference — that's the whole point of the pattern.

| Environment         | Where values come from                            | Where secrets are stored          |
| ------------------- | ------------------------------------------------- | --------------------------------- |
| Local development   | `.env` file, loaded at startup                    | On your machine only, git-ignored |
| CI (GitHub Actions) | Repository secrets injected into the job          | GitHub encrypted secrets          |
| Production (AWS)    | Injected into the container by ECS (Express Mode) | **AWS Secrets Manager**           |

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

| Platform         | How tokens are applied                                                                                                                          |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Web (Next.js)    | Generated into a Tailwind `@theme` block by `web/scripts/build-tokens.mjs`, so Tailwind's palette, type scale, and spacing come from the tokens |
| Android (Kotlin) | Mirrored into a Compose `Theme.kt` — `MaterialTheme` colors, typography, and shapes                                                             |
| iOS (Swift)      | Mirrored into a SwiftUI theme file — `Color` and `Font` extensions                                                                              |

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
- The web expects a persistent top nav, a site footer, hover states, and browser-native controls.
  The footer is where shoppers look for contact details, shipping and returns before they buy;
  omitting it reads as an unfinished store. Mobile apps get neither — they use native navigation
  and a Settings screen instead, which is the "identical brand, native feel" rule below.

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
- Store-specific copy — name, tagline, support address — comes from `store-config.json`, never a
  literal in a component. The footer is where this rule is easiest to break and hardest to notice.

### When the design gets defined

Design tokens are decided at the **start of Phase 3**, before any page is built. Retrofitting a
design system after screens exist means rewriting them. The tokens then stay fixed through Phases 4
and 7 unless deliberately revised.

---

## 5. Build Phases (with tasks)

Do the phases in order. Do not start mobile (Phase 8) until the website works end to end.

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
4. **[You + Claude Code]** Create the Next.js project and wire Tailwind to read from
   `design-tokens.json` so nothing is hardcoded. Note that Tailwind v4 has no `tailwind.config.js`
   — configuration is a `@theme` block in CSS. `web/scripts/build-tokens.mjs` generates that block
   (and a typed `store-config.ts`) from the two repo-root JSON files, running automatically before
   `dev` and `build`. Both generated files are git-ignored: edit the JSON, never the output.
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

### Phase 4.5 — Account Management

**Why this phase exists, and why it is numbered 4.5.** It was not in the original plan. Building
Phase 4 made the gap plain: the vendor portal manages products, stock and orders but cannot see a
single customer, and a customer who forgets their password is locked out permanently — there is no
recovery path at all. Neither is acceptable before taking real money in Phase 5. It is numbered 4.5
rather than renumbering so every existing reference to Phases 5–8 stays correct.

**One constraint shapes the whole phase.** `orders.user_id` is `NOT NULL` with `NO ACTION`, so a
customer who has ever ordered **cannot be deleted**. Erasure is therefore _anonymisation in place_:
personal fields are scrubbed and the order rows keep their foreign key. That is also the normal
answer to a legal erasure request, since tax rules require retaining invoices.

The same constraint reaches one level further, into addresses. `orders.shipping_address_id` is also
`NO ACTION`, and an order carries **no address snapshot** — unlike `order_items`, which freeze name
and price, an order points at the live `addresses` row. So anonymisation **deletes address-book
entries no order references and leaves the rest intact**: scrubbing an order-linked address would
erase where a real parcel was actually sent, which is the record an invoice depends on.

**One existing decision makes suspension cheap.** `get_current_user` already re-reads the user row
on every request (Section 8), so setting `is_active = false` takes effect on that user's very next
request. No token-revocation machinery is needed.

**And the phase needs an audit trail, because of what it adds.** Nothing in the database currently
records who did what — thirteen tables, not one of them an event log. That was tolerable while the
admin could only edit products. This phase adds suspending a person, changing a role, and
irreversibly scrubbing someone's identity, and "who did this, and when?" is the first question asked
after any of them goes wrong. The audit trail is therefore built _before_ the actions it records,
not retrofitted afterwards. It is also the precondition for ever adding impersonation: that feature
is safe only when every action taken inside it is attributable, which is impossible without this.

1. **[You + Claude Code]** Migration: add `users.is_active`, `users.password_changed_at`,
   `users.totp_secret`, `users.totp_enabled`; create `password_reset_tokens`,
   `user_recovery_codes` and `audit_events` (Section 6.3). `audit_events` gets a trigger rejecting
   `UPDATE` and `DELETE`, so append-only is a database guarantee rather than a habit.
2. **[You]** Install `pyotp` and `qrcode[pil]` into the venv and add both to `requirements.txt`.
   They are runtime dependencies, not dev tooling.
3. **[You + Claude Code]** Audit trail service (`app/services/audit.py`) — built third, before any
   endpoint that needs it, so every task below records as it is written instead of being
   retrofitted. `record(db, actor, action, target, metadata)` enqueues the row on the **caller's
   session**, so the event commits in the same transaction as the action it describes: no silent
   actions, and no records of things that never happened. Then retrofit the Phase 4 writes that
   already exist — order status changes, product activate/deactivate.
4. **[You + Claude Code]** Email delivery seam: an `EmailSender` protocol in
   `app/services/email.py` with a console implementation that prints the link during development.
   Add `EMAIL_SENDER` and `APP_BASE_URL` to `.env` and `.env.example`. Phase 6 adds the SES
   implementation and nothing else changes — that is the point of the seam.
5. **[You + Claude Code]** Enforce suspension and password invalidation: reject `is_active = false`
   at login and in `get_current_user`, and reject any token issued before `password_changed_at`.
6. **[You + Claude Code]** Customer self-service API: `PATCH /auth/me` (name, phone),
   `POST /auth/change-email`, `POST /auth/change-password` (requires the current password), and
   `DELETE /auth/me` (anonymises, per the constraint above).
7. **[You + Claude Code]** Password reset API: `POST /auth/forgot-password` and
   `POST /auth/reset-password`. Tokens are stored **hashed**, single-use and short-lived, and the
   request endpoint answers identically whether or not the address exists (Section 8).
8. **[You + Claude Code]** Two-factor API (TOTP): `POST /auth/2fa/setup` (secret + QR),
   `POST /auth/2fa/enable` (verify a code, then issue recovery codes), `POST /auth/2fa/disable`,
   and the login challenge — with 2FA on, `/auth/login` returns a short-lived challenge instead of
   an access token, redeemed by `POST /auth/2fa/verify`.
9. **[You + Claude Code]** Admin user API: `GET /admin/users` (search + pagination, filter by role
   and status), `GET /admin/users/{id}` (orders, addresses, lifetime value),
   `PATCH /admin/users/{id}` (suspend/reactivate, change role),
   `POST /admin/users/{id}/password-reset`, `POST /admin/users/{id}/disable-2fa`, and
   `POST /admin/users/{id}/anonymise` — which requires the acting admin's own password, being the
   one irreversible action of the six.

   **Users, not customers**: the list deliberately includes admins. Filtered to `role = 'customer'`
   it could never show who has access, never demote anyone, and would make the guards below
   unreachable except by hand-crafting an API call.

   The disable-2fa endpoint is the escape hatch for a customer who has lost both their
   authenticator and their recovery codes — without it that account is unrecoverable, which is a
   worse lockout than the password one this phase exists to fix. It is also, unavoidably, an admin
   being able to strip a customer's second factor, which is exactly why it is audited as
   `customer.2fa_disabled` with the acting admin named.
   Two guards, both enforced server-side: an admin cannot suspend or demote **themselves**, and the
   **last remaining admin** cannot be suspended or demoted. Without them the store can be locked
   out of its own portal with no way back in. Every one of these writes an audit event, as do the
   credential changes in tasks 6–8 — a customer disputing "someone changed my password" needs that
   record as much as the vendor does.

   Also **reading** the trail: `GET /admin/audit` (paginated, filterable by `action` and by
   `target_type` + `target_id`, newest first — the two indexes task 1 created exist for exactly
   these two queries). There is deliberately no write, update or delete endpoint for
   `audit_events` at any point in this project: the table is append-only in the database, and
   giving the API a way to touch it would make that guarantee decorative.

10. **[You + Claude Code]** Web — customer: expand `/account` with editable profile, change password,
    two-factor setup and account deletion. Add `/forgot-password` and `/reset-password`, plus the
    second step in the login flow when 2FA is enabled.
11. **[You + Claude Code]** Web — vendor: `/admin/users` list and detail with suspend, reactivate,
    send-reset, disable-2FA and anonymise actions, reusing the Phase 3 primitives. The detail page
    renders only the actions `allowed_actions` reports, so a button can never offer something the
    API will refuse — the same contract as the order dashboard's `allowed_transitions`. It also
    shows that user's audit history, and `/admin/audit` shows the whole log, filterable by action —
    read-only, with no delete control anywhere in the UI.
12. **[You]** Walk the whole thing end to end: request a reset and complete it using the link
    printed to the console; enable 2FA with a real authenticator app and sign in with a code; spend
    a recovery code; suspend an account and confirm the already-open session dies on its next
    request. Then check the audit log records every one of those actions with the right actor, and
    confirm the append-only trigger actually refuses an `UPDATE` and a `DELETE` from `psql`.

**Deliberately not in this phase:**

- **Email verification on signup.** Real, but closes none of the gaps above.
- **Admin impersonation** ("sign in as this customer"). Its safety depends entirely on the audit
  trail this phase introduces, so it becomes _possible_ to build responsibly after 4.5 — not
  before. It also needs a visible banner, a time limit, and a decision about whether an impersonated
  session may place orders or change credentials. That is its own discussion.
- **Customer data portability** (a customer downloading their own data). A compliance feature,
  scoped to one person, distinct from the vendor-side analytics below.
- **Analytics export** (CSV of orders/customers for the vendor). Separate from portability despite
  both being called "export": different consumer, different scope, no legal driver. Section 12
  already defers sales reporting to post-v1, and the database is directly queryable in the
  meantime — `COPY (SELECT ...) TO STDOUT WITH CSV HEADER` needs no code. Worth its own small phase
  if the vendor ever needs it without SQL.

### Phase 4.6 — Product Imagery

Adding a second image to a product used to do nothing a customer could see: the product page took
the primary and discarded the rest, so extra images existed in the database, showed in the portal,
and reached nobody. Choosing "Large / White" also still showed the black shirt, which is worse than
showing nothing — the customer is looking at a photograph of the thing they did not pick.

1. **[You + Claude Code]** `product_images.applies_to` (JSONB, default `{}`). Empty means the image
   shows for every variant, so every row that predates the column keeps behaving exactly as before
   and the migration needs no backfill.
2. **[You + Claude Code]** The matching rule, in `services/image_match.py` and mirrored in
   `web/lib/image-match.ts`: an image shows when every pair in `applies_to` matches the selected
   variant's `attributes`. A **subset** test — `{"color": "Black"}` matches
   `{"size": "L", "color": "Black"}`: a photo of a black shirt is a photo of every size of one.
   Keyed on the visual dimension rather than a `variant_id`, so one photo covers all sizes of a
   colour instead of being duplicated per size. Images tagged _for_ the selection lead the gallery;
   untagged ones follow.
3. **[You + Claude Code]** The API rejects `applies_to` keys no variant of that product uses. The
   database cannot check it (the keys live in JSONB on another table), and without it a misspelling
   like `colour` matches nothing, appears nowhere, and reports no error at all.
4. **[You + Claude Code]** `ProductGallery`: main image plus a keyboard-navigable thumbnail strip,
   filtered live as options are picked. The selection moved out of `AddToCart` into a context
   provider so the gallery and the picker share it — the provider takes `children`, so the name,
   price and description stay server-rendered.
5. **[You + Claude Code]** Portal: a "Shows for" picker on each image, offering the options that
   product's variants actually define. A list, not a text box — the same reason the image URL
   became a picker.

**Deliberately not in this phase:** carousels on the catalogue grid (`ProductListItem` stays
light — the grid is for choosing which product to look at, the product page is where the decision
happens); a per-variant primary image; zoom or lightbox.

### Phase 5 — Payments (Stripe)

1. **[You]** Create a **Stripe** account. Copy your **test-mode** API keys. Store them as
   environment variables — never commit them to Git.
2. **[You + Claude Code]** Backend: create a Stripe PaymentIntent when an order is placed.
3. **[You + Claude Code]** Web checkout: collect payment with Stripe's SDK so card data goes
   straight to Stripe and never touches your server.
4. **[You + Claude Code]** Add a Stripe webhook endpoint that confirms payment and marks the order paid.
5. **[You + Claude Code]** Record payment references in the `payments` table (Section 6.3).

   **Satisfied by tasks 2 and 4 — there is no separate code to write.** Task 2 cannot open a
   PaymentIntent without somewhere to put the reference, so `ensure_payment_intent` writes the row
   (`order_id`, `stripe_payment_intent_id`, `amount`, `currency`, opening `status`), and task 4's
   `apply_payment_event` keeps `status` current. Every column in Section 6.3 is populated. It is
   listed as its own step because _what to store about a payment_ is a decision worth taking
   deliberately rather than by accident; the decision, not the work, is what lives here.

   Two consequences worth knowing before reading the code:
   - **`payments.status` carries Stripe's vocabulary verbatim**, which is why it reads `canceled`
     (one L) where `orders.status` reads `cancelled`. Two columns, two owners, two spellings, on
     purpose. A word we invented would have to be kept in step with theirs forever.
   - **We store a reference, never an instrument.** No card number, no last4, no client secret —
     the secret is returned to the browser and deliberately not written down, because anything
     stored is something that can leak from a backup or a log.

   **Known gap, deferred to Phase 6.** The mirror is only accurate at the moments something looks:
   a webhook delivery, or an admin re-check. Nothing sweeps the table against Stripe, so a row
   whose event was missed stays stale until someone checks that specific order. Acceptable at
   launch scale with the re-check as the manual path; a scheduled reconciliation belongs with the
   other Phase 6 operational concerns.

6. **[You + Claude Code]** Reserve stock instead of decrementing it, and show the vendor the
   difference.

   Today `checkout.py` does `quantity_available -= line.quantity` at order creation — _before_ any
   money moves. That was correct while `pending → paid` was a human decision, and stops being
   correct the moment payment is a separate step that can simply never happen: an abandoned
   checkout holds its stock forever. Ten items and ten abandoned carts leaves a product reading
   sold out having earned nothing, and nothing in the system explains why.

   `inventory.quantity_reserved` already exists for this, with its `>= 0` CHECK, described in
   Section 6.3 as "held during checkout", and is currently written by nothing.
   - Placing an order adds to `quantity_reserved` and leaves `quantity_available` alone.
   - **Sellable becomes `quantity_available - quantity_reserved`.** Every place that asks "is there
     stock?" has to change together: the oversell guard in `checkout.py`, the storefront's
     `in_stock` boolean, and the Sold out badge. Missing one reintroduces overselling in exactly
     the window this is meant to close.
   - Payment confirmed (the task 4 webhook) decrements `quantity_available` and releases the
     reservation **in the same transaction as the status change**, so the two can never disagree.
   - Cancelling or expiring releases the reservation without touching `quantity_available`.
   - **Cancelling a PAID order must put the stock back**, and today nothing does. Measured: place
     an order, cancel it, and `quantity_available` stays decremented — there is no restock path
     anywhere in the codebase, so every cancelled order permanently leaks its inventory. The
     reservation work does not fix this on its own: it covers orders that were never paid, while a
     paid order has already had stock deducted and takes a different route back.
   - **Refunding is not the same as restocking, and must not be automatic.** A cancelled order was
     never dispatched, so its stock is still on the shelf and returning it is safe. A refunded one
     may have been shipped, and what comes back may be damaged, opened, or never returned at all.
     Silently adding it to sellable stock would invent inventory that does not exist. So:
     `→ cancelled` restocks automatically; `→ refunded` does not, and the vendor restocks
     deliberately from `/admin/inventory` if the goods actually came back. Both write an
     `audit_events` row, because "where did those twelve units come from?" has to be answerable.
   - `needs_reorder` keeps comparing against `quantity_available`, not the sellable figure:
     reordering is about physical stock on a shelf, not about what is currently spoken for.
   - The concurrency guard moves with it. `checkout.py` already takes `SELECT ... FOR UPDATE` row
     locks; the comparison inside them becomes `available - reserved >= requested`.

   **Vendor visibility.** `/admin/inventory` gains a **Reserved** column and an **Available to
   sell** figure beside the physical count, so "why is this sold out when I have twelve on the
   shelf?" is answerable from the screen rather than from the database. Sortable like the rest.

   **Also settle the cart's partial-stock gap here**, because `in_stock` is being redefined in this
   task anyway. Today the cart labels a line only at zero stock: hold 3 of something and the vendor
   drops to 1, and the cart looks entirely fine until checkout fails with "only 1 in stock". The
   cart carries a boolean, not a count. Showing "only 1 left" means publishing an exact figure,
   which `VariantRead`'s docstring deliberately avoids for the public catalogue — but a count _for
   something already in a customer's own cart_ is a much narrower disclosure than a catalogue-wide
   one, and it is the difference between fixing the problem in the cart and discovering it at the
   till. A decision to take, not a bug to fix silently.

   Two more decisions to settle when building it, not now:
   - **Counter or derived?** A maintained `quantity_reserved` counter is cheap to read and can
     drift if any release is ever missed — and a drifted reservation is invisible stock loss
     nobody can trace. Deriving it from unpaid orders (`sum(quantity)` over `order_items` joined to
     `pending` orders) cannot drift and is self-healing, at the cost of a query. Recommendation:
     derive it, and keep the column as a materialised copy only if measurement says the query is
     too slow.
   - **What expires a reservation?** Stripe emits `payment_intent.canceled`, but a customer who
     closes the tab emits nothing. Needs an explicit rule — a `reserved_until` on the order plus a
     sweep, or treating reservations older than N minutes as void on read. The lazy read-time
     version needs no scheduler, which suits a single container.

7. **[You]** Run the full checkout using Stripe's test cards and confirm the order is marked paid.
   Then abandon one at the payment step and confirm the stock comes back rather than staying held.

### Phase 5.5 — Fulfilment, Tracking & Delivery Confirmation

Until this phase, `delivered` means an admin clicked a button. The audit trail records _who claimed
it and when they claimed it_ — provenance, not evidence — and `orders` carries no carrier, no
tracking number and no dispatch or delivery timestamp. Three things need that fixed: a payment
processor answering a "product not received" dispute wants `shipping_carrier`,
`shipping_tracking_number` and `shipping_date` and will not accept a status word; a customer
currently sees no tracking link or dates at all; and the vendor has no record of what was sent.

After Phase 5 rather than before it: nothing in Phase 5 consumes shipment data, and dispute evidence
only matters once real money moves, which is Phase 6 onward. Before Phase 6 rather than after,
because that is when it starts mattering.

1. **[You + Claude Code]** Migration: `shipments` and `shipment_events` (Section 6.3), four CHECK
   constraints, the append-only trigger, indexes. Autogenerate does not detect CHECK constraints
   (Section 6.8) — write them by hand, drop them explicitly in `downgrade()`, and verify against
   `pg_constraint`.
2. **[You + Claude Code]** Models, plus the `fulfilment` block in store config: `method` and a
   carrier list of `{code, name, tracking_url}`. Carrier lists are store-specific — a UK clone uses
   Royal Mail — so they belong in config, not code. Validate at startup that `method: "carrier"`
   has a non-empty list.
3. **[You + Claude Code]** Service layer: create a shipment, record an event, couple both to the
   order status in one transaction.
4. **[You + Claude Code]** `POST /admin/orders/{id}/shipment` records dispatch and advances the
   order to `shipped`; `POST /admin/orders/{id}/shipment/events` records `delivered` or `failed`.
   `ALLOWED_TRANSITIONS` stays the single authority on legality — but `shipped` and `delivered` now
   require evidence, so `PATCH /admin/orders/{id}/status` 409s for those two and names the endpoint
   that does the job. Manual delivery remains possible (there is no carrier webhook yet) and is
   recorded honestly as `source: 'admin'`.
5. **[You + Claude Code]** Vendor portal: a dispatch form (carrier picker from config plus tracking
   number) in place of the bare "Mark shipped" button, a shipment panel with the tracking link, and
   the event timeline.
6. **[You + Claude Code]** Storefront: the tracking timeline on the customer's order page — Ordered
   → Paid → Dispatched with a working carrier link → Delivered, with dates. This is the
   transparency the phase exists for.
7. **[You + Claude Code]** Tests, including mutation-testing each new guard: break the CHECK, break
   the transition rule, and watch the test fail before fixing it.
8. **[You]** Walk it end to end with a real tracking number, then confirm from `psql` that
   `shipment_events` refuses an `UPDATE` and a `DELETE`.

**Deliberately not in this phase:**

- **Carrier tracking webhooks** (EasyPost, Shippo, AfterShip, or a carrier API directly). Needs an
  external account, and Phase 5 task 4 builds the webhook pattern — signature verification,
  idempotency, out-of-order events — that this should copy rather than reinvent. Its own phase.
- **The `courier` role, its confirmation endpoint, and the delivery app.** The grocery clone adds
  all three; the schema accepts them with no migration, which is the whole point of the seam.
  Building them now means a role nobody holds and an endpoint with no client, guessing at the auth
  model of an app that does not exist yet.
- **Buying shipping labels, partial shipments, and stored proof-of-delivery files.** The last needs
  S3, which arrives in Phase 6.
- **Auto-marking an order delivered N days after dispatch.** Tempting and wrong: it writes a fact
  nobody observed into the row later handed to a payment processor as evidence, and it is wrong
  precisely when the parcel was lost — the only case that matters.

### Phase 6 — AWS Deployment

1. **[You]** Create an **AWS account** at aws.amazon.com. A payment method is required, but you'll
   stay in the free tier where possible.
2. **[You]** Immediately set a **billing budget with an alert** (start around $10) so any charge
   warns you. Ask Claude Code for the exact current console steps.
3. **[You]** Create an **IAM user** for your daily work and stop using the root account for
   everyday tasks. (This is a security best practice and appears on the Cloud Practitioner exam.)
4. **[You + Claude Code]** Provision **RDS PostgreSQL**. Keep it private so only the API reaches it.
   - **Met, in Phase 7 (2026-08-31).** `PubliclyAccessible` is now false and
     `manitou-db-sg` has exactly one inbound rule, sourced from the API's security
     group. No private subnets or NAT gateway were needed: a DB instance with no
     public IP is unreachable from the internet even in a public subnet. Direct
     `psql` is gone by design; migrations run as one-off ECS tasks via
     `infra/scripts/migrate.sh`.
5. **[You + Claude Code]** Point Alembic at RDS and apply your migrations there, producing the
   same schema you have locally.
6. **[You + Claude Code]** Containerize the API with Docker. Push the image to **ECR** (Elastic
   Container Registry) — Express Mode deploys pre-built images only, not source repos, so this
   push step is required before the next one.
7. **[You + Claude Code]** Deploy the pushed image with **ECS Express Mode**, AWS's current
   recommended successor to App Runner (closed to new customers as of April 30, 2026). Express
   Mode runs on the same Fargate compute and automates the cluster, load balancer, HTTPS, and
   scaling setup App Runner used to handle.
8. **[You + Claude Code]** Deploy the web app as a **second ECS Express Mode service**, sharing the
   ALB the API already pays for. Not Amplify Hosting — it supports Next.js 12–15 and this app is on
   16.3.0. See the Amplify note in Section 7.
9. **[You + Claude Code]** Set up **S3 + CloudFront** for product images and switch uploads to use them.
   This is where the admin image field becomes a real upload. Until now it is a picker listing the
   files already in `web/public/` — deliberately not a free-text URL box, because an external
   address is accepted by the form and then makes `next/image` throw at _render_ time, taking down
   the storefront and the admin edit page together. The upload uses a **presigned PUT**: the browser
   asks the API for a URL, sends the file straight to S3, and posts back only the key, so the API
   never handles the bytes and there is no request-size ceiling. `accept="image/*"` on one file
   input is all that is needed for a phone to offer both camera and photo library — a `capture`
   attribute would force the camera and remove the library, which is the opposite of useful. Add
   the single CloudFront host to `images.remotePatterns`, which is the one host `next.config.ts`
   was always written to expect, and widen the `AdminImageCreate.url` validator to allow it.

   **Uploading is the primary path, not browsing.** The vendor's normal action is "I photographed
   this shirt, attach it to this product" — so the file input lives on the product create/edit
   page and the upload happens there. Browsing an existing library is the _secondary_ path, for
   reusing a photo across products. Building it the other way round is what produces admin screens
   where adding an image means first going somewhere else to put it.

   Presigned uploads need a **confirm step**, because the browser PUTs straight to S3 and the API
   never sees it happen: after the PUT succeeds the client posts the key back, and only then does a
   row exist. An abandoned upload leaves an object nobody references, so the bucket needs a
   lifecycle rule expiring unconfirmed keys — otherwise it fills with orphans nobody can see.

9b. **[You + Claude Code]** Media library: a modal picker for reusing images already uploaded.

The Phase 5.5-era picker renders every file as a thumbnail inline on the product page. That is
right for the six files in `web/public/` and unusable at two hundred — the page becomes a wall
of images with no way to find anything. Replace it with a scrollable modal built on
`web/components/ui/modal.tsx`, which already gives a focus trap, Escape-to-close, an inert
background and focus return via the native `<dialog>` element. It exists and is currently used
only by `/preview`, so this is reuse rather than new UI.

Inside: search by filename and alt text, sort by upload date (newest first, the default anyone
actually wants), name or size, and a grid/list toggle — a list is faster to scan when the names
are meaningful and the pictures all look alike.

**This needs a `media_assets` table, not just an S3 bucket**, and that is the part worth deciding
before writing code. `ListObjectsV2` paginates by continuation token rather than offset, so it
cannot drive `components/pagination.tsx`; it sorts only by key; it cannot search; and it carries
no alt text, dimensions or "which products use this". A table indexed on `uploaded_at` gives all
of it and matches how `/admin/orders`, `/admin/users` and `/admin/audit` already paginate. The
row is written by the confirm step above: key, original filename, content type, byte size,
width, height, `uploaded_at`, `uploaded_by`.

Then `product_images` references the asset (`asset_id` **FK** → `media_assets.id`) rather than
storing a loose URL string. That is what makes "where is this image used?" answerable, and it
lets the FK refuse to delete an asset a product still shows — the same `NO ACTION` reasoning
used everywhere else in this schema. Deleting an unused asset removes both the row and the S3
object; deleting a used one is refused with the list of products holding it.

10. **[You]** Register a domain in **Route 53** and issue an **ACM** certificate for HTTPS.
11. **[You + Claude Code]** Move secrets into **Secrets Manager** and set up **CloudWatch** logs and alarms.

### Phase 7 — Hardening and Launch

1. **[You]** Size a real launch-tier concurrency target using the methodology in Section 10.1 —
   addressable market → realistic early-launch capture rate → visits → concurrent users. Don't
   skip this step in favor of a round number.
   - **Done 2026-08-31.** Cold launch, no list: **~1 concurrent user** at launch-day peak, ~11 if a
     post does 10× better than expected. Working shown in Section 10.1.
2. **[You + Claude Code]** Load test against that sized target, not an assumed one. Adjust the RDS
   instance size and connection pool based on the results.
   - Because the sized target is ~1, the test is a **ramp to failure** to find the headroom, not a
     pass/fail against a number the infrastructure clears without noticing.
   - **Done 2026-08-31.** Comfortable to 50 concurrent, degraded at 100, collapse between 100 and
     200 — roughly **50× headroom** against the sized target. Run twice, at 1 product and at 25, so
     catalogue size was isolated as a variable; `/health` p50 was unchanged across both and is the
     control that makes the comparison mean something.
   - **The RDS size and the pool were not changed, on the evidence.** At collapse the database sat
     at 24% CPU with its burst credits untouched and 25–35 of ~112 connections used, while the API
     and web containers were at 95% and 97%. **The bottleneck is Fargate CPU at `maxTaskCount: 2`,
     not the database** — the opposite of what this task assumed. Full numbers in `infra/README.md`.

2b. **[You + Claude Code]** Defect 30, found while planning task 2 and fixed first: the API
   connected as the RDS **master** user, whose password rotates every 7 days, while ECS resolves an
   injected secret only at task start. A rotation left the running task authenticating with a dead
   password — failing ~25% of concurrent requests while `/health` stayed 200 on its one warm
   connection and no alarm moved. The API now runs as `manitou_app` (DML only, cannot disable the
   `audit_events` trigger); migrations use a separate `manitou-dbadmin` task definition.
3. **[You + Claude Code]** Add rate limiting, review input validation, and do a security pass.
   - **Done 2026-08-31.** Per-IP limits on login, 2FA verify, forgot-password, reset-password and
     register, in-process and in-memory; forgot-password carries a second key on the email address.
     Limits are route dependencies, so they run before the bcrypt comparison.
   - **Two defects found first, and the order was forced.** Defect 32: the audit trail recorded the
     load balancer, because `request.client.host` behind an ALB is the ALB — and rate limiting keys
     on that value, so limits shipped against it would have put the whole internet in one bucket.
     Defect 31: a password one byte over bcrypt's 72-byte limit returned **500 from an
     unauthenticated endpoint**, handing anyone a way to feed the alarm ECS reads during a
     deployment bake.
   - Also: the interactive API schema is no longer served in production (defaults to off), and the
     storefront gained security headers it had none of.
   - **CSP is enforcing from 2026-09-01**, after shipping Report-Only first. That order was not
     ceremony: it caught two missing origins that reading the code did not — `fonts.googleapis.com`,
     which Stripe.js fetches itself so a block would silently restore defect 16, and the presigned
     upload bucket, on a page the checkout test never visits. Verified by a completed test-mode
     purchase plus a sweep of account, orders, admin, the media library and the audit log.
   - **CORS was reviewed and deliberately left absent** — the browser never calls the API, so no
     CORS headers means deny-by-default. See `infra/README.md`.
   - **Port 80 now redirects to HTTPS** (2026-09-01). It was closed, so `http://imprimapress.com`
     failed to connect rather than reaching the shop. The security group already allowed port 80 —
     nothing was listening — so this was one ALB listener and no firewall change. 301, preserving
     host, path and query, covering the apex, `www` and the API subdomain.
4. **[You]** Verify backups by performing a test restore. An untested backup is not a backup.
   - **Done 2026-09-02.** Restored the most recent daily snapshot to a throwaway private instance and
     compared it against production with `infra/probes/db_census.py`. Schema version identical, 19
     tables both sides, and every row that differed was created after the snapshot — a restore that
     matched exactly would have meant the wrong database was measured. Deleted afterwards; a few
     cents.
   - **Recovery time ≈ 6 minutes. Recovery point ≈ up to 24 hours** on daily snapshots — PITR would
     bring that to minutes and has not been exercised yet.
   - **The finding: a restored instance has no readable master password.** Production's master
     password is RDS-managed and rotates weekly; the restore came back with no managed secret at all,
     so its password is frozen at snapshot time and stored nowhere. It worked only because no
     rotation had happened in between. **After any restore, run `modify-db-instance
     --manage-master-user-password` before assuming success** — otherwise the data is intact and
     unreachable. See `infra/README.md`.
5. **[You + Claude Code]** Confirm logging, alerts, and error tracking are in place, then launch.

   **Going live is not a switch, and none of the below is exercised by the test-mode integration.**
   Written down because each item fails in a different place, and two of them fail silently:

   - **[You]** Stripe **live** API keys — secret into Secrets Manager, publishable into the
     `STRIPE_PUBLISHABLE_KEY` repository variable. The publishable key is baked into the client
     bundle at build time, so it needs a rebuild, not a restart.
   - **[You]** A **live-mode webhook endpoint** with its own signing secret. The test-mode secret
     will not verify live events, and the failure is a 400 that looks like ordinary traffic to the
     load balancer — which is exactly what the `AppWarningCount` alarm was built for.
   - **[You]** Register `imprimapress.com` **and** `www.imprimapress.com` on Stripe's Payment method
     domains page. Dashboard only, no file to host. Required for Apple Pay; registering in live mode
     covers sandboxes too.
   - **[You]** Activate the payment methods you actually want in live mode. Unactivated methods show
     in test mode and vanish in live, so the test-mode checkout is not a preview of the live one.
   - **[You + Claude Code]** Re-check the browser console after enabling any wallet. **CSP is
     enforcing**, so an origin a wallet needs but the policy omits removes the button silently
     rather than erroring.

   **Customer-facing email** (built 2026-09-02, dormant until SES production access):

   - **Password reset** and **order confirmation** are both written and tested. They send through
     whatever `EMAIL_SENDER` names, so they run against `MemoryEmailSender` in tests and print to the
     log in production today. Flipping to `ses` is what starts real delivery — no code change.
   - The confirmation follows the **`pending → paid` transition**, not the Stripe event.
     `apply_payment_event` performs that transition exactly once however many times Stripe
     redelivers, so the email inherits that guarantee and needs no sent-flag of its own. Both paths
     that can confirm a payment — the webhook and the admin re-check — send from the same place.
   - **A failed send never fails the webhook**, and that is correctness rather than tidiness: a
     non-2xx would have Stripe redeliver, the redelivery would find the order already paid and take
     the branch that sends nothing, so the message would be lost permanently rather than delayed.
### Phase 8 — Mobile Apps

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
- An **order** contains many **order items** and has one **payment**.

"Has many / belongs to" describes **cardinality** — one-to-one, one-to-many, or many-to-many.
Most relationships above are one-to-many. Cart items and order items are the classic pattern for
turning a many-to-many (products ↔ orders) into two one-to-many links through a join table.

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
| is_active | boolean | default true. False blocks sign-in and every authenticated request (Phase 4.5) |
| password_changed_at | timestamptz | nullable. Tokens issued before this are rejected — the nearest thing to "sign out everywhere" without refresh tokens |
| totp_secret | text | nullable. Base32 TOTP seed; present only once 2FA setup has begun |
| totp_enabled | boolean | default false. Separate from the secret so a half-finished setup cannot lock anyone out |
| created_at | timestamptz | default now() |

**password_reset_tokens** (Phase 4.5)
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| user_id | bigint | **FK** → users.id |
| token_hash | text | Only the hash is stored. The raw token exists solely in the emailed link, so a leaked database cannot be used to reset anyone's password |
| expires_at | timestamptz | Short — 30 minutes |
| used_at | timestamptz | nullable; single use, so a forwarded or logged link cannot be replayed |
| created_at | timestamptz | default now() |

**user_recovery_codes** (Phase 4.5)
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| user_id | bigint | **FK** → users.id |
| code_hash | text | Hashed with bcrypt, exactly like a password — a recovery code _is_ a credential |
| used_at | timestamptz | nullable; each code works once |

**audit_events** (Phase 4.5) — append-only
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| actor_user_id | bigint | **FK** → users.id, nullable. Null for unauthenticated events such as a password reset completed from an emailed link |
| actor_email | text | **Snapshot**, not a join. Anonymising an admin scrubs `users.email`, which would erase who performed every past action if this were resolved at read time. Same reasoning as `order_items.product_name_snapshot` |
| action | text | Dotted verb, e.g. `customer.suspended`, `customer.role_changed`, `customer.anonymised`, `auth.password_changed`, `auth.2fa_enabled`, `order.status_changed` |
| target_type | text | `user`, `order`, `product`, … |
| target_id | bigint | nullable |
| details | jsonb | Before/after values and any reason given. Never credentials — no tokens, hashes, or secrets, even scrubbed. Named `details`, not `metadata`: the latter is reserved by SQLAlchemy's Declarative API and raises `InvalidRequestError` on class definition |
| ip_address | text | nullable |
| created_at | timestamptz | default now() |

**Append-only is enforced by the database**, with a trigger that raises on `UPDATE` and `DELETE`.
A log an application can quietly rewrite is not evidence of anything, and the whole point of this
table is that it can be trusted after something has gone wrong. Retention and archiving are a
Phase 7 concern; nothing prunes it in v1.

**shipments** (Phase 5.5)
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| order_id | bigint | **FK** → orders.id, **unique**. One parcel per order in v1. The constraint is easy to drop later; code that must ask "which shipment?" everywhere is not. Partial shipments would need a `shipment_items` join table — deliberately out of scope |
| method | text | `'carrier'`, `'courier'` or `'pickup'` — CHECK. The Section 1.1 seam: the T-shirt and candle stores ship by carrier, the grocery clone delivers with its own staff |
| carrier | text | nullable; matches a `code` in the store config's carrier list |
| tracking_number | text | nullable |
| dispatched_at | timestamptz | not null |
| delivered_at | timestamptz | nullable. Denormalised from `shipment_events` so "delivered in the last 30 days" is one indexed query rather than a subquery |
| created_at | timestamptz | default now() |

CHECK `method_requires_tracking`: a `carrier` shipment must have both `carrier` and
`tracking_number`. That row is exactly what a payment processor asks for during a "not received"
dispute, so the database refuses to store one without it — an optional field ends up empty
precisely on the orders where it matters.

**shipment_events** (Phase 5.5) — append-only
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| shipment_id | bigint | **FK** → shipments.id, indexed |
| status | text | `dispatched`, `in_transit`, `out_for_delivery`, `delivered`, `failed`, `returned` — CHECK |
| occurred_at | timestamptz | When it happened, according to the source |
| recorded_at | timestamptz | When we learned. Separate on purpose: a webhook arriving Tuesday about a Monday delivery must record Monday, or the customer's timeline lies and the dispute evidence carries the wrong shipping date |
| source | text | `admin`, `carrier`, `courier`, `customer` — CHECK. The second half of the Section 1.1 seam, and what makes evidence quality legible: a status set by an admin clicking a button is not the same fact as one confirmed by a carrier |
| actor_email | text | nullable **snapshot**, never a join — same rule as `audit_events` |
| detail | jsonb | Proof payload: signature URL, photo, geolocation, courier id. Named `detail`, not `metadata`, for the same SQLAlchemy reason as `audit_events.details` |

Append-only by trigger, like `audit_events` and for the same reason: evidence an application can
rewrite is not evidence. This table is what answers a chargeback.

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
| user_id | bigint | **FK** → users.id, unique — one cart per user |

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
- **Not-null constraints** on anything required (email, prices, quantities).
- Let the database enforce these; constraints are your safety net even if the app has a bug.

**Unique constraints** — six in total:

| Column                 | What it guarantees                                                                 |
| ---------------------- | ---------------------------------------------------------------------------------- |
| `users.email`          | One account per address                                                            |
| `categories.slug`      | URLs resolve to one category                                                       |
| `products.slug`        | URLs resolve to one product                                                        |
| `product_variants.sku` | A SKU identifies exactly one sellable item                                         |
| `inventory.variant_id` | At most one stock row per variant — this is what makes the relationship one-to-one |
| `carts.user_id`        | One cart per user                                                                  |

Note what `inventory.variant_id` does _not_ do: it enforces **at most** one inventory row, never
**at least** one. A variant with no stock row is legal SQL. Keeping every variant supplied with one
is an application invariant, upheld in the seed script and in product creation.

**CHECK constraints** — eight, in two groups.

Quantity guards. These are the database-level half of Section 6.7's requirement that stock can
never go negative; the row lock in checkout is the other half:

| Table         | Rule                      |
| ------------- | ------------------------- |
| `inventory`   | `quantity_available >= 0` |
| `inventory`   | `quantity_reserved >= 0`  |
| `cart_items`  | `quantity > 0`            |
| `order_items` | `quantity > 0`            |
| `payments`    | `amount > 0`              |

Enum-like text columns. Section 6.3 specifies `text` rather than a PostgreSQL `ENUM` type, so the
permitted values are enforced with a CHECK:

| Column           | Permitted values                                                   |
| ---------------- | ------------------------------------------------------------------ |
| `users.role`     | `customer`, `admin`                                                |
| `addresses.type` | `shipping`, `billing`                                              |
| `orders.status`  | `pending`, `paid`, `shipped`, `delivered`, `cancelled`, `refunded` |

**`products.unit_of_measure` is deliberately left unconstrained.** It looks like an oversight beside
the columns above and is not one: it is a Section 1.1 reusability seam. A CHECK restricting it to
`each/lb/kg/oz/g` would force a schema migration on any cloned store selling in a unit not on that
list, which is exactly what the seam exists to prevent. It is validated at the API boundary instead.

### 6.6 Indexes

An index speeds up lookups at a small cost to writes. Add indexes on columns you filter or join by:

**PostgreSQL does not automatically index foreign key columns.** This surprises most people. A
foreign key requires an index on the _referenced_ (parent) column — which the primary key already
supplies — but creates nothing on the _referencing_ (child) column. That is why nearly every entry
below is an FK: without them, "find this order's items" is a sequential scan. Unique constraints
_do_ create an index, which is why `users.email` needs no separate one.

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

Concurrency matters at any real traffic level: two people may buy the last item at the same moment.
Protect the inventory decrement so stock can't go negative — either a row lock
(`SELECT ... FOR UPDATE`) inside the transaction, or a conditional update that only succeeds when
enough stock remains. Implement this in `services/checkout` and call it out to Claude Code so it
is not overlooked.

### 6.8 Migrations

A migration is a versioned, repeatable schema change. Use **Alembic**: every change (new table,
column, or index) becomes a migration file committed to Git, applied identically to local and RDS,
and reversible if something goes wrong. Never edit the production database by hand — always through
a migration.

**Autogenerate does not DIFF CHECK constraints on an existing table.** `alembic revision
--autogenerate` compares models against the database and finds added tables, columns, indexes, and
unique constraints. It will not notice a `CheckConstraint` **added to a table that already exists**,
and will silently produce an empty migration.

The exception is worth knowing so you do not hand-write constraints unnecessarily: a **new** table
emits its `CheckConstraint`s correctly, because `create_table` serialises every constraint on the
table object rather than diffing anything. Migrations `be02c29a9f3c` and `8350f895449a` are both
examples. `alembic check` uses the same comparison logic, so it cannot catch the omission either.
Write them by hand with `op.create_check_constraint()`, with matching `op.drop_constraint(...,
type_='check')` calls in `downgrade()`, and verify against `pg_constraint` rather than trusting
`alembic check`.

**Constraint names come from a naming convention** set on `Base.metadata` in `app/db.py`, producing
`pk_<table>`, `fk_<table>_<column>_<referred_table>`, `uq_<table>_<column>`, `ck_<table>_<name>`,
and `ix_<table>_<column>`. Without it the database invents names that vary by engine and are hard
to predict — and a constraint can only be altered or dropped _by name_. Set this before the first
migration; retrofitting it later means renaming every constraint in the database.

### 6.9 Seeding

Write a script that fills a fresh database with a few categories, sample products and variants
with stock, and one **admin** user (the store owner) so you can log into the vendor portal
immediately. This makes local development and testing repeatable.

Seed the **T-shirt store** (the default build): a couple of categories, products with
`unit_of_measure = 'each'`, and variants whose `attributes` carry `{"size": ..., "color": ...}`.
Include at least one product with no variants, so the "single item store" path is exercised from
day one rather than discovered later.

Seed **one customer with a shipping and a billing address** alongside the admin. This is not a test
fixture — task 8's tests build their own data so they never depend on seed state. It is here because
`orders.shipping_address_id` and `billing_address_id` are `NOT NULL`: without a saved address there
is no way to walk checkout by hand at all, which is precisely what this section says the seed is
for. The rule of thumb: seed whatever a developer needs to exercise the app manually, and no more.

**Seed data must satisfy the same validation the API enforces.** The seed writes through the ORM
and so bypasses the Pydantic schemas — which makes it easy to create a row the API itself would
reject, leaving two disagreeing definitions of what is valid. This happened: the admin was seeded
with an `@…​.local` address, which `POST /auth/register` refuses because `.local` is a reserved
special-use domain. The account existed and could never be logged into. When seeding a record type
the API also creates, check that the API would accept it.

### 6.10 Backups and Recovery

Locally, know how to dump and restore with `pg_dump` / `pg_restore`. On RDS, enable **automated
backups** and **point-in-time recovery**, and take a manual snapshot before risky changes. Test a
restore at least once before launch — an untested backup isn't a backup.

### 6.11 Local vs. AWS RDS

Develop against local PostgreSQL via Docker, then point the same app at **RDS PostgreSQL** in
production by swapping the connection string. Because you use migrations, the schema is identical
in both places. At your launch-tier concurrency target (sized per Section 10.1), use **connection
pooling** (SQLAlchemy's pool, plus
**RDS Proxy** in front of the database) so you don't exhaust connections.

---

## 7. AWS Hosting Details

| Need                  | Service                | Notes                                                                                   |
| --------------------- | ---------------------- | --------------------------------------------------------------------------------------- |
| Database              | **RDS (PostgreSQL)**   | Managed Postgres; enable backups; add Multi-AZ before launch                            |
| API hosting           | **ECS (Express Mode)** | Runs your container on Fargate with minimal setup — AWS App Runner's official successor |
| Container registry    | **ECR**                | Where your built API image is pushed before Express Mode deploys it                     |
| Web hosting           | **ECS (Express Mode)** | Amplify supports Next.js 12-15; this app is on 16. See the note below                   |
| Images / static files | **S3 + CloudFront**    | Store product images in S3, serve via the CDN                                           |
| DNS + HTTPS           | **Route 53 + ACM**     | Domain plus free TLS certificates                                                       |
| Secrets               | **Secrets Manager**    | DB password, Stripe keys — out of Git                                                   |
| Permissions           | **IAM**                | Least-privilege roles; a dedicated user for daily work                                  |
| Networking            | **VPC**                | Keep RDS private; only the API reaches it                                               |
| Monitoring            | **CloudWatch**         | Logs, metrics, alarms — Express Mode wires this up automatically                        |

**A note on Amplify Hosting:** the original version of this plan specified Amplify Hosting for the
web app. Amplify Hosting's compute SSR provider supports **Next.js 12 through 15**, and this project
runs **16.3.0** — AWS's own migration page states "Currently, the Amplify Hosting compute SSR
provider supports Next.js version 15." So the storefront is deployed as a **second ECS Express Mode
service** instead.

The cost argument makes it a comfortable substitution rather than a compromise: **up to 25 Express
Mode services in one VPC share an Application Load Balancer**, so the web app adds Fargate capacity
and no second ALB. What it gives up is Amplify's git-push CI/CD and PR previews — deploys are manual
until a pipeline exists. Revisit if AWS ships Next.js 16 support; the app would move back with no
code change.

**A note on App Runner:** the original version of this plan specified App Runner for API hosting.
AWS closed App Runner to new customers on April 30, 2026 and now directs new workloads to **ECS
Express Mode** instead. This isn't a step down — Express Mode runs on the same Fargate compute
App Runner used, and automates the same things (load balancer, HTTPS, scaling, CloudWatch). The
one real difference: Express Mode deploys **pre-built container images only**, not source repos —
which is why Phase 6 now has an explicit "push to ECR" step before deployment.

**Defined upgrade path:** deploy the API with **ECS Express Mode**. Because Express Mode already
runs on Fargate underneath its simplified interface, there's no service migration if you outgrow
it — if the Phase 7 load test shows you need finer control (custom task placement, advanced ALB
rules) than Express Mode's automation allows, you configure standard **ECS Fargate** directly,
same service, training wheels off. Do not add that complexity earlier.

---

## 8. Authentication and Security

- Hash passwords with **bcrypt**; never store or log raw passwords.
- Issue **JWT** access tokens on login; clients send them on each request. This is identical for
  web and mobile.
- Include the user's **role** in the token so the vendor portal can require `admin`.
- **The role claim is for clients, not for server-side authorisation.** It lets the web app decide
  whether to render `/admin` without an extra request. The API reads the role from the _database_
  on every request, so a role changed there takes effect immediately rather than when the token
  expires. Never authorise from the token's claim alone.
- **Registration always creates a `customer`.** The registration schema has no `role` field at all
  — omitted rather than validated — so a request body has no way to ask for an admin account.
  Admins are created deliberately (the seed script, or an admin-only endpoint).
- **Authentication failures must be indistinguishable.** An unknown email and a wrong password
  return the same 401 with the same body _and take the same time_. Identical bodies alone are not
  enough: if a missing user short-circuits before the password check, the response is ~100ms faster
  and that gap enumerates which addresses have accounts. Run a real hash comparison against a dummy
  hash when no user matches.
- Distinguish **401 from 403**. Missing, malformed, or expired credentials are 401 ("who are you?");
  a valid identity without permission is 403 ("I know who you are, and no"). Note that FastAPI's
  `HTTPBearer` returns 403 for a missing header by default — set `auto_error=False` and raise 401.
- **Password reset tokens are stored hashed, never raw** (Phase 4.5). The raw token lives only in
  the emailed link. They are single-use and expire in ~30 minutes, and `POST /auth/forgot-password`
  returns the _same_ response whether or not the address exists — the same anti-enumeration rule as
  login, applied to the one other endpoint that takes an email address.
- **Changing a password sets `password_changed_at`**, and tokens issued before that instant are
  rejected. Without refresh tokens this is the only way to end sessions on other devices after a
  compromise, and it costs one column because `get_current_user` already reads the user row.
- **Suspension is enforced on every request, not just at login.** `is_active = false` is checked in
  `get_current_user`, so an open session stops working immediately rather than when its token
  expires.
- **Two-factor is TOTP and optional** (Phase 4.5), strongly encouraged for the admin account.
  Recovery codes are bcrypt-hashed and single-use, because a recovery code is a credential. Note
  the local tradeoff: `totp_secret` sits in the database in plain form, which is acceptable on a
  development machine and should move behind KMS or Secrets Manager when this is real.
- **Accounts are anonymised, not deleted.** `orders.user_id` is `NOT NULL` with `NO ACTION`, so
  deleting a customer who has ordered is impossible without destroying order history. Scrubbing the
  personal fields in place satisfies an erasure request while keeping the invoices tax rules
  require. Addresses follow the same rule for the same reason: those an order references survive
  (the order holds no snapshot, so the row _is_ the shipping record), and address-book entries no
  order used are deleted.
- **Consequential actions are recorded, and the record is append-only** (Phase 4.5). Suspension,
  role changes, anonymisation, admin-triggered resets, and the customer's own credential changes all
  write an `audit_events` row **in the same transaction as the action** — so an action cannot commit
  without its record, and a record cannot exist for an action that rolled back. `actor_email` is
  snapshotted rather than joined, because anonymising an admin must not erase who they were when
  they acted. The audit trail never stores credentials of any kind.
- **Impersonation is not a v1 feature, and the audit trail is why.** "Sign in as this customer"
  makes an admin's actions indistinguishable from the customer's in every table that records them,
  which is precisely the attribution the audit trail exists to provide. It is also the single
  highest-value endpoint in a system — it mints a valid token for an arbitrary user, so a flaw in it
  is total account takeover rather than one leaked row. Build it only with an audit trail, a visible
  banner, a time limit, and an explicit decision about what an impersonated session may do.
- **No refresh tokens in v1.** A deliberate omission, not an oversight: access tokens expire after
  `ACCESS_TOKEN_EXPIRE_MINUTES` and the user logs in again. Revisit if session length becomes a
  real complaint.
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
- **Tests run against a separate `manitou_test` database, never the development one.** `pytest`
  drops and recreates it, builds the schema by running Alembic against it — which re-proves the
  migrations work from scratch on every session — and truncates every table between tests.
  Truncation rather than transaction rollback, because `create_order_from_cart` calls `commit()`
  and hiding a real commit inside a rolled-back outer transaction needs nested savepoints whose
  failures look like application bugs.
- **Tests build their own data.** Nothing may depend on `seed.py` having run; a test that only
  passes because the store happened to be seeded is not testing anything. `seed.py` exists so a
  developer can use the app by hand, not to supply fixtures.
- **A guard you have never watched fail is not a guard.** The concurrency test must be verified by
  temporarily removing `SELECT ... FOR UPDATE` and confirming it fails — a threaded test can
  otherwise pass simply because the threads happened to serialise. Same principle applies to
  constraint tests: make the constraint reject something before trusting it.
- **Account and credential paths get the same scrutiny as money paths** (Phase 4.5). Specifically:
  a reset token works exactly once; an expired token is refused; `forgot-password` is
  indistinguishable for a known and an unknown address; a suspended user's _existing_ session stops
  on the next request, not at token expiry; a password change invalidates tokens issued earlier;
  and the last admin cannot suspend or demote themselves. Each of these is a guard, so each must be
  watched failing before it is trusted.
- **The audit trail gets tested as a guard too.** Prove the event and the action share a
  transaction by forcing the action to fail after the event is queued and confirming _neither_
  lands. Prove append-only by attempting an `UPDATE` and a `DELETE` on `audit_events` from `psql`
  and watching the trigger refuse both. An audit log nobody has tried to tamper with is not known
  to be tamper-proof.
- Load test against the **launch-tier concurrency target from Section 10.1**, not a flat assumed
  number, and tune RDS size and pool settings to that result.

---

## 10.1 Sizing a Real Concurrency Target (don't assume a round number)

**A flat "~1,000 concurrent users" is not a launch requirement — it's a scale milestone that has to
be earned, and it needs to be derived, not assumed.** Round numbers like 1,000 feel like a safe
planning default, but they carry an implicit workload and business size that may be wildly wrong
for what you're actually building. Size it properly instead, in four steps:

**1. Find the addressable market.** Population of the area served → households → the fraction that
plausibly buys this category online at all. For a statewide grocery store, that might be
~30–35% of households. For a niche T-shirt store, it might be a mailing list size or social
following, not a population figure at all — the method is the same, the inputs differ per store type.

**2. Apply a realistic capture rate for where the business actually is.** A new, single-vendor
entrant does not start with meaningful market share. Model growth in stages:

| Stage                            | Realistic share of the addressable market | What changes it                       |
| -------------------------------- | ----------------------------------------- | ------------------------------------- |
| Early launch (first 6–12 months) | ~0.3–0.5%                                 | Little to no brand recognition yet    |
| Established (year 2–3)           | ~2–3%                                     | Real marketing spend, word of mouth   |
| Mature presence (multi-year)     | ~5–8%                                     | Meaningful competitor in its category |

**3. Convert active customers into visits, using actual behavior, not requests.**
`visits/month ≈ active customers × orders/month × visits per order` (browsing, list-building, and
cart revisits typically produce several visits per completed order, not one).

**4. Convert visits into concurrent users**, following the standard capacity-planning formula:
`concurrent users ≈ peak-hour visits × average session duration ÷ 60`. Peak-hour visits are
usually a concentrated slice of the peak day's total (commonly ~10–15% for a store with a defined
busy window), not spread evenly across 24 hours.

**Worked example (Florida statewide grocery delivery, illustrating the method):**

| Stage                | Active customers | Peak-day visits | Peak-hour concurrent users |
| -------------------- | ---------------- | --------------- | -------------------------- |
| Early launch         | ~10,000–17,000   | ~4,000–4,800    | **~80–90**                 |
| Established regional | ~68,000–100,000  | ~30,000         | **~500–550**               |
| Mature statewide     | ~170,000–270,000 | ~75,000–88,000  | **~1,250–1,400**           |

The finding worth internalizing: **1,000+ concurrent is roughly what a genuinely successful,
multi-year, statewide-recognized business sees at peak — not a reasonable day-one target.** A real
launch for a store like this is closer to 80–100 concurrent, and that number should drive Phase 7's
load test and RDS sizing, not the round-number milestone.

**Why this matters more for grocery-type stores than the default T-shirt build:** real-time
inventory checks against a specific warehouse per delivery address, plus delivery-slot booking
against a genuinely limited resource, make grocery traffic far more write-heavy and backend-costly
per concurrent user than catalog browsing. The _concurrency number_ isn't the whole capacity
picture — the traffic mix behind it (cached reads vs. writes) matters just as much. Re-run this
sizing exercise for whichever store type you actually clone Manitou into; the inputs in step 1 and
the write-heaviness in this last point are what change between a T-shirt store and a grocery store,
not the method.

**Practical rule for this project:** size and load-test against the **early-launch tier** for
whatever store you're actually building. Treat the higher tiers as documented future milestones to
revisit once real usage data exists — don't architect Phase 6/8 around a number with no grounding
in an actual addressable market and capture rate.

### The actual number for ImprimaPress (Phase 7 task 1, done 2026-08-31)

Cold launch: no mailing list, no existing following. So step 1's input is **reach**, not a
population — the method is unchanged, the inputs are what differ per store type.

| Step | Input | Result |
| --- | --- | --- |
| 1. Reachable in the first 6 months | personal network ~200, onward sharing ×2, organic search ≈ 0 on a domain with no history or backlinks | **~500 people** |
| 2. Visits and conversion | ~20% ever click through; ~2% of visitors buy, with no reviews and no brand yet | ~100 visitors, **~2–5 customers** |
| 3. Visits per month | ~100 uniques × ~1.8 visits, over 6 months | **~30/month** |
| 4. Peak-hour concurrency | launch day ~90 visits, ~25% in the peak hour, ~3-minute sessions → 22 × 3 ÷ 60 | **≈ 1** |

| Scenario | Peak-hour concurrent users |
| --- | --- |
| Ordinary day, first months | **< 1** |
| Launch day | **~1** |
| A post that unexpectedly does 10× | **~11** |
| The mature-statewide milestone above, for contrast | ~1,250–1,400 |

**The sized target is about one concurrent user** — three orders of magnitude below the round
number this section exists to argue against, and roughly 100× below what the deployed
infrastructure already serves.

**This changes what the load test is for.** "Can it handle the target" would return green and mean
nothing. The question worth asking is **where it breaks**, so the answer is a headroom figure — it
degrades at N, launch needs 1, a viral day needs 11 — which is what makes later capacity decisions
evidence rather than nerves. Re-run this whole exercise for any store cloned from this repo; a
grocery clone's write-heavy traffic changes the answer even at the same concurrency.

---

## 11. Support for Your AWS Cloud Practitioner Goal

The exam is broad and conceptual. Building on AWS gives you hands-on context for its topics:

- **RDS** → managed databases, backups, Multi-AZ.
- **S3 + CloudFront** → object storage and content delivery.
- **ECS / Fargate / EC2** → compute options and the shared-responsibility model.
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
4. **Account management (Phase 4.5):** password reset, customer self-service settings, optional
   TOTP two-factor, and the vendor's customer list with suspend and anonymise. A store that cannot
   help a customer who forgot their password is not launchable, so this is v1 scope, not a
   follow-on.
5. Stripe test-mode checkout.
6. **Fulfilment and tracking (Phase 5.5):** a carrier and tracking number recorded against every
   dispatch, an append-only delivery event log, and a tracking timeline the customer can see. A
   store that cannot evidence a delivery cannot answer a chargeback, so this is v1 scope, not a
   follow-on — for the same reason password reset was.
7. Deployed on AWS.

After v1 launches, add reviews, richer search, sales reporting, and the mobile apps (Phase 8).

**Deliberately not in v1:**

- **Social / federated sign-in** ("Continue with Google", Apple, GitHub). Not a button — a second
  identity model. `users.password_hash` is `NOT NULL`, and five operations re-check the password to
  re-authenticate: change password, change email, close account, disable two-factor, and admin
  anonymise. A passwordless account needs a separate answer for each of those before the first
  provider is wired up. Linking a provider to an existing account by email address is also an
  account-takeover route unless the provider's `email_verified` claim is required _and_ the link is
  confirmed by the account holder: otherwise someone who registers `victim@gmail.com` with a
  password first inherits the victim's later Google sign-in. Each provider is additionally an
  external account, a consent screen, and — for Google in production — an app review. Revisit
  after v1 as its own phase, not as an addition to an existing one.
- **Guest checkout.** Accounts are required to buy, deliberately. `orders.user_id` is `NOT NULL`
  with `NO ACTION`, and that single constraint is what makes order history, "anonymise never
  delete", and the audit trail's actor column work. Supporting guests means a nullable `user_id`
  plus a contact-details snapshot on the order, which weakens the anonymisation rule — an order
  with no user row is a personal record with nothing to scrub. The conversion cost of forcing
  registration is real and known; the trade is accepted for v1 and worth revisiting once Phase 5
  makes conversion measurable.

---

## 13. Glossary

- **API (Application Programming Interface)** — the backend service clients call to read/write data.
- **ORM (Object-Relational Mapper)** — library that maps database rows to code objects (SQLAlchemy).
- **Migration** — a versioned, repeatable schema change (Alembic).
- **Primary key (PK)** — column that uniquely identifies a row.
- **Foreign key (FK)** — column referencing another table's PK.
- **Index** — structure that speeds up lookups on a column.
- **Transaction** — a group of database (DB) operations that all succeed or all fail together.
- **Normalization** — organizing data so each fact is stored once.
- **JWT (JSON Web Token)** — a signed token proving who a user is on each request.
- **JOIN** — a SQL operation combining rows from related tables in a query.
- **SKU (Stock Keeping Unit)** — a unique code per sellable variant.
- **IAM (Identity and Access Management)** — the AWS service controlling who can do what.
- **VPC (Virtual Private Cloud)** — a private, isolated network within AWS.

**Other acronyms used elsewhere in this plan, for reference:**

- **SQL (Structured Query Language)** — the language used to query and modify relational databases like PostgreSQL.
- **CRUD (Create, Read, Update, Delete)** — the four basic operations an API performs on data.
- **REST (Representational State Transfer)** — the API design style this backend follows: resources addressed by URL, manipulated with standard HTTP methods.
- **JSON (JavaScript Object Notation)** — the text format APIs use to send and receive structured data.
- **JSONB** — PostgreSQL's binary-optimized storage format for JSON, used for `product_variants.attributes` (Section 6).
- **HTTP / HTTPS (HyperText Transfer Protocol / … Secure)** — the protocol clients and the API communicate over; HTTPS adds TLS encryption.
- **TLS (Transport Layer Security)** — the encryption protocol behind HTTPS; ACM issues the certificates that enable it.
- **YAML (YAML Ain't Markup Language)** — the indentation-based format used by `docker-compose.yml` and GitHub Actions workflow files.
- **CI/CD (Continuous Integration / Continuous Deployment)** — automatically testing and deploying code on every push (GitHub Actions).
- **ACID (Atomicity, Consistency, Isolation, Durability)** — the transaction guarantees PostgreSQL provides, central to the checkout logic in Section 6.7.
- **CDN (Content Delivery Network)** — a network of edge servers that cache and serve static content close to the user (CloudFront).
- **DNS (Domain Name System)** — translates a domain name into a server address (Route 53).
- **ACM (AWS Certificate Manager)** — issues the free TLS certificates used for HTTPS.
- **RDS (Relational Database Service)** — AWS's managed PostgreSQL hosting.
- **ECS (Elastic Container Service)** — AWS's container-hosting service; **Express Mode** is its simplified deployment path (Section 7).
- **ECR (Elastic Container Registry)** — where the built Docker image is stored before ECS deploys it.
- **ALB (Application Load Balancer)** — distributes incoming traffic across running containers.
- **S3 (Simple Storage Service)** — AWS's object storage, used here for product images.
- **EC2 (Elastic Compute Cloud)** — AWS's raw virtual server offering, mentioned for contrast with managed options like RDS and ECS.
- **RPS (Requests Per Second)** — the throughput metric used for capacity planning in Section 10.1.
- **SRE (Site Reliability Engineering)** — the discipline behind the capacity-planning approach cited in Section 10.1.
