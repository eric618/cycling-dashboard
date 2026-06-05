import streamlit as st
from data.cache import init_db, get_activities, upsert_activity
from config import DEFAULT_FTP, DEFAULT_HR_THRESHOLD, GARMIN_EMAIL, GARMIN_PASSWORD

st.set_page_config(
    page_title="Cycling Dashboard",
    page_icon="🚴",
    layout="wide",
)

init_db()

# --- Garmin login ---
def _try_login(email: str, password: str):
    from garminconnect import Garmin, GarminConnectAuthenticationError
    try:
        with st.spinner("Conectando con Garmin Connect..."):
            client = Garmin(email, password)
            client.login()
            profile = client.get_full_name()
            st.session_state["garmin_client"] = client
            st.session_state["athlete"] = {
                "id": email,
                "fullname": profile or email,
            }
            st.rerun()
    except GarminConnectAuthenticationError:
        st.error("Credenciales incorrectas. Verifica tu email y contraseña de Garmin Connect.")
    except Exception as e:
        st.error(f"Error al conectar: {e}")


# --- Sidebar ---
with st.sidebar:
    st.title("🚴 Cycling Dashboard")
    st.divider()

    client = st.session_state.get("garmin_client")

    if not client:
        st.subheader("Iniciar sesión")
        with st.form("login_form"):
            email = st.text_input("Email de Garmin", value=GARMIN_EMAIL)
            password = st.text_input("Contraseña", type="password",
                                     value=GARMIN_PASSWORD)
            submitted = st.form_submit_button("Conectar", type="primary",
                                              use_container_width=True)
        if submitted:
            _try_login(email, password)
        st.stop()

    # Athlete info
    athlete = st.session_state.get("athlete", {})
    st.write(f"👤 **{athlete.get('fullname', 'Atleta')}**")

    with st.expander("Configuración"):
        ftp = st.number_input("FTP (W)", value=DEFAULT_FTP,
                              min_value=50, max_value=600, step=5)
        hr_threshold = st.number_input("FC umbral (lpm)",
                                       value=DEFAULT_HR_THRESHOLD,
                                       min_value=100, max_value=220, step=1)

    st.divider()

    if st.button("🔄 Sincronizar actividades", use_container_width=True):
        with st.spinner("Descargando actividades desde Garmin..."):
            try:
                from api.garmin_client import get_all_activities
                raw_acts = get_all_activities(client)
                for act in raw_acts:
                    upsert_activity(act, athlete_id=athlete.get("id", ""))
                st.success(f"✅ {len(raw_acts)} actividades sincronizadas.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al sincronizar: {e}")

    st.divider()

    page = st.radio(
        "Navegación",
        ["Resumen", "Detalle de actividad", "Tendencias", "Rutas"],
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# --- Page routing ---
athlete = st.session_state.get("athlete", {})
ftp = st.session_state.get("ftp", DEFAULT_FTP)
hr_threshold = st.session_state.get("hr_threshold", DEFAULT_HR_THRESHOLD)

if page == "Resumen":
    from pages.overview import render
    render(athlete=athlete, ftp=ftp, hr_threshold=hr_threshold)

elif page == "Detalle de actividad":
    from pages.activity_detail import render
    render(athlete=athlete, ftp=ftp, hr_threshold=hr_threshold,
           client=st.session_state.get("garmin_client"))

elif page == "Tendencias":
    from pages.trends import render
    render(athlete=athlete)

elif page == "Rutas":
    from pages.routes import render
    render(athlete=athlete)
