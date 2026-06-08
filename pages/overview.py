import streamlit as st
import pandas as pd
from data.cache import get_activities_cached, get_computed_batch, get_streams_batch
from data.processor import (
    power_zones, hr_zones, format_duration, ctl_atl,
    fitness_fatigue_form_labels, recommend_next_session, detect_milestones,
    HEURISTIC_DISCLAIMER, DEFAULT_FTP, DEFAULT_HR_THRESHOLD,
)
from components.charts import weekly_distance_bar, zone_donut


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

    # =========================================================================
    # 1. PANEL DE ESTADO — lo primero que se ve: ¿cómo estoy y qué hago ahora?
    # =========================================================================
    _render_status_panel(activities, computed, df, now)

    st.divider()

    # =========================================================================
    # 2. KPIs — la fotografía general (ya no lidera, pero sigue disponible)
    # =========================================================================
    st.subheader("Tu temporada en números")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rides este año", len(ytd))
    c2.metric("Distancia (km)", f"{ytd['km'].sum():.0f}")
    c3.metric("Elevación (m)", f"{ytd['elevation_m'].sum():.0f}")
    c4.metric("Tiempo (h)", f"{ytd['moving_time_s'].sum() / 3600:.0f}")
    best_ftp = df["ftp_estimate"].dropna().max() if "ftp_estimate" in df else None
    c5.metric("FTP estimado", f"{best_ftp:.0f} W" if best_ftp else "—")
    st.caption("Estos números son un buen resumen emocional de tu temporada — "
               "para entender si estás progresando de verdad, mira el panel de estado de arriba y la página de Análisis.")

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

    # =========================================================================
    # 3. Detalles secundarios — distribución de zonas y volumen acumulado
    #    (disponibles, pero ya no protagonistas — son métricas más "emocionales"
    #    que accionables, según el feedback recibido)
    # =========================================================================
    with st.expander("📊 Distribución de esfuerzo y volumen acumulado"):
        st.caption("Distancia semanal y distribución de tu esfuerzo por zonas (acumulado histórico).")
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(weekly_distance_bar(activities), use_container_width=True)
        with col2:
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


def _render_status_panel(activities: list[dict], computed: dict, df: pd.DataFrame, now: pd.Timestamp):
    """
    Panel de estado accionable: traduce CTL/ATL/TSB a lenguaje simple,
    sugiere qué hacer en la próxima sesión, y destaca hitos recientes.
    Este es el primer contenido que ve el usuario al abrir el dashboard.
    """
    st.subheader("¿Cómo estoy y qué debería hacer ahora?")

    # --- Build TSS-by-date series for CTL/ATL/TSB ---
    tss_by_date = {}
    for act in activities:
        date = (act.get("start_date") or "")[:10]
        tss_val = act.get("tss") or 0
        if date:
            tss_by_date[date] = tss_by_date.get(date, 0) + tss_val

    dates, ctl_vals, atl_vals = ctl_atl(tss_by_date)

    if not dates:
        st.info(
            "Todavía no hay suficientes datos de potencia para calcular tu estado de forma. "
            "Sincroniza actividades con streams (`python3 sync.py --streams`) para activar este panel."
        )
        return

    ctl, atl = ctl_vals[-1], atl_vals[-1]
    tsb = ctl - atl
    labels = fitness_fatigue_form_labels(ctl, atl, tsb)

    # Recent load (last 7 days) for the recommendation engine
    cutoff = now - pd.Timedelta(days=7)
    recent_df = df[df["start_date"] >= cutoff]
    recent_hours = recent_df["moving_time_s"].sum() / 3600 if not recent_df.empty else 0
    recent_tss = recent_df["tss"].sum() if "tss" in recent_df.columns else 0

    rec = recommend_next_session(ctl, atl, tsb, recent_hours=recent_hours, recent_tss=recent_tss)

    # --- Status row: Fitness / Fatiga / Forma in plain language ---
    s1, s2, s3 = st.columns(3)
    s1.metric("Fitness (forma física de fondo)", labels["fitness"], help=f"CTL ≈ {labels['ctl']}")
    s2.metric("Fatiga acumulada", labels["fatigue"], help=f"ATL ≈ {labels['atl']}")
    s3.metric("Forma actual", labels["form"], help=f"TSB ≈ {labels['tsb']} (CTL − ATL)")

    # --- Recommendation card ---
    st.markdown(
        f"""
<div style="border-left: 4px solid {rec['color']}; padding: 0.75rem 1rem; border-radius: 4px; background-color: rgba(255,255,255,0.03); margin-top: 0.5rem;">
<strong>👉 Sugerencia para tu próxima sesión: {rec['label']}</strong><br>
<span style="opacity:0.85;">{rec['detail']}</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption(HEURISTIC_DISCLAIMER)

    # --- Milestones / PRs ---
    milestones = detect_milestones(activities, computed, power_curve_history=None, lookback_days=30)
    if milestones:
        st.markdown("##### 🏅 Hitos recientes (últimos 30 días)")
        for m in milestones[:4]:
            st.success(f"{m['icon']} **{m['title']}** — {m['detail']}")
