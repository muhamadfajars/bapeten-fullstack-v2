#!/usr/bin/env bash
# BAPETEN OCR environment repair v0.2.2: backend venv ONLY.
# No sudo. Does not touch Streamlit, uploaded files, matching, frontend or .env.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
PY="$BACKEND/.venv/bin/python"
ACTION="${1:---check}"

case "$ACTION" in
  --check|--diagnose|--install-paddle) ;;
  *) printf 'Usage: bash setup_bapeten_ocr.sh [--check|--diagnose|--install-paddle]\n' >&2; exit 2;;
esac
if [[ ! -x "$PY" ]]; then
  echo "ERROR: Python backend venv tidak ditemukan di $PY" >&2
  echo "Pastikan direktori proyek benar; jalankan setup backend lebih dulu." >&2
  exit 1
fi

printf '\n=== OCR backend environment ===\n'
"$PY" - <<'PY'
import sys, platform, sysconfig, shutil, importlib.util
print('Python path:',sys.executable)
print('Python version:',sys.version.split()[0])
print('Architecture:',platform.machine())
print('System:',platform.system(),platform.release())
print('Platform tag:',sysconfig.get_platform())
print('Tesseract binary:',shutil.which('tesseract') or 'NOT FOUND')
for module in ('paddle','paddleocr','pytesseract','fitz','cv2'):
    try: ok=bool(importlib.util.find_spec(module))
    except Exception: ok=False
    print(module + ':', 'PRESENT' if ok else 'MISSING')
PY
"$PY" -m pip --version

if [[ "$ACTION" == '--install-paddle' ]]; then
  # Wheel availability depends on CPython tag, CPU and platform; explicit guard.
  if ! "$PY" - <<'PY'
import sys,platform
assert (3,9) <= sys.version_info[:2] <= (3,13), 'Need CPython 3.9–3.13 for the selected releases'
assert platform.system() == 'Linux' and platform.machine().lower() in {'x86_64','amd64'}, 'Selected Paddle CPU wheels require Linux x86_64'
PY
  then
    echo 'ERROR: Platform/Python incompatible with the selected Paddle CPU wheels.' >&2
    echo 'Tampilkan output --check ke administrator; jangan mengubah Python sistem.' >&2
    exit 3
  fi
  if [[ -r /proc/cpuinfo ]] && ! grep -qiE '(^|[[:space:]])avx([[:space:]]|$)' /proc/cpuinfo; then
    echo 'ERROR: AVX CPU flag tidak terlihat. Wheel Paddle resmi perlu AVX; periksa setting VM/CPU bersama admin.' >&2
    exit 3
  fi
  echo
  echo 'Installing PaddlePaddle CPU in backend/.venv only.'
  echo 'Attempt 1: PyPI explicit index, paddlepaddle==3.3.1'
  if ! "$PY" -m pip install --prefer-binary --timeout 20 --retries 1 --index-url https://pypi.org/simple 'paddlepaddle==3.3.1'; then
    echo
    echo 'Attempt 2: PaddlePaddle official CPU wheel index, paddlepaddle==3.3.0'
    if ! "$PY" -m pip install --prefer-binary --timeout 20 --retries 1 --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/ 'paddlepaddle==3.3.0'; then
      echo 'ERROR: Paddle wheel tidak dapat diperoleh dari dua sumber.' >&2
      echo 'Periksa akses jaringan/repository pip dan hasil --check; jangan ubah versi secara acak.' >&2
      exit 4
    fi
  fi
  echo
  echo 'Installing PaddleOCR 3.x in backend/.venv.'
  "$PY" -m pip install --prefer-binary --timeout 20 --retries 1 --index-url https://pypi.org/simple 'paddleocr>=3,<4'
  "$PY" - <<'PY'
import paddle
from paddleocr import PaddleOCR
print('Paddle installed version:', getattr(paddle,'__version__','unknown'))
print('PaddleOCR import: OK')
PY
fi

printf '\n=== OCR doctor ===\n'
if [[ -f "$BACKEND/scripts/doctor_ocr.py" ]]; then
  "$PY" "$BACKEND/scripts/doctor_ocr.py"
else
  echo 'Doctor script missing; inspect your v0.2.1 patch installation.'
fi
printf '\nNote: Tesseract is a separate executable, NOT provided by pip install pytesseract.\n'
printf 'Do not paste backend/.env tokens into support chats.\n'
