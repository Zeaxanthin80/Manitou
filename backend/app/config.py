from urllib.parse import quote

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    #: The connection string, supplied directly OR assembled from the DB_* fields.
    #:
    #: Two ways in, because the two environments hand credentials over
    #: differently. Development sets this whole string in .env. Production
    #: cannot: ECS injects the password from the RDS-managed Secrets Manager
    #: secret as its own variable, and that secret holds `{username, password}`
    #: JSON rather than a URL.
    #:
    #: Reading the RDS secret directly is the point -- the alternative is copying
    #: the password into a second secret holding a full URL, which goes stale the
    #: moment RDS rotates and fails as a connection error naming nothing. It has
    #: already been rotated twice by hand during Phase 6.
    #:
    #: Empty rather than required so the assembly below can fill it. The
    #: boot-time failure a required field gave is preserved by the validator,
    #: which raises when neither form is complete.
    database_url: str = ""

    # --- the assembly path, for production ----------------------------------
    #: Unset in development, where DATABASE_URL is given whole.
    db_host: str = ""
    db_port: int = 5432
    db_user: str = ""
    db_name: str = ""
    db_password: SecretStr = SecretStr("")

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

    # --- media storage (Phase 6 task 9) --------------------------------------
    #: The private S3 bucket product photographs are uploaded to, and the
    #: CloudFront host they are served from. Block Public Access is on: nothing
    #: reads the bucket directly, only the distribution does, via OAC.
    #:
    #: All three default to empty, so **local development needs no AWS at all**.
    #: An empty bucket name means the upload endpoints refuse rather than
    #: half-work -- see uploads.py. Seeded images keep pointing at web/public/,
    #: which is why product_images.url survives alongside asset_id.
    s3_bucket: str = ""
    s3_region: str = "us-east-1"

    #: The CloudFront domain, no scheme -- e.g. "d111111abcdef8.cloudfront.net".
    #:
    #: Load-bearing in two places that must agree: web/next.config.ts lists it in
    #: images.remotePatterns, and AdminImageCreate widens its URL validator to
    #: accept exactly this host. Both exist because defect 1 -- one external
    #: image URL made next/image throw at RENDER time and took down the home
    #: page, the product page and the admin edit page together, and the edit page
    #: was the only place that could remove it.
    #:
    #: So this is an allow-list of one, not permission for https generally.
    cdn_host: str = ""

    @model_validator(mode="after")
    def _assemble_database_url(self) -> "Settings":
        """Build database_url from the DB_* parts when it was not supplied whole.

        **The password is percent-encoded**, and the reason is narrower than it
        looks. SQLAlchemy's make_url is a lenient parser: measured, it reads a
        raw `#`, `)`, `%` and `/` in the password position correctly, so this is
        not fixing a bug in the path we use today.

        It is encoded because the encoded form is the RFC 3986-correct one, and
        `database_url` is a plain string that anything may consume -- a psql
        invocation, a future migration runner, libpq directly. Depending on one
        parser's tolerance is a bet renewed every time a new consumer appears.
        `safe=""` because quote() leaves `/` alone by default, and `/` ends the
        authority section in a stricter parser.

        Note this does NOT create defect 21 (percent-encoding breaking
        configparser in alembic/env.py). A password containing a literal `%` --
        which RDS can generate -- puts a `%` in the URL whether or not we encode,
        so env.py's `%%` escape was always required. Encoding only makes it
        surface sooner.

        sslmode=require because assembly only ever happens against RDS, and the
        connection crosses a network. Development sets DATABASE_URL directly and
        keeps whatever mode it wants.

        Raising here rather than defaulting to something: a misconfigured store
        should fail at boot naming the missing field, not at the first request
        with a connection error. Same instinct as validate_gateway_name in
        main.py and as defect 12.
        """
        if self.database_url:
            return self

        missing = [
            name
            for name, value in (
                ("DB_HOST", self.db_host),
                ("DB_USER", self.db_user),
                ("DB_NAME", self.db_name),
                ("DB_PASSWORD", self.db_password.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Set DATABASE_URL, or all of DB_HOST/DB_USER/DB_NAME/DB_PASSWORD "
                f"so it can be assembled. Missing: {', '.join(missing)}."
            )

        password = quote(self.db_password.get_secret_value(), safe="")
        self.database_url = (
            f"postgresql://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?sslmode=require"
        )
        return self

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
