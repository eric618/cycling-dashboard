import streamlit as st
import pandas as pd
from data.cache import get_activities_cached, get_computed_batch
from data.processor import format_duration
from components.maps import multi_activity_map
from streamlit_folium import st_folium


def render(athlete: dict):
    st.title("Rutas")

    activities = get_activities_cached(athlete_id=athlete.get("id"))
    if not activities:
        st.info(
            "No hay actividades todavía.\n\n"
            "Ejecuta en tu Mac:\n```\npython3 sync.py\n```"
        )
        return

    computed = get_computed_batch([a["id"] for a in activities])
    for act in activities:
        cm = computed.get(act["id"])
        if cm:
            act.update(cm)

    st.subheader("Mapa de rutas")
    st.caption("Todas tus rutas en un mismo mapa, coloreadas según la carga de entrenamiento (TSS).")

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

    st.divider()
    _render_route_comparator(activities)


def _render_route_comparator(activities: list[dict]):
    """
    Compara actividades agrupadas por nombre (proxy de "misma ruta") para
    evidenciar progreso en salidas repetidas: tiempo, potencia media, FC media.
    """
    st.subheader("Comparador de rutas repetidas")
    st.caption("Agrupa actividades con el mismo nombre y compara su evolución (tiempo, potencia media, FC media).")

    # Group by name, keep groups with 2+ activities
    groups: dict[str, list[dict]] = {}
    for a in activities:
        name = (a.get("name") or "Sin nombre").strip()
        groups.setdefault(name, []).append(a)
    repeated = {name: acts for name, acts in groups.items() if len(acts) >= 2}

    if not repeated:
        st.info("No se encontraron rutas repetidas (mismo nombre de actividad) para comparar todavía.")
        return

    # Sort group names by frequency (most repeated first)
    sorted_names = sorted(repeated.keys(), key=lambda n: -len(repeated[n]))
    options = {f"{name} ({len(repeated[name])} actividades)": name for name in sorted_names}
    selection = st.selectbox("Selecciona una ruta", list(options.keys()))
    group_name = options[selection]
    group = sorted(repeated[group_name], key=lambda a: a["start_date"])

    labels = {f"{a['start_date'][:10]}": a["id"] for a in group}
    chosen = st.multiselect(
        "Selecciona las actividades a comparar (por defecto, las últimas 5)",
        list(labels.keys()),
        default=list(labels.keys())[-5:],
    )
    if not chosen:
        st.info("Selecciona al menos una actividad para comparar.")
        return

    chosen_ids = {labels[d] for d in chosen}
    selected_acts = [a for a in group if a["id"] in chosen_ids]

    rows = []
    for a in selected_acts:
        rows.append({
            "Fecha": a["start_date"][:10],
            "Distancia": f"{(a.get('distance_m') or 0) / 1000:.1f} km",
            "Tiempo": format_duration(a.get("moving_time_s")),
            "Potencia media": f"{a.get('avg_watts'):.0f} W" if a.get("avg_watts") else "—",
            "FC media": f"{a.get('avg_heartrate'):.0f} lpm" if a.get("avg_heartrate") else "—",
            "TSS": a.get("tss") if a.get("tss") is not None else "—",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Trend chart: moving time across selected activities
    import plotly.graph_objects as go
    times = [(a["start_date"][:10], (a.get("moving_time_s") or 0) / 60) for a in selected_acts]
    times.sort()
    if len(times) >= 2:
        dates, mins = zip(*times)
        fig = go.Figure(go.Scatter(
            x=dates, y=mins, mode="lines+markers",
            line=dict(color="#FC4C02", width=2), marker=dict(size=8),
            hovertemplate="%{x}<br>%{y:.0f} min<extra></extra>",
        ))
        fig.update_layout(
            title=f"Evolución del tiempo — {group_name}",
            xaxis_title=None, yaxis_title="Minutos",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
        delta = mins[-1] - mins[0]
        if delta < 0:
            st.caption(f"⏱️ Has mejorado tu tiempo en esta ruta en **{abs(delta):.0f} minutos** desde la primera vez seleccionada.")
        elif delta > 0:
            st.caption(f"⏱️ Tu tiempo en esta ruta aumentó en **{delta:.0f} minutos** respecto a la primera vez seleccionada.")
