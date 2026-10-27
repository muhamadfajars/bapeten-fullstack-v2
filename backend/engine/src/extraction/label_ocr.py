"""OCR engine adapter, CPU/HPC safe.

PaddleOCR is preferred. Tesseract is a documented fallback when Paddle isn't
available; it is not a silent substitute for a verified PaddleOCR result.
The OCR engine is initialized lazily to avoid importing heavy modules while
parsing PDFs with an existing text layer. Does not modify matching decisions.
"""
from __future__ import annotations
import os
import re
import shutil
import threading
from pathlib import Path

import cv2

_lock = threading.RLock()
_engine = None
_mode = None
_init_error = None
_ocr_engines = {}  # retain independent fast and quality models per worker


def ensure_bgr(image):
    if image is None or isinstance(image, str):
        return image
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if len(image.shape) == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _tess_cmd():
    candidate = os.getenv('BAPETEN_TESSERACT_CMD', '').strip()
    if candidate:
        found = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if not found:
            raise RuntimeError(f'BAPETEN_TESSERACT_CMD tidak ditemukan: {candidate}')
        return str(found)
    found = shutil.which('tesseract')
    if not found:
        raise RuntimeError('Tesseract OCR tidak ditemukan pada PATH HPC. Pasang executable tesseract atau set BAPETEN_TESSERACT_CMD.')
    return found


def _load_paddle():
    # PaddlePaddle 3.3.x PIR/oneDNN CPU runtime cannot handle some float array attrs.
    # Disable oneDNN in the OCR pipeline itself, before importing PaddleX/PaddleOCR.
    os.environ['PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT'] = '0'
    import paddleocr
    from paddleocr import PaddleOCR
    version = getattr(paddleocr, '__version__', '0')
    try:
        major = int(version.split('.')[0])
    except (ValueError, TypeError):
        major = 3
    threads=max(1,int(os.getenv('BAPETEN_OCR_CPU_THREADS','4')))
    profile=os.getenv('BAPETEN_OCR_PROFILE','fast').strip().lower()
    if major >= 3:
        # Speed path: two mobile models, no three auxiliary models, bounded CPU threads.
        # Original accuracy path is reversible by setting BAPETEN_OCR_PROFILE=quality.
        if profile=='fast':
            kwargs=dict(device='cpu',
                        text_detection_model_name='PP-OCRv5_mobile_det',
                        text_recognition_model_name='PP-OCRv5_mobile_rec',
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        cpu_threads=threads,enable_mkldnn=False)
        else:
            kwargs=dict(device='cpu',use_doc_orientation_classify=True,
                        use_doc_unwarping=True,use_textline_orientation=True,
                        cpu_threads=threads,enable_mkldnn=False)
        try:
            engine=PaddleOCR(**kwargs)
        except TypeError:
            # Runtime may use an older 3.x API; preserve a working OCR engine.
            # Some early 3.x builds reject `device`, but we must NEVER drop
            # enable_mkldnn=False or re-enter the broken PIR executor.
            kwargs.pop('device',None)
            try:
                engine=PaddleOCR(**kwargs)
            except TypeError as exc:
                raise RuntimeError('PaddleOCR tidak menerima enable_mkldnn=False; jangan aktifkan oneDNN pada konfigurasi ini. Periksa versi paddleocr.') from exc
        return engine,'paddle_v3'
    engine = PaddleOCR(use_angle_cls=(profile!='fast'), lang='en', use_gpu=False,
                       enable_mkldnn=False, cpu_threads=threads,
                       show_log=False)
    return engine, 'paddle_v2'


def create_ocr():
    """Cache OCR engines by profile; a prior fast read cannot poison quality OCR."""
    global _engine,_mode,_init_error
    profile=os.getenv('BAPETEN_OCR_PROFILE','fast').strip().lower()
    configured=os.getenv('BAPETEN_OCR_ENGINE','auto').strip().lower()
    if configured not in ('auto','paddle','tesseract'):
        raise RuntimeError('BAPETEN_OCR_ENGINE harus auto, paddle, atau tesseract')
    key=(configured,profile)
    with _lock:
        if key in _ocr_engines:
            _engine,_mode=_ocr_engines[key]
            return _engine,_mode
        if configured!='tesseract':
            try:
                _engine,_mode=_load_paddle()
                _ocr_engines[key]=(_engine,_mode)
                return _engine,_mode
            except Exception as exc:
                _init_error=f'{type(exc).__name__}: {exc}'
                if configured=='paddle':
                    raise RuntimeError('PaddleOCR tidak siap: '+_init_error) from exc
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd=_tess_cmd()
        pytesseract.get_tesseract_version()
        _engine,_mode=pytesseract,'tesseract'
        _ocr_engines[key]=(_engine,_mode)
        return _engine,_mode


def extract_ocr_v3(image):
    engine, _ = create_ocr()
    rows = []
    for res in engine.predict(image):
        data = res.json
        data = data.get('res', data) if isinstance(data, dict) else {}
        for text, score, box in zip(data.get('rec_texts', []),
                                    data.get('rec_scores', []),
                                    data.get('rec_boxes', [])):
            if str(text).strip():
                rows.append({'text':str(text).strip(), 'confidence':float(score),
                             'box':box.tolist() if hasattr(box,'tolist') else box,
                             'engine':'paddle'})
    return rows


def extract_ocr_v2(image):
    engine, _ = create_ocr()
    rows=[]
    for page in (engine.ocr(image, cls=True) or []):
        for item in page or []:
            if not item or len(item)<2 or not item[1] or len(item[1])<2:
                continue
            text, score = item[1][:2]
            if str(text).strip():
                rows.append({'text':str(text).strip(),'confidence':float(score),
                             'box':item[0], 'engine':'paddle'})
    return rows


def _tesseract_ocr(image):
    import numpy as np
    from PIL import Image
    import pytesseract
    if isinstance(image, str):
        image = Image.open(image).convert('RGB')
    elif isinstance(image, np.ndarray):
        image = Image.fromarray(cv2.cvtColor(ensure_bgr(image),cv2.COLOR_BGR2RGB))
    data = pytesseract.image_to_data(image, config='--psm 11', output_type=pytesseract.Output.DICT)
    groups={}
    order=[]
    count=len(data.get('text', []))
    for i in range(count):
        word=str(data['text'][i] or '').strip()
        if not word:continue
        try:conf=float(data['conf'][i])
        except (ValueError,TypeError):continue
        if conf < 0:continue
        key=tuple(data[k][i] for k in ('page_num','block_num','par_num','line_num'))
        if key not in groups:
            groups[key]=[];order.append(key)
        groups[key].append((word,conf, int(data['left'][i]),int(data['top'][i]),
                            int(data['width'][i]),int(data['height'][i])))
    out=[]
    for key in order:
        words=groups[key]
        line=' '.join(x[0] for x in words).strip()
        x0=min(x[2] for x in words); y0=min(x[3] for x in words)
        x1=max(x[2]+x[4] for x in words); y1=max(x[3]+x[5] for x in words)
        confidence=sum(x[1] for x in words)/len(words)/100.0
        if line:
            out.append({'text':line, 'confidence':min(round(confidence,4),0.8),
                        'box':[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],
                        'engine':'tesseract'})
    return out


def extract_ocr(image):
    if image is None:return []
    engine, mode = create_ocr()
    image=ensure_bgr(image)
    if mode=='paddle_v3':return extract_ocr_v3(image)
    if mode=='paddle_v2':return extract_ocr_v2(image)
    if mode=='tesseract':return _tesseract_ocr(image)
    raise RuntimeError('OCR backend tidak dikenal')


def get_ocr_mode():
    return _mode or 'uninitialized'


def get_ocr_info():
    return {'mode':get_ocr_mode(), 'paddle_error':_init_error}


def print_ocr_results(results,title=None):
    if title:print(title)
    for row in results:
        print(f"{row.get('confidence',0):.3f} | {row.get('text','')}")
