from pydantic import SecretStr
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

    # --- Stripe (Phase 5) ---------------------------------------------------
    # Required, like database_url and jwt_secret: a store with no Stripe keys is
    # misconfigured, and should say so at boot naming the missing field rather
    # than surface as a confusing Stripe error halfway through a checkout.
    #
    # The SECRET key never leaves the server -- it can create charges, issue
    # refunds and read every customer. SecretStr so a traceback or a stray log
    # of settings prints '**********' instead of the key itself; read the real
    # value with .get_secret_value() at the one place that talks to Stripe.
    stripe_secret_key: SecretStr

    # Designed to be public and shipped to the browser, so no SecretStr. It can
    # only start a payment the secret key already authorised.
    stripe_publishable_key: str

    # Filled in at task 4, when the webhook endpoint exists -- until then it is
    # absent from .env, so it needs a default. Declared now anyway: every key in
    # .env.example must be a field here, and test_config.py enforces that.
    stripe_webhook_secret: SecretStr = SecretStr("")

    # Which PaymentGateway implementation to build (app/services/payments.py).
    # "stripe" talks to the real API in test mode; "fake" is in-memory, for
    # working offline. Tests do not use this -- they override the dependency
    # directly, so the suite never depends on how a laptop happens to be set up.
    payment_gateway: str = "stripe"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
