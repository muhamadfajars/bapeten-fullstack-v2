"""Template-agnostic, conservative suitability-report field extraction.

No assumptions about exact section numbering. Extraction is label-driven; unsupported
scanned pages must be OCRed separately (no silent empty -> authoritative mismatch).
"""
import re
import pymupdf

LABELS = {
    'instansi': [r'nama\s+instansi', r'nama\s+(?:rumah\s+sakit|rs)'],
    'nama_fasilitas': [r'nama\s+fasilitas', r'nama\s+rumah\s+sakit'],
    'alamat': [r'alamat(?:\s+(?:instansi|fasilitas|rumah\s+sakit|lokasi))?'],
    'tube_brand': [r'mer(?:e)?k\s+tabung', r'(?:pabrikan|manufacturer)\s+tabung'],
    'tube_model': [r'(?:model|tipe|type)(?:\s*/\s*(?:tipe|type))?\s+tabung',r'(?:model|tipe|type)\s*\/\s*(?:tipe|type)\s+tabung'],
    'tube_serial': [r'nomor\s+seri\s+tabung', r'no\.?\s*seri\s+tabung', r'tube\s+serial(?:\s+number)?'],
    'unit_brand': [r'pabrikan\s*\/\s*mer[ek]k',r'pabrikan\s*\/\s*merk',r'mer(?:e)?k\s+unit',r'manufacturer(?:\s+unit)?'],
    'unit_model': [r'model\s*\/\s*tipe',r'model\s*\/\s*type',r'tipe\s+unit',r'model\s+unit'],
    'unit_serial': [r'nomor\s+seri(?:\s+unit)?',r'no\.?\s*seri(?:\s+unit)?',r'serial(?:\s+number)?\s+unit'],
}
OTHER = [r'data\s+pemohon\s+uji',r'data\s+pesawat',r'data\s+persyaratan',
         r'generator\s+dan\s+panel\s+kendali',r'wadah\s+tabung',r'lokasi\s+unit',
         r'jenis\s+pesawat',r'tahun\s+pembuatan',r'tipe\s+generator',r'kapasitas\s+maksimum',
         r'nama\s+fasilitas',r'nama\s+instansi',r'alamat',r'merek\s+tabung',r'merk\s+tabung',
         r'nomor\s+seri\s+tabung',r'model\s*\/\s*tipe\s+tabung']
ALL_PATTERNS = [(k,re.compile(r'^\s*(?:\d+\s*[.)]\s*)?(?:'+ '|'.join(v)+r')\s*(?::|\s{2,}|$)',re.I)) for k,v in LABELS.items()]
BOUNDARY = re.compile(r'^\s*(?:[A-D]\s*[.]\s*)?(?:'+ '|'.join(OTHER)+r')\b',re.I)
PHONE = re.compile(r'\b(?:telp?\.?|telepon|phone|fax)\s*[.:]', re.I)

def clean_text(value):
    if value is None:return None
    return re.sub(r'\s+',' ',str(value)).strip(' \t:\n') or None

def extract_pdf_text(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        return '\n'.join(page.get_text('text',sort=True) for page in doc)

def _line_pairs(text):
    """Read `Label: Value`, `Label \n : \n Value`, and inline paired fields.
    Do not concatenate an entire section when a value is missing.
    """
    lines=[x.strip() for x in str(text).splitlines() if x.strip()]
    pairs=[]
    for i,line in enumerate(lines):
        for field,pat in ALL_PATTERNS:
            m=pat.match(line)
            if not m:continue
            tail=line[m.end():].lstrip(' :\t|-')
            if not tail:
                j=i+1
                while j<len(lines) and j<=i+2 and lines[j] in (':','-','|'):j+=1
                if j<len(lines) and j<=i+3 and not BOUNDARY.match(lines[j]):
                    tail=lines[j].lstrip(' :\t|-')
            tail=clean_text(tail)
            if tail and not BOUNDARY.match(tail) and len(tail)<220:
                pairs.append((i,field,tail))
            break
    return lines,pairs

def _section(line):
    l=line.lower()
    if re.search(r'data\s+pemohon|data\s+instansi',l):return 'identity'
    if re.search(r'data\s+pesawat',l):return 'tube'
    if re.search(r'generator\s+dan\s+panel|generator\s+sinar|panel\s+kendali',l):return 'unit'
    if re.search(r'wadah\s+tabung',l):return 'housing'
    return None

def _extract(text):
    lines,pairs=_line_pairs(text)
    contexts=[]; active='identity'
    for line in lines:
        section=_section(line)
        if section: active=section
        contexts.append(active)
    candidates={}
    for index,field,value in pairs:
        context=contexts[index]
        # Weakly scoped generic serials are accepted only in known unit section.
        if field=='unit_serial' and context not in ('unit',):continue
        if field in ('unit_brand','unit_model') and context not in ('unit',):continue
        if field.startswith('tube_') and context not in ('tube','identity'):continue
        if field=='instansi' and context not in ('identity','tube'):continue
        if field=='nama_fasilitas' and context not in ('identity','tube'):continue
        if field=='alamat' and context not in ('identity','tube','unit','housing'):continue
        # An extracted 'value' containing another label is not a clean value.
        if re.search(r'(?i)\b(?:model\s*/\s*tipe|nomor\s+seri|merk\s+tabung|merek\s+tabung)\s*:',value):continue
        if field=='alamat':
            value=PHONE.split(value)[0].rstrip(', ')
        candidates.setdefault(field,[]).append(value)
    # Reassemble soft-wrapped address values from following text lines.
    for idx, field, value in pairs:
        if field != 'alamat' or not re.search(r'(?i)\b(?:jl\.?|jalan)\s+',value):
            continue
        fragments=[value]
        for continuation in lines[idx+1:idx+7]:
            if BOUNDARY.match(continuation) or any(p.match(continuation) for _,p in ALL_PATTERNS):
                break
            if re.match(r'(?i)^(?:data\s+|generator\s+|\d+[.)]\s+pabrikan|lokasi\s+unit)',continuation):
                break
            if len(continuation)>150:break
            fragments.append(continuation.strip(' :'))
            if re.search(r'(?i)\b(?:kode\s*pos\s*:|\d{5}\s*$)',continuation):break
        merged=clean_text(' '.join(fragments))
        merged=PHONE.split(merged)[0].rstrip(', ')
        if merged and len(merged)>len(value)+5:
            candidates['alamat']=[merged]
        break
    def pick(field):
        values=candidates.get(field,[])
        distinct={re.sub(r'\W','',v.casefold()) for v in values}
        return values[0] if len(distinct)==1 else None
    return {'instansi':pick('instansi'),
            'nama_fasilitas':pick('nama_fasilitas') or pick('instansi'),
            'alamat':pick('alamat'),
            'unit':{'merk':pick('unit_brand'),'tipe':pick('unit_model'),'nomor_seri':pick('unit_serial')},
            'tabung':{'merk':pick('tube_brand'),'tipe':pick('tube_model'),'nomor_seri':pick('tube_serial')},
            'candidates':candidates}

def extract_value_after_label(text,label,stop_labels=None):
    # Compatibility with older callers, with bounded line-only extraction.
    pat=re.compile(r'^\s*'+re.escape(label)+r'\s*:?[ \t]*(.+)$',re.I|re.M)
    m=pat.search(text)
    return clean_text(m.group(1)) if m else None

def extract_section(text,start_patterns,end_patterns=None):
    begin=re.search('|'.join(start_patterns),text,re.I)
    if not begin:return None
    remainder=text[begin.end():]
    end=re.search('|'.join(end_patterns),remainder,re.I) if end_patterns else None
    return remainder[:end.start()] if end else remainder

def extract_identity(text):
    d=_extract(text);return {'instansi':d['instansi'],'alamat':d['alamat'],'nama_fasilitas':d['nama_fasilitas']}

def extract_tube_from_data_pesawat(text):return _extract(text)['tabung']
def parse_unit_section(text):
    # Preserve helper for existing tests, injecting the relevant section marker.
    return _extract('Generator dan Panel Kendali Sinar-X\n'+str(text))['unit']
def parse_suitability_text(text):return _extract(text)

def parse_suitability_test(pdf_path):
    from src.extraction.document_reader import read_pages
    pages=read_pages(pdf_path, dpi=180, min_chars=90)
    text='\n'.join(p['text'] for p in pages)
    parsed=parse_suitability_text(text)
    field_values={'instansi':parsed.get('instansi'), 'alamat':parsed.get('alamat'),
                  'unit_brand':parsed.get('unit',{}).get('merk'),
                  'unit_model':parsed.get('unit',{}).get('tipe'),
                  'unit_serial':parsed.get('unit',{}).get('nomor_seri'),
                  'tube_brand':parsed.get('tabung',{}).get('merk'),
                  'tube_model':parsed.get('tabung',{}).get('tipe'),
                  'tube_serial':parsed.get('tabung',{}).get('nomor_seri')}
    missing=[name for name,value in field_values.items() if not value]
    if missing:
        from src.extraction.document_reader import retry_ocr_for_missing
        augmented,diagnostics=retry_ocr_for_missing(pdf_path,pages,missing)
        if diagnostics['retried_pages']:
            retry=parse_suitability_text('\n'.join(pg['text'] for pg in augmented))
            # Only fill missing slots: do not overwrite original determinate values.
            for name in ('instansi','nama_fasilitas','alamat'):
                if not parsed.get(name) and retry.get(name):parsed[name]=retry[name]
            for section in ('unit','tabung'):
                for name in ('merk','tipe','nomor_seri'):
                    if not parsed.get(section,{}).get(name) and retry.get(section,{}).get(name):
                        parsed[section][name]=retry[section][name]
            parsed.setdefault('warnings',[]).append('OCR tambahan digunakan untuk field yang belum terbaca; verifikasi hasil pada dokumen asli.')
        parsed['ocr_completion']=diagnostics
    # Positional extraction on original selectable text; do not override OCR
    # with a less complete source.
    if any(p['method']=='PDF_TEXT' for p in pages):
        parsed=_recover_identity_from_pdf(pdf_path,parsed)
    parsed['page_methods']=[{'page':p['page'],'method':p['method']} for p in pages]
    if not text.strip():
        parsed['warnings']=['Baik teks PDF maupun OCR tidak menghasilkan teks. Semua field belum dapat dipastikan.']
    return parsed


def _recover_identity_from_pdf(pdf_path, result):
    """Recover multi-line address from selectable text without assuming a template.

    Keeps street lines contiguous; never absorbs the next labelled field.
    """
    def has_street(v):
        return bool(re.search(r"(?i)\b(?:jl\.?|jln\.?|jalan)\s+", v or ''))

    def looks_like_field(v):
        return bool(re.match(
            r"(?i)^\s*(?:data\s+|nama\s+|jenis\s+|merk\s+|merek\s+|"
            r"model\s*[/ ]|nomor\s+seri|no\.?\s*seri|lokasi\s+unit|"
            r"generator\b|pabrikan|alamat\s*:|\d+[.)]\s+pabrikan)", v))

    try:
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                text=page.get_text('text',sort=True)
                lines=[x.strip() for x in text.splitlines() if x.strip()]
                for i,line in enumerate(lines):
                    m=re.match(r"(?i)^\s*alamat(?:\s+(?:instansi|fasilitas|rumah\s+sakit))?\s*[:：]?\s*(.*)$",line)
                    if not m:continue
                    parts=[]
                    initial=m.group(1).strip(' :')
                    if has_street(initial):parts.append(initial)
                    # Sometimes ':' is a separate PDF word/line.
                    for cand in lines[i+1:i+7]:
                        cand=cand.strip(' :')
                        if not cand:continue
                        if looks_like_field(cand):break
                        if not parts and not has_street(cand):continue
                        if len(cand)>140:break
                        parts.append(cand)
                        if re.search(r'(?i)\b(?:kode\s*pos\s*:|\d{5}\s*$)',cand):break
                    value=clean_text(' '.join(parts))
                    if value:
                        value=PHONE.split(value)[0].rstrip(', ')
                        old=result.get('alamat')
                        if has_street(value) and (not old or len(value)>len(old)+5):
                            result['alamat']=value
                if result.get('alamat'):break
    except Exception:
        pass
    return result
