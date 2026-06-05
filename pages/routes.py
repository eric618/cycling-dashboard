import streamlit as st
import pandas as pd
from data.cache import get_activities, get_computed
from components.maps import multi_activity_map
from streamlit_folium import st_folium


def render(athlete: dict):
    st.title("Rutas")

    activities = get_activities(athlete_id=athlete.get("id"))
    if not activities:
        st.info("No hay actividades cargadas.")
        return

    for act in activities:
        cm = get_computed(act["id"])
        if cm:
            act.update(cm)

    # Filters
    df = pd.DataFrame(activities)
    df["start_date"] = pd.to_datetime(df["start_date"])

    col1, col2 = st.columns(2)
    min_date = df["start_date"].min().date()
    max_date = df["start_date"].max().date()
    with col1:
        date_from = st.date_input("Desde", min_date)
    with col2:
        date_to = st.date_input("Hasta", max_date)

    mask = (df["start_date"].dt.date >= date_from) & (df["start_date"].dt.date <= date_to)
    filtered = df[mask].to_dict("records")

    acts_with_map = [a for a in filtered if a.get("map_polyline")]
    st.caption(f"{len(acts_with_map)} actividades con ruta en el período seleccionado")

    if acts_with_map:
        m = multi_activity_map(acts_with_map)
        st_folium(m, use_container_width=True, height=550)
    else:
        st.info("No hay rutas disponibles para el período seleccionado.")
