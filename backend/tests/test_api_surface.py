"""What the API exposes to an unauthenticated stranger.

The schema is not a secret and every route stays authenticated with or without
it. What serving it gives away is reconnaissance: 108 KB naming all 62 routes,
every `/admin/*` path, and the exact shape of each request body. Phase 7 task 3
turns it off outside development.
"""

from app.config import Settings, settings


def test_docs_are_off_by_default(monkeypatch):
    """The direction of the default is the security property.

    Production is configured from the ECS task definition and has no `.env`, so
    the value you get by not thinking about it has to be the safe one. A default
    of True would mean every future environment ships the schema until somebody
    remembers to turn it off."""
    for key in ("API_DOCS_ENABLED", "DATABASE_URL", "DB_HOST", "DB_PORT",
                "DB_USER", "DB_NAME", "DB_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    fresh = Settings(
        _env_file=None,
        database_url="postgresql://u:p@h/d",
        jwt_secret="x",
        stripe_secret_key="x",
        stripe_publishable_key="x",
    )
    assert fresh.api_docs_enabled is False


def test_the_schema_routes_follow_the_setting(client):
    """The routes are added or removed, not merely linked or unlinked.

    /openapi.json is the URL actually worth fetching, so serving it while
    dropping /docs would be decoration -- all three are checked.

    **Expressed relative to the setting rather than asserting 404.** An earlier
    version asserted the flag was False and then required 404, which made the
    test depend on the developer's own git-ignored `.env`: it passed in CI and
    for anyone who had not enabled the docs, and failed for anyone following
    `.env.example`. A test that only holds under one local configuration is a
    trap for whoever changes that configuration next.

    The security-relevant invariant -- that the DEFAULT is off -- is hermetic and
    lives in the test above. This one checks the wiring: whatever the flag says,
    the routes agree with it. Hardcoding `docs_url="/docs"` and ignoring the
    setting fails this in any environment where the flag is off."""
    expected = 200 if settings.api_docs_enabled else 404
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == expected, (
            f"{path} should be {expected} when api_docs_enabled is "
            f"{settings.api_docs_enabled}"
        )


def test_health_is_still_served(client):
    """The control. A test that only proves things are missing would also pass
    against an application that failed to start."""
    assert client.get("/health").status_code == 200
