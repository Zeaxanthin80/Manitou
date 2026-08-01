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
  make decisions, and review results. Claude Code can explain *how*, but your hands are on it.
- **[You + Claude Code]** — You work together. Claude Code explains the concept and drafts the
  code; you read it, ask questions, adjust, and only then save it. You must understand each
  change before moving on. This is deliberately not "let the agent do it."

Work through tasks in order. Check each box as you finish.

---

## 1. Project Overview

**What we're building:** an online store for a single vendor (the store owner), reachable from:

- A **website** (customer-facing storefront plus a vendor/admin portal), and
- **Native mobile apps** (Android in Kotlin, iOS in Swift), added after the website works.

**Fixed requirements:**

- One shared database so products, users, inventory, and orders are managed once and reflected everywhere.
- Support ~1,000 concurrent users.
- Payments via **Stripe**.
- Host on **AWS** (this also supports your AWS Certified Cloud Practitioner goal).
- Build order: **database → backend API → website → payments → deploy → mobile apps.**

**Definitions used throughout:**

- "Single vendor" means one seller but many customer accounts. The vendor portal is an admin
  area gated by an `admin` role, not a separate multi-tenant system.
- The website and mobile apps are separate clients that all use one backend (Section 2).

---

## 2. Core Architecture: One API, One Database

Your requirement — manage products and users once, everywhere — is met by one rule: **clients
never touch the database directly. Every client goes through one backend API.**

```
        ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────────┐
        │  Web store   │   │ Vendor portal│   │  iOS (Swift) │   │Android(Kotlin)│
        │  (browser)   │   │  (browser)   │   │              │   │              │
        └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
               │                  │                  │                  │
               └────────────┬─────┴──────────────────┴──────────────────┘
                            │  HTTPS / JSON (REST API)
                     ┌──────▼───────┐
                     │  Backend API  │  ← the ONLY thing that talks to the DB
                     │  (FastAPI)    │     handles auth, validation, business rules
                     └──────┬───────┘
                            │  SQL (via SQLAlchemy)
                     ┌──────▼───────┐
                     │  PostgreSQL   │  ← single source of truth
                     │  (AWS RDS)    │
                     └──────────────┘
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

| Layer | Technology | Reason it was chosen |
|---|---|---|
| Database | **PostgreSQL** | Strong transactions for orders/payments; good JSON support; open source |
| Backend API | **Python 3.12+ with FastAPI** | You know Python; async serves ~1k concurrent well; auto-generated API docs |
| Python isolation | **`venv` (built-in) + `pip` + `requirements.txt`** | Per-project packages; standard tooling; matches what the Docker image installs |
| DB access | **SQLAlchemy + Alembic** | Python-to-SQL mapping plus safe, versioned schema migrations |
| Validation | **Pydantic** | Enforces request/response shapes; ships with FastAPI |
| Web frontend | **Next.js (React)** | You know JS/HTML/CSS; server rendering helps store SEO |
| Vendor portal | **Part of the web app**, gated by an `admin` role | One codebase, one API, one auth system |
| Android | **Kotlin (native)** | You already know it |
| iOS | **Swift (native)** | You already know it |
| Payments | **Stripe** | Strong web + mobile SDKs; handles the PCI burden |
| Auth | **JWT tokens** issued by the API, passwords hashed with **bcrypt** | Identical flow for web and mobile |
| Containerization | **Docker** | Same environment locally and on AWS |
| CI/CD | **GitHub Actions** | You know Git; automate tests and deploys |
| API hosting | **AWS App Runner** | Simplest managed way to run the container (upgrade path defined in Section 7) |
| Web hosting | **AWS Amplify Hosting** | Runs Next.js with built-in CI/CD from your Git repo |
| Database hosting | **AWS RDS (PostgreSQL)** | Managed Postgres with backups and failover |
| Images / static files | **AWS S3 + CloudFront** | Store product images; serve them via CDN |
| DNS + HTTPS | **AWS Route 53 + ACM** | Domain and free TLS certificates |
| Secrets | **AWS Secrets Manager** | DB password and Stripe keys, kept out of Git |
| Monitoring | **AWS CloudWatch** | Logs, metrics, alarms |

---

## 4. Repository Structure

One repository holds everything so the whole system is discoverable:

```
store/
├── CLAUDE.md              # concise guidance for Claude Code
├── PROJECT_PLAN.md        # this file — the master plan
├── README.md              # human-facing setup and run instructions
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

| | Virtual environment (`.venv`) | Docker |
|---|---|---|
| Isolates | Python packages for this project | The entire runtime (OS, Python, system libraries) |
| Used for | Writing code: editor autocomplete, `pytest`, `alembic`, running the API locally | Running PostgreSQL locally; packaging the API for AWS |
| Lives | On your machine, in `backend/.venv/` | In containers |
| Shipped to AWS | No | Yes |

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
*which Python version* is installed, a separate layer from the venv (*which packages*) and Docker
(*which whole runtime ships*). Decision rule: run `python3 --version` in Phase 0 step 2. If it
reports 3.12 or higher, skip pyenv entirely. If it reports lower, install pyenv (macOS/Linux) or
install 3.12 from python.org (Windows) rather than modifying your system Python — on macOS
especially, other OS tooling depends on the bundled version. Either way, the venv is still created
on top of whichever interpreter you end up with, and the Dockerfile pins the production version
independently in Phase 6.

**Environment variables:** the backend reads configuration (database URL, JWT secret, Stripe keys)
from a `.env` file that is never committed. Commit a `.env.example` listing the required variable
names with placeholder values so the setup is reproducible.

---

## 5. Build Phases (with tasks)

Do the phases in order. Do not start mobile (Phase 7) until the website works end to end.

### Phase 0 — Foundations

1. **[You]** Install **Git**. Sign in to (or create) your **GitHub** account. Create a new
   repository named `store`, then clone it to your machine.
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

1. **[You + Claude Code]** Create the Next.js project that consumes the API.
2. **[You + Claude Code]** Build the pages: catalog/home, category, product detail, cart,
   checkout, account, and order history.
3. **[You + Claude Code]** Implement the auth flow (login/register) and store the JWT securely.
4. **[You]** Test the storefront in a browser on both a PC and a phone to confirm it's responsive.

### Phase 4 — Vendor Portal

1. **[You + Claude Code]** Build the `/admin` section, with access gated by the `admin` role in the JWT.
2. **[You + Claude Code]** Product management (create/edit/delete, upload images — wired to S3 in Phase 6).
3. **[You + Claude Code]** Inventory management (stock levels and reorder alerts).
4. **[You + Claude Code]** Order dashboard (view orders and advance status: paid → shipped → delivered).
5. **[You + Claude Code]** A simple sales/inventory summary view.

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

1. **[You + Claude Code]** Android (Kotlin): auth, catalog, product detail, cart, checkout with
   the Stripe Android SDK, and order history — all against the existing API.
2. **[You + Claude Code]** iOS (Swift): the same feature set with the Stripe iOS SDK.
3. **[You]** Test both apps end to end against your deployed backend.

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
2. **Describe how they relate** (an order *has many* items; a product *belongs to* a category).
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
| is_active | boolean | hide products without deleting them |
| created_at | timestamptz | |

**product_variants**
| Column | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| product_id | bigint | **FK** → products.id |
| sku | text | unique — stock keeping unit |
| variant_name | text | e.g., "Large / Red" |
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

| cart_items | Type | Notes |
|---|---|---|
| id | bigint | **PK** |
| cart_id | bigint | **FK** → carts.id |
| variant_id | bigint | **FK** → product_variants.id |
| quantity | integer | |

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
key and nothing else. The schema above is in 3NF. The one deliberate exception is the price/name
snapshot on `order_items` — intentional denormalization for historical accuracy, which is standard.

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

| Need | Service | Notes |
|---|---|---|
| Database | **RDS (PostgreSQL)** | Managed Postgres; enable backups; add Multi-AZ before launch |
| API hosting | **App Runner** | Runs your container with minimal setup |
| Web hosting | **Amplify Hosting** | Runs Next.js with CI/CD from your Git repo |
| Images / static files | **S3 + CloudFront** | Store product images in S3, serve via the CDN |
| DNS + HTTPS | **Route 53 + ACM** | Domain plus free TLS certificates |
| Secrets | **Secrets Manager** | DB password, Stripe keys — out of Git |
| Permissions | **IAM** | Least-privilege roles; a dedicated user for daily work |
| Networking | **VPC** | Keep RDS private; only the API reaches it |
| Monitoring | **CloudWatch** | Logs, metrics, alarms |

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
