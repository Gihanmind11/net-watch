from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NetWatch API"
    version: str = "2.0.0"

    # Database — PostgreSQL + TimescaleDB recommended; SQLite for zero-setup dev.
    database_url: str = "sqlite:///./netmon.db"
    redis_url: str = ""

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
    ]

    # Auth (single demo admin account)
    demo_user: str = "admin"
    demo_password: str = "admin"
    secret_key: str = "please-change-me-in-production"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Scanning & monitoring
    network_cidr: str = "192.168.1.0/24"
    scan_interval_sec: int = 30
    ping_interval_sec: int = 30
    bandwidth_interval_sec: int = 2
    latency_warn_ms: int = 30
    latency_crit_ms: int = 100
    ping_fail_count: int = 3
    max_concurrent_pings: int = 32
    sniffing_enabled: bool = False

    # Storage
    history_retention_days: int = 30
    demo_seed_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
