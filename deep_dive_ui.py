from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

import streamlit as st


@dataclass(frozen=True)
class DeepDiveRenderModel:
    ticker: str
    conviction_score: int
    conviction_history: list[dict[str, Any]]
    component_rows: list[dict[str, Any]]
    raw_metric_rows: list[dict[str, Any]]
    commentary: str
    missing_fundamentals: bool


def build_conviction_history_series(snapshot_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for row in snapshot_rows:
        parsed_date = _parse_snapshot_date(row.get("date"))
        raw_score = row.get("conviction_score")
        if parsed_date is None or raw_score is None:
            continue
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            continue

        series.append({"Date": parsed_date.isoformat(), "Conviction Score": score})

    series.sort(key=lambda item: item["Date"])
    return series[-90:]


def is_fundamentals_data_unavailable(
    peg_ratio: float | None,
    fcf_yield_last_3_quarters: Sequence[float | None] | None,
) -> bool:
    if peg_ratio is None:
        return True
    if not fcf_yield_last_3_quarters or len(fcf_yield_last_3_quarters) < 3:
        return True
    return any(value is None for value in fcf_yield_last_3_quarters[:3])


def build_dynamic_commentary(
    *,
    conviction_score: int,
    monitor_meter_band: str,
    is_recovery: bool,
    missing_fundamentals: bool,
) -> str:
    if conviction_score >= 75 and is_recovery:
        commentary = "Strong setup: trend and conviction are aligned, with momentum confirming the dip thesis."
    elif conviction_score >= 60:
        commentary = "Constructive setup: several signals are positive, but confirmation is still developing."
    elif conviction_score >= 40:
        commentary = "Mixed setup: watchlist-worthy, but current signals are not yet decisive."
    else:
        commentary = "Low-conviction setup: risk signals dominate and confirmation is limited."

    normalized_band = monitor_meter_band.strip().lower()
    if normalized_band == "strike zone":
        commentary += " Price dislocation is in Strike Zone, so monitor for confirmation before sizing in."
    elif normalized_band == "neutral":
        commentary += " Price dislocation is shallow, which can limit immediate upside from mean reversion."

    if missing_fundamentals:
        commentary += " Data Unavailable for PEG and/or FCF; model uses neutral fallback for unavailable fundamentals."

    return commentary


def render_deep_dive_page(model: DeepDiveRenderModel) -> bool:
    st.subheader(f"Deep Dive — {model.ticker}")
    back_clicked = st.button("← Back to Command Center", use_container_width=True)

    st.markdown("### Conviction History (90 Days)")
    if model.conviction_history:
        st.line_chart(
            data=model.conviction_history,
            x="Date",
            y="Conviction Score",
            use_container_width=True,
        )
    else:
        st.info("No historical snapshots available yet for this ticker.")

    if model.missing_fundamentals:
        st.warning("Data Unavailable: PEG and/or FCF is missing; neutral fallback is applied.")

    breakdown_col, metrics_col = st.columns(2)
    with breakdown_col:
        st.markdown("### Score Breakdown")
        st.dataframe(model.component_rows, use_container_width=True)

    with metrics_col:
        st.markdown("### Raw Metrics")
        st.dataframe(model.raw_metric_rows, use_container_width=True)

    st.markdown("### Analyst Commentary")
    st.write(model.commentary)

    return back_clicked


def _parse_snapshot_date(raw_value: Any) -> date | None:
    if isinstance(raw_value, date):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return date.fromisoformat(raw_value)
        except ValueError:
            return None
    return None