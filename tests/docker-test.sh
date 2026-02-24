#!/bin/bash

# Script to run tests in Docker container
# This script should be run from the tests/ directory

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================"
echo "Greek Courier Tracker - Docker Tests"
echo "================================${NC}"
echo ""

# Get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$SCRIPT_DIR"

# Track containers for cleanup
CONTAINERS_TO_CLEAN=""

# Cleanup function
cleanup() {
    local exit_code=$?
    if [ -n "$CONTAINERS_TO_CLEAN" ]; then
        echo -e "${YELLOW}Cleaning up containers...${NC}"
        for container in $CONTAINERS_TO_CLEAN; do
            docker rm -f "$container" 2>/dev/null || true
        done
    fi
    exit $exit_code
}

# Set trap to ensure cleanup on exit
trap cleanup EXIT INT TERM

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Parse arguments
PYTHON_VERSION="3.12"
COVERAGE=false
SHELL=false
CLEAN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --py310)
            PYTHON_VERSION="3.10"
            shift
            ;;
        --py311)
            PYTHON_VERSION="3.11"
            shift
            ;;
        --py312)
            PYTHON_VERSION="3.12"
            shift
            ;;
        --cov|--coverage)
            COVERAGE=true
            shift
            ;;
        --shell)
            SHELL=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --py310     Run tests on Python 3.10"
            echo "  --py311     Run tests on Python 3.11"
            echo "  --py312     Run tests on Python 3.12 (default)"
            echo "  --cov       Generate coverage report"
            echo "  --shell     Open interactive shell"
            echo "  --clean     Clean up Docker images first"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Clean if requested
if [ "$CLEAN" = true ]; then
    echo -e "${YELLOW}Cleaning up Docker resources...${NC}"
    docker rm -f gct-test 2>/dev/null || true
    docker rmi greek-courier-tracker-test 2>/dev/null || true
fi

# Build Docker image
echo -e "${YELLOW}Building Docker image (Python $PYTHON_VERSION)...${NC}"
docker build -f Dockerfile.test -t greek-courier-tracker-test:latest . > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to build Docker image${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Run tests
if [ "$SHELL" = true ]; then
    echo -e "${YELLOW}Opening interactive shell...${NC}"
    docker run --rm -it \
        -v "$PROJECT_ROOT/custom_components:/app/custom_components:ro" \
        -v "$(PWD):/app/tests:ro" \
        -v "$(PWD)/pytest.ini:/app/pytest.ini:ro" \
        -e PYTHONPATH=/app \
        greek-courier-tracker-test:latest \
        /bin/sh
elif [ "$COVERAGE" = true ]; then
    echo -e "${YELLOW}Running tests with coverage...${NC}"
    mkdir -p htmlcov
    docker run --rm \
        -v "$PROJECT_ROOT/custom_components:/app/custom_components:ro" \
        -v "$(PWD):/app/tests:ro" \
        -v "$(PWD)/pytest.ini:/app/pytest.ini:ro" \
        -v "$(PWD)/htmlcov:/app/htmlcov" \
        -e PYTHONPATH=/app \
        greek-courier-tracker-test:latest

    echo ""
    echo -e "${GREEN}✓ Coverage report generated in htmlcov/index.html${NC}"
    echo "  Open it in your browser: file://$(PWD)/htmlcov/index.html"
else
    echo -e "${YELLOW}Running tests...${NC}"
    echo ""
    docker run --rm \
        -v "$PROJECT_ROOT/custom_components:/app/custom_components:ro" \
        -v "$(PWD):/app/tests:ro" \
        -v "$(PWD)/pytest.ini:/app/pytest.ini:ro" \
        -e PYTHONPATH=/app \
        greek-courier-tracker-test:latest
fi

echo ""
echo -e "${GREEN}✓ Tests completed!${NC}"
echo ""
echo -e "${YELLOW}Cleaning up any test containers...${NC}"
docker ps -a --filter "name=gct-test" --format "{{.Names}}" | xargs -r docker rm -f 2>/dev/null || true
