from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    # Signing key for JWTs. Local development uses the value in .env; production
    # draws a different one from AWS Secrets Manager (Section 4.2). A leaked
    # development secret must never be able to forge production tokens.
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
