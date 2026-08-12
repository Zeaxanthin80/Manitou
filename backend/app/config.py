from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    # Signing key for JWTs. Local development uses the value in .env; production
    # draws a different one from AWS Secrets Manager (Section 4.2). A leaked
    # development secret must never be able to forge production tokens.
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Which EmailSender implementation to build (app/services/email.py).
    # "console" logs the message instead of sending it, which is enough to walk
    # the whole password-reset flow locally. Phase 6 adds "ses".
    email_sender: str = "console"

    # The origin that password-reset links point at -- the WEB app, not the API,
    # since the customer clicks through to a page. It differs between a laptop
    # and production, which is exactly what makes it a .env value rather than a
    # store-config.json one (Section 4.2).
    app_base_url: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
