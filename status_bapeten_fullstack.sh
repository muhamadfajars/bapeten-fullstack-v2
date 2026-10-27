#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$ROOT/run/bapeten-fullstack.pid"
PORT="${BAPETEN_PORT:-8001}"
if [ ! -f "$PIDFILE" ]; then echo 'Status: STOPPED (PID file tidak ditemukan)'; exit 0; fi
PID="$(cat "$PIDFILE")"
if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
  echo "Status: RUNNING (PID $PID)"
  echo "URL HPC: http://127.0.0.1:$PORT"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/v1/health" || true
    echo
  fi
else echo 'Status: STOPPED (PID file kedaluwarsa)'; fi
