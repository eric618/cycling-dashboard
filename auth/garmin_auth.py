import streamlit as st
from garminconnect import Garmin, GarminConnectAuthenticationError
from config import GARMIN_EMAIL, GARMIN_PASSWORD


def get_client() -> Garmin | None:
    """Returns an authenticated Garmin client, cached in session_state."""
    if "garmin_client" in st.session_state:
        return st.session_state["garmin_client"]
    return None


def login(email: str, password: str) -> Garmin:
    client = Garmin(email, password)
    client.login()
    return client


def login_from_env() -> Garmin | None:
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        return None
    try:
        client = login(GARMIN_EMAIL, GARMIN_PASSWORD)
        return client
    except GarminConnectAuthenticationError:
        return None


def logout():
    st.session_state.pop("garmin_client", None)
    st.session_state.pop("athlete", None)
    st.rerun()
