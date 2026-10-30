import time
import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient

# 1. Page Configuration (English LTR)
st.set_page_config(
    page_title="Spring Boot AIOps Copilot",
    page_icon="🛡️",
    layout="wide"
)

# 2. Modern Enterprise CSS (Dark Theme, Clean Typography, LTR)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {
    direction: ltr !important;
    text-align: left !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
}

code, pre {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Metric Cards */
.metric-box {
    background: #181C26;
    border-radius: 10px;
    padding: 18px 20px;
    text-align: left;
    border: 1px solid #283042;
    margin-bottom: 12px;
}
.metric-box.danger { border-left: 5px solid #EF4444; }
.metric-box.warning { border-left: 5px solid #F59E0B; }
.metric-box.info { border-left: 5px solid #3B82F6; }
.metric-box.success { border-left: 5px solid #10B981; }

.metric-title {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94A3B8;
    margin-bottom: 6px;
}
.metric-value {
    font-size: 34px;
    font-weight: 800;
    margin-bottom: 2px;
}
.metric-value.danger { color: #EF4444; }
.metric-value.warning { color: #F59E0B; }
.metric-value.info { color: #3B82F6; }
.metric-value.success { color: #10B981; }

.metric-sub {
    font-size: 12px;
    color: #64748B;
}

/* Config Table */
.config-table-container {
    background: #141721;
    border: 1px solid #232938;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 20px;
}
.config-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.config-table th {
    background: #1B202D;
    color: #94A3B8;
    font-weight: 600;
    text-align: left;
    padding: 10px 16px;
    border-bottom: 1px solid #283042;
}
.config-table td {
    padding: 10px 16px;
    color: #E2E8F0;
    border-bottom: 1px solid #1C2230;
}
.config-badge {
    background: #1E3A8A;
    color: #93C5FD;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
}

/* Error Grid Cards */
.error-grid-row {
    background: #161A24;
    border: 1px solid #242C3D;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
    transition: all 0.2s ease;
}
.error-grid-row:hover {
    border-color: #3B82F6;
    background: #1A202C;
}

.badge-crit {
    background: rgba(239, 68, 68, 0.15);
    color: #F87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
}
.badge-high {
    background: rgba(245, 158, 11, 0.15);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.3);
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
}
.badge-med {
    background: rgba(59, 130, 246, 0.15);
    color: #60A5FA;
    border: 1px solid rgba(59, 130, 246, 0.3);
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# 3. Database Connection
mongo_uri = "mongodb://localhost:27017/"
db_name = "log_analysis"

@st.cache_resource
def get_db():
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
    return client[db_name]

try:
    db = get_db()
    col = db["spring_window_incidents"]
except Exception as e:
    st.error(f"MongoDB connection failed: {e}")
    st.stop()

# 4. Header Bar
h_col1, h_col2 = st.columns([3, 1])
with h_col1:
    st.markdown("<h2 style='margin:0; font-weight:800; color:#F8FAFC;'>🛡️ Spring Boot AIOps Incident Monitor</h2>", unsafe_allow_html=True)
    st.markdown("<p style='margin:4px 0 16px 0; color:#94A3B8; font-size:14px;'>Continuous anomaly detection via Laya Gatekeeper with automated root-cause extraction</p>", unsafe_allow_html=True)
with h_col2:
    st.markdown("<div style='text-align:right; margin-top:8px;'><span style='background:#064E3B; color:#34D399; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:600;'>🟢 LIVE MONITOR (3s)</span></div>", unsafe_allow_html=True)

# 5. Sliding Window Configuration Table (Requested Table Format)
st.markdown("##### ⚙️ Sliding Window Ingestion Configuration")
st.markdown("""
<div class="config-table-container">
    <table class="config-table">
        <thead>
            <tr>
                <th>Parameter</th>
                <th>Configured Value</th>
                <th>Sampling Mechanism</th>
                <th>Boundary Protection</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><b>Streaming Mode</b></td>
                <td><span class="config-badge">Overlapping Sliding Window</span></td>
                <td>Continuous block-by-block sliding scanner</td>
                <td>Eliminates edge-boundary truncation</td>
            </tr>
            <tr>
                <td><b>Window Size</b></td>
                <td><b>25 Lines</b></td>
                <td>Contextual frame passed to Laya per evaluation</td>
                <td>Preserves complete stack trace context</td>
            </tr>
            <tr>
                <td><b>Step Stride</b></td>
                <td><b>12 Lines</b></td>
                <td>Forward sliding distance per iteration</td>
                <td>Ensures smooth sequential log advancement</td>
            </tr>
            <tr>
                <td><b>Overlap Coverage</b></td>
                <td><b>13 Lines (52.0% Overlap)</b></td>
                <td>Continuously shared context between adjacent windows</td>
                <td>Guarantees multi-line exceptions are fully captured</td>
            </tr>
        </tbody>
    </table>
</div>
""", unsafe_allow_html=True)

# 6. Log File Selector
available_files = col.distinct("source_file")
if not available_files:
    st.info("No window evaluation records found in MongoDB. Please run `spring_main.py` first.")
    time.sleep(3)
    st.rerun()

col_select, col_meta = st.columns([2, 2])
with col_select:
    selected_file = st.selectbox("Select Active Log File:", available_files, index=0)
with col_meta:
    st.markdown(f"<p style='margin-top:28px; color:#64748B; font-size:13px;'>Active Collection: <code>spring_window_incidents</code></p>", unsafe_allow_html=True)

query = {"source_file": selected_file}
records = list(col.find(query, {"_id": 0}).sort("start_line", 1))

if not records:
    st.warning("No records found for the selected log file.")
    time.sleep(3)
    st.rerun()

df = pd.DataFrame(records)
total_windows = len(df)
anomalies_df = df[df["is_anomaly"] == True]
total_anomalies = len(anomalies_df)
total_normals = total_windows - total_anomalies

infra_count = (df["category"] == "INFRASTRUCTURE_OUTAGE").sum()
tx_count = (df["category"] == "TRANSACTION_FAILURE").sum()
bug_count = (df["category"] == "SOFTWARE_DEFECT").sum()
rule_count = (df["category"] == "BUSINESS_RULE_REJECTION").sum()

# 7. Executive Metric Cards (KPIs)
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.markdown(f"""
    <div class="metric-box danger">
        <div class="metric-title">Anomalies Detected</div>
        <div class="metric-value danger">{total_anomalies:,}</div>
        <div class="metric-sub">{total_anomalies/total_windows*100:.1f}% of evaluated windows</div>
    </div>
    """, unsafe_allow_html=True)

with kpi2:
    st.markdown(f"""
    <div class="metric-box warning">
        <div class="metric-title">DB & Network Outages</div>
        <div class="metric-value warning">{infra_count:,}</div>
        <div class="metric-sub">JDBC connection & pool timeouts</div>
    </div>
    """, unsafe_allow_html=True)

with kpi3:
    st.markdown(f"""
    <div class="metric-box info">
        <div class="metric-title">Transaction Failures</div>
        <div class="metric-value info">{tx_count:,}</div>
        <div class="metric-sub">RollbackException & JTA failures</div>
    </div>
    """, unsafe_allow_html=True)

with kpi4:
    st.markdown(f"""
    <div class="metric-box success">
        <div class="metric-title">Healthy Windows (Normal)</div>
        <div class="metric-value success">{total_normals:,}</div>
        <div class="metric-sub">{total_normals/total_windows*100:.1f}% normal operations</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 8. Main Body: Chart on LEFT, Executive Summary on RIGHT (Requested Layout)
col_left_chart, col_right_summary = st.columns([1, 1])

# LEFT: Incident Category Breakdown Chart
with col_left_chart:
    st.markdown("#### 📊 Incident Category Breakdown")
    chart_data = pd.DataFrame({
        "Category": ["DB & Network Outage", "Transaction Failure", "Code Bug / Crash", "Business Rule Reject"],
        "Windows": [infra_count, tx_count, bug_count, rule_count]
    })
    chart_data = chart_data[chart_data["Windows"] > 0]

    if not chart_data.empty:
        fig = px.pie(
            chart_data,
            names="Category",
            values="Windows",
            hole=0.55,
            color="Category",
            color_discrete_map={
                "DB & Network Outage": "#EF4444",
                "Transaction Failure": "#3B82F6",
                "Code Bug / Crash": "#F59E0B",
                "Business Rule Reject": "#8B5CF6"
            }
        )
        fig.update_traces(
            textinfo="percent+label",
            textposition="inside",
            textfont_size=13,
            hovertemplate="<b>%{label}</b><br>Windows: %{value} (%{percent})"
        )
        fig.update_layout(
            showlegend=False,
            height=300,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.success("All windows represent healthy normal operations.")

# RIGHT: Service Status & RCA Executive Summary
with col_right_summary:
    st.markdown("#### 📋 Service Health & RCA Summary")
    if total_anomalies > 0:
        st.error(f"⚠️ **Incident Storm Detected**: {total_anomalies} anomalous windows flagged in `{selected_file}`.")
        
        # Primary Root Cause determination
        primary_cause = "Database Connection Acquisition Failure" if infra_count > 0 else "Code Exception"
        st.markdown(f"""
        - **Primary Anomaly Type**: `{primary_cause}`
        - **Impacted Subsystems**: Batch Schedulers, JDBC Connection Pool (`GenericJDBCException`), Transaction Manager (`JpaSystemException`).
        - **Root Cause Analysis**: The application failed to acquire database physical connections from DataSource. Threads attempted to access closed or harvested connections.
        - **Immediate SRE Remediation**:
          1. Verify Oracle/PostgreSQL cluster responsiveness and active session counts.
          2. Inspect DataSource `maximumPoolSize` and `connectionTimeout` settings.
          3. Restart stale batch executor threads to release hung socket descriptors.
        """)
    else:
        st.success("🎉 All log windows are executing within healthy parameters (0 Anomalies).")
        st.markdown("""
        - **Status**: Stable
        - **Exceptions Encountered**: None
        - **Recommendations**: Continue baseline monitoring.
        """)

st.markdown("<hr style='border:1px solid #232938; margin: 24px 0;'>", unsafe_allow_html=True)

# 9. Latest Detected Errors Grid (Requested Grid View)
st.markdown("### 🚨 Latest Detected Incidents Grid")

if anomalies_df.empty:
    st.success("No error incidents detected in this stream.")
else:
    # Filter Controls
    f_col1, f_col2 = st.columns([1, 3])
    with f_col1:
        selected_cat = st.selectbox(
            "Filter Category:",
            ["All Categories"] + list(anomalies_df["category"].unique())
        )
    
    filtered_df = anomalies_df if selected_cat == "All Categories" else anomalies_df[anomalies_df["category"] == selected_cat]

    # Grid Display: Clean tabular card grid
    for idx, item in filtered_df.head(15).iterrows():
        sev = item.get("severity", "MEDIUM")
        badge_cls = "badge-crit" if sev == "CRITICAL" else ("badge-high" if sev == "HIGH" else "badge-med")
        
        st.markdown(f"""
        <div class="error-grid-row">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <div>
                    <span class="{badge_cls}">{sev}</span>
                    <span style="font-weight:700; color:#F8FAFC; margin-left:8px; font-size:14px;">{item['window_id']}</span>
                    <span style="color:#64748B; font-size:12px; margin-left:6px;">(Lines {item['start_line']} - {item['end_line']} | {item['overlap_lines']} lines overlap)</span>
                </div>
                <div style="color:#94A3B8; font-size:12px;">
                    🕒 {item['timestamp']} &nbsp;|&nbsp; 🧵 <code>{item['thread']}</code>
                </div>
            </div>
            <div style="color:#EF4444; font-weight:600; font-size:13px; margin-bottom:4px;">
                💥 Exception: {item['exception_type']}
            </div>
            <div style="color:#CBD5E1; font-size:13px; margin-bottom:6px;">
                <b>Root Cause:</b> {item['root_cause']}
            </div>
            <div style="color:#60A5FA; font-size:12px;">
                💡 <b>Suggested Action:</b> {item['recommended_action']}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Raw log snippet in expandable drawer
        if item.get("snippet"):
            with st.expander(f"View Raw Log Lines for {item['window_id']}"):
                st.code(item["snippet"], language="text")

# 10. Real-time Refresh Loop
time.sleep(3)
st.rerun()
