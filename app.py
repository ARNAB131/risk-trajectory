import time
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from simulator import generate_vitals
from risk_engine import RollingWindow, patient_thresholds, classify_level, infer_outcomes
from storage import init_db, save_vital, save_event, load_events

st.set_page_config(page_title="Risk Trajectory", layout="wide")

# ─────────────────────────────────────────────
#  PASSWORD PROTECTION
# ─────────────────────────────────────────────
VALID_USERNAME = "Admin"
VALID_PASSWORD = "admin123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "login_error" not in st.session_state:
    st.session_state.login_error = False

def do_login():
    u = st.session_state.get("inp_user", "")
    p = st.session_state.get("inp_pass", "")
    if u == VALID_USERNAME and p == VALID_PASSWORD:
        st.session_state.authenticated = True
        st.session_state.login_error = False
    else:
        st.session_state.login_error = True

if not st.session_state.authenticated:
    st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer    {visibility: hidden;}
        header    {visibility: hidden;}
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #0f172a 100%);
        }
        .lock-icon {
            font-size: 60px; text-align: center; margin-bottom: 6px;
            filter: drop-shadow(0 0 16px rgba(239,68,68,0.5));
        }
        .login-title {
            color: #f1f5f9; font-size: 26px; font-weight: 700;
            text-align: center; letter-spacing: 0.4px; margin-bottom: 4px;
        }
        .login-subtitle {
            color: #94a3b8; font-size: 13px; text-align: center; margin-bottom: 28px;
        }
        .protected-badge {
            display: inline-flex; align-items: center; gap: 6px;
            background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.35);
            color: #fca5a5; font-size: 11px; font-weight: 700;
            letter-spacing: 1.2px; text-transform: uppercase;
            padding: 4px 14px; border-radius: 999px; margin: 0 auto 26px; width: fit-content;
        }
        .stTextInput label {
            color: #94a3b8 !important; font-size: 13px !important; font-weight: 500 !important;
        }
        .stTextInput input {
            background: rgba(15,23,42,0.7) !important;
            border: 1px solid rgba(100,116,139,0.4) !important;
            border-radius: 10px !important; color: #f1f5f9 !important; font-size: 15px !important;
        }
        .stTextInput input:focus {
            border-color: rgba(239,68,68,0.6) !important;
            box-shadow: 0 0 0 3px rgba(239,68,68,0.1) !important;
        }
        .stButton > button {
            width: 100%;
            background: linear-gradient(135deg, #dc2626, #b91c1c) !important;
            color: white !important; border: none !important;
            border-radius: 10px !important; padding: 12px 0 !important;
            font-size: 15px !important; font-weight: 600 !important; margin-top: 6px;
            box-shadow: 0 4px 18px rgba(220,38,38,0.35) !important;
        }
        .login-error {
            background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.35);
            color: #fca5a5; border-radius: 8px; padding: 10px 14px;
            font-size: 13px; text-align: center; margin-top: 10px;
        }
        .login-footer {
            color: #475569; font-size: 12px; text-align: center; margin-top: 26px;
        }
    </style>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown('<div class="lock-icon">🔒</div>', unsafe_allow_html=True)
        st.markdown('<div class="protected-badge">🔴 &nbsp; System is Password Protected</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-title">Risk Trajectory</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">Authorised personnel only. Please sign in to continue.</div>', unsafe_allow_html=True)

        st.text_input("Username", key="inp_user", placeholder="Enter your username")
        st.text_input("Password", key="inp_pass", placeholder="Enter your password", type="password")
        st.button("🔓  Login", on_click=do_login)

        if st.session_state.login_error:
            st.markdown('<div class="login-error">❌ &nbsp; Invalid username or password. Please try again.</div>', unsafe_allow_html=True)

        st.markdown('<div class="login-footer">© Risk Trajectory · Secure Clinical Dashboard</div>', unsafe_allow_html=True)

    st.stop()   # nothing below runs until authenticated

# ─────────────────────────────────────────────
#  MAIN APP  (only reached after login)
# ─────────────────────────────────────────────

# ---- Patients (demo seed) ----
PATIENTS = [
    {"id": "P001", "name": "Patient 001", "profile": "normal",       "age": 45},
    {"id": "P002", "name": "Patient 002", "profile": "hypertensive", "age": 62},
    {"id": "P003", "name": "Patient 003", "profile": "athlete",      "age": 23},
    {"id": "P004", "name": "Patient 004", "profile": "critical",     "age": 70},
]

# ---- DB session ----
Session = init_db("sqlite:///risk_trajectory.db")

# ---- Session state init ----
if "sim_state" not in st.session_state:
    st.session_state.sim_state = {}
if "windows" not in st.session_state:
    st.session_state.windows = {}
if "history" not in st.session_state:
    st.session_state.history = {}

# ---- Sidebar controls ----
st.sidebar.title("Controls")

if st.sidebar.button("🔒 Logout"):
    st.session_state.authenticated = False
    st.rerun()

patient_id = st.sidebar.selectbox(
    "Select patient",
    [p["id"] for p in PATIENTS],
    format_func=lambda pid: f"{pid} — {next(x['name'] for x in PATIENTS if x['id']==pid)}"
)

patient = next(p for p in PATIENTS if p["id"] == patient_id)

auto        = st.sidebar.toggle("Live monitoring", value=True)
interval_ms = st.sidebar.slider("Refresh interval (ms)", 500, 5000, 1000, step=250)
persist_db  = st.sidebar.toggle("Persist to SQLite", value=True)

st.sidebar.caption("If the page feels static, keep Live monitoring ON.")

if auto:
    st_autorefresh(interval=interval_ms, key="rt_refresh")

if patient_id not in st.session_state.windows:
    st.session_state.windows[patient_id]   = RollingWindow(maxlen=120)
if patient_id not in st.session_state.sim_state:
    st.session_state.sim_state[patient_id] = {}
if patient_id not in st.session_state.history:
    st.session_state.history[patient_id]   = []

# ---- Generate next vitals tick ----
vitals  = generate_vitals(patient["profile"], st.session_state.sim_state[patient_id])
st.session_state.windows[patient_id].push(vitals)
rates   = st.session_state.windows[patient_id].rates_per_min()

th                    = patient_thresholds(patient["profile"])
level, reasons, score = classify_level(vitals, th, rates)
outcomes              = infer_outcomes(vitals, level, reasons)

title_map = {"green": "Stable", "yellow": "Warning", "orange": "High Risk", "red": "CRITICAL ALERT"}
title   = title_map[level]
explain = " | ".join(reasons[:4]) if reasons else "No abnormalities detected."

row = {
    "ts": pd.Timestamp.utcnow().isoformat(),
    "level": level,
    "risk_score": round(score, 1),
    **vitals,
    "d_hr_per_min":   round(rates["heart_rate"],        2),
    "d_spo2_per_min": round(rates["oxygen_saturation"], 2),
    "d_sys_per_min":  round(rates["bp_systolic"],       2),
    "d_temp_per_min": round(rates["temperature"],       2),
}

st.session_state.history[patient_id].append(row)
st.session_state.history[patient_id] = st.session_state.history[patient_id][-300:]

if persist_db:
    save_vital(Session, patient_id, vitals)
    if level in ("yellow", "orange", "red"):
        save_event(Session, patient_id, level, title, explain,
                   {"vitals": vitals, "rates": rates, "outcomes": outcomes})

# ---- UI ----
st.title("Risk Trajectory")

colA, colB, colC, colD = st.columns([2, 1, 1, 1])
with colA:
    st.subheader(f"{patient_id} — {patient['name']}")
    st.caption(f"Profile: {patient['profile']} • Age: {patient['age']}")
with colB:
    st.metric("Risk score", f"{score:.1f}/100")
with colC:
    st.metric("Level", title)
with colD:
    color = {"green": "✅", "yellow": "⚠️", "orange": "🟠", "red": "🚨"}[level]
    st.metric("Status", f"{color} {level.upper()}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Heart rate (bpm)",      f"{vitals['heart_rate']:.1f}")
c2.metric("Blood pressure (mmHg)", f"{vitals['bp_systolic']:.0f}/{vitals['bp_diastolic']:.0f}")
c3.metric("SpO₂ (%)",              f"{vitals['oxygen_saturation']:.1f}")
c4.metric("Temp (°C)",             f"{vitals['temperature']:.2f}")

left, right = st.columns([1.2, 1])
with left:
    st.subheader("Explainability")
    st.write(explain)
    st.subheader("Trend signals (Δ per minute)")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("HR Δ/min",   f"{rates['heart_rate']:.2f}")
    t2.metric("SpO₂ Δ/min", f"{rates['oxygen_saturation']:.2f}")
    t3.metric("Sys Δ/min",  f"{rates['bp_systolic']:.2f}")
    t4.metric("Temp Δ/min", f"{rates['temperature']:.2f}")

with right:
    st.subheader("Predicted outcomes")
    if outcomes:
        for o in outcomes:
            st.markdown(f"**{o['name']}** — probability **{int(o['probability']*100)}%**")
            st.write("Because:", ", ".join(o.get("because", [])[:4]))
            st.write("Action:",  o.get("action", "Clinician review."))
            st.divider()
    else:
        st.write("No predicted outcomes.")

st.subheader("Event Timeline (latest 50)")
if persist_db:
    events = load_events(Session, patient_id, limit=50)
    if events:
        st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
    else:
        st.info("No events yet.")
else:
    st.info("Enable 'Persist to SQLite' to store and view timeline.")

st.subheader("Vitals History (last 100)")
df_hist = pd.DataFrame(st.session_state.history[patient_id][-100:])
st.dataframe(df_hist, use_container_width=True, hide_index=True)
