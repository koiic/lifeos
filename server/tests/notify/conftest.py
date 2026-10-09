"""Notify API tests use the auth harness (a real app, database and signed-in users)."""

from tests.auth.conftest import env

__all__ = ["env"]
