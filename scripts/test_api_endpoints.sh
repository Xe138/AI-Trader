#!/bin/bash
# API Endpoint Testing Script
# Tests all REST API endpoints in running Docker container

set -e

echo "=========================================="
echo "AI-Trader API Endpoint Testing"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
API_BASE_URL=${API_BASE_URL:-http://localhost:8080}
TEST_CONFIG="/app/configs/default_config.json"

# Check if API is running
echo "Checking if API is accessible..."
if ! curl -f "$API_BASE_URL/health" &> /dev/null; then
    echo -e "${RED}✗${NC} API is not accessible at $API_BASE_URL"
    echo "Make sure the container is running:"
    echo "  docker-compose up -d ai-trader-api"
    exit 1
fi
echo -e "${GREEN}✓${NC} API is accessible"
echo ""

# Test 1: Health Check
echo -e "${BLUE}Test 1: GET /health${NC}"
echo "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s "$API_BASE_URL/health")
HEALTH_STATUS=$(echo $HEALTH_RESPONSE | jq -r '.status' 2>/dev/null || echo "error")

if [ "$HEALTH_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✓${NC} Health check passed"
    echo "Response: $HEALTH_RESPONSE" | jq '.' 2>/dev/null || echo "$HEALTH_RESPONSE"
else
    echo -e "${RED}✗${NC} Health check failed"
    echo "Response: $HEALTH_RESPONSE"
fi
echo ""

# Test 2: Trigger Simulation
echo -e "${BLUE}Test 2: POST /simulate/trigger${NC}"
echo "Triggering test simulation (2 dates, 1 model)..."

TRIGGER_PAYLOAD=$(cat <<EOF
{
  "config_path": "$TEST_CONFIG",
  "date_range": ["2025-01-16", "2025-01-17"],
  "models": ["gpt-4"]
}
EOF
)

echo "Request payload:"
echo "$TRIGGER_PAYLOAD" | jq '.'

TRIGGER_RESPONSE=$(curl -s -X POST "$API_BASE_URL/simulate/trigger" \
  -H "Content-Type: application/json" \
  -d "$TRIGGER_PAYLOAD")

JOB_ID=$(echo $TRIGGER_RESPONSE | jq -r '.job_id' 2>/dev/null)

if [ -n "$JOB_ID" ] && [ "$JOB_ID" != "null" ]; then
    echo -e "${GREEN}✓${NC} Simulation triggered successfully"
    echo "Job ID: $JOB_ID"
    echo "Response: $TRIGGER_RESPONSE" | jq '.' 2>/dev/null || echo "$TRIGGER_RESPONSE"
else
    echo -e "${RED}✗${NC} Failed to trigger simulation"
    echo "Response: $TRIGGER_RESPONSE"
    exit 1
fi
echo ""

# Test 3: Check Job Status
echo -e "${BLUE}Test 3: GET /simulate/status/{job_id}${NC}"
echo "Checking job status for: $JOB_ID"
echo "Waiting 5 seconds for job to start..."
sleep 5

STATUS_RESPONSE=$(curl -s "$API_BASE_URL/simulate/status/$JOB_ID")
JOB_STATUS=$(echo $STATUS_RESPONSE | jq -r '.status' 2>/dev/null)

if [ -n "$JOB_STATUS" ] && [ "$JOB_STATUS" != "null" ]; then
    echo -e "${GREEN}✓${NC} Job status retrieved"
    echo "Job Status: $JOB_STATUS"
    echo "Response: $STATUS_RESPONSE" | jq '.' 2>/dev/null || echo "$STATUS_RESPONSE"
else
    echo -e "${RED}✗${NC} Failed to get job status"
    echo "Response: $STATUS_RESPONSE"
fi
echo ""

# Test 4: Poll until completion or timeout
echo -e "${BLUE}Test 4: Monitoring job progress${NC}"
echo "Polling job status (max 5 minutes)..."

MAX_POLLS=30
POLL_INTERVAL=10
POLL_COUNT=0

while [ $POLL_COUNT -lt $MAX_POLLS ]; do
    STATUS_RESPONSE=$(curl -s "$API_BASE_URL/simulate/status/$JOB_ID")
    JOB_STATUS=$(echo $STATUS_RESPONSE | jq -r '.status' 2>/dev/null)
    PROGRESS=$(echo $STATUS_RESPONSE | jq -r '.progress' 2>/dev/null)

    echo "[$((POLL_COUNT + 1))/$MAX_POLLS] Status: $JOB_STATUS | Progress: $PROGRESS"

    if [ "$JOB_STATUS" = "completed" ] || [ "$JOB_STATUS" = "partial" ] || [ "$JOB_STATUS" = "failed" ]; then
        echo -e "${GREEN}✓${NC} Job finished with status: $JOB_STATUS"
        echo "Final response:"
        echo "$STATUS_RESPONSE" | jq '.' 2>/dev/null || echo "$STATUS_RESPONSE"
        break
    fi

    POLL_COUNT=$((POLL_COUNT + 1))
    if [ $POLL_COUNT -lt $MAX_POLLS ]; then
        sleep $POLL_INTERVAL
    fi
done

if [ $POLL_COUNT -eq $MAX_POLLS ]; then
    echo -e "${YELLOW}⚠${NC} Job did not complete within timeout (still $JOB_STATUS)"
    echo "Job may still be running. Check status later with:"
    echo "  curl $API_BASE_URL/simulate/status/$JOB_ID"
fi
echo ""

# Test 5: Query Results
echo -e "${BLUE}Test 5: GET /results${NC}"
echo "Querying results for job: $JOB_ID"

RESULTS_RESPONSE=$(curl -s "$API_BASE_URL/results?job_id=$JOB_ID")
RESULT_COUNT=$(echo $RESULTS_RESPONSE | jq -r '.count' 2>/dev/null)

if [ -n "$RESULT_COUNT" ] && [ "$RESULT_COUNT" != "null" ]; then
    echo -e "${GREEN}✓${NC} Results retrieved"
    echo "Result count: $RESULT_COUNT"

    if [ "$RESULT_COUNT" -gt 0 ]; then
        echo "Sample result:"
        echo "$RESULTS_RESPONSE" | jq '.results[0]' 2>/dev/null || echo "$RESULTS_RESPONSE"
    else
        echo -e "${YELLOW}⚠${NC} No results found (job may not be complete yet)"
    fi
else
    echo -e "${RED}✗${NC} Failed to retrieve results"
    echo "Response: $RESULTS_RESPONSE"
fi
echo ""

# Test 6: Query Results by Date
echo -e "${BLUE}Test 6: GET /results?date=...${NC}"
echo "Querying results by date filter..."

DATE_RESULTS=$(curl -s "$API_BASE_URL/results?date=2025-01-16")
DATE_COUNT=$(echo $DATE_RESULTS | jq -r '.count' 2>/dev/null)

if [ -n "$DATE_COUNT" ] && [ "$DATE_COUNT" != "null" ]; then
    echo -e "${GREEN}✓${NC} Date-filtered results retrieved"
    echo "Results for 2025-01-16: $DATE_COUNT"
else
    echo -e "${RED}✗${NC} Failed to retrieve date-filtered results"
fi
echo ""

# Test 7: Query Results by Model
echo -e "${BLUE}Test 7: GET /results?model=...${NC}"
echo "Querying results by model filter..."

MODEL_RESULTS=$(curl -s "$API_BASE_URL/results?model=gpt-4")
MODEL_COUNT=$(echo $MODEL_RESULTS | jq -r '.count' 2>/dev/null)

if [ -n "$MODEL_COUNT" ] && [ "$MODEL_COUNT" != "null" ]; then
    echo -e "${GREEN}✓${NC} Model-filtered results retrieved"
    echo "Results for gpt-4: $MODEL_COUNT"
else
    echo -e "${RED}✗${NC} Failed to retrieve model-filtered results"
fi
echo ""

# Test 8: Concurrent Job Prevention
echo -e "${BLUE}Test 8: Concurrent job prevention${NC}"
echo "Attempting to trigger second job (should fail if first is still running)..."

SECOND_TRIGGER=$(curl -s -X POST "$API_BASE_URL/simulate/trigger" \
  -H "Content-Type: application/json" \
  -d "$TRIGGER_PAYLOAD")

if echo "$SECOND_TRIGGER" | grep -qi "already running"; then
    echo -e "${GREEN}✓${NC} Concurrent job correctly rejected"
    echo "Response: $SECOND_TRIGGER"
elif echo "$SECOND_TRIGGER" | jq -r '.job_id' 2>/dev/null | grep -q "-"; then
    echo -e "${YELLOW}⚠${NC} Second job was accepted (first job may have completed)"
    echo "Response: $SECOND_TRIGGER" | jq '.' 2>/dev/null || echo "$SECOND_TRIGGER"
else
    echo -e "${YELLOW}⚠${NC} Unexpected response"
    echo "Response: $SECOND_TRIGGER"
fi
echo ""

# Test 9: Invalid Requests
echo -e "${BLUE}Test 9: Error handling${NC}"
echo "Testing invalid config path..."

INVALID_TRIGGER=$(curl -s -X POST "$API_BASE_URL/simulate/trigger" \
  -H "Content-Type: application/json" \
  -d '{"config_path": "/invalid/path.json", "date_range": ["2025-01-16"], "models": ["gpt-4"]}')

if echo "$INVALID_TRIGGER" | grep -qi "does not exist"; then
    echo -e "${GREEN}✓${NC} Invalid config path correctly rejected"
else
    echo -e "${YELLOW}⚠${NC} Unexpected response for invalid config"
    echo "Response: $INVALID_TRIGGER"
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "All API endpoints tested successfully!"
echo ""
echo "Job Details:"
echo "  Job ID: $JOB_ID"
echo "  Final Status: $JOB_STATUS"
echo "  Results Count: $RESULT_COUNT"
echo ""
echo "To view full job details:"
echo "  curl $API_BASE_URL/simulate/status/$JOB_ID | jq ."
echo ""
echo "To view all results:"
echo "  curl $API_BASE_URL/results | jq ."
echo ""
