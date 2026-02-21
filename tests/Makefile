# Makefile for Docker-based testing
# This Makefile should be in the tests/ directory

.PHONY: help build test test-unit test-live test-all test-shell clean

# Default target
help:
	@echo "Greek Courier Tracker - Docker Testing"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  build          Build test Docker images"
	@echo "  test           Run ALL tests (unit + integration + live API)"
	@echo "  test-unit      Run unit and integration tests only (no live API)"
	@echo "  test-live      Run live API tests only (requires network)"
	@echo "  test-all       Run tests on all Python versions"
	@echo "  test-shell     Open interactive shell in test container"
	@echo "  test-cov       Run tests with HTML coverage report"
	@echo "  clean          Remove Docker images and containers"
	@echo "  rebuild        Rebuild Docker images from scratch"
	@echo ""

# Get the directory where this Makefile is located
TESTS_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
PROJECT_ROOT := $(shell dirname $(TESTS_DIR))

# Build Docker images (build context is project root)
build:
	@echo "Building test Docker images..."
	@echo "Project root: $(PROJECT_ROOT)"
	@echo "Tests dir: $(TESTS_DIR)"
	docker build -f Dockerfile.test -t greek-courier-tracker-test:latest $(PROJECT_ROOT)
	@echo "✓ Build complete"

# Run ALL tests (default)
test: build
	@echo "Running ALL tests in Docker..."
	docker run --rm \
		-v "$(PROJECT_ROOT)/custom_components:/app/custom_components:ro" \
		-v "$(TESTS_DIR):/app/tests:ro" \
		-v "$(TESTS_DIR)/pytest.ini:/app/pytest.ini:ro" \
		-e PYTHONPATH=/app \
		greek-courier-tracker-test:latest || true
	@echo "Cleaning up test containers..."
	@docker ps -a --filter "name=gct-test" --format "{{.Names}}" 2>/dev/null | xargs -r docker rm -f 2>/dev/null || true

# Run unit and integration tests only (no live API)
test-unit: build
	@echo "Running unit and integration tests (no live API)..."
	docker run --rm \
		-v "$(PROJECT_ROOT)/custom_components:/app/custom_components:ro" \
		-v "$(TESTS_DIR):/app/tests:ro" \
		-v "$(TESTS_DIR)/pytest.ini:/app/pytest.ini:ro" \
		-e PYTHONPATH=/app \
		greek-courier-tracker-test:latest \
		-m "not live" || true
	@echo "Cleaning up test containers..."
	@docker ps -a --filter "name=gct-test" --format "{{.Names}}" 2>/dev/null | xargs -r docker rm -f 2>/dev/null || true

# Run only live API tests
test-live: build
	@echo "Running live API tests only..."
	docker run --rm \
		-v "$(PROJECT_ROOT)/custom_components:/app/custom_components:ro" \
		-v "$(TESTS_DIR):/app/tests:ro" \
		-v "$(TESTS_DIR)/pytest.ini:/app/pytest.ini:ro" \
		-e PYTHONPATH=/app \
		greek-courier-tracker-test:latest \
		-m "live" || true
	@echo "Cleaning up test containers..."
	@docker ps -a --filter "name=gct-test" --format "{{.Names}}" 2>/dev/null | xargs -r docker rm -f 2>/dev/null || true

# Run tests on all Python versions
test-all:
	@echo "Running tests on all Python versions..."
	@echo ""
	@echo "=== Python 3.12 (GHCR) ==="
	docker run --rm \
		-v "$(PROJECT_ROOT)/custom_components:/app/custom_components:ro" \
		-v "$(TESTS_DIR):/app/tests:ro" \
		-v "$(TESTS_DIR)/pytest.ini:/app/pytest.ini:ro" \
		ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.19 \
		sh -c "pip install -q pytest pytest-asyncio pytest-cov beautifulsoup4 aiohttp async-timeout && cd /app && pytest tests/ -v --tb=short" || true
	@echo "Cleaning up test containers..."
	@docker ps -a --filter "name=gct-test" --format "{{.Names}}" 2>/dev/null | xargs -r docker rm -f 2>/dev/null || true

# Run tests with coverage
test-cov: build
	@echo "Running tests with coverage..."
	@mkdir -p htmlcov
	docker run --rm \
		-v "$(PROJECT_ROOT)/custom_components:/app/custom_components:ro" \
		-v "$(TESTS_DIR):/app/tests:ro" \
		-v "$(TESTS_DIR)/pytest.ini:/app/pytest.ini:ro" \
		-v "$(TESTS_DIR)/htmlcov:/app/htmlcov" \
		-e PYTHONPATH=/app \
		greek-courier-tracker-test:latest \
		--cov=custom_components/greek_courier_tracker --cov-report=html --cov-report=term || true
	@echo "Cleaning up test containers..."
	@docker ps -a --filter "name=gct-test" --format "{{.Names}}" 2>/dev/null | xargs -r docker rm -f 2>/dev/null || true
	@echo "✓ Coverage report generated in htmlcov/"

# Open interactive shell
test-shell: build
	@echo "Opening interactive test shell..."
	docker run --rm -it \
		-v "$(PROJECT_ROOT)/custom_components:/app/custom_components:ro" \
		-v "$(TESTS_DIR):/app/tests:ro" \
		-v "$(TESTS_DIR)/pytest.ini:/app/pytest.ini:ro" \
		-e PYTHONPATH=/app \
		greek-courier-tracker-test:latest \
		/bin/sh

# Clean up
clean:
	@echo "Cleaning up Docker resources..."
	-docker rm -f gct-test-py310 2>/dev/null || true
	-docker rm -f gct-test-py311 2>/dev/null || true
	-docker rm -f gct-test-py312 2>/dev/null || true
	-docker rm -f gct-test-shell 2>/dev/null || true
	-docker rmi greek-courier-tracker-test:3.10 2>/dev/null || true
	-docker rmi greek-courier-tracker-test:3.11 2>/dev/null || true
	-docker rmi greek-courier-tracker-test:3.12 2>/dev/null || true
	-docker rmi greek-courier-tracker-test:latest 2>/dev/null || true
	@echo "✓ Cleanup complete"

# Rebuild from scratch
rebuild: clean build
	@echo "✓ Rebuild complete"
