from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


PRICE_WEIGHT = 30.0
TREND_WEIGHT = 20.0
PEG_WEIGHT = 20.0
FCF_WEIGHT = 15.0
RS_WEIGHT = 15.0


@dataclass(frozen=True)
class ConvictionBreakdown:
    price_architecture: float
    trend_confirmation: float
    peg: float
    fcf_safety: float
    relative_strength: float

    @property
    def total(self) -> float:
        return (
            self.price_architecture
            + self.trend_confirmation
            + self.peg
            + self.fcf_safety
            + self.relative_strength
        )


@dataclass(frozen=True)
class ConvictionResult:
    price_gap_percent: float
    monitor_meter_band: str
    monitor_meter_score: int
    is_recovery: bool
    components: ConvictionBreakdown
    conviction_score: int


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def round_to_int(value: float) -> int:
    return int(round(value))


def neutral_component_score(max_points: float) -> float:
    return max_points / 2.0


def calculate_price_gap_percent(current_price: float, high_52_week: float) -> float:
    if high_52_week <= 0:
        raise ValueError("high_52_week must be positive")
    gap = ((high_52_week - current_price) / high_52_week) * 100.0
    return round(clamp(gap, 0.0, 100.0), 2)


def monitor_meter_from_price_gap(price_gap_percent: float) -> tuple[str, int]:
    gap = clamp(price_gap_percent, 0.0, 100.0)
    if gap <= 15.0:
        score = round_to_int(1.0 + (gap / 15.0) * 2.0)
        return ("Neutral", int(clamp(score, 1, 3)))
    if gap <= 25.0:
        score = round_to_int(4.0 + ((gap - 15.0) / 10.0) * 3.0)
        return ("Watching", int(clamp(score, 4, 7)))
    score = round_to_int(8.0 + ((gap - 25.0) / 15.0) * 2.0)
    return ("Strike Zone", int(clamp(score, 8, 10)))


def is_recovery(price: float, ma_50_day: float) -> bool:
    return price > ma_50_day


def price_architecture_component(price_gap_percent: float) -> float:
    normalized = clamp(price_gap_percent, 0.0, 30.0) / 30.0
    return PRICE_WEIGHT * normalized


def trend_confirmation_component(price: float, ma_50_day: float) -> float:
    return TREND_WEIGHT if is_recovery(price, ma_50_day) else 0.0


def peg_component(peg_ratio: float | None) -> float:
    if peg_ratio is None:
        return neutral_component_score(PEG_WEIGHT)
    if peg_ratio < 1.0:
        return PEG_WEIGHT
    if peg_ratio >= 2.0:
        return 0.0
    return PEG_WEIGHT * (2.0 - peg_ratio)


def fcf_safety_component(fcf_yield_last_3_quarters: Sequence[float | None] | None) -> float:
    if not fcf_yield_last_3_quarters or len(fcf_yield_last_3_quarters) < 3:
        return neutral_component_score(FCF_WEIGHT)
    series = list(fcf_yield_last_3_quarters[:3])
    if any(value is None for value in series):
        return neutral_component_score(FCF_WEIGHT)

    oldest, middle, latest = float(series[0]), float(series[1]), float(series[2])
    if oldest > 0 and middle > 0 and latest > 0 and oldest < middle < latest:
        return FCF_WEIGHT
    return 0.0


def relative_strength_component(stock_return_1m: float | None, sp500_return_1m: float | None) -> float:
    if stock_return_1m is None or sp500_return_1m is None:
        return neutral_component_score(RS_WEIGHT)
    return RS_WEIGHT if stock_return_1m > sp500_return_1m else 0.0


def conviction_breakdown(
    price_gap_percent: float,
    price: float,
    ma_50_day: float,
    peg_ratio: float | None,
    fcf_yield_last_3_quarters: Sequence[float | None] | None,
    stock_return_1m: float | None,
    sp500_return_1m: float | None,
) -> ConvictionBreakdown:
    return ConvictionBreakdown(
        price_architecture=price_architecture_component(price_gap_percent),
        trend_confirmation=trend_confirmation_component(price, ma_50_day),
        peg=peg_component(peg_ratio),
        fcf_safety=fcf_safety_component(fcf_yield_last_3_quarters),
        relative_strength=relative_strength_component(stock_return_1m, sp500_return_1m),
    )


def final_conviction_score(components: ConvictionBreakdown) -> int:
    total = clamp(components.total, 0.0, 100.0)
    return int(clamp(round_to_int(total), 0, 100))


def build_conviction_result(
    current_price: float,
    high_52_week: float,
    ma_50_day: float,
    peg_ratio: float | None,
    fcf_yield_last_3_quarters: Sequence[float | None] | None,
    stock_return_1m: float | None,
    sp500_return_1m: float | None,
) -> ConvictionResult:
    price_gap_percent = calculate_price_gap_percent(current_price, high_52_week)
    meter_band, meter_score = monitor_meter_from_price_gap(price_gap_percent)
    components = conviction_breakdown(
        price_gap_percent=price_gap_percent,
        price=current_price,
        ma_50_day=ma_50_day,
        peg_ratio=peg_ratio,
        fcf_yield_last_3_quarters=fcf_yield_last_3_quarters,
        stock_return_1m=stock_return_1m,
        sp500_return_1m=sp500_return_1m,
    )
    return ConvictionResult(
        price_gap_percent=price_gap_percent,
        monitor_meter_band=meter_band,
        monitor_meter_score=meter_score,
        is_recovery=is_recovery(current_price, ma_50_day),
        components=components,
        conviction_score=final_conviction_score(components),
    )


def project_name() -> str:
    return "AlphaDip 2026"
