"""Verify what `manitou_app` may and may not do on the production database.

Run with:
    TASK_FAMILY=manitou-dbadmin infra/scripts/run_in_vpc.sh infra/probes/role_privileges.py

**No destructive statement is ever executed.** An earlier draft of this probe ran
`DROP TABLE products` as the master too, as a control, relying on Postgres DDL
being transactional to roll it back. That is true, and it was still the wrong
design: it put a live production table one missing rollback away from deletion
to establish something the catalog already knows.

So the two halves are asymmetric on purpose:

* **As the master**: catalogue reads only. Table ownership is a structural fact,
  and `ALTER TABLE ... DISABLE TRIGGER` is granted to the owner by definition --
  so "the master can switch the audit trigger off" is derivable from
  `pg_tables.tableowner` without switching anything off.
* **As `manitou_app`**: the dangerous statements are actually attempted, because
  a refusal is only convincing if it was really tried. These are safe to attempt
  precisely because they are expected to fail, and they run inside a transaction
  that is rolled back in a finally block and never committed.

The "denied" reading is also checked rather than assumed: `permission denied for
table products` proves the table resolved and the refusal was a privilege
decision, where `relation does not exist` would have meant the test was wrong.
That distinction is the whole reason the defect log warns that a comparison only
tests what it can distinguish.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DatabaseError

from app.config import settings

master = create_engine(make_url(settings.database_url))
app = create_engine(
    make_url(settings.database_url).set(
        username="manitou_app", password=os.environ["DB_APP_PASSWORD"])
)


def attempt(sql):
    """Run sql as manitou_app in a transaction that is always rolled back."""
    conn = app.connect()             # SQLAlchemy 2.0: no autocommit
    try:
        conn.execute(text("SET lock_timeout = '2s'"))
        conn.execute(text(sql))
        return "ALLOWED"
    except DatabaseError as exc:
        msg = str(getattr(exc, "orig", exc)).strip().splitlines()[0]
        if "permission denied" in msg or "must be owner" in msg:
            return "DENIED"
        if "does not exist" in msg:
            return "BAD TEST: object missing"
        return f"ERROR: {msg[:50]}"
    finally:
        conn.rollback()              # nothing above is ever committed
        conn.close()


print("=" * 74)
print("A. Structural facts, read from the catalogue as the master")
print("=" * 74)
with master.connect() as c:
    owner = c.execute(text(
        "SELECT tableowner FROM pg_tables WHERE tablename = 'audit_events'")).scalar()
    app_super = c.execute(text(
        "SELECT rolsuper OR rolcreaterole OR rolcreatedb "
        "FROM pg_roles WHERE rolname = 'manitou_app'")).scalar()
    app_owns = c.execute(text(
        "SELECT count(*) FROM pg_tables "
        "WHERE schemaname = 'public' AND tableowner = 'manitou_app'")).scalar()
    n_tables = c.execute(text(
        "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")).scalar()
    trigger_on = c.execute(text(
        "SELECT count(*) FROM pg_trigger t JOIN pg_class k ON k.oid = t.tgrelid "
        "WHERE k.relname = 'audit_events' AND t.tgenabled <> 'D' "
        "AND NOT t.tgisinternal")).scalar()

print(f"  audit_events is owned by                    {owner}")
print(f"  ... so {owner} may DISABLE TRIGGER on it     (owner right, by definition)")
print(f"  tables in public schema                     {n_tables}")
print(f"  tables owned by manitou_app                 {app_owns}   <- must be 0")
print(f"  manitou_app has superuser/createrole/db      {app_super}   <- must be False")
print(f"  audit_events user triggers enabled          {trigger_on}")

print()
print("=" * 74)
print("B. What manitou_app can actually do (attempted, then rolled back)")
print("=" * 74)

CHECKS = [
    # label,                        statement,                                    expected
    ("read products",               "SELECT count(*) FROM products",              "ALLOWED"),
    ("read orders",                 "SELECT count(*) FROM orders",                "ALLOWED"),
    # target_type is NOT NULL with no default, like actor_email and action. An
    # earlier version of this row omitted it and failed on the constraint rather
    # than on privileges -- which still proved INSERT was granted, since Postgres
    # checks permissions before constraints, but tested the wrong thing.
    ("insert an audit row",
     "INSERT INTO audit_events (actor_email, action, target_type) "
     "VALUES ('probe@example.com', 'probe', 'probe')",
     "ALLOWED"),
    ("CREATE TABLE",               "CREATE TABLE probe_privcheck (id integer)",   "DENIED"),
    ("DROP the products table",    "DROP TABLE products",                         "DENIED"),
    ("DISABLE the audit trigger",  "ALTER TABLE audit_events DISABLE TRIGGER USER", "DENIED"),
    ("UPDATE an audit row",        "UPDATE audit_events SET actor_email = 'x'",   "DENIED"),
    ("DELETE an audit row",        "DELETE FROM audit_events",                    "DENIED"),
]

failures = []
print(f"  {'operation':<28} {'result':<12} {'expected':<10}")
print(f"  {'-' * 28} {'-' * 12} {'-' * 10}")
for label, sql, expected in CHECKS:
    got = attempt(sql)
    ok = got == expected
    if not ok:
        failures.append((label, got, expected))
    print(f"  {label:<28} {got:<12} {expected:<10} {'' if ok else '  <-- FAIL'}")

# --- prove the rollbacks rolled back ----------------------------------------
# "I rolled it back" is a claim, and this is the check that turns it into a fact.
print()
with master.connect() as c:
    still_there = c.execute(text("SELECT to_regclass('public.products') IS NOT NULL")).scalar()
    no_leftover = c.execute(text("SELECT to_regclass('public.probe_privcheck') IS NULL")).scalar()
    after_tables = c.execute(text(
        "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")).scalar()
    after_trigger = c.execute(text(
        "SELECT count(*) FROM pg_trigger t JOIN pg_class k ON k.oid = t.tgrelid "
        "WHERE k.relname = 'audit_events' AND t.tgenabled <> 'D' "
        "AND NOT t.tgisinternal")).scalar()
    audit_rows = c.execute(text("SELECT count(*) FROM audit_events")).scalar()

print(f"  products still exists                       {still_there}")
print(f"  probe_privcheck not left behind             {no_leftover}")
print(f"  table count unchanged                       {after_tables == n_tables} "
      f"({n_tables} -> {after_tables})")
print(f"  audit triggers still enabled                {after_trigger == trigger_on}")
print(f"  audit_events row count                      {audit_rows} (probe insert rolled back)")

assert still_there and no_leftover, "rollback failed to clean up"
assert after_tables == n_tables and after_trigger == trigger_on, "schema changed"
assert not app_super and app_owns == 0, "manitou_app has more authority than intended"

if failures:
    for label, got, expected in failures:
        print(f"  FAILED: {label}: got {got}, expected {expected}")
    raise SystemExit(1)

print("\nOK")
