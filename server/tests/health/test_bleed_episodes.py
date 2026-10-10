"""Pure-function tests for bleed-episode logic and TV6, TV9, TV10 (PER-4, PER-5, spec 8.1)."""

from datetime import date

import pytest

from app.health.engine import (
    BleedEpisode,
    check_auto_close,
    classify_episodes,
    find_bleed_episodes,
    is_flow_day,
    needs_length_confirmation,
)


@pytest.mark.req("PER-5")
def test_flow_day_classification() -> None:
    # Flow days: light, medium, heavy
    assert is_flow_day("light") is True
    assert is_flow_day("medium") is True
    assert is_flow_day("heavy") is True

    # Not flow days: spotting, none, None, unknown
    assert is_flow_day("spotting") is False
    assert is_flow_day("none") is False
    assert is_flow_day(None) is False
    assert is_flow_day("other") is False


@pytest.mark.req("PER-4")
def test_episodes_with_lte_2_day_gaps() -> None:
    # Consecutive days (0 dry days gap): same episode
    d1 = date(2026, 6, 1)
    d2 = date(2026, 6, 2)
    episodes = find_bleed_episodes({d1: "medium", d2: "heavy"})
    assert len(episodes) == 1
    assert episodes[0].start_date == d1
    assert episodes[0].end_date == d2
    assert episodes[0].length_days == 2

    # Gap of 1 dry day (d2=June 1, d4=June 3): same episode
    d3 = date(2026, 6, 3)
    episodes_gap1 = find_bleed_episodes({d1: "medium", d3: "light"})
    assert len(episodes_gap1) == 1
    assert episodes_gap1[0].start_date == d1
    assert episodes_gap1[0].end_date == d3
    assert episodes_gap1[0].length_days == 3

    # Gap of 2 dry days (d1=June 1, d4=June 4): same episode
    d4 = date(2026, 6, 4)
    episodes_gap2 = find_bleed_episodes({d1: "medium", d4: "medium"})
    assert len(episodes_gap2) == 1
    assert episodes_gap2[0].start_date == d1
    assert episodes_gap2[0].end_date == d4
    assert episodes_gap2[0].length_days == 4


@pytest.mark.req("PER-4")
def test_episodes_with_gt_2_day_gaps() -> None:
    # Gap of 3 dry days (June 1 and June 5; June 2, 3, 4 are dry): distinct episodes
    d1 = date(2026, 6, 1)
    d5 = date(2026, 6, 5)
    episodes = find_bleed_episodes({d1: "medium", d5: "medium"})
    assert len(episodes) == 2
    assert episodes[0].start_date == d1
    assert episodes[0].end_date == d1
    assert episodes[1].start_date == d5
    assert episodes[1].end_date == d5


@pytest.mark.req("PER-5")
def test_spotting_never_starts_a_period_tv6() -> None:
    # TV6: Only spotting logged on 2026-10-01 -> No new cycle; latest start unchanged
    d = date(2026, 10, 1)
    episodes = find_bleed_episodes({d: "spotting"})
    assert len(episodes) == 0

    # Spotting amidst flow does not break episode if gap condition met
    d1 = date(2026, 10, 2)
    d2 = date(2026, 10, 3)
    episodes_with_spotting = find_bleed_episodes({d: "spotting", d1: "medium", d2: "light"})
    assert len(episodes_with_spotting) == 1
    assert episodes_with_spotting[0].start_date == d1
    assert episodes_with_spotting[0].end_date == d2


@pytest.mark.req("PER-4")
def test_tv9_bleed_episode_length() -> None:
    # TV9: Flow on days 1, 2, 4, 5 (gap of 1 day) -> One episode; period length 5
    d1 = date(2026, 6, 1)
    d2 = date(2026, 6, 2)
    d4 = date(2026, 6, 4)
    d5 = date(2026, 6, 5)

    episodes = find_bleed_episodes(
        {
            d1: "heavy",
            d2: "medium",
            d4: "light",
            d5: "light",
        }
    )
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.start_date == d1
    assert ep.end_date == d5
    assert ep.length_days == 5


@pytest.mark.req("PER-4")
def test_tv10_intra_cycle_bleed() -> None:
    # TV10: Flow on days 1, 2, then 6, 7 (gap of 3 days), 5 days apart
    # -> Second run is an intra-cycle bleed, not a new period
    d1 = date(2026, 6, 1)
    d2 = date(2026, 6, 2)
    d6 = date(2026, 6, 6)
    d7 = date(2026, 6, 7)

    raw_episodes = find_bleed_episodes(
        {
            d1: "heavy",
            d2: "medium",
            d6: "light",
            d7: "light",
        }
    )
    assert len(raw_episodes) == 2

    classified = classify_episodes(raw_episodes)
    assert len(classified) == 2

    # First episode is a period start
    assert classified[0].start_date == d1
    assert classified[0].is_period_start is True
    assert classified[0].is_intra_cycle is False

    # Second episode starts 5 days after first start (< 15 days): intra-cycle bleed
    assert classified[1].start_date == d6
    assert classified[1].is_period_start is False
    assert classified[1].is_intra_cycle is True


@pytest.mark.req("PER-4")
def test_auto_close_after_3_dry_days() -> None:
    # Last flow day is June 5
    ep = BleedEpisode(
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        flow_dates=(date(2026, 6, 1), date(2026, 6, 5)),
    )

    # 1 dry day passed (June 6): open
    assert check_auto_close(ep, today=date(2026, 6, 6)) is False

    # 2 dry days passed (June 7): open
    assert check_auto_close(ep, today=date(2026, 6, 7)) is False

    # 3 dry days passed (June 8): auto-closed!
    assert check_auto_close(ep, today=date(2026, 6, 8)) is True

    # 4 dry days passed (June 9): auto-closed!
    assert check_auto_close(ep, today=date(2026, 6, 9)) is True


@pytest.mark.req("PER-4")
def test_greater_than_10_day_prompt() -> None:
    # 10 days of flow: no confirmation prompt needed
    ep10 = BleedEpisode(
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        flow_dates=(date(2026, 6, 1), date(2026, 6, 10)),
    )
    assert ep10.length_days == 10
    assert needs_length_confirmation(ep10) is False

    # 11 days of flow (> 10 days): prompt to confirm needed
    ep11 = BleedEpisode(
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 11),
        flow_dates=(date(2026, 6, 1), date(2026, 6, 11)),
    )
    assert ep11.length_days == 11
    assert needs_length_confirmation(ep11) is True


@pytest.mark.req("PER-4")
def test_forced_period_start_overrides_15_day_rule() -> None:
    # Episode starting 10 days after previous period start
    d1 = date(2026, 6, 1)
    d11 = date(2026, 6, 11)

    raw = find_bleed_episodes({d1: "medium", d11: "medium"})
    assert len(raw) == 2

    # Without forced start: second episode is intra-cycle bleed
    normal = classify_episodes(raw)
    assert normal[1].is_intra_cycle is True
    assert normal[1].is_period_start is False

    # With forced start at d11: second episode is confirmed as a period start
    forced = classify_episodes(raw, forced_period_starts={d11})
    assert forced[1].is_period_start is True
    assert forced[1].is_intra_cycle is False
