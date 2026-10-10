"""health: Streak calculation (TOD-5).

Pure domain logic (plan 4.2).
"Consecutive days with a daily_log; shown as a Sticker Book badge from 3 days"
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

STREAK_MILESTONES = frozenset({3, 7, 14, 30})


def today_in_timezone(moment: datetime, timezone_name: str) -> date:
    """Determine the calendar date for `moment` in `timezone_name`."""
    return moment.astimezone(ZoneInfo(timezone_name)).date()


def compute_streak(logged_dates: set[date], target_date: date, is_today: bool = True) -> int:
    """Calculate consecutive daily log streak up to `target_date`.

    If `is_today` is True:
      - If `target_date` is logged, count consecutive days backward from `target_date`.
      - If `target_date` is NOT yet logged:
        If yesterday is logged, count consecutive days backward from yesterday
        (today is still ongoing, preserving the active streak).
        If yesterday is NOT logged, streak is 0.
    If `is_today` is False:
      - Historical day: if `target_date` is in `logged_dates`, count consecutive days
        backward from `target_date`. Otherwise 0.
    """
    if target_date in logged_dates:
        start_date = target_date
    elif is_today and (target_date - timedelta(days=1)) in logged_dates:
        start_date = target_date - timedelta(days=1)
    else:
        return 0

    streak = 0
    curr = start_date
    while curr in logged_dates:
        streak += 1
        curr -= timedelta(days=1)

    return streak


def is_streak_milestone(streak: int) -> bool:
    """Spec 5.6: Streak badge wiggles on day 3, 7, 14, 30."""
    return streak in STREAK_MILESTONES
