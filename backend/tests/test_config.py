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
