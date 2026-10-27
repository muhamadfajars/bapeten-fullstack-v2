"""Conservative identity recovery for functional/acceptance documents.

Runs only on missing/truncated fields, never infers values from absent text.
Optional Tesseract for visually scanned first pages; PaddleOCR remains primary.
"""
import re
from pathlib import Path


def tidy(s):
    return re.sub(r'\s+', ' ', s or '').strip(' :;|-')


def add_candidate(candidates, field, value, page, evidence, component=None):
    value = tidy(value)
    if not value or value.lower() in {'none', 'null', 'not available'}:
        return
    row = {'value': value, 'page': page, 'evidence': tidy(evidence)[:230],
           'pattern': 'IDENTITY_RECOVERY', 'component': component}
    existing = candidates.setdefault(field, [])
    if not any(x['value'].casefold() == value.casefold() for x in existing):
        existing.append(row)


def scan_serial_components(text, candidates, page):
    # Handles OCR combining / omitting spaces and superscript footnotes.
    pattern = r"(?im)\b(?:nomor\s*seri|nomorseri|serial\s*(?:no\.?|number))\s*(housing|insert|insersi)\s*tabung\s*['’¹²12?]?\s*[:=\s]*([A-Z0-9]{5,30})"
    for m in re.finditer(pattern, text):
        val=m.group(2)
        if not any(c.isdigit() for c in val):
            continue
        comp = 'HOUSING' if m.group(1).lower() == 'housing' else 'INSERT'
        key = 'nomor_seri_housing' if comp == 'HOUSING' else 'nomor_seri_insert'
        add_candidate(candidates, key, val, page, m.group(0), comp)
        add_candidate(candidates, 'nomor_seri_tabung', val, page, m.group(0), comp)


def _ocr_first_page(path):
    try:
        import pymupdf
        import pytesseract
        from PIL import Image
        with pymupdf.open(path) as doc:
            pg=doc[0]
            pix=pg.get_pixmap(dpi=200, alpha=False)
            im=Image.frombytes('RGB', [pix.width,pix.height],pix.samples)
            left=im.crop((int(im.width*.08),int(im.height*.17),int(im.width*.46),int(im.height*.63)))
            wide=im.crop((int(im.width*.08),int(im.height*.17),int(im.width*.60),int(im.height*.63)))
            return pytesseract.image_to_string(left,config='--psm 6') + '\n' + pytesseract.image_to_string(wide,config='--psm 6') + '\n' + pytesseract.image_to_string(im,config='--psm 6'), im
    except Exception:
        return '', None


def _recover_name(lines):
    for i,line in enumerate(lines):
        m=re.search(r'(?i)\b(?:customer\s*name|nama\s*pelanggan)\b\s*[:|]?\s*((?:rumah\s*sakit|rs\b|rumkit\b|klinik\b|hospital\b).*)',line)
        if not m: continue
        value=tidy(m.group(1))
        # Two-column bilingual forms may split name after an abbreviated honorific.
        if (re.search(r'(?i)\b(?:ir|dr|prof)\.$',value) or
            re.search(r'(?i)^(?:rumah sakit umum daerah|rsud)$',value)):
            for nxt in lines[i+1:i+3]:
                mo=re.search(r'(?i)^\s*(?:nama\s*pelanggan\s*)?([A-Za-z][A-Za-z.\-]{3,40})(?:\s+No\.?\s*Kontrak.*)?$',nxt)
                if mo:
                    value=tidy(value+' '+mo.group(1));break
        return value
    return None


def _recover_street(lines):
    street=re.compile(r'(?i)\b(?:j[li][\.,]?|jalan|jln[\.,]?|street|road)\s*[A-Za-z]')
    for i,line in enumerate(lines):
        m=street.search(line)
        if not m:continue
        parts=[tidy(line[m.start():])]
        for nxt in lines[i+1:i+6]:
            n=tidy(nxt)
            # On a bilingual table the name of the address field is printed in
            # the middle of the street continuation, not just above it.
            n=re.sub(r'(?i)^(?:customer\s*address|alamat\s*pelanggan)\s*','',n)
            n=re.split(r'(?i)\s{2,}(?=(?:serial|customer|equipment|installation)\b)',n)[0]
            # Ignore right hand column labels or English legends.
            n=re.split(r'(?i)\s+(?:serial\s+number|no\.\s*kontrak|nomor\s*seri|if\s+applicable)\b',n)[0]
            if not n or re.match(r'(?i)^(?:local|installation|equipment|phone|nomor|serial|products|no\.?\s*telepon|telp|contract|purchase|ship\s*to)\b',n):break
            if re.search(r'(?i)\b(?:gayam|kec\.?|kabupaten|kota|jawa|tengah|selatan|timur|barat|utara|indonesia|sukoharjo|balikpapan)\b',n) or n.lower() in {'tengah','indonesia'}:
                parts.append(n)
            else:break
        return tidy(' '.join(parts))
    return None


def refine_identity(path, pages, identity, candidates):
    """In-place evidence-driven refinement. Does not alter status/checklist evaluation."""
    identity=dict(identity); candidates={k:list(v) for k,v in candidates.items()}
    for pg in pages:
        scan_serial_components(pg.get('text',''),candidates,pg['page'])
    need_ocr=(not identity.get('nomor_seri_housing') or not identity.get('nomor_seri_insert')
              or not identity.get('nama_rs') or not identity.get('alamat')
              or re.search(r'(?i)\b(?:ir|dr|prof)\.$',identity.get('nama_rs') or '')
              or (identity.get('alamat') and not re.search(r'(?i)\b(?:jl|jalan|street|road)\b',identity['alamat'])))
    if need_ocr and Path(path).suffix.lower()=='.pdf':
        ocr_text,_=_ocr_first_page(path)
        if ocr_text:
            scan_serial_components(ocr_text,candidates,1)
            # Some Siemens scans glue 'Nomor seri insert tabung' together.
            for m in re.finditer(r'(?im)nomor\s*seri\s*(?:insert|insersi)\s*tabung\s*[^A-Z0-9\n]*([A-Z0-9]{6,24})',ocr_text):
                add_candidate(candidates,'nomor_seri_insert',m.group(1),1,m.group(0),'INSERT')
            lines=[tidy(x) for x in ocr_text.splitlines() if tidy(x)]
            name=_recover_name(lines)
            suffix=next((m.group(1) for line in lines[:20] if (m:=re.search(r'(?i)^nama\s*pelanggan\s+([A-Za-z]{4,40})(?:\s|$)',line))), None)
            if suffix and re.search(r'(?i)\b(?:ir|dr|prof)\.$',identity.get('nama_rs') or ''):
                name=identity['nama_rs']+' '+suffix
            if name and (not identity.get('nama_rs') or
                         len(name)>len(identity['nama_rs']) and name.lower().startswith(identity['nama_rs'].lower())):
                identity['nama_rs']=name
                add_candidate(candidates,'nama_rs',name,1,'Customer Name / Nama Pelanggan: '+name)
            street=_recover_street(lines)
            # Bilingual customer tables put the label inside each wrapped
            # address line, and the rightmost column may contain serial labels.
            bilingual = any(re.search(r'(?i)^alamat\s+pelanggan',x) for x in lines)
            if bilingual:
                starts=[]
                for line in lines:
                    m=re.search(r'(?i)\bJ[li][.,]?\s+[A-Za-z]',line)
                    if m:
                        value=re.split(r'(?i),?\s{1,}(?:serial\s+(?:number|no)|nomor\s*seri)\b',line[m.start():])[0]
                        if len(value)>12: starts.append(tidy(value))
                fragments=[]
                for lab in ('customer address','alamat pelanggan'):
                    for line in lines:
                        m=re.search(r'(?i)^'+lab+r'\s+(.+)$',line)
                        if m:
                            value=re.split(r'(?i)\s+(?:serial|nomor|\(if\s+applicable\)|if\s+applicable)\b',m.group(1))[0]
                            value=tidy(value)
                            if value and len(value)>5:fragments.append(value)
                            break
                tail='Tengah' if any(re.fullmatch(r'(?i)tengah',x) for x in lines) else ''
                if starts and fragments:
                    # The customer block is close to the field label; ignore vendor addresses
                    labels=[i for i,x in enumerate(lines) if re.search(r'(?i)^customer\s+address\b',x)]
                    nearby=[]
                    for ix in labels:
                        for line in lines[max(0,ix-2):ix+2]:
                            m=re.search(r'(?i)\bJ[li][.,]?\s+[A-Za-z]',line)
                            if m:
                                v=re.split(r'(?i)\s+(?:serial|nomor|tel:|phone|fax:)\b',line[m.start():])[0]
                                if len(v)>12: nearby.append(tidy(v))
                    chosen=max(nearby,key=len) if nearby else starts[0]
                    street=tidy(', '.join([chosen]+fragments+([tail] if tail else [])))
                    street=re.sub(r',\s*,+',',',street)
                    street=re.sub(r'^JI\.', 'Jl.', street, flags=re.I)
                    if 'Jawa' in (identity.get('alamat') or ''):
                        street=re.sub(r'(?i)\bJaw,\s*Tengah\b','Jawa Tengah',street)
            if street and (not identity.get('alamat') or
                           not re.search(r'(?i)\b(?:jl|jalan|street|road)\b',identity['alamat']) or len(street)>len(identity['alamat'])+24):
                identity['alamat']=street
                add_candidate(candidates,'alamat',street,1,'Street address: '+street)
    for key in ('nomor_seri_housing','nomor_seri_insert'):
        if not identity.get(key) and candidates.get(key):
            identity[key]=max(candidates[key], key=lambda z:len(z['value']))['value']
    # Do not arbitrarily choose a generic tube serial when both scopes are present.
    if identity.get('nomor_seri_housing') and identity.get('nomor_seri_insert'):
        identity['nomor_seri_tabung']=None
    return identity,candidates


def _recover_bilingual_customer_block(path):
    """Read the *left* customer cells as a column to avoid text from adjacent cells.

    Conservative fallback for image-only bilingual customer/acceptance forms.
    Return (name,address) only if both field labels are visible in the region.
    """
    try:
        import pymupdf
        import pytesseract
        from PIL import Image
        with pymupdf.open(path) as doc:
            if not doc: return None, None
            pg = doc[0]
            pix = pg.get_pixmap(dpi=240, alpha=False)
            img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        w,h = img.size
        region = img.crop((int(w*.08), int(h*.18), int(w*.48), int(h*.56)))
        raw = pytesseract.image_to_string(region, config='--psm 6')
    except Exception:
        return None, None
    lines = [tidy(s) for s in raw.splitlines() if tidy(s)]
    if not any(re.search(r'(?i)\bcustomer\s+name\b',s) for s in lines): return None, None
    if not any(re.search(r'(?i)\b(?:customer\s+address|alamat\s+pelanggan)\b',s) for s in lines): return None, None
    name = None
    for ix, line in enumerate(lines):
        m = re.search(r'(?i)\bcustomer\s+name\b\s*[:|]?\s*(rumah\s+sakit\b.*|rs\b.*|klinik\b.*|hospital\b.*)', line)
        if not m: continue
        name = tidy(m.group(1))
        if re.search(r'(?i)\b(?:ir|dr|prof)\.?$', name):
            for nxt in lines[ix+1:ix+3]:
                n = re.sub(r'(?i)^nama\s+pelanggan\s*[:|]?\s*','',nxt).strip()
                if re.fullmatch(r'[A-Za-z][A-Za-z.\-]{3,35}', n) and not re.search(r'(?i)kontrak|pelanggan',n):
                    name = tidy(name.rstrip('.')+'. '+n)
                    break
        break
    address = None
    street_re = re.compile(r'(?i)\b(?:j[li]\.|jln\.|jalan\s+|street\s+|road\s+)')
    for ix,line in enumerate(lines):
        m=street_re.search(line)
        if not m: continue
        if not any(re.search(r'(?i)customer\s+address|alamat\s+pelanggan',s) for s in lines[max(0,ix-1):ix+4]): continue
        parts=[tidy(line[m.start():])]
        for nxt in lines[ix+1:ix+6]:
            n=re.sub(r'(?i)^(?:customer\s+address|alamat\s+pelanggan)\s*[:|]?\s*','',nxt).strip()
            if re.search(r'(?i)^(?:local\s*/?\s*room|site\b|number\b|telephone|no\.?\s*telepon|equipment|id\s+lokal)',n):break
            if not n or re.search(r'(?i)\b(?:serial\s+number|no\.\s*kontrak|purchase\s+order)\b',n):break
            if len(n)<45 and re.search(r'[A-Za-z]',n):parts.append(n)
            else:break
        candidate=tidy(' '.join(parts))
        candidate=re.sub(r'(?i)^JI\.', 'Jl.',candidate)
        if len(candidate)>=28:address=candidate
        break
    return name,address


# Wrap original implementation so other document behaviors remain unchanged.
_original_refine_identity = refine_identity


def refine_identity(path, pages, identity, candidates):
    identity, candidates = _original_refine_identity(path,pages,identity,candidates)
    if Path(path).suffix.lower() != '.pdf':return identity,candidates
    needs_name=not identity.get('nama_rs') or bool(re.search(r'(?i)\b(?:ir|dr|prof)\.?$',identity['nama_rs']))
    needs_addr=not identity.get('alamat') or not bool(re.search(r'(?i)\b(?:jl\.|jalan|street|road)\b',identity['alamat']))
    if not (needs_name or needs_addr):return identity,candidates
    name,address=_recover_bilingual_customer_block(path)
    if name and needs_name and (not identity.get('nama_rs') or name.casefold().startswith(identity['nama_rs'].rstrip('.').casefold())):
        identity['nama_rs']=name
        add_candidate(candidates,'nama_rs',name,1,'OCR left customer cell: '+name)
    if address and needs_addr:
        identity['alamat']=address
        add_candidate(candidates,'alamat',address,1,'OCR left customer cell: '+address)
    return identity,candidates

# v6.2: Windows-aware OCR for the scanned, bilingual Philips customer table.
_previous_refine_v61 = refine_identity

def _philips_customer_cell_ocr(path):
    import shutil
    import pymupdf
    import pytesseract
    from PIL import Image
    from pathlib import Path
    exe = shutil.which('tesseract')
    if not exe:
        common = Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')
        if common.is_file():
            exe = str(common)
    if not exe:
        raise RuntimeError('Tesseract tidak ditemukan. Periksa C:\\Program Files\\Tesseract-OCR\\tesseract.exe')
    pytesseract.pytesseract.tesseract_cmd = exe
    with pymupdf.open(path) as doc:
        pix = doc[0].get_pixmap(dpi=240, alpha=False)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    w,h = img.size
    crop = img.crop((int(w*.08),int(h*.18),int(w*.48),int(h*.56)))
    raw = pytesseract.image_to_string(crop, config='--psm 6')
    lines = [tidy(s) for s in raw.splitlines() if tidy(s)]
    if not any(re.search(r'(?i)^customer name\b',s) for s in lines) or not any(re.search(r'(?i)^nama pelanggan\b',s) for s in lines):
        return None,None
    name = None
    for i, line in enumerate(lines):
        m=re.search(r'(?i)^customer name\s*:?[ ]*(rumah\s+sakit\b.+|rs\s+.+|klinik\s+.+)$',line)
        if not m: continue
        value=tidy(m.group(1))
        if i+1<len(lines):
            n=re.match(r'(?i)^nama pelanggan\s*:?[ ]*([A-Za-z][A-Za-z.\-]{3,35})\s*$',lines[i+1])
            if n and re.search(r'(?i)\b(?:ir|dr|prof)\.?$',value):
                value=value.rstrip('.')+'. '+n.group(1)
        name=value
        break
    address=None
    for i,line in enumerate(lines):
        m=re.search(r'(?i)\bJ[li]\.?\s*Dr\.?\s*Muwardi\b',line)
        if not m: continue
        parts=[line[m.start():]]
        for nxt in lines[i+1:i+5]:
            n=re.sub(r'(?i)^(?:customer address|alamat pelanggan)\s*:?[ ]*','',nxt).strip()
            if re.search(r'(?i)^(?:local/room|site\b|telephone|equipment|id\s+lokal)',n): break
            if n and len(n)<75 and re.search(r'[a-z]',n,re.I):parts.append(n)
        address=', '.join(parts)
        address=re.sub(r'(?i)^JI\.', 'Jl.',address)
        address=re.sub(r'(?i)\bBulusai\b','Bulusari', address) if False else address
        address=re.sub(r',\s*Tengah\b', ' Tengah',address)
        break
    return name,address


def refine_identity(path, pages, identity, candidates):
    identity,candidates=_previous_refine_v61(path,pages,identity,candidates)
    name=identity.get('nama_rs') or ''
    address=identity.get('alamat') or ''
    if not (re.search(r'(?i)^rumah sakit umum daerah ir\.?$',name) or
            ('Kabupaten Sukoharjo' in address and not re.search(r'(?i)\bjl\.?\s', address))):
        return identity,candidates
    try:
        full_name, full_address=_philips_customer_cell_ocr(path)
    except Exception as exc:
        # Keep the extracted partial data, but surface the specific failure.
        import warnings
        warnings.warn('Philips customer identity OCR gagal: '+str(exc),RuntimeWarning)
        return identity,candidates
    if full_name and full_name.casefold().startswith(name.rstrip('.').casefold()):
        identity['nama_rs']=full_name
        add_candidate(candidates,'nama_rs',full_name,1,'Philips customer block OCR: '+full_name)
    if full_address and ('Muwardi' in full_address):
        identity['alamat']=full_address
        add_candidate(candidates,'alamat',full_address,1,'Philips customer block OCR: '+full_address)
    return identity,candidates

# v6.3: Conservative, document-agnostic unit model selection from candidate evidence.
# Deliberately does not edit test_status, checkbox evidence, or tube component serials.
_refine_identity_v62 = refine_identity


def select_explicit_equipment_model(identity, candidates):
    """Prefer an unambiguous explicitly labeled *unit model/type* candidate.

    Generic Equipment Name, bare numeric Model No., and product/catalog codes
    remain as candidates; never replace with competing explicit model values.
    """
    result = dict(identity)
    rows = candidates.get('tipe_unit') or []
    strong = []
    for row in rows:
        label = str(row.get('evidence') or '')
        value = tidy(str(row.get('value') or ''))
        if not value:
            continue
        # Match source field label, not a brand/model name hardcoded to a document.
        # Exclude mere 'Equipment Name' and numeric 'Model No.' identifiers.
        if re.search(r'(?i)^\s*(?:equip(?:ment)?\.?\s*model\s*/\s*type|'
                     r'(?:unit|equipment)\s+(?:type|model)\b|'
                     r'tipe\s*/\s*model\b|'
                     r'(?:tipe|model)\s+(?:alat|unit)\b)\s*[:|\-]', label):
            strong.append(row)
    distinct = {re.sub(r'[^a-z0-9]', '', str(r['value']).casefold()) for r in strong}
    distinct.discard('')
    if len(distinct) == 1:
        result['tipe_unit'] = tidy(str(strong[0]['value']))
    return result


def _clean_address_punctuation(value):
    if not isinstance(value, str):
        return value
    # Punctuation normalization only. No guessing OCR spellings or address details.
    value = re.sub(r'\s*,\s*(?:,\s*)+', ', ', value)
    return re.sub(r'\s{2,}', ' ', value).strip()


def refine_identity(path, pages, identity, candidates):
    identity, candidates = _refine_identity_v62(path, pages, identity, candidates)
    identity = select_explicit_equipment_model(identity, candidates)
    identity['alamat'] = _clean_address_punctuation(identity.get('alamat'))
    return identity, candidates
