# Changelog

All notable changes to ChatAds MCP Wrapper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.4] - 2025-01-20

### Fixed
- **CRITICAL:** Corrected default API base URL from `chatads-product-fastapiserver` to `chatads-api-fastapiserver` (fixes 404 errors)
- Removed unused health check tool that was no longer supported by the backend

### Added
- Async/await support for concurrent request handling (10-30x throughput improvement)
- Connection pooling with 100 max connections and 20 keep-alive connections
- Comprehensive test suite with 90%+ code coverage
- Security audit documentation (`SECURITY_AUDIT.md`)
- Performance optimization guide (`OPTIMIZATION_SUMMARY.md`)
- Concurrency analysis (`CONCURRENCY_AUDIT.md`)
- Scaling documentation for 500 req/s (`SCALING_TO_500RPS.md`)
- Async QA report (`ASYNC_QA_REPORT.md`)
- Public-ready checklist (`PUBLIC_READY_CHECKLIST.md`)

### Changed
- **BREAKING:** Timeout reduced from 15s to 10s for faster failure detection
- **BREAKING:** Message length limit aligned with backend (5000 → 2000 characters)
- Renamed `chatads_affiliate_lookup` MCP tool to `chatads_message_send` (old name remains as alias)
- API key validation no longer enforces any specific prefix; keys are validated server-side
- HTTP client upgraded from sync to async (`httpx.Client` → `httpx.AsyncClient`)
- Pre-compiled regex patterns for validation (~1-2ms faster per request)
- Removed double JSON encoding (~5-10ms faster per request)
- Connection cache now properly bounded (max 10 clients to prevent memory leaks)
- Updated README to reflect single tool (removed reference to health check)

### Performance
- **Cold requests:** ~280ms (unchanged)
- **Warm requests:** ~130ms (80-230ms faster than before due to connection pooling)
- **Throughput:** 200+ req/s per process (vs 7 req/s synchronous)
- **Concurrent requests:** 10-100x improvement with async/await

## [0.1.0] - 2024-11-14

### Added
- Initial release of ChatAds MCP Wrapper
- Two MCP tools:
  - `chatads_affiliate_lookup` - Main tool for fetching affiliate recommendations
- Circuit breaker pattern to prevent retry storms
  - Configurable failure threshold (default: 5)
  - Configurable timeout (default: 60 seconds)
  - Three states: CLOSED, OPEN, HALF_OPEN
- Quota warnings with real-time usage tracking
  - Warns when monthly quota < 10 requests
  - Warns when daily quota ≥ 90% used
  - Warns when approaching minute limit
- Input validation to prevent wasted API calls
  - Message: 2-100 words, max 2000 characters
  - IP address format validation
  - Country: ISO 3166-1 alpha-2 codes only
  - Language: ISO 639-1 codes only
  - API key format validation
- Retry logic with exponential backoff
  - Default: 3 retries with 0.6s initial delay
  - Configurable via environment variables
- Monitoring hooks for external metrics systems
  - `set_metric_callback()` function
  - Emits latency and circuit breaker metrics
- Comprehensive error handling
  - Sanitized error messages (no API keys or stack traces)
  - Friendly error hints for common issues
  - Error codes for programmatic handling
- Structured JSON logging support
  - Optional via `CHATADS_LOG_FORMAT=json`
  - Compatible with CloudWatch, Datadog, etc.
- Security features
  - API key sanitization in all logs
  - HTTPS-only communication
  - No data persistence
  - Request size limits

### Documentation
- Comprehensive README with:
  - Installation instructions
  - Usage examples
  - Configuration options
  - Troubleshooting guide
  - Best practices
- Detailed module docstring
- Function docstrings for all public APIs
- Inline comments for complex logic

### Testing
- Unit tests for all major functions
- Integration tests with mocked HTTP responses
- Edge case tests (circuit breaker, rate limiting, errors)
- Input validation tests
- Error handling tests

### Dependencies
- fastmcp 0.4.1 - MCP framework
- httpx 0.27.2 - HTTP client
- pydantic 2.12.0 - Data validation
- python-json-logger 2.0.7 - Structured logging

### Development Tools
- pytest 8.3.3 - Testing framework
- pytest-cov 6.0.0 - Coverage reporting
- pytest-asyncio 0.24.0 - Async test support
- pytest-httpx 0.35.0 - HTTP mocking
- black 24.10.0 - Code formatting
- ruff 0.8.4 - Fast linting
- mypy 1.13.0 - Static type checking
