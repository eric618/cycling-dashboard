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
