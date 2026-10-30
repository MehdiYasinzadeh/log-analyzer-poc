#!/usr/bin/env bash
set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="/Users/mehdi/IdeaProjects/opentelemetry-demo"

echo "=================================================="
echo "🚀 Starting Balanced AIOps & OpenTelemetry Stack..."
echo "=================================================="

# 1. Start MongoDB
if docker ps -a --format '{{.Names}}' | grep -q "^bgl_mongo$"; then
    echo "📦 Starting existing bgl_mongo container..."
    docker start bgl_mongo >/dev/null
else
    echo "📦 Creating and starting bgl_mongo container..."
    docker run -d --name bgl_mongo -p 27017:27017 mongo:latest >/dev/null
fi

# 2. Start Balanced OTel Demo (flagd, otel-collector, ad, grafana)
echo "🐳 Starting balanced OpenTelemetry containers on port 8080..."
docker compose -f "$DEMO_DIR/compose.balanced.yaml" up -d

# 3. Start Python AIOps Log Analyzer & RCA Receiver
echo "🧠 Starting Python AIOps Log Analyzer (port 5001)..."
pkill -f "uvicorn src.otel_receiver:app" 2>/dev/null || true
nohup "$BASE_DIR/.venv/bin/uvicorn" src.otel_receiver:app --host 0.0.0.0 --port 5001 > "$BASE_DIR/receiver.log" 2>&1 &
echo $! > "$BASE_DIR/.receiver.pid"

# 4. Start Gentle Paced Traffic Generator (1 req / 2.5s)
echo "⚡ Starting paced background traffic generator..."
pkill -f "python paced_traffic.py" 2>/dev/null || true
nohup "$BASE_DIR/.venv/bin/python" "$BASE_DIR/paced_traffic.py" > "$BASE_DIR/traffic.log" 2>&1 &
echo $! > "$BASE_DIR/.traffic.pid"

echo ""
echo "⏳ Waiting for Grafana (port 8080) to be ready..."
for i in {1..15}; do
    if curl -s -I http://localhost:8080/api/health 2>&1 | grep -q "200 OK"; then
        echo "✅ Grafana is healthy and ready!"
        break
    fi
    sleep 1
done

echo ""
echo "=================================================="
echo "🎉 AIOps Observability Stack is RUNNING!"
echo "=================================================="
echo "📊 Grafana System Raw Logs:"
echo "   http://localhost:8080/d/system-live-logs/system-live-telemetry-logs"
echo ""
echo "🧠 Grafana AIOps Incident & Root Cause Analysis (RCA):"
echo "   http://localhost:8080/d/aiops-live-incidents/aiops-live-incidents-and-root-cause-analysis"
echo ""
echo "⚡ Rotating Multi-Fault Simulation Command:"
echo "   curl -X POST \"http://localhost:5001/api/simulate-incident\""
echo ""
echo "🧹 Reset Demo Dashboard Command:"
echo "   curl -X POST \"http://localhost:5001/api/reset\""
echo ""
echo "🛑 To stop everything at any time:"
echo "   $BASE_DIR/stop.sh"
echo "=================================================="
