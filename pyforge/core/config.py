"""Environment Configuration & Startup Validation (Sections 33 & 34)."""
import os
from dataclasses import dataclass

VALID_ENVIRONMENTS = {"development", "testing", "staging", "production"}

@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    secret_key: str
    session_cookie_name: str
    session_ttl_seconds: int
    allowed_origins: list[str]
    sandbox_timeout_seconds: float
    sandbox_memory_mb: int
    sandbox_max_output_bytes: int
    webhook_secret: str

def load_settings(env_override: str | None = None) -> Settings:
    env = (env_override or os.environ.get("PYFORGE_ENV", "development")).lower().strip()
    if env not in VALID_ENVIRONMENTS:
        raise ValueError(f"Invalid PYFORGE_ENV '{env}'. Must be one of {sorted(VALID_ENVIRONMENTS)}")

    secret_key = os.environ.get("PYFORGE_SECRET_KEY", "")
    db_url = os.environ.get("DATABASE_URL", "")
    webhook_secret = os.environ.get("PYFORGE_WEBHOOK_SECRET", "")

    if env in ("production", "staging"):
        missing = []
        if not secret_key or len(secret_key) < 32:
            missing.append("PYFORGE_SECRET_KEY (min 32 chars)")
        if not db_url:
            missing.append("DATABASE_URL")
        if not webhook_secret:
            missing.append("PYFORGE_WEBHOOK_SECRET")
        if missing:
            raise RuntimeError(f"Critical configuration missing for {env} startup: {', '.join(missing)}")
    else:
        if not secret_key:
            secret_key = "dev-test-only-ephemeral-key-do-not-use-in-prod-0123456789"
        if not db_url:
            db_url = "sqlite:///./pyforge_dev.db"
        if not webhook_secret:
            webhook_secret = "dev-test-webhook-secret-key"

    origins_raw = os.environ.get("PYFORGE_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    allowed_origins = [o.strip() for o in origins_raw.split(",") if o.strip() and o.strip() != "*"]
    if not allowed_origins:
        allowed_origins = ["http://localhost:3000"]

    return Settings(
        env=env,
        database_url=db_url,
        secret_key=secret_key,
        session_cookie_name="pyforge_session",
        session_ttl_seconds=int(os.environ.get("PYFORGE_SESSION_TTL", "86400")),
        allowed_origins=allowed_origins,
        sandbox_timeout_seconds=float(os.environ.get("PYFORGE_SANDBOX_TIMEOUT", "2.5")),
        sandbox_memory_mb=int(os.environ.get("PYFORGE_SANDBOX_MEMORY_MB", "64")),
        sandbox_max_output_bytes=int(os.environ.get("PYFORGE_SANDBOX_MAX_OUTPUT", "16384")),
        webhook_secret=webhook_secret,
    )
