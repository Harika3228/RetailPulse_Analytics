"""Simple in-memory TTL cache for expensive computations (forecasts, analytics)."""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

_DEFAULT_TTL = 300  # 5 minutes


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL expiry."""

    def __init__(self, default_ttl: int = _DEFAULT_TTL, max_entries: int = 256) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_entries = max_entries

    @staticmethod
    def _make_key(*parts: Any) -> str:
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            if len(self._store) >= self._max_entries and key not in self._store:
                self._evict_oldest()
            self._store[key] = (time.monotonic() + (ttl or self._default_ttl), value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._store[k]

    def invalidate_all(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict_oldest(self) -> None:
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k][0])
        del self._store[oldest_key]


# Module-level singleton shared across the application
forecast_cache = TTLCache(default_ttl=300, max_entries=128)
analytics_cache = TTLCache(default_ttl=180, max_entries=64)


def get_cached_forecast(company_id: int, endpoint: str, **params: Any) -> Any | None:
    key = TTLCache._make_key("forecast", company_id, endpoint, *sorted(params.items()))
    return forecast_cache.get(key)


def set_cached_forecast(company_id: int, endpoint: str, value: Any, ttl: int = 300, **params: Any) -> None:
    key = TTLCache._make_key("forecast", company_id, endpoint, *sorted(params.items()))
    forecast_cache.set(key, value, ttl=ttl)


def invalidate_forecast_cache(company_id: int) -> None:
    forecast_cache.invalidate_prefix(TTLCache._make_key("forecast", company_id))


def get_cached_analytics(company_id: int, endpoint: str, **params: Any) -> Any | None:
    key = TTLCache._make_key("analytics", company_id, endpoint, *sorted(params.items()))
    return analytics_cache.get(key)


def set_cached_analytics(company_id: int, endpoint: str, value: Any, ttl: int = 180, **params: Any) -> None:
    key = TTLCache._make_key("analytics", company_id, endpoint, *sorted(params.items()))
    analytics_cache.set(key, value, ttl=ttl)
