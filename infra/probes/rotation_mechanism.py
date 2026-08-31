"""Does a password rotation break a running API, and would anyone notice?

Run with:  infra/scripts/run_in_vpc.sh infra/probes/rotation_mechanism.py

**What this is testing.** ECS resolves a `secrets` reference once, when a task
starts, and never refreshes it. The RDS-managed master secret rotates every 7
days. So a long-running API task ends up holding a password the database no
longer accepts. The question this probe answers is what that actually looks
like from outside -- because the answer decides whether our alarms would catch
it.

**Why a throwaway role rather than the real rotation.** Rotating the master
password to find out would take the live API down. A disposable role with no
grants reproduces the same Postgres semantics -- authentication happens at
connect time, and only at connect time -- on the same server, with no blast
radius. The live rotation is worth doing once, deliberately, as the control;
this establishes what to look for first so that test is short.

Nothing secret crosses a boundary: both passwords are generated here and never
printed. token_urlsafe's alphabet is [A-Za-z0-9_-], so interpolating it into
DDL (which cannot take bind parameters) introduces no quoting hazard.
"""

import secrets
import traceback

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings

ROLE = "probe_rotation_tmp"
PW_BEFORE = secrets.token_urlsafe(24)
PW_AFTER = secrets.token_urlsafe(24)

admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
probe_url = make_url(settings.database_url).set(username=ROLE, password=PW_BEFORE)


def show(label, value):
    print(f"  {label:<46} {value}")


print("=" * 72)
print("PROBE: what a password rotation does to a running connection pool")
print("=" * 72)

try:
    with admin.connect() as c:
        show("connected as", c.execute(text("SELECT current_user")).scalar())
        c.execute(text(f"DROP ROLE IF EXISTS {ROLE}"))
        c.execute(text(f"CREATE ROLE {ROLE} LOGIN PASSWORD '{PW_BEFORE}'"))
        show("created disposable role", ROLE)

    # ---------------------------------------------------------------- setup --
    # The SAME pool configuration the API runs today: create_engine with no pool
    # arguments at all. Printing the defaults also settles the arithmetic behind
    # the DatabaseConnections alarm, which is set to 50.
    app_like = create_engine(probe_url)
    pool = app_like.pool
    print("\n-- the pool the API actually has (backend/app/db.py, no pool args) --")
    show("pool class", type(pool).__name__)
    show("pool_size", pool.size())
    show("max_overflow", pool._max_overflow)
    show("pre_ping", bool(getattr(app_like.pool, "_pre_ping", False)))
    show("ceiling per task", pool.size() + pool._max_overflow)
    show("ceiling across maxTaskCount=2", (pool.size() + pool._max_overflow) * 2)

    # A connection checked out and HELD, standing in for the one the ALB health
    # check keeps permanently warm by running SELECT 1 every 30 seconds.
    warm = app_like.connect()
    show("warm connection before rotation", warm.execute(text("SELECT 1")).scalar())

    # ------------------------------------------------------------- rotation --
    with admin.connect() as c:
        c.execute(text(f"ALTER ROLE {ROLE} PASSWORD '{PW_AFTER}'"))
    print("\n-- password rotated; the engine still holds the OLD one --")

    # 1. The warm connection. Already authenticated, so Postgres never re-checks.
    try:
        show("warm connection AFTER rotation", warm.execute(text("SELECT 1")).scalar())
    except Exception as exc:  # noqa: BLE001 - reporting, not handling
        show("warm connection AFTER rotation", f"FAILED {type(exc).__name__}")

    # 2. A NEW connection from the same engine, which is what any concurrency
    #    beyond the single warm connection forces the pool to open.
    try:
        with app_like.connect() as fresh:
            show("NEW connection AFTER rotation", fresh.execute(text("SELECT 1")).scalar())
    except Exception as exc:  # noqa: BLE001
        first_line = str(exc).strip().splitlines()[0][:90]
        show("NEW connection AFTER rotation", f"FAILED {type(exc).__name__}")
        show("  -> ", first_line)

    # 3. Does pool_pre_ping rescue it? Prediction: no. Pre-ping validates a
    #    pooled connection by pinging it and, if the ping fails, discarding it and
    #    opening a replacement -- but the replacement authenticates with the same
    #    stale password. It is the right setting for a reboot or a failover, and
    #    no help at all here. Worth proving rather than asserting, because it is
    #    exactly the setting someone would reach for.
    pre_ping = create_engine(probe_url, pool_pre_ping=True)
    try:
        with pre_ping.connect() as c:
            show("with pool_pre_ping=True", c.execute(text("SELECT 1")).scalar())
    except Exception as exc:  # noqa: BLE001
        show("with pool_pre_ping=True", f"FAILED {type(exc).__name__} (as predicted)")

    # 4. The recovery path, for completeness: a task RESTART re-reads the secret,
    #    which is why forcing a deployment fixes this and why one-off tasks are
    #    immune by construction.
    restarted = create_engine(make_url(probe_url).set(password=PW_AFTER))
    with restarted.connect() as c:
        show("a restarted task (fresh secret)", c.execute(text("SELECT 1")).scalar())

    warm.close()

finally:
    # Always, even if an assertion above blew up -- a probe that leaves a login
    # role behind on the production database is worse than no probe.
    with admin.connect() as c:
        c.execute(text(f"DROP ROLE IF EXISTS {ROLE}"))
    print(f"\n  cleaned up {ROLE}")

print("=" * 72)
