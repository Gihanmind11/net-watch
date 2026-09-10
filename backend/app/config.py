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
    ping_interval_sec: int = 5
    bandwidth_interval_sec: int = 2
    latency_warn_ms: int = 30
    latency_crit_ms: int = 100
    max_concurrent_pings: int = 32
    sniffing_enabled: bool = False

    # Port scan (plain TCP connect — no raw-socket privileges needed). Results
    # populate the OPEN PORTS column in the Devices table. The list is kept
    # short so each 30 s discovery cycle stays fast; closed LAN ports normally
    # answer with RST immediately, the timeout only bounds hosts that drop
    # packets silently.
    port_scan_enabled: bool = True
    port_scan_timeout_sec: float = 0.25
    port_scan_ports: str = "22,23,53,80,139,443,445,515,554,631,1883,3389,5000,5900,8000,8080,8443,9100,62078"

    # Whole-LAN traffic via SNMP polling of the router/gateway. When the router
    # does not answer (SNMP disabled / wrong community / unsupported device) the
    # dashboard silently falls back to this host's own counters.
    snmp_enabled: bool = True
    snmp_host: str = ""  # empty → poll the auto-detected default gateway
    snmp_community: str = "public"
    snmp_version: str = "2c"  # "1" or "2c"
    snmp_port: int = 161
    snmp_timeout_sec: float = 1.0
    snmp_interface: str = ""  # empty → auto-pick the router's busiest interface
    snmp_interval_sec: int = 5

    # Storage
    history_retention_days: int = 30
    demo_seed_enabled: bool = False
    # Grace window before a device absent from discovery is dropped. Wireless
    # clients behind home broadband routers sleep often and disappear from
    # ARP/ping for a while — a single missed scan is not proof of disconnect.
    stale_device_grace_sec: int = 300

    @property
    def port_scan_port_list(self) -> list[int]:
        """`port_scan_ports` as a de-duplicated, sorted list of valid ports."""
        ports: set[int] = set()
        for part in self.port_scan_ports.split(","):
            part = part.strip()
            if part.isdigit() and 0 < int(part) < 65536:
                ports.add(int(part))
        return sorted(ports)


@lru_cache
def get_settings() -> Settings:
    return Settings()
