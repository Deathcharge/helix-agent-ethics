# Contributing to Helix Ethics

Thank you for your interest in contributing to ethical AI governance! This document provides guidelines for contributing to the Helix Ethics project.

## Code of Conduct

We are committed to providing a welcoming community. Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## How to Contribute

### Reporting Issues

When reporting issues, please include:
- Clear, descriptive title
- Steps to reproduce the problem
- Expected vs. actual behavior
- Environment details (Python version, OS, etc.)
- Any relevant code snippets or logs

### Suggesting Enhancements

Enhancement suggestions should include:
- Clear description of the enhancement
- Use cases and benefits
- Potential implementation approach
- Examples of similar features in other projects

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Add tests for new functionality
5. Run tests and linting: `pytest && black . && ruff check .`
6. Commit with clear messages
7. Push and create a pull request

## Development Setup

```bash
# Clone and setup
git clone https://github.com/Deathcharge/helix-hub-knowledge.git
cd helix-hub-knowledge
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Format code
black src/ tests/
ruff check src/ tests/
```

## Code Style

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Include docstrings for all public functions

## Testing

- Aim for >80% code coverage
- Test both success and failure cases
- Include edge cases

## License

By contributing, you agree your contributions will be licensed under Apache License 2.0.

---

Thank you for contributing to ethical AI! 🛡️
