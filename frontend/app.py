# filename: frontend/app.py
# purpose: Streamlit UI — calls FastAPI only, no direct model imports (§7)
# governed by: §7, §7.1, §9.1 (cold start /health check)

import os
from textwrap import dedent
import streamlit as st

# ── Config ──────────────────────────────────────────────────────────────────────
ARGUS_API_URL: str = os.environ.get("ARGUS_API_URL", "http://localhost:8000")

# ── Page config ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Argus-IDS",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Section 1: Global CSS + Design System ───────────────────────────────────────
st.markdown(dedent("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@300;400;500;600&display=swap');

/* ── Design tokens ── */
:root {
    --bg:              #F8FAFC;
    --bg-card:         #FFFFFF;
    --bg-card-alt:     #F1F5F9;
    --bg-card-hover:   #FAFCFF;
    --border:          #E2E8F0;
    --border-strong:   #CBD5E1;
    --text-primary:    #0F172A;
    --text-secondary:  #475569;
    --text-muted:      #94A3B8;
    --accent:          #1D4ED8;
    --accent-hover:    #1E40AF;
    --accent-light:    #EFF6FF;
    --accent-mid:      #DBEAFE;

    --high:            #DC2626;
    --high-bg:         rgba(220, 38, 38, 0.07);
    --high-border:     rgba(220, 38, 38, 0.25);
    --medium:          #D97706;
    --medium-bg:       rgba(217, 119, 6, 0.07);
    --medium-border:   rgba(217, 119, 6, 0.25);
    --low:             #16A34A;
    --low-bg:          rgba(22, 163, 74, 0.07);
    --low-border:      rgba(22, 163, 74, 0.25);
    --anomaly:         #7C3AED;
    --anomaly-bg:      rgba(124, 58, 237, 0.07);
    --anomaly-border:  rgba(124, 58, 237, 0.25);

    --mono:   'JetBrains Mono', monospace;
    --sans:   'DM Sans', sans-serif;
    --radius:    12px;
    --radius-sm:  8px;
    --radius-lg: 16px;

    --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-md: 0 4px 16px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(15, 23, 42, 0.05);
    --shadow-lg: 0 10px 32px rgba(15, 23, 42, 0.10), 0 4px 12px rgba(15, 23, 42, 0.06);
}

/* ── Base reset ── */
html, body, [class*="css"] {
    font-family: var(--sans) !important;
    color: var(--text-primary) !important;
}
.stApp {
    background-color: var(--bg) !important;
}
#MainMenu, footer, header { visibility: hidden; }

.block-container {
    padding: 0 2.5rem 5rem !important;
    max-width: 1480px !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--bg-card) !important;
    border-right: 1px solid var(--border) !important;
    padding-top: 1.5rem !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding: 0 1.2rem !important;
}
[data-testid="stSidebar"] label {
    font-family: var(--sans) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    letter-spacing: 0.02em !important;
    text-transform: uppercase !important;
}

/* ── Buttons ── */
.stButton > button {
    font-family: var(--sans) !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    background: var(--accent) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: 10px 22px !important;
    width: 100% !important;
    transition: all 0.18s ease !important;
    letter-spacing: 0.01em !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    background: var(--accent-hover) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(29, 78, 216, 0.28) !important;
}
.stButton > button:active {
    transform: translateY(0) !important;
}

/* Secondary button variant */
.btn-secondary > button {
    background: var(--bg-card) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border-strong) !important;
    box-shadow: var(--shadow-xs) !important;
}
.btn-secondary > button:hover {
    background: var(--bg-card-alt) !important;
    color: var(--text-primary) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* Danger button variant */
.btn-danger > button {
    background: var(--high-bg) !important;
    color: var(--high) !important;
    border: 1px solid var(--high-border) !important;
}
.btn-danger > button:hover {
    background: rgba(220, 38, 38, 0.12) !important;
    box-shadow: 0 4px 14px rgba(220, 38, 38, 0.14) !important;
}

/* ── DataFrames ── */
.stDataFrame {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
}
.stDataFrame thead th {
    font-family: var(--mono) !important;
    background: var(--bg-card-alt) !important;
    color: var(--text-muted) !important;
    font-size: 0.60rem !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    font-weight: 500 !important;
    border-bottom: 1px solid var(--border) !important;
    padding: 12px 16px !important;
}
.stDataFrame tbody td {
    font-family: var(--mono) !important;
    font-size: 0.75rem !important;
    color: var(--text-secondary) !important;
    padding: 10px 16px !important;
}
.stDataFrame tbody tr:hover td {
    background: var(--accent-light) !important;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: var(--accent) !important;
}

/* ── Headings ── */
h1, h2, h3, h4, h5 {
    font-family: var(--sans) !important;
    color: var(--text-primary) !important;
    font-weight: 700 !important;
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 2rem 0 !important;
}

/* ── Plotly chart container ── */
[data-testid="stPlotlyChart"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ── Streamlit metric — hidden in favour of HTML cards ── */
[data-testid="metric-container"] { display: none !important; }

/* ── Multiselect ── */
[data-testid="stMultiSelect"] > div {
    border-color: var(--border-strong) !important;
    border-radius: var(--radius-sm) !important;
    font-family: var(--sans) !important;
    font-size: 0.82rem !important;
}

/* ── Reusable: section header ── */
.argus-section-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin: 2.4rem 0 1.2rem;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
}
.argus-section-header .title {
    font-family: 'DM Sans', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.01em;
}
.argus-section-header .subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.60rem;
    font-weight: 400;
    color: #94A3B8;
    letter-spacing: 0.10em;
    text-transform: uppercase;
}

/* ── Severity badge ── */
.sev-HIGH   { color: #DC2626; background: rgba(220,38,38,0.07);  border: 1px solid rgba(220,38,38,0.25); }
.sev-MEDIUM { color: #D97706; background: rgba(217,119,6,0.07);  border: 1px solid rgba(217,119,6,0.25); }
.sev-LOW    { color: #16A34A; background: rgba(22,163,74,0.07);  border: 1px solid rgba(22,163,74,0.25); }
.sev-ANOMALY{ color: #7C3AED; background: rgba(124,58,237,0.07); border: 1px solid rgba(124,58,237,0.25); }
</style>
"""), unsafe_allow_html=True)

# ── Section 2: Navbar ───────────────────────────────────────────────────────────
import datetime
import requests
import streamlit as st
import os

ARGUS_API_URL: str = os.environ.get("ARGUS_API_URL", "http://localhost:8000")

# ── Navbar + Health Banner CSS ───────────────────────────────────────────────────
# Injected as a plain string — NO f-string — so curly braces are safe
st.markdown("""
<style>
.argus-navbar {
    position: sticky;
    top: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 0 2.5rem;
    height: 60px;
    background: rgba(255,255,255,0.92);
    backdrop-filter: blur(12px) saturate(1.6);
    -webkit-backdrop-filter: blur(12px) saturate(1.6);
    border-bottom: 1px solid var(--border);
    box-shadow: 0 1px 0 rgba(15,23,42,0.04), 0 2px 12px rgba(15,23,42,0.05);
    margin: 0 -2.5rem 1.8rem;
}
.nav-left {
    display: flex; align-items: center;
    gap: 12px; flex-shrink: 0;
}
.nav-logo-wrap {
    width: 36px; height: 36px;
    background: var(--accent);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 2px 8px rgba(29,78,216,0.30);
    flex-shrink: 0;
}
.nav-wordmark { display: flex; flex-direction: column; gap: 1px; line-height: 1; }
.nav-title {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.95rem; font-weight: 700;
    color: var(--text-primary); letter-spacing: 0.12em;
}
.nav-subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.60rem; font-weight: 400;
    color: var(--text-muted); letter-spacing: 0.08em; text-transform: uppercase;
}
.nav-right { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
.nav-timestamp {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem; color: var(--text-muted);
    letter-spacing: 0.04em; white-space: nowrap;
}
.nav-model-badge {
    display: flex; align-items: center; gap: 5px;
    padding: 4px 10px;
    background: var(--accent-light); border: 1px solid var(--accent-mid);
    border-radius: 999px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.64rem; font-weight: 500;
    color: var(--accent); white-space: nowrap; letter-spacing: 0.03em;
}
.nav-model-ver { opacity: 0.6; }
.nav-status {
    display: flex; align-items: center; gap: 7px;
    padding: 4px 11px 4px 8px;
    background: var(--bg-card-alt); border: 1px solid var(--border);
    border-radius: 999px; white-space: nowrap;
}
.nav-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-online  { background: #16A34A; box-shadow: 0 0 0 2px #bbf7d0; }
.dot-offline { background: #DC2626; box-shadow: 0 0 0 2px #fecaca; }
.dot-unknown { background: #94A3B8; box-shadow: 0 0 0 2px #e2e8f0; }
.dot-online.pulse { animation: navPulse 2.2s ease-in-out infinite; }
@keyframes navPulse {
    0%,100% { box-shadow: 0 0 0 2px #bbf7d0; }
    50%      { box-shadow: 0 0 0 4px #bbf7d0; }
}
.nav-status-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.64rem; font-weight: 500; letter-spacing: 0.04em;
}
.label-online  { color: #16A34A; }
.label-offline { color: #DC2626; }
.label-unknown { color: #94A3B8; }
.nav-spacer { flex: 1; }

/* ── Health banner ── */
.argus-health-banner {
    display: flex; align-items: center; gap: 14px;
    padding: 13px 20px;
    border-radius: var(--radius);
    margin-bottom: 1.6rem;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.82rem; font-weight: 500;
    border: 1px solid;
    animation: bannerSlide 0.3s ease;
}
@keyframes bannerSlide {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0);    }
}
.argus-health-banner.online {
    background: rgba(22,163,74,0.06);
    border-color: rgba(22,163,74,0.25); color: #15803d;
}
.argus-health-banner.offline {
    background: rgba(220,38,38,0.06);
    border-color: rgba(220,38,38,0.25); color: #b91c1c;
}
.banner-icon { font-size: 1rem; flex-shrink: 0; }
.banner-text { flex: 1; line-height: 1.45; }
.banner-text strong {
    font-weight: 700; display: block; font-size: 0.84rem; margin-bottom: 1px;
}
.banner-text span {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem; opacity: 0.75;
}
</style>
""", unsafe_allow_html=True)


# ── Navbar HTML — f-string used only for dynamic runtime values ──────────────────
def _render_navbar() -> None:
    _now    = datetime.datetime.now().strftime("%d %b %Y  %H:%M")
    _status = st.session_state.get("backend_status", "unknown")
    _model  = st.session_state.get("model_name", "")
    _ver    = st.session_state.get("model_version", "")

    _labels = {"online": "Online", "offline": "Offline", "unknown": "Unknown"}
    _label  = _labels.get(_status, "Unknown")
    _pulse  = " pulse" if _status == "online" else ""

    if _model:
        _ver_html = f'<span class="nav-model-ver">&nbsp;{_ver}</span>' if _ver else ""
        _badge = (
            '<div class="nav-model-badge">'
            '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
            'stroke-linejoin="round" style="opacity:0.7">'
            '<path d="M12 2L2 7l10 5 10-5-10-5z"/>'
            '<path d="M2 17l10 5 10-5"/>'
            '<path d="M2 12l10 5 10-5"/>'
            f'</svg>{_model}{_ver_html}</div>'
        )
    else:
        _badge = ""

    st.markdown(
        f'<nav class="argus-navbar">'
        f'<div class="nav-left">'
        f'<div class="nav-logo-wrap">'
        f'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
        f'stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        f'<path d="M9 12l2 2 4-4" stroke-width="2.2"/>'
        f'</svg></div>'
        f'<div class="nav-wordmark">'
        f'<span class="nav-title">ARGUS&#8209;IDS</span>'
        f'<span class="nav-subtitle">Intrusion Detection System</span>'
        f'</div></div>'
        f'<div class="nav-spacer"></div>'
        f'<div class="nav-right">'
        f'<span class="nav-timestamp">&#128344;&nbsp;{_now}</span>'
        f'{_badge}'
        f'<div class="nav-status">'
        f'<div class="nav-status-dot dot-{_status}{_pulse}"></div>'
        f'<span class="nav-status-label label-{_status}">{_label}</span>'
        f'</div></div></nav>',
        unsafe_allow_html=True,
    )


_render_navbar()


# ── Section 3: Health Check Banner ──────────────────────────────────────────────
# governed by: §9.1

def _do_health_check() -> None:
    """
    GET /health  →  { "status": "ok", "model": "...", "version": "..." }
    Sets session_state keys: backend_status, health_checked,
                             model_name, model_version, health_error
    """
    try:
        resp = requests.get(f"{ARGUS_API_URL}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            st.session_state["backend_status"] = "online"
            st.session_state["health_checked"] = True
            st.session_state["model_name"]     = data.get("model",   "Model")
            st.session_state["model_version"]  = data.get("version", "")
            st.session_state["health_error"]   = None
        else:
            raise ValueError(f"HTTP {resp.status_code}")
    except Exception as exc:
        st.session_state["backend_status"] = "offline"
        st.session_state["health_checked"] = False
        st.session_state["health_error"]   = str(exc)


if not st.session_state.get("health_checked", False):
    with st.spinner("Connecting to Argus backend…"):
        _do_health_check()
    st.rerun()   # flip navbar dot + model badge immediately


# ── Banner render ────────────────────────────────────────────────────────────────
_bs    = st.session_state.get("backend_status", "unknown")
_err   = st.session_state.get("health_error",   "")
_mname = st.session_state.get("model_name",     "—")
_mver  = st.session_state.get("model_version",  "")

if _bs == "online":
    _vs = f" &middot; v{_mver}" if _mver else ""
    st.markdown(
        f'<div class="argus-health-banner online">'
        f'<span class="banner-icon">&#9989;</span>'
        f'<div class="banner-text">'
        f'<strong>Backend Online</strong>'
        f'<span>{ARGUS_API_URL}&nbsp;&nbsp;&middot;&nbsp;&nbsp;model: {_mname}{_vs}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

else:
    st.markdown(
        f'<div class="argus-health-banner offline">'
        f'<span class="banner-icon">&#128308;</span>'
        f'<div class="banner-text">'
        f'<strong>Backend Offline &#8212; cannot reach Argus API</strong>'
        f'<span>{ARGUS_API_URL}&nbsp;&nbsp;&middot;&nbsp;&nbsp;{_err or "connection refused"}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    col_btn, col_pad = st.columns([1, 5])
    with col_btn:
        st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
        if st.button("&#8635;  Retry Connection", key="health_retry_btn"):
            for _k in ("health_checked", "backend_status", "health_error",
                       "model_name", "model_version"):
                st.session_state.pop(_k, None)
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── HARD GATE ───────────────────────────────────────────────────────────────
    st.stop()


# ── Sections 4–9 attach below this line ─────────────────────────────────────────
st.markdown(
    "<div style='font-family:JetBrains Mono,monospace;font-size:0.8rem;"
    "color:#94A3B8;padding:3rem 0;'>§2–§3 complete. "
    "Sections 4–9 build here.</div>",
    unsafe_allow_html=True,
)

