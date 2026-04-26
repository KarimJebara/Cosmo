"""Env-driven configuration. Loaded once at import time."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str | None = None) -> str:
    val = os.environ.get(name)
    if val is None or val == "":
        if default is None:
            raise RuntimeError(f"Missing required env var: {name}")
        return default
    return val


@dataclass(frozen=True)
class Config:
    secret_key: str
    database_url: str
    default_base_currency: str
    fx_provider: str
    log_level: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            secret_key=_get("SECRET_KEY", "dev-only-do-not-use-in-prod"),
            database_url=_get("DATABASE_URL", "sqlite:///data/budget_tracker.db"),
            default_base_currency=_get("DEFAULT_BASE_CURRENCY", "EUR"),
            fx_provider=_get("FX_PROVIDER", "frankfurter"),
            log_level=_get("LOG_LEVEL", "INFO"),
        )


CONFIG = Config.from_env()
