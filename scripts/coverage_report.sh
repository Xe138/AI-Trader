#!/bin/bash
# AI-Trader Coverage Report Generator
# Generate detailed coverage reports and check coverage thresholds

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
MIN_COVERAGE=85
OPEN_HTML=false
INCLUDE_INTEGRATION=false

# Usage information
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Generate coverage reports for AI-Trader test suite.

OPTIONS:
    -m, --min-coverage NUM  Minimum coverage percentage (default: 85)
    -o, --open              Open HTML report in browser after generation
    -i, --include-integration  Include integration and e2e tests
    -h, --help              Show this help message

EXAMPLES:
    # Generate coverage report with default threshold (85%)
    $0

    # Set custom coverage threshold
    $0 -m 90

    # Generate and open HTML report
    $0 -o

    # Include integration tests in coverage
    $0 -i

EOF
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--min-coverage)
            MIN_COVERAGE="$2"
            shift 2
            ;;
        -o|--open)
            OPEN_HTML=true
            shift
            ;;
        -i|--include-integration)
            INCLUDE_INTEGRATION=true
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

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI-Trader Coverage Report${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Minimum Coverage: ${MIN_COVERAGE}%"
echo "  Include Integration: $INCLUDE_INTEGRATION"
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${RED}Error: Virtual environment not found${NC}"
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# Build pytest command
PYTEST_CMD="./venv/bin/python -m pytest tests/"
PYTEST_ARGS="-v --tb=short"
PYTEST_ARGS="$PYTEST_ARGS --cov=api --cov=agent --cov=tools"
PYTEST_ARGS="$PYTEST_ARGS --cov-report=term-missing"
PYTEST_ARGS="$PYTEST_ARGS --cov-report=html:htmlcov"
PYTEST_ARGS="$PYTEST_ARGS --cov-report=json:coverage.json"
PYTEST_ARGS="$PYTEST_ARGS --cov-fail-under=$MIN_COVERAGE"

# Filter tests if not including integration
if [ "$INCLUDE_INTEGRATION" = false ]; then
    PYTEST_ARGS="$PYTEST_ARGS -m 'not e2e'"
    echo -e "${YELLOW}Running tests (excluding e2e)...${NC}"
else
    echo -e "${YELLOW}Running all tests...${NC}"
fi

echo ""

# Run tests with coverage
$PYTEST_CMD $PYTEST_ARGS
TEST_EXIT_CODE=$?

echo ""

# Parse coverage from JSON report
if [ -f "coverage.json" ]; then
    TOTAL_COVERAGE=$(./venv/bin/python -c "import json; data=json.load(open('coverage.json')); print(f\"{data['totals']['percent_covered']:.2f}\")")

    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Coverage Summary${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "  Total Coverage: ${GREEN}${TOTAL_COVERAGE}%${NC}"
    echo -e "  Minimum Required: ${MIN_COVERAGE}%"
    echo ""

    if [ $TEST_EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✓ Coverage threshold met!${NC}"
    else
        echo -e "${RED}✗ Coverage below threshold${NC}"
    fi

    echo ""
    echo -e "${YELLOW}Reports Generated:${NC}"
    echo "  HTML:  file://$PROJECT_ROOT/htmlcov/index.html"
    echo "  JSON:  $PROJECT_ROOT/coverage.json"
    echo "  Terminal: (shown above)"

    # Open HTML report if requested
    if [ "$OPEN_HTML" = true ]; then
        echo ""
        echo -e "${BLUE}Opening HTML report...${NC}"

        # Try different browsers/commands
        if command -v xdg-open &> /dev/null; then
            xdg-open "htmlcov/index.html"
        elif command -v open &> /dev/null; then
            open "htmlcov/index.html"
        elif command -v start &> /dev/null; then
            start "htmlcov/index.html"
        else
            echo -e "${YELLOW}Could not open browser automatically${NC}"
            echo "Please open: file://$PROJECT_ROOT/htmlcov/index.html"
        fi
    fi
else
    echo -e "${RED}Error: coverage.json not generated${NC}"
    TEST_EXIT_CODE=1
fi

echo ""
echo -e "${BLUE}========================================${NC}"

exit $TEST_EXIT_CODE