# ChatAds MCP Wrapper

Model Context Protocol (MCP) server that exposes ChatAds as a tool for AI assistants like Claude Desktop.

## Package Info

- **Package name**: `chatads-mcp-wrapper` (on PyPI)
- **Language**: Python 3.8+
- **Protocol**: MCP (Model Context Protocol)

## Purpose

Allows AI assistants that support MCP (like Claude Desktop) to:
- Automatically detect product mentions in conversations
- Insert affiliate links via ChatAds API
- Monetize conversations seamlessly

## Installation

```bash
pip install chatads-mcp-wrapper
```

## Usage

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "chatads": {
      "command": "python",
      "args": ["-m", "chatads_mcp_wrapper"],
      "env": {
        "CHATADS_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

See README.md for full setup instructions.

## Development

```bash
# Install in development mode
pip install -e .

# Run tests
python -m pytest

# Coverage report
python -m pytest --cov=chatads_mcp_wrapper --cov-report=html
```

## Project Structure

- `/chatads_mcp_wrapper` — MCP server implementation
- `/examples` — Usage examples
- `/tests` — Test suite
- `/htmlcov` — Coverage reports (generated)
- `pyproject.toml` — Package configuration
- `README.md` — User-facing documentation

## Related

- `/api` — Backend API this wrapper calls
- `/sdks/chatads-python-sdk` — Underlying Python SDK
- `/zen-mcp-server` — Another MCP server in this monorepo (unrelated to ChatAds)
