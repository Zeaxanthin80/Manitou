# Phase 0 Journal — Foundations

A complete record of Phase 0: every command run, every file and directory created, and the reason
each one exists. This is written to be **replayable** — someone starting from an empty repo can
follow it top to bottom and end up exactly where we ended up.

## How to read this

Each step carries the tag it has in `PROJECT_PLAN.md`:

- **[You]** — the owner did this personally: accounts, installs, running commands, decisions.
- **[You + Claude Code]** — concept explained and code drafted together, reviewed before saving.

Within each step:

- **Concept** — why the step exists and what it teaches. Read this even when replaying.
- **Commands** — verbatim, labeled with who ran them.
- **Created** — each file or directory, and its purpose.
- **Verification** — how we knew it worked, with the output actually observed.

> **A note on accuracy.** Steps 4–14 are transcribed from a working session and reflect commands
> that genuinely ran and output that was genuinely returned. Steps 1–3 were completed by the owner
> *before* that session began, so those commands were never observed directly — they are
> reconstructed from the plan and from the resulting repository state, and are marked as such.

---

## Where Phase 0 ended

Final repository state (git-ignored paths marked):

```
Manitou/
├── .claude/
│   └── agents/
│       ├── code-reviewer.md
│       └── explainer.md
├── .gitignore
├── CLAUDE.md
├── PROJECT_PLAN.md
├── README.md
├── docker-compose.yml
├── docs/
│   └── phase-0-journal.md          ← this file
├── backend/
│   ├── .env                        ← git-ignored (real local secrets)
│   ├── .env.example
│   ├── .venv/                      ← git-ignored (virtual environment)
│   ├── requirements.txt
│   ├── alembic/
│   │   └── .gitkeep
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── main.py
│   │   ├── models/.gitkeep
│   │   ├── routers/.gitkeep
│   │   ├── schemas/.gitkeep
│   │   └── services/.gitkeep
│   └── tests/
│       └── .gitkeep
├── web/
│   └── .gitkeep
├── mobile-android/
│   └── .gitkeep
├── mobile-ios/
│   └── .gitkeep
└── infra/
    └── .gitkeep
```

Working state at the end of Phase 0: PostgreSQL running in Docker, FastAPI running on the host in
the venv, and `GET /health` returning `{"status":"ok"}` only when the database is genuinely
reachable.

### Commit map

Each Phase 0 commit, so any step can be inspected with `git show <sha>`:

| Step(s) | Commit | Subject |
|---|---|---|
| 4 | `117dd62` | Added project directories and `.gitkeep` files to maintain directory structure across multiple backend and mobile directories |
| 5, 8 | `9ef6561` | Add `.gitignore` and `requirements.txt` for project setup |
| 9, 10 | `d03f805` | Add `.env.example` and `docker-compose.yml` for database configuration |
| 11, 12 | `f3b8c7c` | Add initial application structure with configuration, database setup, and health check endpoint |
| 13 | `579ac40` | Add `README.md` with project overview, prerequisites, and local setup instructions |

Two earlier commits (`645efd5`, and the `de86389`/`610066a`/`be132fb`/`7402bdf` chain) predate
step 4 and cover the initial docs plus the owner's own `.claude/agents/` files — not part of the
Phase 0 task list.

### Versions this phase was built against

| Tool | Version observed |
|---|---|
| Python | 3.12.3 |
| Docker Engine | 29.7.1 |
| Docker Compose | v5.1.4 |
| PostgreSQL image | `postgres:16-alpine` |

Python package versions are pinned exactly in `backend/requirements.txt` (Appendix A).

---

## Step 1 — Git, GitHub, and the repository **[You]**

> Completed before the working session. Commands below are the canonical form, reconstructed —
> not a transcript.

### Concept

Everything else depends on version control existing first. The repository is created on GitHub
and cloned locally, so there is a remote backup and a history from the very first file. Committing
early and often is a habit this project deliberately builds (see step 14).

### Commands *(reference)*

```bash
git --version                                    # confirm Git is installed
git clone https://github.com/<your-user>/Manitou.git
cd Manitou
```

### Result

A local clone at `/home/jose/Coding/Manitou` tracking a GitHub remote on branch `main`.

---

## Step 2 — Install the toolchain **[You]**

> Completed before the working session. Reconstructed.

### Concept

Phase 0 needs five separate tools, each doing a distinct job. Installing them all up front means
no step later stalls waiting on a download. Note that these install to **system locations outside
the repo**, which is why this step safely precedes `.gitignore` (step 5) — nothing here writes
into the project folder.

### Commands *(reference)*

```bash
python3 --version        # must report 3.12 or higher
node --version           # Node.js LTS
docker --version
psql --version           # or verify your GUI client (TablePlus / pgAdmin) opens
git --version
```

### What each tool is for

| Tool | Purpose in this project |
|---|---|
| Python 3.12+ | Runs the FastAPI backend |
| Node.js LTS | Runs the Next.js web app (Phase 3) |
| Docker Desktop | Runs local PostgreSQL now; packages the API for AWS in Phase 6 |
| PostgreSQL client | Inspecting the database by hand — important for learning SQL in Phase 1 |
| Editor + Claude Code | Writing and reviewing the code |

### Note on Python versions

`PROJECT_PLAN.md` §4.1 sets the decision rule: if `python3 --version` reports 3.12+, skip `pyenv`
entirely. This machine reported **3.12.3**, so no version manager was needed.

---

## Step 3 — Place the planning documents **[You]**

> Completed before the working session. Reconstructed.

### Concept

`PROJECT_PLAN.md` and `CLAUDE.md` go in first so that every subsequent decision has a written
reference. `CLAUDE.md` is deliberately short (conventions and guardrails, loaded into every
session); `PROJECT_PLAN.md` is the exhaustive ~860-line roadmap, read on demand.

### Commands *(reference)*

```bash
git add PROJECT_PLAN.md CLAUDE.md
git commit -m "first commit"
git push
```

### Created

| File | Purpose |
|---|---|
| `PROJECT_PLAN.md` | The master plan: architecture, final tech stack, all 9 phases, full DB schema |
| `CLAUDE.md` | Short conventions file: the golden rule, repo layout, working style |

---

## Step 4 — Create the folder structure **[You + Claude Code]**

### Concept

The layout in `PROJECT_PLAN.md` §4 separates the project into pieces that will eventually deploy
separately and use different toolchains:

- **`backend/`** — the FastAPI app. Everything that touches PostgreSQL lives here, and nothing
  outside it ever will. That is the project's golden rule made structural.
- **`web/`** — the Next.js app, holding both the storefront and the `/admin` vendor portal. Kept
  separate because it is a different language and runtime with its own dependency file.
- **`mobile-android/`, `mobile-ios/`** — reserved now, populated in Phase 7.
- **`infra/`** — AWS notes and deployment scripts (Phase 6).

Inside `backend/app/`, the four subfolders mirror the layers of a FastAPI application:
`models/` (SQLAlchemy tables), `schemas/` (Pydantic request/response shapes), `routers/`
(endpoints), `services/` (business logic such as checkout and inventory).

**Why `.gitkeep` files:** Git tracks *files*, not directories. An empty folder simply does not
exist as far as Git is concerned, so it would vanish for anyone cloning the repo. A zero-byte
`.gitkeep` is the conventional placeholder that makes the directory real in version control. Each
one is deleted naturally once actual code lands in that folder.

This step creates **structure only** — no `main.py`, no `requirements.txt` contents. Those belong
to later steps, in order.

### Commands *(Claude Code)*

```bash
mkdir -p backend/app/models backend/app/schemas backend/app/routers backend/app/services \
         backend/alembic backend/tests web mobile-android mobile-ios infra

touch backend/app/models/.gitkeep backend/app/schemas/.gitkeep backend/app/routers/.gitkeep \
      backend/app/services/.gitkeep backend/alembic/.gitkeep backend/tests/.gitkeep \
      web/.gitkeep mobile-android/.gitkeep mobile-ios/.gitkeep infra/.gitkeep
```

### Created

| Path | Purpose |
|---|---|
| `backend/app/models/` | SQLAlchemy table definitions (Phase 1) |
| `backend/app/schemas/` | Pydantic request/response models — validation at the API boundary |
| `backend/app/routers/` | API endpoint groups: products, orders, auth (Phase 2) |
| `backend/app/services/` | Business logic: checkout, inventory, payments |
| `backend/alembic/` | Database migrations (Phase 1) |
| `backend/tests/` | Backend tests (Phase 2, step 8) |
| `web/` | Next.js storefront + `/admin` portal (Phase 3) |
| `mobile-android/` | Kotlin / Jetpack Compose app (Phase 7) |
| `mobile-ios/` | Swift / SwiftUI app (Phase 7) |
| `infra/` | AWS deployment notes and scripts (Phase 6) |

### Verification *(Claude Code)*

```bash
git status --short
find backend web mobile-android mobile-ios infra -type f
```

Ten `.gitkeep` files present; five new untracked directories reported by Git.

---

## Step 5 — Create `.gitignore` **[You + Claude Code]**

### Concept

**Ordering matters here, and it is the reason this step is numbered 5 and not later.** The venv
(step 6) and the installed packages (step 8) write thousands of files directly into the repo
folder. If `.gitignore` does not already exist when that happens, those files show up as untracked
noise and can easily be committed by accident. Once something is committed, deleting it later does
*not* remove it from Git history.

What is excluded and why:

| Pattern | Reason |
|---|---|
| `backend/.venv/` | The virtual environment — machine-specific, rebuilt from `requirements.txt` |
| `__pycache__/`, `*.pyc` | Python bytecode caches, regenerated automatically |
| `.env` | **Real secrets.** Never committed. Applies to nested paths like `backend/.env` too |
| `node_modules/` | Node dependencies — rebuilt from `package.json` (Phase 3) |
| `web/.next/` | Next.js build output (Phase 3) |
| `.DS_Store`, `Thumbs.db` | OS-generated junk files |
| `.vscode/`, `.idea/` | Per-developer editor settings |

Note what is **not** ignored: `.env.example`. It is meant to be committed — see step 10.

`*.pyc` is technically redundant given `__pycache__/`, since that is where modern Python puts
compiled files. It is kept as a harmless belt-and-suspenders line found in most Python templates.

### Created

`/.gitignore` — see Appendix A for full contents.

### Verification *(Claude Code)*

```bash
git status --short
# ?? .gitignore
```

Only the new file appeared; nothing else changed.

---

## Step 6 — Create and activate the virtual environment **[You]**

### Concept

Read `PROJECT_PLAN.md` §4.1 before doing this step — it explains the venv/Docker division of
labor, which is the single most confusing part of the local setup.

Without a virtual environment, `pip install` writes packages into system Python. Two projects
needing different versions of the same library then collide, and there is no reliable way to
reproduce the dependency list. A venv gives this project its own isolated package directory.

**The venv and Docker are both used, and they do different jobs:**

| | Virtual environment (`.venv`) | Docker |
|---|---|---|
| Isolates | Python packages for this project | The whole runtime (OS, Python, system libs) |
| Used for | Writing code: autocomplete, `pytest`, `alembic`, running the API locally | Running PostgreSQL locally; packaging the API for AWS |
| Lives | `backend/.venv/` on this machine | In containers |
| Shipped to AWS | No | Yes |

Day-to-day: **PostgreSQL runs in Docker, the API runs on the host in the venv.** That gives fast
hot-reload and easy debugging while developing. Phase 6 packages the same app into a Docker image
for deployment, installing from the same `requirements.txt`, so the two stay in sync.

### Commands *(owner)*

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python --version
```

### Verification

Shell prompt shows the environment name, and `python --version` reports **3.12.3**.

> **Activation is per-shell.** Every new terminal needs `source backend/.venv/bin/activate` again.
> It is not a global or permanent change.

---

## Step 7 — Point the editor at the venv **[You]**

### Concept

The editor runs its own Python analysis process, entirely separate from the terminal. Until it is
told which interpreter to use, it looks at system Python — which has none of this project's
packages — so `import fastapi` shows as an unresolved error and autocomplete for FastAPI,
SQLAlchemy, and Pydantic does not work.

### Action *(owner)*

Select `backend/.venv/bin/python` as the interpreter. In VS Code: Command Palette →
*Python: Select Interpreter* → choose the `./backend/.venv` entry.

---

## Step 8 — Install backend dependencies **[You + Claude Code]**

### Concept

Six top-level packages, each with a distinct job:

| Package | Job |
|---|---|
| `fastapi` | The web framework — routing, validation, automatic API docs |
| `uvicorn[standard]` | The ASGI server that actually runs the app. `[standard]` adds `uvloop` (faster event loop), `httptools` (faster HTTP parsing), and `watchfiles` (hot-reload) |
| `sqlalchemy` | ORM and SQL toolkit — maps database rows to Python objects |
| `alembic` | Versioned schema migrations (Phase 1) |
| `pydantic-settings` | Reads configuration from `.env` / environment variables. Pydantic itself arrives as a FastAPI dependency; this is the separate package for settings management, used in step 12 |
| `psycopg2-binary` | The PostgreSQL driver SQLAlchemy speaks through. The `-binary` build ships precompiled, so no C compiler toolchain is needed locally |

**`pip freeze` and why the file is longer than six lines.** `requirements.txt` records *every*
installed package with an exact version, including transitive dependencies — libraries pulled in
automatically by the six above (`starlette` under FastAPI, `greenlet` under SQLAlchemy, `Mako`
under Alembic, and so on). Pinning all of them exactly is what makes the environment reproducible:
another machine running `pip install -r requirements.txt` gets a byte-identical package set.

### Commands *(Claude Code)*

```bash
# Confirm the venv is active in *this* shell before installing anything
source backend/.venv/bin/activate
which python        # → /home/jose/Coding/Manitou/backend/.venv/bin/python
python --version    # → Python 3.12.3

pip install fastapi "uvicorn[standard]" sqlalchemy alembic pydantic-settings psycopg2-binary

pip freeze > backend/requirements.txt
cat backend/requirements.txt
```

> **Gotcha hit here.** The owner had activated the venv in their own terminal, but Claude Code's
> shell is a *separate process* — activation does not carry across. Every command needed its own
> `source backend/.venv/bin/activate`. Worth internalizing: venv activation is per-shell state,
> and `which python` is the fastest way to check which interpreter you are actually about to use.

### Created

`backend/requirements.txt` — 26 pinned packages. Full contents in Appendix A.

### Verification

`pip install` reported `Successfully installed` for all 26 packages, and `requirements.txt`
contains the six top-level packages plus their dependencies.

---

## Step 9 — Local PostgreSQL via Docker Compose **[You + Claude Code]**

### Concept

Docker Compose describes containers declaratively in a file, so "start the database" is one
command that behaves identically on every machine — no local PostgreSQL install, no version drift,
and a clean teardown.

Design decisions in this file:

- **`postgres:16-alpine`** — PostgreSQL 16 on Alpine Linux; a much smaller image than the default.
- **Credentials `manitou` / `devpassword`** — these are throwaway, local-only, bound to
  `localhost`, and they sit in plaintext in a committed file *on purpose*. They are not secrets.
  Real credentials (Stripe keys, the production DB password) never appear in Git — see step 10.
- **`ports: "5432:5432"`** — maps the container's PostgreSQL port to the host, so both a GUI
  client and the FastAPI app (running outside Docker) can reach it.
- **Named volume `pgdata`** — PostgreSQL's data directory lives in a Docker-managed volume, so
  data survives `docker compose down` and container restarts. It is destroyed only by an explicit
  `docker compose down -v`.
- **`healthcheck` with `pg_isready`** — a started container is not the same as a *ready* database;
  PostgreSQL takes a moment to initialize. The healthcheck makes `docker compose ps` report
  `healthy` only once it genuinely accepts connections.
- **`restart: unless-stopped`** — the database comes back automatically after a reboot unless it
  was deliberately stopped.

### Commands *(Claude Code)*

```bash
# Pre-flight
docker --version           # → Docker version 29.7.1
docker compose version     # → Docker Compose version v5.1.4

docker compose up -d       # start in detached (background) mode
docker compose ps          # confirm health
```

> **Gotcha hit here.** The first `docker compose up -d` failed:
>
> ```
> unable to get image 'postgres:16-alpine': failed to connect to the docker API at
> unix:///home/jose/.docker/desktop/docker.sock; check if the path is correct and
> if the daemon is running
> ```
>
> The Docker *CLI* being installed is not the same as the Docker *daemon* running. Fix: start
> Docker Desktop, then re-run. Any "cannot connect to the Docker daemon" error means the same
> thing.

### Created

| Artifact | Purpose |
|---|---|
| `/docker-compose.yml` | Declarative definition of the local database (Appendix A) |
| Docker image `postgres:16-alpine` | Pulled from Docker Hub |
| Container `manitou-db-1` | The running database |
| Volume `manitou_pgdata` | Persistent storage for the database files |
| Network `manitou_default` | Compose-managed network for the service |

### Verification

```
NAME           IMAGE                STATUS                    PORTS
manitou-db-1   postgres:16-alpine   Up 20 seconds (healthy)   0.0.0.0:5432->5432/tcp
```

The owner then connected independently with their own PostgreSQL client — the point being to
verify the database from *outside* the application, exactly as a real client would:

```bash
psql -h localhost -p 5432 -U manitou -d manitou
```

| Setting | Value |
|---|---|
| host | `localhost` |
| port | `5432` |
| database | `manitou` |
| user | `manitou` |
| password | `devpassword` |

---

## Step 10 — `.env.example` and `.env` **[You + Claude Code]**

### Concept

Configuration lives **outside** the code. The same application code runs on this laptop and on
AWS; only the values fed in at startup change. That is why credentials are never written into
Python files — a hardcoded key is in Git history forever, and moving between test and live
payments would require a code change.

The two-file pattern (`PROJECT_PLAN.md` §4.2):

| | `.env` | `.env.example` |
|---|---|---|
| Contains | Real working values | Variable names with placeholder values |
| Committed to Git? | **Never** | **Always** |
| Purpose | Makes the app run on your machine | Documents what the app requires |
| Who has it | Each developer creates their own | Shared by everyone via the repo |

Without `.env.example`, someone cloning the repo has no way to discover which variables the app
needs — they would hit a cryptic connection error and have to reverse-engineer the requirements
from source. `.env.example` is the committed, safe-to-read *contract*.

**Why only one variable.** §4.2's illustrative example also lists `JWT_SECRET`,
`STRIPE_SECRET_KEY`, and others — but those belong to Phase 2 (auth) and Phase 5 (payments).
Step 10 asks only for the local database connection string. Variables get added when the feature
that needs them is actually built, following the project rule: *whenever you add a variable to
`.env`, add it to `.env.example` in the same commit.*

**Why both files are identical here.** Normally `.env.example` holds a harmless placeholder, never
a working value. In this specific case the distinction does not apply: `manitou`/`devpassword` are
throwaway local Docker credentials already public in the committed `docker-compose.yml`. So
copying the template produces a working setup with no edits. This will **not** be true for the
Stripe and JWT variables added later — those must always be placeholders in `.env.example`.

**How production differs.** There is no `.env` file on AWS at all. Secrets live in AWS Secrets
Manager, and App Runner injects them into the container's environment at startup. The application
code reads them the same way in both places and never knows the difference — which is the entire
point of the pattern.

### Created

| File | Committed? | Contents |
|---|---|---|
| `backend/.env.example` | Yes | `DATABASE_URL=postgresql://manitou:devpassword@localhost:5432/manitou` |
| `backend/.env` | **No** — git-ignored | Same value |

### Verification *(Claude Code)*

```bash
git check-ignore -v backend/.env
# .gitignore:7:.env    backend/.env       ← matched, correctly ignored

git check-ignore -v backend/.env.example
# exit 1                                   ← not ignored, correctly committable

git status --short
# ?? backend/.env.example
# ?? docker-compose.yml
```

`backend/.env` does not appear in `git status` at all — proof the bare `.env` pattern correctly
covers nested paths.

---

## Step 11 — FastAPI app with a health-check endpoint **[You + Claude Code]**

### Concept

- **`app = FastAPI()`** creates the ASGI application object — the thing Uvicorn actually runs.
- **`@app.get("/health")`** registers a route: an HTTP GET to `/health` calls the decorated
  function. The return value is serialized to JSON automatically.
- **A health-check endpoint** returns a minimal "I'm alive" response with no business logic. It is
  a long-standing convention, and a practical one: in Phase 6, AWS App Runner will poll exactly
  this kind of endpoint to decide whether the container is healthy and should receive traffic.
- **`backend/app/__init__.py`** (empty) marks `app/` as an explicit Python package, so
  `uvicorn app.main:app` and later test imports resolve unambiguously.
- **`uvicorn app.main:app --reload`** reads as: import the module `app.main`, find the object named
  `app` inside it, serve it. `--reload` watches the filesystem and restarts on every save.

This step deliberately does **not** touch the database. Verifying the web server alone first means
that if something breaks in step 12, the cause is unambiguous.

### Commands *(Claude Code)*

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

### Created

| File | Purpose |
|---|---|
| `backend/app/__init__.py` | Empty — marks `app/` as a Python package |
| `backend/app/main.py` | The FastAPI application and the `/health` route |

Initial version of `main.py` (superseded in step 12):

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health_check():
    return {"status": "ok"}
```

### Verification

Server startup log:

```
INFO:     Will watch for changes in these directories: ['/home/jose/Coding/Manitou/backend']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

```bash
curl -s http://localhost:8000/health
# {"status":"ok"}
```

The owner then confirmed both URLs in a browser:

- <http://localhost:8000/health> — the JSON response
- <http://localhost:8000/docs> — **interactive Swagger UI, generated automatically** from the route
  definitions. Nothing was written to produce this page; FastAPI derives it from the code. It
  becomes a primary tool from Phase 2 onward for exercising endpoints by hand.

> **Run it from `backend/`.** `uvicorn app.main:app` resolves `app.main` relative to the current
> working directory. Started from the repo root, the import fails.

---

## Step 12 — Connect the API to the database **[You + Claude Code]**

### Concept

Three pieces, each with one responsibility:

**1. `app/config.py` — configuration loading.** A `Settings` class built on `pydantic-settings`
reads `DATABASE_URL` from `backend/.env`. This is the first real use of the file created in step
10. Pydantic validates on startup: if `DATABASE_URL` is missing, the app fails immediately with a
clear error rather than mysteriously later. The field is named `database_url` (lowercase) and
matches the uppercase `DATABASE_URL` because the lookup is case-insensitive.

**2. `app/db.py` — engine, session factory, dependency.**

- `create_engine(...)` builds the **connection pool**. It does not open a connection immediately;
  it manages a reusable set of them. Connection pooling is exactly what §6.11 flags as essential
  for the ~1,000 concurrent user target.
- `SessionLocal = sessionmaker(...)` is a factory producing individual **sessions** — a session is
  one unit of work, roughly one request. `autocommit=False` means nothing is written until an
  explicit commit, which is what makes the Phase 2 checkout transaction possible.
- `Base = declarative_base()` is the parent class every SQLAlchemy model will inherit from in
  Phase 1. Defined here now so all models share one registry.
- `get_db()` is a **FastAPI dependency**. The `try` / `finally` around `yield` guarantees the
  session is closed after the response is sent — including when the route raises. Without this,
  connections leak until the pool is exhausted and the API stops responding.

**3. Proving it works.** Rather than adding a separate endpoint, `/health` was extended to run
`SELECT 1` through a real session. `SELECT 1` is the cheapest possible query — it touches no
tables and exists purely to confirm a round trip to the server succeeded. `Depends(get_db)` is the
dependency-injection pattern every future route will use: FastAPI calls `get_db()`, passes the
session in as the `db` argument, and handles cleanup.

The raw SQL is wrapped in `text()` because SQLAlchemy 2.x requires explicit marking of raw SQL
strings — a guardrail against accidental SQL injection through string concatenation.

### Created

| File | Purpose |
|---|---|
| `backend/app/config.py` | Loads and validates settings from `.env` |
| `backend/app/db.py` | Engine (connection pool), session factory, `Base`, and the `get_db` dependency |

And `backend/app/main.py` was updated to depend on `get_db` and execute `SELECT 1`. Full contents
of all three in Appendix A.

### Verification *(Claude Code)*

The `--reload` server picked up the changes automatically:

```
WARNING:  WatchFiles detected changes in 'app/main.py'. Reloading...
INFO:     Application startup complete.
INFO:     127.0.0.1:53946 - "GET /health HTTP/1.1" 200 OK
```

```bash
curl -s -w "\nHTTP %{http_code}\n" http://localhost:8000/health
# {"status":"ok"}
# HTTP 200
```

### Verification *(owner)* — the important one

A passing test proves little on its own here: `{"status":"ok"}` looks identical whether or not the
database is actually involved. So the owner deliberately broke it:

```bash
docker compose stop db
# → GET /health returns 500 Internal Server Error

docker compose start db
# → GET /health returns {"status":"ok"}
```

This is what confirms the endpoint genuinely depends on PostgreSQL rather than returning a canned
response — the API **fails closed** when the database is unreachable, and recovers cleanly.

> **`.env` is resolved relative to the working directory.** `SettingsConfigDict(env_file=".env")`
> looks for `.env` in the current directory, which is another reason the API must be started from
> `backend/`.

---

## Step 13 — Write the README **[You + Claude Code]**

### Concept

`README.md` and `PROJECT_PLAN.md` serve different readers. The README answers one practical
question — *how do I get this running?* — for a human landing on the repo, including future-you on
a new machine. The master plan is the exhaustive phase-by-phase reference. The README stays short
and **links** to the other documents rather than duplicating them, so there is only one place to
update when something changes.

The setup steps are written in the order that actually works: copy the env template → start
PostgreSQL → create and activate the venv → install dependencies → run the API → verify in a
browser.

### Created

`/README.md` — full contents in Appendix A.

---

## Step 14 — Commit and push **[You]**

### Concept

From here on, commit after each working step. Small commits mean a broken change is easy to
isolate and revert, and the history reads as a record of how the project was built. That is the
habit this step exists to establish.

### Commands *(owner)*

```bash
git add .
git commit -m "..."
git push
```

### Verification

```bash
git status        # clean working tree
git log --oneline
```

All five Phase 0 commits present and pushed (see the commit map above).

---

## Gotchas encountered — consolidated

Four real problems hit during Phase 0, each worth remembering:

1. **"Cannot connect to the Docker daemon."** The Docker CLI being installed is not the same as
   Docker Desktop *running*. `docker compose up -d` failed until Docker Desktop was started. Any
   error mentioning `docker.sock` means the daemon is not running.

2. **venv activation is per-shell.** The owner's terminal and Claude Code's shell are separate
   processes; activating in one does nothing for the other. Every shell needs its own
   `source backend/.venv/bin/activate`. `which python` is the quickest way to confirm which
   interpreter is actually in use.

3. **`uvicorn app.main:app` must run from `backend/`.** The import path `app.main` is resolved
   relative to the current working directory.

4. **`.env` is also resolved relative to the working directory.** `SettingsConfigDict(env_file=".env")`
   will not find `backend/.env` if the app is started from the repo root — the same root cause as
   #3, and the same fix.

---

## Appendix A — Full file contents

### `/.gitignore`

```gitignore
# Python
backend/.venv/
__pycache__/
*.pyc

# Environment secrets
.env

# Node / Next.js
node_modules/
web/.next/

# OS junk
.DS_Store
Thumbs.db

# Editor
.vscode/
.idea/
```

### `/docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: manitou
      POSTGRES_PASSWORD: devpassword
      POSTGRES_DB: manitou
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U manitou -d manitou"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

### `backend/.env.example`

```dotenv
DATABASE_URL=postgresql://manitou:devpassword@localhost:5432/manitou
```

### `backend/.env` *(git-ignored — recreate with `cp backend/.env.example backend/.env`)*

```dotenv
DATABASE_URL=postgresql://manitou:devpassword@localhost:5432/manitou
```

### `backend/requirements.txt`

```
alembic==1.18.5
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.14.2
click==8.4.2
fastapi==0.141.1
greenlet==3.5.4
h11==0.16.0
httptools==0.8.0
idna==3.18
Mako==1.3.12
MarkupSafe==3.0.3
psycopg2-binary==2.9.12
pydantic==2.13.4
pydantic-settings==2.14.2
pydantic_core==2.46.4
python-dotenv==1.2.2
PyYAML==6.0.3
SQLAlchemy==2.0.51
starlette==1.3.1
typing-inspection==0.4.2
typing_extensions==4.16.0
uvicorn==0.52.1
uvloop==0.22.1
watchfiles==1.2.0
websockets==17.0.1
```

### `backend/app/__init__.py`

Empty (0 bytes) — marks `app/` as a Python package.

### `backend/app/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
```

### `backend/app/db.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### `backend/app/main.py`

```python
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

app = FastAPI()


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
```

### `/README.md`

````markdown
# Manitou

A multi-platform online store for a single vendor — web storefront, vendor admin portal, and
(later) native Android/iOS apps, all backed by one FastAPI backend and one shared PostgreSQL
database.

## Prerequisites

- Git
- Python 3.12+
- Node.js LTS
- Docker Desktop
- A PostgreSQL client (e.g. `psql`, TablePlus, pgAdmin)

## Local setup

1. Clone the repo and `cd` into it.
2. Copy the backend env template:
   ```
   cp backend/.env.example backend/.env
   ```
   The default values already match the local Docker Compose database below, so no edits are
   needed to get started.
3. Start local PostgreSQL:
   ```
   docker compose up -d
   ```
4. Create the backend virtual environment, activate it, and install dependencies:
   ```
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
5. Run the API (from `backend/`, with the venv active):
   ```
   uvicorn app.main:app --reload
   ```
6. Confirm it's working:
   - http://localhost:8000/health — should return `{"status":"ok"}`
   - http://localhost:8000/docs — interactive API documentation

## Learn more

- [`PROJECT_PLAN.md`](./PROJECT_PLAN.md) — the full build plan: architecture, tech stack, phases,
  and database schema.
- [`CLAUDE.md`](./CLAUDE.md) — conventions for working in this repo.
````

---

## Appendix B — Daily workflow cheat-sheet

Starting a work session, from the repo root:

```bash
# 1. Start the database (skip if already running)
docker compose up -d

# 2. Activate the venv — required in every new terminal
cd backend
source .venv/bin/activate

# 3. Run the API
uvicorn app.main:app --reload
```

Then open <http://localhost:8000/docs>.

Ending a session:

```bash
# Stop the API
Ctrl+C

# Stop the database, keeping all data
docker compose stop
```

Useful checks:

```bash
docker compose ps            # is the database up and healthy?
which python                 # is the venv active in this shell?
curl -s localhost:8000/health
docker compose logs db       # database logs if something looks wrong
```

> **⚠️ `docker compose down -v` deletes the `pgdata` volume and every row in the database.**
> Plain `docker compose down` removes the container but keeps the data. Use `-v` only when a
> deliberately clean slate is wanted — which will be genuinely useful in Phase 1 for testing that
> migrations and the seed script work from scratch.

---

## Appendix C — Command reference

Every command used in Phase 0, grouped by tool.

### Git

| Command | Purpose |
|---|---|
| `git clone <url>` | Copy the GitHub repository locally |
| `git status --short` | Compact view of changed/untracked files |
| `git check-ignore -v <path>` | Show which `.gitignore` rule (file:line) matches a path |
| `git ls-files` | List every tracked file |
| `git add .` / `git commit -m "..."` / `git push` | Stage, record, and upload changes |
| `git log --oneline` | Compact commit history |
| `git show <sha>` | Inspect exactly what one commit changed |

### Docker

| Command | Purpose |
|---|---|
| `docker --version`, `docker compose version` | Confirm installation |
| `docker compose up -d` | Start services in the background |
| `docker compose ps` | Show status and health of services |
| `docker compose stop` / `start` | Stop or restart containers, keeping data |
| `docker compose down` | Remove containers, **keep** the `pgdata` volume |
| `docker compose down -v` | Remove containers **and delete all data** |
| `docker compose logs db` | View database logs |

### Python, venv, and pip

| Command | Purpose |
|---|---|
| `python3 --version` | Confirm 3.12+ |
| `python3 -m venv .venv` | Create the virtual environment |
| `source .venv/bin/activate` | Activate it — **per shell** |
| `which python` | Confirm which interpreter is active |
| `pip install <pkg>` | Install into the active venv (never globally) |
| `pip install -r requirements.txt` | Reproduce the exact environment |
| `pip freeze > requirements.txt` | Record all packages with pinned versions |

### Running and testing the API

| Command | Purpose |
|---|---|
| `uvicorn app.main:app --reload` | Run the API with hot-reload (from `backend/`) |
| `curl -s http://localhost:8000/health` | Check the health endpoint |
| `curl -s -w "\nHTTP %{http_code}\n" <url>` | Same, and show the HTTP status code |
| `psql -h localhost -p 5432 -U manitou -d manitou` | Connect to the database directly |

---

## What Phase 0 delivered

- A version-controlled repository with the full multi-platform folder structure in place.
- A reproducible Python environment isolated in `backend/.venv`, pinned by `requirements.txt`.
- PostgreSQL 16 running locally in Docker with persistent storage and a health check.
- The configuration pattern (`.env` / `.env.example`) that will carry unchanged all the way to
  AWS Secrets Manager in Phase 6.
- A running FastAPI application, connected to the database, with automatic interactive API docs.
- A README that lets anyone reproduce all of the above.

**Next: Phase 1 — Database.** The ER diagram, SQLAlchemy models for every table in
`PROJECT_PLAN.md` §6.3, Alembic migrations, constraints and indexes, and a seed script. `Base` in
`backend/app/db.py` is already waiting for the models to inherit from it.
