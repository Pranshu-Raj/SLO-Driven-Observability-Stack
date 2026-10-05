import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

REQUIRED = {
    "api": ("REDIS_URL",),
    "worker": ("REDIS_URL",),
    "frontend": ("API_URL",),
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    service: str
    port: int = 8000
    redis_url: str = field(default="", repr=False)
    api_url: str = ""
    api_timeout: float = 2.0
    work_ms: int = 200

    @classmethod
    def from_env(cls, service: str, env: Mapping[str, str] = os.environ) -> Settings:
        missing = [name for name in REQUIRED[service] if not env.get(name)]
        if missing:
            raise ConfigError(f"missing required settings: {', '.join(missing)}")

        return cls(
            service=service,
            port=_number(env, "PORT", 8000, int),
            redis_url=env.get("REDIS_URL", ""),
            api_url=env.get("API_URL", ""),
            api_timeout=_number(env, "API_TIMEOUT_SECONDS", 2.0, float),
            work_ms=_number(env, "WORK_MS", 200, int),
        )


def _number[T: (int, float)](env: Mapping[str, str], name: str, default: T, kind: type[T]) -> T:
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = kind(raw)
    except ValueError:
        raise ConfigError(f"{name} must be {kind.__name__}, got {raw!r}") from None
    if value < 0:
        raise ConfigError(f"{name} must not be negative")
    return value


def load(service: str) -> Settings:
    try:
        return Settings.from_env(service)
    except ConfigError as exc:
        logging.getLogger(f"shop.{service}").critical("refusing to start: %s", exc)
        raise SystemExit(2) from None


def redact(url: str) -> str:
    parts = urlsplit(url)
    if not parts.password:
        return url
    return url.replace(f":{parts.password}@", ":***@", 1)
