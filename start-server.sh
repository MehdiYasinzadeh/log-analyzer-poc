#!/usr/bin/env bash
set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_IP="192.168.50.253"
SERVER_USER="mehdi-server"

echo "=================================================="
echo "🚀 Starting Balanced AIOps Stack on LOCAL SERVER ($SERVER_IP)..."
echo "=================================================="

# 1. Check Connectivity to Local Server
echo "📡 Testing connection to Local Server ($SERVER_IP)..."
if ! nc -zv -G 2 "$SERVER_IP" 22 >/dev/null 2>&1; then
    echo "❌ Error: Cannot connect to $SERVER_IP:22."
    echo "   Please make sure the Local Server is on and you are connected to the same network (or VPN allows LAN traffic)."
    exit 1
fi
echo "   ✅ Local Server is reachable!"

# 2. Start Containers on Local Server via SSH
echo "🐳 Starting Docker containers on Local Server..."
ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "
    cd /home/$SERVER_USER/projects/opentelemetry-demo && docker compose -f compose.balanced.yaml up -d
    cd /home/$SERVER_USER/projects/bgl-log-analyzer-poc && docker compose up -d
"

# 3. Ensure Ollama & Prometheus Services are Running
echo "🧠 Checking Ollama & Prometheus on Local Server..."
ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "
    systemctl is-active ollama >/dev/null || systemctl start ollama
    systemctl is-active prometheus >/dev/null || systemctl start prometheus
    systemctl is-active prometheus-node-exporter >/dev/null || systemctl start prometheus-node-exporter
"

# 4. Start Python AIOps Log Analyzer on Mac (Targeting Local Server)
echo "🧠 Starting Python AIOps Log Analyzer (port 5001)..."
pkill -f "uvicorn src.otel_receiver:app" 2>/dev/null || true
export MONGO_URI="mongodb://$SERVER_IP:27017"
export GRAFANA_URL="http://$SERVER_IP:8080"
export OLLAMA_HOST="http://$SERVER_IP:11434"
nohup "$BASE_DIR/.venv/bin/uvicorn" src.otel_receiver:app --host 0.0.0.0 --port 5001 > "$BASE_DIR/receiver.log" 2>&1 &
echo $! > "$BASE_DIR/.receiver.pid"

# 5. Start Paced Background Traffic Generator directed to Server's Ad service
echo "⚡ Starting paced background traffic generator..."
pkill -f "python paced_traffic.py" 2>/dev/null || true
export AD_SERVICE_URL="http://$SERVER_IP:9555"
nohup "$BASE_DIR/.venv/bin/python" "$BASE_DIR/paced_traffic.py" > "$BASE_DIR/traffic.log" 2>&1 &
echo $! > "$BASE_DIR/.traffic.pid"

# 6. Wait for Grafana on Server
echo "⏳ Waiting for Grafana ($SERVER_IP:8080) to be ready..."
for i in {1..20}; do
    if curl -s -I "http://$SERVER_IP:8080/api/health" 2>&1 | grep -q "200 OK"; then
        echo "✅ Grafana is healthy and ready!"
        break
    fi
    sleep 1
done

echo ""
echo "=================================================="
echo "🎉 AIOps Observability Stack is RUNNING on LOCAL SERVER!"
echo "=================================================="
echo "📊 داشبورد لاگ‌های خام سیستم (Raw Logs):"
echo "   http://$SERVER_IP:8080/d/system-live-logs/system-live-telemetry-logs"
echo ""
echo "🧠 داشبورد تحلیل هوش مصنوعی و علت ریشه‌ای خطا (AI RCA):"
echo "   http://$SERVER_IP:8080/d/aiops-live-incidents/aiops-live-incidents-and-root-cause-analysis"
echo ""
echo "🌡️ داشبورد مانیتورینگ زنده دما و سخت‌افزار (CPU, GPU, RAM):"
echo "   http://$SERVER_IP:8080/d/hardware-thermal-health/e4eb636"
echo ""
echo "⚡ کامند تزریق خطای رندوم و چرخشی:"
echo "   curl -X POST \"http://localhost:5001/api/simulate-incident\""
echo "   (یا اجرای اسکریپت: $BASE_DIR/simulate-error.sh)"
echo ""
echo "🧹 ریست کردن داشبورد:"
echo "   curl -X POST \"http://localhost:5001/api/reset\""
echo ""
echo "🛑 برای متوقف کردن همه سرویس‌ها:"
echo "   $BASE_DIR/stop-server.sh"
echo "=================================================="
