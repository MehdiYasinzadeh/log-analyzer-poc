import os
import re
from datetime import datetime
from typing import List, Dict, Any, Generator

class SpringLogParser:
    """
    High-performance streaming multi-line parser for Spring Boot, Logback, and WebLogic logs.
    """
    HEADER_REGEX = re.compile(
        r'^(?:\[(?P<ts1>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]|(?P<ts2>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d{3})?))\s+'
        r'(?P<level>INFO|ERROR|WARN|DEBUG|FATAL|TRACE)\s+'
        r'(?:\[(?P<thread>[^\]]+)\])?(?:\s*-\s*|\s*:\s*|\s+)'
        r'(?P<message>.*)$'
    )

    @classmethod
    def parse_file(cls, file_path: str, max_events: int = 5000) -> List[Dict[str, Any]]:
        events = []
        current_event = None

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Log file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
            for line_no, raw_line in enumerate(fp, start=1):
                line = raw_line.rstrip("\r\n")
                match = cls.HEADER_REGEX.match(line)

                if match:
                    if current_event:
                        events.append(current_event)
                        if len(events) >= max_events:
                            return events

                    ts = match.group("ts1") or match.group("ts2")
                    current_event = {
                        "event_id": f"evt_{line_no}",
                        "start_line": line_no,
                        "timestamp": ts,
                        "level": match.group("level"),
                        "thread": match.group("thread") or "main",
                        "header_message": match.group("message"),
                        "raw_lines": [line],
                        "stacktrace": []
                    }
                else:
                    if current_event:
                        current_event["raw_lines"].append(line)
                        trimmed = line.strip()
                        if trimmed.startswith(("at ", "Caused by:", "...")) or "Exception" in trimmed or "Error" in trimmed:
                            current_event["stacktrace"].append(trimmed)

            if current_event and len(events) < max_events:
                events.append(current_event)

        return events


class SpringIncidentClassifier:
    """
    Classifies Spring Boot log events into actionable SRE / Business categories.
    """
    CATEGORY_LABELS = {
        "NORMAL": "عادی (روند روتین سرویس)",
        "INFRASTRUCTURE_OUTAGE": "بحران زیرساخت و دیتابیس (Infrastructure Outage)",
        "TRANSACTION_FAILURE": "شکست و رول‌بک ترانزکشن (Transaction Rollback)",
        "BUSINESS_RULE_REJECTION": "عدم تأیید قوانین بیمه (Business Rule Rejection)",
        "SOFTWARE_DEFECT": "خطای برنامه‌نویسی و باگ نرم‌افزاری (Software Defect)",
        "SYSTEM_WARNING": "هشدار سیستمی (System Warning)"
    }

    @staticmethod
    def analyze_event(event: Dict[str, Any]) -> Dict[str, Any]:
        level = event["level"]
        
        # 1. Normal operational event
        if level in ("INFO", "DEBUG", "TRACE"):
            return {
                "category": "NORMAL",
                "category_fa": "عادی (روند روتین سرویس)",
                "severity": "INFO",
                "exception_type": None,
                "root_cause": "عملیات استاندارد سرویس",
                "recommended_action": "نیازی به اقدام ندارد."
            }

        # 2. Warning without stacktrace
        if level == "WARN" and not event["stacktrace"]:
            return {
                "category": "SYSTEM_WARNING",
                "category_fa": "هشدار سیستمی (System Warning)",
                "severity": "LOW",
                "exception_type": None,
                "root_cause": event["header_message"],
                "recommended_action": "بررسی منابع یا تکرار هشدار در ساعات اوج بار."
            }

        # 3. Analyze Error / Stacktrace
        full_text = "\n".join(event["raw_lines"])
        
        # Extract exception chain: valid Java Exception/Error class names
        causes = re.findall(r'(\b(?:[a-z0-9_]+\.)*[A-Z][a-zA-Z0-9_]*(?:Exception|Error))(?::\s*([^\n\r\t]+))?', full_text)
        
        # Filter out logger names like CompressedExceptionLogger
        valid_causes = [c for c in causes if not c[0].endswith("Logger")]
        
        if valid_causes:
            # Pick the primary/root exception
            # In Java stack traces, the last 'Caused by' or the most specific exception is the root cause
            root_exc = valid_causes[-1][0]
            root_msg = valid_causes[-1][1].strip() if valid_causes[-1][1] else ""
            if not root_msg and len(valid_causes) > 1:
                # If last had empty message, check if earlier had message
                for c in reversed(valid_causes):
                    if c[1].strip():
                        root_msg = c[1].strip()
                        break
        else:
            root_exc = "UnknownException"
            root_msg = event["header_message"]

        # Short class name of exception
        exc_short = root_exc.split(".")[-1]

        # Categorize
        # A) Infrastructure & Connectivity Outages
        if re.search(r'(JDBC|Connection|SQLException|MongoSocket|MongoTimeout|DataAccessResourceFailure|CannotAcquireLock|TimeoutException|ResourceException|PersistenceException|JpaSystemException|RollbackException|ConnectException|SocketTimeout|UnknownHost|HttpServerError|RestClientException|BadGateway)', root_exc):
            category = "INFRASTRUCTURE_OUTAGE"
            severity = "CRITICAL"
            root_cause = f"اختلال زیرساخت/دیتابیس ({exc_short}): {root_msg or 'قطعی ارتباط یا خطای ترانزکشن'}"
            recommendation = "بررسی سلامت دیتابیس/کلاستر، بررسی ترافیک شبکه، و مانیتورینگ وضعیت Connection Pool."

        # B) Insurance Business Rule Rejections
        elif re.search(r'(RuleException|ValidationException|ConstraintViolation|MethodArgumentNotValid|BindException)', root_exc):
            category = "BUSINESS_RULE_REJECTION"
            severity = "MEDIUM"
            root_cause = f"رد بر اساس قوانین بیمه ({exc_short}): {root_msg or 'عدم انطباق با شروط و قوانین کسب‌وکار'}"
            recommendation = "بررسی پرونده و داده‌های ورودی؛ نیاز به اصلاح اطلاعات بیمه‌نامه یا مدارک توسط کاربر."

        # C) Code Bug / Crash
        elif re.search(r'(NullPointerException|IndexOutOfBounds|ClassCast|IllegalState|IllegalArgument|NoSuchMethod|ClassNotFound)', root_exc):
            category = "SOFTWARE_DEFECT"
            severity = "HIGH"
            root_cause = f"باگ نرم‌افزاری جاوا ({exc_short}): {root_msg or 'دسترسی نامعتبر یا مقدار تهی (Null)'}"
            recommendation = "ارجاع به تیم توسعه جهت دیباگ متد، افزودن Null-check و بررسی سطر مشخص‌شده در استک‌تریس."

        else:
            category = "SYSTEM_WARNING" if level == "WARN" else "SOFTWARE_DEFECT"
            severity = "MEDIUM"
            root_cause = f"خطای سیستمی ({exc_short}): {root_msg or event['header_message']}"
            recommendation = "بررسی استک‌تریس و بررسی رویدادهای هم‌زمان در همان لاگ."

        return {
            "category": category,
            "category_fa": SpringIncidentClassifier.CATEGORY_LABELS.get(category, category),
            "severity": severity,
            "exception_type": exc_short,
            "exception_full": root_exc,
            "root_message": root_msg,
            "root_cause": root_cause,
            "recommended_action": recommendation
        }

    @classmethod
    def analyze_window(cls, window: Dict[str, Any], laya_prediction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes a sliding window based on Laya's gatekeeper prediction.
        """
        is_error = laya_prediction.get("predicted_label") == "Error"
        confidence = laya_prediction.get("confidence", 0.90)

        # 1. Normal window according to Laya
        if not is_error:
            return {
                "window_id": window["window_id"],
                "start_line": window["start_line"],
                "end_line": window["end_line"],
                "is_anomaly": False,
                "confidence": confidence,
                "category": "NORMAL",
                "category_fa": cls.CATEGORY_LABELS["NORMAL"],
                "severity": "NORMAL",
                "exception_type": None,
                "root_cause": "روند عادی سرور بدون خطا",
                "recommended_action": "وضعیت پایدار؛ نیازی به اقدام ندارد.",
                "timestamp": "N/A",
                "thread": "N/A",
                "snippet": window["lines"][0] if window.get("lines") else ""
            }

        # 2. Window is flagged as ANOMALY / ERROR by Laya: Extract Root Cause
        text = window.get("combined_text", "")
        lines = window.get("lines", text.split("\n"))

        # Find timestamp
        ts_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', text)
        timestamp = ts_match.group(1) if ts_match else "نامشخص"

        # Find thread
        thread_match = re.search(r'\[([^\]]+)\]', text)
        thread = thread_match.group(1) if thread_match else "main"

        # Extract thrown exceptions
        exc_pattern = re.compile(r'(?:Caused by:\s*|^|\n\s*|\s*-\s*)([a-zA-Z0-9_.]+(?:Exception|Error))(?::\s*([^\n\r\t]+))?')
        matches = exc_pattern.findall(text)
        valid_causes = [m for m in matches if not m[0].endswith(('Runnable', 'Logger', 'Handler', 'Helper', 'Template', 'Factory'))]

        if valid_causes:
            root_exc = valid_causes[-1][0]
            root_msg = valid_causes[-1][1].strip() if valid_causes[-1][1] else ""
            if not root_msg and len(valid_causes) > 1:
                for c in reversed(valid_causes):
                    if c[1].strip():
                        root_msg = c[1].strip()
                        break
        else:
            # Fallback check for JDBC / Rollback / gRPC / Payment in raw text
            if "JDBC Connection" in text:
                root_exc = "GenericJDBCException"
                root_msg = "Unable to acquire JDBC Connection"
            elif "rollback" in text.lower():
                root_exc = "RollbackException"
                root_msg = "Transaction rollback detected"
            elif "UNAVAILABLE" in text or "StatusRuntimeException" in text or "code=UNAVAILABLE" in text:
                root_exc = "StatusRuntimeException"
                root_msg = "gRPC service unavailable (Status.UNAVAILABLE)"
            elif "Payment request failed" in text or "Invalid token" in text:
                root_exc = "PaymentProcessingException"
                root_msg = "Payment charge rejected / Invalid token"
            else:
                root_exc = "ApplicationError"
                root_msg = lines[0] if lines else "Error detected in window"

        exc_short = root_exc.split(".")[-1]

        # Categorize
        if re.search(r'(JDBC|Connection|SQLException|MongoSocket|MongoTimeout|DataAccessResourceFailure|CannotAcquireLock|TimeoutException|ResourceException|PersistenceException|JpaSystemException|StatusRuntimeException|UNAVAILABLE)', root_exc):
            category = "INFRASTRUCTURE_OUTAGE"
            severity = "CRITICAL"
            root_cause = f"بحران زیرساخت و ارتباط شبکه ({exc_short}): {root_msg or 'عدم دسترس‌پذیری سرویس یا پایگاه داده'}"
            recommendation = "بررسی سلامت سرویس دیتابیس/gRPC، ترافیک شبکه‌ای و بازبینی لود سرور و وضعیت Circuit Breaker."

        elif "OutOfMemoryError" in root_exc or "heap space" in text.lower():
            category = "INFRASTRUCTURE_OUTAGE"
            severity = "CRITICAL"
            root_cause = f"بحران منابع سرور و سرریز حافظه ({exc_short}): تکمیل ظرفیت JVM Heap Space و عدم امکان تخصیص آبجکت جدید"
            recommendation = "بررسی نشت حافظه (Memory Leak)، آنالیز Heap Dump با Eclipse MAT و بازبینی پارامترهای -Xmx جاوا."

        elif re.search(r'(RollbackException|TransactionSystemException|UnexpectedRollbackException|HeuristicHazard|PaymentProcessingException)', root_exc) or "rollback" in text.lower() or "payment" in text.lower():
            category = "TRANSACTION_FAILURE"
            severity = "HIGH"
            root_cause = f"خطای تراکنش و عملیات مالی ({exc_short}): {root_msg or 'ترانزکشن مالی یا جاب پردازشی با شکست مواجه شد'}"
            recommendation = "بررسی درگاه پرداخت، اعتبار توکن تراکنش، زمان timeout تراکنش و اطمینان از صحت لاگ‌ها."

        elif re.search(r'(RuleException|ValidationException|ConstraintViolation|MethodArgumentNotValid)', root_exc):
            category = "BUSINESS_RULE_REJECTION"
            severity = "MEDIUM"
            root_cause = f"عدم انطباق با قوانین بیمه ({exc_short}): {root_msg or 'رد درخواست بر اساس قوانین سیستم'}"
            recommendation = "بررسی اطلاعات بیمه‌نامه یا مدارک ورودی و اصلاح داده‌ها توسط کارشناس."

        elif re.search(r'(NullPointerException|IndexOutOfBounds|ClassCast|IllegalState|IllegalArgument)', root_exc):
            category = "SOFTWARE_DEFECT"
            severity = "HIGH"
            root_cause = f"باگ نرم‌افزاری در کد جاوا ({exc_short}): مقداردهی تهی (Null) یا دسترسی نامعتبر"
            recommendation = "ارجاع به تیم توسعه جهت اصلاح شرط‌های بررسی مقدار تهی (Null-Check) و دیباگ متد."

        else:
            category = "SOFTWARE_DEFECT"
            severity = "MEDIUM"
            root_cause = f"خطای اجرای سرویس ({exc_short}): {root_msg}"
            recommendation = "بررسی لاگ‌های هم‌زمان و فراخوانی مجدد در صورت خطای گذرا."

        return {
            "window_id": window["window_id"],
            "start_line": window["start_line"],
            "end_line": window["end_line"],
            "is_anomaly": True,
            "confidence": confidence,
            "category": category,
            "category_fa": cls.CATEGORY_LABELS.get(category, category),
            "severity": severity,
            "exception_type": exc_short,
            "exception_full": root_exc,
            "root_cause": root_cause,
            "recommended_action": recommendation,
            "timestamp": timestamp,
            "thread": thread,
            "snippet": "\n".join(lines[:6])
        }

