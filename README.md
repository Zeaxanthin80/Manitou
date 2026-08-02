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
