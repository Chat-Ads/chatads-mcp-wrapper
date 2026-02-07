"""
Basic usage examples for ChatAds MCP Wrapper.

This file demonstrates how to use the ChatAds MCP wrapper for various
common scenarios. The wrapper provides async/await support for efficient
concurrent request handling.

Setup:
    export CHATADS_API_KEY=your_chatads_api_key
    python examples/basic_usage.py

Requirements:
    - Python 3.10+
    - ChatAds API key (get from https://getchatads.com)
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import the wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))

from chatads_mcp_wrapper import chatads_message_send


async def example_1_basic_lookup():
    """Example 1: Basic affiliate lookup with minimal parameters."""
    print("=" * 70)
    print("Example 1: Basic Affiliate Lookup")
    print("=" * 70)

    result = await chatads_message_send(
        message="best laptop for coding"
    )

    print(f"\nStatus: {result['status']}")
    print(f"Matched: {result['matched']}")

    if result['matched']:
        print(f"\n✅ Found affiliate match!")
        print(f"  Product: {result['product']}")
        print(f"  Link: {result['affiliate_link']}")
        print(f"  Message: {result.get('affiliate_message', 'N/A')}")
    else:
        print(f"\n❌ No match found")
        print(f"  Reason: {result.get('reason', 'N/A')}")

    print(f"\n📊 Metadata:")
    print(f"  Request ID: {result['metadata']['request_id']}")
    print(f"  Latency: {result['metadata']['latency_ms']:.2f}ms")
    print(f"  Status Code: {result['metadata']['status_code']}")

    if result['metadata'].get('usage_summary'):
        usage = result['metadata']['usage_summary']
        print(f"\n💰 Usage:")
        print(f"  Monthly: {usage['monthly']['used']}/{usage['monthly']['limit']}")
        print(f"  Daily: {usage['daily']['used']}/{usage['daily']['limit']}")

    print()


async def example_2_with_geo_targeting():
    """Example 2: Lookup with geographic targeting parameters."""
    print("=" * 70)
    print("Example 2: Geographic Targeting")
    print("=" * 70)

    result = await chatads_message_send(
        message="best headphones for music",
        country="US",  # ISO 3166-1 alpha-2 country code
        language="en"  # ISO 639-1 language code
    )

    print(f"\nQuery: 'best headphones for music' (US, English)")
    print(f"Status: {result['status']}")
    print(f"Matched: {result['matched']}")

    if result['matched']:
        print(f"Product: {result['product']}")

    print(f"\n🌍 Geo Info:")
    print(f"  Country: {result['metadata'].get('country', 'N/A')}")
    print(f"  Language: {result['metadata'].get('language', 'N/A')}")
    print()

async def example_4_error_handling():
    """Example 4: Handling validation errors and API errors."""
    print("=" * 70)
    print("Example 4: Error Handling")
    print("=" * 70)

    # Test 1: Invalid input (too short)
    print("\nTest 1: Message too short (< 2 words)")
    result = await chatads_message_send(message="laptop")

    if result['status'] == 'error':
        print(f"  ❌ Error Code: {result['error_code']}")
        print(f"  Message: {result['error_message']}")

    # Test 2: Invalid country code
    print("\nTest 2: Invalid country code")
    result = await chatads_message_send(
        message="best laptop for coding",
        country="USA"  # Should be "US" (2-letter code)
    )

    if result['status'] == 'error':
        print(f"  ❌ Error Code: {result['error_code']}")
        print(f"  Message: {result['error_message']}")

    # Test 3: Message too long
    print("\nTest 3: Message too many words (> 100)")
    long_message = " ".join(["word"] * 101)
    result = await chatads_message_send(message=long_message)

    if result['status'] == 'error':
        print(f"  ❌ Error Code: {result['error_code']}")
        print(f"  Message: {result['error_message']}")

    print()


async def example_5_concurrent_requests():
    """Example 5: Concurrent requests using async/await (the power of async!)."""
    print("=" * 70)
    print("Example 5: Concurrent Requests (Async Performance)")
    print("=" * 70)

    queries = [
        "best laptop for coding",
        "best headphones for music",
        "best monitor for design",
        "best keyboard for gaming",
        "best mouse for productivity",
        "best webcam for meetings",
        "best microphone for podcasting",
        "best speaker for home office",
    ]

    print(f"\n🚀 Running {len(queries)} queries concurrently...\n")

    import time
    start = time.perf_counter()

    # Run all queries concurrently (this is where async shines!)
    results = await asyncio.gather(*[
        chatads_message_send(message=query)
        for query in queries
    ])

    elapsed = (time.perf_counter() - start) * 1000

    print(f"📊 Performance Metrics:")
    print(f"  Total time: {elapsed:.0f}ms")
    print(f"  Queries: {len(results)}")
    print(f"  Average per query: {elapsed / len(results):.0f}ms")
    print(f"  Throughput: {len(results) / (elapsed / 1000):.1f} req/s")

    print(f"\n📋 Results:")
    for i, (query, result) in enumerate(zip(queries, results), 1):
        status_emoji = "✅" if result['matched'] else "❌"
        print(f"  {i}. {status_emoji} {query}")
        print(f"     Status: {result['status']}, Latency: {result['metadata']['latency_ms']:.0f}ms")
        if result['matched']:
            print(f"     Product: {result['product']}")

    print()


async def example_6_with_user_context():
    """Example 6: Using IP and user agent for better targeting."""
    print("=" * 70)
    print("Example 6: User Context Parameters")
    print("=" * 70)

    result = await chatads_message_send(
        message="best running shoes",
        ip="8.8.8.8",  # User's IP (for geo-targeting)
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        country="US",
        language="en"
    )

    print(f"\nQuery: 'best running shoes'")
    print(f"Context: IP=8.8.8.8, Device=iPhone, Country=US")
    print(f"\nStatus: {result['status']}")
    print(f"Matched: {result['matched']}")

    if result['matched']:
        print(f"Product: {result['product']}")

    print()


async def example_7_quota_monitoring():
    """Example 7: Monitoring API quota usage."""
    print("=" * 70)
    print("Example 7: Quota Monitoring")
    print("=" * 70)

    result = await chatads_message_send(
        message="best laptop for students"
    )

    if result['metadata'].get('usage_summary'):
        usage = result['metadata']['usage_summary']

        print(f"\n📊 Current Usage:")

        # Monthly quota
        monthly = usage['monthly']
        monthly_pct = (monthly['used'] / monthly['limit']) * 100 if monthly['limit'] else 0
        print(f"\n  Monthly:")
        print(f"    Used: {monthly['used']}/{monthly['limit']} ({monthly_pct:.1f}%)")
        print(f"    Remaining: {monthly.get('remaining', 'N/A')}")

        # Daily quota
        daily = usage['daily']
        daily_pct = (daily['used'] / daily['limit']) * 100 if daily['limit'] else 0
        print(f"\n  Daily:")
        print(f"    Used: {daily['used']}/{daily['limit']} ({daily_pct:.1f}%)")

        # Account info
        print(f"\n  Account:")
        print(f"    Free Tier: {usage['is_free_tier']}")
        print(f"    Has Credit Card: {usage['has_credit_card']}")

        # Check for warnings
        if result['metadata'].get('notes'):
            print(f"\n  ⚠️ Warnings:")
            for line in result['metadata']['notes'].split('\n'):
                if '⚠️' in line:
                    print(f"    {line.strip()}")
    else:
        print("\n❌ No usage data available in response")

    print()


async def main():
    """Run all examples."""
    # Check API key
    if not os.getenv("CHATADS_API_KEY"):
        print("\n" + "=" * 70)
        print("❌ ERROR: CHATADS_API_KEY environment variable not set")
        print("=" * 70)
        print("\nPlease set your API key:")
        print("  export CHATADS_API_KEY=your_chatads_api_key")
        print("\nGet your API key from: https://getchatads.com")
        print()
        return

    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "ChatAds MCP Wrapper - Usage Examples" + " " * 16 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    try:
        await example_1_basic_lookup()
        await example_2_with_geo_targeting()
        await example_4_error_handling()
        await example_5_concurrent_requests()
        await example_6_with_user_context()
        await example_7_quota_monitoring()

        print("=" * 70)
        print("✅ All examples completed successfully!")
        print("=" * 70)
        print()

    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
