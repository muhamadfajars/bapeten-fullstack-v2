"""Two-layer document classifier for BAPETEN AI Evaluator.

Layer 1: High-speed heuristic regex matching on filename patterns and personnel subtypes.
Layer 2: Content inspection from the first few pages (digital text or fast OCR on page 1).
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path
from typing import Any, Tuple, Optional

import fitz  # PyMuPDF
from PIL import Image

try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False

try:
    import docx
    _HAS_DOCX = True
except ImportError:
    _HAS_DOCX = False

CATEGORIES = (
    'formulir', 'proteksi', 'perawatan', 'manajemen', 'teknis',
    'personel', 'tld', 'spesifikasi', 'label', 'impor',
    'kesesuaian', 'fungsi', 'paparan', 'kebocoran'
)

# One source for browser and backend filename rules. Keep this JSON with the
# backend package; the frontend bundles the same file during its build.
_RULES = json.loads(Path(__file__).with_name('classification_rules.json').read_text(encoding='utf-8'))
NAME_PATTERNS: list[tuple[str, str, Optional[str]]] = [
    (f"(?{_RULES['flags']}){rule['pattern']}", rule['category'], rule['subtype'])
    for rule in _RULES['filenamePatterns']
]

# Layer 2: Regex on extracted text content
CONTENT_PATTERNS: list[tuple[str, str, Optional[str]]] = [
    # Formulir
    (r'(?i)FORMULIR\s+PERMOHONAN|BADAN\s+PENGAWAS\s+TENAGA\s+NUKLIR\s+.*PERMOHONAN', 'formulir', None),
    
    # Proteksi
    (r'(?i)PROGRAM\s+PROTEKSI\s+DAN\s+KESELAMATAN\s+RADIASI|PROGRAM\s+PROTEKSI\s+RADIASI', 'proteksi', None),
    
    # Perawatan
    (r'(?i)(?:DOKUMEN\s+)?PROGRAM\s+PERAWATAN\b|DOKUMEN\s+PERAWATAN\b', 'perawatan', None),
    
    # Manajemen
    (r'(?i)SISTEM\s+MANAJEMEN\s+FASILITAS|SISTEM\s+MANAJEMEN\s+KESELAMATAN|SISTEM\s+MANAJEMEN\b|ASSURANCE\s+QUALIT|QUALITY\s+SYSTEM|SERTIFIKAT\s+MUTU', 'manajemen', None),
    
    # Teknis
    (r'(?i)DOKUMEN\s+TEKNIS\s+FASILITAS|RENCANA\s+TEKNIS|BANGUNAN\s+GEDUNG\s+PENAHAN|DENAH\s+RUANG\s+RADIOLOGI', 'teknis', None),
    
    # Personel
    (r'(?i)SURAT\s+KETERANGAN\s+KERJA', 'personel', 'Surat Keterangan Kerja'),
    (r'(?i)SURAT\s+PENUNJUKAN\s+(?:TUGAS|(?:SEBAGAI\s+)?(?:PPR\b|PETUGAS\s+PROTEKSI(?:\s+RADIASI)?))|PENETAPAN\s+PEKERJA\s+RADIASI|PENUNJUKAN\s+(?:PPR\b|PETUGAS\s+PROTEKSI\s+RADIASI)|SURAT\s+KEPUTUSAN\s+PENUNJUKAN|PENGANGKATAN\s+PETUGAS\s+PROTEKSI', 'personel', 'Surat Penunjukan Tugas'),
    (r'(?i)SURAT\s+PERINTAH', 'personel', 'Surat Perintah'),
    (r'(?i)SERTIFIKAT\s+KOMPETENSI|SERTIFIKAT\s+LULUS\s+UJI\s+KOMPETENSI', 'personel', 'Sertifikat Kompetensi'),
    (r'(?i)SURAT\s+IZIN\s+KERJA|SIKR\b', 'personel', 'Surat Izin Kerja'),
    (r'(?i)SURAT\s+IZIN\s+BEKERJA\s+PETUGAS|SURAT\s+IZIN\s+BEKERJA\s+\(SIB\)|SIB\s+PPR', 'personel', 'Surat Izin Bekerja (SIB)'),
    (r'(?i)SURAT\s+IZIN\s+PRAKTIK|SURAT\s+IZIN\s+PRAKTEK|DOKTER\s+SPESIALIS\s+RADIOLOGI', 'personel', 'Surat Izin Praktik (SIP)'),
    (r'(?i)ZERO\s+CHECK|ZERO\s+CEK|(?:LAPORAN\s+)?(?:HASIL\s+)?(?:EVALUASI|PEMBACAAN)\s+DOSIS|LAPORAN\s+DOSIS|DOSIS\s+AWAL|DOSIS\s+RADIASI\s+TLD', 'personel', 'Evaluasi Dosis / Zero Check'),
    
    # TLD
    # Technology names and laboratory branding alone do not identify administration.
    (r'(?i)DAFTAR\s+(?:PEMAKAI|PENGGUNA|PESERTA)\s+(?:LENCANA\s+)?(?:TLD|OSL|DOSIMETER)\b|PETUGAS\s+(?:TLD|OSL)\b|(?:ADMINISTRASI|KEPESERTAAN)\s+(?:(?:PEMANTAUAN|LAYANAN)\s+)?(?:TLD|OSL|DOSIMETER)\b', 'tld', None),
    
    # Spesifikasi
    (r'(?i)SPESIFIKASI|SPECIFICATIONS|BROCHURE|TECHNICAL\s+SPECIFICATIONS', 'spesifikasi', None),
    
    # Impor
    (r'(?i)PERSETUJUAN\s+IMPOR|SURAT\s+PERSETUJUAN\s+IMPOR|IMPORT\s+APPROVAL', 'impor', None),
    
    # Kesesuaian
    (r'(?i)SERTIFIKAT\s+UJI\s+KESESUAIAN|HASIL\s+UJI\s+KESESUAIAN|LEMBAR\s+HASIL\s+UJI|DATA\s+PERMOHONAN\s+LHU', 'kesesuaian', None),
    
    # Fungsi
    (r'(?i)ACCEPTANCE\s+TEST|INSTALLATION\s+AND\s+VERIFICATION|SERVICE\s+REPORT|BERITA\s+ACARA\s+UJI\s+FUNGSI|HASIL\s+UJI\s+FUNGSI', 'fungsi', None),
    
    # Paparan & Kebocoran
    (r'(?i)PENGUKURAN\s+KEBOCORAN\s+TABUNG|UJI\s+KEBOCORAN\s+TABUNG', 'kebocoran', None),
    (r'(?i)PENGUKURAN\s+PAPARAN\s+RADIASI|UJI\s+PAPARAN\s+RADIASI|LAJU\s+DOSIS\s+PAPARAN', 'paparan', None),
]


# Generic mentions must not outweigh an explicit document title (e.g. a program
# filename mentioning SIP, or a zero-check report mentioning TLD).
WEAK_NAME_HINTS = set(_RULES['weakNameHints'])


def classify_by_filename(filename: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Match filename pattern against known document rules.

    Returns:
        (category, subtype, reason) or (None, None, None)
    """
    clean_name = Path(filename).name
    matches = []
    for pattern, cat, subtype in NAME_PATTERNS:
        m = re.search(pattern, clean_name)
        if m:
            hint = re.sub(r'[\s_-]+', ' ', m.group(0)).lower().strip()
            matches.append((cat, subtype, m.group(0), hint not in WEAK_NAME_HINTS))
    strong = [match for match in matches if match[3]]
    candidates = strong or matches
    if len({(cat, subtype) for cat, subtype, _, _ in candidates}) > 1:
        return None, None, 'Nama berkas mengarah ke beberapa kategori. Perlu Pilih Kategori.'
    if candidates:
        cat, subtype, evidence, _ = candidates[0]
        return cat, subtype, f'Pola nama berkas cocok: {evidence}'
    return None, None, None


def extract_document_text(filename: str, file_bytes: bytes, max_pages: int = 3) -> str:
    """Extract text from the first few pages of PDF, DOCX, or Image."""
    ext = Path(filename).suffix.lower()
    text = ''
    if ext == '.pdf':
        try:
            doc = fitz.open(stream=file_bytes, filetype='pdf')
            for i in range(min(max_pages, len(doc))):
                text += (doc[i].get_text() or '') + '\n'
            # Fallback for scanned PDF: OCR page 1
            if len(re.findall(r'[a-zA-Z]', text)) < 30 and len(doc) > 0 and _HAS_TESSERACT:
                pix = doc[0].get_pixmap(dpi=130)
                img = Image.open(io.BytesIO(pix.tobytes('png')))
                tess_lang = os.environ.get('BAPETEN_TESS_LANG', 'ind+eng')
                ocr_text = pytesseract.image_to_string(img, lang=tess_lang)
                text = (text + '\n' + ocr_text).strip()
        except Exception:
            pass
    elif ext == '.docx' and _HAS_DOCX:
        try:
            d = docx.Document(io.BytesIO(file_bytes))
            text = '\n'.join([p.text for p in d.paragraphs[:40] if p.text.strip()])
        except Exception:
            pass
    elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp') and _HAS_TESSERACT:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            tess_lang = os.environ.get('BAPETEN_TESS_LANG', 'ind+eng')
            text = pytesseract.image_to_string(img, lang=tess_lang)
        except Exception:
            pass

    return text


def classify_by_content(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Match extracted document text against known content patterns.

    Returns:
        (category, subtype, reason) or (None, None, None)
    """
    if not text or len(text.strip()) < 10:
        return None, None, None
    candidates = {}
    # Require a heading at the start of a line. Mentions within narrative text
    # are not enough evidence to choose a document category.
    for pattern, cat, subtype in CONTENT_PATTERNS:
        for m in re.finditer(pattern, text):
            line_start = text.rfind('\n', 0, m.start()) + 1
            prefix = text[line_start:m.start()]
            if re.fullmatch(r'\s*(?:DOKUMEN\s+)?', prefix, re.IGNORECASE):
                candidates[(cat, subtype)] = m.group(0)
    if len(candidates) == 1:
        (cat, subtype), evidence = next(iter(candidates.items()))
        return cat, subtype, f'Judul dokumen cocok: {evidence}'
    if candidates:
        return None, None, 'Judul dokumen mengarah ke beberapa kategori. Perlu Pilih Kategori.'
    return None, None, None


def classify_document(filename: str, file_bytes: Optional[bytes] = None) -> dict[str, Any]:
    """Two-layer classification for a document.

    Layer 1: Filename heuristic analysis.
    Layer 2: Content text extraction / OCR of first 3 pages.
    """
    clean_name = Path(filename).name

    # Layer 1
    cat1, sub1, reason1 = classify_by_filename(clean_name)
    if cat1:
        return {
            'filename': clean_name,
            'category': cat1,
            'subtype': sub1,
            'layer': 1,
            'reason': reason1,
            'confidence': 0.95
        }

    # Layer 2
    reason2 = None
    if not reason1 and file_bytes and len(file_bytes) > 0:
        text = extract_document_text(clean_name, file_bytes, max_pages=3)
        cat2, sub2, reason2 = classify_by_content(text)
        if cat2:
            return {
                'filename': clean_name,
                'category': cat2,
                'subtype': sub2,
                'layer': 2,
                'reason': reason2,
                'confidence': 0.90
            }

    # Unknown
    return {
        'filename': clean_name,
        'category': 'unknown',
        'subtype': None,
        'layer': 0,
        'reason': reason1 or reason2 or 'Dokumen belum teridentifikasi otomatis, silakan tentukan kategori',
        'confidence': 0.0
    }

