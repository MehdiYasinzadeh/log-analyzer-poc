import time
import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient

# تنظیمات صفحه
st.set_page_config(
    page_title="مقایسه لیبل واقعی و پیش‌بینی مدل",
    page_icon="⚖️",
    layout="wide"
)

# اعمال استایل راست‌چین و فونت مناسب برای نمایش مقایسه‌ای
st.markdown("""
<style>
    .reportview-container { direction: rtl; }
    .stMetric { background-color: #0E1117; border: 1px solid #262730; border-radius: 8px; padding: 10px; }
    .match-tag { color: #00CC96; font-weight: bold; }
    .mismatch-tag { color: #FF4B4B; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# سایدبار ساده برای اتصال
st.sidebar.title("تنظیمات دیتابیس")
mongo_uri = st.sidebar.text_input("MongoDB URI", value="mongodb://localhost:27017/")
db_name = st.sidebar.text_input("نام دیتابیس", value="log_analysis")
auto_refresh = st.sidebar.checkbox("🔄 به‌روزرسانی زنده (هر ۳ ثانیه)", value=True)

@st.cache_resource
def get_db(uri, database):
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    return client[database]

try:
    db = get_db(mongo_uri, db_name)
    db.command("ping")
except Exception as e:
    st.error(f"خطا در اتصال به MongoDB: {e}")
    st.stop()

windows_col = db["window_predictions"]
lines_col = db["line_predictions"]

# عنوان اصلی و ساده
st.title("⚖️ مقایسه لیبل واقعی لاگ‌ها با پیش‌بینی مدل زبانی (Laya)")
st.caption("بررسی عملکرد مدل در تفکیک لاگ‌های نرمال (Normal) از خطا (Error)")

# انتخاب سطح مقایسه
view_mode = st.radio(
    "سطح بررسی مقایسه:",
    ["مقایسه در سطح پنجره‌های لاگ (Window-level)", "مقایسه در سطح تک‌تک سطرهای لاگ (Line-level)"],
    horizontal=True
)

if "پنجره" in view_mode:
    raw_data = list(windows_col.find({}, {"_id": 0}).sort("created_at", -1))
    if not raw_data:
        st.warning("هنوز هیچ دیتایی برای پنجره‌ها در مونگو ذخیره نشده است. اسکریپت main.py را اجرا کنید.")
        if auto_refresh:
            time.sleep(3)
            st.rerun()
        st.stop()

    df = pd.DataFrame(raw_data)
    id_col = "window_id"
    label_actual = "true_label"
    label_pred = "predicted_label"
    text_info = "error_line_numbers"
else:
    raw_data = list(lines_col.find({}, {"_id": 0}).sort("line_no", 1).limit(1000))
    if not raw_data:
        st.warning("هنوز دیتایی برای سطرهای لاگ در مونگو ذخیره نشده است.")
        if auto_refresh:
            time.sleep(3)
            st.rerun()
        st.stop()

    df = pd.DataFrame(raw_data)
    id_col = "line_no"
    label_actual = "true_label"
    label_pred = "latest_predicted_label"
    text_info = "raw_text"

# محاسبات مقایسه
df["is_match"] = df[label_actual] == df[label_pred]
total_count = len(df)
match_count = df["is_match"].sum()
mismatch_count = total_count - match_count
accuracy_pct = (match_count / total_count * 100) if total_count > 0 else 0

# ۱. کارت‌های مقایسه بالا
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("کل موارد بررسی‌شده", f"{total_count:,}")
with col2:
    st.metric("تطابق کامل (مدل درست گفته ✅)", f"{match_count:,}", delta=f"{accuracy_pct:.1f}% دقت")
with col3:
    st.metric("مغایرت (خطای مدل ❌)", f"{mismatch_count:,}", delta=f"-{mismatch_count}", delta_color="inverse")
with col4:
    actual_errors = (df[label_actual] == "Error").sum()
    pred_errors = (df[label_pred] == "Error").sum()
    st.metric("تعداد خطاها (واقعی / پیش‌بینی)", f"{actual_errors} واقعی | {pred_errors} پیش‌بینی")

st.markdown("---")

# ۲. دو نمودار مقایسه‌ای بسیار ساده و گویا
ch_col1, ch_col2 = st.columns([1, 1])

with ch_col1:
    st.subheader("📊 مقایسه تعداد کل: لیبل واقعی در برابر پیش‌بینی مدل")
    summary_counts = pd.DataFrame({
        "نوع وضعیت": ["نرمال (Normal)", "ارور (Error)", "نرمال (Normal)", "ارور (Error)"],
        "تعداد": [
            (df[label_actual] == "Normal").sum(),
            (df[label_actual] == "Error").sum(),
            (df[label_pred] == "Normal").sum(),
            (df[label_pred] == "Error").sum()
        ],
        "مرجع": ["لیبل واقعی (Ground Truth)", "لیبل واقعی (Ground Truth)", "پیش‌بینی مدل (Model)", "پیش‌بینی مدل (Model)"]
    })
    fig_bar = px.bar(
        summary_counts,
        x="نوع وضعیت",
        y="تعداد",
        color="مرجع",
        barmode="group",
        text="تعداد",
        color_discrete_map={"لیبل واقعی (Ground Truth)": "#636EFA", "پیش‌بینی مدل (Model)": "#FFA15A"}
    )
    fig_bar.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_bar, use_container_width=True)

with ch_col2:
    st.subheader("🧩 ماتریس مقایسه درستی (Confusion Matrix)")
    # محاسبه ماتریس به روش امن و مستقیم
    tn = ((df[label_actual] == "Normal") & (df[label_pred] == "Normal")).sum()
    fp = ((df[label_actual] == "Normal") & (df[label_pred] == "Error")).sum()
    fn = ((df[label_actual] == "Error") & (df[label_pred] == "Normal")).sum()
    tp = ((df[label_actual] == "Error") & (df[label_pred] == "Error")).sum()

    cm_data = [[tn, fp], [fn, tp]]
    fig_cm = px.imshow(
        cm_data,
        labels=dict(x="پیش‌بینی مدل", y="لیبل واقعی", color="تعداد"),
        x=["پیش‌بینی نرمال", "پیش‌بینی ارور"],
        y=["واقعاً نرمال", "واقعاً ارور"],
        text_auto=True,
        color_continuous_scale="Blues"
    )
    fig_cm.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_cm, use_container_width=True)

st.markdown("---")

# ۳. جدول مقایسه‌ای سطر به سطر
st.subheader("📋 جدول مقایسه مستقیم رکوردها")

# فیلتر نتایج
filter_option = st.radio(
    "فیلتر نمایش رکوردها:",
    ["همه موارد", "فقط مغایرت‌ها (جاهایی که مدل اشتباه کرده ❌)", "فقط تطابق‌ها (پیش‌بینی‌های درست ✅)"],
    horizontal=True
)

filtered_df = df.copy()
if "مغایرت" in filter_option:
    filtered_df = filtered_df[filtered_df["is_match"] == False]
elif "تطابق" in filter_option:
    filtered_df = filtered_df[filtered_df["is_match"] == True]

# تنظیم آیکون وضعیت برای خوانایی بالا
filtered_df["نتیجه مقایسه"] = filtered_df["is_match"].apply(
    lambda x: "✅ تطابق درست" if x else "❌ مغایرت و اشتباه"
)

# انتخاب ستون‌های اصلی جهت نمایش تمیز
if "پنجره" in view_mode:
    display_cols = {
        "window_id": "شناسه پنجره",
        "start_line": "از سطر",
        "end_line": "تا سطر",
        label_actual: "لیبل واقعی (اصلی)",
        label_pred: "لیبل پیش‌بینی مدل",
        "نتیجه مقایسه": "وضعیت",
        "confidence": "ضریب اطمینان مدل"
    }
else:
    display_cols = {
        "line_no": "شماره سطر",
        label_actual: "لیبل واقعی (اصلی)",
        label_pred: "لیبل پیش‌بینی مدل",
        "نتیجه مقایسه": "وضعیت",
        "original_alert_tag": "برچسب لاگ خام",
        "raw_text": "متن لاگ"
    }

show_df = filtered_df[[c for c in display_cols.keys() if c in filtered_df.columns]].rename(columns=display_cols)

st.dataframe(
    show_df,
    use_container_width=True,
    hide_index=True
)

# رفرش خودکار
if auto_refresh:
    time.sleep(3)
    st.rerun()
