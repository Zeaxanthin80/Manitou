"""Describe a database precisely enough to compare two of them.

    infra/scripts/run_in_vpc.sh infra/probes/db_census.py
    TASK_ENV_DB_HOST_OVERRIDE=<endpoint> infra/scripts/run_in_vpc.sh infra/probes/db_census.py

Written for the Phase 7 restore test, where the question is not "did the restore
succeed" -- RDS will happily report `available` for an instance nobody has
looked inside -- but "is what came back the database we think it is".

**The host is an override rather than a whole connection string**, because a
connection string carries a password and container overrides are returned by
DescribeTasks and recorded in CloudTrail for 90 days. Everything else comes from
the task definition's own secrets, so only the endpoint travels.

Output is deliberately flat and sorted so two runs can be diffed directly.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings

url = make_url(settings.database_url)
override = os.environ.get("DB_HOST_OVERRIDE")
if override:
    url = url.set(host=override)

engine = create_engine(url, pool_pre_ping=True)

with engine.connect() as c:
    print(f"  host              {url.host}")
    print(f"  database          {url.database}")
    print(f"  connected as      {c.execute(text('SELECT current_user')).scalar()}")
    print(f"  server version    {c.execute(text('SHOW server_version')).scalar()}")

    # The schema version is the single most important field here. A restore that
    # came back one migration behind the running code is a restore that will fail
    # in a way nobody expects.
    version = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"  alembic_version   {version}")

    tables = [
        r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "ORDER BY tablename"
        ))
    ]
    print(f"  tables            {len(tables)}")

    print("\n  --- row counts ---")
    total = 0
    for t in tables:
        # Identifier interpolation, not a bind parameter: a table name cannot be
        # bound. The values come from pg_tables, so they are the server's own
        # identifiers rather than anything a caller supplied.
        n = c.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
        total += n
        print(f"  {t:<28} {n:>8}")
    print(f"  {'TOTAL':<28} {total:>8}")

    # A spot check that goes past counting. Rows can be present and still be
    # wrong: money is numeric(10,2) and order_items snapshot the name and price
    # at purchase time, which is the property the whole schema is arranged
    # around. Counting rows would not notice if those came back null.
    print("\n  --- newest order, end to end ---")
    order = c.execute(text(
        "SELECT id, status, subtotal, tax, shipping_cost, total, created_at "
        "FROM orders ORDER BY id DESC LIMIT 1"
    )).first()
    if order is None:
        print("  (no orders)")
    else:
        oid, status, sub, tax, ship, tot, created = order
        print(f"  order #{oid} {status}  subtotal={sub} tax={tax} "
              f"shipping={ship} total={tot}")
        print(f"  created_at        {created}")
        arithmetic_ok = (sub + tax + ship) == tot
        print(f"  totals add up     {arithmetic_ok}")
        # The columns carry `_snapshot` for a reason worth preserving in the
        # query: they record the name and price AS SOLD, not as the product reads
        # today. A restore that brought back the rows but resolved these through
        # the products table would look right and be historically wrong.
        for item in c.execute(text(
            "SELECT product_name_snapshot, unit_price_snapshot, quantity "
            "FROM order_items WHERE order_id = :oid ORDER BY id"
        ), {"oid": oid}):
            print(f"    item            {item[0]!r} @ {item[1]} x{item[2]}")
