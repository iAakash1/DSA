"""Structured logging.

JSON in production so logs are greppable/ingestable; human-readable in dev.
Secrets are never logged — `scrub()` is applied to any dict we emit.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.core.config import settings

_SECRET_HINTS = ("key", "token", "secret", "password", "authorization", "cookie")


def scrub(payload: dict[str, Any]) -> dict[str, Any]:
    """Redact anything that looks like a credential."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if any(hint in k.lower() for hint in _SECRET_HINTS):
            out[k] = "***redacted***"
        elif isinstance(v, dict):
            out[k] = scrub(v)
        else:
            out[k] = v
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            base.update(scrub(extra))
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)


class DevFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[38;5;244m",
        "INFO": "\033[38;5;39m",
        "WARNING": "\033[38;5;214m",
        "ERROR": "\033[38;5;196m",
        "CRITICAL": "\033[48;5;196m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        head = f"{color}{record.levelname:<8}{self.RESET} {record.name}"
        msg = record.getMessage()
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict) and extra:
            kv = " ".join(f"{k}={v}" for k, v in scrub(extra).items())
            msg = f"{msg} \033[38;5;244m{kv}{self.RESET}"
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"
        return f"{head} | {msg}"


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if settings.app_env == "production" else DevFormatter()
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # These are chatty and rarely useful at INFO.
    for noisy in ("httpx", "httpcore", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> "BoundLogger":
    return BoundLogger(logging.getLogger(name))


class BoundLogger:
    """Thin wrapper giving every log call keyword-structured fields."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _log(self, level: int, msg: str, **fields: Any) -> None:
        self._logger.log(level, msg, extra={"extra_fields": fields})

    def debug(self, msg: str, **f: Any) -> None:
        self._log(logging.DEBUG, msg, **f)

    def info(self, msg: str, **f: Any) -> None:
        self._log(logging.INFO, msg, **f)

    def warning(self, msg: str, **f: Any) -> None:
        self._log(logging.WARNING, msg, **f)

    def error(self, msg: str, **f: Any) -> None:
        self._log(logging.ERROR, msg, **f)

    def exception(self, msg: str, **f: Any) -> None:
        self._logger.exception(msg, extra={"extra_fields": f})
