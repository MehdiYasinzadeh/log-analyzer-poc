# Enterprise AIOps: Two-Tier Intelligent Log Analysis & RCA Platform

پلتفرم سازمانی تحلیل هوشمند لاگ و ریشه‌یابی خطاها (AIOps) مبتنی بر معماری شناختی دو مرحله‌ای (**System 1 & System 2 Thinking**) با هسته ارکستراسیون Spring Boot 3، مدل طبقه‌بندی سریع Laya، و مدل استدلالی عمیق LLM.

---

## ۱. بیانیه معماری و فلسفه طراحی (Architecture Philosophy)

در سیستم‌های بزرگ سازمانی و میکروسرویسی، روزانه صدها هزار سطر لاگ تولید می‌شود. ارسال مستقیم تمامی لاگ‌ها به یک مدل زبانی بزرگ (LLM):
1. هزینه محاسباتی بسیار سنگینی دارد.
2. کارت‌های گرافیک را داغ و اشباع می‌کند.
3. زمان پاسخ‌دهی را به شدت افزایش می‌دهد.

برای حل این چالش، این پلتفرم از یک معماری **دو سطحی (Two-Tier Cognitive Architecture)** استفاده می‌کند:

```
                               ┌────────────────────────────────────────────────────────┐
                               │           Enterprise Applications / Microservices      │
                               │          (Kubernetes Pods, Spring Boot, Databases)     │
                               └───────────────────────────┬────────────────────────────┘
                                                           │ (Log Stream / File Tailer)
                                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          AIOPS ORCHESTRATOR (Spring Boot 3.x)                                          │
│                                                                                                                        │
│  ┌───────────────────────┐       ┌────────────────────────┐       ┌─────────────────────────────────────────────────┐  │
│  │ 1. Log Ingestion      │ ────> │ 2. Sliding Buffer      │ ────> │ 3. Gatekeeper & Signature Deduplicator          │  │
│  │ (Non-blocking Stream) │       │ (Circular Window 50 L) │       │ (Debounce 95% noise; Group recurring incidents) │  │
│  └───────────────────────┘       └────────────────────────┘       └────────────────────────┬────────────────────────┘  │
│                                                                                            │                           │
│                                                                                            │ (Candidate Windows)       │
│                                                                                            ▼                           │
│                                                           ┌─────────────────────────────────────────────────┐          │
│                                                           │ 4. System-1 Client (REST to FastAPI Laya)       │          │
│                                                           │    Check if Window is: NORMAL or ERROR          │          │
│                                                           └────────────────────────┬────────────────────────┘          │
│                                                                                    │                           │
│                                                        [Only If Anomaly/Error]     │                           │
│                                                                                    ▼                           │
│                                                           ┌─────────────────────────────────────────────────┐          │
│                                                           │ 5. System-2 Agentic Engine (Spring AI / Rest)   │          │
│                                                           │    Multi-Turn Loop (NEED_MORE_LOGS Protocol)    │          │
│                                                           └────────────────────────┬────────────────────────┘          │
│                                                                                    │                           │
│                                                                                    ▼                           │
│                                                           ┌─────────────────────────────────────────────────┐          │
│                                                           │ 6. Persistence & Metrics (JPA / Micrometer)     │          │
│                                                           │    Persist Incidents to PostgreSQL              │          │
│                                                           └────────────────────────┬────────────────────────┘          │
└────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────┘
                                                                                     │
                         ┌───────────────────────────────────┬───────────────────────┴───────────────────────┐
                         │                                   │                                               │
                         ▼ (REST POST /predict)              ▼ (REST POST /api/chat)                         ▼ (SQL DataSource)
        ┌──────────────────────────────────┐┌──────────────────────────────────┐┌──────────────────────────────────┐
        │       FASTAPI LAYA SERVICE       ││       OLLAMA LOCAL SERVER        ││        GRAFANA DASHBOARD         │
        │           (System 1)             ││           (System 2)             ││          (Presentation)          │
        │ - Model: NandhaKishorM/laya      ││ - Model: qwen2.5-coder:7b        ││ - Real-time Incident Table       │
        │ - Non-autoregressive forward pass││ - Hardware: AMD RX 5600 XT       ││ - Root Cause Summary (FA)        │
        │ - Latency: < 5ms per check       ││ - Vulkan RADV (~50 tokens/sec)   ││ - Actionable Remediation (FA)    │
        │ - Classify: Normal vs Error      ││ - Thermal Guard Managed Fans     ││ - Direct Link to Exact Raw Logs  │
        └──────────────────────────────────┘└──────────────────────────────────┘└──────────────────────────────────┘
```

---

## ۲. اجزای اصلی سیستم (System Components)

### ماژول ۱: هسته هماهنگ‌کننده و پردازش ابری (`aiops-orchestrator` - Spring Boot 3.x)
* **فناوری:** Java 21, Spring Boot 3.x, Spring Data JPA, Spring AI (یا RestClient).
* **وظایف:**
  * **دریافت لاگ (Ingestion):** خواندن زنده فایل‌های لاگ (File Tailer با نگهداری Offset) یا دریافت مستقیم از طریق Logback Socket بدون ریسک قطعی شبکه.
  * **بافر هوشمند (Sliding Window Buffer):** ذخیره ۵۰ سطر قبل و بعد از هر خطا در حافظه رم با ساختار داده بافر حلقوی (Circular RingBuffer).
  * **مدیریت تکرار (Debouncing & Signature Cache):** ادغام خطاهای تکراری با استخراج امضای استک‌تریس (مانند `NullPointerException@FanavaranMapperService`).
  * **تعامل چندمرحله‌ای (Agentic Loop):** ارسال پرامپت به اولاما و در صورت بازگشت پاسخ `NEED_MORE_LOGS`، استخراج خطوط ماقبل/مابعد از بافر و ارسال مجدد به مدل.
  * **پایگاه داده (Database):** ثبت حوادث و تحلیل‌ها در پایگاه داده PostgreSQL جهت مانیتورینگ.

### ماژول ۲: سرویس طبقه‌بندی سریع (`aiops-laya-service` - Python / FastAPI)
* **فناوری:** Python 3.11, FastAPI, Uvicorn, PyTorch, [Laya (NandhaKishorM/laya)](https://github.com/NandhaKishorM/laya).
* **وظایف:**
  * اجرای مدل بسیار سریع و غیرخودبازگشتی Laya Router.
  * تفکیک پنجره‌های عادی (`Normal`) از پنجره‌های بحرانی (`Error`) در کمتر از ۵ میلی‌ثانیه.
  * پاسخ‌دهی به اسپرینگ‌بوت از طریق اندپوینت ساده `POST /v1/classify`.

### ماژول ۳: مدل استنتاج زبانی (`aiops-llm-engine` - Ollama Server)
* **فناوری:** Ollama, `qwen2.5-coder:7b`.
* **سخت‌افزار:** AMD Radeon RX 5600 XT روی سرور محلی (`192.168.50.253`) با درایور Vulkan RADV.
* **وظایف:**
  * تحلیل عمیق استک‌تریس و لاگ‌های خطا.
  * استخراج علت ریشه‌ای خطا (Root Cause) به زبان فارسی.
  * ارائه گام‌های مشخص رفع عیب (Actionable Remediation) به زبان فارسی.
  * سیستم محافظت حرارتی (Thermal Guard) با کنترل خودکار دور فن‌ها (PWM) در دمای زیر ۵۰ درجه.

### ماژول ۴: رابط بصری و داشبورد مدیریتی (`aiops-dashboard` - Grafana)
* **فناوری:** Grafana 11/13, PostgreSQL Datasource, Loki Log Viewer.
* **وظایف:**
  * نمایش زنده لاگ‌های سیستم.
  * پنل اختصاصی **«حوادث کشف‌شده توسط هوش مصنوعی»** شامل: زمان رخداد، سرویس هدف، تعداد تکرار، امضای خطا، علت ریشه‌ای و راهکار رفع باگ.

---

## ۳. نتایج اعتبارسنجی عملی (PoC Benchmarks)

عملکرد این معماری روی لاگ‌های واقعی و سازمانی تست و تایید گردید:

| شاخص ارزیابی | داده تست ۱ (`ACC-BATCH.log`) | داده تست ۲ (`api-transmitter-service.log`) |
|---|:---:|:---:|
| **تعداد کل سطرهای فایل** | ۳۸,۹۳۶ سطر | ۸۲,۸۰۰ سطر |
| **زمان اسکن و غربال‌گری** | ۰.۰۸ ثانیه | ۰.۱۸ ثانیه |
| **خطاهای خام کشف‌شده** | ۹۵۲ رخداد | ۳۹ رخداد |
| **تعداد امضاهای یکتا (Debounced)** | ۳ حادثه مجزا | ۵ حادثه مجزا |
| **نرخ کاهش فشار روی LLM** | **۹۹.۷٪** کاهش بار | **۸۷.۲٪** کاهش بار |
| **میانگین سرعت استنتاج GPU** | ۴۹.۵ توکن بر ثانیه | ۴۹.۶ توکن بر ثانیه |
| **پشتیبانی از Multi-Turn** | موفق (درخواست کانتکست قبل) | موفق (درخواست ۲۰ سطر قبل برای Feign) |
| **دمای کارت گرافیک** | ۴۱ تا ۵۲ درجه سانتی‌گراد | ۴۵ تا ۵۰ درجه سانتی‌گراد |

---

## ۴. نقشه راه پیاده‌سازی و ساختار چند ریپازیتوری (Multi-Repo Roadmap)

برای ایجاد معماری تمیز و آماده ارائه سازمانی، پروژه به تفکیک زیر سازمان‌دهی می‌شود:

```text
├── 1. aiops-orchestrator/        # [ریپازیتوری اسپرینگ‌بوت] هسته بیزنس، لاگ‌بک، بافر، اسپرینگ ای‌آی، دیتابیس
├── 2. aiops-laya-detector/       # [ریپازیتوری پایتون] میکروسرویس سبک FastAPI برای مدل Laya
├── 3. aiops-observability/       # [ریپازیتوری مانیتورینگ] کانفیگ‌های Grafana، دیتاسورس‌ها و کامپوزها
└── 4. log-analyzer-poc/          # [این ریپازیتوری] کدهای تست اولیه و بنچ‌مارک‌های PoC
```

---

*تنظیم و تدوین شده جهت توسعه پایدار و ارائه دمو سازمانی AIOps.*
