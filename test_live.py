#!/usr/bin/env python3
"""
Quick live test of ChatAds MCP Wrapper.

This script directly calls the async functions to verify they work.
Unlike running the MCP server, this gives you immediate feedback.

Usage:
    export CHATADS_API_KEY=your_chatads_api_key
    python3 test_live.py
"""

import asyncio
import os
import sys

from chatads_mcp_wrapper import run_chatads_message_send

async def test_basic_lookup():
    """Test 2: Basic affiliate lookup."""
    print("🔍 Test 2: Basic Affiliate Lookup")
    print("-" * 50)

    result = await run_chatads_message_send(
        message="best laptop for coding"
    )

    print(f"Status: {result['status']}")
    print(f"Matched: {result['matched']}")

    if result['status'] == 'error':
        print(f"❌ Error: {result['error_code']}")
        print(f"   Message: {result['error_message']}")
        return False

    if result['matched']:
        print(f"✅ Product: {result['product']}")
        print(f"   Category: {result['category']}")
        print(f"   Link: {result['affiliate_link'][:60]}...")
    else:
        print(f"ℹ️ No match: {result.get('reason', 'N/A')}")

    print(f"\n📊 Metadata:")
    print(f"   Request ID: {result['metadata']['request_id']}")
    print(f"   Latency: {result['metadata']['latency_ms']:.2f}ms")

    if result['metadata'].get('usage_summary'):
        usage = result['metadata']['usage_summary']
        print(f"\n💰 Usage:")
        print(f"   Monthly: {usage['monthly']['used']}/{usage['monthly']['limit']}")
        print(f"   Daily: {usage['daily']['used']}/{usage['daily']['limit']}")

    print()
    return True


async def test_concurrent():
    """Test 3: Concurrent requests (show async power!)."""
    print("⚡ Test 3: Concurrent Requests")
    print("-" * 50)

    queries = [
        "best laptop",
        "best headphones",
        "best monitor",
    ]

    import time
    start = time.perf_counter()

    results = await asyncio.gather(*[
        run_chatads_message_send(message=q)
        for q in queries
    ])

    elapsed = (time.perf_counter() - start) * 1000

    print(f"Processed {len(results)} queries in {elapsed:.0f}ms")
    print(f"Average: {elapsed / len(results):.0f}ms per query")
    print(f"Throughput: {len(results) / (elapsed / 1000):.1f} req/s\n")

    for i, (query, result) in enumerate(zip(queries, results), 1):
        status = "✅" if result['matched'] else "❌"
        print(f"{i}. {status} {query} - {result['status']}")

    print()
    return True


async def test_error_handling():
    """Test 4: Error handling."""
    print("🛡️ Test 4: Error Handling")
    print("-" * 50)

    # Test with invalid input (too short)
    result = await run_chatads_message_send(message="x")

    if result['status'] == 'error':
        print(f"✅ Correctly caught validation error:")
        print(f"   Code: {result['error_code']}")
        print(f"   Message: {result['error_message']}")
    else:
        print(f"⚠️ Expected error but got: {result['status']}")

    print()
    return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("ChatAds MCP Wrapper - Live Test")
    print("=" * 50)
    print()

    # Check API key
    if not os.getenv("CHATADS_API_KEY"):
        print("❌ ERROR: CHATADS_API_KEY not set")
        print("\nSet your API key:")
        print("  export CHATADS_API_KEY=your_chatads_api_key")
        print()
        sys.exit(1)

    api_key = os.getenv("CHATADS_API_KEY")
    print(f"Using API Key: {api_key[:15]}...")
    print()

    try:
        # Run tests
        success = True
        success = await test_basic_lookup() and success
        success = await test_concurrent() and success
        success = await test_error_handling() and success

        # Summary
        print("=" * 50)
        if success:
            print("✅ All tests passed!")
        else:
            print("⚠️ Some tests failed (see above)")
        print("=" * 50)
        print()

        # Next steps
        print("📝 Next Steps:")
        print("  • Run full test suite: pytest test_chatads_mcp_wrapper.py -v")
        print("  • Try examples: python3 examples/basic_usage.py")
        print("  • Configure in Claude Desktop (see README.md)")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
