# AI-Trader Scripts

This directory contains standardized scripts for testing, validation, and operations.

## Testing Scripts

### Interactive Testing

**`test.sh`** - Interactive test menu
```bash
bash scripts/test.sh
```
User-friendly menu for all testing operations. Best for local development.

### Development Testing

**`quick_test.sh`** - Fast unit test feedback
```bash
bash scripts/quick_test.sh
```
- Runs unit tests only
- No coverage
- Fails fast
- ~10-30 seconds

**`run_tests.sh`** - Full test suite
```bash
bash scripts/run_tests.sh [OPTIONS]
```
- All test types (unit, integration, e2e)
- Coverage reporting
- Parallel execution support
- Highly configurable

**`coverage_report.sh`** - Coverage analysis
```bash
bash scripts/coverage_report.sh [OPTIONS]
```
- Generate HTML/JSON/terminal reports
- Check coverage thresholds
- Open reports in browser

### CI/CD Testing

**`ci_test.sh`** - CI-optimized testing
```bash
bash scripts/ci_test.sh [OPTIONS]
```
- JUnit XML output
- Coverage XML for CI tools
- Environment variable configuration
- Excludes Docker tests

## Validation Scripts

**`validate_docker_build.sh`** - Docker build validation
```bash
bash scripts/validate_docker_build.sh
```
Validates Docker setup, build, and container startup.

**`test_api_endpoints.sh`** - API endpoint testing
```bash
bash scripts/test_api_endpoints.sh
```
Tests all REST API endpoints with real simulations.

## Other Scripts

**`migrate_price_data.py`** - Data migration utility
```bash
python scripts/migrate_price_data.py
```
Migrates price data between formats.

## Quick Reference

| Task | Script | Command |
|------|--------|---------|
| Quick test | `quick_test.sh` | `bash scripts/quick_test.sh` |
| Full test | `run_tests.sh` | `bash scripts/run_tests.sh` |
| Coverage | `coverage_report.sh` | `bash scripts/coverage_report.sh -o` |
| CI test | `ci_test.sh` | `bash scripts/ci_test.sh -f` |
| Interactive | `test.sh` | `bash scripts/test.sh` |
| Docker validation | `validate_docker_build.sh` | `bash scripts/validate_docker_build.sh` |
| API testing | `test_api_endpoints.sh` | `bash scripts/test_api_endpoints.sh` |

## Common Options

Most test scripts support:
- `-h, --help` - Show help
- `-v, --verbose` - Verbose output
- `-f, --fail-fast` - Stop on first failure
- `-t, --type TYPE` - Test type (unit, integration, e2e, all)
- `-m, --markers MARKERS` - Pytest markers
- `-p, --parallel` - Parallel execution

## Documentation

For detailed usage, see:
- [Testing Guide](../docs/developer/testing.md)
- [Testing & Validation Guide](../TESTING_GUIDE.md)

## Making Scripts Executable

If scripts are not executable:
```bash
chmod +x scripts/*.sh
```