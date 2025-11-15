# Contributing to ChatAds MCP Wrapper

Thank you for your interest in contributing to ChatAds MCP Wrapper! We welcome contributions from the community.

## Getting Started

### Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/chatads/chatads-mcp-wrapper.git
   cd chatads-mcp-wrapper/mcp
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

4. **Set up your API key:**
   ```bash
   export CHATADS_API_KEY=sk_test_your_test_key_here
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest test_chatads_mcp_wrapper.py -v

# Run with coverage
pytest test_chatads_mcp_wrapper.py --cov=chatads_mcp_wrapper --cov-report=term-missing

# Run specific test class
pytest test_chatads_mcp_wrapper.py::TestInputValidation -v

# Run specific test
pytest test_chatads_mcp_wrapper.py::TestInputValidation::test_valid_inputs -v
```

### Code Quality Checks

Before submitting a pull request, ensure all quality checks pass:

```bash
# Format code with black
black chatads_mcp_wrapper.py test_chatads_mcp_wrapper.py

# Lint with ruff
ruff check chatads_mcp_wrapper.py test_chatads_mcp_wrapper.py

# Type check with mypy
mypy chatads_mcp_wrapper.py
```

### Running the MCP Server Locally

```bash
# Start the server
python chatads_mcp_wrapper.py

# With debug logging
LOGLEVEL=DEBUG python chatads_mcp_wrapper.py

# With JSON logging
CHATADS_LOG_FORMAT=json python chatads_mcp_wrapper.py
```

## Pull Request Process

1. **Fork the repository** and create your branch from `main`:
   ```bash
   git checkout -b feature/amazing-feature
   ```

2. **Make your changes:**
   - Write clear, descriptive commit messages
   - Add tests for new functionality
   - Update documentation as needed
   - Follow the code style guidelines below

3. **Ensure all checks pass:**
   ```bash
   # Run tests
   pytest test_chatads_mcp_wrapper.py -v --cov

   # Format code
   black chatads_mcp_wrapper.py test_chatads_mcp_wrapper.py

   # Lint
   ruff check chatads_mcp_wrapper.py

   # Type check
   mypy chatads_mcp_wrapper.py
   ```

4. **Update CHANGELOG.md:**
   - Add your changes under the `[Unreleased]` section
   - Follow the existing format (Added/Changed/Fixed/etc.)

5. **Push to your fork:**
   ```bash
   git push origin feature/amazing-feature
   ```

6. **Open a Pull Request:**
   - Provide a clear title and description
   - Reference any related issues
   - Explain the motivation and context
   - Include screenshots/examples if relevant

## Code Style Guidelines

### Python Style
- Follow [PEP 8](https://pep8.org/) style guide
- Use [Black](https://black.readthedocs.io/) for formatting (line length: 120)
- Use [Ruff](https://github.com/astral-sh/ruff) for linting

### Type Hints
- Add type hints to all function signatures
- Use `Optional[T]` for nullable parameters
- Use `Dict`, `List`, `Tuple` from `typing` module

Example:
```python
def process_data(
    message: str,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process data with optional configuration."""
    ...
```

### Docstrings
- Use triple-quoted strings for all functions and classes
- Follow Google docstring format

Example:
```python
def fetch_data(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """
    Fetch data from a URL.

    Args:
        url: The URL to fetch from.
        timeout: Request timeout in seconds (default: 10.0).

    Returns:
        Dictionary containing the fetched data.

    Raises:
        ChatAdsAPIError: If the request fails.
    """
    ...
```

### Code Organization
- Keep functions focused and small (<50 lines ideally)
- Use descriptive variable names
- Group related functions together
- Add comments for complex logic
- Avoid deep nesting (max 3-4 levels)

### Error Handling
- Use specific exception types
- Provide helpful error messages
- Sanitize sensitive data (API keys) from error messages
- Log errors at appropriate levels

Example:
```python
try:
    response = await client.post(url, json=payload)
except httpx.TimeoutException as exc:
    LOGGER.warning("Request timed out: %s", sanitize_error(exc))
    raise ChatAdsAPIError(
        "Request timed out. Please try again.",
        code="TIMEOUT",
        status_code=504,
    ) from exc
```

## Testing Guidelines

### Writing Tests
- Write tests for all new functionality
- Aim for >90% code coverage
- Test both happy paths and error cases
- Use descriptive test names

Example:
```python
class TestNewFeature:
    """Tests for the new feature."""

    def test_valid_input_returns_success(self):
        """Test that valid input returns successful response."""
        result = process_feature("valid input")
        assert result["status"] == "success"

    def test_invalid_input_raises_error(self):
        """Test that invalid input raises appropriate error."""
        with pytest.raises(ChatAdsAPIError) as exc_info:
            process_feature("")
        assert exc_info.value.code == "INVALID_INPUT"
```

### Test Categories
- **Unit tests:** Test individual functions in isolation
- **Integration tests:** Test interactions with mocked HTTP responses
- **Edge cases:** Test boundary conditions and unusual inputs

## Reporting Bugs

When reporting bugs, please include:

1. **Clear description:** What happened vs. what you expected
2. **Steps to reproduce:** Minimal code example that reproduces the issue
3. **Environment details:**
   - Python version (`python --version`)
   - Operating system
   - Package versions (`pip list`)
4. **Error messages:** Full error output with stack traces
5. **API key redacted:** Replace API keys with `sk_live_***` or `sk_test_***`

**Example bug report:**
```markdown
### Description
Circuit breaker doesn't transition to HALF_OPEN after timeout

### Steps to Reproduce
1. Trigger 5 consecutive failures to open circuit breaker
2. Wait 60 seconds (timeout period)
3. Make new request
4. Circuit breaker remains OPEN instead of transitioning to HALF_OPEN

### Environment
- Python 3.11.5
- macOS 14.1
- chatads-mcp-wrapper 0.1.0

### Error Output
```
Circuit breaker is open. The API appears to be down.
```

### Expected Behavior
Circuit breaker should transition to HALF_OPEN and allow test request
```

## Suggesting Enhancements

We welcome feature requests! When suggesting enhancements:

1. **Check existing issues:** Search for similar requests first
2. **Provide context:** Explain the use case and motivation
3. **Describe the solution:** How would you like it to work?
4. **Consider alternatives:** Are there other ways to achieve the goal?
5. **Show examples:** Provide code examples if possible

## Questions?

- **Discussions:** Open a [GitHub Discussion](https://github.com/chatads/chatads-mcp-wrapper/discussions)
- **Issues:** For bugs or feature requests, open an [Issue](https://github.com/chatads/chatads-mcp-wrapper/issues)
- **Email:** For private inquiries, contact support@chatads.com

## Code of Conduct

### Our Pledge
We are committed to providing a welcoming and inclusive environment for everyone.

### Our Standards
- **Be respectful:** Treat all contributors with respect
- **Be constructive:** Provide helpful feedback
- **Be collaborative:** Work together to improve the project
- **Be patient:** Understand that contributors have varying experience levels

### Unacceptable Behavior
- Harassment, discrimination, or personal attacks
- Trolling or inflammatory comments
- Publishing others' private information
- Any conduct that would be inappropriate in a professional setting

## License

By contributing to ChatAds MCP Wrapper, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing! 🎉
