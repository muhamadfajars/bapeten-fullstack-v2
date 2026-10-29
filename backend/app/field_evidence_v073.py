"""v0.7.3 narrow evidence fixes, additive after v0.7.2.

Does not modify OCR model, global normalization, lifecycle, or previously
correct unrelated fields. Evidence is from the SAME uploaded document.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unicodedata

from .evidence_cohesion_v072 import (_anchor_pages, _pages, BRAND_RE,
                                      UNIT_MODEL_RE, FACILITY_RE,
                                      facility_equivalent, _simple, _text)

SPEC_FIELD = re.compile(r'(?i)^\s*pemilihan\s+peralatan\s*$')
GENERIC_NAME = {'', 'rumah sakit', 'rumah sakit jiwa', 'rs', 'klinik', '-', '—', 'none', 'null'}


def _s(value):
    return ' '.join(str(value or '').split())


def _tok(value):
    return ''.join(re.findall('[a-z0-9]', unicodedata.normalize('NFKC', str(value or '')).casefold()))


def _good_match(row):
    return (str(row.get('status') or '').upper() == 'MATCH' and
            float(row.get('score') or 0) >= 99 and
            _tok(row.get('expected')) == _tok(row.get('observed')))


def _brand_value(value):
    """Remove field-label remnants; split brand/corporate manufacturer ONLY.

    Do not assume that any two names separated by slash are interchangeable.
    """
    s = _s(value).strip(' :;|,')
    s = re.sub(r'(?i)^(?:pesawat\s*)?sinar\s*[- ]?\s*x\s*[:\-]\s*', '', s)
    s = re.sub(r'(?i)^(?:merek|merk)\s*(?:unit|pesawat)?\s*[:\-]\s*', '', s)
    s = re.split(r'(?i)\s+(?:no\.?\s*seri|nomor\s*seri|tipe\s*unit|model\s*unit)\s*:', s, maxsplit=1)[0]
    pair = re.match(r'^(.+?)\s*/\s*(.+)$', s)
    if pair:
        left,right = (_s(pair.group(i)) for i in (1,2))
        if re.search(r'(?i)\b(?:pvt\.?|ltd\.?|limited|electric|industries|corporation|inc\.?|manufactur\w*|india|indonesia)\b', right):
            s = left
        else:
            # Two actual brands / ambiguous slash: do not turn this into a match.
            return ''
    s = s.strip(' :;|,')
    if (not s or len(s) > 55 or len(s.split()) > 5 or
        re.search(r'(?i)\b(?:no\.?|serial|nomor|tahun|tanggal|alamat|telp|fax|www|http)\b',s)):
        return ''
    if re.match(r'(?i)^(?:sinar\s*-?x|merek|merk|pesawat|tabung)\s*$',s):
        return ''
    return s


def _brand_labels(content):
    """Exact label match, not incidental vendor headers / tube manufacturer."""
    lines=[_s(x) for x in str(content).splitlines() if _s(x)]
    labels = re.compile(
        r'(?i)^\s*(?:merek|merk)\s*'
        r'(?:/\s*pabrikan\s*|(?:\s+(?:unit|generator|pesawat(?:\s+sinar\s*[- ]?\s*x)?))\s*)'
        r'\s*[:\-]?\s*(.*)$'
    )
    results=[]
    for i,line in enumerate(lines):
        match=labels.match(line)
        if not match:continue
        raw=match.group(1).strip(' :;-')
        if not raw:
            # PDF text extraction often splits the table value or ':' into
            # separate text lines. Search at most three subsequent lines, and
            # stop at the next labeled field rather than stealing its value.
            for next_line in lines[i+1:i+4]:
                if re.match(r'(?i)^(?:tipe|type|model|serial|nomor|no\.?\s*seri|merek|merk|tahun|tanggal)\b',next_line):
                    break
                val_candidate=_brand_value(next_line.lstrip(': ').strip())
                if val_candidate:
                    raw=val_candidate
                    break
        val=_brand_value(raw)
        if val: results.append((val, line[:200]))
    return results


def repair_unit_brand(rows, pages):
    """Use the same model+serial anchor already proven in v072.

    Never search all pages for a reference brand and declare a match.
    """
    for row in rows:
        if not isinstance(row,dict):continue
        match=BRAND_RE.fullmatch(_s(row.get('field')))
        if not match or _good_match(row):continue
        anchors=_anchor_pages(pages,rows,match.group(1))
        if not anchors:continue
        best=anchors[0][1]
        candidates=[]
        for pg,text in pages:
            if not isinstance(pg,int) or abs(pg-best)>1:continue
            for val,quote in _brand_labels(text):
                candidates.append((abs(pg-best),pg,val,quote))
        if not candidates:continue
        closest=min(x[0] for x in candidates)
        nearest=[x for x in candidates if x[0]==closest]
        if len({_tok(x[2]) for x in nearest}) != 1: continue
        _,pg,val,quote=nearest[0]
        if not row.get('expected'):continue
        same=_tok(val)==_tok(row['expected'])
        row.update(observed=val,page=pg,quote=quote,
                   status='MATCH' if same else 'MISMATCH',
                   score=100.0 if same else round(100*SequenceMatcher(None,_simple(row['expected']),_simple(val)).ratio(),1),
                   note='Merek dari field berlabel pada halaman alat yang dibuktikan oleh model dan nomor seri.')
    return rows


def _page_ocr(path: Path, index, fraction=1.0, psm=6, clip_box=None):
    """One bounded OCR of a relevant region only, CPU tesseract if installed.

    Fail closed: no invented data and no change on missing binary/OCR error.
    """
    if os.environ.get('BAPETEN_EVIDENCE_TARGETED_OCR','1').strip().lower() in ('0','false','no'):
        return ''
    if path.suffix.lower() != '.pdf':return ''
    try:
        import fitz
        with fitz.open(str(path)) as pdf:
            if index<0 or index>=len(pdf):return ''
            page=pdf[index]
            clip=(fitz.Rect(*clip_box) if clip_box is not None else
                  fitz.Rect(0,0,page.rect.width,page.rect.height*min(1,max(.1,fraction))))
            pix=page.get_pixmap(matrix=fitz.Matrix(3.0 if clip_box else 2.2,3.0 if clip_box else 2.2),
                                clip=clip,alpha=False)
        with tempfile.TemporaryDirectory(prefix='bapeten_ocr_') as tmp:
            output = Path(tmp) / 'crop.png'
            pix.save(str(output))
            tess_lang = os.getenv('BAPETEN_TESS_LANG', 'ind+eng')
            run=subprocess.run(['tesseract',str(output),'stdout','--psm',str(psm),'-l',tess_lang],
                               stdin=subprocess.DEVNULL,capture_output=True,text=True,
                               timeout=25,check=False)
            if run.returncode != 0 and tess_lang != 'eng':
                run=subprocess.run(['tesseract',str(output),'stdout','--psm',str(psm),'-l','eng'],
                                   stdin=subprocess.DEVNULL,capture_output=True,text=True,
                                   timeout=25,check=False)
            return run.stdout[:30000] if run.returncode==0 else ''
    except Exception:
        return ''


def _source_facilities(text, page):
    """Strongly labeled facility names, with a verbatim source value."""
    lines=[_s(v) for v in str(text).splitlines() if _s(v)]
    out=[]
    label=re.compile(r'(?i)^\s*(?:instansi|nama\s+(?:instansi|fasilitas|rumah\s+sakit)|customers?|customer\s*name|rumah\s+sakit\s*/\s*klinik)\s*[:\-]?\s*(.+?)\s*$')
    practice=re.compile(r'(?i)\bdi\s+((?:RSJ|RSUD|RS|Rumkit|Rumah\s+Sakit)\.?\s+.+?)(?=\s+(?:Jl\.?|Jalan|sebagai|untuk|No\.?\s*\d)|$)')
    for line in lines:
        m=label.match(line)
        if m:
            val=_s(m.group(1)).strip(' :-|')
            # OCR of two-column tables may merge the next field horizontally.
            val=re.split(r'(?i)\s+(?:equipment\s+name|serial\s+no\.?|installation\s+date|address|alamat|tanggal|no\.?\s*seri|contact\s+person)\s*[:;_\-|]*', val, maxsplit=1)[0].strip(' :-|')
            if len(val)>5 and len(val)<100:out.append((page,val,line[:220]))
        m=practice.search(line)
        if m:
            val=_s(m.group(1)).strip(' ,:;.-')
            if len(val)>5 and len(val)<100:out.append((page,val,line[:220]))
    return out


def _weak_name(row):
    if not FACILITY_RE.fullmatch(_s(row.get('field'))):return False
    if str(row.get('status') or '').upper() == 'MISMATCH':return False
    observed=_simple(row.get('observed'))
    return observed in GENERIC_NAME or observed=='rsj' or not _s(row.get('observed'))


def rescue_facility(rows,pages,path:Path, allow_ocr=True):
    weak=[r for r in rows if isinstance(r,dict) and _weak_name(r)]
    if not weak:return rows
    candidates=[]
    for pg,content in pages[:5]:candidates+=_source_facilities(content,pg)
    def apply_candidate(row):
        good=[x for x in candidates if facility_equivalent(row.get('expected'),x[1])]
        if not good:return False
        # Conflicting explicit employer/customer names in the SAME source make
        # the document ambiguous. Do not cherry-pick only the matching name.
        explicit=[x for x in candidates if re.match(r'(?i)^\s*(?:instansi|nama\s+(?:instansi|fasilitas|rumah\s+sakit)|customers?)\s*[:\-]',x[2])]
        for _,other,_ in explicit:
            if re.match(r'(?i)^(?:rsj|rsud|rsu|rs\.?|rumkit|rumah\s+sakit|klinik)',other) and not facility_equivalent(row.get('expected'),other):
                return False
        page,name,quote=min(good,key=lambda x: (x[0] if isinstance(x[0],int) else 999))
        row.update(observed=name, status='MATCH',score=100.0,quote=quote,
                   note='Nama fasilitas lengkap ditemukan pada field instansi/penugasan dalam dokumen yang sama.')
        if isinstance(page,int):row['page']=page
        return True
    missing=[r for r in weak if not apply_candidate(r)]
    if missing and allow_ocr:
        text=_page_ocr(path,0,fraction=1.0,psm=6)
        if text:candidates+=_source_facilities(text,1)
        for r in missing:apply_candidate(r)
    return rows


def _model_key(value):
    s=_s(value)
    s=re.sub(r'\s*\([^)]*\)\s*$','',s)
    z=_tok(s)
    return z if len(z)>5 and re.search(r'\d',z) else ''


def _model_in_ocr(model, text):
    """Bounded model identifier; tolerate whitespace/hyphen, not changed suffix."""
    val=_model_key(model)
    if not val:return None
    for line in text.splitlines():
        if val in _tok(line):
            # Return only the source substring, never the form value.
            parts=re.findall(r'[A-Za-z0-9][A-Za-z0-9\- ]{3,}',line)
            for part in parts:
                for m in re.finditer(r'(?i)\b(?:DR\s*[- ]?XD\s*[- ]?\d{3,5}|\w{2,10}\s*[- ]?\w*\d{3,5})\b',part):
                    if _tok(m.group(0))==val:return (m.group(0),line[:220])
    return None


def _serial_in_text(serial,text):
    key=_tok(serial)
    if len(key)<6:return False
    return bool(re.search(r'(?<![A-Za-z0-9])'+r'\s*[-.\s]*'.join(re.escape(c) for c in key)+r'(?![A-Za-z0-9])',text,flags=re.I))


def repair_acceptance(rows,pages,path:Path, source_hint=""):
    """Only Acceptance-Test PDFs with a verified equipment model+serial pair.

    Repair type/facility, NOT address, serial, brands, or unrelated categories.
    """
    relevant=[r for r in rows if isinstance(r,dict) and UNIT_MODEL_RE.fullmatch(_s(r.get('field')))]
    if not relevant or path.suffix.lower()!='.pdf':return rows
    if all(_good_match(r) for r in relevant) and not any(isinstance(r,dict) and _weak_name(r) for r in rows):
        return rows
    from .evidence_cohesion_v072 import UNIT_SERIAL_RE
    texts=[(pg,t) for pg,t in pages[:2]]
    if not (re.search(r'(?i)\bACCEPTANCE\s+TEST\b','\n'.join(t for _,t in texts))
            or re.search(r'(?i)acceptance|uji[ _-]*fungsi',path.name + ' ' + source_hint)):
        return rows
    # Existing text layer can be corrupt. OCR only the TOP of first 2 pages.
    ocr=[]
    for i in range(min(2,len(pages))):
        text=_page_ocr(path,i,fraction=.38,psm=6)
        if text:ocr.append((i+1,text))
    joined='\n'.join(x[1] for x in texts+ocr)
    if not re.search(r'(?i)\bACCEPTANCE\s+TEST\b',joined):return rows
    for row in relevant:
        if _good_match(row):continue
        match=UNIT_MODEL_RE.fullmatch(_s(row.get('field')))
        linked=[r for r in rows if isinstance(r,dict) and UNIT_SERIAL_RE.fullmatch(_s(r.get('field'))) and
                UNIT_SERIAL_RE.fullmatch(_s(r.get('field'))).group(1)==match.group(1)]
        if not linked:continue
        serial=linked[0].get('observed') or linked[0].get('expected')
        if not serial or not _serial_in_text(serial,joined):continue
        hits=[]
        for pg,content in ocr+texts:
            got=_model_in_ocr(row.get('expected'),content)
            if got:hits.append((pg,got[0],got[1]))
        if not hits:continue
        pg,value,quote=hits[0]
        row.update(observed=value,status='MATCH',score=100.0,page=pg,quote=quote,
                   note='Model unit ditemukan pada Acceptance Test dan dikaitkan dengan nomor seri yang sama.')
    # Personnel identity rescue: only if a labeled Customers value exists.
    rescue_facility(rows,ocr+texts,path,allow_ocr=False)
    return rows


def repair_specification(rows,pages,path:Path):
    """Show scan-source evidence in the existing review field, not a made-up MATCH.

    For pages without text, OCR isolated logo and specification heading regions.
    No mapping from the application-form reference into the document value.
    """
    targets=[r for r in rows if isinstance(r,dict) and SPEC_FIELD.fullmatch(_s(r.get('field')))
             and not _s(r.get('observed')).strip('—-')]
    if not targets or path.suffix.lower()!='.pdf':return rows
    text=pages[0][1] if pages else ''
    maker,product_line=None,None
    if re.search(r'(?i)\bspesifikasi\b',text):
        names=[_s(line) for line in text.splitlines() if _s(line)]
        head=next((re.search(r'(?i)\bspesifikasi\s+([A-Z0-9][A-Z0-9 /\-]{2,40})',line) for line in names
                   if re.search(r'(?i)spesifikasi',line)),None)
        logo=next((n for n in names[:8] if re.fullmatch(r'[A-Z][A-Z0-9&.\-]{3,}',n)),None)
        if head and logo:maker,product_line=logo,head.group(1)
    if not maker or not product_line:
        try:
            import fitz
            with fitz.open(str(path)) as d:width,height=d[0].rect.width,d[0].rect.height
            # Logo top-left; specification title top-centre. PSM choices tested
            # on the scanned FDR Nano PDF, with no OCR on the remaining table.
            left=_page_ocr(path,0,psm=11,clip_box=(0,0,width*.29,height*.15))
            centre=_page_ocr(path,0,psm=6,clip_box=(width*.24,0,width*.76,height*.12))
        except (ImportError,OSError,ValueError,RuntimeError):
            return rows
        logo=next((n.strip() for n in left.splitlines() if re.fullmatch(r'[A-Z][A-Z0-9&.\-]{3,}',n.strip())),None)
        title=re.search(r'(?i)\bSPESIFIKAS[I|1]\s+([A-Z0-9][A-Z0-9 /\-]{2,40})',centre)
        if not logo or not title:return rows
        maker,product_line=logo,title.group(1)
    product_line=_s(product_line).strip(' -:|')
    if len(product_line)<3 or len(product_line)>38:return rows
    for row in targets:
        row.update(observed=f'{maker} / {product_line}',score=None,status='REVIEW',page=1,
                   quote=f'{maker} — SPESIFIKASI {product_line}',
                   note='Merek dan lini produk terbaca dari dokumen, tetapi model unit lengkap belum dibuktikan.')
    return rows


def improve(rows,document_path,category=None,subtype=None,filename=None):
    if not isinstance(rows,list):return rows
    path=Path(document_path)
    if not path.is_file():return rows
    relevant=any(isinstance(r,dict) and (BRAND_RE.fullmatch(_s(r.get('field'))) or
                 UNIT_MODEL_RE.fullmatch(_s(r.get('field'))) or
                 SPEC_FIELD.fullmatch(_s(r.get('field'))) or _weak_name(r)) for r in rows)
    if not relevant:return rows
    pages=_pages(path)
    if not pages:return rows
    repair_unit_brand(rows,pages)
    meta=' '.join(str(x or '') for x in (category,subtype,filename))
    repair_acceptance(rows,pages,path,meta)
    repair_specification(rows,pages,path)
    # Only personnel-category weak identities get a full first-page OCR fallback.
    # Otherwise stick to the existing fast text layer (no surprise 20x OCR).
    personel=bool(re.search(r'(?i)personel|penunjukan|surat\s+izin|surat\s+perintah|petugas|sikr|\bsip\b',meta))
    rescue_facility(rows,pages,path,allow_ocr=personel)
    return rows
