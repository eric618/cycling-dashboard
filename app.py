import streamlit as st
from data.cache import init_db, get_activities
from config import DEFAULT_FTP, DEFAULT_HR_THRESHOLD

st.set_page_config(
    page_title="Cycling Dashboard",
    page_icon="🚴",
    layout="wide",
)

init_db()

# --- Sidebar ---
with st.sidebar:
    st.title("🚴 Cycling Dashboard")
    st.divider()

    # Athlete ID — usamos el email como identificador
    from config import GARMIN_EMAIL
    athlete_id = GARMIN_EMAIL or "default"
    athlete = {"id": athlete_id, "fullname": athlete_id.split("@")[0].title()}

    st.write(f"👤 **{athlete['fullname']}**")

    # Persist FTP / HR threshold across page navigations via session_state
    if "ftp" not in st.session_state:
        st.session_state["ftp"] = DEFAULT_FTP
    if "hr_threshold" not in st.session_state:
        st.session_state["hr_threshold"] = DEFAULT_HR_THRESHOLD

    with st.expander("⚙️ Configuración"):
        ftp = st.number_input("FTP (W)", min_value=50, max_value=600, step=5,
                              key="ftp")
        hr_threshold = st.number_input("FC umbral (lpm)",
                                       min_value=100, max_value=220, step=1,
                                       key="hr_threshold")

    st.divider()

    # Activity count info
    acts = get_activities(athlete_id=athlete_id, limit=1)
    if acts:
        total = len(get_activities(athlete_id=athlete_id))
        st.caption(f"📊 {total} actividades en base de datos")
        st.caption("Para sincronizar nuevos entrenos ejecuta en tu Mac:")
        st.code("python3 sync.py", language="bash")
    else:
        st.info("Sin datos aún.\n\nEjecuta en tu Mac:\n```\npython3 sync.py\n```")

    st.divider()

    page = st.radio(
        "Navegación",
        ["Resumen", "Detalle de actividad", "Análisis", "Tendencias", "Rutas"],
        label_visibility="collapsed",
    )

# --- Page routing ---
if page == "Resumen":
    from pages.overview import render
    render(athlete=athlete, ftp=ftp, hr_threshold=hr_threshold)

elif page == "Detalle de actividad":
    from pages.activity_detail import render
    render(athlete=athlete, ftp=ftp, hr_threshold=hr_threshold, client=None)

elif page == "Análisis":
    from pages.analysis import render
    render(athlete=athlete, ftp=ftp, hr_threshold=hr_threshold)

elif page == "Tendencias":
    from pages.trends import render
    render(athlete=athlete)

elif page == "Rutas":
    from pages.routes import render
    render(athlete=athlete)
