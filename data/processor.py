import math
from typing import Optional
from config import DEFAULT_FTP, DEFAULT_HR_THRESHOLD


# Power zones (% of FTP): z1-z7
POWER_ZONES = [
    ("Z1 Recuperación", 0, 0.55),
    ("Z2 Resistencia",  0.55, 0.75),
    ("Z3 Tempo",        0.75, 0.90),
    ("Z4 Umbral",       0.90, 1.05),
    ("Z5 VO2max",       1.05, 1.20),
    ("Z6 Anaeróbico",   1.20, 1.50),
    ("Z7 Neuromuscular",1.50, 99.0),
]

# HR zones (% of threshold HR)
HR_ZONES = [
    ("Z1 Recuperación", 0,    0.68),
    ("Z2 Resistencia",  0.68, 0.83),
    ("Z3 Tempo",        0.83, 0.94),
    ("Z4 Umbral",       0.94, 1.05),
    ("Z5 VO2max",       1.05, 99.0),
]


def format_duration(seconds: Optional[int]) -> str:
    """
    Consistent human-readable duration formatting used across all pages
    (e.g. Overview, Activity Detail, Routes): "45 min" or "1h 23min".
    """
    if not seconds:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h > 0:
        return f"{h}h {m:02d}min"
    return f"{m} min"


def normalized_power(watts_stream: list[float]) -> Optional[float]:
    if not watts_stream or len(watts_stream) < 30:
        return None
    window = 30
    rolling = [
        sum(watts_stream[i:i+window]) / window
        for i in range(len(watts_stream) - window + 1)
    ]
    np = (sum(x**4 for x in rolling) / len(rolling)) ** 0.25
    return round(np, 1)


def intensity_factor(np: float, ftp: float) -> float:
    return round(np / ftp, 3)


def tss(duration_s: int, np: float, if_val: float, ftp: float) -> float:
    return round((duration_s * np * if_val) / (ftp * 3600) * 100, 1)


def estimate_ftp(watts_stream: list[float], duration_s: int) -> Optional[float]:
    """Estimate FTP as 95% of best 20-minute average power."""
    if not watts_stream or duration_s < 1200:
        return None
    window = min(1200, len(watts_stream))
    best = max(
        sum(watts_stream[i:i+window]) / window
        for i in range(len(watts_stream) - window + 1)
    )
    return round(best * 0.95, 1)


def power_zones(watts_stream: list[float], ftp: float) -> dict:
    """Returns seconds spent in each power zone."""
    zones = {z[0]: 0 for z in POWER_ZONES}
    for w in watts_stream:
        pct = w / ftp
        for name, lo, hi in POWER_ZONES:
            if lo <= pct < hi:
                zones[name] += 1
                break
    return zones


def hr_zones(hr_stream: list[float], threshold_hr: float) -> dict:
    """Returns seconds spent in each HR zone."""
    zones = {z[0]: 0 for z in HR_ZONES}
    for hr in hr_stream:
        pct = hr / threshold_hr
        for name, lo, hi in HR_ZONES:
            if lo <= pct < hi:
                zones[name] += 1
                break
    return zones


def compute_activity_metrics(
    watts_stream: Optional[list],
    moving_time_s: int,
    ftp: float = DEFAULT_FTP,
) -> dict:
    result = {"np_watts": None, "tss": None, "if_value": None, "ftp_estimate": None}
    if not watts_stream:
        return result

    np = normalized_power(watts_stream)
    if np is None:
        return result

    if_val = intensity_factor(np, ftp)
    tss_val = tss(moving_time_s, np, if_val, ftp)
    ftp_est = estimate_ftp(watts_stream, moving_time_s)

    result.update({
        "np_watts": np,
        "tss": tss_val,
        "if_value": if_val,
        "ftp_estimate": ftp_est,
    })
    return result


def ctl_atl(tss_by_date: dict) -> tuple[list, list, list]:
    """
    Compute CTL (42-day) and ATL (7-day) from a dict {date_str: tss_value}.
    Returns (dates, ctl_values, atl_values).
    """
    import pandas as pd
    if not tss_by_date:
        return [], [], []

    s = pd.Series(tss_by_date)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    full = s.resample("D").sum().fillna(0)

    ctl = full.ewm(span=42, adjust=False).mean()
    atl = full.ewm(span=7, adjust=False).mean()

    return (
        [d.strftime("%Y-%m-%d") for d in full.index],
        [round(v, 1) for v in ctl.values],
        [round(v, 1) for v in atl.values],
    )


# Standard durations (seconds) for power-curve analysis
POWER_CURVE_DURATIONS = [5, 15, 60, 300, 600, 1200, 3600]
POWER_CURVE_LABELS = {5: "5s", 15: "15s", 60: "1min", 300: "5min",
                      600: "10min", 1200: "20min", 3600: "1h"}


def best_power_for_duration(watts_stream: list[float], duration_s: int) -> Optional[float]:
    """Best (max) rolling average power sustained for `duration_s` seconds."""
    n = len(watts_stream)
    if n < duration_s:
        return None
    window_sum = sum(watts_stream[:duration_s])
    best = window_sum
    for i in range(duration_s, n):
        window_sum += watts_stream[i] - watts_stream[i - duration_s]
        if window_sum > best:
            best = window_sum
    return round(best / duration_s, 1)


def power_curve(streams_by_activity: dict[str, list[float]],
                durations: list[int] = None) -> dict[int, float]:
    """
    Aggregate power curve across many activities.
    `streams_by_activity`: {activity_id: watts_stream}
    Returns {duration_s: best_power_ever_seen}.
    """
    durations = durations or POWER_CURVE_DURATIONS
    best = {d: None for d in durations}
    for watts in streams_by_activity.values():
        if not watts:
            continue
        for d in durations:
            p = best_power_for_duration(watts, d)
            if p is not None and (best[d] is None or p > best[d]):
                best[d] = p
    return best


def decoupling(watts_stream: list[float], hr_stream: list[float]) -> Optional[float]:
    """
    Pw:HR decoupling (%) — compares the power-to-heart-rate ratio between the
    first and second half of an activity. Positive values indicate drift
    (cardiac fatigue): your HR rises relative to power as the effort continues.
    Formula: ((ratio_first_half - ratio_second_half) / ratio_first_half) * 100
    """
    n = min(len(watts_stream), len(hr_stream))
    if n < 600:  # need at least ~10 minutes of overlapping data
        return None

    half = n // 2
    w1, h1 = watts_stream[:half], hr_stream[:half]
    w2, h2 = watts_stream[half:n], hr_stream[half:n]

    avg_w1 = sum(w1) / len(w1)
    avg_h1 = sum(h1) / len(h1)
    avg_w2 = sum(w2) / len(w2)
    avg_h2 = sum(h2) / len(h2)

    if avg_h1 == 0 or avg_h2 == 0 or avg_w2 == 0:
        return None

    ratio1 = avg_w1 / avg_h1
    ratio2 = avg_w2 / avg_h2
    if ratio1 == 0:
        return None

    return round((ratio1 - ratio2) / ratio1 * 100, 1)


def detect_intervals(watts_stream: list[float], ftp: float,
                      threshold_pct: float = 0.88, min_duration_s: int = 90) -> list[dict]:
    """
    Detect sustained high-effort intervals within a ride.
    An interval is a contiguous stretch where power stays above
    `threshold_pct` * FTP for at least `min_duration_s` seconds.
    Returns a list of {start_s, end_s, duration_s, avg_watts}.
    """
    if not watts_stream or not ftp:
        return []

    threshold = threshold_pct * ftp
    intervals = []
    start = None

    for i, w in enumerate(watts_stream):
        above = w >= threshold
        if above and start is None:
            start = i
        elif not above and start is not None:
            duration = i - start
            if duration >= min_duration_s:
                seg = watts_stream[start:i]
                intervals.append({
                    "start_s": start, "end_s": i, "duration_s": duration,
                    "avg_watts": round(sum(seg) / len(seg), 1),
                })
            start = None

    if start is not None:
        duration = len(watts_stream) - start
        if duration >= min_duration_s:
            seg = watts_stream[start:]
            intervals.append({
                "start_s": start, "end_s": len(watts_stream), "duration_s": duration,
                "avg_watts": round(sum(seg) / len(seg), 1),
            })

    return intervals
