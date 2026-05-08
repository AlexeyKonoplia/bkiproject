from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    AUTH_MODE: str = "hybrid"

    POSTGRES_DB: str = "bki"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    APP_API_URL: str = "http://app:8000"
    APP_API_TIMEOUT_SECONDS: float = 180.0

    JWT_SECRET: str = "change_me_super_secret"
    JWT_ALGORITHM: str = "HS256"

    PORTAL_JWT_SECRET: str = "change_me_portal_secret"
    PORTAL_JWT_ALGORITHM: str = "HS256"
    PORTAL_JWT_ISSUER: str | None = None
    PORTAL_JWT_AUDIENCE: str | None = None
    PORTAL_SUB_CLAIM: str = "sub"
    PORTAL_USERNAME_CLAIM: str = "preferred_username"
    PORTAL_ROLES_CLAIM: str = "roles"
    PORTAL_AUTO_PROVISION_USERS: bool = True

    PORTAL_API_PREFIX: str = "/api"
    PORTAL_TITLE: str = "bki-document-portal"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
