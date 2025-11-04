#!/bin/bash
# AI-Trader Test Runner
# Standardized script for running tests with various options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
TEST_TYPE="all"
COVERAGE=true
VERBOSE=false
FAIL_FAST=false
MARKERS=""
PARALLEL=false
HTML_REPORT=true

# Usage information
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Run AI-Trader test suite with standardized configuration.

OPTIONS:
    -t, --type TYPE        Test type: all, unit, integration, e2e (default: all)
    -m, --markers MARKERS  Run tests matching markers (e.g., "unit and not slow")
    -f, --fail-fast        Stop on first failure
    -n, --no-coverage      Skip coverage reporting
    -v, --verbose          Verbose output
    -p, --parallel         Run tests in parallel (requires pytest-xdist)
    --no-html              Skip HTML coverage report
    -h, --help             Show this help message

EXAMPLES:
    # Run all tests with coverage
    $0

    # Run only unit tests
    $0 -t unit

    # Run integration tests without coverage
    $0 -t integration -n

    # Run specific markers with fail-fast
    $0 -m "unit and not slow" -f

    # Run tests in parallel
    $0 -p

    # Quick test run (unit only, no coverage, fail-fast)
    $0 -t unit -n -f

MARKERS:
    unit         - Fast, isolated unit tests
    integration  - Tests with real dependencies
    e2e          - End-to-end tests (requires Docker)
    slow         - Tests taking >10 seconds
    performance  - Performance benchmarks
    security     - Security tests

EOF
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            TEST_TYPE="$2"
            shift 2
            ;;
        -m|--markers)
            MARKERS="$2"
            shift 2
            ;;
        -f|--fail-fast)
            FAIL_FAST=true
            shift
            ;;
        -n|--no-coverage)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        --no-html)
            HTML_REPORT=false
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="./venv/bin/python -m pytest"
PYTEST_ARGS="-v --tb=short"

# Add test type markers
if [ "$TEST_TYPE" != "all" ]; then
    if [ -n "$MARKERS" ]; then
        MARKERS="$TEST_TYPE and ($MARKERS)"
    else
        MARKERS="$TEST_TYPE"
    fi
fi

# Add custom markers
if [ -n "$MARKERS" ]; then
    PYTEST_ARGS="$PYTEST_ARGS -m \"$MARKERS\""
fi

# Add coverage options
if [ "$COVERAGE" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS --cov=api --cov=agent --cov=tools"
    PYTEST_ARGS="$PYTEST_ARGS --cov-report=term-missing"

    if [ "$HTML_REPORT" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS --cov-report=html:htmlcov"
    fi
else
    PYTEST_ARGS="$PYTEST_ARGS --no-cov"
fi

# Add fail-fast
if [ "$FAIL_FAST" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -x"
fi

# Add parallel execution
if [ "$PARALLEL" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -n auto"
fi

# Add verbosity
if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -vv"
fi

# Add test path
PYTEST_ARGS="$PYTEST_ARGS tests/"

# Print configuration
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI-Trader Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Test Type:    $TEST_TYPE"
echo "  Markers:      ${MARKERS:-none}"
echo "  Coverage:     $COVERAGE"
echo "  Fail Fast:    $FAIL_FAST"
echo "  Parallel:     $PARALLEL"
echo "  Verbose:      $VERBOSE"
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${RED}Error: Virtual environment not found at $PROJECT_ROOT/venv${NC}"
    echo -e "${YELLOW}Please run: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt${NC}"
    exit 1
fi

# Check if pytest is installed
if ! ./venv/bin/python -c "import pytest" 2>/dev/null; then
    echo -e "${RED}Error: pytest not installed${NC}"
    echo -e "${YELLOW}Please run: ./venv/bin/pip install -r requirements.txt${NC}"
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# Run tests
echo -e "${BLUE}Running tests...${NC}"
echo ""

# Execute pytest with eval to handle quotes properly
eval "$PYTEST_CMD $PYTEST_ARGS"
TEST_EXIT_CODE=$?

# Print results
echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"

    if [ "$COVERAGE" = true ] && [ "$HTML_REPORT" = true ]; then
        echo ""
        echo -e "${YELLOW}Coverage report generated:${NC}"
        echo "  HTML: file://$PROJECT_ROOT/htmlcov/index.html"
    fi
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Tests failed${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $TEST_EXIT_CODE