import streamlit as st
from data.cache import get_activities, get_stream, get_computed, get_hr_zones
from data.processor import power_zones, hr_zones, compute_activity_metrics, format_duration
from components.charts import stream_line, elevation_area, zone_donut
from components.maps import activity_map
from streamlit_folium import st_folium


def render(athlete: dict, ftp: int, hr_threshold: int, client=None):
    st.title("Detalle de actividad")

    activities = get_activities(athlete_id=athlete.get("id"))
    # Filter only cycling activities
    cycling = [a for a in activities if "cycling" in (a.get("activity_type") or "").lower()
               or "ride" in (a.get("activity_type") or "").lower()
               or "bike" in (a.get("activity_type") or "").lower()]
    if not cycling:
        cycling = activities  # fallback: show all if no cycling detected

    if not cycling:
        st.info(
            "No hay actividades todavía.\n\n"
            "Ejecuta en tu Mac:\n```\npython3 sync.py --streams\n```\n"
            "(`--streams` descarga además las series de potencia/FC/cadencia para ver el detalle completo)."
        )
        return

    options = {f"{a['start_date'][:10]} — {a['name']}": a["id"] for a in cycling}
    selection = st.selectbox("Selecciona una actividad", list(options.keys()))
    activity_id = options[selection]
    act = next(a for a in cycling if a["id"] == activity_id)

    # Fetch detail streams if needed
    if client and not act.get("detail_fetched"):
        _fetch_streams(activity_id, client, act, ftp)
        act = next((a for a in get_activities(athlete_id=athlete.get("id")) if a["id"] == activity_id), act)

    watts = get_stream(activity_id, "watts")
    heartrate = get_stream(activity_id, "heartrate")
    cadence = get_stream(activity_id, "cadence")
    altitude = get_stream(activity_id, "altitude")
    latlng = get_stream(activity_id, "latlng")
    time_s = get_stream(activity_id, "time")

    cm = get_computed(activity_id)
    if not cm and watts:
        cm = compute_activity_metrics(watts, act.get("moving_time_s", 0), ftp)

    # KPI row
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Distancia", f"{(act.get('distance_m') or 0)/1000:.1f} km")
    c2.metric("Tiempo", format_duration(act.get("moving_time_s")))
    c3.metric("Desnivel", f"{act.get('elevation_gain_m') or 0:.0f} m")
    avg_w = act.get("avg_watts")
    np_val = (cm or {}).get("np_watts")
    c4.metric("Potencia media", f"{avg_w:.0f} W" if avg_w else "—")
    c5.metric("NP", f"{np_val:.0f} W" if np_val else "—")
    c6.metric("TSS", f"{(cm or {}).get('tss') or '—'}")
    c7.metric("FC media", f"{act.get('avg_heartrate') or '—'} lpm")

    st.divider()

    # Time-series charts
    if time_s and watts:
        st.plotly_chart(
            stream_line(time_s, watts, "Potencia", "Watts", rolling=30, color="#FC4C02"),
            use_container_width=True,
        )
    if time_s and heartrate:
        st.plotly_chart(
            stream_line(time_s, heartrate, "Frecuencia cardíaca", "lpm", color="#E91E63"),
            use_container_width=True,
        )
    if time_s and cadence:
        st.plotly_chart(
            stream_line(time_s, cadence, "Cadencia", "rpm", color="#9C27B0"),
            use_container_width=True,
        )
    if time_s and altitude:
        st.plotly_chart(elevation_area(time_s, altitude), use_container_width=True)

    # Zone breakdown
    col1, col2 = st.columns(2)
    if watts:
        pz = power_zones(watts, ftp)
        col1.plotly_chart(zone_donut(pz, "Zonas de potencia"), use_container_width=True)

    # HR zones: prefer Garmin's own zone data if available
    garmin_hz = get_hr_zones(activity_id)
    if garmin_hz:
        hz_dict = {z.get("zoneName", f"Z{i+1}"): z.get("secsInZone", 0)
                   for i, z in enumerate(garmin_hz)}
        col2.plotly_chart(zone_donut(hz_dict, "Zonas de FC (Garmin)"), use_container_width=True)
    elif heartrate:
        hz = hr_zones(heartrate, hr_threshold)
        col2.plotly_chart(zone_donut(hz, "Zonas de FC"), use_container_width=True)

    # Map
    st.subheader("Ruta")
    m = activity_map(latlng=latlng, polyline_enc=act.get("map_polyline"))
    if m:
        st_folium(m, use_container_width=True, height=420)
    else:
        st.info("No hay datos de ruta GPS para esta actividad.")


def _fetch_streams(activity_id, client, act: dict, ftp: int):
    """Fetch detail data from Garmin for a single activity (shared logic)."""
    from data.stream_processor import fetch_and_store_activity_detail
    try:
        with st.spinner("Cargando detalle de la actividad desde Garmin..."):
            found = fetch_and_store_activity_detail(client, activity_id, act, ftp)
            if not found:
                st.info("Esta actividad no tiene streams de potencia disponibles.")
    except Exception as e:
        st.warning(f"No se pudo cargar el detalle: {e}")
