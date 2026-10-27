"""Last-mile guard against generic/truncated facility false matches.

Only checks existing evidence in each row. It NEVER fills an absent observed value
with the application/form reference, and does not perform OCR or read private files.
Kept separate from the original extraction and v065/v068/v069 logic.
"""
from __future__ import annotations
import re
import unicodedata

_NAME_FIELD = re.compile(r'(?i)^\s*(?:nama\s+(?:fasilitas(?:\s+kesehatan)?|(?:rumah\s+sakit)|rs|klinik|instansi)|nama\s*/\s*alamat\s+(?:fasilitas|rs)|instansi)\s*$')
_EMPTY = {'', '-', '—', '–', 'n/a', 'none', 'null', 'tidak ditemukan'}
_GENERIC = {'rumah', 'sakit', 'jiwa', 'umum', 'daerah', 'klinik', 'hospital',
            'rs', 'rsj', 'rsud', 'rsu', 'fasilitas', 'kesehatan', 'instansi',
            'kota', 'kabupaten', 'provinsi', 'regional'}


def _tokens(value):
    s = unicodedata.normalize('NFKC', str(value or '')).casefold()
    s = re.sub(r'\b(?:rsj)\s*\.?\s*', ' rumah sakit jiwa ', s)
    s = re.sub(r'\b(?:rsud)\s*\.?\s*', ' rumah sakit umum daerah ', s)
    s = re.sub(r'\b(?:rsu)\s*\.?\s*', ' rumah sakit umum ', s)
    s = re.sub(r'\brs\s*\.\s*', ' rumah sakit ', s)
    s = re.sub(r'\brs\b', ' rumah sakit ', s)
    return tuple(re.findall(r'[a-z0-9]+', s))


def _distinct(value):
    return [word for word in _tokens(value) if word not in _GENERIC]


def _field(row):
    return bool(_NAME_FIELD.fullmatch(str(row.get('field') or '').strip()))


def _valid_strong_partial(reference, value):
    """For existing MATCH only: accept distinctive brand/name with locality omitted.

    Examples: 'Klinik Insan Utama Balikpapan' vs 'Klinik Insan Utama'.
    Do not accept 'Rumah Sakit Jiwa Aceh' vs 'Rumah Sakit Jiwa', or
    'Rumah Sakit Jiwa Aceh' vs 'RS Aceh' as complete identities.
    """
    a, b = set(_distinct(reference)), set(_distinct(value))
    if len(b) < 2 or not b.issubset(a):
        return False
    # Require consistent facility type if both contain an explicit type.
    left, right = _tokens(reference), _tokens(value)
    if 'klinik' in left and 'klinik' not in right:
        return False
    if 'klinik' in right and 'klinik' not in left:
        return False
    return True


def guard_rows(rows):
    """Check every facility row at the final post-processing boundary.

    Preserve source value unchanged for audit; downgrade unjustified MATCH to
    REVIEW and remove misleading scores. Existing MISMATCH and ordinary REVIEW
    with specific names are not overwritten. Exact expanded abbreviations can
    be recognized as MATCH when source text actually contains the name.
    """
    if not isinstance(rows, list):
        return rows
    for row in rows:
        if not isinstance(row, dict) or not _field(row):
            continue
        expected = str(row.get('expected') or '').strip()
        observed = str(row.get('observed') or '').strip()
        if not expected or expected.casefold() in _EMPTY:
            continue
        raw_status = str(row.get('status') or '').upper()
        if raw_status not in ('MATCH', 'REVIEW', 'MISMATCH', 'MISSING'):
            continue
        evidence = tuple(_tokens(observed))
        identity = tuple(_tokens(expected))
        if not evidence or observed.casefold() in _EMPTY:
            if raw_status == 'MATCH':
                row['status'], row['score'] = 'REVIEW', None
                row['note'] = 'Nama fasilitas sumber tidak ditemukan; tidak dapat dinyatakan cocok.'
            continue
        # Distinctive identity must survive extraction, not just generic class.
        distinctive = _distinct(observed)
        if not distinctive:
            row['status'], row['score'] = 'REVIEW', None
            row['note'] = 'Yang terbaca hanya jenis fasilitas, bukan nama spesifiknya; perlu verifikasi dokumen.'
            continue
        if identity == evidence and _distinct(expected):
            # Safe exact-name match after standard abbreviation expansion.
            if raw_status == 'REVIEW':
                row['status'], row['score'] = 'MATCH', 100.0
                row['note'] = 'Nama fasilitas identik setelah normalisasi singkatan.'
            continue
        if raw_status != 'MATCH':
            continue
        if not _valid_strong_partial(expected, observed):
            row['status'], row['score'] = 'REVIEW', None
            row['note'] = 'Nama fasilitas belum membuktikan identitas lengkap; bandingkan nama spesifik pada sumber.'
    return rows
