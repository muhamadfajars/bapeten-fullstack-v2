#!/usr/bin/env bash
# BAPETEN AI Evaluator Full-Stack — one-time setup on HPC Ubuntu.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo "=== Setup BAPETEN AI Evaluator Full-Stack ==="
if [ ! -f "$BACKEND/requirements.txt" ] || [ ! -f "$FRONTEND/package.json" ]; then
  echo "ERROR: Jalankan file ini dari paket full-stack lengkap (backend/ dan frontend/ harus ada)." >&2
  exit 1
fi

BOOTSTRAP_PYTHON="${BAPETEN_BOOTSTRAP_PYTHON:-python3}"
if ! command -v "$BOOTSTRAP_PYTHON" >/dev/null 2>&1; then
  echo "ERROR: Python 3 tidak ditemukan." >&2; exit 1
fi
"$BOOTSTRAP_PYTHON" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ diperlukan"'
if [ -n "${BAPETEN_PYTHON:-}" ]; then
  PYTHON="${BAPETEN_PYTHON}"
  if [ ! -x "$PYTHON" ]; then echo "ERROR: BAPETEN_PYTHON bukan executable: $PYTHON" >&2; exit 1; fi
  echo "Memakai Python environment existing: $PYTHON"
else
  if [ ! -x "$BACKEND/.venv/bin/python" ]; then
    echo "Membuat Python venv backend/.venv ..."
    "$BOOTSTRAP_PYTHON" -m venv "$BACKEND/.venv"
  fi
  PYTHON="$BACKEND/.venv/bin/python"
fi

echo "Memasang/memeriksa paket Python..."
"$PYTHON" -m pip install -r "$BACKEND/requirements.txt"
"$PYTHON" -m compileall -q "$BACKEND/app" "$BACKEND/engine/src"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: Node.js >=20 dan npm diperlukan SEKALI untuk membangun React." >&2
  echo "Alternatif: build frontend di laptop, lalu salin folder frontend/dist ke HPC." >&2
  exit 1
fi
node -e 'if (Number(process.versions.node.split(".")[0]) < 20) process.exit(1)' || {
  echo "ERROR: Node.js minimum versi 20" >&2; exit 1;
}
echo "Memasang/memeriksa paket npm dan membangun frontend..."
(cd "$FRONTEND" && {
  if [ -f package-lock.json ]; then npm ci; else npm install; fi
  VITE_API_URL= npm run build
})
if [ ! -f "$FRONTEND/dist/index.html" ]; then
  echo "ERROR: Build frontend tidak menghasilkan dist/index.html." >&2; exit 1
fi

ENV_FILE="$BACKEND/.env"
if [ ! -f "$ENV_FILE" ]; then
  TOKEN="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  {
    printf 'BAPETEN_API_TOKEN=%q\n' "$TOKEN"
    printf 'BAPETEN_DATA_DIR=%q\n' "${BAPETEN_DATA_DIR:-$HOME/bapeten-private-data}"
    printf 'BAPETEN_MAX_FILE_MB=40\n'
    printf 'BAPETEN_MAX_DOCUMENTS=120\n'
    printf 'BAPETEN_ANALYSIS_WORKERS=1\n'
    printf 'BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV=0\n'
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Token privat baru disimpan di backend/.env (TIDAK ditampilkan otomatis)."
else
  chmod 600 "$ENV_FILE"
  echo "Memakai backend/.env yang sudah ada; token tidak diubah."
fi
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a
mkdir -p "$BAPETEN_DATA_DIR" "$ROOT/logs" "$ROOT/run"
chmod 700 "$BAPETEN_DATA_DIR" "$ROOT/logs" "$ROOT/run"
echo
printf 'SELESAI: jalankan bash "%s/start_bapeten_fullstack.sh"\n' "$ROOT"
echo 'Akses lewat SSH tunnel localhost:8001; jangan membuka port API ke internet.'
echo 'OCR Paddle/Tesseract harus tersedia pada Python environment yang dipakai backend.'
