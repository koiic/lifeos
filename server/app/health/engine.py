"""Cycle engine pure algorithms: calendar-1.0.

Spec sections: 8.1-8.4, 8.6; CYC-2, CYC-3, CYC-4, CYC-6; TV1-TV12.
Pure functions only: completely deterministic, no database, no async runtime, no I/O.
"""

import statistics
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ALGO_VERSION = "calendar-1.0"
DEFAULT_SD = 3.0
MAX_HALF_WIDTH = 7


def round_half_up(val: float | Decimal) -> int:
    """Standard arithmetic rounding: half rounds away from zero (spec 8.3)."""
    d = Decimal(str(round(float(val), 9)))
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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


@dataclass(frozen=True)
class CycleEngineProfile:
    """Health profile configuration relevant to cycle computation (spec 8.1-8.3)."""

    last_period_hint: date | None = None
    usual_cycle_length: int | None = None
    usual_period_length: int | None = 5
    mode: str = "cycle_tracking"
    mode_started_on: date | None = None
    forced_period_starts: frozenset[date] = frozenset()
    user_excluded_cycles: frozenset[date] = frozenset()


@dataclass(frozen=True)
class Cycle:
    """Spec 8.1, 8.2: A menstrual cycle from one period start to the day before the next."""

    start_date: date
    end_date: date | None
    period_length_days: int
    length_days: int | None
    is_complete: bool
    is_user_excluded: bool = False
    exclusion_reason: str | None = None

    @property
    def excluded(self) -> bool:
        """True if the cycle is excluded from statistical prediction (spec 8.2)."""
        return self.exclusion_reason is not None


@dataclass(frozen=True)
class Prediction:
    """Spec 8.3: Deterministic prediction of the next menstrual cycle start and fertile window."""

    confidence: str
    suppressed_reason: str | None = None
    predicted_start: date | None = None
    range_low: date | None = None
    range_high: date | None = None
    ovulation_est: date | None = None
    fertile: tuple[date, date] | None = None
    n_cycles: int = 0
    mean_len: float | None = None
    sd_len: float | None = None
    mean_period_len: float | None = None
    algorithm_version: str = ALGO_VERSION


@dataclass(frozen=True)
class DerivedState:
    """Spec 8.4: Derived UI state and cycle phase."""

    state: str
    cycle_day: int | None
    days_late: int | None = None
    days_until: int | None = None
    period_day: int | None = None
    is_irregular: bool = False
    has_long_gap: bool = False
    phase: str | None = None
    message: str = ""


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
    forced_period_starts: set[date] | frozenset[date] | None = None,
) -> list[BleedEpisode]:
    """Classify bleed episodes into period starts vs intra-cycle bleeds.

    Spec 8.1:
    - Period start: the first day of a bleed episode that begins at least 15 days after
      the previous period start, or any date in health_profile.forced_period_starts.
    - An episode starting sooner is an intra-cycle bleed.
    """
    forced = forced_period_starts or frozenset()
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


def build_cycles(
    episodes: list[BleedEpisode],
    profile: CycleEngineProfile,
    logged_dates: set[date] | None = None,
) -> list[Cycle]:
    """Build cycles from bleed episodes and evaluate inclusion/exclusion rules (spec 8.1, 8.2)."""
    period_episodes = [ep for ep in episodes if ep.is_period_start]
    cycles: list[Cycle] = []
    num_starts = len(period_episodes)

    # Pre-sort logged dates for data_gap detection
    sorted_logs = sorted(logged_dates) if logged_dates else []

    for i in range(num_starts):
        ep = period_episodes[i]
        start_date = ep.start_date
        period_length = ep.length_days

        if i + 1 < num_starts:
            next_start = period_episodes[i + 1].start_date
            end_date = next_start - timedelta(days=1)
            length_days = (next_start - start_date).days
            is_complete = True
        else:
            end_date = None
            length_days = None
            is_complete = False

        # Determine exclusion rules (spec 8.2)
        exclusion_reason: str | None = None
        is_user_excluded = start_date in profile.user_excluded_cycles

        if is_user_excluded:
            exclusion_reason = "user_excluded"
        elif is_complete and length_days is not None:
            if (
                profile.mode == "postpartum"
                and profile.mode_started_on is not None
                and start_date < profile.mode_started_on
            ):
                exclusion_reason = "postpartum"
            elif sorted_logs:
                # Check if there is a gap > 60 days with no logs at all after this cycle start
                # before the next start
                next_start = period_episodes[i + 1].start_date
                logs_in_cycle = [d for d in sorted_logs if start_date <= d <= next_start]
                has_data_gap = False
                if len(logs_in_cycle) >= 2:
                    for idx in range(len(logs_in_cycle) - 1):
                        if (logs_in_cycle[idx + 1] - logs_in_cycle[idx]).days > 60:
                            has_data_gap = True
                            break
                elif (next_start - start_date).days > 60:
                    has_data_gap = True

                if has_data_gap:
                    exclusion_reason = "data_gap"
                elif length_days < 15 or length_days > 60:
                    exclusion_reason = "outlier"
            elif length_days < 15 or length_days > 60:
                exclusion_reason = "outlier"

        cycles.append(
            Cycle(
                start_date=start_date,
                end_date=end_date,
                period_length_days=period_length,
                length_days=length_days,
                is_complete=is_complete,
                is_user_excluded=is_user_excluded,
                exclusion_reason=exclusion_reason,
            )
        )

    return cycles


def confidence(n: int, sd: float) -> str:
    """Spec 8.3: Confidence levels based on count of used cycles and standard deviation."""
    if n >= 6 and sd <= 2.0:
        return "high"
    if n >= 3 and sd <= 4.0:
        return "medium"
    return "low"


def predict(today: date, cycles: list[Cycle], profile: CycleEngineProfile) -> Prediction:
    """Deterministic prediction algorithm calendar-1.0 (spec 8.3, CYC-2)."""
    used = [c for c in cycles if c.is_complete and not c.excluded][-6:]
    n = len(used)

    if profile.mode == "postpartum":
        after = [
            c
            for c in used
            if profile.mode_started_on is not None and c.start_date >= profile.mode_started_on
        ]
        if len(after) < 2:
            return Prediction(confidence="none", suppressed_reason="postpartum_waiting")

    if not cycles:
        if profile.last_period_hint is None:
            return Prediction(confidence="none", suppressed_reason="no_data")
        last_start = profile.last_period_hint
    else:
        last_start = cycles[-1].start_date

    if n == 0:
        if profile.usual_cycle_length is None:
            return Prediction(confidence="none", suppressed_reason="need_one_cycle")
        mean = float(profile.usual_cycle_length)
        sd = DEFAULT_SD
    elif n == 1:
        cycle_len = used[0].length_days
        mean = (
            float(cycle_len) if cycle_len is not None else float(profile.usual_cycle_length or 28)
        )
        sd = DEFAULT_SD
    else:
        lengths = [float(c.length_days) for c in used if c.length_days is not None]
        mean = statistics.mean(lengths)
        sd = statistics.stdev(lengths)

    half = min(MAX_HALF_WIDTH, max(1, round_half_up(sd)))
    predicted = last_start + timedelta(days=round_half_up(mean))
    mean_period = (
        statistics.mean([float(c.period_length_days) for c in used])
        if used
        else float(profile.usual_period_length or 5)
    )

    ovulation = predicted - timedelta(days=14)
    fertile: tuple[date, date] | None = (
        ovulation - timedelta(days=5),
        ovulation + timedelta(days=1),
    )
    if ovulation <= last_start + timedelta(days=round_half_up(mean_period)):
        fertile = None
        ovulation_est: date | None = None
    else:
        ovulation_est = ovulation

    return Prediction(
        predicted_start=predicted,
        range_low=predicted - timedelta(days=half),
        range_high=predicted + timedelta(days=half),
        ovulation_est=ovulation_est,
        fertile=fertile,
        confidence=confidence(n, sd),
        n_cycles=n,
        mean_len=mean,
        sd_len=sd,
        mean_period_len=mean_period,
        algorithm_version=ALGO_VERSION,
    )


def derive_state(
    today: date,
    cycles: list[Cycle],
    prediction: Prediction | None,
    profile: CycleEngineProfile,
    today_flow: str | None = None,
    latest_episode: BleedEpisode | None = None,
) -> DerivedState:
    """Derive UI states and cycle phases from today, cycles, and prediction (spec 8.4)."""
    if prediction is not None and prediction.suppressed_reason == "postpartum_waiting":
        return DerivedState(
            state="waiting",
            cycle_day=None,
            message="Waiting for your cycle to return",
        )

    latest_start = cycles[-1].start_date if cycles else profile.last_period_hint
    cycle_day = (today - latest_start).days + 1 if latest_start is not None else None
    has_long_gap = latest_start is not None and (today - latest_start).days > 90

    # Irregular check: max - min of used cycle lengths > 7
    used_lengths = [c.length_days for c in cycles if c.is_complete and not c.excluded][-6:]
    valid_lengths = [len_val for len_val in used_lengths if len_val is not None]
    is_irregular = (
        (max(valid_lengths) - min(valid_lengths)) > 7 if len(valid_lengths) >= 2 else False
    )

    # Check if currently on period (spec 8.4: Today is within latest episode or flow logged today)
    is_on_period = False
    period_day: int | None = None

    if latest_episode is not None and latest_episode.start_date <= today <= latest_episode.end_date:
        is_on_period = True
        period_day = (today - latest_episode.start_date).days + 1
    elif today_flow is not None and is_flow_day(today_flow):
        is_on_period = True
        period_day = (today - latest_start).days + 1 if latest_start is not None else 1

    if is_on_period:
        return DerivedState(
            state="on_period",
            cycle_day=cycle_day or period_day,
            period_day=period_day,
            is_irregular=is_irregular,
            has_long_gap=has_long_gap,
            phase="menstrual",
            message=f"Day {period_day} of your period",
        )

    if prediction is not None and prediction.suppressed_reason == "postpartum_waiting":
        return DerivedState(
            state="waiting",
            cycle_day=cycle_day,
            message="Waiting for your cycle to return",
        )

    if prediction is not None and prediction.suppressed_reason in ("no_data", "need_one_cycle"):
        return DerivedState(
            state="no_data",
            cycle_day=cycle_day,
            message="Log your period to start predictions",
        )

    # Not on period: compute upcoming, window, or late
    state = "upcoming"
    days_late: int | None = None
    days_until: int | None = None
    message = ""

    if (
        prediction is not None
        and prediction.range_low is not None
        and prediction.range_high is not None
        and prediction.predicted_start is not None
    ):
        if today < prediction.range_low:
            state = "upcoming"
            days_until = (prediction.predicted_start - today).days
            message = f"Period in about {days_until} days"
        elif prediction.range_low <= today <= prediction.range_high:
            state = "window"
            message = "Period may start any day now"
        else:
            state = "late"
            days_late = (today - prediction.range_high).days
            message = f"Your period is {days_late} days later than expected"

    # Phase determination
    phase: str | None = None
    if prediction is not None and prediction.predicted_start is not None:
        mean_period = round_half_up(prediction.mean_period_len or 5)
        if cycle_day is not None and cycle_day <= mean_period:
            phase = "menstrual"
        elif prediction.fertile is not None and today < prediction.fertile[0]:
            phase = "follicular"
        elif (
            prediction.fertile is not None
            and prediction.fertile[0] <= today <= prediction.fertile[1]
        ):
            phase = "fertile_window"
        else:
            phase = "luteal"

    return DerivedState(
        state=state,
        cycle_day=cycle_day,
        days_late=days_late,
        days_until=days_until,
        is_irregular=is_irregular,
        has_long_gap=has_long_gap,
        phase=phase,
        message=message,
    )


def rebuild_and_predict(
    today: date,
    flow_by_date: dict[date, Any],
    profile: CycleEngineProfile,
    logged_dates: set[date] | None = None,
) -> tuple[list[Cycle], Prediction, DerivedState]:
    """Pure, deterministic rebuild of cycles, prediction, and state from logs and profile."""
    episodes = find_bleed_episodes(flow_by_date)
    classified = classify_episodes(episodes, profile.forced_period_starts)
    cycles = build_cycles(classified, profile, logged_dates)
    pred = predict(today, cycles, profile)

    today_flow = flow_by_date.get(today)
    latest_episode = episodes[-1] if episodes else None
    state = derive_state(
        today=today,
        cycles=cycles,
        prediction=pred,
        profile=profile,
        today_flow=str(today_flow) if today_flow is not None else None,
        latest_episode=latest_episode,
    )
    return cycles, pred, state
