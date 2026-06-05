import streamlit as st
import pandas as pd
from data.cache import get_activities, get_computed
from data.processor import ctl_atl
from components.charts import (
    ftp_trend_line, ctl_atl_chart, tss_weekly_bar, monthly_distance_bar
)


def render(athlete: dict):
    st.title("Tendencias")

    activities = get_activities(athlete_id=athlete.get("id"))
    if not activities:
        st.info("No hay actividades cargadas.")
        return

    # Merge computed metrics
    for act in activities:
        cm = get_computed(act["id"])
        if cm:
            act.update(cm)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(ftp_trend_line(activities), use_container_width=True)
    with col2:
        st.plotly_chart(tss_weekly_bar(activities), use_container_width=True)

    st.divider()

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
    st.plotly_chart(monthly_distance_bar(activities), use_container_width=True)
