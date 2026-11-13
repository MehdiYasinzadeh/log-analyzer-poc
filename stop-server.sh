#!/usr/bin/env bash

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_IP="192.168.50.253"
SERVER_USER="mehdi-server"

echo "=================================================="
echo "🛑 Stopping AIOps Stack on LOCAL SERVER ($SERVER_IP)..."
echo "=================================================="

# 1. Stop Python traffic generator on Mac
if [ -f "$BASE_DIR/.traffic.pid" ]; then
    PID=$(cat "$BASE_DIR/.traffic.pid")
    echo "⚡ Stopping paced traffic generator (PID: $PID)..."
    kill "$PID" 2>/dev/null || true
    rm -f "$BASE_DIR/.traffic.pid"
fi
pkill -f "python paced_traffic.py" 2>/dev/null || true

# 2. Stop Python AIOps Receiver on Mac
if [ -f "$BASE_DIR/.receiver.pid" ]; then
    PID=$(cat "$BASE_DIR/.receiver.pid")
    echo "🧠 Stopping AIOps Python Receiver (PID: $PID)..."
    kill "$PID" 2>/dev/null || true
    rm -f "$BASE_DIR/.receiver.pid"
fi
pkill -f "uvicorn src.otel_receiver:app" 2>/dev/null || true

# 3. Stop Docker containers on Local Server via SSH
if nc -zv -G 2 "$SERVER_IP" 22 >/dev/null 2>&1; then
    echo "🐳 Stopping Docker containers on Local Server..."
    ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "
        cd /home/$SERVER_USER/projects/opentelemetry-demo && docker compose -f compose.balanced.yaml down 2>/dev/null || true
        cd /home/$SERVER_USER/projects/bgl-log-analyzer-poc && docker compose down 2>/dev/null || true
    "
else
    echo "⚠️ Warning: Local Server $SERVER_IP is not reachable via SSH. Could not stop remote containers."
fi

echo ""
echo "=================================================="
echo "✅ All services and containers are STOPPED."
echo "❄️ MacBook & Local Server resources are 100% freed."
echo "🚀 To start everything again, run:"
echo "   $BASE_DIR/start-server.sh"
echo "=================================================="
