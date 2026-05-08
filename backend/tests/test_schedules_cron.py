"""Cron validation used by user schedules."""

import pytest

pytest.importorskip("croniter")

from croniter import croniter  # noqa: E402
from datetime import datetime  # noqa: E402


def test_croniter_next_smoke():
    base = datetime(2026, 1, 1, 12, 0, 0)
    it = croniter("0 * * * *", base)
    n = it.get_next(datetime)
    assert n > base
