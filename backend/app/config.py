from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Every value can be overridden by an environment
    variable of the same name (or a `.env` file next to the backend)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where SQLite DB and uploaded documents live when running locally.
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    database_url: str | None = None

    # "local" today; "gcs" later (Cloud Storage bucket) without touching the routers.
    storage_backend: str = "local"
    gcs_bucket: str | None = None

    # Optional: enables Claude for unknown document layouts and category suggestions.
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"

    default_currency: str = "EUR"
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'spendings.db'}"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.documents_dir.mkdir(parents=True, exist_ok=True)
