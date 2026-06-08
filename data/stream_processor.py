"""
Shared logic to fetch a Garmin activity's detail payload, extract time-series
streams (watts, HR, cadence, altitude, latlng), compute derived metrics
(NP, TSS, FTP estimate) and persist everything via data.cache.

Used by both sync.py (bulk local sync) and pages/activity_detail.py (lazy fetch).
"""
from data.cache import save_stream, save_computed, save_hr_zones, mark_detail_fetched
from data.processor import compute_activity_metrics


def fetch_and_store_activity_detail(client, activity_id, act: dict, ftp: int = 250) -> bool:
    """
    Fetches detail + streams + HR zones for a single activity from Garmin
    and stores them via data.cache. Returns True if streams were found.
    """
    from api.garmin_client import get_activity_details, get_activity_hr_zones

    detail = get_activity_details(client, int(activity_id))
    found = extract_and_save_streams(activity_id, detail, ftp, act)

    hz = get_activity_hr_zones(client, int(activity_id))
    if hz:
        save_hr_zones(activity_id, hz)

    mark_detail_fetched(activity_id)
    return found


def extract_and_save_streams(activity_id, detail: dict, ftp: int, act: dict) -> bool:
    """
    Parse Garmin's activity detail structure to extract time-series streams.
    Garmin returns metrics via activityDetailMetrics / metricDescriptors.
    Returns True if any stream (watts) was found and stored.
    """
    metrics_data = detail.get("activityDetailMetrics") or {}
    descriptors = detail.get("metricDescriptors") or metrics_data.get("metricDescriptors") or []
    intervals = metrics_data if isinstance(metrics_data, list) else metrics_data.get("activityDetailMetrics") or []

    if not descriptors or not intervals:
        return False

    key_map = {d["key"]: d["metricsIndex"] for d in descriptors if "key" in d and "metricsIndex" in d}

    def extract(key):
        idx = key_map.get(key)
        if idx is None:
            return None
        vals = [row["metrics"][idx] if row.get("metrics") and idx < len(row["metrics"]) else None
                for row in intervals]
        return [v for v in vals if v is not None]

    time_stream = extract("directTimestamp") or list(range(len(intervals)))
    if time_stream and isinstance(time_stream[0], (int, float)) and time_stream[0] > 1e9:
        t0 = time_stream[0]
        time_stream = [int(t - t0) / 1000 for t in time_stream]

    watts = extract("directPower")
    hr = extract("directHeartRate")
    cad = extract("directBikeCadence") or extract("directCadence")
    alt = extract("directAltitude") or extract("directElevation")
    lat = extract("directLatitude")
    lon = extract("directLongitude")

    if time_stream:
        save_stream(activity_id, "time", time_stream)
    if watts:
        save_stream(activity_id, "watts", watts)
        cm = compute_activity_metrics(watts, act.get("moving_time_s", 0), ftp)
        save_computed(activity_id, **cm)
    if hr:
        save_stream(activity_id, "heartrate", hr)
    if cad:
        save_stream(activity_id, "cadence", cad)
    if alt:
        save_stream(activity_id, "altitude", alt)
    if lat and lon:
        save_stream(activity_id, "latlng", list(zip(lat, lon)))

    return bool(watts)
