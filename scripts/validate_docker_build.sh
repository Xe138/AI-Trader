#!/bin/bash
# Docker Build & Validation Script
# Run this script to validate the Docker setup before production deployment

set -e  # Exit on error

echo "=========================================="
echo "AI-Trader Docker Build Validation"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Step 1: Check prerequisites
echo "Step 1: Checking prerequisites..."

# Check if Docker is installed
if command -v docker &> /dev/null; then
    print_status 0 "Docker is installed: $(docker --version)"
else
    print_status 1 "Docker is not installed"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker daemon is running
if docker info &> /dev/null; then
    print_status 0 "Docker daemon is running"
else
    print_status 1 "Docker daemon is not running"
    echo "Please start Docker Desktop or Docker daemon"
    exit 1
fi

# Check if docker-compose is available
if command -v docker-compose &> /dev/null; then
    print_status 0 "docker-compose is installed: $(docker-compose --version)"
elif docker compose version &> /dev/null; then
    print_status 0 "docker compose (plugin) is available"
    COMPOSE_CMD="docker compose"
else
    print_status 1 "docker-compose is not available"
    exit 1
fi

# Default to docker-compose if not set
COMPOSE_CMD=${COMPOSE_CMD:-docker-compose}

echo ""

# Step 2: Check environment file
echo "Step 2: Checking environment configuration..."

if [ -f .env ]; then
    print_status 0 ".env file exists"

    # Check required variables
    required_vars=("OPENAI_API_KEY" "ALPHAADVANTAGE_API_KEY" "JINA_API_KEY")
    missing_vars=()

    for var in "${required_vars[@]}"; do
        if grep -q "^${var}=" .env && ! grep -q "^${var}=your_.*_key_here" .env && ! grep -q "^${var}=$" .env; then
            print_status 0 "$var is set"
        else
            missing_vars+=("$var")
            print_status 1 "$var is missing or not configured"
        fi
    done

    if [ ${#missing_vars[@]} -gt 0 ]; then
        print_warning "Some required environment variables are not configured"
        echo "Please edit .env and add:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        echo ""
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
else
    print_status 1 ".env file not found"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    print_warning "Please edit .env and add your API keys before continuing"
    exit 1
fi

echo ""

# Step 3: Build Docker image
echo "Step 3: Building Docker image..."
echo "This may take several minutes on first build..."
echo ""

if docker build -t ai-trader-test . ; then
    print_status 0 "Docker image built successfully"
else
    print_status 1 "Docker build failed"
    exit 1
fi

echo ""

# Step 4: Check image
echo "Step 4: Verifying Docker image..."

IMAGE_SIZE=$(docker images ai-trader-test --format "{{.Size}}")
print_status 0 "Image size: $IMAGE_SIZE"

# List exposed ports
EXPOSED_PORTS=$(docker inspect ai-trader-test --format '{{range $p, $conf := .Config.ExposedPorts}}{{$p}} {{end}}')
print_status 0 "Exposed ports: $EXPOSED_PORTS"

echo ""

# Step 5: Test API mode startup (brief)
echo "Step 5: Testing API mode startup..."
echo "Starting container in background..."

$COMPOSE_CMD up -d ai-trader

if [ $? -eq 0 ]; then
    print_status 0 "Container started successfully"

    echo "Waiting 10 seconds for services to initialize..."
    sleep 10

    # Check if container is still running
    if docker ps | grep -q ai-trader; then
        print_status 0 "Container is running"

        # Check logs for errors
        ERROR_COUNT=$(docker logs ai-trader 2>&1 | grep -i "error" | grep -v "ERROR:" | wc -l)
        if [ $ERROR_COUNT -gt 0 ]; then
            print_warning "Found $ERROR_COUNT error messages in logs"
            echo "Check logs with: docker logs ai-trader"
        else
            print_status 0 "No critical errors in logs"
        fi
    else
        print_status 1 "Container stopped unexpectedly"
        echo "Check logs with: docker logs ai-trader"
        exit 1
    fi
else
    print_status 1 "Failed to start container"
    exit 1
fi

echo ""

# Step 6: Test health endpoint
echo "Step 6: Testing health endpoint..."

# Wait for API to be ready with retries
echo "Waiting for API to be ready (up to 30 seconds)..."
MAX_RETRIES=15
RETRY_COUNT=0
API_READY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f -s http://localhost:8080/health &> /dev/null; then
        API_READY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Attempt $RETRY_COUNT/$MAX_RETRIES..."
    sleep 2
done

if [ "$API_READY" = true ]; then
    print_status 0 "Health endpoint responding"

    # Get health details
    HEALTH_DATA=$(curl -s http://localhost:8080/health)
    echo "Health response: $HEALTH_DATA"
else
    print_status 1 "Health endpoint not responding after $MAX_RETRIES attempts"
    print_warning "Diagnostics:"

    # Check if container is still running
    if docker ps | grep -q ai-trader; then
        echo "  ✓ Container is running"
    else
        echo "  ✗ Container has stopped"
    fi

    # Check if port is listening
    if docker exec ai-trader netstat -tuln 2>/dev/null | grep -q ":8080"; then
        echo "  ✓ Port 8080 is listening inside container"
    else
        echo "  ✗ Port 8080 is NOT listening inside container"
    fi

    # Try curl from inside container
    echo "  Testing from inside container..."
    INTERNAL_TEST=$(docker exec ai-trader curl -f -s http://localhost:8080/health 2>&1)
    if [ $? -eq 0 ]; then
        echo "  ✓ Health endpoint works inside container: $INTERNAL_TEST"
        echo "  ✗ Issue is with port mapping or host networking"
    else
        echo "  ✗ Health endpoint doesn't work inside container: $INTERNAL_TEST"
        echo "  ✗ API server may not have started correctly"
    fi

    echo ""
    echo "Recent logs:"
    docker logs ai-trader 2>&1 | tail -20
fi

echo ""

# Step 7: Cleanup
echo "Step 7: Cleanup..."
read -p "Stop the container? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    $COMPOSE_CMD down
    print_status 0 "Container stopped"
fi

echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. If all checks passed, proceed with API endpoint testing:"
echo "   bash scripts/test_api_endpoints.sh"
echo ""
echo "2. Test batch mode:"
echo "   bash scripts/test_batch_mode.sh"
echo ""
echo "3. If any checks failed, review logs:"
echo "   docker logs ai-trader"
echo ""
echo "4. For troubleshooting, see: DOCKER_API.md"
echo ""
