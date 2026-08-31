from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Pool settings written down rather than inherited.
#
# These are SQLAlchemy's own defaults, stated explicitly. Nothing changes at
# runtime; what changes is that the numbers are now visible, because they are
# load-bearing in two places outside this file:
#
#   * The ceiling is pool_size + max_overflow = 15 per task, and Express Mode
#     runs at most 2 tasks, so steady state tops out around 30 connections. The
#     `manitou-rds-connections-high` alarm was set to fire above 50 -- which the
#     load test never came close to, making it an alarm that could not fire. Now
#     24, and it fired correctly on its first real saturation event.
#   * **30 is the steady-state bound, not a hard one.** The load test peaked at
#     35: a scale-out or task replacement briefly runs more than maxTaskCount
#     while the old task drains, and each new task brings its own pool. Worth
#     stating because the tidy 2 x 15 arithmetic invites treating it as a limit.
#   * db.t4g.micro allows ~112 connections, so even 35 is comfortable. The load
#     test confirmed the database is nowhere near being the bottleneck: RDS CPU
#     peaked at 24% while the API container sat at 93%.
#
# pool_pre_ping issues a cheap SELECT 1 when a connection is taken out of the
# pool and transparently replaces it if the check fails. This store is
# low-traffic by design (PROJECT_PLAN.md 10.1 sizes launch at ~1 concurrent
# user), so connections sit idle for hours and are exactly the ones an RDS
# reboot, failover or maintenance window silently closes. Without pre-ping the
# next customer after a quiet night gets the 500.
#
# It is NOT what protects against a rotated password -- pre-ping's replacement
# connection authenticates with the same stale credential and fails too. That
# was measured before relying on it, and defect 30 is fixed by not connecting as
# the rotating master user at all.
engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Deterministic constraint names, so a constraint can be altered or dropped by
# name in a later migration. Without this, the database invents the names and
# they are neither portable nor predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
