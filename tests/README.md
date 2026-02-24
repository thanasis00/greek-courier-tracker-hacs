# Tests

Test suite for Greek Courier Tracker Home Assistant integration.

## Running Tests

All tests run in Docker containers - no local Python installation required.

### Quick Start
```bash
cd tests && make test
```

### Available Make Targets

```bash
make test          # Run ALL tests (unit + integration + live API)
make test-unit     # Run unit and integration tests only (no live API)
make test-live     # Run live API tests only (requires network)
make test-cov      # Run with coverage report
make test-shell    # Open interactive shell in container
make clean         # Clean Docker resources
make rebuild       # Rebuild Docker images from scratch
```

### Using Script
```bash
cd tests
./docker-test.sh              # Run tests
./docker-test.sh --cov        # With coverage
./docker-test.sh --shell      # Interactive shell
./docker-test.sh --help       # Show all options
```

## Test Files

### Unit Tests (No Network Required)
- `test_tracking_detection.py` - Tracking number format detection
- `test_couriers_simple.py` - Courier properties and status translation
- `test_mocked_apis.py` - Mocked API response tests for all couriers

### Integration Tests
- `test_integration.py` - Home Assistant integration tests (config flow, coordinator, sensors)

### Live API Tests (Network Required)
- `test_live_apis.py` - Live API calls to courier services
- `test_standalone.py` - Standalone script with live API tests

**Note:** Live API tests require network access and may fail without valid tracking numbers or if courier APIs are down.

## Test Coverage

✅ **84 tests** covering:
- All 6 couriers (ELTA, ACS, SpeedEx, BoxNow, Geniki, CourierCenter)
- Tracking number detection and validation
- Status translation and categorization
- Home Assistant config flow, coordinator, and sensors
- Mocked API responses for reliability
- Live API tests for real-world validation

## Test Markers

Tests are organized with pytest markers:
- `unit` - Fast unit tests without external dependencies
- `integration` - Integration tests with Home Assistant components
- `live` - Tests making actual HTTP requests to courier APIs

## Docker Images

Uses `ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.19` - no rate limits.

## GitHub Actions

The test suite runs automatically on:
- Push to `main` or `dev` branches
- Pull requests to `main` or `dev` branches
- Manual workflow dispatch

CI runs tests on Python 3.10, 3.11, and 3.12 using both local pytest and Docker containers.
