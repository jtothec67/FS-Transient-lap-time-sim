"""Session-wide pytest fixtures shared across all test modules."""
import os
import pytest

# Disable rate limiting during tests so endpoint calls from different test files
# do not consume each other's per-minute budgets. The rate_limiting tests use
# a fresh Limiter instance with rate limiting explicitly enabled so they still
# verify the correct behaviour.
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")
