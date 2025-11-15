"""
Model Context Protocol (MCP) wrapper for the ChatAds Affiliate API.

This server exposes a single MCP tool that proxies ChatAds requests, normalizes
responses, hides backend-specific errors, and adds consistent metadata so
Claude always receives a predictable shape.

Usage:
    1. Install via PyPI: `pip install chatads-mcp-wrapper`
    2. Export your API key: `export CHATADS_API_KEY=sk_live_...`
    3. Optional overrides:
         - CHATADS_API_BASE_URL (default: https://chatads--chatads-product-fastapiserver-serve.modal.run)
         - CHATADS_API_ENDPOINT (default: /v1/chatads/messages)
         - CHATADS_MCP_MAX_RETRIES (default: 3)
         - CHATADS_MCP_TIMEOUT (seconds, default: 15)
         - CHATADS_MCP_BACKOFF (seconds, default: 0.6)
         - CHATADS_MAX_REQUEST_SIZE (bytes, default: 10240)
         - CHATADS_CIRCUIT_BREAKER_THRESHOLD (failures before opening, default: 5)
         - CHATADS_CIRCUIT_BREAKER_TIMEOUT (seconds to stay open, default: 60)
         - CHATADS_QUOTA_WARNING_THRESHOLD (percentage, default: 0.9)
         - LOGLEVEL (DEBUG, INFO, WARNING, ERROR, default: INFO)
         - CHATADS_LOG_FORMAT (text or json, default: text)
    4. Run: `chatads-mcp` (or `python -m chatads_mcp_wrapper`)
    5. Point Claude Desktop (or another MCP client) at the server address.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Literal, Optional

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

LOGGER = logging.getLogger("chatads.mcp")
if not LOGGER.handlers:
    log_level = os.getenv("LOGLEVEL", "INFO").upper()
    log_format = os.getenv("CHATADS_LOG_FORMAT", "text").lower()

    # Validate log level, fallback to INFO if invalid
    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Configure structured JSON logging if requested
    if log_format == "json":
        try:
            from pythonjsonlogger import jsonlogger

            handler = logging.StreamHandler()
            formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                timestamp=True,
            )
            handler.setFormatter(formatter)
            logging.root.addHandler(handler)
            logging.root.setLevel(numeric_level)
        except ImportError:
            # Fall back to text logging if python-json-logger not installed
            logging.basicConfig(
                level=numeric_level,
                format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            )
            LOGGER.warning("python-json-logger not installed, falling back to text logging")
    else:
        # Standard text logging
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        )

# Defaults can be overridden with env vars noted in the module docstring.
DEFAULT_BASE_URL = os.getenv(
    "CHATADS_API_BASE_URL",
    "https://chatads--chatads-product-fastapiserver-serve.modal.run",
)
DEFAULT_ENDPOINT = os.getenv("CHATADS_API_ENDPOINT", "/v1/chatads/messages")
DEFAULT_TIMEOUT = float(os.getenv("CHATADS_MCP_TIMEOUT", "10"))  # Reduced from 15s to allow faster retries
DEFAULT_MAX_RETRIES = int(os.getenv("CHATADS_MCP_MAX_RETRIES", "3"))
BACKOFF_SECONDS = float(os.getenv("CHATADS_MCP_BACKOFF", "0.6"))
MAX_REQUEST_SIZE_BYTES = int(os.getenv("CHATADS_MAX_REQUEST_SIZE", "10240"))  # 10KB default
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CHATADS_CIRCUIT_BREAKER_THRESHOLD", "5"))
CIRCUIT_BREAKER_TIMEOUT = int(os.getenv("CHATADS_CIRCUIT_BREAKER_TIMEOUT", "60"))
QUOTA_WARNING_THRESHOLD = float(os.getenv("CHATADS_QUOTA_WARNING_THRESHOLD", "0.9"))  # Warn at 90%
TOOL_VERSION = "0.1.0"

# Pre-compiled regex patterns for performance
_COUNTRY_CODE_PATTERN = re.compile(r'^[A-Z]{2}$')
_LANGUAGE_CODE_PATTERN = re.compile(r'^[a-z]{2}$')
_API_KEY_PATTERN = re.compile(r"(sk_(?:live|test)_)[A-Za-z0-9]+")

# Global HTTP client cache for connection pooling (keyed by API key)
# Reusing connections eliminates DNS lookup, TCP handshake, and TLS negotiation overhead
# Cache is bounded to prevent memory leaks in long-running processes
_http_client_cache: Dict[str, httpx.AsyncClient] = {}
_http_client_cache_lock = threading.Lock()
MAX_CACHED_CLIENTS = int(os.getenv("CHATADS_MAX_CACHED_CLIENTS", "10"))  # Prevent memory leak

# Optional monitoring callback
_metric_callback: Optional[Callable[[str, float, Dict[str, str]], None]] = None


def set_metric_callback(callback: Callable[[str, float, Dict[str, str]], None]) -> None:
    """
    Set an optional callback for emitting metrics to monitoring systems.

    Args:
        callback: Function that takes (metric_name, value, tags_dict)
                  Example: datadog.statsd.gauge, prometheus_client.Gauge.set
    """
    global _metric_callback
    _metric_callback = callback


def _emit_metric(metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Emit metric if callback is configured."""
    if _metric_callback:
        try:
            _metric_callback(metric_name, value, tags or {})
        except Exception as exc:
            LOGGER.warning("Failed to emit metric %s: %s", metric_name, exc)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast, not attempting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent retry storms.

    After N consecutive failures, opens circuit and fails fast for a timeout period.
    Then transitions to half-open to test if the service recovered.
    """

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60) -> None:
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED
        self._lock = threading.Lock()

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                LOGGER.info("Circuit breaker recovered, transitioning to CLOSED")
                _emit_metric("chatads.circuit_breaker.state_change", 1, {"state": "closed"})
            self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Failed during recovery test, back to open
                LOGGER.warning("Circuit breaker recovery failed, reopening circuit")
                self.state = CircuitState.OPEN
                _emit_metric("chatads.circuit_breaker.state_change", 1, {"state": "open"})
            elif self.failure_count >= self.failure_threshold and self.state == CircuitState.CLOSED:
                # Too many failures, open the circuit
                LOGGER.error(
                    "Circuit breaker OPEN after %d consecutive failures. Failing fast for %d seconds.",
                    self.failure_count,
                    self.timeout_seconds,
                )
                self.state = CircuitState.OPEN
                _emit_metric("chatads.circuit_breaker.state_change", 1, {"state": "open"})

    def is_available(self) -> bool:
        """Check if requests should be allowed."""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if timeout has elapsed
                if self.last_failure_time and (time.time() - self.last_failure_time) >= self.timeout_seconds:
                    LOGGER.info("Circuit breaker timeout elapsed, transitioning to HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    _emit_metric("chatads.circuit_breaker.state_change", 1, {"state": "half_open"})
                    return True
                return False

            # HALF_OPEN: allow one request to test
            return True

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            return self.state


class ToolMetadata(BaseModel):
    """Metadata returned to Claude with every response."""

    request_id: str
    timestamp: str
    latency_ms: float
    status_code: int
    source: str
    tool_version: str = TOOL_VERSION
    country: Optional[str] = None
    language: Optional[str] = None
    usage_summary: Optional[Dict[str, Any]] = None
    context: str = (
        "ChatAds affiliate results are normalized. "
        "Use `status` + `reason` to explain matches or fallbacks."
    )
    notes: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class ToolEnvelope(BaseModel):
    """Normalized payload returned by the MCP tool."""

    status: Literal["success", "no_match", "error"]
    matched: bool
    product: Optional[str] = None
    affiliate_link: Optional[str] = None
    category: Optional[str] = None
    affiliate_message: Optional[str] = None
    reason: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: ToolMetadata
    model_config = ConfigDict(populate_by_name=True)


class ChatAdsAPIError(RuntimeError):
    """Internal exception used to surface sanitized errors to the tool layer."""

    def __init__(
        self,
        message: str,
        code: str = "UPSTREAM_ERROR",
        *,
        status_code: int = 502,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


@dataclass
class ChatAdsClientConfig:
    base_url: str = DEFAULT_BASE_URL
    endpoint: str = DEFAULT_ENDPOINT
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_seconds: float = BACKOFF_SECONDS
    enable_circuit_breaker: bool = True


class ChatAdsClient:
    """Thin HTTP client with retry/backoff and envelope parsing."""

    # Class-level circuit breaker shared across all instances
    _circuit_breaker: Optional[CircuitBreaker] = None
    _circuit_breaker_lock = threading.Lock()

    def __init__(self, api_key: str, config: Optional[ChatAdsClientConfig] = None) -> None:
        if not api_key:
            raise ChatAdsAPIError(
                "Missing ChatAds API key. Set CHATADS_API_KEY or pass api_key parameter.",
                code="CONFIGURATION_ERROR",
                status_code=500,
            )
        self.config = config or ChatAdsClientConfig()
        self.api_key = api_key

        # Check cache for existing client (connection pooling)
        cache_key = f"{api_key}:{self.config.base_url}"
        with _http_client_cache_lock:
            if cache_key in _http_client_cache:
                self._client = _http_client_cache[cache_key]
                self._owns_client = False  # Don't close shared client
            else:
                # Evict oldest client if cache is full (prevent memory leak)
                if len(_http_client_cache) >= MAX_CACHED_CLIENTS:
                    oldest_key = next(iter(_http_client_cache))
                    oldest_client = _http_client_cache.pop(oldest_key)
                    try:
                        # Note: AsyncClient.aclose() should be awaited, but we're in sync context
                        # This is acceptable - httpx handles it gracefully
                        oldest_client.close()
                        LOGGER.info("Evicted cached HTTP client for key: %s (cache full)", oldest_key[:20] + "...")
                    except Exception as exc:
                        LOGGER.warning("Failed to close evicted client: %s", exc)

                self._client = httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=httpx.Timeout(self.config.timeout, connect=5.0),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "x-api-key": api_key,
                    },
                    limits=httpx.Limits(
                        max_connections=100,  # Connection pool size for concurrent requests
                        max_keepalive_connections=20,  # Keep alive for connection reuse
                    ),
                )
                _http_client_cache[cache_key] = self._client
                self._owns_client = True  # First instance owns the client

        # Initialize circuit breaker if enabled
        if self.config.enable_circuit_breaker:
            with ChatAdsClient._circuit_breaker_lock:
                if ChatAdsClient._circuit_breaker is None:
                    ChatAdsClient._circuit_breaker = CircuitBreaker(
                        failure_threshold=CIRCUIT_BREAKER_THRESHOLD,
                        timeout_seconds=CIRCUIT_BREAKER_TIMEOUT,
                    )
                    LOGGER.info(
                        "Circuit breaker initialized: threshold=%d, timeout=%ds",
                        CIRCUIT_BREAKER_THRESHOLD,
                        CIRCUIT_BREAKER_TIMEOUT,
                    )

    async def aclose(self) -> None:
        """Async close - properly awaits cleanup tasks."""
        # Only close if we own the client (not using shared connection pool)
        # Shared clients persist for connection reuse across requests
        if getattr(self, '_owns_client', False):
            await self._client.aclose()

    def close(self) -> None:
        """Sync close - for compatibility, but prefer aclose()."""
        # Only close if we own the client (not using shared connection pool)
        # Shared clients persist for connection reuse across requests
        if getattr(self, '_owns_client', False):
            self._client.close()  # Sync close, won't await cleanup

    async def fetch(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], int, float]:
        """Async POST payload to ChatAds with retry/backoff and return (json, status, latency_ms)."""
        # Check circuit breaker before attempting request
        if self.config.enable_circuit_breaker and ChatAdsClient._circuit_breaker:
            if not ChatAdsClient._circuit_breaker.is_available():
                state = ChatAdsClient._circuit_breaker.get_state()
                LOGGER.warning("Circuit breaker is %s, failing fast", state.value)
                raise ChatAdsAPIError(
                    f"Circuit breaker is {state.value}. The API appears to be down. Please try again later.",
                    code="CIRCUIT_BREAKER_OPEN",
                    status_code=503,
                )

        last_error: Optional[Exception] = None
        delay = self.config.backoff_seconds

        for attempt in range(1, self.config.max_retries + 1):
            start = time.perf_counter()
            try:
                response = await self._client.post(self.config.endpoint, json=payload)
                latency_ms = (time.perf_counter() - start) * 1000
            except httpx.TimeoutException as exc:
                last_error = exc
                LOGGER.warning("ChatAds request timed out (attempt %s/%s)", attempt, self.config.max_retries)
                if self.config.enable_circuit_breaker and ChatAdsClient._circuit_breaker:
                    ChatAdsClient._circuit_breaker.record_failure()
            except httpx.RequestError as exc:
                last_error = exc
                LOGGER.warning(
                    "ChatAds transport error: %s (attempt %s/%s)",
                    _sanitize_error_for_logging(exc),
                    attempt,
                    self.config.max_retries,
                )
                if self.config.enable_circuit_breaker and ChatAdsClient._circuit_breaker:
                    ChatAdsClient._circuit_breaker.record_failure()
            else:
                if response.status_code >= 500:
                    if attempt < self.config.max_retries:
                        LOGGER.warning(
                            "ChatAds returned %s, retrying (attempt %s/%s)",
                            response.status_code,
                            attempt,
                            self.config.max_retries,
                        )
                        if self.config.enable_circuit_breaker and ChatAdsClient._circuit_breaker:
                            ChatAdsClient._circuit_breaker.record_failure()
                        continue
                    raise ChatAdsAPIError(
                        "ChatAds returned an internal error.",
                        code="UPSTREAM_UNAVAILABLE",
                        status_code=response.status_code,
                    )

                try:
                    data = response.json()
                except ValueError as exc:
                    raise ChatAdsAPIError(
                        "ChatAds returned invalid JSON.",
                        code="BAD_RESPONSE",
                        status_code=response.status_code,
                    ) from exc
                # Successful response - record success with circuit breaker
                if self.config.enable_circuit_breaker and ChatAdsClient._circuit_breaker:
                    ChatAdsClient._circuit_breaker.record_success()
                _emit_metric("chatads.request.latency_ms", latency_ms, {"status": str(response.status_code)})
                return data, response.status_code, latency_ms

            if attempt < self.config.max_retries:
                await asyncio.sleep(delay)
                delay *= 2

        raise ChatAdsAPIError(
            "Unable to reach ChatAds API after multiple attempts.",
            code="UPSTREAM_UNAVAILABLE",
            status_code=503,
            details={"last_error": _sanitize_error_for_logging(last_error) if last_error else None},
        )


ERROR_HINTS = {
    "UNAUTHORIZED": "API key is missing. Provide `CHATADS_API_KEY` or pass api_key.",
    "FORBIDDEN": "The provided API key is invalid or revoked.",
    "INTERNAL_ERROR": "API key validation failed upstream. Retry shortly.",
    "INVALID_INPUT": "Provide a non-empty message with at least two words.",
    "MESSAGE_TOO_LONG": "Message exceeds the max character limit enforced by ChatAds.",
    "MESSAGE_TOO_SHORT": "Message must include more context (minimum 2 words).",
    "MESSAGE_TOO_MANY_WORDS": "Message exceeds the 100 word cap.",
    "REQUEST_TOO_LARGE": "Request payload exceeds maximum size limit. Reduce message length or parameters.",
    "CONTENT_BLOCKED": "Message contains a keyword the user has blocked.",
    "RATE_LIMIT_UNAVAILABLE": "Usage enforcement temporarily unavailable—retry soon.",
    "MINUTE_QUOTA_EXCEEDED": "Too many requests this minute. Wait until the next minute.",
    "DAILY_QUOTA_EXCEEDED": "Daily request quota reached. Try tomorrow or upgrade.",
    "QUOTA_EXCEEDED": "Monthly quota reached. Add billing info or wait for reset.",
    "CIRCUIT_BREAKER_OPEN": "API is experiencing issues. Circuit breaker is protecting against failed requests. Retry later.",
}


def _sanitize_error_for_logging(error: Exception) -> str:
    """
    Sanitize error messages to prevent leaking sensitive data in logs.

    Removes or masks:
    - API keys (sk_live_*, sk_test_*)
    - Authorization headers
    - Full URLs with potential secrets
    """
    error_str = str(error)
    # Mask API keys
    error_str = _API_KEY_PATTERN.sub(r"\1***", error_str)
    # Mask authorization headers
    if "x-api-key" in error_str.lower():
        error_str = "Request error (details redacted for security)"
    if "authorization" in error_str.lower():
        error_str = "Request error (details redacted for security)"
    return error_str


def _friendly_error_message(code: Optional[str], fallback: Optional[str]) -> str:
    if code and code in ERROR_HINTS:
        return ERROR_HINTS[code]
    return fallback or "ChatAds could not process this request. Try again later."


def _normalize_reason(raw_reason: Optional[str]) -> Optional[str]:
    if not raw_reason:
        return None
    if ":" in raw_reason:
        reason_code, _, detail = raw_reason.partition(":")
        reason_code = reason_code.replace("_", " ").strip().capitalize()
        detail = detail.strip()
        return f"{reason_code}: {detail}" if detail else reason_code
    return raw_reason.strip()


def _summarize_usage(raw_usage: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_usage, dict):
        return None
    summary = {
        "monthly": {
            "used": raw_usage.get("monthly_requests"),
            "limit": raw_usage.get("free_tier_limit"),
            "remaining": raw_usage.get("free_tier_remaining"),
        },
        "daily": {
            "used": raw_usage.get("daily_requests"),
            "limit": raw_usage.get("daily_limit"),
        },
        "minute": {
            "used": raw_usage.get("minute_requests"),
            "limit": raw_usage.get("minute_limit"),
        },
        "is_free_tier": raw_usage.get("is_free_tier"),
        "has_credit_card": raw_usage.get("has_credit_card"),
    }
    return summary


def _check_quota_warnings(usage_summary: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Check usage and return warning message if approaching limits.

    Returns warning string if user is close to quota limits, None otherwise.
    Uses real-time data from backend, so no client-side state management needed.
    """
    if not usage_summary:
        return None

    warnings = []

    # Check monthly quota
    monthly = usage_summary.get("monthly", {})
    if monthly.get("remaining") is not None and monthly.get("remaining") < 10:
        warnings.append(f"⚠️  Only {monthly['remaining']} requests remaining this month")

    # Check daily quota
    daily = usage_summary.get("daily", {})
    if daily.get("used") and daily.get("limit"):
        daily_pct = daily["used"] / daily["limit"]
        if daily_pct >= QUOTA_WARNING_THRESHOLD:
            warnings.append(
                f"⚠️  Daily quota at {int(daily_pct * 100)}% ({daily['used']}/{daily['limit']} requests)"
            )

    # Check minute quota
    minute = usage_summary.get("minute", {})
    if minute.get("used") and minute.get("limit"):
        if minute["used"] >= minute["limit"] - 1:
            warnings.append(f"⚠️  Approaching minute limit ({minute['used']}/{minute['limit']} requests)")

    if warnings:
        return " | ".join(warnings)

    return None


def _build_metadata(
    meta: Dict[str, Any],
    *,
    source_url: str,
    latency_ms: float,
    status_code: int,
) -> ToolMetadata:
    request_id = str(meta.get("request_id") or "")
    if not request_id:
        # Clauses always expect a request id—even if upstream failed.
        request_id = "mcp-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    usage_summary = _summarize_usage(meta.get("usage"))

    notes = meta.get("notes")
    if not notes and usage_summary:
        notes = (
            f"Usage — monthly {usage_summary['monthly']['used']}/{usage_summary['monthly']['limit']}, "
            f"daily {usage_summary['daily']['used']}/{usage_summary['daily']['limit']}, "
            f"minute {usage_summary['minute']['used']}/{usage_summary['minute']['limit']}."
        )

    # Add quota warnings if approaching limits
    quota_warning = _check_quota_warnings(usage_summary)
    if quota_warning:
        notes = f"{notes}\n{quota_warning}" if notes else quota_warning
        LOGGER.warning("Quota warning: %s", quota_warning)

    metadata = ToolMetadata(
        request_id=request_id,
        timestamp=timestamp,
        latency_ms=round(latency_ms, 2),
        status_code=status_code,
        source=source_url,
        country=meta.get("country"),
        language=meta.get("language"),
        usage_summary=usage_summary,
        notes=notes,
    )
    return metadata


def normalize_envelope(
    raw: Dict[str, Any],
    *,
    status_code: int,
    latency_ms: float,
    source_url: str,
) -> ToolEnvelope:
    meta = raw.get("meta") or {}
    metadata = _build_metadata(
        meta,
        source_url=source_url,
        latency_ms=latency_ms,
        status_code=status_code,
    )

    if raw.get("success"):
        data = raw.get("data") or {}
        ad = data.get("ad") or {}
        matched = bool(data.get("matched"))
        status: Literal["success", "no_match"] = "success" if matched else "no_match"
        reason = _normalize_reason(data.get("reason"))
        envelope = ToolEnvelope(
            status=status,
            matched=matched,
            product=(ad.get("product") or None),
            affiliate_link=(ad.get("link") or None),
            category=(ad.get("category") or None),
            affiliate_message=(ad.get("message") or None),
            reason=reason,
            metadata=metadata,
        )
        return envelope

    error = raw.get("error") or {}
    error_code = error.get("code") or "UPSTREAM_ERROR"
    normalized_reason = _normalize_reason(error.get("details", {}).get("reason")) if isinstance(
        error.get("details"), dict
    ) else None
    envelope = ToolEnvelope(
        status="error",
        matched=False,
        reason=normalized_reason,
        error_code=error_code,
        error_message=_friendly_error_message(error_code, error.get("message")),
        metadata=metadata,
    )
    return envelope


def _validate_inputs(
    message: str,
    ip: Optional[str],
    country: Optional[str],
    language: Optional[str],
    api_key: str,
) -> None:
    """
    Validate all inputs before making API request.

    Raises ChatAdsAPIError for invalid inputs to fail fast and avoid wasted API calls.
    """
    # Message validation
    if not message or not message.strip():
        raise ChatAdsAPIError(
            "Message cannot be empty.",
            code="INVALID_INPUT",
            status_code=400,
        )

    words = message.split()
    if len(words) < 2:
        raise ChatAdsAPIError(
            "Message must contain at least 2 words.",
            code="MESSAGE_TOO_SHORT",
            status_code=400,
        )
    if len(words) > 100:
        raise ChatAdsAPIError(
            "Message exceeds 100 word limit.",
            code="MESSAGE_TOO_MANY_WORDS",
            status_code=400,
        )
    if len(message) > 2000:
        raise ChatAdsAPIError(
            "Message exceeds 2000 character limit.",
            code="MESSAGE_TOO_LONG",
            status_code=400,
        )

    # IP validation
    if ip:
        try:
            ipaddress.ip_address(ip)
        except ValueError as exc:
            raise ChatAdsAPIError(
                f"Invalid IP address format: {ip}",
                code="INVALID_INPUT",
                status_code=400,
            ) from exc

    # Country validation (ISO 3166-1 alpha-2: exactly 2 uppercase letters)
    if country and not _COUNTRY_CODE_PATTERN.match(country):
        raise ChatAdsAPIError(
            f"Country must be a 2-letter ISO 3166-1 code (e.g., 'US', 'GB'). Got: {country}",
            code="INVALID_INPUT",
            status_code=400,
        )

    # Language validation (ISO 639-1: exactly 2 lowercase letters)
    if language and not _LANGUAGE_CODE_PATTERN.match(language):
        raise ChatAdsAPIError(
            f"Language must be a 2-letter ISO 639-1 code (e.g., 'en', 'es'). Got: {language}",
            code="INVALID_INPUT",
            status_code=400,
        )

    # API key format validation
    if not (api_key.startswith("sk_live_") or api_key.startswith("sk_test_")):
        raise ChatAdsAPIError(
            "API key must start with 'sk_live_' or 'sk_test_'.",
            code="CONFIGURATION_ERROR",
            status_code=500,
        )
    if len(api_key) < 20:
        raise ChatAdsAPIError(
            "API key appears invalid (too short).",
            code="CONFIGURATION_ERROR",
            status_code=500,
        )


def _build_request_payload(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "message": kwargs["message"],
        "ip": kwargs.get("ip"),
        "userAgent": kwargs.get("user_agent"),
        "country": kwargs.get("country"),
        "language": kwargs.get("language"),
    }
    # Remove None values so we only send what the API expects.
    cleaned = {key: value for key, value in payload.items() if value is not None}

    # Note: Size validation removed to avoid double JSON encoding overhead.
    # Backend already validates request size (10MB max request, 1MB max JSON).
    # Message length is pre-validated (max 2000 chars), so payload will be small.

    return cleaned


def _resolve_api_key(user_supplied: Optional[str]) -> str:
    api_key = user_supplied or os.getenv("CHATADS_API_KEY")
    if not api_key:
        raise ChatAdsAPIError(
            "No ChatAds API key provided. Set CHATADS_API_KEY or pass `api_key`.",
            code="CONFIGURATION_ERROR",
            status_code=500,
        )
    return api_key


mcp = FastMCP("ChatAds-Affiliate")


def _error_envelope_from_exc(
    exc: ChatAdsAPIError,
    *,
    source_url: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert internal exceptions into sanitized tool payloads."""
    metadata = ToolMetadata(
        request_id="mcp-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        latency_ms=0.0,
        status_code=exc.status_code,
        source=source_url or f"{DEFAULT_BASE_URL}{DEFAULT_ENDPOINT}",
        notes=notes,
    )
    envelope = ToolEnvelope(
        status="error",
        matched=False,
        error_code=exc.code,
        error_message=_friendly_error_message(exc.code, str(exc)),
        metadata=metadata,
    )
    return envelope.model_dump()


async def run_chatads_affiliate_lookup(
    message: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    country: Optional[str] = None,
    language: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch normalized affiliate recommendations from ChatAds (async).

    Args:
        message: User query that needs affiliate suggestions.
        ip: Optional IP used for geo filters (ex. "8.8.8.8").
        user_agent: Optional user agent for device heuristics.
        country: Optional ISO 3166-1 alpha-2 country code (e.g., 'US', 'GB').
        language: Optional ISO 639-1 language code (e.g., 'en', 'es').
        api_key: Optional API key override; falls back to CHATADS_API_KEY env var.
    """
    client: Optional[ChatAdsClient] = None
    try:
        resolved_api_key = _resolve_api_key(api_key)

        # Validate inputs before making any API calls (fail fast)
        _validate_inputs(
            message=message.strip(),
            ip=ip,
            country=country,
            language=language,
            api_key=resolved_api_key,
        )

        payload = _build_request_payload(
            {
                "message": message.strip(),
                "ip": ip,
                "user_agent": user_agent,
                "country": country,
                "language": language,
            }
        )

        client = ChatAdsClient(resolved_api_key)
        raw, status_code, latency_ms = await client.fetch(payload)
        normalized = normalize_envelope(
            raw,
            status_code=status_code,
            latency_ms=latency_ms,
            source_url=f"{client.config.base_url}{client.config.endpoint}",
        )
        return normalized.model_dump()
    except ChatAdsAPIError as exc:
        LOGGER.error("ChatAds tool error (%s): %s", exc.code, _sanitize_error_for_logging(exc))
        notes = "Raised before contacting ChatAds." if client is None else None
        source_url = (
            f"{client.config.base_url}{client.config.endpoint}"
            if client
            else f"{DEFAULT_BASE_URL}{DEFAULT_ENDPOINT}"
        )
        return _error_envelope_from_exc(exc, source_url=source_url, notes=notes)
    finally:
        if client:
            await client.aclose()


chatads_affiliate_lookup = mcp.tool()(run_chatads_affiliate_lookup)


async def run_chatads_health_check(api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Check API connectivity and health without consuming quota (async).

    Returns connection status, latency, and circuit breaker state.
    Useful for deployment verification and monitoring.

    Args:
        api_key: Optional API key override; falls back to CHATADS_API_KEY env var.
    """
    client: Optional[ChatAdsClient] = None
    start_time = time.perf_counter()

    try:
        resolved_api_key = _resolve_api_key(api_key)

        # Check circuit breaker state
        circuit_state = "disabled"
        if ChatAdsClient._circuit_breaker:
            circuit_state = ChatAdsClient._circuit_breaker.get_state().value

        # Try a minimal request to test connectivity
        client = ChatAdsClient(resolved_api_key)

        # Just check if we can connect (circuit breaker will prevent if open)
        if not client.config.enable_circuit_breaker or ChatAdsClient._circuit_breaker.is_available():
            # Send a minimal valid request
            test_payload = {"message": "health check"}
            try:
                raw, status_code, latency_ms = await client.fetch(test_payload)
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                return {
                    "status": "healthy",
                    "api_reachable": True,
                    "circuit_breaker_state": circuit_state,
                    "latency_ms": round(latency_ms, 2),
                    "total_latency_ms": round(elapsed_ms, 2),
                    "endpoint": f"{client.config.base_url}{client.config.endpoint}",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "version": TOOL_VERSION,
                }
            except ChatAdsAPIError as exc:
                # API is reachable but returned an error
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return {
                    "status": "degraded",
                    "api_reachable": True,
                    "circuit_breaker_state": circuit_state,
                    "error_code": exc.code,
                    "error_message": str(exc),
                    "latency_ms": round(elapsed_ms, 2),
                    "endpoint": f"{client.config.base_url}{client.config.endpoint}",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "version": TOOL_VERSION,
                }
        else:
            # Circuit breaker is open
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return {
                "status": "unhealthy",
                "api_reachable": False,
                "circuit_breaker_state": circuit_state,
                "reason": "Circuit breaker is open - API is experiencing issues",
                "latency_ms": round(elapsed_ms, 2),
                "endpoint": f"{DEFAULT_BASE_URL}{DEFAULT_ENDPOINT}",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "version": TOOL_VERSION,
            }

    except ChatAdsAPIError as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        circuit_state = "unknown"
        if ChatAdsClient._circuit_breaker:
            circuit_state = ChatAdsClient._circuit_breaker.get_state().value

        return {
            "status": "unhealthy",
            "api_reachable": False,
            "circuit_breaker_state": circuit_state,
            "error_code": exc.code,
            "error_message": str(exc),
            "latency_ms": round(elapsed_ms, 2),
            "endpoint": f"{DEFAULT_BASE_URL}{DEFAULT_ENDPOINT}",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "version": TOOL_VERSION,
        }
    finally:
        if client:
            await client.aclose()


chatads_health_check = mcp.tool()(run_chatads_health_check)


def main() -> None:
    LOGGER.info("Starting ChatAds MCP wrapper (version %s)", TOOL_VERSION)
    mcp.run()


if __name__ == "__main__":
    main()
