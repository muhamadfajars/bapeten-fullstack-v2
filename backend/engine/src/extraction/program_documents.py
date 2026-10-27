"""Evidence-first extraction of BAPETEN program/technical documents.

A positive MATCH requires explicit supporting source text. OCR-only or
ambiguous evidence must be reviewed by an evaluator; no legal validity claims.
"""
import os
import re
import tempfile
import base64
import unicodedata
from difflib import SequenceMatcher

import fitz
from src.matching.suitability_matcher import compare_institution, compare_address, compare_equipment_value
from src.extraction.equipment_sections import select_primary_pages, consistency_warnings

CATEGORIES = {
    'program_protection_upload': 'Program Proteksi Radiasi',
    'program_maintenance_upload': 'Program Perawatan',
    'management_system_upload': 'Sistem Manajemen',
    'technical_documents_upload': 'Dokumen Teknis',
}
FIELDS = ('merk_unit','tipe_unit','nomor_seri_unit','merk_tabung','tipe_tabung','nomor_seri_tabung')
EQUIPMENT_ALIASES = {
    'merk_unit': ('merk pesawat sinar-x','merek pesawat sinar-x','merk unit','merek/pabrikan','merk pesawat'),
    'tipe_unit': ('tipe/model pesawat sinar-x','type/model pesawat sinar-x','tipe unit','type unit','tipe/model','model pesawat'),
    'nomor_seri_unit': ('no. seri pesawat sinar-x','no seri pesawat sinar-x','nomor seri unit','nomor seri pesawat','serial number generator','nomor seri','no. seri unit'),
    'merk_tabung': ('merk tabung','merek tabung'),
    'tipe_tabung': ('tipe tabung','model tabung','tipe/model tabung','model/type'),
    'nomor_seri_tabung': ('no. seri tabung','no seri tabung','nomor seri tabung','serial number insersi'),
}

def _plain(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()

def _norm(s):
    return re.sub(r'[^a-z0-9]+','',unicodedata.normalize('NFKD',str(s or '')).casefold())

def _matching(a,b):
    a,b=_norm(a),_norm(b)
    if not a or not b: return False
    if a==b:return True
    return len(a)>=7 and len(b)>=7 and SequenceMatcher(None,a,b).ratio()>=.94

def _ocr_page(page):
    """Fallback for scanned PDF pages via the project's installed PaddleOCR."""
    import cv2
    import numpy as np
    from src.extraction.label_ocr import extract_ocr
    pix=page.get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False)
    img=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
    if pix.n==3: img=cv2.cvtColor(img,cv2.COLOR_RGB2BGR)
    elif pix.n==4: img=cv2.cvtColor(img,cv2.COLOR_RGBA2BGR)
    rows=extract_ocr(img)
    return '\n'.join(str(r.get('text','')) for r in rows)

def read_pages(path):
    ext=os.path.splitext(path)[1].lower()
    errors=[]
    pages=[]
    if ext=='.pdf':
        with fitz.open(path) as doc:
            for i,page in enumerate(doc):
                text=page.get_text(sort=True).strip()
                if len(_norm(text))<80:
                    try:
                        ocr=_ocr_page(page)
                        if len(_norm(ocr))>len(_norm(text)):
                            text=ocr
                    except Exception as exc:
                        errors.append(f'Halaman {i+1}: OCR tidak tersedia ({type(exc).__name__})')
                pages.append({'page':i+1,'text':text,'source':'pdf'})
    elif ext=='.docx':
        from docx import Document
        doc=Document(path)
        # DOCX page boundaries cannot be inferred reliably from raw paragraphs.
        lines=[p.text for p in doc.paragraphs]
        for tb in doc.tables:
            for row in tb.rows:
                lines.append(' | '.join(c.text for c in row.cells))
        pages=[{'page':None,'text':'\n'.join(lines),'source':'docx'}]
    elif ext in ('.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'):
        import cv2
        from src.extraction.label_ocr import extract_ocr
        image=cv2.imread(path)
        if image is None: raise ValueError('Gambar gagal dibuka')
        pages=[{'page':1,'text':'\n'.join(str(x.get('text','')) for x in extract_ocr(image)),'source':'image'}]
    else:
        raise ValueError('Format tidak didukung untuk ekstraksi. DOC lama perlu dikonversi ke DOCX/PDF terlebih dahulu.')
    return pages,errors

def _evidence(pages, pattern, max_count=8):
    pat=re.compile(pattern,re.I)
    hits=[]
    for p in pages:
        for line in p['text'].splitlines():
            if pat.search(line):
                hits.append({'page':p['page'],'quote':_plain(line)[:230]})
                if len(hits)>=max_count:return hits
    return hits

def _get_identity(pages, patterns):
    matches=[]
    for pattern in patterns:
        hits=_evidence(pages,pattern,5)
        matches.extend(hits)
    return matches[:8]

def _is_toc_page(text):
    """TOC evidence is not an approval page."""
    top = str(text or '')[:1800]
    if not re.search(r'(?i)\bdaftar\s+isi\b', top):
        return False
    return bool(re.search(r'(?i)\b(?:bab\s+[ivx]+|pendahuluan|dokumentasi|program\s+perawatan)\b', top)
                or len(re.findall(r'\.{4,}|…{2,}',top)) >= 2)


def _approval(pages):
    """Locate headed approval sheet; standalone heading sufficient as a candidate.

    PDFs sometimes merge the heading and subsequent content onto one line,
    or put every letter of the heading in a separate text span. A TOC reference
    is NEVER accepted. The result still requires visual verification.
    """
    heading = re.compile(r'(?i)\b(?:lembar|halaman)\s+pengesahan\b')
    spaced = re.compile(r'(?i)\b(?:l\s*e\s*m\s*b\s*a\s*r|h\s*a\s*l\s*a\s*m\s*a\s*n)\s+p\s*e\s*n\s*g\s*e\s*s\s*a\s*h\s*a\s*n\b')
    candidates=[]
    for p in pages:
        raw=p.get('text') or ''
        if not raw.strip() or _is_toc_page(raw):continue
        lines=[_plain(x) for x in raw.splitlines() if x.strip()]
        for i,line in enumerate(lines):
            m=heading.search(line) or spaced.search(line)
            if not m:continue
            # Avoid bibliographic mentions, sentences, dotted leaders and TOC entries.
            pre=line[:m.start()].strip(); post=line[m.end():].strip()
            if len(pre)>55 or re.search(r'(?i)\b(?:pada|lihat|daftar|tercantum|menuju|berikut)\b',pre):continue
            if re.search(r'\.{3,}|…{2,}',line):continue
            if re.match(r'^\s*(?:\d+|[ivxlcdm]+)\s*$',post,re.I):continue
            if len(post)>100 and not re.search(r'(?i)\b(?:rumah\s+sakit|disusun|disetujui|oleh|nama|tanggal)\b',post[:60]):continue
            body=' '.join(lines[i+1:i+12])
            candidates.append({'page':p.get('page'), 'quote':_plain(line+' '+body)[:300],
                               'approval_indicators':0,'has_date':False,'heading':'Lembar Pengesahan',
                               'source':p.get('source','text')})
            break
    return candidates[:3]


def _approval_ocr_fallback(path, pages, max_pages=12):
    """OCR likely early pages only when embedded PDF text missed a heading.

    This covers headings drawn as images in otherwise searchable documents.
    OCR failures only affect review evidence; they never certify approval.
    """
    if os.path.splitext(path)[1].lower() != '.pdf':return []
    import fitz
    # Approval pages are usually in the preliminary section. TOC pages are
    # excluded; the first max_pages physical pages are scanned in order.
    try:
        with fitz.open(path) as doc:
            for i in range(min(max_pages,len(doc))):
                if i<len(pages) and _is_toc_page(pages[i].get('text','')):continue
                try: raw=_ocr_page(doc[i])
                except Exception:continue
                result=_approval([{'page':i+1,'text':raw,'source':'ocr'}])
                if result:return result
    except Exception:return []
    return []

def _toc_target(pages):
    pat=re.compile(r'(?:\b4\s*[.．]\s*4\s*[.．]?\s*)?pemeriksaan\s+dan\s+pengujian\s+teknis',re.I)
    refs=[]
    for p in pages[:min(30,len(pages))]:
        lines=p['text'].splitlines()
        for j,line in enumerate(lines):
            if pat.search(line):
                context=' '.join(lines[j:j+2])[:240]
                after=context[pat.search(context).end():]
                nums=re.findall(r'(?<!\d)(\d{1,3})(?!\d)',after)
                # Any printed page is a hint only; physical PDF offset differs.
                printed=int(nums[-1]) if nums else None
                refs.append({'toc_pdf_page':p['page'],'printed_page_hint':printed,'quote':_plain(context)})
    return refs[:8]

def _section_maintenance(pages):
    """Find actual subsection, excluding TOC and generic mentions in introduction."""
    test_heading=re.compile(r'(?im)^\s*(?:4\s*[.．]\s*4\s*[.．]\s*\d+\s*[.．]?\s*)?(?:uji\s+kesesuaian(?:\s*\(\s*constancy\s+test\s*\))?|constancy\s+test)\s*$')
    freq_pattern=re.compile(r'(?:setiap|tiap|sekali\s+setiap|per)\s+\d+\s*(?:bulan|tahun)|\d+\s*(?:bulan|tahun)\s+sekali|setelah\s+(?:pemasangan|perbaikan|penggantian)[^\n.]{0,90}',re.I)
    found=[]
    for index,p in enumerate(pages):
        txt=p.get('text') or ''
        if re.search(r'\bdaftar\s+isi\b',txt[:300],re.I):continue
        for m in test_heading.finditer(txt):
            # Preserve line breaks to parse labeled frequency and numbered parameters.
            window=txt[m.start():m.start()+4400]
            if index+1<len(pages) and len(window)<2500:
                window+='\n'+(pages[index+1].get('text') or '')[:2300]
            next_heading=re.search(r'(?m)^\s*4\s*[.．]\s*4\s*[.．]\s*\d+\s+[A-Z][^\n]{4,}',window[m.end()-m.start()+15:])
            if next_heading:
                window=window[:m.end()-m.start()+15+next_heading.start()]
            freq=list(dict.fromkeys(_plain(x.group()) for x in freq_pattern.finditer(window)))
            params=[]
            para=re.search(r'parameter(?:\s+yang\s+diuji)?\s*(?:meliputi)?\s*:',window,re.I)
            if para:
                after=window[para.end():]
                for line in after.splitlines():
                    clean=_plain(line)
                    if re.match(r'^\s*(?:\d+\s*[.)]|[-•▪])\s+\S+',clean):
                        params.append(re.sub(r'^\s*(?:\d+\s*[.)]|[-•▪])\s*','',clean)[:180])
                    elif params:break
                    if len(params)>=16:break
            found.append({'page':p['page'],'heading':_plain(txt[m.start():m.end()]),
                         'frequencies':freq,'parameters':params,'excerpt':_plain(window[:460])})
    # One entry per genuine section, not every page mentioning uji kesesuaian.
    return found[:4]

def _split_value(line):
    if ':' in line:return _plain(line.split(':',1)[1])
    if '|' in line:return _plain(line.split('|',1)[1])
    return ''

def _compare_device(expected, observed, key):
    kind = 'serial' if key.startswith('nomor_seri') else 'brand' if key.startswith('merk') else 'type'
    # Parenthetical product-line annotations are ancillary when the actual
    # model identifier matches. Preserve the original for display.
    if kind == 'type':
        expected_core = re.sub(r'\s*\([^)]*\)', '', expected).strip()
        observed_core = re.sub(r'\s*\([^)]*\)', '', observed).strip()
        return compare_equipment_value(expected_core, observed_core, kind)
    return compare_equipment_value(expected, observed, kind)


def _field_label_match(line, key):
    """Avoid taking a value from a different unit/tube field."""
    compact = _plain(line).casefold()
    aliases = EQUIPMENT_ALIASES[key]
    return any(re.search(r'(?<![a-z])' + re.escape(alias).replace(r'\ ', r'\s+') + r'(?=\s*[:|]|\s*$)', compact) for alias in aliases)


def _identity_candidates(pages, expected):
    """Retrieve entity spans rather than entire paragraphs that contain generic words."""
    expected_words = set(re.findall(r'[a-z0-9]+', expected.casefold())) - {'rs', 'rumah', 'sakit', 'klinik', 'tk', 'iv'}
    options = []
    for page in pages:
        if _is_toc_page(page.get('text', '')):
            continue
        lines = page.get('text', '').splitlines()
        for i, line in enumerate(lines):
            line = _plain(line)
            if not line:
                continue
            # A label followed by the value can be separated by a colon or PDF extraction.
            pattern = r'(?i)^\s*(?:nama\s+)?(?:fasilitas|rumah\s+sakit|rs|klinik|instansi)\s*[:|]\s*(.+)$'
            m = re.search(pattern, line)
            value = _plain(m.group(1)) if m else line
            value = re.sub(r'(?i)^(?:revisi|versi|judul\s+dokumen)\s*[:|]\s*', '', value)
            # Prefer a header or self-contained facility name; reject narrative text.
            if len(value) > 110 or len(value.split()) > 12:
                continue
            if re.search(r'(?i)\b(?:kebijakan|menjadi|meliputi|pelaksanaan|target|penanggungjawab|kegiatan|sasaran|terhadap)\b', value):
                continue
            words = set(re.findall(r'[a-z0-9]+', value.casefold()))
            specificity = len(words & expected_words)
            if specificity == 0 and expected_words:
                continue
            if not m and re.search(r'(?i)\b(?:alamat|jalan|jl\.|telp|fax)\b', value):
                continue
            comparison = compare_institution(expected, value)
            options.append((specificity, 1 if m else 0, -page.get('page', 999), comparison, value,
                            {'page': page.get('page'), 'quote': line[:200], 'method':'facility_candidate'}))
    return sorted(options, reverse=True, key=lambda x:(x[0],x[1],x[2]))


def _address_components(raw):
    """Compare only mutually supplied components; do not punish extra province/ZIP."""
    s=_plain(raw).lower()
    s=re.split(r'(?i)\b(?:telp|telepon|telephone|phone|hp|fax|faks|facsimile)\b\s*[.:]?',s)[0]
    s=re.sub(r'\b(?:jln?|jalan)\.?\s*', 'jalan ', s)
    s=re.sub(r'\b(?:no|nomor)\.?\s*(?=\d)', 'nomor ', s)
    s=re.sub(r'\b0+(?=\d)', '', s)
    m=re.search(r'\bjalan\s+(.+?)(?=\bnomor\s*\d|[,;]|$)',s)
    street = re.sub(r'[^a-z0-9]+',' ',m.group(1)).strip() if m else None
    if street:
        street = re.sub(r'\b(?:dr|tni|ad)\b', '',street)
        street = ' '.join(street.split())
    no=re.search(r'\bnomor\s*(\d+[a-z]?)\b',s)
    num=no.group(1) if no else None
    city=re.search(r'\b(?:kota|kabupaten|kab\.?)\s+([a-z][a-z ]{2,28}?)(?=,|\b(?:riau|aceh|jawa|kalimantan|sumatera|sulawesi|bali|ntb|ntt)\b|\d{5}\b|$)',s)
    if city:
        city=city.group(1).strip()
    else:
        city=None
        for known in ('pekanbaru','balikpapan','banda aceh','semarang','malang'):
            if re.search(r'\b'+re.escape(known)+r'\b',s):city=known;break
    return {'street':street,'number':num,'city':city}


def _compare_address_shared(expected,observed):
    a,b=_address_components(expected),_address_components(observed)
    keys=[k for k in ('street','number','city') if a[k] and b[k]]
    if not keys:return {'status':'REVIEW','score':None,'reason':'Tidak ada komponen alamat yang dapat dibandingkan'}
    scores={}
    for k in keys:
        if k=='street':
            wa=set(a[k].split());wb=set(b[k].split())
            scores[k]=100.0*len(wa&wb)/max(len(wa),len(wb),1)
        else:
            scores[k]=100.0 if _norm(a[k])==_norm(b[k]) else 0.0
    weights={'street':5,'number':4,'city':2}
    score=round(sum(scores[k]*weights[k] for k in keys)/sum(weights[k] for k in keys),1)
    if 'number' in keys and scores['number']<100:
        status='MISMATCH'
    elif 'street' in keys and scores['street']>=85 and ('number' not in a or 'number' not in b or scores.get('number')==100):
        status='MATCH' if (('number' in keys) or ('city' in keys)) else 'REVIEW'
    else:status='REVIEW'
    return {'status':status,'score':score,'compared':keys,'components':scores}


def _clean_address_fragment(text):
    """Remove trailing document furniture without deleting street/house number."""
    text = _plain(text)
    text = re.sub(r'(?i)\b(?:halaman|page)\s*\d+\s*(?:dari|of|/)\s*\d+.*$', '', text)
    # PDF text extraction can interleave header-table cells inside address lines.
    text = re.sub(r'(?i)\b(?:halaman|page)\s*(?=\d+\s*[A-Za-z]|[A-Za-z]+)', '', text)
    text = re.sub(r'(?i)\b(?:revisi|tanggal)\s*[:]?\s*(?=$|\b(?:nomor|kota|provinsi)\b)', '', text)
    text = re.sub(r'(?i)\balamat\s*:\s*(?=\w)', ' ', text)
    text = re.sub(r'(?i)\b(?:halaman|page)\s*\d+\s*(?:dari|of|/)\s*\d+\b', '', text)
    text = re.split(r'(?i)\b(?:telp|tel\.|telepon|telephone|phone|fax|faks|facsimile)\s*[:.]?\s*(?=\+?\d|\()', text)[0]
    text = re.split(r'(?i)\s+\b(?:nomor\s+dokumen|tanggal\s+terbit|revisi\s*:)\b', text)[0]
    return _plain(text).strip(' ,;:-')


def _address_lines(lines, start):
    """Collect a multi-line facility address, including city after RT/RW.

    Stop at table furniture and non-address fields, not at every newline.
    """
    first = _plain(lines[start])
    mat = re.search(r'(?i)\b(?:jl\.?|jln\.?|jalan)\s+[a-z]', first)
    if not mat:
        return ''
    parts = [first[mat.start():]]
    continuation = re.compile(r'(?i)^(?:rt\.?|rw\.?|no\.?\s*\d|nomor\s*\d|\d+[a-z]?\s*[,;]?|kel(?:urahan|\.)?|kec(?:amatan|\.)?|kota\b|kab(?:upaten|\.)?|provinsi\b|kalimantan\b|riau\b|aceh\b|jawa\b|balikpapan\b|pekanbaru\b|banda\s+aceh\b|tengah\b|sumber\s+rejo\b)')
    stop = re.compile(r'(?i)^(?:halaman|page|tanggal|nomor\s*(?!\d)|revisi|bab\b|daftar\s+isi|pendahuluan|program\s+proteksi|program\s+perawatan|sistem\s+manajemen|data\s+pesawat|merk\b|tipe\b|nama\s+fasilitas)')
    for line in lines[start+1:start+5]:
        line = _plain(line)
        if not line or stop.search(line):
            break
        if continuation.search(line) or (parts[-1].rstrip().endswith(',') and len(line)<95 and not ':' in line):
            parts.append(line)
        else:
            break
    block = ' '.join(parts)
    # Correct a frequent PDF reading-order artifact: label from a neighboring
    # header column inserted between the district name and its continuation.
    block = re.sub(r'(?i)\b(?:halaman|page)\s+(?=\b(?:tengah|utara|selatan|barat|timur|kota)\b)', ' ', block)
    block = re.sub(r'(?i)\b(?:alamat)\s*:\s*(?=\b(?:tengah|utara|selatan|barat|timur|kota)\b)', ' ', block)
    return _clean_address_fragment(block)[:340]


def _retrieve_address(pages, expected):
    """Retrieve complete address spans, prefer nearby facility headers.

    Comparisons remain component-based, and a city-only mention can never
    generate an automatic MATCH.
    """
    candidates=[]
    for p in pages:
        if _is_toc_page(p.get('text','')):continue
        lines=p.get('text','').splitlines()
        for i,line in enumerate(lines):
            if not re.search(r'(?i)\b(?:jl\.?|jln\.?|jalan)\s+[a-z]', line):
                continue
            value=_address_lines(lines,i)
            if not value: continue
            result=_compare_address_shared(expected,value)
            comps=result.get('compared',[])
            valid=int('street' in comps)+int('number' in comps)+int('city' in comps)
            # Prefer the header address to unrelated references in narrative.
            near=' '.join(_plain(x) for x in lines[max(0,i-3):i]).casefold()
            header=int(bool(re.search(r'nama\s+fasilitas|rumah\s+sakit|klinik|rs\s+tk\b|program\s+(?:proteksi|perawatan)|sistem\s+manajemen',near)))
            evidence={'page':p.get('page'),'quote':value[:260],'method':'multiline_address_block','compared_components':comps}
            candidates.append((valid,result.get('score') or 0,result,value,evidence,header))
    candidates.sort(key=lambda x:(x[2]['status']=='MATCH',x[0],x[5],x[1]),reverse=True)
    return candidates

def _field_evidence(pages, key, expected):
    """Only labeled values are scored; uncontextualized mentions are REVIEW.

    If labeled values disagree, distinguish confirmed conflicts from ambiguous
    multi-device references. Never infer a mismatch from a missing value.
    """
    expected = _plain(expected)
    if not expected:
        return {'status':'REVIEW','evidence':[],'observed':'','score':None}
    aliases = EQUIPMENT_ALIASES[key]
    candidates = []
    weak = []
    for p in pages:
        lines = (p.get('text') or '').splitlines()
        for i, line in enumerate(lines):
            normalized = _plain(line)
            if not normalized:
                continue
            label_hit = any(alias in normalized.casefold() for alias in aliases)
            # Some device declarations list 'Serial Number Insersi', 'Model/type',
            # then bare 'Merk : Kailong'. This is tube brand only within the
            # same short block, never an unconstrained generic Merk occurrence.
            if key == 'merk_tabung' and not label_hit and re.match(r'(?i)^\s*(?:merk|merek)\s*[:|]', normalized):
                preceding = ' '.join(_plain(x) for x in lines[max(0, i-6):i]).casefold()
                label_hit = bool(re.search(r'(?:serial\s+number\s+insersi|nomor\s+seri\s+tabung|model\s*/\s*type|tipe\s+tabung|data\s+tabung)', preceding))
            # The generic 'Nomor Seri' label is only valid inside a unit
            # section. Never use it for tube/insertion/housing identifiers.
            if key == 'nomor_seri_unit' and label_hit and re.search(
                r'(?i)(?:tabung|tube|insersi|insertion|housing)', normalized
            ):
                label_hit = False
            if not label_hit:
                if _norm(expected) and _norm(expected) in _norm(normalized):
                    weak.append({'page':p['page'],'quote':normalized[:160]})
                continue
            extracted = _split_value(normalized)
            if not extracted and i + 1 < len(lines):
                extracted = _plain(lines[i+1])
            if not extracted or len(extracted) > 150:
                continue
            result = _compare_device(expected, extracted, key)
            candidates.append({'page':p['page'],'quote':normalized[:200],
                               'value':extracted,'status':result['status'],
                               'score':result.get('score',0)})
    # Rank directly labeled observations above OCR fragments and broad aliases.
    # Strong evidence is field-specific, anchored to the start of a line; a
    # weaker mention cannot veto an exact match in that field.
    strong_patterns = {
        'merk_unit': r'(?:merk|merek|brand)\s+(?:unit|pesawat(?:\s+sinar[- ]?x)?)',
        'tipe_unit': r'(?:tipe|type|model|tipe/model)\s+(?:unit|pesawat(?:\s+sinar[- ]?x)?)',
        'nomor_seri_unit': r'(?:(?:nomor|no\.?|serial)\s+(?:seri|number)(?:\s+(?:unit|pesawat(?:\s+sinar[- ]?x)?))?)',
        'merk_tabung': r'(?:merk|merek|brand)\s+tabung',
        'tipe_tabung': r'(?:tipe|type|model)\s+tabung',
        'nomor_seri_tabung': r'(?:(?:nomor|no\.?)\s+seri\s+tabung|serial\s+number\s+(?:tabung|tube))',
    }
    strong_re = re.compile(r'^\s*' + strong_patterns[key] + r'\s*[:|]', re.I)
    for c in candidates:
        c['strong'] = bool(strong_re.search(c['quote'])) or (key == 'merk_tabung' and bool(re.match(r'(?i)^\s*(?:merk|merek)\s*[:|]', c['quote'])))
    selected = [c for c in candidates if c['strong']] or candidates
    matches = [c for c in selected if c['status'] == 'MATCH']
    mismatches = [c for c in selected if c['status'] == 'MISMATCH']
    reliable_matches=[c for c in matches if c.get('strong')]
    reliable_mismatches=[c for c in mismatches if c.get('strong')]
    if reliable_matches and not reliable_mismatches:
        c=max(reliable_matches,key=lambda x:x.get('score') or 0)
        return {'status':'MATCH','score':c.get('score') or 100.0,'observed':c['value'],
                'evidence':reliable_matches[:3], 'method':'strong_field'}
    if matches and mismatches:
        return {'status':'REVIEW', 'evidence':(matches+mismatches)[:3],
                'observed':matches[0]['value'],'score':None,
                'reason':'Ada nilai bertentangan pada field yang sama'}
    if matches:
        c=max(matches,key=lambda x:x.get('score') or 0)
        return {'status':'MATCH','evidence':matches[:3], 'observed':c['value'],
                'score':c.get('score')}
    if mismatches:
        unique={_norm(c['value']) for c in mismatches}
        c=mismatches[0]
        if len(unique)==1:
            return {'status':'MISMATCH','evidence':mismatches[:3],
                    'observed':c['value'],'score':c.get('score')}
        return {'status':'REVIEW','evidence':mismatches[:3],
                'observed':c['value'],'score':None}
    if selected:
        c=selected[0]
        return {'status':'REVIEW','evidence':selected[:3],
                'observed':c['value'],'score':c.get('score')}
    # Form-guided fallback. Search document values, but accept them only if
    # accompanied by the right nearby field label within the unit/tube section.
    # A naked number in a paragraph must NOT produce a match.
    field_context = {
        'merk_unit': r'(?i)\b(?:merek|merk|brand)\s*(?:unit|pesawat)',
        'tipe_unit': r'(?i)\b(?:tipe|type|model)\s*(?:unit|pesawat)',
        'nomor_seri_unit': r'(?i)\b(?:nomor|no\.?|serial)\s*(?:seri|number)(?:\s+(?:unit|pesawat))?\b',
        'merk_tabung': r'(?i)\b(?:merek|merk|brand)\s+tabung',
        'tipe_tabung': r'(?i)\b(?:tipe|type|model)\s+tabung',
        'nomor_seri_tabung': r'(?i)\b(?:nomor|no\.?)\s*seri\s+tabung',
    }
    expected_core = re.sub(r'\s*\([^)]*\)', '', expected).strip() if key == 'tipe_unit' else expected
    sought = _norm(expected_core)
    if sought:
        for p in pages:
            lines = [_plain(x) for x in (p.get('text') or '').splitlines()]
            for i, line in enumerate(lines):
                # Avoid matching product names, numbers from unrelated pages.
                if sought not in _norm(line):
                    continue
                vicinity = lines[max(0,i-2):min(len(lines),i+2)]
                if not any(re.search(field_context[key], x) for x in vicinity):
                    continue
                if key == 'nomor_seri_unit' and any(re.search(r'(?i)\b(?:tabung|tube|insersi|housing)\b',x) for x in vicinity):
                    continue
                candidate = {'page':p['page'],'quote':line[:200]}
                return {'status':'MATCH','evidence':[candidate], 'observed':expected_core,
                        'score':100.0,'method':'form_guided_context_fallback'}
    return {'status':'REVIEW','evidence':weak[:3],'observed':'','score':None}

def _extract_equipment(pages,equipment):
    result=[]
    for ref in equipment or []:
        group=[]
        for key in FIELDS:
            expected=_plain(ref.get(key,''))
            if not expected:continue
            entry=_field_evidence(pages,key,expected)
            entry.update({'field':key,'expected':expected})
            group.append(entry)
        result.append(group)
    return result

def _extract_personnel(pages, personnel):
    """Find explicit names and plausible variants; never auto-MATCH fuzzy names."""
    found=[]
    prefixes={'dr','drg','sp','rad','amd','a','md','s','kom','apt','prof'}
    def terms(name):
        return [w for w in re.findall(r'[a-z]+', unicodedata.normalize('NFKC', name).casefold()) if len(w)>2 and w not in prefixes]
    for person in personnel or []:
        name=_plain(person.get('nama',''))
        if not name:continue
        exact=[]; alternates=[]
        expected_terms=terms(name)
        for p in pages:
            for line in (p.get('text') or '').splitlines():
                line=_plain(line)
                if not line or len(line)>160:continue
                if _norm(name) in _norm(line):
                    exact.append({'page':p.get('page'),'quote':line[:160],'value':name})
                    continue
                # Named-entity candidate must be a compact personnel field or
                # a short name, rather than a paragraph mentioning one word.
                m=re.match(r'(?i)^\s*(?:nama\s+(?:petugas|dokter|ppr|personil|personel)?|dokter|ppr|petugas)\s*[:|]\s*(.+)$',line)
                candidate=_plain(m.group(1)) if m else line
                if len(candidate.split())>8 or len(candidate)<5:continue
                overlap=len(set(expected_terms)&set(terms(candidate)))
                if overlap<2:continue
                ratio=SequenceMatcher(None,_norm(name),_norm(candidate)).ratio()
                if ratio>=.60:
                    alternates.append((ratio,{'page':p.get('page'),'quote':line[:160],'value':candidate}))
        if exact:
            found.append({'name':name,'observed':name,'status':'MATCH','score':100.0,'evidence':exact[:3]})
        elif alternates:
            ratio,best=max(alternates,key=lambda x:x[0])
            found.append({'name':name,'observed':best['value'],'status':'REVIEW',
                          'score':round(ratio*100,1),'evidence':[best],
                          'reason':'Nama mirip tetapi tidak identik; verifikasi ejaan'})
        else:
            found.append({'name':name,'observed':'','status':'REVIEW','score':None,'evidence':[]})
    return found

def analyze(path, category, reference=None):
    reference=reference or {}
    pages,errors=read_pages(path)
    # v27: contextual candidate search rather than first generic keyword hit.
    name_hits=[]
    address_hits=[]
    approvals=_approval(pages)
    if not approvals:
        approvals=_approval_ocr_fallback(path,pages)
    # identity matching may require normalizing hospital abbreviations; avoid auto approval based on the keyword alone.
    hospital=_plain(reference.get('nama_fasilitas') or reference.get('instansi',''))
    address=_plain(reference.get('alamat_proyek',''))
    alltext='\n'.join(p['text'] for p in pages)
    def match_identity(expected, hits, comparer, is_address=False):
        if not expected or not hits:
            return {'status':'REVIEW','score':None,'observed':'','evidence':hits}
        checks=[]
        for hit in hits:
            # Leave the full quote for address normalisation; strip index
            # prefixes and field labels only, not street numbers.
            observed = re.sub(r'^\s*\d+\s+(?=alamat\b)', '',hit['quote'],flags=re.I)
            observed = re.sub(r'(?i)^\s*(?:nama\s+)?(?:alamat|instansi|rumah\s+sakit)\s*:\s*', '', observed)
            comparison = comparer(expected, observed)
            if is_address and comparison.get('status') == 'MATCH':
                # Similarity is not the same as a component-level address
                # match; avoid reporting 100% for different-length strings.
                def address_clean(x):
                    x=re.split(r'(?i)\b(?:telp|telepon|fax|phone)\s*[.:]', x)[0]
                    x=re.sub(r'(?i)^.*?(?=\b(?:jl\.?|jln\.?|jalan)\b)', '', x) if re.search(r'(?i)\b(?:jl\.?|jln\.?|jalan)\b', x) else x
                    x=re.sub(r'(?i)\b(?:jl|jln)\.?', 'jalan',x)
                    x=re.sub(r'(?i)\bno\.?\s*', 'nomor ',x)
                    return _norm(x)
                ca,cb=address_clean(expected),address_clean(observed)
                comparison={**comparison,'score':round(SequenceMatcher(None,ca,cb).ratio()*100,1) if ca and cb else 0}
            checks.append((comparison, observed, hit))
        matches=[x for x in checks if x[0]['status']=='MATCH']
        if matches:
            best=max(matches,key=lambda x:x[0].get('score',0))
            return {'status':'MATCH','score':best[0]['score'],'observed':best[1],
                    'evidence':[best[2]]}
        best=max(checks,key=lambda x:x[0].get('score',0))
        return {'status':'REVIEW','score':best[0].get('score'),
                'observed':best[1],'evidence':[best[2]]}

    def render_approval_preview():
        if not approvals or not path.lower().endswith('.pdf'):
            return None
        page_index=approvals[0].get('page')
        if not isinstance(page_index,int):
            return None
        try:
            with fitz.open(path) as document:
                page=document[page_index-1]
                pix=page.get_pixmap(matrix=fitz.Matrix(1.25,1.25),alpha=False)
                return base64.b64encode(pix.tobytes('png')).decode('ascii')
        except Exception:
            return None

    name_candidates=_identity_candidates(pages,hospital) if hospital else []
    address_candidates=_retrieve_address(pages,address) if address else []
    if name_candidates:
        name_best=next((x for x in name_candidates if x[3]['status']=='MATCH'),name_candidates[0])
        hospital_result={'status':('MATCH' if name_best[3]['status']=='MATCH' else 'REVIEW'), 'score':name_best[3].get('score'),
                         'observed':name_best[4], 'evidence':[name_best[5]],
                         'method':'contextual_facility_retrieval'}
    else:
        hospital_result={'status':'REVIEW','score':None,'observed':'','evidence':[],
                         'reason':'Tidak ditemukan kandidat nama fasilitas yang meyakinkan'}
    if address_candidates:
        a_best=address_candidates[0]
        address_result={'status':a_best[2]['status'],'score':a_best[2]['score'],
                        'observed':a_best[3],'evidence':[a_best[4]],
                        'compared_components':a_best[2].get('compared',[]),
                        'method':'shared_address_components'}
    else:
        address_result={'status':'REVIEW','score':None,'observed':'','evidence':[],
                        'reason':'Alamat belum ditemukan'}
    output={
        'category':category,'filename':os.path.basename(path),'pages':len(pages),
        'warnings':errors,
        'hospital':{'expected':hospital,**hospital_result},
        'address':{'expected':address,**address_result},
        'approval':{'status':'MATCH' if approvals else 'REVIEW','evidence':approvals},
        'approval_preview':render_approval_preview(),
        'maintenance':None,'personnel':None,'equipment':None,
        'consistency_warnings':[],
    }
    if category=='program_maintenance_upload':
        refs=_toc_target(pages)
        subsections=_section_maintenance(pages)
        output['maintenance']={'toc':refs,'toc_status':'FOUND' if refs else 'REVIEW', 'section':subsections,'section_status':'FOUND' if subsections else 'REVIEW'}
    if category=='program_protection_upload':
        primary=select_primary_pages(pages,category)
        output['personnel']=_extract_personnel(pages,reference.get('personnel',[]))
        output['equipment']=None  # computed by v43_program_robust
        output['consistency_warnings']=consistency_warnings(pages,primary)
    if category=='technical_documents_upload':
        primary=select_primary_pages(pages,category)
        output['equipment']=None  # computed by v43_program_robust
        output['consistency_warnings']=consistency_warnings(pages,primary)
    # v44_program_robust: evidence-bound, subtype-aware matching.
    from src.extraction.program_robust_v46 import (
        facility_result as facility_result_v44, address_result as address_result_v44,
        match_equipment as match_equipment_v44, maintenance_sections as maintenance_sections_v44,
    )
    if hospital:
        output['hospital']={'expected':hospital, **facility_result_v44(pages,hospital,path)}
    if address:
        output['address']={'expected':address, **address_result_v44(pages,address,path)}
    if category in ('program_protection_upload','technical_documents_upload'):
        output['equipment']=match_equipment_v44(path,pages,reference.get('equipment',[]))
    if category=='program_maintenance_upload':
        output['maintenance']=maintenance_sections_v44(pages,output.get('maintenance'))
    return output
