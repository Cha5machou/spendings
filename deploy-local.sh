#!/usr/bin/env bash
# Build the frontend and run the whole app as one local process on http://localhost:8000
#   ./deploy-local.sh          build + (re)start
#   ./deploy-local.sh stop     stop the running server
#   ./deploy-local.sh logs     follow the server log
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
PID_FILE="$PWD/backend/data/server.pid"
LOG_FILE="$PWD/backend/data/server.log"

stop_server() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")"
    echo "Stopped server (pid $(cat "$PID_FILE"))"
  fi
  rm -f "$PID_FILE"
}

case "${1:-start}" in
  stop) stop_server; exit 0 ;;
  logs) exec tail -f "$LOG_FILE" ;;
  start) ;;
  *) echo "usage: $0 [start|stop|logs]"; exit 1 ;;
esac

echo "Building frontend..."
(cd frontend && npm install --silent && npm run build --silent)

echo "Installing backend dependencies..."
(cd backend && uv sync --quiet)

stop_server
mkdir -p backend/data
cd backend
nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"
cd ..

for _ in $(seq 1 30); do
  if curl -sf "http://localhost:$PORT/api/health" > /dev/null; then
    echo "Spendings is running: http://localhost:$PORT  (API docs: http://localhost:$PORT/docs)"
    echo "Logs: $LOG_FILE   Stop: ./deploy-local.sh stop"
    exit 0
  fi
  sleep 1
done
echo "Server did not come up; last log lines:"; tail -20 "$LOG_FILE"; exit 1
