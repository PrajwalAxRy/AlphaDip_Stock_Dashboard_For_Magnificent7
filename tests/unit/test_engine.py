from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import (
    ConvictionBreakdown,
    build_conviction_result,
    final_conviction_score,
    fcf_safety_component,
    is_recovery,
    monitor_meter_from_price_gap,
    peg_component,
)


@pytest.mark.unit
def test_monitor_meter_boundaries() -> None:
    assert monitor_meter_from_price_gap(0.0) == ("Neutral", 1)
    assert monitor_meter_from_price_gap(15.0) == ("Neutral", 3)
    assert monitor_meter_from_price_gap(15.01)[0] == "Watching"
    assert monitor_meter_from_price_gap(25.0) == ("Watching", 7)
    assert monitor_meter_from_price_gap(25.01)[0] == "Strike Zone"
    assert monitor_meter_from_price_gap(60.0) == ("Strike Zone", 10)


@pytest.mark.unit
def test_peg_threshold_boundaries() -> None:
    assert peg_component(0.99) == 20.0
    assert peg_component(1.0) == 20.0
    assert peg_component(1.5) == 10.0
    assert peg_component(2.0) == 0.0
    assert peg_component(2.2) == 0.0


@pytest.mark.unit
def test_score_rounding_and_clamp_is_deterministic() -> None:
    assert final_conviction_score(ConvictionBreakdown(40.0, 40.0, 40.0, 10.0, 5.0)) == 100
    assert final_conviction_score(ConvictionBreakdown(-10.0, -5.0, 0.0, 0.0, 0.0)) == 0
    assert final_conviction_score(ConvictionBreakdown(19.5, 20.0, 10.5, 7.5, 7.5)) == 65


@pytest.mark.unit
def test_missing_data_uses_neutral_fallback_components() -> None:
    result = build_conviction_result(
        current_price=95.0,
        high_52_week=100.0,
        ma_50_day=100.0,
        peg_ratio=None,
        fcf_yield_last_3_quarters=[None, 0.02, 0.03],
        stock_return_1m=0.01,
        sp500_return_1m=0.02,
    )

    assert result.components.peg == 10.0
    assert result.components.fcf_safety == 7.5


@pytest.mark.unit
def test_is_recovery_rule_is_strictly_greater_than_50d_ma() -> None:
    assert is_recovery(100.01, 100.0) is True
    assert is_recovery(100.0, 100.0) is False


@pytest.mark.unit
def test_manual_parity_fixture_msft_reference_case() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "msft_reference_case.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    result = build_conviction_result(**fixture["input"])
    expected = fixture["expected"]

    assert result.price_gap_percent == expected["price_gap_percent"]
    assert result.monitor_meter_band == expected["monitor_meter_band"]
    assert result.monitor_meter_score == expected["monitor_meter_score"]
    assert result.is_recovery is expected["is_recovery"]
    assert result.conviction_score == expected["conviction_score"]

    assert result.components.price_architecture == expected["components"]["price_architecture"]
    assert result.components.trend_confirmation == expected["components"]["trend_confirmation"]
    assert result.components.peg == expected["components"]["peg"]
    assert result.components.fcf_safety == expected["components"]["fcf_safety"]
    assert result.components.relative_strength == expected["components"]["relative_strength"]


@pytest.mark.unit
def test_fcf_safety_requires_positive_and_increasing_series() -> None:
    assert fcf_safety_component([0.01, 0.02, 0.03]) == 15.0
    assert fcf_safety_component([0.03, 0.02, 0.01]) == 0.0
    assert fcf_safety_component([0.0, 0.01, 0.02]) == 0.0
