#!/usr/bin/env bash
# BAPETEN AI Evaluator Full-Stack — start React + FastAPI with a single HTTP port.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
PIDFILE="$ROOT/run/bapeten-fullstack.pid"
LOGFILE="$ROOT/logs/bapeten-fullstack.log"
HOST="${BAPETEN_HOST:-127.0.0.1}"
PORT="${BAPETEN_PORT:-8001}"
if [ "$HOST" != '127.0.0.1' ]; then
  echo 'ERROR: Launcher ini sengaja hanya bind ke 127.0.0.1 untuk akses via SSH tunnel.' >&2
  echo 'Gunakan konfigurasi reverse proxy + TLS + autentikasi institusi untuk akses jaringan.' >&2
  exit 1
fi
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
  echo 'ERROR: BAPETEN_PORT harus 1024-65535' >&2; exit 1
fi
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo 'ERROR: frontend/dist belum dibuild. Jalankan bash setup_bapeten_fullstack.sh dahulu.' >&2
  exit 1
fi
if [ -n "${BAPETEN_PYTHON:-}" ]; then
  PYTHON="$BAPETEN_PYTHON"
else
  PYTHON="$BACKEND/.venv/bin/python"
fi
if [ ! -x "$PYTHON" ]; then
  echo 'ERROR: Python backend belum disiapkan. Jalankan setup_bapeten_fullstack.sh.' >&2
  exit 1
fi
ENV_FILE="$BACKEND/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo 'ERROR: backend/.env belum ada. Jalankan setup_bapeten_fullstack.sh.' >&2
  exit 1
fi
if [ "$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo 600)" != '600' ]; then chmod 600 "$ENV_FILE"; fi
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a
if [ -z "${BAPETEN_API_TOKEN:-}" ] || [ "$BAPETEN_API_TOKEN" = 'CHANGE_TO_A_LONG_RANDOM_SECRET' ]; then
  echo 'ERROR: backend/.env harus memiliki BAPETEN_API_TOKEN yang aman.' >&2
  exit 1
fi
export BAPETEN_FRONTEND_DIST="$ROOT/frontend/dist"
export BAPETEN_DATA_DIR="${BAPETEN_DATA_DIR:-$HOME/bapeten-private-data}"
mkdir -p "$BAPETEN_DATA_DIR" "$ROOT/run" "$ROOT/logs"
chmod 700 "$BAPETEN_DATA_DIR" "$ROOT/run" "$ROOT/logs"

if [ -f "$PIDFILE" ]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    CMD="$(ps -p "$OLD_PID" -o args= 2>/dev/null || true)"
    if [[ "$CMD" == *'uvicorn app.main:app'* ]]; then
      echo "Aplikasi sudah berjalan, PID $OLD_PID. Akses: http://127.0.0.1:$PORT"; exit 0
    fi
    echo "ERROR: PID $OLD_PID milik proses lain; cek $PIDFILE sebelum lanjut." >&2
    exit 1
  fi
  rm -f "$PIDFILE"
fi

"$PYTHON" -c 'import fastapi, uvicorn, multipart' || {
  echo 'ERROR: dependensi FastAPI belum siap. Jalankan setup_bapeten_fullstack.sh.' >&2; exit 1;
}

command -v setsid >/dev/null || { echo "ERROR: setsid tidak tersedia." >&2; exit 1; }
echo "Menjalankan BAPETEN Full-Stack di 127.0.0.1:$PORT ..."
(
  cd "$BACKEND"
  exec setsid "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 1 < /dev/null >> "$LOGFILE" 2>&1
) &
PID=$!
sleep 0.3
PGID="$(ps -p "$PID" -o pgid= 2>/dev/null | tr -d '[:space:]' || true)"
if [[ "$PGID" != "$PID" ]]; then
  echo "ERROR: backend tidak berada di process group mandiri; start dibatalkan (PID=$PID, PGID=$PGID)." >&2
  kill -TERM "$PID" 2>/dev/null || true
  exit 1
fi
printf '%s\n' "$PID" > "$PIDFILE"

# The health endpoint does NOT require an API token.
READY=0
for attempt in $(seq 1 35); do
  if ! kill -0 "$PID" 2>/dev/null; then break; fi
  if "$PYTHON" - "$PORT" <<'PY' >/dev/null 2>&1
import sys, urllib.request
port=sys.argv[1]
with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health',timeout=1) as r:
    assert r.status==200
with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=1) as r:
    assert r.status==200 and b'<html' in r.read(3000).lower()
PY
  then READY=1; break; fi
  sleep 1
done
if [ "$READY" -ne 1 ]; then
  echo "ERROR: server tidak siap. Lihat: tail -n 80 '$LOGFILE'" >&2
  bash "$ROOT/stop_bapeten_fullstack.sh" || true
  exit 1
fi
printf 'Berhasil: PID %s | http://127.0.0.1:%s\n' "$PID" "$PORT"
echo "Tunnel di laptop: ssh -L $PORT:127.0.0.1:$PORT USER@HPC"
echo "Buka di laptop: http://localhost:$PORT/"
echo "Log: $LOGFILE"
