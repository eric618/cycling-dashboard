import streamlit as st
import pandas as pd
from data.cache import get_activities_cached, get_computed_batch
from data.processor import ctl_atl
from components.charts import (
    ftp_trend_line, ctl_atl_chart, tss_weekly_bar, monthly_distance_bar
)


def render(athlete: dict):
    st.title("Tendencias")

    activities = get_activities_cached(athlete_id=athlete.get("id"))
    if not activities:
        st.info(
            "No hay actividades todavía.\n\n"
            "Ejecuta en tu Mac:\n```\npython3 sync.py\n```"
        )
        return

    # Merge computed metrics (single batch query instead of N queries)
    computed = get_computed_batch([a["id"] for a in activities])
    for act in activities:
        cm = computed.get(act["id"])
        if cm:
            act.update(cm)

    st.subheader("Forma física")
    st.caption("Evolución de tu FTP estimado y de la carga de entrenamiento semanal (TSS).")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(ftp_trend_line(activities), use_container_width=True)
    with col2:
        st.plotly_chart(tss_weekly_bar(activities), use_container_width=True)

    st.divider()

    st.subheader("Fitness / Fatiga / Forma (CTL · ATL · TSB)")
    st.caption("CTL = carga crónica (42 días) · ATL = carga aguda (7 días) · TSB = forma (CTL − ATL).")
    # CTL / ATL
    tss_by_date = {}
    for act in activities:
        date = (act.get("start_date") or "")[:10]
        tss_val = act.get("tss") or 0
        if date:
            tss_by_date[date] = tss_by_date.get(date, 0) + tss_val

    dates, ctl, atl = ctl_atl(tss_by_date)
    if dates:
        st.plotly_chart(ctl_atl_chart(dates, ctl, atl), use_container_width=True)
    else:
        st.info("Sincroniza actividades con datos de potencia para ver CTL/ATL.")

    st.divider()
    st.subheader("Volumen mensual")
    st.caption("Distancia total recorrida por mes.")
    st.plotly_chart(monthly_distance_bar(activities), use_container_width=True)
