"""Health tests that need a registered user use the auth harness."""

from tests.auth.conftest import env

__all__ = ["env"]
