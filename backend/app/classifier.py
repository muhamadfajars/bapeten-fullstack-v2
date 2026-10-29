"""Two-layer document classifier for BAPETEN AI Evaluator.

Layer 1: High-speed heuristic regex matching on filename patterns and personnel subtypes.
Layer 2: Content inspection from the first few pages (digital text or fast OCR on page 1).
"""
from __future__ import annotations

import io
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

# Layer 1: Regex on filename
# Ordered by specificity.
NAME_PATTERNS: list[tuple[str, str, Optional[str]]] = [
    # Formulir
    (r'(?i)formulir|form[\s_-]*permohonan|ktun.*permohonan|permohonan[\s_-]*\d{5,7}', 'formulir', None),
    
    # Proteksi
    (r'(?i)program[\s_-]*proteksi|proteksi[\s_-]*radiasi|ppkr|keselamatan[\s_-]*radiasi', 'proteksi', None),
    
    # Perawatan
    (r'(?i)program[\s_-]*perawatan|perawatan[\s_-]*pesawat|maintenance[\s_-]*program|pemeliharaan', 'perawatan', None),
    
    # Manajemen
    (r'(?i)sistem[\s_-]*manajemen|manajemen[\s_-]*fasilitas|quality[\s_-]*management', 'manajemen', None),
    
    # Teknis
    (r'(?i)dokumen[\s_-]*teknis|rencana[\s_-]*teknis|gedung[\s_-]*penahan|penahan[\s_-]*radiasi|denah[\s_-]*ruang', 'teknis', None),
    
    # Personel - Specific Subtypes
    (r'(?i)surat[\s_-]*keterangan[\s_-]*kerja|skk\b', 'personel', 'Surat Keterangan Kerja'),
    (r'(?i)surat[\s_-]*penunjukan[\s_-]*tugas|sk[\s_-]*penunjukan|pengangkatan.*ppr', 'personel', 'Surat Penunjukan Tugas'),
    (r'(?i)sprint|surat[\s_-]*perintah|surat[\s_-]*tugas', 'personel', 'Surat Perintah'),
    (r'(?i)sertifikat.*(?:kompetensi|ppr|lulus)', 'personel', 'Sertifikat Kompetensi'),
    (r'(?i)sikr\b|surat[\s_-]*izin[\s_-]*kerja', 'personel', 'Surat Izin Kerja'),
    (r'(?i)data[\s_-]*sib|kartu[\s_-]*sib|sib\b|izin[\s_-]*bekerja', 'personel', 'Surat Izin Bekerja (SIB)'),
    (r'(?i)sipr?\b|dr\.?[\s_-]*[a-z]+[\s_-]*sp\.?rad|surat[\s_-]*izin[\s_-]*prakt?ik', 'personel', 'Surat Izin Praktik (SIP)'),
    (r'(?i)evaluasi[\s_-]*dosis|zero[\s_-]*check|zerocheck|zero[\s_-]*cek', 'personel', 'Evaluasi Dosis / Zero Check'),
    
    # TLD / Petugas TLD
    (r'(?i)dosis[\s_-]*awal|laporan[\s_-]*dosis|petugas[\s_-]*tld|tld\b|dosimeter|osl\b', 'tld', None),
    
    # Spesifikasi
    (r'(?i)spesifikasi|brochure|brosur|manual[\s_-]*book|datasheet|data[\s_-]*sheet', 'spesifikasi', None),
    
    # Impor
    (r'(?i)persetujuan[\s_-]*impor|persetujuan[\s_-]*import|izin[\s_-]*impor|izin[\s_-]*import', 'impor', None),
    
    # Kesesuaian
    (r'(?i)uji[\s_-]*kesesuaian|sertifikat[\s_-]*uk|ktun.*uk|lhu\b|resume[\s_-]*bapeten', 'kesesuaian', None),
    
    # Uji Fungsi / Acceptance
    (r'(?i)uji[\s_-]*fungsi|ujifungsi|acceptance[\s_-]*test|accepatance|caf\b|bauf\b|bast\b|service[\s_-]*report|installation.*record|installation.*verification', 'fungsi', None),
    
    # Paparan & Kebocoran
    (r'(?i)kebocoran[\s_-]*tabung|pengukuran[\s_-]*kebocoran|uji[\s_-]*kebocoran', 'kebocoran', None),
    (r'(?i)pengukuran[\s_-]*paparan|paparan[\s_-]*radiasi|upar\b|uji[\s_-]*paparan|survey[\s_-]*radiasi', 'paparan', None),
    
    # Label (unit / tabung / generator / plate)
    (r'(?i)foto[\s_-]*label|label[\s_-]*generator|label[\s_-]*tabung|label[\s_-]*unit|sn[\s_-]*unit|foto[\s_-]*tube|foto[\s_-]*nomor[\s_-]*seri|foto[\s_-]*keseluruhan', 'label', None),
]

# Layer 2: Regex on extracted text content
CONTENT_PATTERNS: list[tuple[str, str, Optional[str]]] = [
    # Formulir
    (r'(?i)FORMULIR\s+PERMOHONAN|BADAN\s+PENGAWAS\s+TENAGA\s+NUKLIR\s+.*PERMOHONAN', 'formulir', None),
    
    # Proteksi
    (r'(?i)PROGRAM\s+PROTEKSI\s+DAN\s+KESELAMATAN\s+RADIASI|PROGRAM\s+PROTEKSI\s+RADIASI', 'proteksi', None),
    
    # Perawatan
    (r'(?i)PROGRAM\s+PERAWATAN\s+PESAWAT|PROGRAM\s+PERAWATAN\s+DAN\s+PEMELIHARAAN', 'perawatan', None),
    
    # Manajemen
    (r'(?i)SISTEM\s+MANAJEMEN\s+FASILITAS|SISTEM\s+MANAJEMEN\s+KESELAMATAN|SISTEM\s+MANAJEMEN\b|ASSURANCE\s+QUALIT|QUALITY\s+SYSTEM|SERTIFIKAT\s+MUTU', 'manajemen', None),
    
    # Teknis
    (r'(?i)DOKUMEN\s+TEKNIS\s+FASILITAS|RENCANA\s+TEKNIS|BANGUNAN\s+GEDUNG\s+PENAHAN|DENAH\s+RUANG\s+RADIOLOGI', 'teknis', None),
    
    # Personel
    (r'(?i)SURAT\s+KETERANGAN\s+KERJA', 'personel', 'Surat Keterangan Kerja'),
    (r'(?i)SURAT\s+PENUNJUKAN\s+TUGAS|SURAT\s+KEPUTUSAN\s+PENUNJUKAN|PENGANGKATAN\s+PETUGAS\s+PROTEKSI', 'personel', 'Surat Penunjukan Tugas'),
    (r'(?i)SURAT\s+PERINTAH', 'personel', 'Surat Perintah'),
    (r'(?i)SERTIFIKAT\s+KOMPETENSI|SERTIFIKAT\s+LULUS\s+UJI\s+KOMPETENSI', 'personel', 'Sertifikat Kompetensi'),
    (r'(?i)SURAT\s+IZIN\s+KERJA|SIKR\b', 'personel', 'Surat Izin Kerja'),
    (r'(?i)SURAT\s+IZIN\s+BEKERJA\s+PETUGAS|SURAT\s+IZIN\s+BEKERJA\s+\(SIB\)|SIB\s+PPR', 'personel', 'Surat Izin Bekerja (SIB)'),
    (r'(?i)SURAT\s+IZIN\s+PRAKTIK|SURAT\s+IZIN\s+PRAKTEK|DOKTER\s+SPESIALIS\s+RADIOLOGI', 'personel', 'Surat Izin Praktik (SIP)'),
    (r'(?i)ZERO\s+CHECK|ZERO\s+CEK|EVALUASI\s+DOSIS|DOSIS\s+RADIASI\s+TLD', 'personel', 'Evaluasi Dosis / Zero Check'),
    
    # TLD
    (r'(?i)NUKLINDOLAB|TLD\s+BETA\s+GAMMA|LENCANA\s+TLD|LENCANA\s+OSL|DOSIS\s+PERORANGAN|LAPORAN\s+DOSIS\s+AWAL|DAFTAR\s+PEMAKAI\s+TLD|PETUGAS\s+TLD', 'tld', None),
    
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


def classify_by_filename(filename: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Match filename pattern against known document rules.

    Returns:
        (category, subtype, reason) or (None, None, None)
    """
    clean_name = Path(filename).name
    for pattern, cat, subtype in NAME_PATTERNS:
        m = re.search(pattern, clean_name)
        if m:
            return cat, subtype, f'Pola nama berkas cocok: {m.group(0)}'
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
    for pattern, cat, subtype in CONTENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return cat, subtype, f'Teks halaman awal cocok: {m.group(0)}'
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
    if file_bytes and len(file_bytes) > 0:
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
        'reason': 'Dokumen belum teridentifikasi otomatis, silakan tentukan kategori',
        'confidence': 0.0
    }

