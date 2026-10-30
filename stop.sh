#!/usr/bin/env bash

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="/Users/mehdi/IdeaProjects/opentelemetry-demo"

echo "=================================================="
echo "🛑 Stopping Balanced AIOps & OpenTelemetry Stack..."
echo "=================================================="

# 1. Stop Python traffic generator
if [ -f "$BASE_DIR/.traffic.pid" ]; then
    PID=$(cat "$BASE_DIR/.traffic.pid")
    echo "⚡ Stopping paced traffic generator (PID: $PID)..."
    kill "$PID" 2>/dev/null || true
    rm -f "$BASE_DIR/.traffic.pid"
fi
pkill -f "python paced_traffic.py" 2>/dev/null || true

# 2. Stop Python AIOps Receiver
if [ -f "$BASE_DIR/.receiver.pid" ]; then
    PID=$(cat "$BASE_DIR/.receiver.pid")
    echo "🧠 Stopping AIOps Python Receiver (PID: $PID)..."
    kill "$PID" 2>/dev/null || true
    rm -f "$BASE_DIR/.receiver.pid"
fi
pkill -f "uvicorn src.otel_receiver:app" 2>/dev/null || true

# 3. Stop OpenTelemetry demo containers
echo "🐳 Stopping balanced OpenTelemetry containers..."
docker compose -f "$DEMO_DIR/compose.balanced.yaml" down 2>/dev/null || true

# 4. Stop MongoDB container
echo "📦 Stopping MongoDB container..."
docker stop bgl_mongo 2>/dev/null || true

echo ""
echo "=================================================="
echo "✅ All services and containers are STOPPED."
echo "❄️ CPU, memory, and ports are 100% freed."
echo "🚀 To start everything again, run:"
echo "   $BASE_DIR/start.sh"
echo "=================================================="
