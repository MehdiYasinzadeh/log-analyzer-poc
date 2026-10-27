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
