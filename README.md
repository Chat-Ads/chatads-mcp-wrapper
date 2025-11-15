# ChatAds MCP Wrapper

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

This directory houses the Model Context Protocol (MCP) wrapper that exposes the ChatAds Affiliate API to Claude (or any MCP-aware client). The wrapper normalizes responses, hides backend-specific errors, and provides consistent metadata so Claude always receives a predictable envelope.

## Requirements

- Python 3.10+
- `uv` **or** standard `pip`
- Environment variables:
  - `CHATADS_API_KEY` – your ChatAds API key (required)
  - Optional overrides:
    - `CHATADS_API_BASE_URL` (default: Modal deployment URL)
    - `CHATADS_API_ENDPOINT` (default: /v1/chatads/messages)
    - `CHATADS_MCP_TIMEOUT` (default: 15 seconds)
    - `CHATADS_MCP_MAX_RETRIES` (default: 3)
    - `CHATADS_MCP_BACKOFF` (default: 0.6 seconds)
    - `CHATADS_MAX_REQUEST_SIZE` (default: 10240 bytes / 10KB)
    - `CHATADS_CIRCUIT_BREAKER_THRESHOLD` (default: 5 failures before opening)
    - `CHATADS_CIRCUIT_BREAKER_TIMEOUT` (default: 60 seconds)
    - `CHATADS_QUOTA_WARNING_THRESHOLD` (default: 0.9 / 90%)
    - `LOGLEVEL` (default: INFO, options: DEBUG, INFO, WARNING, ERROR)
    - `CHATADS_LOG_FORMAT` (default: text, options: text, json)

## Installation

### From PyPI (recommended)

```bash
pip install chatads-mcp-wrapper
```

### From source (development)

```bash
git clone https://github.com/chatads/chatads-mcp-wrapper.git
cd chatads-mcp-wrapper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

Set your API key:

```bash
export CHATADS_API_KEY=sk_live_...
```

## Running the MCP Server

```bash
chatads-mcp
# or: python -m chatads_mcp_wrapper
```

The server provides two MCP tools:
- `chatads_affiliate_lookup` - Main tool for fetching affiliate recommendations
- `chatads_health_check` - Health check tool for API status verification

### Claude Desktop integration

Add a server entry to `claude_desktop_config.json` (path varies per OS):

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "chatads-affiliate": {
      "command": "chatads-mcp",
      "args": [],
      "env": {
        "CHATADS_API_KEY": "sk_live_your_key_here"
      }
    }
  }
}
```

Restart Claude Desktop and the tool will be available.

## Tool Signature

```text
chatads_affiliate_lookup(
    message: str,
    ip?: str,
    user_agent?: str,
    country?: str,
    language?: str,
    api_key?: str
) -> {
    status: "success" | "no_match" | "error",
    matched: bool,
    product?: str,
    affiliate_link?: str,
    category?: str,
    affiliate_message?: str,
    reason?: str,
    error_code?: str,
    error_message?: str,
    metadata: {
        request_id: str,
        timestamp: str,
        latency_ms: float,
        status_code: int,
        source: str,
        country?: str,
        language?: str,
        usage_summary?: {...},
        notes?: str
    }
}
```

## Features

### Circuit Breaker

Prevents retry storms when the API is experiencing issues. After N consecutive failures (default: 5), the circuit breaker "opens" and fails fast for a cooldown period (default: 60 seconds) instead of wasting resources.

**States:**
- `CLOSED`: Normal operation
- `OPEN`: Failing fast, not attempting requests
- `HALF_OPEN`: Testing if service recovered

**Configuration:**
```bash
export CHATADS_CIRCUIT_BREAKER_THRESHOLD=5
export CHATADS_CIRCUIT_BREAKER_TIMEOUT=60
```

### Health Check Tool

Use `chatads_health_check()` to verify API connectivity without consuming quota:

```python
result = chatads_health_check()
# Returns: status (healthy/degraded/unhealthy), latency, circuit breaker state
```

Useful for:
- Deployment verification
- Monitoring dashboards
- Pre-flight checks

### Quota Warnings

The wrapper automatically checks usage metadata and warns when approaching limits:
- Monthly quota < 10 requests remaining
- Daily quota ≥ 90% used (configurable via `CHATADS_QUOTA_WARNING_THRESHOLD`)
- Minute quota near limit

Warnings appear in `metadata.notes` and logs. No client-side state management needed - uses real-time data from backend.

### Monitoring Hooks

Integrate with your monitoring system:

```python
from chatads_mcp_wrapper import set_metric_callback
import datadog

# Configure callback for metrics
set_metric_callback(datadog.statsd.gauge)
```

Emitted metrics:
- `chatads.request.latency_ms` - Request latency
- `chatads.circuit_breaker.state_change` - Circuit breaker transitions

## Best Practices

- **Validate prompts**: ensure `message` is non-empty and under 100 words to avoid upstream validation errors.
- **Monitor quota warnings**: Check `metadata.notes` for quota warnings to avoid hitting limits.
- **Use health checks**: Verify API availability before critical operations.
- **Honor circuit breaker**: When circuit is open, wait for cooldown period before retrying.
- **Log metadata**: persist `metadata.request_id` and `metadata.usage_summary` for debugging and analytics.
- **Handle `no_match`**: treat `status="no_match"` as a graceful fallback—use `reason` to explain why no ad was returned.
- **Override cautiously**: only pass `country`/`language` when you have high-confidence signals; otherwise let ChatAds infer them.
- **Secure API keys**: prefer environment variables; only use the `api_key` argument for per-request overrides inside trusted contexts.

## Troubleshooting

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `CONFIGURATION_ERROR` | Missing `CHATADS_API_KEY` | Export the key or pass `api_key` argument. |
| `FORBIDDEN` / `UNAUTHORIZED` | Invalid or revoked key | Verify the key in Supabase / dashboard; rotate if needed. |
| `MINUTE_QUOTA_EXCEEDED` / `DAILY_QUOTA_EXCEEDED` / `QUOTA_EXCEEDED` | Hitting rate or hard caps | Respect `metadata.notes` and retry after the implied window or upgrade the plan. |
| `CIRCUIT_BREAKER_OPEN` | Too many consecutive failures | Circuit breaker is protecting against failed requests. Wait 60 seconds or check API health with `chatads_health_check()`. |
| `UPSTREAM_UNAVAILABLE` | Network outage or repeated 5xx | Wait/backoff; confirm Modal deployment health; consider raising `CHATADS_MCP_MAX_RETRIES`. |
| `INVALID_INPUT` | Empty message or <2 words | Provide more descriptive user text; sanitize before sending. |
| `REQUEST_TOO_LARGE` | Payload exceeds size limit | Reduce message length or increase `CHATADS_MAX_REQUEST_SIZE`. |

Enable debug logging if deeper insight is needed:

```bash
# Text logging (default)
LOGLEVEL=DEBUG chatads-mcp

# JSON structured logging (recommended for production)
CHATADS_LOG_FORMAT=json LOGLEVEL=INFO chatads-mcp
```

JSON logging outputs structured logs compatible with log aggregation systems (CloudWatch, Datadog, etc.).

Logs include upstream latency, retry attempts, and normalized error payloads without exposing internal stack traces or API keys to Claude.
