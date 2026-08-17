"""Shared HTTP plumbing for external platforms.

Rules every integration inherits:

* bounded timeouts — a hanging upstream never hangs a request;
* exponential backoff with jitter on transient failures only;
* a minimum interval between calls, because Codeforces bans for hammering;
* a small TTL cache, so repeated dashboard loads do not re-fetch;
* typed exceptions, so callers can degrade gracefully instead of 500-ing.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class IntegrationError(Exception):
    """Base class for upstream failures."""

    def __init__(self, service: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.service = service
        self.message = message
        self.retryable = retryable


class RateLimited(IntegrationError):
    def __init__(self, service: str, retry_after: float | None = None) -> None:
        super().__init__(service, f"{service} rate limit reached", retryable=True)
        self.retry_after = retry_after


class NotAvailable(IntegrationError):
    """The upstream is unreachable or erroring. Expected, not exceptional."""


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """Tiny thread-safe TTL cache. Avoids Redis for a local-first app."""

    def __init__(self, default_ttl: float = 300.0) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            self._store[key] = CacheEntry(
                value=value, expires_at=time.monotonic() + (ttl or self._default_ttl)
            )

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class BaseClient:
    """HTTP client with retry, throttle and cache."""

    service_name = "external"
    #: Minimum seconds between outbound calls to this service.
    min_interval = 0.0
    default_cache_ttl = 300.0

    _last_call_at: dict[str, float] = {}
    _throttle_lock = threading.Lock()

    def __init__(self, *, timeout: float | None = None, cache: TTLCache | None = None):
        self.timeout = timeout or settings.external_timeout_seconds
        self.cache = cache or _shared_cache
        self.max_retries = settings.external_max_retries

    def _throttle(self) -> None:
        if not self.min_interval:
            return
        with BaseClient._throttle_lock:
            last = BaseClient._last_call_at.get(self.service_name, 0.0)
            wait = self.min_interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            BaseClient._last_call_at[self.service_name] = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        *,
        cache_key: str | None = None,
        cache_ttl: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        if cache_key:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    response = client.request(method, url, **kwargs)

                if response.status_code == 429:
                    retry_after = _parse_retry_after(response)
                    if attempt == self.max_retries - 1:
                        raise RateLimited(self.service_name, retry_after)
                    time.sleep(retry_after or _backoff(attempt))
                    continue

                if response.status_code >= 500:
                    if attempt == self.max_retries - 1:
                        raise NotAvailable(
                            self.service_name,
                            f"{self.service_name} returned {response.status_code}",
                            retryable=True,
                        )
                    time.sleep(_backoff(attempt))
                    continue

                if cache_key:
                    self.cache.set(cache_key, response, cache_ttl or self.default_cache_ttl)
                return response

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(_backoff(attempt))

        raise NotAvailable(
            self.service_name,
            f"Could not reach {self.service_name}: {last_error}",
            retryable=True,
        ) from last_error

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.request("GET", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise NotAvailable(
                self.service_name, f"{self.service_name} returned a non-JSON response"
            ) from exc

    def post_json(self, url: str, **kwargs: Any) -> Any:
        response = self.request("POST", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise NotAvailable(
                self.service_name, f"{self.service_name} returned a non-JSON response"
            ) from exc


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter, capped so retries stay bounded."""
    return min(8.0, (2**attempt) * 0.5) + random.uniform(0, 0.4)


def _parse_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


_shared_cache = TTLCache()
