"""
dashboard.py — Smart Farm Real-Time Monitoring Dashboard
=========================================================
Run locally:
    streamlit run dashboard.py

Deploy: push to GitHub → share.streamlit.io
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import paho.mqtt.client as mqtt
import json
import time
import threading
from datetime import datetime

# ═══════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Smart Farm Monitor",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  div[data-testid="metric-container"] {
    background: #0f2318;
    border: 1px solid #1e4d2b;
    border-radius: 12px;
    padding: 14px 18px;
  }
  div[data-testid="metric-container"] label {
    color: #7ab88a !important;
    font-size: 0.78rem !important;
    font-weight: 600;
    letter-spacing: 0.05em;
  }
  div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    color: #c8f5d0 !important;
    font-size: 1.6rem !important;
    font-weight: 700;
  }
  .section-header {
    font-size: 0.85rem;
    font-weight: 700;
    color: #7ab88a;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 20px 0 10px 0;
    border-left: 3px solid #2e7d32;
    padding-left: 10px;
  }
  .badge-on  { background:#1b3a1b; color:#4caf50; border:1px solid #4caf50;
               border-radius:20px; padding:4px 14px; font-size:0.85rem; font-weight:700; }
  .badge-off { background:#1e1e1e; color:#666; border:1px solid #444;
               border-radius:20px; padding:4px 14px; font-size:0.85rem; }
  .conn-ok  { color:#4caf50; font-weight:700; }
  .conn-err { color:#f44336; font-weight:700; }
  #MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# MQTT CONFIG
# ═══════════════════════════════════════════════════════════
BROKER    = "broker.hivemq.com"
PORT      = 1883
TOPIC     = "farm/sensors/all"
MQTT_USER = "hivemq.webclient.1774179330145"
MQTT_PASS = "E8@*$pA1dbnx.SUPlX67"
CLIENT_ID = "hivemq.webclient.1774179330145"

# ═══════════════════════════════════════════════════════════
# SHARED BUFFER  (MQTT thread writes, Streamlit reads)
# ═══════════════════════════════════════════════════════════
_lock = threading.Lock()

_buf = dict(
    moisture_a=0.0, moisture_b=0.0, moisture_c=0.0,
    deadline_a=9999.0, deadline_b=9999.0, deadline_c=9999.0,
    valve_a=0, valve_b=0, valve_c=0, pump=0,
    temperature=0.0, humidity=0.0,
    history=[],
    last_update=None,
    connected=False,
    msg_count=0,
)

# ═══════════════════════════════════════════════════════════
# MQTT CALLBACKS
# ═══════════════════════════════════════════════════════════
def _on_connect(client, userdata, flags, rc):
    with _lock:
        _buf["connected"] = (rc == 0)
    if rc == 0:
        client.subscribe(TOPIC, 0)

def _on_disconnect(client, userdata, rc):
    with _lock:
        _buf["connected"] = False

def _on_message(client, userdata, msg):
    try:
        p = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return

    with _lock:
        _buf["moisture_a"]  = p.get("moisture_a",  0)
        _buf["moisture_b"]  = p.get("moisture_b",  0)
        _buf["moisture_c"]  = p.get("moisture_c",  0)
        _buf["deadline_a"]  = p.get("deadline_a",  9999)
        _buf["deadline_b"]  = p.get("deadline_b",  9999)
        _buf["deadline_c"]  = p.get("deadline_c",  9999)
        _buf["valve_a"]     = p.get("valve_a",     0)
        _buf["valve_b"]     = p.get("valve_b",     0)
        _buf["valve_c"]     = p.get("valve_c",     0)
        _buf["pump"]        = p.get("pump",        0)
        _buf["temperature"] = p.get("temperature", 0)
        _buf["humidity"]    = p.get("humidity",    0)
        _buf["last_update"] = datetime.now().strftime("%H:%M:%S")
        _buf["msg_count"]  += 1

        _buf["history"].append({
            "time":        datetime.now().strftime("%H:%M:%S"),
            "moisture_a":  _buf["moisture_a"],
            "moisture_b":  _buf["moisture_b"],
            "moisture_c":  _buf["moisture_c"],
            "temperature": _buf["temperature"],
            "humidity":    _buf["humidity"],
            "pump":        _buf["pump"],
        })
        if len(_buf["history"]) > 300:
            _buf["history"].pop(0)

# ═══════════════════════════════════════════════════════════
# START MQTT ONCE PER SESSION
# ═══════════════════════════════════════════════════════════
@st.cache_resource(show_spinner="Connecting to HiveMQ...")
def start_mqtt():
    c = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    c.username_pw_set(MQTT_USER, MQTT_PASS)
    c.on_connect    = _on_connect
    c.on_disconnect = _on_disconnect
    c.on_message    = _on_message
    c.connect_async(BROKER, PORT, keepalive=60)
    c.loop_start()
    return c

# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════
def badge(on):
    cls = "badge-on" if on else "badge-off"
    txt = "ON" if on else "OFF"
    return f'<span class="{cls}">{txt}</span>'

def deadline_str(d):
    return "Met" if d >= 9999 else f"{d:.2f}"

def m_delta(val, target):
    if val >= target:        return "normal"
    if val >= target * 0.75: return "inverse"
    return "off"

# ═══════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════
def main():
    start_mqtt()

    with _lock:
        s       = dict(_buf)
        history = list(_buf["history"])

    # ── Sidebar ───────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 🌱 Smart Farm")
        st.markdown("---")
        cls = "conn-ok" if s["connected"] else "conn-err"
        dot = "● Connected" if s["connected"] else "● Disconnected"
        st.markdown(f'<span class="{cls}">{dot}</span>', unsafe_allow_html=True)
        st.caption(f"Messages received: {s['msg_count']}")
        st.caption(f"Last update: {s['last_update'] or 'waiting...'}")
        st.markdown("---")
        refresh = st.slider("Refresh (sec)", 2, 30, 5)
        st.markdown("---")
        st.markdown("**Broker:** `broker.hivemq.com:8883`")
        st.markdown("**Topic:** `farm/sensors/all`")
        st.markdown("---")
        st.markdown("**Soil Targets**")
        st.markdown("Zone A: **70%** · Zone B: **60%** · Zone C: **50%**")

    # ── Header ────────────────────────────────────────────
    st.markdown("# 🌾 Smart Irrigation Monitor")
    st.markdown("---")

    if not s["connected"]:
        st.warning("⏳ Connecting to HiveMQ broker...")

    # ── Soil Moisture ─────────────────────────────────────
    st.markdown('<div class="section-header">Soil Moisture</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Zone A", f"{s['moisture_a']:.1f}%",
              delta="Good" if s['moisture_a'] >= 70 else "Low",
              delta_color=m_delta(s['moisture_a'], 70))
    c2.metric("Zone B", f"{s['moisture_b']:.1f}%",
              delta="Good" if s['moisture_b'] >= 60 else "Low",
              delta_color=m_delta(s['moisture_b'], 60))
    c3.metric("Zone C", f"{s['moisture_c']:.1f}%",
              delta="Good" if s['moisture_c'] >= 50 else "Low",
              delta_color=m_delta(s['moisture_c'], 50))

    # ── Environment ───────────────────────────────────────
    st.markdown('<div class="section-header">Environment</div>', unsafe_allow_html=True)
    e1, e2 = st.columns(2)
    e1.metric("Temperature", f"{s['temperature']:.1f} °C")
    e2.metric("Humidity",    f"{s['humidity']:.1f} %")

    # ── EDF Deadlines ─────────────────────────────────────
    st.markdown('<div class="section-header">EDF Deadlines (lower = more urgent)</div>', unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)
    d1.metric("Zone A", deadline_str(s['deadline_a']))
    d2.metric("Zone B", deadline_str(s['deadline_b']))
    d3.metric("Zone C", deadline_str(s['deadline_c']))

    # ── Valve / Pump ──────────────────────────────────────
    st.markdown('<div class="section-header">Control Status</div>', unsafe_allow_html=True)
    v1, v2, v3, v4 = st.columns(4)
    v1.markdown(f"**Valve A** &nbsp; {badge(s['valve_a'])}", unsafe_allow_html=True)
    v2.markdown(f"**Valve B** &nbsp; {badge(s['valve_b'])}", unsafe_allow_html=True)
    v3.markdown(f"**Valve C** &nbsp; {badge(s['valve_c'])}", unsafe_allow_html=True)
    v4.markdown(f"**Pump** &nbsp;&nbsp;&nbsp; {badge(s['pump'])}",  unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────
    st.markdown('<div class="section-header">Historical Trends</div>', unsafe_allow_html=True)

    if len(history) < 2:
        st.info("📡 Waiting for data... charts appear after a few readings.")
    else:
        df   = pd.DataFrame(history)
        GRID = "#1e4d2b"
        BG   = "rgba(0,0,0,0)"

        tab1, tab2, tab3 = st.tabs(["💧 Moisture", "🌡️ Temp & Humidity", "⚡ Pump"])

        with tab1:
            fig = go.Figure()
            for col, name, color, target in [
                ("moisture_a", "Zone A", "#4CAF50", 70),
                ("moisture_b", "Zone B", "#2196F3", 60),
                ("moisture_c", "Zone C", "#FF9800", 50),
            ]:
                fig.add_trace(go.Scatter(
                    x=df["time"], y=df[col],
                    name=name, line=dict(color=color, width=2), mode="lines"
                ))
                fig.add_hline(y=target, line_dash="dot", line_color=color, opacity=0.4,
                              annotation_text=f"{name} target ({target}%)")
            fig.update_layout(height=320, margin=dict(l=0,r=0,t=20,b=0),
                xaxis_title="Time", yaxis_title="Moisture (%)",
                legend=dict(orientation="h"),
                paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color="#c8f5d0"))
            fig.update_xaxes(showgrid=True, gridcolor=GRID)
            fig.update_yaxes(showgrid=True, gridcolor=GRID)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=df["time"], y=df["temperature"],
                name="Temp (°C)", line=dict(color="#FF5722", width=2), yaxis="y"))
            fig2.add_trace(go.Scatter(x=df["time"], y=df["humidity"],
                name="Humidity (%)", line=dict(color="#03A9F4", width=2), yaxis="y2"))
            fig2.update_layout(height=320, margin=dict(l=0,r=0,t=20,b=0),
                yaxis =dict(title="°C", color="#FF5722"),
                yaxis2=dict(title="%",  color="#03A9F4", overlaying="y", side="right"),
                legend=dict(orientation="h"),
                paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color="#c8f5d0"))
            fig2.update_xaxes(showgrid=True, gridcolor=GRID)
            fig2.update_yaxes(showgrid=True, gridcolor=GRID)
            st.plotly_chart(fig2, use_container_width=True)

        with tab3:
            fig3 = px.area(df, x="time", y="pump",
                color_discrete_sequence=["#4CAF50"],
                labels={"pump": "Pump (1=ON)", "time": "Time"})
            fig3.update_layout(height=280, margin=dict(l=0,r=0,t=20,b=0),
                paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color="#c8f5d0"))
            fig3.update_xaxes(showgrid=True, gridcolor=GRID)
            fig3.update_yaxes(showgrid=True, gridcolor=GRID, range=[-0.1, 1.5])
            st.plotly_chart(fig3, use_container_width=True)

    # ── Raw payload ───────────────────────────────────────
    with st.expander("🔍 Raw MQTT payload"):
        debug = {k: v for k, v in s.items() if k != "history"}
        st.json(debug)

    # ── Auto-refresh ──────────────────────────────────────
    time.sleep(refresh)
    st.rerun()


if __name__ == "__main__":
    main()
