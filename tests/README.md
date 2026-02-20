# Tests

Test suite for Greek Courier Tracker Home Assistant integration.

## Running Tests

### Quick Start (Docker - Recommended)
```bash
# From project root
make test

# Or from tests/ directory
cd tests && make test
```

### Options
```bash
make test-cov       # Run with coverage report
make test-shell     # Open interactive shell in container
make clean          # Clean Docker resources
make rebuild        # Rebuild Docker images from scratch
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

- `test_tracking_detection.py` - Tracking number format detection
- `test_couriers_simple.py` - Courier properties and status translation
- `test_integration.py` - Home Assistant integration tests
- `test_standalone.py` - Standalone API tests

## Test Coverage

✅ 63 tests covering:
- All 6 couriers (ELTA, ACS, SpeedEx, BoxNow, Geniki, CourierCenter)
- Tracking number detection and validation
- Status translation and categorization
- Home Assistant config flow, coordinator, and sensors

## Docker Images

Uses `ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.19` - no rate limits.
