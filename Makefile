# Makefile for Greek Courier Tracker
# Main entry point - delegates to tests/Makefile

.PHONY: help test test-all test-cov test-shell clean rebuild

# Default target - show help
help:
	@echo "Greek Courier Tracker"
	@echo ""
	@echo "Testing Commands:"
	@echo "  make test       Run tests in Docker"
	@echo "  make test-all   Test on all Python versions"
	@echo "  make test-cov   Run with coverage"
	@echo "  make test-shell Open interactive shell"
	@echo "  make clean      Clean Docker resources"
	@echo "  make rebuild    Rebuild Docker images"
	@echo ""
	@echo "For more options, see tests/README.md"

# Delegate all test commands to tests/Makefile
test test-all test-cov test-shell clean rebuild:
	$(MAKE) -C tests $(MAKECMDGOALS)
