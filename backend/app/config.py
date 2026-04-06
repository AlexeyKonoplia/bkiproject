from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_DB: str = "bki"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    OLLAMA_BASE_URL: str = "http://ollama:11434"

    JWT_SECRET: str = "change_me_super_secret"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin_password_change_me"
    ENABLE_BOOTSTRAP_ADMIN: bool = True

    # Embeddings / LLM defaults (used later in ingestion & RAG)
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768
    LLM_MODEL: str = "llama3:8b"

    # Chunking defaults (used later in ingestion)
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150

    ENABLE_SELF_CORRECTION: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        # asyncpg connection string
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()

