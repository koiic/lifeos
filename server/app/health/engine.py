"""Cycle engine pure algorithms: flow classification, bleed episodes, and cycle rules.

Spec sections: 8.1, 8.2; PER-4, PER-5; TV6, TV9, TV10.
Pure functions only: no database, no network, completely deterministic.
"""

from dataclasses import dataclass, replace
from datetime import date
from typing import Any


def is_flow_day(flow: str | None) -> bool:
    """Spec 8.1: A flow day is light, medium or heavy. Spotting is stored but never counts."""
    return flow in ("light", "medium", "heavy")


@dataclass(frozen=True)
class BleedEpisode:
    """Spec 8.1: A run of flow days where gaps between consecutive flow days are at most 2 days."""

    start_date: date
    end_date: date
    flow_dates: tuple[date, ...] = ()
    is_period_start: bool = False
    is_intra_cycle: bool = False

    @property
    def length_days(self) -> int:
        """Period length: last flow day of the episode - start + 1."""
        return (self.end_date - self.start_date).days + 1

    @property
    def needs_confirmation(self) -> bool:
        """PER-4: If > 10 days of flow, prompt to confirm."""
        return self.length_days > 10

    def is_closed(self, today: date) -> bool:
        """PER-4: Open period with no flow for 3 consecutive days is treated as ended."""
        return (today - self.end_date).days >= 3


def find_bleed_episodes(
    flow_by_date: dict[date, Any] | list[tuple[date, Any]],
) -> list[BleedEpisode]:
    """Group flow days into bleed episodes.

    Spec 8.1: A run of flow days where gaps between consecutive flow days are at most 2 days.
    Spotting and non-flow days are ignored.
    """
    items = flow_by_date.items() if isinstance(flow_by_date, dict) else flow_by_date

    flow_dates = sorted({d for d, f in items if is_flow_day(str(f) if f is not None else None)})
    if not flow_dates:
        return []

    episodes: list[BleedEpisode] = []
    current_run: list[date] = [flow_dates[0]]

    for d in flow_dates[1:]:
        # Gap <= 2 dry days between consecutive flow days: (d - prev).days <= 3
        if (d - current_run[-1]).days <= 3:
            current_run.append(d)
        else:
            episodes.append(
                BleedEpisode(
                    start_date=current_run[0],
                    end_date=current_run[-1],
                    flow_dates=tuple(current_run),
                )
            )
            current_run = [d]

    episodes.append(
        BleedEpisode(
            start_date=current_run[0],
            end_date=current_run[-1],
            flow_dates=tuple(current_run),
        )
    )
    return episodes


def classify_episodes(
    episodes: list[BleedEpisode],
    forced_period_starts: set[date] | None = None,
) -> list[BleedEpisode]:
    """Classify bleed episodes into period starts vs intra-cycle bleeds.

    Spec 8.1:
    - Period start: the first day of a bleed episode that begins at least 15 days after
      the previous period start, or any date in health_profile.forced_period_starts.
    - An episode starting sooner is an intra-cycle bleed.
    """
    forced = forced_period_starts or set()
    classified: list[BleedEpisode] = []
    last_period_start: date | None = None

    for ep in episodes:
        is_start = (
            last_period_start is None
            or ep.start_date in forced
            or (ep.start_date - last_period_start).days >= 15
        )

        if is_start:
            last_period_start = ep.start_date

        classified.append(
            replace(
                ep,
                is_period_start=is_start,
                is_intra_cycle=not is_start,
            )
        )

    return classified


def check_auto_close(episode: BleedEpisode, today: date) -> bool:
    """PER-4: Open period with no flow for 3 consecutive days is treated as ended."""
    return (today - episode.end_date).days >= 3


def needs_length_confirmation(episode: BleedEpisode) -> bool:
    """PER-4: If > 10 days of flow, prompt to confirm."""
    return episode.length_days > 10
