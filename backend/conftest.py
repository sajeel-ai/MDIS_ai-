"""Pytest Root Configuration."""

import sys
import os
import pytest
from sqlalchemy.engine import make_url

# Add backend root directory to sys.path so 'import app' resolves cleanly
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def require_disposable_test_database(database_url: str | None = None) -> None:
    """Refuse pytest sessions unless DATABASE_URL names an isolated *_test DB."""
    from app.config import settings

    candidate = database_url or os.getenv("DATABASE_URL") or settings.database_url
    try:
        database_name = make_url(candidate).database or ""
    except Exception as exc:
        raise RuntimeError("Tests require DATABASE_URL to name a disposable *_test database") from exc
    if not database_name.lower().endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against database '{database_name}'; DATABASE_URL must end in _test"
        )


def pytest_sessionstart(session):
    try:
        require_disposable_test_database()
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=4)
