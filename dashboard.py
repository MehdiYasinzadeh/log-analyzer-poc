import time
import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient

# تنظیمات پایه
st.set_page_config(
    page_title="داشبورد پایش و تحلیل هوشمند لاگ‌ها",
    page_icon="🛡️",
    layout="wide"
)

# اعمال استایل راست‌چین (RTL) و فونت فارسی
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
    padding: 20px;
    text-align: center;
    border: 1px solid #2B3245;
    margin-bottom: 15px;
}
.metric-box.normal { border-top: 5px solid #00CC96; }
.metric-box.infra { border-top: 5px solid #EF553B; }
.metric-box.bug { border-top: 5px solid #FFA15A; }
.metric-box.rule { border-top: 5px solid #AB63FA; }

.metric-title {
    font-size: 15px;
    color: #94A3B8;
    margin-bottom: 8px;
}
.metric-value {
    font-size: 38px;
    font-weight: 900;
    margin-bottom: 4px;
}
.metric-value.normal { color: #00CC96; }
.metric-value.infra { color: #EF553B; }
.metric-value.bug { color: #FFA15A; }
.metric-value.rule { color: #AB63FA; }

.metric-sub {
    font-size: 13px;
    color: #64748B;
}

.incident-card {
    background: #181C26;
    border: 1px solid #283042;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 12px;
}
.incident-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# تنظیمات دیتابیس
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

# تیتر اصلی
st.markdown("<h2 style='text-align: center;'>🛡️ دستیار هوشمند پایش و تحلیل حوادث لاگ (AIOps Copilot)</h2>", unsafe_allow_html=True)

# انتخاب حالت کاری
active_mode = st.radio(
    "انتخاب سیستم جهت تحلیل:",
    ["سیستم لاگ‌های اسپرینگ‌بوت بیمه (Spring Boot AIOps)", "بنچمارک سوپرکامپیوتر (BGL Benchmark)"],
    horizontal=True
)

st.markdown("<hr style='border: 1px solid #2B3245; margin: 20px 0;'>", unsafe_allow_html=True)

# ========================================================
# ۱. حالت لاگ‌های اسپرینگ‌بوت بیمه
# ========================================================
if "اسپرینگ‌بوت" in active_mode:
    col = db["spring_incidents"]
    
    # لیست فایل‌های تحلیل‌شده
    available_files = col.distinct("source_file")
    
    if not available_files:
        st.info("داده‌ای از لاگ‌های اسپرینگ‌بوت در دیتابیس یافت نشد. لطفاً اسکریپت `spring_main.py` را اجرا کنید.")
        st.stop()
        
    selected_file = st.selectbox(
        "انتخاب فایل لاگ سازمانی جهت پایش:",
        ["تمامی فایل‌ها"] + available_files,
        index=0
    )
    
    query = {} if selected_file == "تمامی فایل‌ها" else {"source_file": selected_file}
    records = list(col.find(query, {"_id": 0}))
    
    if not records:
        st.warning("هیچ رویدادی برای این فایل ثبت نشده است.")
        st.stop()
        
    df = pd.DataFrame(records)
    total_events = len(df)
    
    # شمارش دسته‌ها
    norm_count = (df["category"] == "NORMAL").sum()
    infra_count = (df["category"] == "INFRASTRUCTURE_OUTAGE").sum()
    bug_count = (df["category"] == "SOFTWARE_DEFECT").sum()
    rule_count = (df["category"] == "BUSINESS_RULE_REJECTION").sum()
    
    # کارت‌های KPI
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-box normal">
            <div class="metric-title">عملیات عادی (Normal)</div>
            <div class="metric-value normal">{norm_count:,}</div>
            <div class="metric-sub">{norm_count/total_events*100:.1f}٪ از کل رویدادها</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-box infra">
            <div class="metric-title">بحران زیرساخت و دیتابیس</div>
            <div class="metric-value infra">{infra_count:,}</div>
            <div class="metric-sub">نیاز به مداخله فوری SRE/DBA</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-box bug">
            <div class="metric-title">باگ نرم‌افزاری کد (Defect)</div>
            <div class="metric-value bug">{bug_count:,}</div>
            <div class="metric-sub">ارجاع به تیم توسعه جهت رفع خطا</div>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="metric-box rule">
            <div class="metric-title">رد قوانین کسب‌وکار بیمه</div>
            <div class="metric-value rule">{rule_count:,}</div>
            <div class="metric-sub">عدم تایید مدارک / سقف بیمه</div>
        </div>
        """, unsafe_allow_html=True)
        
    # نمودار توزیع حوادث
    ch_col1, ch_col2 = st.columns([1, 1])
    
    with ch_col1:
        st.markdown("#### 📊 توزیع دسته‌بندی رخدادها")
        chart_data = pd.DataFrame({
            "دسته": ["عادی", "بحران زیرساخت", "باگ نرم‌افزاری", "رد قوانین بیمه"],
            "تعداد": [norm_count, infra_count, bug_count, rule_count]
        })
        chart_data = chart_data[chart_data["تعداد"] > 0]
        
        fig = px.pie(
            chart_data,
            names="دسته",
            values="تعداد",
            hole=0.55,
            color="دسته",
            color_discrete_map={
                "عادی": "#00CC96",
                "بحران زیرساخت": "#EF553B",
                "باگ نرم‌افزاری": "#FFA15A",
                "رد قوانین بیمه": "#AB63FA"
            }
        )
        fig.update_traces(textinfo="percent+label", textposition="inside")
        fig.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
        
    with ch_col2:
        st.markdown("#### 🚨 پرتکرارترین انواع Exception")
        err_df = df[df["category"] != "NORMAL"]
        if not err_df.empty and "exception_type" in err_df:
            top_excs = err_df["exception_type"].value_counts().head(5).reset_index()
            top_excs.columns = ["کلاس Exception", "تعداد"]
            fig_bar = px.bar(
                top_excs,
                x="تعداد",
                y="کلاس Exception",
                orientation="h",
                color="کلاس Exception",
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            fig_bar.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_bar, width="stretch")
        else:
            st.success("هیچ خطایی در این فایل ثبت نشده است (سیستم کاملاً سالم است).")

    # جدول حوادث شناسایی‌شده
    st.markdown("### 📋 فهرست حوادث و تحلیل علت ریشه‌ای (Root Cause Analysis)")
    incidents = df[df["category"] != "NORMAL"]
    
    if incidents.empty:
        st.success("🎉 هیچ حادثه‌ای شناسایی نشد. وضعیت سیستم پایدار است.")
    else:
        # فیلتر شدت
        sev_filter = st.multiselect(
            "فیلتر بر اساس شدت حادثه:",
            ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            default=["CRITICAL", "HIGH", "MEDIUM"]
        )
        filtered_incidents = incidents[incidents["severity"].isin(sev_filter)]
        
        for _, inc in filtered_incidents.head(20).iterrows():
            sev_badge = "🔴 بحرانی" if inc['severity'] == "CRITICAL" else ("🟠 بالا" if inc['severity'] == "HIGH" else "🟡 متوسط")
            with st.expander(f"{sev_badge} | {inc['timestamp']} | {inc['category_fa']} ({inc['exception_type']})"):
                st.markdown(f"**علت ریشه‌ای خطا:** {inc['root_cause']}")
                st.markdown(f"**راهکار پیشنهادی برای تیم عملیات:** `{inc['recommended_action']}`")
                st.markdown(f"**ترد و ماژول اجرا:** `{inc['thread']}`")
                if inc['stacktrace_preview']:
                    st.code(inc['stacktrace_preview'], language="text")

# ========================================================
# ۲. بنچمارک سوپرکامپیوتر BGL
# ========================================================
else:
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
        st.info("داده‌ای از بنچمارک BGL در دیتابیس یافت نشد.")
    else:
        bgl_df = pd.DataFrame(records)
        bgl_total = len(bgl_df)
        bgl_correct = (bgl_df["true_label"] == bgl_df["predicted_label"]).sum()
        bgl_wrong = bgl_total - bgl_correct
        bgl_pct_correct = (bgl_correct / bgl_total * 100) if bgl_total > 0 else 0
        bgl_pct_wrong = (bgl_wrong / bgl_total * 100) if bgl_total > 0 else 0

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <div class="metric-box normal">
                <div class="metric-title">پیش‌بینی درست (تطابق کامل)</div>
                <div class="metric-value normal">{bgl_pct_correct:.1f}٪</div>
                <div class="metric-sub">{bgl_correct:,} از {bgl_total:,} مورد</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="metric-box infra">
                <div class="metric-title">پیش‌بینی غلط (مغایرت)</div>
                <div class="metric-value infra">{bgl_pct_wrong:.1f}٪</div>
                <div class="metric-sub">{bgl_wrong:,} از {bgl_total:,} مورد</div>
            </div>
            """, unsafe_allow_html=True)

        chart_df = pd.DataFrame({
            "نتیجه": ["درست", "غلط"],
            "تعداد": [bgl_correct, bgl_wrong]
        })
        bgl_fig = px.pie(
            chart_df,
            names="نتیجه",
            values="تعداد",
            hole=0.55,
            color="نتیجه",
            color_discrete_map={"درست": "#00CC96", "غلط": "#EF553B"}
        )
        bgl_fig.update_traces(textinfo="percent+label", textposition="inside", textfont_size=16)
        bgl_fig.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(bgl_fig, width="stretch")

# رفرش دوره‌ای
time.sleep(4)
st.rerun()
