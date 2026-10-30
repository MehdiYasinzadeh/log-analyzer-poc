import os
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque
import threading

import requests
from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

from src.classifier import LayaLogClassifier
from src.spring_analyzer import SpringIncidentClassifier

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "bgl_aiops"
COLLECTION_NAME = "otel_live_incidents"
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:8080")

# Windowing parameters
WINDOW_SIZE = 25
WINDOW_STEP = 12

app = FastAPI(title="AIOps OTel Log Analyzer & RCA Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared State
classifier: Optional[LayaLogClassifier] = None
service_buffers: Dict[str, deque] = {}
service_line_counters: Dict[str, int] = {}
service_window_counters: Dict[str, int] = {}
raw_logs_deque = deque(maxlen=400)
total_logs_ingested = 0
total_incidents_detected = 0
simulation_index = 0
state_lock = threading.Lock()

# MongoDB Client
mongo_client: Optional[MongoClient] = None
db = None
incidents_col = None

def get_mongo_collection():
    global mongo_client, db, incidents_col
    if incidents_col is None:
        try:
            mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            db = mongo_client[DB_NAME]
            incidents_col = db[COLLECTION_NAME]
            incidents_col.create_index([("timestamp", -1)])
            incidents_col.create_index([("service", 1)])
        except Exception as e:
            print(f"[Mongo Warning] Could not connect to MongoDB: {e}")
            incidents_col = None
    return incidents_col

def get_classifier():
    global classifier
    if classifier is None:
        print("[AIOps] Initializing LayaLogClassifier...")
        classifier = LayaLogClassifier(model_name="english")
    return classifier

def send_grafana_annotation(incident: Dict[str, Any]):
    """
    Sends an incident event as a native annotation to Grafana API.
    """
    annotation_urls = [
        "http://localhost:8080/api/annotations"
    ]
    
    text = (
        f"🚨 <b>AIOps Root Cause Analysis</b><br/>"
        f"<b>Service:</b> {incident.get('service')}<br/>"
        f"<b>Severity:</b> <span style='color:red;'>{incident.get('severity')}</span><br/>"
        f"<b>Category:</b> {incident.get('category_fa')} ({incident.get('category')})<br/>"
        f"<b>Root Cause:</b> {incident.get('root_cause')}<br/>"
        f"<b>Recommended SRE Action:</b> {incident.get('recommended_action')}"
    )

    payload = {
        "time": int(time.time() * 1000),
        "text": text,
        "tags": ["AIOps", "AI-RCA", incident.get("service", "unknown"), incident.get("severity", "HIGH")]
    }

    # Grafana default credentials or anonymous
    headers = {"Content-Type": "application/json"}
    auth = ("admin", "admin")

    for url in annotation_urls:
        try:
            resp = requests.post(url, json=payload, headers=headers, auth=auth, timeout=2.0)
            if resp.status_code in (200, 201):
                print(f"[Grafana] Successfully annotated incident at {url}: id={resp.json().get('id')}")
                return True
        except Exception:
            continue
    return False

def evaluate_window(service_name: str, window_lines: List[str], window_id: str, start_line: int, end_line: int):
    """
    Evaluates a 25-line window using Laya domain classifier and SpringIncidentClassifier.
    """
    global total_incidents_detected
    clf = get_classifier()
    
    window = {
        "window_id": window_id,
        "start_line": start_line,
        "end_line": end_line,
        "lines": window_lines,
        "combined_text": "\n".join(window_lines)
    }

    prediction = clf.classify_window(window)
    rca = SpringIncidentClassifier.analyze_window(window, prediction)

    is_anomaly = (
        (rca.get("is_anomaly") or prediction.get("predicted_label") == "Error")
        and float(prediction.get("confidence", 0.0)) >= 0.50
    )

    if is_anomaly:
        with state_lock:
            total_incidents_detected += 1

        incident_doc = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "time_epoch_ms": int(time.time() * 1000),
            "service": service_name,
            "window_id": window_id,
            "start_line": start_line,
            "end_line": end_line,
            "severity": rca.get("severity", "HIGH"),
            "category": rca.get("category", "SOFTWARE_DEFECT"),
            "category_fa": rca.get("category_fa", ""),
            "exception_type": rca.get("exception_type", "Unknown"),
            "root_cause": rca.get("root_cause", ""),
            "recommended_action": rca.get("recommended_action", ""),
            "confidence": float(rca.get("confidence", 0.95)),
            "thread": rca.get("thread", "main"),
            "raw_snippet": window_lines[-5:] if len(window_lines) >= 5 else window_lines
        }

        print(f"\n[🚨 ANOMALY DETECTED] Service: {service_name} | Severity: {incident_doc['severity']}")
        print(f"  Root Cause: {incident_doc['root_cause']}")
        print(f"  Recommended Action: {incident_doc['recommended_action']}")

        # Persist to Mongo
        col = get_mongo_collection()
        if col is not None:
            try:
                col.insert_one(incident_doc)
            except Exception as e:
                print(f"[Mongo Error] Failed to insert incident: {e}")

        # Send Annotation to Grafana
        send_grafana_annotation(incident_doc)

def ingest_log_line(service_name: str, timestamp_str: str, severity: str, body: str, bg_tasks: BackgroundTasks):
    """
    Appends line to service sliding window buffer and triggers evaluation when step is reached.
    """
    global total_logs_ingested
    with state_lock:
        total_logs_ingested += 1
        
        if service_name not in service_buffers:
            service_buffers[service_name] = deque(maxlen=WINDOW_SIZE)
            service_line_counters[service_name] = 0
            service_window_counters[service_name] = 0

        service_line_counters[service_name] += 1
        current_line_no = service_line_counters[service_name]

        formatted_line = f"{timestamp_str} {severity.upper()} [{service_name}] - {body}"
        service_buffers[service_name].append(formatted_line)
        raw_logs_deque.appendleft({
            "timestamp": timestamp_str,
            "service": service_name,
            "severity": severity.upper(),
            "message": body
        })

        buf = service_buffers[service_name]
        is_error_line = severity.upper() in ("ERROR", "FATAL") or bool(re.search(r'(Exception|Error:|\bfail\b|\bfailed\b)', body, re.I))

        should_trigger = False
        if len(buf) == WINDOW_SIZE and (current_line_no - WINDOW_SIZE) % WINDOW_STEP == 0:
            should_trigger = True
        elif is_error_line and len(buf) >= 3 and (current_line_no - service_line_counters.get(f"{service_name}_last_err", -999)) >= 5:
            service_line_counters[f"{service_name}_last_err"] = current_line_no
            should_trigger = True

        if should_trigger:
            service_window_counters[service_name] += 1
            w_count = service_window_counters[service_name]
            window_id = f"win_{service_name}_{w_count}"
            window_lines = list(buf)
            start_line = max(1, current_line_no - len(window_lines) + 1)
            end_line = current_line_no

            bg_tasks.add_task(evaluate_window, service_name, window_lines, window_id, start_line, end_line)


@app.get("/api/health")
def health():
    return {
        "status": "UP",
        "total_logs_ingested": total_logs_ingested,
        "total_incidents_detected": total_incidents_detected,
        "active_services": list(service_buffers.keys()),
        "grafana_target": GRAFANA_URL
    }

@app.get("/api/incidents")
def get_incidents(
    limit: int = Query(default=20, ge=1, le=200),
    service: Optional[str] = None
):
    """
    Endpoint for Grafana Infinity plugin or custom dashboard tables.
    Returns detected AI Root Cause incidents formatted as JSON.
    """
    col = get_mongo_collection()
    query = {}
    if service:
        query["service"] = service

    if col is not None:
        try:
            cursor = col.find(query, {"_id": 0}).sort("time_epoch_ms", -1).limit(limit)
            incidents = list(cursor)
            return incidents
        except Exception as e:
            return {"error": str(e), "data": []}
    return []

@app.get("/api/logs")
def get_raw_logs(
    limit: int = Query(default=100, ge=1, le=400),
    service: Optional[str] = None
):
    """
    Returns recent raw streaming logs for the System Logs Grafana dashboard.
    """
    with state_lock:
        logs = list(raw_logs_deque)
    if service:
        logs = [l for l in logs if l.get("service") == service]
    return logs[:limit]

@app.get("/api/stats")
def get_stats():
    """
    Summary stats for Grafana Stat panels.
    """
    with state_lock:
        return [
            {"stat": "Total Logs Ingested", "value": total_logs_ingested},
            {"stat": "AI Incidents Detected", "value": total_incidents_detected},
            {"stat": "Monitored Microservices", "value": len(service_buffers) or 1}
        ]

@app.post("/api/reset")
def reset_incidents():
    """
    Clears MongoDB incidents and in-memory incident counters for clean demo validations.
    """
    global total_incidents_detected
    col = get_mongo_collection()
    if col is not None:
        try:
            col.delete_many({})
        except Exception as e:
            print(f"[Mongo Error] {e}")
    with state_lock:
        total_incidents_detected = 0
    return {"status": "ok", "message": "Demo data reset successfully"}

@app.post("/v1/logs")
async def receive_otlp_logs(request: Request, bg_tasks: BackgroundTasks):
    """
    Standard OpenTelemetry OTLP/HTTP Logs receiver endpoint.
    Parses OTLP JSON payload forwarded by OpenTelemetry Collector.
    """
    try:
        body_bytes = await request.body()
        content_encoding = request.headers.get("content-encoding", "").lower()
        if content_encoding == "gzip" or (len(body_bytes) >= 2 and body_bytes[:2] == b'\x1f\x8b'):
            import gzip
            body_bytes = gzip.decompress(body_bytes)

        import json
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        # Fallback for plain text or unexpected error
        text = body_bytes.decode("utf-8", errors="ignore")
        print(f"[OTLP Parse Error] content-type={request.headers.get('content-type')} err={e} len={len(body_bytes)}")
        ingest_log_line("unknown-service", datetime.utcnow().isoformat(), "INFO", text[:200], bg_tasks)
        return {"status": "accepted", "records": 1}

    record_count = 0
    resource_logs = payload.get("resourceLogs", [])

    for r_log in resource_logs:
        resource = r_log.get("resource", {})
        attributes = resource.get("attributes", [])
        
        service_name = "unknown-service"
        for attr in attributes:
            if attr.get("key") == "service.name":
                val = attr.get("value", {})
                service_name = val.get("stringValue", service_name)
                break

        scope_logs = r_log.get("scopeLogs", [])
        for s_log in scope_logs:
            log_records = s_log.get("logRecords", [])
            for rec in log_records:
                record_count += 1
                severity = rec.get("severityText", "INFO") or "INFO"
                
                # Extract timestamp
                time_nano = rec.get("timeUnixNano")
                if time_nano:
                    try:
                        ts_sec = int(time_nano) / 1e9
                        ts_str = datetime.utcfromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    ts_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

                # Extract message body
                body_val = rec.get("body", {})
                if isinstance(body_val, dict):
                    msg = body_val.get("stringValue", str(body_val))
                else:
                    msg = str(body_val)

                ingest_log_line(service_name, ts_str, severity, msg, bg_tasks)

    return {"status": "accepted", "processed_records": record_count}

@app.post("/api/simulate-incident")
def simulate_incident(
    service: str = "ad",
    type: Optional[str] = None,
    bg_tasks: BackgroundTasks = None
):
    """
    Simulates rotating production outages across diverse categories:
    - database_timeout (HikariCP connection pool timeout)
    - null_pointer (Java NullPointerException in business logic)
    - out_of_memory (JVM Heap Space exhaustion)
    - grpc_unavailable (gRPC network outage)
    - deadlock_timeout (Database deadlock & lock contention)
    - validation_rule (Business validation rule rejection)
    
    If 'type' is omitted, rotates to the next fault automatically on every call!
    """
    global simulation_index

    scenarios = [
        {
            "id": "database_timeout",
            "name": "اختلال استخر اتصالات دیتابیس (HikariCP / JPA Timeout)",
            "exception": "SQLTransientConnectionException",
            "service": service or "ad",
            "lines": [
                f"2026-10-30 21:00:13 ERROR [{service}] - Failed to obtain JDBC Connection: HikariPool-1 - Connection is not available, request timed out after 30000ms.",
                f"2026-10-30 21:00:14 ERROR [{service}] - org.springframework.dao.DataAccessResourceFailureException: Unable to acquire JDBC Connection",
                f"2026-10-30 21:00:15 ERROR [{service}] - \tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:213)",
                f"2026-10-30 21:00:16 ERROR [{service}] - \tat org.hibernate.engine.jdbc.connections.internal.DatasourceConnectionProviderImpl.getConnection(DatasourceConnectionProviderImpl.java:122)",
                f"2026-10-30 21:00:17 ERROR [{service}] - Caused by: java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms.",
                f"2026-10-30 21:00:18 ERROR [{service}] - \tat com.zaxxer.hikari.util.ConcurrentBag.borrow(ConcurrentBag.java:149)",
                f"2026-10-30 21:00:19 ERROR [{service}] - org.springframework.transaction.CannotCreateTransactionException: Could not open JPA EntityManager for transaction",
                f"2026-10-30 21:00:20 WARN  [{service}] - Fallback cache route attempted, but circuit breaker is OPEN.",
                f"2026-10-30 21:00:21 ERROR [{service}] - HTTP 500 Internal Server Error returned to downstream gateway.",
                f"2026-10-30 21:00:22 ERROR [{service}] - Transaction rollback completed for order_id=98271."
            ]
        },
        {
            "id": "null_pointer",
            "name": "باگ نرم‌افزاری و دسترسی نامعتبر (NullPointerException)",
            "exception": "NullPointerException",
            "service": service or "ad",
            "lines": [
                f"2026-10-30 21:00:13 ERROR [{service}] - Unexpected error occurred in AdCatalogService: Null pointer encountered",
                f"2026-10-30 21:00:14 ERROR [{service}] - java.lang.NullPointerException: Cannot invoke \"com.opentelemetry.demo.AdItem.getCategory()\" because \"targetAd\" is null",
                f"2026-10-30 21:00:15 ERROR [{service}] - \tat com.opentelemetry.demo.AdService.getAdsByCategory(AdService.java:84)",
                f"2026-10-30 21:00:16 ERROR [{service}] - \tat com.opentelemetry.demo.AdService.processTargetedAds(AdService.java:128)",
                f"2026-10-30 21:00:17 ERROR [{service}] - \tat com.opentelemetry.demo.AdServiceGrpc$MethodHandlers.invoke(AdServiceGrpc.java:214)",
                f"2026-10-30 21:00:18 ERROR [{service}] - \tat io.grpc.stub.ServerCalls$UnaryServerCallHandler$UnaryServerCallListener.onHalfClose(ServerCalls.java:182)",
                f"2026-10-30 21:00:19 ERROR [{service}] - HTTP 500 Internal Server Error: unhandled NullPointerException during dispatch",
                f"2026-10-30 21:00:20 WARN  [{service}] - Client session 4091 aborted abnormally due to unhandled NullPointerException"
            ]
        },
        {
            "id": "out_of_memory",
            "name": "سرریز حافظه و اتمام فضای هیپ (OutOfMemoryError: Java heap space)",
            "exception": "OutOfMemoryError",
            "service": service or "ad",
            "lines": [
                f"2026-10-30 21:00:13 WARN  [{service}] - JVM Garbage Collection took 4280ms (> 98% GC overhead limit exceeded)",
                f"2026-10-30 21:00:14 ERROR [{service}] - java.lang.OutOfMemoryError: Java heap space",
                f"2026-10-30 21:00:15 ERROR [{service}] - \tat java.base/java.util.Arrays.copyOf(Arrays.java:3537)",
                f"2026-10-30 21:00:16 ERROR [{service}] - \tat java.base/java.io.ByteArrayOutputStream.grow(ByteArrayOutputStream.java:115)",
                f"2026-10-30 21:00:17 ERROR [{service}] - \tat com.opentelemetry.demo.CacheManager.cacheProductVectors(CacheManager.java:214)",
                f"2026-10-30 21:00:18 ERROR [{service}] - \tat com.opentelemetry.demo.AdService.buildAdResponse(AdService.java:190)",
                f"2026-10-30 21:00:19 ERROR [{service}] - Fatal memory allocation failure: JVM heap 256MB exhausted",
                f"2026-10-30 21:00:20 ERROR [{service}] - Application cannot satisfy memory request, worker thread killed"
            ]
        },
        {
            "id": "grpc_unavailable",
            "name": "قطعی شبکه و عدم دسترسی به مایکروسرویس (StatusRuntimeException UNAVAILABLE)",
            "exception": "StatusRuntimeException",
            "service": service or "ad",
            "lines": [
                f"2026-10-30 21:00:13 ERROR [{service}] - gRPC Channel to payment-service failed connection handshake",
                f"2026-10-30 21:00:14 ERROR [{service}] - io.grpc.StatusRuntimeException: UNAVAILABLE: io exception: Connection refused - downstream service is dead",
                f"2026-10-30 21:00:15 ERROR [{service}] - \tat io.grpc.stub.ClientCalls.toStatusRuntimeException(ClientCalls.java:271)",
                f"2026-10-30 21:00:16 ERROR [{service}] - \tat io.grpc.stub.ClientCalls.getUnchecked(ClientCalls.java:252)",
                f"2026-10-30 21:00:17 ERROR [{service}] - \tat io.grpc.stub.ClientCalls.blockingUnaryCall(ClientCalls.java:165)",
                f"2026-10-30 21:00:18 ERROR [{service}] - \tat com.opentelemetry.demo.PaymentClient.charge(PaymentClient.java:54)",
                f"2026-10-30 21:00:19 WARN  [{service}] - Retried 3 times with exponential backoff: payment-service unreachable",
                f"2026-10-30 21:00:20 ERROR [{service}] - Circuit Breaker state transitioned to OPEN: 100% downstream failures"
            ]
        },
        {
            "id": "deadlock_timeout",
            "name": "بن‌بست تراکنش‌های همزمان دیتابیس (CannotAcquireLockException)",
            "exception": "CannotAcquireLockException",
            "service": service or "ad",
            "lines": [
                f"2026-10-30 21:00:13 ERROR [{service}] - Deadlock detected when trying to get lock; try restarting transaction",
                f"2026-10-30 21:00:14 ERROR [{service}] - org.springframework.dao.CannotAcquireLockException: could not execute statement [Lock wait timeout exceeded]; SQL [UPDATE inventory SET stock = stock - 1 WHERE id = 42 FOR UPDATE]",
                f"2026-10-30 21:00:15 ERROR [{service}] - \tat org.hibernate.exception.internal.SQLExceptionTypeDelegate.convert(SQLExceptionTypeDelegate.java:66)",
                f"2026-10-30 21:00:16 ERROR [{service}] - \tat org.hibernate.engine.jdbc.spi.SqlExceptionHelper.convert(SqlExceptionHelper.java:108)",
                f"2026-10-30 21:00:17 ERROR [{service}] - Caused by: java.sql.SQLException: Deadlock found when trying to get lock; try restarting transaction",
                f"2026-10-30 21:00:18 ERROR [{service}] - \tat com.mysql.cj.jdbc.exceptions.SQLError.createSQLException(SQLError.java:129)",
                f"2026-10-30 21:00:19 ERROR [{service}] - Transaction rollback initiated for concurrent update thread pool-worker-18",
                f"2026-10-30 21:00:20 WARN  [{service}] - High database contention detected on row lock id=42"
            ]
        },
        {
            "id": "validation_rule",
            "name": "رد درخواست بر اساس قوانین تجاری و اعتبارسنجی (MethodArgumentNotValidException)",
            "exception": "MethodArgumentNotValidException",
            "service": service or "ad",
            "lines": [
                f"2026-10-30 21:00:13 ERROR [{service}] - Insurance policy rule engine rejected claim due to invalid coverage conditions",
                f"2026-10-30 21:00:14 ERROR [{service}] - org.springframework.web.bind.MethodArgumentNotValidException: Validation failed for claim [PolicyClaimPayload: deductible=0, max_coverage=1000000000]",
                f"2026-10-30 21:00:15 ERROR [{service}] - \tat org.springframework.web.method.annotation.ModelAttributeMethodProcessor.resolveArgument(ModelAttributeMethodProcessor.java:165)",
                f"2026-10-30 21:00:16 ERROR [{service}] - Caused by: javax.validation.ConstraintViolationException: Policy maximum coverage exceeds insured threshold limit",
                f"2026-10-30 21:00:17 ERROR [{service}] - \tat com.insurance.engine.rules.PolicyRuleValidator.validate(PolicyRuleValidator.java:73)",
                f"2026-10-30 21:00:18 ERROR [{service}] - HTTP 422 Unprocessable Entity returned to client: business rule violation",
                f"2026-10-30 21:00:19 WARN  [{service}] - Fraud detection flag triggered for claim ref=7013"
            ]
        }
    ]

    selected = None
    if type:
        for s in scenarios:
            if s["id"] == type or type in s["id"] or type.lower() in s["exception"].lower():
                selected = s
                break

    if selected is None:
        with state_lock:
            simulation_index += 1
            idx = (simulation_index - 1) % len(scenarios)
            selected = scenarios[idx]

    target_svc = selected["service"]
    prefix_lines = [
        f"2026-10-30 21:00:0{i:02d} INFO [{target_svc}] - Routine background processing item={100+i}"
        for i in range(14)
    ]
    simulated_window = prefix_lines + selected["lines"]

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for line in simulated_window:
        sev = "ERROR" if "ERROR" in line else ("WARN" if "WARN" in line else "INFO")
        msg = line.split(" - ", 1)[-1] if " - " in line else line
        with state_lock:
            raw_logs_deque.appendleft({
                "timestamp": now_str,
                "service": target_svc,
                "severity": sev,
                "message": msg
            })

    evaluate_window(target_svc, simulated_window, f"sim_{selected['id']}_{int(time.time())}", 1, len(simulated_window))

    return {
        "status": "simulated",
        "scenario_id": selected["id"],
        "name_fa": selected["name"],
        "exception": selected["exception"],
        "service": target_svc,
        "next_scenario_on_next_run": scenarios[simulation_index % len(scenarios)]["id"]
    }
