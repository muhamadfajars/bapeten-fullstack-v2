"""Document-aware extractor for Uji Fungsi / Acceptance / Verification records.
No PASS guarantee is inferred from OCR coverage or isolated keywords.
Supports scans via project PaddleOCR adapter; pytesseract is a local fallback.
"""
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pymupdf as fitz
import numpy as np
import cv2

FIELDS = ('nama_rs', 'alamat', 'tipe_unit', 'nomor_seri_unit',
          'tipe_tabung', 'nomor_seri_tabung', 'nomor_seri_housing', 'nomor_seri_insert')
LABELS = {
 'nama_rs': [r'hospital\s*name',r'customer\s*name',r'nama\s*instansi',r'nama\s*pelanggan',r'pelanggan',r'hospital(?!\s+power)',r'ship\s*to',r'customer\s*name'],
 'alamat': [r'customer\s*address',r'alamat\s*(?:instansi|pelanggan|rumah\s*sakit)?',r'address',r'location\s*address'],
 'tipe_unit':[r'unit\s*type',r'equipment\s*name',r'equip\.?\s*model\s*/?\s*type',r'equipment\s*model',r'product\s*name',r'device\s*model',r'nama\s*alat',r'tipe\s*/?\s*model',r'model\s*(?:unit|no\.?|number)',r'model\s*pesawat'],
 'nomor_seri_unit':[r'serial\s*number\s*generator',r'nomor\s*seri\s*alat',r'nomor\s*seri\s*unit',r'device\s*serial\s*no',r'serial\s*(?:number|no\.?|n[o0]\.?)',r'ser\.?\s*no\.?',r'system\s*s/?n',r'no\.?\s*seri\s*alat'],
 'tipe_tabung':[r'tube\s*(?:insert\s*)?(?:model|type)',r'(?:insert|tube\s*housing)\s*model',r'tipe\s*tabung',r'model\s*tabung'],
 'nomor_seri_tabung':[r'(?:tube\s*housing|housing\s*tube)\s*(?:serial|s/?n|no\.?\s*seri)',r'(?:tube\s*insert|insert\s*tube)\s*(?:serial|s/?n|no\.?\s*seri)',r'(?:nomor\s*seri\s*(?:housing|insert)\s*tabung)',r'(?:nomor\s*seri\s*tabung)',r'(?:serial\s*number\s*tube\s*head\s*sinar\s*[-–]?\s*x)',r'(?:serial\s*number\s*insersi)',r'(?:tube|x\s*ray\s*tube)\s*s/?n',r'nomor\s*seri\s*housing\s*tabung',r'nomor\s*seri\s*insert\s*tabung'],
}
P = {field:[re.compile(r'(?<!\w)(?:'+q+r')(?!\w)',re.I) for q in pats] for field,pats in LABELS.items()}
TRIM_NEXT = re.compile(r'^(?:hospital\s+information|hospital\s+power|unit\s+information|work\s+details|equipment\s+details|data\s+unit|data\s+instansi|page\s*\d|date|phone|telephone|engineer|contact|report|installation|functional\s+test|safety\s+check|customer\s+contract|product\s+number|serial\s+number|alamat|nama\s+instansi)\b',re.I)
SERIAL_RE = re.compile(r'^[A-Z0-9][A-Z0-9._\-/]{2,35}$',re.I)
BANNED = re.compile(r'^(?:none|no|yes|pass|fail|ok|ng|n/?a|available|not\s+available|date|type|name|number|address|model)$',re.I)

def norm_line(s):
 return re.sub(r'[^a-z0-9]+','',str(s).casefold())

def clean(s):
 s=unicodedata.normalize('NFKC',str(s or ''))
 return re.sub(r'\s+',' ',s).strip(' \t:|;')

def _boxes_to_lines(items):
 # PaddleOCR output already in rough reading order; keep individual lines.
 return [clean(x.get('text')) for x in items if clean(x.get('text'))]

def _ocr_image(img):
 try:
  from src.extraction.label_ocr import extract_ocr
  return _boxes_to_lines(extract_ocr(img))
 except (ImportError, ModuleNotFoundError):
  try:
   import pytesseract
   return [clean(x) for x in pytesseract.image_to_string(img,config='--psm 11').splitlines() if clean(x)]
  except ImportError as e:
   raise RuntimeError('PaddleOCR adapter or pytesseract is required for scan OCR') from e

def _is_garbled(s):
 chars=[c for c in s if not c.isspace()]
 if not chars: return True
 bad=sum((ord(c)>127 and not c.isalpha()) or c in '鮮舅瑕饉鑽鬱彎' for c in chars)
 ascii_words=re.findall(r'[A-Za-z]{3,}',s)
 cjk=sum('\u3400'<=c<='\u9fff' for c in chars)
 return cjk>2 or bad/len(chars)>0.12 or (len(s)>250 and len(ascii_words)<12)

def read_document(path,dpi=170,force_ocr=False):
 path=str(path)
 ext=Path(path).suffix.lower()
 pages=[]
 if ext=='.pdf':
  with fitz.open(path) as pdf:
   for i,page in enumerate(pdf):
    raw=page.get_text('text',sort=True)
    use_ocr=force_ocr or len(raw.strip())<90 or _is_garbled(raw)
    if use_ocr:
     pix=page.get_pixmap(dpi=dpi,alpha=False,colorspace=fitz.csRGB)
     img=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
     lines=_ocr_image(cv2.cvtColor(img,cv2.COLOR_RGB2BGR)); method='OCR'
    else:
     lines=[clean(x) for x in raw.splitlines() if clean(x)]; method='PDF_TEXT'
    pages.append({'page':i+1,'method':method,'lines':lines,'text':'\n'.join(lines),'char_count':len('\n'.join(lines))})
 elif ext in {'.jpg','.jpeg','.png','.bmp','.webp'}:
  arr=np.fromfile(path,dtype=np.uint8);img=cv2.imdecode(arr,cv2.IMREAD_COLOR)
  if img is None:raise ValueError('Cannot read image')
  lines=_ocr_image(img)
  pages=[{'page':1,'method':'OCR','lines':lines,'text':'\n'.join(lines),'char_count':len('\n'.join(lines))}]
 else:raise ValueError('Supported formats: PDF, JPG, JPEG, PNG, BMP, WEBP')
 return pages

def _candidate(field,value,page,evidence,pattern,component=None):
 value=clean(value)
 if not value or BANNED.fullmatch(value) or len(value)>180:return None
 if field.startswith('nomor_seri'):
  if re.match(r'^(?:tube|insersi|insert|housing|generator|unit)\b',value,re.I): return None
  value=value.split()[0].strip(' \t,;:()')
  if not SERIAL_RE.fullmatch(value) or not any(c.isdigit() for c in value):return None
 elif field.startswith('tipe_'):
  if len(value)<3 or re.match(r'^(?:data|status|result|inspection|serial\s*(?:number|no)|model\s*no|type\s*/\s*no)\b',value,re.I):return None
 else:
  if len(value)<4 or re.search(r'(?i)^(?:acceptance form|ref\.? no|contract|purchase|order|quotation|room|installation|equipment|service|hospital information|company|no\.? kontrak|if applicable|nama pelanggan)\b',value):return None
 return {'value':value,'page':page,'evidence':clean(evidence)[:230], 'pattern':pattern,'component':component}

def extract_candidates(pages):
 found=defaultdict(list)
 for pg in pages:
  lines=pg['lines']
  for idx,line in enumerate(lines):
   # multi-line name/address and label-value in a neighboring table cell
   for field,regexes in P.items():
    for pat in regexes:
     match=pat.search(line)
     if not match:continue
     if field=='nama_rs' and match.start()>2 and match.group(0).casefold() in ('customer','customers','hospital','pelanggan'):continue
     if field=='alamat' and re.search(r'\b(?:ip|e-?mail|web|network)\s+address\b',line,re.I):continue
     if field=='nomor_seri_unit' and re.search(r'\b(?:tube|insersi|insert|housing)\b',line[:match.end()+18],re.I) and not re.search(r'\b(?:system|main\s*unit|generator)\b',line[:match.end()+18],re.I):continue
     tail=clean(line[match.end():])
     tail=re.sub(r'^[\s:=\-*/\\\"‘’“”²¹]+','',tail)
     if field.startswith('tipe_') or field in ('nama_rs','alamat'):
      tail=re.split(r'(?i)\s+(?=(?:Serial\s+(?:Number|No\.?)|Product Number|UDI|Work Order|Device Status|Customer Contract|No\.? Kontrak)\s*[:=])',tail,1)[0]
     if tail and TRIM_NEXT.match(tail):tail=''
     if not tail and idx+1<len(lines):
      tail=clean(lines[idx+1]);ev=line+' | '+tail
     else:ev=line
     if field=='alamat' and tail and idx+2<len(lines):
      # continuation on next line only when it resembles street/city content
      nxt=clean(lines[idx+1]);
      if not TRIM_NEXT.match(nxt) and norm_line(nxt)!=norm_line(tail) and len(tail)<75 and re.search(r'\b(?:jl\.?|jalan|street|kota|kabupaten|kec\.?|kel\.?|indonesia|no\.?\d)',nxt,re.I):tail+=' '+nxt
     component=None
     if field=='nomor_seri_tabung':
      c=match.group(0).lower()
      component='HOUSING' if 'housing' in c or 'tube head' in c else ('INSERT' if 'insert' in c or 'insersi' in c else 'UNSPECIFIED')
     obj=_candidate(field,tail,pg['page'],ev,pat.pattern,component)
     if obj:
      found[field].append(obj)
      if field=='nomor_seri_tabung' and component in ('HOUSING','INSERT'):
       found['nomor_seri_housing' if component=='HOUSING' else 'nomor_seri_insert'].append(obj)
     break
   # GS1 (21) denotes an item serial number when within a UDI block.
   if re.search(r'\bUDI(?:/SystemID)?\b',line,re.I) or re.search(r'^\(21\)\s*[A-Z0-9]{3,}',line,re.I):
    section=' '.join(lines[max(0,idx-3):idx+4])
    ai21=re.search(r'\(21\)\s*([A-Z0-9]{3,35})',section,re.I)
    if ai21 and re.search(r'\bUDI\b',section,re.I):
     obj=_candidate('nomor_seri_unit',ai21.group(1),pg['page'],section,'UDI_AI21')
     if obj:found['nomor_seri_unit'].append(obj)
   # specialized context: GLOMEDA Subsystem | Model No | Serial No
   if re.search(r'\b(?:main\s*unit|collimator|generator|tube)\b',line,re.I) and idx+2<len(lines):
    joined=' '.join(lines[idx:idx+3])
    matches=re.findall(r'\b[A-Z0-9]{6,}\b',joined)
    if matches and re.search(r'\b(tube|main\s*unit)\b',joined,re.I) and re.match(r'^(?:Main\s*Unit|Tube)\b',line,re.I):
     component='UNSPECIFIED' if 'tube' in line.lower() else None
     field='nomor_seri_tabung' if component else 'nomor_seri_unit'
     obj=_candidate(field,matches[-1],pg['page'],joined,'SUBSYSTEM_TABLE',component)
     if obj:found[field].append(obj)
     if component:
      m=re.search(r'(?i)\bTube\s+([A-Z][A-Z0-9-]{2,})\s+[A-Z0-9]{4,}',joined)
      if m:
       tube=_candidate('tipe_tabung',m.group(1),pg['page'],joined,'SUBSYSTEM_TABLE')
       if tube:found['tipe_tabung'].append(tube)
 # de-dupe without losing page/candidate evidence
 result={}
 for field in FIELDS:
  unique=[];seen=set()
  for item in found[field]:
   key=(item['value'].casefold(),item['page'],item.get('component'))
   if key not in seen:seen.add(key);unique.append(item)
  result[field]=unique
 return result

def _choose_identity(field, items):
    """Choose a meaningful field value without treating different components as equal."""
    if not items:
        return None
    def rank(item):
        value=item['value']
        pat=item.get('pattern','')
        label=item.get('evidence','').split(' | ')[0].lower()
        score=0
        if field=='tipe_unit':
            score+=30 if re.search(r'unit\s*type|equipment\s*name|product\s*name|nama\s*alat|device\s*model',label,re.I) else 0
            score-=40 if re.fullmatch(r'\d+',value) else 0
            score+=8 if re.search(r'[A-Za-z]',value) and re.search(r'\d',value) else 0
        elif field=='nama_rs':
            score+=40 if re.search(r'hospital\s*name|customer\s*name|nama\s*instansi|nama\s*pelanggan|^pelanggan$',label,re.I) else 0
            score+=35 if re.search(r'(?i)\b(?:rs|rumkit|rumah sakit|hospital|klinik)\b',value) else 0
            score-=25 if re.search(r'(?i)\b(?:representative|acceptance|comment|contract|no\.? kontrak)\b',value) else 0
        elif field=='alamat':
            score+=45 if re.search(r'(?i)\b(?:jl|jalan|street|road|no\.?\s*\d)',value) else 0
            score+=8 if re.search(r'(?i)\b(?:kota|kabupaten|kec|indonesia|tangerang|pekanbaru)',value) else 0
            score-=40 if re.search(r'(?i)if applicable|kontrak|contract',value) else 0
        elif field.startswith('nomor_seri'):
            score+=20 if re.search(r'subsystem|nomor\s*seri\s*alat|serial\s*number\s*generator',pat,re.I) else 0
        score+=min(len(value),80)/100
        return score
    ordered=sorted(items,key=rank,reverse=True)
    best=ordered[0]
    if field in {'nama_rs','alamat','tipe_unit'} and rank(best)<0:
        return None
    return best['value']


def _context_uncertain(pages, rows):
    """Flag inspection items for which OCR failed to read a result.
    A line about a component is NOT evidence that it passed or failed.
    """
    uncertain=[]
    triggers=re.compile(r'(?i)\b(?:door\s+switch|door\s+contact|emergency\s+(?:status|stop)|radiation\s+(?:indicator|on\s*off)|x.?ray\s+warning|safety\s+check)\b')
    seen={(r['page'],r['text']) for r in rows}
    for page in pages:
        for line in page['lines']:
            if not triggers.search(line):continue
            if (page['page'],line[:250]) in seen:continue
            if _status_of_line(line) is not None:continue
            uncertain.append({'page':page['page'],'text':line[:250],'reason':'Safety-related inspection item has no reliably decoded result'})
    return uncertain

def _status_of_line(line):
 """Interpret explicit text result or CHECKED box, never mere option labels.

 Unchecked `☐Tidak` alongside checked `☑Baik` must NOT be FAIL.
 """
 s=clean(line)
 checked=re.findall(r'[☑☒✅✔✓]\s*([^☑☒☐□✅✔✓]+)',s)
 any_boxes=bool(re.search(r'[☑☒☐□✅✔✓]',s))
 if checked:
  normalized=' '.join(checked)
  if re.search(r'^(?:not\s+ok|not\s+pass|ng|fail|tidak|rusak)',normalized,re.I) or re.search(r'(?:^|\s)(?:fail(?:ed)?|not\s+ok|ng|rusak\s+berat|tidak\s+baik|tidak\s+dapat)',normalized,re.I):return 'FAIL'
  if re.search(r'(?:^|\s)(?:ok|pass|baik|good|bersih|alat\s+be\w*\s+dengan\s+baik)',normalized,re.I):return 'PASS'
  if re.search(r'^(?:n/?a|not\s+applicable|not\s+installed)',normalized,re.I):return 'EXCEPTION'
  return None
 if any_boxes:return None
 # OCR sometimes loses empty-box glyphs: paired OK and NG are choices, not a FAIL.
 if re.search(r'\b(?:[A-Z]?OK)\b',s,re.I) and re.search(r'\bNG\b',s,re.I):return None
 if re.search(r'\b(?:not\s+ok|not\s+pass|fail(?:ed)?|ng|rusak\s+berat|tidak\s+baik|tidak\s+dapat\s+digunakan|unsatisfactory)\s*$',s,re.I):return 'FAIL'
 if re.search(r'\b(?:pass(?:ed)?|ok|baik|good|satisfactory)\s*$',s,re.I):return 'PASS'
 if re.search(r'\b(?:n\.?a\.?|not\s+applicable|not\s+available|not\s+installed)\s*$',s,re.I):return 'EXCEPTION'
 return None

def extract_test_status(pages):
 rows=[];uncertain=[]
 for page in pages:
  for line in page['lines']:
   # do not count headings/instructions or incidental text saying "No damage" as results
   if len(line)<6 or re.search(r'^\s*(?:date|status|result|check\s*item|standard|remarks|page|note|keterangan)\s*:?$',line,re.I):continue
   status=_status_of_line(line)
   if status:
    rows.append({'page':page['page'],'text':line[:250],'status':status,'method':page['method']})
   elif re.search(r'[☐□]\s*(?:OK|NG|Baik|Tidak|N/?A|Not\s*OK)',line,re.I):
    uncertain.append({'page':page['page'],'text':line[:250],'reason':'Checkbox not reliably interpreted'})
 uncertain.extend(_context_uncertain(pages,rows))
 counts={v:sum(x['status']==v for x in rows) for v in ('PASS','FAIL','EXCEPTION')}
 # Text-only OCR cannot certify completeness even when all extracted lines are PASS.
 overall='FAIL_DETECTED' if counts['FAIL'] else 'REVIEW'
 return {'status':overall,'counts':counts,'rows':rows,'uncertain_rows':uncertain,
         'coverage_verified':False,'note':'This is evidence screening, not complete checklist certification. Manually verify any FAIL, exceptions, unread rows and unchecked items.'}

def classify_document(pages):
 head='\n'.join(p['text'] for p in pages[:3]).lower()
 if re.search(r'customer\s+acceptance\s+form|berita\s+acara\s+serah\s+terima',head):return 'CUSTOMER_ACCEPTANCE'
 if re.search(r'acceptance\s+test',head):return 'ACCEPTANCE_TEST'
 if re.search(r'functional\s+test|function\s+check|uji\s+fungsi',head):return 'UJI_FUNGSI'
 if re.search(r'install(?:ation)?\s+and\s+verification|test\s+and\s+verification',head):return 'INSTALLATION_VERIFICATION'
 if re.search(r'service\s+report',head):return 'SERVICE_REPORT'
 return 'UNKNOWN'

def parse_functional_test(path,dpi=170,force_ocr=False,include_checkboxes=True):
 pages=read_document(path,dpi=dpi,force_ocr=force_ocr)
 candidates=extract_candidates(pages)
 # Abstain on ambiguous candidates; never silently pick the first of several devices.
 identity={}
 for field,items in candidates.items():
  vals={re.sub(r'[^a-z0-9]','',x['value'].lower()) for x in items}
  identity[field]=_choose_identity(field,items)
 from src.extraction.functional_identity_refine import refine_identity
 identity,candidates=refine_identity(path,pages,identity,candidates)
 from src.extraction.functional_status_layout import enrich_test_status
 status=enrich_test_status(path,pages,extract_test_status(pages))
 if include_checkboxes and Path(path).suffix.lower()=='.pdf':
  try:
   from src.extraction.checkbox_detector import inspect_checkbox_pdf
   from src.extraction.functional_evidence_merge import merge_evidence
   checkbox_result=inspect_checkbox_pdf(path)
   status=merge_evidence(status,checkbox_result)
  except Exception as exc:
   status.setdefault('integration_warnings',[]).append(f'Checkbox inspection unavailable: {type(exc).__name__}: {exc}')
   status['status']='FAIL_DETECTED' if status.get('counts',{}).get('FAIL',0) else 'REVIEW'
   status['coverage_verified']=False
 return {'source_name':os.path.basename(str(path)), 'document_type':classify_document(pages),
         'total_pages':len(pages),'identity':identity,'candidates':candidates,
         'test_status':status,'pages':pages}
