import os
from dotenv import load_dotenv

load_dotenv()

def _secret(key: str, default: str = "") -> str:
    """Read from Streamlit secrets first, fall back to env vars."""
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)

GARMIN_EMAIL    = _secret("GARMIN_EMAIL")
GARMIN_PASSWORD = _secret("GARMIN_PASSWORD")

SUPABASE_URL = _secret("SUPABASE_URL")
SUPABASE_KEY = _secret("SUPABASE_KEY")

DEFAULT_FTP          = int(_secret("FTP_WATTS", "250"))
DEFAULT_HR_THRESHOLD = int(_secret("HR_THRESHOLD", "170"))
