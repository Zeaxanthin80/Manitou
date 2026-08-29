"""Config tests: the .env.example file and the Settings class must agree.

Neither test touches the database. They still run under the session's Postgres
setup, because conftest's clean_tables fixture is autouse and pulls in engine,
so every test in the suite gets manitou_test built whether it needs it or not.

Why this file exists. `.env.example` is documentation and `Settings` is the
guard that reads it, and the two are kept in step by hand. When they drifted --
Stripe keys added to .env, no matching fields on Settings -- pydantic-settings'
default extra="forbid" turned it into a ValidationError at import time, which
took down the API, `alembic upgrade head` and the whole test suite at once,
because every one of them imports app.config. See docs/defect-log.md.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, settings

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"


def _env_example_keys() -> set[str]:
    """The KEY names in .env.example, lowercased to match field names."""
    return {
        line.split("=", 1)[0].strip().lower()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }


def test_env_example_and_settings_agree():
    """Every documented variable is a field, and every field is documented.

    Equality rather than a subset, because both directions are real failures: a
    key in .env.example with no field crashes the app at boot (the defect this
    file was written for), and a field with no placeholder in .env.example
    leaves a fresh clone unable to start, which CLAUDE.md forbids.
    """
    assert _env_example_keys() == set(Settings.model_fields)


def test_the_stripe_secret_is_masked_in_its_own_string_forms():
    """SecretStr, so a traceback or a stray log of settings cannot leak the key.

    The failure that prompted this printed the live key into a stack trace. On a
    laptop that is harmless; from Phase 6 it is a boot failure writing sk_... to
    CloudWatch. Asserted against the value itself rather than a prefix, so the
    test holds for any key, including the .env.example placeholder.
    """
    value = settings.stripe_secret_key.get_secret_value()

    assert value, "there should be a real value behind the mask"
    assert value not in repr(settings.stripe_secret_key)
    assert value not in str(settings.stripe_secret_key)


# ---------------------------------------------------------------------------
# Assembling DATABASE_URL from parts (Phase 6 task 7)
# ---------------------------------------------------------------------------
#
# Production cannot set DATABASE_URL whole: ECS injects the password from the
# RDS-managed Secrets Manager secret, which holds {username, password} JSON
# rather than a connection string. So config.py assembles the URL from DB_*
# parts when DATABASE_URL is absent.
#
# Every test here passes _env_file=None. Without it backend/.env supplies
# DATABASE_URL, the assembly branch never runs, and the tests pass for the wrong
# reason -- which is exactly what happened the first time they were written. The
# container has no .env at all (.dockerignore), so None is the honest simulation.

_REQUIRED = dict(
    jwt_secret="x",
    stripe_secret_key="sk_test_x",
    stripe_publishable_key="pk_test_x",
)
_DB_PARTS = dict(
    db_host="db.example.com", db_user="manitou", db_name="manitou",
)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **_REQUIRED, **kw)


def test_an_explicit_database_url_is_left_alone():
    """The control. Development sets the whole string and assembly must not fire."""
    url = "postgresql://u:p@localhost:5432/manitou"
    assert _settings(database_url=url).database_url == url


def test_the_url_is_assembled_when_only_the_parts_are_given():
    assert _settings(**_DB_PARTS, db_password="simple").database_url == (
        "postgresql://manitou:simple@db.example.com:5432/manitou?sslmode=require"
    )


def test_a_password_with_url_metacharacters_survives_a_round_trip():
    """The case this exists for: RDS generates `#`, `)`, `%` and `/` in passwords.

    Asserted by parsing the result back rather than by matching the encoded
    string, because what matters is that psycopg2 receives the original password
    -- not that it was spelled a particular way in between.

    **This test does NOT guard the encoding**, and that is worth knowing rather
    than discovering. Mutation-tested: remove quote() from config.py and this
    still passes, because SQLAlchemy's make_url reads the raw password correctly.
    The only test that fails is the alembic one below, on its `%23` assertion.
    So the encoding rests on a single assertion -- delete that one and nothing
    notices it is gone.
    """
    from sqlalchemy.engine import make_url

    password = "hrk8#PPRdq)Gn%Zp/HE"
    parsed = make_url(_settings(**_DB_PARTS, db_password=password).database_url)

    assert parsed.password == password
    assert parsed.host == "db.example.com"
    assert parsed.database == "manitou"
    assert parsed.username == "manitou"


def test_a_percent_in_the_assembled_url_still_reaches_alembic():
    """Guards the interaction between this and defect 21.

    alembic/env.py escapes `%` as `%%` before handing the URL to configparser.
    Encoding a password makes `%` far more likely, so the two changes have to
    keep working together -- and a future simplification of either would break
    migrations while every test here still passed.
    """
    from alembic.config import Config

    url = _settings(**_DB_PARTS, db_password="a#b").database_url
    assert "%23" in url

    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    assert cfg.get_main_option("sqlalchemy.url") == url


def test_no_database_configuration_at_all_refuses_to_boot():
    """A misconfigured store should say so at startup, naming the missing field.

    Making database_url optional to allow assembly could easily have traded this
    away for a connection error on the first request. It did not.
    """
    with pytest.raises(ValidationError, match="Missing: DB_HOST, DB_USER, DB_NAME, DB_PASSWORD"):
        _settings()


def test_incomplete_parts_refuse_to_boot_and_name_what_is_missing():
    with pytest.raises(ValidationError, match="Missing: DB_NAME, DB_PASSWORD"):
        _settings(db_host="db.example.com", db_user="manitou")
