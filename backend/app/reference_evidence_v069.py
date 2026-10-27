"""Conservative reference-guided rescue from the *same uploaded document*.

No fabricated values. Reads existing, searchable text only. Strong matches require
an exact bounded identifier and a nearby label appropriate to the field. We never
rewrite a nonempty contradictory observation or the existing equipment matching.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
import re
import unicodedata

EMPTY = {'', '-', '—', '–', 'none', 'null', 'n/a', 'tidak ditemukan'}
FACILITY_GENERIC = {'rumah sakit', 'rs', 'rsud', 'rsu', 'klinik', 'fasilitas kesehatan', 'rumah sakit umum'}
ADDRESS_FIELD = re.compile(r'(?i)alamat|tempat\s+praktik')
FACILITY_FIELD = re.compile(r'(?i)(?:^|:)\s*(?:nama\s+(?:fasilitas|rs|rumah\s+sakit|instansi)|instansi)\b')
SERIAL_UNIT = re.compile(r'(?i)(?:no\.?\s*seri|nomor\s+seri|serial(?:\s+number)?|\bs/?n\b)\s*(?:unit|pesawat|generator)?\s*$')
SERIAL_TUBE = re.compile(r'(?i)(?:no\.?\s*seri|nomor\s+seri|serial(?:\s+number)?|\bs/?n\b)\s*(?:tabung|tube|insersi\s+tabung)\s*$')
UNIT_TYPE = re.compile(r'(?i)(?:tipe|type|model)\s+(?:unit|pesawat)\s*$')
BRAND = re.compile(r'(?i)(?:merek|merk|brand)\s+(?:unit|tabung)\s*$')
PERSON = re.compile(r'(?i)(?:nama\s+)?(?:petugas|dokter|personel|ppr)\b')

LABELS = {
    'serial_unit': re.compile(r'(?i)(?:serial\s*(?:no\.?|number)?|(?:nomor|no\.?)\s*seri(?:al)?(?:\s+(?:unit|pesawat|generator))?|\bs\s*/\s*n\b|\bS/N\b)'),
    'serial_tube': re.compile(r'(?i)(?:serial\s*(?:no\.?|number)?\s*(?:tube|tabung)|(?:nomor|no\.?)\s*seri(?:al)?\s*(?:tabung|tube|insersi)|(?:tube|tabung)\s+(?:serial|s/n))'),
    'unit_type': re.compile(r'(?i)(?:tipe|type|model|equipment\s+(?:model|name))\s*(?:/\s*(?:model|type))?\s*(?:unit|pesawat|generator)?\b'),
    'brand': re.compile(r'(?i)(?:merek|merk|brand|pabrikan)\s*(?:/\s*pabrikan)?\s*(?:unit|tabung)?\b'),
    'facility': re.compile(r'(?i)(?:nama\s+(?:instansi|fasilitas|rumah\s+sakit|RS)|customer(?:\s+name)?|rumah\s+sakit\s*:)\b'),
    'person': re.compile(r'(?i)(?:nama\s+(?:petugas|dokter|personel|ppr|pemegang)|dokter\s*:)\b'),
}


def _norm(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def _empty(value):
    return str(value or '').strip().casefold() in EMPTY


def _kind(field):
    name = re.sub(r'(?i)^\s*alat\s*\d+\s*:\s*', '', str(field or '')).strip()
    if SERIAL_UNIT.fullmatch(name) or re.fullmatch(r'(?i)(?:nomor|no\.?)\s*seri\s*unit', name):
        return 'serial_unit'
    if SERIAL_TUBE.fullmatch(name) or re.fullmatch(r'(?i)(?:nomor|no\.?)\s*seri\s*(?:tabung|insersi\s+tabung)', name):
        return 'serial_tube'
    if UNIT_TYPE.fullmatch(name):
        return 'unit_type'
    if BRAND.fullmatch(name):
        return 'brand'
    if FACILITY_FIELD.search(name):
        return 'facility'
    if PERSON.search(name) and not ADDRESS_FIELD.search(name):
        return 'person'
    return 'other'


def _pdf_text(path: Path, limit=24):
    import fitz
    pages = []
    with fitz.open(str(path)) as doc:
        for idx in range(min(len(doc), limit)):
            text = doc[idx].get_text(sort=True)
            if text.strip():
                pages.append((idx + 1, text))
    return pages


def _docx_text(path: Path):
    from docx import Document
    doc = Document(str(path))
    chunks = [p.text for p in doc.paragraphs]
    for table in doc.tables[:35]:
        for row in table.rows[:100]:
            chunks.append(' | '.join(c.text for c in row.cells))
    return [(None, '\n'.join(chunks))]


def load_pages(path: Path):
    try:
        suffix = path.suffix.lower()
        if suffix == '.pdf':
            return _pdf_text(path)
        if suffix == '.docx':
            return _docx_text(path)
    except (ImportError, OSError, ValueError, RuntimeError):
        return []
    return []


def _expected_model(value):
    text = str(value).strip()
    # Only a textual description in parentheses is removable. Numeric revision
    # (V2), additional numeric model, and serial cannot be discarded.
    m = re.fullmatch(r'(.+?)\s*\(\s*([^()]*)\s*\)', text)
    if m and re.search('[a-zA-Z]', m.group(2)) and not re.search(r'\d', m.group(2)):
        text = m.group(1)
    return text


def _token_match(line, value, *, compact=False):
    value = str(value or '').strip()
    if not value:
        return None
    if compact:
        # Match model/serial across hyphens, whitespace, periods; bounded by
        # other alphanumeric runs to avoid ABC123 matching ABC1234.
        tokens = re.findall(r'[A-Za-z0-9]+', value)
        if not tokens:
            return None
        pat = r'(?<![A-Za-z0-9])' + r'[\s.\-]*'.join(map(re.escape, ''.join(tokens))) + r'(?![A-Za-z0-9])'
    else:
        words = re.findall(r'[\w]+', value, re.UNICODE)
        if not words:
            return None
        pat = r'(?<!\w)' + r'[\s.,;:()\[\]\-/]*'.join(map(re.escape, words)) + r'(?!\w)'
    return re.search(pat, line, re.IGNORECASE)


def _context_ok(kind, lines, i, m):
    # Target must be close to its own field label; prevents accidental mentions
    # in an unrelated device, supplier address, reference list, or contact data.
    neighbors = '\n'.join(lines[max(0, i-2):i+1])
    label = LABELS.get(kind)
    if not label or not label.search(neighbors):
        return False
    if kind == 'serial_unit' and LABELS['serial_tube'].search(lines[i]):
        return False
    if kind == 'serial_unit' and re.search(r'(?i)\b(?:tube|tabung|insersi)\b', '\n'.join(lines[max(0,i-1):i+1])):
        return False
    if kind == 'serial_tube' and re.search(r'(?i)\bserial\s+(?:generator|unit)\b', lines[i]):
        return False
    if kind == 'facility' and re.fullmatch(r'(?:rumah\s+sakit|klinik|rsud|rsj)(?:\s+umum)?', _norm(m.group(0))):
        return False
    return True


def _distinct_expected(kind, value):
    v = str(value or '').strip()
    if _empty(v) or len(v) > 160:
        return None
    if kind in {'serial_unit', 'serial_tube'}:
        compact = ''.join(re.findall(r'[a-z0-9]+', v.casefold()))
        # >5 alphanumerics, with digit, not a simple year/date/value.
        if len(compact) < 6 or not any(c.isdigit() for c in compact):
            return None
        return v
    if kind == 'unit_type':
        core = _expected_model(v)
        compact = ''.join(re.findall(r'[a-z0-9]+', core.casefold()))
        if len(compact) < 5 or not re.search(r'[a-z]', compact) or not re.search(r'\d', compact):
            return None
        return core
    if kind in {'facility','person','brand'}:
        if kind == 'facility' and _norm(v) in FACILITY_GENERIC:
            return None
        if len(_norm(v)) < 7:
            return None
        return v
    # Conservative generic fallback: only long, distinctive IDs, never generic
    # field expectations ('Bukti pengesahan', dates, 'Kompeten', etc.).
    compact = ''.join(re.findall(r'[a-z0-9]+', v.casefold()))
    if len(compact) >= 9 and bool(re.search(r'\d', compact)) and bool(re.search(r'[a-z]',compact)):
        return v
    # Other missing fields can receive a source-page *clue*, never an auto-MATCH.
    # Exclude boilerplate form instructions or generic checkboxes / approval text.
    excluded = ('bukti pengesahan', 'subbab uji', 'indikasi pengesahan',
                'tersedia', 'ditemukan', 'lulus', 'kompeten', 'keberadaan halaman',
                'pemilihan peralatan', 'nomor dokumen')
    words = re.findall(r'[a-z]+', v.casefold())
    if len(v) >= 12 and len(words) >= 2 and not any(x in v.casefold() for x in excluded):
        return v
    return None


def find_evidence(pages, expected, kind):
    query = _distinct_expected(kind, expected)
    if query is None:
        return None
    hits = []
    for page, text in pages:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            match = _token_match(line, query, compact=kind in {'serial_unit','serial_tube','unit_type','other'})
            if not match:
                continue
            # A same-page value is not sufficient: contextual label mandatory
            # for automatic match. Otherwise surface a review-only clue.
            strong = _context_ok(kind, lines, i, match)
            snippet = ' '.join(lines[max(0,i-1):min(len(lines),i+2)])[:350]
            hits.append({'page':page,'value':match.group(0),'quote':snippet,
                         'strong':strong,'kind':kind})
    if not hits:
        return None
    strong = [x for x in hits if x['strong']]
    if strong:
        # Multiple identical values in the same correct context can be okay;
        # document-category ambiguity is still left to the evaluator.
        return strong[0]
    return hits[0]


def _address_score(expected, observed, existing):
    from difflib import SequenceMatcher
    from .address_equivalence_v068 import canonical_text
    if isinstance(existing, (int, float)) and not isinstance(existing, bool):
        return round(max(0., min(100., float(existing))), 1)
    a, b = canonical_text(expected), canonical_text(observed)
    if not a or not b:
        return None
    # Character similarity is a diagnostic score, not a proof of co-location.
    return round(100. * SequenceMatcher(None, a, b).ratio(), 1)


def improve_rows(rows, document_path):
    """Modify only incomplete rows and numeric display of known addresses.

    No changes to explicit nonempty MISMATCH values, no fabricated evidence,
    no extra OCR load. This must run after v065 identity and v068 unit logic.
    """
    if not isinstance(rows, list):
        return rows
    missing = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        field = str(row.get('field') or '')
        expected, observed = row.get('expected'), row.get('observed')
        if ADDRESS_FIELD.search(field):
            if not _empty(expected) and not _empty(observed):
                row['score'] = _address_score(expected, observed, row.get('score'))
                if row['status'] != 'MATCH' and row['score'] is not None:
                    reason = str(row.get('note') or '').strip()
                    row['note'] = (reason + ' | Skor hanya kemiripan teks; komponen alamat perlu diverifikasi.').strip(' |')[:300]
            continue
        weak_facility = FACILITY_FIELD.search(field) and _norm(observed) in FACILITY_GENERIC and _norm(expected) not in FACILITY_GENERIC
        if weak_facility:
            row['status'] = 'REVIEW'
            row['score'] = None
            row['note'] = 'Nama fasilitas yang terbaca terlalu umum; identitas spesifik belum terbukti'
            # Try source-supported evidence below, not a form-derived guess.
        if not _empty(observed) and not weak_facility:
            continue
        if row.get('status') not in ('REVIEW','MISSING','MATCH','MISMATCH'):
            continue
        kind = _kind(field)
        if _distinct_expected(kind, expected) is not None:
            if row.get('status') == 'MATCH':
                row['status'] = 'REVIEW'
                row['score'] = None
                row['note'] = 'Tidak ada nilai dokumen; status MATCH tidak dapat dibuktikan'
            missing.append((row, kind))
    if not missing:
        return rows
    pages = load_pages(Path(document_path))
    if not pages:
        return rows
    for row, kind in missing:
        hit = find_evidence(pages, row.get('expected'), kind)
        if hit is None:
            continue
        row['page'] = hit['page'] if isinstance(hit['page'],int) else row.get('page')
        row['quote'] = hit['quote']
        if hit['strong'] and kind in {'serial_unit','serial_tube','unit_type','facility','person'}:
            row['observed'] = hit['value']
            row['score'] = 100.0
            row['status'] = 'MATCH'
            row['note'] = 'Fallback berbasis nilai acuan; ditemukan dengan konteks field pada dokumen asli. Verifikasi bukti sumber.'
        else:
            # Only possible reference occurrence, not established field identity.
            row['note'] = 'Nilai acuan muncul di sumber, tetapi konteks field belum cukup; verifikasi pada halaman bukti.'
    return rows
