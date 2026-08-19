from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite/Postgres dialect-safe, lexicographically sortable)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, index=True)
    mac_address: Mapped[str] = mapped_column(String(17), default="")
    device_type: Mapped[str] = mapped_column(String(64), default="")
    os_guess: Mapped[str] = mapped_column(String(64), default="")
    vendor: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # up | down | warn | unknown
    ping_ms: Mapped[float] = mapped_column(Float, default=0.0)
    uptime_pct: Mapped[float] = mapped_column(Float, default=0.0)
    open_ports: Mapped[str] = mapped_column(String(512), default="")
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    total_checks: Mapped[int] = mapped_column(Integer, default=0)
    total_ups: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PingHistory(Base):
    __tablename__ = "ping_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    ping_ms: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), index=True)  # crit | warn | new | info
    message: Mapped[str] = mapped_column(Text, default="")
    device_ip: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    resolved: Mapped[int] = mapped_column(Integer, default=0)


class BandwidthLog(Base):
    __tablename__ = "bandwidth_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interface: Mapped[str] = mapped_column(String(64), index=True)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
