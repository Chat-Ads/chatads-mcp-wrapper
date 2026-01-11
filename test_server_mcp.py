#!/usr/bin/env python3
"""
Test the server-side MCP endpoint (Go API on Fly.io).

This tests the remote MCP server at https://api.getchatads.com/mcp/mcp
which requires NO local installation - just an API key.

Usage:
    export CHATADS_API_KEY=your_api_key
    python test_server_mcp.py

    # Or with .env file
    python test_server_mcp.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

# Load .env file if it exists
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

MCP_SERVER_URL = "https://api.getchatads.com/mcp/mcp"


async def test_mcp_server():
    """Test the server-side MCP endpoint."""
    api_key = os.environ.get("CHATADS_API_KEY")
    if not api_key:
        print("Set CHATADS_API_KEY env var or create .env file")
        return False

    print("=" * 60)
    print("ChatAds Server-Side MCP Test")
    print("=" * 60)
    print(f"\nEndpoint: {MCP_SERVER_URL}")
    print(f"API Key: {api_key[:15]}...")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Initialize session
        print("1. Initialize MCP session...")
        init_response = await client.post(
            MCP_SERVER_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            },
        )

        if init_response.status_code != 200:
            print(f"   FAIL: HTTP {init_response.status_code}")
            print(f"   Response: {init_response.text[:500]}")
            return False

        init_data = init_response.json()
        if "error" in init_data:
            print(f"   FAIL: {init_data['error']}")
            return False

        print(f"   OK: Server version {init_data.get('result', {}).get('serverInfo', {}).get('version', 'unknown')}")

        # Extract session ID from response header if present
        session_id = init_response.headers.get("mcp-session-id")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
        }
        if session_id:
            headers["mcp-session-id"] = session_id

        # Test 2: List tools
        print("\n2. List available tools...")
        tools_response = await client.post(
            MCP_SERVER_URL,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )

        if tools_response.status_code != 200:
            print(f"   FAIL: HTTP {tools_response.status_code}")
            return False

        tools_data = tools_response.json()
        tools = tools_data.get("result", {}).get("tools", [])
        print(f"   OK: Found {len(tools)} tool(s)")
        for tool in tools:
            print(f"       - {tool.get('name')}")

        # Test 3: Call chatads_message_send
        print("\n3. Call chatads_message_send...")
        call_response = await client.post(
            MCP_SERVER_URL,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "chatads_message_send",
                    "arguments": {
                        "message": "I need a good standing desk for my home office",
                    },
                },
            },
        )

        if call_response.status_code != 200:
            print(f"   FAIL: HTTP {call_response.status_code}")
            print(f"   Response: {call_response.text[:500]}")
            return False

        call_data = call_response.json()
        if "error" in call_data:
            print(f"   FAIL: {call_data['error']}")
            return False

        result = call_data.get("result", {})
        content = result.get("content", [])

        if content:
            # Parse the text content
            text_content = content[0].get("text", "{}")
            try:
                parsed = json.loads(text_content)
                offers = parsed.get("data", {}).get("Offers", [])
                print(f"   OK: Got {len(offers)} offer(s)")
                if offers:
                    offer = offers[0]
                    product = offer.get("Product", {})
                    print(f"       Product: {product.get('Title', 'N/A')[:60]}...")
                    print(f"       URL: {offer.get('URL', 'N/A')[:60]}...")
            except json.JSONDecodeError:
                print(f"   OK: Got response (non-JSON)")
                print(f"       {text_content[:100]}...")
        else:
            print("   OK: Empty response (no offers)")

        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
        return True


if __name__ == "__main__":
    success = asyncio.run(test_mcp_server())
    sys.exit(0 if success else 1)
