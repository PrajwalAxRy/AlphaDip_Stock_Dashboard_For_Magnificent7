from __future__ import annotations


def monitor_meter_label(band: str, score: int) -> str:
    normalized = (band or "").strip().lower()
    if normalized == "neutral":
        prefix = "🟢"
    elif normalized == "watching":
        prefix = "🟠"
    elif normalized == "strike zone":
        prefix = "🔴"
    else:
        prefix = "⚪"
    return f"{prefix} {band} ({score}/10)"
