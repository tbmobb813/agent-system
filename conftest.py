"""Pytest hooks when running from the repo root (see pytest.ini).

Using the system `pytest` without the backend venv leads to missing `fastapi`,
`asyncpg`, etc. Fail fast with a concrete fix instead of sixteen import errors.
"""

from __future__ import annotations

import sys
import pytest

def pytest_configure(config: pytest.Config) -> None:
    try:
        import fastapi  # noqa: F401
    except ImportError:
        hint = (
            "This repo's tests need the backend virtualenv (not system Python).\n\n"
            "  backend/.venv/bin/pytest\n\n"
            "or:\n\n"
            "  cd backend && source .venv/bin/activate && cd .. && pytest\n\n"
            "Create the venv if needed:\n\n"
            "  cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt\n"
        )
        hint += f"\nCurrent interpreter: {sys.executable}\n"
        pytest.exit(hint, returncode=1)
