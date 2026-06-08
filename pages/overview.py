import streamlit as st
import pandas as pd
from data.cache import get_activities_cached, get_computed_batch, get_streams_batch
from data.processor import power_zones, hr_zones, format_duration, DEFAULT_FTP, DEFAULT_HR_THRESHOLD
from components.charts import (
    weekly_distance_bar, zone_donut, kpi_metric
)


def render(athlete: dict, ftp: int, hr_threshold: int):
    st.title("Resumen")

    activities = get_activities_cached(athlete_id=athlete.get("id"))
    if not activities:
        st.info(
            "No hay actividades todavía.\n\n"
            "Ejecuta en tu Mac (ver barra lateral para más detalles):\n"
            "```\npython3 sync.py\n```"
        )
        return

    # Merge computed metrics (single batch query instead of N queries)
    activity_ids = [a["id"] for a in activities]
    computed = get_computed_batch(activity_ids)
    for act in activities:
        cm = computed.get(act["id"])
        if cm:
            act.update(cm)

    df = pd.DataFrame(activities)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["km"] = df["distance_m"] / 1000
    df["elevation_m"] = df["elevation_gain_m"]

    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    ytd = df[df["start_date"].dt.year == now.year]

    # KPI row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rides este año", len(ytd))
    c2.metric("Distancia (km)", f"{ytd['km'].sum():.0f}")
    c3.metric("Elevación (m)", f"{ytd['elevation_m'].sum():.0f}")
    c4.metric("Tiempo (h)", f"{ytd['moving_time_s'].sum() / 3600:.0f}")
    best_ftp = df["ftp_estimate"].dropna().max() if "ftp_estimate" in df else None
    c5.metric("FTP estimado", f"{best_ftp:.0f} W" if best_ftp else "—")

    st.divider()
    st.subheader("Actividad reciente")
    st.caption("Distancia semanal y distribución de tu esfuerzo por zonas (acumulado).")

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(weekly_distance_bar(activities), use_container_width=True)
    with col2:
        # Aggregate zone seconds — batch-fetch streams (1 query per type, cached)
        agg_power = {}
        agg_hr = {}
        with st.spinner("Calculando zonas agregadas..."):
            watts_streams = get_streams_batch(activity_ids, "watts")
            hr_streams = get_streams_batch(activity_ids, "heartrate")
            for w in watts_streams.values():
                pz = power_zones(w, ftp)
                for k, v in pz.items():
                    agg_power[k] = agg_power.get(k, 0) + v
            for hr in hr_streams.values():
                hz = hr_zones(hr, hr_threshold)
                for k, v in hz.items():
                    agg_hr[k] = agg_hr.get(k, 0) + v

        if sum(agg_power.values()) > 0:
            st.plotly_chart(zone_donut(agg_power, "Zonas de potencia (total)"), use_container_width=True)
        elif sum(agg_hr.values()) > 0:
            st.plotly_chart(zone_donut(agg_hr, "Zonas de FC (total)"), use_container_width=True)
        else:
            st.info("Sincroniza actividades con streams para ver zonas.")

    st.divider()
    st.subheader("Últimas actividades")
    st.caption("Tus 20 salidas más recientes con sus métricas principales.")

    display_cols = ["start_date", "name", "km", "moving_time_s",
                    "elevation_m", "avg_watts", "avg_heartrate", "tss"]
    available = [c for c in display_cols if c in df.columns]
    recent = df[available].head(20).copy()
    recent["start_date"] = recent["start_date"].dt.strftime("%Y-%m-%d")
    recent["moving_time_s"] = recent["moving_time_s"].apply(format_duration)
    recent.columns = [c.replace("_", " ").title() for c in recent.columns]
    st.dataframe(recent, use_container_width=True, hide_index=True)
