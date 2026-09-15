from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. NetWatch keeps users in Supabase Postgres — copy the "
        "project's connection string (Supabase → Project Settings → Database → Connection "
        "string) into backend/.env as DATABASE_URL. There is no local database fallback."
    )

# pool_pre_ping absorbs the idle-connection drops of the Supabase pooler.
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(engine)
