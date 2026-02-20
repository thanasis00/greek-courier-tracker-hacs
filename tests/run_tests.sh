#!/bin/bash

# Script to run tests for Greek Courier Tracker

set -e

echo "================================"
echo "Greek Courier Tracker Test Suite"
echo "================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -q -r requirements_tests.txt

# Run tests
echo ""
echo -e "${GREEN}Running tests...${NC}"
echo ""

# Run unit tests first
echo "Running unit tests..."
pytest tests/ -v --tb=short -m "not integration" || true

echo ""
echo "Running all tests (including integration)..."
pytest tests/ -v --tb=short --cov=custom_components/greek_courier_tracker --cov-report=term-missing

echo ""
echo -e "${GREEN}Tests completed!${NC}"
