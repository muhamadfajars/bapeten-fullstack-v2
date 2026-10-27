"""Shared selective PDF/image reader for BAPETEN documents.
Never infer MATCH from text presence or absence. Preserve reading method per page.
"""
import re
from pathlib import Path
import cv2
import numpy as np
import pymupdf

IMAGE_SUFFIXES={'.jpg','.jpeg','.png','.bmp','.webp'}

def _poor_text(text, min_chars=80):
    stripped=''.join(c for c in text if not c.isspace())
    if len(stripped)<min_chars:return True
    replacement=text.count('\ufffd')
    controls=sum(ord(c)<32 and c not in '\r\n\t' for c in text)
    return (replacement+controls)/max(len(text),1)>0.03

def _ocr(img):
    from src.extraction.label_ocr import extract_ocr
    records=extract_ocr(img)
    return '\n'.join(str(record.get('text','')).strip() for record in records if str(record.get('text','')).strip())

def read_pages(path, dpi=180, min_chars=80, force_ocr=False):
    path=str(path);suffix=Path(path).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        data=np.fromfile(path,dtype=np.uint8);img=cv2.imdecode(data,cv2.IMREAD_COLOR)
        if img is None:raise ValueError('Gambar tidak bisa dibaca')
        txt=_ocr(img)
        return [{'page':1,'text':txt,'lines':txt.splitlines(),'method':'OCR','native_text':'','ocr_text':txt}]
    if suffix!='.pdf':raise ValueError('Format harus PDF atau gambar')
    pages=[]
    with pymupdf.open(path) as doc:
        for i,page in enumerate(doc):
            native=page.get_text('text',sort=True).strip()
            use_ocr=force_ocr or _poor_text(native,min_chars)
            ocr_text='';method='PDF_TEXT';text=native
            if use_ocr:
                pix=page.get_pixmap(dpi=dpi,alpha=False,colorspace=pymupdf.csRGB)
                rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
                ocr_text=_ocr(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                if ocr_text:
                    text=ocr_text;method='OCR'
                elif native:
                    method='PDF_TEXT_OCR_EMPTY'
                else:
                    method='OCR_EMPTY'
            pages.append({'page':i+1,'text':text,'lines':text.splitlines(),
                          'method':method,'native_text':native,'ocr_text':ocr_text})
    return pages


def retry_ocr_for_missing(path, pages, missing_fields, dpi=180, max_pages=12):
    """OCR selectively on PDF_TEXT pages when required extracted fields are missing.

    Returns (pages, diagnostics). Original page text is preserved. Pages already OCRed
    are never OCRed twice. Callers MUST re-extract and resolve conflicts; this helper
    never asserts that a field is present or a match is valid.
    """
    requested=tuple(sorted(set(missing_fields or ())))
    diag={'requested_fields':list(requested),'retried_pages':[],
          'skipped_pages':[],'warnings':[]}
    if not requested or Path(path).suffix.lower()!='.pdf':
        return pages,diag
    candidates=[p for p in pages if p.get('method')=='PDF_TEXT']
    if len(candidates)>max_pages:
        diag['warnings'].append('OCR completeness retry capped at %s pages' % max_pages)
    indexes={p['page'] for p in candidates[:max_pages]}
    if not indexes:return pages,diag
    result=[]
    with pymupdf.open(str(path)) as doc:
        for pg in pages:
            if pg['page'] not in indexes:
                result.append(pg);continue
            page=doc[pg['page']-1]
            pix=page.get_pixmap(dpi=dpi,alpha=False,colorspace=pymupdf.csRGB)
            rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
            try:
                ocr_text=_ocr(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            except Exception as exc:
                diag['warnings'].append(f"OCR page {pg['page']} failed: {type(exc).__name__}: {exc}")
                result.append(pg);continue
            copy=dict(pg)
            if ocr_text.strip():
                native=pg.get('native_text') or pg.get('text','')
                copy.update({'native_text':native,'ocr_text':ocr_text,
                             'text':native+'\n'+ocr_text,
                             'lines':(native+'\n'+ocr_text).splitlines(),
                             'method':'PDF_TEXT_PLUS_OCR'})
                diag['retried_pages'].append(pg['page'])
            else:
                diag['skipped_pages'].append(pg['page'])
            result.append(copy)
    return result,diag
