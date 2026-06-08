"""
Data cache layer — uses Supabase (PostgreSQL) as the backend.
All functions mirror the old SQLite API so the rest of the app needs no changes.
"""
import json
from functools import lru_cache
from config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client, Client


@lru_cache(maxsize=1)
def _client() -> Client:
    url = key = ""
    # Try Streamlit secrets first (cloud), then env vars (local)
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        pass
    if not url or not key:
        import os
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL y SUPABASE_KEY. "
            "Agrégalas al .env o a los Secrets de Streamlit Cloud."
        )
    return create_client(url, key)


def init_db():
    """No-op — tables are created in the Supabase dashboard."""
    pass


# --- Activities ---

def upsert_activity(act: dict, athlete_id: str = ""):
    act_id = str(act.get("activityId") or act.get("id", ""))
    name = act.get("activityName") or act.get("name", "Sin nombre")
    act_type = (
        act.get("activityType", {}).get("typeKey", "")
        if isinstance(act.get("activityType"), dict)
        else act.get("activityType", "")
    )
    start_date   = act.get("startTimeLocal") or act.get("startTimeGMT") or act.get("start_date", "")
    distance     = float(act.get("distance") or act.get("distance_m") or 0)
    moving_time  = int(act.get("movingDuration") or act.get("duration") or act.get("moving_time_s") or 0)
    elapsed_time = int(act.get("elapsedDuration") or act.get("elapsed_time_s") or moving_time)
    elevation    = float(act.get("elevationGain") or act.get("elevation_gain_m") or 0)
    avg_speed    = float(act.get("averageSpeed") or act.get("avg_speed_ms") or 0)
    max_speed    = float(act.get("maxSpeed") or act.get("max_speed_ms") or 0)
    avg_watts    = act.get("avgPower") or act.get("average_watts")
    max_watts    = act.get("maxPower") or act.get("max_watts")
    avg_hr       = act.get("averageHR") or act.get("avg_heartrate")
    max_hr       = act.get("maxHR") or act.get("max_heartrate")
    avg_cadence  = act.get("averageBikingCadenceInRevPerMinute") or act.get("averageCadence")
    calories     = act.get("calories")
    polyline     = act.get("summaryPolyline") or act.get("map_polyline")

    row = dict(
        id=act_id, athlete_id=athlete_id, name=name, activity_type=act_type,
        start_date=start_date, distance_m=distance, moving_time_s=moving_time,
        elapsed_time_s=elapsed_time, elevation_gain_m=elevation,
        avg_speed_ms=avg_speed, max_speed_ms=max_speed,
        avg_watts=avg_watts, max_watts=max_watts,
        avg_heartrate=avg_hr, max_heartrate=max_hr,
        avg_cadence=avg_cadence, calories=calories,
        map_polyline=polyline,
    )
    _client().table("activities").upsert(row, on_conflict="id").execute()


def get_activities(athlete_id=None, limit=None):
    q = _client().table("activities").select("*").order("start_date", desc=True)
    if athlete_id:
        q = q.eq("athlete_id", str(athlete_id))
    if limit:
        q = q.limit(limit)
    return q.execute().data or []


def get_activities_cached(athlete_id=None, limit=None):
    """
    Streamlit-cached wrapper around get_activities (ttl=300s).
    Falls back to the uncached version outside a Streamlit runtime
    (e.g. sync.py) so this module stays importable everywhere.
    """
    try:
        import streamlit as st

        @st.cache_data(ttl=300, show_spinner=False)
        def _cached(athlete_id, limit):
            return get_activities(athlete_id=athlete_id, limit=limit)

        return _cached(athlete_id, limit)
    except Exception:
        return get_activities(athlete_id=athlete_id, limit=limit)


def get_activity(activity_id):
    res = _client().table("activities").select("*").eq("id", str(activity_id)).execute()
    return res.data[0] if res.data else None


def mark_detail_fetched(activity_id):
    _client().table("activities").update({"detail_fetched": True}).eq("id", str(activity_id)).execute()


# --- Streams ---

def save_stream(activity_id, stream_type, data):
    _client().table("streams").upsert(
        {"activity_id": str(activity_id), "stream_type": stream_type, "data_json": json.dumps(data)},
        on_conflict="activity_id,stream_type"
    ).execute()


def get_stream(activity_id, stream_type):
    res = _client().table("streams").select("data_json") \
        .eq("activity_id", str(activity_id)).eq("stream_type", stream_type).execute()
    return json.loads(res.data[0]["data_json"]) if res.data else None


# --- Computed metrics ---

def save_computed(activity_id, np_watts=None, tss=None, if_value=None, ftp_estimate=None):
    _client().table("computed_metrics").upsert(
        {"activity_id": str(activity_id), "np_watts": np_watts,
         "tss": tss, "if_value": if_value, "ftp_estimate": ftp_estimate},
        on_conflict="activity_id"
    ).execute()


def get_computed(activity_id):
    res = _client().table("computed_metrics").select("*").eq("activity_id", str(activity_id)).execute()
    return res.data[0] if res.data else None


def get_computed_batch(activity_ids: list) -> dict:
    """Fetch computed_metrics for many activities in a single query.
    Returns {activity_id: row}."""
    ids = [str(i) for i in activity_ids]
    if not ids:
        return {}
    res = _client().table("computed_metrics").select("*").in_("activity_id", ids).execute()
    return {row["activity_id"]: row for row in (res.data or [])}


def get_streams_batch(activity_ids: list, stream_type: str) -> dict:
    """Fetch one stream type for many activities in a single query.
    Returns {activity_id: data_list}."""
    ids = [str(i) for i in activity_ids]
    if not ids:
        return {}
    res = _client().table("streams").select("activity_id,data_json") \
        .eq("stream_type", stream_type).in_("activity_id", ids).execute()
    return {row["activity_id"]: json.loads(row["data_json"]) for row in (res.data or [])}


# --- HR Zones ---

def save_hr_zones(activity_id, data: list):
    _client().table("hr_zones").upsert(
        {"activity_id": str(activity_id), "data_json": json.dumps(data)},
        on_conflict="activity_id"
    ).execute()


def get_hr_zones(activity_id):
    res = _client().table("hr_zones").select("data_json").eq("activity_id", str(activity_id)).execute()
    return json.loads(res.data[0]["data_json"]) if res.data else None
