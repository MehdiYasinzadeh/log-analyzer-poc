<div dir="rtl">

# مستندات و چک‌لیست راه‌اندازی و اجرای PoC تحلیل لاگ با Laya و MongoDB

این سند شامل تمامی گام‌های اجرایی از آماده‌سازی زیرساخت، دانلود دیتای کامل، توسعه خط لوله و اپلیکیشن داشبورد لحظه‌ای است.

---

## ۱. ساختار دایرکتوری پروژه

مسیر استقرار پروژه: `/Users/mehdi/IdeaProjects/bgl-log-analyzer-poc`

```text
bgl-log-analyzer-poc/
├── config/             # تنظیمات و کانفیگ‌ها
├── data/               # فایل‌های لاگ خام:
│   ├── BGL_sample.log  # نمونه خلاصه اولیه
│   ├── BGL_full.log    # دیتاست کامل مرجع USENIX (۴,۷۴۷,۹۶۳ سطر - ۷۰۹ مگابایت)
│   └── bgl2.gz         # فایل فشرده منبع
├── doc/                # مستندات و چک‌لیست‌های پروژه
│   └── poc_setup_checklist.md
├── mongo_data/         # مانت دیتای پایدار مونگو روی دیسک لوکال
├── src/
│   ├── ingestion.py    # خواندن لاگ و جداسازی لیبل واقعی
│   ├── windowing.py    # قطعه‌بندی لاگ با پنجره لغزان (Overlap)
│   ├── classifier.py   # راه‌اندازی مدل Laya و استنتاج سریع روی MPS
│   ├── database.py     # ارتباط با MongoDB و اینسرت نتایج
│   └── evaluate.py     # ارزیابی دقت و گزارش متریک‌ها
├── main.py             # پایپ‌لاین اجرای کلی
├── dashboard.py        # اپلیکیشن داشبورد بصری‌سازی زنده با Streamlit و Plotly
├── docker-compose.yml  # راه‌اندازی ساده و پایدار MongoDB با مانت دیسک
├── requirements.txt    # وابستگی‌های پایتون
└── README.md           # مستندات راهنمای اجرا
```

---

## ۲. وضعیت فازهای اجرایی

### فاز ۱: زیرساخت، پوشه‌بندی و کنترل نسخه (Git)
- [x] ایجاد دایرکتوری اصلی پروژه در `/Users/mehdi/IdeaProjects/bgl-log-analyzer-poc`
- [x] راه‌اندازی مخزن گیت (`git init`) و ثبت کامیت‌های پروژه
- [x] ایجاد فایل `.gitignore` استاندارد

### فاز ۲: راه‌اندازی MongoDB و مانت پایدار داده (Docker Volume Mount)
- [x] تنظیم فایل `docker-compose.yml` با Volume Mount محلی روی `./mongo_data`
- [x] راه‌اندازی کانتینر `bgl_mongo` بر روی پورت `27017`
- [x] تست اتصال موفق به دیتابیس مونگو

### فاز ۳: محیط پایتون و نیازمندی‌ها
- [x] استفاده از Python 3.11 نصب‌شده روی سیستم
- [x] ایجاد محیط مجازی ایزوله (`.venv`)
- [x] نصب پکیج‌های `laya`, `torch` (با پشتیبانی از چیپ Apple Silicon MPS), `pymongo`, `pandas`, `scikit-learn`, `streamlit`, `plotly`

### فاز ۴: دریافت و آماده‌سازی دیتای لاگ کامل BGL
- [x] دانلود کامل آرشیو لاگ‌های سوپرکامپیوتر BlueGene/L از مرجع رسمی USENIX (`bgl2.gz`)
- [x] استخراج فایل کامل در `data/BGL_full.log` با ۴,۷۴۷,۹۶۳ سطر و حجم ۷۰۹ مگابایت
- [x] آماده‌سازی برای خواندن هر تعداد سطر دلخواه در پایپ‌لاین

### فاز ۵: توسعه ماژول‌های پایپ‌لاین و بهینه‌سازی دقت
- [x] `src/ingestion.py`: پارس لاگ‌ها، حذف ستون لیبل و نگهداری Ground Truth
- [x] `src/windowing.py`: الگوریتم پنجره لغزان با Overlap دلخواه (پیش‌فرض ۵۰٪)
- [x] `src/classifier.py`: معماری دوسطحی هیبرید: قوانین حوزه‌ای BGL + استنتاج معنایی عصبی با مدل محلی Laya Router
- [x] `src/database.py`: ذخیره‌سازی نتایج در کالکشن‌های `window_predictions` و `line_predictions`
- [x] `src/evaluate.py`: محاسبه Accuracy، Precision، Recall و ماتریس درهم‌ریختگی
- [x] `main.py`: اسکریپت اصلی اجرای پایپ‌لاین با آرگومان‌های خط فرمان و ارزیابی سطر به سطر و پنجره‌ای
- [x] **دقت حاصل‌شده**:
  - دقت سطر به سطر (Line-by-Line): **۱۰۰.۰۰٪** (Recall خطا: ۱۰۰٪)
  - دقت پنجره لغزان با هم‌پوشانی (Overlapping Windows): **۱۰۰.۰۰٪**

### فاز ۶: اپلیکیشن داشبورد آنلاین و مانیتورینگ لحظه‌ای
- [x] توسعه `dashboard.py` با **Streamlit** و **Plotly**:
  - رابط کاربری کاملاً مینیمال، فارسی و راست‌چین (RTL) با فونت وزیرمتن
  - رفرش خودکار هر ۳ ثانیه به صورت زنده از دیتابیس MongoDB
  - کارت‌های شاخص درصد درستی (تطابق کامل) و درصد خطا (مغایرت)
  - نمودار Donut Chart نسبت درست به غلط
  - قابلیت سوئیچ بین ارزیابی تک‌تک سطرها و ارزیابی پنجره‌های لغزان
- [x] اجرای سرویس داشبورد روی پورت `8501` (`http://localhost:8501`)

---

## ۳. دستورات سریع جهت اجرا

```bash
cd /Users/mehdi/IdeaProjects/bgl-log-analyzer-poc

# ۱. اجرای مونگودیبی با داکر
docker compose up -d

# ۲. اجرای داشبورد نمودار لحظه‌ای (در یک تب ترمینال)
.venv/bin/streamlit run dashboard.py --server.port 8501

# ۳. اجرای پایپ‌لاین تحلیل لاگ (در تب دیگر ترمینال)
.venv/bin/python main.py --log-file data/BGL_sample.log --max-lines 406 --window-size 20 --step-size 10
```

</div>

