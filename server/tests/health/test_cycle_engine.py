"""Cycle engine tests for calendar-1.0 (spec sections 8.1-8.4, 8.6, CYC-2).

Verifies test vectors TV1 to TV12 as named tests, Hypothesis property tests,
and edge branch coverage for 100% branch coverage.
"""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.health.engine import (
    BleedEpisode,
    CycleEngineProfile,
    build_cycles,
    classify_episodes,
    derive_state,
    find_bleed_episodes,
    rebuild_and_predict,
    round_half_up,
)

# ---------------------------------------------------------------------------
# Test Vectors (Spec 8.6, TV1-TV12) - Requirement CYC-2
# ---------------------------------------------------------------------------


@pytest.mark.req("CYC-2")
def test_tv1_standard_four_cycles() -> None:
    """TV1: Starts 2026-06-01, 06-29, 07-28, 08-26, 09-24; period 5 days each.

    Expected: n=4, mean 28.75, sd 0.5 -> half-width 1; predicted 2026-10-23; range 10-22 to 10-24;
    ovulation 10-09; fertile 10-04 to 10-10; confidence medium.
    """
    flow_map: dict[date, str] = {}
    starts = [
        date(2026, 6, 1),
        date(2026, 6, 29),
        date(2026, 7, 28),
        date(2026, 8, 26),
        date(2026, 9, 24),
    ]
    for s in starts:
        for offset in range(5):
            flow_map[s + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = date(2026, 10, 1)

    cycles, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert len(cycles) == 5
    complete_cycles = [c for c in cycles if c.is_complete]
    assert len(complete_cycles) == 4
    assert [c.length_days for c in complete_cycles] == [28, 29, 29, 29]

    assert pred.n_cycles == 4
    assert pred.mean_len == pytest.approx(28.75)
    assert pred.sd_len == pytest.approx(0.5)
    assert pred.predicted_start == date(2026, 10, 23)
    assert pred.range_low == date(2026, 10, 22)
    assert pred.range_high == date(2026, 10, 24)
    assert pred.ovulation_est == date(2026, 10, 9)
    assert pred.fertile == (date(2026, 10, 4), date(2026, 10, 10))
    assert pred.confidence == "medium"
    assert pred.algorithm_version == "calendar-1.0"


@pytest.mark.req("CYC-2")
def test_tv2_single_cycle_default_sd() -> None:
    """TV2: One complete cycle of 30 days, latest start 2026-09-20.

    Expected: sd 3 -> predicted 2026-10-20; range 10-17 to 10-23; confidence low.
    """
    flow_map: dict[date, str] = {}
    # Cycle 1 start: 2026-08-21, length 30 days -> next start 2026-09-20
    for offset in range(5):
        flow_map[date(2026, 8, 21) + timedelta(days=offset)] = "medium"
        flow_map[date(2026, 9, 20) + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = date(2026, 9, 25)

    cycles, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert len(cycles) == 2
    complete_cycles = [c for c in cycles if c.is_complete]
    assert len(complete_cycles) == 1
    assert complete_cycles[0].length_days == 30

    assert pred.n_cycles == 1
    assert pred.mean_len == pytest.approx(30.0)
    assert pred.sd_len == pytest.approx(3.0)
    assert pred.predicted_start == date(2026, 10, 20)
    assert pred.range_low == date(2026, 10, 17)
    assert pred.range_high == date(2026, 10, 23)
    assert pred.confidence == "low"


@pytest.mark.req("CYC-2")
def test_tv3_no_cycles_profile_hint() -> None:
    """TV3: No cycles; usual length 28; last period hint 2026-09-15.

    Expected: predicted 2026-10-13; range 10-10 to 10-16; confidence low.
    """
    flow_map: dict[date, str] = {}
    profile = CycleEngineProfile(
        last_period_hint=date(2026, 9, 15),
        usual_cycle_length=28,
        usual_period_length=5,
    )
    today = date(2026, 9, 20)

    cycles, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert len(cycles) == 0
    assert pred.n_cycles == 0
    assert pred.mean_len == pytest.approx(28.0)
    assert pred.sd_len == pytest.approx(3.0)
    assert pred.predicted_start == date(2026, 10, 13)
    assert pred.range_low == date(2026, 10, 10)
    assert pred.range_high == date(2026, 10, 16)
    assert pred.confidence == "low"


@pytest.mark.req("CYC-2")
def test_tv4_postpartum_suppression() -> None:
    """TV4: Postpartum mode from 2026-08-01; one complete cycle after it.

    Expected: Suppressed: postpartum_waiting.
    """
    flow_map: dict[date, str] = {}
    # Cycle 1: starts 2026-08-10, ends 2026-09-08 (30 days); latest start 2026-09-09
    for offset in range(5):
        flow_map[date(2026, 8, 10) + timedelta(days=offset)] = "medium"
        flow_map[date(2026, 9, 9) + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile(
        mode="postpartum",
        mode_started_on=date(2026, 8, 1),
    )
    today = date(2026, 9, 15)

    _, pred, state = rebuild_and_predict(today, flow_map, profile)

    assert pred.confidence == "none"
    assert pred.suppressed_reason == "postpartum_waiting"
    assert state.state == "waiting"


@pytest.mark.req("CYC-2")
def test_tv5_irregular_cycles_note() -> None:
    """TV5: Lengths 25, 35, 28, 40, 26.

    Expected: mean 30.8, sd 6.46 -> half-width 6; irregular note shown; confidence low.
    """
    lengths = [25, 35, 28, 40, 26]
    flow_map: dict[date, str] = {}
    curr = date(2026, 1, 1)
    for length in lengths:
        for offset in range(5):
            flow_map[curr + timedelta(days=offset)] = "medium"
        curr += timedelta(days=length)
    # Latest incomplete cycle start
    for offset in range(5):
        flow_map[curr + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = curr + timedelta(days=5)

    _, pred, state = rebuild_and_predict(today, flow_map, profile)

    assert pred.n_cycles == 5
    assert pred.mean_len == pytest.approx(30.8)
    assert pred.sd_len == pytest.approx(6.46, abs=0.01)
    assert pred.confidence == "low"
    assert (pred.range_high - pred.predicted_start).days == 6
    assert state.is_irregular is True


@pytest.mark.req("CYC-2")
def test_tv6_spotting_only_no_cycle() -> None:
    """TV6: Only spotting logged on 2026-10-01.

    Expected: No new cycle; latest start unchanged.
    """
    flow_map: dict[date, str] = {
        date(2026, 9, 1): "medium",
        date(2026, 9, 2): "medium",
        date(2026, 10, 1): "spotting",
    }
    profile = CycleEngineProfile()
    today = date(2026, 10, 2)

    cycles, _, _ = rebuild_and_predict(today, flow_map, profile)

    assert len(cycles) == 1
    assert cycles[0].start_date == date(2026, 9, 1)


@pytest.mark.req("CYC-2")
def test_tv7_intra_cycle_and_forced_outlier() -> None:
    """TV7: Flow begins 10 days after the latest start.

    Expected: Intra-cycle bleed; no new cycle; prompt shown; after "yes", a new cycle
    of 10 days exists and is excluded as outlier.
    """
    # 1. Flow begins 10 days after latest start: intra-cycle bleed
    flow_map: dict[date, str] = {
        date(2026, 9, 1): "medium",
        date(2026, 9, 2): "medium",
        date(2026, 9, 11): "medium",
        date(2026, 9, 12): "medium",
    }
    profile = CycleEngineProfile()
    today = date(2026, 9, 15)

    episodes = find_bleed_episodes(flow_map)
    classified = classify_episodes(episodes)
    assert len(classified) == 2
    assert classified[0].is_period_start is True
    assert classified[1].is_intra_cycle is True

    cycles, _, _ = rebuild_and_predict(today, flow_map, profile)
    assert len(cycles) == 1

    # 2. After user answers "yes" (date added to forced_period_starts):
    profile_forced = CycleEngineProfile(forced_period_starts=frozenset({date(2026, 9, 11)}))
    cycles_forced, _, _ = rebuild_and_predict(today, flow_map, profile_forced)
    assert len(cycles_forced) == 2
    # Cycle 1 is complete, length 10 days, excluded as outlier (<15 days)
    assert cycles_forced[0].length_days == 10
    assert cycles_forced[0].exclusion_reason == "outlier"


@pytest.mark.req("CYC-2")
def test_tv8_long_cycle_outlier_exclusion() -> None:
    """TV8: One cycle of 70 days among 28-day cycles.

    Expected: That cycle excluded as outlier (>60 days); stats computed from the rest.
    """
    lengths = [28, 70, 28, 28]
    flow_map: dict[date, str] = {}
    curr = date(2026, 1, 1)
    for length in lengths:
        for offset in range(5):
            flow_map[curr + timedelta(days=offset)] = "medium"
        curr += timedelta(days=length)
    # Latest start
    for offset in range(5):
        flow_map[curr + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = curr + timedelta(days=5)

    cycles, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert len(cycles) == 5
    assert cycles[1].length_days == 70
    assert cycles[1].exclusion_reason == "outlier"

    # Only 3 cycles used in statistics
    assert pred.n_cycles == 3
    assert pred.mean_len == pytest.approx(28.0)
    assert pred.sd_len == pytest.approx(0.0)


@pytest.mark.req("CYC-2")
def test_tv9_bleed_episode_gap_and_length() -> None:
    """TV9: Flow on days 1, 2, 4, 5 (gap of 1 day).

    Expected: One episode; period length 5.
    """
    flow_map: dict[date, str] = {
        date(2026, 9, 1): "heavy",
        date(2026, 9, 2): "medium",
        date(2026, 9, 4): "light",
        date(2026, 9, 5): "light",
    }
    episodes = find_bleed_episodes(flow_map)
    assert len(episodes) == 1
    assert episodes[0].start_date == date(2026, 9, 1)
    assert episodes[0].end_date == date(2026, 9, 5)
    assert episodes[0].length_days == 5


@pytest.mark.req("CYC-2")
def test_tv10_gap_greater_than_two_dry_days_intra_cycle() -> None:
    """TV10: Flow on days 1, 2, then 6, 7 (gap of 3 days), 5 days apart.

    Expected: Second run is an intra-cycle bleed, not a new period.
    """
    flow_map: dict[date, str] = {
        date(2026, 9, 1): "medium",
        date(2026, 9, 2): "medium",
        date(2026, 9, 6): "light",
        date(2026, 9, 7): "light",
    }
    episodes = find_bleed_episodes(flow_map)
    assert len(episodes) == 2
    assert episodes[0].start_date == date(2026, 9, 1)
    assert episodes[1].start_date == date(2026, 9, 6)

    classified = classify_episodes(episodes)
    assert classified[0].is_period_start is True
    assert classified[1].is_intra_cycle is True


@pytest.mark.req("CYC-2")
def test_tv11_late_state_and_reminder_dates() -> None:
    """TV11: Prediction run on 2026-10-26 with TV1 data and no new period.

    Expected: State Late, 2 days; late_period reminder scheduled for 10-27 09:00.
    """
    flow_map: dict[date, str] = {}
    starts = [
        date(2026, 6, 1),
        date(2026, 6, 29),
        date(2026, 7, 28),
        date(2026, 8, 26),
        date(2026, 9, 24),
    ]
    for s in starts:
        for offset in range(5):
            flow_map[s + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = date(2026, 10, 26)

    _, pred, state = rebuild_and_predict(today, flow_map, profile)

    assert pred.range_high == date(2026, 10, 24)
    assert state.state == "late"
    assert state.days_late == 2

    # late_period reminder: 3 days after range_high
    late_reminder_date = pred.range_high + timedelta(days=3)
    assert late_reminder_date == date(2026, 10, 27)


@pytest.mark.req("CYC-2")
def test_tv12_flow_edit_rebuild_cycles_and_prediction() -> None:
    """TV12: Edit a past flow day that changes a start date.

    Expected: Cycles rebuilt; prediction superseded; deterministic recalculation.
    """
    flow_map_v1: dict[date, str] = {
        date(2026, 8, 20): "medium",
        date(2026, 8, 21): "medium",
        date(2026, 9, 20): "medium",
        date(2026, 9, 21): "medium",
    }
    profile = CycleEngineProfile()
    today = date(2026, 9, 25)

    cycles_v1, pred_v1, _ = rebuild_and_predict(today, flow_map_v1, profile)
    assert cycles_v1[0].length_days == 31
    assert pred_v1.predicted_start == date(2026, 10, 21)

    # Edit past flow: August start moves from 2026-08-20 to 2026-08-22
    flow_map_v2 = dict(flow_map_v1)
    del flow_map_v2[date(2026, 8, 20)]
    flow_map_v2[date(2026, 8, 22)] = "medium"

    cycles_v2, pred_v2, _ = rebuild_and_predict(today, flow_map_v2, profile)
    assert cycles_v2[0].start_date == date(2026, 8, 21)
    assert cycles_v2[0].length_days == 30
    assert pred_v2.predicted_start == date(2026, 10, 20)


# ---------------------------------------------------------------------------
# Hypothesis Property-Based Tests (Spec 8.6) - Requirement CYC-2
# ---------------------------------------------------------------------------


@pytest.mark.req("CYC-2")
@given(
    flow_days=st.sets(
        st.dates(min_value=date(2025, 1, 1), max_value=date(2026, 12, 31)),
        min_size=0,
        max_size=50,
    )
)
def test_property_rebuild_is_idempotent(flow_days: set[date]) -> None:
    """Hypothesis: Rebuilding cycles twice from the same flow logs yields identical results."""
    flow_map = {d: "medium" for d in flow_days}
    profile = CycleEngineProfile(usual_cycle_length=28)
    today = date(2026, 6, 1)

    cycles1, pred1, state1 = rebuild_and_predict(today, flow_map, profile)
    cycles2, pred2, state2 = rebuild_and_predict(today, flow_map, profile)

    assert cycles1 == cycles2
    assert pred1 == pred2
    assert state1 == state2


@pytest.mark.req("CYC-2")
@given(
    num_cycles=st.integers(min_value=2, max_value=8),
    cycle_lengths=st.lists(
        st.integers(min_value=20, max_value=35),
        min_size=2,
        max_size=8,
    ),
)
def test_property_cycle_lengths_sum_to_span(num_cycles: int, cycle_lengths: list[int]) -> None:
    """Hypothesis: Cycle lengths sum to the span between first and latest start."""
    flow_map: dict[date, str] = {}
    curr = date(2026, 1, 1)
    lengths_used = cycle_lengths[:num_cycles]
    for length in lengths_used:
        for offset in range(3):
            flow_map[curr + timedelta(days=offset)] = "medium"
        curr += timedelta(days=length)
    # Latest start
    for offset in range(3):
        flow_map[curr + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = curr + timedelta(days=5)

    cycles, _, _ = rebuild_and_predict(today, flow_map, profile)

    complete_cycles = [c for c in cycles if c.is_complete]
    if complete_cycles:
        total_len = sum(c.length_days for c in complete_cycles if c.length_days is not None)
        first_start = complete_cycles[0].start_date
        latest_start = cycles[-1].start_date
        assert total_len == (latest_start - first_start).days


@pytest.mark.req("CYC-2")
@given(
    mean_len=st.integers(min_value=21, max_value=40),
    num_cycles=st.integers(min_value=1, max_value=6),
)
def test_property_range_low_lte_predicted_lte_range_high(mean_len: int, num_cycles: int) -> None:
    """Hypothesis: Every prediction satisfies range_low <= predicted_start <= range_high."""
    flow_map: dict[date, str] = {}
    curr = date(2026, 1, 1)
    for _ in range(num_cycles):
        for offset in range(4):
            flow_map[curr + timedelta(days=offset)] = "medium"
        curr += timedelta(days=mean_len)
    for offset in range(4):
        flow_map[curr + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = curr + timedelta(days=2)

    _, pred, _ = rebuild_and_predict(today, flow_map, profile)

    if pred.predicted_start is not None:
        assert pred.range_low is not None
        assert pred.range_high is not None
        assert pred.range_low <= pred.predicted_start <= pred.range_high
        # Range must never be a single day only (CYC-2)
        assert pred.range_low < pred.range_high


# ---------------------------------------------------------------------------
# Edge Cases and Boundary Tests for 100% Branch Coverage
# ---------------------------------------------------------------------------


@pytest.mark.req("CYC-2")
def test_round_half_up_boundaries() -> None:
    """Tests arithmetic half-up rounding for standard and edge values."""
    assert round_half_up(0.0) == 0
    assert round_half_up(0.4) == 0
    assert round_half_up(0.5) == 1
    assert round_half_up(0.9) == 1
    assert round_half_up(28.75) == 29
    assert round_half_up(6.46) == 6
    assert round_half_up(6.5) == 7


@pytest.mark.req("CYC-2")
def test_suppressed_no_data() -> None:
    """No cycles and no profile hint returns suppressed no_data."""
    profile = CycleEngineProfile()
    today = date(2026, 10, 1)
    _, pred, state = rebuild_and_predict(today, {}, profile)

    assert pred.confidence == "none"
    assert pred.suppressed_reason == "no_data"
    assert state.state == "no_data"


@pytest.mark.req("CYC-2")
def test_suppressed_need_one_cycle() -> None:
    """No cycles, but last_period_hint set without usual_cycle_length -> need_one_cycle."""
    profile = CycleEngineProfile(last_period_hint=date(2026, 9, 1))
    today = date(2026, 10, 1)
    _, pred, state = rebuild_and_predict(today, {}, profile)

    assert pred.confidence == "none"
    assert pred.suppressed_reason == "need_one_cycle"
    assert state.state == "no_data"


@pytest.mark.req("CYC-2")
def test_high_confidence_prediction() -> None:
    """n >= 6 and sd <= 2 yields high confidence."""
    # 7 starts -> 6 complete cycles of 28, 28, 28, 28, 29, 28
    lengths = [28, 28, 28, 28, 29, 28]
    flow_map: dict[date, str] = {}
    curr = date(2026, 1, 1)
    for length in lengths:
        for offset in range(4):
            flow_map[curr + timedelta(days=offset)] = "medium"
        curr += timedelta(days=length)
    for offset in range(4):
        flow_map[curr + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = curr + timedelta(days=2)

    _, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert pred.n_cycles == 6
    assert pred.sd_len is not None
    assert pred.sd_len <= 2.0
    assert pred.confidence == "high"


@pytest.mark.req("CYC-2")
def test_cycle_too_short_suppresses_fertile_window() -> None:
    """Spec 8.3: If ovulation <= last_start + round_half_up(mean_period), fertile is None."""
    # 1 complete cycle of 18 days, mean period length 6
    # predicted = last_start + 18; ovulation = predicted - 14 = last_start + 4
    # last_start + 4 <= last_start + 6 -> fertile is None
    flow_map: dict[date, str] = {}
    for offset in range(6):
        flow_map[date(2026, 9, 1) + timedelta(days=offset)] = "heavy"
        flow_map[date(2026, 9, 19) + timedelta(days=offset)] = "heavy"

    profile = CycleEngineProfile(usual_period_length=6)
    today = date(2026, 9, 25)

    _, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert pred.predicted_start == date(2026, 9, 19) + timedelta(days=18)
    assert pred.ovulation_est is None
    assert pred.fertile is None


@pytest.mark.req("CYC-2")
def test_user_excluded_cycle() -> None:
    """Spec 8.2: User-excluded cycle is marked with user_excluded reason and omitted from stats."""
    flow_map: dict[date, str] = {}
    starts = [date(2026, 6, 1), date(2026, 6, 29), date(2026, 7, 28)]
    for s in starts:
        for offset in range(5):
            flow_map[s + timedelta(days=offset)] = "medium"

    # Exclude cycle starting 2026-06-01
    profile = CycleEngineProfile(user_excluded_cycles=frozenset({date(2026, 6, 1)}))
    today = date(2026, 8, 1)

    cycles, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert cycles[0].exclusion_reason == "user_excluded"
    assert cycles[0].excluded is True
    assert pred.n_cycles == 1  # Only cycle starting 2026-06-29 is included


@pytest.mark.req("CYC-2")
def test_data_gap_exclusion() -> None:
    """Spec 8.2: Cycle before a >60 day gap with no logs is excluded as data_gap."""
    flow_map: dict[date, str] = {}
    # Cycle 1: starts 2026-01-01, ends 2026-01-28 (28 days)
    for offset in range(5):
        flow_map[date(2026, 1, 1) + timedelta(days=offset)] = "medium"
    # Gap from 2026-01-06 to 2026-04-10: 94 days with no logs at all
    # Cycle 2: starts 2026-04-10, ends 2026-05-07 (28 days)
    for offset in range(5):
        flow_map[date(2026, 4, 10) + timedelta(days=offset)] = "medium"
        flow_map[date(2026, 5, 8) + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()
    today = date(2026, 5, 10)
    logged_dates = set(flow_map.keys())

    cycles, pred, _ = rebuild_and_predict(today, flow_map, profile, logged_dates=logged_dates)

    assert cycles[0].exclusion_reason == "data_gap"
    assert pred.n_cycles == 1


@pytest.mark.req("CYC-2")
def test_ui_derived_states_and_phases() -> None:
    """Spec 8.4: Derives all UI states (On period, Upcoming, Window, Late, Long gap) and phases."""
    flow_map: dict[date, str] = {}
    for offset in range(5):
        flow_map[date(2026, 9, 1) + timedelta(days=offset)] = "medium"
        flow_map[date(2026, 9, 29) + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile()

    # 1. On period (Day 2 of period)
    today_on_period = date(2026, 9, 30)
    _, _, state_period = rebuild_and_predict(today_on_period, flow_map, profile)
    assert state_period.state == "on_period"
    assert state_period.period_day == 2
    assert state_period.cycle_day == 2
    assert state_period.phase == "menstrual"

    # 2. Upcoming (Follicular phase)
    today_upcoming = date(2026, 10, 5)
    _, _, state_upcoming = rebuild_and_predict(today_upcoming, flow_map, profile)
    assert state_upcoming.state == "upcoming"
    assert state_upcoming.phase == "follicular"
    assert state_upcoming.days_until is not None

    # 3. Fertile window phase
    today_fertile = date(2026, 10, 10)
    _, _, state_fertile = rebuild_and_predict(today_fertile, flow_map, profile)
    assert state_fertile.phase == "fertile_window"

    # 4. Luteal phase
    today_luteal = date(2026, 10, 18)
    _, _, state_luteal = rebuild_and_predict(today_luteal, flow_map, profile)
    assert state_luteal.phase == "luteal"

    # 5. Window (Period may start any day now)
    today_window = date(2026, 10, 27)  # near predicted 10-27
    _, _, state_window = rebuild_and_predict(today_window, flow_map, profile)
    assert state_window.state == "window"

    # 6. Long gap (> 90 days since last start)
    today_long_gap = date(2026, 9, 29) + timedelta(days=95)
    _, _, state_gap = rebuild_and_predict(today_long_gap, flow_map, profile)
    assert state_gap.has_long_gap is True


@pytest.mark.req("CYC-2")
def test_bleed_episode_properties_and_methods() -> None:
    """Tests BleedEpisode.needs_confirmation and BleedEpisode.is_closed."""
    ep_short = BleedEpisode(start_date=date(2026, 9, 1), end_date=date(2026, 9, 5))
    assert ep_short.needs_confirmation is False
    assert ep_short.is_closed(date(2026, 9, 7)) is False
    assert ep_short.is_closed(date(2026, 9, 8)) is True

    ep_long = BleedEpisode(start_date=date(2026, 9, 1), end_date=date(2026, 9, 15))
    assert ep_long.needs_confirmation is True


@pytest.mark.req("CYC-2")
def test_postpartum_cycle_exclusion_and_two_cycles_resumption() -> None:
    """Spec 8.2 & 8.3: Pre-postpartum cycle is excluded; 2 cycles after resumes predictions."""
    flow_map: dict[date, str] = {}
    # Cycle 1: starts 2026-06-01, ends 2026-06-28 (before mode_started_on 2026-07-01)
    # Cycle 2: starts 2026-07-05, ends 2026-08-01 (after mode_started_on)
    # Cycle 3: starts 2026-08-05, ends 2026-09-01 (after mode_started_on)
    # Latest start: 2026-09-05
    starts = [date(2026, 6, 1), date(2026, 7, 5), date(2026, 8, 5), date(2026, 9, 5)]
    for s in starts:
        for offset in range(4):
            flow_map[s + timedelta(days=offset)] = "medium"

    profile = CycleEngineProfile(
        mode="postpartum",
        mode_started_on=date(2026, 7, 1),
    )
    today = date(2026, 9, 10)

    cycles, pred, _ = rebuild_and_predict(today, flow_map, profile)

    assert cycles[0].exclusion_reason == "postpartum"
    assert cycles[0].excluded is True

    # 2 cycles after mode started (cycles[1] and cycles[2]) -> prediction succeeds!
    assert pred.confidence != "none"
    assert pred.suppressed_reason is None
    assert pred.n_cycles == 2


@pytest.mark.req("CYC-2")
def test_data_gap_single_log_and_outlier_with_sorted_logs() -> None:
    """Tests data_gap when len(logs_in_cycle) < 2, and outlier when logs exist without gap."""
    profile = CycleEngineProfile()

    # Case A: len(logs_in_cycle) < 2 and span > 60 days
    episodes_a = [
        BleedEpisode(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1), is_period_start=True),
        BleedEpisode(start_date=date(2026, 4, 1), end_date=date(2026, 4, 1), is_period_start=True),
    ]
    cycles_a = build_cycles(episodes_a, profile, logged_dates={date(2026, 1, 1)})
    assert cycles_a[0].exclusion_reason == "data_gap"

    # Case B: sorted_logs provided with no gap, but cycle length > 60 -> outlier
    episodes_b = [
        BleedEpisode(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1), is_period_start=True),
        BleedEpisode(
            start_date=date(2026, 3, 10), end_date=date(2026, 3, 10), is_period_start=True
        ),
    ]
    # Logs every 10 days (no gap > 60), total 68 days
    logs_b = {date(2026, 1, 1) + timedelta(days=10 * i) for i in range(7)}
    cycles_b = build_cycles(episodes_b, profile, logged_dates=logs_b)
    assert cycles_b[0].length_days == 68
    assert cycles_b[0].exclusion_reason == "outlier"

    # Case C: len(logs_in_cycle) == 1 and span <= 60 -> not a data gap, included
    episodes_c = [
        BleedEpisode(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1), is_period_start=True),
        BleedEpisode(
            start_date=date(2026, 1, 29), end_date=date(2026, 1, 29), is_period_start=True
        ),
    ]
    cycles_c = build_cycles(episodes_c, profile, logged_dates={date(2026, 1, 1)})
    assert cycles_c[0].length_days == 28
    assert cycles_c[0].exclusion_reason is None


@pytest.mark.req("CYC-2")
def test_derive_state_flow_today_without_episode_and_none_prediction() -> None:
    """Tests derive_state with today_flow logged and with None prediction."""
    profile = CycleEngineProfile(last_period_hint=date(2026, 9, 1))
    today = date(2026, 9, 5)

    # 1. Flow logged today without latest_episode
    state_flow = derive_state(
        today=today,
        cycles=[],
        prediction=None,
        profile=profile,
        today_flow="medium",
        latest_episode=None,
    )
    assert state_flow.state == "on_period"
    assert state_flow.phase == "menstrual"
    assert state_flow.period_day == 5

    # 2. No flow, no prediction
    state_none = derive_state(
        today=today,
        cycles=[],
        prediction=None,
        profile=profile,
        today_flow=None,
        latest_episode=None,
    )
    assert state_none.state == "upcoming"
    assert state_none.phase is None
