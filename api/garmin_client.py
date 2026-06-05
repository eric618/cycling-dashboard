from datetime import date, timedelta
from garminconnect import Garmin


def get_athlete_profile(client: Garmin) -> dict:
    profile = client.get_full_name()
    stats = client.get_user_summary(date.today().isoformat())
    return {
        "id": client.get_user_id() if hasattr(client, "get_user_id") else 0,
        "fullname": profile or "Atleta",
        "stats": stats,
    }


def get_activities(client: Garmin, start: int = 0, limit: int = 100) -> list[dict]:
    """Fetch activities list from Garmin Connect."""
    return client.get_activities(start, limit)


def get_all_activities(client: Garmin, max_activities: int = 500) -> list[dict]:
    """Fetch all activities with pagination."""
    all_acts = []
    batch = 100
    offset = 0
    while offset < max_activities:
        page = get_activities(client, start=offset, limit=batch)
        if not page:
            break
        all_acts.extend(page)
        if len(page) < batch:
            break
        offset += batch
    return all_acts


def get_activity_details(client: Garmin, activity_id: int) -> dict:
    """Fetch detailed data for a single activity (includes splits, HR, power)."""
    return client.get_activity(activity_id)


def get_activity_hr_zones(client: Garmin, activity_id: int) -> list:
    """Fetch heart rate zones for an activity."""
    try:
        return client.get_activity_hr_timeinzones(activity_id)
    except Exception:
        return []


def get_activity_splits(client: Garmin, activity_id: int) -> dict:
    """Fetch lap/split data for an activity."""
    try:
        return client.get_activity_splits(activity_id)
    except Exception:
        return {}
