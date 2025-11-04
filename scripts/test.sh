#!/bin/bash
# AI-Trader Test Helper
# Interactive menu for common test operations

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

show_menu() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   AI-Trader Test Helper${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "${CYAN}Quick Actions:${NC}"
    echo "  1) Quick test (unit only, no coverage)"
    echo "  2) Full test suite (with coverage)"
    echo "  3) Coverage report"
    echo ""
    echo -e "${CYAN}Specific Test Types:${NC}"
    echo "  4) Unit tests only"
    echo "  5) Integration tests only"
    echo "  6) E2E tests only (requires Docker)"
    echo ""
    echo -e "${CYAN}Advanced Options:${NC}"
    echo "  7) Run with custom markers"
    echo "  8) Parallel execution"
    echo "  9) CI mode (for automation)"
    echo ""
    echo -e "${CYAN}Other:${NC}"
    echo "  h) Show help"
    echo "  q) Quit"
    echo ""
    echo -ne "${YELLOW}Select an option: ${NC}"
}

run_quick_test() {
    echo -e "${BLUE}Running quick test...${NC}"
    bash "$SCRIPT_DIR/quick_test.sh"
}

run_full_test() {
    echo -e "${BLUE}Running full test suite...${NC}"
    bash "$SCRIPT_DIR/run_tests.sh"
}

run_coverage() {
    echo -e "${BLUE}Generating coverage report...${NC}"
    bash "$SCRIPT_DIR/coverage_report.sh" -o
}

run_unit() {
    echo -e "${BLUE}Running unit tests...${NC}"
    bash "$SCRIPT_DIR/run_tests.sh" -t unit
}

run_integration() {
    echo -e "${BLUE}Running integration tests...${NC}"
    bash "$SCRIPT_DIR/run_tests.sh" -t integration
}

run_e2e() {
    echo -e "${BLUE}Running E2E tests...${NC}"
    echo -e "${YELLOW}Note: This requires Docker to be running${NC}"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        bash "$SCRIPT_DIR/run_tests.sh" -t e2e
    fi
}

run_custom_markers() {
    echo ""
    echo -e "${YELLOW}Available markers:${NC}"
    echo "  - unit"
    echo "  - integration"
    echo "  - e2e"
    echo "  - slow"
    echo "  - performance"
    echo "  - security"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  unit and not slow"
    echo "  integration or performance"
    echo "  not e2e"
    echo ""
    read -p "Enter markers expression: " markers

    if [ -n "$markers" ]; then
        echo -e "${BLUE}Running tests with markers: $markers${NC}"
        bash "$SCRIPT_DIR/run_tests.sh" -m "$markers"
    else
        echo -e "${RED}No markers provided, skipping${NC}"
        sleep 2
    fi
}

run_parallel() {
    echo -e "${BLUE}Running tests in parallel...${NC}"
    bash "$SCRIPT_DIR/run_tests.sh" -p
}

run_ci() {
    echo -e "${BLUE}Running in CI mode...${NC}"
    bash "$SCRIPT_DIR/ci_test.sh"
}

show_help() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}AI-Trader Test Scripts Help${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "${CYAN}Available Scripts:${NC}"
    echo ""
    echo -e "${GREEN}1. quick_test.sh${NC}"
    echo "   Fast feedback loop for development"
    echo "   - Runs unit tests only"
    echo "   - No coverage reporting"
    echo "   - Fails fast on first error"
    echo "   Usage: bash scripts/quick_test.sh"
    echo ""
    echo -e "${GREEN}2. run_tests.sh${NC}"
    echo "   Main test runner with full options"
    echo "   - Supports all test types (unit, integration, e2e)"
    echo "   - Coverage reporting"
    echo "   - Custom marker filtering"
    echo "   - Parallel execution"
    echo "   Usage: bash scripts/run_tests.sh [OPTIONS]"
    echo "   Examples:"
    echo "     bash scripts/run_tests.sh -t unit"
    echo "     bash scripts/run_tests.sh -m 'not slow' -f"
    echo "     bash scripts/run_tests.sh -p"
    echo ""
    echo -e "${GREEN}3. coverage_report.sh${NC}"
    echo "   Generate detailed coverage reports"
    echo "   - HTML, JSON, and terminal reports"
    echo "   - Configurable coverage thresholds"
    echo "   - Can open HTML report in browser"
    echo "   Usage: bash scripts/coverage_report.sh [OPTIONS]"
    echo "   Examples:"
    echo "     bash scripts/coverage_report.sh -o"
    echo "     bash scripts/coverage_report.sh -m 90"
    echo ""
    echo -e "${GREEN}4. ci_test.sh${NC}"
    echo "   CI/CD optimized test runner"
    echo "   - JUnit XML output"
    echo "   - Coverage XML for CI tools"
    echo "   - Environment variable configuration"
    echo "   - Skips Docker-dependent tests"
    echo "   Usage: bash scripts/ci_test.sh [OPTIONS]"
    echo "   Examples:"
    echo "     bash scripts/ci_test.sh -f -m 90"
    echo "     CI_PARALLEL=true bash scripts/ci_test.sh"
    echo ""
    echo -e "${CYAN}Common Options:${NC}"
    echo "  -t, --type        Test type (unit, integration, e2e, all)"
    echo "  -m, --markers     Pytest markers expression"
    echo "  -f, --fail-fast   Stop on first failure"
    echo "  -p, --parallel    Run tests in parallel"
    echo "  -n, --no-coverage Skip coverage reporting"
    echo "  -v, --verbose     Verbose output"
    echo "  -h, --help        Show help"
    echo ""
    echo -e "${CYAN}Test Markers:${NC}"
    echo "  unit          - Fast, isolated unit tests"
    echo "  integration   - Tests with real dependencies"
    echo "  e2e           - End-to-end tests (requires Docker)"
    echo "  slow          - Tests taking >10 seconds"
    echo "  performance   - Performance benchmarks"
    echo "  security      - Security tests"
    echo ""
    echo -e "Press any key to return to menu..."
    read -n 1 -s
}

# Main menu loop
if [ $# -eq 0 ]; then
    # Interactive mode
    while true; do
        show_menu
        read -n 1 choice
        echo ""

        case $choice in
            1)
                run_quick_test
                ;;
            2)
                run_full_test
                ;;
            3)
                run_coverage
                ;;
            4)
                run_unit
                ;;
            5)
                run_integration
                ;;
            6)
                run_e2e
                ;;
            7)
                run_custom_markers
                ;;
            8)
                run_parallel
                ;;
            9)
                run_ci
                ;;
            h|H)
                show_help
                ;;
            q|Q)
                echo -e "${GREEN}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}"
                sleep 1
                ;;
        esac

        if [ $? -eq 0 ]; then
            echo ""
            echo -e "${GREEN}Operation completed successfully!${NC}"
        else
            echo ""
            echo -e "${RED}Operation failed!${NC}"
        fi

        echo ""
        read -p "Press Enter to continue..."
    done
else
    # Non-interactive: forward to run_tests.sh
    bash "$SCRIPT_DIR/run_tests.sh" "$@"
fi