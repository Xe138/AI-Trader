#!/bin/bash
# AI-Trader Quick Test Script
# Fast test run for rapid feedback during development

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

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI-Trader Quick Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Running unit tests (no coverage, fail-fast)${NC}"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Check if virtual environment exists
if [ ! -d "./venv" ]; then
    echo -e "${RED}Error: Virtual environment not found${NC}"
    echo -e "${YELLOW}Please run: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt${NC}"
    exit 1
fi

# Run unit tests only, no coverage, fail on first error
./venv/bin/python -m pytest tests/ \
    -v \
    -m "unit and not slow" \
    -x \
    --tb=short \
    --no-cov

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Quick tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}For full test suite with coverage, run:${NC}"
    echo "  bash scripts/run_tests.sh"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Quick tests failed${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $TEST_EXIT_CODE