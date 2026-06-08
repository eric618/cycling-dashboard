import streamlit as st
from data.cache import get_activities_cached, get_stream
from data.processor import (
    power_curve, decoupling, detect_intervals, power_zones,
    POWER_CURVE_DURATIONS,
)
from components.charts import (
    power_curve_chart, decoupling_trend_chart, zone_trend_stacked_bar,
)
import pandas as pd


@st.cache_data(ttl=600, show_spinner=False)
def _load_power_streams(activity_ids: tuple) -> dict:
    """Batch-load watts streams for a set of activities (cached)."""
    return {aid: s for aid in activity_ids if (s := get_stream(aid, "watts"))}


@st.cache_data(ttl=600, show_spinner=False)
def _load_hr_streams(activity_ids: tuple) -> dict:
    return {aid: s for aid in activity_ids if (s := get_stream(aid, "heartrate"))}


@st.cache_data(ttl=600, show_spinner=False)
def _compute_power_curve(activity_ids: tuple) -> dict:
    streams = _load_power_streams(activity_ids)
    return power_curve(streams, POWER_CURVE_DURATIONS)


def render(athlete: dict, ftp: int, hr_threshold: int):
    st.title("Análisis")
    st.caption("Insights basados en las series de potencia y FC de tus salidas — pensado para preparar el próximo entreno.")

    activities = get_activities_cached(athlete_id=athlete.get("id"))
    cycling = [a for a in activities if a.get("detail_fetched")]

    if not cycling:
        st.info(
            "Todavía no hay streams descargados para analizar.\n\n"
            "Ejecuta en tu Mac:\n```\npython3 sync.py --streams\n```\n"
            "para descargar las series de potencia/FC de tus actividades."
        )
        return

    # Limit to most recent N with detail to keep things fast
    recent = cycling[:120]
    activity_ids = tuple(a["id"] for a in recent)

    # --- 1. Power curve ---
    st.subheader("Curva de potencia")
    st.caption("Mejor potencia sostenida histórica para distintas duraciones — tu \"perfil de fuerza\".")
    with st.spinner("Calculando curva de potencia..."):
        curve = _compute_power_curve(activity_ids)
    if any(v is not None for v in curve.values()):
        st.plotly_chart(power_curve_chart(curve), use_container_width=True)
    else:
        st.info("No hay suficientes datos de potencia para calcular la curva todavía.")

    st.divider()

    # --- 2. Decoupling trend ---
    st.subheader("Decoupling Pw:HR")
    st.caption(
        "Compara la relación potencia/FC entre la primera y segunda mitad de cada salida. "
        "Valores altos sugieren que tu FC sube más que tu potencia conforme avanza el esfuerzo (fatiga). "
        "Valores bajos/estables son señal de buena resistencia aeróbica."
    )
    watts_streams = _load_power_streams(activity_ids)
    hr_streams = _load_hr_streams(activity_ids)
    rows = []
    for a in recent:
        aid = a["id"]
        w = watts_streams.get(aid)
        h = hr_streams.get(aid)
        if not w or not h:
            continue
        d = decoupling(w, h)
        if d is not None:
            rows.append((a["start_date"][:10], d))
    if rows:
        rows.sort()
        dates, values = zip(*rows)
        st.plotly_chart(decoupling_trend_chart(list(dates), list(values)), use_container_width=True)
        avg_decoupling = sum(values) / len(values)
        st.caption(f"Promedio reciente: **{avg_decoupling:.1f}%** "
                   f"({'buena estabilidad aeróbica' if avg_decoupling < 5 else 'posible margen de mejora en resistencia aeróbica'})")
    else:
        st.info("Necesitas actividades con potencia y FC simultáneas (>10 min) para ver esta métrica.")

    st.divider()

    # --- 3. Zone trend over time ---
    st.subheader("Evolución de zonas de potencia (semanal)")
    st.caption("Cómo se distribuye tu tiempo de entrenamiento entre zonas a lo largo de las semanas.")
    zone_rows = []
    for a in recent:
        aid = a["id"]
        w = watts_streams.get(aid)
        if not w:
            continue
        zone_rows.append((a["start_date"][:10], power_zones(w, ftp)))
    if zone_rows:
        df = pd.DataFrame([{"date": d, **z} for d, z in zone_rows])
        df["date"] = pd.to_datetime(df["date"])
        df["week"] = df["date"].dt.to_period("W").dt.start_time
        zone_cols = [c for c in df.columns if c not in ("date", "week")]
        weekly = df.groupby("week")[zone_cols].sum().reset_index()
        dates = [d.strftime("%Y-%m-%d") for d in weekly["week"]]
        zone_data = weekly[zone_cols].to_dict("records")
        st.plotly_chart(zone_trend_stacked_bar(dates, zone_data, "Minutos por zona de potencia (semanal)"),
                        use_container_width=True)
    else:
        st.info("No hay datos de potencia suficientes para mostrar la evolución por zonas.")

    st.divider()

    # --- 4. Interval detection ---
    st.subheader("Detección de intervalos")
    st.caption("Identifica tramos sostenidos de alta intensidad (≥ 88% FTP durante ≥ 90s) dentro de una salida.")
    options = {f"{a['start_date'][:10]} — {a['name']}": a["id"] for a in recent if watts_streams.get(a["id"])}
    if options:
        selection = st.selectbox("Selecciona una actividad para analizar sus intervalos", list(options.keys()))
        sel_id = options[selection]
        w = watts_streams.get(sel_id)
        intervals = detect_intervals(w, ftp)
        if intervals:
            table = [{
                "Inicio": f"{iv['start_s'] // 60}:{iv['start_s'] % 60:02d}",
                "Duración": f"{iv['duration_s'] // 60}min {iv['duration_s'] % 60}s",
                "Potencia media": f"{iv['avg_watts']:.0f} W",
                "% FTP": f"{iv['avg_watts'] / ftp * 100:.0f}%",
            } for iv in intervals]
            st.dataframe(table, use_container_width=True, hide_index=True)
            st.caption(f"Se detectaron **{len(intervals)}** intervalos sostenidos en esta actividad.")
        else:
            st.info("No se detectaron intervalos sostenidos por encima del umbral en esta actividad.")
    else:
        st.info("No hay actividades con datos de potencia disponibles para analizar intervalos.")
