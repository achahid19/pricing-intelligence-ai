from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/pricing_intelligence"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://user:password@localhost:5432/pricing_intelligence"

    # Signs auth tokens — separate from FERNET_ENCRYPTION_KEY below on purpose.
    JWT_SECRET_KEY: str = "dev-only-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Encrypts each workspace's stored AI provider key at rest (Fernet).
    # Generate once via Fernet.generate_key() and never rotate casually —
    # rotating it breaks decryption of every already-stored key.
    FERNET_ENCRYPTION_KEY: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
