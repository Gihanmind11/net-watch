from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _enable_timescale(engine) -> None:
    """Convert time-series tables to TimescaleDB hypertables when available."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        except Exception:
            return
        for table, column in (("ping_history", "checked_at"), ("bandwidth_logs", "recorded_at")):
            try:
                conn.execute(
                    text(
                        f"SELECT create_hypertable('{table}', '{column}', "
                        f"if_not_exists => TRUE, migrate_data => TRUE)"
                    )
                )
            except Exception:
                pass
        try:
            conn.execute(
                text("SELECT add_retention_policy('ping_history', INTERVAL '90 days', if_not_exists => TRUE)")
            )
            conn.execute(
                text("SELECT add_retention_policy('bandwidth_logs', INTERVAL '30 days', if_not_exists => TRUE)")
            )
        except Exception:
            pass


def init_db() -> None:
    from . import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(engine)
    _enable_timescale(engine)
