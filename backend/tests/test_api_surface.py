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


def test_the_schema_is_not_served_when_disabled(client):
    """Removing the routes, not merely hiding the links.

    /openapi.json is the URL actually worth fetching -- leaving it served while
    dropping /docs would be decoration."""
    assert settings.api_docs_enabled is False, "this test assumes the suite's config"
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, f"{path} should not exist"


def test_health_is_still_served(client):
    """The control. A test that only proves things are missing would also pass
    against an application that failed to start."""
    assert client.get("/health").status_code == 200
