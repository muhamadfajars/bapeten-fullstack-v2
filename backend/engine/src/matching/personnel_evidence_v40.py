"""Evidence-first personnel matching. v41: retain source quotes and refuse unsupported matches.

Source pages are untrusted. No address/facility/role can be inferred from the
application or a shared city alone. Match and confidence are distinct.
"""
import re
import unicodedata
from rapidfuzz import fuzz

STREET_RE = re.compile(r'(?<![a-z])(?:jl\.?|jln\.?|jalan)\s*', re.I)
ADDRESS_LABEL_RE = re.compile(r'(?i)\b(?:alamat\s+prakt[ie]k|lokasi\s+prakt[ie]k|tempat\s+prakt[ie]k|alamat\s+(?:fasilitas|rumah\s+sakit|proyek)|tempat\s+kerja)\b')
FACILITY_RE = re.compile(r'(?i)\b(?:rumah\s+sakit\b|rsud\b|rs\.?(?=\s)|rumkit\b|klinik\b|puskesmas\b)')
ROLE_RE = re.compile(r'(?i)\b(?:radiolog\w*|radiograf\w*|dokter|petugas\s+proteksi\s+radiasi|\bppr\b|fisikawan|profesi|jabatan|keahlian|untuk\s+praktik)\b')
SIGNER_RE = re.compile(r'(?i)\b(?:disetujui\s+oleh|approved\s+by|ditandatangani\s+oleh|mengesahkan|penanggung\s+jawab|kepala\s+laboratorium|direktur\s+laboratorium)\b')
APPROVAL_SECTION_RE = re.compile(r'(?i)^\s*(?:disetujui\s+oleh|approved\s+by|ditandatangani\s+oleh|pengesahan\b|disahkan\s+oleh|menyetujui\b)')
PASS_RE = re.compile(r'(?i)\b(?:lulus\s*/\s*has\s+passed|dinyatakan\s+kompeten|dinyatakan\s+lulus|lulus|has\s+passed|kompeten|competent|passed\s+the\s+exam)\b')
FAIL_RE = re.compile(r'(?i)\b(?:tidak\s+lulus|belum\s+lulus|not\s+passed|not\s+competent|tidak\s+kompeten)\b')
NON_ADDRESS_END = re.compile(r'(?i)\b(?:nomor\s+str|nomor\s+sip|masa\s+berlaku|tanggal\s+lahir|tempat\s+lahir|nomor\s+registrasi|nomor\s+surat|profesi|jabatan|keahlian|berlaku\s+sampai|revisi\s*:|halaman\s*\d+\s+dari|email\s*:|telp\.?\s*:|fax\.?\s*:)\b')
STOP = {'jl','jalan','jln','no','nomor','kota','kabupaten','provinsi','desa','kelurahan','kecamatan','rt','rw','alamat','indonesia','dan','atau','yang','dari','halaman','rumah','sakit','rs','klinik','prov','kab'}

def norm(s):
    s=unicodedata.normalize('NFKC',str(s or '')).casefold().replace('ﬁ','fi').replace('ﬂ','fl')
    s=re.sub(r'\b(?:jln?\.?|jalan)\b','jalan',s)
    s=re.sub(r'\b(?:no\.?|nomor)\b','nomor',s)
    s=re.sub(r'\b(?:rs\.?|r\s+s)\b','rumah sakit',s)
    return ' '.join(re.findall(r'[a-z0-9]+',s))

def _lines(text):
    return [re.sub(r'\s+',' ',s).strip() for s in str(text or '').splitlines() if s.strip()]

def lines_with_context(text):
    lines=_lines(text)
    for i,line in enumerate(lines):
        if len(line)<=420:
            yield i,line
        # OCR often splits the label, location and administrative subdivisions.
        for size in (2,3,4):
            if i+size>len(lines):break
            merged=' '.join(lines[i:i+size])
            if len(merged)>420:break
            if NON_ADDRESS_END.search(' '.join(lines[i+1:i+size])):break
            yield i,merged

def street_key(s):
    match=STREET_RE.search(str(s or ''))
    if not match:return ''
    tail=str(s)[match.end():]
    tail=re.split(r'(?i)\b(?:rt\.?\s*\d|rw\.?\s*\d|kel(?:urahan)?\.?|kec(?:amatan)?\.?|kota\s|kab(?:upaten)?\.?|provinsi|telp|fax|kode\s+pos|halaman|revisi|tanggal|desa\s)\b',tail,maxsplit=1)[0]
    tail=re.split(r'(?i)\b(?:no\.?|nomor)\s*[:.]?\s*\d+',tail,maxsplit=1)[0]
    tail=re.sub(r'\([^)]*\)',' ',tail)
    return norm(tail)

def house_number(s):
    m=re.search(r'(?i)\b(?:no\.?|nomor)\s*[:.]?\s*(\d+[a-z]?)\b',str(s or ''))
    return m.group(1).lower().lstrip('0') if m else None

def location_tokens(s):
    """Only compare explicitly available components, not missing province/postcode."""
    value=norm(s)
    # Avoid code/postal/administrative filler as a similarity substitute.
    return {t for t in value.split() if t not in STOP and len(t)>2 and not t.isdigit()}

def match_street(expected, actual):
    e=street_key(expected);a=street_key(actual)
    if not e or not a:return None
    et=[t for t in e.split() if t not in STOP and len(t)>2]
    at=[t for t in a.split() if t not in STOP and len(t)>2]
    if not et or not at:return None
    shared=sum(any(fuzz.ratio(t,w)>=86 for w in at) for t in et)
    fraction=shared/len(et)
    if fraction<.72:return None
    en,an=house_number(expected),house_number(actual)
    if en and an and en!=an:return None
    # Scoring is based on street and known number. Location details missing in
    # the excerpt reduce evidence completeness, not trigger false mismatch.
    street_score=min(100.,.6*fuzz.ratio(e,a)+40*fraction)
    if en and an and en==an:street_score=min(100.,street_score+0)
    elif en and not an:street_score=min(street_score,85.)
    city_tokens=[x for x in re.findall(r'(?i)\b(?:kota|kab(?:upaten)?\.?|provinsi)\s+([\w-]+)',str(expected))]
    if city_tokens and not any(norm(city) in norm(actual) for city in city_tokens):
        street_score=min(street_score,94.)
    return round(street_score,1)

def _address_candidates(text):
    lines=_lines(text)
    candidates=[]
    for i,line in enumerate(lines):
        # For a labelled address, strip field title and recover its continuation.
        label=ADDRESS_LABEL_RE.search(line)
        if label:
            after=line[label.end():].lstrip(' :\t-')
            portion=[after] if after else []
            for later in lines[i+1:i+4]:
                if NON_ADDRESS_END.search(later):break
                if re.match(r'(?i)^\s*(?:nama\s*:|jenis\s*:|alamat\s*:|nomor\s*:)',later):break
                portion.append(later)
            merged=' '.join(portion)
            m=STREET_RE.search(merged)
            if m:candidates.append((3,merged[m.start():].strip()))
        # Street mention in running text or OCR cells.
        if STREET_RE.search(line):
            for size in (1,2,3):
                parts=[line]
                for nxt in lines[i+1:i+size]:
                    if NON_ADDRESS_END.search(nxt) or re.match(r'(?i)^\s*(?:nama\s*:|nomor\s*str|masa\s*berlaku)',nxt):break
                    parts.append(nxt)
                merged=' '.join(parts)
                m=STREET_RE.search(merged)
                if m:
                    hint=1 if re.search(r'(?i)\b(?:untuk\s+menjalankan|untuk\s+praktik|tempat\s+praktik|di\s+rs\b)',line) else 0
                    candidates.append((hint,merged[m.start():].strip()))
    return candidates

def find_address(text, expected):
    if not text or not expected:return None,None
    hits=[]
    for priority,quote in _address_candidates(text):
        quote=NON_ADDRESS_END.split(quote,maxsplit=1)[0].strip(' :;,')
        if len(quote)>275:quote=quote[:275].strip()
        score=match_street(expected,quote)
        if score is None:continue
        # Strong address-field proximity first, then comparison reliability,
        # then richer original evidence; NEVER prefer a truncated 2-word quote.
        fullness=len(quote.split())
        hits.append((priority,score,min(fullness,35),quote))
    if not hits:return None,None
    hits.sort(key=lambda row:(row[0],row[1],row[2]),reverse=True)
    _priority,score,_fullness,quote=hits[0]
    return quote,score

def _facility_excerpt(line):
    match=FACILITY_RE.search(line)
    if not match:return None
    span=line[match.start():]
    span=re.split(r'(?i)\s*(?:[,;]|\b(?:jl\.?|jalan|nomor\s+str|nomor\s+sertifikat|untuk\s+melaksanakan|untuk\s+menjalankan|yang\s+beralamat|tanggal|telp|fax)\b)',span,maxsplit=1)[0]
    # Restrict narrative tails without cutting actual names with two modifiers.
    span=re.split(r'(?i)\s+\b(?:sebagai|adalah|untuk|dengan|telah|yang|berlaku|berlokasi|menyatakan|dalam|dilaksanakan|berdasarkan)\b',span,maxsplit=1)[0]
    return span.strip(' :;,.')[:135]

def _facility_score(expected, observed):
    target=norm(expected);source=norm(observed)
    if not target or not source:return None
    core=[t for t in target.split() if t not in STOP and len(t)>2]
    target_words=source.split()
    if not core or sum(any(fuzz.ratio(t,w)>=88 for w in target_words) for t in core)<max(1,len(core)-1):return None
    score=fuzz.token_set_ratio(target,source)
    missing=sum(not any(fuzz.ratio(t,w)>=88 for w in target_words) for t in core)
    if missing:score=min(score,89.)
    return round(float(score),1)

def _expertise_score(expected, quote):
    t=norm(expected);q=norm(quote)
    if not t or not q:return None
    aliases={'ppr':'petugas proteksi radiasi','sp rad':'dokter spesialis radiologi','radiographer':'radiografer'}
    for old,new in aliases.items():
        t=t.replace(old,new);q=q.replace(old,new)
    core=[x for x in t.split() if x not in STOP and x not in {'dan','atau','intervensional','diagnostik'} and len(x)>2]
    if not core:return None
    if not any(x in q.split() for x in core):return None
    covered=sum(x in q.split() for x in core)/len(core)
    # A generic 'Dokter Spesialis' is insufficient evidence of radiology.
    return round(min(fuzz.token_set_ratio(t,q),100*covered),1)

def find_evidence(text,expected,kind):
    if not text or not expected:return None,None
    if kind=='address':return find_address(text,expected)
    target=norm(expected)
    if not target:return None,None
    candidates=[]
    for index,line in lines_with_context(text):
        if len(line)>360:continue
        quote=line.strip()
        if kind=='facility':
            excerpt=_facility_excerpt(line)
            if not excerpt:continue
            # Fall back to text that includes relevant full facility name, but
            # do not match unrelated facilities in the same report.
            score=_facility_score(expected,excerpt)
            if score is None:continue
            quote=excerpt
        elif kind=='expertise':
            if not ROLE_RE.search(line):continue
            score=_expertise_score(expected,line)
            if score is None:continue
        elif kind=='person':
            core=[x for x in target.split() if x not in {'dr','dokter','sp','rad','a','md','s','kes'} and len(x)>=3]
            actual=norm(line).split()
            if not core or not all(any(fuzz.ratio(x,w)>=83 for w in actual) for x in core[:2]):continue
            if SIGNER_RE.search(line):continue
            score=float(fuzz.token_set_ratio(target,norm(line)))
        else:continue
        if score>=65:
            candidates.append((float(score),-len(quote),quote))
    if not candidates:return None,None
    candidates.sort(reverse=True)
    score,_,quote=candidates[0]
    return quote,round(score,1)

def find_pass_status(text):
    for line in (text or '').splitlines():
        if FAIL_RE.search(line):return line.strip(),False
        m=PASS_RE.search(line)
        if m:return m.group(0),True
    return None,None

def dose_person_found(text, expected):
    """Require a monitored-worker table or equivalent list, never a signatory."""
    if not text or not expected:return None,None
    lines=_lines(text)
    # Restrict to rows after a table heading, if detected; this avoids false
    # positives when a doctor is merely named as director / approver.
    starts=[]
    table_heading=re.compile(r'(?i)\b(?:nama\s+pengguna\s+lencana|nama\s+pekerja|nama\s+petugas|nama\s+personel|nama\s+terpantau|nomor\s+barcode|dosis\s+ekuivalen)\b')
    for idx,line in enumerate(lines):
        if table_heading.search(line):starts.append(idx)
    if starts:
        candidate_lines=lines[max(0,min(starts)-2):]
    else:
        # In a plain, unstructured PDF only use listed rows with an explicit
        # dose number or barcode. Otherwise do not assume every name is a worker.
        candidate_lines=lines
    end_re=re.compile(r'(?i)^\s*(?:disetujui\s+oleh|approved\s+by|pengesahan\s*[:(]|ditandatangani\s+oleh|catatan\s*[:])')
    for i,line in enumerate(candidate_lines):
        if end_re.search(line):candidate_lines=candidate_lines[:i];break
    quote,score=find_evidence('\n'.join(candidate_lines),expected,'person')
    if quote is None:return None,None
    # Do not credit a name that only occurs in approval/administrative text.
    if re.search(r'(?i)\b(?:disetujui|approved|pengesahan|penyelia|penguji|direktur|ditandatangani|penanggung\s+jawab)\b',quote):
        return None,None
    if not starts:
        # No identifiable worker table: return REVIEW only when row contains
        # a measured dose/ID rather than declaring an unsupported match.
        if not re.search(r'(?i)(?:\b\d+[.,]\d+\b|\b(?:tld|hp\s*\(?10|npr|barcode)\b)',quote):return None,None
    return quote,score

def find_practice_facility(text):
    """Find institution explicitly associated with work/practice, not issuer."""
    for _, line in lines_with_context(text):
        if not re.search(r'(?i)\b(?:untuk\s+menjalankan\s+pekerjaan|untuk\s+melaksanakan\s+tugas|untuk\s+praktik|alamat\s+praktik|tempat\s+praktik)\b',line):
            continue
        # Work permit '... sebagai Radiografer di RSUD ...'.
        location=re.search(r'(?i)\bdi\s+(?=(?:rsud|rs\.?|rumah\s+sakit|klinik)\b)',line)
        rest=line[location.end():] if location else line
        quote=_facility_excerpt(rest)
        if quote:return quote
    return None

def find_role_phrase(text):
    """Return documented job title, even when not equivalent to form expertise."""
    for _,line in lines_with_context(text):
        m=re.search(r'(?i)(?:\b(?:jabatan|profesi|keahlian|untuk\s+praktik)\s*[:]?\s*|\bsebagai\s+)(.{4,100})',line)
        if not m:continue
        role=m.group(1).strip(' :;,')
        role=re.split(r'(?i)\b(?:di\s+rumah|di\s+rsud\b|di\s+rs\.?\s|di\s+klinik|untuk\s+melaksanakan|yang\s+beralamat|nomor\s+str)\b',role,maxsplit=1)[0].strip()
        if ROLE_RE.search(role) and len(role)<=100:
            return role
    return None
