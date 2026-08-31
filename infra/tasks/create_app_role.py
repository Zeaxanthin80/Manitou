"""Create `manitou_app`, the role the API connects as. Idempotent.

Run with:
    TASK_FAMILY=manitou-dbadmin infra/scripts/run_in_vpc.sh infra/tasks/create_app_role.py

Must run on the **dbadmin** task definition, which is the one carrying the master
credentials and `DB_APP_PASSWORD`. On the API's own task definition this fails
at the first CREATE ROLE, which is the correct outcome -- the API is not
supposed to be able to do this.

**Why the API stops using the master user** (defect 30):

1. The RDS-managed master secret rotates every 7 days, and ECS resolves a
   `secrets` reference once, at task start. A long-running task therefore ends up
   holding a password the database has stopped accepting -- proven live, and the
   symptom is 25% of concurrent requests failing while every health check passes.
   `manitou_app`'s password lives in `manitou/api`, which does not rotate.
2. The master owns every table, so it can `DROP` and `ALTER` anything. A
   storefront needs none of that.
3. Most specifically: owning a table is enough to `ALTER TABLE ... DISABLE
   TRIGGER`. `audit_events` is described as append-only *because a trigger
   rejects UPDATE and DELETE* -- but the API could have switched that trigger
   off. A guarantee the guarded party can disable is not a guarantee.

The password is read from the environment, never passed as an argument:
container overrides come back from DescribeTasks and are recorded by CloudTrail.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings

ROLE = "manitou_app"
PASSWORD = os.environ["DB_APP_PASSWORD"]
DB = make_url(settings.database_url).database

# GetRandomPassword generated this with ExcludePunctuation, so it is [A-Za-z0-9].
# CREATE ROLE cannot take a bind parameter, so the value is interpolated -- and
# this assertion is what makes that safe rather than merely usual.
assert PASSWORD.isalnum(), "app password must be alphanumeric to be interpolated into DDL"

engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")


def show(label, value):
    print(f"  {label:<44} {value}")


with engine.connect() as c:
    show("connected as", c.execute(text("SELECT current_user")).scalar())
    show("database", DB)

    exists = c.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
    ).scalar()

    if exists:
        c.execute(text(f"ALTER ROLE {ROLE} WITH LOGIN PASSWORD '{PASSWORD}'"))
        show("role", f"{ROLE} already existed; password reset")
    else:
        c.execute(
            text(
                f"CREATE ROLE {ROLE} LOGIN PASSWORD '{PASSWORD}' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
            )
        )
        show("role", f"{ROLE} created")

    # --- what the application may do ----------------------------------------
    # DML on the tables, and nothing else. No ownership, so no DDL: no CREATE,
    # no DROP, no ALTER, and no disabling a trigger.
    c.execute(text(f'GRANT CONNECT ON DATABASE "{DB}" TO {ROLE}'))
    c.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROLE}"))
    c.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}"))
    # Sequences, because every insert into a table with an identity column needs
    # nextval. Omitting this is the classic half-done grant: reads work, the
    # schema looks right, and the first INSERT fails in production.
    c.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}"))
    show("granted", "DML on all tables, USAGE+SELECT on all sequences")

    # --- and on tables that do not exist yet ---------------------------------
    # Without this, the next migration's table is invisible to the API and the
    # failure arrives as a permission error on a table the developer just
    # created. Set once, applies to everything `manitou` creates from now on.
    for objs, privs in (("TABLES", "SELECT, INSERT, UPDATE, DELETE"),
                        ("SEQUENCES", "USAGE, SELECT")):
        c.execute(
            text(f"ALTER DEFAULT PRIVILEGES FOR ROLE manitou IN SCHEMA public "
                 f"GRANT {privs} ON {objs} TO {ROLE}")
        )
    show("default privileges", "future tables and sequences covered")

    # --- append-only, at two layers -----------------------------------------
    # The trigger already rejects UPDATE and DELETE on audit_events. Revoking
    # them as well means the guarantee survives the trigger being dropped by
    # something that CAN drop it. Cheap, and it makes the claim in CLAUDE.md
    # true at the privilege layer rather than only at the trigger layer.
    c.execute(text(f"REVOKE UPDATE, DELETE ON audit_events FROM {ROLE}"))
    show("audit_events", "UPDATE/DELETE revoked as well as trigger-blocked")

# --- self-check: can the new role actually connect and read? -----------------
# A grant script that reports success without ever using the role it created is
# the same shape as a migration that reports success without connecting.
app_url = make_url(settings.database_url).set(username=ROLE, password=PASSWORD)
with create_engine(app_url).connect() as c:
    show("connects as", c.execute(text("SELECT current_user")).scalar())
    show("is_superuser", c.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar())
    show("can read products", c.execute(text("SELECT count(*) FROM products")).scalar())
    show("can read orders", c.execute(text("SELECT count(*) FROM orders")).scalar())

print("OK")
