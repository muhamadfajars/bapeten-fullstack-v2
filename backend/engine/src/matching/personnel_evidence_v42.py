"""Context-aware comparison helpers for personnel documents (v42).

All matches require source evidence. These functions cannot authenticate signatures,
confirm licensing with an issuer, or infer missing facts from the application.
"""
import re
import unicodedata
from rapidfuzz import fuzz
from src.matching.personnel_evidence_v40 import (
    norm, street_key, house_number, match_street, _facility_score,
    find_practice_facility, find_evidence, find_role_phrase,
)

SPACE = re.compile(r'\s+')
ADDRESS_STOP = re.compile(
    r'(?i)(?:\s*\b(?:email|e-?mail|tanggal\s+(?:evaluasi|pelaporan|penerimaan|pengujian|uji)|nomor\s+(?:str|tld|registrasi|sertifikat)|masa\s+berlaku|periode\s+pemakaian|untuk\s+rencana|catatan|penguji|penyelia|pengesahan|halaman\s*\d+\s*dari|revisi|telp|fax)\b\s*:?|(?<=[a-z])alamat\s*:)'
)
ADDRESS_LABEL = re.compile(r'(?i)\b(?:alamat\s+(?:prakt[ie]k|fasilitas|rumah\s+sakit|proyek)|tempat\s+prakt[ie]k|alamat\s*:)\s*:?')
STREET = re.compile(r'(?i)(?<!\w)(?:j(?:l|ln)\.?|jalan)\s*')
WORK_CLAUSE = re.compile(r'(?i)\b(?:untuk\s+menjalankan\s+pekerjaan|untuk\s+melaksanakan\s+tugas|di(?:tugaskan)?\s+(?:sebagai|pada))\b')
ROLE_CLASS = re.compile(r'(?i)\b(?:petugas\s+proteksi\s+radiasi|\bppr\b|radiograf\w*|dokter\s+spesialis|radiolog\w*)\b')


def source_lines(text):
    return [SPACE.sub(' ', x).strip() for x in str(text or '').splitlines() if x.strip()]


def clean_address(s):
    """Preserve original written components; remove only clearly unrelated fields."""
    s = SPACE.sub(' ', str(s or '')).strip()
    # Remove an adjacent repeated OCR label, e.g. 'BalikpapanAlamat : Tengah'.
    s = re.sub(r'(?i)(?<=[A-Za-z])\s*(?:alamat|email|tanggal\s+evaluasi)\s*:', ' ', s).strip()
    s = ADDRESS_STOP.split(s, maxsplit=1)[0]
    s = re.sub(r'(?i)\b(?:halaman\s+\d+\s+dari\s+\d+|\bpage\s+\d+\s+of\s+\d+)\b', '', s)
    return s.strip(' -:,.')[:240]


def _street_comparable(expected, actual):
    e, a = street_key(expected), street_key(actual)
    if not (e and a):
        return None
    et = [w for w in e.split() if len(w)>2 and w not in {'jalan','nomor','no'}]
    at = [w for w in a.split() if len(w)>2 and w not in {'jalan','nomor','no'}]
    if not et or not at:
        return None
    covered = sum(any(fuzz.ratio(w, t) >= 84 for t in at) for w in et)/len(et)
    if covered < .55:
        return round(100*covered,1)
    en, an = house_number(expected), house_number(actual)
    if en and an and en != an:
        return 0.0
    # Never collapse explicitly different administrative destinations into a
    # street-only MATCH, even when the street names and house numbers agree.
    def labelled_locality(value, label):
        m=re.search(r'(?i)\b'+label+r'\s+([a-zA-Z]+)\b',str(value))
        return norm(m.group(1)) if m else None
    for label in ('kota',r'kab(?:upaten)?\.?','provinsi'):
        left,right=labelled_locality(expected,label),labelled_locality(actual,label)
        if left and right and fuzz.token_set_ratio(left,right)<65:
            return 0.0
    score = .55*fuzz.ratio(e,a) + 45*covered
    if en and an and en==an:
        score = max(score, 90.)
    if covered>=.74 and (not en or not an or en==an):
        score = max(score, 86.)
    # 'Saili' is not enough alone for equivalence: require several road tokens.
    if len(et)<2 and not(en and an and en==an):
        score=min(score,85.)
    if en and not an:
        score=min(score,92.)
    return round(min(100.,score),1)


def address_evidence(text, expected, *, workplace=False):
    """Return (source quote, comparable score, decision).

    The best *source address* is found first. A different place is never
    hidden just because it does not match the expected street.
    """
    lines=source_lines(text)
    choices=[]
    for i,line in enumerate(lines):
        if workplace and not (STREET.search(line) and (WORK_CLAUSE.search(line) or i and WORK_CLAUSE.search(lines[i-1]))):
            continue
        label=ADDRESS_LABEL.search(line)
        start=(label.end() if label else 0)
        if not (label or STREET.search(line)):
            continue
        parts=[line[start:]]
        for nxt in lines[i+1:i+4]:
            if re.match(r'(?i)^(?:nama\b|alamat\b|email\b|nomor\s+str|tanggal\b|berlaku\b|pengesahan\b|catatan\b|untuk\s+rencana)',nxt):
                break
            if len(' '.join(parts+[nxt]))>295:
                break
            parts.append(nxt)
        blob=' '.join(parts)
        hit=STREET.search(blob)
        if hit is None:
            continue
        address=clean_address(blob[hit.start():])
        if not address or len(address)<8:
            continue
        score=_street_comparable(expected,address)
        if score is None:
            continue
        n=house_number(address)
        priority=(5 if workplace else 0)+(3 if label else 0)
        # Prefer a full clean address over OCR noise. The city/province need
        # not be present on both sides, but must not be inferred.
        rank=(priority,score, int(n is not None), min(len(address.split()),24), -len(address))
        choices.append((rank,address,score))
    if not choices:
        return None,None,'REVIEW'
    choices.sort(key=lambda x:x[0],reverse=True)
    _,addr,score=choices[0]
    return addr,score,('MATCH' if score>=85 else 'REVIEW' if score>=65 else 'MISMATCH')


def workplace_address(text, expected):
    lines=source_lines(text)
    snippets=[]
    for i,line in enumerate(lines):
        if WORK_CLAUSE.search(line):
            snippets.append('\n'.join(lines[i:i+3]))
    if snippets:
        for snippet in snippets:
            quote,score,status=address_evidence(snippet,expected,workplace=False)
            if quote:
                return quote,score,status
    # No trustworthy workplace location. Never use the employee's HOME address
    # labelled simply 'Alamat' as the address of the hospital.
    return None,None,'REVIEW'


def _role_family(text):
    v=norm(text)
    if 'petugas proteksi radiasi' in v or re.search(r'\bppr\b',v):return 'ppr'
    if 'radiografer' in v or 'radiographer' in v:return 'radiografer'
    if 'dokter spesialis radiologi' in v or 'sp rad' in v:return 'radiologi'
    if 'dokter spesialis' in v:return 'dokter_spesialis'
    return None


def explicit_assignment_role(text):
    """The assigned function, not an earlier civil-service rank/job title."""
    lines=source_lines(text)
    for i,line in enumerate(lines):
        blob=' '.join(lines[i:i+3])[:450]
        for m in re.finditer(r'(?i)\bsebagai\s+(petugas\s+proteksi\s+radiasi|\bppr\b|radiografer\b|dokter\s+spesialis\s+radiologi\b)',blob):
            prefix=blob[:m.start()]
            if re.search(r'(?i)\b(?:tugas|menugaskan|ditunjuk|menetapkan|pengangkatan|kepada|melaksanakan)\b',prefix):
                return m.group(1)
        m=re.search(r'(?i)\b(?:menetapkan|pengangkatan)\b.{0,220}?\bsebagai\s+(petugas\s+proteksi\s+radiasi|\bppr\b|radiografer\b)',blob)
        if m:return m.group(1)
    return None


def personnel_role_quote(text, expected, *, assignment=False, strict_detail=False):
    if assignment:
        role=explicit_assignment_role(text)
        if role:return role,100.
    lines=source_lines(text)
    family=_role_family(expected)
    scored=[]
    for i,line in enumerate(lines):
        # SIB title or certificate 'PPR Radiologi Diagnostik dan atau' wraps.
        if not ROLE_CLASS.search(line):continue
        if len(line)>180:continue
        quote=line
        if re.search(r'(?i)(?:\bdan\s+atau\s*$|\bdan\s*$|\batau\s*$)',line) and i+1<len(lines):
            continuation=lines[i+1]
            if re.match(r'(?i)^\s*(?:intervensional\b|diagnostik\b|radiologi\b)',continuation):
                quote+=' '+continuation
        if family=='ppr' and _role_family(quote)!='ppr':continue
        if family=='radiografer' and _role_family(quote)!='radiografer':continue
        if family=='radiologi' and _role_family(quote) not in ('radiologi','dokter_spesialis'):continue
        # Strip optional printed document headers and prefixes, never invent
        # words missing from the source.
        m=re.search(r'(?i)(petugas\s+proteksi\s+radiasi|\bppr\b|radiografer|dokter\s+spesialis(?:\s+radiologi)?)\b',quote)
        if m:quote=quote[m.start():]
        quote=re.split(r'(?i)\s+\b(?:nomor\s+sertifikat|nomor\s+sib|nama\s*[:]|untuk\s+melaksanakan)\b',quote)[0].strip()
        score=100 if (_role_family(quote)==family or (family=='radiologi' and _role_family(quote)=='radiologi')) else 67
        if family=='radiologi' and _role_family(quote)=='dokter_spesialis':score=67
        if strict_detail and family=='ppr':
            required=[w for w in ('diagnostik','intervensional') if w in norm(expected).split()]
            if any(w not in norm(quote).split() for w in required):
                score=min(score,75)
        scored.append((score, min(len(quote.split()),12), -len(quote), quote))
    if not scored:
        # Surface unverified role information but do not give MATCH.
        return find_role_phrase(text),None
    scored.sort(reverse=True)
    score,_,_,quote=scored[0]
    if family=='ppr' and _role_family(quote)=='ppr' and not strict_detail:score=100
    return quote,score


def choose_person_reference(text, persons, *, role_hint=None):
    """Disambiguate duplicate names using document's actual designated role."""
    rows=[]
    hint=_role_family(role_hint) if role_hint else None
    for p in persons:
        name=p.get('nama') or p.get('name')
        if not name:continue
        role=p.get('keahlian') or p.get('keahlian_klasifikasi') or p.get('profesi') or p.get('jabatan')
        quote,score=find_evidence(text,name,'person')
        if quote is None:continue
        family=_role_family(role)
        merit=round(float(score),1)
        if hint:
            merit+=25 if family==hint else -25
        rows.append((merit,score,name,role,quote))
    if not rows:return None
    rows.sort(reverse=True)
    _,score,name,role,quote=rows[0]
    return (name,quote,score,role)


def compact_person_quote(text, expected):
    """Find a short source excerpt, not an entire regulation sentence."""
    if not expected:return None
    lines=source_lines(text)
    value=norm(expected)
    tokens=[t for t in value.split() if t not in {'dr','dokter','sp','rad','a','md','kes'} and len(t)>2]
    if not tokens:return None
    matches=[]
    for i,line in enumerate(lines):
        hay=norm(line)
        if not all(t in hay.split() for t in tokens[:min(2,len(tokens))]):continue
        if len(line)>260:continue
        candidate=line
        # Name labels and the top portion of a permit can be used directly.
        label=re.search(r'(?i)\b(?:nama\s*(?:lengkap)?\s*[:]|nama\s*/\s*name\s*[:]|izin\s+prakt[ie]k\s+kepada\s*[:])',line)
        if label:candidate=line[label.end():].strip()
        # Embedded full name in a long sentence; capture a conservative name
        # span around an actually present title and the expected last token.
        if len(candidate)>100:
            needle=tokens[0]
            mt=re.search(r'(?i)\b(?:dr\.?\s+)?'+re.escape(needle)+r'\b',candidate)
            if mt:
                end=re.search(r'(?i)\b'+re.escape(tokens[-1])+r'\b',candidate[mt.start():])
                if end:
                    right=mt.start()+end.end()
                    tail=candidate[right:right+30]
                    suf=re.match(r'(?i)[\s,]*(?:M\.?\s*Kes\.?|Sp\.?\s*Rad\.?|A\.?\s*Md\.?\s*Rad\.?)',tail)
                    candidate=candidate[mt.start():right+(suf.end() if suf else 0)]
                else:candidate=candidate[mt.start():mt.start()+65]
        candidate=candidate.strip(' :;,')
        matches.append((int(bool(label)),int(len(candidate)<75),-len(candidate),candidate))
    if not matches:return None
    matches.sort(reverse=True)
    return matches[0][3]


def monitored_dose_person(text, expected):
    """Require a row in a dosimetry table and return NAME ONLY (not dose/ID)."""
    if not text or not expected:return None,None
    lines=source_lines(text)
    header=re.compile(r'(?i)(?:nama\s+(?:pengguna\s+lencana|pekerja|petugas|personel)|dosis\s+(?:ekuivalen|badan|kulit|tara)|\btld\b|\blencana\b|nomor\s+barcode|periode\s+pemakaian|\bno\.?\s*urut\b|nama\s+posisi)')
    footer=re.compile(r'(?i)^\s*(?:catatan\b|dibuat\s+oleh\b|disahkan\s+oleh\b|disetujui\s+oleh\b|pengesahan\s*[:]|penguji\s*:|penyelia\s*:)')
    actual_tokens=[t for t in norm(expected).split() if len(t)>2 and t not in {'dr','dokter','sp','rad','a','md','kes'}]
    if not actual_tokens:return None,None
    header_positions=[i for i,line in enumerate(lines) if header.search(line)]
    segments=[]
    if not header_positions:
        # Several OCR/PDF engines split 'No. Lencana | Nama | Posisi' into
        # separate cells/lines; an isolated 'Nama' is a table header only when
        # it is surrounded by dosimetry terminology in a short window.
        for i,line in enumerate(lines):
            if re.fullmatch(r'(?i)nama\s*',line):
                nearby=' '.join(lines[max(i-5,0):min(i+5,len(lines))])
                if re.search(r'(?i)\b(?:lencana|dosis|pemakaian|ur[uo]t|posisi)\b',nearby):
                    header_positions.append(i)
    if header_positions:
        for pos in header_positions:
            end=next((j for j in range(pos+1,len(lines)) if footer.search(lines[j])),len(lines))
            if re.search(r'(?i)^\s*nama\s+(?:petugas|pekerja|personel)\s*:',lines[pos]):
                segments.append(lines[pos])
            segments.extend(lines[pos+1:end])
    else:
        # OCR-only documents without table headers must still have an explicit
        # named-person label or numeric row with dose/ID evidence.
        segments=[line for line in lines if re.search(r'(?i)(?:^\s*\d+[.\s]|\bnama\s+(?:petugas|pekerja)\s*:)',line)]
    evidence=[]
    for line in segments:
        if len(line)>270 or re.search(r'(?i)\b(?:ditandatangani|menyetujui|penanggung\s+jawab|pengesahan|penguji|penyelia|direktur)\b',line):continue
        normalized=norm(line).split()
        if not all(any(fuzz.ratio(t,u)>88 for u in normalized) for t in actual_tokens):continue
        # Bound the person's own name within the table line; preserve source
        # capitalization/spelling and remove barcode/id and measurements.
        match=re.search(r'(?i)(?:\b(?:dr\.?\s+)?'+re.escape(actual_tokens[0])+r'\b)',line)
        if match:
            end=match.end()
            valid=True
            for token in actual_tokens[1:]:
                hit=re.search(r'(?i)\b'+re.escape(token)+r'\b',line[end:])
                if not hit or hit.start()>45:valid=False;break
                end=end+hit.end()
            if valid:
                quote=line[match.start():end].strip()
                evidence.append((100,quote))
    if not evidence:return None,None
    evidence.sort(key=lambda it:len(it[1]))
    return evidence[0][1],float(evidence[0][0])


def related_facility_score(expected, quote, full_text, address_score=None):
    score=_facility_score(expected,quote)
    if score is None:return None
    expected_tokens=norm(expected).split()
    missing=set(expected_tokens)-set(norm(quote).split())
    # If a source CLIENT name omits its trailing locality, require that
    # exact locality in the independently extracted SOURCE address.
    if (len(missing)==1 and expected_tokens[-1] in missing and
            expected_tokens[-1] in norm(full_text).split() and
            address_score is not None and address_score>=85):
        return 100.
    return score
