#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_EXTRA_PORTS="${FRONTEND_EXTRA_PORTS:-5174 5175}"
BACKEND_RELOAD="${BACKEND_RELOAD:-0}"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"
DEFAULT_AGENT_OPTIONS_FILE_REL="backend/config/agent_options.local.json"
DEEPSEEK_OPTIONS_FILE_REL="backend/config/deepseek_agent_config.json"
AGENT_OPTIONS_TEMPLATE_FILE_REL="backend/config/agent_options.placeholder.json"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"

mkdir -p "$RUN_DIR"

resolve_agent_options_file() {
  if [[ -n "${AGENT_OPTIONS_FILE:-}" ]]; then
    echo "$AGENT_OPTIONS_FILE"
    return 0
  fi
  if [[ -f "$ROOT_DIR/$DEFAULT_AGENT_OPTIONS_FILE_REL" ]]; then
    echo "$DEFAULT_AGENT_OPTIONS_FILE_REL"
    return 0
  fi
  if [[ -f "$ROOT_DIR/$DEEPSEEK_OPTIONS_FILE_REL" ]]; then
    echo "$DEEPSEEK_OPTIONS_FILE_REL"
    return 0
  fi
  echo "$AGENT_OPTIONS_TEMPLATE_FILE_REL"
}

kill_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  elif command -v ss >/dev/null 2>&1; then
    pids="$(ss -lptn "sport = :$port" 2>/dev/null | awk -F 'pid=' 'NR>1{print $2}' | awk -F ',' '{print $1}' | tr '\n' ' ' || true)"
  elif command -v powershell.exe >/dev/null 2>&1; then
    pids="$(powershell.exe -NoProfile -Command "Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess" | tr -d '\r' || true)"
  fi

  if [[ -n "${pids// }" ]]; then
    echo "Stopping processes on port $port: $pids"
    kill $pids 2>/dev/null || true
    sleep 0.5
    kill -9 $pids 2>/dev/null || true
  fi
}

kill_pid_file() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "${pid// }" ]]; then
    kill "$pid" 2>/dev/null || true
    sleep 0.2
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

kill_by_pattern() {
  local pattern="$1"
  if command -v pgrep >/dev/null 2>&1; then
    local pids
    pids="$(pgrep -f "$pattern" 2>/dev/null || true)"
    if [[ -n "${pids// }" ]]; then
      echo "Stopping by pattern [$pattern]: $pids"
      kill $pids 2>/dev/null || true
      sleep 0.3
      kill -9 $pids 2>/dev/null || true
    fi
    return 0
  fi
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command \
      "\$pattern='$pattern'; \$targets=Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like \"*\$pattern*\" } | Select-Object -ExpandProperty ProcessId; foreach(\$id in \$targets){ Stop-Process -Id \$id -Force -ErrorAction SilentlyContinue }" >/dev/null 2>&1 || true
  fi
}

resolve_python() {
  if [[ -x "$ROOT_DIR/.venv-Hackathon/Scripts/python.exe" ]]; then
    echo "$ROOT_DIR/.venv-Hackathon/Scripts/python.exe"
    return 0
  fi
  if [[ -x "$ROOT_DIR/backend/.venv/Scripts/python.exe" ]]; then
    echo "$ROOT_DIR/backend/.venv/Scripts/python.exe"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi
  echo "python"
}

start_backend() {
  local py
  local agent_options_file
  local reload_flag=""
  py="$(resolve_python)"
  agent_options_file="$(resolve_agent_options_file)"
  if [[ "$BACKEND_RELOAD" == "1" ]]; then
    reload_flag="--reload"
  fi
  echo "Starting backend on :$BACKEND_PORT"
  echo "Using AGENT_OPTIONS_FILE=$agent_options_file"
  (
    cd "$ROOT_DIR/backend"
    AGENT_OPTIONS_FILE="$agent_options_file" \
      nohup "$py" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" $reload_flag >"$BACKEND_LOG" 2>&1 </dev/null &
    echo $! >"$BACKEND_PID_FILE"
  )
}

start_frontend() {
  echo "Starting frontend on :$FRONTEND_PORT"
  (
    cd "$ROOT_DIR/frontend"
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 </dev/null &
    echo $! >"$FRONTEND_PID_FILE"
  )
}

stop_all() {
  kill_pid_file "$BACKEND_PID_FILE"
  kill_pid_file "$FRONTEND_PID_FILE"
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  for extra_port in $FRONTEND_EXTRA_PORTS; do
    kill_port "$extra_port"
  done
  kill_by_pattern "uvicorn app.main:app"
  kill_by_pattern "vite --host"
  kill_by_pattern "trae-sandbox 'npx vite"
}

status() {
  echo "Backend log:  $BACKEND_LOG"
  echo "Frontend log: $FRONTEND_LOG"
  if command -v lsof >/dev/null 2>&1; then
    echo "Backend listeners:"
    lsof -i tcp:"$BACKEND_PORT" -sTCP:LISTEN || true
    echo "Frontend listeners:"
    lsof -i tcp:"$FRONTEND_PORT" -sTCP:LISTEN || true
  else
    echo "Use logs to verify startup:"
    echo "tail -f \"$BACKEND_LOG\""
    echo "tail -f \"$FRONTEND_LOG\""
  fi
}

mode="${1:-restart}"
case "$mode" in
  start)
    start_backend
    start_frontend
    ;;
  restart)
    stop_all
    start_backend
    start_frontend
    ;;
  stop)
    stop_all
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 [start|restart|stop|status]"
    exit 1
    ;;
esac

echo "Done. Backend: http://localhost:$BACKEND_PORT  Frontend: http://localhost:$FRONTEND_PORT"
echo "Logs:"
echo "  $BACKEND_LOG"
echo "  $FRONTEND_LOG"
