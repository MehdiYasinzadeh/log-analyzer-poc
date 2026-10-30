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
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")

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
total_logs_ingested = 0
total_incidents_detected = 0
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
        "http://localhost:8080/api/annotations",
        "http://localhost:3000/api/annotations"
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
def simulate_incident(service: str = "ad", bg_tasks: BackgroundTasks = None):
    """
    Testing helper: simulates an outage window for a given service to verify end-to-end RCA & Grafana annotation.
    """
    simulated_lines = [
        f"2026-10-30 21:00:0{i:02d} INFO [{service}] - Processing routine request id={1000+i}" for i in range(15)
    ]
    simulated_lines.extend([
        f"2026-10-30 21:00:16 ERROR [{service}] - Failed to obtain JDBC Connection: HikariPool-1 - Connection is not available, request timed out after 30000ms.",
        f"2026-10-30 21:00:17 ERROR [{service}] - org.springframework.dao.DataAccessResourceFailureException: Unable to acquire JDBC Connection",
        f"2026-10-30 21:00:17 ERROR [{service}] - \tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:213)",
        f"2026-10-30 21:00:18 ERROR [{service}] - \tat org.hibernate.engine.jdbc.connections.internal.DatasourceConnectionProviderImpl.getConnection(DatasourceConnectionProviderImpl.java:122)",
        f"2026-10-30 21:00:19 ERROR [{service}] - Caused by: java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms.",
        f"2026-10-30 21:00:20 ERROR [{service}] - \tat com.zaxxer.hikari.util.ConcurrentBag.borrow(ConcurrentBag.java:149)",
        f"2026-10-30 21:00:21 ERROR [{service}] - org.springframework.transaction.CannotCreateTransactionException: Could not open JPA EntityManager for transaction",
        f"2026-10-30 21:00:22 WARN  [{service}] - Fallback cache route attempted, but circuit breaker is OPEN.",
        f"2026-10-30 21:00:23 ERROR [{service}] - HTTP 500 Internal Server Error returned to downstream gateway.",
        f"2026-10-30 21:00:24 ERROR [{service}] - Transaction rollback completed for order_id=98271."
    ])

    evaluate_window(service, simulated_lines, f"sim_{service}_{int(time.time())}", 1, 25)
    return {"status": "simulated", "service": service, "lines": len(simulated_lines)}
