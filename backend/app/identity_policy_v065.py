"""Source-bound facility/address evidence cleanup and one final address policy.

Never infer a missing identity from the reference, and never turn a score alone
into a MATCH without a recognizable location anchor. No additional OCR.
"""
from __future__ import annotations
import re
import unicodedata
from difflib import SequenceMatcher
from .address_equivalence_v068 import house_number, street_words, canonical_text, shared_locality, rt_rw_conflict

EMPTY={'','-','—','–','none','null','n/a','tidak ditemukan'}
FACLABEL=re.compile(r'(?i)^\s*(?:\d+[.)]?\s*)?(?:nama\s+(?:fasilitas(?:\s+kesehatan)?|rumah\s+sakit|rs|instansi|klinik)|nama\s*/\s*alamat\s+(?:fasilitas|rs)|fasilitas\s+kesehatan|hospital\s+name)\s*[:|\-]?\s*')
ADDRLABEL=re.compile(r'(?i)^\s*(?:\d+[.)]?\s*)?(?:alamat\s+(?:fasilitas|rs|rumah\s+sakit|instansi|proyek|klinik|pemohon)|alamat(?!\s+(?:penguji|supplier|importir|petugas|kantor|laboratorium|vendor))|lokasi\s+(?:fasilitas|pelayanan|proyek))\s*[:|\-]?\s*')
STOP=re.compile(r'(?i)^(?:\d+[.)]?\s*)?(?:nama\s+(?:petugas|penguji|pemohon|penanggung|direktur|dokter|tenaga|ppr|fasilitas|rumah\s+sakit|instansi)|alamat\s+(?:fasilitas|proyek|penguji|instansi|pemohon)|nomor\s+(?:dokumen|izin|registrasi|sertifikat)|no\s*(?:dokumen|izin)|tanggal|tempat\s*/\s*tanggal|masa\s+berlaku|telepon|telp|tel\b|fax|faks|email|surel|website|jabatan|profesi|keahlian|penguji|penanggung\s+jawab|pengesahan|lembar\s+pengesahan|merk|merek|tipe|jenis\s+alat|no\.?\s+seri|data\s+penguji|data\s+alat|supplier|importir|laboratorium|daftar\s+isi|BAB\s+[IVX\d]+)\b')
INLINESTOP=re.compile(r'(?i)\s+(?:\||;|\s{3,})\s*(?:nama\s+(?:petugas|penguji|fasilitas)|alamat\s+(?:penguji|pemohon)|nomor\s+(?:dokumen|izin|registrasi)|tanggal|masa\s+berlaku|telp|telepon|fax|faks|email|website)\s*:')
LAYOUT_META=re.compile(r'(?i)\s{2,}(?:halaman|hal\.?|page|revisi|rev\.?|tanggal|tgl\.?|nomor\s+dokumen|no\.?\s+dokumen|telp\.?|telepon|fax\.?|faks\.?)\b.*$')
CONTACT=re.compile(r'(?i)(?:\s*[,;|]\s*|\s{2,})(?:(?:no\.?\s*)?(?:telp|telepon|tel|phone|fax|faks|email|website))\s*[:.]?\s*(?=\S)')
FACSTART=re.compile(r'(?i)\b(?:rsud|rsu|rsj|rumah\s+sakit(?:\s+umum\s+daerah)?|rumkit|rs\.?\s+(?=\w)|klinik|puskesmas|balai\s+kesehatan|balai\s+pengobatan|hospital)\b')
ROAD=re.compile(r'(?i)\b(?:jalan|jl|jln|j1|ji|gang|gg|komplek?s?|kawasan)[.:-]?\s*(?=[\w])')
CONT=re.compile(r'(?i)^(?:jalan|jl\.?|jln\.?|j1\.?|ji\.?|gang|gg\.?|rt\b|rw\b|no\.?\s*\d|nomor\s*\d|kel(?:urahan)?\b|desa\b|kec(?:amatan)?\b|kota\b|kab(?:upaten)?\b|prov(?:insi)?\b|kode\s*pos|\d{5}\b|\d+[a-z]?\s*[,;]?\s*(?:rt|rw)\b|kalimantan\b|jawa\b|sumatera\b|sulawesi\b|bali\b|papua\b|aceh\b)')


def norm(s):
    s=unicodedata.normalize('NFKC',str(s or '')).casefold()
    s=re.sub(r'\b(?:jln|jalan|jl|ji|j1)\.?\s+', ' jalan ',s)
    s=re.sub(r'\b(?:nomor|no)\.?\s*(?=\d)',' nomor ',s)
    return ' '.join(re.findall(r'[a-z0-9]+',s))


def is_empty(s):return norm(s) in {'','none','null','n a','tidak ditemukan'} or str(s or '').strip().lower() in EMPTY


def clean_evidence(value,kind):
    if is_empty(value):return ''
    s=str(value).replace('\r','\n').strip()
    # Preserve addresses that wrap vertically. Stop at a new unrelated field.
    items=[]
    for raw in s.split('\n'):
        t=raw.strip(' \t|;')
        if not t:continue
        if STOP.match(t):
            # A header may be the first meaningful line. Remove its label.
            label=(ADDRLABEL if kind=='address' else FACLABEL).match(t)
            if label:
                t=t[label.end():].strip(' :|-')
                if not t:continue
            else:break
        else:
            t=(ADDRLABEL if kind=='address' else FACLABEL).sub('',t,count=1).strip(' :|-')
        if not t:continue
        t=INLINESTOP.split(t,maxsplit=1)[0]
        t=LAYOUT_META.split(t,maxsplit=1)[0]
        cut=CONTACT.search(t)
        if cut:t=t[:cut.start()]
        if kind=='facility':
            street=ROAD.search(t)
            if street:t=t[:street.start()]
        t=t.strip(' ,;|:-')
        if t:items.append(t)
        if len(items)>=6:break
    if not items:return ''
    if kind=='facility':
        val=' '.join(items)
        # A facility value containing another labeled field is not trustworthy.
        if not FACSTART.search(val):return ''
        return val[:130].strip(' ,;:-')
    # Only retain a real address span; discard unrelated preamble.
    value=' '.join(items)
    road=ROAD.search(value)
    if road and road.start()>0:
        value=value[road.start():]
    # Address must be place-specific, not a person's name or document ID.
    if not ROAD.search(value) and not re.search(r'(?i)\b(?:rt\s*\d|rw\s*\d|kecamatan|kelurahan|desa|kota|kabupaten)\b',value):return ''
    return re.sub(r'\s+',' ',value).strip(' ,;:-')[:380]


def _street(v):
    # Preserve v065 street-anchor safeguards, normalize punctuation and acronyms.
    return street_words(v)


def _number(v):
    # No. 02 / No:2 / No-002 / No/2 all denote the same *house number*.
    # Compound 2/4, suffix 2A, and RT/RW must remain distinct when different.
    return house_number(v)


def _postal(v):
    x=re.findall(r'(?<!\d)\d{5}(?!\d)',str(v or ''))
    return x[-1] if x else None


def _major_city(value):
    m=re.search(r'(?i)\bkota\s+([a-z]+)(?:\s+(barat|timur|utara|selatan|pusat))?\b',str(value or ''))
    return (m.group(1).casefold(),(m.group(2) or '').casefold()) if m else None


def address_decision(expected,observed,original_status,score):
    """MATCH for >=85 only when actual street evidence supports it.

    A misleading high score from a non-address fragment becomes unscored REVIEW,
    not a cosmetically edited 100%-REVIEW. Explicit conflicts are never MATCH.
    """
    left,right=clean_evidence(expected,'address'),clean_evidence(observed,'address')
    if not left or not right:
        return 'REVIEW',None,'Alamat tidak terbaca lengkap atau tidak relevan'
    if canonical_text(left)==canonical_text(right):
        if ROAD.search(left) or _number(left):return 'MATCH',100.0,''
        return 'REVIEW',None,'Alamat hanya memuat fragmen lokasi, belum cukup spesifik'
    n1,n2=_number(left),_number(right)
    p1,p2=_postal(left),_postal(right)
    if rt_rw_conflict(left,right):
        return 'REVIEW',None,'RT/RW tercantum berbeda; cek dokumen asli'
    if (n1 and n2 and n1!=n2) or (p1 and p2 and p1!=p2):
        return 'REVIEW',None,'Nomor bangunan atau kode pos bertentangan; cek dokumen asli'
    city1,city2=_major_city(left),_major_city(right)
    if city1 and city2 and (city1[0]!=city2[0] or (city1[1] and city2[1] and city1[1]!=city2[1])):
        return 'REVIEW',None,'Kota atau wilayah administratif berbeda; periksa alamat asli'
    st1,st2=_street(left),_street(right)
    if not st1 or not st2:
        return 'REVIEW',None,'Bukti nama jalan belum lengkap; skor teks tidak dapat memastikan alamat'
    intersection=len(st1&st2)/max(1,min(len(st1),len(st2)))
    # Street anchor: one distinctive token is too weak when road has >1 tokens.
    score=float(score) if isinstance(score,(int,float)) and not isinstance(score,bool) else None
    # OCR aliases of the same street sometimes change one token (Ahmad/Imat).
    # Only tolerate that with a shared place marker and a high matcher score.
    street_similarity=SequenceMatcher(None,' '.join(sorted(st1)),' '.join(sorted(st2))).ratio()
    location_tokens={'balikpapan','semarang','pekanbaru','jakarta','malang','bandung','surabaya','aceh','kebumen','yogyakarta','medan','makassar','samarinda'}
    shared_location=bool(set(norm(left).split())&set(norm(right).split())&location_tokens)
    weak_anchor=intersection<0.50 or (len(st1&st2)<2 and max(len(st1),len(st2))>1)
    if weak_anchor and not (intersection>=0.50 and street_similarity>=.70 and shared_location and score is not None and score>=85):
        return 'REVIEW',None,'Nama jalan berbeda atau terlalu sedikit bukti spesifik'
    # Same distinctive road AND explicit house number plus corroborating
    # locality can override an overly punitive raw-character score.
    # Never override explicit house/ZIP/city/RT-RW conflicts checked above.
    if st1==st2 and st1 and n1 is not None and n1==n2 and shared_locality(left,right):
        score=max(85.0,score or 0.0)
    if score is None:
        # Comparable exact street (including aliases) and clear common location
        # can supply a validated score in the absence of a source matcher score.
        if st1==st2 and (n1 and n1==n2 or p1 and p1==p2):
            score=100.0
        else:
            return 'REVIEW',None,'Skor alamat tidak tersedia; perlu pemeriksaan'
    score=max(0.0,min(100.0,score))
    if score>=85:return 'MATCH',score,''
    if score>=75:return 'REVIEW',score,'Skor alamat di bawah ambang MATCH 85%'
    return 'REVIEW',score,'Kemiripan alamat rendah; perlu pemeriksaan dokumen'


def facility_decision(expected,observed,previous,score):
    value=clean_evidence(observed,'facility')
    if not value:return 'REVIEW',None,'Nama fasilitas tidak terbaca secara meyakinkan'
    a,b=norm(expected),norm(value)
    if a==b:return 'MATCH',100.0,''
    # Do not automatically promote partial name or generic "Rumah Sakit" match.
    return previous,score,''


def _join(lines,start,kind):
    pattern=FACLABEL if kind=='facility' else ADDRLABEL
    first=lines[start].strip()
    m=pattern.match(first)
    if not m:return ''
    value=first[m.end():].strip(' :|-')
    pieces=[value] if value else []
    for nxt in lines[start+1:start+7]:
        x=nxt.strip()
        if not x:continue
        if STOP.match(x) or FACLABEL.match(x) or ADDRLABEL.match(x):break
        if len(x)>110 or x.count('|')>2:break
        if kind=='facility':
            if ROAD.search(x) or re.search(r'(?i)\b(?:telp|fax|email|kota|alamat)\s*:',x):break
            if len(pieces)>=2:break
            if pieces and len(pieces[-1].split())>=9:break
            # A second baseline may contain a distinctive proper name.
            if not pieces and not (FACSTART.search(x) or re.search('[A-Za-z]{3,}',x)):break
        else:
            if not pieces:
                if not (ROAD.search(x) or CONT.search(x)):break
            elif not CONT.search(x) and not (pieces[-1].rstrip().endswith(',') and len(x)<75 and ':' not in x):
                break
        pieces.append(x)
        if len(pieces)>=5:break
    return clean_evidence('\n'.join(pieces),kind)


def _bare_header_address(lines,start):
    """Collect a street on a facility letterhead even without an Alamat label."""
    first=lines[start].strip()
    m=ROAD.search(first)
    if not m:return ''
    pieces=[first[m.start():]]
    for raw in lines[start+1:start+7]:
        line=raw.strip()
        if not line:continue
        if STOP.match(line) or FACLABEL.match(line) or ADDRLABEL.match(line):break
        if len(line)>115:break
        if CONT.search(line) or (pieces[-1].rstrip().endswith(',') and len(line)<80 and ':' not in line):
            pieces.append(line)
        else:break
        if len(pieces)>=5:break
    return clean_evidence('\n'.join(pieces),'address')


def candidate_lines(pages,kind):
    """Extract labelled vertical and inline values with source provenance.

    Scope to licensee/facility section, never copy a supplier's header/footer.
    """
    candidates=[]
    pat=FACLABEL if kind=='facility' else ADDRLABEL
    for page,content in pages:
        lines=[x.strip() for x in content.splitlines()]
        supplier_section=False
        for idx,line in enumerate(lines[:180]):
            if re.match(r'(?i)^\s*(?:[IVX]+[.]?\s*)?(?:data|identitas)\s+(?:penguji|supplier|importir|laboratorium)\b',line):
                supplier_section=True
            if re.match(r'(?i)^\s*(?:[IVX]+[.]?\s*)?(?:data|identitas)\s+(?:instansi|pemohon|fasilitas|rumah\s+sakit)\b',line):
                supplier_section=False
            if supplier_section or not pat.match(line):continue
            value=_join(lines,idx,kind)
            if not value:continue
            if kind=='facility' and not FACSTART.search(value):continue
            if kind=='address' and not ROAD.search(value):continue
            candidates.append({'value':value,'page':page,'quote':line[:160],'source':'label_vertical_or_inline'})
        # A facility letterhead commonly has an unlabeled street immediately
        # under the hospital name, sometimes with page/revision metadata in the
        # neighboring column. Require an actual facility heading nearby.
        if kind=='address' and not any(c['page']==page for c in candidates):
            for idx,line in enumerate(lines[:24]):
                if not ROAD.search(line):continue
                neighbor=' '.join(lines[max(0,idx-5):idx]).casefold()
                if not FACSTART.search(neighbor):continue
                if re.search(r'(?i)\b(?:data\s+penguji|supplier|importir|laboratorium\s+penguji)\b',neighbor):continue
                val=_bare_header_address(lines,idx)
                if val and ROAD.search(val):
                    candidates.append({'value':val,'page':page,'quote':line.strip()[:160],
                                       'source':'verified_facility_letterhead'})
                    break
        # May be on a hospital letterhead without an explicit field label:
        if kind=='facility' and not any(c['page']==page for c in candidates):
            for idx,line in enumerate(lines[:20]):
                if not FACSTART.match(line) or len(line)>110:continue
                val=clean_evidence(line,'facility')
                if val:candidates.append({'value':val,'page':page,'quote':line[:160],'source':'hospital_header'})
    return candidates


def _location_tokens(value):
    """Get labeled locality context from any Indonesian region, not city whitelist."""
    out=set()
    pattern=r'(?i)\b(?:kota|kabupaten|kab\.?|kecamatan|kec\.?|kelurahan|kel\.?|desa)\s+([a-z][a-z\s]{1,38})'
    for match in re.finditer(pattern,str(value or '')):
        part=re.split(r'(?i)\b(?:kota|kabupaten|kecamatan|kelurahan|desa|provinsi|kalimantan|jawa|sumatera|sulawesi)\b|[,;]|\d{5}',match.group(1),maxsplit=1)[0]
        out.update(w for w in norm(part).split() if len(w)>3 and w not in {'timur','barat','utara','selatan','tengah'})
    return out


def address_source_score(expected,observed):
    """Component-based score for new source-derived evidence, not raw length.

    Extra genuine RT/RW, kelurahan, province never lowers the score by itself.
    Must still pass address_decision street/number/postal checks.
    """
    if norm(expected)==norm(observed):return 100.0
    street_expected,street_observed=_street(expected),_street(observed)
    if not street_expected or not street_observed:return None
    overlap=len(street_expected&street_observed)/max(1,min(len(street_expected),len(street_observed)))
    street_similarity=SequenceMatcher(None,' '.join(sorted(street_expected)),' '.join(sorted(street_observed))).ratio()
    if overlap<.50 or street_similarity<.65:return None
    local1,local2=_location_tokens(expected),_location_tokens(observed)
    locality=bool(local1&local2) or (_postal(expected) is not None and _postal(expected)==_postal(observed))
    same_number=bool(_number(expected) and _number(expected)==_number(observed))
    if not locality and not same_number:return None
    if overlap>=1:return 98.0 if same_number else 94.0
    if street_similarity>=.78 and locality:return 88.0
    if street_similarity>=.70 and locality:return 85.0
    return None


def select_candidate(candidates,expected,kind,observed=''):
    """Prefer source-backed candidate only when strongly supported by the reference.

    Reference is used to rank *observed candidates*, never to construct a value.
    """
    left=norm(expected)
    if not left:return None
    scored=[]
    for c in candidates:
        val=c['value']; right=norm(val)
        if not right:continue
        ratio=SequenceMatcher(None,left,right).ratio()
        if kind=='facility':
            distinct=set(left.split())-{'rumah','sakit','umum','daerah','klinik','rs','rsud','kota'}
            common=distinct & set(right.split())
            if not common or ratio<.53:continue
            similarity=round(100*ratio,1)
        else:
            a,b=_street(expected),_street(val)
            if not a or not b or len(a&b)<max(1,(min(len(a),len(b))+1)//2):continue
            similarity=address_source_score(expected,val)
            if similarity is None:continue
            if _number(expected) and _number(val) and _number(expected)!=_number(val):continue
            if _postal(expected) and _postal(val) and _postal(expected)!=_postal(val):continue
        current=SequenceMatcher(None,left,norm(observed)).ratio() if observed else 0
        fuller_source=(kind=='address' and len(right)>len(norm(observed))*1.25 and
                       bool(_street(observed)) and _street(observed)==_street(val))
        if current>=ratio and not is_empty(observed) and len(norm(observed))>=len(right)*.70 and not fuller_source:
            continue
        scored.append((similarity,len(right),c))
    if not scored:return None
    similarity,_,best=max(scored,key=lambda x:(x[0],x[1]))
    if kind=='address':
        # Parser score is a text similarity, not proof; policy will verify anchors.
        return dict(best,score=similarity)
    return dict(best,score=similarity)
