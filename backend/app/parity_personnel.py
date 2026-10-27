"""Streamlit v46 personnel field-level decision rules; extracted verbatim from uploaded new/app/app.py.

Streamlit UI calls at the end are replaced with return rows.
"""
import re

def _compact_normal_status(value):
    value=str(value or 'REVIEW').upper()
    return {'VALID':'MATCH','AUTO_SELECTED':'MATCH','INCOMPLETE':'MISSING'}.get(value,value) if value in ('MATCH','REVIEW','MISMATCH','MISSING','VALID','AUTO_SELECTED','INCOMPLETE') else 'REVIEW'

def _personnel_evidence_text(expected, text, field, validation_part):
    """Select an OCR quotation; never claim the form's value was extracted from a file."""
    import unicodedata
    if field == 'Masa Berlaku':
        evidence = validation_part.get('evidence')
        return str(evidence).strip() if evidence else '—'
    if field == 'Pengesahan':
        return 'Indikasi pengesahan terdeteksi' if validation_part.get('status') == 'DETECTED' else 'Belum ada bukti pengesahan yang cukup'
    if not text:
        return '—'
    clean = lambda x: re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(x))).strip()
    flat = clean(text)
    target = clean(expected).split(' — ')[0].strip()
    # First try a literal match, which is an actual quote from the document.
    if target:
        literal = re.search(re.escape(target), flat, re.IGNORECASE)
        if literal:
            return flat[literal.start():literal.end()]
    # For names, match only person-like spans and show the source OCR wording.
    if field in ('Nama + Keahlian', 'Nama Petugas Ditugaskan'):
        name = validation_part.get('name') or (validation_part.get('best') or {}).get('name') or target
        name_tokens = re.findall(r'[a-z]{3,}', clean(name).lower())
        lines = [clean(line) for line in text.splitlines() if clean(line)]
        candidates=[]
        for line in lines:
            tokens = re.findall(r'[a-z]{3,}', line.lower())
            overlap = len(set(name_tokens) & set(tokens))
            if overlap >= min(2,len(name_tokens)) and len(line) <= 180:
                candidates.append((overlap/ max(1,len(set(name_tokens))), len(line), line))
        if candidates:
            candidates.sort(key=lambda t: (-t[0],t[1]))
            return candidates[0][2]
    # For address/hospital show a source line only if relevant keywords were found.
    if field in ('Tempat Praktik / Alamat Proyek', 'Alamat Rumah Sakit','Nama Rumah Sakit'):
        keys = [t for t in re.findall(r'[a-z]{4,}', target.lower()) if t not in {'kota','jalan','nomor','rumah','sakit'}]
        lines=[clean(line) for line in text.splitlines() if clean(line)]
        ranked=[]
        for line in lines:
            count = sum(1 for word in set(keys) if word in line.lower())
            if count >= 2 and len(line) <= 230:
                ranked.append((count,len(line),line))
        if ranked:
            ranked.sort(key=lambda x: (-x[0], x[1]))
            return ranked[0][2]
    return '—'

def _personnel_date_status(raw_date):
    """Check parsed expiry date against local date, without fuzzy comparisons."""
    from datetime import date, datetime
    from dateutil import parser as date_parser
    if not raw_date or str(raw_date).strip() in ('-', '—'):
        return 'REVIEW'
    try:
        if isinstance(raw_date, datetime):
            expiry = raw_date.date()
        elif isinstance(raw_date, date):
            expiry = raw_date
        else:
            expiry = date_parser.parse(str(raw_date), dayfirst=not bool(re.match(r'^\d{4}[-/]', str(raw_date)))).date()
        return 'MATCH' if expiry >= date.today() else 'MISMATCH'
    except (ValueError, TypeError, OverflowError):
        return 'REVIEW'

def _personnel_field_status(score, evidence, original_status, *, threshold=90):
    """Accept a field only with documentary evidence and sufficiently strong score.

    Overall candidate ambiguity must not silently manufacture a matching name.
    """
    if not evidence or str(evidence).strip() in ('-', '—'):
        return 'REVIEW'
    if not isinstance(score, (int, float)):
        return _compact_normal_status(original_status)
    if score >= threshold:
        return 'MATCH'
    return 'REVIEW' if score >= 65 else 'MISMATCH'

def _personnel_name_evidence(expected, text):
    """Find a name in document OCR, returning an actual OCR snippet."""
    if not text or not expected:
        return '—'
    import unicodedata
    from difflib import SequenceMatcher
    clean = lambda v: re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(v))).strip()
    expected_clean = clean(expected)
    if not expected_clean or expected_clean in ('-', '—'):
        return '—'
    match = re.search(re.escape(expected_clean), clean(text), re.IGNORECASE)
    if match:
        return match.group(0)
    norm = lambda x: re.sub(r'[^a-z0-9 ]+', ' ', clean(x).lower())
    target_words = [w for w in norm(expected_clean).split() if len(w) > 2 and w not in ('dr','sp','rad')]
    if not target_words:
        return '—'
    best = (0.0, '—')
    for raw_line in text.splitlines():
        line = clean(raw_line)
        if not line or len(line) > 150:
            continue
        line_words = norm(line).split()
        if not line_words:
            continue
        overlap = sum(any(SequenceMatcher(None,w,c).ratio() >= .84 for c in line_words) for w in target_words)
        score = overlap/len(target_words)
        if len(target_words)==1 and score>=.90 and not re.search(r'(?i)\b(?:alamat|nomor\s+seri|sertifikat\s+nomor)\b',line):
            return line
        if score > best[0]:
            best=(score,line)
    return best[1] if best[0] >= (.90 if len(target_words)==1 else .66) else '—'

def _unified_personnel_table(validation, document_type, document_text=''):
    """Field-wise personnel comparison; no fabricated evidence or forced overall VALID."""
    rows=[]
    def add(field, expected, observed, score, status):
        rows.append({'Field': field, 'Formulir': str(expected or '—'),
                     'Dokumen': str(observed or '—'),
                     'Skor': f'{score:.1f}%' if isinstance(score,(float,int)) else '—',
                     'Status': status})

    person = validation.get('employee') or {}
    best = person.get('best') or {}
    if document_type in ('SIP','SIB'):
        expected_name = best.get('name')
        from src.matching.personnel_evidence_v42 import compact_person_quote
        observed_name = compact_person_quote(document_text,expected_name) or _personnel_name_evidence(expected_name, document_text)
        ns = best.get('name_score')
        add('Nama Petugas', expected_name, observed_name, ns,
            _personnel_field_status(ns, observed_name, person.get('status')))

        expected_expertise = best.get('expertise')
        es = best.get('expertise_score')
        # The matcher knows the expertise similarity, but the UI must show
        # authentic evidence rather than copying the expected value.
        observed_expertise = _personnel_evidence_text(expected_expertise, document_text,
                                                     'Keahlian', person)
        # Recheck source-local evidence. A global fuzzy 100% for the word
        # 'Dokter' is not proof of the specialty 'Radiologi'.
        from src.matching.personnel_evidence_v42 import personnel_role_quote
        role_quote, role_score = personnel_role_quote(document_text,expected_expertise,strict_detail=document_type=='SIB')
        if role_quote:
            observed_expertise,es=role_quote,role_score
        elif observed_expertise in ('—','-'):
            es=None
        add('Keahlian',expected_expertise,observed_expertise,es,
            _personnel_field_status(es,observed_expertise, person.get('status'),threshold=85))

        if document_type == 'SIP':
            place=validation.get('practice_place') or {}
            expected=place.get('expected')
            from src.matching.personnel_evidence_v40 import find_address
            observed,score=find_address(document_text,expected)
            add('Tempat Praktik / Alamat Proyek',expected,observed,score,
                'MATCH' if score is not None and score>=85 else 'REVIEW')

        validity=validation.get('validity') or {}
        exp=validity.get('expiry_date')
        add('Masa Berlaku',exp,validity.get('evidence') or exp,None,
            _personnel_date_status(exp) if validity.get('expiry_status') == 'ACTIVE' else 'MISMATCH' if validity.get('expiry_status')=='EXPIRED' else 'REVIEW')
        if document_type == 'SIP':
            approval=validation.get('approval') or {}
            detected=approval.get('status')=='DETECTED'
            add('Pengesahan','Bukti pengesahan',
                'Indikasi pengesahan ditemukan' if detected else '—',
                100 if detected else None, 'MATCH' if detected else 'REVIEW')

    elif document_type == 'SPRINT':
        assigned=validation.get('assigned_person') or {}
        expected=assigned.get('name')
        observed=_personnel_name_evidence(expected,document_text)
        add('Nama Petugas Ditugaskan',expected,observed,assigned.get('name_score'),
            _personnel_field_status(assigned.get('name_score'),observed,assigned.get('status')))
        for label,key,threshold in [('Nama Rumah Sakit','hospital',82),
                                     ('Alamat Rumah Sakit','address',75)]:
            part=validation.get(key) or {}
            expected=part.get('expected')
            observed=_personnel_evidence_text(expected,document_text,label,part)
            add(label,expected,observed,part.get('score'),
                _personnel_field_status(part.get('score'),observed,part.get('status'),threshold=threshold))
        approval=validation.get('approval') or {}
        detected = approval.get('status') == 'DETECTED' or approval.get('validation_status') == 'MATCH'
        add('Pengesahan','Bukti pengesahan',
            'Indikasi pengesahan ditemukan' if detected else 'Belum ditemukan',
            100 if detected else None, 'MATCH' if detected else 'REVIEW')

    return rows

