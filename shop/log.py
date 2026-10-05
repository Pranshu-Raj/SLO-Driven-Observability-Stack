import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# anything on a record that isn't in this set was passed through extra={...}
_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def __init__(self, static: dict[str, str]):
        super().__init__()
        self.static = static

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            **self.static,
        }
        rid = request_id.get()
        if rid:
            entry["request_id"] = rid
        entry.update((k, v) for k, v in vars(record).items() if k not in _STANDARD)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup(service: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            {
                "service": service,
                "env": os.environ.get("APP_ENV", "dev"),
                "version": os.environ.get("APP_VERSION", "dev"),
            }
        )
    )
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, handlers=[handler], force=True)
