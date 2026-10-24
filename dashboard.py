import time
import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient

# تنظیمات پایه
st.set_page_config(
    page_title="ارزیابی دقت مدل",
    page_icon="🎯",
    layout="centered"
)

# اعمال استایل راست‌چین (RTL) و فونت فارسی تمیز
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');

html, body, [data-testid="stAppViewContainer"], .stApp {
    direction: rtl !important;
    text-align: right !important;
    font-family: 'Vazirmatn', sans-serif !important;
}

.stRadio > div {
    flex-direction: row-reverse !important;
    justify-content: center !important;
    gap: 20px !important;
}

.metric-box {
    background: #1E232F;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    border: 1px solid #2B3245;
}
.metric-box.success {
    border-top: 5px solid #00CC96;
}
.metric-box.danger {
    border-top: 5px solid #EF553B;
}
.metric-title {
    font-size: 18px;
    color: #94A3B8;
    margin-bottom: 10px;
}
.metric-value {
    font-size: 48px;
    font-weight: 900;
    margin-bottom: 6px;
}
.metric-value.success { color: #00CC96; }
.metric-value.danger { color: #EF553B; }
.metric-sub {
    font-size: 14px;
    color: #64748B;
}
</style>
""", unsafe_allow_html=True)

# تنظیمات اتصال
mongo_uri = "mongodb://localhost:27017/"
db_name = "log_analysis"

@st.cache_resource
def get_db():
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
    return client[db_name]

try:
    db = get_db()
except Exception as e:
    st.error(f"خطا در ارتباط با دیتابیس مونگو: {e}")
    st.stop()

# تیتر صفحه
st.markdown("<h2 style='text-align: center;'>🎯 نتیجه ارزیابی پیش‌بینی مدل</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #94A3B8;'>مقایسه نسبت درستی و نادرستی پیش‌بینی‌های مدل Laya در برابر لیبل واقعی</p>", unsafe_allow_html=True)

# انتخاب سطح ارزیابی
view_level = st.radio(
    "نمایش نتایج بر اساس:",
    ["تک‌تک سطرهای لاگ (Line-by-Line)", "پنجره‌های لاگ با هم‌پوشانی (Windows)"],
    horizontal=True
)

if "سطر" in view_level:
    raw_records = list(db["line_predictions"].find(
        {"latest_predicted_label": {"$exists": True}},
        {"_id": 0, "true_label": 1, "latest_predicted_label": 1}
    ))
    records = [
        {"true_label": r["true_label"], "predicted_label": r["latest_predicted_label"]}
        for r in raw_records
    ]
else:
    records = list(db["window_predictions"].find(
        {},
        {"_id": 0, "true_label": 1, "predicted_label": 1}
    ))

if not records:
    st.info("داده‌ای در دیتابیس یافت نشد. لطفاً پایپ‌لاین main.py را اجرا کنید.")
    time.sleep(3)
    st.rerun()

df = pd.DataFrame(records)
total = len(df)
correct = (df["true_label"] == df["predicted_label"]).sum()
wrong = total - correct

pct_correct = (correct / total * 100) if total > 0 else 0
pct_wrong = (wrong / total * 100) if total > 0 else 0

st.markdown("<br>", unsafe_allow_html=True)

# ۱. نمایش درصد درست و غلط
col1, col2 = st.columns(2)

with col1:
    st.markdown(f"""
    <div class="metric-box success">
        <div class="metric-title">پیش‌بینی درست (تطابق کامل)</div>
        <div class="metric-value success">{pct_correct:.1f}٪</div>
        <div class="metric-sub">{correct:,} از {total:,} مورد</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-box danger">
        <div class="metric-title">پیش‌بینی غلط (مغایرت)</div>
        <div class="metric-value danger">{pct_wrong:.1f}٪</div>
        <div class="metric-sub">{wrong:,} از {total:,} مورد</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ۲. نمودار نسبت درست به غلط (Donut Chart مینیمال)
chart_df = pd.DataFrame({
    "نتیجه": ["درست", "غلط"],
    "تعداد": [correct, wrong]
})

fig = px.pie(
    chart_df,
    names="نتیجه",
    values="تعداد",
    hole=0.55,
    color="نتیجه",
    color_discrete_map={"درست": "#00CC96", "غلط": "#EF553B"}
)

fig.update_traces(
    textinfo="percent+label",
    textposition="inside",
    textfont_size=16,
    hovertemplate="<b>%{label}</b><br>تعداد: %{value} (%{percent})"
)

fig.update_layout(
    showlegend=False,
    height=340,
    margin=dict(t=10, b=10, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)"
)

st.plotly_chart(fig, width="stretch")

# رفرش لحظه‌ای
time.sleep(3)
st.rerun()
