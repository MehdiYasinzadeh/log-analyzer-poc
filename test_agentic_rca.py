import os
import sys
import re
import json
import time
import requests
import subprocess
from typing import List, Dict, Any, Optional

# --- Configuration ---
DEFAULT_LOG_FILE = os.path.expanduser("~/IdeaProjects/bgl-log-analyzer-poc/data/logs-from-api-transmitter-service-in-api-transmitter-service.log")
PRIMARY_OLLAMA_URL = "http://192.168.50.253:11434"
FALLBACK_OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5-coder:7b"
SERVER_SSH = "root@192.168.50.253"

# --- GPU Fan & Thermal Management ---
def check_and_adjust_gpu_fan(ssh_target: str, target_pwm: int = 120):
    """
    Checks GPU temperature on the server. If active cooling is needed or requested,
    sets PWM fan speed (120 ~= 45% RPM) to keep the RX 5600 XT cool during LLM inference.
    """
    try:
        # Check current temperature
        cmd = "cat /sys/class/drm/card1/device/hwmon/hwmon3/temp1_input 2>/dev/null || echo 0"
        res = subprocess.run(["ssh", "-o", "ConnectTimeout=2", ssh_target, cmd],
                             capture_output=True, text=True, timeout=4)
        if res.returncode == 0 and res.stdout.strip().isdigit():
            temp_c = int(res.stdout.strip()) / 1000.0
            print(f"🌡️  [GPU Thermal Guard] Current RX 5600 XT Edge Temp: {temp_c:.1f}°C")
            
            # Enable manual fan control and set cooling speed
            fan_cmd = f"echo 1 > /sys/class/drm/card1/device/hwmon/hwmon3/pwm1_enable && echo {target_pwm} > /sys/class/drm/card1/device/hwmon/hwmon3/pwm1"
            subprocess.run(["ssh", "-o", "ConnectTimeout=2", ssh_target, fan_cmd],
                           capture_output=True, timeout=4)
            print(f"❄️  [GPU Thermal Guard] Active cooling engaged: Fans set to ~45% (PWM {target_pwm})")
    except Exception as e:
        print(f"⚠️  [GPU Thermal Guard] Notice: {e}")

def restore_gpu_fan_auto(ssh_target: str):
    """Restores GPU fans to automatic firmware curve when finished."""
    try:
        cmd = "echo 2 > /sys/class/drm/card1/device/hwmon/hwmon3/pwm1_enable"
        subprocess.run(["ssh", "-o", "ConnectTimeout=2", ssh_target, cmd],
                       capture_output=True, timeout=4)
        print("🔄 [GPU Thermal Guard] Restored GPU fans to Automatic Control.")
    except Exception:
        pass

# --- Ollama Connection Check ---
def get_working_ollama_url() -> str:
    for url in [PRIMARY_OLLAMA_URL, FALLBACK_OLLAMA_URL]:
        try:
            r = requests.get(f"{url}/api/tags", timeout=2)
            if r.status_code == 200:
                print(f"✅ Connected to Ollama at: {url} (Model: {MODEL_NAME})")
                return url
        except Exception:
            continue
    raise ConnectionError("Could not reach Ollama on Local Server or MacBook!")

# --- Fast Tier-1 Stream Parser & Deduplicator ---
HEADER_REGEX = re.compile(
    r"^(?:\[?(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:[+-]\d{2}:\d{2})?)\]?)\s+"
    r"(?P<level>INFO|ERROR|WARN|DEBUG|FATAL|TRACE)\s+"
    r"(?:(?:\d+\s+---\s+(?:\[[^\]]*\]\s+)?)?\[(?P<thread>[^\]]+)\](?::\s*|\s+)|\s+)?"
    r"(?:(?P<source>[a-zA-Z0-9_.$]+)(?:\s*\([^)]*\))?\s*(?::\s*|\s+))?"
    r"(?P<message>.*)$"
)

def extract_signature(lines: List[str]) -> str:
    """Extracts a unique incident signature (Root Exception + Key Throwing Location)."""
    full_text = "\n".join(lines)
    # Detect Java Exception headers
    exc_candidates = re.findall(r"^(?:Caused by:\s*)?([a-zA-Z0-9_.$]+(?:Exception|Error))(?::\s*(.*))?$", full_text, re.MULTILINE)
    if exc_candidates:
        root_exc = exc_candidates[-1][0].split(".")[-1]
    else:
        exc_simple = re.findall(r"([a-zA-Z0-9_.]+(?:Exception|Error))", full_text)
        root_exc = exc_simple[-1].split(".")[-1] if exc_simple else "UnknownError"

    # Find the most relevant application/business frame (filtering out reflection / proxy noise)
    frames = re.findall(r"at\s+([a-zA-Z0-9_.$]+)\.([a-zA-Z0-9_]+)\(", full_text)
    app_frame = "unknown"
    for cls, method in frames:
        cls_short = cls.split(".")[-1]
        if not any(skip in cls for skip in ["reflect", "Cglib", "Proxy", "cglib", "FilterChain", "HandlerMethod", "DispatcherServlet"]):
            app_frame = f"{cls_short}.{method}"
            break
            
    return f"{root_exc}@{app_frame}"

class LogStreamBuffer:
    def __init__(self, file_path: str):
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            self.all_lines = [l.rstrip("\r\n") for l in f]

    def get_context_around(self, start_line: int, end_line: int, before_count: int = 5, after_count: int = 5) -> Dict[str, List[str]]:
        b_start = max(0, start_line - before_count)
        before_lines = self.all_lines[b_start:start_line]
        
        a_end = min(len(self.all_lines), end_line + after_count)
        after_lines = self.all_lines[end_line:a_end]
        
        return {
            "before": before_lines,
            "after": after_lines
        }

def scan_incidents(file_path: str, max_distinct_incidents: int = 4) -> List[Dict[str, Any]]:
    """
    Tier-1 Fast Filter: Scans the log file, filters normal logs,
    groups multiline stack traces into events, and debounces duplicate errors.
    """
    buffer = LogStreamBuffer(file_path)
    incidents = []
    seen_signatures = {}

    current_event = None
    event_start_line = 0

    print(f"📂 Scanning {len(buffer.all_lines)} lines from {os.path.basename(file_path)}...")

    for line_idx, line in enumerate(buffer.all_lines):
        m = HEADER_REGEX.match(line)
        if m:
            # End previous event
            if current_event:
                if current_event["level"] in ("ERROR", "FATAL"):
                    sig = extract_signature(current_event["lines"])
                    if sig not in seen_signatures:
                        ctx = buffer.get_context_around(event_start_line, line_idx, before_count=6, after_count=6)
                        current_event["signature"] = sig
                        current_event["start_line"] = event_start_line + 1
                        current_event["end_line"] = line_idx
                        current_event["context_before"] = ctx["before"]
                        current_event["context_after"] = ctx["after"]
                        current_event["count"] = 1
                        seen_signatures[sig] = current_event
                        incidents.append(current_event)
                    else:
                        seen_signatures[sig]["count"] += 1

            # Start new event
            event_start_line = line_idx
            current_event = {
                "timestamp": m.group("ts"),
                "level": m.group("level"),
                "thread": m.group("thread"),
                "source": m.group("source"),
                "header_message": m.group("message"),
                "lines": [line]
            }
        else:
            if current_event:
                current_event["lines"].append(line)

    # Flush last event
    if current_event and current_event["level"] in ("ERROR", "FATAL"):
        sig = extract_signature(current_event["lines"])
        if sig not in seen_signatures:
            ctx = buffer.get_context_around(event_start_line, len(buffer.all_lines), before_count=6, after_count=6)
            current_event["signature"] = sig
            current_event["start_line"] = event_start_line + 1
            current_event["end_line"] = len(buffer.all_lines)
            current_event["context_before"] = ctx["before"]
            current_event["context_after"] = ctx["after"]
            current_event["count"] = 1
            incidents.append(current_event)
        else:
            seen_signatures[sig]["count"] += 1

    # Sort by frequency (highest occurrences first)
    incidents.sort(key=lambda x: x["count"], reverse=True)
    return incidents[:max_distinct_incidents]

# --- Agentic Multi-Turn Diagnostic Loop ---
SYSTEM_PROMPT = """You are an elite Senior Site Reliability Engineer (SRE) and Java/Spring enterprise diagnostics expert.
Your job is to analyze real-world system errors and stack traces.
Reply strictly in valid JSON format. Be concise, direct, and avoid repeating phrases.

DECISION PROTOCOL:
1. If the provided error log and initial context are sufficient to diagnose the Root Cause, return:
{
  "status": "DIAGNOSED",
  "root_cause_summary": "خلاصه علت ریشه‌ای به فارسی (حداکثر ۱ جمله)",
  "detailed_analysis": "تحلیل چرایی وقوع خطا به فارسی (حداکثر ۲ الی ۳ جمله)",
  "actionable_remediation": [
    "گام اجرایی اول به فارسی",
    "گام اجرایی دوم به فارسی"
  ],
  "severity": "CRITICAL"
}

2. If you genuinely lack critical context (e.g. need prior database pool warnings or thread logs before the crash), return:
{
  "status": "NEED_MORE_LOGS",
  "direction": "before",
  "lines_count": 10,
  "reason": "توضیح کوتاه اینکه دنبال چه مدرکی در لاگ‌های اطراف هستید"
}"""

def query_ollama_chat(ollama_url: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    url = f"{ollama_url}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
            "top_p": 0.2,
            "repeat_penalty": 1.2,
            "num_predict": 600
        }
    }
    t0 = time.time()
    resp = requests.post(url, json=payload, timeout=120)
    latency = time.time() - t0
    resp.raise_for_status()
    data = resp.json()
    content = data.get("message", {}).get("content", "{}")
    eval_count = data.get("eval_count", 0)
    eval_duration_sec = data.get("eval_duration", 1) / 1e9
    tps = eval_count / eval_duration_sec if eval_duration_sec > 0 else 0
    
    try:
        parsed = json.loads(content)
    except Exception:
        # Fallback if json is embedded in markdown
        m = re.search(r'\{.*\}', content, re.DOTALL)
        parsed = json.loads(m.group(0)) if m else {"raw": content}

    return {
        "parsed": parsed,
        "latency": latency,
        "tps": tps,
        "raw": content
    }

def diagnose_incident_agentic(ollama_url: str, incident: Dict[str, Any], buffer: LogStreamBuffer) -> Dict[str, Any]:
    """
    Executes the multi-turn agentic diagnosis loop.
    If the LLM asks for NEED_MORE_LOGS, dynamically injects surrounding logs and requests final verdict.
    """
    # Build initial message
    before_str = "\n".join(incident["context_before"][-5:]) if incident["context_before"] else "(No prior logs)"
    error_str = "\n".join(incident["lines"][:25]) # send top 25 lines of stack trace
    
    user_turn_1 = f"""[INCIDENT REPORT]
Timestamp: {incident['timestamp']}
Thread: {incident['thread']}
Occurrences in Batch: {incident['count']} times
Start Line: {incident['start_line']}

--- PRECEDING CONTEXT (Prior 5 Lines) ---
{before_str}

--- ERROR & STACK TRACE ---
{error_str}

Evaluate if this context is sufficient. If yes, DIAGNOSE it. If critical details are missing, request NEED_MORE_LOGS."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_turn_1}
    ]

    print(f"\n🧠 [Turn 1] Submitting Incident '{incident['signature']}' to {MODEL_NAME}...")
    res1 = query_ollama_chat(ollama_url, messages)
    parsed1 = res1["parsed"]
    print(f"⏱️  [Turn 1 Latency]: {res1['latency']:.2f}s ({res1['tps']:.1f} tok/s)")

    if parsed1.get("status") == "NEED_MORE_LOGS":
        direction = parsed1.get("direction", "before")
        count = int(parsed1.get("lines_count", 10))
        reason = parsed1.get("reason", "Needs more background")
        print(f"🔍 [Agent Decision] Model requested MORE logs! Direction: '{direction}', Count: {count}")
        print(f"   Reason: {reason}")
        
        # Extract requested extra logs
        extra_lines = []
        if direction in ("before", "both"):
            start = max(0, incident["start_line"] - 1 - count - 5)
            end = max(0, incident["start_line"] - 1)
            extra_lines.extend(["--- ADDITIONAL PRECEDING LOGS ---"] + buffer.all_lines[start:end])
        if direction in ("after", "both"):
            start = incident["end_line"]
            end = min(len(buffer.all_lines), incident["end_line"] + count)
            extra_lines.extend(["--- ADDITIONAL SUBSEQUENT LOGS ---"] + buffer.all_lines[start:end])

        turn_2_prompt = f"""Here are the additional requested surrounding log lines from the buffer:

{chr(10).join(extra_lines)}

Now synthesize the complete picture and provide your final DIAGNOSED JSON report."""

        messages.append({"role": "assistant", "content": res1["raw"]})
        messages.append({"role": "user", "content": turn_2_prompt})

        print(f"🧠 [Turn 2] Resubmitting with {len(extra_lines)} extra lines of requested context...")
        res2 = query_ollama_chat(ollama_url, messages)
        print(f"⏱️  [Turn 2 Latency]: {res2['latency']:.2f}s ({res2['tps']:.1f} tok/s)")
        return {
            "turns": 2,
            "final_diagnosis": res2["parsed"],
            "total_latency": res1["latency"] + res2["latency"],
            "requested_extra_context": reason
        }
    else:
        return {
            "turns": 1,
            "final_diagnosis": parsed1,
            "total_latency": res1["latency"],
            "requested_extra_context": None
        }

# --- Main Test Runner ---
def main():
    log_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG_FILE
    log_name = os.path.basename(log_file)
    print("=" * 75)
    print(f"🚀 Real-World AIOps Agentic Test Runner ({log_name})")
    print("=" * 75)

    # 1. Hardware Thermal Guard
    check_and_adjust_gpu_fan(SERVER_SSH, target_pwm=120)

    try:
        # 2. Connection Check
        ollama_url = get_working_ollama_url()
        buffer = LogStreamBuffer(log_file)

        # 3. Fast Tier-1 Filter & Deduplication
        incidents = scan_incidents(log_file, max_distinct_incidents=5)
        print(f"\n📊 Tier-1 Gatekeeper Identified {len(incidents)} DISTINCT incident signatures:")
        for idx, inc in enumerate(incidents, start=1):
            print(f"   [{idx}] Signature: {inc['signature']:<35} | Occurrences: {inc['count']:>3} times | Start Line: {inc['start_line']}")

        # 4. Agentic Diagnosis Loop for Each Distinct Incident
        print("\n" + "=" * 75)
        print("🧠 Launching Multi-Turn Agentic RCA with Dynamic Context Fetching...")
        print("=" * 75)

        for idx, inc in enumerate(incidents, start=1):
            print(f"\n🔹 ------------------ Analyzing Incident [{idx}/{len(incidents)}] ------------------")
            print(f"📌 Signature: {inc['signature']} (Repeated {inc['count']} times in file)")
            print(f"🧵 Thread: {inc['thread']} | Timestamp: {inc['timestamp']}")

            result = diagnose_incident_agentic(ollama_url, inc, buffer)
            diag = result["final_diagnosis"]

            print("\n📋 [DIAGNOSTIC REPORT]")
            print(f"• Severity: {diag.get('severity', 'UNKNOWN')}")
            print(f"• Turns: {result['turns']} (Extra Context Requested: {result['requested_extra_context'] or 'None'})")
            print(f"• Total Latency: {result['total_latency']:.2f}s")
            print(f"\n🔍 [Root Cause Summary]:\n{diag.get('root_cause_summary', 'N/A')}")
            remed = diag.get('actionable_remediation', 'N/A')
            if isinstance(remed, list):
                remed_str = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(remed))
            else:
                remed_str = str(remed)
            print(f"\n🛠️  [Actionable Remediation]:\n{remed_str}")
            print("-" * 75)

            # Polite pacing delay to allow GPU thermal recovery
            time.sleep(1)

        print("\n✅ All distinct incidents analyzed successfully without overloading the system!")

    finally:
        # 5. Restore GPU Fans to Auto
        restore_gpu_fan_auto(SERVER_SSH)

if __name__ == "__main__":
    main()
