"""Conservative second opinion for an O/0-confused SERIAL LABEL only.

Never rewrite an unrelated serial to the form value. Return MATCH only if a
second independent Tesseract pass directly reads the expected token from source.
"""
from __future__ import annotations
import re
from pathlib import Path


def normalize_serial(s):
    return re.sub(r'[^A-Z0-9]','',str(s or '').upper())


def _ambiguity_only(expected,observed):
    a,b=normalize_serial(expected),normalize_serial(observed)
    if len(a)<5 or len(a)!=len(b) or a==b:return False
    diffs=[(x,y) for x,y in zip(a,b) if x!=y]
    return len(diffs)<=2 and all({x,y}=={'O','0'} for x,y in diffs)


def verify_image_serial(path, expected, observed, page=1):
    """Observed is unchanged on failure. Never validate by fuzzy distance alone."""
    if not _ambiguity_only(expected,observed):return None
    try:
        from PIL import Image,ImageOps,ImageEnhance
        import pytesseract, fitz
        src=Path(path)
        if src.suffix.lower()=='.pdf':
            with fitz.open(src) as pdf:
                if not 1<=page<=len(pdf):return None
                pg=pdf[page-1]
                scale=min(2.5,2600/max(pg.rect.width,pg.rect.height))
                pix=pg.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
                im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        elif src.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.bmp'):
            with Image.open(src) as img:im=img.convert('RGB')
        else:return None
        if max(im.size)>2600:im.thumbnail((2600,2600))
        gray=ImageOps.grayscale(im)
        variants=[ImageEnhance.Contrast(gray).enhance(1.9)]
        # Two cheap orientations/layouts; no expensive Paddle inference.
        target=normalize_serial(expected)
        token=re.compile(r'(?<![A-Z0-9])'+re.escape(target)+r'(?![A-Z0-9])')
        for variant in variants:
            for psm in (11,6):
                raw=pytesseract.image_to_string(variant,lang='eng',config=f'--psm {psm}')
                flat=re.sub(r'(?<=\w)\s+(?=\w)','',raw.upper())
                if token.search(raw.upper()) or token.search(flat):
                    return {'status':'MATCH','observed':str(expected),'score':100.0,
                            'note':'Nomor seri dikonfirmasi OCR kedua pada gambar sumber'}
    except Exception:
        return None
    return None
