from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.config import settings
from app.db import Base
import app.models  # noqa: F401  -- registers every table on Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# The URL is not stored in alembic.ini (it is committed to Git and holds a
# password).  It comes from .env via app.config.settings instead.
#
# Only set it if a caller has not already supplied one. The test suite builds its
# schema by handing Alembic a Config pointing at manitou_test; overwriting that
# unconditionally would silently run the migration against the development
# database instead.
if not config.get_main_option("sqlalchemy.url", None):
    # `%` doubled, because set_main_option writes through configparser, where a
    # single `%` starts an interpolation token. A password containing one -- or
    # any percent-encoded character, which is how you are told to write `#` or
    # `@` into a URL -- raises ValueError before a connection is attempted, and
    # the message quotes the whole URL back at you, password included.
    #
    # Found the first time Alembic ran against RDS: the generated master password
    # held a `#`, percent-encoding made it `%23`, and configparser rejected it.
    # `devpassword` locally has no special characters, so nothing caught it for
    # five phases.
    config.set_main_option(
        "sqlalchemy.url", settings.database_url.replace("%", "%%")
    )

# Interpret the config file for Python logging.
#
# **disable_existing_loggers=False, and the default is a trap.** fileConfig
# defaults to True, which sets `.disabled = True` on every logger that already
# exists at this moment -- not just the ones alembic.ini mentions.
#
# Standalone `alembic upgrade head` barely notices: almost nothing is imported
# yet. The test suite is a different shape entirely. conftest builds the schema
# by running these migrations IN PROCESS, after pytest has already collected the
# test modules -- so every `logging.getLogger(__name__)` bound at module scope is
# silenced for the rest of the session.
#
# Nothing failed loudly. The application still logged in production (migrations
# run as their own one-off task and never share the API's process), and tests
# that assert on logging passed as long as they fetched their logger INSIDE the
# test, after this line had run. It surfaced only when a test imported the module
# under test at the top of the file and then found its warnings had vanished --
# a logging assertion that quietly cannot fail, which is worse than no assertion.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Autogenerate compares this metadata against the live database.
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
