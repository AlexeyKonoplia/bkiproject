from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    AUTH_MODE: str = "hybrid"

    POSTGRES_DB: str = "bki"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    OLLAMA_BASE_URL: str = "http://ollama:11434"

    JWT_SECRET: str = "change_me_super_secret"
    JWT_ALGORITHM: str = "HS256"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin_password_change_me"
    ENABLE_BOOTSTRAP_ADMIN: bool = True

    PORTAL_JWT_SECRET: str = "change_me_portal_secret"
    PORTAL_JWT_ALGORITHM: str = "HS256"
    PORTAL_JWT_ISSUER: str | None = None
    PORTAL_JWT_AUDIENCE: str | None = None
    PORTAL_SUB_CLAIM: str = "sub"
    PORTAL_USERNAME_CLAIM: str = "preferred_username"
    PORTAL_ROLES_CLAIM: str = "roles"
    PORTAL_AUTO_PROVISION_USERS: bool = True

    # Embeddings / LLM defaults (used later in ingestion & RAG)
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768
    LLM_MODEL: str = "qwen2.5:7b"
    VERIFIER_LLM_MODEL: str | None = None
    LLM_NUM_CTX: int = 4096
    LLM_NUM_PREDICT: int = 512
    LLM_KEEP_ALIVE: str = "10m"

    # Chunking defaults (used later in ingestion)
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150

    ENABLE_SELF_CORRECTION: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        # asyncpg connection string
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()

