import sqlite3
import json
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS activities (
            id               TEXT PRIMARY KEY,
            athlete_id       TEXT,
            name             TEXT,
            activity_type    TEXT,
            start_date       TEXT,
            distance_m       REAL,
            moving_time_s    INTEGER,
            elapsed_time_s   INTEGER,
            elevation_gain_m REAL,
            avg_speed_ms     REAL,
            max_speed_ms     REAL,
            avg_watts        REAL,
            max_watts        REAL,
            avg_heartrate    REAL,
            max_heartrate    REAL,
            avg_cadence      REAL,
            calories         REAL,
            map_polyline     TEXT,
            detail_fetched   BOOLEAN DEFAULT 0,
            fetched_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS streams (
            activity_id  TEXT,
            stream_type  TEXT,
            data_json    TEXT,
            PRIMARY KEY (activity_id, stream_type)
        );

        CREATE TABLE IF NOT EXISTS computed_metrics (
            activity_id  TEXT PRIMARY KEY,
            np_watts     REAL,
            tss          REAL,
            if_value     REAL,
            ftp_estimate REAL
        );

        CREATE TABLE IF NOT EXISTS hr_zones (
            activity_id  TEXT PRIMARY KEY,
            data_json    TEXT
        );
    """)
    conn.commit()
    conn.close()


def upsert_activity(act: dict, athlete_id: str = ""):
    """
    Normalizes a Garmin activity dict and stores it.
    Garmin field names differ from Strava — we map them here.
    """
    conn = get_conn()

    # Garmin uses camelCase
    act_id = str(act.get("activityId") or act.get("id", ""))
    name = act.get("activityName") or act.get("name", "Sin nombre")
    act_type = (act.get("activityType") or {}).get("typeKey", "") if isinstance(act.get("activityType"), dict) else act.get("activityType", "")
    start_date = act.get("startTimeLocal") or act.get("startTimeGMT") or act.get("start_date", "")
    distance = act.get("distance") or act.get("distance_m") or 0
    moving_time = int(act.get("movingDuration") or act.get("duration") or act.get("moving_time_s") or 0)
    elapsed_time = int(act.get("elapsedDuration") or act.get("elapsed_time_s") or moving_time)
    elevation = act.get("elevationGain") or act.get("elevation_gain_m") or 0
    avg_speed = act.get("averageSpeed") or act.get("avg_speed_ms") or 0
    max_speed = act.get("maxSpeed") or act.get("max_speed_ms") or 0
    avg_watts = act.get("avgPower") or act.get("average_watts") or None
    max_watts = act.get("maxPower") or act.get("max_watts") or None
    avg_hr = act.get("averageHR") or act.get("avg_heartrate") or None
    max_hr = act.get("maxHR") or act.get("max_heartrate") or None
    avg_cadence = act.get("averageBikingCadenceInRevPerMinute") or act.get("averageCadence") or None
    calories = act.get("calories") or None
    polyline = act.get("summaryPolyline") or act.get("map_polyline") or None

    conn.execute("""
        INSERT OR REPLACE INTO activities
        (id, athlete_id, name, activity_type, start_date, distance_m, moving_time_s,
         elapsed_time_s, elevation_gain_m, avg_speed_ms, max_speed_ms,
         avg_watts, max_watts, avg_heartrate, max_heartrate, avg_cadence,
         calories, map_polyline, detail_fetched, fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                COALESCE((SELECT detail_fetched FROM activities WHERE id=?), 0),
                datetime('now'))
    """, (
        act_id, athlete_id, name, act_type, start_date,
        distance, moving_time, elapsed_time, elevation,
        avg_speed, max_speed, avg_watts, max_watts,
        avg_hr, max_hr, avg_cadence, calories, polyline,
        act_id
    ))
    conn.commit()
    conn.close()


def get_activities(athlete_id=None, limit=None):
    conn = get_conn()
    q = "SELECT * FROM activities"
    params = []
    if athlete_id:
        q += " WHERE athlete_id = ?"
        params.append(str(athlete_id))
    q += " ORDER BY start_date DESC"
    if limit:
        q += f" LIMIT {limit}"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_activity(activity_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM activities WHERE id=?", (str(activity_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_detail_fetched(activity_id):
    conn = get_conn()
    conn.execute("UPDATE activities SET detail_fetched=1 WHERE id=?", (str(activity_id),))
    conn.commit()
    conn.close()


def save_stream(activity_id, stream_type, data):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO streams VALUES (?,?,?)",
        (str(activity_id), stream_type, json.dumps(data))
    )
    conn.commit()
    conn.close()


def get_stream(activity_id, stream_type):
    conn = get_conn()
    row = conn.execute(
        "SELECT data_json FROM streams WHERE activity_id=? AND stream_type=?",
        (str(activity_id), stream_type)
    ).fetchone()
    conn.close()
    return json.loads(row["data_json"]) if row else None


def save_computed(activity_id, np_watts=None, tss=None, if_value=None, ftp_estimate=None):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO computed_metrics VALUES (?,?,?,?,?)",
        (str(activity_id), np_watts, tss, if_value, ftp_estimate)
    )
    conn.commit()
    conn.close()


def get_computed(activity_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM computed_metrics WHERE activity_id=?", (str(activity_id),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_hr_zones(activity_id, data: list):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO hr_zones VALUES (?,?)",
        (str(activity_id), json.dumps(data))
    )
    conn.commit()
    conn.close()


def get_hr_zones(activity_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT data_json FROM hr_zones WHERE activity_id=?", (str(activity_id),)
    ).fetchone()
    conn.close()
    return json.loads(row["data_json"]) if row else None
