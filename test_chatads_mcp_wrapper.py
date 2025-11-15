"""
Unit tests for ChatAds MCP wrapper.

Run with: pytest test_chatads_mcp_wrapper.py -v
Coverage: pytest test_chatads_mcp_wrapper.py --cov=chatads_mcp_wrapper --cov-report=term-missing
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

import chatads_mcp_wrapper as chatads_module
from chatads_mcp_wrapper import (
    ChatAdsAPIError,
    ChatAdsClient,
    ChatAdsClientConfig,
    CircuitBreaker,
    CircuitState,
    ToolEnvelope,
    _API_KEY_REDACTION,
    _build_metadata,
    _build_request_payload,
    _check_quota_warnings,
    _friendly_error_message,
    _normalize_reason,
    _resolve_api_key,
    _sanitize_error_for_logging,
    _summarize_usage,
    _validate_inputs,
    normalize_envelope,
)


@pytest.fixture(autouse=True)
def reset_client_state():
    """Ensure HTTP client cache/circuit breaker do not leak between tests."""
    chatads_module._http_client_cache.clear()
    ChatAdsClient._circuit_breaker = None


class TestSanitization:
    """Test error message sanitization to prevent data leaks."""

    def test_sanitize_masks_provided_api_key(self):
        api_key = "my-secret-api-key"
        error = Exception(f"Failed with key {api_key}")
        result = _sanitize_error_for_logging(error, api_key=api_key)
        assert _API_KEY_REDACTION in result
        assert api_key not in result

    def test_sanitize_api_key_header(self):
        error = Exception("Request failed with x-api-key: some_key")
        result = _sanitize_error_for_logging(error)
        assert result == "Request error (details redacted for security)"

    def test_sanitize_authorization_header(self):
        error = Exception("Authorization header invalid")
        result = _sanitize_error_for_logging(error)
        assert result == "Request error (details redacted for security)"

    def test_sanitize_safe_error(self):
        error = Exception("Connection timeout")
        result = _sanitize_error_for_logging(error)
        assert result == "Connection timeout"


class TestInputValidation:
    """Test input validation for fast failure."""

    def test_valid_inputs(self):
        # Should not raise
        _validate_inputs(
            message="best laptop for coding",
            ip="8.8.8.8",
            country="US",
            language="en",
            api_key="mock_api_key_1234567890abcdefghij",
        )

    def test_valid_inputs_minimal(self):
        # Minimal valid inputs (only required params)
        _validate_inputs(
            message="test message",
            ip=None,
            country=None,
            language=None,
            api_key="mock_api_key_1234567890abcdefghij",
        )

    # Message validation tests
    def test_empty_message(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("", None, None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_message(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("   ", None, None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    def test_message_too_short_one_word(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("laptop", None, None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "MESSAGE_TOO_SHORT"
        assert "2 words" in str(exc_info.value)

    def test_message_exactly_two_words(self):
        # Should pass
        _validate_inputs("laptop recommendations", None, None, None, "mock_api_key_1234567890abcdefghij")

    def test_message_too_many_words(self):
        message = " ".join(["word"] * 101)
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs(message, None, None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "MESSAGE_TOO_MANY_WORDS"
        assert "100 word" in str(exc_info.value)

    def test_message_exactly_100_words(self):
        # Should pass
        message = " ".join(["word"] * 100)
        _validate_inputs(message, None, None, None, "mock_api_key_1234567890abcdefghij")

    def test_message_too_long_characters(self):
        message = ("a" * 1001) + " " + ("b" * 1000)
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs(message, None, None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "MESSAGE_TOO_LONG"
        assert "2000 character" in str(exc_info.value)

    def test_message_exactly_2000_characters(self):
        # Should pass with 2 words and exactly 2000 characters
        message = ("a" * 1000) + " " + ("b" * 999)
        assert len(message) == 2000
        _validate_inputs(message, None, None, None, "mock_api_key_1234567890abcdefghij")

    # IP validation tests
    def test_valid_ipv4(self):
        _validate_inputs("test message", "192.168.1.1", None, None, "mock_api_key_1234567890abcdefghij")

    def test_valid_ipv6(self):
        _validate_inputs("test message", "2001:0db8::1", None, None, "mock_api_key_1234567890abcdefghij")

    def test_invalid_ip_localhost(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", "localhost", None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"
        assert "Invalid IP" in str(exc_info.value)

    def test_invalid_ip_incomplete(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", "192.168.1", None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    def test_invalid_ip_text(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", "not.an.ip", None, None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    # Country validation tests
    def test_valid_country_us(self):
        _validate_inputs("test message", None, "US", None, "mock_api_key_1234567890abcdefghij")

    def test_valid_country_gb(self):
        _validate_inputs("test message", None, "GB", None, "mock_api_key_1234567890abcdefghij")

    def test_invalid_country_lowercase(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, "us", None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"
        assert "ISO 3166-1" in str(exc_info.value)

    def test_invalid_country_three_letters(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, "USA", None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    def test_invalid_country_full_name(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, "United States", None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    def test_invalid_country_one_letter(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, "U", None, "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    # Language validation tests
    def test_valid_language_en(self):
        _validate_inputs("test message", None, None, "en", "mock_api_key_1234567890abcdefghij")

    def test_valid_language_es(self):
        _validate_inputs("test message", None, None, "es", "mock_api_key_1234567890abcdefghij")

    def test_invalid_language_uppercase(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, None, "EN", "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"
        assert "ISO 639-1" in str(exc_info.value)

    def test_invalid_language_three_letters(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, None, "eng", "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    def test_invalid_language_full_name(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, None, "English", "mock_api_key_1234567890abcdefghij")
        assert exc_info.value.code == "INVALID_INPUT"

    # API key validation tests
    def test_valid_api_key_generic(self):
        _validate_inputs("test message", None, None, None, "my_api_key_value")

    def test_invalid_api_key_empty(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _validate_inputs("test message", None, None, None, "")
        assert exc_info.value.code == "CONFIGURATION_ERROR"


class TestReasonNormalization:
    """Test reason string normalization."""

    def test_normalize_reason_with_colon(self):
        result = _normalize_reason("no_match: insufficient data")
        assert result == "No match: insufficient data"

    def test_normalize_reason_simple(self):
        result = _normalize_reason("fallback_used")
        assert result == "fallback_used"

    def test_normalize_reason_empty(self):
        result = _normalize_reason("")
        assert result is None

    def test_normalize_reason_none(self):
        result = _normalize_reason(None)
        assert result is None

    def test_normalize_reason_multiple_colons(self):
        result = _normalize_reason("error: failed: retry")
        assert result == "Error: failed: retry"


class TestUsageSummarization:
    """Test usage data summarization."""

    def test_summarize_valid_usage(self):
        raw_usage = {
            "monthly_requests": 100,
            "free_tier_limit": 1000,
            "free_tier_remaining": 900,
            "daily_requests": 10,
            "daily_limit": 100,
            "minute_requests": 1,
            "minute_limit": 5,
            "is_free_tier": True,
            "has_credit_card": False,
        }
        result = _summarize_usage(raw_usage)
        assert result["monthly"]["used"] == 100
        assert result["monthly"]["limit"] == 1000
        assert result["monthly"]["remaining"] == 900
        assert result["is_free_tier"] is True

    def test_summarize_invalid_usage(self):
        result = _summarize_usage("not a dict")
        assert result is None

    def test_summarize_none_usage(self):
        result = _summarize_usage(None)
        assert result is None


class TestErrorHints:
    """Test friendly error messages."""

    def test_known_error_code(self):
        result = _friendly_error_message("UNAUTHORIZED", None)
        assert "API key is missing" in result

    def test_unknown_error_code_with_fallback(self):
        result = _friendly_error_message("UNKNOWN_CODE", "Custom error")
        assert result == "Custom error"

    def test_unknown_error_code_no_fallback(self):
        result = _friendly_error_message("UNKNOWN_CODE", None)
        assert "ChatAds could not process this request" in result


class TestAPIKeyResolution:
    """Test API key resolution logic."""

    def test_resolve_from_parameter(self):
        result = _resolve_api_key("mock_api_key_from_param")
        assert result == "mock_api_key_from_param"

    def test_resolve_from_environment(self, monkeypatch):
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_from_env")
        result = _resolve_api_key(None)
        assert result == "mock_api_key_from_env"

    def test_resolve_missing_raises(self, monkeypatch):
        monkeypatch.delenv("CHATADS_API_KEY", raising=False)
        with pytest.raises(ChatAdsAPIError) as exc_info:
            _resolve_api_key(None)
        assert exc_info.value.code == "CONFIGURATION_ERROR"


class TestMetadataBuilding:
    """Test metadata construction."""

    def test_build_metadata_complete(self):
        meta = {
            "request_id": "req_123",
            "country": "US",
            "language": "en",
            "usage": {
                "monthly_requests": 50,
                "free_tier_limit": 1000,
                "free_tier_remaining": 950,
                "daily_requests": 5,
                "daily_limit": 100,
                "minute_requests": 1,
                "minute_limit": 5,
            },
        }
        result = _build_metadata(
            meta,
            source_url="https://api.example.com",
            latency_ms=123.456,
            status_code=200,
        )
        assert result.request_id == "req_123"
        assert result.latency_ms == 123.46
        assert result.status_code == 200
        assert result.country == "US"

    def test_build_metadata_generates_request_id(self):
        meta = {}
        result = _build_metadata(
            meta,
            source_url="https://api.example.com",
            latency_ms=100.0,
            status_code=200,
        )
        assert result.request_id.startswith("mcp-")


class TestEnvelopeNormalization:
    """Test response envelope normalization."""

    def test_normalize_success_with_match(self):
        raw = {
            "success": True,
            "data": {
                "matched": True,
                "ad": {
                    "product": "MacBook Pro",
                    "link": "https://amazon.com/...",
                    "category": "laptops",
                    "message": "Great for coding!",
                },
                "reason": "exact_match: high confidence",
            },
            "meta": {"request_id": "req_1"},
        }
        result = normalize_envelope(raw, status_code=200, latency_ms=100.0, source_url="https://api.test")
        assert result.status == "success"
        assert result.matched is True
        assert result.product == "MacBook Pro"
        assert result.affiliate_link == "https://amazon.com/..."

    def test_normalize_no_match(self):
        raw = {
            "success": True,
            "data": {"matched": False, "reason": "no_match: insufficient context"},
            "meta": {"request_id": "req_2"},
        }
        result = normalize_envelope(raw, status_code=200, latency_ms=100.0, source_url="https://api.test")
        assert result.status == "no_match"
        assert result.matched is False
        assert "No match" in result.reason

    def test_normalize_error_response(self):
        raw = {
            "success": False,
            "error": {
                "code": "QUOTA_EXCEEDED",
                "message": "Monthly quota reached",
            },
            "meta": {"request_id": "req_3"},
        }
        result = normalize_envelope(raw, status_code=429, latency_ms=50.0, source_url="https://api.test")
        assert result.status == "error"
        assert result.matched is False
        assert result.error_code == "QUOTA_EXCEEDED"


class TestChatAdsClient:
    """Test HTTP client with retry logic."""

    def test_client_initialization_without_api_key(self):
        with pytest.raises(ChatAdsAPIError) as exc_info:
            ChatAdsClient("")
        assert exc_info.value.code == "CONFIGURATION_ERROR"

    def test_client_initialization_with_api_key(self):
        client = ChatAdsClient("mock_api_key_test")
        assert client._client.headers["x-api-key"] == "mock_api_key_test"
        assert hasattr(client, "aclose")

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_fetch_success(self, mock_client_class):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "data": {}}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = ChatAdsClientConfig(max_retries=3)
        client = ChatAdsClient("mock_api_key_123", config)
        data, status_code, latency_ms = await client.fetch({"message": "test"})

        assert data == {"success": True, "data": {}}
        assert status_code == 200
        assert latency_ms > 0
        await client.aclose()

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_fetch_retries_on_timeout(self, mock_client_class):
        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            httpx.TimeoutException("Timeout"),
            httpx.TimeoutException("Timeout"),
        ]
        mock_client_class.return_value = mock_client

        config = ChatAdsClientConfig(max_retries=2, backoff_seconds=0.0)
        client = ChatAdsClient("mock_api_key_123", config)

        with pytest.raises(ChatAdsAPIError) as exc_info:
            await client.fetch({"message": "test"})

        assert exc_info.value.code == "UPSTREAM_UNAVAILABLE"
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_fetch_retries_on_500_error(self, mock_client_class):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal server error"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [mock_response, mock_response, mock_response]
        mock_client_class.return_value = mock_client

        config = ChatAdsClientConfig(max_retries=2, backoff_seconds=0.0)
        client = ChatAdsClient("mock_api_key_123", config)

        with pytest.raises(ChatAdsAPIError) as exc_info:
            await client.fetch({"message": "test"})

        assert exc_info.value.code == "UPSTREAM_UNAVAILABLE"
        assert mock_client.post.call_count == 2


class TestChatAdsAPIError:
    """Test custom exception class."""

    def test_error_initialization(self):
        error = ChatAdsAPIError(
            "Test error",
            code="TEST_CODE",
            status_code=400,
            details={"key": "value"},
        )
        assert str(error) == "Test error"
        assert error.code == "TEST_CODE"
        assert error.status_code == 400
        assert error.details == {"key": "value"}

    def test_error_defaults(self):
        error = ChatAdsAPIError("Default error")
        assert error.code == "UPSTREAM_ERROR"
        assert error.status_code == 502
        assert error.details == {}


class TestRequestPayloadBuilding:
    """Test request payload construction (size validation removed for performance)."""

    def test_build_valid_payload(self):
        kwargs = {
            "message": "best laptop for coding",
            "ip": "8.8.8.8",
            "user_agent": "Mozilla/5.0",
            "country": "US",
            "language": "en",
        }
        result = _build_request_payload(kwargs)
        assert result["message"] == "best laptop for coding"
        assert result["ip"] == "8.8.8.8"
        assert result["userAgent"] == "Mozilla/5.0"

    def test_build_payload_removes_none_values(self):
        kwargs = {
            "message": "test",
            "ip": None,
            "user_agent": None,
            "country": None,
            "language": None,
        }
        result = _build_request_payload(kwargs)
        assert result == {"message": "test"}
        assert "ip" not in result

    def test_large_message_allowed(self):
        # Size validation removed - backend handles it
        # Message length validation happens separately (max 2000 chars)
        long_message = "word " * 400  # ~2000 chars (within limit)
        kwargs = {
            "message": long_message,
            "ip": None,
            "user_agent": None,
            "country": None,
            "language": None,
        }
        result = _build_request_payload(kwargs)
        assert result["message"] == long_message


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=10)
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.is_available() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=10)
        cb.record_failure()
        assert cb.get_state() == CircuitState.CLOSED
        cb.record_failure()
        assert cb.get_state() == CircuitState.CLOSED
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN
        assert cb.is_available() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.get_state() == CircuitState.CLOSED

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN
        assert cb.is_available() is False

        # Wait for timeout
        import time

        time.sleep(0.2)

        # Should transition to HALF_OPEN
        assert cb.is_available() is True
        assert cb.get_state() == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        import time

        time.sleep(0.2)
        cb.is_available()  # Transition to HALF_OPEN

        cb.record_success()
        assert cb.get_state() == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        import time

        time.sleep(0.2)
        cb.is_available()  # Transition to HALF_OPEN

        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN


class TestQuotaWarnings:
    """Test quota warning system."""

    def test_no_warning_when_usage_healthy(self):
        usage_summary = {
            "monthly": {"used": 100, "limit": 1000, "remaining": 900},
            "daily": {"used": 10, "limit": 100},
            "minute": {"used": 1, "limit": 5},
        }
        warning = _check_quota_warnings(usage_summary)
        assert warning is None

    def test_warning_when_monthly_low(self):
        usage_summary = {
            "monthly": {"used": 995, "limit": 1000, "remaining": 5},
            "daily": {"used": 10, "limit": 100},
            "minute": {"used": 1, "limit": 5},
        }
        warning = _check_quota_warnings(usage_summary)
        assert warning is not None
        assert "5 requests remaining" in warning

    def test_warning_when_daily_high(self):
        usage_summary = {
            "monthly": {"used": 100, "limit": 1000, "remaining": 900},
            "daily": {"used": 95, "limit": 100},
            "minute": {"used": 1, "limit": 5},
        }
        warning = _check_quota_warnings(usage_summary)
        assert warning is not None
        assert "95%" in warning or "Daily quota" in warning

    def test_warning_when_minute_limit_approaching(self):
        usage_summary = {
            "monthly": {"used": 100, "limit": 1000, "remaining": 900},
            "daily": {"used": 10, "limit": 100},
            "minute": {"used": 4, "limit": 5},
        }
        warning = _check_quota_warnings(usage_summary)
        assert warning is not None
        assert "minute" in warning.lower()

    def test_multiple_warnings_combined(self):
        usage_summary = {
            "monthly": {"used": 995, "limit": 1000, "remaining": 5},
            "daily": {"used": 95, "limit": 100},
            "minute": {"used": 4, "limit": 5},
        }
        warning = _check_quota_warnings(usage_summary)
        assert warning is not None
        # Should contain multiple warnings separated by |
        assert "|" in warning

    def test_no_warning_when_no_usage_data(self):
        warning = _check_quota_warnings(None)
        assert warning is None

    def test_no_warning_when_incomplete_data(self):
        usage_summary = {"monthly": {}}
        warning = _check_quota_warnings(usage_summary)
        assert warning is None


class TestIntegrationWithMockedHTTP:
    """Integration tests with mocked HTTP responses."""

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_successful_match_end_to_end(self, mock_client_class, monkeypatch):
        """Test complete flow with successful product match."""
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "matched": True,
                "ad": {
                    "product": "MacBook Pro M3",
                    "link": "https://amazon.com/macbook-pro",
                    "category": "laptops",
                    "message": "Perfect for developers!",
                },
                "reason": "exact_match: high confidence",
            },
            "meta": {
                "request_id": "req_abc123",
                "country": "US",
                "language": "en",
                "usage": {
                    "monthly_requests": 10,
                    "free_tier_limit": 1000,
                    "free_tier_remaining": 990,
                    "daily_requests": 5,
                    "daily_limit": 100,
                    "minute_requests": 1,
                    "minute_limit": 5,
                    "is_free_tier": True,
                    "has_credit_card": False,
                },
            },
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("best laptop for coding")

        assert result["status"] == "success"
        assert result["matched"] is True
        assert result["product"] == "MacBook Pro M3"
        assert result["affiliate_link"] == "https://amazon.com/macbook-pro"
        assert result["metadata"]["request_id"] == "req_abc123"

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_no_match_end_to_end(self, mock_client_class, monkeypatch):
        """Test complete flow with no match."""
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "matched": False,
                "reason": "no_match: insufficient context",
            },
            "meta": {"request_id": "req_xyz789"},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("random text here")

        assert result["status"] == "no_match"
        assert result["matched"] is False
        assert "No match" in result["reason"]

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_quota_exceeded_end_to_end(self, mock_client_class, monkeypatch):
        """Test complete flow with quota exceeded error."""
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {
            "success": False,
            "error": {
                "code": "QUOTA_EXCEEDED",
                "message": "Monthly quota reached",
            },
            "meta": {"request_id": "req_quota123"},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("best laptop")

        assert result["status"] == "error"
        assert result["error_code"] == "QUOTA_EXCEEDED"
        assert "Monthly quota" in result["error_message"]

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_network_timeout_with_retry(self, mock_client_class, monkeypatch):
        """Test retry logic on network timeout."""
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        mock_client = AsyncMock()
        # First two calls timeout, third succeeds
        mock_client.post.side_effect = [
            httpx.TimeoutException("Timeout"),
            httpx.TimeoutException("Timeout"),
            Mock(
                status_code=200,
                json=lambda: {
                    "success": True,
                    "data": {"matched": False},
                    "meta": {"request_id": "req_retry"},
                },
            ),
        ]
        mock_client_class.return_value = mock_client

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("test message")

        assert result["status"] == "no_match"
        assert mock_client.post.call_count == 3  # Retried twice, succeeded on third

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_invalid_api_key_end_to_end(self, mock_client_class, monkeypatch):
        """Test flow with invalid API key."""
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "success": False,
            "error": {
                "code": "FORBIDDEN",
                "message": "Invalid API key",
            },
            "meta": {"request_id": "req_forbidden"},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("test message")

        assert result["status"] == "error"
        assert result["error_code"] == "FORBIDDEN"

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_invalid_input_fails_before_api_call(self, mock_client_class, monkeypatch):
        """Test that validation errors don't make API calls."""
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("test message", country="USA")

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"
        # API should NOT have been called
        assert mock_client.post.call_count == 0

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch):
        """Test that missing API key fails gracefully."""
        monkeypatch.delenv("CHATADS_API_KEY", raising=False)

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("test message")

        assert result["status"] == "error"
        assert result["error_code"] == "CONFIGURATION_ERROR"
        assert "API key" in result["error_message"]

    @pytest.mark.asyncio
    @patch("chatads_mcp_wrapper.httpx.AsyncClient")
    async def test_server_error_with_retry(self, mock_client_class, monkeypatch):
        """Test retry logic on 500 server errors."""
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        mock_client = AsyncMock()
        # First call returns 500, second succeeds
        mock_client.post.side_effect = [
            Mock(status_code=500, json=lambda: {"error": "Internal Server Error"}),
            Mock(
                status_code=200,
                json=lambda: {
                    "success": True,
                    "data": {"matched": False},
                    "meta": {"request_id": "req_500"},
                },
            ),
        ]
        mock_client_class.return_value = mock_client

        from chatads_mcp_wrapper import run_chatads_message_send

        result = await run_chatads_message_send("test message")

        assert result["status"] == "no_match"
        assert mock_client.post.call_count == 2  # Retried once


class TestHealthCheck:
    """Validate run_chatads_health_check helper."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, monkeypatch):
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        class DummyClient:
            _circuit_breaker = None

            def __init__(self, api_key):
                self.config = SimpleNamespace(
                    base_url="https://example.com",
                    endpoint="/v1/test",
                    enable_circuit_breaker=False,
                )

            async def fetch(self, payload):
                return {"success": True}, 200, 42.0

            async def aclose(self):
                return None

        monkeypatch.setattr(chatads_module, "ChatAdsClient", DummyClient)

        result = await chatads_module.run_chatads_health_check()
        assert result["status"] == "healthy"
        assert result["api_reachable"] is True
        assert result["circuit_breaker_state"] == "disabled"

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, monkeypatch):
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        class DummyClient:
            _circuit_breaker = None

            def __init__(self, api_key):
                self.config = SimpleNamespace(
                    base_url="https://example.com",
                    endpoint="/v1/test",
                    enable_circuit_breaker=False,
                )

            async def fetch(self, payload):
                raise ChatAdsAPIError("invalid-input", code="INVALID_INPUT", status_code=400)

            async def aclose(self):
                return None

        monkeypatch.setattr(chatads_module, "ChatAdsClient", DummyClient)

        result = await chatads_module.run_chatads_health_check()
        assert result["status"] == "degraded"
        assert result["api_reachable"] is True
        assert result["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_health_check_circuit_breaker_open(self, monkeypatch):
        monkeypatch.setenv("CHATADS_API_KEY", "mock_api_key_test1234567890abcdef")

        class DummyBreaker:
            def __init__(self, state: str):
                self._state = state

            def is_available(self) -> bool:
                return False

            def get_state(self):
                return SimpleNamespace(value=self._state)

        class DummyClient:
            _circuit_breaker = DummyBreaker("open")

            def __init__(self, api_key):
                self.config = SimpleNamespace(
                    base_url="https://example.com",
                    endpoint="/v1/test",
                    enable_circuit_breaker=True,
                )

            async def fetch(self, payload):
                raise AssertionError("should not be called when circuit breaker open")

            async def aclose(self):
                return None

        monkeypatch.setattr(chatads_module, "ChatAdsClient", DummyClient)

        result = await chatads_module.run_chatads_health_check()
        assert result["status"] == "unhealthy"
        assert result["api_reachable"] is False
        assert result["circuit_breaker_state"] == "open"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=chatads_mcp_wrapper", "--cov-report=term-missing"])
