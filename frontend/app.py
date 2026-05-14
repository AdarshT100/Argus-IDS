# filename: frontend/app.py
# purpose: Streamlit UI — calls FastAPI only, no direct model imports (§7)
# governed by: §7, §7.1, §9.1 (cold start /health check)

import os
import streamlit as st

# FastAPI base URL — set via env var for deployment flexibility (§9)
API_BASE_URL: str = os.environ.get("ARGUS_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Argus-IDS",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("Argus-IDS")
st.caption("Explainable AI-driven IoT Gateway Intrusion Detection")

# TODO (Week 3): port full UI from prototype frontend, replace all direct model
# calls with FastAPI requests. Implement /health cold-start spinner (§9.1).
# Embed JS alert dashboard via st.components.v1.html (§7.1).

st.info("Frontend stub — full implementation in Week 3.")