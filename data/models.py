from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Athlete:
    id: int
    firstname: str
    lastname: str
    profile_medium: str = ""


@dataclass
class Activity:
    id: int
    name: str
    start_date: str
    distance_m: float = 0.0
    moving_time_s: int = 0
    elevation_gain_m: float = 0.0
    avg_speed_ms: float = 0.0
    max_speed_ms: float = 0.0
    avg_watts: Optional[float] = None
    max_watts: Optional[float] = None
    avg_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    map_polyline: Optional[str] = None
    np_watts: Optional[float] = None
    tss: Optional[float] = None


@dataclass
class Stream:
    activity_id: int
    stream_type: str
    data: List
