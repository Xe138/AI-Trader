# Testing Guide

This guide covers running tests for the AI-Trader project, including unit tests, integration tests, and end-to-end tests.

## Quick Start

```bash
# Interactive test menu (recommended for local development)
bash scripts/test.sh

# Quick unit tests (fast feedback)
bash scripts/quick_test.sh

# Full test suite with coverage
bash scripts/run_tests.sh

# Generate coverage report
bash scripts/coverage_report.sh
```

---

## Test Scripts Overview

### 1. `test.sh` - Interactive Test Helper

**Purpose:** Interactive menu for common test operations

**Usage:**
```bash
# Interactive mode
bash scripts/test.sh

# Non-interactive mode
bash scripts/test.sh -t unit -f
```

**Menu Options:**
1. Quick test (unit only, no coverage)
2. Full test suite (with coverage)
3. Coverage report
4. Unit tests only
5. Integration tests only
6. E2E tests only
7. Run with custom markers
8. Parallel execution
9. CI mode

---

### 2. `quick_test.sh` - Fast Feedback Loop

**Purpose:** Rapid test execution during development

**Usage:**
```bash
bash scripts/quick_test.sh
```

**When to use:**
- During active development
- Before committing code
- Quick verification of changes
- TDD workflow

---

### 3. `run_tests.sh` - Main Test Runner

**Purpose:** Comprehensive test execution with full configuration options

**Usage:**
```bash
# Run all tests with coverage (default)
bash scripts/run_tests.sh

# Run only unit tests
bash scripts/run_tests.sh -t unit

# Run without coverage
bash scripts/run_tests.sh -n

# Run with custom markers
bash scripts/run_tests.sh -m "unit and not slow"

# Fail on first error
bash scripts/run_tests.sh -f

# Run tests in parallel
bash scripts/run_tests.sh -p
```

**Options:**
```
-t, --type TYPE        Test type: all, unit, integration, e2e (default: all)
-m, --markers MARKERS  Run tests matching markers
-f, --fail-fast        Stop on first failure
-n, --no-coverage      Skip coverage reporting
-v, --verbose          Verbose output
-p, --parallel         Run tests in parallel
--no-html              Skip HTML coverage report
-h, --help             Show help message
```

---

### 4. `coverage_report.sh` - Coverage Analysis

**Purpose:** Generate detailed coverage reports

**Usage:**
```bash
# Generate coverage report (default: 85% threshold)
bash scripts/coverage_report.sh

# Set custom coverage threshold
bash scripts/coverage_report.sh -m 90

# Generate and open HTML report
bash scripts/coverage_report.sh -o
```

**Options:**
```
-m, --min-coverage NUM  Minimum coverage percentage (default: 85)
-o, --open              Open HTML report in browser
-i, --include-integration  Include integration and e2e tests
-h, --help              Show help message
```

---

### 5. `ci_test.sh` - CI/CD Optimized Runner

**Purpose:** Test execution optimized for CI/CD environments

**Usage:**
```bash
# Basic CI run
bash scripts/ci_test.sh

# Fail fast with custom coverage
bash scripts/ci_test.sh -f -m 90

# Using environment variables
CI_FAIL_FAST=true CI_COVERAGE_MIN=90 bash scripts/ci_test.sh
```

**Environment Variables:**
```bash
CI_FAIL_FAST=true          # Enable fail-fast mode
CI_COVERAGE_MIN=90         # Set coverage threshold
CI_PARALLEL=true           # Enable parallel execution
CI_VERBOSE=true            # Enable verbose output
```

**Output artifacts:**
- `junit.xml` - Test results for CI reporting
- `coverage.xml` - Coverage data for CI tools
- `htmlcov/` - HTML coverage report

---

## Test Structure

```
tests/
├── conftest.py              # Shared pytest fixtures
├── unit/                    # Fast, isolated tests
├── integration/             # Tests with dependencies
├── e2e/                     # End-to-end tests
├── performance/             # Performance benchmarks
└── security/                # Security tests
```

---

## Test Markers

Tests are organized using pytest markers:

| Marker | Description | Usage |
|--------|-------------|-------|
| `unit` | Fast, isolated unit tests | `-m unit` |
| `integration` | Tests with real dependencies | `-m integration` |
| `e2e` | End-to-end tests (requires Docker) | `-m e2e` |
| `slow` | Tests taking >10 seconds | `-m slow` |
| `performance` | Performance benchmarks | `-m performance` |
| `security` | Security tests | `-m security` |

**Examples:**
```bash
# Run only unit tests
bash scripts/run_tests.sh -m unit

# Run all except slow tests
bash scripts/run_tests.sh -m "not slow"

# Combine markers
bash scripts/run_tests.sh -m "unit and not slow"
```

---

## Common Workflows

### During Development

```bash
# Quick check before each commit
bash scripts/quick_test.sh

# Run relevant test type
bash scripts/run_tests.sh -t unit -f

# Full test before push
bash scripts/run_tests.sh
```

### Before Pull Request

```bash
# Run full test suite
bash scripts/run_tests.sh

# Generate coverage report
bash scripts/coverage_report.sh -o

# Ensure coverage meets 85% threshold
```

### CI/CD Pipeline

```bash
# Run CI-optimized tests
bash scripts/ci_test.sh -f -m 85
```

---

## Debugging Test Failures

```bash
# Run with verbose output
bash scripts/run_tests.sh -v -f

# Run specific test file
./venv/bin/python -m pytest tests/unit/test_database.py -v

# Run specific test function
./venv/bin/python -m pytest tests/unit/test_database.py::test_function -v

# Run with debugger on failure
./venv/bin/python -m pytest --pdb tests/

# Show print statements
./venv/bin/python -m pytest -s tests/
```

---

## Coverage Configuration

Configured in `pytest.ini`:
- Minimum coverage: 85%
- Target coverage: 90%
- Coverage reports: HTML, JSON, terminal

---

## Writing New Tests

### Unit Test Example

```python
import pytest

@pytest.mark.unit
def test_function_returns_expected_value():
    # Arrange
    input_data = {"key": "value"}

    # Act
    result = my_function(input_data)

    # Assert
    assert result == expected_output
```

### Integration Test Example

```python
@pytest.mark.integration
def test_database_integration(clean_db):
    conn = get_db_connection(clean_db)
    insert_data(conn, test_data)
    result = query_data(conn)
    assert len(result) == 1
```

---

## Docker Testing

### Docker Build Validation

```bash
bash scripts/validate_docker_build.sh
```

Validates:
- Docker installation
- Environment configuration
- Image build
- Container startup
- Health endpoint

### API Endpoint Testing

```bash
bash scripts/test_api_endpoints.sh
```

Tests all API endpoints with real simulations.

---

## Summary

| Script | Purpose | Speed | Coverage | Use Case |
|--------|---------|-------|----------|----------|
| `test.sh` | Interactive menu | Varies | Optional | Local development |
| `quick_test.sh` | Fast feedback | ⚡⚡⚡ | No | Active development |
| `run_tests.sh` | Full test suite | ⚡⚡ | Yes | Pre-commit, pre-PR |
| `coverage_report.sh` | Coverage analysis | ⚡ | Yes | Coverage review |
| `ci_test.sh` | CI/CD pipeline | ⚡⚡ | Yes | Automation |

---

For detailed testing procedures and troubleshooting, see [TESTING_GUIDE.md](../../TESTING_GUIDE.md).
