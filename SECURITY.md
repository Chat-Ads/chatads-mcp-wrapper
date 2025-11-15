# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in ChatAds MCP Wrapper, please report it responsibly:

### How to Report

1. **Email us:** security@chatads.com
2. **Subject line:** "Security Vulnerability in ChatAds MCP Wrapper"
3. **Include:**
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact and severity
   - Suggested fix (if any)
   - Your contact information

### What to Expect

- **Acknowledgment:** We will acknowledge receipt within 48 hours
- **Updates:** We will provide updates every 5-7 days on progress
- **Timeline:** We aim to fix critical vulnerabilities within 7 days
- **Credit:** We will credit you in the security advisory (if desired)

### Disclosure Policy

- We will work with you to understand and validate the issue
- We will develop and test a fix
- We will coordinate the release of the fix with you
- We will publish a security advisory after the fix is released

## Security Best Practices

When using ChatAds MCP Wrapper:

### 1. API Key Management

**DO:**
- ✅ Store API keys in environment variables
- ✅ Use different keys for development and production
- ✅ Rotate keys regularly (every 90 days)
- ✅ Revoke compromised keys immediately
- ✅ Use `sk_test_*` keys for development
- ✅ Use `sk_live_*` keys only in production

**DON'T:**
- ❌ Commit API keys to version control
- ❌ Share API keys in public channels
- ❌ Use production keys in development
- ❌ Store keys in code or configuration files
- ❌ Log API keys (wrapper sanitizes them automatically)

### 2. Network Security

**Enforced by Default:**
- ✅ HTTPS-only communication (no HTTP fallback)
- ✅ TLS certificate validation enabled
- ✅ No insecure SSL options

**Additional Recommendations:**
- Use a firewall to restrict outbound connections
- Monitor network traffic for unusual patterns
- Keep httpx library updated (security patches)

### 3. Input Validation

**Handled by Wrapper:**
- ✅ Message length limits (2-100 words, max 2000 chars)
- ✅ IP address format validation
- ✅ Country/language code validation (ISO standards)
- ✅ API key format validation
- ✅ Request size limits (max 10KB)

**Additional Recommendations:**
- Sanitize user input before passing to wrapper
- Validate data from untrusted sources
- Use parameterized queries (avoid string concatenation)

### 4. Rate Limiting

**Built-in Protection:**
- ✅ Circuit breaker prevents retry storms
- ✅ Exponential backoff on retries
- ✅ Configurable retry limits
- ✅ Backend enforces quota limits

**Recommendations:**
- Monitor `metadata.usage_summary` for quota warnings
- Implement client-side rate limiting if needed
- Respect circuit breaker state (don't force retries)

### 5. Error Handling

**Security Features:**
- ✅ API keys sanitized from all error messages
- ✅ No stack traces exposed to end users
- ✅ Generic error messages prevent information disclosure
- ✅ Detailed errors only in server logs

**Recommendations:**
- Log errors securely (separate from user-facing logs)
- Monitor error rates for unusual patterns
- Don't expose detailed errors to untrusted clients

### 6. Dependencies

**Keep Updated:**
```bash
# Check for outdated packages
pip list --outdated

# Update dependencies
pip install -U fastmcp httpx pydantic python-json-logger

# Security audit
pip install safety
safety check
```

**Pinned Versions:**
- We pin dependencies in `requirements.txt` for reproducibility
- Update regularly but test thoroughly
- Review changelogs for security fixes

### 7. Logging

**What We Log:**
- ✅ Request metadata (timestamps, latency, status codes)
- ✅ Error messages (sanitized)
- ✅ Circuit breaker state changes
- ✅ Cache operations

**What We DON'T Log:**
- ❌ API keys (automatically sanitized)
- ❌ User messages (privacy)
- ❌ IP addresses (PII)
- ❌ Personal data

**Recommendations:**
- Use structured JSON logging in production
- Encrypt logs at rest
- Rotate logs regularly
- Restrict log access to authorized personnel

### 8. Privacy Considerations

**Data Sent to Backend:**
- User message content (required for analysis)
- IP address (optional - **PII under GDPR**)
- User agent (optional - device fingerprinting)
- Country/language (optional - location data)

**Privacy Best Practices:**
- ✅ Only send necessary data
- ✅ Obtain user consent for PII (GDPR requirement)
- ✅ Document data collection in privacy policy
- ✅ Provide opt-out mechanisms
- ✅ All data encrypted in transit (HTTPS)
- ✅ No client-side data persistence

**GDPR Compliance:**
- Inform users about data collection
- Obtain explicit consent for EU users
- Provide data access/deletion mechanisms
- Document data retention policies

## Known Security Considerations

### Not Vulnerabilities (By Design)

1. **API keys in environment variables**
   - Standard practice for API clients
   - More secure than hardcoding
   - Use secrets management in production

2. **Threading.Lock in async code**
   - Works correctly with Python's GIL
   - No race conditions detected
   - May upgrade to asyncio.Lock in future

3. **Connection pool shared across requests**
   - Intentional for performance
   - Thread-safe (httpx.AsyncClient guarantees)
   - Bounded to prevent memory leaks

### Potential Attack Vectors

1. **Denial of Service (DoS)**
   - **Mitigated:** Circuit breaker prevents retry storms
   - **Mitigated:** Backend rate limiting enforced
   - **Mitigated:** Request size limits
   - **Recommendation:** Add client-side throttling if needed

2. **Man-in-the-Middle (MITM)**
   - **Mitigated:** HTTPS-only communication
   - **Mitigated:** Certificate validation enabled
   - **Recommendation:** Use certificate pinning for critical apps

3. **Injection Attacks**
   - **Mitigated:** Input validation prevents SQL/command injection
   - **Mitigated:** Parameterized requests (JSON, not string concat)
   - **Recommendation:** Sanitize user input before passing to wrapper

4. **API Key Theft**
   - **Mitigated:** Keys sanitized from logs/errors
   - **Mitigated:** HTTPS prevents eavesdropping
   - **Mitigated:** No key persistence to disk
   - **Recommendation:** Rotate keys regularly, monitor usage

## Security Audit Reports

We have conducted comprehensive security audits:

- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) - Full security analysis
- [CONCURRENCY_AUDIT.md](CONCURRENCY_AUDIT.md) - Thread safety analysis
- [ASYNC_QA_REPORT.md](ASYNC_QA_REPORT.md) - Async implementation review

## Compliance

### Standards
- OWASP Top 10 (2021) - No critical vulnerabilities
- CWE/SANS Top 25 - Mitigations in place
- GDPR - Privacy considerations documented

### Certifications
- None currently (open-source project)
- Enterprise support available on request

## Contact

- **Security Issues:** security@chatads.com
- **General Support:** support@chatads.com
- **Documentation:** https://github.com/chatads/chatads-mcp-wrapper

## Acknowledgments

We appreciate responsible disclosure from security researchers. Contributors will be credited in security advisories (with permission).

---

**Last Updated:** 2024-11-14
**Version:** 0.1.0
