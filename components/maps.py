import folium
import polyline as polyline_lib
from typing import Optional


def decode_polyline(encoded: str) -> list[tuple]:
    if not encoded:
        return []
    try:
        return polyline_lib.decode(encoded)
    except Exception:
        return []


def activity_map(latlng: list = None, polyline_enc: str = None,
                 height: int = 400) -> Optional[folium.Map]:
    """Render a single activity route."""
    coords = latlng or decode_polyline(polyline_enc or "")
    if not coords:
        return None

    center = coords[len(coords) // 2]
    m = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")
    folium.PolyLine(coords, color="#FC4C02", weight=3, opacity=0.85).add_to(m)
    folium.Marker(coords[0], tooltip="Inicio",
                  icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker(coords[-1], tooltip="Fin",
                  icon=folium.Icon(color="red", icon="stop")).add_to(m)
    return m


def multi_activity_map(activities: list[dict], height: int = 500) -> folium.Map:
    """All activities on a single map, color-coded by TSS.
    Centered dynamically on the bounding box of the activities' routes
    (no hardcoded default location)."""
    # Pre-compute bounds so the map opens centered on the user's own routes
    all_coords = []
    for act in activities:
        all_coords.extend(decode_polyline(act.get("map_polyline") or ""))

    if all_coords:
        lats = [c[0] for c in all_coords]
        lons = [c[1] for c in all_coords]
        center = [(min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2]
    else:
        center = all_coords[0] if all_coords else [0, 0]

    m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

    max_tss = max((a.get("tss") or 0 for a in activities), default=1) or 1

    for act in activities:
        polyline_enc = act.get("map_polyline")
        if not polyline_enc:
            continue
        coords = decode_polyline(polyline_enc)
        if not coords:
            continue

        tss_val = act.get("tss") or 0
        intensity = tss_val / max_tss
        r = int(252 * intensity)
        g = int(76 * (1 - intensity))
        b = 2
        color = f"#{r:02x}{g:02x}{b:02x}"

        dist_km = (act.get("distance_m") or 0) / 1000
        popup_text = (
            f"<b>{act.get('name', 'Actividad')}</b><br>"
            f"{act.get('start_date', '')[:10]}<br>"
            f"{dist_km:.1f} km | TSS: {tss_val:.0f}"
        )
        folium.PolyLine(
            coords, color=color, weight=2.5, opacity=0.75,
            tooltip=act.get("name", ""),
            popup=folium.Popup(popup_text, max_width=200),
        ).add_to(m)

    if all_coords:
        lats = [c[0] for c in all_coords]
        lons = [c[1] for c in all_coords]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    return m
