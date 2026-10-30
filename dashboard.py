import time
import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient

# ۱. تنظیمات صفحه
st.set_page_config(
    page_title="داشبورد پایش هوشمند لاگ‌های Spring Boot",
    page_icon="🛡️",
    layout="wide"
)

# ۲. اعمال استایل راست‌چین (RTL) و فونت فارسی وزیرمتن
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');

html, body, [data-testid="stAppViewContainer"], .stApp {
    direction: rtl !important;
    text-align: right !important;
    font-family: 'Vazirmatn', sans-serif !important;
}

.window-badge {
    background: #182234;
    border: 1px solid #2B4C7E;
    border-radius: 10px;
    padding: 12px 20px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.window-badge-title {
    font-size: 15px;
    font-weight: 700;
    color: #60A5FA;
}
.window-badge-desc {
    font-size: 13px;
    color: #94A3B8;
}

.metric-box {
    background: #1E232F;
    border-radius: 12px;
    padding: 18px;
    text-align: center;
    border: 1px solid #2B3245;
    margin-bottom: 15px;
}
.metric-box.danger { border-top: 5px solid #EF553B; }
.metric-box.warning { border-top: 5px solid #F59E0B; }
.metric-box.info { border-top: 5px solid #3B82F6; }
.metric-box.success { border-top: 5px solid #10B981; }

.metric-title {
    font-size: 14px;
    color: #94A3B8;
    margin-bottom: 6px;
}
.metric-value {
    font-size: 36px;
    font-weight: 900;
    margin-bottom: 4px;
}
.metric-value.danger { color: #EF553B; }
.metric-value.warning { color: #F59E0B; }
.metric-value.info { color: #3B82F6; }
.metric-value.success { color: #10B981; }

.metric-sub {
    font-size: 12px;
    color: #64748B;
}

.incident-card {
    background: #1A1F2C;
    border-right: 4px solid #EF553B;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ۳. اتصال به دیتابیس MongoDB
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
    st.error(f"خطا در ارتباط با دیتابیس مونگو: {e}")
    st.stop()

# ۴. تیتر اصلی
st.markdown("<h2 style='text-align: center; margin-bottom: 5px;'>🛡️ مانیتورینگ بلادرنگ و تحلیل ریشه‌ای حوادث Spring Boot</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #94A3B8; margin-bottom: 20px;'>تشخیص خودکار ناهنجاری با مدل Laya به عنوان دروازه‌بان (Gatekeeper) و استخراج علل ریشه‌ای خطاها</p>", unsafe_allow_html=True)

# ۵. بنر مشخصات پنجره‌های لغزان با هم‌پوشانی (Overlap)
st.markdown("""
<div class="window-badge">
    <div>
        <span class="window-badge-title">⚙️ پردازش مبتنی بر پنجره‌های لغزان با هم‌پوشانی (Sliding Windows with Overlap)</span>
        <div class="window-badge-desc">اندازه پنجره: <b>۲۵ سطر</b> | گام حرکت (Step): <b>۱۲ سطر</b> | هم‌پوشانی پیوسته: <b>۱۳ سطر مشترک (۵۲.۰٪ Overlap)</b></div>
    </div>
    <div style="background: #2563EB; color: white; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: bold;">
        اسکن پیوسته (بدون قطعی مرزی)
    </div>
</div>
""", unsafe_allow_html=True)

# ۶. بازیابی داده‌ها از کالکشن پنجره‌های اسپرینگ‌بوت
available_files = col.distinct("source_file")
if not available_files:
    st.info("هنوز پنجره‌ای در دیتابیس ثبت نشده است. لطفاً پایپ‌لاین `spring_main.py` را اجرا کنید.")
    time.sleep(3)
    st.rerun()

col_sel1, col_sel2 = st.columns([3, 1])
with col_sel1:
    selected_file = st.selectbox("انتخاب فایل لاگ فعال جهت بررسی:", available_files, index=0)
with col_sel2:
    st.markdown(f"<div style='margin-top: 28px; color: #10B981; font-size: 13px;'>🟢 اتصال زنده (بروزرسانی هر ۳ ثانیه)</div>", unsafe_allow_html=True)

query = {"source_file": selected_file}
records = list(col.find(query, {"_id": 0}).sort("start_line", 1))

if not records:
    st.warning("هیچ داده‌ای برای این فایل لاگ یافت نشد.")
    time.sleep(3)
    st.rerun()

df = pd.DataFrame(records)
total_windows = len(df)
anomalies_df = df[df["is_anomaly"] == True]
total_anomalies = len(anomalies_df)
total_normals = total_windows - total_anomalies

# شمارش دسته‌های خطا
infra_count = (df["category"] == "INFRASTRUCTURE_OUTAGE").sum()
tx_count = (df["category"] == "TRANSACTION_FAILURE").sum()
bug_count = (df["category"] == "SOFTWARE_DEFECT").sum()
rule_count = (df["category"] == "BUSINESS_RULE_REJECTION").sum()

# ۷. کارت‌های شاخص‌های کلیدی (KPI)
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""
    <div class="metric-box danger">
        <div class="metric-title">پنجره‌های خطادار کشف‌شده</div>
        <div class="metric-value danger">{total_anomalies:,}</div>
        <div class="metric-sub">{total_anomalies/total_windows*100:.1f}٪ از کل پنجره‌ها</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-box warning">
        <div class="metric-title">بحران دیتابیس و ارتباط شبکه</div>
        <div class="metric-value warning">{infra_count:,}</div>
        <div class="metric-sub">قطعی کانکشن و تایم‌اوت JDBC</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-box info">
        <div class="metric-title">شکست و رول‌بک ترانزکشن</div>
        <div class="metric-value info">{tx_count:,}</div>
        <div class="metric-sub">RollbackException و ترانزکشن ناموفق</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="metric-box success">
        <div class="metric-title">پنجره‌های کاملاً سالم (Normal)</div>
        <div class="metric-value success">{total_normals:,}</div>
        <div class="metric-sub">عملیات بدون رخداد ناهنجاری</div>
    </div>
    """, unsafe_allow_html=True)

# ۸. نمودار دسته‌بندی و توزیع خطاها
st.markdown("<br>", unsafe_allow_html=True)
col_chart, col_summary = st.columns([1, 1])

with col_chart:
    st.markdown("#### 📊 دسته‌بندی خطاهای شناسایی‌شده")
    chart_data = pd.DataFrame({
        "نوع خطا": ["بحران دیتابیس و شبکه", "شکست ترانزکشن", "باگ کد جاوا", "رد قوانین بیمه"],
        "تعداد پنجره": [infra_count, tx_count, bug_count, rule_count]
    })
    chart_data = chart_data[chart_data["تعداد پنجره"] > 0]

    if not chart_data.empty:
        fig = px.pie(
            chart_data,
            names="نوع خطا",
            values="تعداد پنجره",
            hole=0.55,
            color="نوع خطا",
            color_discrete_map={
                "بحران دیتابیس و شبکه": "#EF553B",
                "شکست ترانزکشن": "#3B82F6",
                "باگ کد جاوا": "#F59E0B",
                "رد قوانین بیمه": "#8B5CF6"
            }
        )
        fig.update_traces(textinfo="percent+label", textposition="inside", textfont_size=14)
        fig.update_layout(showlegend=False, height=300, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
    else:
        st.success("هیچ خطایی در این فایل ثبت نشده است.")

with col_summary:
    st.markdown("#### 📌 خلاصه وضعیت سرویس")
    if total_anomalies > 0:
        st.error(f"⚠️ مدل Laya تعداد **{total_anomalies} پنجره بحرانی** را در لاگ `{selected_file}` شناسایی کرد.")
        st.markdown(f"""
        - **علت شایع:** قطع مکرر ارتباط با پایگاه داده و ناتوانی در دریافت کانکشن JDBC (`GenericJDBCException`).
        - **اثرات جانبی:** رول‌بک شدن جاب‌های اصلاح کارمزد (`CorrectiveCommissionIssuanceDraftSchedule`).
        - **اقدام اولویت‌دار:** بازبینی سلامت دیتابیس اوراکل/پستگرس و افزایش سقف کانکشن‌های DataSource.
        """)
    else:
        st.success("تمامی پنجره‌های لاگ دارای وضعیت عادی و بدون خطا هستند.")

# ۹. فید آخرین خطاهای کشف‌شده (Stream of Latest Errors)
st.markdown("<hr style='border: 1px solid #2B3245; margin: 25px 0;'>", unsafe_allow_html=True)
st.markdown("### 🚨 آخرین خطاهای کشف‌شده توسط Laya (جریان بلادرنگ پنجره‌ها)")

if anomalies_df.empty:
    st.success("هیچ خطایی یافت نشد. وضعیت سیستم پایدار است.")
else:
    # نمایش ۲۰ پنجره خطای اخیر
    for _, item in anomalies_df.head(20).iterrows():
        sev_icon = "🔴 بحرانی" if item["severity"] == "CRITICAL" else ("🟠 بالا" if item["severity"] == "HIGH" else "🟡 متوسط")
        category_name = item.get("category_fa", item.get("category", "خطا"))
        
        with st.expander(f"{sev_icon} | {item['window_id']} (سطرهای {item['start_line']} تا {item['end_line']}) | {category_name} ({item['exception_type']})"):
            c_info1, c_info2 = st.columns(2)
            with c_info1:
                st.markdown(f"**زمان رخداد:** `{item['timestamp']}`")
                st.markdown(f"**ترد سیستم:** `{item['thread']}`")
            with c_info2:
                st.markdown(f"**شناسه پنجره:** `{item['window_id']}`")
                st.markdown(f"**هم‌پوشانی پنجره:** `{item['overlap_lines']} سطر مشترک ({item['overlap_percent']}%)`")
            
            st.markdown(f"**علت ریشه‌ای خطا (Root Cause):**")
            st.info(item["root_cause"])
            
            st.markdown(f"**راهکار پیشنهادی برای تیم عملیات (Action):**")
            st.warning(item["recommended_action"])

            if item["snippet"]:
                st.markdown("**قطعه لاگ خام پنجره:**")
                st.code(item["snippet"], language="text")

# ۱۰. رفرش خودکار هر ۳ ثانیه
time.sleep(3)
st.rerun()
