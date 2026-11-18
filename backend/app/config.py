from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated


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

    # --- Cloud deployment ---------------------------------------------------
    # Authentication: Firebase Auth (Google sign-in). When enabled, every /api route except
    # /api/health and /api/config needs a valid ID token from an allowed e-mail address.
    auth_enabled: bool = False
    firebase_project_id: str | None = None
    firebase_api_key: str | None = None  # web config values are public identifiers, not secrets
    firebase_auth_domain: str | None = None
    allowed_emails: Annotated[list[str], NoDecode] = []  # comma separated in the environment
    # Anyone with a verified Google account may sign up (each user only sees their own data).
    # Without it, ALLOWED_EMAILS is required: an unconfigured deployment stays closed.
    open_signup: bool = False
    # E-mail that inherits the data created before per-user accounts existed (migration, runs at startup).
    legacy_data_owner: str | None = None

    # Cloud SQL (PostgreSQL) through the Cloud Run unix socket, as an alternative to DATABASE_URL.
    db_user: str | None = None
    db_password: str | None = None
    db_name: str | None = None
    cloud_sql_connection_name: str | None = None  # project:region:instance

    @field_validator("legacy_data_owner", mode="before")
    @classmethod
    def lowercase_owner(cls, value):
        return value.strip().lower() if isinstance(value, str) and value.strip() else None

    @field_validator("allowed_emails", mode="before")
    @classmethod
    def split_emails(cls, value):
        if isinstance(value, str):
            return [email.strip().lower() for email in value.split(",") if email.strip()]
        return [email.lower() for email in value]

    default_currency: str = "EUR"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Built frontend (vite build). When the folder exists the backend serves it,
    # so one process is enough: http://localhost:8000
    frontend_dist: Path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.cloud_sql_connection_name and self.db_user and self.db_name:
            from urllib.parse import quote_plus

            password = quote_plus(self.db_password or "")
            return f"postgresql+psycopg2://{quote_plus(self.db_user)}:{password}@/{self.db_name}?host=/cloudsql/{self.cloud_sql_connection_name}"
        return f"sqlite:///{self.data_dir / 'spendings.db'}"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.documents_dir.mkdir(parents=True, exist_ok=True)
