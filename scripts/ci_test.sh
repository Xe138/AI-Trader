#!/bin/bash
# AI-Trader CI Test Script
# Optimized for CI/CD environments (GitHub Actions, Jenkins, etc.)

set -e

# Colors for output (disabled in CI if not supported)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# CI-specific defaults
FAIL_FAST=false
JUNIT_XML=true
COVERAGE_MIN=85
PARALLEL=false
VERBOSE=false

# Parse environment variables (common in CI)
if [ -n "$CI_FAIL_FAST" ]; then
    FAIL_FAST="$CI_FAIL_FAST"
fi

if [ -n "$CI_COVERAGE_MIN" ]; then
    COVERAGE_MIN="$CI_COVERAGE_MIN"
fi

if [ -n "$CI_PARALLEL" ]; then
    PARALLEL="$CI_PARALLEL"
fi

if [ -n "$CI_VERBOSE" ]; then
    VERBOSE="$CI_VERBOSE"
fi

# Parse command line arguments (override env vars)
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--fail-fast)
            FAIL_FAST=true
            shift
            ;;
        -m|--min-coverage)
            COVERAGE_MIN="$2"
            shift 2
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --no-junit)
            JUNIT_XML=false
            shift
            ;;
        -h|--help)
            cat << EOF
Usage: $0 [OPTIONS]

CI-optimized test runner for AI-Trader.

OPTIONS:
    -f, --fail-fast         Stop on first failure
    -m, --min-coverage NUM  Minimum coverage percentage (default: 85)
    -p, --parallel          Run tests in parallel
    -v, --verbose           Verbose output
    --no-junit              Skip JUnit XML generation
    -h, --help              Show this help message

ENVIRONMENT VARIABLES:
    CI_FAIL_FAST            Set to 'true' to enable fail-fast
    CI_COVERAGE_MIN         Minimum coverage threshold
    CI_PARALLEL             Set to 'true' to enable parallel execution
    CI_VERBOSE              Set to 'true' for verbose output

EXAMPLES:
    # Basic CI run
    $0

    # Fail fast with custom coverage threshold
    $0 -f -m 90

    # Parallel execution
    $0 -p

    # GitHub Actions
    CI_FAIL_FAST=true CI_COVERAGE_MIN=90 $0

EOF
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI-Trader CI Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}CI Configuration:${NC}"
echo "  Fail Fast:        $FAIL_FAST"
echo "  Min Coverage:     ${COVERAGE_MIN}%"
echo "  Parallel:         $PARALLEL"
echo "  Verbose:          $VERBOSE"
echo "  JUnit XML:        $JUNIT_XML"
echo "  Environment:      ${CI:-local}"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
PYTHON_VERSION=$(./venv/bin/python --version 2>&1)
echo "  $PYTHON_VERSION"
echo ""

# Install/verify dependencies
echo -e "${YELLOW}Verifying test dependencies...${NC}"
./venv/bin/python -m pip install --quiet pytest pytest-cov pytest-xdist 2>&1 | grep -v "already satisfied" || true
echo "  ✓ Dependencies verified"
echo ""

# Build pytest command
PYTEST_CMD="./venv/bin/python -m pytest"
PYTEST_ARGS="-v --tb=short --strict-markers"

# Coverage
PYTEST_ARGS="$PYTEST_ARGS --cov=api --cov=agent --cov=tools"
PYTEST_ARGS="$PYTEST_ARGS --cov-report=term-missing:skip-covered"
PYTEST_ARGS="$PYTEST_ARGS --cov-report=html:htmlcov"
PYTEST_ARGS="$PYTEST_ARGS --cov-report=xml:coverage.xml"
PYTEST_ARGS="$PYTEST_ARGS --cov-fail-under=$COVERAGE_MIN"

# JUnit XML for CI integrations
if [ "$JUNIT_XML" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS --junit-xml=junit.xml"
fi

# Fail fast
if [ "$FAIL_FAST" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -x"
fi

# Parallel execution
if [ "$PARALLEL" = true ]; then
    # Check if pytest-xdist is available
    if ./venv/bin/python -c "import xdist" 2>/dev/null; then
        PYTEST_ARGS="$PYTEST_ARGS -n auto"
        echo -e "${YELLOW}Parallel execution enabled${NC}"
    else
        echo -e "${YELLOW}Warning: pytest-xdist not available, running sequentially${NC}"
    fi
    echo ""
fi

# Verbose
if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -vv"
fi

# Exclude e2e tests in CI (require Docker)
PYTEST_ARGS="$PYTEST_ARGS -m 'not e2e'"

# Test path
PYTEST_ARGS="$PYTEST_ARGS tests/"

# Run tests
echo -e "${BLUE}Running test suite...${NC}"
echo ""
echo "Command: $PYTEST_CMD $PYTEST_ARGS"
echo ""

# Execute tests
set +e  # Don't exit on test failure, we want to process results
$PYTEST_CMD $PYTEST_ARGS
TEST_EXIT_CODE=$?
set -e

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Test Results${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Process results
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""

    # Show artifacts
    echo -e "${YELLOW}Artifacts generated:${NC}"
    if [ -f "coverage.xml" ]; then
        echo "  ✓ coverage.xml (for CI coverage tools)"
    fi
    if [ -f "junit.xml" ]; then
        echo "  ✓ junit.xml (for CI test reporting)"
    fi
    if [ -d "htmlcov" ]; then
        echo "  ✓ htmlcov/ (HTML coverage report)"
    fi
else
    echo -e "${RED}✗ Tests failed (exit code: $TEST_EXIT_CODE)${NC}"
    echo ""

    if [ $TEST_EXIT_CODE -eq 1 ]; then
        echo "  Reason: Test failures"
    elif [ $TEST_EXIT_CODE -eq 2 ]; then
        echo "  Reason: Test execution interrupted"
    elif [ $TEST_EXIT_CODE -eq 3 ]; then
        echo "  Reason: Internal pytest error"
    elif [ $TEST_EXIT_CODE -eq 4 ]; then
        echo "  Reason: pytest usage error"
    elif [ $TEST_EXIT_CODE -eq 5 ]; then
        echo "  Reason: No tests collected"
    fi
fi

echo ""
echo -e "${BLUE}========================================${NC}"

# Exit with test result code
exit $TEST_EXIT_CODE