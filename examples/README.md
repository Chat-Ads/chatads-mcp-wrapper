# ChatAds MCP Wrapper - Examples

This directory contains example code demonstrating how to use the ChatAds MCP Wrapper.

## Quick Start

1. **Set your API key:**
   ```bash
   export CHATADS_API_KEY=your_chatads_api_key
   ```

2. **Run the examples:**
   ```bash
   cd /path/to/chatads-backend/mcp
   python examples/basic_usage.py
   ```

## Examples Included

### `basic_usage.py`

Comprehensive examples covering all major use cases:

**Example 1: Basic Lookup**
- Simple affiliate recommendation query
- Understanding the response structure

**Example 2: Geographic Targeting**
- Using country and language parameters
- Region-specific recommendations

**Example 3: Error Handling**
- Common validation errors
- How to handle API errors gracefully

**Example 4: Concurrent Requests** 🚀
- Using async/await for performance
- Processing multiple queries simultaneously
- Performance benchmarking

**Example 5: User Context**
- Passing IP address and user agent
- Better targeting with user data

**Example 6: Quota Monitoring**
- Tracking API usage
- Avoiding quota limits

## Sample Output

```
╔====================================================================╗
║               ChatAds MCP Wrapper - Usage Examples                ║
╚====================================================================╝

======================================================================
Example 1: Basic Affiliate Lookup
======================================================================

Status: success
Matched: True

✅ Found affiliate match!
  Product: MacBook Pro M3
  Category: laptops
  Link: https://amazon.com/...
  Message: Perfect for developers and power users

📊 Metadata:
  Request ID: req_abc123
  Latency: 127.45ms
  Status Code: 200

💰 Usage:
  Monthly: 10/1000
  Daily: 5/100
  Minute: 1/5

======================================================================
Example 4: Concurrent Requests (Async Performance)
======================================================================

🚀 Running 8 queries concurrently...

📊 Performance Metrics:
  Total time: 245ms
  Queries: 8
  Average per query: 31ms
  Throughput: 32.7 req/s

📋 Results:
  1. ✅ best laptop for coding
     Status: success, Latency: 128ms
     Product: MacBook Pro M3
  2. ✅ best headphones for music
     Status: success, Latency: 134ms
     Product: Sony WH-1000XM5
  [...]
```

## Tips

### Concurrent Requests

The async/await pattern allows you to process multiple queries efficiently:

```python
# Sequential (slow)
result1 = await chatads_message_send("query 1")
result2 = await chatads_message_send("query 2")
# Total: ~260ms

# Concurrent (fast!)
results = await asyncio.gather(
    chatads_message_send("query 1"),
    chatads_message_send("query 2"),
)
# Total: ~130ms
```

### Error Handling

Always check the `status` field:

```python
result = await chatads_message_send(message="...")

if result['status'] == 'success':
    # Use the affiliate link
    link = result['affiliate_link']
elif result['status'] == 'no_match':
    # No affiliate found, use reason to explain
    reason = result['reason']
else:  # status == 'error'
    # Handle error
    error_code = result['error_code']
    error_msg = result['error_message']
```

### Quota Monitoring

Monitor usage to avoid hitting limits:

```python
usage = result['metadata']['usage_summary']

if usage['monthly']['remaining'] < 10:
    print("⚠️ Low on monthly quota!")

if usage['daily']['used'] / usage['daily']['limit'] > 0.9:
    print("⚠️ Approaching daily limit!")
```

## Next Steps

- Read the main [README](../README.md) for full documentation
- Check [CONTRIBUTING.md](../CONTRIBUTING.md) to contribute
- Review [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) for security best practices

## Questions?

Open an issue or contact support@chatads.com
