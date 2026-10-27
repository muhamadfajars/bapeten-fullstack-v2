"""Narrow identity rescue for v070: source-backed complete facility header detection.

The original category extractors remain unchanged. This last-mile layer uses
only text from the SAME uploaded document, and never creates an answer from
an application-form field. No OCR, no extra worker and no network access.
"""
from __future__ import annotations
import re
from pathlib import Path

from .facility_guard_v070 import _tokens, _distinct, guard_rows
from .identity_policy_v065 import clean_evidence, is_empty, address_decision
from .address_equivalence_v068 import canonical_text, house_number

NAME_FIELD = re.compile(r'(?i)^\s*(?:nama\s+(?:fasilitas(?:\s+kesehatan)?|rumah\s+sakit|rs|klinik|instansi)|nama\s*/\s*alamat\s+(?:fasilitas|rs)|instansi)\s*$')
ADDRESS_FIELD = re.compile(r'(?i)(?:alamat\s+(?:fasilitas|proyek)|tempat\s+praktik\s*/\s*alamat\s+proyek)')
HEAD = re.compile(r'(?i)^\s*(?:rumah\s+sakit|rsj|rsud|rsu|rs\.?\s|klinik|puskesmas|balai\s+kesehatan|hospital)\b')
LABEL = re.compile(r'(?i)^\s*(?:nama\s+(?:instansi|fasilitas|rumah\s+sakit|rs|klinik)|customer\s*name|customers|nama\s+rumah\s+sakit)\s*[:|\-]?\s*')
STREET = re.compile(r'(?i)\b(?:jl\.?|jalan|jln\.?|gang|komplek?s?)\s+')
STOP = re.compile(r'(?i)^\s*(?:jl\.?|jalan|alamat|address|nomor|no\.?|tanggal|tgl|telepon|telp|fax|email|www|http|kode\s+pos|tahun\s+\d|bab\b|halaman|revisi|profesi|nama\s+petugas|merek|merk|tipe|type|serial|no\s+seri|untuk\b|program\b|data\b|pendahuluan\b)')
SENTENCE = re.compile(r'(?i)\b(?:adalah|dengan|menyatakan|yang|tersebut|memiliki|berikut|telah|pada|terdiri|milik)\b')


def _clean_line(value):
    return ' '.join(str(value or '').strip().split())


def _words_match(ref, cand):
    """Accept only explicit distinctive names, or safe RSJ/RS/RSUD abbreviation."""
    ref_tokens, cand_tokens = tuple(_tokens(ref)), tuple(_tokens(cand))
    if not ref_tokens or not cand_tokens or not _distinct(ref):
        return False
    # Full expanded identity only (e.g., RSJ Aceh -> Rumah Sakit Jiwa Aceh).
    return ref_tokens == cand_tokens


def _is_identity_header(value):
    value = _clean_line(value)
    if not value or len(value) > 110 or len(value.split()) > 12:
        return False
    if not HEAD.match(value) or STREET.search(value) or SENTENCE.search(value):
        return False
    if re.search(r'(?i)\b(?:program|dokumen|penyelenggaraan|perizinan|instalasi|laporan|pemeriksaan|pemanfaatan|protokol|uji)\b', value):
        return False
    return len(_distinct(value)) >= 1


def _page_lines(text):
    return [_clean_line(line) for line in str(text).splitlines() if _clean_line(line)]


def _candidates(pages):
    """Only labeled values or prominent facility headings; never free-text mentions.

    Provide name provenance (page number, verbatim quote). Header candidates are
    restricted to beginning of page, except directly labeled name in data table.
    """
    seen = set()
    for page, text in pages:
        lines = _page_lines(text)
        for i, line in enumerate(lines[:160]):
            match = LABEL.match(line)
            if match:
                remainder = line[match.end():].strip(' :|-')
                # A label and value may be separated by a colon on distinct rows.
                parts = [remainder] if remainder else []
                if i + 1 < len(lines) and len(parts) < 1:
                    parts.append(lines[i+1])
                # The distinct name may wrap to next text line within same block.
                if parts and i + 1 < len(lines) and not STOP.match(lines[i+1]) and not SENTENCE.search(lines[i+1]):
                    if len(_distinct(' '.join(parts))) == 0 and len(lines[i+1]) < 65:
                        parts.append(lines[i+1])
                candidate = ' '.join(parts)
                if _is_identity_header(candidate):
                    key=(page,candidate.casefold())
                    if key not in seen:
                        seen.add(key)
                        yield {'value':candidate, 'page':page, 'quote':line[:180], 'source':'labeled_name'}
            # Full hospital/clinic heading at top of page; avoid incidental
            # references or a different institution deeper in document.
            if i > 35 or not HEAD.match(line):
                continue
            options=[line]
            if i+1 < len(lines) and len(line.split()) <= 4:
                tail = lines[i+1]
                if (not STOP.match(tail) and not HEAD.match(tail) and not STREET.search(tail)
                    and not SENTENCE.search(tail) and len(tail) < 65
                    and len(tail.split()) <= 5 and not re.search(r'\d',tail)):
                    options.append(line+' '+tail)
            for candidate in options:
                if _is_identity_header(candidate):
                    key=(page,candidate.casefold())
                    if key not in seen:
                        seen.add(key)
                        yield {'value':candidate,'page':page,'quote':candidate[:180], 'source':'facility_heading'}


def _read_document_pages(path):
    """Use existing text layer; absent/invalid text is not treated as a match."""
    path=Path(path)
    try:
        if path.suffix.lower()=='.pdf':
            import fitz
            with fitz.open(str(path)) as pdf:
                return [(p+1, pdf[p].get_text('text',sort=True)) for p in range(min(len(pdf),8))]
        if path.suffix.lower()=='.docx':
            from docx import Document
            doc=Document(str(path))
            lines=[p.text for p in doc.paragraphs]
            for table in doc.tables[:30]:
                for r in table.rows[:100]:
                    lines.append(' | '.join(c.text for c in r.cells))
            return [(None,'\n'.join(lines))]
    except (OSError,ValueError,ImportError,RuntimeError):
        pass
    return []


def _is_weak_name(row):
    expected, observed = str(row.get('expected') or ''), str(row.get('observed') or '')
    if is_empty(observed):
        return True
    left = set(_distinct(expected)); right = set(_distinct(observed))
    if not right or not left:
        return True
    # Existing distinctive but incomplete names may also need a *stronger*
    # verified full-name header. Preserve explicit conflicting names entirely.
    return right.issubset(left) and tuple(_tokens(expected)) != tuple(_tokens(observed))


def _score_address(expected,observed):
    from difflib import SequenceMatcher
    left,right=canonical_text(expected),canonical_text(observed)
    if not left or not right: return None
    return round(100*SequenceMatcher(None,left,right).ratio(),1)


def finalize_identity(rows, document_path):
    """Uniform end-stage facility/address policy applied to all categories.

    Rescue from EXACT, prominent source name only when weak; validate afterward.
    Do not change existing specific MISMATCH values, brand/model/serial rows, or
    explicit address status. Keep a diagnostic address score even when REVIEW.
    """
    if not isinstance(rows,list):
        return rows
    guard_rows(rows)
    weak=[r for r in rows if isinstance(r,dict) and NAME_FIELD.fullmatch(str(r.get('field') or ''))
          and _is_weak_name(r) and str(r.get('status') or '').upper() != 'MISMATCH']
    if weak:
        pages=_read_document_pages(document_path)
        candidates=list(_candidates(pages)) if pages else []
        for row in weak:
            ref=row.get('expected')
            matches=[c for c in candidates if _words_match(ref,c['value'])]
            if not matches:continue
            # An explicitly labeled DIFFERENT facility on this same document
            # defeats a rescue based on an incidental cover/header mention.
            conflicting_label = any(c['source']=='labeled_name'
                                    and _distinct(c['value'])
                                    and not _words_match(ref,c['value'])
                                    for c in candidates)
            if conflicting_label:continue
            # Full source name has to be witnessed in a facility name heading or
            # explicit field label. Reference merely selects, never constructs.
            cand=min(matches, key=lambda c:(c['page'] if isinstance(c['page'],int) else 1,
                                            0 if c['source']=='labeled_name' else 1))
            row['observed']=cand['value']
            row['status']='MATCH'
            row['score']=100.0
            if isinstance(cand['page'],int):row['page']=cand['page']
            row['quote']=cand['quote']
            row['note']='Nama fasilitas lengkap ditemukan pada '+('label identitas' if cand['source']=='labeled_name' else 'judul/kop dokumen')+'; verifikasi pada halaman sumber.'
    # All address categories share the same score normalizer. Scores do not
    # themselves promote a REVIEW to MATCH. Preserve v068 identity safeguards.
    for row in rows:
        if not isinstance(row,dict) or not ADDRESS_FIELD.search(str(row.get('field') or '')):
            continue
        a,b=row.get('expected'),row.get('observed')
        if is_empty(a) or is_empty(b):
            row['score']=None
            continue
        # v069 already reports the canonical diagnostic score when available.
        # Compute a score only for rows still lacking it: do not overwrite
        # evidence-derived MATCH scores (e.g. normalized house numbers).
        if not isinstance(row.get('score'),(int,float)) or isinstance(row.get('score'),bool):
            score=_score_address(a,b)
            if score is not None:
                row['score']=score
        # Explicit house-number conflicts are not normalization differences;
        # never allow a lingering MATCH in that case.
        x,y=house_number(a),house_number(b)
        if x and y and x != y and row.get('status')=='MATCH':
            row['status']='REVIEW'
            row['note']='Nomor bangunan berbeda dalam dua bukti; perlu pemeriksaan dokumen asli.'
    guard_rows(rows)
    return rows
