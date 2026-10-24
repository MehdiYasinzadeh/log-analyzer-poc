import time
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
from datetime import datetime
from pymongo import MongoClient

# Page Configuration
st.set_page_config(
    page_title="BGL Log Analysis - Real-Time Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .metric-card {
        background-color: #1E222D;
        border: 1px solid #2E3648;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
    }
    .metric-title { font-size: 14px; color: #8A99AD; }
    .metric-value { font-size: 26px; font-weight: bold; color: #FFFFFF; }
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("⚙️ Dashboard Controls")
mongo_uri = st.sidebar.text_input("MongoDB URI", value="mongodb://localhost:27017/")
db_name = st.sidebar.text_input("Database Name", value="log_analysis")

auto_refresh = st.sidebar.toggle("🔄 Real-Time Auto Refresh", value=True)
refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", min_value=1, max_value=10, value=3)

# MongoDB Connection
@st.cache_resource
def get_db(uri, database):
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    return client[database]

try:
    db = get_db(mongo_uri, db_name)
    db.command("ping")
    st.sidebar.success("✅ Connected to MongoDB")
except Exception as e:
    st.sidebar.error(f"❌ MongoDB Connection Failed: {e}")
    st.stop()

# Data Fetching
windows_col = db["window_predictions"]
lines_col = db["line_predictions"]

windows_data = list(windows_col.find({}, {"_id": 0}).sort("created_at", -1))
total_lines_count = lines_col.count_documents({})

# Header
st.title("🛡️ BGL Supercomputer Log Anomaly Detection")
st.caption(f"Real-time monitoring & LLM (Laya) verification against Ground Truth | Last update: {datetime.now().strftime('%H:%M:%S')}")

if not windows_data:
    st.info("ℹ️ No prediction data found in MongoDB yet. Run the pipeline (`main.py`) to stream predictions!")
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()
    st.stop()

df = pd.DataFrame(windows_data)
# Add sequence index for chronological plotting
df["seq_idx"] = range(len(df), 0, -1)
df = df.iloc[::-1].reset_index(drop=True)  # chronological order

# Metrics Calculation
total_windows = len(df)
correct_count = df["is_correct"].sum()
accuracy = (correct_count / total_windows) * 100 if total_windows > 0 else 0

# True vs Pred for Error class
true_errors = (df["true_label"] == "Error").sum()
pred_errors = (df["predicted_label"] == "Error").sum()
tp = ((df["true_label"] == "Error") & (df["predicted_label"] == "Error")).sum()
fp = ((df["true_label"] == "Normal") & (df["predicted_label"] == "Error")).sum()
fn = ((df["true_label"] == "Error") & (df["predicted_label"] == "Normal")).sum()
tn = ((df["true_label"] == "Normal") & (df["predicted_label"] == "Normal")).sum()

precision_error = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0.0
recall_error = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0.0
mismatches_count = total_windows - correct_count

# KPI Metrics Row
col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    st.metric("Total Windows", f"{total_windows:,}")
with col2:
    st.metric("Total Lines Scanned", f"{total_lines_count:,}")
with col3:
    st.metric("Overall Accuracy", f"{accuracy:.1f}%")
with col4:
    st.metric("Error Precision", f"{precision_error:.1f}%")
with col5:
    st.metric("Error Recall", f"{recall_error:.1f}%")
with col6:
    st.metric("Mismatches", f"{mismatches_count}", delta=f"-{mismatches_count}" if mismatches_count > 0 else "0", delta_color="inverse")

st.markdown("---")

# Visualizations Row 1
chart_col1, chart_col2 = st.columns([1, 2])

with chart_col1:
    st.subheader("🧩 Confusion Matrix")
    z = [[tn, fp], [fn, tp]]
    x_labels = ["Pred Normal", "Pred Error"]
    y_labels = ["Actual Normal", "Actual Error"]

    fig_cm = ff.create_annotated_heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        colorscale="Blues",
        showscale=True
    )
    fig_cm.update_layout(
        margin=dict(t=30, l=40, r=20, b=30),
        height=320,
        font=dict(size=13)
    )
    st.plotly_chart(fig_cm, use_container_width=True)

with chart_col2:
    st.subheader("📈 Window Anomaly Probability Timeline")
    # Extract error probability
    def get_error_prob(row):
        probs = row.get("probabilities", {})
        if isinstance(probs, dict):
            return probs.get("Error", 1.0 if row["predicted_label"] == "Error" else 0.0)
        return 1.0 if row["predicted_label"] == "Error" else 0.0

    df["error_prob"] = df.apply(get_error_prob, axis=1)
    df["status_display"] = df["is_correct"].apply(lambda x: "Match (Correct)" if x else "Mismatch")

    fig_timeline = px.scatter(
        df,
        x="seq_idx",
        y="error_prob",
        color="status_display",
        color_discrete_map={"Match (Correct)": "#00CC96", "Mismatch": "#EF553B"},
        hover_data=["window_id", "start_line", "end_line", "true_label", "predicted_label", "confidence"],
        labels={"seq_idx": "Window Sequence Index", "error_prob": "Model Error Probability"},
        title="Error Probability per Window (Green = Agreement with Ground Truth, Red = Discrepancy)"
    )
    fig_timeline.add_hline(y=0.5, line_dash="dash", line_color="gray", annotation_text="Threshold (0.5)")
    fig_timeline.update_layout(height=320, margin=dict(t=40, l=40, r=20, b=30))
    st.plotly_chart(fig_timeline, use_container_width=True)

# Visualizations Row 2: Distributions & Details
st.markdown("---")
tab1, tab2, tab3 = st.tabs(["⚠️ Discrepancies & Mismatches", "📋 All Window Predictions", "🔍 Window Deep-Dive Inspector"])

with tab1:
    mismatches_df = df[df["is_correct"] == False][["window_id", "start_line", "end_line", "true_label", "predicted_label", "confidence", "error_line_numbers"]]
    if len(mismatches_df) == 0:
        st.success("🎉 No mismatches! The model prediction perfectly matches the Ground Truth for all windows.")
    else:
        st.dataframe(
            mismatches_df,
            column_config={
                "window_id": "Window ID",
                "start_line": "Start Line",
                "end_line": "End Line",
                "true_label": "Ground Truth",
                "predicted_label": "Model Prediction",
                "confidence": st.column_config.ProgressColumn("Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
                "error_line_numbers": "Actual Error Lines in Window"
            },
            use_container_width=True
        )

with tab2:
    st.dataframe(
        df[["window_id", "start_line", "end_line", "log_count", "true_label", "predicted_label", "is_correct", "confidence"]].iloc[::-1],
        column_config={
            "is_correct": st.column_config.CheckboxColumn("Match"),
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0.0, max_value=1.0, format="%.2f")
        },
        use_container_width=True
    )

with tab3:
    st.subheader("Inspect Constituent Raw Logs for a Window")
    selected_window_id = st.selectbox("Select Window to inspect:", df["window_id"].unique())
    if selected_window_id:
        selected_win = df[df["window_id"] == selected_window_id].iloc[0]
        start_l = int(selected_win["start_line"])
        end_l = int(selected_win["end_line"])

        st.markdown(f"**Window Range:** Lines `{start_l}` to `{end_l}` | **Ground Truth:** `{selected_win['true_label']}` | **Model:** `{selected_win['predicted_label']}` (Confidence: `{selected_win['confidence']:.2f}`)")

        lines_in_win = list(lines_col.find(
            {"line_no": {"$gte": start_l, "$lte": end_l}},
            {"_id": 0}
        ).sort("line_no", 1))

        if lines_in_win:
            lines_display = pd.DataFrame(lines_in_win)[["line_no", "original_alert_tag", "true_label", "raw_text"]]
            st.dataframe(lines_display, use_container_width=True)
        else:
            st.info("Line details not yet indexed for this window.")

# Auto-refresh loop
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
