#!/usr/bin/env python3
"""No network; reports OCR readiness of the EXACT backend interpreter."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

print('=== BAPETEN OCR DOCTOR ===')
print('Python:', sys.executable)
print('Python version:', sys.version.split()[0])
print('Preferred OCR:', os.getenv('BAPETEN_OCR_ENGINE','auto'))
mods = {k: bool(importlib.util.find_spec(k)) for k in
        ('paddle','paddleocr','pytesseract','cv2','fitz','PIL')}
for name,installed in mods.items():
    print(f'{name}: {"OK" if installed else "MISSING"}')
cmd=os.getenv('BAPETEN_TESSERACT_CMD','').strip() or shutil.which('tesseract')
if cmd and not (Path(cmd).is_file() or shutil.which(cmd)):
    cmd=None
languages=[]
if cmd:
    try:
        version=subprocess.run([cmd,'--version'],capture_output=True,text=True,timeout=5)
        available=subprocess.run([cmd,'--list-langs'],capture_output=True,text=True,timeout=5)
        if version.returncode==0:
            print('Tesseract executable:', cmd)
            print('Tesseract version:', (version.stdout or version.stderr).splitlines()[0])
            languages=[s.strip() for s in available.stdout.splitlines()[1:]] if available.returncode==0 else []
            print('Tesseract languages:', ', '.join(x for x in ('eng','ind') if x in languages) or '(eng/ind not found)', f'({len(languages)} packs installed)')
        else:cmd=None
    except (OSError,subprocess.TimeoutExpired) as exc:
        print('Tesseract executable error:',exc);cmd=None
else:
    print('Tesseract executable: MISSING')

engine=os.getenv('BAPETEN_OCR_ENGINE','auto').lower()
paddle_ready=mods['paddle'] and mods['paddleocr']
tess_ready=bool(cmd) and mods['pytesseract'] and bool(languages)
if engine=='paddle':usable=paddle_ready
elif engine=='tesseract':usable=tess_ready
else:usable=paddle_ready or tess_ready
print('OCR dependency state:', 'READY (dependency check)' if usable else 'NOT READY')
if not paddle_ready:
    print('PaddleOCR missing: optional CPU installation via bash setup_bapeten_ocr.sh --install-paddle')
if not tess_ready:
    print('Tesseract missing: ask HPC administrator to install tesseract-ocr and English language data, or configure BAPETEN_TESSERACT_CMD')
if tess_ready and not paddle_ready:
    print('Fallback Tesseract active. OCR scan accuracy may be lower; review ambiguous fields.')
if 'eng' not in languages and tess_ready:
    print('WARNING: English language pack missing (scan OCR may degrade).')
if '--strict' in sys.argv and not usable:
    sys.exit(2)
