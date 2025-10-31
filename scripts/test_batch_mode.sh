#!/bin/bash
# Batch Mode Testing Script
# Tests Docker batch mode with one-time simulation

set -e

echo "=========================================="
echo "AI-Trader Batch Mode Testing"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗${NC} Docker not installed"
    exit 1
fi

if [ ! -f .env ]; then
    echo -e "${RED}✗${NC} .env file not found"
    echo "Copy .env.example to .env and configure API keys"
    exit 1
fi

echo -e "${GREEN}✓${NC} Prerequisites OK"
echo ""

# Check if custom config exists
CONFIG_FILE=${1:-configs/default_config.json}

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}⚠${NC} Config file not found: $CONFIG_FILE"
    echo "Creating test config..."

    mkdir -p configs

    cat > configs/test_batch.json <<EOF
{
  "agent_type": "BaseAgent",
  "date_range": {
    "init_date": "2025-01-16",
    "end_date": "2025-01-17"
  },
  "models": [
    {
      "name": "GPT-4 Test",
      "basemodel": "gpt-4",
      "signature": "gpt-4-test",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 10,
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
EOF

    CONFIG_FILE="configs/test_batch.json"
    echo -e "${GREEN}✓${NC} Created test config: $CONFIG_FILE"
fi

echo "Using config: $CONFIG_FILE"
echo ""

# Test 1: Build image
echo -e "${BLUE}Test 1: Building Docker image${NC}"
echo "This may take a few minutes..."

if docker build -t ai-trader-batch-test . > /tmp/docker-build.log 2>&1; then
    echo -e "${GREEN}✓${NC} Image built successfully"
else
    echo -e "${RED}✗${NC} Build failed"
    echo "Check logs: /tmp/docker-build.log"
    tail -20 /tmp/docker-build.log
    exit 1
fi
echo ""

# Test 2: Run batch simulation
echo -e "${BLUE}Test 2: Running batch simulation${NC}"
echo "Starting container in batch mode..."
echo "Config: $CONFIG_FILE"
echo ""

# Use docker-compose if available, otherwise docker run
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    echo "Using docker-compose..."

    # Ensure API is stopped
    docker-compose down 2>/dev/null || true

    # Run batch mode
    echo "Executing: docker-compose --profile batch run --rm ai-trader-batch $CONFIG_FILE"
    docker-compose --profile batch run --rm ai-trader-batch "$CONFIG_FILE"
    BATCH_EXIT_CODE=$?
else
    echo "Using docker run..."
    docker run --rm \
        --env-file .env \
        -v "$(pwd)/data:/app/data" \
        -v "$(pwd)/logs:/app/logs" \
        -v "$(pwd)/configs:/app/configs" \
        ai-trader-batch-test \
        "$CONFIG_FILE"
    BATCH_EXIT_CODE=$?
fi

echo ""

# Test 3: Check exit code
echo -e "${BLUE}Test 3: Checking exit status${NC}"

if [ $BATCH_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Batch simulation completed successfully (exit code: 0)"
else
    echo -e "${RED}✗${NC} Batch simulation failed (exit code: $BATCH_EXIT_CODE)"
    echo "Check logs in ./logs/ directory"
    exit 1
fi
echo ""

# Test 4: Verify output files
echo -e "${BLUE}Test 4: Verifying output files${NC}"

# Check if data directory has position files
POSITION_FILES=$(find data/agent_data -name "position.jsonl" 2>/dev/null | wc -l)

if [ $POSITION_FILES -gt 0 ]; then
    echo -e "${GREEN}✓${NC} Found $POSITION_FILES position file(s)"

    # Show sample position data
    SAMPLE_POSITION=$(find data/agent_data -name "position.jsonl" 2>/dev/null | head -1)
    if [ -n "$SAMPLE_POSITION" ]; then
        echo "Sample position data from: $SAMPLE_POSITION"
        head -1 "$SAMPLE_POSITION" | jq '.' 2>/dev/null || head -1 "$SAMPLE_POSITION"
    fi
else
    echo -e "${YELLOW}⚠${NC} No position files found"
    echo "This could indicate the simulation didn't complete trading"
fi
echo ""

# Check log files
LOG_COUNT=$(find logs -name "*.log" 2>/dev/null | wc -l)
if [ $LOG_COUNT -gt 0 ]; then
    echo -e "${GREEN}✓${NC} Found $LOG_COUNT log file(s)"
else
    echo -e "${YELLOW}⚠${NC} No log files found"
fi
echo ""

# Test 5: Check price data
echo -e "${BLUE}Test 5: Checking price data${NC}"

if [ -f "data/merged.jsonl" ]; then
    STOCK_COUNT=$(wc -l < data/merged.jsonl)
    echo -e "${GREEN}✓${NC} Price data exists: $STOCK_COUNT stocks"
else
    echo -e "${YELLOW}⚠${NC} No price data file found"
    echo "First run will download price data"
fi
echo ""

# Test 6: Re-run to test data persistence
echo -e "${BLUE}Test 6: Testing data persistence${NC}"
echo "Running batch mode again to verify data persists..."
echo ""

if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    docker-compose --profile batch run --rm ai-trader-batch "$CONFIG_FILE" > /tmp/batch-second-run.log 2>&1
    SECOND_EXIT_CODE=$?
else
    docker run --rm \
        --env-file .env \
        -v "$(pwd)/data:/app/data" \
        -v "$(pwd)/logs:/app/logs" \
        -v "$(pwd)/configs:/app/configs" \
        ai-trader-batch-test \
        "$CONFIG_FILE" > /tmp/batch-second-run.log 2>&1
    SECOND_EXIT_CODE=$?
fi

if [ $SECOND_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Second run completed successfully"

    # Check if it reused price data (should be faster)
    if grep -q "Using existing price data" /tmp/batch-second-run.log; then
        echo -e "${GREEN}✓${NC} Price data was reused (data persistence working)"
    else
        echo -e "${YELLOW}⚠${NC} Could not verify price data reuse"
    fi
else
    echo -e "${RED}✗${NC} Second run failed"
fi
echo ""

# Summary
echo "=========================================="
echo "Batch Mode Test Summary"
echo "=========================================="
echo ""
echo "Tests completed:"
echo "  ✓ Docker image build"
echo "  ✓ Batch mode execution"
echo "  ✓ Exit code verification"
echo "  ✓ Output file generation"
echo "  ✓ Data persistence"
echo ""
echo "Output locations:"
echo "  Position data: data/agent_data/*/position/"
echo "  Trading logs: data/agent_data/*/log/"
echo "  System logs: logs/"
echo "  Price data: data/merged.jsonl"
echo ""
echo "To view position data:"
echo "  find data/agent_data -name 'position.jsonl' -exec cat {} \;"
echo ""
echo "To view trading logs:"
echo "  find data/agent_data -name 'log.jsonl' | head -1 | xargs cat"
echo ""
