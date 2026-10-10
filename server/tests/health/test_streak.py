"""Pure-function tests for streak counting (spec 4.3 TOD-5).

Acceptance criteria:
- Consecutive days with a `daily_log`.
- Shown as a Sticker Book badge from 3 days.
- Wiggles on day 3, 7, 14, 30.
- Handles timezone boundaries and ongoing today preservation.
"""

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from app.health.streak import compute_streak, is_streak_milestone, today_in_timezone


@pytest.mark.req("TOD-5")
def test_streak_empty_logs() -> None:
    today = date(2026, 10, 8)
    assert compute_streak(set(), today) == 0


@pytest.mark.req("TOD-5")
def test_streak_logged_today_single_day() -> None:
    today = date(2026, 10, 8)
    logged = {today}
    assert compute_streak(logged, today) == 1


@pytest.mark.req("TOD-5")
def test_streak_unlogged_today_preserves_ongoing_streak() -> None:
    """When today is in progress and not yet logged, yesterday's streak continues."""
    today = date(2026, 10, 8)
    # Logged yesterday and the day before, but not today
    logged = {date(2026, 10, 7), date(2026, 10, 6)}
    assert compute_streak(logged, today) == 2


@pytest.mark.req("TOD-5")
def test_streak_logged_today_extends_streak() -> None:
    """Checking in today extends the consecutive count."""
    today = date(2026, 10, 8)
    logged = {date(2026, 10, 8), date(2026, 10, 7), date(2026, 10, 6)}
    assert compute_streak(logged, today) == 3


@pytest.mark.req("TOD-5")
def test_streak_broken_when_yesterday_missed() -> None:
    """When yesterday is missing, streak is 0 if today is also not logged."""
    today = date(2026, 10, 8)
    # Logged 2 days ago, but missed yesterday and today
    logged = {date(2026, 10, 6), date(2026, 10, 5)}
    assert compute_streak(logged, today) == 0


@pytest.mark.req("TOD-5")
def test_streak_restarts_at_1_when_yesterday_missed_but_today_logged() -> None:
    today = date(2026, 10, 8)
    # Logged today, missed yesterday, logged 2 days ago
    logged = {date(2026, 10, 8), date(2026, 10, 6)}
    assert compute_streak(logged, today) == 1


@pytest.mark.req("TOD-5")
def test_streak_past_date_when_not_today() -> None:
    """For a completed historical date, streak counts consecutive days ending on that date."""
    target_date = date(2026, 10, 5)
    logged = {date(2026, 10, 5), date(2026, 10, 4), date(2026, 10, 3)}
    assert compute_streak(logged, target_date, is_today=False) == 3

    # If the historical date was not logged, streak on that day was 0
    assert compute_streak(logged, date(2026, 10, 6), is_today=False) == 0


@pytest.mark.req("TOD-5")
def test_streak_across_timezones_and_day_boundaries() -> None:
    """Demonstrate streak consistency when user is across different timezones."""
    # 2026-10-08 at 23:30 UTC
    # In Europe/London (BST = UTC+1): 2026-10-09 00:30 (today is 2026-10-09)
    # In America/New_York (EDT = UTC-4): 2026-10-08 19:30 (today is 2026-10-08)
    # In Asia/Tokyo (JST = UTC+9): 2026-10-09 08:30 (today is 2026-10-09)
    from datetime import datetime

    moment = datetime(2026, 10, 8, 23, 30, tzinfo=ZoneInfo("UTC"))
    today_london = today_in_timezone(moment, "Europe/London")
    today_ny = today_in_timezone(moment, "America/New_York")
    today_tokyo = today_in_timezone(moment, "Asia/Tokyo")

    assert today_london == date(2026, 10, 9)
    assert today_ny == date(2026, 10, 8)
    assert today_tokyo == date(2026, 10, 9)

    # Suppose user logged on 2026-10-07 and 2026-10-08
    logged = {date(2026, 10, 7), date(2026, 10, 8)}

    # In New York, today (Oct 8) has a log, so streak is 2
    assert compute_streak(logged, today_ny) == 2

    # In London / Tokyo, today (Oct 9) has no log yet, but yesterday (Oct 8) does:
    # streak is preserved at 2!
    assert compute_streak(logged, today_london) == 2
    assert compute_streak(logged, today_tokyo) == 2


@pytest.mark.req("TOD-5")
def test_streak_milestones() -> None:
    """Milestones that trigger wiggles per spec 5.6: 3, 7, 14, 30."""
    assert is_streak_milestone(3) is True
    assert is_streak_milestone(7) is True
    assert is_streak_milestone(14) is True
    assert is_streak_milestone(30) is True
    assert is_streak_milestone(1) is False
    assert is_streak_milestone(2) is False
    assert is_streak_milestone(4) is False
    assert is_streak_milestone(5) is False
    assert is_streak_milestone(10) is False
